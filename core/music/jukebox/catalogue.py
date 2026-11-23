"""The jukebox's track catalogue (curated/jukebox.json): which complete themes a playlist can
hold, which of them a build has and each one's name in the five languages.

A track's name is a monster (the retail quests' name, curated/monster_names.json), a map (the game's own `mapName`
text), a message of the game's texts (an archive, a message file, a message number) or text written in the five
languages, with an optional suffix (a variant). The module is shared with Heavenfall
Beta, so nothing of a left-out subsystem is imported here: the game's files are read through the function a caller
passes (`read`: RomFS path -> bytes) and the heavier readers are imported inside the functions that use them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from core.game.data.paths import CURATED_DIR

CATALOGUE_FILE = CURATED_DIR / "jukebox.json"
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
SOURCES = ("retail", "mhw", "ported", "extra", "xx", "xx_all")
XX_SOURCES = ("xx", "xx_all")           # read from the player's MH XX, both only with the option jukebox_xx: xx its
                                        # four village themes, xx_all its other songs (xx_tracks.py)
SHIPPED_SOURCES = ("mhw", "extra")      # tracks whose .mca the mod ships; their path is relative to the checkout's top
CHECKOUT = Path(__file__).resolve().parents[3]
MONSTER_NAMES_FILE = CURATED_DIR / "monster_names.json"
_NAME_KEYS = {"eng": "en", "fre": "fr", "ger": "de", "ita": "it", "spa": "es"}       # monster_names.json's keys
COMMON_ARC = "{lang}/data/core_common.arc"
MAP_NAME_STEM = "mapName"
MESSAGE_ARC = "{lang}/data/{arc}.arc"
_MESSAGE_KEYS = {"arc", "file", "id"}


class CatalogueError(ValueError):
    """The catalogue file is malformed."""


@dataclass(frozen=True)
class Track:
    id: int
    path: str
    category: str
    source: str
    name: Mapping
    needs: str | None = None
    retired: bool = False
    provisional: bool = False
    level: str | None = None        # xx tracks: the key of their level in extra_ost_volumes.json
    same_as: int | None = None      # xx_all tracks: the track that sounds the same; left out when the build has it


@dataclass(frozen=True)
class Category:
    key: str
    name: Mapping[str, str]


@dataclass(frozen=True)
class Catalogue:
    limits: Mapping[str, int]
    defaults: Mapping[str, int]
    loops_range: tuple[int, int]
    fade_range: tuple[int, int]
    exclusion: Mapping
    excluded: tuple[Mapping, ...]
    replaced: Mapping[str, list]
    categories: tuple[Category, ...]
    tracks: tuple[Track, ...]
    xx: Mapping = None              # MH XX's songs: their queues, their level's key, how a same recording is found

    def track(self, track_id: int) -> Track:
        for track in self.tracks:
            if track.id == track_id:
                return track
        raise KeyError(track_id)


def _five(texts: object, what: str) -> dict[str, str]:
    if not isinstance(texts, dict) or set(texts) != set(LANGUAGES) or not all(
            isinstance(v, str) and v for v in texts.values()):
        raise CatalogueError(f"{what}: text must be in {', '.join(LANGUAGES)}")
    return dict(texts)


def _check_name(name: object, what: str) -> None:
    if not isinstance(name, dict):
        raise CatalogueError(f"{what}: name must be an object")
    kinds = [k for k in ("monster", "map", "message", "text") if k in name]
    if len(kinds) != 1 or not set(name) <= {kinds[0], "suffix"}:
        raise CatalogueError(f"{what}: name needs exactly one of monster / map / message / text (and may have a "
                             "suffix)")
    if kinds[0] == "text":
        _five(name["text"], what)
    elif kinds[0] == "message":
        ref = name["message"]
        if (not isinstance(ref, dict) or set(ref) != _MESSAGE_KEYS or not isinstance(ref["arc"], str)
                or not isinstance(ref["file"], str) or not isinstance(ref["id"], int) or isinstance(ref["id"], bool)
                or ref["id"] < 0 or not ref["arc"] or not ref["file"]):
            raise CatalogueError(f"{what}: message must be {{arc, file, id}} (names, then a number)")
    elif not isinstance(name[kinds[0]], int):
        raise CatalogueError(f"{what}: {kinds[0]} must be a number")
    if "suffix" in name:
        _five(name["suffix"], what)


def _range(value: object, what: str) -> tuple[int, int]:
    if (not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, int) for v in value)
            or not value[0] <= value[1]):
        raise CatalogueError(f"{what}: must be [low, high]")
    return value[0], value[1]


def parse(data: Mapping) -> Catalogue:
    """The catalogue of the file's content, checked: unique ids, known categories and sources, names in the five
    languages, limits and ranges that make sense."""
    limits, defaults = data["limits"], data["defaults"]
    for key in ("playlists", "tracks", "name_chars"):
        if not isinstance(limits.get(key), int) or limits[key] < 1:
            raise CatalogueError(f"limits.{key} must be a positive number")
    loops, fade = _range(data["loops_range"], "loops_range"), _range(data["fade_range"], "fade_range")
    if not loops[0] <= defaults["loops"] <= loops[1] or not fade[0] <= defaults["fade_seconds"] <= fade[1]:
        raise CatalogueError("defaults must be inside their ranges")
    for key in ("keep", "halls"):
        if defaults.get(key) not in (0, 1) or isinstance(defaults[key], bool):
            raise CatalogueError(f"defaults.{key} must be 0 or 1")
    categories = tuple(Category(c["key"], _five(c["name"], f"category {c['key']}")) for c in data["categories"])
    keys = [c.key for c in categories]
    if len(set(keys)) != len(keys):
        raise CatalogueError("category keys must be unique")
    tracks, seen = [], set()
    for record in data["tracks"]:
        what = f"track {record.get('id')}"
        if not isinstance(record["id"], int) or record["id"] in seen:
            raise CatalogueError(f"{what}: ids are unique numbers")
        seen.add(record["id"])
        if record["category"] not in keys:
            raise CatalogueError(f"{what}: unknown category {record['category']}")
        if record["source"] not in SOURCES:
            raise CatalogueError(f"{what}: unknown source {record['source']}")
        _check_name(record["name"], what)
        if record["source"] == "xx" and not record.get("level"):
            raise CatalogueError(f"{what}: an xx track names its level's key")
        if record.get("same_as") is not None and record["source"] != "xx_all":
            raise CatalogueError(f"{what}: same_as is for an xx_all track")
        tracks.append(Track(record["id"], record["path"], record["category"], record["source"], record["name"],
                            record.get("needs"), bool(record.get("retired")), bool(record.get("provisional")),
                            record.get("level"), record.get("same_as")))
    ids = [t.id for t in tracks]
    for track in tracks:
        if track.same_as is not None and (track.same_as not in seen or ids.index(track.same_as) >= ids.index(track.id)):
            raise CatalogueError(f"track {track.id}: same_as names a track listed before it")
    return Catalogue(limits, defaults, loops, fade, data["exclusion"], tuple(data["excluded"]), data["replaced"],
                     categories, tuple(tracks), data.get("xx", {}))


def load(path: Path = CATALOGUE_FILE) -> Catalogue:
    """The catalogue of curated/jukebox.json."""
    return parse(json.loads(path.read_text(encoding="utf-8")))


def available(catalogue: Catalogue, sources: Collection[str], ports: Collection[str] = ()) -> list[Track]:
    """The tracks a build has, in the file's order: not retired, from one of `sources` (retail, mhw, ported, extra,
    xx, xx_all) and, when the track needs a port, with that port (its key) among `ports`; an xx_all track only when
    the track it sounds as (same_as) is not among them."""
    found: list[Track] = []
    kept: set[int] = set()
    for t in catalogue.tracks:
        if t.retired or t.source not in sources or (t.needs is not None and t.needs not in ports):
            continue
        if t.same_as is not None and t.same_as in kept:
            continue
        found.append(t)
        kept.add(t.id)
    return found


def shipped_bytes(track: Track, root: Path = CHECKOUT) -> bytes:
    """The .mca of a track the mod ships (source mhw or extra) from the checkout `root`. Nothing of the left-out
    subsystems is imported, so Heavenfall Beta, which has no core/music/mhw/, can use the module."""
    if track.source not in SHIPPED_SOURCES:
        raise CatalogueError(f"track {track.id}: {track.source} tracks are read from the game, not the checkout")
    return (root / track.path).read_bytes()


def _monster_names() -> Mapping[str, Mapping[str, str]]:
    return json.loads(MONSTER_NAMES_FILE.read_text(encoding="utf-8"))["names"]


def map_names(read: Callable[[str], bytes]) -> dict[str, list[str]]:
    """{language: the game's `mapName` messages, indexed by map number}, from the game's `core_common.arc` of each
    language (`read`: RomFS path -> bytes)."""
    from core.game.files.arc import parse_arc
    from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd
    result: dict[str, list[str]] = {}
    for lang in LANGUAGES:
        for entry in parse_arc(read(COMMON_ARC.format(lang=lang))).entries:
            if entry.type_hash == LMD_TYPE_HASH and entry.name.split("\\")[-1] == f"{MAP_NAME_STEM}_{lang}":
                lmd = parse_lmd(entry.data)
                result[lang] = [lmd.message(i) for i in range(lmd.message_count)]
                break
        else:
            raise CatalogueError(f"no {MAP_NAME_STEM}_{lang} in {COMMON_ARC.format(lang=lang)}")
    return result


def message_reader(read: Callable[[str], bytes]) -> Callable[[str, str, int], dict[str, str]]:
    """A function (archive stem, message file stem, message number) -> {language: the game's message}, from the game's
    `<lang>/data/<archive>.arc` of each language (`read`: RomFS path -> bytes). The message file `<file>_<lang>` is
    found by its name in the archive; each is parsed once."""
    from core.game.files.arc import parse_arc
    from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd
    files: dict[tuple[str, str, str], object] = {}

    def lmd_of(arc: str, file: str, lang: str):
        key = (arc, file, lang)
        if key not in files:
            path = MESSAGE_ARC.format(lang=lang, arc=arc)
            for entry in parse_arc(read(path)).entries:
                if entry.type_hash == LMD_TYPE_HASH and entry.name.split("\\")[-1] == f"{file}_{lang}":
                    files[key] = parse_lmd(entry.data)
                    break
            else:
                raise CatalogueError(f"no {file}_{lang} in {path}")
        return files[key]

    def message(arc: str, file: str, index: int) -> dict[str, str]:
        result = {}
        for lang in LANGUAGES:
            lmd = lmd_of(arc, file, lang)
            if not 0 <= index < lmd.message_count:
                raise CatalogueError(f"{file}_{lang} has no message {index}")
            text = " ".join(lmd.message(index).split())
            if not text:
                raise CatalogueError(f"{file}_{lang} message {index} is empty")
            result[lang] = text
        return result

    return message


def track_names(track: Track, maps: Mapping[str, list[str]] | None = None,
                messages: Callable[[str, str, int], dict[str, str]] | None = None) -> dict[str, str]:
    """The track's name in each language: the monster's, map's or message's text of the game's texts, or the written
    text, then the suffix after a space. `maps`: `map_names(read)`, needed by a map's track; `messages`:
    `message_reader(read)`, needed by a message's track."""
    name = track.name
    if "text" in name:
        names = dict(name["text"])
    elif "message" in name:
        if messages is None:
            raise CatalogueError(f"track {track.id}: a message's name needs the game's texts")
        ref = name["message"]
        names = messages(ref["arc"], ref["file"], ref["id"])
    elif "monster" in name:
        record = _monster_names().get(str(name["monster"]))
        if record is None:
            raise CatalogueError(f"track {track.id}: no name for monster {name['monster']}")
        names = {lang: record[_NAME_KEYS[lang]] for lang in LANGUAGES}
    else:
        if maps is None:
            raise CatalogueError(f"track {track.id}: a map's name needs the game's texts")
        names = {lang: maps[lang][name["map"]] for lang in LANGUAGES}
    if "suffix" in name:
        names = {lang: f"{names[lang]} {name['suffix'][lang]}" for lang in LANGUAGES}
    return names


def too_wide(names: Iterable[tuple[int, Mapping[str, str]]], measure: Callable[[str, str], int],
             width: int) -> list[tuple[int, str, int]]:
    """The names that do not fit: [(track id, language, measured width)] for each name wider than `width`. `names`:
    (track id, {language: name}); `measure(text, language)`: the width of a text in the menu's pane (the menu's
    own measuring function)."""
    return [(track_id, lang, w) for track_id, texts in names for lang in LANGUAGES
            if (w := measure(texts[lang], lang)) > width]
