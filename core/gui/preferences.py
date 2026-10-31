"""Small per-user GUI memory (last paths and settings), stored in the home folder."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.app.edition import edition, migrate_legacy_user_folder

PREFERENCES_PATH = edition().home / "gui.json"


@dataclass
class Preferences:
    rom_path: str = ""
    mhgen_rom_path: str = ""   # optional: MH Generations' ROM (options mhgen_models and alatreon)
    output_dir: str = str(Path.cwd() / "output")
    last_settings: dict = field(default_factory=dict)
    language: str = ""         # "" until the player picks one: the window follows the system language (gui/qt/app.py)
    appearance: str = "dark"   # system | light | dark
    platform: str = "emulator"  # emulator | console (real 3DS, not available yet)
    mode: str = "randomize"     # randomize | fix (a game in progress, core/app/fix.py)
    install_options: dict = field(default_factory=dict)  # the Install page's choices
    install_target: str = "auto"  # "auto" or the mod folder to install into
    sd_root: str = ""           # the 3DS SD card's root (Luma3DS form)
    randomizer_settings: dict = field(default_factory=dict)  # the Randomizer page's settings

    @classmethod
    def load(cls) -> "Preferences":
        if PREFERENCES_PATH.parent == edition().home:       # a tool reads the choices without starting the app
            migrate_legacy_user_folder()
        try:
            values = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8"))
            return cls(**{k: v for k, v in values.items() if k in cls.__dataclass_fields__})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        try:
            PREFERENCES_PATH.parent.mkdir(parents=True, exist_ok=True)
            PREFERENCES_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass  # preferences are a convenience; never fail because of them
