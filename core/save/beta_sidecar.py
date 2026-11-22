"""Heavenfall Beta's save on MH4U's own files, with sidecars.

Heavenfall Beta plays on MH4U's `userN` and `cardN`; on disk they stay clean retail files, and what only Heavenfall
knows is set apart into sidecar files in MH4U's extdata (core/save/files.py) by the extras core
(core/save/c/extras.c). Four sites, each one instruction replaced by `bl` to a stub of the
block `beta_sidecar_stubs` (save/beta_sidecar.s), which calls the C of `beta_sidecar_code` (save/beta_sidecar.c):

* SPLIT_USER, FUN_002abe04 (the builder of `userN`) before its checksum: `mov r2, r8`;
* SPLIT_CARD, FUN_002adedc (the builder of `cardN`) before its checksum: `mov r2, r9`;
* JOIN_USER, FUN_002af280 (the title's read of a slot), its copy of the checked data: `bl save_copy_in`;
* JOIN_CARD, FUN_002adc98 (the load's read of the slot's card), its copy of the item sets: `bl card_sets_in`.

Heavenfall Beta only; update's executable (canonical addresses), each site checked first.
"""

import struct
from collections.abc import Callable
from dataclasses import dataclass

from core.game.executable.blocks import BETA_SIDECAR_CARD_SIZE, BETA_SIDECAR_STATE_SIZE, GAME_SYMBOLS
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, encode_branch, load_layout
from core.save import files

STUBS = "beta_sidecar_stubs"
CODE = "beta_sidecar_code"
STATE = "beta_sidecar_state"
CARD_IMAGES = "beta_sidecar_card"

SPLIT_USER = 0x2ABEB8           # FUN_002abe04: mov r2, r8 (the file's size for the checksum)
SPLIT_CARD = 0x2ADFE0           # FUN_002adedc: mov r2, r9
JOIN_USER = 0x2AF2E0            # FUN_002af280: bl FUN_00c27830 (save_copy_in)
JOIN_CARD = 0x2ADDE8            # FUN_002adc98: bl FUN_00c1ac68 (card_sets_in)


# FUN_00c19264, the save archive's mount: Heavenfall's own extdata (own_extdata.py) makes it answer -0xC, and the
# sidecars need "data:" mounted, so the two patches never meet (patch_beta_sidecar refuses, patch_own_extdata too)
MOUNT = 0xC19264
MOUNT_ORIGINAL = 0xE92D4070


def own_extdata_patched(code: bytes) -> bool:
    """True if the save archive's mount no longer holds the game's word (Heavenfall's own extdata is applied)."""
    at = MOUNT - BASE_ADDRESS
    return struct.unpack_from("<I", code, at)[0] != MOUNT_ORIGINAL if 0 <= at <= len(code) - 4 else False


def _bl(at: int, target: int) -> bytes:
    return encode_branch(at, target, link=True)


# (site, the stub it calls, the instruction it replaces)
HOOKS = ((SPLIT_USER, "beta_sidecar_split_user", struct.pack("<I", 0xE1A02008)),
         (SPLIT_CARD, "beta_sidecar_split_card", struct.pack("<I", 0xE1A02009)),
         (JOIN_USER, "beta_sidecar_join_user", _bl(JOIN_USER, GAME_SYMBOLS["save_copy_in"])),
         (JOIN_CARD, "beta_sidecar_join_card", _bl(JOIN_CARD, GAME_SYMBOLS["card_sets_in"])))

# The state (beta_sidecar.c struct state): its header, the three slots, the card's left-overs, the request, the name,
# then the log's ring of LOG_RING notes
STATE_MAGIC = 0x53424648        # "HFBS"
STATE_VERSION = 2
LOG_RING = 64
LOG_AT = 0x1FC
SLOTS_AT = 0x10
SLOT_SIZE = 0x40
CARD_LEFT_AT = 0xD0
assert LOG_AT + 16 * LOG_RING == BETA_SIDECAR_STATE_SIZE
SENTINEL = 16                   # beta_sidecar.c read_file: the bytes past an image a read may fill
assert BETA_SIDECAR_CARD_SIZE == 2 * files.CARD_EXTRAS_SIZE + SENTINEL

SITES = {1: "split user", 2: "split card", 3: "join user", 4: "join card", 5: "sweep"}
WHATS = {1: "done", 2: "nothing", 3: "no extdata", 4: "refused", 5: "no image", 6: "other hunter",
         7: "as it is", 8: "newer ignored", 9: "keep joined", 10: "flag failed", 11: "read failed", 12: "kept failed",
         13: "original failed", 14: "write failed", 15: "core failed", 16: "not known",
         17: "joined late", 18: "other file", 19: "older set apart", 20: "older kept", 21: "not clean"}
BITS = {0x01: "carry", 0x02: "kept", 0x04: "original", 0x08: "retried", 0x10: "b", 0x20: "carry lost",
        0x40: "drop all", 0x80: "keep flagged"}
# the two mark bits together: the userN file marked "lacks"; a card file marked "not joined"
BOTH_MARKS = 0xC0
BOTH_MARKS_NAMES = {1: "lacks", 2: "not joined"}
# struct slot's flags
SLOT_FLAGS = {0x01: "user known", 0x02: "card known", 0x04: "user tag", 0x08: "card tag", 0x10: "original",
              0x20: "user on disk", 0x40: "card on disk", 0x80: "kept ok", 0x100: "plan",
              0x200: "late", 0x400: "pending", 0x800: "late landed", 0x1000: "title content",
              0x2000: "title marked", 0x4000: "swept"}


def bit_names(bits: int, site: int) -> list[str]:
    """A note's bits by name (BITS; both mark bits at once: BOTH_MARKS_NAMES by the site)."""
    if bits & BOTH_MARKS == BOTH_MARKS:
        return [name for bit, name in BITS.items() if bits & bit & ~BOTH_MARKS] + [BOTH_MARKS_NAMES.get(site, "marks")]
    return [name for bit, name in BITS.items() if bits & bit]


@dataclass(frozen=True)
class Note:
    """One step (struct note): where, which slot (0-2), what happened (WHATS), its bits (BITS), the core's answer,
    the request's result and the generation."""
    site: int
    slot: int
    what: int
    bits: int
    core: int
    io: int
    generation: int

    def text(self) -> str:
        bits = ", ".join(bit_names(self.bits, self.site))
        return (f"{SITES.get(self.site, self.site)} {self.slot + 1}: {WHATS.get(self.what, self.what)}"
                f"{f' ({bits})' if bits else ''}  core {self.core}  io {self.io & 0xFFFFFFFF:#x}"
                f"  generation {self.generation}")


@dataclass(frozen=True)
class Slot:
    """A slot's facts (struct slot)."""
    flags: int
    user_tag: int
    card_tag: int
    user_newest: int
    card_newest: int
    user_left: int
    user_flagged: int
    user_late: int              # "late": the generation of the image the title could not join
    user_disk: int              # CRC32 of userN on disk (enciphered) when the last split read it, 0 not known
    pending_tag: int            # "pending": the tag of the file the last split wrote, and its plain tail's CRC
    pending_tail: int
    pending_flagged: int        # "pending": user_flagged before that split
    disk_tail: int              # the plain tail's CRC of the userN on disk, 0 not known
    pending_gen: int            # "pending": the generation of the image the last split wrote
    disk_gen: int               # the generation of the image the userN on disk goes with, 0 not known
    title_mark: int             # the whole mark the title read in userN


SLOT_WORDS = 16                 # struct slot's words


@dataclass(frozen=True)
class State:
    saves: int
    slots: list[Slot]
    card_slot: int              # 0-2, or 0xFF: no card left-overs
    card_left: int
    card_flagged: int
    notes: list[Note]           # oldest first
    lost: int                   # notes gone round the ring


def read_state(u32: Callable[[int], int], base: int) -> State | None:
    """The state at `base` (the variable STATE), read through `u32` (address -> word); None before the first call (or
    a state of another layout)."""
    if u32(base) != STATE_MAGIC or u32(base + 4) != STATE_VERSION:
        return None
    written, saves = u32(base + 8), u32(base + 12)
    slots = [Slot(*(u32(base + SLOTS_AT + SLOT_SIZE * n + 4 * k) for k in range(SLOT_WORDS))) for n in range(3)]
    notes = []
    for n in range(max(0, written - LOG_RING), written):
        at = base + LOG_AT + 16 * (n % LOG_RING)
        head = u32(at)
        signed = lambda v: v - (1 << 32) if v & 0x80000000 else v      # noqa: E731
        notes.append(Note(head & 0xFF, head >> 8 & 0xFF, head >> 16 & 0xFF, head >> 24, signed(u32(at + 4)),
                          signed(u32(at + 8)), u32(at + 12)))
    return State(saves, slots, u32(base + CARD_LEFT_AT), u32(base + CARD_LEFT_AT + 4), u32(base + CARD_LEFT_AT + 8),
                 notes, max(0, written - LOG_RING))


def supports_beta_sidecar(code: bytes) -> bool:
    """True if the four sites hold the update's instructions (none patched yet)."""
    try:
        return all(bytes(code[site - BASE_ADDRESS:site - BASE_ADDRESS + 4]) == original for site, _, original in HOOKS)
    except IndexError:
        return False


def patch_beta_sidecar(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) where the game's `userN` and `cardN` are written clean, Heavenfall's part in
    the sidecars, and put back together when they are read."""
    if not supports_beta_sidecar(code):
        raise CodeSpaceError("beta sidecar: the sites at " + " / ".join(f"{site:#x}" for site, _, _ in HOOKS)
                             + " are not the update's (another executable, or already patched)")
    if own_extdata_patched(code):
        raise CodeSpaceError("beta sidecar: Heavenfall's own extdata is applied (the save archive is never mounted); "
                             "the sidecars are Heavenfall Beta's, on MH4U's own save")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.reserve(out, STATE, CARD_IMAGES)            # in the extension's variables
    layout.place(out, CODE)
    layout.place(out, STUBS)
    for site, entry, original in HOOKS:
        layout.hook(out, site, layout.symbol(STUBS, entry), original=original)
    return bytes(out)
