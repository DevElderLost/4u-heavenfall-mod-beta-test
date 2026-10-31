"""The patched canonical image back onto the player's executable (step
4).

The patchers write into the player's executable laid out as the canonical one (`canonical.to_canonical`). `rebase`
starts from the player's own bytes and carries only the words the patchers changed, each at its place in his
version (`VersionMap.to_version`) and with its value translated: the relocations of the blocks placed
(`Block.relocs`, from the link), the branches (`Session.branches`, noted by `code_space.encode_branch` and the
writers that build their own) and the game pointers Python wrote (`Session.pointers`). Our free regions are identity
in every map. Every other changed word is copied as it is, after the leak detector (`_Leaks`): a word that, where a
position is likely, decodes as a branch whose copy would land elsewhere than its translated target or holds a game
address the version has elsewhere (or not at all) is an error, unless a named exemption (`EXEMPT`: a block or region,
never a bare address) says its words are values. A silent wrong address is worse than a refusal.
"""

import array
import bisect
import struct
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from core.monsters.porting.new_id_data import FIRST_NEW_ID, ID_TABLES
from core.game.executable.canonical import (
    BASE, arm_branch, arm_branch_target, thumb_branch, thumb_branch_target, to_canonical,
)
from core.game.executable.code_space import ABS32, CALL, REGIONS, Layout
from core.game.executable.session import Session
from core.game.executable.versions import VersionMap

BRANCH, POINTER = "branch", "pointer"
HOLE = "hole"               # VersionMap.coverage: a patch site the version does not have
_CHUNK = 1 << 12            # bytes compared at once while looking for the changed words
GAME_CODE = ((BASE, REGIONS["text_tail"].start),)   # MH4U's .text (canonical): a changed word there may be code
FREE = tuple(sorted((region.start, region.end) for region in REGIONS.values()))   # our free regions
_UNCONDITIONAL = frozenset({0xEA, 0xEB, 0xFA, 0xFB})  # top bytes of b, bl and blx imm with no condition


class RebaseError(ValueError):
    """A patched word that cannot be carried to the player's version: in a hole, a target the version lacks, a
    note that does not match its word, or a leak (a position no source accounts for)."""


@dataclass(frozen=True)
class Exempt:
    """Words the leak detector leaves as written: those of block or region `name` (bytes [start, end) of it; `end`
    None: to its end), for the checks of `kinds`; `why` says what the values are."""
    name: str
    why: str
    start: int = 0
    end: int | None = None
    kinds: frozenset[str] = frozenset({BRANCH, POINTER})


def _id_table(name: str):
    return next(table for table in ID_TABLES if table.name == name)


_SOUNDS, _PARTS = _id_table("sound_ranges"), _id_table("part_sets")
# Words of our blocks that are values though they may look like branches or game addresses; each says why. The ids
# past a table's own entries copy what follows the game's table, as the game reads it for them
# (monsters/porting/new_id.py): values of the canonical executable, kept as they are.
EXEMPT: tuple[Exempt, ...] = (
    Exempt("new_id_sound_ranges", "id 123's entry copies the next table's first word (0xEB6F80, read as two floats)",
           _SOUNDS.entry * _SOUNDS.count, _SOUNDS.entry * FIRST_NEW_ID),
    Exempt("new_id_part_sets", "ids 88-123 copy the tables after the game's 88 entries (packed values)",
           _PARTS.entry * _PARTS.count, _PARTS.entry * FIRST_NEW_ID),
    Exempt("single_screen_priorities", "the single-screen draw table: layout group name hashes (and draw offsets), "
           "random words that now and then look like a branch"),
    Exempt("single_screen_frame_table", "the Palico menus' frames: layout group name hashes, bit masks and floats, "
           "random words that now and then look like a branch or a game address"),
    Exempt("single_screen_label_table", "the minimap's place name: three layout name hashes and four floats, random "
           "words that now and then look like a branch or a game address"),
    Exempt("game_gui_table", "the game GUI engine's table: group and pane name hashes, floats, counts and offsets from "
           "its own start (no address), random words that now and then look like a branch or a game address"),
)


@dataclass
class Rebased:
    """The player's executable with the patches (`code`), and the version addresses of the branches (odd: a Thumb
    pair at the address minus one) and pointers whose values were translated, as `VersionMap`'s slots."""
    code: bytes
    branch_slots: tuple[int, ...]
    pointer_slots: tuple[int, ...]
    carried: int                # changed words carried


def _word(code: bytes | bytearray, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE)[0]


def _in(address: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= address < end for start, end in ranges)


def _pointers_held(original: bytes, vmap: VersionMap) -> set[int]:
    """The values of the version's pointer slots: the game's own pointers to its moved code and data."""
    words = array.array("I", original[:len(original) - len(original) % 4])
    if sys.byteorder != "little":
        words.byteswap()
    return {words[(slot - BASE) >> 2] for slot in vmap.pointer_slots if slot - BASE < 4 * len(words)}


def changed_words(base: bytes | bytearray, patched: bytes | bytearray) -> list[int]:
    """Addresses of the words of `patched` that differ from `base` (past `base`'s end: from zero), in order."""
    out: list[int] = []
    size = len(patched) - len(patched) % 4
    zeros = bytes(_CHUNK)
    for start in range(0, size, _CHUNK):
        stop = min(start + _CHUNK, size)
        old = base[start:stop] if stop <= len(base) else bytes(base[start:len(base)]).ljust(stop - start, b"\0")
        new = patched[start:stop]
        if old == new or (start >= len(base) and new == zeros[:stop - start]):
            continue
        for sub in range(start, stop, 64):
            end = min(sub + 64, stop)
            a, b = old[sub - start:end - start], new[sub - start:end - start]
            if a == b:
                continue
            count = (end - sub) // 4
            for k, (x, y) in enumerate(zip(struct.unpack(f"<{count}I", a), struct.unpack(f"<{count}I", b))):
                if x != y:
                    out.append(BASE + sub + 4 * k)
    return out


class _Places:
    """Names for error messages: the nearest symbol at or below an address, and the hole holding it."""

    def __init__(self, symbols: Mapping[str, int], vmap: VersionMap, layout: Layout | None):
        named = sorted((at, name) for name, at in symbols.items())
        if layout is not None:
            named += sorted((block.address, block.name) for block in layout.blocks.values())
            named.sort()
        self._addresses = [at for at, _ in named]
        self._names = [name for _, name in named]
        self._holes = vmap.holes
        self._hole_starts = [start for start, _ in vmap.holes]

    def __call__(self, address: int) -> str:
        i = bisect.bisect_right(self._addresses, address) - 1
        where = f"{address:#x}" + (f" ({self._names[i]}+{address - self._addresses[i]:#x})" if i >= 0 else "")
        k = bisect.bisect_right(self._hole_starts, address) - 1
        if k >= 0 and address < self._holes[k][1]:
            where += f", in the hole {self._holes[k][0]:#x}-{self._holes[k][1]:#x}"
        return where


class _Exemptions:
    """The exempt ranges as disjoint segments, each with the checks it waives."""

    def __init__(self, exempt: Sequence[Exempt], layout: Layout | None):
        ranges = []
        for item in exempt:
            if layout is not None and item.name in layout.blocks:
                block = layout.blocks[item.name]
                start, size = block.address, len(block.data)
            elif item.name in REGIONS:
                start, size = REGIONS[item.name].start, REGIONS[item.name].size
            else:
                continue                # a name this layout lacks exempts nothing (tests check every name)
            end = start + (size if item.end is None else min(item.end, size))
            if start + item.start < end:
                ranges.append((start + item.start, end, item.kinds))
        cuts = sorted({at for start, end, _ in ranges for at in (start, end)})
        self._starts = cuts
        self._kinds = [frozenset().union(*(kinds for start, end, kinds in ranges if start <= cut < end))
                       for cut in cuts]

    def kinds(self, address: int) -> frozenset[str]:
        i = bisect.bisect_right(self._starts, address) - 1
        return self._kinds[i] if i >= 0 else frozenset()


class _Leaks:
    """The leak detector, for a word `w` written at canonical `at` (in `patched`) and carried as it is to `here`.
    Tables of values (u16 pairs, strings, floats) hold words in the address range often, so outside the game's code a
    word counts only where it is likely a position:
    * a branch: an ARM B/BL/BLX imm whose copy would land elsewhere than its target's place in the version: in the
      game's code any of them (a hook); in our free regions an unconditional one to the game's code; none in the
      game's data (where the mod writes tables of values);
    * a pointer: an address of the game (a Thumb one with bit 0) that the version has elsewhere or not at all, when
      the word is in the game's code (a literal), or names a GAME_SYMBOLS address, or replaced one of the game's own
      pointers (its place is a pointer slot), or sits in a run of three words that all hold pointers the game itself
      holds (its pointer slots' values: a copied vtable or pointer table)."""

    def __init__(self, vmap: VersionMap, original: bytes, patched: bytes | bytearray, symbols: Mapping[str, int],
                 exemptions: _Exemptions, place: _Places, game_code: tuple[tuple[int, int], ...] = (),
                 free: tuple[tuple[int, int], ...] = ()):
        self._vmap, self._original, self._patched = vmap, original, patched
        self._exemptions, self._place, self._code, self._free = exemptions, place, game_code, free
        self._end = max(run.end for run in vmap.runs)
        self._symbols = {value & ~1 for value in symbols.values()}
        self._held: set[int] | None = None          # built when first needed
        self._slots: set[int] | None = None

    def _game_held(self, w: int) -> bool:
        """`w` is an address of the game's that moved, and the game's own pointers hold it."""
        moved = self._vmap.to_version(w & ~1)
        if moved is None or moved == w & ~1:
            return False
        if self._held is None:
            self._held = _pointers_held(self._original, self._vmap)
        return moved | (w & 1) in self._held

    def check(self, at: int, here: int, w: int) -> str | None:
        vmap, place = self._vmap, self._place
        waived = self._exemptions.kinds(at)
        code = _in(at, self._code)
        if BRANCH not in waived and (code or w >> 24 in _UNCONDITIONAL and _in(at, self._free)):
            target = arm_branch_target(w, at)
            if target is not None and (BASE <= target < self._end if code else _in(target, self._code)) \
                    and vmap.to_version(target) != here + target - at:
                return f"the word {w:#010x} at {place(at)} is a branch to {place(target)} that no note accounts for"
        value = w & ~1
        if POINTER in waived or not BASE <= value < self._end or vmap.to_version(value) == value:
            return None
        if self._slots is None:
            self._slots = set(vmap.pointer_slots)
        if code or value in self._symbols or here in self._slots:
            likely = True
        elif self._game_held(w):
            end = BASE + len(self._patched) - 3
            near = [_word(self._patched, at + k) for k in (-8, -4, 4, 8) if BASE <= at + k < end]
            held = [self._game_held(x) for x in near]
            likely = any(all(held[i:i + 2]) for i in range(len(held) - 1)) if len(held) == 4 else sum(held) >= 2
        else:
            likely = False
        if likely:
            return f"the word at {place(at)} holds the game pointer {w:#x} ({place(value)}), which no note accounts for"
        return None


def rebase(patched: bytes | bytearray, original: bytes, vmap: VersionMap, notes: Session,
           layout: Layout | None = None, *, canonical: bytes | None = None, symbols: Mapping[str, int] | None = None,
           exempt: Sequence[Exempt] = EXEMPT, game_code: tuple[tuple[int, int], ...] = GAME_CODE,
           free: tuple[tuple[int, int], ...] = FREE) -> Rebased:
    """The patches of `patched` (the canonical image `to_canonical(original, vmap)` after the patchers, which ran
    inside a `session.recording()` that gave `notes`) carried onto `original`, the player's executable of version
    `vmap`. `layout`: the blocks `notes.placed` names (their relocations); `canonical`: the unpatched image if the
    caller has it; `symbols`: the names of the relocations (GAME_SYMBOLS); `game_code` and `free`: the canonical
    ranges of the game's code and of our free regions (the leak detector's)."""
    if symbols is None:
        from core.game.executable.blocks import GAME_SYMBOLS as symbols
    if vmap.is_canonical:
        return Rebased(bytes(patched), (), (), len(changed_words(original, patched)))
    base = to_canonical(original, vmap) if canonical is None else canonical
    if len(base) != len(original):
        raise RebaseError(f"{vmap.key}: the canonical image has {len(base):#x} bytes, the executable "
                          f"{len(original):#x}")
    if len(patched) < len(base):
        raise RebaseError(f"{vmap.key}: the patched image is shorter than the executable")
    place = _Places(symbols, vmap, layout)
    out = bytearray(original)
    out.extend(bytes(len(patched) - len(out)))
    branch_slots: list[int] = []
    pointer_slots: list[int] = []

    def to_version(address: int, what: str) -> int:
        moved = vmap.to_version(address)
        if moved is None:
            raise RebaseError(f"{vmap.key}: {what} {place(address)}, which this game version does not have")
        return moved

    def translate(value: int, what: str) -> int:
        """A game address (a Thumb one keeps its bit 0) in the version."""
        return to_version(value & ~1, what) | (value & 1)

    def put(at: int, value: int) -> None:
        if at + 4 - BASE > len(out):
            raise RebaseError(f"{vmap.key}: {place(at)} lies past the executable")
        struct.pack_into("<I", out, at - BASE, value)

    changed = changed_words(base, patched)
    handled: set[int] = set()

    # Our linked blocks: the words that point into the game, from the link (code_space.json)
    linked: dict[int, int] = {}             # address -> the linked word, for every word of a placed block
    for name, at in notes.placed.items():
        if layout is None:
            raise RebaseError(f"{vmap.key}: block {name} was placed but no layout was given")
        block = layout.block(name)
        if block.address != at:
            raise RebaseError(f"{vmap.key}: block {name} placed at {at:#x}, the layout has it at {block.address:#x}")
        for k in range(0, len(block.data) - 3, 4):
            linked[at + k] = struct.unpack_from("<I", block.data, k)[0]
        for reloc in block.relocs:
            a = at + reloc.offset
            w = _word(patched, a)
            if w != linked.get(a):
                continue                    # Python wrote over it after placing: checked as any word below
            if reloc.symbol not in symbols:
                raise RebaseError(f"{vmap.key}: block {name}'s relocation at +{reloc.offset:#x} names "
                                  f"{reloc.symbol!r}, which is no game symbol")
            symbol = symbols[reloc.symbol]
            here = to_version(a, f"block {name}'s word at")      # our free regions: the block stays where it is
            if reloc.kind == CALL:
                target = arm_branch_target(w, a)
                if target is None:
                    raise RebaseError(f"{vmap.key}: block {name}'s call at +{reloc.offset:#x} is no ARM branch")
                moved = to_version(symbol & ~1, f"{name}'s call to {reloc.symbol} at") + target - (symbol & ~1)
                value = arm_branch(w, here, moved)
                if value is None:
                    raise RebaseError(f"{vmap.key}: block {name}'s call to {reloc.symbol} does not reach "
                                      f"{moved:#x}")
                branch_slots.append(here)
            elif reloc.kind == ABS32:
                value = (w + to_version(symbol & ~1, f"{name}'s word naming {reloc.symbol}:") - (symbol & ~1)) \
                    & 0xFFFFFFFF
                pointer_slots.append(here)
            else:
                raise RebaseError(f"{vmap.key}: block {name}: unknown relocation kind {reloc.kind!r}")
            put(here, value)
            handled.add(a)

    # The branches Python wrote, re-encoded for their place and target with their condition and link bits
    changed_set = set(changed)
    thumb: list[tuple[int, int, int, int]] = []
    for at, target in notes.branches.items():
        words = {at & ~3, (at + 2) & ~3} if at & 2 else {at}
        if not words & changed_set or words & handled:
            continue                        # unchanged: the version's own word is right
        w = _word(patched, at & ~3)
        decoded = arm_branch_target(w, at) if not at & 3 else None
        if decoded is not None and decoded == target & ~1:
            here = to_version(at, "a branch at")
            moved = translate(decoded, f"the target of the branch at {at:#x},") & ~1
            value = arm_branch(w, here, moved)
            if value is None:
                raise RebaseError(f"{vmap.key}: the branch at {place(at)} does not reach {moved:#x} from {here:#x}")
            put(here, value)
            branch_slots.append(here)
            handled.add(at)
            continue
        first, second = struct.unpack_from("<2H", patched, at - BASE)
        decoded = thumb_branch_target(first, second, at)
        if decoded is None or decoded != target & ~1:
            raise RebaseError(f"{vmap.key}: the branch noted at {place(at)} is no branch to {target:#x}")
        thumb.append((at, first, second, decoded))
        handled.update(words)

    # The game pointers Python wrote
    for at in notes.pointers:
        if at not in changed_set or at in handled:
            continue
        w = _word(patched, at)
        value = translate(w, f"the game address {w:#x} written at {at:#x}:")
        here = to_version(at, "a pointer at")
        put(here, value)
        pointer_slots.append(here)
        handled.add(at)

    # Every other changed word, as written, if it means the same in the version
    leaks = _Leaks(vmap, original, patched, symbols, _Exemptions(exempt, layout), place, game_code, free)
    for at in changed:
        if at in handled:
            continue
        w = _word(patched, at)
        here = to_version(at, "the patch writes")
        if linked.get(at) != w:             # a linked block's own word: the link proves it names no game address
            leak = leaks.check(at, here, w)
            if leak:
                raise RebaseError(f"{vmap.key}: leak: {leak}")
        put(here, w)

    for at, first, second, decoded in thumb:
        here = to_version(at, "a Thumb branch at")
        if to_version(at + 2, "a Thumb branch at") != here + 2:
            raise RebaseError(f"{vmap.key}: the Thumb branch at {place(at)} straddles two runs")
        for k in {at & ~3, (at + 2) & ~3}:  # the other halfwords of its words, as written
            if k in changed_set:
                put(to_version(k, "a Thumb branch at"), _word(patched, k))
        moved = translate(decoded, f"the target of the Thumb branch at {at:#x},")
        pair = thumb_branch(first, second, here, moved)
        if pair is None:
            raise RebaseError(f"{vmap.key}: the Thumb branch at {place(at)} does not reach {moved:#x}")
        struct.pack_into("<2H", out, here - BASE, *pair)
        branch_slots.append(here | 1)
    return Rebased(bytes(out), tuple(sorted(set(branch_slots))), tuple(sorted(set(pointer_slots))), len(changed))


def from_canonical(patched: bytes | bytearray, original: bytes, vmap: VersionMap, notes: Session,
                   layout: Layout | None = None, **options) -> bytes:
    """`rebase(...).code`: the player's executable with the patches of the canonical image `patched`."""
    return rebase(patched, original, vmap, notes, layout, **options).code


def feature_gaps(vmap: VersionMap) -> dict[str, tuple[str, ...]]:
    """The patch sites of `vmap.coverage` the version does not have ("hole"), by the module that names them
    ("GAME_SYMBOLS" for the game's symbols): module -> its constants (e.g. "TABLE_WORDS[24]"). A feature with a site
    here cannot patch that version: package D's notice "not available on this game version"."""
    out: dict[str, list[str]] = {}
    for name, status in sorted(vmap.coverage.items()):
        if status != HOLE:
            continue
        head, bracket, index = name.partition("[")
        module, _, constant = head.rpartition(".")
        out.setdefault(module, []).append(constant + bracket + index)
    return {module: tuple(names) for module, names in out.items()}
