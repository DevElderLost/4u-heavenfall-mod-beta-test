"""User-facing options of a run: the randomizer's and the player's own.

They live outside `randomizer/` so that the GUI, the installer and an edition without the randomizer
 load them alone.

`Settings` is a plain dataclass so it can be saved and loaded as a JSON preset
and edited by the GUI. Every option is documented where it is declared.

Defaults are as close to the original game as possible: every switch off and
every mode on its least random value (also the first choice shown in the GUI).
The two master switches (`randomize_quests`, `randomize_equipment`) are on by
default; with every option under them off they change nothing either.
"""

import json
from dataclasses import asdict, dataclass, field, fields, replace
from enum import Enum
from pathlib import Path

from core.cheats.aspect_table import OFF as ASPECT_OFF, interface_size, load_ratios


class StructureMode(str, Enum):
    """Number of waves and of monsters per wave."""
    KEEP = "keep"                            # same structure as the original quest
    KEEP_PROGRESSION = "keep_progression"    # keep it only in key and urgent quests
    RANDOM = "random"                        # random structure everywhere


class DuplicateMode(str, Enum):
    """Whether the same species may appear more than once in a quest."""
    NEVER = "never"
    ALLOWED = "allowed"
    # Retired (the GUI no longer offers it): every slot that comes from the same original monster gets the same new
    # one, so a random structure built from a one-monster quest repeats it in every slot (4 Tetsucabras). Kept only so
    # games made with it, the old default, still load and regenerate in fix mode.
    ONLY_IF_ORIGINAL = "only_if_original"


class ProgressionMode(str, Enum):
    """How the difficulty tier of new monsters is chosen."""
    PROGRESSIVE = "progressive"  # weighted by quest rank (curated/progression.json)
    BALANCED = "balanced"        # within ±2 tiers of the replaced monster
    NONE = "none"                # any tier, uniformly


class Frequency(str, Enum):
    """How often a category of maps may be chosen."""
    NORMAL = "normal"
    RARE = "rare"
    NEVER = "never"


class FrenzyChance(str, Enum):
    """Chance that each large monster able to carry the Frenzy virus does (tuning.json, quests.frenzy_chance_*)."""
    NEVER = "never"
    RARE = "rare"      # 2 %
    COMMON = "common"  # 6 %


class RewardSource(str, Enum):
    QUEST_MONSTERS_AND_RANK = "quest_monsters_and_rank"  # some materials from the quest's monsters
    RANK = "rank"                                        # any gear material of the quest's rank


class SubQuestMode(str, Enum):
    KEEP = "keep"            # original sub quests (re-pointed only if their monster left the quest)
    DISABLE = "disable"      # remove sub quests
    RANDOMIZE = "randomize"  # break a part of one of the quest's (non-intruder) monsters


class TextMode(str, Enum):
    KEEP = "keep"                    # leave texts untouched
    REPLACE_NAMES = "replace_names"  # swap monster names inside the original texts
    # names with the right articles + objective and failure text written like the retail ones
    REGENERATE = "list_monsters"
    LIST_MONSTERS = REGENERATE       # old name (the value stays "list_monsters" so presets keep working)


class StatMode(str, Enum):
    KEEP = "keep"
    PERCENT = "percent"  # ±20 %, bell curve centred on "no change"
    RANGE = "range"      # anywhere between the min and max of the same class/part and rank


class ArmorSkillMode(str, Enum):
    KEEP = "keep"
    SAME_SUM = "same_sum"  # same total points per piece, spread over random skills
    CHAOTIC = "chaotic"    # random skills and points on every piece


class ModelMode(str, Enum):
    FAMILIES = "families"  # whole lines/sets take the look of another line/set, in order
    CHAOTIC = "chaotic"    # any model of the same weapon class / armor part


class PalicoModelMode(str, Enum):
    FULL_SET = "full_set"    # a theme's weapon, head and body take the look of another theme together
    SEPARATE = "separate"    # weapons among themselves, armor sets among themselves
    CHAOTIC = "chaotic"      # any model of the same kind of piece


class AlatreonMode(str, Enum):
    """Where Alatreon is met (core/monsters/alatreon)."""
    OFF = "off"
    FINAL_BOSS = "final_boss"    # his quest takes the place of Gogmazios' urgent quest (monsters/alatreon/quest.py)
    EXTRA_QUEST = "extra_quest"  # a quest of his own, after Gogmazios' urgent quest is cleared
    RANDOMIZED = "randomized"    # a top tier monster of the quest randomizer (randomize_monsters)
    # Retired (the GUI no longer offers it): his quest takes the place of the rank 1 quest 10110, the option
    # `alatreon` of the first versions (`true`). Kept so the games made with it still load and regenerate in fix mode.
    FIELD_TRIP = "field_trip"


RETIRED_ALATREON_MODES = (AlatreonMode.FIELD_TRIP,)  # loaded and regenerated, never offered


class MizutsuneMode(str, Enum):
    """Where Mizutsune is met (core/monsters/mizutsune/mizutsune_quests.py)."""
    OFF = "off"
    QUESTS = "quests"            # three Gathering Hall quests of his own on the Primal Forest: 3★, 6★ and G★1
    RANDOMIZED = "randomized"    # one tier above Zinogre among the randomized monsters, without his quests
    EXTENDED = "extended"        # his quests, randomized as any quest, and he joins the randomized monsters


class GlavenusMode(str, Enum):
    """Where Glavenus is met (core/monsters/glavenus/glavenus_quests.py)."""
    OFF = "off"
    QUESTS = "quests"            # four Gathering Hall quests of his own: 3★, 6★ and G★1 on the Volcanic Hollow, and G★2
    #                              with Mizutsune on the Sunken Hollow (only while Mizutsune is in the mod too)
    RANDOMIZED = "randomized"    # tier 4 among the randomized monsters, without his quests
    EXTENDED = "extended"        # his quests, randomized as any quest, and he joins the randomized monsters


class GreatMaccaoMode(str, Enum):
    """Where Great Maccao (from MH XX) is met (core/monsters/great_maccao/great_maccao_quests.py)."""
    OFF = "off"
    QUESTS = "quests"            # three Gathering Hall quests of his own on the Primal Forest: 2★, 4★ and G★1
    RANDOMIZED = "randomized"    # tier 1 among the randomized monsters, without his quests
    EXTENDED = "extended"        # his quests, randomized as any quest, and he joins the randomized monsters


class ValstraxMode(str, Enum):
    """Where Valstrax (from MH XX) is met (core/monsters/valstrax/valstrax_quests.py)."""
    OFF = "off"
    QUESTS = "quests"            # two Gathering Hall quests of his own on the Tower Summit: ★7 and G★3
    RANDOMIZED = "randomized"    # tier 7 among the randomized monsters, without his quests
    EXTENDED = "extended"        # his quests, randomized as any quest, and he joins the randomized monsters


class AstalosMode(str, Enum):
    """Where Astalos (from MH XX) is met (core/monsters/astalos/astalos_quests.py)."""
    OFF = "off"
    QUESTS = "quests"            # three Gathering Hall quests of his own on the Ancestral Steppe: 3★, 6★ and G★1
    RANDOMIZED = "randomized"    # tier 3 among the randomized monsters, without his quests
    EXTENDED = "extended"        # his quests, randomized as any quest, and he joins the randomized monsters


class DeviantMode(str, Enum):
    """Where a Deviant (Boltreaver Astalos, Hellblade Glavenus, Soulseer Mizutsune: MH XX's variant 4 of a ported base)
    is met; one enum for the three (core/monsters/porting/spec.py BOLTREAVER, HELLBLADE, SOULSEER; docs/monsters/
    deviants.md, "V4: identity")."""
    OFF = "off"
    QUESTS = "quests"            # his one Gathering Hall quest (G★3 for now)
    RANDOMIZED = "randomized"    # tier 6 among the randomized monsters, without his quest
    EXTENDED = "extended"        # his quest, randomized as any quest, and he joins the randomized monsters


@dataclass(frozen=True)
class PortedOption:
    """The option of one ported monster: an entry of PORTED_OPTIONS, the one place that names the
    monsters whose option the code treats alike. A monster's `Settings` field is named `key`, which is his spec's key
    (monsters/porting/spec.py); the
    generic code finds his files by it: `alatreon/<key>_quests.py` (`TABLE`, when `quests` is set) and
    `alatreon/<key>_monster.py` (`RECORD`, when `pool` is set)."""
    key: str
    name: str                                    # as messages show it
    modes: type[Enum]                            # his option's enum, its `off` the field's default
    off: Enum
    pool: Enum | None = None                     # the mode that puts him among the randomized monsters: it needs
    #                                              randomize_quests and randomize_monsters, else it counts as `off`
    # the mode that adds his quest table (monsters/porting/ported_quests.py)
    quests: Enum | None = None
    extended: Enum | None = None                 # the mode that adds his quests AND randomizes them as any quest (with
    #                                              randomize_quests; off, it is `quests`) AND puts him among the
    #                                              randomized monsters (as `pool`, with randomize_quests and
    #                                              randomize_monsters)
    builds: tuple[Enum, ...] | None = None       # the modes that build him (files and code); None: all but `off`
    retired: tuple[Enum, ...] = ()               # modes loaded and regenerated, never offered (CLI, GUI)
    cli_help: str = ""                           # the help of his flag `--<key>`
    base: str = ""                               # a Deviant's base monster (his key): the Deviant is off whenever
    #                                              the base's mode is off (Settings.mode_of)
    game: str = "xx"                             # the game he is ported from (spec.game, monsters/porting/spec.py):
    #                                              MH XX, whose decrypted .3ds a run needs

    def __post_init__(self):
        if self.builds is None:
            object.__setattr__(self, "builds", tuple(mode for mode in self.modes if mode is not self.off))


# One entry per ported monster, in the order of the code space's packing (spec.BUILT) and of the executable's new quest
# list (gameplay/quests/new_quests.NEW_QUESTS, which only grows at the end): a third monster is a field, an enum and an
# entry here.
PORTED_OPTIONS: tuple[PortedOption, ...] = (
    PortedOption(
        "alatreon", "Alatreon", AlatreonMode, AlatreonMode.OFF, pool=AlatreonMode.RANDOMIZED,
        retired=RETIRED_ALATREON_MODES,
        cli_help="add Alatreon from MH XX (switches the additional monsters on): in Gogmazios' urgent quest, "
                 "in a quest of his own, or among the randomized monsters (needs --rom and --xx-rom, "
                 "MH XX's decrypted .3ds)",
        game="xx"),
    PortedOption(
        "mizutsune", "Mizutsune", MizutsuneMode, MizutsuneMode.OFF, pool=MizutsuneMode.RANDOMIZED,
        quests=MizutsuneMode.QUESTS, extended=MizutsuneMode.EXTENDED,
        cli_help="add Mizutsune from MH XX (switches the additional monsters on): three quests of his own on "
                 "the Primal Forest (low rank 3 stars, high rank 6 stars and G rank 1 star), only among the "
                 "randomized monsters, or `extended`: his quests, randomized like any quest, and among the "
                 "randomized monsters (needs --rom and --xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    PortedOption(
        "glavenus", "Glavenus", GlavenusMode, GlavenusMode.OFF, pool=GlavenusMode.RANDOMIZED,
        quests=GlavenusMode.QUESTS, extended=GlavenusMode.EXTENDED,
        cli_help="add Glavenus from MH XX (switches the additional monsters on): four quests of his own on "
                 "the Volcanic Hollow (low rank 3 stars, high rank 6 stars, G rank 1 star) and, with --mizutsune, "
                 "G rank 2 stars with Mizutsune on the Sunken Hollow, only among the randomized monsters, "
                 "or `extended`: his quests, randomized like any quest, and among the randomized monsters "
                 "(needs --rom and --xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    PortedOption(
        "great_maccao", "Great Maccao", GreatMaccaoMode, GreatMaccaoMode.OFF, pool=GreatMaccaoMode.RANDOMIZED,
        quests=GreatMaccaoMode.QUESTS, extended=GreatMaccaoMode.EXTENDED,
        cli_help="add Great Maccao from MH XX (switches the additional monsters on): three quests of his own on "
                 "the Primal Forest (low rank 2 stars, high rank 4 stars, G rank 1 star), only among the "
                 "randomized monsters, or `extended`: his quests, randomized like any quest, and among the "
                 "randomized monsters (needs --rom and --xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    PortedOption(
        "valstrax", "Valstrax", ValstraxMode, ValstraxMode.OFF, pool=ValstraxMode.RANDOMIZED,
        quests=ValstraxMode.QUESTS, extended=ValstraxMode.EXTENDED,
        cli_help="add Valstrax from MH XX (switches the additional monsters on): two quests of his own on "
                 "the Tower Summit (high rank 7 stars and G rank 3 stars), only among the randomized "
                 "monsters, or `extended`: his quests, randomized like any quest, and among the randomized "
                 "monsters (needs --rom and --xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    # Astalos has no installer or GUI option: he will be fixed on in both presets (curated/gui_presets.json `fixed`, as
    # Great Maccao) once phase G puts him in spec.BUILT; until then a run that asks for him is refused
    PortedOption(
        "astalos", "Astalos", AstalosMode, AstalosMode.OFF, pool=AstalosMode.RANDOMIZED,
        quests=AstalosMode.QUESTS, extended=AstalosMode.EXTENDED,
        cli_help="add Astalos from MH XX (switches the additional monsters on): three quests of his own on "
                 "the Ancestral Steppe (low rank 3 stars, high rank 6 stars and G rank 1 star), only among the "
                 "randomized monsters, or `extended`: his quests, randomized like any quest, and among the "
                 "randomized monsters (needs --rom and --xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    # The Deviants: no installer or GUI option, fixed on like Astalos once each is in
    # spec.BUILT (the link tasks flip curated/gui_presets.json), and off whenever the base is off. Order: Boltreaver,
    # Hellblade, Soulseer.
    # `quests` and `extended` (`core/monsters/<key>/<key>_quests.TABLE`) and `pool` (`<key>_monster.RECORD`) are set
    # (QP task); the presets keep them off until the link tasks flip them.
    PortedOption(
        "boltreaver", "Boltreaver Astalos", DeviantMode, DeviantMode.OFF, base="astalos",
        pool=DeviantMode.RANDOMIZED, quests=DeviantMode.QUESTS, extended=DeviantMode.EXTENDED,
        cli_help="add Boltreaver Astalos from MH XX (switches the additional monsters on): a quest of his own, "
                 "only among the randomized monsters, or `extended`; off while --astalos is off (needs --rom and "
                 "--xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    PortedOption(
        "hellblade", "Hellblade Glavenus", DeviantMode, DeviantMode.OFF, base="glavenus",
        pool=DeviantMode.RANDOMIZED, quests=DeviantMode.QUESTS, extended=DeviantMode.EXTENDED,
        cli_help="add Hellblade Glavenus from MH XX (switches the additional monsters on): a quest of his own, "
                 "only among the randomized monsters, or `extended`; off while --glavenus is off (needs --rom and "
                 "--xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
    PortedOption(
        "soulseer", "Soulseer Mizutsune", DeviantMode, DeviantMode.OFF, base="mizutsune",
        pool=DeviantMode.RANDOMIZED, quests=DeviantMode.QUESTS, extended=DeviantMode.EXTENDED,
        cli_help="add Soulseer Mizutsune from MH XX (switches the additional monsters on): a quest of his own, "
                 "only among the randomized monsters, or `extended`; off while --mizutsune is off (needs --rom and "
                 "--xx-rom, MH XX's decrypted .3ds)",
        game="xx"),
)


def ported_options() -> tuple[PortedOption, ...]:
    """The registry (PORTED_OPTIONS, read when called)."""
    return PORTED_OPTIONS


def ported_option(key: str) -> PortedOption:
    """The entry of the monster `key` (KeyError when he has none)."""
    for option in ported_options():
        if option.key == key:
            return option
    raise KeyError(f"{key}: not in the ported monsters' options ({', '.join(o.key for o in ported_options())})")


class AlatreonMusic(str, Enum):
    """Alatreon's music (core/music/mhw/music.py)."""
    ORIGINAL = "original"  # his own theme from MH XX; alatreon_slain_theme when his death ends the quest
    MODERN = "modern"      # World's alatreon_battle_theme, Proof of a Hero at 10 % health, then Fatalis' slain theme


class HudScale(str, Enum):
    """Size of the top-screen HUD in % (core/interface/hud)."""
    FULL = "100"
    P90 = "90"
    P80 = "80"
    P70 = "70"
    P60 = "60"

    @property
    def factor(self) -> float:
        return int(self.value) / 100


class Cheat3D(str, Enum):
    """The "3D off" cheat (core/cheats/cheats.py): the game's own 3D, or 3D forced off with the
    dithering off or on."""
    OFF = "off"
    DITHER_OFF = "dither_off"
    DITHER_ON = "dither_on"


class CheatFps(str, Enum):
    """The frame rate cheat (core/cheats/cheats.py): the game's own, or a fixed rate."""
    GAME = "off"
    F30 = "30"
    F35 = "35"                # every 5 between 30 and 60: the frames alternate one and two vsyncs
    F40 = "40"
    F45 = "45"
    F50 = "50"
    F55 = "55"
    F60 = "60"                # higher rates did not work in Azahar

    @classmethod
    def _missing_(cls, value):
        # 90 to 240, offered once and taken out: a saved one loads as the highest rate that works
        return cls.F60 if str(value).isdigit() and int(value) > 60 else None

    @property
    def rate(self) -> int:
        """Frames per second; 0 for the game's own."""
        return 0 if self is CheatFps.GAME else int(self.value)


# Options that need the game executable (they patch exefs/code.bin).
EQUIPMENT_SWITCHES = ("randomize_recipes", "randomize_weapon_stats", "randomize_armor_stats", "randomize_models",
                      "randomize_palico_recipes", "randomize_palico_weapon_stats", "randomize_palico_armor_stats",
                      "randomize_palico_models")

# Options each player chooses for themselves: they change neither quests nor equipment, so two friends playing the
# same seed may differ in them (they are left out of the fix checksum, core/app/fix.py). The monster icons only
# change quest board pictures, which the checksum ignores.
# The shape of the emulator's picture (core/cheats/aspect_ratio.py): off, or one of the
# curated ratios. A str enum, as the other cheats' are
CheatAspect = Enum("CheatAspect", {"OFF": ASPECT_OFF, **{f"R{ratio.name.replace(':', '_')}": ratio.name
                                                         for ratio in load_ratios()}}, type=str)

PERSONAL_FIELDS = ("hud_scale", "new_monster_icons", "touchless_target", "single_screen", "starting_kit",
                   "skip_intro", "skip_caravan_tutorial", "fast_text", "fast_gathering", "hold_a", "camera_speed",
                   "box_equipment", "system_keyboard", "damage_numbers",
                   "layered_equipment", "layered_by_rank", "rare_exchange", "quality_of_life", "mhw_fatalis_music",
                   "alatreon_music",
                   "cheat_3d_mode",
                   "cheat_no_bloom_dof", "cheat_fps",
                   "cheat_fov", "cheat_net_fix", "cheat_insta_kill", "cheat_raw_unbloat",
                   "cheat_aspect_allowed", "cheat_aspect_ratio")

# Options a real 3DS does not get: the GUI hides them on the 3DS platform
# (gui/options.py, Option.emulator_only), a 3DS run takes their defaults (Settings.for_console) and the START menu's
# page has no row for them (mod_options.available_options): the HUD size and the touchless target; the ported monsters
# (Alatreon, Mizutsune, Glavenus) go to a 3DS too; the cheats are emulator only. Single-screen mode moves layouts
# between the screens, which only the emulator's single screen view needs.
EMULATOR_ONLY = ("hud_scale", "touchless_target", "single_screen", "cheat_3d_mode", "cheat_no_bloom_dof", "cheat_fps",
                 "cheat_fov", "cheat_net_fix", "cheat_insta_kill", "cheat_raw_unbloat",
                 "cheat_aspect_allowed", "cheat_aspect_ratio", "system_keyboard")

# The value a gameplay setting takes when a settings file predates it, as saved by to_dict(): the one that gives
# what the older version made. Only needed when that is not the field's default.
LEGACY_VALUES: dict[str, object] = {"free_cutscene_monsters": False, "monster_routes": False}

# Gameplay settings that are no option: what a run made, recorded in its settings file. The GUI has no widget for
# them and carries the loaded file's value, so a fix keeps its game's (pipeline.run sets them in a new run).
RECORDED_FIELDS = ("free_cutscene_monsters",)

# The old default of a gameplay setting whose default changed, as saved by to_dict(). Every settings file has the
# field, so nothing is loaded with it; it stays the neutral value of the checksum code, so the games made with the
# old default keep their code.
OLD_DEFAULTS: dict[str, object] = {"duplicates": DuplicateMode.ONLY_IF_ORIGINAL.value}


@dataclass
class Settings:
    seed: str = ""

    # Master switch of every quest option below (up to "Equipment"); off, quest01.arc is left as it is
    randomize_quests: bool = True

    # Large monsters
    randomize_monsters: bool = False
    structure: StructureMode = StructureMode.KEEP
    duplicates: DuplicateMode = DuplicateMode.NEVER
    progression: ProgressionMode = ProgressionMode.BALANCED
    adjust_stats: bool = False           # health index closest to the replaced monster's health; attack index kept
    # Intro cutscene monsters (the Fatalis, Akantor...) may open a quest on any map: an executable patch skips
    # their cutscene off its map (core/gameplay/intro_cutscenes/intro_cutscenes.py). No option: every new run asks for
    # it (pipeline.run), and turns it off when it cannot patch them; the settings file keeps what its game got, for
    # fixes
    free_cutscene_monsters: bool = True
    # Frenzy virus: each large monster of a species that can be frenzied
    # (and is not Apex) rolls this chance on its own; the retail frenzied slots keep their Frenzy unless keep_frenzy
    # is off. Own random stream "frenzy"
    frenzy_chance: FrenzyChance = FrenzyChance.NEVER
    keep_frenzy: bool = True

    # Maps
    randomize_maps: bool = False
    arena_maps: Frequency = Frequency.NEVER
    everwood: Frequency = Frequency.NEVER
    always_music: bool = True            # avoid silent maps unless a monster brings its theme
    one_monster_per_wave_on_arenas: bool = True
    # Monsters change area on any field map: placed only where they can, and given the reference routes where
    # they have none. Needs the ROM; without it the pipeline turns it off
    monster_routes: bool = True

    # Objectives and text
    sub_quests: SubQuestMode = SubQuestMode.KEEP
    text: TextMode = TextMode.KEEP
    # A quest whose only target is one capturable monster, alone in one wave, becomes a capture quest with the
    # chance quests.capture_quest_chance (tuning.json). Own random stream "capture"
    capture_quests: bool = False

    # Rewards and supplies
    randomize_rewards: bool = False
    reward_source: RewardSource = RewardSource.QUEST_MONSTERS_AND_RANK
    randomize_supplies: bool = False     # the Map is always kept; boxes are sorted (Map, item id, empty slots)
    gunner_supplies: bool = False        # at least 4 slots get different ammo / coatings in full stacks

    # Other monsters
    randomize_small_monsters: bool = False
    randomize_intruders: bool = False

    # Equipment (patches the game executable)
    randomize_equipment: bool = True     # master switch of every hunter and Felyne equipment option below
    randomize_recipes: bool = False      # materials of the equipment's rank (equipment/recipes.py: fixed rules)
    randomize_weapon_stats: bool = False
    weapon_attack: StatMode = StatMode.KEEP
    weapon_affinity: StatMode = StatMode.KEEP
    weapon_element: StatMode = StatMode.KEEP     # element / status value
    weapon_element_type: bool = False               # change the element / status of weapons that have one
    weapon_element_add_remove: bool = False         # weapons may gain or lose their element / status
    weapon_defense: StatMode = StatMode.KEEP
    weapon_slots: StatMode = StatMode.KEEP
    weapon_sharpness: StatMode = StatMode.KEEP
    weapon_upgrades_improve: bool = False       # upgrades beat the weapon they come from (within the rank cap)
    weapon_upgrades_keep_element: bool = False  # natural evolutions inherit the element/status
    randomize_armor_stats: bool = False
    armor_defense: StatMode = StatMode.KEEP
    armor_resistances: StatMode = StatMode.KEEP
    armor_slots: StatMode = StatMode.KEEP
    armor_skills: ArmorSkillMode = ArmorSkillMode.KEEP
    armor_skill_min_points: int = 0       # per positive skill (0 counts as 1)
    armor_skill_max_points: int = 10      # per positive skill
    armor_skill_max_count: int = 3        # skills per piece, 1 to 5 (format limit)
    armor_skills_no_negative: bool = False
    armor_skills_shared_variants: bool = False  # Blademaster/Gunner versions of a piece share their new skills
    randomize_models: bool = False
    model_mode: ModelMode = ModelMode.FAMILIES
    models_use_each_once: bool = False
    # the models pack (made from MH XX's files) joins the model shuffle and layered equipment's looks
    mhgen_models: bool = False
    allow_op_equipment: bool = False      # no stat limits: the game accepts quests with any worn gear

    # Felyne (Palico) equipment
    randomize_palico_recipes: bool = False
    randomize_palico_weapon_stats: bool = False
    palico_weapon_attack: StatMode = StatMode.KEEP       # melee; ranged (boomerang) keeps the same proportion
    palico_weapon_affinity: StatMode = StatMode.KEEP
    palico_weapon_element: StatMode = StatMode.KEEP
    palico_weapon_defense: StatMode = StatMode.KEEP
    palico_weapon_element_type: bool = False
    palico_weapon_element_add_remove: bool = False
    randomize_palico_armor_stats: bool = False
    palico_armor_defense: StatMode = StatMode.KEEP
    palico_armor_resistances: StatMode = StatMode.KEEP
    randomize_palico_models: bool = False
    palico_model_mode: PalicoModelMode = PalicoModelMode.FULL_SET
    palico_models_use_each_once: bool = False

    # Interface (game files and executable patches, not randomized)
    hud_scale: HudScale = HudScale.FULL  # each top-screen HUD element shrinks towards its corner
    # No "?" monster icon: Fatalis and Gogmazios icons (needs the ROM), Dalamadur's quests
    new_monster_icons: bool = True
    # Lock on without the touch screen: L + D-pad up locks / switches the large-monster target (with a hint in the
    # item selector) and the target camera panel's monster face is also shown on the top screen
    touchless_target: bool = False
    # Play seeing the top screen only: the touch screen's menus the player needs (the quest list, the Canteen's
    # ingredients, the yes / no boxes...) are shown on the top screen
    # (interface/single_screen/executable/single_screen.py, interface/single_screen/layout/single_screen.py)
    single_screen: bool = False
    # Holding B runs through the conversation windows: every page at once, the next one every other frame
    # (core/interface/fast_text/fast_text.py)
    fast_text: bool = False
    # Gathering, mining, bug catching, carving and fishing GATHER_SPEED times faster, on top of the Speed Gatherer
    # skill (core/gameplay/fast_gathering/fast_gathering.py)
    fast_gathering: bool = False
    # Holding A repeats it: in a quest with the weapon sheathed (picking up, gathering, mining, carving), and in the
    # quest rewards and the Wyporium's claim items panel, where A takes an item and the cursor goes on to the next
    # (core/gameplay/hold_a/hold_a.py)
    hold_a: bool = False
    # The camera's top turning speed with the buttons: the cap of how long a turn has been held, 10 the game's own
    # (core/interface/mod_settings/mod_options.py CAMERA_CAP; its values in curated/mod_settings.json)
    camera_speed: int = 10
    # Manage Equipment and Equipment Sets at every item box, not only at home (the Hall's box's lines:
    # curated/mod_settings.json; core/interface/mod_settings/mod_options.py BOX_LINES)
    box_equipment: bool = False
    # A number over the monster at each hit, as MH Wilds and Rise show (core/interface/damage_numbers/); its style,
    # size, duration and Show All Damage are the START menu's (curated
    # mod_settings.json)
    damage_numbers: bool = False
    # Names, chat and guild card texts are typed in the 3DS system keyboard, which the emulator shows as a text box for
    # the computer's keyboard (core/interface/system_keyboard/system_keyboard.py); emulator only. No edition offers it:
    # the emulation waits while the text box is open
    system_keyboard: bool = False
    # "Layered Equipment" at the Smithy: choose the look of each armor part and weapon class over what is worn
    # (core/equipment/layered/layered_equipment.py)
    layered_equipment: bool = False
    # With layered equipment: the forge-style screens offer the looks of the ranks the player has unlocked, and the
    # Wyporium's new trades open by rank too (low from the start, high after the Hall's star 3 urgent, G after the
    # urgent that opens Dundorma; curated layered_looks.json `rank_unlocks`). Off: every look and every new trade from
    # the start. The GUI starts with it on
    # (curated/gui_defaults.json).
    layered_by_rank: bool = False
    # "Rare Materials Exchange" at the Wyporium: hand over a number of the items of the monsters that drop a rare
    # material, on a screen of its own, and get that material (core/gameplay/wyporium/rare_exchange.py)
    rare_exchange: bool = False
    # The switch of an edition's quality-of-life module (gui_presets.json `install.modules`; core/app/presets.py
    # apply_modules): off, the controls, fast text, the item boxes and the cheats of that module take the game's own
    # values and leave the START menu's page. An edition without modules fixes it on
    quality_of_life: bool = True
    # Monster Hunter World's music for Black and Crimson Fatalis: its battle theme, phase 2 from half health, Proof of
    # a Hero from 10 %, its slain theme when that death ends the quest (core/music/mhw/music.py)
    mhw_fatalis_music: bool = False

    # Cheats (emulator only; executable patches written from the players' cheat codes for 1.1: core/app/
    # cheats.py). The neutral values leave the game as it is; the GUI's defaults are in
    # curated/gui_defaults.json
    cheat_3d_mode: Cheat3D = Cheat3D.OFF  # 3D forced off, with the dithering off or on
    cheat_no_bloom_dof: bool = False      # no bloom and no depth of field
    cheat_fps: CheatFps = CheatFps.GAME   # the frame rate forced to a fixed value
    cheat_fov: int = 50                   # the camera's field of view in degrees; 50 is the game's own (untouched)
    cheat_net_fix: bool = False           # the online fix by Klark231
    cheat_insta_kill: bool = False        # debug: the hunter's attack multiplied (curated tuning.json, cheats)
    cheat_raw_unbloat: bool = False       # the menus show weapons' true attack; the damage does not change
    cheat_aspect_allowed: bool = False    # the GUI's switch before the ratios, still in testing (presets._expand)
    cheat_aspect_ratio: CheatAspect = CheatAspect.OFF  # the game fits the emulator's picture

    # New game (executable patch, not randomized)
    starting_kit: bool = True  # the developer's kit in the item box (game/data/curated/starting_kit.txt)
    # A new character starts in Val Habar registered with the Guild: no prologue on the sand ship, no arrival or
    # registration scenes
    skip_intro: bool = False
    # With skip_intro: the character also has the caravan tutorial done (the Caravaneer's talk and deliveries, quests
    # 11-24, 101 and 102 cleared, their story flags) and the first Palico equipped. Ignored without skip_intro
    skip_caravan_tutorial: bool = False

    # Additional monsters, from the player's MH XX ROM (core/monsters). Master switch: off, every option below is
    # ignored
    additional_monsters: bool = False
    # Alatreon: in Gogmazios' urgent quest, in a quest of his own, or among the randomized monsters
    alatreon: AlatreonMode = AlatreonMode.OFF
    alatreon_music: AlatreonMusic = AlatreonMusic.ORIGINAL  # his music, original or World's (personal)
    # Mizutsune: three quests of his own on the Primal Forest, one per rank
    mizutsune: MizutsuneMode = MizutsuneMode.OFF
    # Glavenus: three quests of his own on the Volcanic Hollow, one per rank, and one with Mizutsune on the Sunken
    # Hollow
    glavenus: GlavenusMode = GlavenusMode.OFF
    # Great Maccao, from the player's MH XX ROM: three quests of his own on the Primal Forest, one per rank
    great_maccao: GreatMaccaoMode = GreatMaccaoMode.OFF
    # Valstrax, from the player's MH XX ROM: two quests of his own on the Tower Summit (high rank and G rank)
    valstrax: ValstraxMode = ValstraxMode.OFF
    # Astalos, from the player's MH XX ROM: three quests of his own on the Ancestral Steppe, one per rank (no option in
    # the GUI: fixed on once he is built)
    astalos: AstalosMode = AstalosMode.OFF
    # The Deviants (no option in the GUI: fixed on once built, off while their base is off): the quest at G★3 for now
    boltreaver: DeviantMode = DeviantMode.OFF
    hellblade: DeviantMode = DeviantMode.OFF
    soulseer: DeviantMode = DeviantMode.OFF

    # Debug
    debug_weak_monsters: bool = False    # lowest health and attack index for every monster

    # Fixes of a game in progress (core/app/fix.py): quests drawn again with another sub-seed; equipment and the
    # quests not rerolled stay the same
    quest_reroll: int = 0                # every quest
    quest_rerolls: dict[int, int] = field(default_factory=dict)  # quest id -> times that quest was rerolled

    def emulator_only_changes(self) -> list[str]:
        """The EMULATOR_ONLY settings that are not at their defaults."""
        defaults = Settings()
        return [name for name in EMULATOR_ONLY if getattr(self, name) != getattr(defaults, name)]

    def for_console(self) -> "Settings":
        """These settings for a real 3DS: every EMULATOR_ONLY setting at its default."""
        defaults = Settings()
        return replace(self, **{name: getattr(defaults, name) for name in EMULATOR_ONLY})

    @property
    def aspect_on(self) -> bool:
        """The mod can change the picture's shape: the hooks and the list in the game, even at the game's own shape."""
        return self.cheat_aspect_allowed or self.cheat_aspect_ratio.value != ASPECT_OFF

    @property
    def hud_edge(self) -> tuple[float, float]:
        """The interface's width and height against the game's (cheat_aspect_ratio): the HUD keeps to the picture's
        edges."""
        return interface_size(self.cheat_aspect_ratio.value)

    @property
    def patches_interface_code(self) -> bool:
        """The interface options that patch the executable (core/interface/hud): they need the game ROM."""
        return self.hud_scale != HudScale.FULL or self.touchless_target

    @property
    def patches_cutscenes(self) -> bool:
        """free_cutscene_monsters, when the quests can move a monster off its map."""
        return self.free_cutscene_monsters and self.randomize_quests \
            and (self.randomize_monsters or self.randomize_maps)

    @property
    def writes_routes(self) -> bool:
        """monster_routes, when the quests can put a monster where it does not roam."""
        return self.monster_routes and self.randomize_quests and (self.randomize_monsters or self.randomize_maps
                                                                  or self.randomize_intruders)

    @property
    def randomizes_equipment(self) -> bool:
        return self.randomize_equipment and (any(getattr(self, name) for name in EQUIPMENT_SWITCHES)
                                             or self.armor_skills is not ArmorSkillMode.KEEP or self.allow_op_equipment)

    @property
    def uses_mhgen_models(self) -> bool:
        """The models pack (made from MH XX's files) joins the model shuffle or
        layered equipment's looks: it needs XX's ROM and the
        game ROM."""
        return self.mhgen_models and (self.randomize_equipment and self.randomize_models or self.layered_equipment)

    @property
    def allows_op_equipment(self) -> bool:
        """allow_op_equipment, unless the equipment master switch is off."""
        return self.randomize_equipment and self.allow_op_equipment

    def mode_of(self, key: str) -> Enum:
        """The mode of the ported monster `key` (PORTED_OPTIONS): his field, unless the master switch is off; his pool
        mode counts only while the quests' large monsters are randomized (he joins nothing otherwise)."""
        option = ported_option(key)
        if not self.additional_monsters:
            return option.off
        if option.base and self.mode_of(option.base) is ported_option(option.base).off:
            return option.off
        mode = getattr(self, key)
        if mode is option.pool and not (self.randomize_quests and self.randomize_monsters):
            return option.off
        return mode

    def dropped_pool_monsters(self) -> list[str]:
        """The names of the ported monsters whose field asks for his pool mode while the quests' large monsters are not
        randomized, so that mode_of counts him as off (the command line refuses such settings)."""
        if not self.additional_monsters:
            return []
        return [option.name for option in PORTED_OPTIONS
                if option.pool is not None and getattr(self, option.key) is option.pool
                and self.mode_of(option.key) is option.off]

    def deviants_without_base(self) -> list[tuple[str, str]]:
        """(Deviant's name, his base's name) of each Deviant whose field is not off while his base's mode counts as
        off, so that mode_of counts him as off (the command line refuses such settings)."""
        if not self.additional_monsters:
            return []
        return [(option.name, ported_option(option.base).name) for option in PORTED_OPTIONS
                if option.base and getattr(self, option.key) is not option.off
                and self.mode_of(option.base) is ported_option(option.base).off]

    def has_quests(self, key: str) -> bool:
        """The ported monster `key` adds his quest table (his quests or extended mode)."""
        option = ported_option(key)
        return option.quests is not None and self.mode_of(key) in (option.quests, option.extended)

    def in_pool(self, key: str) -> bool:
        """The ported monster `key` joins the randomized large monsters (his pool mode, or extended with the quests'
        monsters randomized)."""
        option = ported_option(key)
        mode = self.mode_of(key)
        return option.pool is not None and (mode is option.pool or (
            mode is option.extended is not None and self.randomize_quests and self.randomize_monsters))

    def randomizes_own_quests(self, key: str) -> bool:
        """His quest table's quests go through the quest randomizer (extended mode with randomize_quests)."""
        option = ported_option(key)
        return option.extended is not None and self.mode_of(key) is option.extended and self.randomize_quests

    def builds(self, key: str) -> bool:
        """The ported monster `key`: his files and his code go into the mod, with his quests in his quests mode (they
        need MH XX's ROM and the game ROM)."""
        return self.mode_of(key) in ported_option(key).builds

    @property
    def alatreon_mode(self) -> AlatreonMode:
        """mode_of("alatreon")."""
        return self.mode_of("alatreon")

    @property
    def builds_alatreon(self) -> bool:
        """builds("alatreon")."""
        return self.builds("alatreon")

    @property
    def mizutsune_mode(self) -> MizutsuneMode:
        """mode_of("mizutsune")."""
        return self.mode_of("mizutsune")

    @property
    def builds_mizutsune(self) -> bool:
        """builds("mizutsune")."""
        return self.builds("mizutsune")

    @property
    def glavenus_mode(self) -> GlavenusMode:
        """mode_of("glavenus")."""
        return self.mode_of("glavenus")

    @property
    def builds_glavenus(self) -> bool:
        """builds("glavenus")."""
        return self.builds("glavenus")

    @property
    def great_maccao_mode(self) -> GreatMaccaoMode:
        """mode_of("great_maccao")."""
        return self.mode_of("great_maccao")

    @property
    def builds_great_maccao(self) -> bool:
        """builds("great_maccao")."""
        return self.builds("great_maccao")

    @property
    def valstrax_mode(self) -> ValstraxMode:
        """mode_of("valstrax")."""
        return self.mode_of("valstrax")

    @property
    def builds_valstrax(self) -> bool:
        """builds("valstrax")."""
        return self.builds("valstrax")

    @property
    def astalos_mode(self) -> AstalosMode:
        """mode_of("astalos")."""
        return self.mode_of("astalos")

    @property
    def builds_astalos(self) -> bool:
        """builds("astalos")."""
        return self.builds("astalos")

    @property
    def builds_ported(self) -> bool:
        """A ported monster goes into the mod (any of PORTED_OPTIONS)."""
        return any(self.builds(option.key) for option in ported_options())

    @property
    def needs_xx(self) -> bool:
        """The run needs MH XX's decrypted .3ds (`xx_rom`) beside the other games': a monster is ported (his gear's
        models are made from XX's files, whichever game his monster comes from) or the models pack is on
        (`uses_mhgen_models`). It is the only other game a run reads."""
        return self.builds_ported or self.uses_mhgen_models

    def quest_seed(self, quest_id: int) -> str:
        """Seed of one quest's random streams: the seed itself unless the quest was rerolled."""
        own = self.quest_rerolls.get(quest_id, 0)
        if not self.quest_reroll and not own:
            return self.seed
        return f"{self.seed}~{self.quest_reroll}.{own}"

    def to_dict(self) -> dict:
        values = {k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(self).items()}
        values["quest_rerolls"] = {str(k): v for k, v in sorted(self.quest_rerolls.items())}
        return values

    def gameplay_dict(self) -> dict:
        """to_dict() without the options each player chooses for themselves (PERSONAL_FIELDS)."""
        return {k: v for k, v in self.to_dict().items() if k not in PERSONAL_FIELDS}

    def checksum_dict(self) -> dict:
        """gameplay_dict() without the settings at their neutral value (LEGACY_VALUES or OLD_DEFAULTS, else the
        default): a setting added later leaves the checksum code of the games made before it unchanged."""
        neutral = {**Settings().to_dict(), **LEGACY_VALUES, **OLD_DEFAULTS}
        values = self.gameplay_dict()
        if self.additional_monsters and self.alatreon is AlatreonMode.FIELD_TRIP:
            # As the first versions saved it (`alatreon: true`, no master switch): their games keep their code.
            values.update(alatreon=True, additional_monsters=False)
        return {k: v for k, v in values.items() if k not in neutral or v != neutral[k]}

    @classmethod
    def from_dict(cls, values: dict) -> "Settings":
        if isinstance(values.get("alatreon"), bool):
            # The first versions' switch: on, his quest took 10110's place; there was no master switch.
            values = {**values, "alatreon": (AlatreonMode.FIELD_TRIP if values["alatreon"] else AlatreonMode.OFF).value,
                      "additional_monsters": values.get("additional_monsters", values["alatreon"])}
        kwargs = {}
        for f in fields(cls):
            if f.name not in values and f.name not in LEGACY_VALUES:
                continue
            value = values[f.name] if f.name in values else LEGACY_VALUES[f.name]
            default = getattr(cls(), f.name)
            if isinstance(default, Enum):
                value = type(default)(value)
            elif isinstance(default, dict):
                value = {int(quest): int(count) for quest, count in value.items() if int(count)}
            kwargs[f.name] = value
        # Old presets had target_switch and target_face_top as two separate options, merged into touchless_target.
        if values.get("target_switch") or values.get("target_face_top"):
            kwargs["touchless_target"] = True
        return cls(**kwargs)

    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Settings":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
