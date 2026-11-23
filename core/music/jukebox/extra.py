"""The jukebox's extra songs: `.mca` files (MADP, already looped) imported from a folder into
`core/music/jukebox/extra/`, one record each in curated/jukebox.json (source and category `extra`) and a level in
extra_ost_volumes.json. Run by tools/build/import_jukebox_tracks.py, never by a build; a build uses only `check_madp`
and `in_mh4u_layout` (MH XX's village themes, read from the player's game).

The module is shared with Heavenfall Beta, so nothing of a left-out subsystem is imported here.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

from core.game.data.paths import CURATED_DIR
from core.music.audio.madp import CHANNEL_INFO_SIZE, SEEK_OFFSET, build_madp, parse_madp
from core.music.audio.volumes import VOLUMES_FILE

EXTRA_DIR = Path(__file__).resolve().parent / "extra"
EXTRA_PATH = "core/music/jukebox/extra"     # EXTRA_DIR relative to the checkout's top
CATALOGUE_FILE = CURATED_DIR / "jukebox.json"
SOURCE = CATEGORY = "extra"
CHANNELS, RATE, ADPCM_FRAME_SAMPLES = 2, 32728, 14
DEFAULT_PERCENT = 100
LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
HEADER_BYTES = 0x1C
CATALOGUE_END = "\n ]\n}\n"                  # how jukebox.json ends: the tracks are its last key
VOLUMES_END = "\n}\n"


class ExtraError(ValueError):
    """A song that cannot be imported, or a file that is not laid out as the importer expects."""


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)     # (file name, why)
    lines: list[str] = field(default_factory=list)


def slug_of(file_name: str) -> str:
    """Lowercase ASCII letters, digits and '_' from a file name's stem (anything else becomes '_', runs merge)."""
    return re.sub(r"[^a-z0-9]+", "_", Path(file_name).stem.lower()).strip("_")


def title_of(file_name: str) -> str:
    """The file name's stem in title case, with '_' as spaces."""
    return " ".join(Path(file_name).stem.replace("_", " ").split()).title()


def check_madp(data: bytes) -> dict:
    """{samples, loop_start, loop_end, seconds} of a MADP that a track can be made from; ExtraError for anything
    else: not MADP, not two channels, not 32728 Hz, loop points outside the samples, a loop start that is not a
    multiple of 14 (loop_end 0 means no loop)."""
    if len(data) < HEADER_BYTES or data[:4] != b"MADP":
        raise ExtraError("not a MADP file")
    channels = data[0x08]
    samples, rate, loop_start, loop_end = struct.unpack_from("<4I", data, 0x0C)
    if channels != CHANNELS:
        raise ExtraError(f"{channels} channel(s), needs {CHANNELS}")
    if rate != RATE:
        raise ExtraError(f"{rate} Hz, needs {RATE}")
    if samples == 0:
        raise ExtraError("no samples")
    if loop_end:
        if not loop_start < loop_end <= samples:
            raise ExtraError(f"loop {loop_start}..{loop_end} is not inside the {samples} samples")
        if loop_start % ADPCM_FRAME_SAMPLES:
            raise ExtraError(f"loop start {loop_start} is not a multiple of {ADPCM_FRAME_SAMPLES}")
    return {"samples": samples, "loop_start": loop_start, "loop_end": loop_end, "seconds": samples / rate}


def in_mh4u_layout(data: bytes) -> bytes:
    """`data` as MH4U plays it: a MADP in MH Generations' layout (build date in the header, size 0x98 for two
    channels) is rewritten with the same frames, seek table and loop in MH4U's layout (0x90); any other is returned
    as it is. Call after check_madp."""
    (head,) = struct.unpack_from("<I", data, 0x1C)
    if head == SEEK_OFFSET + CHANNEL_INFO_SIZE * data[0x08]:
        return data
    try:
        return build_madp(parse_madp(data))
    except (ValueError, struct.error, IndexError) as error:
        raise ExtraError(f"a MADP in an unknown layout ({error})") from error


def _new_record(track_id: int, slug: str, title: str) -> dict:
    return {"id": track_id, "path": f"{EXTRA_PATH}/{slug}.mca", "category": CATEGORY, "source": SOURCE,
            "name": {"text": {lang: title for lang in LANGUAGES}}, "provisional": True}


def _append(text: str, end: str, addition: str, what: str) -> str:
    """`text` with `addition` before its `end`, which it must have."""
    if not text.endswith(end):
        raise ExtraError(f"{what} does not end as expected")
    return text[:-len(end)] + addition + end


def import_inbox(inbox: Path, extra_dir: Path = EXTRA_DIR, catalogue_file: Path = CATALOGUE_FILE,
                 volumes_file: Path = VOLUMES_FILE) -> Report:
    """Import every `.mca` of `inbox` (other files are ignored): checked, copied to `extra_dir`, one record each in
    `catalogue_file` and a level in `volumes_file` when it has none. A song already imported with the same bytes
    changes nothing; with other bytes its copy is replaced and its id kept. A bad file is reported and skipped. Both
    JSON files keep every byte but the lines added (one record per line). A new id is the highest one ever used + 1."""
    report = Report()
    text = catalogue_file.read_bytes().decode("utf-8")
    records = json.loads(text)["tracks"]
    by_path = {r["path"]: r for r in records}
    next_id = max((r["id"] for r in records), default=0) + 1
    volumes_text = volumes_file.read_bytes().decode("utf-8")
    volumes = json.loads(volumes_text)
    new_records, new_volumes, copies, taken = [], [], [], {}
    for source in sorted(inbox.iterdir(), key=lambda p: p.name.lower()):
        if not source.is_file() or source.suffix.lower() != ".mca":
            continue
        slug = slug_of(source.name)
        content = source.read_bytes()
        try:
            if not slug:
                raise ExtraError("no letters or digits in the name")
            if slug in taken:
                raise ExtraError(f"same song name as {taken[slug]}")
            info = check_madp(content)
            content = in_mh4u_layout(content)
        except ExtraError as error:
            report.skipped.append((source.name, str(error)))
            continue
        taken[slug] = source.name
        target = extra_dir / f"{slug}.mca"
        record = by_path.get(f"{EXTRA_PATH}/{slug}.mca")
        if record is None:
            record = _new_record(next_id, slug, title_of(source.name))
            next_id += 1
            new_records.append(record)
            report.added.append(slug)
            report.lines.append(f"added {slug}: id {record['id']}, {info['seconds']:.1f} s, loop "
                                f"{info['loop_start']}..{info['loop_end']}, {len(content)} bytes")
        elif not target.is_file() or target.read_bytes() != content:
            report.updated.append(slug)
            report.lines.append(f"updated {slug}: id {record['id']} kept, {len(content)} bytes")
        else:
            report.unchanged.append(slug)
            continue
        copies.append((target, content))
        if slug not in volumes:
            volumes[slug] = DEFAULT_PERCENT
            new_volumes.append(slug)
    if new_records:
        text = _append(text, CATALOGUE_END, "".join(f",\n  {json.dumps(r, ensure_ascii=False)}" for r in new_records),
                       "the catalogue")
    if new_volumes:
        volumes_text = _append(volumes_text, VOLUMES_END,
                               "".join(f',\n  "{slug}": {DEFAULT_PERCENT}' for slug in new_volumes), "the volumes file")
    for target, content in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    if new_records:
        catalogue_file.write_bytes(text.encode("utf-8"))
    if new_volumes:
        volumes_file.write_bytes(volumes_text.encode("utf-8"))
    return report
