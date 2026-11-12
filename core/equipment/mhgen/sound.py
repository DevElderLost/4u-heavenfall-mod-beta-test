"""MH Generations' weapon sounds as MH4U's.

MHGen keeps a weapon's sounds in an archive of their own (`arc/weapon/wNN/snd/NNN.arc`), MH4U in the model
archive. Both hold waves, a bank naming the waves by path and requests naming the bank, in other versions of
the same classes:
* wave: MADP (DSP-ADPCM, the same in both); MHGen adds a build date at 0x2C, before the channel blocks, so the
  blocks, the header end (+0x1C) and the data (the header end aligned to 0x20) move back 8 bytes.
* bank: SBKR v4 -> SNDB v11. Its entries come in groups (two in the bowguns' SF banks), each with a 12-byte
  descriptor whose flags byte differs (MH4U 0x80 or 0x88, MHGen 0x08) and an 8-byte trailer. An entry is the
  wave's path (empty, type 0: no wave), type and 76 bytes; MHGen keeps the entry id (3 bytes, what the requests
  point at) at +0x47 where MH4U has it at +0x0C, the fields between 4 bytes later.
* requests: SRQR v5 -> SREQ v8, records of 0x64 -> 0x5C bytes with the same first 0x58.
MH4U's paths name the waves' folder `wave` (MHGen: `wav`) and keep the bowguns under `bgn\\`.
"""

import re
import struct

from core.game.files.arc import Arc, ArcEntry

WAVE = 0x67195A2E           # MADP
SOUND_BANK = 0x14B5C8E6     # SNDB
SOUND_REQUEST = 0x2618DE3F  # SREQ
SOUND_TYPES = (WAVE, SOUND_BANK, SOUND_REQUEST)
GEN_WAVE = 0x79C47B59       # MHGen's MADP
GEN_BANK = 0x15D782FB       # SBKR
GEN_REQUESTS = 0x1BCC4966   # SRQR

WAVE_HEADER = 0x2C          # MH4U's channel blocks; MHGen's are 8 bytes later
GEN_DATE = 8
CHANNEL_BLOCK = 0x34        # data offset, 16 coefficients, gain, scale, history
WAVE_HEADER_END = 0x1C
WAVE_ALIGN = 0x20

BANK_VERSION = 11
BANK_HEADER = 0x20
BANK_GROUPS = 0x10          # u32: groups of entries, each with a descriptor (the first at +0x14) and a trailer
GROUP = 12                  # descriptor: u16 group, u8 2 x entries, u8 flags, u32 first entry, u32 0
GROUP_FLAGS = 3
BANK_FLAGS_AT = 0x14 + GROUP_FLAGS
BANK_FLAGS = 0x80           # MH4U's usual group flags (0x88 on some); MHGen writes 0x08
BANK_ENTRY = 76
BANK_ENTRY_FLAG = 0x08      # +0x02 of every MH4U bank entry; 0 in MHGen
BANK_TRAILER = 8            # per group: a float, the group, 3 bytes MHGen fills (0xCD) and MH4U mostly leaves 0

REQUEST_VERSION = 8
REQUEST_HEADER = 0x10
REQUEST, GEN_REQUEST = 0x5C, 0x64
REQUEST_SHARED = 0x58       # then +0x58: the record's bank once loaded (FUN_0039800c), released if not 0 (FUN_00397d08)
# Request ids every MH4U model of a class has and MHGen's lack, per bank kind: the id -> the id it copies (as
# MH4U's own files do).
REQUEST_COPIES = {"snd_wp_hbgB": {3: 2}, "snd_wp_lbgB": {3: 2}}
SOUND_FOLDERS = {"hbg": "bgn\\hbg", "lbg": "bgn\\lbg"}  # MH4U's folder of a class's sounds, when not its name


def sound_renamer(cls: str, model: int, new_model: int):
    """The MH4U path of a sound path of `cls` model `model` (MHGen's or MH4U's), at model `new_model`. Every
    model folder becomes `new_model`'s: a few MHGen models play another's waves (swo 119 one of swo 118), which
    at their old path would be that MH4U model's own."""
    folder = SOUND_FOLDERS.get(cls, cls)
    models = re.compile(rf"(?<=\\wp\\{re.escape(folder)}\\)\d{{3}}(?=\\)")
    leaf = re.compile(rf"(?<=[A-Za-z]){model:03d}(?=[_\x00]|$)")  # bowguns: snd_wp_lbgB001

    def rename(path: str) -> str:
        path = path.replace(f"\\wp\\{cls}\\", f"\\wp\\{folder}\\").replace("\\wav\\", "\\wave\\")
        return leaf.sub(f"{new_model:03d}", models.sub(f"{new_model:03d}", path))
    return rename


def convert_wave(data: bytes) -> bytes:
    """MHGen's MADP `data` as MH4U's."""
    channels = data[8] if len(data) > 8 else 0
    blocks_at = WAVE_HEADER + GEN_DATE
    if data[:4] != b"MADP" or not channels or len(data) < blocks_at + CHANNEL_BLOCK * channels or \
            struct.unpack_from("<I", data, WAVE_HEADER_END)[0] != blocks_at + CHANNEL_BLOCK * channels:
        raise ValueError("not a MH Generations wave")
    start = struct.unpack_from("<I", data, blocks_at)[0]
    end = WAVE_HEADER + CHANNEL_BLOCK * channels
    new_start = (end + WAVE_ALIGN - 1) & ~(WAVE_ALIGN - 1)
    out = bytearray(data[:WAVE_HEADER] + data[blocks_at:blocks_at + CHANNEL_BLOCK * channels])
    struct.pack_into("<I", out, WAVE_HEADER_END, end)
    for channel in range(channels):
        at = WAVE_HEADER + CHANNEL_BLOCK * channel
        struct.pack_into("<I", out, at, new_start + struct.unpack_from("<I", out, at)[0] - start)
    return bytes(out + bytes(new_start - end) + data[start:])


def _bank_entry(gen: bytes) -> bytes:
    entry = bytearray(gen[:0x0B] + b"\x00" + gen[0x47:0x4A] + gen[0x0B:0x44] + bytes(4))
    entry[2] = BANK_ENTRY_FLAG
    return bytes(entry)


def _group_flags_at(groups: int) -> list[int]:
    """Where each group descriptor keeps its flags: the first in the header, the others after it."""
    return [BANK_FLAGS_AT] + [BANK_HEADER + GROUP * i - GROUP + GROUP_FLAGS for i in range(1, groups)]


def bank_flags(data: bytes) -> tuple[int, ...]:
    """The flags of each group of MH4U's SNDB `data`."""
    if data[:4] != b"SNDB" or len(data) < BANK_HEADER:
        return ()
    groups = min(struct.unpack_from("<I", data, BANK_GROUPS)[0], (len(data) - BANK_HEADER) // GROUP + 1)
    return tuple(data[at] for at in _group_flags_at(groups))


def convert_bank(data: bytes, rename, flags: tuple[int, ...] = (BANK_FLAGS,)) -> bytes:
    """MHGen's SBKR `data` as MH4U's SNDB, its wave paths renamed with `rename`, with `flags` for its groups (the
    last for those past them)."""
    if data[:4] != b"SBKR" or len(data) < BANK_HEADER:
        raise ValueError("not a MH Generations sound bank")
    groups = struct.unpack_from("<I", data, BANK_GROUPS)[0]
    at = BANK_HEADER + GROUP * (groups - 1)
    if not groups or len(data) < at:
        raise ValueError("a sound bank of another layout")
    out = bytearray(b"SNDB" + struct.pack("<I", BANK_VERSION) + data[8:at])
    for group, flags_at in enumerate(_group_flags_at(groups)):
        out[flags_at] = flags[min(group, len(flags) - 1)]
    for _ in range(struct.unpack_from("<I", data, 0x0C)[0]):
        end = data.find(b"\x00", at)
        if end < 0 or end + 5 + BANK_ENTRY > len(data):
            raise ValueError("a sound bank entry past the end")
        type_hash = struct.unpack_from("<I", data, end + 1)[0]
        out += (rename(data[at:end].decode("ascii")).encode("ascii") + b"\x00"
                + struct.pack("<I", WAVE if type_hash == GEN_WAVE else type_hash)
                + _bank_entry(data[end + 5:end + 5 + BANK_ENTRY]))
        at = end + 5 + BANK_ENTRY
    if len(data) - at != BANK_TRAILER * groups:
        raise ValueError("a sound bank of another layout")
    for trailer in range(at, len(data), BANK_TRAILER):
        out += data[trailer:trailer + 5] + bytes(BANK_TRAILER - 5)  # a float, the group; MHGen fills 0xCD after
    return bytes(out)


def convert_requests(data: bytes, rename, copies: dict[int, int] | None = None) -> bytes:
    """MHGen's SRQR `data` as MH4U's SREQ, its bank path renamed with `rename`; each id of `copies` it lacks gets
    a copy of the record of the id it names."""
    if data[:4] != b"SRQR" or len(data) < REQUEST_HEADER:
        raise ValueError("not a MH Generations sound request list")
    count, table_end = struct.unpack_from("<II", data, 8)
    if table_end != REQUEST_HEADER + count * GEN_REQUEST or table_end + 4 > len(data):
        raise ValueError("a sound request list of another layout")
    records = {}
    for i in range(count):
        record = data[REQUEST_HEADER + i * GEN_REQUEST:][:REQUEST_SHARED]
        records.setdefault(struct.unpack_from("<H", record)[0], record)
    for new, source in (copies or {}).items():
        if new not in records and source in records:
            records[new] = struct.pack("<H", new) + records[source][2:]
    path_at = struct.unpack_from("<I", data, table_end)[0]
    path_end = data.find(b"\x00", path_at)
    if path_end < 0:
        raise ValueError("a sound request list without its bank")
    end = REQUEST_HEADER + len(records) * REQUEST
    out = bytearray(b"SREQ" + struct.pack("<III", REQUEST_VERSION, len(records), end))
    for _, record in sorted(records.items()):
        out += record + bytes(REQUEST - REQUEST_SHARED)
    return bytes(out + struct.pack("<I", end + 4) + rename(data[path_at:path_end].decode("ascii")).encode("ascii")
                 + b"\x00")


def _kind(name: str) -> str:
    """A bank's kind: its name without the model (snd_wp_two, snd_wp_hbgB, snd_wp_hbgSF)."""
    return re.sub(r"\d", "", name.split("\\")[-1])


def weapon_sounds(source: Arc, cls: str, model: int, new_model: int, donor: Arc | None = None) -> list[ArcEntry]:
    """MHGen's sound archive `source` of `cls` model `model` as MH4U sound entries at model `new_model`, each
    bank with the flags of the bank of its kind in MH4U weapon archive `donor`. ValueError when an entry does
    not convert."""
    rename = sound_renamer(cls, model, new_model)
    flags = {_kind(e.name): bank_flags(e.data) for e in (donor.entries if donor else ()) if e.type_hash == SOUND_BANK}
    out = []
    for e in source.entries:
        if e.type_hash == GEN_WAVE:
            out.append(ArcEntry(rename(e.name), WAVE, convert_wave(e.data)))
        elif e.type_hash == GEN_BANK:
            out.append(ArcEntry(rename(e.name), SOUND_BANK,
                                convert_bank(e.data, rename, flags.get(_kind(e.name)) or (BANK_FLAGS,))))
        elif e.type_hash == GEN_REQUESTS:
            out.append(ArcEntry(rename(e.name), SOUND_REQUEST,
                                convert_requests(e.data, rename, REQUEST_COPIES.get(_kind(e.name)))))
        else:
            raise ValueError(f"a sound entry of unknown type {e.type_hash:#010x}: {e.name}")
    return out
