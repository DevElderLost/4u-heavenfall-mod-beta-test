"""Mod Settings' lists of ten rows: the panes the START menu's
widgets (`ui020`, each language's core_common.arc) lack for a page of ten.

The game's small list has five lines (`ui020_mozi01`: m_10-m_14) and frames for two to five rows; its big list has
eight (`ui020_mozi04`: m_40-m_47, the frame `ui020_waku10`, the row strips of `ui020_list10_00`, the icons' backings of
`ui020_shita10`). The game's own menus use the same groups, so everything added here shows only while a list of Mod
Settings is on the screen (mod_settings.c): the texts are empty and the nulls hidden when the layout loads, and the code
writes the texts, shows the nulls and hides the game's frame of the same list for as long as its list is open.

* The small list: m_15-m_19 below m_14; the null `hf_waku01_10`, the 5-row frame `ui020_waku01_01` made 5 rows taller
  (drawn where the game's is, before the row strips); the null `hf_list01_10`, the row strips of rows 5-9.
* The big list: m_48 and m_49 below m_47; the null `hf_waku10_10`, the frame `ui020_waku10` (with its title strip)
  made 2 rows taller; `hf_list10_10`, the strips of rows 8 and 9; `hf_shita10_10`, their icons' backings.

A frame's sides are a strip of `cmn_win00_ID` that repeats down its length: a taller side takes more of it, as far as
the texture goes, and is stretched past that (a few pixels; the strip's pattern shows no seam).
"""

from collections.abc import Iterator, Mapping

from core.game.files.arc import parse_arc, write_arc
from core.game.files.gui.lyt import LYT_TYPE_HASH, Pane, name_hash, parse_lyt
from core.interface.hud.build import LANGUAGES, GameFiles

ARC = "core_common.arc"
LAYOUT = "lyt\\common\\ui020"           # the entry is "<lang>\\" + it
PITCH = 18                              # a row's height in both lists (their texts, strips and the cursors' step)
SMALL_ROWS, BIG_ROWS = 5, 8             # the game's lines in each list
PAGE_ROWS = 10                          # a page of either list: mod_settings.py LIST_PAGE_ROWS, LIST_ROWS

SMALL_GROUP, SMALL_TEXTS = "ui020_subwaku00", "ui020_mozi01"
SMALL_FRAME, SMALL_STRIPS = "ui020_waku01_01", "ui020_list01_00"    # the game's 5-row frame and its strips
SMALL_FRAME_TEN, SMALL_STRIPS_TEN = "hf_waku01_10", "hf_list01_10"
BIG_GROUP, BIG_TEXTS, BIG_BACKS_GROUP = "ui020_listwaku00_001", "ui020_mozi04", "ui020_item_shita00"
BIG_FRAME, BIG_STRIPS, BIG_BACKS = "ui020_waku10", "ui020_list10_00", "ui020_shita10"
BIG_FRAME_TEN, BIG_STRIPS_TEN, BIG_BACKS_TEN = "hf_waku10_10", "hf_list10_10", "hf_shita10_10"
# the names mod_settings.c finds by their hash in a root group's first level: (the game's frame, ours), (the strips,
# the backings) of each list
HASHED = (SMALL_FRAME, SMALL_FRAME_TEN, SMALL_STRIPS_TEN, BIG_FRAME, BIG_FRAME_TEN, BIG_STRIPS_TEN, BIG_BACKS_TEN)


def text_name(row: int, big: bool) -> str:
    """The text pane of a list's row: m_10 + row in the small list, m_40 + row in the big one."""
    return f"ui020_m_{(40 if big else 10) + row}"


def hashes() -> tuple[int, ...]:
    """The name hashes of HASHED, in its order (mod_settings_data)."""
    return tuple(name_hash(name) for name in HASHED)


def _child(parent: Pane, name: str) -> Pane:
    pane = next((c for c in parent.children if c.name == name), None)
    if pane is None:
        raise ValueError(f"ui020 has no {name} under {parent.name}")
    return pane


def _taller(layout, null: Pane, into: Pane, extra: float) -> None:
    """Copies of `null`'s sprites into `into`: the ones as tall as the frame (its sides and middle) `extra` taller; a
    side (the tallest texture region: as many texels as pixels) takes as much more of its strip as the texture has and
    is stretched past it, the middle (a texel stretched) keeps its region; the rest (a title strip) as they are."""
    height = max(child.size[1] for child in null.children)
    side = max(child.region[3] for child in null.children)
    for sprite in null.children:
        u, v, w, h = sprite.region
        width, tall = sprite.size
        if tall == height:
            if h == side:
                h = min(h * (tall + extra) / tall, 1.0 - v)
            tall += extra
        copy = layout.insert_sprite(into, sprite, f"hf_{sprite.name[len('ui020_'):]}_10", sprite.position, (u, v, w, h))
        copy.size = (width, tall)


def _rows_below(layout, null: Pane, into: Pane, rows: range, first: int, per_row: int) -> None:
    """Copies of the first `per_row` sprites of `null` (one row of strips or backings) into `into` for each row of
    `rows`, `PITCH` lower each: row `first` is the row of the copied sprites."""
    for row in rows:
        for sprite in null.children[:per_row]:
            x, y = sprite.position
            layout.insert_sprite(into, sprite, f"hf_{sprite.name[len('ui020_'):]}_r{row}",
                                 (x, y - PITCH * (row - first)))


def _texts_below(layout, group: Pane, last: Pane, rows: range, last_row: int) -> None:
    for row in rows:
        x, y = last.position
        layout.insert_text(group, last, text_name(row, group.name == BIG_TEXTS), (x, y - PITCH * (row - last_row)),
                           last.size, "")


def build(data: bytes) -> bytes:
    """ui020 with the panes of a page of ten rows. A layout that already has them is returned as it is."""
    layout = parse_lyt(data)
    if any(pane.name == SMALL_FRAME_TEN for pane in layout.panes):
        return data
    groups = {group.name: group for group in layout.roots}

    small = groups[SMALL_GROUP]
    frame = _child(small, SMALL_FRAME)
    ten = layout.insert_null(small, frame, SMALL_FRAME_TEN, frame.position, visible=False, behind=frame)
    _taller(layout, frame, ten, PITCH * (PAGE_ROWS - SMALL_ROWS))
    strips = _child(small, SMALL_STRIPS)
    ten = layout.insert_null(small, strips, SMALL_STRIPS_TEN, strips.position, visible=False)
    _rows_below(layout, strips, ten, range(SMALL_ROWS, PAGE_ROWS), 0, 2)
    texts = groups[SMALL_TEXTS]
    _texts_below(layout, texts, _child(texts, text_name(SMALL_ROWS - 1, False)), range(SMALL_ROWS, PAGE_ROWS),
                 SMALL_ROWS - 1)

    big = groups[BIG_GROUP]
    frame = _child(big, BIG_FRAME)
    ten = layout.insert_null(big, frame, BIG_FRAME_TEN, frame.position, visible=False, behind=frame)
    _taller(layout, frame, ten, PITCH * (PAGE_ROWS - BIG_ROWS))
    strips = _child(big, BIG_STRIPS)
    ten = layout.insert_null(big, strips, BIG_STRIPS_TEN, strips.position, visible=False)
    _rows_below(layout, strips, ten, range(BIG_ROWS, PAGE_ROWS), 0, 2)
    backs_group = groups[BIG_BACKS_GROUP]
    backs = _child(backs_group, BIG_BACKS)
    ten = layout.insert_null(backs_group, backs, BIG_BACKS_TEN, backs.position, visible=False)
    _rows_below(layout, backs, ten, range(BIG_ROWS, PAGE_ROWS), 0, 1)
    texts = groups[BIG_TEXTS]
    _texts_below(layout, texts, _child(texts, text_name(BIG_ROWS - 1, True)), range(BIG_ROWS, PAGE_ROWS),
                 BIG_ROWS - 1)
    return layout.to_bytes()


def patch_arc(raw: bytes, lang: str) -> bytes:
    """core_common.arc of `lang` with ui020's panes of ten rows."""
    arc = parse_arc(raw)
    name = f"{lang}\\{LAYOUT}"
    entry = next((e for e in arc.entries if e.type_hash == LYT_TYPE_HASH and e.name == name), None)
    if entry is None:
        raise ValueError(f"{ARC} of {lang} has no {LAYOUT}")
    built = build(entry.data)
    if built == entry.data:
        return raw
    entry.data = built
    return write_arc(arc)


def ten_row_files(rom: GameFiles, files: Mapping[str, bytes] | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of each language's core_common.arc with the panes; an ARC already in `files` (an earlier
    step's: the menu's texts) is patched as it is, the others start from the game's."""
    files = files or {}
    for lang in LANGUAGES:
        path = f"{lang}/data/{ARC}"
        yield path, patch_arc(files.get(path) or rom.read(path), lang)


__all__ = ["ARC", "BIG_FRAME_TEN", "BIG_ROWS", "HASHED", "LAYOUT", "PAGE_ROWS", "PITCH", "SMALL_FRAME_TEN",
           "SMALL_ROWS", "build", "hashes", "patch_arc", "ten_row_files", "text_name"]
