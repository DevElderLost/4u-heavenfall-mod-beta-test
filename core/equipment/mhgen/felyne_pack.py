"""MH Generations' Felyne (Palico) models as MH4U archives, and the executable tables their new model numbers need.

A Felyne's gear is three archives per model number, `data/o_helm<N>`, `o_body<N>` and `o_we<N>`, that MHGen keeps in
`arc/otomo/mod/<N>/{h,b,w}.arc` (and the weapon's sounds in `arc/otomo/wp_se/<N>.arc`). The two games number their
models differently, so a MHGen model is written at a number of MH4U's own (FIRST_MODEL on, past the 113 it has), fixed
per model (model_number). Four per-model tables of the executable end at model 113 (or hold nothing past it): the masks
of the base Felyne's parts that a helm and a body leave showing, the helm's cloth bit and the weapon's sound path. They
move to the extension with the new entries.

The Felyne's base model draws all its parts (head, torso, limbs, ears, eyes, tail); a MH4U armor piece is an overlay
that hides a few of them. MHGen's pieces carry their own skin patches where the base would show, so a converted
piece hides every part it replaces and only lets the ears, eyes and tail show when its display flags say so
(head_mask, body_mask).
"""

import re
import struct
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from core.game.files.arc import Arc, ArcEntry, parse_arc, write_arc
from core.game.executable.code_space import Layout, load_layout
from core.equipment.mhgen import convert, equipment_pack as pack, sound
from core.equipment.mhgen.felyne_face import (base_face_samples, dress_bare_skin, fit_head, hide_additive,
                                               hide_second_form)
from core.equipment.mhgen.gear_data import FELYNE_WEAPON_SIZE, XX_FORMAT, GenGame
from core.equipment.mhgen.felyne_skin import reweight_cloth
from core.equipment.mhgen.tables import CODE_BASE, hair_flags, repoint

# The ported monsters' Felyne sets: the MHGen model of each, and the MH4U model
# that already is the same look (Alatreon's "F Escador" is MHGen's model 16).
MHGEN_MODELS = {"mizutsune": 124, "great_maccao": 119, "glavenus": 121}
MH4U_MODELS = {"alatreon": 70}

GAME_MODELS = 114              # MH4U's Felyne models 0-113: what its per-model tables hold
FIRST_MODEL = 114              # the first number a MHGen model takes
FIRST_LOOK = 118               # model N of MH XX's folders is number FIRST_LOOK + N (117 is Valstrax's)
LAST_SOURCE = 214              # the highest folder of MH XX with a named piece (215 holds only DUMMY records)
SPARE_MODELS = 3               # numbers past the looks for the next sets (FELYNE_IDS stays in 42 bytes of bits)
FELYNE_IDS = FIRST_LOOK + LAST_SOURCE + 1 + SPARE_MODELS      # entries of the moved tables, and the numbers in use
# The ported monsters' sets keep the numbers they first took, so a set never changes number (fix mode).
# 191: Valstrax, 122: Astalos (both XX only). 114-117 were the spares before the
# looks (118 on); the next ported sets take the numbers past the last look: FIRST_LOOK + LAST_SOURCE + 1 (333) on
# The Deviants' sets (folders 184 Boltreaver, 151 Hellblade, 185 Soulseer) wear the number of their own look
# (FIRST_LOOK + folder): the files are the same, so a run with both writes them once (`merged`); no spare is used.
MODEL_SLOTS = {124: 114, 119: 115, 121: 116, 191: 117, 122: 333, 184: FIRST_LOOK + 184, 151: FIRST_LOOK + 151,
               185: FIRST_LOOK + 185}
PARTS = {"helm": "h", "body": "b", "we": "w"}   # MH4U's archive prefix `o_<part>` -> MHGen's file

# The update's tables (VA; file offset + CODE_BASE) and the literal words their readers load them from. All
# readers of the masks and the cloth bits: FUN_002f8e30 / FUN_002f8e1c (a u16 per model) and FUN_006963d0,
# FUN_006970d0, FUN_0069915c (a byte per helm model, bit 0).
HEAD_MASKS, HEAD_MASK_LITERALS = 0xF5AF60, (0x2F8E40,)
BODY_MASKS, BODY_MASK_LITERALS = 0xF5B044, (0x2F8E2C,)
HEAD_CLOTH, HEAD_CLOTH_LITERALS = 0xFB832C, (0x6963F0, 0x6972C4, 0x6993FC)
# The weapon's sound path, a pointer per model (0 none) read by FUN_0030e8c0 from the literal at 0x30F188: model m
# at SOUND_PATHS + 4 * m. Models 114-117 are free (0); a table of other paths follows, so it moves too.
SOUND_PATHS, SOUND_PATH_LITERALS = 0xEFC4FC, (0x30F188,)
SOUND_SLOT = 32                # a block of FELYNE_IDS - FIRST_MODEL strings of this size
SOUND_PATH = "sound\\se\\otomo\\wp\\snd_otm_wp{:03d}"

# The masks' bits: set shows the base model's part (FUN_001a0ab8; a clear bit hides it). The base's other head
# groups are bits 0, 4, 5, 8, the body's 1, 2, 3, 6, 7, 9, 10: a converted piece hides them all.
SHOWN = 0x3FFF                 # a mask that hides nothing: the game's own value for "no equipment"
HEAD_EARS, HEAD_EYES, BODY_TAIL = 0x0800, 0x2000, 0x1000
HEAD_FACE = 0x0031             # the base head: skin (groups 0, 5) and whiskers (group 4), mask bits 0, 4, 5
# MHGen's display flags (rPlayerPartsDisp, per object 2-33; a clear bit hides): ears are bit 0 of the first word,
# eyes bit 1 of the second, tails bit 2 of the first, on objects 2-6 (the tails; the others hold the rest).
EARS_FLAG, EYES_FLAG, TAIL_FLAG = 0x0001, 0x0002, 0x0004
TAIL_OBJECTS = range(2, 7)

MHGEN_SOUNDS = "arc/otomo/wp_se/{:03d}.arc"
SKIN_ARC = "arc/otomo/mod/skin/000.arc"   # the first coat: its texture is the one the pieces name as their skin
ARMOR_MODEL, ARMOR_FORMS = 6, 0x1D         # an `otArmorData` record of MH XX: its model, and non-zero for two forms
ARMOR_PRICE = 8                            # its u32 price (gear_data.parse_felyne_armor)
WEAPON_MODEL, WEAPON_PRICE = 4, 25         # an `otWeaponData` record: u16 model, u32 price (parse_felyne_weapon)
DONOR_WEAPON = "data/o_we001.arc"   # a MH4U Felyne weapon whose sounds a model without its own gets
WAVES, BANK_ENTRIES, MAX_REQUEST = ("down", "up"), 3, 3   # what MH4U's Felyne weapon banks hold (o_we001: 3, 0-3)
FELYNE_FILE = re.compile(r"(?:loc/)?data/o_(?:helm|body|we)(\d{3})\.arc")
SOUND_STRING = re.compile(rb"sound\\se\\otomo\\wp\\[ -~]+?(?=\x00)")
MANIFEST = "mhgen_felyne_files.txt"   # in the mod folder: the archives written into romfs/data
DATA_DIR = Path("romfs") / "data"


@dataclass(frozen=True)
class FelyneModel:
    source: int   # MHGen's model number
    model: int    # the MH4U number it is written at


@dataclass(frozen=True)
class FelyneNeeds:
    """What patch_executable writes, per MH4U model number."""
    head_masks: dict[int, int]       # model -> mask (HEAD_EARS | HEAD_EYES, or 0)
    body_masks: dict[int, int]       # model -> mask (BODY_TAIL, or 0)
    head_cloth: frozenset[int]       # helm models whose archive has cloth (bit 0 of HEAD_CLOTH)
    weapons: frozenset[int]          # weapon models whose archive has sounds (their path slot)


@dataclass(frozen=True)
class FelynePack:
    models: tuple[FelyneModel, ...]
    files: dict[str, bytes]          # path in romfs (data/o_helm114.arc) -> the archive
    needs: FelyneNeeds
    sources: dict[str, tuple[str, ...]] = field(default_factory=dict)   # romfs path -> MH XX files read


def model_number(source: int) -> int:
    """The MH4U number of the Felyne model in folder `source`, whichever others are on (a look, a ported set)."""
    return MODEL_SLOTS.get(source, FIRST_LOOK + source)


def plan_models(sources: Sequence[int], taken: Collection[int] = ()) -> list[FelyneModel]:
    """The MH4U number of each MHGen Felyne model in `sources`, in order (model_number). `taken`: the numbers MH4U's
    files use. ValueError when a model repeats, its number is taken or past the tables."""
    if len(set(sources)) != len(sources):
        raise ValueError(f"a Felyne model twice in {list(sources)}")
    out = []
    for source in sources:
        model = model_number(source)
        if model >= FELYNE_IDS:
            raise ValueError(f"no Felyne model number for folder {source}: the tables end at {FELYNE_IDS - 1}")
        if model in taken:
            raise ValueError(f"MH4U already has files for Felyne model {model}")
        out.append(FelyneModel(source, model))
    return out


def mh4u_models(m4) -> set[int]:
    """The Felyne model numbers MH4U has files for (`m4`, a RomFS), the downloadable ones in loc/data included."""
    return {int(match[1]) for path in m4.walk() if (match := FELYNE_FILE.fullmatch(path))}


# ----- the parts the base model still shows ------------------------------------------------------------------


def head_mask(arc: Arc) -> int:
    """The head mask of MHGen helm archive `arc`: the ears (HEAD_EARS) and eyes (HEAD_EYES) its display flags
    leave showing, none of the base's other head parts. Everything shows without flags."""
    flags = hair_flags(arc)
    if not flags:
        return HEAD_EARS | HEAD_EYES
    ears = all(first & EARS_FLAG for first, _ in flags.values())
    eyes = all(second & EYES_FLAG for _, second in flags.values())
    return (HEAD_EARS if ears else 0) | (HEAD_EYES if eyes else 0)


def game_head_mask(arc: Arc) -> int:
    """The mask the game gets for helm archive `arc`: head_mask, and where the eyes show also the base head
    (HEAD_FACE: its skin and whiskers), so that the eyes lie on the Felyne's own coat and not on the helm's skin patch,
    which is another colour; the patch, whiskers included, is hidden (felyne_face)."""
    mask = head_mask(arc)
    return mask | HEAD_FACE if mask & HEAD_EYES else mask


def body_mask(arc: Arc) -> int:
    """The body mask of MHGen body archive `arc`: BODY_TAIL when no tail object is hidden, none of the base's
    other body parts."""
    flags = hair_flags(arc)
    if not flags:
        return BODY_TAIL
    return BODY_TAIL if all(flags.get(obj, (0xFFFF, 0xFFFF))[0] & TAIL_FLAG for obj in TAIL_OBJECTS) else 0


# ----- archives ----------------------------------------------------------------------------------------------


def mhgen_file(source: int, part: str) -> str:
    return f"arc/otomo/mod/{source:03d}/{PARTS[part]}.arc"


def mh4u_file(model: int, part: str) -> str:
    return f"data/o_{part}{model:03d}.arc"


def _renamed(arc: Arc, model: FelyneModel) -> Arc:
    """`arc` with its entries and texture paths at model.model: the model's folder and its numbered files."""
    folder, new_folder = f"otomo\\mod\\ot{model.source:03d}\\", f"otomo\\mod\\ot{model.model:03d}\\"
    number = re.compile(rf"(?<=[a-z]){model.source:03d}(?=_|$)")

    def rename(path: str) -> str:
        return new_folder + number.sub(f"{model.model:03d}", path[len(folder):]) if path.startswith(folder) else path
    return pack._renamed(arc, rename)


def _converted(source: bytes, source_shaders, target_shaders, model: FelyneModel) -> Arc:
    """MHGen archive `source` converted (convert.convert_arc), at the model's number, with its materials fitted to
    MH4U's Felyne gear (convert.fit_felyne_materials)."""
    arc = _renamed(convert.convert_arc(parse_arc(source), source_shaders, target_shaders), model)
    for entry in arc.entries:
        if entry.type_hash == convert.MRL:
            entry.data = convert.fit_felyne_materials(entry.data, target_shaders[1])
    return arc


def form_models(rom) -> frozenset[int]:
    """The Felyne models whose armor has two forms, as MH XX's table marks them (ARMOR_FORMS of `otArmorData`, `rom`
    its RomFS): their groups 1 and 2 are not armor worn together, unlike those of an unmarked model. A game with no
    such byte has none."""
    game = GenGame(rom, names={})
    if game.fmt is not XX_FORMAT:
        return frozenset()
    return frozenset(r[ARMOR_MODEL] for r in game.records("otArmorData", game.fmt.felyne_armor_size) if r[ARMOR_FORMS])


def xx_felyne_prices(rom) -> dict[tuple[str, int], int]:
    """(part, model folder) -> what forging a Felyne piece of that model costs in MH XX (`rom` its RomFS):
    `otArmorData`'s price (one record serves the head and the body, each forged at it) and `otWeaponData`'s; the
    cheapest record of a model. A game with no such tables (not XX) has none."""
    game = GenGame(rom, names={})
    if game.fmt is not XX_FORMAT:
        return {}
    prices: dict[tuple[str, int], int] = {}

    def keep(key: tuple[str, int], price: int) -> None:
        prices[key] = min(price, prices.get(key, price))

    for record in game.records("otArmorData", game.fmt.felyne_armor_size):
        for part in ("head", "body"):
            keep((part, record[ARMOR_MODEL]), struct.unpack_from("<I", record, ARMOR_PRICE)[0])
    for record in game.records("otWeaponData", FELYNE_WEAPON_SIZE):
        keep(("weapon", struct.unpack_from("<H", record, WEAPON_MODEL)[0]),
             struct.unpack_from("<I", record, WEAPON_PRICE)[0])
    return prices


def skin_texture(rom) -> ArcEntry | None:
    """The placeholder skin that MH XX's and MHGen's Felyne pieces name (the first coat's texture, `rom`'s RomFS),
    as MH4U reads it; None for a game without the file."""
    if not rom.exists(SKIN_ARC):
        return None
    entry = next((e for e in parse_arc(rom.read(SKIN_ARC)).entries if e.type_hash == convert.TEX), None)
    return None if entry is None else ArcEntry(entry.name, entry.type_hash, convert.convert_tex(entry.data),
                                               convert.MH4U_FLAGS.get(entry.type_hash, convert.MH4U_DEFAULT_FLAGS))


def _armor_arc(source: bytes, source_shaders, target_shaders, model: FelyneModel, cloth: bool,
               skin: ArcEntry | None = None, forms: bool = False) -> Arc:
    """MHGen armor archive `source` converted. `skin`: the texture a material with none gets (dress_bare_skin);
    `forms`: the model's armor has two forms, of which it keeps the game's at rest (hide_second_form). `cloth`: it
    keeps its CTC."""
    arc = _converted(source, source_shaders, target_shaders, model)
    if skin is not None:
        dress_bare_skin(arc, target_shaders[1], skin)
    if forms:
        hide_second_form(arc)
    if not cloth:
        arc.entries = [e for e in arc.entries if e.type_hash != convert.CTC]
        for entry in arc.entries:
            if entry.type_hash == convert.MOD:
                entry.data = reweight_cloth(entry.data)
    return arc


def head_arc(source: bytes, source_shaders, target_shaders, model: FelyneModel,
             faces: Mapping[str, Sequence] | None = None, skin: ArcEntry | None = None, forms: bool = False) -> Arc:
    """MHGen helm archive `source` as MH4U's `o_helm<N>`, keeping its cloth (CTC): the game loads it for the
    helms whose bit of HEAD_CLOTH is set. A helm that shows the base's eyes or ears (head_mask) gets every surface
    that lies on them sunk behind them (felyne_face.fit_head; `faces`: face_samples of the base Felyne): the two
    would share their depth and win some pixels in each frame. Without `faces` only the skin patch of a helm that
    shows the eyes is hidden. `skin`, `forms`: as _armor_arc; a helm's bare copy of the head is such a patch."""
    arc = _armor_arc(source, source_shaders, target_shaders, model, True, skin, forms)
    mask = game_head_mask(parse_arc(source))
    samples = [p for bit, kind in ((HEAD_EYES, "eyes"), (HEAD_EARS, "ears")) if mask & bit and faces
               for p in faces[kind]]
    head = faces["head"] if mask & HEAD_FACE and faces and "head" in faces else ()
    fit_head(arc, target_shaders[1], samples, bool(mask & HEAD_EYES), head)
    hide_additive(arc, target_shaders[1])
    return arc


def body_arc(source: bytes, source_shaders, target_shaders, model: FelyneModel, skin: ArcEntry | None = None,
             forms: bool = False) -> Arc:
    """MHGen body archive `source` as MH4U's `o_body<N>`, without its cloth: the game's Felyne body path
    (FUN_001a0ab8) attaches no chain, and no MH4U body archive has a CTC or weights a cloth joint, so the weight of
    those joints goes to their parent (reweight_cloth). `skin`, `forms`: as _armor_arc."""
    arc = _armor_arc(source, source_shaders, target_shaders, model, False, skin, forms)
    hide_additive(arc, target_shaders[1])
    return arc


def _bank_paths(data: bytes) -> list[str]:
    """The wave path of each entry of a MH4U sound bank (one group)."""
    at = sound.BANK_HEADER
    out = []
    for _ in range(struct.unpack_from("<I", data, 0x0C)[0]):
        end = data.find(b"\x00", at)
        out.append(data[at:end].decode("ascii"))
        at = end + 5 + sound.BANK_ENTRY
    return out


def _trim_bank(data: bytes, keep: int) -> bytes:
    """MH4U sound bank `data` (one group) with its first `keep` entries only."""
    count = struct.unpack_from("<I", data, 0x0C)[0]
    if struct.unpack_from("<I", data, sound.BANK_GROUPS)[0] != 1 or count < keep:
        raise ValueError("a Felyne sound bank of another layout")
    at = sound.BANK_HEADER
    for _ in range(keep):
        at = data.find(b"\x00", at) + 5 + sound.BANK_ENTRY
    out = bytearray(data[:at] + data[len(data) - sound.BANK_TRAILER:])
    struct.pack_into("<I", out, 0x0C, keep)
    out[sound.BANK_FLAGS_AT - 1] = 2 * keep   # the group's descriptor: 2 x its entries
    return bytes(out)


def _trim_requests(data: bytes, max_id: int) -> bytes:
    """MH4U sound requests `data` with the records of ids up to `max_id`."""
    count, end = struct.unpack_from("<II", data, 8)
    records = [data[sound.REQUEST_HEADER + i * sound.REQUEST:sound.REQUEST_HEADER + (i + 1) * sound.REQUEST]
               for i in range(count)]
    kept = [r for r in records if struct.unpack_from("<H", r)[0] <= max_id]
    new_end = sound.REQUEST_HEADER + len(kept) * sound.REQUEST
    return (b"SREQ" + struct.pack("<III", sound.REQUEST_VERSION, len(kept), new_end) + b"".join(kept)
            + struct.pack("<I", new_end + 4) + data[end + 4:])


def weapon_sounds(source: Arc, model: FelyneModel) -> list[ArcEntry]:
    """MHGen's Felyne weapon sound archive `source` (`wp_se/<N>.arc`) as the sound entries of a MH4U `o_we<N>` at
    model.model: the weapon's own waves, a bank of the first BANK_ENTRIES entries and the requests up to
    MAX_REQUEST (the shape of MH4U's own). MHGen adds the shared hit and whoosh waves and requests 11-14, which
    MH4U's code never asks for. ValueError when an entry does not convert."""
    old, new = f"{model.source:03d}", f"{model.model:03d}"

    def rename(path: str) -> str:
        return (path.replace("\\se\\neko\\wp\\", "\\se\\otomo\\wp\\").replace("\\wav\\", "\\wave\\")
                .replace("neko_wp" + old, "otm_wp" + new))

    waves, bank, requests = {}, None, None
    for entry in source.entries:
        if entry.type_hash == sound.GEN_WAVE:
            waves[rename(entry.name)] = sound.convert_wave(entry.data)
        elif entry.type_hash == sound.GEN_BANK:
            bank = _trim_bank(sound.convert_bank(entry.data, rename), BANK_ENTRIES)
            name = rename(entry.name)
        elif entry.type_hash == sound.GEN_REQUESTS:
            requests = entry.data
        else:
            raise ValueError(f"a sound entry of unknown type {entry.type_hash:#010x}: {entry.name}")
    if bank is None or requests is None:
        raise ValueError("a Felyne weapon sound archive without its bank or its requests")
    out = []
    for path in dict.fromkeys(_bank_paths(bank)):
        if path not in waves:
            raise ValueError(f"the bank names {path}, which the archive lacks")
        out.append(ArcEntry(path, sound.WAVE, waves[path], convert.MH4U_DEFAULT_FLAGS))
    requests = _trim_requests(sound.convert_requests(requests, rename), MAX_REQUEST)
    out.append(ArcEntry(name, sound.SOUND_BANK, bank, convert.MH4U_DEFAULT_FLAGS))
    out.append(ArcEntry(name, sound.SOUND_REQUEST, requests, convert.MH4U_DEFAULT_FLAGS))
    return out


def _donor_sounds(donor: Arc, model: FelyneModel) -> list[ArcEntry]:
    """The sound entries of MH4U Felyne weapon archive `donor`, named for model.model (same length)."""
    entries = [e for e in donor.entries if e.type_hash in sound.SOUND_TYPES]
    bank = next((re.search(r"wp(\d{3})", e.name) for e in entries if e.type_hash == sound.SOUND_BANK), None)
    if bank is None:
        raise ValueError("the donor archive has no weapon sounds")
    old, new = f"wp{bank[1]}", f"wp{model.model:03d}"
    return [ArcEntry(e.name.replace(old, new), e.type_hash, e.data.replace(old.encode(), new.encode()), e.flags)
            for e in entries]


def weapon_arc(source: bytes, source_shaders, target_shaders, model: FelyneModel, donor: Arc | None = None,
               own_sounds: Arc | None = None, donor_used: list | None = None) -> Arc:
    """MHGen weapon archive `source` as MH4U's `o_we<N>`, with MHGen's own sounds (`own_sounds`, wp_se/<N>.arc;
    weapon_sounds) or, without them or when they do not convert, those of MH4U Felyne weapon archive `donor`
    renamed (`donor_used`, when given, then gets a True appended). A weapon with neither has no sound. Its additive
    shells are hidden (felyne_face.hide_additive)."""
    arc = _converted(source, source_shaders, target_shaders, model)
    hide_additive(arc, target_shaders[1])
    if own_sounds is not None:
        try:
            arc.entries += weapon_sounds(own_sounds, model)
            return arc
        except ValueError:
            pass  # the donor's then
    if donor is not None:
        arc.entries += _donor_sounds(donor, model)
        if donor_used is not None:
            donor_used.append(True)
    return arc


def convert_models(gen, m4, sources: Sequence[int], xx=None, xx_sources: Collection[int] = (),
                   parts: Mapping[int, Collection[str]] | None = None) -> FelynePack:
    """The archives of MHGen's Felyne models `sources` (`gen`, a RomFS of MH Generations) at MH4U numbers
    (plan_models against the files of `m4`, a RomFS), and what the executable needs for them. A model MHGen lacks
    a part of gets no archive for it. ValueError for a model MHGen has none of, or one that does not convert.
    The models of `xx_sources` (those a monster ported from MH XX wears) are read from `xx`, MH XX's RomFS, which
    holds the same files; `gen` may then be None. `parts`: only these parts of a model (PARTS' keys), default all."""
    models = plan_models(sources, mh4u_models(m4))
    m4_shaders = convert.shader_records(m4.read(pack.SHADER_PACKAGE))
    shaders_of, looks_of = {}, {}

    def source_of(model: int):
        """(RomFS, shader records) the Felyne model `model` is read from."""
        rom = xx if model in xx_sources else gen
        if rom is None:
            raise ValueError(f"Felyne model {model} needs {'MH XX' if model in xx_sources else 'MH Generations'}")
        if id(rom) not in shaders_of:
            shaders_of[id(rom)] = (convert.shader_records(rom.read(pack.SHADER_PACKAGE)), m4_shaders)
            looks_of[id(rom)] = (skin_texture(rom), form_models(rom))
        return rom, shaders_of[id(rom)]

    donor = parse_arc(m4.read(DONOR_WEAPON)) if m4.exists(DONOR_WEAPON) else None
    faces = None   # the base Felyne's eyes and ears, read when the first helm needs them
    files: dict[str, bytes] = {}
    xx_read: dict[str, tuple[str, ...]] = {}   # the archives made from `xx` -> the files read
    head_masks, body_masks, cloth, weapons = {}, {}, set(), set()
    for model in models:
        rom, shaders = source_of(model.source)      # the game this model is read from
        skin, marked = looks_of[id(rom)]
        forms = model.source in marked
        found = [part for part in PARTS if rom.exists(mhgen_file(model.source, part))
                 and (parts is None or part in parts[model.source])]
        if not found:
            raise ValueError(f"MH Generations has no Felyne model {model.source}")
        for part in found:
            read = [mhgen_file(model.source, part)]
            source = rom.read(read[0])
            if part == "helm":
                faces = faces or base_face_samples(m4)
                arc = head_arc(source, *shaders, model, faces, skin, forms)
                head_masks[model.model] = game_head_mask(parse_arc(source))
                if convert.CTC in {e.type_hash for e in arc.entries}:
                    cloth.add(model.model)
            elif part == "body":
                arc = body_arc(source, *shaders, model, skin, forms)
                body_masks[model.model] = body_mask(parse_arc(source))
            else:
                own = MHGEN_SOUNDS.format(model.source)
                if rom.exists(own):
                    read.append(own)
                arc = weapon_arc(source, *shaders, model, donor, parse_arc(rom.read(own)) if rom.exists(own) else None,
                                 donor_used=(used := []))
                if used:
                    read.append("mh4u:" + DONOR_WEAPON)
                if any(e.type_hash in sound.SOUND_TYPES for e in arc.entries):
                    weapons.add(model.model)
            if skin is not None and any(e.data is skin.data for e in arc.entries):
                read.append(SKIN_ARC)      # dress_bare_skin added the skin texture, bytes of the coat's archive
            files[mh4u_file(model.model, part)] = write_arc(arc)
            if rom is xx:
                xx_read[mh4u_file(model.model, part)] = tuple(read)
    return FelynePack(tuple(models), files, FelyneNeeds(head_masks, body_masks, frozenset(cloth), frozenset(weapons)),
                      xx_read)


def merged(first: FelynePack | None, second: FelynePack | None) -> FelynePack | None:
    """Both packs as one, for the files of a run (a number is one model, so a file both hold is the same)."""
    if first is None or second is None:
        return first or second
    needs = FelyneNeeds({**first.needs.head_masks, **second.needs.head_masks},
                        {**first.needs.body_masks, **second.needs.body_masks},
                        first.needs.head_cloth | second.needs.head_cloth, first.needs.weapons | second.needs.weapons)
    models = tuple(dict.fromkeys(first.models + second.models))
    return FelynePack(models, {**first.files, **second.files}, needs, {**first.sources, **second.sources})


def file_names(felyne: FelynePack) -> list[str]:
    return [path.split("/")[-1] for path in felyne.files]


def written_names(mod_dir: Path) -> set[str]:
    """The names of the archives in `mod_dir`/romfs/data that a run wrote (MANIFEST)."""
    manifest = mod_dir / MANIFEST
    return {Path(name).name for name in manifest.read_text(encoding="utf-8").split()} if manifest.is_file() else set()


def remove_files(mod_dir: Path) -> None:
    """Delete the archives an earlier run wrote into `mod_dir`/romfs/data (its MANIFEST) and the manifest."""
    for name in written_names(mod_dir):
        (mod_dir / DATA_DIR / name).unlink(missing_ok=True)
    (mod_dir / MANIFEST).unlink(missing_ok=True)


def write_files(mod_dir: Path, felyne: FelynePack) -> list[str]:
    """Write the archives into `mod_dir`/romfs/data, replacing an earlier run's, and list their names."""
    remove_files(mod_dir)
    names = file_names(felyne)
    if names:
        (mod_dir / DATA_DIR).mkdir(parents=True, exist_ok=True)
        for path, data in felyne.files.items():
            (mod_dir / DATA_DIR / path.split("/")[-1]).write_bytes(data)
        # LF on every system: the web page's mod is the program's, byte for byte
        (mod_dir / MANIFEST).write_bytes("".join(f"{name}\n" for name in names).encode("utf-8"))
    return names


# ----- the executable ----------------------------------------------------------------------------------------


def _check_models(models: Collection[int], what: str) -> None:
    for model in models:
        if not GAME_MODELS <= model < FELYNE_IDS:
            raise ValueError(f"{what} for Felyne model {model}: only {GAME_MODELS}-{FELYNE_IDS - 1} are new")


def _game_entries(code: bytes, address: int, fmt: str) -> list[int]:
    return list(struct.unpack_from(f"<{GAME_MODELS}{fmt}", code, address - CODE_BASE))


def moved_masks(code: bytes, address: int, masks: dict[int, int]) -> bytes:
    """A mask table (HEAD_MASKS or BODY_MASKS) of FELYNE_IDS u16: the game's entries, SHOWN for the new models and
    then `masks` (model -> value)."""
    _check_models(masks, "a mask")
    table = _game_entries(code, address, "H") + [SHOWN] * (FELYNE_IDS - GAME_MODELS)
    for model, value in masks.items():
        table[model] = value
    return struct.pack(f"<{FELYNE_IDS}H", *table)


def moved_head_cloth(code: bytes, cloth: Collection[int]) -> bytes:
    """The helm cloth table of FELYNE_IDS bytes: the game's, then bit 0 set for the models of `cloth`."""
    _check_models(cloth, "a cloth bit")
    table = _game_entries(code, HEAD_CLOTH, "B") + [0] * (FELYNE_IDS - GAME_MODELS)
    for model in cloth:
        table[model] |= 1
    return bytes(table)


def sound_paths(weapons: Collection[int]) -> bytes:
    """The block of path strings, SOUND_SLOT bytes for each model from FIRST_MODEL on."""
    _check_models(weapons, "a sound path")
    out = bytearray((FELYNE_IDS - FIRST_MODEL) * SOUND_SLOT)
    for model in weapons:
        path = SOUND_PATH.format(model).encode() + b"\x00"
        out[(model - FIRST_MODEL) * SOUND_SLOT:(model - FIRST_MODEL) * SOUND_SLOT + len(path)] = path
    return bytes(out)


def moved_sound_table(code: bytes, weapons: Collection[int], paths: int) -> bytes:
    """The sound table of FELYNE_IDS pointers: the game's, then the paths of `weapons` in the block at `paths`. A slot
    past the game's that is not free means another executable."""
    _check_models(weapons, "a sound path")
    free = struct.unpack_from(f"<{FIRST_LOOK - GAME_MODELS}I", code, SOUND_PATHS + 4 * GAME_MODELS - CODE_BASE)
    if any(free):
        raise ValueError("the sound table's free slots are not free: not the update's executable")
    table = _game_entries(code, SOUND_PATHS, "I") + [0] * (FELYNE_IDS - GAME_MODELS)
    for model in weapons:
        table[model] = paths + (model - FIRST_MODEL) * SOUND_SLOT
    return struct.pack(f"<{FELYNE_IDS}I", *table)


def patch_executable(code: bytes, needs: FelyneNeeds, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) with the per-model tables of `needs` (a Felyne model past 113): the head
    and body masks, the helm cloth bits and the weapons' sound paths moved to the extension with their readers
    repointed. A second call adds its models to the tables the first moved (the ported monsters' sets, then layered
    equipment's looks). Nothing to patch leaves `code` alone. Refuses another executable."""
    if not (needs.head_masks or needs.body_masks or needs.head_cloth or needs.weapons):
        return code
    layout = layout or load_layout()
    out = bytearray(code)
    for name, address, literals, masks in (("felyne_head_masks", HEAD_MASKS, HEAD_MASK_LITERALS, needs.head_masks),
                                           ("felyne_body_masks", BODY_MASKS, BODY_MASK_LITERALS, needs.body_masks)):
        if not masks:
            continue
        if struct.unpack_from("<I", out, literals[0] - CODE_BASE)[0] == layout.address(name):
            _check_models(masks, "a mask")
            for model, value in masks.items():
                struct.pack_into("<H", out, layout.address(name) + 2 * model - CODE_BASE, value)
        else:
            layout.place(out, name, moved_masks(code, address, masks))
            out = bytearray(repoint(bytes(out), literals, address, layout.address(name)))
    if needs.head_masks or needs.head_cloth:
        cloth = layout.address("felyne_head_cloth")
        if struct.unpack_from("<I", out, HEAD_CLOTH_LITERALS[0] - CODE_BASE)[0] == cloth:
            _check_models(needs.head_cloth, "a cloth bit")
            for model in needs.head_cloth:
                out[cloth + model - CODE_BASE] |= 1
        else:
            layout.place(out, "felyne_head_cloth", moved_head_cloth(code, needs.head_cloth))
            out = bytearray(repoint(bytes(out), HEAD_CLOTH_LITERALS, HEAD_CLOTH, cloth))
    if needs.weapons:
        paths, table = layout.address("felyne_sound_paths"), layout.address("felyne_sound_table")
        if struct.unpack_from("<I", out, SOUND_PATH_LITERALS[0] - CODE_BASE)[0] == table:
            added = sound_paths(needs.weapons)
            for model in needs.weapons:
                at = (model - FIRST_MODEL) * SOUND_SLOT
                out[paths + at - CODE_BASE:paths + at + SOUND_SLOT - CODE_BASE] = added[at:at + SOUND_SLOT]
                struct.pack_into("<I", out, table + 4 * model - CODE_BASE, paths + at)
        else:
            layout.place(out, "felyne_sound_paths", sound_paths(needs.weapons))
            layout.place(out, "felyne_sound_table", moved_sound_table(code, needs.weapons, paths), pointers=True)
            out = bytearray(repoint(bytes(out), SOUND_PATH_LITERALS, SOUND_PATHS, table))
    return bytes(out)
