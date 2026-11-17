"""The jukebox's engine in the executable: the block `jukebox` (jukebox.c and its
units, jukebox.h), its data block (each track id's request, the replaced places' requests, the limits, the defaults,
the menu's messages and lists) and three changes to the game's code (the menu's own: menu_patch.py):

* FUN_00304990 (the town's theme selector): its exit, `mov r0, r4` at PICK_EXIT, calls jukebox_pick_stub, which
  returns the request the selector gives (the playlist's song in place of a replaced place's request);
* FUN_00302ba0 (the sound manager's commands): command 2's first call of FUN_00304990 (COMMAND_PICK) calls
  jukebox_command_pick, which runs the jukebox's frame (jukebox_tick) and then that call;
* FUN_0030ace0 (the resume list's lookup): its first three instructions become `push {r1, lr}; bl
  jukebox_resume_index; pop {r1, pc}`, so the lookup answers from jukebox_resume_index (the game's answer for the
  game's requests).

Update's executable only; the version maps carry it to the base games. The inputs (the catalogue and the request of
each track the build has, `queue.jukebox_files`) come as arguments, so nothing of the game is read here.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping, Sequence
from typing import Protocol

from core.game.executable.blocks import JUKEBOX_DATA_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.music.jukebox.catalogue import Catalogue

CODE, DATA, STATE = "jukebox", "jukebox_data", "jukebox_state"
# The saved layout's room (jukebox.h): the limits may not pass it
PLAYLISTS, SONGS, NAME_CHARS = 8, 40, 10
PLACES = 16                     # each list of replaced requests (jukebox.h JUKEBOX_PLACES)
MESSAGES = 64                   # the menu's message numbers (JUKEBOX_MESSAGES)
TRACK_ROOM = 512                # track ids the request table holds (JUKEBOX_TRACK_ROOM)
CATEGORIES = 8                  # the menu's categories (JUKEBOX_CATEGORIES)
MENU_TRACKS = 256               # the menu's track list (JUKEBOX_MENU_TRACKS)
NO_REQUEST = 0xFFFF
# Requests a playlist never replaces: Dundorma's arena area's theme and its room's while object 0x73 is there
NEVER_REPLACED = (0x36, 0x39)

# FUN_00304990 (the town's theme selector): every stage's pick leaves through `mov r0, r4` (then pop {r4-r8, pc})
PICK_EXIT = 0x304B70
MOV_R0_R4 = 0xE1A00004
# FUN_00302ba0, command 2 (0x302C98): its first instruction that calls the selector, `bl FUN_00304990` (r0 the manager,
# r1 = 0)
COMMAND_PICK = 0x302CA0
TOWN_THEME = 0x304990
# FUN_0030ace0(manager, request) -> the request's index in the resume list 0xFCCE54, or -1: its first three words
RESUME_LOOKUP = 0x30ACE0
RESUME_WORDS = (0xE59F203C, 0xE59FC03C, 0xE3A00000)    # ldr r2, [pc, #0x3c]; ldr ip, [pc, #0x3c]; mov r0, #0
PUSH_R1_LR, POP_R1_PC = 0xE92D4002, 0xE8BD8002


class JukeboxError(ValueError):
    """The catalogue or the request map does not fit the data block."""


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_jukebox(code: bytes) -> bool:
    """`code` (the update's executable, canonical) has the instructions the patch replaces."""
    if len(code) < RESUME_LOOKUP + 12 - BASE_ADDRESS:
        return False
    return (_word(code, PICK_EXIT) == MOV_R0_R4 and bl_target(code, COMMAND_PICK) == TOWN_THEME
            and all(_word(code, RESUME_LOOKUP + 4 * i) == word for i, word in enumerate(RESUME_WORDS)))


def _request(value, what: str) -> int:
    request = int(value, 0) if isinstance(value, str) else value
    if not isinstance(request, int) or isinstance(request, bool) or not 0 <= request < NO_REQUEST:
        raise JukeboxError(f"{what}: {value!r} is not a request")
    return request


def _places(values, what: str) -> list[int]:
    requests = [_request(value, what) for value in values]
    if len(requests) > PLACES:
        raise JukeboxError(f"{what}: {len(requests)} requests, room for {PLACES}")
    if any(request in NEVER_REPLACED for request in requests):
        raise JukeboxError(f"{what}: {', '.join(hex(r) for r in NEVER_REPLACED)} are never replaced")
    return requests


def _byte(value, what: str, low: int = 0, high: int = 255) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise JukeboxError(f"{what}: {value!r} is not in {low}-{high}")
    return value


class MenuLists(Protocol):
    """The menu's lists (music/jukebox/texts.py MenuTexts): the tracks it lists by category, the name message of the
    first (each next track's follows it), and each category's (first track, tracks, name message)."""
    messages: Sequence[int]
    tracks: Sequence[int]
    track_names: int
    categories: Sequence[tuple[int, int, int]]


def _menu_part(menu: MenuLists | None, requests: Mapping[int, int]) -> bytes:
    """The menu's part of jukebox_data (from counter_x on); the page counter's place stays 0 (menu_patch.py sets it)."""
    tracks = list(menu.tracks) if menu else []
    categories = list(menu.categories) if menu else []
    if len(tracks) > MENU_TRACKS:
        raise JukeboxError(f"the menu lists {len(tracks)} tracks, room for {MENU_TRACKS}")
    if len(categories) > CATEGORIES:
        raise JukeboxError(f"the menu has {len(categories)} categories, room for {CATEGORIES}")
    missing = [track for track in tracks if track not in requests]
    if missing:
        raise JukeboxError(f"the menu lists tracks the build lacks: {missing}")
    names = _request(menu.track_names, "track_names") if menu else 0
    if names + len(tracks) > NO_REQUEST:
        raise JukeboxError("the tracks' names pass the message numbers")
    rows = []
    for first, count, name in categories:
        if not 0 <= first <= first + count <= len(tracks) or count < 1:
            raise JukeboxError(f"a category's tracks {first}-{first + count - 1} are not in the menu's list")
        rows.append(struct.pack("<4H", first, count, _request(name, "a category's name"), 0))
    rows += [bytes(8)] * (CATEGORIES - len(categories))
    return (struct.pack("<2h2H", 0, 0, names, len(categories)) + b"".join(rows)
            + struct.pack(f"<{MENU_TRACKS}H", *tracks, *[NO_REQUEST] * (MENU_TRACKS - len(tracks))))


def data_block(catalogue: Catalogue, requests: Mapping[int, int], messages: Sequence[int] = (),
               menu: MenuLists | None = None) -> bytes:
    """The block jukebox_data (jukebox.h struct jukebox_data): the replaced requests (catalogue.replaced's villages and
    halls), the limits and the defaults (catalogue.limits, .loops_range, .fade_range, .defaults), the jukebox's request
    range, the menu's `messages` (or else `menu`'s), the request of each track id in `requests` ({track id: request in
    bgm_lob}, the tracks the build has; every other id gets none) and the menu's lists (`menu`)."""
    if menu is not None and not messages:
        messages = menu.messages
    villages = _places(catalogue.replaced.get("villages", ()), "replaced.villages")
    halls = _places(catalogue.replaced.get("halls", ()), "replaced.halls")
    limits = catalogue.limits
    playlists = _byte(limits["playlists"], "limits.playlists", 1, PLAYLISTS)
    songs = _byte(limits["tracks"], "limits.tracks", 1, SONGS)
    name_chars = _byte(limits["name_chars"], "limits.name_chars", 1, NAME_CHARS)
    loops = tuple(_byte(v, "loops_range", 1) for v in catalogue.loops_range)
    fade = tuple(_byte(v, "fade_range") for v in catalogue.fade_range)
    defaults = catalogue.defaults
    options = (0, _byte(defaults.get("keep"), "defaults.keep", 0, 1), _byte(defaults.get("halls"),
               "defaults.halls", 0, 1), _byte(defaults["loops"], "defaults.loops", *loops),
               _byte(defaults["fade_seconds"], "defaults.fade_seconds", *fade))
    if len(messages) > MESSAGES:
        raise JukeboxError(f"{len(messages)} messages, room for {MESSAGES}")
    tracks = max([track.id for track in catalogue.tracks] + list(requests), default=-1) + 1
    if tracks > TRACK_ROOM:
        raise JukeboxError(f"track ids up to {tracks - 1}, room for {TRACK_ROOM}")
    table = [NO_REQUEST] * TRACK_ROOM
    for track, request in requests.items():
        if not isinstance(track, int) or track < 0:
            raise JukeboxError(f"track {track!r} is not a track id")
        table[track] = _request(request, f"track {track}")
    own = [table[track] for track in range(tracks) if table[track] != NO_REQUEST]
    first, last = (min(own), max(own)) if own else (1, 0)
    if any(first <= place <= last for place in villages + halls):
        raise JukeboxError("a replaced place's request is among the jukebox's own requests")
    data = b"".join(struct.pack(f"<{PLACES}H", *places, *[NO_REQUEST] * (PLACES - len(places)))
                    for places in (villages, halls))
    data += bytes([playlists, songs, name_chars, *loops, *fade, 0])
    data += bytes([*options, 0, 0, 0])
    data += struct.pack("<4H", first, last, tracks, 0)
    numbers = [_request(message, "messages") for message in messages]
    data += struct.pack(f"<{MESSAGES}H", *numbers, *[0] * (MESSAGES - len(numbers)))
    data += struct.pack(f"<{TRACK_ROOM}H", *table)
    data += _menu_part(menu, requests)
    if len(data) != JUKEBOX_DATA_SIZE:
        raise JukeboxError(f"jukebox_data holds {JUKEBOX_DATA_SIZE} bytes, made {len(data)}")
    return data


def patch_jukebox(code: bytes, catalogue: Catalogue, requests: Mapping[int, int], layout: Layout | None = None,
                  messages: Sequence[int] = (), menu: MenuLists | None = None) -> bytes:
    """`code` (the update's executable) with the jukebox's engine: its block, its data (data_block, with the menu's
    `messages` and lists) and its three changes to the game's code. Refuses an executable where a site is not the
    game's instruction, or one patched already."""
    if not supports_jukebox(code):
        raise CodeSpaceError("unexpected code at the town's music: the jukebox needs the update's executable")
    layout = layout or load_layout()
    out = bytearray(code)
    try:
        layout.place(out, CODE)
        layout.place(out, DATA, data_block(catalogue, requests, messages, menu))
    except CodeSpaceError as error:
        raise CodeSpaceError(f"jukebox: {error}") from error
    layout.reserve(out, STATE)
    layout.hook(out, PICK_EXIT, layout.symbol(CODE, "jukebox_pick_stub"), original=struct.pack("<I", MOV_R0_R4))
    layout.hook(out, COMMAND_PICK, layout.symbol(CODE, "jukebox_command_pick"), calls=TOWN_THEME)
    struct.pack_into("<I", out, RESUME_LOOKUP - BASE_ADDRESS, PUSH_R1_LR)
    layout.hook(out, RESUME_LOOKUP + 4, layout.symbol(CODE, "jukebox_resume_index"),
                original=struct.pack("<I", RESUME_WORDS[1]))
    struct.pack_into("<I", out, RESUME_LOOKUP + 8 - BASE_ADDRESS, POP_R1_PC)
    return bytes(out)


__all__ = ["CATEGORIES", "CODE", "COMMAND_PICK", "DATA", "JukeboxError", "MENU_TRACKS", "MESSAGES", "MenuLists",
           "NEVER_REPLACED", "PICK_EXIT", "RESUME_LOOKUP", "STATE", "TOWN_THEME", "TRACK_ROOM", "data_block",
           "patch_jukebox", "supports_jukebox"]
