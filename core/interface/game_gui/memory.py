"""The running game's memory in the emulator's process (interface/game_gui/process.py), with canonical addresses: the
version that runs is found by the anchor table, as tools/inspect/citra_state.py finds
it in a save state. Read only.

Taken from the archived live editor, where `attach`
found the game on two PCs; its writing was removed."""

from collections.abc import Iterable
from pathlib import Path

from core.interface.game_gui.process import LinkError, LinkRefused, ProcessMemory

BASE_ADDRESS = 0x100000
ANCHOR = 0xFB8140          # static .data table, 0x90 bytes, read only by FUN_006949d4
ANCHOR_SIZE = 0x90


class UnknownGame(LinkError):
    """No local executable's anchor table matches the running game (the emulator runs another game, or not yet)."""


class GameMemory:
    """`u32` / `read` of canonical .data / .bss addresses go through the running version's map; `word` / `read_raw`
    take the process's own addresses (the heap). `client` reads the game's addresses (interface/game_gui/process.py,
    ProcessMemory)."""

    def __init__(self, client: ProcessMemory, version=None):
        self.client = client
        self.version = version

    def shift(self, address: int) -> int:
        moved = None if self.version is None else self.version.to_version(address)
        return address if moved is None else moved

    def u32(self, address: int) -> int:
        return self.client.word(self.shift(address))

    def word(self, address: int) -> int:
        return self.client.word(address)

    def read_raw(self, address: int, size: int) -> bytes:
        return self.client.read(address, size)

    def read(self, address: int, size: int) -> bytes:
        return self.client.read(self.shift(address), size)

    def close(self) -> None:
        self.client.close()


def anchor_of(code: bytes, version) -> tuple[int, bytes]:
    """(the running address, the bytes) of the anchor table in `code`, whose version map is `version`."""
    moved = None if version is None else version.to_version(ANCHOR)
    at = ANCHOR if moved is None else moved
    return at, code[at - BASE_ADDRESS:at - BASE_ADDRESS + ANCHOR_SIZE]


def detect_version(client: ProcessMemory, candidates: Iterable[tuple[bytes, object]]):
    """The version map of the first (code.bin, VersionMap or None) whose anchor table the running game holds."""
    for code, version in candidates:
        at, anchor = anchor_of(code, version)
        if len(anchor) < ANCHOR_SIZE or not any(anchor):
            continue
        try:
            if client.read(at, ANCHOR_SIZE) == anchor:
                return version
        except LinkRefused:
            continue
    raise UnknownGame("the running game is none of the local executables (local.ini: code, code_update, code_usa)")


def attach(pid: int, candidates: Iterable[tuple[bytes, object]]) -> GameMemory:
    """The game in the emulator process `pid`: of the page tables its memory holds (ProcessMemory.page_tables), the
    first whose anchor table is one of `candidates`' (code.bin, VersionMap or None), read through its version's map.
    LinkError: no game there yet; UnknownGame: a game none of the candidates is."""
    link = ProcessMemory(pid)
    candidates, unknown = list(candidates), False
    try:
        tables = link.page_tables()
        for table in tables:
            link.table = table
            try:
                return GameMemory(link, detect_version(link, candidates))
            except UnknownGame:
                unknown = True
            except LinkError:
                continue                        # not the game's table after all
    except BaseException:
        link.close()
        raise
    link.close()
    if unknown:
        raise UnknownGame("the emulator runs none of the local executables (local.ini: code, code_update, code_usa)")
    raise LinkError(f"no game in the emulator yet (process {pid}: {link.scanned} allocations of 8 MB or more looked "
                    f"into, {len(tables)} page tables by their shape, none holding a game)")


def local_candidates(paths: Iterable[Path] | None = None) -> list[tuple[bytes, object]]:
    """(code, version map) of this machine's executables (work/inputs: code, code_update, code_usa), or of `paths`;
    an executable of no known version is read as the update's (a probe build)."""
    from core.app import local_config
    from core.game.executable.versions import UnsupportedVersion, canonical_map, identify
    if paths is None:
        config = local_config.load()
        paths = [config.input(name) for name in ("code", "code_update", "code_usa")]
    out = []
    for path in paths:
        if path.is_file():
            code = path.read_bytes()
            try:
                version = identify(code)
            except UnsupportedVersion:
                version = canonical_map("mh4u")
            out.append((code, version))
    return out
