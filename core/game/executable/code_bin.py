"""Load the game executable from whatever file the player has."""

from pathlib import Path

from core.game.executable.containers import ExtractError, looks_like_container
from core.game.executable.extract import extract_code


def is_container(path: Path) -> bool:
    """True for a game file in an accepted format (.3ds, .cci, .cxi, .app, .cia, .zcci, .zcxi, .zcia; containers.py),
    as opposed to a loose game file."""
    return looks_like_container(path)


def load_code(path: Path) -> bytes:
    """Decompressed, verified code.bin from a code.bin or a decrypted game file (a .3ds, an update's .app...)."""
    from core.equipment.tables.tables import (  # the equipment tables, only when a file is loaded
        CodeBinError, verify_code,
    )
    path = Path(path)
    if is_container(path):
        try:
            code, _ = extract_code(path)
        except ExtractError as error:
            raise CodeBinError(str(error)) from error
    else:
        code = path.read_bytes()
    verify_code(code)
    return code
