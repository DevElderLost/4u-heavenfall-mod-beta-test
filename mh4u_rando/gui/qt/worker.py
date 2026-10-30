"""Run a callable off the main thread, and a smooth progress bar driver.

    task = Task(lambda report: heavy(report))   # heavy imports (pipeline, fix) go INSIDE the callable
    task.progress.connect(...); task.stage.connect(...); task.done.connect(...); task.failed.connect(...)
    task.start()

The callable receives a `Reporter` (`report.progress(done, total)`, `report.stage(name)`); its return value comes
back in `done`, an exception's traceback in `failed`. `ProgressDriver` animates a QProgressBar with the semi-fake
`ProgressAnimator` (gui/progress.py) on a QTimer.
"""

import time
import traceback
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from ..progress import ProgressAnimator


class Reporter:
    def __init__(self, task: "Task"):
        self._task = task

    def progress(self, done: int, total: int) -> None:
        self._task.progress.emit(int(done), int(total))

    def stage(self, name: str) -> None:
        self._task.stage.emit(str(name))


class _Thread(QThread):
    def __init__(self, task: "Task"):
        super().__init__(task)
        self._task = task

    def run(self) -> None:
        task = self._task
        try:
            result = task.function(Reporter(task))
        except BaseException:  # noqa: BLE001 - everything goes to the GUI
            task.failed.emit(traceback.format_exc())
        else:
            task.done.emit(result)


class Task(QObject):
    progress = Signal(int, int)
    stage = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[[Reporter], object], parent: QObject | None = None):
        super().__init__(parent)
        self.function = function
        self._thread = _Thread(self)

    def start(self) -> None:
        self._thread.start()

    def wait(self, msecs: int = 10_000) -> bool:
        return self._thread.wait(msecs)

    def is_running(self) -> bool:
        return self._thread.isRunning()


class ProgressDriver(QObject):
    """Drives a QProgressBar (range 0..1000) with `ProgressAnimator`; `finished` fires once the bar is full."""

    finished = Signal()

    def __init__(self, bar, interval_ms: int = 30, parent: QObject | None = None):
        super().__init__(parent or bar)
        self.bar = bar
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.animator = ProgressAnimator(time.monotonic())
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self._tick)

    def start(self) -> None:
        self.animator = ProgressAnimator(time.monotonic())
        self.bar.setValue(0)
        self.timer.start()

    def push_stage(self, name: str) -> None:
        self.animator.push_stage(name)

    def set_fraction(self, done: int, total: int) -> None:
        if total:
            self.animator.set_quest_fraction(done / total)

    def _tick(self) -> None:
        self.bar.setValue(round(self.animator.tick(time.monotonic()) * 1000))
        if self.animator.finished:
            self.bar.setValue(1000)
            self.timer.stop()
            self.finished.emit()
