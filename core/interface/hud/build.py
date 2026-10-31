"""The top-screen HUD: which layouts it is made of, and the files of the HUD size mod.

The layouts were identified in the game with research/probes/hud_probe.py.
"""

import os
import re
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Protocol

from core.game.files.arc import parse_arc, write_arc
from core.interface.hud.hint import GLYPH_ARCS, add_glyph, add_hint
from core.game.files.gui.lanl import LANL_TYPE_HASH, parse_lanl
from core.game.files.gui.lyt import LYT_TYPE_HASH, parse_lyt
from core.interface.hud.scale import Anchor, AnchorSpec, anchor_all, scale_hud

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
QUEST_ARC = "core_quest.arc"
# ARC in <lang>/data/ -> layout -> anchor of every root group, or {root group: anchor} (others are not scaled).
HUD_LAYOUTS: dict[str, dict[str, AnchorSpec | dict[str, AnchorSpec]]] = {
    "core_quest.arc": {
        "ui202": Anchor.TOP_LEFT,      # clock, health, stamina, sharpness, weapon gauges
        "ui203": Anchor.TOP_LEFT,      # party list
        # Hold / fishing gauges; Frenzy icon. The mount gauge (ui204_nori) needs the executable patch.
        "ui204": {"ui204_hold": Anchor.BOTTOM, "ui204_fish": Anchor.BOTTOM, "ui204_virus": Anchor.TOP_LEFT},
        "ui205": Anchor.BOTTOM_RIGHT,  # item and ammo selector
    },
    "core_common.arc": {
        "ui001": Anchor.IN_PLACE,      # prompts (climb...) and names over the characters, placed by the code
    },
}
# One per area and language (164 each). The code moves the whole map layout; it is drawn as if the map's
# 128x128 frame started at the screen's top-left corner, so its top-right corner is at (72, 120).
# Only together with the executable patch (code_patch.patch_hud): the code places the map icons.
MAP_ARC = re.compile(r"m\d\d(a\d\d)?_map\d?\.arc")
MINIMAP_ANCHOR = (72.0, 120.0)
# Also only with the executable patch, which fixes what the code places: the map icons (they only change size)
# and the mount gauge (its monster face).
CODE_PATCH_LAYOUTS: dict[str, dict[str, AnchorSpec | dict[str, AnchorSpec]]] = {
    "core_quest.arc": {"ui250": Anchor.IN_PLACE, "ui204": {"ui204_nori": Anchor.BOTTOM}},
}


def layouts_of(arc_name: str, with_code_patch: bool) -> dict[str, AnchorSpec | dict[str, AnchorSpec]]:
    """HUD_LAYOUTS of an ARC, plus CODE_PATCH_LAYOUTS when the executable is patched too."""
    layouts = dict(HUD_LAYOUTS.get(arc_name, {}))
    for name, anchor in (CODE_PATCH_LAYOUTS.get(arc_name, {}) if with_code_patch else {}).items():
        current = layouts.get(name)
        layouts[name] = {**current, **anchor} if isinstance(current, dict) and isinstance(anchor, dict) else anchor
    return layouts

UPDATE_TITLE_ID = "0004000e00126100"
# Emulators keep installed titles decrypted on their virtual SD card:
# <user folder>/<emulator>/sdmc/Nintendo 3DS/<id>/<id>/title/0004000e/00126100/content/00000000.app
EMULATORS = ("Citra", "Azahar", "Lime3DS", "citra-emu", "azahar-emu", "lime3ds-emu")
UPDATE_CONTENT = Path("title") / "0004000e" / "00126100" / "content" / "00000000.app"


class GameFiles(Protocol):
    """A RomFS (core.game.executable.romfs.RomFS) or anything else with the same two methods."""
    def read(self, path: str) -> bytes: ...
    def walk(self) -> Iterator[str]: ...


def short_name(entry_name: str) -> str:
    return entry_name.split("\\")[-1]


def scale_arc(raw: bytes, layouts: Mapping[str, AnchorSpec | Mapping[str, AnchorSpec]], factor: float) -> bytes:
    """The ARC with the given layouts scaled, together with every animation of the ARC that moves them."""
    arc = parse_arc(raw)
    entries = {short_name(e.name): e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    animation_entries = [e for e in arc.entries if e.type_hash == LANL_TYPE_HASH]
    animations = [parse_lanl(e.data) for e in animation_entries]
    for name, anchor in layouts.items():
        if name not in entries:
            raise KeyError(f"no layout named {name}")
        layout = parse_lyt(entries[name].data)
        anchors = anchor if isinstance(anchor, Mapping) else anchor_all(layout, anchor)
        scale_hud(layout, animations, factor, anchors)
        entries[name].data = layout.to_bytes()
    for entry, file in zip(animation_entries, animations):
        entry.data = file.to_bytes()
    return write_arc(arc)


def glyph_files(rom: GameFiles) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of the other copies of the hint's texture (hint.GLYPH_ARCS but core_quest)."""
    for lang in LANGUAGES:
        for arc_name in GLYPH_ARCS:
            if arc_name != QUEST_ARC:
                path = f"{lang}/data/{arc_name}"
                yield path, add_glyph(rom.read(path))


def hint_files(rom: GameFiles) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of the quest HUD of each language with only the target switch hint (hint.py), and
    the other copies of its texture."""
    for lang in LANGUAGES:
        path = f"{lang}/data/{QUEST_ARC}"
        yield path, add_hint(rom.read(path))
    yield from glyph_files(rom)


def hud_files(rom: GameFiles, factor: float,
              with_code_patch: bool = False, target_hint: bool = False) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every file of the HUD size mod, for the 5 languages, all from the base game's
    copies (`rom`: the mod runs the base game's code and ships its data).
    `with_code_patch` adds the minimap and the mount gauge: only together with code_patch.patch_hud in the
    executable. `target_hint` adds the target switch hint to the item selector, which then shrinks with it, and
    the other copies of its texture."""
    map_paths = [p for p in rom.walk() if p.split("/")[0] in LANGUAGES
                 and MAP_ARC.fullmatch(p.split("/")[-1])] if with_code_patch else []
    if target_hint:
        yield from glyph_files(rom)
    for lang in LANGUAGES:
        for arc_name in HUD_LAYOUTS:
            path = f"{lang}/data/{arc_name}"
            raw = rom.read(path)
            if target_hint and arc_name == QUEST_ARC:
                raw = add_hint(raw)
            yield path, scale_arc(raw, layouts_of(arc_name, with_code_patch), factor)
        for path in map_paths:
            if path.startswith(lang + "/"):
                raw = rom.read(path)
                names = [short_name(e.name) for e in parse_arc(raw).entries if e.type_hash == LYT_TYPE_HASH]
                yield path, scale_arc(raw, {name: MINIMAP_ANCHOR for name in names}, factor)


def emulator_folders() -> list[Path]:
    """User folders where Citra and its forks keep their data (Windows, Linux, macOS)."""
    bases = [Path(os.environ[var]) for var in ("APPDATA", "XDG_DATA_HOME") if os.environ.get(var)]
    bases += [Path.home() / ".local" / "share", Path.home() / "Library" / "Application Support"]
    return [base / name for base in bases for name in EMULATORS]


def find_update() -> Path | None:
    """The update's 00000000.app installed in an emulator, if any: for research tools that build from it on
    purpose (research/probes/port_probe.py update_app); a run never looks for it."""
    for folder in emulator_folders():
        sd_card = folder / "sdmc" / "Nintendo 3DS"
        if sd_card.is_dir():
            for path in sorted(sd_card.glob("*/*/" + UPDATE_CONTENT.as_posix())):
                if path.is_file():
                    return path
    return None


def hud_paths(mod_dir: Path) -> list[Path]:
    """Every file the HUD size mod can leave in a mod folder (core ARCs, the hint's texture copies and the map
    ARCs)."""
    paths = []
    for lang in LANGUAGES:
        folder = Path(mod_dir) / "romfs" / lang / "data"
        paths += [folder / name for name in dict.fromkeys([*HUD_LAYOUTS, *GLYPH_ARCS])]
        if folder.is_dir():
            paths += [p for p in folder.iterdir() if MAP_ARC.fullmatch(p.name)]
    return paths


def remove_hud_files(mod_dir: Path) -> None:
    for path in hud_paths(mod_dir):
        path.unlink(missing_ok=True)


def write_hud_files(mod_dir: Path, rom: GameFiles, factor: float,
                    with_code_patch: bool = False, target_hint: bool = False) -> list[Path]:
    """Write the HUD size mod into a mod folder (romfs/<lang>/data/...). Files of an earlier run are replaced.
    See hud_files() for `with_code_patch` and `target_hint`."""
    remove_hud_files(mod_dir)
    written = []
    for path, data in hud_files(rom, factor, with_code_patch, target_hint):
        target = Path(mod_dir) / "romfs" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(target)
    return written
