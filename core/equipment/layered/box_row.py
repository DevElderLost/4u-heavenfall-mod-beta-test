"""The item box's Layered Gear line: its panes in the box
menu's layout (lyt\\lobby\\ui406, in core_lobby.arc) and the hashes the block shows and hides them by (struct
fg_box_row in layered.h).

The box menu has two frames, and the game shows one by the box's kind (menu + 2): waku00, of 7 rows (the house's box,
and every box with box_equipment), and waku10, of 4 (a box away from home without it). Rows 0-3 are in the nulls
list00 (plates) and mozi00_00 (texts), drawn in both frames; rows 4-6 in list10 and mozi00_01, hidden in the 4-row one.
The Layered Gear line is the box's last (layered_box.c): line 7 at the house (8 lines), 6 away with box_equipment (7:
the game's Change Appearance is not there), 4 away without it (5). The layout gets a copy of the row for each of those
lines, in list00 and mozi00_00 so that it shows in either frame, and a frame one row taller than each of the game's
(8 rows in waku00, 5 in waku10), drawn in place of the game's when the line is one past it. All start hidden: only
the block's code shows them.
"""

import struct
from collections.abc import Iterator

from core.game.files.arc import parse_arc, write_arc
from core.game.files.gui.lyt import LYT_TYPE_HASH, Layout, Pane, name_hash, parse_lyt

LAYOUT = "lyt\\lobby\\ui406"
GROUPS = ("ui406_listwaku00", "ui406_mozi_shita00", "ui406_mozi00")   # the roots of the frames, plates and texts
PLATES = "ui406_list00"          # the null of rows 0-3's plates, shown in both frames
TEXTS = "ui406_mozi00_00"        # the null of rows 0-3's texts, shown in both frames
_PLATE_PAIRS = ((0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11), (20, 21))
# Each of the game's rows: its plate pair (the line's plate, the icon's) and its text
GAME_ROWS = tuple((f"ui406_list00_{a:02}", f"ui406_list00_{b:02}", f"ui406_m_00_{row:02}")
                  for row, (a, b) in enumerate(_PLATE_PAIRS))
# The two frames: the null and its two sides and middle, which our taller copies stand in for
FRAMES = (("ui406_waku00", ("ui406_waku00_00", "ui406_waku00_01", "ui406_naka00")),
          ("ui406_waku10", ("ui406_waku10_00", "ui406_waku10_01", "ui406_naka10")))
# Where the line can be: (its line, the frame it shows in: 0 the 7-row one, 1 the 4-row one, our taller frame drawn)
LINES = ((4, 1, True), (6, 0, False), (7, 0, True))
TEMPLATE_ROW = 6                 # the game's row the copies are made from


class BoxRowError(ValueError):
    pass


def row_panes(line: int) -> tuple[str, str, str]:
    """Our copy of the row at `line`: its plate pair and its text."""
    return f"ui406_lg_list{line}_0", f"ui406_lg_list{line}_1", f"ui406_lg_m_{line}"


def frame_panes(kind: int) -> tuple[str, ...]:
    """Our taller copy of the frame of `kind` (0 waku00, 1 waku10): its sides and middle."""
    return tuple(name.replace("ui406_", "ui406_lg_", 1) for name in FRAMES[kind][1])


def _step(layout: Layout) -> float:
    """The rows' pitch, as the layout has it (the plates' and the texts' alike)."""
    plates = layout.find(GAME_ROWS[0][0]).position[1] - layout.find(GAME_ROWS[1][0]).position[1]
    texts = layout.find(GAME_ROWS[0][2]).position[1] - layout.find(GAME_ROWS[1][2]).position[1]
    if plates <= 0 or plates != texts:
        raise BoxRowError(f"{LAYOUT}: the rows' plates and texts are not one pitch apart ({plates}, {texts})")
    return plates


def _same_place(layout: Layout, pane: str, into: str) -> None:
    """A copy of `pane` moves into the null `into`: both nulls must sit at one place."""
    if layout.find(pane).parent.position != layout.find(into).position:
        raise BoxRowError(f"{LAYOUT}: {pane}'s null and {into} are not at one place")


def _lower(pane: Pane, step: float) -> float:
    """How much lower a pane's position goes when its height grows by `step` and its top stays (by its origin: the
    top row of the 3 x 3 origins keeps its y, the middle one goes down half, the bottom one all of it)."""
    return step * ((pane.origin & 0xF) // 3) / 2


def add_box_row_panes(data: bytes, room: int) -> bytes:
    """A ui406 layout with the Layered Gear line's panes (unchanged if it has them). `room`: the characters the line's
    text holds."""
    layout = parse_lyt(data)
    if any(pane.name == row_panes(LINES[0][0])[0] for pane in layout.panes):
        return bytes(data)
    step = _step(layout)
    template = GAME_ROWS[TEMPLATE_ROW]
    for name in template[:2]:
        _same_place(layout, name, PLATES)
    _same_place(layout, template[2], TEXTS)
    for line, _, _ in LINES:
        dy = step * (TEMPLATE_ROW - line)
        names = row_panes(line)
        for name, source in zip(names[:2], template[:2]):
            pane = layout.find(source)
            x, y = pane.position
            layout.insert_sprite(layout.find(PLATES), pane, name, (x, y + dy)).visible = False
        text = layout.find(template[2])
        x, y = text.position
        layout.insert_text(layout.find(TEXTS), text, names[2], (x, y + dy), text.size, " " * room)
    for kind, (null, pieces) in enumerate(FRAMES):
        behind = layout.find(pieces[-1])
        for name, source in zip(frame_panes(kind), pieces):
            pane = layout.find(source)
            (x, y), (width, height) = pane.position, pane.size
            copy = layout.insert_sprite(layout.find(null), pane, name, (x, y - _lower(pane, step)), behind=behind)
            copy.size = (width, height + step)
            copy.visible = False
            behind = copy
    return bytes(layout.data)


def add_box_row(arc: bytes, lang: str, room: int) -> bytes:
    """`arc` with the line's panes in its ui406 of `lang` (unchanged if it has no such layout)."""
    parsed = parse_arc(arc)
    name = f"{lang}\\{LAYOUT}"
    entry = next((e for e in parsed.entries if e.name == name and e.type_hash == LYT_TYPE_HASH), None)
    if entry is None:
        return arc
    entry.data = add_box_row_panes(entry.data, room)
    return write_arc(parsed)


# ----- what the code reads (struct fg_box_row in layered.h) -----------------------------------------------------------

LINE_RECORD = struct.Struct("<4B3I")
BOX_ROW = struct.Struct(f"<{len(GROUPS)}I{2 * 2 * 3}I{len(GAME_ROWS) * 3}I{len(LINES) * LINE_RECORD.size}s2H")


def _hashes(names) -> Iterator[int]:
    return (name_hash(name) for name in names)


def box_row_data(msg_entry: int) -> bytes:
    """struct fg_box_row: the groups, the frames (the game's and ours, of each kind), the game's rows, our row at each
    line it can be and the line's message (E_makeshop)."""
    frames = [name for kind, (_, pieces) in enumerate(FRAMES) for name in (*pieces, *frame_panes(kind))]
    lines = b"".join(LINE_RECORD.pack(line, kind, int(own), 0, *_hashes(row_panes(line))) for line, kind, own in LINES)
    return BOX_ROW.pack(*_hashes(GROUPS), *_hashes(frames), *_hashes(name for row in GAME_ROWS for name in row),
                        lines, msg_entry, 0)
