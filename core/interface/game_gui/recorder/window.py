"""The recorder's window (PySide6; texts in the tools' language, interface/game_gui/strings.py): each emulator window's
state («Ventana 1» / "Window 1", «Ventana 2»), the
screen it is on, the screens recorded, those still to record, a note for the request, «Marcar esta pantalla» ("Mark this
screen") and «Pausar» ("Pause"). The recording runs in a thread of its own (`RecorderService.run`); the window only
reads its status."""

import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget, QMainWindow, QPushButton, QVBoxLayout,
                               QWidget)

from core.app.edition import edition
from core.interface.game_gui import strings as S


def window_text(window: dict) -> str:
    if window["screen_name"]:
        screen = window["screen_name"]
    elif window["screen"]:
        screen = S.tr(S.UNNAMED_SCREEN, groups=window["groups"], screen=window["screen"])
    else:
        screen = S.tr(S.NO_STEADY_SCREEN)
    return S.tr(S.WINDOW_STATE, label=window["label"], status=window["status"], screen=screen,
                copies=window["copies"], rejected=window["rejected"])


class RecorderWindow(QMainWindow):
    def __init__(self, service, refresh_ms: int = 300, start: bool = True):
        super().__init__()
        self.service = service
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.setWindowTitle(S.tr(S.WINDOW_TITLE, product=edition().name))
        body = QWidget()
        layout = QVBoxLayout(body)
        self.session = QLabel()
        self.windows = QLabel(S.tr(S.LOOKING))
        self.recorded = QLabel()
        self.missing_title = QLabel(S.tr(S.TO_RECORD))
        self.missing = QListWidget()
        self.note = QLineEdit()
        self.note.setPlaceholderText(S.tr(S.NOTE_HINT))
        self.note.textChanged.connect(self._note_changed)
        self.mark_button = QPushButton(S.tr(S.MARK))
        self.mark_button.clicked.connect(self.mark)
        self.pause_button = QPushButton(S.tr(S.PAUSE))
        self.pause_button.clicked.connect(self.toggle_pause)
        self.message = QLabel()
        buttons = QHBoxLayout()
        buttons.addWidget(self.mark_button)
        buttons.addWidget(self.pause_button)
        for widget in (self.session, self.windows, self.recorded, self.missing_title, self.missing, self.note):
            layout.addWidget(widget)
        layout.addLayout(buttons)
        layout.addWidget(self.message)
        self.setCentralWidget(body)
        self.resize(560, 520)
        self._requests = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(refresh_ms)
        if start:
            self.thread = threading.Thread(target=service.run, args=(self.stop,), name="recorder", daemon=True)
            self.thread.start()
        self.refresh()

    def _note_changed(self, text: str) -> None:
        self.service.note = text

    def mark(self) -> None:
        self.service.mark(self.note.text())
        self.note.clear()

    def toggle_pause(self) -> None:
        self.service.paused = not self.service.paused
        self.refresh()

    def refresh(self) -> None:
        status = self.service.status()
        self.session.setText(S.tr(S.SESSION, session=status["session"]))
        windows = status["windows"]
        self.windows.setText("\n".join(window_text(w) for w in windows) if windows else S.tr(S.WAITING))
        self.recorded.setText(S.tr(S.RECORDED, screens=status["screens"], variants=status["variants"],
                                   requests=status["requests"]))
        if status["coverage"]:
            self.missing_title.setText(S.tr(S.TO_RECORD_COUNT, missing=len(status["missing"]),
                                            total=status["coverage"]))
        else:
            self.missing_title.setText(S.tr(S.TO_RECORD_NO_LIST))
        if [self.missing.item(i).text() for i in range(self.missing.count())] != status["missing"]:
            self.missing.clear()
            self.missing.addItems(status["missing"])
        self.pause_button.setText(S.tr(S.RESUME if status["paused"] else S.PAUSE))
        if status["requests"] != self._requests:
            self._requests = status["requests"]
            if not self.service.note:
                self.note.clear()
        self.message.setText(status["message"])

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt's name
        self.timer.stop()
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        super().closeEvent(event)
