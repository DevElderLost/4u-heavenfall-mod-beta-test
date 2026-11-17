"""STRQ (.stq) stream queues: the tracks a queue can play and the requests the game asks for.

The game reads every queue from copies inside ARCs (`queue_archives`); the loose `sound/bgm/**/*.stq` files are
never loaded, so a changed queue must be written into those ARCs (`replace_queue`). Tracks (`.mca`) are loose."""

import re
import struct
from typing import Callable

from core.game.files.arc import parse_arc, write_arc
from core.music.audio.madp import MADP_TYPE_HASH, parse_madp

STRQ_TYPE_HASH = 0x3A6A5A4D
STREAM_SIZE = 0x24
REQUEST_SIZE = 0x64
NO_STREAM = 0xFFFFFFFF
LEVEL_WORD = 9          # a request's volume offset: f32, dB on its track
MAX_VOLUME = 12.05      # dB, set_volume's cap (400 %, music/audio/volumes.py)
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
# Queue name -> per-language ARCs ({lang}/data/NAME.arc) holding it. Event ARCs (data/dNNNN.arc, data/eNNNN.arc)
# also carry copies of the lobby and event queues for their cutscenes; they are not listed.
LANGUAGE_ARCS = {
    "bgm_bat": ("core_quest", "core_event"),
    "bgm_com": ("core_quest", "core_event"),
    "bgm_ev_st": ("core_quest", "core_event"),
    "se_ev_st": ("core_quest", "core_event"),
    "bgm_lob": ("core_lobby",),
    "bgm_ev_lob": ("core_lobby",),
    "se_ev_lob": ("core_lobby",),
    "bgm_sys": ("core_title",),
    "bgm_dl": ("core_dlc",),
    "bgm_st_11": ("core_arena",),
}
# Maps whose ARC holds another map's queue: Slayground (12) uses the Arena's field queue, map 21 map 14's ambience.
SHARED_MAP_QUEUES = {"bgm_st_11": ("m12",), "str_m14": ("m21",)}
NO_FIELD_QUEUE = {"09", "12", "14", "16", "20", "21"}  # maps without a bgm_st_NN of their own


def parse_strq(data: bytes) -> dict:
    """A .stq: its streams (one per .mca) and its requests (what the game asks to play)."""
    if data[:4] != b"STRQ":
        raise ValueError("not a STRQ file")
    version, stream_count, request_count, stream_offset, request_offset = struct.unpack_from("<5I", data, 4)
    streams = []
    for i in range(stream_count):
        (path_offset, size, samples, channels, rate, loop_start, loop_end, type_hash,
         unknown) = struct.unpack_from("<9I", data, stream_offset + STREAM_SIZE * i)
        path = data[path_offset:data.index(b"\0", path_offset)].decode("ascii")
        streams.append({"path": path, "size": size, "samples": samples, "channels": channels, "rate": rate,
                        "loop_start": loop_start, "loop_end": loop_end, "type_hash": type_hash,
                        "unknown": unknown, "entry": stream_offset + STREAM_SIZE * i})
    requests = []
    for i in range(request_count):
        at = request_offset + REQUEST_SIZE * i
        words = list(struct.unpack_from("<25I", data, at))
        requests.append({"entry": at, "words": words, "id": words[0], "priority": words[6] & 0xFF,
                         "stream": None if words[23] == NO_STREAM else words[23]})
    return {"version": version, "streams": streams, "requests": requests}


def build_strq(queue: dict) -> bytes:
    """The .stq bytes of a parsed queue (streams, then requests, then the paths in stream order)."""
    streams, requests = queue["streams"], queue["requests"]
    request_offset = 0x18 + STREAM_SIZE * len(streams)
    strings_offset = request_offset + REQUEST_SIZE * len(requests)
    out = bytearray(struct.pack("<4s5I", b"STRQ", queue["version"], len(streams), len(requests), 0x18,
                                request_offset))
    strings = bytearray()
    for s in streams:
        out += struct.pack("<9I", strings_offset + len(strings), s["size"], s["samples"], s["channels"], s["rate"],
                           s["loop_start"], s["loop_end"], s["type_hash"], s["unknown"])
        strings += s["path"].encode("ascii") + b"\0"
    for r in requests:
        out += struct.pack("<25I", *r["words"])
    return bytes(out + strings)


def unused_streams(queue: dict) -> list[int]:
    """Indexes of the streams no request plays. No retail queue has one; a battle queue with one (a request
    pointed at another stream) is the suspected cause of quests that never finish loading."""
    used = {r["words"][23] for r in queue["requests"]}
    return [i for i in range(len(queue["streams"])) if i not in used]


def stream_entry(path: str, data: bytes) -> dict:
    """A .stq stream entry for the .mca `data`, played from `path` ('sound\\bgm\\...\\name', no extension)."""
    header = parse_madp(data)
    return {"path": path, "size": len(data), "samples": header.samples, "channels": len(header.channels),
            "rate": header.rate, "loop_start": header.loop_start, "loop_end": header.loop_end,
            "type_hash": MADP_TYPE_HASH, "unknown": 2}


def romfs_path(stream_path: str) -> str:
    """'sound\\bgm\\stage\\wav\\bgm_map_01' -> 'sound/bgm/stage/wav/bgm_map_01.mca'."""
    return stream_path.replace("\\", "/") + ".mca"


def stream_path(romfs: str) -> str:
    """'sound/bgm/stage/wav/bgm_map_01.mca' -> 'sound\\bgm\\stage\\wav\\bgm_map_01'."""
    return romfs.removesuffix(".mca").replace("/", "\\")


def queue_name(romfs: str) -> str:
    """'sound/bgm/battle/bgm_bat.stq' -> the ARC entry name 'sound\\bgm\\battle\\bgm_bat'."""
    return romfs.removesuffix(".stq").replace("/", "\\")


def queue_archives(queue: str) -> list[str]:
    """RomFS paths of the ARCs the game reads queue `queue` ('sound\\bgm\\battle\\bgm_bat') from."""
    name = queue.rsplit("\\", 1)[-1]
    arcs = [f"{lang}/data/{arc}.arc" for arc in LANGUAGE_ARCS.get(name, ()) for lang in LANGUAGES]
    stage = re.fullmatch(r"bgm_st_(\d\d)|str_([mv]\d\d)", name)
    if stage and stage[1] not in NO_FIELD_QUEUE:
        maps = ("m" + stage[1],) if stage[1] else (stage[2],)
        arcs = [f"loc/data/{m}.arc" for m in maps + SHARED_MAP_QUEUES.get(name, ())] + arcs
    if not arcs:
        raise KeyError(f"no known ARC holds {queue}")
    return arcs


def replace_queue(arc_data: bytes, queue: str, stq: bytes) -> bytes:
    """The ARC `arc_data` with its copy of `queue` replaced by `stq`."""
    arc = parse_arc(arc_data)
    entries = [e for e in arc.entries if e.type_hash == STRQ_TYPE_HASH and e.name == queue]
    if not entries:
        raise ValueError(f"the ARC has no {queue}")
    for entry in entries:
        entry.data = stq
    return write_arc(arc)


def read_queue(read: Callable[[str], bytes], queue: str) -> bytes:
    """The .stq bytes of `queue` as the game sees them: its copy in the first of its ARCs, read with `read`."""
    arc = parse_arc(read(queue_archives(queue)[0]))
    return next(e.data for e in arc.entries if e.type_hash == STRQ_TYPE_HASH and e.name == queue)


def queue_files(read: Callable[[str], bytes], queue: str, stq: bytes) -> dict[str, bytes]:
    """{RomFS path: new ARC} putting `stq` as `queue` in every ARC that holds it; `read` gives each ARC's
    current bytes (a mod's copy, the update's or the ROM's)."""
    return {path: replace_queue(read(path), queue, stq) for path in queue_archives(queue)}


def add_track(read: Callable[[str], bytes], queue: str, request: int, path: str, mca: bytes,
              like: int) -> dict[str, bytes]:
    """{RomFS path: data}: the new track `path` ('sound\\bgm\\...\\name') as `mca`, and the ARCs of `queue` with a
    stream for it, played by `request`, an empty request (no stream) that becomes a copy of request `like` (kind,
    priority, volume, fades). The loader takes any number of streams, each with a request."""
    files = {romfs_path(path): mca}
    stq = parse_strq(read_queue(read, queue))
    if any(s["path"] == path for s in stq["streams"]):
        raise ValueError(f"{queue} already has {path}")
    if stq["requests"][request]["stream"] is not None:
        raise ValueError(f"{queue}: request {request:#x} already plays stream {stq['requests'][request]['stream']}")
    words = list(stq["requests"][like]["words"])
    words[0], words[23] = request, len(stq["streams"])
    stq["streams"].append(stream_entry(path, mca))
    stq["requests"][request] = {"words": words}
    files.update(queue_files(read, queue, build_strq(stq)))
    return files


def repoint_stream(read: Callable[[str], bytes], queue: str, request: int, path: str, mca: bytes) -> dict[str, bytes]:
    """{RomFS path: data}: the new track `path` as `mca`, and the ARCs of `queue` with the stream `request` plays
    pointed at it (path and header). Other queues that play the old track keep it. The stream must be that request's
    alone, and the path new in the queue (two entries with one path did not play)."""
    files = {romfs_path(path): mca}
    stq = parse_strq(read_queue(read, queue))
    index = stq["requests"][request]["stream"]
    if index is None:
        raise ValueError(f"{queue}: request {request:#x} plays no stream")
    if any(s["path"] == path for s in stq["streams"]):
        raise ValueError(f"{queue} already has {path}")
    sharing = [i for i, r in enumerate(stq["requests"]) if r["stream"] == index and i != request]
    if sharing:
        raise ValueError(f"{queue}: requests {sharing} play the same stream as {request:#x}")
    stq["streams"][index] = stream_entry(path, mca)
    files.update(queue_files(read, queue, build_strq(stq)))
    return files


def add_request(read: Callable[[str], bytes], queue: str, request: int, path: str, like: int) -> dict[str, bytes]:
    """{RomFS path: ARC}: the ARCs of `queue` where `request`, an empty request, plays the stream of `path` already in
    the queue, as a copy of request `like` (retail queues have streams played by two requests)."""
    stq = parse_strq(read_queue(read, queue))
    index = next((i for i, s in enumerate(stq["streams"]) if s["path"] == path), None)
    if index is None:
        raise ValueError(f"{queue} has no {path}")
    if stq["requests"][request]["stream"] is not None:
        raise ValueError(f"{queue}: request {request:#x} already plays stream {stq['requests'][request]['stream']}")
    words = list(stq["requests"][like]["words"])
    words[0], words[23] = request, index
    stq["requests"][request] = {"words": words}
    return queue_files(read, queue, build_strq(stq))


def header_entry(path: str, size: int, head: bytes) -> dict:
    """A .stq stream entry from a .mca's `size` and its first 0x1C bytes `head` alone (samples, rate and loop points
    are in the first 0x1C bytes of every MADP; the channel count is at +0x08)."""
    if head[:4] != b"MADP" or len(head) < 0x1C:
        raise ValueError(f"{path}: not a MADP header")
    samples, rate, loop_start, loop_end = struct.unpack_from("<4I", head, 0x0C)
    return {"path": path, "size": size, "samples": samples, "channels": head[0x08], "rate": rate,
            "loop_start": loop_start, "loop_end": loop_end, "type_hash": MADP_TYPE_HASH, "unknown": 2}


def add_streams(read: Callable[[str], bytes], queue: str, tracks: list[dict], like: int
                ) -> tuple[dict[str, bytes], list[int]]:
    """({RomFS path: ARC}, the request index of each track): the ARCs of `queue` with a new request at the end for
    every track, rebuilt once. A track is {"path": 'sound\\bgm\\...\\name', "entry": its stream entry (stream_entry,
    header_entry; or a function making it, called only when the queue lacks the path), "db": its level, None for
    `like`'s}. A request is a copy of request `like` with its own index (word 0), its stream (word 23) and its
    level (word 9). A path the queue
    already has (or an earlier track added) gets no second stream, only a request on that stream. Existing streams
    and requests stay as they are; the result is refused if a stream would have no request or a path twice."""
    stq = parse_strq(read_queue(read, queue))
    streams, requests = stq["streams"], stq["requests"]
    first_new = len(streams)
    index = {}
    for i, s in enumerate(streams):
        index.setdefault(s["path"], i)
    pattern = requests[like]["words"]
    made = []
    for track in tracks:
        path = track["path"]
        if path not in index:
            entry = track.get("entry")
            entry = entry() if callable(entry) else entry
            if entry is None:
                raise ValueError(f"{queue}: no stream entry for the new track {path}")
            if entry["path"] != path:
                raise ValueError(f"{queue}: the entry of {path} names {entry['path']}")
            index[path] = len(streams)
            streams.append(entry)
        words = list(pattern)
        words[0], words[23] = len(requests), index[path]
        if track.get("db") is not None:
            if track["db"] > MAX_VOLUME:
                raise ValueError(f"{path}: {track['db']} dB is past {MAX_VOLUME}")
            words[LEVEL_WORD] = struct.unpack("<I", struct.pack("<f", track["db"]))[0]
        made.append(len(requests))
        requests.append({"words": words})
    paths = [s["path"] for s in streams]
    if len(set(paths[first_new:])) != len(paths) - first_new or set(paths[first_new:]) & set(paths[:first_new]):
        raise ValueError(f"{queue}: two streams with one path")
    unused = unused_streams(stq)
    if unused:
        raise ValueError(f"{queue}: stream(s) {unused} would have no request")
    return queue_files(read, queue, build_strq(stq)), made


def volume(request: dict) -> float:
    """A request's volume offset in dB (word LEVEL_WORD; retail battle themes −5.0 to 0.0)."""
    return struct.unpack("<f", struct.pack("<I", request["words"][LEVEL_WORD]))[0]


def set_volume(read: Callable[[str], bytes], queue: str, request: int, db: float) -> dict[str, bytes]:
    """{RomFS path: ARC}: the ARCs of `queue` with `request`'s volume offset at `db` (at most MAX_VOLUME: above the
    retail 0.0 is only for tracks whose waveform peaks already, so the gain cannot go into the samples)."""
    if db > MAX_VOLUME:
        raise ValueError(f"{db} dB is past {MAX_VOLUME}")
    stq = parse_strq(read_queue(read, queue))
    stq["requests"][request]["words"][LEVEL_WORD] = struct.unpack("<I", struct.pack("<f", db))[0]
    return queue_files(read, queue, build_strq(stq))


def set_priority(read: Callable[[str], bytes], queue: str, request: int, priority: int) -> dict[str, bytes]:
    """{RomFS path: ARC}: the ARCs of `queue` with `request`'s priority byte (the low byte of word 6, which the
    priority loop compares: the highest wins) set to `priority`."""
    if not 0 <= priority <= 0xFF:
        raise ValueError(f"priority {priority} is not a byte")
    stq = parse_strq(read_queue(read, queue))
    words = stq["requests"][request]["words"]
    words[6] = (words[6] & ~0xFF) | priority
    return queue_files(read, queue, build_strq(stq))


def replace_track(read: Callable[[str], bytes], queues: list[str], path: str, mca: bytes) -> dict[str, bytes]:
    """{RomFS path: data}: the track `path` ('sound\\bgm\\...\\name') as `mca`, and the ARCs of `queues` with
    its stream entry updated."""
    files = {romfs_path(path): mca}
    entry = stream_entry(path, mca)

    def current(name: str) -> bytes:  # queues may share an ARC (bgm_bat and bgm_com are both in core_quest)
        return files[name] if name in files else read(name)
    for queue in queues:
        stq = parse_strq(read_queue(current, queue))
        stq["streams"] = [entry if s["path"] == path else s for s in stq["streams"]]
        unused = unused_streams(stq)
        if unused:  # a quest never finishes loading with one of these; replace the entry instead
            raise ValueError(f"{queue}: stream(s) {unused} would be unused, no request would play them")
        files.update(queue_files(current, queue, build_strq(stq)))
    return files
