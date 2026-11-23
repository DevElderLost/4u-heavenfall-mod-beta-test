"""Change Appearance at an item box away from home (option `box_equipment`).

The box's line 6 opens the hunter's edit screen, which binds the ten root groups of the layout ui415 (FUN_005976a8,
its table GAME_SYMBOLS `appearance_binds`). Only the rooms' areas load that layout: their stage lists name it and their
map ARCs hold it. A town area's layouts are the lobby's (FUN_00c0ff8c, from core_lobby.arc, loaded with the town) and
its stage list's (FUN_00c10ce8, the table STAGE_LISTS: per stage kind a list of layout paths and one of screen bytes,
or none); a path whose file no loaded ARC holds is read as a null file and faults (FUN_00c0f474 reads its +0x64), so a
list may name ui415 only where an ARC holds it. Here every town area gets it:

* `lobby_files`: each language's core_lobby.arc gets the room's ui415 (ROOM_ARC's) and the textures it names that the
  room's ARC holds (the others are core_common's), the textures first: a layout binds its textures by path as the
  archive loads. A room's map ARC still holds its
  own copy: an archive whose entry's path is registered already only takes a reference to the first, so the rooms load
  the lobby's;
* `patch_stage_lists` (block `box_appearance_lists`): every stage kind whose game's list lacks ui415 (KINDS_WITHOUT)
  gets that list with ui415 after the others (the earlier layouts keep their places), or a list of ui415 alone for a
  kind without one; its screen byte is the rooms'.

The box's menu offers Change Appearance where ui415's groups are loaded (mod_options.c `mod_box_count`): an area these
lists do not reach keeps the six lines. The two halves go together (pipeline.py: `box_appearance`).
"""

import struct
from collections.abc import Mapping

from core.game.executable.blocks import BOX_APPEARANCE_LISTS_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, load_layout, note_game_pointers
from core.game.files.arc import ArcEntry, parse_arc, write_arc
from core.game.files.gui.lyt import LYT_TYPE_HASH, Layout as LytLayout
from core.game.files.gui.tex import TEX_TYPE_HASH
from core.interface.hud.build import LANGUAGES, GameFiles

BLOCK = "box_appearance_lists"
LAYOUT_NAME = "ui415"                       # the hunter's edit screen (pages, colours, camera)
LAYOUT_PATH = "lyt\\lobby\\ui415"           # its path in the stage lists (the language is put in front when loaded)
ROOM_ARC = "v00a01_map.arc"                 # a room's map ARC: ui415 and its lobby textures
LOBBY_ARC = "core_lobby.arc"                # loaded with the town, before any stage list (FUN_00b7e290)

STAGE_LISTS = 0xFB8088                      # FUN_00c10ce8's table: per stage kind (layout paths, screen bytes)
STAGE_ENTRY = 8
STAGE_KINDS = 17
ROOM_LIST = (0xEFE05C, 0xEFE088)            # the rooms' list (kinds 3, 5, 7, 10, 16): ui415 is its 7th path
ROOM_INDEX = 6
NO_LIST = (0, 0)
# The table as the game has it: kind -> (paths, bytes); NO_LIST for a kind without a list
GAME_ENTRIES = {0: NO_LIST, 1: (0xEFE040, 0xEFE054), 2: NO_LIST, 3: ROOM_LIST, 4: NO_LIST, 5: ROOM_LIST, 6: NO_LIST,
                7: ROOM_LIST, 8: (0xEFE094, 0xEFE0B0), 9: (0xEFE030, 0xEFE03C), 10: ROOM_LIST, 11: NO_LIST,
                12: (0xEFE040, 0xEFE054), 13: (0xEFE0B8, 0xEFE0C8), 14: (0xEFE0D8, 0xEFE0F0),
                15: (0xEFE0CC, 0xEFE0D4), 16: ROOM_LIST}
KINDS_WITH = (3, 5, 7, 8, 10, 16)           # the kinds whose game's list names ui415 (the rooms)
KINDS_WITHOUT = tuple(kind for kind in range(STAGE_KINDS) if kind not in KINDS_WITH)
LIST_END = 0xFF                             # the byte after a list's screen bytes


class BoxAppearanceError(ValueError):
    """The game's files are not what the copy expects."""


# ---- the RomFS: ui415 in the lobby's ARC

def _layout_entry(arc, lang: str) -> ArcEntry | None:
    name = f"{lang}\\{LAYOUT_PATH}"
    return next((e for e in arc.entries if e.type_hash == LYT_TYPE_HASH and e.name == name), None)


def add_appearance_layout(target_raw: bytes, room_raw: bytes, lang: str) -> bytes:
    """The ARC `target_raw` with the room's ui415 (`room_raw`, the same language's room ARC) at its end, and before it
    every texture that layout names which the room's ARC holds and the target lacks, in the room's order. An ARC that
    already holds ui415 is returned as it is."""
    target, room = parse_arc(target_raw), parse_arc(room_raw)
    if _layout_entry(target, lang) is not None:
        return target_raw
    layout = _layout_entry(room, lang)
    if layout is None:
        raise BoxAppearanceError(f"{lang}'s {ROOM_ARC} has no {LAYOUT_PATH}")
    named = set(LytLayout(layout.data).textures)
    held = {e.name for e in target.entries if e.type_hash == TEX_TYPE_HASH}
    copied = [e for e in room.entries if e.type_hash == TEX_TYPE_HASH and e.name in named and e.name not in held]
    target.entries += [ArcEntry(e.name, e.type_hash, e.data, e.flags) for e in (*copied, layout)]
    return write_arc(target)


def lobby_files(rom: GameFiles, files: Mapping[str, bytes] | None = None) -> dict[str, bytes]:
    """(RomFS path -> ARC) of each language's core_lobby.arc with the room's ui415 (`add_appearance_layout`), added to
    the copy in `files` (an earlier step's) or to the game's; the room's ARC is read the same way."""
    files = files or {}
    out = {}
    for lang in LANGUAGES:
        room_path, path = f"{lang}/data/{ROOM_ARC}", f"{lang}/data/{LOBBY_ARC}"
        room = files.get(room_path) or rom.read(room_path)
        out[path] = add_appearance_layout(files.get(path) or rom.read(path), room, lang)
    return out


# ---- the executable: every town area's stage list names ui415

def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def path_string(code: bytes, address: int) -> str | None:
    """The layout path at `address` of `code`, None when there is none."""
    start = address - BASE_ADDRESS
    if not 0 <= start < len(code):
        return None
    end = code.find(b"\0", start, start + 0x40)
    return code[start:end].decode("latin1") if end > start else None


def _paths(code: bytes, address: int) -> list[int]:
    out = []
    while address and (pointer := _word(code, address + 4 * len(out))) and len(out) < 16:
        out.append(pointer)
    return out


def _entry(code: bytes, kind: int) -> tuple[int, int]:
    return struct.unpack_from("<2I", code, STAGE_LISTS + STAGE_ENTRY * kind - BASE_ADDRESS)


def supports_stage_lists(code: bytes) -> bool:
    """`code` (the update's executable, canonical) has the game's stage lists: the table's entries, the rooms' lists
    naming ui415 and the others without it."""
    if any(_entry(code, kind) != entry for kind, entry in GAME_ENTRIES.items()):
        return False
    room = _paths(code, ROOM_LIST[0])
    if len(room) <= ROOM_INDEX or path_string(code, room[ROOM_INDEX]) != LAYOUT_PATH:
        return False
    for kind in range(STAGE_KINDS):
        names = [path_string(code, p) for p in _paths(code, GAME_ENTRIES[kind][0])]
        if None in names or (LAYOUT_PATH in names) != (kind in KINDS_WITH):
            return False
    return True


def lists_data(code: bytes, base: int) -> tuple[bytes, dict[tuple[int, int], tuple[int, int]], list[tuple[int, int]]]:
    """The block's bytes at address `base`: per distinct game list of KINDS_WITHOUT (NO_LIST among them), its paths
    with ui415's after them and a 0, then its screen bytes with the rooms' byte for ui415 and LIST_END (padded to a word
    with it); the game's (paths, bytes) -> the block's, and the (offset, size) of each path array (the pointers the
    versions move)."""
    layout_path = _paths(code, ROOM_LIST[0])[ROOM_INDEX]
    room_byte = code[ROOM_LIST[1] + ROOM_INDEX - BASE_ADDRESS]
    data, moved, arrays = bytearray(), {}, []
    for entry in dict.fromkeys(GAME_ENTRIES[kind] for kind in KINDS_WITHOUT):
        paths = [*_paths(code, entry[0]), layout_path]
        own = code[entry[1] - BASE_ADDRESS:entry[1] - BASE_ADDRESS + len(paths) - 1] if entry[1] else b""
        screens = bytes(own) + bytes((room_byte,))
        at = len(data)
        data += struct.pack(f"<{len(paths) + 1}I", *paths, 0)
        arrays.append((at, 4 * len(paths)))
        screens += bytes((LIST_END,)) * (4 - len(screens) % 4)
        moved[entry] = (base + at, base + len(data))
        data += screens
    if len(data) > BOX_APPEARANCE_LISTS_SIZE:
        raise CodeSpaceError(f"{BLOCK}: the lists take {len(data)} bytes, the block {BOX_APPEARANCE_LISTS_SIZE}")
    return bytes(data) + bytes(BOX_APPEARANCE_LISTS_SIZE - len(data)), moved, arrays


def patch_stage_lists(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` with every stage kind of KINDS_WITHOUT loading ui415 too: its list copied into the block with ui415
    after the others (a kind without a list gets one of ui415 alone), and its entry of STAGE_LISTS pointing at the
    copy. Refuses an executable whose lists are not the game's (patched already, or another game)."""
    if not supports_stage_lists(code):
        raise CodeSpaceError("the stage lists are not the update's: already patched or another game")
    layout = layout or load_layout()
    base = layout.address(BLOCK)
    data, moved, arrays = lists_data(code, base)
    out = bytearray(code)
    layout.place(out, BLOCK, data)
    for at, size in arrays:
        note_game_pointers(base + at, data[at:at + size])
    for kind in KINDS_WITHOUT:
        struct.pack_into("<2I", out, STAGE_LISTS + STAGE_ENTRY * kind - BASE_ADDRESS, *moved[GAME_ENTRIES[kind]])
    return bytes(out)


def stage_layouts(kind: int) -> tuple[str, ...]:
    """The layouts this module adds to stage kind `kind`'s list (the game GUI's pool check counts them)."""
    return (LAYOUT_NAME,) if kind in KINDS_WITHOUT else ()


__all__ = ["BLOCK", "KINDS_WITH", "KINDS_WITHOUT", "LOBBY_ARC", "BoxAppearanceError", "add_appearance_layout",
           "lists_data", "lobby_files", "patch_stage_lists", "path_string", "stage_layouts", "supports_stage_lists"]
