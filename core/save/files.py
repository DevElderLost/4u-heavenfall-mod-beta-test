"""The single description of the save files: the 14 files of
MH4U's save, the three containers that hold them (MH4U's save archive, MH4U's extdata, Heavenfall's own extdata), the
names of the sidecar files the single-screen edition keeps in MH4U's extdata, the cheats' flag beside them, and the
legacy names read only to migrate. The program (both editions) and the 3DS launcher (`c_defines`, `c_header`) read
nothing else.

Format constants only: the sizes and kinds are the game's (`FUN_002ace98`, the names at 0xF31FC8); the tuning of
backups is core/game/data/curated/save_backups.json. This module imports nothing heavy: the editions all ship it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import PurePosixPath

EUR, USA = "eur", "usa"
REGIONS = (EUR, USA)
SLOTS = (1, 2, 3)

# The titles: MH4U's (core/game/executable/titles.py spells the same ids) and Heavenfall's own application, whose
# unique id (bits 8-27) names its extdata.
MH4U_TITLES = {EUR: "0004000000126100", USA: "0004000000126300"}
HEAVENFALL_TITLES = {EUR: "0004000006969100", USA: "0004000006969200"}

# The containers, by key.
MH4U_SAVE = "mh4u_save"                  # the save archive of MH4U's title: system, user1-3
MH4U_EXTDATA = "mh4u_extdata"            # MH4U's extdata: card1-3, cardbox, quest1-5, otomo1 (and the sidecars)
HEAVENFALL_EXTDATA = "heavenfall_extdata"    # Heavenfall's own extdata: the whole set, 14 names
CONTAINERS = (MH4U_SAVE, MH4U_EXTDATA, HEAVENFALL_EXTDATA)

# The ciphers (core/save/crypt.py): `user` the whole file, `card` Blowfish from CARD_BLOWFISH_FROM; `none` is a file
# the PC program never opens.
USER, CARD, NONE = "user", "card", "none"

MAIN, SIDECAR, LEGACY = "main", "sidecar", "legacy"


@dataclass(frozen=True)
class SaveFile:
    kind: int | None            # the game's file kind (0-13); None for a sidecar or a legacy file
    name: str
    size: int | None            # None for a legacy file (read only to migrate, whatever its size)
    slot: int | None            # 1-3 for a hunter's file, None for the shared ones (system, cardbox, ...)
    cipher: str
    role: str = MAIN


def _files() -> tuple[SaveFile, ...]:
    made = [SaveFile(3, "system", 0x200, None, NONE)]
    made += [SaveFile(slot - 1, f"user{slot}", 0x13E00, slot, USER) for slot in SLOTS]
    made += [SaveFile(3 + slot, f"card{slot}", 0x78C00, slot, CARD) for slot in SLOTS]
    made.append(SaveFile(7, "cardbox", 0x42000, None, NONE))
    made += [SaveFile(7 + number, f"quest{number}", 0x50400, None, NONE) for number in range(1, 6)]
    made.append(SaveFile(13, "otomo1", 0x2200, None, NONE))
    return tuple(sorted(made, key=lambda f: f.kind))


FILES = _files()                                  # the 14 files, by kind
FILE_BY_NAME = {f.name: f for f in FILES}
NAMES = tuple(f.name for f in FILES)
SAVE_ARCHIVE_KINDS = range(0, 4)                  # the game keeps kinds 0-3 in the save archive, 4-13 in the extdata


def files_of(container: str) -> tuple[SaveFile, ...]:
    """The files `container` holds: the archive's four, MH4U's extdata's ten, Heavenfall's extdata's whole set."""
    if container == MH4U_SAVE:
        return tuple(f for f in FILES if f.kind in SAVE_ARCHIVE_KINDS)
    if container == MH4U_EXTDATA:
        return tuple(f for f in FILES if f.kind not in SAVE_ARCHIVE_KINDS)
    if container == HEAVENFALL_EXTDATA:
        return FILES
    raise ValueError(f"unknown container {container!r}")


# ---- the names beside the 14: sidecars (single-screen edition) and legacy (read only to migrate) ---------------------

GENERATIONS = ("a", "b")        # two alternating generations of the extras: the one not picked is written next

# The sidecars' sizes, chosen once and for good: an extdata file keeps the size it was created with, so a later build
# grows an image only inside these (a new field in the spare room, told apart by the image's version field). The
# images' layout is core/save/extras.py's (its test checks it fits):
# * user image 0x6000: header 0x40, fixed fields to 0x414 (spare to 0x800), 51 Felyne looks of 12 bytes from 0x800
#   (spare to 0x1000), 2864 item entries of 6 bytes from 0x1000 (every item box and pouch slot twice over: taken, and
#   as many left over) to 0x5320, spare to 0x6000;
# * card image 0x5000: header 0x40, the card file's tail whole (0x388) and the 100 book cards' looks (0x34 each: the
#   block, then the card's check sum) to 0x1818 (spare to 0x1C00), 1536 item set entries of 6 bytes from 0x1C00 (24 sets
#   of 32 pairs twice over) to 0x4000, spare to 0x5000 (a whole kilobyte more than the fields to come need).
USER_EXTRAS_SIZE = 0x6000
CARD_EXTRAS_SIZE = 0x5000
ORIGINAL_USER_SIZE = 0x13E00                     # the original `userN`, whole
KEPT_EXTRAS_SIZE = USER_EXTRAS_SIZE + CARD_EXTRAS_SIZE   # another hunter's user image, then its card image
# what an older Heavenfall left in the slot's userN / cardN (core/save/heav.py): blocks appended, never rewritten; the
# size of the two card images, whose buffer the game's card operations read it into (core/save/beta_sidecar.c)
HEAV_SIZE = 2 * CARD_EXTRAS_SIZE


def user_extras(slot: int, generation: int) -> str:
    """The slot's user extras, generation 0 (`a`) or 1 (`b`)."""
    return f"hfxu{slot}{GENERATIONS[generation]}"


def card_extras(slot: int, generation: int) -> str:
    return f"hfxc{slot}{GENERATIONS[generation]}"


def original_user(slot: int) -> str:
    """The original `userN`, kept before its first conversion."""
    return f"hfold{slot}"


def kept_extras(slot: int) -> str:
    """Extras set aside from another hunter."""
    return f"hfkeep{slot}"


def heav_extras(slot: int) -> str:
    """What an older Heavenfall left in the slot's files, set apart (core/save/heav.py)."""
    return f"hfheav{slot}"


# The cheats' flag: a file of MH4U's extdata, beside the sidecars, that the
# 3DS launcher writes (More > Cheats) and Heavenfall Beta's installed title reads once a launch (save/beta_sidecar.c
# beta_cheats_flag). Little-endian: the magic, the version, `allowed` (1: the title shows and runs its Cheats group),
# a zero word. A missing file, or one shorter than that, of another magic or version, `allowed` other than 1 or a last
# word other than 0, allows nothing; bytes past the 16 are not looked at.
CHEATS_FLAG = "hfcheat"
CHEATS_FLAG_SIZE = 16
CHEATS_FLAG_MAGIC = b"HFCH"
CHEATS_FLAG_VERSION = 1


def cheats_flag(allowed: bool) -> bytes:
    """The flag file's bytes."""
    return CHEATS_FLAG_MAGIC + struct.pack("<3I", CHEATS_FLAG_VERSION, int(allowed), 0)


def cheats_allowed(data: bytes | None) -> bool:
    """Whether a flag file's bytes (None: no file) allow the cheats, as the game reads them."""
    if data is None or len(data) < CHEATS_FLAG_SIZE or data[:4] != CHEATS_FLAG_MAGIC:
        return False
    version, allowed, zero = struct.unpack_from("<3I", data, 4)
    return version == CHEATS_FLAG_VERSION and allowed == 1 and zero == 0


def legacy_user(slot: int) -> str:
    return f"hfuser{slot}"


def legacy_card(slot: int) -> str:
    return f"hfcard{slot}"


def legacy_record(slot: int) -> str:
    return f"hfxfer{slot}"


def sidecar_names() -> tuple[str, ...]:
    names = []
    for slot in SLOTS:
        names += [user_extras(slot, 0), user_extras(slot, 1), card_extras(slot, 0), card_extras(slot, 1),
                  original_user(slot), kept_extras(slot), heav_extras(slot)]
    return tuple(names)


def legacy_names() -> tuple[str, ...]:
    return tuple(name for slot in SLOTS for name in (legacy_user(slot), legacy_card(slot), legacy_record(slot)))


def sidecar_size(name: str) -> int:
    """The fixed size of a sidecar file, by its name."""
    for prefix, size in (("hfxu", USER_EXTRAS_SIZE), ("hfxc", CARD_EXTRAS_SIZE), ("hfold", ORIGINAL_USER_SIZE),
                         ("hfkeep", KEPT_EXTRAS_SIZE), ("hfheav", HEAV_SIZE)):
        if name.startswith(prefix):
            return size
    raise ValueError(f"not a sidecar: {name!r}")


def sidecar_files() -> tuple[SaveFile, ...]:
    return tuple(SaveFile(None, name, sidecar_size(name), int(name[-2]) if name[-1] in "ab" else int(name[-1]), NONE,
                          SIDECAR) for name in sidecar_names())


def legacy_files() -> tuple[SaveFile, ...]:
    return tuple(SaveFile(None, name, None, int(name[-1]), NONE, LEGACY) for name in legacy_names())


def hunter_names(container: str) -> tuple[str, ...]:
    """Every name of a hunter's data worth a backup in `container`: the 14 in each; MH4U's extdata also holds the
    sidecars and the legacy files."""
    extra = sidecar_names() + legacy_names() if container == MH4U_EXTDATA else ()
    return NAMES + extra


# ---- ids and paths per region ----------------------------------------------------------------------------------------

def _region(region: str) -> str:
    if region not in REGIONS:
        raise ValueError(f"unknown region {region!r}")
    return region


def title_id(container: str, region: str) -> str:
    """The title the container belongs to: MH4U's for its two, Heavenfall's own application for its extdata."""
    table = HEAVENFALL_TITLES if container == HEAVENFALL_EXTDATA else MH4U_TITLES
    return table[_region(region)]


def extdata_id(container: str, region: str) -> int:
    """The extdata id of an extdata container: its title's unique id (bits 8-27 of the title id)."""
    if container == MH4U_SAVE:
        raise ValueError("the save archive has no extdata id")
    return int(title_id(container, region), 16) >> 8 & 0xFFFFF


def container_path(container: str, region: str) -> PurePosixPath:
    """The container's folder under the console's `<id0>/<id1>` folder of an emulator's SD card."""
    title = title_id(container, region)
    if container == MH4U_SAVE:
        return PurePosixPath("title") / title[:8] / title[8:] / "data" / "00000001"
    return PurePosixPath("extdata") / "00000000" / f"{extdata_id(container, region):08x}" / "user"


# ---- the 3DS launcher's C -----------------------------------------------------------------------------------------

def c_defines() -> dict[str, str]:
    """The save's constants as C macros (name -> the text after the name), for `-D` flags or `c_header`."""
    defines = {"HF_SAVE_FILE_COUNT": str(len(FILES)), "HF_SAVE_SLOTS": str(len(SLOTS))}
    for f in FILES:
        key = f"HF_FILE_{f.name.upper()}"
        defines[f"{key}_KIND"] = str(f.kind)
        defines[f"{key}_SIZE"] = hex(f.size)
        defines[f"{key}_NAME"] = f'"{f.name}"'
    for region in REGIONS:
        suffix = region.upper()
        defines[f"HF_MH4U_TITLE_{suffix}"] = f"0x{MH4U_TITLES[region]}ull"
        defines[f"HF_MH4U_EXTDATA_{suffix}"] = hex(extdata_id(MH4U_EXTDATA, region))
        defines[f"HF_HEAVENFALL_TITLE_{suffix}"] = f"0x{HEAVENFALL_TITLES[region]}ull"
        defines[f"HF_HEAVENFALL_EXTDATA_{suffix}"] = hex(extdata_id(HEAVENFALL_EXTDATA, region))
    defines["HF_SIDECAR_USER_EXTRAS_FMT"] = '"hfxu%d%c"'         # slot, generation letter
    defines["HF_SIDECAR_CARD_EXTRAS_FMT"] = '"hfxc%d%c"'
    defines["HF_SIDECAR_ORIGINAL_USER_FMT"] = '"hfold%d"'
    defines["HF_SIDECAR_KEPT_EXTRAS_FMT"] = '"hfkeep%d"'
    defines["HF_SIDECAR_HEAV_FMT"] = '"hfheav%d"'
    defines["HF_LEGACY_USER_FMT"] = '"hfuser%d"'
    defines["HF_LEGACY_CARD_FMT"] = '"hfcard%d"'
    defines["HF_LEGACY_RECORD_FMT"] = '"hfxfer%d"'
    defines["HF_SIDECAR_USER_EXTRAS_SIZE"] = hex(USER_EXTRAS_SIZE)
    defines["HF_SIDECAR_CARD_EXTRAS_SIZE"] = hex(CARD_EXTRAS_SIZE)
    defines["HF_SIDECAR_ORIGINAL_USER_SIZE"] = hex(ORIGINAL_USER_SIZE)
    defines["HF_SIDECAR_KEPT_EXTRAS_SIZE"] = hex(KEPT_EXTRAS_SIZE)
    defines["HF_SIDECAR_HEAV_SIZE"] = hex(HEAV_SIZE)
    return defines


HEADER_GUARD = "HEAVENFALL_SAVE_FILES_H"


def c_header() -> str:
    """The text of a C header holding `c_defines`, for the launcher."""
    lines = ["/* Heavenfall's save files: generated by core/save/files.py (c_header); do not edit. */",
             f"#ifndef {HEADER_GUARD}", f"#define {HEADER_GUARD}", ""]
    lines += [f"#define {key} {value}" for key, value in c_defines().items()]
    lines += ["", f"#endif /* {HEADER_GUARD} */", ""]
    return "\n".join(lines)
