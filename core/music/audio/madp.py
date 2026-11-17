"""MADP (.mca) audio: Capcom's container for Nintendo DSP ADPCM (format)."""

import struct
from dataclasses import dataclass, field

MADP_TYPE_HASH = 0x67195A2E
VERSION = 5
SEEK_OFFSET = 0x30
INTERLEAVE = 0x100
FRAME_BYTES, FRAME_SAMPLES = 8, 14
CHANNEL_INFO_SIZE = 0x30
GEN_DATE = 8  # MH Generations' MADP v5: a build date at +0x2C, everything after it 8 bytes on
DATA_ALIGN = 0x20
LOOP_TAIL = 32  # samples after loop_end in retail tracks


@dataclass
class DspState:
    """Decoder state before a sample: frame header byte (predictor << 4 | scale) and the last two samples."""
    ps: int = 0
    hist1: int = 0
    hist2: int = 0


@dataclass
class Channel:
    coefs: list[int]  # 8 predictor pairs
    gain: int = 0
    start: DspState = field(default_factory=DspState)
    loop: DspState = field(default_factory=DspState)
    pad: int = 0


@dataclass
class SeekPoint:
    """Decoder state of every channel at `sample` (a frame boundary)."""
    index: int
    sample: int
    states: list[DspState]


@dataclass
class Madp:
    channels: list[Channel]
    samples: int
    rate: int
    loop_start: int
    loop_end: int  # 0 = no loop
    seek: list[SeekPoint]
    data: list[bytes]  # DSP frames of each channel
    version: int = VERSION
    interleave: int = INTERLEAVE

    @property
    def seconds(self) -> float:
        return self.samples / self.rate


def frame_count(samples: int) -> int:
    return -(-samples // FRAME_SAMPLES)


def parse_madp(data: bytes) -> Madp:
    """MH4U's MADP, or MH Generations' (the same but for its build date at +0x2C: the data offset is at
    +0x34 and the seek table starts at 0x38). Told apart by the header size, +0x1C."""
    if data[:4] != b"MADP":
        raise ValueError("not a MADP file")
    (version,) = struct.unpack_from("<H", data, 0x04)
    count = data[0x08]
    (interleave,) = struct.unpack_from("<H", data, 0x0A)
    samples, rate, loop_start, loop_end, head, data_size = struct.unpack_from("<6I", data, 0x0C)
    date = head - SEEK_OFFSET - CHANNEL_INFO_SIZE * count
    if date not in (0, GEN_DATE):
        raise ValueError(f"MADP header size {head:#x} for {count} channels")
    (seek_count,) = struct.unpack_from("<I", data, 0x28)
    (data_offset,) = struct.unpack_from("<I", data, 0x2C + date)
    entry = 8 + 6 * count
    seek = []
    for i in range(seek_count):
        at = SEEK_OFFSET + date + entry * i
        index, sample = struct.unpack_from("<2I", data, at)
        states = [DspState(*struct.unpack_from("<Hhh", data, at + 8 + 6 * c)) for c in range(count)]
        seek.append(SeekPoint(index, sample, states))
    channels = []
    for c in range(count):
        at = SEEK_OFFSET + date + entry * seek_count + CHANNEL_INFO_SIZE * c
        coefs = list(struct.unpack_from("<16h", data, at))
        gain, ps, h1, h2, lps, lh1, lh2, pad = struct.unpack_from("<HHhhHhhH", data, at + 0x20)
        channels.append(Channel(coefs, gain, DspState(ps, h1, h2), DspState(lps, lh1, lh2), pad))
    body = data[data_offset:data_offset + data_size]
    per_channel = [bytearray() for _ in range(count)]
    block = interleave * count
    full = len(body) // block * block
    for at in range(0, full, block):
        for c in range(count):
            per_channel[c] += body[at + c * interleave:at + (c + 1) * interleave]
    tail = (len(body) - full) // count
    for c in range(count):
        per_channel[c] += body[full + c * tail:full + (c + 1) * tail]
    needed = frame_count(samples) * FRAME_BYTES
    return Madp(channels, samples, rate, loop_start, loop_end, seek, [bytes(d[:needed]) for d in per_channel],
                version, interleave)


def decode_channel(frames: bytes, coefs: list[int], samples: int, watch: set[int] = frozenset(),
                   start: DspState | None = None) -> tuple[list[int], dict[int, DspState]]:
    """16-bit PCM of one channel, and the decoder state at each sample index in `watch`. `start` is the channel's
    state before its first sample (None: silence, as in every retail track)."""
    pcm: list[int] = []
    states: dict[int, DspState] = {}
    hist1, hist2 = (start.hist1, start.hist2) if start else (0, 0)
    for frame in range(0, len(frames) - FRAME_BYTES + 1, FRAME_BYTES):
        ps = frames[frame]
        if len(pcm) in watch:
            states[len(pcm)] = DspState(ps, hist1, hist2)
        scale, index = 1 << (ps & 0xF), ps >> 4
        c1, c2 = coefs[index * 2], coefs[index * 2 + 1]
        for n in range(FRAME_SAMPLES):
            nibble = frames[frame + 1 + n // 2]
            nibble = nibble >> 4 if n % 2 == 0 else nibble & 0xF
            if nibble >= 8:
                nibble -= 16
            sample = ((nibble * scale << 11) + 1024 + c1 * hist1 + c2 * hist2) >> 11
            sample = max(-32768, min(32767, sample))
            hist2, hist1 = hist1, sample
            pcm.append(sample)
    return pcm[:samples], states


def decode_madp(madp: Madp) -> list[list[int]]:
    """16-bit PCM of each channel."""
    return [decode_channel(d, ch.coefs, madp.samples, start=ch.start)[0] for d, ch in zip(madp.data, madp.channels)]


def trim_start(madp: Madp, samples: int) -> Madp:
    """`madp` without its first `samples`, a whole number of interleave blocks (so every seek point stays on one): the
    frames after the cut are kept as they are, each channel starts from the decoder's state there, and the loop and the
    seek points move back as much. The cut must come before the loop's start."""
    block = madp.interleave // FRAME_BYTES * FRAME_SAMPLES
    end = madp.loop_start if madp.loop_end else madp.samples
    if samples % block or not 0 <= samples < end:
        raise ValueError(f"a track's start is cut by whole blocks of {block} samples before {end}, not {samples}")
    if not samples:
        return madp
    cut = samples // FRAME_SAMPLES * FRAME_BYTES
    channels = []
    for data, channel in zip(madp.data, madp.channels):
        _, states = decode_channel(data[:cut + FRAME_BYTES], channel.coefs, samples + 1, {samples}, channel.start)
        channels.append(Channel(channel.coefs, channel.gain, states[samples], channel.loop, channel.pad))
    kept = [p for p in madp.seek if p.sample > samples]
    seek = [SeekPoint(i + 1, p.sample - samples, p.states) for i, p in enumerate(kept)]
    loop_start, loop_end = (madp.loop_start - samples, madp.loop_end - samples) if madp.loop_end else (0, 0)
    return Madp(channels, madp.samples - samples, madp.rate, loop_start, loop_end, seek, [d[cut:] for d in madp.data],
                madp.version, madp.interleave)


def build_madp(madp: Madp) -> bytes:
    """The .mca bytes in MH4U's layout: header, seek table, channel info, then the frames interleaved in
    blocks."""
    count = len(madp.channels)
    entry = 8 + 6 * count
    info = SEEK_OFFSET + entry * len(madp.seek)
    data_offset = -(-(info + CHANNEL_INFO_SIZE * count) // DATA_ALIGN) * DATA_ALIGN
    padded = [d + bytes(-len(d) % madp.interleave) for d in madp.data]
    body = bytearray()
    for at in range(0, len(padded[0]), madp.interleave):
        for d in padded:
            body += d[at:at + madp.interleave]
    out = bytearray(data_offset)
    struct.pack_into("<4sHHBBH6IfII", out, 0, b"MADP", madp.version, 0, count, 0, madp.interleave, madp.samples,
                     madp.rate, madp.loop_start, madp.loop_end, SEEK_OFFSET + CHANNEL_INFO_SIZE * count,
                     len(body), madp.seconds,
                     len(madp.seek), data_offset)
    for i, point in enumerate(madp.seek):
        at = SEEK_OFFSET + entry * i
        struct.pack_into("<2I", out, at, point.index, point.sample)
        for c, s in enumerate(point.states):
            struct.pack_into("<Hhh", out, at + 8 + 6 * c, s.ps, s.hist1, s.hist2)
    for c, ch in enumerate(madp.channels):
        struct.pack_into("<16hHHhhHhhH", out, info + CHANNEL_INFO_SIZE * c, *ch.coefs, ch.gain, ch.start.ps,
                         ch.start.hist1, ch.start.hist2, ch.loop.ps, ch.loop.hist1, ch.loop.hist2, ch.pad)
    return bytes(out + body)


# Encoder (needs numpy: pip install heavenfall[audio])

RATE = 32728  # every retail track
SEEK_SPACING = 56 * 1176  # samples between seek points (~2 s); retail spacing varies, always a multiple of 56
MAX_SCALE = 12
CANDIDATES = 4  # predictors tried per frame (best open-loop peaks): +1 dB over 1 at 1.7x the time
COEF_ITERATIONS = 24
SILENT_FRAME_ENERGY = 14 * 64 ** 2  # frames quieter than this don't shape the coefficients


def _frame_stats(x):
    """Per frame: sums of x[n-i] * x[n-j] for (i, j) in 00, 01, 02, 11, 12, 22."""
    import numpy as np
    frames = frame_count(len(x))
    padded = np.zeros(frames * FRAME_SAMPLES + 2)
    padded[2:2 + len(x)] = x
    s = [padded[2 - k:len(padded) - k] for k in range(3)]
    return {(i, j): (s[i] * s[j]).reshape(frames, FRAME_SAMPLES).sum(axis=1)
            for i, j in ((0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2))}


def _solve(r):
    """Least-squares (a1, a2) of x[n] ~ a1 x[n-1] + a2 x[n-2] from summed stats (scalars or arrays)."""
    import numpy as np
    det = r[1, 1] * r[2, 2] - r[1, 2] ** 2
    det = np.where(np.abs(det) < 1e-9, np.inf, det)
    return (r[0, 1] * r[2, 2] - r[0, 2] * r[1, 2]) / det, (r[0, 2] * r[1, 1] - r[0, 1] * r[1, 2]) / det


def compute_coefs(x) -> list[int]:
    """8 predictor pairs (s16, 1.0 = 2048) for one channel: k-means of the frames by prediction error.

    Each frame's statistics are normalised by its energy, so quiet passages count as much as loud ones
    (DSP ADPCM picks a scale per frame, so the error that matters is relative).
    """
    import numpy as np
    stats = _frame_stats(np.asarray(x, dtype=np.float64))
    keep = stats[0, 0] > SILENT_FRAME_ENERGY
    if not keep.any():
        return [0] * 16
    r = {k: v[keep] / stats[0, 0][keep] for k, v in stats.items()}

    def errors(pairs):
        a1, a2 = pairs[:, 0:1], pairs[:, 1:2]
        return (r[0, 0] - 2 * a1 * r[0, 1] - 2 * a2 * r[0, 2] + a1 ** 2 * r[1, 1] + 2 * a1 * a2 * r[1, 2]
                + a2 ** 2 * r[2, 2])

    a1, a2 = _solve({k: v + (1e-6 if k[0] == k[1] else 0) for k, v in r.items()})
    own = np.stack([a1, a2], axis=1)
    own = own[np.isfinite(own).all(axis=1)]
    order = np.argsort(own[:, 0])
    pairs = own[order[np.linspace(0, len(order) - 1, 8).astype(int)]] if len(own) else np.zeros((8, 2))
    for _ in range(COEF_ITERATIONS):
        pairs = np.clip(pairs, -32768 / 2048, 32767 / 2048)
        assign = errors(pairs).argmin(axis=0)
        for k in range(8):
            mine = assign == k
            if not mine.any():  # re-seed an empty cluster on the worst-predicted frame
                worst = errors(pairs).min(axis=0).argmax()
                pairs[k] = own[min(worst, len(own) - 1)] if len(own) else 0
                continue
            b1, b2 = _solve({key: v[mine].sum() for key, v in r.items()})
            if np.isfinite(b1) and np.isfinite(b2):
                pairs[k] = (b1, b2)
    pairs = np.clip(np.round(pairs * 2048), -32768, 32767).astype(int)
    return [int(v) for pair in pairs for v in pair]


def _quantize(frame, c1, c2, hist1, hist2, scale):
    nibbles, error, clipped = [], 0, False
    step = 1 << scale
    for value in frame:
        prediction = c1 * hist1 + c2 * hist2
        q = round(((value << 11) - prediction) / (step << 11))
        if q > 7:
            q, clipped = 7, True
        elif q < -8:
            q, clipped = -8, True
        sample = (prediction + (q * step << 11) + 1024) >> 11
        sample = -32768 if sample < -32768 else 32767 if sample > 32767 else sample
        error += (value - sample) ** 2
        hist2, hist1 = hist1, sample
        nibbles.append(q)
    return nibbles, error, clipped, hist1, hist2


def encode_channel(x, coefs: list[int], watch: set[int] = frozenset()) -> tuple[bytes, dict[int, DspState]]:
    """DSP frames of one channel (int16 samples), and the decoder state at each frame start in `watch`.

    The predictor and a first scale come from the source (vectorised); quantisation then follows the
    decoder exactly, retrying one scale up when a frame clips.
    """
    import numpy as np
    x = np.asarray(x, dtype=np.int64)
    frames = frame_count(len(x))
    padded = np.zeros(frames * FRAME_SAMPLES + 2, dtype=np.int64)
    padded[2:2 + len(x)] = x
    s0 = padded[2:].reshape(frames, FRAME_SAMPLES)
    s1 = padded[1:-1].reshape(frames, FRAME_SAMPLES)
    s2 = padded[:-2].reshape(frames, FRAME_SAMPLES)
    pairs = np.array(coefs, dtype=np.int64).reshape(8, 2)
    peaks = np.stack([np.abs(s0 * 2048 - c1 * s1 - c2 * s2).max(axis=1) for c1, c2 in pairs], axis=1) / 2048
    scales = np.zeros(peaks.shape, dtype=np.int64)
    for _ in range(MAX_SCALE):
        scales += peaks > 7.5 * (1 << scales)
    candidates = np.argsort(peaks, axis=1, kind="stable")[:, :CANDIDATES].tolist()
    scales = scales.tolist()
    pairs = pairs.tolist()
    out = bytearray()
    states: dict[int, DspState] = {}
    hist1 = hist2 = 0
    rows = s0.tolist()
    for f in range(frames):
        best = None
        for k in candidates[f]:
            c1, c2 = pairs[k]
            scale = scales[f][k]
            tried = _quantize(rows[f], c1, c2, hist1, hist2, scale)
            if tried[2] and scale < MAX_SCALE:
                retry = _quantize(rows[f], c1, c2, hist1, hist2, scale + 1)
                if retry[1] < tried[1]:
                    tried, scale = retry, scale + 1
            if best is None or tried[1] < best[0][1]:
                best = tried, k, scale
        best, k, scale = best
        if f * FRAME_SAMPLES in watch:
            states[f * FRAME_SAMPLES] = DspState(k << 4 | scale, hist1, hist2)
        nibbles, _, _, hist1, hist2 = best
        out.append(k << 4 | scale)
        for n in range(0, FRAME_SAMPLES, 2):
            out.append((nibbles[n] & 0xF) << 4 | nibbles[n + 1] & 0xF)
    return bytes(out), states


def encode_madp(pcm, rate: int = RATE, loop_start: int = 0, loop_end: int = 0) -> Madp:
    """A MADP of int16 PCM (channels x samples). `loop_start` must be a frame boundary (multiple of 14)."""
    if loop_end and loop_start % FRAME_SAMPLES:
        raise ValueError("loop_start must be a multiple of 14 samples")
    samples = len(pcm[0])
    seek_at = list(range(SEEK_SPACING, samples, SEEK_SPACING))
    watch = set(seek_at) | ({loop_start} if loop_end else set())
    channels, data, states = [], [], []
    for x in pcm:
        coefs = compute_coefs(x)
        frames, found = encode_channel(x, coefs, watch)
        start = DspState(frames[0] if frames else 0)
        channels.append(Channel(coefs, start=start, loop=found.get(loop_start, DspState()) if loop_end
                                else DspState()))
        data.append(frames)
        states.append(found)
    seek = [SeekPoint(i + 1, at, [s[at] for s in states]) for i, at in enumerate(seek_at)]
    return Madp(channels, samples, rate, loop_start if loop_end else 0, loop_end, seek, data)


def _resample(x, length: int):
    """FFT resampling of float rows to `length` samples (treats each row as periodic)."""
    import numpy as np
    n = x.shape[1]
    spectrum = np.fft.rfft(x, axis=1)
    out = np.zeros((x.shape[0], length // 2 + 1), dtype=complex)
    keep = min(spectrum.shape[1], out.shape[1])
    out[:, :keep] = spectrum[:, :keep]
    return np.fft.irfft(out, n=length, axis=1) * (length / n)


def prepare_pcm(pcm, rate: int, loop: tuple[int, int] | None = None, target_rate: int = RATE):
    """Make source audio ready for `encode_madp`: stereo int16 at the game's rate, loop on a frame boundary.

    `pcm` is float or int rows (channels x samples) in the int16 range; `loop` is (start, end) in source
    samples, end exclusive. Returns (pcm, loop_start, loop_end); a looped track keeps LOOP_TAIL samples
    after loop_end (the audio that follows, as in retail files). Seamless: the loop length is resampled
    to a whole number of samples, so the music after loop_end continues exactly as at loop_start.
    """
    import numpy as np
    x = np.asarray(pcm, dtype=np.float64)
    if x.ndim == 1:
        x = x[None]
    if x.shape[0] == 1:
        x = np.repeat(x, 2, axis=0)
    if x.shape[0] != 2:
        raise ValueError("only mono or stereo audio")
    if loop is None:
        length = round(x.shape[1] * target_rate / rate)
        out = x if length == x.shape[1] else _resample(x, length)
        start = end = 0
    else:
        start, end = loop
        if not 0 <= start < end <= x.shape[1]:
            raise ValueError("loop outside the audio")
        body = end - start
        new_body = round(body * target_rate / rate)
        ratio = new_body / body
        repeats = 1 + -(-(rate + LOOP_TAIL) // body)  # at least one more loop and a second of margin
        ext = np.concatenate([x[:, :end]] + [x[:, start:end]] * repeats, axis=1)
        out = ext if new_body == body else _resample(ext, round(ext.shape[1] * ratio))
        start = round(start * ratio)
        pad = -start % FRAME_SAMPLES
        start += pad
        end = start + new_body
        out = np.concatenate([np.zeros((2, pad)), out], axis=1)[:, :end + LOOP_TAIL]
    return np.clip(np.round(out), -32768, 32767).astype(np.int16), start, end
