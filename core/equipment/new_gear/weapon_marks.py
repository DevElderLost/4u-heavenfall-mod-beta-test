"""The save's marks of the new weapons whose ids are past their class's bits: the bits they use and the patch that
routes them there.

The game keeps three marks per piece of equipment (had it once, seen, new) in three bit arrays of the save data
(`ARRAYS`, 8864 bits each; the Felynes' arrays follow at `FELYNE_ARRAYS`). A piece's bit is `base[type] + id`, the
i16 table `SAVE_BASES` at `BASES`, so a type has the bits up to the next type's base (`capacity`): a weapon class has
bits for 40 (the Insect Glaive) to 73 ids past its last. Six functions (`ACCESSORS`: get, set and clear, each by type
and id or by a piece's reference) are the only code that reads or writes a mark; the game clears the whole "new" array
at once (FUN_00c1fe20), and the save, the title and the export copy the save data whole.

The armor parts give the room. FUN_002f2484 (`GUARD`), which all six call first, refuses every armor id from
`UNTRACKED_FROM` on (872 to 903, below each part's count): no armor id past it is ever marked, and the game has no
armor id past the part's count. The bits from each part's count to the next type's base (`windows`, 365 in all) are
used by nothing: no id of the game, no new armor id (refused too), no rule of Layered Gear's forge (they name pieces of
the game's tables). Real saves hold no bit there.

A weapon id below its class's capacity keeps the game's bit. One at or past it gets a bit of those windows: each class
has a run of `mark_room() - spare` places (`runs`), the classes in type order, the windows from the body to the head, so
every class could mark the same number of ids past its last (`mark_room`, 82). The layout depends only on the game's
bases, counts and bounds, so an id's bit never moves. A class marks `MARKED` (80) of them: the last places of each run
(ids 80 and 81) and the places after the last run are the Felynes' (`spare_places`, 40: equipment/new_gear/
felyne_marks.py). An id past its marked ones has no bit: a read answers 0, a write does nothing, where the game would
have touched another type's bits (the Charge Blade's, the Felynes' arrays).

The patch (`patch_marks`, called by `new_weapons.patch_new_weapons`): block `weapon_marks_code` (weapon_marks.c,
`weapon_mark_bit`), its table `weapon_marks_table`, and in each accessor the instruction that adds the id to the base
(`add rB, r0, r6`) replaced by a `b` to a stub of `weapon_marks_stubs`: the game's sum, the C function with the type
and the id, the bit back where the game's code expects it (or the function's own way out when there is none), the flags
of the game's `cmp r7, #0` again, and on.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from functools import cache

from core.equipment.new_gear.new_weapon_room import (
    FIRST_TYPE, MARK_ACCESSORS, MARK_ROW_SIZE, MARK_STUB_SIZE, MARK_TABLE_BYTES, MARK_WINDOWS, MARK_WINDOW_SIZE, ROOM,
    TYPES,
)
from core.equipment.tables.layout import ARMOR_PARTS, WEAPON_CLASSES, WeaponClass
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, encode_branch

CODE, TABLE, STUBS = "weapon_marks_code", "weapon_marks_table", "weapon_marks_stubs"

# The save data's mark arrays (data = save + 0x5C): had it once, seen, new; 0x454 bytes each
ARRAYS = (0xCE14, 0xD268, 0xD6BC)
ARRAY_BITS = 8864
FELYNE_ARRAYS = 0xDB10
BASES = 0xFD0918                 # i16 per type 0..20: the first bit of the type's ids
SAVE_BASES = (0, 0, 1040, 2070, 3120, 4170, 5200, 5220, 5520, 5830, 6130, 6410, 6650, 6880, 7160, 7420, 7700, 7950,
              8230, 8470, 8670)
TALISMAN, TALISMAN_COUNT = 6, 18
# The ids past its last a weapon class marks: the save's layout (the run places past them are the Felynes', so a bit
# never moves). new_weapon_room.ROOM may not pass it.
MARKED = 80
assert ROOM <= MARKED, "new_weapon_room.ROOM passes the weapon ids the save marks (weapon_marks.MARKED)"

# FUN_002f2484(object, type, id): 1 (no mark) for an armor id at or past its part's bound, else 0. Its words, and the
# bounds they hold (the jump table sends types 1, 2-3, 4 and 5 to `mov r0, #0x378`, `#0x368`, `#0x370` and the
# literal 0x387).
GUARD_AT = 0x2F2484
GUARD = (0xE1A03001, 0xE52DE004, 0xEBFFFFA1, 0xE3500000, 0x1A000014, 0xE3530006, 0x0A000012, 0xE3530006,
         0x379FF103, 0xEA00000F, 0x002F24EC, 0x002F24C4, 0x002F24CC, 0x002F24CC, 0x002F24D4, 0x002F24DC,
         0xE3A00FDE, 0xEA000004, 0xE3A00FDA, 0xEA000002, 0xE3A00E37, 0xEA000000, 0xE59F0010, 0xE1520000,
         0x23A00001, 0x2A000000, 0xE3A00000, 0xE49DF004, 0x00000387)
UNTRACKED_FROM = {1: 0x378, 2: 0x368, 3: 0x368, 4: 0x370, 5: 0x387}


@dataclass(frozen=True)
class Accessor:
    """One of the six functions that read or write a mark. Each holds the type in r5, the id in r6 and the array
    (0-2) in r7; `at` is its `add rB, r0, r6` (r0 the type's base, rB the bit) and `out` where it answers nothing
    (`out_word` the instruction there)."""
    name: str
    entry: int
    at: int
    register: int
    out: int
    out_word: int


LDMIA = 0xE8BD81F0                 # ldmia sp!, {r4-r8, pc}
ACCESSORS = (
    Accessor("get", 0xC1FE40, 0xC1FE88, 1, 0xC1FF08, 0xE3A00000),             # (save, type, id, array); mov r0, #0
    Accessor("get_piece", 0xC1EAA4, 0xC1EB00, 0, 0xC1EAE8, 0xE1A00008),       # (save, piece, array); mov r0, r8 (0)
    Accessor("set", 0xC21A08, 0xC21A50, 1, 0xC21A98, LDMIA),                  # (save, type, id, array)
    Accessor("set_piece", 0xC1FF18, 0xC1FF68, 1, 0xC1FFB0, LDMIA),            # (save, piece, array)
    Accessor("clear_piece", 0xC22788, 0xC227D8, 1, 0xC22820, LDMIA),          # (save, piece, array)
    Accessor("clear", 0xC23604, 0xC2364C, 1, 0xC23694, LDMIA),                # (save, type, id, array)
)
assert len(ACCESSORS) == MARK_ACCESSORS
# The three words before each `at`: cmp r7, #0; add r0, r0, r5, lsl #1; ldrsh r0, [r0]
BEFORE = (0xE3570000, 0xE0800085, 0xE1D000F0)
CMP_R7_0 = 0xE3570000
COND_MI = 0x4


def add_word(accessor: Accessor) -> int:
    """The accessor's `add rB, r0, r6`."""
    return 0xE0800006 | accessor.register << 12


def _counts() -> dict[int, int]:
    counts = {wc.recipe_type: wc.count for wc in WEAPON_CLASSES}
    counts.update({part.recipe_type: part.count for part in ARMOR_PARTS})
    counts[TALISMAN] = TALISMAN_COUNT
    return counts


COUNTS = _counts()


def capacity(equipment_type: int) -> int:
    """The bits of a type: from its base to the next type's."""
    end = SAVE_BASES[equipment_type + 1] if equipment_type + 1 < len(SAVE_BASES) else ARRAY_BITS
    return end - SAVE_BASES[equipment_type]


def spare(wc: WeaponClass) -> int:
    """The ids past the class's last that its own bits hold."""
    return capacity(wc.recipe_type) - wc.count


def windows() -> tuple[tuple[int, int], ...]:
    """The bits no piece uses: (first bit, bits) from each armor part's count to the next type's base, the body
    (type 1) first."""
    return tuple((SAVE_BASES[t] + COUNTS[t], max(0, capacity(t) - COUNTS[t])) for t in range(1, 1 + MARK_WINDOWS))


@cache
def mark_room() -> int:
    """The most ids past its last that every class can mark: its own spare ids, then its run of the windows."""
    free = sum(bits for _, bits in windows())
    room = min(spare(wc) for wc in WEAPON_CLASSES)
    while sum(max(0, room + 1 - spare(wc)) for wc in WEAPON_CLASSES) <= free:
        room += 1
    return room


@cache
def runs() -> dict[int, tuple[int, int]]:
    """Weapon type -> (its first place in the windows, counted through them in order; the places it has, `mark_room`
    less its spare: the layout)."""
    out, first = {}, 0
    for t in range(FIRST_TYPE, FIRST_TYPE + TYPES):
        size = max(0, mark_room() - (capacity(t) - COUNTS[t]))
        out[t] = (first, size)
        first += size
    return out


def marked_places(equipment_type: int) -> int:
    """The places of a weapon type's run its ids use: up to MARKED ids past its last."""
    return max(0, min(runs()[equipment_type][1], MARKED - (capacity(equipment_type) - COUNTS[equipment_type])))


def marked_ids(wc: WeaponClass) -> int:
    """The ids past the class's last that the save can mark."""
    return spare(wc) + marked_places(wc.recipe_type)


def place_bit(place: int) -> int | None:
    """The bit of a place of the windows, counted through them in order."""
    for start, bits in windows():
        if place < bits:
            return start + place
        place -= bits
    return None


@cache
def spare_places() -> tuple[int, ...]:
    """The window bits no weapon id gets, in a fixed order: each run's places past MARKED (class order), then the
    places after the last run. The Felynes' ids past their own arrays use them (felyne_marks.py)."""
    places = [first + marked_places(t) + k for t, (first, size) in runs().items()
              for k in range(size - marked_places(t))]
    used = sum(size for _, size in runs().values())
    places += range(used, sum(bits for _, bits in windows()))
    return tuple(place_bit(place) for place in places)


def mark_bit(equipment_type: int, piece: int) -> int | None:
    """The bit of a piece's marks once patched, as weapon_marks.c answers: the game's for any type but a weapon class's
    and for a weapon id below its class's capacity; a bit of the windows for one past it within its marked places;
    None (no bit) past them. (An armor id from UNTRACKED_FROM on never gets here: FUN_002f2484 stops it before.)"""
    bit = SAVE_BASES[equipment_type] + piece
    if not FIRST_TYPE <= equipment_type < FIRST_TYPE + TYPES or piece < capacity(equipment_type):
        return bit
    n = piece - capacity(equipment_type)
    if n >= marked_places(equipment_type):
        return None
    return place_bit(runs()[equipment_type][0] + n)


def table() -> bytes:
    """Block TABLE: a row per weapon type (capacity, first place, marked places, 0), then the windows (first bit,
    bits)."""
    rows = b"".join(struct.pack("<4H", capacity(t), runs()[t][0], marked_places(t), 0)
                    for t in range(FIRST_TYPE, FIRST_TYPE + TYPES))
    data = rows + b"".join(struct.pack("<2H", *w) for w in windows())
    assert len(rows) == MARK_ROW_SIZE * TYPES and len(data) == MARK_TABLE_BYTES == \
        MARK_ROW_SIZE * TYPES + MARK_WINDOW_SIZE * MARK_WINDOWS
    return data


def _branch(at: int, target: int, *, link: bool = False, cond: int = 0xE) -> int:
    return struct.unpack("<I", encode_branch(at, target, link=link, cond=cond))[0]


def stub(accessor: Accessor, at: int, function: int) -> bytes:
    """The accessor's stub, placed at `at`, the C function at `function`."""
    words = (add_word(accessor) & ~0xF000 | 2 << 12,                   # add r2, r0, r6: the game's bit
             0xE1A00005, 0xE1A01006,                                    # mov r0, r5 (type); mov r1, r6 (id)
             _branch(at + 12, function, link=True),                     # bl weapon_mark_bit
             0xE1B00000 | accessor.register << 12,                      # movs rB, r0: the bit, negative for none
             _branch(at + 20, accessor.out, cond=COND_MI),              # bmi: the function's way out
             CMP_R7_0,                                                  # the flags of the game's cmp r7, #0
             _branch(at + 28, accessor.at + 4))
    data = struct.pack(f"<{len(words)}I", *words)
    assert len(data) == MARK_STUB_SIZE
    return data


def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def supports_marks(code: bytes) -> bool:
    """True if the bases, FUN_002f2484 and the six accessors' words are the update's."""
    if len(code) < BASES - BASE_ADDRESS + 2 * len(SAVE_BASES):
        return False
    if struct.unpack_from(f"<{len(SAVE_BASES)}h", code, BASES - BASE_ADDRESS) != SAVE_BASES:
        return False
    if struct.unpack_from(f"<{len(GUARD)}I", code, GUARD_AT - BASE_ADDRESS) != GUARD:
        return False
    return all(struct.unpack_from("<4I", code, a.at - 12 - BASE_ADDRESS) == (*BEFORE, add_word(a)) and
               _word(code, a.out) == a.out_word for a in ACCESSORS)


def patch_marks(code: bytearray, layout: Layout) -> None:
    """Route the marks of the ids past a class's bits (`mark_bit`) in `code`, the update's executable extended."""
    if not supports_marks(bytes(code)):
        raise CodeSpaceError("unexpected code at the save's mark functions: already patched, or not the update's "
                             "executable")
    layout.place(code, CODE)
    layout.place(code, TABLE, table())
    base, function = layout.address(STUBS), layout.symbol(CODE, "weapon_mark_bit")
    stubs = b"".join(stub(a, base + i * MARK_STUB_SIZE, function) for i, a in enumerate(ACCESSORS))
    layout.place(code, STUBS, stubs)
    for i, accessor in enumerate(ACCESSORS):
        layout.hook(code, accessor.at, base + i * MARK_STUB_SIZE, original=struct.pack("<I", add_word(accessor)),
                    link=False)
