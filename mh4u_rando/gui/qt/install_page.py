"""The Install page: pick the two game files, see where the mod goes and what is there, install / update / remove it.

Install is the mod without the randomizer (presets "install": the player's own options from the Options page, the new
monsters always). The pieces other pages reuse live here: `Discovery` and `Jobs` (the seams tests inject),
`resolve_request`, `confirm_request`, `InstallJob` (one run in a worker, reported on signals) and `ProgressPanel`.
"""

from __future__ import annotations

import dataclasses
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from ...edition import edition
from ...install import find_games
from ...install.targets import mods_folder_for
from ..i18n import T
from ..strings import REGIONS, install_error
from . import jobs
from .page import Page
from .state import AppState
from .translate import translator
from .worker import ProgressDriver, Reporter, Task

TITLE = T("Instalar", "Install")

# ---- texts ----------------------------------------------------------------------------------------------------------

T_FILES = T("Archivos del juego", "Game files")
T_FILES_HELP = T("Se leen sin modificarlos. Hacen falta los dos, europeos o americanos y ya descifrados (.3ds, .cia o "
                 "los comprimidos de Azahar). El mod se instala para la región de tu Monster Hunter 4 Ultimate.",
                 "They are only read, never changed. Both are needed, European or American and already decrypted "
                 "(.3ds, .cia or Azahar's compressed files). The mod is installed for the region of your Monster "
                 "Hunter 4 Ultimate.")
T_MH4U = T("Monster Hunter 4 Ultimate", "Monster Hunter 4 Ultimate")
T_MHGEN = T("Monster Hunter Generations", "Monster Hunter Generations")
T_CHOOSE = T("Elegir…", "Choose…")
T_NOT_CHOSEN = T("Sin elegir", "Not chosen")
T_CHECKING = T("Comprobando…", "Checking…")
T_OK = T("✓ Correcto", "✓ Valid")
T_BAD = T("✗ {problem}", "✗ {problem}")
T_OK_REGION = T("✓ Correcto · {region}", "✓ Valid · {region}")

# Where a game file was found (find_games.Candidate.source) and the other files found
T_SEARCHING = T("Buscando tus juegos…", "Looking for your games…")
T_FOUND = {
    find_games.EMULATOR_FOLDER: T("Encontrado en la lista de juegos de {place}.", "Found in {place}'s game list."),
    find_games.EMULATOR_INSTALLED: T("Encontrado entre los juegos instalados de {place}.",
                                     "Found among the games installed in {place}."),
    find_games.USER_FOLDER: T("Encontrado en tu carpeta {place}.", "Found in your {place} folder."),
}
T_OTHERS = T("Otros archivos encontrados", "Other files found")

# Why Install is disabled (one sentence per cause, shown beside the button)
T_WHY_NO_MH4U = T("Falta el archivo de Monster Hunter 4 Ultimate.", "The Monster Hunter 4 Ultimate file is missing.")
T_WHY_BAD_MH4U = T("El archivo de Monster Hunter 4 Ultimate no sirve (mira el motivo arriba).",
                   "The Monster Hunter 4 Ultimate file cannot be used (see the reason above).")
T_WHY_NO_MHGEN = T("Falta el archivo de Monster Hunter Generations.", "The Monster Hunter Generations file is missing.")
T_WHY_BAD_MHGEN = T("El archivo de Monster Hunter Generations no sirve (mira el motivo arriba).",
                    "The Monster Hunter Generations file cannot be used (see the reason above).")
T_WHY_CHECKING = T("Comprobando los archivos del juego…", "Checking the game files…")
T_WHY_NO_EMU = T("No hay un emulador donde instalar: elige su carpeta.",
                 "There is no emulator to install into: choose its folder.")
T_WHY_NO_SD = T("Elige primero la tarjeta SD de la 3DS.", "Choose the 3DS SD card first.")

T_DEST = T("Destino", "Destination")
T_EMU_FOLDER = T("Elegir carpeta…", "Choose folder…")
T_NO_EMU = T("No se encontró ningún emulador (Azahar, Citra, Lime3DS). Elige su carpeta.",
             "No emulator found (Azahar, Citra, Lime3DS). Choose its folder.")
T_SD = T("Tarjeta SD de la 3DS", "3DS SD card")
T_SD_PLACEHOLDER = T("— elige una tarjeta —", "— choose a card —")
T_SD_HELP = T("Se copia a la carpeta luma de la tarjeta (Luma3DS).", "Copied to the card's luma folder (Luma3DS).")
T_FTP = T("Exportar para FTP…", "Export for FTP…")
T_FTP_HELP = T(
    "Sin sacar la tarjeta: exporta y copia por FTP.\n"
    "1. Copia mh4u_luma.pack a la raíz de la tarjeta.\n"
    "2. Copia 3ds/mh4u_installer.3dsx a la carpeta /3ds/.\n"
    "3. Ejecuta el instalador desde el Homebrew Launcher.\n"
    "En Luma activa «Enable game patching» (mantén SELECT al encender).",
    "Without removing the card: export and copy over FTP.\n"
    "1. Copy mh4u_luma.pack to the card's root.\n"
    "2. Copy 3ds/mh4u_installer.3dsx to the /3ds/ folder.\n"
    "3. Run the installer from the Homebrew Launcher.\n"
    "In Luma enable \"Enable game patching\" (hold SELECT when powering on).")

T_INSTALL = T("Instalar", "Install")
T_UPDATE = T("Actualizar", "Update")
T_UNINSTALL = T("Desinstalar", "Uninstall")
T_LOG = T("Registro", "Log")

T_ASK_RANDOM = T(
    "Ahí hay un juego randomizado (semilla {seed}). Si sigues, se sustituye por la instalación normal. ¿Continuar?",
    "A randomized game is installed there (seed {seed}). Continuing replaces it with the normal install. Continue?")
T_ASK_UNKNOWN = T(
    "Esa carpeta tiene archivos que no son de este instalador. Si sigues, se reemplazan. ¿Continuar?",
    "That folder holds files that are not from this installer. Continuing replaces them. Continue?")
T_ASK_UNINSTALL = T(f"Se quitará {edition().name} de esa carpeta. ¿Continuar?",
                    f"{edition().name} will be removed from that folder. Continue?")
T_ASK_TITLE = T("Confirmar", "Confirm")

T_DONE_EMU = T("Listo. Reinicia la emulación para jugar.", "Done. Restart the emulation to play.")
T_DONE_SD = T(
    "Listo. Pon la tarjeta en la 3DS y activa «Enable game patching» en Luma (mantén SELECT al encender).",
    "Done. Put the card in the 3DS and enable \"Enable game patching\" in Luma (hold SELECT when powering on).")
T_DONE_EXPORT = T("Exportado en {folder}. Sigue los 3 pasos de arriba.",
                  "Exported to {folder}. Follow the 3 steps above.")
T_DONE_REMOVED = T("Desinstalado.", "Uninstalled.")
T_FAILED = T("No se pudo completar: {reason}", "Could not finish: {reason}")
T_NO_TARGET = T("Elige primero dónde instalar.", "Choose where to install first.")
T_FILES_FIRST = T("Elige primero los archivos del juego en la página Instalar.",
                  "Choose the game files on the Install page first.")

T_STATE_EMPTY = T("Vacío: no hay nada instalado.", "Empty: nothing is installed.")
T_STATE_OURS = T(f"{edition().name} instalado ({{kind}}{{seed}}).",
                 f"{edition().name} installed ({{kind}}{{seed}}).")
T_KIND_INSTALL = T("instalación normal", "normal install")
T_KIND_RANDOMIZER = T("randomizer", "randomizer")
T_STATE_UNKNOWN = T("Hay archivos de otro mod. Se pedirá confirmación antes de reemplazarlos.",
                    "There are files from another mod. You will be asked before they are replaced.")

STAGE_NAMES = {
    "start": T("Preparando…", "Preparing…"),
    "rom": T("Leyendo el juego…", "Reading the game…"),
    "quests": T("Preparando misiones…", "Preparing quests…"),
    "write": T("Escribiendo archivos…", "Writing files…"),
    "equipment": T("Equipo…", "Equipment…"),
    "install": T("Copiando…", "Copying…"),
    "done": T("Listo", "Done"),
}

_PROBLEM_WORDS = {
    "the file was not found": T("no se encontró el archivo", "the file was not found"),
    "(title ": T("(título ", "(title "),     # after the refusal of a game the mod does not know
}


def _problem_words() -> dict:
    """The English texts a problem may hold, with their translations (the game file refusals by kind)."""
    from ...exefs.containers import MESSAGES
    from ...install.build import GAME_PROBLEMS
    from ..strings import EXTRACT_ERRORS
    from ..strings import GAME_PROBLEMS as TRANSLATIONS
    return {**_PROBLEM_WORDS, **{MESSAGES[kind]: text for kind, text in EXTRACT_ERRORS.items()},
            **{GAME_PROBLEMS[kind]: text for kind, text in TRANSLATIONS.items()}}

# ---- seams ----------------------------------------------------------------------------------------------------------


@dataclass
class Discovery:
    """What is found on this machine; tests pass their own."""

    emulator_targets: Callable[[], list] | None = None
    sd_cards: Callable[[], list] | None = None
    game_finder: Callable[[], find_games.Found] | None = None

    def emulators(self) -> list:
        if self.emulator_targets is not None:
            return list(self.emulator_targets())
        from ...install.targets import emulator_targets
        return emulator_targets()

    def cards(self) -> list:
        if self.sd_cards is not None:
            return list(self.sd_cards())
        from ...install.targets import sd_cards
        return sd_cards()

    def games(self, stop: threading.Event | None = None) -> find_games.Found:
        """The game files found in the emulators and the player's folders (a worker's job: it reads disks)."""
        if self.game_finder is not None:
            return self.game_finder()
        return find_games.find(emulators=self.emulators(), stop=stop)


@dataclass
class Failure:
    problems: list[str]


@dataclass
class ExportOutcome:
    pack: Path
    app: Path | None
    folder: Path


class Jobs:
    """The work run in workers (heavy imports inside); tests subclass it to record or replace calls."""

    def check(self, rom: Path | None, mhgen: Path | None) -> list[str]:
        from ...install.build import check_inputs
        return check_inputs(rom, mhgen)

    def install(self, request: jobs.InstallRequest, report: Reporter):
        return jobs.run_install(request, report)

    def uninstall(self, request: jobs.InstallRequest, report: Reporter):
        return jobs.run_uninstall(request, report)

    def export(self, request: jobs.InstallRequest, dest: Path, report: Reporter) -> ExportOutcome:
        from ...install.build import build
        from ...install.console import export_ftp
        result = build(request.rom, request.mhgen_rom, request.settings, console=True, kind=request.kind,
                       progress=report.progress, stage=report.stage)
        code = result.checksum.code if result.checksum else ""
        report.stage("install")
        pack, app = export_ftp(result.output_dir, dest, request.kind, result.seed, code,
                               request.settings.for_console().to_dict())
        jobs.discard_build(request, result.output_dir)
        report.stage("done")
        return ExportOutcome(pack, app, Path(dest))


# ---- file and message boxes (module functions so tests can answer them) ----------------------------------------------

def _file_filter() -> str:
    from ...exefs.containers import EXTENSIONS
    return "3DS (" + " ".join("*" + suffix for suffix in EXTENSIONS) + ");;*"


FILE_FILTER = _file_filter()


def choose_file(parent: QWidget, title: str) -> str:
    path, _ = QFileDialog.getOpenFileName(parent, title, "", FILE_FILTER)
    return path


def choose_folder(parent: QWidget, title: str) -> str:
    return QFileDialog.getExistingDirectory(parent, title)


def ask(parent: QWidget, text: str) -> bool:
    answer = QMessageBox.question(parent, translator.text(T_ASK_TITLE), text,
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    return answer == QMessageBox.StandardButton.Yes


# ---- requests -------------------------------------------------------------------------------------------------------

def rom_title(state: AppState) -> str:
    """The mod folder's title for the MH4U file chosen (European when it cannot be read yet)."""
    from ...exefs import titles
    found = titles.mod_title_of_file(state.rom_path) if state.rom_path else None
    return found or titles.mod_title(titles.EUR)


def resolve_target(state: AppState, discovery: Discovery) -> Path | None:
    """Where the mod goes now: the SD card chosen (3DS), or the emulator's mod folder of the game's region ("auto":
    the newest emulator found)."""
    try:
        return jobs.request_from_state(state, None, "install", emulators=discovery.emulators).target
    except jobs.NoTarget:
        return None


def resolve_request(state: AppState, discovery: Discovery, kind: str = "install") -> jobs.InstallRequest:
    """The request for the player's current choices (raises jobs.NoTarget)."""
    from ...presets import install_settings
    return jobs.request_from_state(state, install_settings(state.personal), kind, emulators=discovery.emulators)


def confirm_request(parent: QWidget, request: jobs.InstallRequest) -> jobs.InstallRequest | None:
    """Ask before replacing what is not a plain install of this program; None when the player declines."""
    from ...install.deploy import State
    state = jobs.target_state(request)
    if state is State.UNKNOWN:
        if not ask(parent, translator.text(T_ASK_UNKNOWN)):
            return None
        return dataclasses.replace(request, replace_unknown=True)
    if state is State.OURS:
        marker = jobs.installed_marker(request) or {}
        if marker.get("kind") == "randomizer":
            if not ask(parent, T_ASK_RANDOM.format(translator.language, seed=marker.get("seed", ""))):
                return None
    return request


def describe_target(request: jobs.InstallRequest, language: str) -> str:
    """What is in the install folder, as a sentence."""
    from ...install.deploy import State
    state = jobs.target_state(request)
    if state is State.EMPTY:
        return T_STATE_EMPTY(language)
    if state is State.UNKNOWN:
        return T_STATE_UNKNOWN(language)
    marker = jobs.installed_marker(request) or {}
    kind = (T_KIND_RANDOMIZER if marker.get("kind") == "randomizer" else T_KIND_INSTALL)(language)
    seed = f", {marker['seed']}" if marker.get("seed") else ""
    code = f" {marker['checksum']}" if marker.get("checksum") else ""
    return T_STATE_OURS.format(language, kind=kind, seed=seed + code)


def same_path(a: str | Path, b: str | Path) -> bool:
    """`a` and `b` name the same file (as the file system compares them: case on Windows, ..)."""
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def file_region(path: str) -> T | None:
    """The region (Europe / America) of a game file the mod knows, for the label beside its picker."""
    from ...exefs import titles
    kind = titles.file_kind(path)
    return REGIONS[kind[1]] if kind else None


def _describe_problem(problem: str, language: str, words: dict) -> str:
    """One refusal in the player's language: a whole message of the install path (strings.INSTALL_ERRORS), else its
    known pieces (a game file's refusals by kind)."""
    translated = install_error(problem, language)
    if translated is not None:
        return translated
    for english, text in words.items():
        problem = problem.replace(english, text(language))
    return problem


def describe_failure(failure: Failure | str, language: str) -> str:
    words = _problem_words()
    if isinstance(failure, Failure):
        return "; ".join(_describe_problem(problem, language, words) for problem in failure.problems)
    return _describe_problem(failure, language, words)


# ---- one run ---------------------------------------------------------------------------------------------------------

class InstallJob(QObject):
    """Install, update, uninstall or export, one at a time (the AppState's busy claim). `finished(ok, payload)`:
    the outcome, or a `Failure` / the error's last line."""

    stage = Signal(str)
    progress = Signal(int, int)
    finished = Signal(bool, object)

    def __init__(self, state: AppState, runner: Jobs | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.state = state
        self.runner = runner or Jobs()
        self._task: Task | None = None
        self.log: list[str] = []

    def start(self, action: str, request: jobs.InstallRequest, dest: Path | None = None) -> bool:
        if not self.state.claim():
            return False
        self.log = []
        runner = self.runner

        def work(report: Reporter):
            from ...exefs.rebase import RebaseError
            from ...exefs.versions import UnsupportedVersion
            from ...install.build import InputsError
            from ...install.deploy import ForeignContent, UnsafeTarget
            try:
                if action == "uninstall":
                    return runner.uninstall(request, report)
                if action == "export":
                    return runner.export(request, dest, report)
                return runner.install(request, report)
            except InputsError as error:
                return Failure(error.problems)
            except (ForeignContent, UnsafeTarget, UnsupportedVersion, RebaseError) as error:
                return Failure([str(error)])    # an unknown game version: INSTALL_ERRORS says it in his language

        self._task = Task(work, self)
        self._task.stage.connect(self._on_stage)
        self._task.progress.connect(self.progress)
        self._task.done.connect(self._on_done)
        self._task.failed.connect(self._on_failed)
        self._task.start()
        return True

    def wait(self, msecs: int = 10_000) -> bool:
        return self._task.wait(msecs) if self._task else True

    def _on_stage(self, name: str) -> None:
        self.log.append(name)
        self.stage.emit(name)

    def _on_done(self, outcome) -> None:
        self.state.release()
        self.finished.emit(not isinstance(outcome, Failure), outcome)

    def _on_failed(self, text: str) -> None:
        self.state.release()
        self.log.append(text)
        lines = [line for line in text.strip().splitlines() if line.strip()]
        self.finished.emit(False, lines[-1] if lines else text)


# ---- widgets ---------------------------------------------------------------------------------------------------------

def card(title: T | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 14, 18, 14)
    layout.setSpacing(8)
    if title is not None:
        heading = QLabel()
        heading.setProperty("role", "subtitle")
        translator.bind(heading, heading.setText, title)
        layout.addWidget(heading)
    return frame, layout


def label(text: T | Callable[[str], str], role: str | None = None) -> QLabel:
    widget = QLabel()
    widget.setWordWrap(True)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if role:
        widget.setProperty("role", role)
    translator.bind(widget, widget.setText, text)
    return widget


def button(text: T, role: str | None = None) -> QPushButton:
    widget = QPushButton()
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if role:
        widget.setProperty("role", role)
    translator.bind(widget, widget.setText, text)
    return widget


class ProgressPanel(QWidget):
    """A progress bar, the stage text and (optionally) a collapsible log; driven by an `InstallJob`'s signals."""

    def __init__(self, with_log: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(10)
        layout.addWidget(self.bar)
        self.driver = ProgressDriver(self.bar, parent=self)
        self.stage_name = ""
        self.stage_label = QLabel()
        self.stage_label.setProperty("role", "muted")
        layout.addWidget(self.stage_label)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self._message_text: Callable[[str], str] = lambda _lang: ""
        self.log_toggle = button(T_LOG)
        self.log_toggle.setCheckable(True)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(140)
        self.log_view.setVisible(False)
        self.log_toggle.toggled.connect(self.log_view.setVisible)
        if with_log:
            layout.addWidget(self.log_toggle, 0, Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(self.log_view)
        else:
            self.log_toggle.hide()
        self.reset()
        translator.bind(self, lambda _s: self._show_stage(), lambda lang: lang)

    def reset(self) -> None:
        self.bar.setValue(0)
        self.stage_name = ""
        self._message_text = lambda _lang: ""
        self.log_view.clear()
        self._show_stage()
        self.message.setText("")

    def begin(self) -> None:
        self.reset()
        self.driver.start()

    def on_stage(self, name: str) -> None:
        self.stage_name = name
        self.driver.push_stage(name)
        self.log_view.appendPlainText(name)
        self._show_stage()

    def on_progress(self, done: int, total: int) -> None:
        self.driver.set_fraction(done, total)

    def show_message(self, text: Callable[[str], str], error: bool = False) -> None:
        self._message_text = text
        self.message.setProperty("role", "error" if error else "muted")
        self.message.setStyleSheet("color: #d9534f;" if error else "")
        self.message.setText(text(translator.language))

    def stop(self) -> None:
        self.driver.timer.stop()
        self.bar.setValue(0)

    def _show_stage(self) -> None:
        name = STAGE_NAMES.get(self.stage_name)
        self.stage_label.setText(name(translator.language) if name else self.stage_name)
        self.message.setText(self._message_text(translator.language))


class InstallPage(Page):
    title = TITLE

    def __init__(self, state: AppState, finder: Discovery | None = None, runner: Jobs | None = None):
        super().__init__()
        self.state = state
        self.finder = finder or Discovery()
        self.runner = runner or Jobs()
        self.job = InstallJob(state, self.runner, self)
        self._tasks: list[Task] = []
        self._check_serial = 0
        self._problems: dict[str, list[str] | None] = {"rom": None, "mhgen": None}   # None: not checked yet
        self._status_updaters: list[Callable[[], None]] = []
        self._targets: list = []
        self._action, self._request, self._dest = "install", None, None
        self._found: dict[str, list[find_games.Candidate]] = {"rom": [], "mhgen": []}   # what the search found
        self._found_labels: dict[str, QLabel] = {}
        self._found_combos: dict[str, QComboBox] = {}
        self._searching = False
        self._stop_search = threading.Event()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)
        body = QWidget()
        body.setObjectName("page")
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)
        heading = label(TITLE, "title")
        layout.addWidget(heading)

        self._build_files(layout)
        self._build_destination(layout)
        self._build_run(layout)
        layout.addStretch(1)

        self.job.stage.connect(self.progress.on_stage)
        self.job.progress.connect(self.progress.on_progress)
        self.job.finished.connect(self._finished)
        state.changed.connect(self._state_changed)
        self.refresh()
        self._validate()
        self._find_games()

    # -- construction
    def _build_files(self, layout: QVBoxLayout) -> None:
        frame, box = card(T_FILES)
        box.addWidget(label(T_FILES_HELP, "muted"))
        self.rom_edit, self.rom_status = self._file_row(box, T_MH4U, "rom")
        if self.needs_mhgen:
            self.mhgen_edit, self.mhgen_status = self._file_row(box, T_MHGEN, "mhgen")
        else:   # an edition without MH Generations (edition.json needs_mhgen): the row is made, never shown
            self._mhgen_row = QWidget()
            self.mhgen_edit, self.mhgen_status = self._file_row(QVBoxLayout(self._mhgen_row), T_MHGEN, "mhgen")
        layout.addWidget(frame)

    def _file_row(self, box: QVBoxLayout, title: T, which: str) -> tuple[QLineEdit, QLabel]:
        box.addWidget(label(title))
        row = QHBoxLayout()
        edit = QLineEdit()
        edit.setReadOnly(True)
        translator.bind(edit, edit.setPlaceholderText, T_NOT_CHOSEN)
        pick = button(T_CHOOSE)
        pick.clicked.connect(lambda: self._pick_file(which, title))
        row.addWidget(edit, 1)
        row.addWidget(pick)
        box.addLayout(row)
        status = label(lambda _lang: "", "muted")
        box.addWidget(status)
        found = label(lambda _lang: "", "muted")      # where the search found this file
        box.addWidget(found)
        others = QComboBox()                          # the other files it found, when there are some
        translator.bind(others, others.setPlaceholderText, T_OTHERS)
        others.activated.connect(lambda index: self._other_picked(which, index))
        others.hide()
        box.addWidget(others)
        self._found_labels[which], self._found_combos[which] = found, others
        self._status_updaters.append(lambda: self._show_file_status(which, status))
        self._status_updaters.append(lambda: self._show_found(which))
        return edit, status

    def _build_destination(self, layout: QVBoxLayout) -> None:
        frame, box = card(T_DEST)
        self.dest_stack = QStackedWidget()
        # emulator
        emulator = QWidget()
        e_box = QVBoxLayout(emulator)
        e_box.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.emulator_combo = QComboBox()
        self.emulator_combo.activated.connect(self._emulator_picked)
        self.emulator_pick = button(T_EMU_FOLDER)
        self.emulator_pick.clicked.connect(self._pick_emulator_folder)
        row.addWidget(self.emulator_combo, 1)
        row.addWidget(self.emulator_pick)
        e_box.addLayout(row)
        self.emulator_note = label(lambda _lang: "", "muted")
        e_box.addWidget(self.emulator_note)
        self.dest_stack.addWidget(emulator)
        # 3DS
        console = QWidget()
        c_box = QVBoxLayout(console)
        c_box.setContentsMargins(0, 0, 0, 0)
        c_box.addWidget(label(T_SD))
        row = QHBoxLayout()
        self.sd_combo = QComboBox()
        self.sd_combo.activated.connect(self._sd_picked)
        self.sd_pick = button(T_CHOOSE)
        self.sd_pick.clicked.connect(self._pick_sd_folder)
        row.addWidget(self.sd_combo, 1)
        row.addWidget(self.sd_pick)
        c_box.addLayout(row)
        c_box.addWidget(label(T_SD_HELP, "muted"))
        c_box.addWidget(label(T_FTP_HELP, "muted"))
        self.export_button = button(T_FTP)
        self.export_button.clicked.connect(self.export_ftp)
        c_box.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.dest_stack.addWidget(console)
        box.addWidget(self.dest_stack)
        self.contents = label(lambda _lang: "")
        box.addWidget(self.contents)
        layout.addWidget(frame)

    def _build_run(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.run_button = button(T_INSTALL, "primary")
        self.run_button.setMinimumHeight(44)
        self.run_button.clicked.connect(self.run)
        self.uninstall_button = button(T_UNINSTALL)
        self.uninstall_button.setMinimumHeight(44)
        self.uninstall_button.clicked.connect(self.uninstall)
        row.addWidget(self.run_button, 1)
        row.addWidget(self.uninstall_button)
        layout.addLayout(row)
        self.run_hint = label(lambda _lang: "", "muted")   # why Install is disabled
        self.run_hint.hide()
        layout.addWidget(self.run_hint)
        self.progress = ProgressPanel()
        layout.addWidget(self.progress)

    # -- Page hooks
    def on_shown(self) -> None:
        self.refresh()

    def set_platform(self, console: bool) -> None:
        super().set_platform(console)
        self.dest_stack.setCurrentIndex(1 if console else 0)
        self.refresh()

    def retranslate(self) -> None:
        self._update_texts()

    # -- finding the games (a worker: the window never waits for the disks)
    def _path(self, which: str) -> str:
        return self.state.rom_path if which == "rom" else self.state.mhgen_rom_path

    def _set_path(self, which: str, path: str) -> None:
        if which == "rom":
            self.state.rom_path = path
        else:
            self.state.mhgen_rom_path = path

    def _find_games(self) -> None:
        """Fill the pickers that are empty, or whose saved file is gone, with the games found in the emulators and the
        player's folders (install/find_games.py): the best one of each, the others in the picker's list. A picker the
        player fills meanwhile is left alone."""
        started = {"rom": self.state.rom_path, "mhgen": self.state.mhgen_rom_path}
        finder, stop = self.finder, self._stop_search

        def work(report):
            gone = [which for which, path in started.items() if not path or not Path(path).is_file()]
            return gone, (finder.games(stop) if gone else None)

        self._searching = not all(started.values())
        task = Task(work, self)
        self._tasks.append(task)
        task.done.connect(lambda result: self._games_found(result, started, task))
        task.failed.connect(lambda _text: self._games_found(([], None), started, task))
        task.start()
        self._update_texts()

    def _games_found(self, result, started: dict[str, str], task: Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        self._searching = False
        gone, found = result
        for which in gone if found is not None else []:
            candidates = list(found.mh4u if which == "rom" else found.mhgen)
            self._found[which] = candidates
            if candidates and self._path(which) == started[which]:
                self._set_path(which, str(candidates[0].path))
        self._update_texts()
        self._update_buttons()

    def _show_found(self, which: str) -> None:
        """Beside a picker: where its file was found, and the list of the other files found."""
        language, path = translator.language, self._path(which)
        candidates = self._found[which]
        chosen = next((i for i, c in enumerate(candidates) if path and same_path(c.path, path)), -1)
        if chosen >= 0:
            text = T_FOUND[candidates[chosen].source].format(language, place=candidates[chosen].place)
        else:
            text = T_SEARCHING(language) if self._searching and not path else ""
        note, combo = self._found_labels[which], self._found_combos[which]
        note.setText(text)
        note.setVisible(bool(text))
        combo.blockSignals(True)
        combo.clear()
        for candidate in candidates:
            combo.addItem(f"{candidate.path.name} — {REGIONS[candidate.region](language)} · {candidate.place}",
                          str(candidate.path))
        combo.setCurrentIndex(chosen)
        combo.blockSignals(False)
        combo.setVisible(len(candidates) > 1)

    def _other_picked(self, which: str, index: int) -> None:
        path = self._found_combos[which].itemData(index)
        if path:
            self._set_path(which, str(path))

    def on_close(self) -> None:
        """The window is closing: end the search and wait for the workers (Qt aborts if a thread outlives its
        object)."""
        self._stop_search.set()
        for task in list(self._tasks):
            task.wait(3000)

    # -- why Install is disabled
    def _blockers(self, has_target: bool) -> list[T]:
        """The causes, in order, that keep Install from being offered now (none while a task runs: the progress
        panel says what is going on)."""
        if self.state.busy:
            return []
        reasons = []
        for which, missing, bad in (("rom", T_WHY_NO_MH4U, T_WHY_BAD_MH4U), ("mhgen", T_WHY_NO_MHGEN, T_WHY_BAD_MHGEN)):
            if which == "mhgen" and not self.needs_mhgen:
                continue
            problems = self._problems[which]
            if not self._path(which):
                reasons.append(missing)
            elif problems is None:
                if T_WHY_CHECKING not in reasons:
                    reasons.append(T_WHY_CHECKING)
            elif problems:
                reasons.append(bad)
        if not has_target:
            reasons.append(T_WHY_NO_SD if self.state.console else T_WHY_NO_EMU)
        return reasons

    def _update_hint(self, has_target: bool | None = None) -> None:
        if has_target is None:
            has_target = resolve_target(self.state, self.finder) is not None
        text = " ".join(reason(translator.language) for reason in self._blockers(has_target))
        self.run_hint.setText(text)
        self.run_hint.setVisible(bool(text))

    # -- state
    def _state_changed(self, key: str) -> None:
        if key in ("rom_path", "mhgen_rom_path"):
            self._validate()
            self._update_buttons()
        elif key == "busy":
            self._update_buttons()
        elif key in ("target", "sd_root", "console"):
            self.refresh()

    def refresh(self) -> None:
        """Re-read what is found (emulators, cards, the update) and what is in the install folder."""
        self._targets = self.finder.emulators()
        self._fill_emulators()
        self._fill_cards()
        self._update_texts()
        self._update_buttons()

    def _fill_emulators(self) -> None:
        combo = self.emulator_combo
        combo.blockSignals(True)
        combo.clear()
        title = rom_title(self.state)
        for target in self._targets:
            combo.addItem(f"{target.name} — {target.mods_dir(title)}", str(target.mods_dir(title)))
        chosen = self.state.target
        if chosen and chosen != "auto":
            chosen = str(mods_folder_for(chosen, title))   # an earlier choice may be the other region's folder
            index = combo.findData(chosen)
            if index < 0:
                combo.addItem(str(chosen), chosen)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
        elif combo.count():
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _fill_cards(self) -> None:
        combo = self.sd_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(translator.text(T_SD_PLACEHOLDER), "")
        for card_path in self.finder.cards():
            combo.addItem(str(card_path), str(card_path))
        if self.state.sd_root:
            index = combo.findData(self.state.sd_root)
            if index < 0:
                combo.addItem(self.state.sd_root, self.state.sd_root)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _emulator_picked(self, index: int) -> None:
        data = self.emulator_combo.itemData(index)
        self.state.target = "auto" if index == 0 and self._targets else str(data)
        self.refresh()

    def _sd_picked(self, index: int) -> None:
        self.state.sd_root = str(self.sd_combo.itemData(index) or "")
        self.refresh()

    def _pick_emulator_folder(self) -> None:
        folder = choose_folder(self, translator.text(T_EMU_FOLDER))
        if folder:
            self.state.target = str(mods_folder_for(folder, rom_title(self.state)))
            self.refresh()

    def _pick_sd_folder(self) -> None:
        folder = choose_folder(self, translator.text(T_SD))
        if folder:
            self.state.sd_root = folder
            self.refresh()

    def _pick_file(self, which: str, title: T) -> None:
        path = choose_file(self, translator.text(title))
        if not path:
            return
        if which == "rom":
            self.state.rom_path = path
        else:
            self.state.mhgen_rom_path = path

    # -- validation of the game files (a worker: opening a .3ds takes a moment)
    def _validate(self) -> None:
        rom, mhgen = self.state.rom_path, self.state.mhgen_rom_path
        self.rom_edit.setText(rom)
        self.mhgen_edit.setText(mhgen)
        self._check_serial += 1
        serial = self._check_serial
        if not rom and not mhgen:
            self._problems = {"rom": None, "mhgen": None}
            self._update_texts()
            return
        self._problems = {"rom": None if rom else [], "mhgen": None if mhgen else []}
        task = Task(lambda report: self.runner.check(Path(rom) if rom else None, Path(mhgen) if mhgen else None), self)
        self._tasks.append(task)
        task.done.connect(lambda problems: self._checked(serial, problems, task))
        task.failed.connect(lambda text: self._checked(serial, [text.strip().splitlines()[-1]], task))
        task.start()
        self._update_texts()

    def _checked(self, serial: int, problems: list[str], task: Task) -> None:
        if task in self._tasks:
            self._tasks.remove(task)
        if serial != self._check_serial:
            return
        rom, mhgen = bool(self.state.rom_path), bool(self.state.mhgen_rom_path)
        mine = [p for p in problems if p.startswith("Monster Hunter 4 Ultimate")]
        other = [p for p in problems if p not in mine]
        self._problems = {"rom": mine if rom else [], "mhgen": other if mhgen else []}
        self._update_texts()
        self._update_buttons()

    @property
    def needs_mhgen(self) -> bool:
        """MH Generations' game is asked for (edition.json `needs_mhgen`)."""
        return edition().needs_mhgen

    @property
    def files_ok(self) -> bool:
        needed = ("rom", "mhgen") if self.needs_mhgen else ("rom",)
        return all(self._problems[k] == [] for k in needed) and all(self._path(k) for k in needed)

    def _show_file_status(self, which: str, widget: QLabel) -> None:
        language = translator.language
        path = self.state.rom_path if which == "rom" else self.state.mhgen_rom_path
        problems = self._problems[which]
        if not path:
            text = T_NOT_CHOSEN(language)
        elif problems is None:
            text = T_CHECKING(language)
        elif problems:
            text = T_BAD.format(language, problem=describe_failure(Failure(problems), language))
        else:
            text = T_OK(language)
            region = file_region(path)
            if region:
                text = T_OK_REGION.format(language, region=region(language))
        widget.setText(text)

    def _update_texts(self) -> None:
        for update in self._status_updaters:
            update()
        language = translator.language
        if not self._targets and not self.console and self.state.target == "auto":
            self.emulator_note.setText(T_NO_EMU(language))
        else:
            self.emulator_note.setText("")
        try:
            request = resolve_request(self.state, self.finder)
        except jobs.NoTarget:
            self.contents.setText("")
        else:
            self.contents.setText(describe_target(request, language))
        self.run_button.setText((T_UPDATE if self.is_installed else T_INSTALL)(language))
        self._update_hint()

    # -- actions
    @property
    def is_installed(self) -> bool:
        """The mod is installed at the current destination."""
        try:
            request = resolve_request(self.state, self.finder)
        except jobs.NoTarget:
            return False
        return jobs.installed_marker(request) is not None

    def _update_buttons(self) -> None:
        idle = not self.state.busy
        installed = self.is_installed
        has_target = resolve_target(self.state, self.finder) is not None
        self.run_button.setText(translator.text(T_UPDATE if installed else T_INSTALL))
        self.run_button.setEnabled(idle and self.files_ok and has_target)
        self.uninstall_button.setVisible(installed)
        self.uninstall_button.setEnabled(idle)
        self.export_button.setEnabled(idle and self.files_ok)
        for widget in (self.emulator_pick, self.sd_pick, self.emulator_combo, self.sd_combo):
            widget.setEnabled(idle)
        self._update_hint(has_target)

    def run(self) -> None:
        """Install or update."""
        try:
            request = resolve_request(self.state, self.finder)
        except jobs.NoTarget:
            self.progress.show_message(T_NO_TARGET, error=True)
            return
        request = confirm_request(self, request)
        if request is not None:
            self._start("install", request)

    def uninstall(self) -> None:
        try:
            request = resolve_request(self.state, self.finder)
        except jobs.NoTarget:
            self.progress.show_message(T_NO_TARGET, error=True)
            return
        if ask(self, translator.text(T_ASK_UNINSTALL)):
            self._start("uninstall", request)

    def export_ftp(self) -> None:
        folder = choose_folder(self, translator.text(T_FTP))
        if not folder:
            return
        try:
            request = dataclasses.replace(resolve_request(self.state, self.finder), console=True)
        except jobs.NoTarget:
            from ...presets import install_settings
            request = jobs.InstallRequest(Path(self.state.rom_path),
                                          Path(self.state.mhgen_rom_path) if self.state.mhgen_rom_path else None,
                                          install_settings(self.state.personal), "install", True, Path(folder),
                                          rom_title(self.state))
        self._start("export", request, Path(folder))

    def _start(self, action: str, request: jobs.InstallRequest, dest: Path | None = None) -> None:
        self._action = action
        self._request = request
        self._dest = dest
        self.progress.begin()
        if not self.job.start(action, request, dest):
            self.progress.stop()
            return
        self._update_buttons()

    def _finished(self, ok: bool, payload) -> None:
        self._update_buttons()
        self._update_texts()
        if not ok:
            self.progress.stop()
            self.progress.show_message(
                lambda lang: T_FAILED.format(lang, reason=describe_failure(payload, lang)), error=True)
            return
        self.progress.on_stage("done")
        if self._action == "uninstall":
            self.progress.show_message(T_DONE_REMOVED)
        elif self._action == "export":
            self.progress.show_message(lambda lang: T_DONE_EXPORT.format(lang, folder=self._dest))
        else:
            self.progress.show_message(T_DONE_SD if self._request.console else T_DONE_EMU)
