"""The arrangement of the game's screens: blocks (root groups of a layout that move together) and screens (an explicit
rule on the root groups
shown, and the final place of each block there). Every value is absolute: a block's final place on a screen is its
screen's value, else its default's, else the game's own; nothing is added to anything at run time.

Files, under game/data/curated/game_gui/: `blocks.json`, `settings.json` and `screens/<theme>.json` (one file per
theme), `fixes.json` (fixes.py) and `names_en.json` (the English names the tools show in English,
interface/game_gui/strings.py). `load_arrangement` reads and checks them (ValueError naming the file and the record);
`save_screens` writes a theme file back in the layout people and diffs read best (one line per screen header and per
block placement)."""

import json
import re
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

from core.game.data.paths import CURATED_DIR

ARRANGEMENT_DIR = CURATED_DIR / "game_gui"
ENGLISH_NAMES = "names_en.json"
SCREENS = ("top", "bottom")
MODES = ("single_screen", "normal")
PRIORITY_RANGE = (0, 255)            # the 8 bits of a root group's draw priority (bits 19-26 of group + 0x18)
# The raw pad bits of the 3DS's buttons (pad + 0x8C; FUN_005b8460): the
# photo mode's buttons are named here. The game's raw read sets no bit for SELECT, and the circle pad, the C-stick and
# the touch are no button.
RAW_BUTTONS = {"A": 0x2000, "B": 0x4000, "X": 0x1000, "Y": 0x8000, "L": 0x100, "R": 0x200, "START": 0x8,
               "UP": 0x10, "RIGHT": 0x20, "DOWN": 0x40, "LEFT": 0x80}
_GROUP = re.compile(r"^ui\d{3}[a-z]?\d*_\w+$")
_ID = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)?$")
_NUMBER = re.compile(r"^\d{2,3}[a-z]?$")


@dataclass(frozen=True)
class Placement:
    """Where a block goes: the top-left corner of its visible box in the screen's pixels (x right, y down), its
    scale, its screen, its root groups' draw priority and whether it is hidden. A field left None is not set here."""
    x: float | None = None
    y: float | None = None
    scale: float | None = None
    screen: str | None = None
    priority: int | None = None
    hidden: bool | None = None

    def over(self, other: "Placement") -> "Placement":
        """This placement's fields, the others' where this one leaves them None (a screen's over its block's default).
        """
        return Placement(**{f.name: getattr(other, f.name) if getattr(self, f.name) is None else getattr(self, f.name)
                            for f in fields(self)})

    def to_json(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}


@dataclass(frozen=True)
class Rule:
    """A screen shows when every group of `all` shows, one of `any` does (or `any` is empty) and none of `none`."""
    all: tuple[str, ...] = ()
    any: tuple[str, ...] = ()
    none: tuple[str, ...] = ()

    def matches(self, shown: set[str] | frozenset[str]) -> bool:
        return (all(name in shown for name in self.all) and (not self.any or any(name in shown for name in self.any))
                and not any(name in shown for name in self.none))

    def groups(self) -> set[str]:
        return set(self.all) | set(self.any) | set(self.none)

    def to_json(self) -> dict:
        return {key: list(getattr(self, key)) for key in ("all", "any", "none") if getattr(self, key)}


@dataclass(frozen=True)
class Block:
    """Root groups of one layout that move together. `name` is its Spanish name (as the game shows the
    thing); `default` is its place in single-screen mode when no screen sets it; `backdrop` blocks may lie under others
    (a background); `overlay` blocks open over another screen (a window, a menu on top) and may cover what is drawn
    under them. A **part** block (`part`: panes of its one root group, siblings under one null right under the group,
    in a row) moves those panes on their own: the block that holds the group whole keeps the rest, and the group's
    screen, priority and visibility, so a part sets only x, y and scale; with none set it follows the whole block; it
    may also be `hidden` on its own, or shown while the whole block
    is hidden (`Arrangement.hides`)."""
    id: str
    name: str
    layout: str
    groups: tuple[str, ...]
    default: Placement = Placement()
    backdrop: bool = False
    overlay: bool = False
    part: tuple[str, ...] = ()
    name_en: str = ""                       # its English name (names_en.json); "" when it has none


@dataclass(frozen=True)
class Screen:
    """One screen of the game in one mode: its number and Spanish name (what people call it), its rule,
    and the placement of each block it changes."""
    id: str
    number: str
    name: str
    mode: str
    when: Rule
    blocks: dict[str, Placement] = field(default_factory=dict)
    theme: str = ""
    # the photo mode is available here: the
    photo: tuple[str, ...] | None = None
    #                                         root groups it keeps drawn (the sky); None: not available
    photo_toggle: str | None = None         # the button (`RAW_BUTTONS`) that turns it on here; None: the settings'
    name_en: str = ""                       # its English name (names_en.json); "" when it has none


@dataclass(frozen=True)
class Photo:
    """The photo mode's buttons, by the names of `RAW_BUTTONS`: `toggle`
    turns it on, each of `dismiss` turns it off (and that press is the mode's, not the game's)."""
    toggle: str
    dismiss: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    scale: tuple[float, float]       # the smallest and largest scale a block may take
    move: float                      # how far outside a screen (pixels) a block's corner may lie
    photo: Photo | None = None       # the photo mode's buttons; None: the arrangement has no photo mode


@dataclass
class Arrangement:
    blocks: dict[str, Block]
    screens: list[Screen]
    settings: Settings
    fixes: dict = field(default_factory=dict)   # layout name -> its fixes (fixes.py; hud.single_screen.LayoutSetting)

    def block(self, block_id: str) -> Block:
        return self.blocks[block_id]

    def screens_of(self, mode: str) -> list[Screen]:
        """`mode`'s screens in the order the engine tries them: by number, the overlays' screens (`is_overlay`) after
        every other, so a window open over a screen leaves that screen's places to it. The checker makes sure every
        recorded screen matches exactly one other screen, so the order only decides combinations never recorded."""
        return sorted((s for s in self.screens if s.mode == mode), key=lambda s: (self.is_overlay(s), s.number))

    def matching(self, shown: set[str] | frozenset[str], mode: str) -> list[Screen]:
        return [screen for screen in self.screens_of(mode) if screen.when.matches(shown)]

    def is_overlay(self, screen: Screen) -> bool:
        """Whether `screen` only numbers overlays (and backdrops) left at their defaults: it opens over another screen,
        which places everything else (the engine tries it first, `screens_of`)."""
        return bool(screen.blocks) and all((self.blocks[b].overlay or self.blocks[b].backdrop) and p == Placement()
                                           for b, p in screen.blocks.items())

    def final(self, screen: Screen | None, block_id: str, mode: str = "single_screen") -> Placement:
        """A block's final placement in `screen` (None: no screen of `mode` matches): the screen's fields, then, in
        single-screen mode, the default's; a field still None is the game's own."""
        mode = screen.mode if screen is not None else mode
        default = self.blocks[block_id].default if mode == "single_screen" else Placement()
        if screen is None or block_id not in screen.blocks:
            return default
        return screen.blocks[block_id].over(default)

    def shown_placement(self, group: str, mode: str = "single_screen") -> Placement | None:
        """The placement of the block holding the root group `group` where `mode` shows it: the one place its shown
        screens give it (listed, not hidden), else its default unless hidden; None when no block holds the group or the
        mode shows it nowhere. What a layout of today's mechanism that follows the block reads (the town minimap's
        frame and place name, interface/single_screen/layout/single_screen_minimap.py). Raises ValueError for two
        different places."""
        block = self.blocks.get(self.owners().get(group, ""))
        if block is None:
            return None
        places = {self.final(s, block.id, mode) for s in self.screens_of(mode) if block.id in s.blocks}
        places = {p for p in places if not p.hidden}
        if len(places) > 1:
            raise ValueError(f"block {block.id}: {mode} shows it in {len(places)} places (one is needed here)")
        if places:
            return places.pop()
        default = self.final(None, block.id, mode)
        return None if default.hidden else default

    def owners(self) -> dict[str, str]:
        """Root group -> the block that holds it whole (part blocks left out)."""
        return {group: block.id for block in self.blocks.values() if not block.part for group in block.groups}

    def parts_of(self, block_id: str) -> list[Block]:
        """The part blocks of the groups a whole block holds, in blocks.json's order."""
        groups = set(self.blocks[block_id].groups)
        return [b for b in self.blocks.values() if b.part and b.groups[0] in groups]

    def whole_of(self, block_id: str) -> Block:
        """The block that holds a part block's group whole (the block itself for a whole block)."""
        block = self.blocks[block_id]
        return self.blocks[self.owners()[block.groups[0]]] if block.part else block

    def box_panes(self, block_id: str) -> tuple[frozenset[str] | None, frozenset[str]]:
        """(only, skip) for geometry.file_boxes: a part block's own panes, or a whole block's groups without their
        parts' panes."""
        block = self.blocks[block_id]
        if block.part:
            return frozenset(block.part), frozenset()
        return None, frozenset(pane for part in self.parts_of(block_id) for pane in part.part)

    def follows(self, screen: Screen | None, block_id: str, mode: str = "single_screen") -> bool:
        """Whether a part block takes its whole block's place in `screen`: it sets no x, y or scale there."""
        placement = self.final(screen, block_id, mode)
        return bool(self.blocks[block_id].part) and (placement.x, placement.y, placement.scale) == (None,) * 3

    def hides(self, screen: Screen | None, block_id: str, mode: str = "single_screen") -> bool:
        """Whether `block_id` is not drawn in `screen`: its placement's `hidden`; a part block's own when it sets one
        (a part with `hidden: false` stays drawn when its whole block is hidden), else its whole block's (a part that
        says nothing goes with it). The group itself is drawn while any of its parts is not hidden."""
        placement = self.final(screen, block_id, mode)
        if self.blocks[block_id].part and placement.hidden is None:
            return self.hides(screen, self.whole_of(block_id).id, mode)
        return bool(placement.hidden)


def _fail(where: str, message: str):
    raise ValueError(f"{where}: {message}")


def _names(value, where: str, what: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) and _GROUP.match(v) for v in value):
        _fail(where, f"{what} must be a list of root group names (uiNNN_...)")
    if len(set(value)) != len(value):
        _fail(where, f"{what} names a group twice")
    return tuple(value)


def _placement(record, where: str, settings: Settings) -> Placement:
    if not isinstance(record, dict):
        _fail(where, "a placement is an object")
    unknown = set(record) - {f.name for f in fields(Placement)}
    if unknown:
        _fail(where, f"unknown keys {sorted(unknown)}")
    out = {}
    for key in ("x", "y"):
        if key in record:
            value = record[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                _fail(where, f"{key} must be a number")
            limit = (400 if key == "x" else 240) + settings.move
            if not -settings.move <= value <= limit:
                _fail(where, f"{key} {value} lies too far outside the screen")
            out[key] = float(value)
    if "scale" in record:
        value = record["scale"]
        low, high = settings.scale
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not low <= value <= high:
            _fail(where, f"scale must be a number from {low} to {high}")
        out["scale"] = float(value)
    if "screen" in record:
        if record["screen"] not in SCREENS:
            _fail(where, f"screen must be one of {SCREENS}")
        out["screen"] = record["screen"]
    if "priority" in record:
        value, (low, high) = record["priority"], PRIORITY_RANGE
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            _fail(where, f"priority must be a whole number from {low} to {high}")
        out["priority"] = value
    if "hidden" in record:
        if not isinstance(record["hidden"], bool):
            _fail(where, "hidden must be true or false")
        out["hidden"] = record["hidden"]
    return Placement(**out)


def load_settings(path: Path) -> Settings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    scale, move = data.get("scale"), data.get("move")
    if (not isinstance(scale, list) or len(scale) != 2 or not all(isinstance(v, (int, float)) for v in scale)
            or not 0 < scale[0] < scale[1]):
        _fail(str(path), "scale must be [smallest, largest], both above 0")
    if not isinstance(move, (int, float)) or move < 0:
        _fail(str(path), "move must be a number of pixels, 0 or more")
    return Settings(scale=(float(scale[0]), float(scale[1])), move=float(move),
                    photo=_photo(data.get("photo"), str(path)))


def _photo(record, where: str) -> Photo | None:
    if record is None:
        return None
    if not isinstance(record, dict) or set(record) != {"toggle", "dismiss"}:
        _fail(where, "photo is an object of toggle and dismiss")
    names = ", ".join(RAW_BUTTONS)
    if record["toggle"] not in RAW_BUTTONS:
        _fail(where, f"photo toggle must be one of {names}")
    dismiss = record["dismiss"]
    if (not isinstance(dismiss, list) or not dismiss or not all(d in RAW_BUTTONS for d in dismiss)
            or len(set(dismiss)) != len(dismiss)):
        _fail(where, f"photo dismiss must be a list of buttons, each once, from {names}")
    return Photo(record["toggle"], tuple(dismiss))


def load_blocks(path: Path, settings: Settings) -> dict[str, Block]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, Block] = {}
    grouped: dict[str, str] = {}
    for index, record in enumerate(data.get("blocks", [])):
        where = f"{Path(path).name}, block {index}"
        if not isinstance(record, dict):
            _fail(where, "a block is an object")
        unknown = set(record) - {"id", "name", "layout", "groups", "default", "backdrop", "overlay", "part"}
        if unknown:
            _fail(where, f"unknown keys {sorted(unknown)}")
        block_id, name, layout = record.get("id"), record.get("name"), record.get("layout")
        if not isinstance(block_id, str) or not _ID.match(block_id):
            _fail(where, "id must be lower case words joined by _ and one optional dot")
        where = f"{Path(path).name}, block {block_id}"
        if block_id in out:
            _fail(where, "id used twice")
        if not isinstance(name, str) or not name.strip():
            _fail(where, "name must be the Spanish name the game shows")
        if not isinstance(layout, str) or not re.match(r"^ui\d{3}[a-z]?\d*$", layout):
            _fail(where, "layout must be a layout's name (uiNNN)")
        groups = _names(record.get("groups"), where, "groups")
        if not groups:
            _fail(where, "a block needs at least one root group")
        part = record.get("part", [])
        if not isinstance(part, list) or not all(isinstance(p, str) and p for p in part) or len(set(part)) != len(part):
            _fail(where, "part must be a list of pane names, each once")
        if part and len(groups) != 1:
            _fail(where, "a part block names the one root group its panes are in")
        for group in groups:
            if not group.startswith(layout + "_"):
                _fail(where, f"{group} is not a group of {layout}")
            if part:
                continue
            if group in grouped:
                _fail(where, f"{group} is already in block {grouped[group]}")
            grouped[group] = block_id
        backdrop, overlay = record.get("backdrop", False), record.get("overlay", False)
        if not isinstance(backdrop, bool):
            _fail(where, "backdrop must be true or false")
        if not isinstance(overlay, bool):
            _fail(where, "overlay must be true or false")
        default = _placement(record.get("default", {}), f"{where}, default", settings)
        if part:
            _part_placement(default, f"{where}, default")
        out[block_id] = Block(block_id, name.strip(), layout, groups, default, backdrop, overlay, tuple(part))
    taken: dict[tuple[str, str], str] = {}
    for block in out.values():
        if not block.part:
            continue
        where = f"{Path(path).name}, block {block.id}"
        if block.groups[0] not in grouped:
            _fail(where, f"no block holds {block.groups[0]} whole (it keeps the rest of the group)")
        for pane in block.part:
            if (block.groups[0], pane) in taken:
                _fail(where, f"{pane} is already in part block {taken[block.groups[0], pane]}")
            taken[block.groups[0], pane] = block.id
    return out


def _part_placement(placement: Placement, where: str) -> None:
    """A part block's placement sets x, y, scale and hidden only: the screen and priority are its group's."""
    if (placement.screen, placement.priority) != (None, None):
        _fail(where, "a part block sets only x, y, scale and hidden (its group's screen and priority are the whole "
                     "block's)")


def load_screens(path: Path, blocks: dict[str, Block], settings: Settings) -> list[Screen]:
    return parse_screens(json.loads(Path(path).read_text(encoding="utf-8")), Path(path).name, blocks, settings)


def parse_screens(data: dict, filename: str, blocks: dict[str, Block], settings: Settings) -> list[Screen]:
    """The screens of a theme file's JSON `data` (`filename`: its name, for the messages and the theme)."""
    theme = Path(filename).stem
    out = []
    for index, record in enumerate(data.get("screens", [])):
        where = f"{filename}, screen {index}"
        if not isinstance(record, dict):
            _fail(where, "a screen is an object")
        unknown = set(record) - {"id", "number", "name", "mode", "when", "blocks", "photo", "photo_toggle"}
        if unknown:
            _fail(where, f"unknown keys {sorted(unknown)}")
        screen_id, number, name = record.get("id"), record.get("number"), record.get("name")
        if not isinstance(screen_id, str) or not _ID.match(screen_id) or "." in screen_id:
            _fail(where, "id must be lower case words joined by _")
        where = f"{filename}, screen {screen_id}"
        if not isinstance(number, str) or not _NUMBER.match(number):
            _fail(where, 'number must be like "07" or "07b"')
        if not isinstance(name, str) or not name.strip():
            _fail(where, "name must be the Spanish name the game shows")
        mode = record.get("mode", "single_screen")
        if mode not in MODES:
            _fail(where, f"mode must be one of {MODES}")
        when = record.get("when")
        if not isinstance(when, dict) or set(when) - {"all", "any", "none"}:
            _fail(where, "when must be an object of all / any / none")
        rule = Rule(_names(when.get("all"), where, "when.all"), _names(when.get("any"), where, "when.any"),
                    _names(when.get("none"), where, "when.none"))
        if not rule.all and not rule.any:
            _fail(where, "a rule needs groups in all or any (else it matches everything)")
        if (set(rule.all) | set(rule.any)) & set(rule.none):
            _fail(where, "a group is both wanted and refused")
        placements = record.get("blocks", {})
        if not isinstance(placements, dict):
            _fail(where, "blocks must be an object of block id -> placement")
        moved = {}
        for block_id, placement in placements.items():
            if block_id not in blocks:
                _fail(where, f"unknown block {block_id}")
            moved[block_id] = _placement(placement, f"{where}, {block_id}", settings)
            if blocks[block_id].part:
                _part_placement(moved[block_id], f"{where}, {block_id}")
        photo = None
        if "photo" in record:
            if settings.photo is None:
                _fail(where, "photo mode needs the buttons of settings.json `photo`")
            photo = _names(record["photo"], where, "photo")
        toggle = record.get("photo_toggle")
        if toggle is not None and (photo is None or toggle not in RAW_BUTTONS):
            _fail(where, f"photo_toggle must be one of {', '.join(RAW_BUTTONS)}, on a screen with `photo`")
        out.append(Screen(screen_id, number, name.strip(), mode, rule, moved, theme, photo, toggle))
    return out


def load_english_names(path: Path) -> dict[str, dict[str, str]]:
    """names_en.json: {"screens" | "blocks" | "coverage": {id: English name}}; empty sections when the file does not
    exist."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data.pop("description", None)
    out = {}
    for section in ("screens", "blocks", "coverage"):
        names = data.pop(section, {})
        if not isinstance(names, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip()
                                                  for k, v in names.items()):
            _fail(f"{path.name}, {section}", "must map each id to its English name")
        out[section] = {k: v.strip() for k, v in names.items()}
    if data:
        _fail(path.name, f"unknown sections {sorted(data)}: screens, blocks and coverage")
    return out


def load_arrangement(folder: Path = ARRANGEMENT_DIR) -> Arrangement:
    """The arrangement in `folder`, checked: ids and numbers unique per mode, every block a screen names declared."""
    folder = Path(folder)
    settings = load_settings(folder / "settings.json")
    blocks = load_blocks(folder / "blocks.json", settings)
    screens: list[Screen] = []
    for path in sorted((folder / "screens").glob("*.json")):
        screens += load_screens(path, blocks, settings)
    seen_ids: dict[str, str] = {}
    seen_numbers: dict[tuple[str, str], str] = {}
    for screen in screens:
        if screen.id in seen_ids:
            _fail(f"{screen.theme}.json, screen {screen.id}", f"id also used in {seen_ids[screen.id]}.json")
        seen_ids[screen.id] = screen.theme
        key = (screen.mode, screen.number)
        if key in seen_numbers:
            _fail(f"{screen.theme}.json, screen {screen.id}", f"number {screen.number} is also {seen_numbers[key]}'s")
        seen_numbers[key] = screen.id
    fixes = {}
    if (folder / "fixes.json").is_file():
        from core.interface.game_gui.fixes import load_fixes          # fixes.py reads this module's ARRANGEMENT_DIR
        fixes = load_fixes(folder / "fixes.json")
    english = load_english_names(folder / ENGLISH_NAMES)
    blocks = {key: replace(block, name_en=english["blocks"].get(key, "")) for key, block in blocks.items()}
    screens = [replace(screen, name_en=english["screens"].get(screen.id, "")) for screen in screens]
    return Arrangement(blocks, screens, settings, fixes)


def _line(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def screens_text(screens: list[Screen], description: str = "") -> str:
    """A theme file's text: the description, then each screen's header on one line and each block's placement on a
    line of its own, blocks in the order the screen lists them."""
    lines = ["{"]
    if description:
        lines.append(f'  "description": {_line(description)},')
    lines.append('  "screens": [')
    for i, screen in enumerate(screens):
        head = {"id": screen.id, "number": screen.number, "name": screen.name, "mode": screen.mode,
                "when": screen.when.to_json()}
        if screen.photo is not None:
            head["photo"] = list(screen.photo)
        if screen.photo_toggle is not None:
            head["photo_toggle"] = screen.photo_toggle
        lines.append("    " + _line(head)[:-1] + ', "blocks": {')
        items = list(screen.blocks.items())
        for j, (block_id, placement) in enumerate(items):
            comma = "," if j < len(items) - 1 else ""
            lines.append(f"      {_line(block_id)}: {_line(placement.to_json())}{comma}")
        lines.append("    }}" + ("," if i < len(screens) - 1 else ""))
    lines += ["  ]", "}", ""]
    return "\n".join(lines)


def save_screens(path: Path, screens: list[Screen], arrangement: Arrangement) -> None:
    """Write a theme file (its description kept), refusing (ValueError, nothing written) what `load_screens` would
    refuse with `arrangement`'s blocks and settings."""
    path = Path(path)
    description = ""
    if path.is_file():
        description = json.loads(path.read_text(encoding="utf-8")).get("description", "")
    text = screens_text([replace(screen, theme=path.stem) for screen in screens], description)
    parse_screens(json.loads(text), path.name, arrangement.blocks, arrangement.settings)
    path.write_text(text, encoding="utf-8", newline="\n")
