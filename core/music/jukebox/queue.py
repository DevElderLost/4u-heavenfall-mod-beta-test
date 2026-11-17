"""The villages' stream queue (bgm_lob) with a stream and a request for every track of the jukebox."""

import re
from functools import partial
from typing import Callable

from core.music.audio.strq import add_streams, header_entry, stream_entry, stream_path
from core.music.audio.volumes import percent_db

LOBBY_QUEUE = "sound\\bgm\\lobby\\bgm_lob"
SHIPPED_FOLDER = "sound/bgm/jukebox"
MAX_STREAM_PATH = 0x103     # the loader's path buffer: a stream path must be shorter
HEADER_BYTES = 0x1C         # what a stream entry needs of a retail .mca (strq.header_entry)


def shipped_name(file: str) -> str:
    """The RomFS path of a track the mod ships: its file's stem (`file`: the file's name or path) with every
    character but letters, digits, '_' and '-' as '_'."""
    stem = re.split(r"[\\/]", file)[-1].removesuffix(".mca")
    return f"{SHIPPED_FOLDER}/{re.sub(r'[^A-Za-z0-9_-]', '_', stem)}.mca"


def jukebox_files(read: Callable[[str], bytes], tracks: list[dict], head: Callable[[str, int], tuple[int, bytes]],
                  like: int, queue: str = LOBBY_QUEUE) -> tuple[dict[str, bytes], dict[str, int]]:
    """({RomFS path: bytes}, {track id: request index}): the ARCs of `queue` (every language's core_lobby.arc, from
    the copies `read` gives) with a stream and a request for each track, and the .mca of the tracks the mod ships.
    A track is {"id", "path": a track's RomFS path in the game or the mod ('sound/bgm/.../x.mca') or "data": the
    .mca's bytes and "file": the file it comes from (its stem names the shipped file), "source", "percent": its level
    (100 = the game's) or "db": its level in dB (absent: the level of request `like`)}; a track with a path may carry
    "entry", its stream entry (strq.stream_entry, header_entry), else `head(path, length)` gives its size and first
    bytes (RomFS.head): the game's files are never read whole. Request `like`
    is the pattern of every new request. Two tracks with one path share a stream."""
    files: dict[str, bytes] = {}
    items, seen = [], set()
    for track in tracks:
        name = track["id"]
        if name in seen:
            raise ValueError(f"track {name} twice")
        seen.add(name)
        if ("path" in track) == ("data" in track):
            raise ValueError(f"track {name} ({track.get('source')}): needs a path or its bytes, not both")
        if "percent" in track and "db" in track:
            raise ValueError(f"track {name} ({track.get('source')}): a level in percent or in dB, not both")
        if "entry" in track and "path" not in track:
            raise ValueError(f"track {name} ({track.get('source')}): a stream entry goes with a path")
        if "data" in track:
            if not track.get("file"):
                raise ValueError(f"track {name} ({track.get('source')}): a shipped track needs its file")
            rom = shipped_name(track["file"])
            if rom in files:
                raise ValueError(f"track {name} ({track.get('source')}): {rom} is another track's file")
            files[rom] = track["data"]
            path = stream_path(rom)
            entry = partial(stream_entry, path, track["data"])
        else:
            rom = track["path"]
            if not rom.startswith("sound/bgm/") or not rom.endswith(".mca"):
                raise ValueError(f"track {name} ({track.get('source')}): {rom} is not a track of the game")
            path = stream_path(rom)
            entry = track["entry"] if "entry" in track else partial(_retail_entry, head, path, rom)
        if not path.isascii() or len(path) >= MAX_STREAM_PATH:
            raise ValueError(f"track {name} ({track.get('source')}): the stream path {path!r} is not ASCII or too long")
        db = track["db"] if "db" in track else None if track.get("percent") is None else percent_db(track["percent"])
        items.append((name, path, entry, db))
    queue_tracks = [{"path": path, "entry": entry, "db": db} for _, path, entry, db in items]
    arcs, requests = add_streams(read, queue, queue_tracks, like)
    files.update(arcs)
    return files, {name: request for (name, *_), request in zip(items, requests)}


def _retail_entry(head: Callable[[str, int], tuple[int, bytes]], path: str, rom: str) -> dict:
    """The stream entry of the retail track `rom`, from its size and header only."""
    size, first = head(rom, HEADER_BYTES)
    return header_entry(path, size, first)
