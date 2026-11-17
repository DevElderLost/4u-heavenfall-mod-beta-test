"""WAV files: read source music (with its loop points) and write decoded tracks."""

import struct
import wave
from pathlib import Path

PCM, FLOAT, EXTENSIBLE = 1, 3, 0xFFFE


def read_wav(path: Path):
    """(samples as float rows in the int16 range, rate, loop or None) of a PCM or float WAV.

    The loop is the first loop of the `smpl` chunk, as (start, end) with end exclusive.
    Needs numpy.
    """
    import numpy as np
    data = Path(path).read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAV file")
    chunks, at = {}, 12
    while at + 8 <= len(data):
        name, size = struct.unpack_from("<4sI", data, at)
        chunks.setdefault(name, data[at + 8:at + 8 + size])
        at += 8 + size + (size & 1)
    if b"fmt " not in chunks or b"data" not in chunks:
        raise ValueError(f"{path}: no fmt or data chunk")
    tag, channels, rate, _, align, bits = struct.unpack_from("<HHIIHH", chunks[b"fmt "])
    if tag == EXTENSIBLE:
        (tag,) = struct.unpack_from("<H", chunks[b"fmt "], 24)
    raw = chunks[b"data"]
    raw = raw[:len(raw) // align * align]
    if tag == FLOAT and bits in (32, 64):
        x = np.frombuffer(raw, dtype=f"<f{bits // 8}").astype(np.float64) * 32768
    elif tag == PCM and bits == 8:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128) * 256
    elif tag == PCM and bits in (16, 32):
        x = np.frombuffer(raw, dtype=f"<i{bits // 8}").astype(np.float64) / (1 << (bits - 16))
    elif tag == PCM and bits == 24:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        x = ((b[:, 0] | b[:, 1] << 8 | b[:, 2] << 16) << 8 >> 8).astype(np.float64) / 256
    else:
        raise ValueError(f"{path}: unsupported WAV format (tag {tag}, {bits} bits)")
    x = x.reshape(-1, channels).T
    loop = None
    smpl = chunks.get(b"smpl")
    if smpl and len(smpl) >= 36 + 24 and struct.unpack_from("<I", smpl, 28)[0]:
        start, end = struct.unpack_from("<2I", smpl, 36 + 8)
        loop = (start, min(end + 1, x.shape[1]))
    return x, rate, loop


def write_wav(path: Path, pcm: list[list[int]], rate: int) -> None:
    """16-bit WAV of channel rows of int samples."""
    frames = bytearray()
    for frame in zip(*pcm):
        frames += struct.pack(f"<{len(frame)}h", *frame)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(len(pcm))
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))
