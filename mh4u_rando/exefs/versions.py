"""The game versions the mod is built from, and the address map of each one.

Every address in the code and the docs is the EUR update's (MH4U) or the EUR game's (MH Generations): the
canonical address space. A `VersionMap` says where each canonical range sits in another version's executable:
`runs` move a canonical range by a delta, `holes` are canonical ranges the version does not have (code the update
changed), and the slots are the version's words that hold a position (branches and pointers) and so change when
the ranges move. The maps are made from the dumps by `tools/build_version_maps.py` and kept in
`generated/versions/`; the canonical versions themselves need no file (one run, delta 0).
"""

import base64
import bisect
import hashlib
import itertools
import json
import struct
import zlib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from . import titles

MAPS_DIR = Path(__file__).with_name("generated") / "versions"
FORMAT = 1
MH4U, MHGEN = "mh4u", "mhgen"
# The canonical executables: the EUR update's code.bin (MH4U) and the EUR game's (MH Generations).
CANONICAL = {MH4U: "eur_update", MHGEN: "mhgen_eur"}
CANONICAL_SHA256 = {
    "eur_update": "4ffd2ebb8c7d212a8a33cd222ccc85e8e337db9ee1ea1467189899e485017722",
    "mhgen_eur": "35064a55243233cc62cb67bd11d5929a3d43c2a1c6a7344ff4d9755b1e5b7691",
}
CANONICAL_TITLES = {"eur_update": titles.MH4U_EUR, "mhgen_eur": titles.MHGEN_EUR}
ADDRESS_END = 1 << 32


class UnsupportedVersion(ValueError):
    """An executable that is none of the known versions (modified, another region, another game)."""

    def __init__(self, message: str, title_id: str | None = None):
        super().__init__(message)
        self.title_id = title_id


@dataclass(frozen=True)
class Run:
    """Canonical addresses [start, end) sit at address + delta in the version."""
    start: int
    end: int
    delta: int


def pack_addresses(addresses) -> str:
    """Sorted addresses as base64 of zlib of the gaps between them, little-endian u32 (the slot lists hold tens of
    thousands, and their gaps compress far better than the addresses)."""
    values = sorted(set(addresses))
    gaps = [b - a for a, b in zip([0, *values], values)]
    return base64.b64encode(zlib.compress(struct.pack(f"<{len(gaps)}I", *gaps), 9)).decode("ascii")


def unpack_addresses(text: str) -> tuple[int, ...]:
    data = zlib.decompress(base64.b64decode(text)) if text else b""
    return tuple(itertools.accumulate(struct.unpack(f"<{len(data) // 4}I", data)))


@dataclass
class VersionMap:
    """One version's executable against the canonical one of its game. `branch_slots` and `pointer_slots` are
    version addresses: the B/BL/BLX whose target moved by another delta than the branch itself (an odd slot is a
    Thumb BL/BLX pair at the address minus one), and the words that hold an address of a moved range. A hole may
    hold one-word runs: the entries of changed functions, whose address the version has (calls to them translate)
    but whose bytes differ. `coverage` names, for each canonical symbol or patch site the builder checked, whether
    it is in a run ("run"), mapped by hand ("manual") or in a hole or missing ("hole")."""
    key: str
    game: str
    title_id: str
    region: str
    sha256: str
    runs: tuple[Run, ...]
    holes: tuple[tuple[int, int], ...] = ()
    branch_slots: tuple[int, ...] = ()
    pointer_slots: tuple[int, ...] = ()
    coverage: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.runs = tuple(sorted(self.runs, key=lambda run: run.start))
        self._starts = [run.start for run in self.runs]
        by_version = sorted(self.runs, key=lambda run: run.start + run.delta)
        self._version_runs = by_version
        self._version_starts = [run.start + run.delta for run in by_version]

    @property
    def canonical(self) -> str:
        return CANONICAL[self.game]

    @property
    def is_canonical(self) -> bool:
        return self.key == self.canonical

    def run_of(self, address: int) -> Run | None:
        """The run holding canonical `address`, or None (a hole, or outside the executable)."""
        i = bisect.bisect_right(self._starts, address) - 1
        return self.runs[i] if i >= 0 and address < self.runs[i].end else None

    def to_version(self, address: int) -> int | None:
        """Where canonical `address` sits in this version, or None when the version has no counterpart."""
        run = self.run_of(address)
        return None if run is None else address + run.delta

    def to_canonical(self, address: int) -> int | None:
        """The canonical address of this version's `address`, or None for code the canonical one lacks."""
        i = bisect.bisect_right(self._version_starts, address) - 1
        if i < 0:
            return None
        run = self._version_runs[i]
        return address - run.delta if address < run.end + run.delta else None

    def to_json(self) -> dict:
        return {"format": FORMAT, "key": self.key, "game": self.game, "title_id": self.title_id,
                "region": self.region, "sha256": self.sha256,
                "runs": [[f"{run.start:#x}", f"{run.end:#x}", run.delta] for run in self.runs],
                "holes": [[f"{start:#x}", f"{end:#x}"] for start, end in self.holes],
                "branch_slots": pack_addresses(self.branch_slots),
                "pointer_slots": pack_addresses(self.pointer_slots),
                "coverage": dict(sorted(self.coverage.items()))}

    @classmethod
    def from_json(cls, data: dict) -> "VersionMap":
        if data.get("format") != FORMAT:
            raise ValueError(f"version map {data.get('key')}: format {data.get('format')}, expected {FORMAT}")
        return cls(key=data["key"], game=data["game"], title_id=data["title_id"], region=data["region"],
                   sha256=data["sha256"],
                   runs=tuple(Run(int(start, 16), int(end, 16), delta) for start, end, delta in data["runs"]),
                   holes=tuple((int(start, 16), int(end, 16)) for start, end in data["holes"]),
                   branch_slots=unpack_addresses(data["branch_slots"]),
                   pointer_slots=unpack_addresses(data["pointer_slots"]),
                   coverage=dict(data.get("coverage", {})))


def canonical_map(game: str) -> VersionMap:
    """The canonical version of `game` against itself: every address where it is."""
    key = CANONICAL[game]
    return VersionMap(key=key, game=game, title_id=CANONICAL_TITLES[key], region=titles.EUR,
                      sha256=CANONICAL_SHA256[key], runs=(Run(0, ADDRESS_END, 0),))


@cache
def known_maps() -> tuple[VersionMap, ...]:
    """Every version with a map file, plus the two canonical ones."""
    maps = [canonical_map(MH4U), canonical_map(MHGEN)]
    for path in sorted(MAPS_DIR.glob("*.json")) if MAPS_DIR.is_dir() else []:
        maps.append(VersionMap.from_json(json.loads(path.read_text(encoding="utf-8"))))
    return tuple(maps)


def identify(code: bytes, game: str = MH4U, title_id: str | None = None) -> VersionMap:
    """The map of the version whose decompressed code.bin is `code`; UnsupportedVersion if none is."""
    digest = hashlib.sha256(code).hexdigest()
    for version in known_maps():
        if version.game == game and version.sha256 == digest:
            return version
    name = "Monster Hunter 4 Ultimate" if game == MH4U else "Monster Hunter Generations"
    raise UnsupportedVersion(f"{name}: this executable is not a version the mod knows (title {title_id or '?'}, "
                             f"sha256 {digest[:12]}); use the European or American game, unmodified", title_id)
