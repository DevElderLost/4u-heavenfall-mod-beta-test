"""The mod as a CIA for a real 3DS: the player's decrypted base game with the mod's files merged
into one RomFS, the mod's executable and exheader, under the edition's own title id for the game's region and with its
names and icons on the HOME Menu.

The mod folder is the emulator's form a run writes (`romfs/`, `exefs/code.bin`, `exheader.bin`;
game/executable/output.py). The base title keeps the game's RomFS and its hashes (kept_romfs.py), so the game is read
once and never held in memory; the CIA is written beside `out` and renamed into place when complete.

The split title is two: the game data (`build_game_cia`), an add-on content title holding
the dump's RomFS as it is, and the edition's title with the mod's files alone (`build_mod_cia`). Their build data:
`mod_title_digest` and `game_digest`.
"""

import hashlib
import json
import os
import struct
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.app.edition import Edition, edition
from core.game.executable import titles
from core.game.executable.containers import MEDIA_UNIT, open_container
from core.game.executable.exheader import built_version, exheader_version, without_compression
from core.game.executable.extract import ncch_identity, read_exactly, read_ncch
from core.game.executable.output import CODE_PATH, EXHEADER_PATH
from core.install.title.cia import write_cia
from core.install.title.ncch import (
    ADDON_HIGH, UPDATE_HIGH, Cfa, GameParts, Ncch, exefs, read_game_parts, retitle_exheader, sha256,
)
from core.install.title.kept_romfs import KeptRomfsImage, LayoutError
from core.install.title.romfs_writer import READ_CHUNK, RomfsImage, Source, game_sources
from core.install.title.title_digest import FORMAT_SPLIT, DigestFile, GameDigest, TitleDigest
from core.install.title.smdh import title_smdh

ROMFS_DIR = "romfs"
FAT32_LIMIT = 1 << 32           # an installed content is one file on the SD card
PATCH_MOUNT = b"patch:"         # the update RomFS's mount name, in an executable that reads it


class TitleError(ValueError):
    pass


def mod_sources(mod_dir: Path) -> dict[str, Source]:
    """Every file of the mod's `romfs/`, by its RomFS path."""
    root = Path(mod_dir) / ROMFS_DIR
    return {path.relative_to(root).as_posix(): Source.from_file(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def title_for(rom: Path, current: Edition | None = None) -> tuple[str, str]:
    """(region, the installed title's id) for a decrypted base MH4U of either region."""
    title_id, decrypted = ncch_identity(Path(rom))
    region = titles.mh4u_region(title_id)
    if region is None or not decrypted:
        raise TitleError(f"{Path(rom).name} is not a decrypted base MH4U (European or American)")
    console = (current or edition()).console_title
    if console is None:
        raise TitleError("this edition has no title for a real 3DS")
    if titles.identify(console.title_id(region)) is not None:     # it would replace the player's game
        raise TitleError(f"the edition's title {console.title_id(region)} is a game's own")
    return region, console.title_id(region)


@dataclass
class _Mod:
    """What both titles take from the game and the mod folder."""
    parts: GameParts
    region: str
    title_id: str               # the base title's
    code: bytes
    exheader: bytes             # the mod's, not yet retitled
    smdh: bytes


def _read_mod(rom: Path, mod_dir: Path, current: Edition) -> _Mod:
    region, title_id = title_for(rom, current)
    parts = read_game_parts(rom)
    code_path = mod_dir / CODE_PATH
    if not code_path.is_file():
        raise TitleError(f"{mod_dir} holds no {CODE_PATH.as_posix()}: not a mod folder in the emulator's form")
    exheader_path = mod_dir / EXHEADER_PATH
    exheader = exheader_path.read_bytes() if exheader_path.is_file() else without_compression(parts.exheader)
    if built_version(exheader) != exheader_version(parts.exheader):
        raise TitleError(f"the mod in {mod_dir} was not built from this game ({region})")
    console = current.console_title
    smdh = title_smdh(parts.exefs_files["icon"], console.short_name, console.long_name, console.publisher)
    return _Mod(parts, region, title_id, code_path.read_bytes(), exheader, smdh)


def _write(out: Path, title_id: str, ncch: Ncch, smdh: bytes, progress, stage, save_size: int | None = None,
           title_version: int | None = None) -> None:
    if ncch.size >= FAT32_LIMIT:
        raise TitleError(f"the title would be {ncch.size / 2**30:.2f} GiB; an installed title must stay under 4 GiB")
    if stage:
        stage("writing")
    partial = out.with_name(out.name + ".part")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with partial.open("wb") as f:
            write_cia(f, title_id, ncch, smdh, progress, save_size=save_size, title_version=title_version)
            f.flush()
            os.fsync(f.fileno())
        os.replace(partial, out)
    finally:
        partial.unlink(missing_ok=True)


def mod_manifest(mod_dir: Path) -> dict[str, str]:
    """The SHA-256 (hex) of every file of the mod's `romfs/`, by its RomFS path: what a base title holds, so an
    update title carries only what differs from it."""
    root = Path(mod_dir) / ROMFS_DIR
    manifest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    digest.update(block)
            manifest[path.relative_to(root).as_posix()] = digest.hexdigest()
    return manifest


def write_manifest(manifest: dict[str, str], path: Path) -> None:
    Path(path).write_text(json.dumps(manifest, indent=0, sort_keys=True), encoding="utf-8")


def read_manifest(path: Path) -> dict[str, str]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_cia(rom: Path, mod_dir: Path, out: Path, progress: Callable[[int, int], None] | None = None,
              stage: Callable[[str], None] | None = None, current: Edition | None = None,
              title_version: int | None = None) -> str:
    """Write the base title's CIA: the game `rom` with the mod in `mod_dir` over it, to `out`; return its title id.
    With an update title beside it (`build_update_cia`), what the update holds wins. `title_version`: the TMD's (the
    launcher writes the release's version there; cia.build_tmd)."""
    current = current or edition()
    rom, mod_dir, out = Path(rom), Path(mod_dir), Path(out)
    mod, ncch = _base_ncch(rom, mod_dir, current, progress, stage)
    _write(out, mod.title_id, ncch, mod.smdh, progress, stage, title_version=title_version)
    return mod.title_id


def _title_exefs(mod: _Mod) -> bytes:
    """The title's ExeFS: the game's files in its order, the mod's executable and the title's SMDH in their place."""
    replaced = {".code": mod.code, "icon": mod.smdh}
    return exefs([(name, replaced.get(name, data)) for name, data in mod.parts.exefs_files.items()])


def _base_ncch(rom: Path, mod_dir: Path, current: Edition, progress=None, stage=None) -> tuple[_Mod, Ncch]:
    """The base title's NCCH, its RomFS kept around the game's (kept_romfs.py) and prepared: the game is read once
    more when it streams."""
    mod = _read_mod(rom, mod_dir, current)
    exefs_image = _title_exefs(mod)
    try:
        romfs = KeptRomfsImage(rom, mod_sources(mod_dir))
        if stage:
            stage("hashing")
        romfs.prepare(progress)
    except LayoutError as e:
        raise TitleError(f"{Path(rom).name}: {e}") from e
    ncch = Ncch(mod.parts.header, mod.title_id, retitle_exheader(mod.exheader, mod.title_id), exefs_image, romfs,
                mod.parts.plain, mod.parts.logo)
    return mod, ncch


def base_title_digest(rom: Path, mod_dir: Path, progress: Callable[[int, int], None] | None = None,
                      current: Edition | None = None) -> TitleDigest:
    """The base title's build data (title_digest.py) for the game `rom` and the mod in `mod_dir`: its content is
    streamed once into SHA-256, nothing is written. The console's files must be these bytes for it to hold: for a patch
    set, the C applier's output (tools/release/build_console_patches.py), not the Python mod's ARCs."""
    current = current or edition()
    rom, mod_dir = Path(rom), Path(mod_dir)
    mod, ncch = _base_ncch(rom, mod_dir, current, progress)
    return _digest(mod, ncch, mod_dir, ncch.romfs.tail_hashes, progress)


def _digest(mod: _Mod, ncch: Ncch, mod_dir: Path, level2: bytes, progress=None, **more) -> TitleDigest:
    """The build data of the title `ncch` of `mod`: its content streamed once into SHA-256; `level2` the hashes the
    console checks the bytes it makes against."""
    digest = hashlib.sha256()
    for chunk in ncch.chunks(progress):
        digest.update(chunk)
    sizes = {path: src.size for path, src in mod_sources(mod_dir).items()}
    files = tuple(DigestFile(path, sizes[path], bytes.fromhex(sha)) for path, sha in mod_manifest(mod_dir).items())
    return TitleDigest(int(mod.title_id, 16), ncch.size, digest.digest(), mod.parts.header[0x1E0:0x200],
                       _sha(mod.code), _sha(mod.exheader), _sha(mod.smdh), files, level2, **more)


def _sha(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


# ---- the split title -----------------------------------------------------------------

def game_title_id(title_id: str) -> str:
    """The game data title of an edition's title: its low word under 0004008C (add-on content)."""
    return ADDON_HIGH + titles.normal(title_id)[8:]


class DumpRomfs:
    """The dump's RomFS region as it is, for the game data title: its IVFC levels and superblock hash unchanged, so
    nothing is hashed. Its hash region is checked against the NCCH header at once (TitleError for a damaged dump)."""

    def __init__(self, rom: Path):
        self._path = Path(rom)
        with open_container(self._path) as f:
            base, header = read_ncch(f)
            offset, size, region = struct.unpack_from("<III", header, 0x1B0)
            self._start = base + offset * MEDIA_UNIT
            self.size = size * MEDIA_UNIT
            self.hash_region_size = region * MEDIA_UNIT
            if not size or not 0 < self.hash_region_size <= min(self.size, READ_CHUNK):
                raise TitleError(f"{self._path.name} has no RomFS of the usual form")
            f.seek(self._start)
            self._region = read_exactly(f, self.hash_region_size, "the RomFS header")
        if sha256(self._region) != header[0x1E0:0x200]:
            raise TitleError(f"{self._path.name}: its RomFS does not match its NCCH header (a damaged dump)")
        self.template = header
        self.romfs_hash = header[0x1E0:0x200]

    def header_region(self) -> bytes:
        return self._region

    def chunks(self, progress=None):
        with open_container(self._path) as f:
            f.seek(self._start)
            left = self.size
            while left:
                data = f.read(min(READ_CHUNK, left))
                if not data:
                    raise TitleError(f"{self._path.name} is cut short inside its RomFS")
                left -= len(data)
                yield data
                if progress:
                    progress(self.size - left, self.size)


def _game_cfa(rom: Path, current: Edition) -> Cfa:
    _, title_id = title_for(rom, current)
    romfs = DumpRomfs(rom)
    return Cfa(romfs.template, game_title_id(title_id), romfs)


def build_game_cia(rom: Path, out: Path, progress: Callable[[int, int], None] | None = None,
                   stage: Callable[[str], None] | None = None, current: Edition | None = None,
                   title_version: int | None = None) -> str:
    """Write the game data title's CIA for the decrypted base game `rom` to `out`: an add-on content title (no
    executable, no save) whose one content is a CFA holding the dump's RomFS as it is. Returns its title id."""
    cfa = _game_cfa(Path(rom), current or edition())
    _write(Path(out), cfa.title_id, cfa, None, progress, stage, save_size=0, title_version=title_version)
    return cfa.title_id


def game_digest(rom: Path, current: Edition | None = None,
                progress: Callable[[int, int], None] | None = None) -> GameDigest:
    """The game data title's content size and SHA-256 for the dump `rom`, keyed by its RomFS superblock hash (a slot's
    game entry): the dump is read once, nothing is written."""
    cfa = _game_cfa(Path(rom), current or edition())
    digest = hashlib.sha256()
    for chunk in cfa.chunks(progress):
        digest.update(chunk)
    return GameDigest(cfa.romfs.romfs_hash, cfa.size, digest.digest())


def _mod_ncch(rom: Path, mod_dir: Path, current: Edition, progress=None, stage=None) -> tuple[_Mod, Ncch]:
    """The edition's title of the split: the full title's executable, exheader, ExeFS and regions, and a fresh RomFS
    (prepared) of the mod's files alone."""
    mod = _read_mod(rom, mod_dir, current)
    romfs = RomfsImage(mod_sources(mod_dir))
    if stage:
        stage("hashing")
    romfs.prepare(progress)
    ncch = Ncch(mod.parts.header, mod.title_id, retitle_exheader(mod.exheader, mod.title_id), _title_exefs(mod), romfs,
                mod.parts.plain, mod.parts.logo)
    return mod, ncch


def build_mod_cia(rom: Path, mod_dir: Path, out: Path, progress: Callable[[int, int], None] | None = None,
                  stage: Callable[[str], None] | None = None, current: Edition | None = None,
                  title_version: int | None = None) -> str:
    """Write the edition's title of the split to `out`: the mod in `mod_dir` with only its own files in the RomFS (the
    game's come from the game data title, build_game_cia). Returns its title id, the edition's."""
    current = current or edition()
    mod, ncch = _mod_ncch(Path(rom), Path(mod_dir), current, progress, stage)
    _write(Path(out), mod.title_id, ncch, mod.smdh, progress, stage, title_version=title_version)
    return mod.title_id


def mod_title_digest(rom: Path, mod_dir: Path, games: tuple[GameDigest, ...] = (),
                     progress: Callable[[int, int], None] | None = None, current: Edition | None = None) -> TitleDigest:
    """The split title's build data (format 3): the mod title's content hash and the level-2 hashes of its whole RomFS,
    what they were made from, the game data's title id and `games` (game_digest of each dump known). As
    base_title_digest, the console's files must be these bytes: the C applier's output for a patch set."""
    current = current or edition()
    mod_dir = Path(mod_dir)
    mod, ncch = _mod_ncch(Path(rom), mod_dir, current, progress)
    return _digest(mod, ncch, mod_dir, ncch.romfs.level2_hashes, progress, format=FORMAT_SPLIT,
                   game_title_id=int(game_title_id(mod.title_id), 16), games=tuple(games))


def update_title_id(base_title_id: str) -> str:
    """The update title of a base title: its low word under 0004000E, as the system looks for it."""
    return UPDATE_HIGH + titles.normal(base_title_id)[8:]


def update_files(rom: Path, mod_dir: Path, base: dict[str, str]) -> dict[str, Source]:
    """The files an update title carries over a base title holding `base` (mod_manifest of its mod): the mod's files
    that are new or differ, and the game's own copy of a file the base's mod replaced and this mod no longer does."""
    sources = mod_sources(mod_dir)
    now = mod_manifest(mod_dir)
    files = {path: sources[path] for path, digest in now.items() if base.get(path) != digest}
    dropped = [path for path in base if path not in now]
    if dropped:
        game = game_sources(rom)
        files.update({path: game[path] for path in dropped if path in game})
    return files


def build_update_cia(rom: Path, mod_dir: Path, base: dict[str, str], out: Path,
                     progress: Callable[[int, int], None] | None = None, stage: Callable[[str], None] | None = None,
                     current: Edition | None = None) -> tuple[str, int]:
    """Write the update title's CIA for a base title whose mod is
    `base` (mod_manifest): the mod's executable and exheader and only the files that differ. The executable must
    read the update's RomFS (`patch:`, the console title build). Returns (its title id, the files it holds)."""
    current = current or edition()
    rom, mod_dir, out = Path(rom), Path(mod_dir), Path(out)
    mod = _read_mod(rom, mod_dir, current)
    if PATCH_MOUNT not in mod.code:
        raise TitleError(f"the executable in {mod_dir} does not read an update's files: build it for the console title")
    update_id = update_title_id(mod.title_id)
    files = update_files(rom, mod_dir, base)
    romfs = RomfsImage(files)
    if stage:
        stage("hashing")
    romfs.prepare(progress)
    exefs_image = exefs([(".code", mod.code), ("icon", mod.smdh)])     # the official update's ExeFS has only these
    exheader = retitle_exheader(mod.exheader, update_id, mod.title_id)
    ncch = Ncch(mod.parts.header, update_id, exheader, exefs_image, romfs, mod.parts.plain, mod.parts.logo)
    _write(out, update_id, ncch, mod.smdh, progress, stage, save_size=0)
    return update_id, len(files)
