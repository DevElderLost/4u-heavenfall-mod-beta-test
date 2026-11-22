"""MH XX's songs in the jukebox: the option `jukebox_xx` brings XX's monster,
area, town and hall themes (catalogue source `xx_all`), read from the player's MH XX at build time.

* `xx_level`: a song's level, the one its request has in XX's own queue (an STQR in the folder above its `wav`
  folder: curated `xx.queues`), so XX's songs keep XX's mix; the catalogue's `xx.level` key of extra_ost_volumes.json
  moves them all together.
* `same_recording`: whether two `.mca` hold the same recording (the first seconds of their first channel decoded, the
  second matched to the first in gain and in a few samples of delay); research/music/jukebox_xx.py uses it to mark
  an XX song that sounds as a song the build already has (`same_as`), which a build then leaves out.

The module is shared with Heavenfall Beta: the game is read through the functions a caller passes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from core.music.audio.strq import parse_stqr


class XXTrackError(ValueError):
    """An XX song without its queue or its request."""


def queue_of(path: str, queues: Mapping[str, str]) -> str:
    """The XX queue (STQR) that plays the song at RomFS path `path`: curated `xx.queues`, by the song's folder."""
    folder = path.rsplit("/", 1)[0]
    if folder not in queues:
        raise XXTrackError(f"{path}: no queue of MH XX is listed for {folder}")
    return queues[folder]


def xx_level(read: Callable[[str], bytes], path: str, queues: Mapping[str, str]) -> float:
    """The level in dB of XX's first request that plays the song at `path` in its own queue (`read`: MH XX's
    RomFS)."""
    queue = parse_stqr(read(queue_of(path, queues)))
    stream = "\\".join(path.removesuffix(".mca").split("/"))
    for request in queue["requests"]:
        index = request["stream"]
        if index is not None and index < len(queue["streams"]) and queue["streams"][index]["path"] == stream:
            return request["db"]
    raise XXTrackError(f"{path}: no request of {queue_of(path, queues)} plays it")


def _window(data: bytes, start: int, length: int) -> list[int]:
    """Samples [start, start + length) of the first channel of a MADP (either layout), decoded."""
    from core.music.audio.madp import FRAME_BYTES, FRAME_SAMPLES, decode_channel, parse_madp
    madp = parse_madp(data)
    end = min(start + length, madp.samples)
    frames = -(-end // FRAME_SAMPLES)
    channel = madp.channels[0]
    pcm, _ = decode_channel(madp.data[0][:frames * FRAME_BYTES], channel.coefs, end, start=channel.start)
    return pcm[start:end]


def recording_distance(first: bytes, second: bytes, compare: Mapping) -> float:
    """How far `second` sounds from `first`: the energy left after `second`'s window is matched to `first`'s in gain
    and in delay (up to `compare["lag_samples"]` either way), over `first`'s energy (0: the same samples, about 1 or
    more: another song). `compare`: curated `xx.compare` (`from_seconds`, `seconds`, `lag_samples`, `rate`)."""
    import numpy as np
    rate, lag = compare["rate"], compare["lag_samples"]
    start, length = int(compare["from_seconds"] * rate), int(compare["seconds"] * rate)
    a = np.asarray(_window(first, start, length), dtype=np.float64)
    b = np.asarray(_window(second, max(0, start - lag), length + 2 * lag), dtype=np.float64)
    energy = float(a @ a)
    if energy == 0 or len(b) < len(a):
        return float("inf")
    best = float("inf")
    for shift in range(0, len(b) - len(a) + 1):
        part = b[shift:shift + len(a)]
        power = float(part @ part)
        if power == 0:
            continue
        gain = float(a @ part) / power
        rest = a - gain * part
        best = min(best, float(rest @ rest) / energy)
    return best


def same_recording(first: bytes, second: bytes, compare: Mapping) -> bool:
    """`first` and `second` hold the same recording: their lengths within `compare["length_samples"]` and their
    distance (recording_distance) below `compare["same_below"]`."""
    from core.music.jukebox.extra import check_madp
    if abs(check_madp(first)["samples"] - check_madp(second)["samples"]) > compare["length_samples"]:
        return False
    return recording_distance(first, second, compare) < compare["same_below"]


__all__ = ["XXTrackError", "queue_of", "recording_distance", "same_recording", "xx_level"]
