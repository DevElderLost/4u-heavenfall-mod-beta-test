"""What the pages share: the game files, where the mod goes, the player's own options, the platform and whether a
task is running. One AppState per window; pages read it and listen to `changed(key)`, and only the page that owns a
value writes it (Install: the files and the target; Options: `personal`; the window: `console`).

It is kept in the preferences file (gui/preferences.py) on every change.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from core.gui.preferences import Preferences


class AppState(QObject):
    changed = Signal(str)   # the key that changed: rom_path, xx_rom_path, target, sd_root, personal,
    #                         console, busy

    def __init__(self, preferences: Preferences | None = None):
        super().__init__()
        self.preferences = preferences if preferences is not None else Preferences.load()
        self._busy = False

    # -- the game files (Install page)
    @property
    def rom_path(self) -> str:
        return self.preferences.rom_path

    @rom_path.setter
    def rom_path(self, value: str) -> None:
        self._set("rom_path", value)

    @property
    def xx_rom_path(self) -> str:
        """MH XX's ROM: the Install page asks for it, and the runs need it, while the player's choices add a ported
        monster or the models pack (`needs_xx`)."""
        return self.preferences.xx_rom_path

    @xx_rom_path.setter
    def xx_rom_path(self, value: str) -> None:
        self._set("xx_rom_path", value)

    @property
    def needs_xx(self) -> bool:
        """The player's own options (Options page) add a ported monster or the models pack: Settings.needs_xx."""
        from core.app.presets import install_settings
        return install_settings(self.personal).needs_xx

    @property
    def offers_xx(self) -> bool:
        """MH XX is optional in this edition (`Edition.xx_optional`) and the player's options use what it adds (Layered
        Gear's looks): the Install page offers its file, and a run reads it when one is given."""
        from core.app.edition import edition
        from core.app.presets import install_settings
        return edition().xx_optional and install_settings(self.personal).layered_equipment

    def xx_rom_for(self, settings) -> str:
        """The MH XX file a run reads: the chosen one when the settings need it (`needs_xx`) or the edition offers it
        (`offers_xx`), else none."""
        return self.xx_rom_path if self.xx_rom_path and (getattr(settings, "needs_xx", False) or self.offers_xx) else ""

    # -- where the mod goes (Install page): "auto" (the emulator found) or a mod folder; the 3DS SD card's root
    @property
    def target(self) -> str:
        return self.preferences.install_target

    @target.setter
    def target(self, value: str) -> None:
        self._set("install_target", value, key="target")

    @property
    def sd_root(self) -> str:
        return self.preferences.sd_root

    @sd_root.setter
    def sd_root(self, value: str) -> None:
        self._set("sd_root", value)

    # -- the player's own options (Options page): field -> value as saved in a settings file (enums by value)
    @property
    def personal(self) -> dict:
        """The saved choices over the defaults (gui_defaults.json), so a first start needs no visit to Options; a saved
        choice for an option the presets no longer offer is dropped."""
        from core.app.presets import personal_defaults
        defaults = personal_defaults()
        return {**defaults, **{k: v for k, v in self.preferences.install_options.items() if k in defaults}}

    @personal.setter
    def personal(self, values: dict) -> None:
        self._set("install_options", dict(values), key="personal")

    # -- the platform (the window's selector)
    @property
    def console(self) -> bool:
        return self.preferences.platform == "console"

    @console.setter
    def console(self, value: bool) -> None:
        self._set("platform", "console" if value else "emulator", key="console")

    # -- one task at a time (build, install, randomize, fix): pages disable their run buttons while busy
    @property
    def busy(self) -> bool:
        return self._busy

    def claim(self) -> bool:
        """Mark a task as running; False when another one already is."""
        if self._busy:
            return False
        self._busy = True
        self.changed.emit("busy")
        return True

    def release(self) -> None:
        if self._busy:
            self._busy = False
            self.changed.emit("busy")

    def _set(self, attribute: str, value, key: str | None = None) -> None:
        if getattr(self.preferences, attribute) == value:
            return
        setattr(self.preferences, attribute, value)
        self.preferences.save()
        self.changed.emit(key or attribute)
