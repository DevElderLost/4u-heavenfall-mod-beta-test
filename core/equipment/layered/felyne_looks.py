"""The Felynes' looks of layered equipment: the game's own Felyne armor and weapons and, in a build with its models, MH
XX's, as looks for the player's active cats.

A look of MH XX is a model folder for one part (head, body, weapon), at its fixed MH4U number
(felyne_pack.model_number). That catalog comes from `curated/felyne_looks_names.json`, which holds each look's rarity
and its names in five languages (research/porting/xx_names.py --felyne); a look whose file a game lacks is left out. Its
archives are converted by a run (felyne_pack.convert_models). The game's own rows come from its clean tables
(looks.build_felyne_rows, in the generated look lists) and read their names from the game's texts
(texts.felyne_piece_names).

The block felyne_looks_data (struct felyne_data in felyne_looks.h) gives the render hooks the numbers that exist in this
build and the pieces the game's code goes by the id of. The screens list everything by model number (FelyneRow, in the
block layered_rules).
"""

import json
import struct
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from core.equipment.mhgen.felyne_pack import FELYNE_IDS, PARTS, FelynePack, convert_models, mhgen_file, model_number
from core.equipment.layered.looks import LANGUAGES, common_name, generated_felyne_rows
from core.equipment.mhgen.looks import rank_of
from core.game.data.paths import CURATED_DIR

NAMES_FILE = CURATED_DIR / "felyne_looks_names.json"
LOOK_PARTS = ("head", "body", "weapon")     # the order of the block's bitmaps and of the look word's fields
PACK_PARTS = {"head": "helm", "body": "body", "weapon": "we"}    # felyne_pack.PARTS' key of each
BLOCK_SIZE = 0x100                          # game/executable/blocks.py, felyne_looks_data
DATA_MAGIC = 0x4C454646                     # "FFEL"
KNOWN_BYTES = 42                            # felyne_looks.h: a bit per model number, for each part
CASES = 10                                  # felyne_looks.h, FELYNE_CASES: looks.CASE_PIECES' pieces
CASE = struct.Struct("<H2B")                # a model number; its part (LOOK_PARTS); the piece the game knows by its id
# magic; looks; numbers the bitmaps hold; the messages; the bitmaps; the cases
HEADER = struct.Struct(f"<I2H3H2x{3 * KNOWN_BYTES}s2x{CASES * CASE.size}s")
MESSAGES = ("felynes", "felyne_none", "felyne_choose")
assert (FELYNE_IDS + 7) // 8 == KNOWN_BYTES and HEADER.size == 184 and tuple(PARTS.values()) == ("h", "b", "w")
GAME_MH4U, GAME_GENERATIONS = 0, 1          # a row's game: the screen's filter (layered_forge.c, GAME_MH4U, GAME_GEN)
GAME_FILES = {"head": "o_helm", "body": "o_body", "weapon": "o_we"}    # data/<name>NNN.arc, or in loc/data


@dataclass(frozen=True)
class FelyneLook:
    part: str                 # LOOK_PARTS
    source: int               # MH XX's model folder
    rarity: int               # 1-11
    names: Mapping[str, str]  # language -> name
    price: int = 0            # what forging its piece cost in MH XX (xx_felyne_prices; 0: unknown)

    @property
    def model(self) -> int:
        return model_number(self.source)

    @property
    def rank(self) -> int:
        return rank_of(self.rarity)


@dataclass(frozen=True)
class FelyneRow:
    """What the forge-style screen lists for the Felynes: all the looks of one model number (a head, a body and a weapon
    of one set; a model that exists for fewer parts has fewer)."""
    number: int
    parts: int                # bit i: LOOK_PARTS[i] exists
    rank: int                 # 1 low, 2 high, 3 G
    rarity: int
    names: Mapping[str, str]  # language -> the armor pieces' common name, else the weapon's (MH XX's rows)
    game: int = GAME_GENERATIONS
    pieces: Mapping[str, int] = field(default_factory=dict)    # the game's rows: part -> the piece that names it
    forge: tuple[str, ...] | None = None                       # the game's rows: when it appears (forge_rule)
    cases: Mapping[str, int] = field(default_factory=dict)     # part -> its piece of looks.CASE_PIECES
    price: int = 0                                             # MH XX's rows: what forging its pieces cost


@dataclass(frozen=True)
class FelyneLooks:
    """The looks of the run: MH XX's per part in list order (by rarity, as the curated file), which a run converts and
    `len` counts, and the rows of the game's own gear."""
    looks: Mapping[str, tuple[FelyneLook, ...]]
    game: tuple[FelyneRow, ...] = ()

    def all(self) -> list[FelyneLook]:
        return [look for part in LOOK_PARTS for look in self.looks[part]]

    def __len__(self) -> int:
        return sum(len(self.looks[part]) for part in LOOK_PARTS)


NO_LOOKS = FelyneLooks({part: () for part in LOOK_PARTS})


def felyne_rows(looks: FelyneLooks) -> list[FelyneRow]:
    """The rows of `looks`, by rank, within it the game's own before MH XX's, each by rarity and then model number. A
    row of MH XX has the lowest rarity of its parts (the game's parts of one model share it)."""
    by_number: dict[int, dict[str, FelyneLook]] = defaultdict(dict)
    for look in looks.all():
        by_number[look.model][look.part] = look
    rows = []
    for number, parts in by_number.items():
        first = min(parts.values(), key=lambda look: look.rarity)
        armor = [parts[part] for part in LOOK_PARTS[:2] if part in parts] or [parts["weapon"]]
        names = {lang: common_name(look.names.get(lang) or look.names["eng"] for look in armor) for lang in LANGUAGES}
        rows.append(FelyneRow(number, sum(1 << LOOK_PARTS.index(part) for part in parts), first.rank, first.rarity,
                              names, price=sum(look.price for look in parts.values())))
    return sorted((*rows, *looks.game), key=lambda row: (row.rank, row.game, row.rarity, row.number))


def load_catalog(exists=None, prices: Mapping[tuple[str, int], int] | None = None) -> FelyneLooks:
    """The curated looks; `exists(path)`, if given, keeps those whose file MH XX has (a RomFS's `exists`). `prices`:
    (part, model folder) -> what forging the piece cost in MH XX (felyne_pack.xx_felyne_prices); none: unknown."""
    data = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
    prices = prices or {}
    looks = {}
    for part in LOOK_PARTS:
        rows = []
        for source, row in data[part].items():
            names = {lang: name for lang, name in row.items() if lang != "rarity"}
            look = FelyneLook(part, int(source), row["rarity"], names, prices.get((part, int(source)), 0))
            if exists is None or exists(mhgen_file(look.source, PACK_PARTS[part])):
                rows.append(look)
        looks[part] = tuple(rows)
    return FelyneLooks(looks)


def _game_file_exists(exists, part: str, number: int) -> bool:
    name = f"data/{GAME_FILES[part]}{number:03d}.arc"
    return exists(name) or exists(f"loc/{name}")


def load_game_rows(exists=None) -> tuple[FelyneRow, ...]:
    """The rows of the game's own gear, by rarity and number; `exists(path)`, if given, keeps the parts whose file this
    game has (a RomFS's `exists`). A row with no part left is none."""
    rows = []
    for record in generated_felyne_rows():
        pieces = {part: piece for part, piece in record["pieces"].items()
                  if exists is None or _game_file_exists(exists, part, record["number"])}
        if pieces:
            rows.append(FelyneRow(record["number"], sum(1 << LOOK_PARTS.index(part) for part in pieces),
                                  rank_of(record["rarity"]), record["rarity"], {}, GAME_MH4U, pieces,
                                  tuple(record["forge"]),
                                  {part: piece for part, piece in record.get("cases", {}).items() if part in pieces}))
    return tuple(sorted(rows, key=lambda row: (row.rarity, row.number)))


def run_catalog(game_exists, xx_exists=None, xx_prices: Mapping[tuple[str, int], int] | None = None) -> FelyneLooks:
    """The Felyne looks of a run: the game's own rows, whose files `game_exists` finds (None: no game files, no rows),
    and MH XX's looks when the run has its models (`xx_exists`: its RomFS's `exists`), with what forging each piece
    cost there (`xx_prices`: felyne_pack.xx_felyne_prices)."""
    if game_exists is None:
        return NO_LOOKS
    looks = load_catalog(xx_exists, xx_prices).looks if xx_exists else NO_LOOKS.looks
    return FelyneLooks(looks, load_game_rows(game_exists))


def convert_looks(xx, m4, looks: FelyneLooks) -> FelynePack:
    """The archives of `looks`, read from MH XX's RomFS `xx`, and what the executable's tables need for them."""
    parts: dict[int, set[str]] = {}
    for look in looks.all():
        parts.setdefault(look.source, set()).add(PACK_PARTS[look.part])
    sources = sorted(parts)
    return convert_models(None, m4, sources, xx, sources, parts)


def felyne_data(looks: FelyneLooks, messages: Mapping[str, int]) -> bytes:
    """The block felyne_looks_data: `messages` are the E_makeshop messages of the screens' own lines, by MESSAGES' keys.
    `total` counts the parts of every look, MH XX's and the game's. Its size is BLOCK_SIZE."""
    known = bytearray(3 * KNOWN_BYTES)
    for index, part in enumerate(LOOK_PARTS):
        for look in looks.looks[part]:
            if look.model >= FELYNE_IDS:
                raise ValueError(f"Felyne look of folder {look.source}: number {look.model} is past the tables")
            known[index * KNOWN_BYTES + look.model // 8] |= 1 << (look.model % 8)
    cases = []
    for row in looks.game:
        for part, piece in row.cases.items():
            cases.append(CASE.pack(row.number, LOOK_PARTS.index(part), piece))
        for part in row.pieces:
            at = LOOK_PARTS.index(part) * KNOWN_BYTES + row.number // 8
            known[at] |= 1 << (row.number % 8)
    if len(cases) > CASES:
        raise ValueError(f"{len(cases)} pieces the game goes by the id of, the block holds {CASES}")
    total = len(looks) + sum(len(row.pieces) for row in looks.game)
    data = HEADER.pack(DATA_MAGIC, total, FELYNE_IDS, *(messages[key] for key in MESSAGES), bytes(known),
                       b"".join(cases))
    return data + bytes(BLOCK_SIZE - len(data))


def look_word(numbers: Iterable[int]) -> int:
    """The word a record holds at + 0x74 (felyne_looks.c): the three numbers, LOOK_PARTS' order, and its mark."""
    head, body, weapon = numbers
    return 1 << 30 | weapon << 20 | body << 10 | head
