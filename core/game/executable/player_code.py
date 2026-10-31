"""The player's executable in a run: read from their game (or a loose
code.bin), identified by its version map, laid out as the canonical one for the patchers, and the patched image
carried back onto their own bytes. Every patcher works in the canonical address space (the EUR update's) whatever the
player has; the canonical executable itself (the update's, given as a developer's `code_path`) maps to itself.
"""

from dataclasses import dataclass
from pathlib import Path

from core.game.executable.canonical import to_canonical
from core.game.executable.code_bin import is_container
from core.game.executable.code_space import Layout, load_layout
from core.game.executable.containers import ExtractError
from core.game.executable.exheader import ExheaderError, exheader_version, extract_exheader
from core.game.executable.extract import extract_code
from core.game.executable.rebase import Rebased, RebaseError, rebase
from core.game.executable.session import Session
from core.game.executable.versions import MH4U, VersionMap, identify

# The refusal a patch the player's version cannot take becomes (gui/strings.py INSTALL_ERRORS translates it)
REFUSAL = "the mod cannot be built for this game version"


@dataclass(frozen=True)
class PlayerCode:
    """`original`: the player's decompressed code.bin, of version `version`; `image`: it laid out as the canonical
    executable (what every patcher patches); `exheader`: their game's, for the mod's exheader.bin (None for a loose
    code.bin whose game is not at hand)."""
    version: VersionMap
    original: bytes
    image: bytes
    exheader: bytes | None = None

    def carry(self, patched: bytes, notes: Session, layout: Layout | None = None) -> Rebased:
        """The patches of `patched` (`image` after the patchers, which noted `notes`) on the player's executable;
        a patch their version cannot take raises RebaseError (REFUSAL, then the reason). `layout` places the blocks
        placed (default: the committed one; a probe's adds its own blocks)."""
        try:
            return rebase(patched, self.original, self.version, notes, layout or load_layout(), canonical=self.image)
        except RebaseError as error:
            raise RebaseError(f"{REFUSAL}: {error}") from error


def read_code(source: Path) -> tuple[bytes, str | None]:
    """The decompressed code.bin of `source` (a game file in any accepted format, or a loose code.bin) and the
    title id it carries (None for a loose file)."""
    source = Path(source)
    if is_container(source):
        return extract_code(source)
    return source.read_bytes(), None


def _exheader(paths, version: VersionMap) -> bytes | None:
    """The first exheader of the game files `paths` that is `version`'s."""
    for path in paths:
        if path is None or not is_container(path):
            continue
        try:
            exheader = extract_exheader(Path(path))
            if exheader_version(exheader) == version.key:
                return exheader
        except (ExheaderError, ExtractError, OSError):
            continue
    return None


def open_code(source: Path, game: Path | None = None) -> PlayerCode:
    """The executable of `source` (the player's game, or a developer's code.bin or game file of any version with a
    map) ready for a run; UnsupportedVersion for any other executable. The exheader is `source`'s, else `game`'s when
    it is the same version's."""
    code, title = read_code(source)
    version = identify(code, MH4U, title)
    return PlayerCode(version, code, to_canonical(code, version), _exheader((source, game), version))
