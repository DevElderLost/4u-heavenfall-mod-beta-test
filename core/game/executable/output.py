"""Write the patched executable into a mod folder, in the form the emulator and Luma3DS load.

The mod always ships the whole `exefs/code.bin`, with the game's exheader as `exheader.bin` at the mod's root:
extended when the executable grew (a block in the extension), else only
marked not compressed. Never `exefs/code.ips`: an IPS applies to whatever code.bin runs, the update's included, while
the mod is built for the player's own version. A `code.ips` left by an
older run is removed, so a mod folder rebuilt by another run (or by fix mode) never mixes both.
"""

from pathlib import Path

from core.game.executable.code_space import BASE_ADDRESS
from core.game.executable.exheader import extend_exheader, without_compression

IPS_PATH = Path("exefs") / "code.ips"
CODE_PATH = Path("exefs") / "code.bin"
EXHEADER_PATH = Path("exheader.bin")


def write_exefs(mod_dir: Path, original: bytes, patched: bytes, exheader: bytes | None = None) -> Path:
    """Write `patched` (built from `original`, the clean executable) into `mod_dir` as code.bin and return its path.
    `exheader`: the clean executable's (its game's), needed when `patched` grew; without one (a bare code.bin) only
    code.bin is written."""
    mod_dir = Path(mod_dir)
    if len(patched) > len(original):
        if exheader is None:
            raise ValueError("an extended executable needs its game's exheader")
        new_exheader = extend_exheader(exheader, BASE_ADDRESS + len(patched))
    else:
        new_exheader = None if exheader is None else without_compression(exheader)
    written = mod_dir / CODE_PATH
    written.parent.mkdir(parents=True, exist_ok=True)
    written.write_bytes(patched)
    if new_exheader is None:
        (mod_dir / EXHEADER_PATH).unlink(missing_ok=True)
    else:
        (mod_dir / EXHEADER_PATH).write_bytes(new_exheader)
    (mod_dir / IPS_PATH).unlink(missing_ok=True)
    return written


def remove_exefs(mod_dir: Path, keep: Path | None = None) -> None:
    """Remove the executable files of `mod_dir` (but `keep`): a patch left by an earlier run would still be loaded."""
    for relative in (IPS_PATH, CODE_PATH, EXHEADER_PATH):
        path = Path(mod_dir) / relative
        if path != keep:
            path.unlink(missing_ok=True)
