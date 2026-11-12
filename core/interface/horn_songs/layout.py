"""The Hunting Horn's songs' game files: a layout of our own in each
language's core_quest.arc, which the quest loads with its other layouts (the quest's shared hooks,
interface/quest_layouts/).

The layout `lyt\\quest\\hf_horn` has one root group, `hf_horn`, with the list's null `hf_horn_list` at the list's top
right corner and ROWS row nulls under it (hidden when the layout loads), each holding its bar (a sprite of our white
texture, the whole row, drawn first: behind), its song's name (a text with room for TEXT_ROOM characters, left-aligned
in its box) and NOTES note sprites (the HUD's own note pictures, qst00), left of the name; horn_songs.c fills, colours
and shows them. The bars touch: the shown rows are one dark block. The records are copies of the HUD's: the horn's
notes group, a note's null and its picture (ui202_hue, ui202_onpu00, ui202_jyakushi00) and the item selector's name
(ui205_m_00), in the same language. The places come from the curated horn_songs.json, at the HUD's full size: the
list flush with the screen's right edge, its top `minimap_gap` pixels under the minimap's bottom edge. The group has
a scale of its own at each HUD size (`list_scale`: a smaller HUD keeps the list readable), applied about the top right
corner (scale.py) with its top placed from the minimap's scaled bottom edge, and a wider picture moves it with the
HUD's top right (interface/hud/anchors.py hud_entries).
"""

import json
import struct
from collections.abc import Iterator, Mapping
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.files.gui.lyt import HEADER, LYT_TYPE_HASH, MAGIC, RECORD_SIZES, VERSION, Layout, PaneKind, name_hash, \
    parse_lyt
from core.game.files.gui.tex import LA4, TEX_TYPE_HASH, new_tex
from core.interface.hud.build import LANGUAGES, GameFiles
from core.interface.hud.scale import NO_EDGE, SCREEN_HALF_HEIGHT, SCREEN_HALF_WIDTH, Anchor, scale_hud

TUNING_FILE = CURATED_DIR / "horn_songs.json"
ARC = "core_quest.arc"
NAME = "hf_horn"                        # the layout's short name (interface/hud/anchors.py hud_entries)
LAYOUT_PATH = "lyt\\quest\\hf_horn"     # what the quest's shared hooks load; the entry is "<lang>\\" + it
TEXTURE = "lyt\\quest\\texture\\hf_horn_GSM_NOMIP"     # the bars' white texture
GROUP, LIST = "hf_horn", "hf_horn_list"
HUD = "lyt\\quest\\ui202"               # the horn's notes in the HUD: the records copied
TEMPLATE_GROUP, TEMPLATE_NULL, TEMPLATE_NOTE = "ui202_hue", "ui202_onpu00", "ui202_jyakushi00"
NAMES = "lyt\\quest\\ui205"             # the item selector: its item's name
TEMPLATE_TEXT = "ui205_m_00"
ROWS, NOTES = 8, 4                      # horn_songs.c ROWS, NOTES
ANCHOR = Anchor.TOP_RIGHT
SCREEN_WIDTH = 2 * SCREEN_HALF_WIDTH
MINIMAP_SIDE = 128.0                    # the minimap: 128 x 128 at the top right corner
NOTE_CELL = 16 / 512                    # a note's cell in qst00 (512 x 512): the template's region w, h
NOTE_INK = 10 / 16                      # the note's drawn width in its 16-texel cell (texels 3-12), outline included
TEXT_ROOM = 32                          # the name's characters of room: the longest of the five languages has 27
WHITE_SIDE = 8                          # the white texture's side (the 3DS draws textures of 8 and up)
CENTRE = 4                              # a sprite's or a text box's origin: its x, y is its centre
LEFT = 0                                # a text's lines: left-aligned in the box


class HornSongsError(ValueError):
    """The curated tuning is not what the layout can hold."""


def load_tuning(path: Path = TUNING_FILE) -> dict:
    """The curated tuning, checked: every key as its value; refuses a colour that is not four bytes, a note or a name
    taller than its row's band, notes drawn over each other and letters over each other."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tuning = {}
    for key in ("minimap_gap", "list_scale", "row", "font", "colours", "group"):
        entry = raw.get(key)
        if not isinstance(entry, dict) or "value" not in entry or not isinstance(entry.get("description"), str):
            raise HornSongsError(f"horn_songs.json: {key} must be {{\"value\": ..., \"description\": ...}}")
        tuning[key] = entry["value"]
    colours = tuning["colours"]
    states = ("idle", "partial", "full")
    if set(colours) != {"text", "bar", "notes"} or set(colours["text"]) != set(states) \
            or set(colours["bar"]) != set(states) or set(colours["notes"]) != {"waiting", "lit"}:
        raise HornSongsError("horn_songs.json: colours are text and bar (idle, partial, full) and notes (waiting, lit)")
    if any(len(c) != 4 or not all(0 <= x <= 255 for x in c) for group in colours.values() for c in group.values()):
        raise HornSongsError("horn_songs.json: a colour is four bytes (RGBA)")
    table = tuning["list_scale"]
    if not table or any(not 0 < scale <= 1.5 for scale in table.values()) \
            or any(not 0 < int(percent) <= 100 for percent in table):
        raise HornSongsError("horn_songs.json: list_scale maps HUD sizes (percent, 100 or less) to scales up to 1.5")
    if tuning["minimap_gap"] < 0:
        raise HornSongsError("horn_songs.json: the gap under the minimap is not negative")
    row, font = tuning["row"], tuning["font"]
    if not 0 < row["height"] <= row["pitch"] or not 0 < row["note_size"] <= row["height"] \
            or not 0 < font["size"] <= row["height"]:
        raise HornSongsError("horn_songs.json: a row's band holds its notes and its name, and a row its pitch")
    if row["note_pitch"] < row["note_size"] * NOTE_INK:
        raise HornSongsError("horn_songs.json: a note's pitch is under its drawn width (notes would overlap)")
    if font["spacing"] < 0:
        raise HornSongsError("horn_songs.json: the font's spacing is not negative (letters would overlap)")
    return tuning


def row_width(tuning: dict) -> float:
    """A row's width, its bar's: the padding, the notes' column (NOTES notes note_pitch apart), the gap, the name's box
    and the padding."""
    row = tuning["row"]
    notes = (NOTES - 1) * row["note_pitch"] + row["note_size"]
    return 2 * row["padding"] + notes + row["text_gap"] + row["text_width"]


def list_scale(factor: float, tuning: dict | None = None) -> float:
    """The list's own scale at the HUD size `factor` (1.0 the full size): the tuning's table, linear between its
    sizes, the nearest one outside them."""
    table = sorted((int(percent) / 100, scale) for percent, scale in (tuning or load_tuning())["list_scale"].items())
    if factor <= table[0][0]:
        return table[0][1]
    for (low, a), (high, b) in zip(table, table[1:]):
        if factor <= high:
            return a + (b - a) * (factor - low) / (high - low)
    return table[-1][1]


def list_box(tuning: dict | None = None, factor: float = 1.0) -> tuple[float, float, float, float]:
    """The list with all its rows, in top-screen pixels at the HUD size `factor` and the game's 5:3 shape (left, top,
    right, bottom): flush with the screen's right edge, its top `minimap_gap` under the minimap's (scaled) bottom."""
    tuning = tuning or load_tuning()
    scale = list_scale(factor, tuning)
    right, top = SCREEN_WIDTH, MINIMAP_SIDE * factor + tuning["minimap_gap"]
    row = tuning["row"]
    return (right - row_width(tuning) * scale, top, right,
            top + ((ROWS - 1) * row["pitch"] + row["height"]) * scale)


def row_name(row: int) -> str:
    return f"{GROUP}_{row:02d}"


def pane_names(row: int) -> list[str]:
    """A row's panes in file order: its bar, its name, its notes from the first one played."""
    base = row_name(row)
    return [f"{base}_bar", f"{base}_name"] + [f"{base}_n{i}" for i in range(NOTES)]


def texture() -> bytes:
    """The bars' picture: white and opaque (the game's vertex colours tint it)."""
    tex = new_tex(WHITE_SIDE, WHITE_SIDE, LA4)
    tex.set_region(0, 0, WHITE_SIDE, WHITE_SIDE, bytes((255, 255, 255, 255)) * WHITE_SIDE * WHITE_SIDE)
    return tex.to_bytes()


def _padded(text: str) -> bytes:
    encoded = text.encode("ascii") + b"\x00"
    return encoded + b"\x00" * (-len(encoded) % 4)


def _skeleton(source: Layout, textures: list[str]) -> Layout:
    """A layout of one empty root group GROUP (a copy of the template's group record) and `textures`."""
    group = source.find(TEMPLATE_GROUP)
    texture_word = struct.unpack_from("<I", source.data, source.texture_table)[0]
    last = source.panes[-1]
    last_end = last.offset + RECORD_SIZES[last.kind]
    record = bytearray(source.data[group.offset:group.offset + RECORD_SIZES[PaneKind.GROUP]])
    names = b"".join(_padded(name) for name in textures)
    texture_table = HEADER.size
    pane_table = texture_table + 8 * len(textures) + len(names)
    name_at = pane_table + 8 + len(record)
    tail = name_at + len(_padded(GROUP))
    struct.pack_into("<III2f", record, 0, name_hash(GROUP), name_at, RECORD_SIZES[PaneKind.GROUP], 0.0, 0.0)
    record[-8:] = source.data[last_end - 8:last_end]          # the end of the pane table
    out = bytearray(HEADER.pack(MAGIC, VERSION, 1, len(textures), 0, 0, 0, 0, 0, texture_table, pane_table, tail))
    at = texture_table + 8 * len(textures)
    for name in textures:
        out += struct.pack("<II", texture_word, at)
        at += len(_padded(name))
    out += names + struct.pack("<II", PaneKind.GROUP, 0) + record + _padded(GROUP) + bytes(4)
    return parse_lyt(bytes(out))


def build_layout(hud: bytes, names: bytes, factor: float = 1.0, edge: tuple[float, float] = NO_EDGE,
                 tuning: dict | None = None) -> bytes:
    """Our layout, its records copied from the HUD's layout `hud` (ui202) and the item selector's `names` (ui205) of
    one language, at the HUD size `factor` and the interface's `edge` (scale.py)."""
    tuning = tuning or load_tuning()
    source, selector = parse_lyt(hud), parse_lyt(names)
    note_t, null_t, text_t = source.find(TEMPLATE_NOTE), source.find(TEMPLATE_NULL), selector.find(TEMPLATE_TEXT)
    layout = _skeleton(source, [source.textures[note_t.texture], TEXTURE])
    notes_texture, bar_texture = 0, 1
    row, font, colours = tuning["row"], tuning["font"], tuning["colours"]
    scale = list_scale(factor, tuning)
    # laid out at the list's full size, then scaled by `scale` about the corner: the top is where it lands under the
    # minimap, which the HUD size scales on its own
    top = (MINIMAP_SIDE * factor + tuning["minimap_gap"]) / scale
    right = SCREEN_WIDTH
    group = layout.find(GROUP)
    holder = layout.insert_null(group, null_t, LIST, (SCREEN_HALF_WIDTH - right, SCREEN_HALF_HEIGHT - top))
    # x from the row's right edge (the layout's x grows leftwards), in pixels: the padding, the name's box, the gap, the
    # notes from the last one played to the first, the padding
    width, height = row_width(tuning), row["height"]
    first_note = width - row["padding"] - row["note_size"] / 2
    for r in range(ROWS):
        bar_name, text_name, *note_names = pane_names(r)
        line = layout.insert_null(holder, null_t, row_name(r), (0.0, -float(r * row["pitch"])), visible=False)
        bar = layout.insert_sprite(line, note_t, bar_name, (width / 2, -height / 2), region=(0.0, 0.0, 1.0, 1.0),
                                   texture=bar_texture)
        bar.size = (width, height)
        bar.colors = [tuple(colours["bar"]["idle"])] * 4
        text = layout.insert_text(line, text_t, text_name, (row["padding"] + row["text_width"] / 2, -height / 2),
                                  (row["text_width"], height), " " * TEXT_ROOM)
        text.font_size = (font["size"], font["size"])
        text.spacing = (font["spacing"], 0.0)
        text.text_align = LEFT
        text.text_origin = CENTRE
        text.colors = [tuple(colours["text"]["idle"])] * 3 + [text.colors[3]]
        for i, name in enumerate(note_names):
            x = first_note - i * row["note_pitch"]
            note = layout.insert_sprite(line, note_t, name, (x, -height / 2), texture=notes_texture)
            note.size = (row["note_size"], row["note_size"])
            note.origin = CENTRE
            note.colors = [tuple(colours["notes"]["waiting"])] * 4
    # the loader takes a node for each null and one for each text's holder
    nulls = sum(1 for p in layout.panes if p.kind in (PaneKind.NULL, PaneKind.TEXT))
    struct.pack_into("<I", layout.data, 0x10, nulls)
    scale_hud(layout, [], scale, {GROUP: ANCHOR}, edge=edge)
    return layout.to_bytes()


def patch_arc(raw: bytes, lang: str, factor: float = 1.0, edge: tuple[float, float] = NO_EDGE,
              tuning: dict | None = None, templates: bytes | None = None) -> bytes:
    """core_quest.arc of `lang` with our texture and layout added (after its own entries; the texture first), the
    records copied from `templates` (the game's own core_quest.arc of `lang`; default `raw`). An ARC that already has
    them is returned as it is."""
    arc = parse_arc(raw)
    names = {entry.name for entry in arc.entries}
    entry_name = f"{lang}\\{LAYOUT_PATH}"
    if entry_name in names:
        return raw
    source = arc if templates is None else parse_arc(templates)
    found = {e.name: e for e in source.entries if e.type_hash == LYT_TYPE_HASH}
    hud, selector = found.get(f"{lang}\\{HUD}"), found.get(f"{lang}\\{NAMES}")
    if hud is None or selector is None:
        raise ValueError(f"{ARC} of {lang} has no {HUD} or {NAMES}")
    tex_flags = next((e.flags for e in arc.entries if e.type_hash == TEX_TYPE_HASH), hud.flags)
    if TEXTURE not in names:
        arc.entries.append(ArcEntry(TEXTURE, TEX_TYPE_HASH, texture(), tex_flags))
    arc.entries.append(ArcEntry(entry_name, LYT_TYPE_HASH, build_layout(hud.data, selector.data, factor, edge, tuning),
                                hud.flags))
    return write_arc(arc)


def horn_songs_files(rom: GameFiles, files: Mapping[str, bytes] | None = None, factor: float = 1.0,
                     edge: tuple[float, float] = NO_EDGE) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of each language's core_quest.arc with our layout at the HUD size `factor` and the
    interface's `edge`; an ARC already in `files` (an earlier step's) is patched as it is, the others start from the
    game's. The records are copied from the game's own layouts, never an earlier step's scaled copies."""
    files = files or {}
    tuning = load_tuning()
    for lang in LANGUAGES:
        path = f"{lang}/data/{ARC}"
        game = rom.read(path)
        yield path, patch_arc(files.get(path) or game, lang, factor, edge, tuning, templates=game)


def horn_songs_paths(mod_dir: Path) -> list[Path]:
    """Every file the layout can leave in a mod folder."""
    return [Path(mod_dir) / "romfs" / lang / "data" / ARC for lang in LANGUAGES]


def remove_horn_songs_files(mod_dir: Path) -> None:
    for path in horn_songs_paths(mod_dir):
        path.unlink(missing_ok=True)


__all__ = ["ANCHOR", "ARC", "GROUP", "LAYOUT_PATH", "LIST", "NAME", "NOTES", "NOTE_CELL", "ROWS", "TEXTURE",
           "build_layout", "horn_songs_files", "horn_songs_paths", "list_box", "list_scale", "load_tuning",
           "pane_names",
           "patch_arc", "remove_horn_songs_files", "row_name", "row_width", "texture"]
