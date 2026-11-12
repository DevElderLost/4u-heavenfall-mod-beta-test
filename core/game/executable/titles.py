"""Title ids of the games the mod reads, and their regions.

The mod is built from the player's base game (cartridge or eShop dump), European or American; the updates are
known only to recognise them and to tell the player they are not needed. The mod folder is named after the base
title: Azahar and Luma apply it with or without the update installed.
"""

from pathlib import Path

from core.memo import remember

MH4U_EUR = "0004000000126100"
MH4U_USA = "0004000000126300"
MH4U_EUR_UPDATE = "0004000e00126100"
MH4U_USA_UPDATE = "0004000e00126300"
MHGEN_EUR = "0004000000185b00"
MHGEN_USA = "0004000000187000"
MHXX_JPN = "0004000000197100"       # MH XX (Double Cross), the Japanese release: a source game of the ported monsters

EUR, USA, JPN = "eur", "usa", "jpn"

MH4U_REGIONS = {MH4U_EUR: EUR, MH4U_USA: USA}
MH4U_UPDATES = {MH4U_EUR_UPDATE: EUR, MH4U_USA_UPDATE: USA}
MHGEN_REGIONS = {MHGEN_EUR: EUR, MHGEN_USA: USA}
MHXX_REGIONS = {MHXX_JPN: JPN}


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

MH4U, MH4U_UPDATE, MHGEN, MHXX = "mh4u", "mh4u_update", "mhgen", "mhxx"


def identify(title_id: str) -> tuple[str, str] | None:
    """(game, region) of a title the mod knows: MH4U, MH4U_UPDATE, MHGEN or MHXX, and "eur", "usa" or (MH XX) "jpn";
    None for anything else (another game, another region, DLC)."""
    title_id = normal(title_id)
    for game, table in ((MH4U, MH4U_REGIONS), (MH4U_UPDATE, MH4U_UPDATES), (MHGEN, MHGEN_REGIONS),
                        (MHXX, MHXX_REGIONS)):
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
    def make():
        from core.game.executable.containers import ExtractError
        from core.game.executable.extract import ncch_identity
        try:
            return ncch_identity(Path(path))[0]
        except (ExtractError, OSError):
            return None

    return remember(_FILE_TITLES, (path, size, mtime), make)


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
