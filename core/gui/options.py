"""Declarative description of the GUI's options (toolkit-independent; the Qt pages build widgets from it).

`AREAS` is the catalogue of every option: each area (quests, equipment...) has sections, each section groups, each
group options bound to `Settings` fields, with their bilingual texts. The Qt GUI shows parts of it, chosen by
curated/gui_presets.json: `RANDOMIZER_AREAS` (the Randomizer page) and `INSTALL_SECTIONS` (the Options page); the
rest is fixed for a new run. To expose a new setting, add an `Option` here and
place its field in gui_presets.json; `tests/gui/test_gui_options.py` fails if a `Settings` field is missing or in two
places, an enum value has no choice or a text is not translated.

This module imports no GUI toolkit, so it can be tested headless.
"""

from dataclasses import dataclass, replace
from enum import Enum

from core.app import presets
from core.gameplay.fast_gathering.fast_gathering import GATHER_SPEED
from core.app.settings import (
    AlatreonMode, AlatreonMusic, ArmorSkillMode, Cheat3D, CheatAspect, CheatFps, DuplicateMode, FrenzyChance, Frequency,
    GlavenusMode, HudScale, MizutsuneMode, ModelMode, PalicoModelMode, ProgressionMode, RewardSource, StatMode,
    StructureMode, SubQuestMode, TextMode,
)
from core.gui.i18n import EMPTY, T

# shown in the fast gathering option (gameplay/fast_gathering/fast_gathering.py)
_GATHER_PERCENT = round(GATHER_SPEED * 100)
_FOV_MIN, _FOV_MAX = presets.field_range("cheat_fov")  # curated/gui_presets.json, "ranges"


@dataclass(frozen=True)
class Choice:
    value: Enum
    label: T
    tooltip: T = EMPTY
    legacy: bool = False             # retired value: only shown while a loaded game (fix mode) has it; list it last


@dataclass(frozen=True)
class Option:
    field: str                       # Settings attribute
    label: T = EMPTY
    tooltip: T = EMPTY
    choices: tuple[Choice, ...] = ()  # radio buttons for enum fields
    minimum: int = 0                 # stepper for int fields
    maximum: int = 0
    requires: str | None = None      # Settings field that must be on (bool) or not on its first choice (enum)
    also_with: str | None = None     # a bool Settings field that enables it too, whatever `requires` and its area
    compact: bool = False            # enum shown as a labelled drop-down instead of radio buttons
    range_to: str | None = None      # int pair "between N and M": `field` is N, this Settings field is M
    emulator_only: bool = False      # not available on a real 3DS (hidden on the "3DS" platform; EMULATOR_ONLY)
    links: tuple[str, ...] = ()      # other Settings fields the widget writes with the same value


@dataclass(frozen=True)
class Hint:
    """A recommendation under a group's description that follows other settings: `on` while every one of `fields`
    is on (bool) or not on its first choice (enum), else `off`."""
    fields: tuple[str, ...]
    on: T
    off: T


@dataclass(frozen=True)
class Group:
    title: T
    options: tuple[Option, ...]
    description: T = EMPTY
    hint: Hint | None = None


@dataclass(frozen=True)
class Section:
    title: T
    groups: tuple[Group, ...]
    inputs: tuple[str, ...] = ()     # file fields shown as a card after the groups (unused by the Qt GUI: the
    #                                  game files are chosen on its Install page)


@dataclass(frozen=True)
class Area:
    """First row of tabs (quests / equipment); its sections are the second row. `master` is a bool switch shown
    above the tabs; with it off, every option of the area is disabled."""
    title: T
    sections: tuple[Section, ...]
    master: Option | None = None


STAT_CHOICES = (
    Choice(StatMode.KEEP, T("No cambiar", "Don't change"),
           T("Se conserva el valor del juego original.", "The original game's value is kept.")),
    Choice(StatMode.PERCENT, T("Progresivo", "Progressive"),
           T("Cambio de hasta un 20 %, casi siempre pequeño, así que el equipo sigue mejorando al avanzar. "
             "Un valor 0 sigue siendo 0.",
             "A change of up to 20%, usually small, so gear still improves as you progress. A value of 0 stays 0.")),
    Choice(StatMode.RANGE, T("Aleatorio", "Random"),
           T("Cualquier valor entre el mínimo y el máximo de ese tipo de equipo en el mismo rango (bajo, alto o G) "
             "del juego original.",
             "Any value between the minimum and maximum of that kind of equipment in the same rank (low, high "
             "or G) of the original game.")),
)
STAT_MODES_HELP = T(
    "Progresivo: cambio de hasta un 20 %, casi siempre pequeño, así que el equipo sigue mejorando al avanzar. "
    "Aleatorio: cualquier valor entre el mínimo y el máximo de ese tipo de equipo en el mismo rango (bajo, alto "
    "o G) del juego original.",
    "Progressive: a change of up to 20%, usually small, so gear still improves as you progress. Random: any value "
    "between the minimum and maximum of that kind of equipment in the same rank (low, high or G) of the original "
    "game.")


def stat(field: str, label: T, requires: str, tooltip: T = EMPTY) -> Option:
    return Option(field, label, tooltip, choices=STAT_CHOICES, requires=requires, compact=True)


QUEST_SECTIONS: tuple[Section, ...] = (
    Section(T("Monstruos grandes", "Large monsters"), (
        Group(T("Monstruos", "Monsters"), (
            Option("randomize_monsters", T("Randomizar monstruos grandes", "Randomize large monsters"),
                   T("Sustituye los monstruos grandes de cada misión respetando las reglas del motor del juego.",
                     "Replaces the large monsters of every quest while respecting the game engine's rules.")),
        ), T("Dragones de final, monstruos con cinemática y Dalamadur se colocan siempre donde el juego los admite.",
             "Finale dragons, cutscene monsters and Dalamadur are always placed where the game supports them.")),
        Group(T("Estructura de oleadas", "Wave structure"), (
            Option("structure", requires="randomize_monsters", choices=(
                Choice(StructureMode.KEEP, T("Mantener la original", "Don't change"),
                       T("Mismo número de oleadas y de monstruos por oleada que la misión original.",
                         "Same number of waves and monsters per wave as the original quest.")),
                Choice(StructureMode.KEEP_PROGRESSION,
                       T("Mantener solo en misiones clave", "Don't change in key quests"),
                       T("Las misiones clave y urgentes conservan su estructura; el resto se genera al azar.",
                         "Key and urgent quests keep their structure; all others are generated at random.")),
                Choice(StructureMode.RANDOM, T("Aleatoria", "Random"),
                       T("Número de oleadas y de monstruos por oleada al azar.",
                         "Random number of waves and monsters per wave.")),
            )),
        )),
        Group(T("Monstruos repetidos", "Repeated monsters"), (
            Option("duplicates", requires="randomize_monsters", choices=(
                Choice(DuplicateMode.NEVER, T("Nunca", "Never"),
                       T("Todos los monstruos de una misión son distintos.", "Every monster in a quest is different.")),
                Choice(DuplicateMode.ALLOWED, T("Permitidos", "Allowed"),
                       T("El mismo monstruo puede aparecer varias veces, al azar.",
                         "The same monster may appear several times, at random.")),
                Choice(DuplicateMode.ONLY_IF_ORIGINAL, T("Solo si la original los repetía (antigua)",
                                                         "Only where the original did (old)"),
                       T("Opción retirada: con estructura aleatoria repetía el mismo monstruo en todos los huecos. "
                         "Solo aparece en partidas creadas con ella; elige otra para dejar de usarla (cambia todas "
                         "las misiones).",
                         "Retired option: with a random structure it repeated the same monster in every slot. It "
                         "only shows in games made with it; pick another to stop using it (it changes every "
                         "quest)."),
                       legacy=True),
            )),
        )),
        Group(T("Progresión de dificultad", "Difficulty progression"), (
            Option("progression", requires="randomize_monsters", choices=(
                Choice(ProgressionMode.BALANCED, T("Equilibrada", "Balanced"),
                       T("Cada monstruo se sustituye por otro de dificultad similar (±2 niveles).",
                         "Each monster is replaced by one of similar difficulty (±2 tiers).")),
                Choice(ProgressionMode.PROGRESSIVE, T("Progresiva", "Progressive"),
                       T("La dificultad de los monstruos se pondera según el rango de la misión. Al menos una "
                         "misión ★1 del Gremio tiene como objetivo un monstruo fácil.",
                         "Monster difficulty is weighted by the quest's rank. At least one ★1 Gathering Hall quest "
                         "targets an easy monster.")),
                Choice(ProgressionMode.NONE, T("Sin progresión", "No progression"),
                       T("Cualquier monstruo puede aparecer en cualquier misión.",
                         "Any monster can appear in any quest.")),
            )),
            Option("adjust_stats", T("Ajustar la vida a la dificultad", "Scale health to difficulty"),
                   T("Un monstruo más fuerte que el sustituido recibe más vida que él, pero menos de la suya, sobre "
                     "todo al principio; uno más débil, la suya. Con monstruos añadidos, cada uno tiene menos vida. "
                     "Las partes se rompen como en el rango de la misión. El ataque es el de la misión original.",
                     "A monster stronger than the one it replaces gets more health than it, but less than its "
                     "own, above all early on; a weaker one, its own. With added monsters, each has less health. "
                     "Parts break as at the quest's rank. Attack stays the original quest's."),
                   requires="randomize_monsters"),
        )),
        Group(T("Monstruos coléricos", "Frenzied monsters"), (
            Option("frenzy_chance", choices=(
                Choice(FrenzyChance.NEVER, T("Nunca", "Never"),
                       T("No se añade el virus Colérico a ningún monstruo.",
                         "No monster gets the Frenzy virus.")),
                Choice(FrenzyChance.RARE, T("Poco frecuentes (2 %)", "Rare (2 %)"),
                       T("Cada monstruo grande que puede estar colérico tiene un 2 % de estarlo, por separado.",
                         "Each large monster that can be frenzied has a 2 % chance of it, on its own.")),
                Choice(FrenzyChance.COMMON, T("Frecuentes (6 %)", "Common (6 %)"),
                       T("Cada monstruo grande que puede estar colérico tiene un 6 % de estarlo, por separado.",
                         "Each large monster that can be frenzied has a 6 % chance of it, on its own.")),
            )),
            Option("keep_frenzy", T("Mantener los coléricos originales", "Keep the original frenzied monsters"),
                   T("Los monstruos que el juego original pone coléricos siguen siéndolo tras randomizar. "
                     "Sin esto, solo estarán coléricos los que salgan del azar de arriba. Los monstruos Apex "
                     "no cambian.",
                     "The monsters the original game makes frenzied stay frenzied after randomizing. Without it, "
                     "only the ones rolled above are frenzied. Apex monsters are not changed.")),
        ), T("Solo las especies que el juego original pone coléricas (nunca dragones ancianos ni Apex).",
             "Only species the original game makes frenzied (never elder dragons or Apex).")),
    )),
    Section(T("Mapas", "Maps"), (
        Group(T("Mapas", "Maps"), (
            Option("randomize_maps", T("Randomizar mapas", "Randomize maps"),
                   T("Traslada las misiones a otros mapas junto con sus monstruos pequeños y ajustes de zona.",
                     "Moves quests to other maps together with their small monsters and area settings.")),
            Option("always_music", T("Evitar mapas sin música", "Avoid maps without music"),
                   T("Solo usa mapas sin música de zona si todos los monstruos tienen su propio tema.",
                     "Only uses maps without area music if every monster has its own theme."),
                   requires="randomize_maps"),
            Option("one_monster_per_wave_on_arenas",
                   T("Un monstruo por oleada en arenas", "One monster per wave in arenas"),
                   T("No traslada a una arena las misiones con varios monstruos simultáneos.",
                     "Does not move quests with simultaneous monsters to an arena."),
                   requires="randomize_maps"),
            Option("monster_routes", T("Los monstruos cambian de zona en cualquier mapa",
                                       "Monsters change area on any map"),
                   T("Coloca a cada monstruo en zonas desde las que puede moverse y, en los mapas donde no tiene "
                     "rutas propias, le da rutas por las zonas grandes del mapa: todo monstruo que se mueve en el "
                     "juego original se mueve en cualquier mapa. Los monstruos enormes (Fatalis, Gogmazios, "
                     "Akantor, Ukanlos) van solo a zonas donde caben. Sin esto, un monstruo en un mapa que no "
                     "conoce se queda toda la misión en su zona. Las zonas "
                     "de cada mapa y de cada monstruo se editan en core/game/data/curated/monster_areas.json.",
                     "Places each monster in areas it can move from and, on maps where it has no routes of its "
                     "own, gives it routes through the map's big areas: every monster that moves in the original "
                     "game moves on any map. The huge monsters (Fatalis, Gogmazios, Akantor, Ukanlos) only go to "
                     "areas they fit in. Without this, a monster on a map it does not know stays in its area for "
                     "the whole quest. The areas of each map and each "
                     "monster are edited in core/game/data/curated/monster_areas.json.")),
        )),
        Group(T("Arenas", "Arenas"), (
            Option("arena_maps", requires="randomize_maps", choices=(
                Choice(Frequency.NEVER, T("Nunca", "Never"),
                       T("Ninguna misión se traslada a una arena.", "No quest is moved to an arena.")),
                Choice(Frequency.RARE, T("Ocasionales", "Occasional"),
                       T("Las arenas aparecen con menos frecuencia.", "Arenas appear less often.")),
                Choice(Frequency.NORMAL, T("Frecuentes", "Common"),
                       T("Las arenas aparecen con la misma frecuencia que cualquier otro mapa.",
                         "Arenas appear as often as any other map.")),
            )),
        ), T("Mapas pequeños de una sola zona, como la Arena o el Gran Mar.",
             "Small single-area maps, such as the Arena or the Great Sea.")),
        Group(T("Bosque Eterno", "Everwood"), (
            Option("everwood", requires="randomize_maps", choices=(
                Choice(Frequency.NEVER, T("Nunca", "Never"),
                       T("Recomendado hasta que se compruebe en el juego.", "Recommended until verified in-game.")),
                Choice(Frequency.RARE, T("Ocasional", "Occasional"), T("Experimental.", "Experimental.")),
                Choice(Frequency.NORMAL, T("Frecuente", "Common"),
                       T("Experimental: las zonas del Bosque Eterno se generan proceduralmente.",
                         "Experimental: Everwood areas are generated procedurally.")),
            )),
        )),
    )),
    Section(T("Objetivos y textos", "Objectives & text"), (
        Group(T("Objetivo principal", "Main objective"), (
            Option("capture_quests", T("Misiones de captura", "Capture quests"),
                   T("Cada misión cuyo único objetivo es un monstruo grande que se puede capturar, solo en la "
                     "misión, tiene un 5 % de pasar a ser de captura.",
                     "Each quest whose only target is a large monster that can be captured, alone in the quest, "
                     "has a 5 % chance of becoming a capture quest.")),
        )),
        Group(T("Submisiones", "Subquests"), (
            Option("sub_quests", choices=(
                Choice(SubQuestMode.KEEP, T("Mantener las originales", "Don't change"),
                       T("Cada misión conserva su submisión. Si su monstruo ya no está en la misión, pasa a "
                         "otro de los monstruos.",
                         "Every quest keeps its subquest. If its monster is no longer in the quest, it moves to "
                         "another of the quest's monsters.")),
                Choice(SubQuestMode.DISABLE, T("Desactivadas", "Disabled"),
                       T("Las misiones no tienen submisión.", "Quests have no subquest.")),
                Choice(SubQuestMode.RANDOMIZE, T("Romper una parte", "Break a part"),
                       T("La submisión consiste en romper una parte de uno de los monstruos de la misión.",
                         "The subquest asks you to break a part of one of the quest's monsters.")),
            )),
        )),
        Group(T("Textos de las misiones", "Quest text"), (
            Option("text", choices=(
                Choice(TextMode.KEEP, T("Sin cambios", "Don't change"),
                       T("El tablón muestra los textos originales.", "The quest board shows the original text.")),
                Choice(TextMode.REPLACE_NAMES, T("Sustituir nombres", "Replace names"),
                       T("Actualiza los nombres de los monstruos en título y descripción. Cuando cambian los "
                         "monstruos o la misión pasa a ser de captura, el objetivo principal y la condición de "
                         "fallo se escriben con las frases del juego original y nombran a todos: «Caza una A», "
                         "«Captura una A y un B» o, con tres o más, «Caza a todos los monstruos grandes». En los "
                         "cinco idiomas.",
                         "Updates monster names in title and description. When the monsters change or the quest "
                         "becomes a capture, the main objective and the failure condition are written with the "
                         "game's own sentences and name all of them: “Hunt a A”, “Capture a A and a B” or, with "
                         "three or more, “Hunt all large monsters”. In all five languages.")),
                Choice(TextMode.REGENERATE, T("Regenerar", "Regenerate"),
                       T("Como «Sustituir nombres», y además reescribe con esas frases el objetivo principal y la "
                         "condición de fallo aunque los monstruos de la misión no cambien.",
                         "Like “Replace names”, and also rewrites the main objective and the failure condition "
                         "with those sentences even when the quest's monsters stay the same.")),
            )),
        )),
    )),
    Section(T("Recompensas y suministros", "Rewards & supplies"), (
        Group(T("Recompensas", "Rewards"), (
            Option("randomize_rewards", T("Randomizar recompensas", "Randomize rewards"),
                   T("Las recompensas entregan materiales de monstruo del rango de la misión, hasta 5 por hueco.",
                     "Rewards hand out monster materials of the quest's rank, up to 5 per slot.")),
            Option("reward_source", requires="randomize_rewards", choices=(
                Choice(RewardSource.QUEST_MONSTERS_AND_RANK,
                       T("Monstruos de la misión y rango", "Quest monsters and rank"),
                       T("Casi todo lo que sueltan los monstruos de la misión en su rango, con sus probabilidades, "
                         "y algún material más del rango.",
                         "Mostly what the quest's monsters drop in its rank, with their chances, and a few more "
                         "materials of the rank.")),
                Choice(RewardSource.RANK, T("Cualquiera del rango", "Any from the rank"),
                       T("Materiales al azar con la rareza del rango de la misión.",
                         "Random materials with the rarity of the quest's rank.")),
            )),
        )),
        Group(T("Suministros", "Supplies"), (
            Option("randomize_supplies", T("Randomizar suministros", "Randomize supplies"),
                   T("Cada hueco de la caja de suministros contiene un consumible al azar en su cantidad máxima, "
                     "casi siempre útil (curas, bombas, trampas, piedras de afilar...) y casi nunca basura. Cada caja "
                     "lleva al menos una cura, y la misión cambia el resto: bombas de luz con monstruos voladores, "
                     "bombas boñiga con varios monstruos en una oleada, la bebida del clima en mapas calurosos o "
                     "fríos, trampas en las capturas. El mapa se conserva siempre. Cada caja se ordena: mapa "
                     "primero, luego por id de objeto y los huecos vacíos al final.",
                     "Each supply box slot holds a random consumable in its maximum quantity, almost always a useful "
                     "one (healing, bombs, traps, whetstones...) and almost never junk. Every box holds at least one "
                     "healing item, and the quest changes the rest: Flash Bombs with flying monsters, Dung Bombs "
                     "with several monsters in a wave, the climate's drink on hot or cold maps, traps in captures. "
                     "The map is always kept. Each box is sorted: Map first, then by item id, empty slots last.")),
            Option("gunner_supplies", T("Munición para artilleros", "Gunner ammo"),
                   T("Al menos 4 huecos de los baúles (inicial y reabastecimiento) llevan munición o revestimientos "
                     "distintos al azar, en stack lleno. Si hay menos huecos, todos.",
                     "At least 4 slots of the supply boxes (initial and refills) hold different random ammo or "
                     "coatings, in full stacks. With fewer slots, all of them."),
                   requires="randomize_supplies"),
        )),
    )),
    Section(T("Otros monstruos", "Other monsters"), (
        Group(T("Monstruos pequeños", "Small monsters"), (
            Option("randomize_small_monsters", T("Randomizar monstruos pequeños", "Randomize small monsters"),
                   T("Intercambia especies pequeñas dentro de su grupo: herbívoros, raptores e insectos.",
                     "Swaps small species within their group: herbivores, raptors and insects.")),
        )),
        Group(T("Intrusos", "Intruders"), (
            Option("randomize_intruders", T("Randomizar intrusos", "Randomize intruders"),
                   T("Cambia los monstruos que pueden irrumpir en la misión. Nunca se usan dragones de final "
                     "ni monstruos con cinemática.",
                     "Changes the monsters that may intrude on the quest. Finale dragons and cutscene monsters "
                     "are never used.")),
        )),
    )),
    Section(T("Depuración", "Debug"), (
        Group(T("Pruebas", "Testing"), (
            Option("debug_weak_monsters", T("Monstruos débiles", "Weak monsters"),
                   T("Vida y ataque al mínimo en todos los monstruos, para probar misiones rápidamente.",
                     "Minimum health and attack for every monster, to test quests quickly.")),
        ), T("Opciones pensadas para probar el randomizer, no para jugar.",
             "Options meant for testing the randomizer, not for playing.")),
    )),
)


EQUIPMENT_SECTIONS: tuple[Section, ...] = (
    Section(T("Recetas", "Recipes"), (
        Group(T("Recetas de creación y mejora", "Create and upgrade recipes"), (
            Option("randomize_recipes", T("Randomizar recetas", "Randomize recipes"),
                   T("Cada receta de creación y de mejora pide 1 a 2 materiales distintos en rango bajo, 1 a 3 en "
                     "alto y 1 a 4 en G, cada uno de 1 a 4 veces. Al menos uno es parte de un monstruo grande del "
                     "rango del equipo; los demás pueden ser partes de monstruos pequeños, minerales o huesos. Las "
                     "mejoras de glaive insecto solo admiten 2.",
                     "Every create and upgrade recipe asks for 1 to 2 different materials in low rank, 1 to 3 in "
                     "high and 1 to 4 in G, each 1 to 4 times. At least one is a part of a large monster of the "
                     "equipment's rank; the others may be parts of small monsters, ores or bones. Insect Glaive "
                     "upgrades only hold 2.")),
        ), T("Solo se usan materiales que el juego original ya pide en ese rango y que no son difíciles de "
             "conseguir (probabilidad de obtención máxima de al menos 10 %).",
             "Only materials the original game already asks for in that rank and that are not hard to get "
             "(best drop chance of at least 10%) are used.")),
    )),
    Section(T("Armas", "Weapons"), (
        Group(T("Estadísticas", "Stats"), (
            Option("randomize_weapon_stats", T("Randomizar estadísticas de armas", "Randomize weapon stats"),
                   T("Los valores cambian en el juego y en los menús.",
                     "Values change both in game and in the menus.")),
            stat("weapon_attack", T("Ataque", "Attack"), "randomize_weapon_stats",
                 T("Ataque del arma, el que se ve en los menús. Con Progresivo, las armas iniciales tienen un "
                   "10 % más.",
                   "Weapon attack, as shown in the menus. With Progressive, the starting weapons get 10% more.")),
            stat("weapon_affinity", T("Afinidad", "Affinity"), "randomize_weapon_stats",
                 T("Probabilidad de golpe crítico (negativa: golpes más débiles). Progresivo no cambia las "
                   "armas con 0 %.",
                   "Critical hit chance (negative: weaker hits). Progressive leaves weapons at 0% unchanged.")),
            stat("weapon_defense", T("Bonus de defensa", "Defense bonus"), "randomize_weapon_stats",
                 T("Defensa extra que dan algunas armas. Progresivo no se la añade a las que no la tienen.",
                   "Extra defense some weapons give. Progressive does not add it to weapons without it.")),
            stat("weapon_slots", T("Huecos de joya", "Decoration slots"), "randomize_weapon_stats",
                 T("Huecos para joyas (0 a 3). Con Progresivo, un arma con huecos gana o pierde uno de vez en "
                   "cuando.",
                   "Slots for decorations (0 to 3). With Progressive, a weapon with slots gains or loses one "
                   "now and then.")),
            stat("weapon_sharpness", T("Afilado", "Sharpness"), "randomize_weapon_stats",
                 T("Progresivo: los colores de cada perfil de afilado se alargan o acortan hasta un 20 % (los "
                   "perfiles los comparten varias armas); las armas iniciales tienen el afilado de su tercera mejora, "
                   "con algo de verde, y sus mejoras nunca uno peor. Aleatorio: el afilado de otra arma de la misma "
                   "clase y rango.",
                   "Progressive: the colors of each sharpness profile grow or shrink by up to 20% (profiles are "
                   "shared by several weapons); the starting weapons get the sharpness of their third upgrade, with "
                   "some green, and their upgrades never a worse one. Random: the sharpness of another weapon of the "
                   "same class and rank.")),
        ), STAT_MODES_HELP, Hint(
            ("randomize_quests", "randomize_rewards"),
            T("Recomendado: Aleatorio. Las recompensas están randomizadas y dan materiales de todo el rango desde "
              "el principio, así que el orden de las mejoras del juego original ya no guía la partida.",
              "Recommended: Random. Rewards are randomized and hand out materials of the whole rank from the start, "
              "so the original game's upgrade order no longer guides the game."),
            T("Recomendado: Progresivo. Las recompensas no están randomizadas, así que avanzas como en el juego "
              "original y el equipo sigue mejorando al subir de rango.",
              "Recommended: Progressive. Rewards are not randomized, so you progress as in the original game and "
              "gear keeps improving as you rank up."))),
        Group(T("Elemento y estado", "Element and status"), (
            stat("weapon_element", T("Valor", "Value"), "randomize_weapon_stats",
                 T("Valor del elemento o estado de las armas que lo tienen.",
                   "Element or status value of the weapons that have one.")),
            Option("weapon_element_type", T("Cambiar el tipo", "Change the type"),
                   T("Las armas con elemento o estado reciben otro distinto (fuego, agua, rayo, hielo, dragón, "
                     "veneno, parálisis, sueño o nitro).",
                     "Weapons with an element or status get a different one (fire, water, thunder, ice, dragon, "
                     "poison, paralysis, sleep or blast)."),
                   requires="randomize_weapon_stats"),
            Option("weapon_element_add_remove", T("Añadir y quitar", "Add and remove"),
                   T("Cualquier arma puede ganar o perder su elemento o estado, en la misma proporción que las "
                     "armas de su clase y rango en el juego original.",
                     "Any weapon may gain or lose its element or status, in the same proportion as the weapons of "
                     "its class and rank in the original game."),
                   requires="randomize_weapon_stats"),
        ), T("No afecta a las ballestas, que usan munición.", "Does not affect bowguns, which use ammo.")),
        Group(T("Mejoras", "Upgrades"), (
            Option("weapon_upgrades_improve", T("Las mejoras siempre mejoran", "Upgrades always improve"),
                   T("Cada mejora tiene más ataque que el arma de la que viene, y no menos afinidad, defensa, "
                     "huecos, afilado ni valor del mismo elemento. Si el tope del rango no deja sitio, se baja el "
                     "arma anterior.",
                     "Every upgrade has more attack than the weapon it comes from, and no less affinity, defense, "
                     "slots, sharpness or value of the same element. If the rank cap leaves no room, the previous "
                     "weapon is lowered."),
                   requires="randomize_weapon_stats"),
            Option("weapon_upgrades_keep_element", T("Las evoluciones naturales conservan el elemento",
                                                     "Natural evolutions keep the element"),
                   T("La evolución natural de un arma es la mejora que en el juego original sigue su línea (mismo "
                     "elemento o, si no, el nombre más parecido). Con esta opción hereda el elemento o estado "
                     "del arma; las demás ramas pueden cambiarlo.",
                     "A weapon's natural evolution is the upgrade that continues its line in the original game "
                     "(same element or, failing that, the most similar name). With this option it inherits the "
                     "weapon's element or status; the other branches may change it."),
                   requires="randomize_weapon_stats"),
        ), T("Ninguna estadística supera nunca el máximo original de su clase de arma y rango (bajo, alto o G).",
             "No stat ever goes above the original maximum of its weapon class and rank (low, high or G).")),
    )),
    Section(T("Armaduras", "Armor"), (
        Group(T("Estadísticas", "Stats"), (
            Option("randomize_armor_stats", T("Randomizar estadísticas de armaduras", "Randomize armor stats"),
                   T("Los valores cambian en el juego y en los menús.",
                     "Values change both in game and in the menus.")),
            stat("armor_defense", T("Defensa", "Defense"), "randomize_armor_stats",
                 T("Defensa base de cada pieza (sin mejorar).", "Base defense of each piece (not upgraded).")),
            stat("armor_resistances", T("Resistencias elementales", "Elemental resistances"), "randomize_armor_stats",
                 T("Resistencias a fuego, agua, rayo, hielo y dragón; cada una cambia por separado.",
                   "Fire, water, thunder, ice and dragon resistances; each one changes on its own.")),
            stat("armor_slots", T("Huecos de joya", "Decoration slots"), "randomize_armor_stats",
                 T("Huecos para joyas (0 a 3). Con Progresivo, una pieza con huecos gana o pierde uno de vez en "
                   "cuando.",
                   "Slots for decorations (0 to 3). With Progressive, a piece with slots gains or loses one now "
                   "and then.")),
        ), STAT_MODES_HELP),
        Group(T("Habilidades", "Skills"), (
            Option("armor_skills", choices=(
                Choice(ArmorSkillMode.KEEP, T("No cambiar", "Don't change"),
                       T("Cada pieza conserva sus habilidades.", "Every piece keeps its skills.")),
                Choice(ArmorSkillMode.SAME_SUM, T("Misma suma de puntos", "Same point total"),
                       T("Cada pieza conserva el total de sus puntos de habilidad, repartido entre habilidades al "
                         "azar. Las piezas sin habilidades siguen sin ellas.",
                         "Every piece keeps the total of its skill points, spread over random skills. Pieces "
                         "without skills stay without them.")),
                Choice(ArmorSkillMode.CHAOTIC, T("Caótico", "Chaotic"),
                       T("Todas las piezas reciben habilidades y puntos al azar; los valores altos son cada vez "
                         "más raros.",
                         "Every piece gets random skills and points; high values are increasingly rare.")),
            )),
            Option("armor_skill_max_count", T("Habilidades por pieza (máximo)", "Skills per piece (maximum)"),
                   T("Cada pieza recibe entre 1 y este número de habilidades (el juego admite hasta 5)."
                     " Si no estás seguro, se recomienda dejar el valor por defecto.",
                     "Each piece gets between 1 and this many skills (the game holds up to 5)."
                     " If unsure, leaving the default is recommended."),
                   minimum=1, maximum=5, requires="armor_skills"),
            Option("armor_skill_min_points", T("Puntos mínimos por habilidad", "Minimum points per skill"),
                   T("Puntos mínimos de cada habilidad positiva (0 cuenta como 1). Si no estás seguro, se "
                     "recomienda dejar el valor por defecto.",
                     "Minimum points of each positive skill (0 counts as 1). If unsure, leaving the default is "
                     "recommended."),
                   minimum=0, maximum=15, requires="armor_skills"),
            Option("armor_skill_max_points", T("Puntos máximos por habilidad", "Maximum points per skill"),
                   T("Puntos máximos de cada habilidad positiva (en el juego original rara vez pasan de 5)."
                     " Si no estás seguro, se recomienda dejar el valor por defecto.",
                     "Maximum points of each positive skill (in the original game they rarely exceed 5)."
                     " If unsure, leaving the default is recommended."),
                   minimum=1, maximum=20, requires="armor_skills"),
            Option("armor_skills_no_negative", T("Sin habilidades negativas", "No negative skills"),
                   T("Ninguna pieza recibe habilidades negativas. Ojo: cada punto negativo se compensa con un "
                     "punto positivo más, así que permitirlas también da más habilidades positivas.",
                     "No piece gets negative skills. Note: every negative point is compensated with one more "
                     "positive point, so allowing them also gives more positive skills."),
                   requires="armor_skills"),
            Option("armor_skills_shared_variants", T("Compartir entre Espadachín y Artillero",
                                                      "Share between Blademaster and Gunner"),
                   T("Las versiones de Espadachín y Artillero de una misma pieza reciben las mismas habilidades "
                     "nuevas.",
                     "The Blademaster and Gunner versions of a piece get the same new skills."),
                   requires="armor_skills"),
        ), T("Como mucho una habilidad negativa por pieza.", "At most one negative skill per piece.")),
    )),
    Section(T("Equipo OP", "OP equipment"), (
        Group(T("Límites del juego", "Game limits"), (
            Option("allow_op_equipment", T("Permitir equipo OP", "Allow OP equipment"),
                   T("Quita la comprobación del juego que rechaza las misiones (\"No puedes aceptar estos datos de "
                     "misión\") cuando llevas puesta una pieza con defensa de 180 o más (contando mejoras), una "
                     "resistencia de 10 o más, o un arma por encima de sus topes. Con la opción activada puedes "
                     "entrar a cualquier misión con cualquier arma y armadura, y las estadísticas de armadura "
                     "aleatorias ya no se limitan a esos valores.",
                     "Removes the game's check that refuses quests (\"You can't accept this quest data\") when you "
                     "wear a piece with 180 or more defense (counting upgrades), a resistance of 10 or more, or a "
                     "weapon past its limits. With it on you can enter any quest with any weapon and armor, and "
                     "random armor stats are no longer kept under those values.")),
        ), T("Desactivada, el randomizer mantiene la armadura por debajo de los límites para que las misiones "
             "se puedan aceptar.",
             "When off, the randomizer keeps armor under the limits so quests can be accepted.")),
    )),
    Section(T("Modelos", "Models"), (
        Group(T("Aspecto", "Looks"), (
            Option("randomize_models", T("Randomizar modelos", "Randomize models"),
                   T("Cambia el aspecto de armas y armaduras por el de otra de la misma clase o parte.",
                     "Changes the look of weapons and armor to that of another of the same class or part.")),
            Option("models_use_each_once", T("Usar cada modelo una sola vez", "Use each model only once"),
                   T("Se usan todos los modelos y ninguno se repite mientras sea posible.",
                     "Every model is used and none is repeated while possible."),
                   requires="randomize_models"),
            Option("mhgen_models", T("Modelos de MH Generations", "MH Generations models"),
                   T("Añade al sorteo las armas y armaduras de MH Generations que MH4U no tiene (unas 1500), y al "
                     "equipo superpuesto una línea «Generations» con ellas. Necesita la ROM de MH Generations "
                     "(europea o americana). Por familias, solo las armaduras.",
                     "Adds MH Generations' weapons and armor that MH4U lacks (about 1500) to the draw, and a "
                     "\"Generations\" line with them to layered equipment. Needs the MH Generations ROM (European "
                     "or American). By families, armor only."),
                   requires="randomize_models", also_with="layered_equipment"),
        )),
        Group(T("Modo", "Mode"), (
            Option("model_mode", requires="randomize_models", choices=(
                Choice(ModelMode.FAMILIES, T("Por familias", "By families"),
                       T("Cada línea de armas toma los modelos de otra, en orden: el arma más básica recibe el "
                         "aspecto más básico. Cada conjunto de armadura toma el aspecto de otro conjunto.",
                         "Each weapon line takes the models of another, in order: the most basic weapon gets the "
                         "most basic look. Each armor set takes the look of another set.")),
                Choice(ModelMode.CHAOTIC, T("Caótico", "Chaotic"),
                       T("Cada pieza recibe cualquier modelo de su clase de arma o parte de armadura.",
                         "Each piece gets any model of its weapon class or armor part.")),
            )),
        )),
    )),
    Section(T("Felyne", "Felyne"), (
        Group(T("Recetas Felyne", "Felyne recipes"), (
            Option("randomize_palico_recipes", T("Randomizar recetas", "Randomize recipes"),
                   T("Cada arma y armadura Felyne pide materiales del rango de la pieza con las mismas reglas que el "
                     "equipo de cazador.",
                     "Every Felyne weapon and armor piece asks for materials of its rank with the same rules as "
                     "hunter gear.")),
        )),
        Group(T("Armas Felyne", "Felyne weapons"), (
            Option("randomize_palico_weapon_stats", T("Randomizar estadísticas de armas", "Randomize weapon stats"),
                   T("Los valores cambian en el juego y en los menús.",
                     "Values change both in game and in the menus.")),
            stat("palico_weapon_attack", T("Ataque", "Attack"), "randomize_palico_weapon_stats",
                 T("Ataque cuerpo a cuerpo; el de bumerán cambia en la misma proporción.",
                   "Melee attack; the boomerang attack changes in the same proportion.")),
            stat("palico_weapon_affinity", T("Afinidad", "Affinity"), "randomize_palico_weapon_stats",
                 T("Probabilidad de golpe crítico. Progresivo no cambia las armas con 0 %.",
                   "Critical hit chance. Progressive leaves weapons at 0% unchanged.")),
            stat("palico_weapon_element", T("Valor del elemento", "Element value"), "randomize_palico_weapon_stats",
                 T("Valor del elemento de las armas que lo tienen.", "Element value of the weapons that have one.")),
            stat("palico_weapon_defense", T("Bonus de defensa", "Defense bonus"), "randomize_palico_weapon_stats",
                 T("Defensa extra que dan algunas armas. Progresivo no se la añade a las que no la tienen.",
                   "Extra defense some weapons give. Progressive does not add it to weapons without it.")),
            Option("palico_weapon_element_type", T("Cambiar el elemento", "Change the element"),
                   T("Las armas con elemento reciben otro distinto (fuego, agua, rayo, hielo o dragón).",
                     "Weapons with an element get a different one (fire, water, thunder, ice or dragon)."),
                   requires="randomize_palico_weapon_stats"),
            Option("palico_weapon_element_add_remove", T("Añadir y quitar elemento", "Add and remove element"),
                   T("Cualquier arma puede ganar o perder su elemento, en la misma proporción que las armas Felyne "
                     "de su rango en el juego original.",
                     "Any weapon may gain or lose its element, in the same proportion as the Felyne weapons of its "
                     "rank in the original game."),
                   requires="randomize_palico_weapon_stats"),
        ), STAT_MODES_HELP),
        Group(T("Armaduras Felyne", "Felyne armor"), (
            Option("randomize_palico_armor_stats", T("Randomizar estadísticas de armaduras",
                                                     "Randomize armor stats"),
                   T("Los valores cambian en el juego y en los menús.",
                     "Values change both in game and in the menus.")),
            stat("palico_armor_defense", T("Defensa", "Defense"), "randomize_palico_armor_stats",
                 T("Defensa de cada casco y torso.", "Defense of each head and body piece.")),
            stat("palico_armor_resistances", T("Resistencias elementales", "Elemental resistances"),
                 "randomize_palico_armor_stats",
                 T("Resistencias a fuego, agua, rayo, hielo y dragón de cada pieza; las del conjunto son la suma "
                   "de casco y torso.",
                   "Fire, water, thunder, ice and dragon resistances of each piece; a set's are head plus body.")),
        ), STAT_MODES_HELP),
        Group(T("Aspecto Felyne", "Felyne looks"), (
            Option("randomize_palico_models", T("Randomizar modelos", "Randomize models"),
                   T("Cambia el aspecto de armas y armaduras Felyne por el de otras del mismo tipo.",
                     "Changes the look of Felyne weapons and armor to that of others of the same kind.")),
            Option("palico_model_mode", requires="randomize_palico_models", choices=(
                Choice(PalicoModelMode.FULL_SET, T("Conjunto completo", "Whole set"),
                       T("Arma, casco y torso de un tema toman juntos el aspecto de otro tema (p. ej. todo lo de "
                         "Kut-Ku pasa a verse como Rathalos).",
                         "A theme's weapon, head and body take the look of another theme together (e.g. all the "
                         "Kut-Ku gear looks like Rathalos).")),
                Choice(PalicoModelMode.SEPARATE, T("Armas y armaduras por separado", "Weapons and armor apart"),
                       T("Las armas cambian entre sí y los conjuntos de armadura (casco y torso) entre sí.",
                         "Weapons swap among themselves and armor sets (head and body) among themselves.")),
                Choice(PalicoModelMode.CHAOTIC, T("Caótico", "Chaotic"),
                       T("Cada pieza recibe cualquier modelo de su tipo.", "Each piece gets any model of its kind.")),
            )),
            Option("palico_models_use_each_once", T("Usar cada modelo una sola vez", "Use each model only once"),
                   T("Se usan todos los modelos y ninguno se repite mientras sea posible.",
                     "Every model is used and none is repeated while possible."),
                   requires="randomize_palico_models"),
        )),
    )),
)

INTERFACE_SECTIONS: tuple[Section, ...] = (
    Section(T("HUD", "HUD"), (
        Group(T("Tamaño del HUD", "HUD size"), (
            Option("hud_scale", T("Tamaño", "Size"),
                   T("Tamaño de lo que se dibuja sobre el juego en la pantalla superior.",
                     "Size of what is drawn over the game on the top screen."),
                   choices=(
                       Choice(HudScale.FULL, T("100 % (original)", "100% (original)")),
                       Choice(HudScale.P90, T("90 %", "90%")),
                       Choice(HudScale.P80, T("80 %", "80%")),
                       Choice(HudScale.P70, T("70 %", "70%")),
                       Choice(HudScale.P60, T("60 %", "60%"),
                              T("Difícil de leer en la pantalla de una 3DS.", "Hard to read on a 3DS screen.")),
                   ), compact=True, emulator_only=True),
        ), T("Pensado para jugar en un monitor. Cada elemento se encoge hacia su esquina: reloj, vida, aguante, "
             "filo y medidores del arma, lista del grupo, selector de objetos, minimapa, medidor de montar y "
             "avisos sobre los personajes. Solo funciona en el emulador.",
             "Meant for playing on a monitor. Each element shrinks towards its corner: clock, health, stamina, "
             "sharpness and weapon gauges, party list, item selector, minimap, mount gauge and the prompts over "
             "the characters. It only works in the emulator.")),
        Group(T("Objetivo", "Target"), (
            Option("touchless_target", T("Fijar monstruos sin pantalla táctil", "Lock on to monsters without the "
                                          "touch screen"),
                   T("Mantén pulsado L (modo objetos) y pulsa arriba en la cruceta: se fija el monstruo grande o "
                     "se cambia al otro, igual que al tocar el panel de la cámara de objetivo. El selector de "
                     "objetos muestra un icono de la cruceta mientras tanto, y con L pulsado la cruceta deja de "
                     "mover la cámara (el C-stick sigue moviéndola). La cara del monstruo fijado se ve también en "
                     "la pantalla superior, a la izquierda del selector de objetos, con su marca de fijado.",
                     "Hold L (item mode) and press D-pad up: it locks the large monster or switches to the other "
                     "one, like a tap on the target camera panel. The item selector shows a D-pad hint while L is "
                     "held, and the D-pad no longer moves the camera then (the C-stick still does). The locked "
                     "monster's face is also shown on the top screen, left of the item selector, with its lock "
                     "mark."), emulator_only=True),
        ), T("Pensado para jugar solo con la pantalla superior (por ejemplo, en un monitor). Necesita el panel de "
             "la cámara de objetivo puesto en la pantalla táctil, y solo funciona una vez que el monstruo ya se ha "
             "encontrado (como el panel). Desactivada, el juego no se toca.",
             "Meant for playing with the top screen only (e.g. on a monitor). It needs the target camera panel on "
             "the touch screen, and only works once the monster has been found (like the panel). Switched off, "
             "the game is left untouched.")),
        Group(T("Pantalla única", "Single screen"), (
            Option("single_screen", T("Modo pantalla única", "Single Screen mode"),
                   T("Lo que la pantalla táctil muestra y hace falta para jugar se ve en la pantalla superior: la "
                     "lista de misiones (a la izquierda de la misión elegida, con su contador de páginas), los "
                     "ingredientes de la Cantina (junto a sus efectos), las preguntas de sí / no (como la de la "
                     "Herrería al fabricar) y el menú del título con las partidas guardadas. La pantalla táctil "
                     "sigue funcionando igual.",
                     "What the touch screen shows and play needs is shown on the top screen: the quest list (left "
                     "of the chosen quest, with its page counter), the Canteen's ingredients (beside their "
                     "effects), the yes / no questions (such as the Smithy's after forging) and the title menu "
                     "with the saved games. The touch screen still works as before."), emulator_only=True),
        ), T("Para jugar viendo solo la pantalla superior del emulador (por ejemplo, en un monitor): los menús de "
             "la pantalla táctil que hacen falta pasan a la pantalla superior: la lista de misiones, los "
             "ingredientes de la Cantina, las preguntas de sí / no y el menú del título. La pantalla táctil sigue "
             "funcionando igual. Solo funciona en el emulador; desactivado, el juego no se toca.",
             "For playing with only the emulator's top screen shown (e.g. on a monitor): the touch screen's menus "
             "that play needs move to the top screen: the quest list, the Canteen's ingredients, the yes / no "
             "questions and the title menu. The touch screen still works as before. It only works in the "
             "emulator; switched off, the game is left untouched.")),
        Group(T("Iconos", "Icons"), (
            Option("new_monster_icons", T("Iconos propios, sin «?»", "Icons of their own, no \"?\""),
                   T("Los Fatalis (negro, carmesí y blanco) y Gogmazios reciben un icono propio en lugar de «?» "
                     "en el tablón, la cámara de objetivo y los menús, y las misiones de Dalamadur muestran su "
                     "cabeza y su cola. El Fatalis carmesí súper conserva el «?». Las imágenes son los PNG de "
                     "36×36 de core/interface/monster_icons/icons/ y se pueden sustituir.",
                     "The Fatalis (black, crimson and white) and Gogmazios get an icon of their own instead of "
                     "the \"?\" on the quest board, the target camera and the menus, and Dalamadur's quests show "
                     "its head and its tail. Super Crimson Fatalis keeps the \"?\". The images are the 36×36 PNGs "
                     "of core/interface/monster_icons/icons/ and can be replaced.")),
        )),
    )),
    Section(T("Texto", "Text"), (
        Group(T("Conversaciones", "Conversations"), (
            Option("fast_text", T("Pasar el texto rápido con B", "Fast text with B"),
                   T("Mientras mantienes pulsado B, el texto de las conversaciones aparece de golpe y pasa solo de "
                     "página muy deprisa. Se detiene en las preguntas y los menús, que se siguen eligiendo a mano. "
                     "Suelta B para leer con normalidad.",
                     "While you hold B, conversation text appears at once and turns its pages by itself, very "
                     "fast. It stops at questions and menus, which you still choose by hand. Let go of B to read "
                     "normally.")),
        )),
    )),
    Section(T("Acciones", "Actions"), (
        Group(T("Recolección", "Gathering"), (
            Option("fast_gathering", T(f"Recolectar al {_GATHER_PERCENT} %", f"Gather at {_GATHER_PERCENT}%"),
                   T(f"Recolectar, picar mineral y huesos, cazar insectos, tallar monstruos y pescar van al "
                     f"{_GATHER_PERCENT} % de velocidad. Se suma a la habilidad Recolección rápida. Andar, luchar "
                     "y lo demás van a su velocidad normal.",
                     f"Gathering, mining ore and bones, catching bugs, carving monsters and fishing run at "
                     f"{_GATHER_PERCENT}% speed. It stacks with the Speed Gatherer skill. Walking, fighting and "
                     "everything else keep their normal speed.")),
        ), T("Solo afecta a tu cazador.", "Only your own hunter is affected.")),
        Group(T("Patada", "Kick"), (
            Option("select_kick", T("Patada con SELECT", "Kick with SELECT"),
                   T("SELECT da la patada, el ataque especial del panel táctil, y solo START abre el menú del "
                     "juego. Sin esta opción, SELECT abre el menú igual que START y no hay botón de patada. La "
                     "opción propia del juego «Botón START» sigue como esté.",
                     "SELECT kicks, the touch panel's special attack, and only START opens the Game Menu. "
                     "Without it, SELECT opens the menu like START and there is no kick button. The game's own "
                     "option for the START button stays as it is.")),
        ), T("Sirve para jugar sin la pantalla táctil.", "Meant for playing without the touch screen.")),
        Group(T("Botón A", "A button"), (
            Option("hold_a", T("Mantener A para repetirlo", "Hold A to repeat it"),
                   T("Con el arma guardada, mantener pulsado A repite la pulsación: recoger, recolectar, picar y "
                     "tallar sin machacar el botón. En las recompensas de la misión y en la pantalla de objetos del "
                     "Wyporio, una pulsación de A coge el objeto y el cursor pasa solo al siguiente; si mantienes "
                     "A, sigue cogiendo. Los menús de cambiar o salir siguen pidiendo una pulsación.",
                     "With the weapon sheathed, holding A repeats the press: pick up, gather, mine and carve "
                     "without mashing the button. In the quest rewards and the Wyporium's items screen, one press "
                     "of A takes the item and the cursor moves on to the next by itself; hold A to keep taking. "
                     "The swap and exit menus still need a press each.")),
        )),
    )),
    Section(T("Música", "Music"), (
        Group(T("Monster Hunter World", "Monster Hunter World"), (
            Option("mhw_fatalis_music", T("Música de World para Fatalis negro y carmesí",
                                          "World's music for Black and Crimson Fatalis"),
                   T("Su tema de batalla pasa a ser el de Fatalis de Monster Hunter World; con la mitad de la vida "
                     "suena su segunda fase, y con un 10 % «Proof of a Hero». Si llegó a «Proof of a Hero» y su "
                     "muerte termina la misión, suena el tema de Fatalis abatido en lugar de la música de misión "
                     "completada. Fatalis blanco y Fatalis carmesí súper no cambian.",
                     "Their battle theme becomes Monster Hunter World's Fatalis theme; at half health its second "
                     "phase plays, and at 10 % \"Proof of a Hero\". If \"Proof of a Hero\" played and their death "
                     "ends the quest, World's Fatalis slain theme plays instead of the quest complete music. White "
                     "Fatalis and Crimson Fatalis (Super) do not change.")),
        ), T("La música viene con el randomizer.", "The music comes with the randomizer.")),
    )),
    Section(T("Aspecto", "Looks"), (
        Group(T("Equipo superpuesto", "Layered equipment"), (
            Option("layered_equipment", T("Equipo superpuesto", "Layered equipment"),
                   T("La herrería tiene una entrada nueva, «Equipo superpuesto», para elegir el aspecto de cada "
                     "pieza de armadura (o de un conjunto entero) y de cada tipo de arma, entre los del "
                     "juego, sin cambiar lo que llevas puesto. Tu cazador lleva ese aspecto "
                     "en el pueblo y en las misiones, y se guarda con la partida; la vista previa lo muestra al "
                     "elegir (el stick lo gira).",
                     "The Smithy gets a new line, \"Layered Equipment\", to choose the look of each armor piece "
                     "(or a whole set) and of each weapon class, from the looks in the game, "
                     "without changing what you wear. Your hunter wears that look in the village and in quests, "
                     "and it is kept with the save; the preview shows it as you choose (the stick turns it).")),
            Option("layered_by_rank", T("Desbloquear looks por rango", "Unlock looks by rank"),
                   T("Los aspectos de rango bajo están desde el principio; los de rango alto, tras la misión "
                     "urgente de ★3 del Gremio (o la de ★7 de la Caravana); los de rango G, tras la urgente que "
                     "abre Dundorma. Desactivado, todos los aspectos están desde el principio.",
                     "Low rank looks are there from the start; high rank looks come after the Hall's ★3 urgent "
                     "quest (or the Caravan's ★7); G rank looks after the urgent quest that opens Dundorma. "
                     "Off, every look is there from the start."),
                   requires="layered_equipment"),
        )),
    )),
    Section(T("Trucos", "Cheats"), (
        Group(T("3D", "3D"), (
            Option("cheat_3d_mode", T("3D", "3D"),
                   T("Apaga el 3D estereoscópico del juego. El tramado es el patrón de puntos con el que el juego "
                     "dibuja transparencias y sombreados.",
                     "Turns the game's stereoscopic 3D off. Dithering is the pattern of dots the game uses to draw "
                     "transparency and shading."),
                   choices=(
                       Choice(Cheat3D.OFF, T("Sin cambios", "Unchanged"),
                              T("El 3D del juego, tal como es.", "The game's own 3D.")),
                       Choice(Cheat3D.DITHER_OFF, T("3D desactivado, sin tramado", "3D off, no dithering"),
                              T("Imagen limpia, sin el patrón de puntos.", "A clean image, without the dot pattern.")),
                       Choice(Cheat3D.DITHER_ON, T("3D desactivado, con tramado", "3D off, with dithering"),
                              T("Deja el patrón de puntos del juego.", "Keeps the game's dot pattern.")),
                   ), emulator_only=True),
            Option("cheat_no_bloom_dof", T("Sin bloom ni desenfoque de profundidad",
                                           "No bloom or depth of field"),
                   T("Quita el resplandor y el desenfoque de lo que queda lejos: la imagen se ve más nítida.",
                     "Removes the glow and the blur of distant things: the picture looks sharper."),
                   emulator_only=True),
        ), T("Trucos de imagen. Solo funcionan en el emulador.", "Picture cheats. They only work in the emulator.")),
        Group(T("Imágenes por segundo", "Frame rate"), (
            Option("cheat_fps", T("FPS", "FPS"),
                   T("El juego va siempre a las imágenes por segundo que elijas.",
                     "The game always runs at the frames per second you choose."),
                   choices=(
                       Choice(CheatFps.GAME, T("Las del juego", "The game's own")),
                       Choice(CheatFps.F30, T("30 FPS", "30 FPS"),
                              T("Recomendado si tu PC es de gama baja.", "Recommended on a low-end PC.")),
                       *(Choice(rate, T(f"{rate.value} FPS", f"{rate.value} FPS"))
                         for rate in CheatFps if rate.rate > 30),
                   ), compact=True, emulator_only=True),
        ), T("Se recomiendan 30 FPS si tienes un PC de gama baja. Solo funciona en el emulador.",
             "30 FPS is recommended on a low-end PC. It only works in the emulator.")),
        Group(T("Proporción de la imagen", "Aspect ratio"), (
            Option("cheat_aspect_allowed", T("Permitir otras proporciones", "Allow other aspect ratios"),
                   T("Activa la lista de proporciones, que aún está en pruebas, y su lista dentro del juego: START, "
                     "tercera página, Ajustes del mod.",
                     "Turns on the list of aspect ratios, which is still being tested, and its list inside the game: "
                     "START, third page, Mod Settings."),
                   emulator_only=True),
            Option("cheat_aspect_ratio", T("Proporción", "Aspect ratio"),
                   T("Ajusta el juego a la forma de la imagen del emulador, para que nada se vea estirado.",
                     "Fits the game to the shape of the emulator's picture, so nothing looks stretched."),
                   choices=(
                       Choice(CheatAspect.OFF, T("5:3, la del juego", "5:3, the game's own")),
                       *(Choice(ratio, T(ratio.value, ratio.value)) for ratio in CheatAspect
                         if ratio is not CheatAspect.OFF),
                   ), requires="cheat_aspect_allowed", compact=True, emulator_only=True),
        ), T("Aviso: aún está en pruebas y puede haber menús o indicaciones mal colocados. Por favor, informa de "
             "cualquier problema que veas. El emulador debe mostrar la imagen con esa forma: en Azahar, Single Screen "
             "con Stretch. Elige aquí la que vayas a usar: dentro del juego, los fondos y algunas filas siguen en la "
             "de la instalación. Solo funciona en el emulador.",
             "Warning: this is still in testing, and some menus or prompts may be out of place. Please report any "
             "problem you see. The emulator must show the picture in that shape: in Azahar, Single Screen with "
             "Stretch. Choose here the one you will use: inside the game, backgrounds and some rows stay at the "
             "installed one. It only works in the emulator.")),
        Group(T("Campo de visión", "Field of view"), (
            Option("cheat_fov", T("Campo de visión", "Field of view"),
                   T("El juego usa 50; con un valor más alto se ve más alrededor del cazador.",
                     "The game uses 50; a higher value shows more around the hunter."),
                   minimum=_FOV_MIN, maximum=_FOV_MAX, emulator_only=True),
        ), T("Truco de mikewii7. Solo funciona en el emulador.", "Cheat by mikewii7. It only works in the emulator.")),
        Group(T("Juego en línea", "Online"), (
            Option("cheat_net_fix", T("Arreglo de red", "Net fix"),
                   T("Al crear una sala o unirte a una, la conexión espera mucho más antes de rendirse, para que "
                     "las salas en línea del emulador no fallen por una conexión lenta.",
                     "When you host or join a room, the connection waits much longer before giving up, so the "
                     "emulator's online rooms do not fail on a slow connection."),
                   emulator_only=True),
        ), T("Truco de Klark231. Solo funciona en el emulador.", "Cheat by Klark231. It only works in the emulator.")),
        Group(T("Armas", "Weapons"), (
            Option("cheat_raw_unbloat", T("Ataque real de las armas", "Weapons' true attack"),
                   T("Los menús muestran el ataque real de cada arma, sin el multiplicador que el juego le aplica "
                     "según su tipo.",
                     "Menus show each weapon's true attack, without the multiplier the game applies by weapon "
                     "type."),
                   emulator_only=True),
        ), T("Solo cambian los números que se ven, no el daño. Solo funciona en el emulador.",
             "Only the numbers shown change, not the damage. It only works in the emulator.")),
        Group(T("Depuración", "Debug"), (
            Option("cheat_insta_kill", T("Muerte instantánea", "Insta kill"),
                   T("El ataque del cazador se multiplica: cada golpe derriba a un monstruo al instante.",
                     "The hunter's attack is multiplied: every hit brings a monster down at once."),
                   emulator_only=True),
        ), T("Para probar misiones, no para jugar. Solo funciona en el emulador.",
             "For testing quests, not for playing. It only works in the emulator.")),
    )),
)

NEW_GAME_SECTIONS: tuple[Section, ...] = (
    Section(T("Objetos iniciales", "Starting items"), (
        Group(T("Caja de objetos", "Item box"), (
            Option("starting_kit", T("Kit inicial", "Starting kit"),
                   T("Al crear una partida nueva, la caja de objetos trae un kit fijo, el mismo para todos: "
                     "pociones, megapociones, bebidas frías y calientes, piedras de afilar, bolas de pintura, "
                     "trampas, bombas tranquilizantes, drogas, filetes, carne cruda y herramientas de la mejor "
                     "calidad, la mayoría ×99, además de los objetos originales. Los sets de objetos no cambian.",
                     "When you create a new game, the item box holds a fixed kit, the same for everyone: "
                     "potions, mega potions, cool and hot drinks, whetstones, paintballs, traps, tranq bombs, "
                     "drugs, steaks, raw meat and the best gathering tools, most of them ×99, plus the original "
                     "items. The item sets do not change.")),
        ), T("Solo afecta a las partidas que se creen con el mod puesto; las existentes no cambian.",
             "Only saves created with the mod installed are affected; existing ones do not change.")),
    )),
    Section(T("Inicio de la partida", "Game start"), (
        Group(T("Prólogo", "Prologue"), (
            Option("skip_intro", T("Saltar la introducción", "Skip the intro"),
                   T("Un personaje nuevo empieza directamente en Val Habar, ya registrado en el Gremio: sin el "
                     "prólogo en el barco de arena, sin las escenas de llegada y registro y sin la presentación del "
                     "Gran Salón. Recibe lo que daba el prólogo (1500z y la armadura inicial puesta) y RC 1; el "
                     "Gran Salón y el juego en línea están disponibles desde el principio. La caravana y sus "
                     "misiones siguen como en el juego original.",
                     "A new character starts in Val Habar, already registered with the Guild: no prologue on the "
                     "sand ship, no arrival and registration scenes and no Gathering Hall introduction. It gets what "
                     "the prologue gave (1500z and the starting armor, worn) and HR 1; the Gathering Hall and online "
                     "play are open from the start. The caravan and its quests stay as in the original game.")),
            Option("skip_caravan_tutorial", T("Saltar el tutorial de la caravana", "Skip the caravan tutorial"),
                   T("Solo con «Saltar la introducción». El personaje nuevo ya tiene hecho lo que deja el tutorial "
                     "de la caravana: la charla del Caravanero y sus misiones iniciales (101 y 102) y las misiones de "
                     "entrenamiento completadas, y el primer Felyne ya es su compañero, con el equipo puesto, listo "
                     "para las misiones de la caravana. La caravana sigue en ★1.",
                     "Only with \"Skip the intro\". The new character already has what the caravan tutorial leaves: "
                     "the Caravaneer's talk, his first two quests (101 and 102) and the Training quests done, and "
                     "the first Felyne is already the partner, equipped and ready for the caravan quests. The "
                     "caravan stays at ★1."),
                   requires="skip_intro"),
        ), T("Solo afecta a los personajes que se creen con el mod puesto; las partidas existentes no cambian.",
             "Only characters created with the mod installed are affected; existing saves do not change.")),
    )),
)

NEW_MONSTER_SECTIONS: tuple[Section, ...] = (
    Section(T("Monstruos de MH Generations", "Monsters from MH Generations"), (
        Group(T("Alatreon", "Alatreon"), (
            Option("alatreon", T("Alatreon", "Alatreon"),
                   T("Alatreon de Monster Hunter Generations, con su modelo, sus ataques, su música y sus sonidos. "
                     "Elige dónde aparece.",
                     "Alatreon from Monster Hunter Generations, with his model, attacks, music and sounds. Choose "
                     "where he appears."),
                   choices=(
                       Choice(AlatreonMode.OFF, T("No", "No")),
                       Choice(AlatreonMode.FINAL_BOSS, T("Jefe final", "Final boss"),
                              T("Su misión, en la Isla Ingle, sustituye a la misión urgente de Gogmazios de G★3 "
                                "(«Quagmire Quarrel») y se queda con sus recompensas. El randomizer no toca esa "
                                "misión y Alatreon no sale en ninguna otra.",
                                "His quest, on Ingle Isle, replaces Gogmazios' G★3 urgent quest (\"Quagmire "
                                "Quarrel\") and keeps its rewards. The randomizer leaves that quest alone and "
                                "Alatreon appears in no other.")),
                       Choice(AlatreonMode.EXTRA_QUEST, T("Misión extra", "Extra quest"),
                              T("Al superar la misión urgente de Gogmazios aparece una misión nueva de G★3, «El "
                                "triunfo del amanecer», con Alatreon en la Isla Ingle y las recompensas de la "
                                "misión de Gogmazios. Las demás misiones no cambian.",
                                "Clearing Gogmazios' urgent quest unlocks a new G★3 quest, \"Dawn's Triumph\", "
                                "with Alatreon on Ingle Isle and the rewards of Gogmazios' quest. The other quests "
                                "do not change.")),
                       Choice(AlatreonMode.RANDOMIZED, T("En el randomizer", "In the randomizer"),
                              T("Entra en el reparto de monstruos como uno del nivel más alto, solo en la Isla "
                                "Ingle (su mapa), en cualquier oleada, nunca con Fatalis carmesí y nunca dos veces "
                                "en una misión. Necesita «Randomizar misiones» y «Randomizar monstruos grandes»; "
                                "con mapas aleatorios y la Isla Ingle permitida sale más a menudo.",
                                "He joins the monster shuffle as one of the top tier, only on Ingle Isle (his map), "
                                "in any wave, never with Crimson Fatalis and never twice in a quest. Needs "
                                "\"Randomize quests\" and \"Randomize large monsters\"; with random maps and Ingle "
                                "Isle allowed he shows up more often.")),
                       Choice(AlatreonMode.FIELD_TRIP, T("En «Field Trip» (antiguo)", "In \"Field Trip\" (old)"),
                              T("Las primeras versiones: su misión sustituía a la de 1★ «Field Trip» (10110).",
                                "The first versions: his quest replaced the 1★ quest \"Field Trip\" (10110)."),
                              legacy=True),
                   )),
            Option("alatreon_music", T("Música", "Music"),
                   T("La música de su combate.", "The music of his fight."),
                   choices=(
                       Choice(AlatreonMusic.ORIGINAL, T("Original", "Original"),
                              T("Su tema de MH Generations. Si su muerte termina la misión, suena el tema de "
                                "Alatreon abatido de Monster Hunter World.",
                                "His MH Generations theme. If his death ends the quest, Monster Hunter World's "
                                "Alatreon slain theme plays.")),
                       Choice(AlatreonMusic.MODERN, T("Moderna", "Modern"),
                              T("Su tema de Monster Hunter World; con un 10 % de vida, «Proof of a Hero», y si su "
                                "muerte termina la misión, el tema de Fatalis abatido.",
                                "His Monster Hunter World theme; at 10 % health \"Proof of a Hero\", and if his "
                                "death ends the quest, the Fatalis slain theme.")),
                   ), requires="alatreon"),
        ), T("Se construye a partir de tu ROM descifrada de MH Generations (elígela al lado); el mod no "
             "lleva nada de ese juego. Es un monstruo nuevo, con su nombre, su icono (provisional) y su música; "
             "no sustituye a ningún otro.",
             "It is built from your decrypted MH Generations ROM (choose it alongside); the mod carries nothing "
             "of that game. He is a new "
             "monster, with his own name, icon (a placeholder) and music; he replaces no other.")),
        Group(T("Mizutsune", "Mizutsune"), (
            Option("mizutsune", T("Mizutsune", "Mizutsune"),
                   T("Mizutsune de Monster Hunter Generations, con su modelo, sus ataques, sus burbujas, su música y "
                     "sus sonidos. Cambia de zona por la Selva Jurásica como un monstruo de MH4U.",
                     "Mizutsune from Monster Hunter Generations, with his model, attacks, bubbles, music and sounds. "
                     "He changes area on the Primal Forest as an MH4U monster does."),
                   choices=(
                       Choice(MizutsuneMode.OFF, T("No", "No")),
                       Choice(MizutsuneMode.QUESTS, T("Sus misiones", "His quests"),
                              T("Tres misiones nuevas de la sala de reunión, con Mizutsune en la Selva Jurásica: "
                                "rango bajo 3★, rango alto 6★ y rango G G★1, con las recompensas de las misiones de "
                                "Zinogre de ese rango. Aparecen al superar la misión urgente que abre su rango (o "
                                "su estrella). Las demás misiones no cambian.",
                                "Three new Gathering Hall quests with Mizutsune on the Primal Forest: low rank 3★, "
                                "high rank 6★ and G rank G★1, with the rewards of Zinogre's quests of that rank. "
                                "They show once the urgent quest that opens their rank (or star) is cleared. The "
                                "other quests do not change.")),
                       Choice(MizutsuneMode.RANDOMIZED, T("Solo en el randomizer", "Randomizer only"),
                              T("Entra en el reparto de monstruos un nivel por encima de Zinogre, en cualquier mapa "
                                "y con cualquier monstruo, sin misiones propias. Con «Los monstruos cambian de zona "
                                "en cualquier mapa» lo hace también en los mapas que Zinogre no recorre. Necesita "
                                "«Randomizar misiones» y «Randomizar monstruos grandes».",
                                "He joins the monster shuffle one tier above Zinogre, on any map and with any "
                                "monster, without quests of his own. With \"Monsters change area on any map\" he also "
                                "does on the maps Zinogre does not roam. Needs \"Randomize quests\" and \"Randomize "
                                "large monsters\".")),
                       Choice(MizutsuneMode.EXTENDED, T("Sus misiones, randomizadas", "His quests, randomized"),
                              T("Sus tres misiones existen y el randomizer las cambia como cualquier otra; además "
                                "entra en el reparto de monstruos. Necesita «Randomizar misiones» y «Randomizar "
                                "monstruos grandes» para entrar en el reparto.",
                                "His three quests exist and the randomizer changes them as any other; he also joins "
                                "the monster shuffle. Needs \"Randomize quests\" and \"Randomize large monsters\" to "
                                "join the shuffle.")),
                   )),
        ), T("Como Alatreon, se construye a partir de tu ROM de MH Generations. Es un monstruo nuevo, con su nombre, "
             "su icono y su música; no sustituye a ningún otro.",
             "As Alatreon, he is built from your MH Generations ROM. He is a new "
             "monster, with his own name, icon and music; he replaces no other.")),
        Group(T("Glavenus", "Glavenus"), (
            Option("glavenus", T("Glavenus", "Glavenus"),
                   T("Glavenus de Monster Hunter Generations, con su modelo, sus ataques de fuego, su cola-espada, su "
                     "música y sus sonidos. Cambia de zona por el Hoyo Volcán y la Sima Hueca como un monstruo de "
                     "MH4U.",
                     "Glavenus from Monster Hunter Generations, with his model, fire attacks, blade tail, music and "
                     "sounds. He changes area on the Volcanic Hollow and the Sunken Hollow as an MH4U monster does."),
                   choices=(
                       Choice(GlavenusMode.OFF, T("No", "No")),
                       Choice(GlavenusMode.QUESTS, T("Sus misiones", "His quests"),
                              T("Cuatro misiones nuevas de la sala de reunión: con Glavenus en el Hoyo Volcán, rango "
                                "bajo 3★, rango alto 6★ y rango G G★1, y una de rango G G★2 con Glavenus y Mizutsune "
                                "en la Sima Hueca (solo si Mizutsune está activado). Aparecen al superar la misión "
                                "urgente que abre su rango (la de G★2, al superar la de G★1). Las demás misiones "
                                "no cambian.",
                                "Four new Gathering Hall quests: with Glavenus on the Volcanic Hollow, low rank 3★, "
                                "high rank 6★ and G rank G★1, and a G rank G★2 one with Glavenus and Mizutsune on "
                                "the Sunken Hollow (only while Mizutsune is on). They show once the urgent quest "
                                "that opens their rank is cleared (the G★2 one, once the G★1 one is). The other "
                                "quests do not change.")),
                       Choice(GlavenusMode.RANDOMIZED, T("Solo en el randomizer", "Randomizer only"),
                              T("Entra en el reparto de monstruos en el nivel 4, en cualquier mapa y con cualquier "
                                "monstruo, sin misiones propias. Con «Los monstruos cambian de zona en cualquier "
                                "mapa» lo hace también en los mapas que Deviljho no recorre. Necesita «Randomizar "
                                "misiones» y «Randomizar monstruos grandes».",
                                "He joins the monster shuffle at tier 4, on any map and with any monster, without "
                                "quests of his own. With \"Monsters change area on any map\" he also does on the maps "
                                "Deviljho does not roam. Needs \"Randomize quests\" and \"Randomize large "
                                "monsters\".")),
                       Choice(GlavenusMode.EXTENDED, T("Sus misiones, randomizadas", "His quests, randomized"),
                              T("Sus misiones existen y el randomizer las cambia como cualquier otra; además entra "
                                "en el reparto de monstruos. Necesita «Randomizar misiones» y «Randomizar monstruos "
                                "grandes» para entrar en el reparto.",
                                "His quests exist and the randomizer changes them as any other; he also joins the "
                                "monster shuffle. Needs \"Randomize quests\" and \"Randomize large monsters\" to join "
                                "the shuffle.")),
                   )),
        ), T("Como los otros, se construye a partir de tu ROM de MH Generations. Es un monstruo nuevo, con su nombre, "
             "su icono y su música; no sustituye a ningún otro.",
             "Like the others, he is built from your MH Generations ROM. He is a new "
             "monster, with his own name, icon and music; he replaces no other.")),
    ), inputs=("mhgen",)),
)

AREAS: tuple[Area, ...] = (
    Area(T("Misiones", "Quests"), QUEST_SECTIONS,
         Option("randomize_quests", T("Randomizar misiones", "Randomize quests"),
                T("Desactivado, las misiones quedan como en el juego original y se ignoran todas las opciones de "
                  "esta pestaña.",
                  "When off, quests stay as in the original game and every option of this tab is ignored."))),
    Area(T("Equipo", "Equipment"), EQUIPMENT_SECTIONS,
         Option("randomize_equipment", T("Randomizar equipo", "Randomize equipment"),
                T("Desactivado, el equipo queda como en el juego original (el ejecutable no se parchea por esto) y "
                  "se ignoran todas las opciones de esta pestaña.",
                  "When off, equipment stays as in the original game (the executable is not patched for it) and "
                  "every option of this tab is ignored."))),
    Area(T("Partida nueva", "New game"), NEW_GAME_SECTIONS),
    Area(T("Extra", "Extra"), INTERFACE_SECTIONS),
    Area(T("Monstruos adicionales", "Additional monsters"), NEW_MONSTER_SECTIONS,
         Option("additional_monsters", T("Monstruos adicionales", "Additional monsters"),
                T("Desactivado, no se añade ningún monstruo y se ignoran todas las opciones de esta pestaña.",
                  "When off, no monster is added and every option of this tab is ignored."))),
)
SECTIONS: tuple[Section, ...] = (QUEST_SECTIONS + EQUIPMENT_SECTIONS + NEW_GAME_SECTIONS + INTERFACE_SECTIONS
                                 + NEW_MONSTER_SECTIONS)


def area_options(area: Area) -> list[Option]:
    """The options of an area's sections (not its master switch)."""
    return [option for section in area.sections for group in section.groups for option in group.options]


def hidden_on_console() -> set[str]:
    """The fields the 3DS platform hides: the emulator-only options and those that require one of them."""
    hidden = {option.field for option in all_options() if option.emulator_only}
    grown = True
    while grown:
        more = {option.field for option in all_options() if option.requires in hidden}
        grown = not more <= hidden
        hidden |= more
    return hidden


def area_masters() -> list[Option]:
    return [area.master for area in AREAS if area.master]


def all_options() -> list[Option]:
    return area_masters() + [option for section in SECTIONS for group in section.groups for option in group.options]


def all_texts() -> list[T]:
    """Every translatable text of the option panels (for tests)."""
    texts = [area.title for area in AREAS]
    for master in area_masters():
        texts += [master.label, master.tooltip]
    for section in SECTIONS:
        texts.append(section.title)
        for group in section.groups:
            texts.append(group.title)
            if group.description is not EMPTY:
                texts.append(group.description)
            if group.hint:
                texts += [group.hint.on, group.hint.off]
            for option in group.options:
                texts += [t for t in (option.label, option.tooltip) if t is not EMPTY]
                for choice in option.choices:
                    texts += [t for t in (choice.label, choice.tooltip) if t is not EMPTY]
    return texts


# --- The GUI (Qt): the installer's options and the randomizer's areas ---------------------------------------
# Which field goes where is decided by curated/gui_presets.json (presets.py): what a new run fixes has no widget, the
# installer's options live in INSTALL_SECTIONS only, and the randomizer shows the rest. The panels above are the
# catalogue they are cut from.

def _filter(sections: tuple[Section, ...], keep) -> tuple[Section, ...]:
    """The sections with only the options whose field `keep(field)` accepts, then without the empty groups and
    sections. A `requires` / `also_with` / hint field that is gone no longer constrains the option (a fixed field
    is not a choice)."""
    def option(o: Option) -> Option:
        changes = {}
        if o.requires is not None and not keep(o.requires):
            changes["requires"] = None
        if o.also_with is not None and not keep(o.also_with):
            changes["also_with"] = None
        return replace(o, **changes) if changes else o

    def group(g: Group) -> Group | None:
        options = tuple(option(o) for o in g.options if keep(o.field))
        if not options:
            return None
        hint = g.hint
        if hint is not None:
            fields = tuple(f for f in hint.fields if keep(f))
            hint = replace(hint, fields=fields) if fields else None
        return replace(g, options=options, hint=hint)

    result = []
    for section in sections:
        groups = tuple(g for g in map(group, section.groups) if g)
        if groups:
            result.append(replace(section, groups=groups))
    return tuple(result)


def prune(sections: tuple[Section, ...], drop: set[str]) -> tuple[Section, ...]:
    """The sections without the options of the fields in `drop`, and without the groups and sections left empty.
    What required or hinted at a dropped field no longer does."""
    return _filter(sections, lambda field: field not in drop)


def _find(field: str) -> Option:
    return next(o for o in all_options() if o.field == field)


def _install_sections() -> tuple[Section, ...]:
    kept = set(presets.section("install_options"))
    sections = _filter(INTERFACE_SECTIONS + NEW_GAME_SECTIONS + NEW_MONSTER_SECTIONS, lambda field: field in kept)
    links = presets.install_links()
    swaps = {
        "skip_intro": Option(
            "skip_intro", T("Empezar en Val Habar con la caravana hecha", "Start in Val Habar with the caravan done"),
            T("Un personaje nuevo empieza directamente en Val Habar, ya registrado en el Gremio, sin el prólogo, las "
              "escenas de llegada y la presentación del Gran Salón. Recibe 1500z, la armadura inicial y RC 1, y ya "
              "tiene hecho el tutorial de la caravana: el primer Felyne es su compañero, con el equipo puesto, listo "
              "para las misiones de la caravana.",
              "A new character starts in Val Habar, already registered with the Guild, without the prologue, the "
              "arrival scenes and the Gathering Hall introduction. It gets 1500z, the starting armor and HR 1, and "
              "the caravan tutorial is already done: the first Felyne is the partner, equipped and ready for the "
              "caravan quests."),
            links=tuple(links.get("skip_intro", ()))),    # an edition without it has no such link
    }
    result = []
    for section in sections:
        groups = []
        for g in section.groups:
            options = tuple(swaps.get(o.field, o) for o in g.options)
            groups.append(replace(g, options=options))
        result.append(replace(section, groups=tuple(groups), inputs=()))
    return tuple(result)


def _alatreon_option() -> Option:
    """The randomizer's one Alatreon option: the retired choices (gui_presets.json `legacy_choices`) last."""
    option = _find("alatreon")
    legacy = presets.legacy_choices().get("alatreon", [])
    choices = [replace(c, legacy=c.legacy or c.value.value in legacy) for c in option.choices]
    return replace(option, choices=tuple(sorted(choices, key=lambda c: c.legacy)))


def _randomizer_areas() -> tuple[Area, ...]:
    drop = presets.fixed_fields("randomizer") | presets.installer_fields() | {"alatreon"}
    new_monsters = Section(T("Monstruos nuevos", "New monsters"), (
        Group(T("Alatreon", "Alatreon"), (_alatreon_option(),),
              T("Se construye a partir de tu ROM descifrada de MH Generations. «Jefe final» es lo recomendado.",
                "It is built from your decrypted MH Generations ROM. \"Final boss\" is the recommended one.")),
    ))
    return (
        Area(AREAS[0].title, prune(QUEST_SECTIONS, drop) + (new_monsters,), AREAS[0].master),
        Area(AREAS[1].title, prune(EQUIPMENT_SECTIONS, drop), AREAS[1].master),
    )


INSTALL_SECTIONS: tuple[Section, ...] = _install_sections()
RANDOMIZER_AREAS: tuple[Area, ...] = _randomizer_areas()
