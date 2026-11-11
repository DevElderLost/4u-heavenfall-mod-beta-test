"""MH XX's reward lists of a monster, read from `arc/result.arc` at run time: what he carves and drops as a shiny
(`hagi`), what his part breaks and his capture pay (`bui`) and what his
quests pay (`rem`).

    files = RewardFiles(romfs)                          # romfs: anything with `read(path)`
    read_monster_rewards(files, 82)["high"].shiny       # Mizutsune's list in high rank

A `Drop` has XX's item id (XX numbers its items anew): nothing here turns it into another game's. `read_monster_rewards`
gives the lists of the three ranks; `RewardFiles.hagi` and `bui` give any level's whole file, with the lists of a
variant 4 monster's other forms (slot + 1 and + 2, type + 1 and + 2); `parse_rem` also reads the tables only quest
archives hold."""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass

from core.game.files.arc import parse_arc

RESULT_ARC = "arc/result.arc"
HAGI_ENTRY = "enemy\\hagi\\hagi_s{level}_em{em:03d}_{variant:02d}"
BUI_ENTRY = "quest\\bui\\bui_s{level}"
REM_ENTRY = "quest\\rem\\rem_1{digit}{em:03d}{variant}"

# Each rank's level (a quest's `mHagiLv`, in the name of its `hagi` and `bui` files) and its `rem` table's digit
RANK_LEVELS = {"low": 1, "high": 2, "G": 4}
REM_DIGITS = {"low": 1, "high": 2, "G": 3}

# rHagi: u32 tag, u8 mIndexTable[22] (the first row of a slot's list, 0xFF none; [0] is no list), u8 rate, u8 num,
# u16 item mListData[80]; a list ends at a rate of 0xFF
HAGI_TAG = 0x14120103
HAGI_SIZE = 346
HAGI_SLOTS = 22
HAGI_INDEX = 4
HAGI_ROWS = 0x1A
HAGI_NONE = 0xFF
BODY_SLOT = 1                   # the body's carves (a DTP carve record of kind 0)
CUT_SLOT = 4                    # the cut piece's (kind 1)
SECOND_CUT_SLOT = 7             # the second cut piece's (kind 2)
SHINY_SLOT = 10                 # the shiny drop

# rBui: f32 version, u32 count, records: u16 monster id, (u8 type, u8 count)[18], (u8 rate, u8 num, u16 item)[106]; the
# lists follow each other, each with an end row after its counted ones
BUI_VERSION = 2.0
BUI_HEADER = 8
BUI_RECORD = 462
BUI_HEADS = 18
BUI_ROWS = 0x26
CAPTURE_TYPE = 10               # the type of the capture list
BREAK_BITS = range(1, 6)        # the reward bits that pay: FUN_0090d4d4 registers nothing for bit 0 or a bit over 5
BIT_FLAG = 0x80                 # of a DTP threshold record's bit: every part with this bit must reach its threshold

# rRem: f32 version, u32 count, (u8 flag, u8 count)[8], (u16 item, u8 num, u8 rate)[40]; laid out as in rBui
REM_VERSION = 1.0
REM_SIZE = 184
REM_HEADS = 8
REM_HEAD = 8
REM_ROWS = 0x18
REM_OTHER_FLAG = 4              # a second group, for some quest kinds: FUN_0095d630 draws the first with another flag


@dataclass(frozen=True)
class Drop:
    """One row of a reward list."""
    item: int           # XX's item id
    percent: int
    qty: int


@dataclass(frozen=True)
class RemGroup:
    """A group of rows of a `rem` table (the game finds a group by its flag; a table may repeat a flag)."""
    flag: int
    rows: tuple[Drop, ...]


@dataclass(frozen=True)
class RankRewards:
    """A monster's lists in one rank; empty where the game has none."""
    body: tuple[Drop, ...]
    cut: tuple[Drop, ...]
    second_cut: tuple[Drop, ...]
    shiny: tuple[Drop, ...]
    capture: tuple[Drop, ...]
    breaks: Mapping[int, tuple[Drop, ...]]      # by reward bit (a DTP threshold record's last byte, `break_list_type`)
    quest: tuple[Drop, ...]


def monster_id(em: int, variant: int = 0) -> int:
    """The id a monster has in `bui`: 513 is em001_02."""
    return em | variant << 8


def break_list_type(bit: int) -> int | None:
    """The `bui` type a DTP threshold record's bit pays (N + 1) x 10, or None when it pays nothing (bit 0, over 5)."""
    bit &= ~BIT_FLAG
    return (bit + 1) * 10 if bit in BREAK_BITS else None


def _check_header(data: bytes, version: float, what: str) -> int:
    if len(data) < 8 or struct.unpack_from("<f", data)[0] != version:
        raise ValueError(f"not a {what} file of XX's format: version {data[:4].hex()}")
    return struct.unpack_from("<I", data, 4)[0]


def parse_hagi(data: bytes) -> dict[int, tuple[Drop, ...]]:
    """An rHagi file's lists by slot."""
    if len(data) != HAGI_SIZE or struct.unpack_from("<I", data)[0] != HAGI_TAG:
        raise ValueError(f"not a hagi file of XX's format: {len(data)} bytes, {data[:4].hex()}")
    lists = {}
    for slot in range(1, HAGI_SLOTS):
        first = data[HAGI_INDEX + slot]
        if first == HAGI_NONE:
            continue
        rows = []
        for at in range(HAGI_ROWS + 4 * first, HAGI_SIZE, 4):
            rate, num, item = struct.unpack_from("<BBH", data, at)
            if rate == 0xFF:
                break
            rows.append(Drop(item, rate, num))
        lists[slot] = tuple(rows)
    return lists


def _consecutive(heads: list[tuple[int, int]], row_at, rows_at: int) -> list[tuple[int, tuple[Drop, ...]]]:
    """The lists of `heads` (key, its rows), which follow each other from `rows_at` with an end row after each."""
    lists = []
    at = rows_at
    for key, count in heads:
        lists.append((key, tuple(row_at(at + 4 * k) for k in range(count))))
        at += 4 * (count + 1)
    return lists


def parse_bui(data: bytes) -> dict[int, dict[int, tuple[Drop, ...]]]:
    """An rBui file's lists: monster id -> type -> rows."""
    count = _check_header(data, BUI_VERSION, "bui")
    if len(data) != BUI_HEADER + count * BUI_RECORD:
        raise ValueError(f"a bui file of {count} records has {len(data)} bytes")
    records = {}
    for k in range(count):
        base = BUI_HEADER + k * BUI_RECORD
        heads = [(data[base + 2 + 2 * j], data[base + 3 + 2 * j]) for j in range(BUI_HEADS)]

        def row(at: int) -> Drop:
            rate, num, item = struct.unpack_from("<BBH", data, at)
            return Drop(item, rate, num)
        lists = _consecutive([head for head in heads if head != (0, 0)], row, base + BUI_ROWS)
        records[struct.unpack_from("<H", data, base)[0]] = dict(lists)
    return records


def parse_rem(data: bytes) -> tuple[RemGroup, ...]:
    """An rRem file's groups, in the file's order."""
    _check_header(data, REM_VERSION, "rem")
    if len(data) != REM_SIZE:
        raise ValueError(f"a rem file has {REM_SIZE} bytes, not {len(data)}")
    heads = [(data[REM_HEAD + 2 * j], data[REM_HEAD + 1 + 2 * j]) for j in range(REM_HEADS)]

    def row(at: int) -> Drop:
        item, num, rate = struct.unpack_from("<HBB", data, at)
        return Drop(item, rate, num)
    return tuple(RemGroup(flag, rows) for flag, rows in _consecutive([h for h in heads if h != (0, 0)], row, REM_ROWS))


class RewardFiles:
    """XX's reward files in `romfs` (anything with `read(path)`: game.executable.romfs.RomFS), its archive read once."""

    def __init__(self, romfs):
        self.romfs = romfs
        self._result: dict | None = None
        self._bui: dict[int, dict[int, dict[int, tuple[Drop, ...]]]] = {}

    def result(self) -> dict:
        """The entries of `arc/result.arc`, by name."""
        if self._result is None:
            self._result = {e.name: e for e in parse_arc(self.romfs.read(RESULT_ARC)).entries}
        return self._result

    def hagi(self, em: int, variant: int, level: int) -> dict[int, tuple[Drop, ...]]:
        """The lists by slot of a monster's `hagi` file of `level`."""
        entry = self.result().get(HAGI_ENTRY.format(level=level, em=em, variant=variant))
        return parse_hagi(entry.data) if entry else {}

    def bui(self, level: int) -> dict[int, dict[int, tuple[Drop, ...]]]:
        """The `bui` file of `level`: monster id -> type -> rows."""
        if level not in self._bui:
            entry = self.result().get(BUI_ENTRY.format(level=level))
            self._bui[level] = parse_bui(entry.data) if entry else {}
        return self._bui[level]

    def rem(self, em: int, variant: int, digit: int) -> tuple[RemGroup, ...]:
        """A monster's `rem` table of rank digit `digit` in `arc/result.arc`; no groups when it has none."""
        entry = self.result().get(REM_ENTRY.format(digit=digit, em=em, variant=variant))
        return parse_rem(entry.data) if entry else ()


def read_monster_rewards(files: RewardFiles, em: int, variant: int = 0) -> dict[str, RankRewards]:
    """Monster `em` (with `variant`)'s lists by rank ("low", "high", "G"); a variant 4 monster's first form."""
    ranks = {}
    for rank, level in RANK_LEVELS.items():
        slots = files.hagi(em, variant, level)
        kinds = files.bui(level).get(monster_id(em, variant), {})
        breaks = {bit: kinds[(bit + 1) * 10] for bit in BREAK_BITS if (bit + 1) * 10 in kinds}
        groups = files.rem(em, variant, REM_DIGITS[rank])
        quest = next((group.rows for group in groups if group.flag != REM_OTHER_FLAG), ())
        ranks[rank] = RankRewards(slots.get(BODY_SLOT, ()), slots.get(CUT_SLOT, ()), slots.get(SECOND_CUT_SLOT, ()),
                                  slots.get(SHINY_SLOT, ()), kinds.get(CAPTURE_TYPE, ()), breaks, quest)
    return ranks
