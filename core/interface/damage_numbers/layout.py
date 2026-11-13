"""Damage Numbers' game files: a layout of our own and its picture in
each language's core_quest.arc, which the quest loads with its other layouts (interface/quest_layouts).

The layout `lyt\\quest\\hf_dmg` has one root group, `hf_dmg`, with SLOTS nulls (one number each, hidden when the
layout loads), each holding EFFECTS sprites (the critical marks, drawn first: behind) and DIGITS sprites (the digits);
damage_numbers.c places, sizes, tints and shows them every frame. Its records are copies of the target marker's
(ui211: its group, its null ui211_target00, its arrow ui211_yazu00, which draw from an LA4 texture as ours does), with
our names, centred sprites and our one texture, `lyt\\quest\\texture\\hf_dmg_GSM_NOMIP`: the atlas of
art/damage_numbers.png (tools/build/build_damage_numbers_art.py) as an LA4 texture, placed before the layout in the same
archive so the layout finds it. A new layout, not groups added to a quest layout: the quest's range of group indices
is full.
"""

import json
import struct
from collections.abc import Iterator, Mapping
from functools import cache
from pathlib import Path

from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.files.gui.lyt import END, HEADER, LYT_TYPE_HASH, MAGIC, RECORD_SIZES, VERSION, PaneKind, name_hash, \
    parse_lyt
from core.game.files.gui.png import read_png
from core.game.files.gui.tex import LA4, TEX_TYPE_HASH, new_tex
from core.interface.hud.build import LANGUAGES, GameFiles

ART = Path(__file__).resolve().parent / "art"
PICTURE, CELLS = ART / "damage_numbers.png", ART / "damage_numbers_atlas.json"
ARC = "core_quest.arc"
LAYOUT_PATH = "lyt\\quest\\hf_dmg"      # its quest_layouts entry; the arc entry is "<lang>\\" + it
TEXTURE = "lyt\\quest\\texture\\hf_dmg_GSM_NOMIP"
GROUP = "hf_dmg"
TEMPLATE = "lyt\\quest\\ui211"          # the target marker: the records copied
TEMPLATE_GROUP, TEMPLATE_NULL, TEMPLATE_SPRITE = "ui211_target", "ui211_target00", "ui211_yazu00"
SLOTS, EFFECTS, DIGITS = 16, 2, 6        # damage_numbers.c SLOTS, EFFECTS, DIGITS
CENTRE = 4                               # a sprite's origin: its x, y is its centre


def slot_name(slot: int) -> str:
    return f"{GROUP}_{slot:02d}"


def sprite_names(slot: int) -> list[str]:
    """A slot's sprites in the order the code walks them: the marks, then the digits from the left."""
    return [f"{slot_name(slot)}_e{i}" for i in range(EFFECTS)] + [f"{slot_name(slot)}_d{i}" for i in range(DIGITS)]


@cache
def atlas() -> dict:
    """The art's cells (art/damage_numbers_atlas.json): {"size": [w, h], "styles": {style: {"digits": [[x, y, w, h]
    ...]}}, "effects": {mark: [x, y, w, h]}}, in pixels from the top left."""
    return json.loads(CELLS.read_text(encoding="utf-8"))


def texture() -> bytes:
    """The atlas as an LA4 texture (grey and alpha: the game's vertex colours tint it)."""
    width, height, rgba = read_png(PICTURE.read_bytes())
    tex = new_tex(width, height, LA4)
    tex.set_region(0, 0, width, height, rgba)
    return tex.to_bytes()


def _padded(text: str) -> bytes:
    encoded = text.encode("ascii") + b"\x00"
    return encoded + b"\x00" * (-len(encoded) % 4)


def build_layout(template: bytes) -> bytes:
    """Our layout, its records copied from the target marker's layout `template` (ui211)."""
    source = parse_lyt(template)
    group_t, null_t, sprite_t = (source.find(name) for name in (TEMPLATE_GROUP, TEMPLATE_NULL, TEMPLATE_SPRITE))
    texture_word = struct.unpack_from("<I", source.data, source.texture_table)[0]
    end_word = bytes(source.data[source.panes[-1].offset + RECORD_SIZES[source.panes[-1].kind] - 8:
                                 source.panes[-1].offset + RECORD_SIZES[source.panes[-1].kind]])

    def record(template_pane, name: str) -> bytearray:
        size = RECORD_SIZES[template_pane.kind]
        return bytearray(source.data[template_pane.offset:template_pane.offset + size]), name

    panes = [(PaneKind.GROUP, 0, *record(group_t, GROUP))]
    for slot in range(SLOTS):
        null, name = record(null_t, slot_name(slot))
        struct.pack_into("<3f", null, 0x0C, 0.0, 0.0, 0.0)
        struct.pack_into("<2f", null, 0x18, 1.0, 1.0)
        null[0x20:0x24] = bytes((255, 255, 255, 255))
        struct.pack_into("<I", null, 0x2C, 0)                       # hidden when the layout loads
        panes.append((PaneKind.NULL, 1, null, name))
        for sprite_name in sprite_names(slot):
            sprite, _ = record(sprite_t, sprite_name)
            struct.pack_into("<3f", sprite, 0x0C, 0.0, 0.0, 0.0)
            struct.pack_into("<4f", sprite, 0x18, 0.0, 0.0, 1.0, 1.0)     # size 0 until the code sizes it; scale 1
            struct.pack_into("<4f", sprite, 0x28, 0.0, 0.0, 0.0, 0.0)
            sprite[0x38:0x48] = bytes((255, 255, 255, 255)) * 4
            struct.pack_into("<I", sprite, 0x50, CENTRE)
            struct.pack_into("<I", sprite, 0x58, 0)                     # our one texture
            struct.pack_into("<I", sprite, 0x60, 0)                     # hidden
            panes.append((PaneKind.SPRITE, 2, sprite, sprite_name))

    texture_table = HEADER.size
    texture_name = texture_table + 8
    pane_table = texture_name + len(_padded(TEXTURE))
    names_at = pane_table + 8 + sum(len(r) for _, _, r, _ in panes)
    name_offsets, at = [], names_at
    for *_, name in panes:
        name_offsets.append(at)
        at += len(_padded(name))
    tail = at
    # each record's size (a container's: its subtree's), its name, and the next pane's kind and depth at its end
    subtree = [RECORD_SIZES[kind] for kind, *_ in panes]
    for i in range(len(panes) - 1, -1, -1):
        depth = panes[i][1]
        j = i + 1
        while j < len(panes) and panes[j][1] > depth:
            if panes[j][1] == depth + 1:
                subtree[i] += subtree[j]
            j += 1
    body = bytearray()
    for i, (_kind, _depth, data, name) in enumerate(panes):
        struct.pack_into("<III", data, 0, name_hash(name), name_offsets[i], subtree[i])
        data[-8:] = struct.pack("<II", panes[i + 1][0], panes[i + 1][1]) if i + 1 < len(panes) else end_word
        body += data
    nulls = sum(1 for kind, *_ in panes if kind == PaneKind.NULL)
    sprites = sum(1 for kind, *_ in panes if kind == PaneKind.SPRITE)
    out = bytearray(HEADER.pack(MAGIC, VERSION, 1, 1, nulls, sprites, 0, 0, 0, texture_table, pane_table, tail))
    out += struct.pack("<II", texture_word, texture_name) + _padded(TEXTURE)
    out += struct.pack("<II", PaneKind.GROUP, 0) + body
    out += b"".join(_padded(name) for *_, name in panes)
    out += bytes(4)                                                     # the trailing table: a word per root group
    assert len(out) == tail + 4 and END == 0xFF
    return bytes(out)


def patch_arc(raw: bytes, lang: str) -> bytes:
    """core_quest.arc of `lang` with our texture and layout added (after its own entries; the texture first). An ARC
    that already has them is returned as it is."""
    arc = parse_arc(raw)
    names = {entry.name for entry in arc.entries}
    entry_name = f"{lang}\\{LAYOUT_PATH}"
    if entry_name in names:
        return raw
    template = next((e for e in arc.entries if e.type_hash == LYT_TYPE_HASH and e.name == f"{lang}\\{TEMPLATE}"), None)
    if template is None:
        raise ValueError(f"{ARC} of {lang} has no {TEMPLATE}")
    tex_flags = next((e.flags for e in arc.entries if e.type_hash == TEX_TYPE_HASH), template.flags)
    if TEXTURE not in names:
        arc.entries.append(ArcEntry(TEXTURE, TEX_TYPE_HASH, texture(), tex_flags))
    arc.entries.append(ArcEntry(entry_name, LYT_TYPE_HASH, build_layout(template.data), template.flags))
    return write_arc(arc)


def damage_numbers_files(rom: GameFiles, files: Mapping[str, bytes] | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of each language's core_quest.arc with our layout; an ARC already in `files` (an earlier
    step's) is patched as it is, the others start from the game's."""
    files = files or {}
    for lang in LANGUAGES:
        path = f"{lang}/data/{ARC}"
        yield path, patch_arc(files.get(path) or rom.read(path), lang)


def damage_numbers_paths(mod_dir: Path) -> list[Path]:
    """Every file the layout can leave in a mod folder."""
    return [Path(mod_dir) / "romfs" / lang / "data" / ARC for lang in LANGUAGES]


def remove_damage_numbers_files(mod_dir: Path) -> None:
    for path in damage_numbers_paths(mod_dir):
        path.unlink(missing_ok=True)


__all__ = ["ARC", "DIGITS", "EFFECTS", "GROUP", "LAYOUT_PATH", "SLOTS", "TEXTURE", "atlas", "build_layout",
           "damage_numbers_files", "damage_numbers_paths", "patch_arc", "remove_damage_numbers_files", "slot_name",
           "sprite_names", "texture"]
