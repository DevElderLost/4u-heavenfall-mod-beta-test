"""Title ids of the games the mod reads, and their regions.

The mod is built from the player's base game (cartridge or eShop dump), European or American; the updates are
known only to recognise them and to tell the player they are not needed. The mod folder is named after the base
title: Azahar and Luma apply it with or without the update installed.
"""

from pathlib import Path

MH4U_EUR = "0004000000126100"
MH4U_USA = "0004000000126300"
MH4U_EUR_UPDATE = "0004000e00126100"
MH4U_USA_UPDATE = "0004000e00126300"
MHGEN_EUR = "0004000000185b00"
MHGEN_USA = "0004000000187000"

EUR, USA = "eur", "usa"

MH4U_REGIONS = {MH4U_EUR: EUR, MH4U_USA: USA}
MH4U_UPDATES = {MH4U_EUR_UPDATE: EUR, MH4U_USA_UPDATE: USA}
MHGEN_REGIONS = {MHGEN_EUR: EUR, MHGEN_USA: USA}


def normal(title_id: str) -> str:
    """`title_id` as these constants spell it: 16 lowercase hex digits."""
    return title_id.lower().removeprefix("0x").rjust(16, "0")


def mh4u_region(title_id: str) -> str | None:
    """"eur" or "usa" for a base MH4U, None for anything else (an update included)."""
    return MH4U_REGIONS.get(normal(title_id))


def mhgen_region(title_id: str) -> str | None:
    """"eur" or "usa" for MH Generations, None for anything else."""
    return MHGEN_REGIONS.get(normal(title_id))


def mod_title(region: str) -> str:
    """The title id the mod folder is named after (load/mods/<id>, luma/titles/<id>), in upper case as Azahar
    and Luma write it."""
    return {EUR: MH4U_EUR, USA: MH4U_USA}[region].upper()


# ---- which game a title or a file is ---------------------------------------------------------------------------------

MH4U, MH4U_UPDATE, MHGEN = "mh4u", "mh4u_update", "mhgen"


def identify(title_id: str) -> tuple[str, str] | None:
    """(game, region) of a title the mod knows: MH4U, MH4U_UPDATE or MHGEN, and "eur" or "usa"; None for anything
    else (another game, another region, DLC)."""
    title_id = normal(title_id)
    for game, table in ((MH4U, MH4U_REGIONS), (MH4U_UPDATE, MH4U_UPDATES), (MHGEN, MHGEN_REGIONS)):
        if title_id in table:
            return game, table[title_id]
    return None


def file_title(path) -> str | None:
    """The title id of a game file in any accepted format (header only, no RomFS); None when it cannot be read.
    Remembered per file (path, size and date), so a page may ask on every refresh."""
    path = Path(path)
    try:
        stat = path.stat()
    except OSError:
        return None
    return _file_title(str(path), stat.st_size, stat.st_mtime_ns)


def _file_title(path: str, size: int, mtime: int) -> str | None:
    key = (path, size, mtime)
    if key not in _FILE_TITLES:
        from core.game.executable.containers import ExtractError
        from core.game.executable.extract import ncch_identity
        try:
            _FILE_TITLES[key] = ncch_identity(Path(path))[0]
        except (ExtractError, OSError):
            _FILE_TITLES[key] = None
    return _FILE_TITLES[key]


def file_kind(path) -> tuple[str, str] | None:
    """`identify` of a game file's title (None: unreadable, or a game the mod does not know)."""
    title_id = file_title(path)
    return identify(title_id) if title_id else None


def mod_title_of_file(path) -> str | None:
    """The mod folder's title for a base MH4U file of either region (its update too: developer use); None for any
    other file."""
    kind = file_kind(path)
    return mod_title(kind[1]) if kind and kind[0] in (MH4U, MH4U_UPDATE) else None


_FILE_TITLES: dict[tuple[str, int, int], str | None] = {}
