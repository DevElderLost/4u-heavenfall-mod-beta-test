"""What MH4U's executable needs for the pack's models (the tables).

* Gimmick donors: every per-model table of a weapon's moving parts reads one copy of the model, set by
  FUN_002d6d80. The gimmick_donor hook (asm/gimmick_donor.s) puts there, for a pack weapon, a MH4U model of its
  class with the same gimmick type in MHGen's `pwl` (donor_table: a byte per equipment type and model).
* Weapon effects: the Gunlance and Insect Glaive keep 3 bytes per model (EFFECT_TABLES), MHGen's `pwl` +0x0C;
  they move to the extension with the pack's entries.
* Hair under helms: a u32 per helm model and gender (HAIR_TABLES), moved to the extension. A pack helm shows the
  hair MHGen shows under it per hairstyle (`rPlayerPartsDisp`; both games have the same hair models), with the
  other groups of the MH4U helm whose flags are nearest; when that differs by hairstyle, the value indexes a row
  of hair_rows, placed in the extension on the grid of the game's rows (HAIR_ROWS).
* Sounds: a weapon plays the sounds of a number its class's table gives its model; a pack weapon gets its own id
  (own_sound_numbers inside the tables, the sound_number hooks past them: asm/sound_number.s), the number its
  sounds are named with (equipment_pack.weapon_arc).
* Armor movement sounds: a byte per armor model, gender and part (ARMOR_SOUND_POINTERS), moved to the extension
  with MHGen's own value for each pack piece (mhgen_armor_sounds) and their readers' bounds raised.
* Cloth: equipment_pack's moved cloth tables.

executable_needs() reads all of it from the games (cacheable with the plan); patch_executable() writes it.
"""

import re
import struct
from collections import Counter
from dataclasses import dataclass, field

from core.game.files.arc import Arc, parse_arc
from core.game.executable.code_space import COND_HI, Layout, load_layout
from core.equipment.mhgen import convert
from core.equipment.mhgen import equipment_pack as pack
from core.equipment.mhgen.equipment_pack import CLOTH_IDS, WEAPON_FOLDERS, WEAPON_IDS

CODE_BASE = 0x100000
PWL = 0x540D49C1  # weapon\wNN\pwl\pl_wNN in loc/arc/resident.arc: u32 0x40000000, u32 count, 16 bytes per model
PWL_HEADER = 8
PWL_RECORD = 16
GIMMICK = slice(0, 4)   # the gimmick type (the first byte) and its motion list
EFFECT = slice(12, 15)  # the Gunlance's and Insect Glaive's effect bytes
# The classes in equipment type order, 7 to 20 (the byte the gimmick_donor hook reads from the equipment reference).
EQUIPMENT_CLASSES = ("two", "one", "ham", "lan", "lbg", "hbg", "swo", "axe", "gun", "bow", "sou", "hue", "rod",
                     "gaxe")

# The hook: FUN_002d6d80 at `cpy r1, r0` (the model from FUN_002f0fd4; r5 = the equipment reference), before
# `b FUN_00354530` stores r1 as the gimmick's model.
GIMMICK_HOOK = 0x2D6DAC
GIMMICK_HOOK_ORIGINAL = bytes.fromhex("0010a0e1")  # cpy r1, r0


@dataclass(frozen=True)
class EffectTable:
    address: int
    entries: int                # the class's last model + 1
    literals: tuple[int, ...]   # every literal word its readers load it from


EFFECT_SIZE = 3
EFFECT_TABLES = {
    "gun": EffectTable(0xE103AC, 115, (0xCB0630, 0xCB09BC, 0xCB1190, 0xCB204C, 0xCB2C94)),
    "rod": EffectTable(0xDF916C, 72, (0xC51008, 0xCBE154, 0xCBFAA8, 0xCBFDF0, 0xCC05DC)),
}

# Sound numbers: FUN_0030d08c (the only reader) plays a weapon's sounds of number table[model], a byte per model
# (0xFF: none) in a table per class, the bowguns' SF banks in tables of their own; each table holds the models up
# to the class's bound. A u32 per class number (MHGen's wNN) at each: the table's address, its bound.
SOUND_TABLES, SOUND_BOUNDS = 0xFCD450, 0xE08424
SF_SOUND_TABLES, SF_SOUND_BOUNDS = 0xFCD490, 0xE08464
SOUND_CLASSES = {cls: int(folder[1:]) for folder, cls in WEAPON_FOLDERS.items()}
NO_SOUND = 0xFF
# The sound_number hooks: each lookup's `bhi` past it (to 0x30D740), pointed at a label of the block instead.
SOUND_HOOKS = ((0x30D324, bytes.fromhex("0501008a"), "_start"), (0x30D3D8, bytes.fromhex("d800008a"), "sf"))

# Armor movement sounds: a signed byte per armor model, N plays snd_pl_arm_N (0: none), in a table per gender and
# part. Pointers at ARMOR_SOUND_POINTERS, ARMOR_SOUND_GENDER bytes per gender: body, arms, waist, legs (helms
# none). Its readers (FUN_0030d08c, FUN_0030a174, FUN_002fb184) skip models from the bound in
# their literals at ARMOR_SOUND_BOUNDS on.
ARMOR_SOUND_POINTERS = 0xFCD4D0
ARMOR_SOUND_GENDER = 0x18
ARMOR_SOUND_PARTS = ("body", "arm", "wst", "leg")
ARMOR_SOUND_BOUNDS = (0x2FB1B0, 0x30A8DC, 0x30D938)
ARMOR_SOUND_SIZE = 582  # models 0-581
ARMOR_SOUND_IDS = CLOTH_IDS
# MHGen's in loc/arc/resident.arc: table\armorSeriesData, a record per armor series (all its parts and both
# genders) with its model at SERIES_MODEL and per gender 3 bytes at SERIES_SOUND: its own sound, then whether
# instead its row of table\armorSeData gives one per part, and that row (helm, body, arms, waist, legs).
SERIES_TYPE, SE_TYPE = 0x7896B60A, 0x017CA1B2
MHGEN_TABLE_HEADER = 8  # u32 version, u32 count
SERIES_RECORD = 126
SERIES_MODEL = 11
SERIES_SOUND = {"m": 119, "f": 122}
SE_RECORD = 5
SE_PARTS = ("helm", "body", "arm", "wst", "leg")

HAIR_TABLES = {"m": 0x100CA20, "f": 0x100D33C}
HAIR_LITERALS = {"m": 0xB0B5D8, "f": 0xB0B5DC}  # FUN_00b0b448, the only reader
HAIR_TABLE_SIZE = 583  # helms 0-582
HAIR_IDS = CLOTH_IDS    # entries of the moved tables, as the moved cloth tables
# A value with PER_HAIRSTYLE set is an index i into rows of HAIRSTYLES u32 at HAIR_ROWS + (i - 1) * HAIR_ROW
# (literal 0xB0B5E0, left in place: an index up to 0x7FFF reaches the extension).
PER_HAIRSTYLE = 0x8000
HAIR_ROWS = 0x100DC58
HAIR_ROW = 0x70
HAIRSTYLES = 28
HAIR_GROUPS = 0x3FF      # bits 0-9: the hair model's mesh groups shown
OTHER_GROUPS = 0x7F0000  # bits 16-22: the other groups (kept from the donor helm)
HAIR_ROW_ROOM = 224      # rows of the hair_rows block (game/executable/blocks.py): 214 used by XX's whole pack
MESH_GROUP = 4           # a MOD mesh's group, a byte
MH4U_HAIR = re.compile(r"data/pl_([mf])_hair(\d{3})\.arc")
FIRST_HAIR_OBJECT = 2    # MHGen's parts display object of hairstyle 0; one per hairstyle after it
_HAIR_ENTRY = re.compile(rb"\x05\x00(..)\x10\x00\x00\x00\x01\x00\x00\x00(..)\x01\x00\x00\x00(..)", re.S)
HairFlags = dict[int, tuple[int, int]]  # MHGen parts display object -> (mDispFlag0, mDispFlag1)


@dataclass(frozen=True)
class ExecutableNeeds:
    donors: dict[tuple[str, int], int]        # (class, pack weapon) -> MH4U model with its gimmick
    effects: dict[tuple[str, int], bytes]     # (class, pack Gunlance or Insect Glaive) -> its `pwl` effect bytes
    hair: dict[tuple[str, int], int]          # (gender, pack helm) -> MH4U helm with the nearest hair flags
    cloth: dict[tuple[str, str, int], int]    # (gender, part, pack model) -> cloth bits (equipment_pack)
    # (gender, pack helm) -> per MH4U hairstyle, the hair groups MHGen shows (shown_hair)
    hair_shown: dict[tuple[str, int], tuple[int, ...]] = field(default_factory=dict)
    # (gender, part, pack model) -> its movement sound (mhgen_armor_sounds), parts of ARMOR_SOUND_PARTS
    armor_sounds: dict[tuple[str, str, int], int] = field(default_factory=dict)


def pwl_records(resident: Arc) -> dict[str, list[bytes]]:
    """MHGen's `pwl` records per class (MH4U's class names), from loc/arc/resident.arc."""
    out = {}
    for entry in resident.entries:
        folder = entry.name.rsplit("_", 1)[-1]
        if entry.type_hash == PWL and folder in WEAPON_FOLDERS:
            count = struct.unpack_from("<I", entry.data, 4)[0]
            out[WEAPON_FOLDERS[folder]] = [entry.data[PWL_HEADER + PWL_RECORD * i:PWL_HEADER + PWL_RECORD * (i + 1)]
                                           for i in range(count)]
    return out


def gimmick_donor(records: list[bytes], source: int, models: set[int]) -> int | None:
    """The MH4U model (one of `models`, those with a file) whose `pwl` record has the gimmick bytes of MHGen's
    `source`, and of those the most other bytes alike, then the lowest; None if no model has that gimmick or
    `source` has no record."""
    if not 0 <= source < len(records):
        return None
    want = records[source]
    alike = [(sum(a == b for a, b in zip(records[m], want)), -m) for m in models
             if 0 < m < len(records) and records[m][GIMMICK] == want[GIMMICK]]
    return -max(alike)[1] if alike else None


def static_donor(records: list[bytes], source: int, models: set[int]) -> int | None:
    """The MH4U model (one of `models`) with no moving parts (gimmick bytes all zero) whose `pwl` record has the
    most other bytes like MHGen's `source`, then the lowest: the donor of a weapon whose gimmick type MH4U lacks
    (gimmick_donor is None), which then stands still. None if `source` has no record or no model is static."""
    if not 0 <= source < len(records):
        return None
    want = records[source]
    alike = [(sum(a == b for a, b in zip(records[m][4:], want[4:])), -m) for m in models
             if 0 < m < len(records) and not any(records[m][GIMMICK])]
    return -max(alike)[1] if alike else None


def gimmickless(records: dict[str, list[bytes]], gen: pack.Signatures, m4: pack.Signatures) -> set[tuple[str, int]]:
    """MHGen's weapons (class, model; those of `gen`, its signatures) with no gimmick donor: their moving parts
    need motions MH4U lacks, or their type is unknown, so the pack leaves them out (`m4`: MH4U's signatures,
    which models have a file)."""
    return {(cls, model) for cls in WEAPON_FOLDERS.values() for model in gen.get((cls,), {})
            if gimmick_donor(records.get(cls, []), model, set(m4.get((cls,), {}))) is None}


def executable_needs(plan, records: dict[str, list[bytes]], m4: pack.Signatures,
                     hair: dict[tuple[str, int], HairFlags], cloth: dict[tuple[str, str, int], int],
                     groups: dict[tuple[str, int], int] | None = None,
                     sounds: dict[tuple[str, str, int], int] | None = None) -> ExecutableNeeds:
    """What patch_executable writes for `plan` (equipment_pack.plan_pack): MHGen's `pwl` `records`, MH4U's
    signatures `m4`, MHGen's hair flags of every helm `hair` ((gender, model) -> flags), the cloth bits
    write_pack returned, MH4U's hair groups (hair_groups; without them, pack helms show their donors' hair) and
    MHGen's armor sounds (mhgen_armor_sounds; without them, pack armor is silent)."""
    donors, effects, hair_donors, shown = {}, {}, {}, {}
    armor_sounds = {(g, p.slot, p.model): sounds[(g, p.slot, p.source)] for p in plan for g in pack.GENDERS
                    if (g, p.slot, p.source) in (sounds or {})}
    if sounds is not None:
        # MH4U's tables hold sounds for numbers no armor uses; a pack piece placed there with none of its own (0 in
        # XX's data) must not play that leftover (it was Zinogre's chain on Booyah's waist)
        for p in plan:
            if p.slot in ARMOR_SOUND_PARTS and p.model < ARMOR_SOUND_SIZE:
                for g in pack.GENDERS:
                    armor_sounds.setdefault((g, p.slot, p.model), 0)
    shared = {g: {model: flags for (gg, model), flags in hair.items()
                  if gg == g and model < HAIR_TABLE_SIZE and model in m4.get((g, "helm"), {})} for g in pack.GENDERS}
    indexes = {g: HairIndex(helms) for g, helms in shared.items() if helms}
    for p in plan:
        if p.slot in WEAPON_FOLDERS.values():
            donor = gimmick_donor(records[p.slot], p.source, set(m4.get((p.slot,), {})))
            if donor is None:
                raise ValueError(f"{p.slot} {p.source} has no gimmick donor: leave it out of the plan (gimmickless)")
            donors[(p.slot, p.model)] = donor
            if p.slot in EFFECT_TABLES:
                effects[(p.slot, p.model)] = records[p.slot][p.source][EFFECT]
        elif p.slot == "helm":
            for g in pack.GENDERS:
                if (g, p.source) in hair and g in indexes:
                    hair_donors[(g, p.model)] = indexes[g].donor(hair[(g, p.source)])
                    if groups is not None:
                        shown[(g, p.model)] = shown_hair(hair[(g, p.source)], groups, g)
    return ExecutableNeeds(donors, effects, hair_donors, dict(cloth), shown, armor_sounds)


def donor_table(donors: dict[tuple[str, int], int]) -> bytes:
    """The gimmick_donor hook's data: a byte per equipment type (EQUIPMENT_CLASSES) and model, the donor, or 0
    for a model that keeps its own id."""
    out = bytearray(len(EQUIPMENT_CLASSES) * WEAPON_IDS)
    for (cls, model), donor in donors.items():
        if not 0 <= model < WEAPON_IDS or not 0 < donor < 256:
            raise ValueError(f"{cls} {model}: the donor table holds models below {WEAPON_IDS} and donors 1-255")
        out[EQUIPMENT_CLASSES.index(cls) * WEAPON_IDS + model] = donor
    return bytes(out)


def game_effect_table(code: bytes, cls: str) -> bytes:
    """The game's effect table of `cls` (EFFECT_TABLES)."""
    table = EFFECT_TABLES[cls]
    return code[table.address - CODE_BASE:table.address - CODE_BASE + EFFECT_SIZE * table.entries]


def moved_effect_table(game: bytes, cls: str, effects: dict[tuple[str, int], bytes],
                       donors: dict[tuple[str, int], int]) -> bytes:
    """The effect table of `cls` for WEAPON_IDS models: the game's entries (`game`), then for each pack weapon of
    the class its `pwl` bytes, or its donor's entry when a byte is past the largest the game uses in that column
    (its records may end there)."""
    out = bytearray(EFFECT_SIZE * WEAPON_IDS)
    out[:len(game)] = game
    largest = [max(game[k::EFFECT_SIZE]) for k in range(EFFECT_SIZE)]
    for (c, model), own in effects.items():
        if c != cls:
            continue
        if not all(b <= top for b, top in zip(own, largest)):
            donor = donors[(cls, model)]
            own = game[EFFECT_SIZE * donor:EFFECT_SIZE * (donor + 1)]
        out[EFFECT_SIZE * model:EFFECT_SIZE * (model + 1)] = own
    return bytes(out)


def _sound_table_at(code: bytes, pointers: int, bounds: int, number: int) -> tuple[int, int]:
    address, bound = (struct.unpack_from("<I", code, at + 4 * number - CODE_BASE)[0] for at in (pointers, bounds))
    return address, bound


def game_sound_table(code: bytes, pointers: int, bounds: int, number: int) -> bytes:
    """The sound numbers of class `number` (SOUND_CLASSES) in the table at `pointers` with its bound at `bounds`
    (SOUND_TABLES or SF_SOUND_TABLES); empty when the class has none."""
    address, bound = _sound_table_at(code, pointers, bounds, number)
    return code[address - CODE_BASE:address - CODE_BASE + bound + 1] if address else b""


def own_sound_numbers(code: bytes, weapons) -> bytes:
    """`code` where each pack weapon ((class, model) in `weapons`) inside its class's sound tables has its own id
    as sound number (the gaps between MH4U's models hold 0xFF, no sound); the sound_number hooks give it to those
    past them."""
    out = bytearray(code)
    for cls, model in weapons:
        if not 0 <= model < NO_SOUND:
            raise ValueError(f"{cls} {model}: sound numbers are bytes below {NO_SOUND:#x}")
        for pointers, bounds in ((SOUND_TABLES, SOUND_BOUNDS), (SF_SOUND_TABLES, SF_SOUND_BOUNDS)):
            address, bound = _sound_table_at(code, pointers, bounds, SOUND_CLASSES[cls])
            if address and model <= bound:
                out[address + model - CODE_BASE] = model
    return bytes(out)


def repoint(code: bytes, literals: tuple[int, ...], old: int, new: int) -> bytes:
    """`code` with the literal words at `literals`, all `old`, set to `new`. Refuses another executable."""
    out = bytearray(code)
    for at in literals:
        if struct.unpack_from("<I", out, at - CODE_BASE)[0] != old:
            raise ValueError(f"the literal at {at:#x} is not {old:#x}: not the update's executable")
        struct.pack_into("<I", out, at - CODE_BASE, new)
    return bytes(out)


def _mhgen_table(resident: Arc, type_hash: int, size: int) -> list[bytes]:
    data = next(e.data for e in resident.entries if e.type_hash == type_hash)
    count = struct.unpack_from("<I", data, 4)[0]
    return [data[MHGEN_TABLE_HEADER + size * i:MHGEN_TABLE_HEADER + size * (i + 1)] for i in range(count)]


def mhgen_armor_sounds(resident: Arc, series_size: int = SERIES_RECORD,
                       series_shift: int = 0) -> dict[tuple[str, str, int], int]:
    """MHGen's movement sound of each armor model ((gender, part, model) -> N of snd_pl_arm_N; parts of
    ARMOR_SOUND_PARTS, none for no sound) from its loc/arc/resident.arc. A model several series share takes the
    sound most of them give (the first series' on a tie). MH XX's table (arc/resident.arc) has the same layout
    with a record one byte longer from +105 (gear_data.XX_FORMAT: `series_size` 127, `series_shift` 1)."""
    rows = _mhgen_table(resident, SE_TYPE, SE_RECORD)
    votes: dict[tuple[str, str, int], Counter] = {}
    for record in _mhgen_table(resident, SERIES_TYPE, series_size):
        model = struct.unpack_from("<H", record, SERIES_MODEL)[0]
        for gender, at in SERIES_SOUND.items():
            at += series_shift
            own, from_row, row = record[at:at + 3]
            for part in ARMOR_SOUND_PARTS:
                sound = rows[row][SE_PARTS.index(part)] if from_row else own
                votes.setdefault((gender, part, model), Counter())[sound] += 1
    return {key: sound for key, counts in votes.items() if (sound := counts.most_common(1)[0][0])}


def _armor_sound_pointer(gender: str, part: str) -> int:
    return ARMOR_SOUND_POINTERS + pack.GENDERS.index(gender) * ARMOR_SOUND_GENDER + 4 * ARMOR_SOUND_PARTS.index(part)


def game_armor_sound_table(code: bytes, gender: str, part: str) -> bytes:
    """The game's movement sounds of `gender`'s `part` (ARMOR_SOUND_PARTS), a byte per model."""
    address = struct.unpack_from("<I", code, _armor_sound_pointer(gender, part) - CODE_BASE)[0]
    return code[address - CODE_BASE:address - CODE_BASE + ARMOR_SOUND_SIZE]


def moved_armor_sound_tables(code: bytes, sounds: dict[tuple[str, str, int], int]) -> bytes:
    """The male then the female tables of the movement sounds per part (ARMOR_SOUND_PARTS), ARMOR_SOUND_IDS bytes
    each: the game's, zeros after, and `sounds` ((gender, part, model) -> sound)."""
    out = bytearray()
    for gender in pack.GENDERS:
        for part in ARMOR_SOUND_PARTS:
            table = bytearray(game_armor_sound_table(code, gender, part)) + bytes(ARMOR_SOUND_IDS - ARMOR_SOUND_SIZE)
            for (g, p, model), sound in sounds.items():
                if (g, p) == (gender, part):
                    if not 0 <= model < ARMOR_SOUND_IDS or not 0 <= sound < 0x80:
                        raise ValueError(f"{gender} {part} {model}: sound {sound} does not fit the moved tables")
                    table[model] = sound
            out += table
    return bytes(out)


def repoint_armor_sound_tables(code: bytes, address: int) -> bytes:
    """`code` with the armor sound tables' pointers at moved_armor_sound_tables placed at `address` and their
    readers' bound raised to ARMOR_SOUND_IDS. Refuses another executable."""
    out = bytearray(repoint(code, ARMOR_SOUND_BOUNDS, ARMOR_SOUND_SIZE, ARMOR_SOUND_IDS))
    for i, (gender, part) in enumerate((g, p) for g in pack.GENDERS for p in ARMOR_SOUND_PARTS):
        struct.pack_into("<I", out, _armor_sound_pointer(gender, part) - CODE_BASE, address + i * ARMOR_SOUND_IDS)
    return bytes(out)


def hair_flags(arc: Arc) -> HairFlags | None:
    """MHGen's hair flags per hairstyle of a helm archive (its rPlayerPartsDisp), or None without one."""
    for entry in arc.entries:
        if entry.type_hash == convert.PARTS_DISP:
            return {struct.unpack("<H", index)[0]: (struct.unpack("<H", f0)[0], struct.unpack("<H", f1)[0])
                    for index, f0, f1 in _HAIR_ENTRY.findall(entry.data)}
    return None


class HairIndex:
    """`shared` (MH4U helms with their MHGen flags) packed for hair_donor: per helm one int holding 32 bits per
    display object any of them has (flag 0 | flag 1 << 16), all ones for an object the helm lacks. An object only
    the asked flags have differs from every helm alike, so it cannot change the donor and is left out."""

    def __init__(self, shared: dict[int, HairFlags]):
        objects = sorted(set().union(*shared.values()))
        self._shift = {obj: 32 * i for i, obj in enumerate(objects)}
        self._full = (1 << 32 * len(objects)) - 1
        self._helms = [(helm, self._pack(shared[helm])) for helm in sorted(shared)]

    def _pack(self, flags: HairFlags) -> int:
        out = self._full
        for obj, (f0, f1) in flags.items():
            shift = self._shift.get(obj)
            if shift is not None:
                out ^= (0xFFFFFFFF ^ (f0 | f1 << 16)) << shift
        return out

    def donor(self, flags: HairFlags) -> int:
        """The helm whose flags differ from `flags` in the fewest bits, the lowest on a tie."""
        wanted = self._pack(flags)
        return min(self._helms, key=lambda helm: ((helm[1] ^ wanted).bit_count(), helm[0]))[0]


def hair_donor(flags: HairFlags, shared: dict[int, HairFlags]) -> int:
    """The helm of `shared` (MH4U helms with their MHGen flags) whose flags differ from `flags` in the fewest
    bits, the lowest on a tie (HairIndex: build one for many questions)."""
    return HairIndex(shared).donor(flags)


def hair_groups(m4) -> dict[tuple[str, int], int]:
    """The mesh groups (bits 0-9) of each MH4U hair model ((gender, hairstyle) -> bits), from its romfs `m4`."""
    out = {}
    for path in m4.walk():
        if match := MH4U_HAIR.fullmatch(path):
            for entry in parse_arc(m4.read(path)).entries:
                if entry.type_hash == convert.MOD:
                    data = entry.data
                    meshes = struct.unpack_from("<I", data, convert.MOD_MESHES)[0]
                    found = (data[meshes + convert.MESH_SIZE * i + MESH_GROUP]
                             for i in range(struct.unpack_from("<H", data, convert.MOD_MESH_COUNT)[0]))
                    out[(match[1], int(match[2]))] = sum({1 << group for group in found if 1 << group & HAIR_GROUPS})
    return out


def shown_hair(flags: HairFlags, groups: dict[tuple[str, int], int], gender: str) -> tuple[int, ...]:
    """The hair groups MHGen's `flags` show per MH4U hairstyle (MHGen's object FIRST_HAIR_OBJECT + hairstyle;
    both games have the same hair models), among those the hairstyle has (`groups`, all for one without). One
    value for all when one fits every hairstyle."""
    wanted = [flags.get(FIRST_HAIR_OBJECT + h, (0xFFFF, 0xFFFF))[0] & HAIR_GROUPS for h in range(HAIRSTYLES)]
    has = [groups.get((gender, h), HAIR_GROUPS) for h in range(HAIRSTYLES)]
    every = 0
    for bits in wanted:
        every |= bits
    if all(every & h == bits & h for bits, h in zip(wanted, has)):
        return (every,) * HAIRSTYLES
    return tuple(bits & h for bits, h in zip(wanted, has))


def _game_hair_value(code: bytes, gender: str, helm: int) -> int:
    return struct.unpack_from("<I", code, HAIR_TABLES[gender] + 4 * helm - CODE_BASE)[0]


def _game_hair_row(code: bytes, gender: str, helm: int) -> list[int]:
    """The game's hair value of `helm` per hairstyle."""
    value = _game_hair_value(code, gender, helm)
    if not value & PER_HAIRSTYLE:
        return [value] * HAIRSTYLES
    at = HAIR_ROWS + ((value & 0x7FFF) - 1) * HAIR_ROW - CODE_BASE
    return list(struct.unpack_from(f"<{HAIRSTYLES}I", code, at))


def hair_entries(code: bytes, donors: dict[tuple[str, int], int], shown: dict[tuple[str, int], tuple[int, ...]],
                 rows_at: int, room: int = HAIR_ROW_ROOM) -> tuple[dict[tuple[str, int], int], bytes]:
    """The hair value of each pack helm (`donors`: (gender, model) -> donor helm) and the hair_rows block placed at
    `rows_at`, with room for `room` rows. A helm shows the hair of `shown` with its donor's other groups: one value
    when that is the same in every hairstyle, else the index of a row on the game's grid (shared by helms alike).
    Without `shown`, or once the rows are full, a helm takes its donor's value."""
    first = rows_at + (HAIR_ROWS - rows_at) % HAIR_ROW
    rows: dict[tuple[int, ...], int] = {}
    values = {}
    for key in sorted(donors):
        gender, donor = key[0], donors[key]
        row = (tuple(other & OTHER_GROUPS | hair for other, hair in zip(_game_hair_row(code, gender, donor),
                                                                        shown[key])) if key in shown else ())
        if len(set(row)) == 1:
            values[key] = row[0]
        elif row and (row in rows or len(rows) < room):
            values[key] = PER_HAIRSTYLE | rows.setdefault(row, (first - HAIR_ROWS) // HAIR_ROW + 1 + len(rows))
        else:
            values[key] = _game_hair_value(code, gender, donor)
    if (first - HAIR_ROWS) // HAIR_ROW + room >= PER_HAIRSTYLE:
        raise ValueError("the hair rows are past the index the game can hold")
    block = bytearray(room * HAIR_ROW + HAIR_ROW - 4)
    for row, index in rows.items():
        struct.pack_into(f"<{HAIRSTYLES}I", block, HAIR_ROWS + (index - 1) * HAIR_ROW - rows_at, *row)
    return values, bytes(block)


def moved_hair_tables(code: bytes, values: dict[tuple[str, int], int]) -> bytes:
    """The male then the female hair table, HAIR_IDS u32 each: the game's values, zeros after, and `values`
    ((gender, model) -> value; hair_entries)."""
    out = bytearray()
    for gender in pack.GENDERS:
        at = HAIR_TABLES[gender] - CODE_BASE
        table = list(struct.unpack_from(f"<{HAIR_TABLE_SIZE}I", code, at)) + [0] * (HAIR_IDS - HAIR_TABLE_SIZE)
        for (g, model), value in values.items():
            if g == gender:
                if not 0 <= model < HAIR_IDS:
                    raise ValueError(f"helm {model} is outside the moved hair tables")
                table[model] = value
        out += struct.pack(f"<{HAIR_IDS}I", *table)
    return bytes(out)


def patch_executable(code: bytes, needs: ExecutableNeeds, layout: Layout | None = None, *,
                     scaled: bool = False) -> bytes:
    """`code` (the update's executable) with the gimmick donor hook and the moved effect, hair, armor sound and
    cloth tables for the pack (`needs`). Refuses another executable.

    `scaled` (a pack of a few models, ported_pack.py) patches only what `needs` asks for: no weapons, no donor
    hook, sound number hooks or effect tables; no helms, no hair tables (and no hair rows without a helm whose hair
    differs by hairstyle); no armor, no armor sound tables; cloth bits written into the game's own table when every
    model is inside it. With every kind of model the result is the same as without `scaled`."""
    layout = layout or load_layout()
    out = bytearray(code)
    weapon_classes = {cls for cls, _ in needs.donors}
    if weapon_classes or not scaled:
        layout.place(out, "gimmick_donor")
        layout.place(out, "gimmick_donor_table", donor_table(needs.donors))
        layout.hook(out, GIMMICK_HOOK, "gimmick_donor", original=GIMMICK_HOOK_ORIGINAL)
        layout.place(out, "sound_number")
        for at, original, label in SOUND_HOOKS:
            target = layout.address("sound_number") if label == "_start" else layout.symbol("sound_number", label)
            layout.hook(out, at, target, original=original, link=False, cond=COND_HI)
        out = bytearray(own_sound_numbers(bytes(out), needs.donors))
    for cls, table in EFFECT_TABLES.items():
        if scaled and cls not in weapon_classes:
            continue
        block = f"{cls}_effects"
        layout.place(out, block, moved_effect_table(game_effect_table(code, cls), cls, needs.effects, needs.donors))
        out = bytearray(repoint(bytes(out), table.literals, table.address, layout.address(block)))
    if needs.hair or not scaled:
        values, rows = hair_entries(code, needs.hair, needs.hair_shown, layout.address("hair_rows"))
        if not scaled or any(value & PER_HAIRSTYLE for value in values.values()):
            layout.place(out, "hair_rows", rows)
        layout.place(out, "hair_tables", moved_hair_tables(code, values))
        for i, gender in enumerate(pack.GENDERS):
            out = bytearray(repoint(bytes(out), (HAIR_LITERALS[gender],), HAIR_TABLES[gender],
                                    layout.address("hair_tables") + 4 * HAIR_IDS * i))
    if needs.armor_sounds or not scaled:
        layout.place(out, "armor_sound_tables", moved_armor_sound_tables(code, needs.armor_sounds))
        out = bytearray(repoint_armor_sound_tables(bytes(out), layout.address("armor_sound_tables")))
    if scaled and all(model < pack.CLOTH_TABLE_SIZE for _, _, model in needs.cloth):
        for (gender, part, model), bits in needs.cloth.items():
            out = bytearray(pack.set_cloth_flags(bytes(out), gender, part, model, bits))
        return bytes(out)
    layout.place(out, "cloth_tables", pack.moved_cloth_tables(code, needs.cloth))
    return pack.repoint_cloth_tables(bytes(out), layout.address("cloth_tables"))


def mhgen_hair_flags(gen) -> dict[tuple[str, int], HairFlags]:
    """The hair flags of every MHGen helm ((gender, model) -> flags) in `gen`, a RomFS."""
    out = {}
    for path in gen.walk():
        match = pack.MHGEN_ARMOR.fullmatch(path)
        if match and match[3] == "helm" and (flags := hair_flags(parse_arc(gen.read(path)))) is not None:
            out[(match[1], int(match[2]))] = flags
    return out
