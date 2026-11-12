"""The models pack in a run (option mhgen_models): the pack prepared from MH XX's
files and MH4U's and cached, its archives written into the mod folder (and listed, so a later run can remove them), and
the looks it adds to the model shuffle and to layered equipment (looks.py): the catalog of XX's armor series and
weapons, named by the curated names file. No Generations file is read.

Preparing reads every equipment archive of both games (about 30 s), so the result is cached by the ROMs' paths,
sizes and modification times (cached_pack).
"""

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from core.game.files.arc import parse_arc
from core.app.edition import edition, migrate_legacy_user_folder
from core.game.executable.romfs import RomFS
from core.randomizer.equipment.models import ExtraModels
from core.equipment.mhgen import convert, equipment_pack as pack, looks, tables
from core.equipment.mhgen.equipment_pack import PackModel
from core.equipment.mhgen.gear_data import XX_FORMAT
from core.equipment.mhgen.looks import CLASS_KEYS, PART_KEYS, GenCatalog, GenLooks
from core.equipment.mhgen.tables import ExecutableNeeds

CACHE_VERSION = 12  # raise it when the plan, the needs or the catalog change for the same games (7: the pack from
                   # XX's files, with the table of ids and the model's game kept; 8: the catalog from XX, named by
                   # looks_names.json, whose bytes are part of the key; 9: every XX-only look in the pack;
                   # 10: a pack piece with no sound of its own is silent; 11: the catalog keeps XX's forge prices;
                   # 12: and XX's default colours of the pieces)
RESIDENT = "loc/arc/resident.arc"  # MHGen's, with the weapons' pwl and the armor series (XX's: XX_FORMAT.resident)
MANIFEST = "mhgen_pack_files.txt"  # in the mod folder: the archives the pack wrote into romfs/data
DATA_DIR = Path("romfs") / "data"


@dataclass(frozen=True)
class PreparedPack:
    plan: tuple[PackModel, ...]
    needs: ExecutableNeeds
    catalog: GenCatalog = GenCatalog((), ())  # XX's armor series and weapons that have names (looks.read_catalog)
    same: dict = field(default_factory=dict)  # equipment_pack.identical_models

    def extra_models(self) -> ExtraModels:
        """The looks the pack adds, for the model shuffle: a pack armor model is a set named after MHGen's id."""
        weapons: dict[str, list[int]] = {}
        armor: dict[str, dict[str, int]] = {}
        for p in self.plan:
            if p.slot in PART_KEYS:
                armor.setdefault(PART_KEYS[p.slot], {})[f"mhgen{p.source}"] = p.model
            else:
                weapons.setdefault(CLASS_KEYS[p.slot], []).append(p.model)
        return ExtraModels({key: tuple(models) for key, models in weapons.items()}, armor)

    def gen_looks(self) -> GenLooks:
        """The pack's looks for layered equipment."""
        return looks.gen_looks(self.catalog, self.plan, self.same)

    def to_json(self) -> dict:
        needs = self.needs
        return {"version": CACHE_VERSION,
                "plan": [[p.slot, p.source, p.model, p.game] for p in self.plan],
                "donors": [[*key, value] for key, value in needs.donors.items()],
                "effects": [[*key, value.hex()] for key, value in needs.effects.items()],
                "hair": [[*key, value] for key, value in needs.hair.items()],
                "cloth": [[*key, value] for key, value in needs.cloth.items()],
                "hair_shown": [[*key, list(value)] for key, value in needs.hair_shown.items()],
                "armor_sounds": [[*key, value] for key, value in needs.armor_sounds.items()],
                "catalog": self.catalog.to_json(),
                "same": [[*key, *value] for key, value in self.same.items()]}

    @classmethod
    def from_json(cls, data: dict) -> "PreparedPack":
        if data.get("version") != CACHE_VERSION:
            raise ValueError("a pack cache of another version")
        needs = ExecutableNeeds(donors={(c, m): d for c, m, d in data["donors"]},
                                effects={(c, m): bytes.fromhex(e) for c, m, e in data["effects"]},
                                hair={(g, m): d for g, m, d in data["hair"]},
                                cloth={(g, part, m): bits for g, part, m, bits in data["cloth"]},
                                hair_shown={(g, m): tuple(shown) for g, m, shown in data["hair_shown"]},
                                armor_sounds={(g, part, m): s for g, part, m, s in data["armor_sounds"]})
        return cls(tuple(PackModel(*p) for p in data["plan"]), needs, GenCatalog.from_json(data["catalog"]),
                   {(slot, source): tuple(models) for slot, source, *models in data["same"]})


def _shaders(gen, m4):
    """The shader records of `gen` (the RomFS the models are made from; None: not given) and `m4`."""
    return (convert.shader_records(gen.read(pack.SHADER_PACKAGE)) if gen is not None else None,
            convert.shader_records(m4.read(pack.SHADER_PACKAGE)))


def prepare_pack(xx, m4, ids: pack.PackIds | None = None, names: Mapping | None = None) -> PreparedPack:
    """The pack of MH XX's romfs `xx` for MH4U's `m4` (RomFS): its plan (the table of ids, equipment_pack.plan_pack),
    without the weapons whose moving parts MH4U cannot play, what the executable needs for it, the models the plan
    left out as identical and the catalog of the looks (`names`: looks.load_names() by default). `ids`: another table
    of ids than the curated one."""
    shaders = _shaders(xx, m4)
    m4_signatures = pack.mh4u_signatures(m4)
    signatures = pack.mhgen_signatures(xx, shaders)
    resident = parse_arc(xx.read(XX_FORMAT.resident))
    records = tables.pwl_records(resident)
    plan = pack.plan_pack(signatures, m4_signatures, tables.gimmickless(records, signatures, m4_signatures), ids)
    cloth = {}
    for p in plan:
        if p.slot in pack.ARMOR_PARTS:
            for gender in pack.GENDERS:
                source = parse_arc(xx.read(pack.mhgen_armor_file(gender, p.slot, p.source)))
                if flags := pack.cloth_flags(p.slot, source):  # conversion keeps the cloth files
                    cloth[(gender, p.slot, p.model)] = flags
    sounds = tables.mhgen_armor_sounds(resident, XX_FORMAT.series_size, XX_FORMAT.series_shift)
    needs = tables.executable_needs(plan, records, m4_signatures, tables.mhgen_hair_flags(xx), cloth,
                                    tables.hair_groups(m4), sounds)
    same = pack.identical_models(signatures, m4_signatures, plan)
    return PreparedPack(tuple(plan), needs, looks.read_catalog(xx, names), same)


def default_cache_dir() -> Path:
    """`MH4U_RANDO_CACHE`, else `cache` in the edition's folder under the home (an earlier name's folder is copied
    there first, `edition.migrate_legacy_user_folder`)."""
    if "MH4U_RANDO_CACHE" in os.environ:
        return Path(os.environ["MH4U_RANDO_CACHE"])
    migrate_legacy_user_folder()
    return edition().home / "cache"


def cached_pack(xx_rom: Path, mh4u_rom: Path, cache_dir: Path | None = None,
                open_romfs: Callable[[Path], object] = RomFS) -> PreparedPack:
    """prepare_pack of the ROMs, from `cache_dir` when it holds it for these files (path, size, time) and the names
    files' bytes (names, table of ids)."""
    roms = [xx_rom, mh4u_rom]
    key = ([CACHE_VERSION] + [[str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns] for p in roms]
           + [hashlib.sha256(path.read_bytes()).hexdigest() for path in (looks.NAMES_FILE, pack.PACK_IDS_FILE)])
    name = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
    path = (cache_dir or default_cache_dir()) / f"mhgen_pack_{name}.json"
    if path.is_file():
        try:
            return PreparedPack.from_json(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError):
            pass  # an older or broken cache: prepared again
    prepared = prepare_pack(open_romfs(xx_rom), open_romfs(mh4u_rom))
    path.parent.mkdir(parents=True, exist_ok=True)
    # Whole or not at all: another process (a test worker, a second window) may read it meanwhile. No lock: one left by
    # a program closed while preparing would hold up every later build; two preparing at once only repeat the work.
    partial = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    partial.write_text(json.dumps(prepared.to_json()), encoding="utf-8")
    os.replace(partial, path)
    return prepared


def pack_file_names(mod_dir: Path) -> set[str]:
    """The names of the archives in `mod_dir`/romfs/data that its pack wrote (MANIFEST)."""
    manifest = mod_dir / MANIFEST
    return {Path(name).name for name in manifest.read_text(encoding="utf-8").split()} if manifest.is_file() else set()


def remove_pack_files(mod_dir: Path) -> None:
    """Delete the archives an earlier run's pack wrote (its MANIFEST) and the manifest."""
    for name in pack_file_names(mod_dir):
        (mod_dir / DATA_DIR / name).unlink(missing_ok=True)
    (mod_dir / MANIFEST).unlink(missing_ok=True)


def plan_file_names(plan) -> list[str]:
    """The names of the archives a plan's models are written to (romfs/data): two for an armor model, one for a
    weapon's."""
    folders = {cls: folder for folder, cls in pack.WEAPON_FOLDERS.items()}
    names = []
    for p in plan:
        files = ([pack.mh4u_armor_file(g, p.slot, p.model) for g in pack.GENDERS] if p.slot in pack.ARMOR_PARTS
                 else [pack.mh4u_weapon_file(folders[p.slot], p.model)])
        names += [file.split("/")[-1] for file in files]
    return names


def write_pack_files(mod_dir: Path, gen, m4, prepared: PreparedPack, xx=None, sources: dict | None = None) -> list[str]:
    """Write the pack's archives into `mod_dir`/romfs/data, replacing an earlier pack, and list them. `xx`: MH XX's
    RomFS, for the models of game "xx" (all of the pack's); `gen`: MH Generations', for those of game "gen" (the
    gear's static weapons), None when the plan has none. `sources` receives the MH XX files each archive was made
    from (equipment_pack.write_pack)."""
    remove_pack_files(mod_dir)
    data_dir = mod_dir / DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    names = plan_file_names(prepared.plan)
    # LF on every system: the web page's mod is the program's, byte for byte
    (mod_dir / MANIFEST).write_bytes("".join(f"{name}\n" for name in names).encode("utf-8"))
    pack.write_pack(data_dir, gen, m4, list(prepared.plan), _shaders(gen, m4), xx, sources)
    return names
