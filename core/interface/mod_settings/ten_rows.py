"""Mod Settings' lists of every size: the panes the START
menu's widgets (`ui020`, each language's core_common.arc) lack to show a list of 1 to 10 rows in a frame of as many.

The game's small list has five lines (`ui020_mozi01`: m_10-m_14) and frames for two to five rows (2 and 3 in groups of
their own, 4 and 5 in `ui020_subwaku00`); its big list has eight lines (`ui020_mozi04`: m_40-m_47) and one frame, of
eight rows (`ui020_waku10`, the row strips of `ui020_list10_00`, the icons' backings of `ui020_shita10`). The game's
own menus use the same groups, so everything added here shows only while a list of Mod Settings is on the screen
(mod_settings.c): the texts are empty and the nulls hidden when the layout loads, and the code writes the texts, shows
the nulls and hides the game's frame and strips of the same list for as long as its list is open.

* The small list: m_15-m_19 below m_14; a frame `hf_waku01_<n>` for each size the game has none of (1 and 6 to 10
  rows), the 5-row frame `ui020_waku01_01` made as many rows shorter or taller, drawn where the game's is (before the
  row strips); `hf_list01_10`, the row strips of rows 0-9.
* The big list: m_48 and m_49 below m_47; a frame `hf_waku10_<n>` for each size but the game's eight (1 to 7, 9 and
  10), the frame `ui020_waku10` (with its title strip) made as many rows shorter or taller; `hf_list10_10`, the strips
  of rows 0-9; `hf_shita10_10`, their icons' backings.

A frame's sides are a strip of `cmn_win00_ID` that repeats down its length: a side takes as many texels of it as it is
tall (as the game's frames of each size do), as far as the texture goes, and is stretched past that (a few pixels of
the tallest; the strip's pattern shows no seam); the middle is one texel stretched. The code shows the sprites of a
strip null's first rows, as many as the list has.
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
SMALL_GAME_SIZES = (2, 3, 4, 5)         # the small list's sizes with a frame of the game's (FUN_005e87b4)

SMALL_GROUP, SMALL_TEXTS = "ui020_subwaku00", "ui020_mozi01"
SMALL_FRAME_4, SMALL_FRAME = "ui020_waku01_00", "ui020_waku01_01"     # the game's 4- and 5-row frames
SMALL_STRIPS, SMALL_STRIPS_OURS = "ui020_list01_00", "hf_list01_10"
BIG_GROUP, BIG_TEXTS, BIG_BACKS_GROUP = "ui020_listwaku00_001", "ui020_mozi04", "ui020_item_shita00"
BIG_FRAME, BIG_STRIPS, BIG_BACKS = "ui020_waku10", "ui020_list10_00", "ui020_shita10"
BIG_STRIPS_OURS, BIG_BACKS_OURS = "hf_list10_10", "hf_shita10_10"
# the names mod_settings.c finds by their hash in a root group's first level, in its order (enum of the panes): the
# small list's game frames, its strips and ours; the big list's frame, strips and backings, then our strips and backings
NAMED = (SMALL_FRAME_4, SMALL_FRAME, SMALL_STRIPS, SMALL_STRIPS_OURS, BIG_FRAME, BIG_STRIPS, BIG_BACKS, BIG_STRIPS_OURS,
         BIG_BACKS_OURS)


def small_frame(rows: int) -> str | None:
    """Our small list's frame of `rows` rows (1 to 10), None for a size the game has a frame of."""
    return None if rows in SMALL_GAME_SIZES else f"hf_waku01_{rows}"


def big_frame(rows: int) -> str | None:
    """Our big list's frame of `rows` rows (1 to 10), None for the game's eight."""
    return None if rows == BIG_ROWS else f"hf_waku10_{rows}"


def text_name(row: int, big: bool) -> str:
    """The text pane of a list's row: m_10 + row in the small list, m_40 + row in the big one."""
    return f"ui020_m_{(40 if big else 10) + row}"


def hashes() -> tuple[int, ...]:
    """The name hashes mod_settings_data holds: NAMED's in its order, then each size's frame of ours in the small list
    and in the big one (sizes 1 to 10), 0 for a size whose frame is the game's."""
    frames = [name for frame in (small_frame, big_frame) for name in map(frame, range(1, PAGE_ROWS + 1))]
    return (*map(name_hash, NAMED), *(name_hash(name) if name else 0 for name in frames))


def _child(parent: Pane, name: str) -> Pane:
    pane = next((c for c in parent.children if c.name == name), None)
    if pane is None:
        raise ValueError(f"ui020 has no {name} under {parent.name}")
    return pane


def _sized(layout, group: Pane, game: Pane, name: str, rows: int, game_rows: int, behind: Pane) -> Pane:
    """A hidden null `name` right after `behind` in `group`: copies of the frame `game`'s sprites (a frame of
    `game_rows` rows) for `rows` rows. The ones as tall as the frame (its sides and middle) are as many rows shorter or
    taller; a side (the tallest texture region: as many texels as pixels) takes as many texels as it is tall, as far as
    the texture has, the middle (a texel stretched) keeps its region; the rest (a title strip) are as they are."""
    null = layout.insert_null(group, game, name, game.position, visible=False, behind=behind)
    extra = PITCH * (rows - game_rows)
    height = max(child.size[1] for child in game.children)
    side = max(child.region[3] for child in game.children)
    for sprite in game.children:
        u, v, w, h = sprite.region
        width, tall = sprite.size
        if tall == height:
            if h == side:
                h = min(h * (tall + extra) / tall, 1.0 - v)
            tall += extra
        copy = layout.insert_sprite(null, sprite, f"hf_{sprite.name[len('ui020_'):]}_{rows}", sprite.position,
                                    (u, v, w, h))
        copy.size = (width, tall)
    return null


def _frames(layout, group: Pane, game: Pane, game_rows: int, ours) -> None:
    """Our frames of every size `ours` names, after the game's frame `game` (of `game_rows` rows), smallest first."""
    behind = game
    for rows in range(1, PAGE_ROWS + 1):
        if ours(rows) is not None:
            behind = _sized(layout, group, game, ours(rows), rows, game_rows, behind)


def _rows(layout, group: Pane, game: Pane, name: str, per_row: int) -> None:
    """A hidden null `name` at the end of `group`, where the null `game` is: copies of its first `per_row` sprites (its
    first row of strips or backings) for each row of a page, `PITCH` lower each, row by row."""
    null = layout.insert_null(group, game, name, game.position, visible=False)
    for row in range(PAGE_ROWS):
        for sprite in game.children[:per_row]:
            x, y = sprite.position
            layout.insert_sprite(null, sprite, f"hf_{sprite.name[len('ui020_'):]}_r{row}", (x, y - PITCH * row))


def _texts_below(layout, group: Pane, last: Pane, rows: range, last_row: int) -> None:
    for row in rows:
        x, y = last.position
        layout.insert_text(group, last, text_name(row, group.name == BIG_TEXTS), (x, y - PITCH * (row - last_row)),
                           last.size, "")


def build(data: bytes) -> bytes:
    """ui020 with the panes of every list size. A layout that already has them is returned as it is."""
    layout = parse_lyt(data)
    if any(pane.name == small_frame(1) for pane in layout.panes):
        return data
    groups = {group.name: group for group in layout.roots}

    small = groups[SMALL_GROUP]
    _frames(layout, small, _child(small, SMALL_FRAME), SMALL_ROWS, small_frame)
    _rows(layout, small, _child(small, SMALL_STRIPS), SMALL_STRIPS_OURS, 2)
    texts = groups[SMALL_TEXTS]
    _texts_below(layout, texts, _child(texts, text_name(SMALL_ROWS - 1, False)), range(SMALL_ROWS, PAGE_ROWS),
                 SMALL_ROWS - 1)

    big = groups[BIG_GROUP]
    _frames(layout, big, _child(big, BIG_FRAME), BIG_ROWS, big_frame)
    _rows(layout, big, _child(big, BIG_STRIPS), BIG_STRIPS_OURS, 2)
    backs = groups[BIG_BACKS_GROUP]
    _rows(layout, backs, _child(backs, BIG_BACKS), BIG_BACKS_OURS, 1)
    texts = groups[BIG_TEXTS]
    _texts_below(layout, texts, _child(texts, text_name(BIG_ROWS - 1, True)), range(BIG_ROWS, PAGE_ROWS),
                 BIG_ROWS - 1)
    return layout.to_bytes()


def patch_arc(raw: bytes, lang: str) -> bytes:
    """core_common.arc of `lang` with ui020's panes of every list size."""
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


__all__ = ["ARC", "BIG_BACKS", "BIG_BACKS_OURS", "BIG_FRAME", "BIG_ROWS", "BIG_STRIPS", "BIG_STRIPS_OURS", "LAYOUT",
           "NAMED", "PAGE_ROWS", "PITCH", "SMALL_FRAME", "SMALL_FRAME_4", "SMALL_GAME_SIZES", "SMALL_ROWS",
           "SMALL_STRIPS", "SMALL_STRIPS_OURS", "big_frame", "build", "hashes", "patch_arc", "small_frame",
           "ten_row_files", "text_name"]
