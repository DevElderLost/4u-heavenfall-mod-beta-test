"""The recorder's snapshot of the game's GUI: every GUI manager with its root groups
and their pane trees, the proof that the copy is exact, and where it came from. Stored as JSON compressed with zstd
(`.json.zst`).

The format is versioned (`FORMAT`). Groups and panes keep a fixed core (address, hash, name, kind, the tree) and put
every value read from the game in `fields` (name -> JSON value): a reader that knows more of the structures
(`gamegui/structs.py`) adds fields without changing the format. `raw` keeps the bytes the reader took a pane's values
from, so nothing read is lost."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORMAT = 1
SUFFIX = ".json.zst"


class SnapshotFormatError(ValueError):
    """A file that is no snapshot, or one of a format this code does not read."""


@dataclass
class Pane:
    address: int
    hash: int
    kind: str                       # "sprite", "null", "text", "boundary", or "kind <n>" for one not known
    depth: int                      # 1 for the root group's own panes
    name: str | None = None         # from the layout file (checks.py); None for a text's own null
    role: str = ""                  # "text null": the null the game adds after each text (no record in the file)
    fields: dict = field(default_factory=dict)
    placed_by_game: list[str] = field(default_factory=list)   # fields whose value differs from the layout file's
    raw: str = ""                   # hex of the pane's data object as copied
    text: str | None = None         # a text pane's string, once a reader knows where it is
    children: list["Pane"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass
class Group:
    address: int
    slot: int                       # index in its manager's list
    hash: int
    screen: int                     # 0 top, 7 bottom (bits 14-17 of +0x44)
    shown: bool
    layer: int
    priority: int
    name: str | None = None         # the root group's name in its layout file
    layout: str | None = None       # the layout's ARC entry name
    instance: int = 0               # 0 for the first group of this name in the manager, 1 for the next...
    fields: dict = field(default_factory=dict)
    placed_by_game: list[str] = field(default_factory=list)
    panes: list[Pane] = field(default_factory=list)

    @property
    def label(self) -> str:
        """The group's name (its hash when unnamed), with `#n` for a second instance."""
        name = self.name or f"{self.hash:08x}"
        return name if not self.instance else f"{name}#{self.instance}"

    def walk(self):
        for pane in self.panes:
            yield from pane.walk()


@dataclass
class Manager:
    name: str                       # "main" for the GUI's own; the scenes' own managers by their scene
    address: int
    groups: list[Group] = field(default_factory=list)


@dataclass
class Proof:
    """Why the copy is exact. `method` "frame_marks": the game's two frame marks read before and after the copy agreed
    (`started` == `done`, unchanged), after `attempts` tries; "save_state": a save state, frozen by nature."""
    method: str
    started: int | None = None
    done: int | None = None
    attempts: int = 1


@dataclass
class Source:
    kind: str                       # "live" or "state"
    path: str | None = None         # the save state's file
    window: str | None = None       # "Ventana 1"... for live copies
    pid: int | None = None


@dataclass
class Snapshot:
    source: Source
    time: float                     # seconds since the epoch: the copy, or the save state file's time
    proof: Proof
    reader: str                     # which reader made `managers`
    managers: list[Manager] = field(default_factory=list)
    game_version: str | None = None     # the version map's key (eur_base, usa_base, eur_update...)
    mod: dict | None = None             # the installed mod's marker and executable hash; None when not known
    language: str | None = None         # the emulator's system language (the game's), None when not known
    checks: dict = field(default_factory=dict)   # what the checks found (checks.py)
    extra: dict = field(default_factory=dict)
    format: int = FORMAT

    def groups(self):
        for manager in self.managers:
            yield from manager.groups

    def shown(self) -> list[str]:
        """The labels of the shown root groups, sorted."""
        return sorted(group.label for group in self.groups() if group.shown)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        if data.get("format") != FORMAT:
            raise SnapshotFormatError(f"snapshot format {data.get('format')!r}, this code reads {FORMAT}")

        def pane(d: dict) -> Pane:
            return Pane(**{**d, "children": [pane(c) for c in d.get("children", [])]})

        def group(d: dict) -> Group:
            return Group(**{**d, "panes": [pane(p) for p in d.get("panes", [])]})

        managers = [Manager(m["name"], m["address"], [group(g) for g in m["groups"]]) for m in data["managers"]]
        return cls(**{**data, "source": Source(**data["source"]), "proof": Proof(**data["proof"]),
                      "managers": managers})

    def to_bytes(self) -> bytes:
        import zstandard
        text = json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))
        return zstandard.ZstdCompressor(level=3).compress(text.encode("utf-8"))

    @classmethod
    def from_bytes(cls, data: bytes) -> "Snapshot":
        import zstandard
        try:
            text = zstandard.ZstdDecompressor().stream_reader(data).read()
            return cls.from_dict(json.loads(text))
        except (zstandard.ZstdError, ValueError, KeyError, TypeError) as error:
            if isinstance(error, SnapshotFormatError):
                raise
            raise SnapshotFormatError(f"not a snapshot: {error}") from error

    def save(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        part.write_bytes(self.to_bytes())
        part.replace(path)
        return path


def load(path: Path) -> Snapshot:
    return Snapshot.from_bytes(Path(path).read_bytes())
