"""The Options page: the player's own choices (HUD size, music, starting kit...), kept in `AppState.personal`.

They apply to the next Install / Update and to randomizer runs; "Apply now" runs the Install page's Update.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.app.edition import edition
from core.gui.i18n import T
from core.gui.qt import jobs
from core.gui.qt.install_page import (
    T_FILES_FIRST, T_NO_TARGET, Discovery, InstallJob, Jobs, ProgressPanel, button, confirm_request, label,
    resolve_request,
)
from core.gui.qt.option_widgets import SettingsForm
from core.gui.qt.page import Page
from core.gui.qt.state import AppState

TITLE = T("Opciones", "Options")
T_NOTE = T("Estas opciones se aplican en la próxima instalación o actualización y en cada partida randomizada.",
           "These options apply to the next install or update and to every randomizer run.")
T_APPLY = T("Aplicar ahora", "Apply now")
T_APPLY_NOTE = T(f"Actualiza ahora el {edition().name} ya instalado con estas opciones.",
                 f"Updates the {edition().name} already installed with these options now.")
T_APPLIED = T("Listo. Reinicia la emulación para ver los cambios.", "Done. Restart the emulation to see the changes.")
T_FAILED = T("No se pudo aplicar.", "Could not apply.")


def raw(value):
    """A form value as saved in a settings file: enums by their value."""
    return value.value if isinstance(value, Enum) else value


class OptionsPage(Page):
    title = TITLE

    def __init__(self, state: AppState, finder: Discovery | None = None, runner: Jobs | None = None):
        super().__init__()
        from core.app.presets import personal_defaults
        from core.gui.options import INSTALL_SECTIONS
        self.state = state
        self.finder = finder or Discovery()
        self._fields = set(personal_defaults())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(10)
        layout.addWidget(label(TITLE, "title"))
        layout.addWidget(label(T_NOTE, "muted"))
        self.form = SettingsForm(INSTALL_SECTIONS)
        self.form.set_values({**personal_defaults(), **state.personal})
        self.form.changed.connect(self._edited)
        layout.addWidget(self.form, 1)
        row = QHBoxLayout()
        self.apply_button = button(T_APPLY, "primary")
        self.apply_button.clicked.connect(self.apply_now)
        row.addWidget(self.apply_button)
        row.addWidget(label(T_APPLY_NOTE, "muted"), 1)
        layout.addLayout(row)
        self.job = InstallJob(state, runner or Jobs(), self)
        self.progress = ProgressPanel(with_log=False)
        layout.addWidget(self.progress)
        self.job.stage.connect(self.progress.on_stage)
        self.job.progress.connect(self.progress.on_progress)
        self.job.finished.connect(self._finished)
        state.changed.connect(self._state_changed)
        self._update_button()

    # -- Page hooks
    def set_platform(self, console: bool) -> None:
        super().set_platform(console)
        self.form.set_platform(console)
        self._update_button()

    def on_shown(self) -> None:
        self.form.set_values({**self.form.values(), **self.state.personal})
        self._update_button()

    # -- the values
    def personal_values(self) -> dict:
        """The player's choices as saved: only the installer's own fields, enums by value."""
        return {field: raw(value) for field, value in self.form.values().items() if field in self._fields}

    def _edited(self, _field: str) -> None:
        self.state.personal = self.personal_values()

    def _state_changed(self, key: str) -> None:
        if key == "personal":
            self.form.set_values(self.state.personal)
        if key in ("busy", "target", "sd_root", "console"):
            self._update_button()

    # -- Apply now
    @property
    def can_apply(self) -> bool:
        try:
            request = resolve_request(self.state, self.finder)
        except jobs.NoTarget:
            return False
        return jobs.installed_marker(request) is not None

    def _update_button(self) -> None:
        self.apply_button.setVisible(self.can_apply)
        self.apply_button.setEnabled(not self.state.busy)

    def apply_now(self) -> None:
        if not self.state.rom_path or (self.state.needs_xx and not self.state.xx_rom_path):
            self.progress.show_message(T_FILES_FIRST, error=True)
            return
        try:
            request = resolve_request(self.state, self.finder)
        except jobs.NoTarget:
            self.progress.show_message(T_NO_TARGET, error=True)
            return
        request = confirm_request(self, request)
        if request is None:
            return
        self.progress.begin()
        if not self.job.start("install", request):
            self.progress.stop()
        self._update_button()

    def _finished(self, ok: bool, _payload) -> None:
        self._update_button()
        if ok:
            self.progress.on_stage("done")
            self.progress.show_message(T_APPLIED)
        else:
            self.progress.stop()
            self.progress.show_message(T_FAILED, error=True)


