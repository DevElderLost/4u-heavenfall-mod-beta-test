"""The jukebox menu's texts: messages added to the house Felyne's message file
Room_s (lobby message file 0x13) in every language, which jukebox_menu.c shows by number (jukebox_data's messages,
track_names and category[]; patch.data_block).

After Room_s's own messages come, in this order: the menu's texts (TEXT_KEYS, curated/jukebox_menu.json; a '{}' is a
number node, which shows string slot 0), the name of each category that holds a track of the build, then the name of
each track the menu lists, by category in the catalogue's order. Every copy of the file the game reads is changed
(core_lobby, core_arena, core_result), on the version an earlier step left (`read`: RomFS path -> bytes); every copy
must hold the same messages, so the numbers are the same everywhere. A name wider than a row is cut to fit, ending in
the curated 'cut'.

Shared with Heavenfall Beta: the game's readers and the text measuring are imported inside the functions that use them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from core.game.data.paths import CURATED_DIR
from core.music.jukebox.catalogue import LANGUAGES, Catalogue, Track, map_names, message_reader, track_names

MENU_FILE = CURATED_DIR / "jukebox_menu.json"
# The menu's messages, in the order of jukebox.h's JM_* (jukebox_data.messages)
TEXT_KEYS = ("line", "line_help", "slot", "playlist", "options", "help_main",
             "play", "stop", "add", "edit", "rename", "in_order", "shuffle", "clear", "help_playlist",
             "clear_prompt", "help_categories", "help_songs", "help_edit", "help_moving",
             "halls_off", "halls_on", "keep_session", "keep_always", "loops", "fade", "help_options")
ROOM_ARCS = ("core_lobby.arc", "core_arena.arc", "core_result.arc")
ROOM_STEM = "Room_s"
ROOM_MESSAGES = 153     # the game's own messages in Room_s
CATEGORIES = 8          # jukebox.h JUKEBOX_CATEGORIES
MENU_TRACKS = 256       # jukebox.h JUKEBOX_MENU_TRACKS
SLOT = "{}"


class MenuTextError(ValueError):
    """The menu's texts or the copies of Room_s do not fit."""


@dataclass(frozen=True)
class MenuTexts:
    """What the menu shows (patch.MenuLists): the message of each of TEXT_KEYS, the tracks it lists by category, the
    name message of the first (each next track's follows it) and each category's (first track, tracks, name
    message)."""
    messages: tuple[int, ...]
    tracks: tuple[int, ...]
    track_names: int
    categories: tuple[tuple[int, int, int], ...]
    files: Mapping[str, bytes] = field(default_factory=dict, repr=False)


def load_menu(curated: Mapping | None = None) -> Mapping:
    return curated or json.loads(MENU_FILE.read_text(encoding="utf-8"))


def text_px(text: str, font: int) -> float:
    """A text's width in pixels at `font` (a Helvetica estimate)."""
    from core.equipment.new_gear.new_texts import name_width
    return name_width(text) * font / 1000


def cut_to(text: str, width: Mapping, cut: str) -> str:
    """`text`, or as much of it as fits `width` ({px, font}) followed by `cut`."""
    if text_px(text, width["font"]) <= width["px"]:
        return text
    while text and text_px(text.rstrip() + cut, width["font"]) > width["px"]:
        text = text[:-1]
    return text.rstrip() + cut


def _filled(key: str, text: str, catalogue: Catalogue) -> str:
    """A text with its '{}' filled with the widest value the menu shows there."""
    value = {"playlist": catalogue.limits["playlists"], "loops": catalogue.loops_range[1],
             "fade": catalogue.fade_range[1]}.get(key, "")
    return text.replace(SLOT, str(value))


def wide_texts(catalogue: Catalogue, curated: Mapping | None = None) -> list[tuple[str, str, float, int]]:
    """The menu's texts that do not fit: (key, language, width, room) for each row text wider than a row or the ribbon's
    title (the line's name also wider than the menu's line), the widest number a row shows ('number': a playlist's
    songs, a category's tracks) wider than its pane, each help line wider than the help window or each help with too
    many lines; the categories' names are rows too ('category:<key>')."""
    menu = load_menu(curated)
    texts, widths = menu["texts"], menu["widths"]
    found = []

    def check(key: str, lang: str, text: str, width: Mapping) -> None:
        px = text_px(text, width["font"])
        if px > width["px"]:
            found.append((key, lang, round(px, 1), width["px"]))

    sizes = [sum(t.category == c.key and not t.retired for t in catalogue.tracks) for c in catalogue.categories]
    widest = str(max([catalogue.limits["tracks"], *sizes]))
    for lang in LANGUAGES:
        check("line", lang, texts["line"][lang], widths["line"])
        check("number", lang, widest, widths["number"])
        for key in menu["rows"]:
            for width in (widths["row"], widths["title"]):
                check(key, lang, _filled(key, texts[key][lang], catalogue), width)
        for category in catalogue.categories:
            for width in (widths["row"], widths["title"]):
                check(f"category:{category.key}", lang, category.name[lang], width)
        for key in menu["help"]:
            lines = texts[key][lang].split("\n")
            if len(lines) > widths["help"]["lines"]:
                found.append((key, lang, len(lines), widths["help"]["lines"]))
            for line in lines:
                check(key, lang, line, widths["help"])
    return found


def menu_lists(catalogue: Catalogue, tracks: Iterable[Track]) -> list[tuple[str, list[Track]]]:
    """The menu's categories (their keys) that hold a track of `tracks` (the build's), in the catalogue's order, each
    with its tracks in `tracks`' order."""
    have = list(tracks)
    lists = [(c.key, [t for t in have if t.category == c.key]) for c in catalogue.categories]
    lists = [(key, members) for key, members in lists if members]
    count = sum(len(members) for _key, members in lists)
    if len(lists) > CATEGORIES or count > MENU_TRACKS:
        raise MenuTextError(f"the menu lists {count} tracks in {len(lists)} categories, room for {MENU_TRACKS} in "
                            f"{CATEGORIES}")
    return lists


def menu_messages(lang: str, catalogue: Catalogue, lists: Sequence[tuple[str, Sequence[Track]]],
                  names: Mapping[int, Mapping[str, str]], curated: Mapping | None = None) -> list[str]:
    """Every message added to Room_s in one language, in message order: TEXT_KEYS', the categories', the tracks'.
    `names`: {track id: {language: name}}."""
    menu = load_menu(curated)
    row, cut = menu["widths"]["row"], menu["cut"]
    out = [menu["texts"][key][lang] for key in TEXT_KEYS]
    by_key = {c.key: c for c in catalogue.categories}
    out += [cut_to(by_key[key].name[lang], row, cut) for key, _members in lists]
    out += [cut_to(names[t.id][lang], row, cut) for _key, members in lists for t in members]
    return out


def _room(arc: bytes, lang: str):
    from core.game.files.arc import parse_arc
    from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd
    parsed = parse_arc(arc)
    for entry in parsed.entries:
        if entry.type_hash == LMD_TYPE_HASH and entry.name.split("\\")[-1] == f"{ROOM_STEM}_{lang}":
            return parsed, entry, parse_lmd(entry.data)
    return parsed, None, None


def add_messages(arc: bytes, lang: str, messages: Sequence[str], first: int) -> bytes:
    """`arc` with `messages` appended to its Room_s from message `first` on (a '{}': a number node)."""
    from core.game.files.arc import write_arc
    from core.game.files.text.lmd import write_lmd
    parsed, entry, lmd = _room(arc, lang)
    if lmd is None:
        raise MenuTextError(f"no {ROOM_STEM}_{lang} in the archive")
    if lmd.message_count != first:
        raise MenuTextError(f"{ROOM_STEM}_{lang} has {lmd.message_count} messages, the other copies {first}")
    for text in messages:
        if SLOT in text:
            lmd.add_mixed_message(text)
        else:
            lmd.add_message(text)
    entry.data = write_lmd(lmd)
    return write_arc(parsed)


def room_paths() -> list[str]:
    """Every copy of Room_s the game reads (RomFS paths)."""
    return [f"{lang}/data/{arc}" for lang in LANGUAGES for arc in ROOM_ARCS]


def jukebox_menu_texts(read: Callable[[str], bytes], catalogue: Catalogue, tracks: Iterable[Track],
                       curated: Mapping | None = None) -> MenuTexts:
    """The menu's texts for the build's `tracks` (those with a request): every copy of Room_s with the messages added
    (MenuTexts.files, {RomFS path: new ARC}) and their numbers. `read` gives each file as an earlier step left it."""
    lists = menu_lists(catalogue, tracks)
    members = [t for _key, group in lists for t in group]
    maps = map_names(read) if any("map" in t.name for t in members) else None
    reader = message_reader(read)
    names = {t.id: track_names(t, maps, reader) for t in members}
    raw = {path: read(path) for path in room_paths()}
    counts = set()
    for path, arc in raw.items():
        lmd = _room(arc, path.split("/")[0])[2]
        if lmd is None:
            raise MenuTextError(f"no {ROOM_STEM} in {path}")
        counts.add(lmd.message_count)
    if len(counts) != 1 or min(counts) < ROOM_MESSAGES:
        raise MenuTextError(f"the copies of {ROOM_STEM} hold {sorted(counts)} messages, not the same of at least "
                            f"{ROOM_MESSAGES}")
    first = counts.pop()
    files = {}
    for path, arc in raw.items():
        lang = path.split("/")[0]
        files[path] = add_messages(arc, lang, menu_messages(lang, catalogue, lists, names, curated), first)
    categories, at = [], 0
    for index, (_key, group) in enumerate(lists):
        categories.append((at, len(group), first + len(TEXT_KEYS) + index))
        at += len(group)
    return MenuTexts(messages=tuple(first + i for i in range(len(TEXT_KEYS))), tracks=tuple(t.id for t in members),
                     track_names=first + len(TEXT_KEYS) + len(lists), categories=tuple(categories), files=files)


__all__ = ["MENU_FILE", "MenuTextError", "MenuTexts", "ROOM_ARCS", "ROOM_MESSAGES", "TEXT_KEYS", "add_messages",
           "cut_to", "jukebox_menu_texts", "load_menu", "menu_lists", "menu_messages", "room_paths", "text_px",
           "wide_texts"]
