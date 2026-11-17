"""The retail tracks' stream table (generated/jukebox_streams.json): for every
retail track of the catalogue, what its stream entry in the lobby's queue needs (size, samples, channels, rate, loop
points: its .mca's header, as strq.header_entry reads it) and the level of the request that plays it in its own queue,
so a build reads nothing more of the game for it. `stream_records` makes the table from the game
(tools/build/build_jukebox_streams.py); a track missing there is read from the game (its header; the pattern request's
level).

A track's own queue is the first queue, in QUEUE_ARCS' order and then each map's, with a request whose stream is the
track; its level is that queue's lowest such request's. The module is shared with Heavenfall Beta: the game is read
through the functions a caller passes."""

from __future__ import annotations

import json
import re
import struct
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from core.game.data.paths import GENERATED_DIR
from core.music.audio.madp import MADP_TYPE_HASH
from core.music.audio.strq import STRQ_TYPE_HASH, header_entry, parse_strq, stream_path, volume
from core.music.jukebox.catalogue import Track

STREAMS_FILE = GENERATED_DIR / "jukebox_streams.json"
FIELDS = ("size", "samples", "channels", "rate", "loop_start", "loop_end")     # a stream entry's, after its path
HEADER_BYTES = 0x1C             # what strq.header_entry needs of a .mca
# The ARCs holding the queues of the whole game but the maps' (strq.LANGUAGE_ARCS: the first language's copy), in the
# order a track's own queue is looked for; then every map's own ARC (MAP_ARC)
QUEUE_ARCS = ("eng/data/core_lobby.arc", "eng/data/core_quest.arc", "eng/data/core_event.arc",
              "eng/data/core_title.arc", "eng/data/core_dlc.arc", "eng/data/core_arena.arc")
MAP_ARC = re.compile(r"loc/data/m\d\d\.arc")
DB_DIGITS = 6                   # a level's decimals in the table: its f32 comes back the same


class StreamTableError(ValueError):
    """A retail track has no stream entry or no request in the game, or the table is malformed."""


def load_streams(path: Path = STREAMS_FILE) -> dict[str, dict]:
    """{track's RomFS path: its record} of the table."""
    records = json.loads(path.read_text(encoding="utf-8"))["tracks"]
    table = {}
    for record in records:
        if not set(FIELDS) | {"path", "db"} <= set(record):
            raise StreamTableError(f"{path.name}: a record needs path, {', '.join(FIELDS)} and db")
        table[record["path"]] = record
    return table


def entry_of(record: Mapping) -> dict:
    """The stream entry (strq.parse_strq's fields) of a table's record, played from its track's path."""
    return {"path": stream_path(record["path"]), **{key: record[key] for key in FIELDS},
            "type_hash": MADP_TYPE_HASH, "unknown": 2}


def queue_copies(read: Callable[[str], bytes], arcs: Iterable[str]) -> list[tuple[str, str, dict]]:
    """(ARC, queue name, parsed queue) of every queue in `arcs`, in their order; a queue another ARC had first is not
    taken again."""
    from core.game.files.arc import parse_arc
    seen, found = set(), []
    for arc in arcs:
        for entry in parse_arc(read(arc)).entries:
            if entry.type_hash == STRQ_TYPE_HASH and entry.name not in seen:
                seen.add(entry.name)
                found.append((arc, entry.name, parse_strq(entry.data)))
    return found


def game_queue_arcs(paths: Iterable[str]) -> list[str]:
    """The ARCs the table looks for queues in: QUEUE_ARCS, then each map's ARC of `paths` (the game's files), sorted."""
    return [*QUEUE_ARCS, *sorted(path for path in paths if MAP_ARC.fullmatch(path))]


def own_request(queues: Iterable[tuple[str, str, dict]], path: str) -> tuple[str, int, float] | None:
    """(queue name, request index, level in dB) of the first request playing the track `path` (its RomFS path) in the
    first of `queues` that has one, or None."""
    wanted = stream_path(path)
    for _arc, name, queue in queues:
        streams = [s["path"] for s in queue["streams"]]
        for index, request in enumerate(queue["requests"]):
            if request["stream"] is not None and streams[request["stream"]] == wanted:
                return name, index, volume(request)
    return None


def stream_record(track: Track, head: Callable[[str, int], tuple[int, bytes]], queues: list[tuple[str, str, dict]]
                  ) -> dict:
    """The table's record of a retail track: its id and path, its header's stream fields (`head`: RomFS.head), the
    level, queue and request index of its own request."""
    size, first = head(track.path, HEADER_BYTES)
    entry = header_entry(stream_path(track.path), size, first)
    own = own_request(queues, track.path)
    if own is None:
        raise StreamTableError(f"track {track.id}: no queue of the game plays {track.path}")
    queue, request, db = own
    return {"id": track.id, "path": track.path, **{key: entry[key] for key in FIELDS},
            "db": round(db, DB_DIGITS), "queue": queue, "request": request}


def stream_records(tracks: Iterable[Track], read: Callable[[str], bytes],
                   head: Callable[[str, int], tuple[int, bytes]], paths: Iterable[str]) -> list[dict]:
    """The table's records of the retail tracks of `tracks` (the catalogue's), in their order, from the game: `read`
    and `head` (RomFS.read, RomFS.head), `paths` (every file of its RomFS, RomFS.walk)."""
    queues = queue_copies(read, game_queue_arcs(paths))
    return [stream_record(track, head, queues) for track in tracks if track.source == "retail" and not track.retired]


def same_level(record: Mapping, db: float) -> bool:
    """The record's level is `db` as the queue's f32 holds it."""
    return struct.pack("<f", record["db"]) == struct.pack("<f", db)


__all__ = ["FIELDS", "QUEUE_ARCS", "STREAMS_FILE", "StreamTableError", "entry_of", "game_queue_arcs", "load_streams",
           "own_request", "queue_copies", "same_level", "stream_record", "stream_records"]
