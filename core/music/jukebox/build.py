"""The jukebox in a build of the mod: the tracks the build has, its RomFS files
and the executable's three patches.

`jukebox_build` gives the RomFS files (the five core_lobby.arc with a request for each track in the lobby's queue
bgm_lob, a copy of request LIKE; every copy of Room_s with the menu's texts; the .mca the mod ships under
sound/bgm/jukebox/) and what the executable's patches need (each track's request, the menu's message numbers, the page
counter's place). `patch_executable` applies the engine's, the card's and the menu's patches in that order.

A track's sources: `retail` (the game's: its stream entry and level from the generated table, streams.py; a track
missing there, from its header and request LIKE's level), `extra` and `mhw` (the .mca the mod ships, at its level of
extra_ost_volumes.json, keyed by the file's stem; `mhw` only when the run has World's music), `xx` (MH XX's village
themes: read from the player's MH XX at their RomFS path, rewritten in MH4U's layout and shipped like the extra songs,
at the level of the key their record names), `xx_all` (MH XX's other monster, area, town and hall themes: read and
shipped the same way, at their request's level in XX's own queue moved by the catalogue's `xx.level` key,
xx_tracks.py; a song that sounds as a track the build has, `same_as`, is left out); both only when the run has MH XX
and the option jukebox_xx, else no song of XX is listed or shipped; and `ported` (a ported monster's theme, played
from the port's own track at the port's level; only the ports the run gives). The module is
shared with Heavenfall Beta: what the ported monsters and World's music know comes as arguments, and the game is read
through the functions a caller passes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from core.game.executable.code_space import Layout, load_layout
from core.music.audio.strq import queue_archives, stream_entry, stream_path
from core.music.audio.volumes import VOLUMES_FILE, percent_db, volumes
from core.music.jukebox.catalogue import CHECKOUT, Catalogue, Track, available, load, shipped_bytes
from core.music.jukebox.extra import check_madp, in_mh4u_layout
from core.music.jukebox.menu_patch import patch_jukebox_menu, supports_jukebox_menu
from core.music.jukebox.patch import patch_jukebox, supports_jukebox
from core.music.jukebox.queue import LOBBY_QUEUE, SHIPPED_FOLDER, jukebox_files, shipped_name
from core.music.jukebox.save_patch import patch_jukebox_save, supports_jukebox_save
from core.music.jukebox.streams import entry_of, load_streams
from core.music.jukebox.texts import MenuTexts, jukebox_menu_texts, room_paths
from core.music.jukebox.xx_tracks import xx_level

# Val Habar's theme: every request of the jukebox is a copy of it, so the rooms' 50 %, the grill's 20 % and the game's
# fades treat a song as a village theme
LIKE = 0x0D
COUNTER_MENU = "jukebox"        # the menu's name among single-screen mode's page counters (single_screen.json)
# On a wider picture single-screen mode's counter group (ui036_yazi00) keeps to the left, by its box in the file, while
# screen 13's list (ui443.list) stays in the middle: the counter takes the way of one side back, to stay on the list's
# plank
COUNTER_SIDES = 1               # the list's side (the middle, 0) minus the counter group's (the left, -1)
SIDE_WAY = 200                  # the way to a side of a picture w times the game's width: SIDE_WAY * (w - 1) pixels


class JukeboxBuildError(ValueError):
    """A track of the build cannot be played: a ported theme at another path, a shipped track without a level."""


@dataclass(frozen=True)
class PortTheme:
    """A ported monster's theme as the run writes it: its RomFS path (the port's own track), the .mca's bytes, its
    level in percent (extra_ost_volumes.json)."""
    path: str
    data: bytes = field(repr=False)
    percent: float


@dataclass(frozen=True)
class JukeboxBuild:
    """The jukebox of a build: the catalogue, the tracks it has (each with a request), what the executable's patches
    need (`requests`, `menu`'s numbers, `counter`: the page counter's place, None for the game's, and `counter_way`,
    its way back on a wider picture) and the RomFS files."""
    catalogue: Catalogue
    tracks: tuple[Track, ...]
    requests: Mapping[int, int]
    menu: MenuTexts
    counter: tuple[int, int] | None
    files: Mapping[str, bytes] = field(repr=False)
    made_from_xx: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    counter_way: tuple[int, int] = (0, 0)

    def numbers(self) -> tuple:
        """Everything the executable takes from the files: two builds with the same numbers patch it the same."""
        return (dict(self.requests), tuple(self.menu.messages), tuple(self.menu.tracks), self.menu.track_names,
                tuple(self.menu.categories), self.counter, self.counter_way)


def build_sources(world: bool, ported: bool, xx: bool = False) -> tuple[str, ...]:
    """The catalogue's sources a build has: the game's and the extra songs, World's with `world`, MH XX's songs (its
    village themes and the others) with `xx`, the ported monsters' themes with `ported`."""
    return (("retail", "extra") + (("mhw",) if world else ()) + (("xx", "xx_all") if xx else ())
            + (("ported",) if ported else ()))


def jukebox_tracks(catalogue: Catalogue, world: bool, themes: Mapping[str, PortTheme],
                   xx: bool = False) -> list[Track]:
    """The tracks a build has, in the catalogue's order: `themes` gives the ported monsters whose theme it has."""
    return available(catalogue, build_sources(world, bool(themes), xx), themes.keys())


def volume_key(track: Track, catalogue: Catalogue | None = None) -> str:
    """The track's level's name in the volumes file (VOLUMES_FILE), for a song the mod ships (not retail nor ported):
    an MH XX village theme's level, MH XX's other songs' shared key (the catalogue's `xx.level`), else its file's
    stem."""
    if track.source == "xx_all":
        return (catalogue or load()).xx["level"]
    return track.level if track.source == "xx" else Path(track.path).stem


def shipped_xx_file(track: Track) -> str:
    """The file name an MH XX song is shipped as: a village theme's level key (the name the committed copies had, so
    saved playlists kept working), any other song its own stem after `xx_`."""
    return f"{track.level}.mca" if track.source == "xx" else f"xx_{Path(track.path).stem}.mca"


def shipped_file(track: Track) -> str:
    """The file name a track the mod ships from the checkout (catalogue.SHIPPED_SOURCES) is shipped as: its id,
    `t<id>.mca`, never its file's name (the release's shared file names its entries alike:
    install/title/shared_file.py, entry_name)."""
    return f"t{track.id}.mca"


def xx_song(track: Track, xx_read: Callable[[str], bytes], songs: dict | None = None) -> bytes:
    """An MH XX song in MH4U's layout, checked; `songs` ({RomFS path: bytes}) keeps it for the run's second build."""
    if songs is not None and track.path in songs:
        return songs[track.path]
    data = xx_read(track.path)
    check_madp(data)
    data = in_mh4u_layout(data)
    if songs is not None:
        songs[track.path] = data
    return data


def queue_track(track: Track, streams: Mapping[str, Mapping], levels: Mapping[str, float],
                themes: Mapping[str, PortTheme], root: Path = CHECKOUT,
                xx_read: Callable[[str], bytes] | None = None, catalogue: Catalogue | None = None,
                xx_songs: dict | None = None) -> dict:
    """The track as queue.jukebox_files takes it. `xx_read`: a file of MH XX's RomFS, for the xx and xx_all tracks;
    `xx_songs`: the songs of MH XX made so far in the run (xx_song)."""
    base = {"id": track.id, "source": track.source}
    if track.source == "retail":
        record = streams.get(track.path)
        if record is None:      # its header and request LIKE's level
            return {**base, "path": track.path}
        return {**base, "path": track.path, "entry": entry_of(record), "db": record["db"]}
    if track.source == "ported":
        theme = themes.get(track.needs)
        if theme is None:
            raise JukeboxBuildError(f"track {track.id}: no theme of {track.needs} in the build")
        if theme.path != track.path:
            raise JukeboxBuildError(f"track {track.id}: {track.needs}'s theme is {theme.path}, not {track.path}")
        return {**base, "path": track.path, "entry": stream_entry(stream_path(track.path), theme.data),
                "percent": theme.percent}
    key = volume_key(track, catalogue)
    if key not in levels:
        raise JukeboxBuildError(f"track {track.id}: no level for {key} in {VOLUMES_FILE.name}")
    if track.source in ("xx", "xx_all"):
        if xx_read is None:
            raise JukeboxBuildError(f"track {track.id}: a song of MH XX needs MH XX's RomFS")
        out = {**base, "data": xx_song(track, xx_read, xx_songs), "file": shipped_xx_file(track)}
        if track.source == "xx":
            return {**out, "percent": levels[key]}
        queues = (catalogue or load()).xx["queues"]
        return {**out, "db": xx_level(xx_read, track.path, queues) + percent_db(levels[key])}
    return {**base, "data": shipped_bytes(track, root), "file": shipped_file(track), "percent": levels[key]}


def counter_place(single_screen: bool) -> tuple[int, int] | None:
    """The menu's page counter's place: single-screen mode's (single_screen.json, page_counters), else None (the
    game's)."""
    if not single_screen:
        return None
    from core.interface.single_screen.executable.single_screen_page_counters import (
        own_counter_place, page_counter_shifts,
    )
    return own_counter_place(COUNTER_MENU, page_counter_shifts())


def counter_way(single_screen: bool, width: float) -> tuple[int, int]:
    """(sides, fitted pixels): the way back the menu's counter takes on a wider picture (jukebox.h counter_sides,
    counter_fitted). `width`: the installed ratio's interface width against the game's (Settings.hud_edge), from which
    the aspect ratio's aspect_way counts. (0, 0) in two-screen mode: the counter is on the touch screen."""
    if not single_screen:
        return 0, 0
    return COUNTER_SIDES, round(COUNTER_SIDES * SIDE_WAY * (width - 1))


def jukebox_build(read: Callable[[str], bytes], head: Callable[[str, int], tuple[int, bytes]], settings, *,
                  world: bool = False, themes: Mapping[str, PortTheme] | None = None, single_screen: bool = False,
                  catalogue: Catalogue | None = None, streams: Mapping[str, Mapping] | None = None,
                  levels: Mapping[str, float] | None = None, root: Path = CHECKOUT,
                  xx_read: Callable[[str], bytes] | None = None, xx_songs: dict | None = None) -> JukeboxBuild | None:
    """The jukebox of a build, or None when `settings.jukebox` is off. `read`: a RomFS file as the mod leaves it so far
    (its copy, else the game's); `head`: a game's file's size and first bytes (RomFS.head); `world`: the run has
    World's music; `themes`: {port key: its theme} of the ported monsters the run builds; `single_screen`: the run
    has single-screen mode; `xx_read`: a file of MH XX's RomFS (RomFS.read), None without MH XX; its songs come only
    with it and `settings.jukebox_xx`; `xx_songs`: a dict the run keeps between its two
    builds, so MH XX's songs are read and made once. `catalogue`, `streams` (load_streams), `levels` ({key: percent},
    extra_ost_volumes.json) and `root` (the checkout the shipped tracks are read from) default to the mod's own."""
    if not settings.jukebox:
        return None
    catalogue = catalogue or load()
    streams = load_streams() if streams is None else streams
    levels = volumes() if levels is None else levels
    themes = themes or {}
    xx = xx_read is not None and bool(getattr(settings, "jukebox_xx", False))
    tracks = jukebox_tracks(catalogue, world, themes, xx)
    queued = [queue_track(t, streams, levels, themes, root, xx_read, catalogue, xx_songs) for t in tracks]
    files, requests = jukebox_files(read, queued, head, LIKE)
    have = tuple(t for t in tracks if t.id in requests)
    menu = jukebox_menu_texts(lambda path: files[path] if path in files else read(path), catalogue, have)
    files.update(menu.files)
    width = getattr(settings, "hud_edge", (1.0, 1.0))[0]
    return JukeboxBuild(catalogue, have, requests, menu, counter_place(single_screen), files,
                        xx_provenance(have, files), counter_way(single_screen, width))


def xx_provenance(tracks, files: Mapping[str, bytes]) -> dict[str, tuple[str, ...]]:
    """{mod path: (MH XX RomFS path,)} of each shipped file made from a song of MH XX (the provenance file,
    xx_sources.write_sources: the console's patch set rebuilds it from the player's MH XX). Only songs in `files`."""
    out = {}
    for track in tracks:
        if track.source in ("xx", "xx_all") and shipped_name(shipped_xx_file(track)) in files:
            out["romfs/" + shipped_name(shipped_xx_file(track))] = (track.path,)
    return out


def supports(code: bytes) -> bool:
    """`code` (the update's executable, canonical) has every instruction the jukebox's three patches replace."""
    return supports_jukebox(code) and supports_jukebox_save(code) and supports_jukebox_menu(code)


def patch_executable(code: bytes, build: JukeboxBuild, layout: Layout | None = None) -> bytes:
    """`code` (the update's executable) with the jukebox: the engine and its data (patch.patch_jukebox, the build's
    requests and menu), the card's hooks (save_patch), the menu's hooks and the page counter's place (menu_patch)."""
    layout = layout or load_layout()
    out = patch_jukebox(code, build.catalogue, build.requests, layout, menu=build.menu)
    out = patch_jukebox_save(out, layout)
    return patch_jukebox_menu(out, layout, counter=build.counter, counter_way=build.counter_way)


def romfs_paths() -> list[str]:
    """The ARCs a build writes (every language's core_lobby.arc, every copy of Room_s); the shipped tracks are in
    SHIPPED_FOLDER."""
    return list(dict.fromkeys([*queue_archives(LOBBY_QUEUE), *room_paths()]))


def remove_files(mod: Path) -> None:
    """The files an earlier run's jukebox may have written in the mod folder `mod` (its ARCs are also other features'
    files: before those are written)."""
    for path in romfs_paths():
        (mod / "romfs" / path).unlink(missing_ok=True)
    folder = mod / "romfs" / SHIPPED_FOLDER
    if folder.is_dir():
        for track in folder.glob("*.mca"):
            track.unlink()


__all__ = ["COUNTER_MENU", "COUNTER_SIDES", "JukeboxBuild", "JukeboxBuildError", "LIKE", "PortTheme", "SIDE_WAY",
           "build_sources", "counter_place", "counter_way", "jukebox_build", "jukebox_tracks", "patch_executable",
           "queue_track", "remove_files", "romfs_paths", "shipped_file", "shipped_xx_file", "supports", "xx_song"]
