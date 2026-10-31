"""Single-screen mode, the players' box at the top left (emulator
only), layout side.

In a hall with other hunters the game's own member list is the lobby's `ui500`: a board and four cards of 119 x 58
pixels (two by two on the touch screen), each filled by the game with one hunter: the weapon type's icon, the name, the
Hunter Rank (a label and a number), the ticket icons of the quest the hunter chose or joined, the G mark and the host
flag. The game writes text, texture cells, colours and shown / hidden, never positions, so the cards can be laid out
anew in the file: this module puts the four of them in four rows at the top left of the top screen, each row a plate
(the game's own name plate, three sprites stretched to the row) with its parts in curated columns; the board, the card
frames, the weapon's name and the signal bars (curated `hide`) are made clear. The executable
(interface/single_screen/executable/single_screen_players.c) shows the group in the hub states where the game does not
and has the game refresh the cards.

Everything is curated (single_screen.json, "players"): the box's corner, the rows' pitch, the
plate, and a rectangle in pixels (from the row's top-left corner) and a font size for each part. The panes are found by
the layout's structure, which is checked: the cards' names differ from one card to the next (`ui500_pl_name`,
`ui500_pl_name2`...). The step runs after the layout is placed (interface/single_screen/layout/single_screen.py: the
setting's `priority`, which draws the group in front of the top screen's own), so the placing neither scales nor moves
it.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from core.game.files.arc import parse_arc, write_arc
from core.interface.hud.build import LANGUAGES, GameFiles
from core.game.files.gui.lyt import LYT_TYPE_HASH, Layout, Pane, PaneKind, parse_lyt
from core.interface.hud.scale import SCREEN_HALF_HEIGHT, SCREEN_HALF_WIDTH
from core.interface.single_screen.layout.single_screen import SETTINGS_FILE, _hide

ARC_NAME = "core_lobby.arc"
LAYOUT = "ui500"                  # the only layout the box knows how to read
ROOT = "ui500_PL_list"
CARDS = 4
ROLES = ("weapon", "name", "hr_label", "hr_number", "ticket", "g_mark", "host")
TEXT_ROLES = ("name", "hr_label", "hr_number")
HIDE_ROLES = ("board", "frame", "weapon_name", "signal")     # what a card or the layout has that the box can drop
CENTRED = 4               # a sprite's origin (low byte) or a text's: x, y is its centre, not its corner
ALIGNMENTS = {"left": 0, "right": 1, "centre": 2}     # a text's lines in its box (the record's word 0x70, bits 0-1)
Rect = tuple[float, float, float, float]    # left, top, width, height, in pixels from the row's top-left corner
_KEYS = {"layout", "left", "top", "pitch", "plate", "parts", "hide"}
_PLATE_KEYS = {"width", "height", "cap"}
# the parts of a card by name, in the order of its content null's children (the file's own: checked)
_CONTENT = (("ui500_pl_name", PaneKind.TEXT), ("ui500_pl_HR", PaneKind.TEXT), ("ui500_pl_HR_suji", PaneKind.TEXT),
            ("ui500_pl_buki", PaneKind.TEXT), ("ui500_pl_buki_icon", PaneKind.SPRITE),
            ("ui500_pl_ticket", PaneKind.SPRITE), ("ui500_pl_ticket", PaneKind.SPRITE),
            ("ui500_icon", PaneKind.NULL), ("ui500_icon", PaneKind.NULL), ("ui500_g_icon", PaneKind.SPRITE))
_PLATE_PANE = re.compile(r"ui500_name_ita([123])(?:_\d+)?$")


@dataclass(frozen=True)
class Part:
    """A part of a card: its `rect` in the row and, for a text, its `font` size (pixels; the pane is `rect`'s height
    tall) and how its line sits in `rect` (`align`: left, right or centre)."""
    rect: Rect
    font: float | None
    align: str | None = None


@dataclass(frozen=True)
class Plate:
    """The row's name plate: `width` x `height` pixels, its two ends `cap` pixels wide (the middle is stretched)."""
    width: float
    height: float
    cap: float


@dataclass(frozen=True)
class PlayersBox:
    """The curated "players" section: the member list's `layout`, the box's top-left corner (`left`, `top`) on the top
    screen, the `pitch` of its four rows, the `plate`, the `parts` (by role) and the roles of the game's card the box
    leaves out (`hide`)."""
    layout: str
    left: float
    top: float
    pitch: float
    plate: Plate
    parts: Mapping[str, Part]
    hide: tuple[str, ...]


def _fail(where: str, what: str) -> ValueError:
    return ValueError(f"single_screen.json, players{where}: {what}")


def _number(value: object, where: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        raise _fail(where, f"a number from {low:g} to {high:g}")
    return float(value)


def _record(value: object, wanted: set[str], where: str) -> dict:
    if not isinstance(value, dict) or set(value) != wanted:
        raise _fail(where, f"a record with {', '.join(sorted(wanted))}, nothing else")
    return value


def players_settings(path: Path = SETTINGS_FILE) -> PlayersBox:
    """The players section of single_screen.json, validated: every error names the section and the key."""
    data = json.loads(Path(path).read_text(encoding="utf-8")).get("players")
    record = _record(data, _KEYS, "")
    if record["layout"] != LAYOUT:
        raise _fail(", layout", f"{LAYOUT}, the only layout the box can read")
    left = _number(record["left"], ", left", 0, SCREEN_HALF_WIDTH * 2)
    top = _number(record["top"], ", top", 0, SCREEN_HALF_HEIGHT * 2)
    pitch = _number(record["pitch"], ", pitch", 1, 120)
    plate_record = _record(record["plate"], _PLATE_KEYS, ", plate")
    width = _number(plate_record["width"], ", plate, width", 8, SCREEN_HALF_WIDTH * 2)
    height = _number(plate_record["height"], ", plate, height", 4, 60)
    cap = _number(plate_record["cap"], ", plate, cap", 1, width / 2)
    plate = Plate(width, height, cap)
    if not isinstance(record["parts"], dict) or set(record["parts"]) != set(ROLES):
        raise _fail(", parts", f"exactly the parts {', '.join(ROLES)}")
    parts = {}
    for role in ROLES:
        where = f", parts, {role}"
        wanted = {"rect", "font", "align"} if role in TEXT_ROLES else {"rect"}
        part = _record(record["parts"][role], wanted, where)
        rect = part["rect"]
        if not isinstance(rect, list) or len(rect) != 4:
            raise _fail(where + ", rect", "[left, top, width, height]")
        values = tuple(_number(v, where + ", rect", 0, SCREEN_HALF_WIDTH * 2) for v in rect)
        if (values[2] <= 0 or values[3] <= 0 or values[0] + values[2] > width + 1e-6
                or values[1] + values[3] > height + 1e-6):
            raise _fail(where + ", rect", "a rectangle inside the plate")
        font = _number(part["font"], where + ", font", 1, 60) if role in TEXT_ROLES else None
        align = part["align"] if role in TEXT_ROLES else None
        if role in TEXT_ROLES and align not in ALIGNMENTS:
            raise _fail(where + ", align", f"one of {', '.join(ALIGNMENTS)}")
        parts[role] = Part(values, font, align)
    hide = record["hide"]
    if not isinstance(hide, list) or len(set(hide)) != len(hide) or not set(hide) <= set(HIDE_ROLES):
        raise _fail(", hide", f"each of {', '.join(HIDE_ROLES)} at most once")
    return PlayersBox(LAYOUT, left, top, pitch, plate, parts, tuple(hide))


# ----- the member list's structure -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Card:
    """One of the four cards, found by structure: its frame (with the plate's three sprites, the right cap first: they
    come as ita3, ita2, ita1), its content, its host flag and the part panes."""
    frame: Pane
    plate: dict[int, Pane]
    content: tuple[Pane, ...]
    host: Pane


def _structure_error(layout_name: str, what: str) -> ValueError:
    return ValueError(f"{layout_name}: not the member list the players' box lays out ({what})")


def _cards(layout: Layout, layout_name: str = LAYOUT) -> tuple[Pane, list[Card]]:
    """The root group and the four cards of `layout`, every pane checked by kind and name; ValueError when the layout is
    not ui500 (or another version of it)."""
    try:
        root = layout.find(ROOT)
    except KeyError:
        raise _structure_error(layout_name, f"no {ROOT}") from None
    kids = root.children
    if (root.kind != PaneKind.GROUP or len(kids) < CARDS + 1 or not kids[0].name.startswith("ui500_list")
            or any(kid.kind != PaneKind.BOUNDARY for kid in kids[CARDS + 1:])):
        raise _structure_error(layout_name, "the board, four cards and their touch areas")
    cards = []
    for n, card in enumerate(kids[1:CARDS + 1], 1):
        if card.kind != PaneKind.NULL or card.name != f"ui500_PL_list{n}" or len(card.children) != 3:
            raise _structure_error(layout_name, f"card {n}")
        frame, content, host = card.children
        if not (frame.kind == PaneKind.NULL and frame.name.startswith("ui500_pl_list")
                and content.kind == PaneKind.NULL and content.name.startswith("ui500_m_pl_list")
                and host.kind == PaneKind.SPRITE and host.name.startswith("ui500_host_icon")):
            raise _structure_error(layout_name, f"card {n}'s frame, content and host flag")
        parts = content.children
        if len(parts) != len(_CONTENT) or any(part.kind != kind or not part.name.startswith(prefix)
                                             for part, (prefix, kind) in zip(parts, _CONTENT)):
            raise _structure_error(layout_name, f"card {n}'s parts")
        plate = {int(m.group(1)): pane for pane in frame.children
                 if (m := _PLATE_PANE.match(pane.name)) and pane.kind == PaneKind.SPRITE}
        if sorted(plate) != [1, 2, 3]:
            raise _structure_error(layout_name, f"card {n}'s name plate")
        cards.append(Card(frame, plate, tuple(parts), host))
    return root, cards


# ----- the layout ----------------------------------------------------------------------------------------------------

def _origin(pane: Pane) -> tuple[float, float]:
    """The layout-coordinate position of `pane`'s parent: the sum of its ancestors' positions (the nulls above a card's
    parts all have scale 1, which is checked: a scale would multiply what is under it)."""
    x = y = 0.0
    parent = pane.parent
    while parent is not None:
        if parent.kind == PaneKind.NULL and tuple(parent.scale) != (1.0, 1.0):
            raise ValueError(f"{parent.name}: the box needs nulls of scale 1 above its parts")
        x, y = x + parent.position[0], y + parent.position[1]
        parent = parent.parent
    return x, y


def _put(pane: Pane, left: float, top: float, width: float, height: float, font: float | None = None,
         align: str | None = None) -> None:
    """Place `pane` so that what it draws covers the screen rectangle (left, top, width, height) of the top screen: by
    its corner, or by its centre when its origin is the centre (a sprite's, or a text's such as the card's name: the
    record says which; the layout's x and y grow towards the left and the top: screen = (200 - x, 120 - y)). A text
    gets the `font` size and its line the `align`ment in the box."""
    ox, oy = _origin(pane)
    origin = pane.text_origin if pane.kind == PaneKind.TEXT else (pane.origin or 0) & 0xFF
    if origin == CENTRED:
        left, top = left + width / 2, top + height / 2
    elif origin:
        raise ValueError(f"{pane.name}: origin {origin}, neither the corner nor the centre")
    pane.position = (SCREEN_HALF_WIDTH - left - ox, SCREEN_HALF_HEIGHT - top - oy)
    pane.size = (width, height)
    if font is not None:
        pane.font_size = (font, font)
    if align is not None:
        pane.text_align = ALIGNMENTS[align]


def place_players(layout: Layout, box: PlayersBox) -> None:
    """Lay the member list's four cards out as the box's four rows: hide what `box.hide` drops, then put each card's
    plate and parts in its row. Raises ValueError when `layout` is not the member list."""
    root, cards = _cards(layout, box.layout)
    if "board" in box.hide:
        _hide(root.children[0])
    plate = box.plate
    for index, card in enumerate(cards):
        row = box.top + index * box.pitch
        if "frame" in box.hide:
            plates = {id(pane) for pane in card.plate.values()}
            for pane in card.frame.children:
                if id(pane) not in plates:
                    _hide(pane)
        if "weapon_name" in box.hide:
            _hide(card.content[3])
        if "signal" in box.hide:
            _hide(card.content[7])
            _hide(card.content[8])
        # the plate: the left cap (ita1), the stretched middle (ita2) and the right cap (ita3, drawn mirrored: its size
        # is negative and its position the plate's right end)
        _put(card.plate[1], box.left, row, plate.cap, plate.height)
        _put(card.plate[2], box.left + plate.cap, row, plate.width - 2 * plate.cap, plate.height)
        _put(card.plate[3], box.left + plate.width, row, -plate.cap, plate.height)
        for role, pane in (("name", card.content[0]), ("hr_label", card.content[1]), ("hr_number", card.content[2]),
                           ("weapon", card.content[4]), ("ticket", card.content[5]), ("ticket", card.content[6]),
                           ("g_mark", card.content[9]), ("host", card.host)):
            part = box.parts[role]
            left, top, width, height = part.rect
            _put(pane, box.left + left, row + top, width, height, part.font, part.align)


def players_arc(raw: bytes, box: PlayersBox) -> bytes:
    """The ARC with the member list laid out as the box. An ARC without the layout is returned as it was."""
    arc = parse_arc(raw)
    entries = {e.name.split("\\")[-1]: e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    if box.layout not in entries:
        return raw
    layout = parse_lyt(entries[box.layout].data)
    place_players(layout, box)
    entries[box.layout].data = layout.to_bytes()
    return write_arc(arc)


def players_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
                  box: PlayersBox | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_lobby.arc with the member list laid out as the box: from the copy in
    `files` (the run's earlier interface files, the placed layouts included) or the game's. The curated box by
    default."""
    box = box or players_settings()
    out = {}
    for language in LANGUAGES:
        path = f"{language}/data/{ARC_NAME}"
        out[path] = players_arc((files or {}).get(path) or rom.read(path), box)
    return out
