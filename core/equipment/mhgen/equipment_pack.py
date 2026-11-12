"""MH Generations' weapon and armor models as MH4U archives.

MHGen keeps MH4U's model numbers and adds its own after them. An armor archive
(`arc/player/com/<gender>/NNN/<part>.arc`) already names its files as MH4U does
(`player\\mod\\m\\plNNN\\m_helmNNN`); a weapon archive (`arc/weapon/wNN/NNN.arc`) names its folder by class
number (`weapon\\w00\\two001\\`) where MH4U uses the class name (`weapon\\two\\two001\\`) and carries no
sounds, which MH4U loads from the model archive (`sound\\se\\pl\\wp\\two\\001\\snd_wp_two001`): a packed weapon
gets MHGen's own (`arc/weapon/wNN/snd/NNN.arc`, converted by sound.py) or, without them, a MH4U donor's.

MH4U loads a part's cloth physics (CTC, and CCL for helms) only when a per-model byte table says the model
has them (CLOTH_TABLES, read by FUN_00af7a88, FUN_00af7724 and FUN_00af76bc).
"""

import hashlib
import json
import re
import struct
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.game.files.arc import Arc, ArcEntry, parse_arc, write_arc
from core.equipment.mhgen import convert
from core.equipment.mhgen.felyne_face import hide_additive
from core.equipment.mhgen.sound import SOUND_TYPES, sound_renamer, weapon_sounds as own_weapon_sounds

SHADER_PACKAGE = "system/ltshader/LtShaderPackage.lfx"  # both games' (convert.shader_records)
GENDERS = "mf"
FALLBACK_MODEL = 1  # the MH4U model a piece that has no model of its own wears (every class and part has it)
ARMOR_PARTS = ("helm", "body", "arm", "wst", "leg")
# MHGen's weapon folders (the class numbers of both executables) -> MH4U's class names.
WEAPON_FOLDERS = {"w00": "two", "w01": "one", "w02": "ham", "w03": "lan", "w04": "hbg", "w06": "lbg",
                  "w07": "swo", "w08": "axe", "w09": "gun", "w10": "bow", "w11": "sou", "w12": "hue",
                  "w13": "rod", "w14": "gaxe"}
# The randomizer's weapon class keys (equipment/tables/layout.py) -> MHGen's folders.
CLASS_FOLDERS = {"great_sword": "w00", "sword_and_shield": "w01", "hammer": "w02", "lance": "w03",
                 "heavy_bowgun": "w04", "light_bowgun": "w06", "long_sword": "w07", "switch_axe": "w08",
                 "gunlance": "w09", "bow": "w10", "dual_blades": "w11", "hunting_horn": "w12",
                 "insect_glaive": "w13", "charge_blade": "w14"}

SOUND_PATH = re.compile(rb"sound\\se\\pl\\wp\\[ -~]+?(?=\x00)")

# Per-model cloth flags, one byte per model id and gender (VA in the update; same in the base game).
CLOTH_TABLES = {"m": 0xFB8458, "f": 0xFB86EE}
CLOTH_TABLE_SIZE = 662
# The literal words its three readers load the tables from (FUN_00af7724, FUN_00af76bc, FUN_00af7a88).
CLOTH_LITERALS = {"m": (0xAF771C, 0xAF77B4, 0xAF7EE0), "f": (0xAF7720, 0xAF77B8, 0xAF7EE4)}
# Entries of the moved per-model tables (cloth, hair, movement sounds): MHGen's last armor model is 698, and
# the pack needs about 60 ids past it (helms). Below 1000 (%03d).
CLOTH_IDS = 800
CODE_BASE = 0x100000
CLOTH_BITS = {"body": 0x10, "arm": 0x04, "wst": 0x40, "helm": 0x01, "leg": 0x00}
HELM_COLLISION_BIT = 0x02  # the helm's CCL, loaded only together with its CTC
CLOTH_MASKS = {part: bit | (HELM_COLLISION_BIT if part == "helm" else 0) for part, bit in CLOTH_BITS.items()}


def mhgen_armor_file(gender: str, part: str, model: int) -> str:
    return f"arc/player/com/{gender}/{model:03d}/{part}.arc"


def mhgen_weapon_file(folder: str, model: int) -> str:
    return f"arc/weapon/{folder}/{model:03d}.arc"


def mhgen_sound_file(folder: str, model: int) -> str:
    return f"arc/weapon/{folder}/snd/{model:03d}.arc"


def mh4u_armor_file(gender: str, part: str, model: int) -> str:
    return f"data/pl_{gender}_{part}{model:03d}.arc"


def mh4u_weapon_file(folder: str, model: int) -> str:
    return f"data/pl_{WEAPON_FOLDERS[folder]}{model:03d}.arc"


def _renamed(arc: Arc, rename) -> Arc:
    entries = []
    for entry in arc.entries:
        data = entry.data
        if entry.type_hash == convert.MRL:
            data = convert.rename_mrl_textures(data, rename)
        entries.append(ArcEntry(rename(entry.name), entry.type_hash, data, entry.flags))
    return Arc(version=arc.version, entries=entries)


def armor_arc(source: bytes, source_shaders, target_shaders, gender: str, part: str, model: int,
              new_model: int | None = None) -> Arc:
    """MHGen armor archive `source` (model `model`) as MH4U's, at model `new_model` (default: the same), its
    additive meshes hidden (felyne_face.hide_additive)."""
    arc = convert.convert_arc(parse_arc(source), source_shaders, target_shaders)
    hide_additive(arc, target_shaders[1])
    new_model = model if new_model is None else new_model
    if new_model == model:
        return arc
    folder, new_folder = f"\\pl{model:03d}\\", f"\\pl{new_model:03d}\\"
    leaf, new_leaf = f"{gender}_{part}{model:03d}", f"{gender}_{part}{new_model:03d}"
    return _renamed(arc, lambda path: path.replace(folder, new_folder).replace(leaf, new_leaf))


def _donor_model(sounds: Arc) -> int:
    for entry in sounds.entries:
        if entry.type_hash in SOUND_TYPES:
            match = re.search(r"\\(\d{3})\\", entry.name)
            if match:
                return int(match.group(1))
    raise ValueError("the donor archive has no weapon sounds")


def weapon_sounds(sounds: Arc, cls: str, model: int) -> list[ArcEntry]:
    """The sound entries of a MH4U weapon archive, moved to model `model`: their names and the paths the
    bank and the requests hold (same length, so nothing else moves)."""
    donor = _donor_model(sounds)
    rename = sound_renamer(cls, donor, model)

    def rename_data(match: re.Match) -> bytes:
        renamed = rename(match.group(0).decode("ascii")).encode("ascii")
        assert len(renamed) == len(match.group(0))
        return renamed

    return [ArcEntry(rename(e.name), e.type_hash, SOUND_PATH.sub(rename_data, e.data), e.flags)
            for e in sounds.entries if e.type_hash in SOUND_TYPES]


def weapon_arc(source: bytes, source_shaders, target_shaders, folder: str, model: int,
               sounds: Arc | None = None, new_model: int | None = None, own_sounds: Arc | None = None,
               donor_used: list | None = None) -> Arc:
    """MHGen weapon archive `source` (folder wNN, model `model`) as MH4U's, at model `new_model` (default:
    the same), with its own sounds (`own_sounds`, MHGen's sound archive of the model; sound.weapon_sounds) or,
    without them or when they do not convert, those of MH4U weapon archive `sounds` of the same class
    (`donor_used`, when given, then gets a True appended). Its additive meshes are hidden (felyne_face.hide_additive:
    the white glow over the weapon)."""
    cls = WEAPON_FOLDERS[folder]
    new_model = model if new_model is None else new_model
    old_folder, new_folder = f"weapon\\{folder}\\{cls}{model:03d}\\", f"weapon\\{cls}\\{cls}{new_model:03d}\\"
    number = re.compile(rf"(?<=[a-z]){model:03d}(?=_|$)")

    def rename(path: str) -> str:
        if not path.startswith(old_folder):
            return path
        return new_folder + number.sub(f"{new_model:03d}", path[len(old_folder):])

    arc = _renamed(convert.convert_arc(parse_arc(source), source_shaders, target_shaders), rename)
    hide_additive(arc, target_shaders[1])
    if own_sounds is not None:
        try:
            arc.entries += own_weapon_sounds(own_sounds, cls, model, new_model, sounds)
            return arc
        except ValueError:
            pass  # the donor's then
    if sounds is not None:
        arc.entries += weapon_sounds(sounds, cls, new_model)
        if donor_used is not None:
            donor_used.append(True)
    return arc


def cloth_flags(part: str, arc: Arc) -> int:
    """The bits of the cloth table a part's archive needs: its CTC, and the helm's CCL with it."""
    types = {e.type_hash for e in arc.entries}
    if convert.CTC not in types:
        return 0
    flags = CLOTH_BITS[part]
    if part == "helm" and convert.CCL in types:
        flags |= HELM_COLLISION_BIT
    return flags


def _with_flags(value: int, part: str, flags: int) -> int:
    mask = CLOTH_MASKS[part]
    return (value & ~mask & 0xFF) | (flags & mask)


def set_cloth_flags(code: bytes, gender: str, part: str, model: int, flags: int) -> bytes:
    """`code` (an executable at CODE_BASE) with `part`'s bits of model `model` set to `flags`, in the game's
    own table (models below CLOTH_TABLE_SIZE)."""
    if not 0 <= model < CLOTH_TABLE_SIZE:
        raise ValueError(f"model {model} is outside the cloth table ({CLOTH_TABLE_SIZE} entries)")
    at = CLOTH_TABLES[gender] - CODE_BASE + model
    out = bytearray(code)
    out[at] = _with_flags(out[at], part, flags)
    return bytes(out)


def moved_cloth_tables(code: bytes, flags: dict[tuple[str, str, int], int]) -> bytes:
    """The male then the female cloth table, CLOTH_IDS entries each: the game's entries, then zeros, with
    the bits of `flags` ((gender, part, model) -> bits) set."""
    tables = {}
    for gender, address in CLOTH_TABLES.items():
        start = address - CODE_BASE
        tables[gender] = bytearray(code[start:start + CLOTH_TABLE_SIZE]) + bytes(CLOTH_IDS - CLOTH_TABLE_SIZE)
    for (gender, part, model), bits in flags.items():
        if not 0 <= model < CLOTH_IDS:
            raise ValueError(f"model {model} is outside the moved cloth tables ({CLOTH_IDS} entries)")
        tables[gender][model] = _with_flags(tables[gender][model], part, bits)
    return bytes(tables["m"] + tables["f"])


def repoint_cloth_tables(code: bytes, address: int) -> bytes:
    """`code` with every reader of the cloth tables pointed at moved_cloth_tables placed at `address`.
    Refuses an executable whose literal words are not the game's."""
    out = bytearray(code)
    for gender, literals in CLOTH_LITERALS.items():
        target = address + (CLOTH_IDS if gender == "f" else 0)
        for at in literals:
            current = int.from_bytes(out[at - CODE_BASE:at - CODE_BASE + 4], "little")
            if current != CLOTH_TABLES[gender]:
                raise ValueError(f"{at:#x} holds {current:#x}, not the {gender} cloth table: another executable")
            out[at - CODE_BASE:at - CODE_BASE + 4] = target.to_bytes(4, "little")
    return bytes(out)


# ----- the pack: which MHGen models go in, at which MH4U ids ----------------------------------------------------

WEAPON_IDS = 256  # effect code reads the weapon model as a byte
ARMOR_IDS = CLOTH_IDS  # armor ids index the cloth tables, moved to CLOTH_IDS entries

# slot -> {model id: signature}, a slot being (gender, part) for armor and (class,) for weapons. A signature
# tells models apart (`signature`); None marks a model that does not convert.
Signatures = dict[tuple[str, ...], dict[int, tuple | None]]

PACK_IDS_FILE = CURATED_DIR / "pack_ids.json"
SLOT_ORDER = (*ARMOR_PARTS, *WEAPON_FOLDERS.values())


def parse_ids(text: str) -> dict[int, int]:
    """Source model -> pack id from a row of tokens: "n" and "a-b" are models at their own ids, "s>m" is model s at
    id m."""
    out = {}
    for token in text.split():
        if ">" in token:
            source, model = token.split(">")
            out[int(source)] = int(model)
        else:
            first, _, last = token.partition("-")
            out.update({model: model for model in range(int(first), int(last or first) + 1)})
    return out


def format_ids(ids: Mapping[int, int]) -> str:
    """The row parse_ids reads back: runs of models at their own ids first, then the moved ones, by source."""
    own = sorted(source for source, model in ids.items() if source == model)
    tokens, start = [], 0
    while start < len(own):
        end = start
        while end + 1 < len(own) and own[end + 1] == own[end] + 1:
            end += 1
        tokens.append(str(own[start]) if end == start else f"{own[start]}-{own[end]}")
        start = end + 1
    return " ".join(tokens + [f"{source}>{ids[source]}" for source in sorted(ids) if source != ids[source]])


@dataclass(frozen=True)
class PackIds:
    """The table of ids (game/data/curated/pack_ids.json): `ids` is every (slot, source model) of the pack with the
    MH4U id it is written at, `xx_only` the same for the looks only MH XX has, which the pack carries only where
    `armor_models` (armor model numbers) or `every_xx_only` say so."""
    ids: Mapping[tuple[str, int], int]
    xx_only: Mapping[tuple[str, int], int]
    armor_models: frozenset[int] = frozenset()
    every_xx_only: bool = False

    def in_pack(self, slot: str, source: int) -> bool:
        return (slot, source) in self.ids or self.every_xx_only or (slot in ARMOR_PARTS and source in self.armor_models)

    def listed(self, slot: str) -> dict[int, int]:
        """The sources of `slot` the pack plans at the id the table gives them."""
        rows = {s: m for (sl, s), m in self.ids.items() if sl == slot}
        rows.update({s: m for (sl, s), m in self.xx_only.items() if sl == slot and self.in_pack(sl, s)})
        return rows

    def held_back(self, slot: str) -> set[int]:
        """The XX-only sources of `slot` the pack does not carry."""
        return {s for (sl, s) in self.xx_only if sl == slot and not self.in_pack(sl, s)}


def load_pack_ids(path=PACK_IDS_FILE) -> PackIds:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    sections = {name: {(slot, source): model for slot, row in data[name].items()
                       for source, model in parse_ids(row).items()} for name in ("ids", "xx_only")}
    return PackIds(sections["ids"], sections["xx_only"], frozenset(data["in_pack"]["armor_models"]),
                   bool(data["in_pack"]["all"]))


@dataclass(frozen=True)
class PackModel:
    slot: str    # an armor part (ARMOR_PARTS) or a weapon class (WEAPON_FOLDERS' values)
    source: int  # the model id in the game it is made from
    model: int   # the MH4U id it is written at (both genders for armor)
    game: str = "gen"   # the game whose archive it is made from: "gen" (MH Generations) or "xx" (MH XX)


def plan_pack(sources: Signatures, m4: Signatures, leave_out: Collection[tuple[str, int]] = frozenset(),
              ids: PackIds | None = None) -> list[PackModel]:
    """The models of MH XX's files (`sources`) that MH4U lacks and the ids they take, armor (ARMOR_PARTS order) then
    weapons, all of game "xx".

    A model goes in when its signature (the model itself) is none of MH4U's for its slot and none of an
    earlier model's, and it is not in `leave_out` ((slot, model), e.g. tables.gimmickless); armor goes in pairs, a
    part whose male or female model is new, at one id for both genders. The table of `ids` (default: the curated
    one) gives the id of every model it lists, and a listed id that an MH4U file uses raises; a model the table
    lacks is planned after the listed ones, at its own id where MH4U and the pack have no file and otherwise at the
    lowest free one. The XX-only looks the table holds back are not planned."""
    ids = load_pack_ids() if ids is None else ids

    def kept(slot: str, models: dict) -> dict:
        held = ids.held_back(slot)
        return {model: None if (slot, model) in leave_out or model in held else s for model, s in models.items()}

    plan = []
    for slot in SLOT_ORDER:
        listed = ids.listed(slot)
        if slot in ARMOR_PARTS:
            args = ([kept(slot, sources.get((g, slot), {})) for g in GENDERS], [m4.get((g, slot), {}) for g in GENDERS],
                    ARMOR_IDS)
        else:
            args = ([kept(slot, sources.get((slot,), {}))], [m4.get((slot,), {})], WEAPON_IDS)

        def rounds(_slot: str, found: set[int], listed=listed) -> list[set[int]]:
            return [found & set(listed), found - set(listed)]
        plan += [replace(p, game="xx") for p in _plan_slot(slot, *args, rounds, listed)]
    return plan


def plan_rounds(gen: Signatures, m4: Signatures, leave_out: Collection[tuple[str, int]] = frozenset(),
                later: Sequence[Collection[tuple[str, int]]] = ()) -> list[PackModel]:
    """The planner that made the table of ids (research/porting/xx_delta_gear.py, `rounds`): every new model, armor
    then weapons, at its own id where MH4U has no file and otherwise at the lowest free one; the models of `later`
    ((slot, model) per round) are planned after the others, round by round, so that they move no id the rounds
    before them gave."""
    def kept(slot: str, models: dict) -> dict:
        return {model: None if (slot, model) in leave_out else s for model, s in models.items()}

    def rounds(slot: str, found: set[int]) -> list[set[int]]:
        laters = [{source for source in found if (slot, source) in added} for added in later]
        return [found - set().union(*laters), *laters]

    plan = []
    for part in ARMOR_PARTS:
        plan += _plan_slot(part, [kept(part, gen.get((g, part), {})) for g in GENDERS],
                           [m4.get((g, part), {}) for g in GENDERS], ARMOR_IDS, rounds)
    for cls in WEAPON_FOLDERS.values():
        plan += _plan_slot(cls, [kept(cls, gen.get((cls,), {}))], [m4.get((cls,), {})], WEAPON_IDS, rounds)
    return plan


def _plan_slot(slot: str, gen: list[dict], m4: list[dict], limit: int, rounds,
               listed: Mapping[int, int] | None = None) -> list[PackModel]:
    listed = listed or {}
    known = [set(models.values()) for models in m4]
    used = set().union(*m4)
    plan, seen = [], set()
    for sources in rounds(slot, set.intersection(*(set(models) for models in gen))):
        chosen = []
        for source in sorted(sources):
            signatures = tuple(models[source] for models in gen)
            if None in signatures or signatures in seen or all(s in k for s, k in zip(signatures, known)):
                continue
            seen.add(signatures)
            chosen.append(source)
        for source in chosen:
            if source in listed:
                if listed[source] in used or not 0 < listed[source] < limit:
                    raise ValueError(f"{slot} {source} is listed at id {listed[source]}, which an MH4U file or another "
                                     f"model uses or which is past the limit {limit}")
                used.add(listed[source])
        kept = {source for source in chosen if source not in listed and source not in used and source < limit}
        used |= kept
        free = (model for model in range(1, limit) if model not in used)
        for source in chosen:
            model = listed[source] if source in listed else source if source in kept else next(free, None)
            if model is None:
                continue  # no free id left in this round: the model stays out of the pack
            used.add(model)
            plan.append(PackModel(slot, source, model))
    return plan


def identical_models(gen: Signatures, m4: Signatures, plan: list[PackModel]) -> dict[tuple[str, int], tuple]:
    """(slot, MHGen model) -> the models that MHGen model is, for each model `plan` left out as MH4U's or an
    earlier pack model's: (male, female) for armor, (model,) for weapons; the lowest MH4U id when several are
    alike. Models that do not convert or that `plan` left out for another reason are not in it."""
    packed = {(p.slot, p.source) for p in plan}
    out = {}
    for slot, genders in [(part, [(g, part) for g in GENDERS]) for part in ARMOR_PARTS] + \
            [(cls, [(cls,)]) for cls in WEAPON_FOLDERS.values()]:
        pack_models = [p for p in plan if p.slot == slot]
        for source in sorted(set.intersection(*(set(gen.get(key, {})) for key in genders))):
            if (slot, source) in packed:
                continue
            models = []
            for key in genders:
                wanted = gen[key][source]
                twins = sorted(model for model, s in m4.get(key, {}).items() if s == wanted and wanted is not None)
                repeats = [p.model for p in pack_models if wanted is not None and gen[key][p.source] == wanted]
                models.append((twins or repeats or [None])[0])
            if None not in models:
                out[(slot, source)] = tuple(models)
    return out


MH4U_ARMOR = re.compile(r"(?:data|loc/data)/pl_([mf])_(helm|body|arm|wst|leg)(\d{3})\.arc")
MH4U_WEAPON = re.compile(r"(?:data|loc/data)/pl_([a-z]+)(\d{3})\.arc")
MHGEN_ARMOR = re.compile(r"arc/player/com/([mf])/(\d{3})/(helm|body|arm|wst|leg)\.arc")
MHGEN_WEAPON = re.compile(r"arc/weapon/(w\d\d)/(\d{3})\.arc")
MOD_COUNTS = slice(0x06, 0x1C)  # MOD header: bones, meshes, materials, vertices, faces, edges, buffer sizes
MOD_VERTEX_SIZE = 0x18          # u32: the vertex buffer's size
MOD_BUFFERS = 0x38              # u32 vertex buffer offset, u32 index buffer offset (to the end of the file)
MESH_VERTICES, MESH_STRIDE, MESH_VERTEX_BASE = 0x02, 0x0A, 0x0C  # u16, u8, u32 (then u32 offset in the buffer)
VERTEX_WEIGHTS = 26             # 2 bytes of every vertex (all equipment formats): skin weights, rounded otherwise
TEX_PIXELS = 8                  # a TEX past its magic and version bytes
SKIN_TEXTURES = ("player\\mod\\common\\m_skin_BM", "player\\mod\\common\\f_skin_BM")  # MHGen bundles them
SOUND_DONOR = 1  # the MH4U model of each class whose sounds a packed weapon without its own gets


def _digest(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=16).digest()


def _geometry(data: bytes) -> bytes:
    """A digest of a MOD's vertex and index buffers, the skin weight bytes of every vertex zeroed."""
    size = struct.unpack_from("<I", data, MOD_VERTEX_SIZE)[0]
    vertices, indices = struct.unpack_from("<2I", data, MOD_BUFFERS)
    buffer = bytearray(data[vertices:vertices + size] if vertices else b"")
    meshes = struct.unpack_from("<I", data, convert.MOD_MESHES)[0]
    for i in range(struct.unpack_from("<H", data, convert.MOD_MESH_COUNT)[0]):
        mesh = meshes + convert.MESH_SIZE * i
        count, stride = struct.unpack_from("<H", data, mesh + MESH_VERTICES)[0], data[mesh + MESH_STRIDE]
        base, offset = struct.unpack_from("<2I", data, mesh + MESH_VERTEX_BASE)
        start = offset + base * stride + VERTEX_WEIGHTS
        for byte in range(start, start + 2):
            weights = slice(byte, byte + count * stride, stride or 1)
            buffer[weights] = bytes(len(buffer[weights]))
    return _digest(bytes(buffer) + (data[indices:] if indices else b""))


def signature(arc: Arc) -> tuple:
    """What tells two models apart: each MOD's header counts and geometry (skin weights aside) and the textures'
    pixels, in no order. Materials are left out: MHGen retuned their
    lighting constants on models it kept."""
    mods = tuple(sorted((e.data[MOD_COUNTS], _geometry(e.data)) for e in arc.entries if e.type_hash == convert.MOD))
    textures = tuple(sorted(_digest(e.data[TEX_PIXELS:]) for e in arc.entries
                            if e.type_hash == convert.TEX and e.name not in SKIN_TEXTURES))
    return mods, textures


def mh4u_signatures(m4) -> Signatures:
    """The signature of every MH4U armor and weapon model (`m4`, a RomFS), DLC files in loc/data included."""
    out: Signatures = {}
    classes = set(WEAPON_FOLDERS.values())
    for path in m4.walk():
        if match := MH4U_ARMOR.fullmatch(path):
            slot, model = (match[1], match[2]), int(match[3])
        elif (match := MH4U_WEAPON.fullmatch(path)) and match[1] in classes:
            slot, model = (match[1],), int(match[2])
        else:
            continue
        out.setdefault(slot, {})[model] = signature(parse_arc(m4.read(path)))
    return out


def mhgen_signatures(gen, shaders, only: Collection[tuple[str, int]] | None = None) -> Signatures:
    """The signature of every MHGen armor and weapon model (`gen`, a RomFS; MH XX's has the same files), None for
    those that do not convert with `shaders` (MHGen's and MH4U's shader_records). `only`: just these models,
    (an armor part or weapon class, model) pairs."""
    out: Signatures = {}
    for path in gen.walk():
        if match := MHGEN_ARMOR.fullmatch(path):
            slot, model = (match[1], match[3]), int(match[2])
        elif (match := MHGEN_WEAPON.fullmatch(path)) and match[1] in WEAPON_FOLDERS:
            slot, model = (WEAPON_FOLDERS[match[1]],), int(match[2])
        else:
            continue
        if only is not None and (slot[-1], model) not in only:
            continue
        arc = parse_arc(gen.read(path))
        try:
            convert.convert_arc(arc, *shaders)
        except ValueError:
            out.setdefault(slot, {})[model] = None
            continue
        out.setdefault(slot, {})[model] = signature(arc)
    return out


def write_pack(data_dir, gen, m4, plan: list[PackModel], shaders, xx=None,
               sources: dict[str, tuple[str, ...]] | None = None) -> dict[tuple[str, str, int], int]:
    """Write the archive of every model of `plan` into `data_dir` (romfs/data) and return the cloth bits the
    armor needs ((gender, part, model) -> bits, for moved_cloth_tables). The models of game "xx" are read from
    `xx` (MH XX's RomFS), the others from `gen`, which may be None when the plan has none of those; `shaders`: the
    shader records of MH Generations' package and MH4U's (None for Generations' without `gen`). `sources`, when
    given, receives for each archive made from `xx` its mod path (romfs/data/...) -> the files of `xx` it read, in
    order (xx_sources)."""
    folders = {cls: folder for folder, cls in WEAPON_FOLDERS.items()}
    xx_shaders = (convert.shader_records(xx.read(SHADER_PACKAGE)), shaders[1]) if xx is not None else None
    cloth = {}
    for p in plan:
        if p.game == "xx":
            if xx is None:
                raise ValueError(f"{p.slot} {p.source} is made from MH XX, which was not given")
            source, source_shaders = xx, xx_shaders
        else:
            source, source_shaders = gen, shaders
        if p.slot in ARMOR_PARTS:
            for gender in GENDERS:
                read = mhgen_armor_file(gender, p.slot, p.source)
                arc = armor_arc(source.read(read), *source_shaders, gender, p.slot, p.source, new_model=p.model)
                target = mh4u_armor_file(gender, p.slot, p.model)
                (data_dir / target.split("/")[-1]).write_bytes(write_arc(arc))
                if sources is not None and p.game == "xx":
                    sources["romfs/" + target] = (read,)
                if flags := cloth_flags(p.slot, arc):
                    cloth[(gender, p.slot, p.model)] = flags
        else:
            folder = folders[p.slot]
            donor_file = mh4u_weapon_file(folder, SOUND_DONOR)
            sounds = parse_arc(m4.read(donor_file))
            own = mhgen_sound_file(folder, p.source)
            read = [mhgen_weapon_file(folder, p.source)]
            data = source.read(read[0])
            if source.exists(own):
                read.append(own)
            arc = weapon_arc(data, *source_shaders, folder, p.source, sounds=sounds, new_model=p.model,
                             own_sounds=parse_arc(source.read(own)) if len(read) > 1 else None,
                             donor_used=(used := []))
            target = mh4u_weapon_file(folder, p.model)
            (data_dir / target.split("/")[-1]).write_bytes(write_arc(arc))
            if sources is not None and p.game == "xx":
                sources["romfs/" + target] = (*read, "mh4u:" + donor_file) if used else tuple(read)
    return cloth
