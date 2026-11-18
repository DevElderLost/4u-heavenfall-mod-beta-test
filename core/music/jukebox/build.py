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
at the level of the key their record names; only when the run has MH XX) and `ported` (a ported monster's theme, played
from the port's own track at the port's level; only the ports the run gives). The module is
shared with Heavenfall Beta: what the ported monsters and World's music know comes as arguments, and the game is read
through the functions a caller passes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from core.game.executable.code_space import Layout, load_layout
from core.music.audio.strq import queue_archives, stream_entry, stream_path
from core.music.audio.volumes import VOLUMES_FILE, volumes
from core.music.jukebox.catalogue import CHECKOUT, Catalogue, Track, available, load, shipped_bytes
from core.music.jukebox.extra import check_madp, in_mh4u_layout
from core.music.jukebox.menu_patch import patch_jukebox_menu, supports_jukebox_menu
from core.music.jukebox.patch import patch_jukebox, supports_jukebox
from core.music.jukebox.queue import LOBBY_QUEUE, SHIPPED_FOLDER, jukebox_files, shipped_name
from core.music.jukebox.save_patch import patch_jukebox_save, supports_jukebox_save
from core.music.jukebox.streams import entry_of, load_streams
from core.music.jukebox.texts import MenuTexts, jukebox_menu_texts, room_paths

# Val Habar's theme: every request of the jukebox is a copy of it, so the rooms' 50 %, the grill's 20 % and the game's
# fades treat a song as a village theme
LIKE = 0x0D
COUNTER_MENU = "jukebox"        # the menu's name among single-screen mode's page counters (single_screen.json)


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
    need (`requests`, `menu`'s numbers, `counter`: the page counter's place, None for the game's) and the RomFS
    files."""
    catalogue: Catalogue
    tracks: tuple[Track, ...]
    requests: Mapping[int, int]
    menu: MenuTexts
    counter: tuple[int, int] | None
    files: Mapping[str, bytes] = field(repr=False)
    made_from_xx: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def numbers(self) -> tuple:
        """Everything the executable takes from the files: two builds with the same numbers patch it the same."""
        return (dict(self.requests), tuple(self.menu.messages), tuple(self.menu.tracks), self.menu.track_names,
                tuple(self.menu.categories), self.counter)


def build_sources(world: bool, ported: bool, xx: bool = False) -> tuple[str, ...]:
    """The catalogue's sources a build has: the game's and the extra songs, World's with `world`, MH XX's village
    themes with `xx`, the ported monsters' themes with `ported`."""
    return (("retail", "extra") + (("mhw",) if world else ()) + (("xx",) if xx else ())
            + (("ported",) if ported else ()))


def jukebox_tracks(catalogue: Catalogue, world: bool, themes: Mapping[str, PortTheme],
                   xx: bool = False) -> list[Track]:
    """The tracks a build has, in the catalogue's order: `themes` gives the ported monsters whose theme it has."""
    return available(catalogue, build_sources(world, bool(themes), xx), themes.keys())


def volume_key(track: Track) -> str:
    """The track's level's name in the volumes file (VOLUMES_FILE), for a song the mod ships (not retail nor ported):
    an MH XX song's level, else its file's stem."""
    return track.level if track.source == "xx" else Path(track.path).stem


def queue_track(track: Track, streams: Mapping[str, Mapping], levels: Mapping[str, float],
                themes: Mapping[str, PortTheme], root: Path = CHECKOUT,
                xx_read: Callable[[str], bytes] | None = None) -> dict:
    """The track as queue.jukebox_files takes it. `xx_read`: a file of MH XX's RomFS, for the xx tracks."""
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
    key = volume_key(track)
    if key not in levels:
        raise JukeboxBuildError(f"track {track.id}: no level for {key} in {VOLUMES_FILE.name}")
    if track.source == "xx":
        if xx_read is None:
            raise JukeboxBuildError(f"track {track.id}: a song of MH XX needs MH XX's RomFS")
        data = xx_read(track.path)
        check_madp(data)
        # shipped as {key}.mca, the name the committed copy had: saved playlists keep working
        return {**base, "data": in_mh4u_layout(data), "file": f"{key}.mca", "percent": levels[key]}
    return {**base, "data": shipped_bytes(track, root), "file": track.path, "percent": levels[key]}


def counter_place(single_screen: bool) -> tuple[int, int] | None:
    """The menu's page counter's place: single-screen mode's (single_screen.json, page_counters), else None (the
    game's)."""
    if not single_screen:
        return None
    from core.interface.single_screen.executable.single_screen_page_counters import (
        own_counter_place, page_counter_shifts,
    )
    return own_counter_place(COUNTER_MENU, page_counter_shifts())


def jukebox_build(read: Callable[[str], bytes], head: Callable[[str, int], tuple[int, bytes]], settings, *,
                  world: bool = False, themes: Mapping[str, PortTheme] | None = None, single_screen: bool = False,
                  catalogue: Catalogue | None = None, streams: Mapping[str, Mapping] | None = None,
                  levels: Mapping[str, float] | None = None, root: Path = CHECKOUT,
                  xx_read: Callable[[str], bytes] | None = None) -> JukeboxBuild | None:
    """The jukebox of a build, or None when `settings.jukebox` is off. `read`: a RomFS file as the mod leaves it so far
    (its copy, else the game's); `head`: a game's file's size and first bytes (RomFS.head); `world`: the run has
    World's music; `themes`: {port key: its theme} of the ported monsters the run builds; `single_screen`: the run
    has single-screen mode; `xx_read`: a file of MH XX's RomFS (RomFS.read), None without MH XX (its songs are left
    out). `catalogue`, `streams` (load_streams), `levels` ({key: percent}, extra_ost_volumes.json)
    and `root` (the checkout the shipped tracks are read from) default to the mod's own."""
    if not settings.jukebox:
        return None
    catalogue = catalogue or load()
    streams = load_streams() if streams is None else streams
    levels = volumes() if levels is None else levels
    themes = themes or {}
    tracks = jukebox_tracks(catalogue, world, themes, xx_read is not None)
    queued = [queue_track(t, streams, levels, themes, root, xx_read) for t in tracks]
    files, requests = jukebox_files(read, queued, head, LIKE)
    have = tuple(t for t in tracks if t.id in requests)
    menu = jukebox_menu_texts(lambda path: files[path] if path in files else read(path), catalogue, have)
    files.update(menu.files)
    return JukeboxBuild(catalogue, have, requests, menu, counter_place(single_screen), files,
                        xx_provenance(have, files))


def xx_provenance(tracks, files: Mapping[str, bytes]) -> dict[str, tuple[str, ...]]:
    """{mod path: (MH XX RomFS path,)} of each shipped file made from a song of MH XX (the provenance file,
    xx_sources.write_sources: the console's patch set rebuilds it from the player's MH XX). Only songs in `files`."""
    out = {}
    for track in tracks:
        if track.source == "xx" and shipped_name(f"{track.level}.mca") in files:
            out["romfs/" + shipped_name(f"{track.level}.mca")] = (track.path,)
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
    return patch_jukebox_menu(out, layout, counter=build.counter)


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


__all__ = ["COUNTER_MENU", "JukeboxBuild", "JukeboxBuildError", "LIKE", "PortTheme", "build_sources",
           "counter_place", "jukebox_build", "jukebox_tracks", "patch_executable", "queue_track", "remove_files",
           "romfs_paths", "supports"]
