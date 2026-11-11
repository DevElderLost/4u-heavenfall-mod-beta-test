"""The provenance file of a run with MH XX: `mhxx_sources.txt` in the
mod folder, beside the pack's manifest and not part of the mod's files (no installer or patch set takes it). UTF-8,
one line per file a run made from MH XX's archives (the hunters' `romfs/data/pl_*` and the Felynes' `o_*`): its mod
path, a tab, then the MH XX RomFS paths it was read from, tab-separated, in the order the run read them, each once.
Sorted by mod path; a file with no MH XX source has no line.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path

FILE = "mhxx_sources.txt"


def write_sources(mod_dir: Path, sources: Mapping[str, Sequence[str]]) -> None:
    """Write FILE into `mod_dir` from `sources` (mod path -> MH XX paths read), or remove it when no file has one."""
    lines = []
    for mod_path in sorted(sources):
        paths = list(dict.fromkeys(sources[mod_path]))
        if not paths:
            continue
        if any(c in text for text in (mod_path, *paths) for c in "\t\r\n"):
            raise ValueError(f"a tab or a line break in the provenance of {mod_path}")
        lines.append("\t".join((mod_path, *paths)) + "\n")
    target = Path(mod_dir) / FILE
    if lines:
        target.write_bytes("".join(lines).encode("utf-8"))
    else:
        target.unlink(missing_ok=True)


def read_sources(mod_dir: Path) -> dict[str, tuple[str, ...]]:
    """The file's content (mod path -> MH XX paths), empty when `mod_dir` has none."""
    target = Path(mod_dir) / FILE
    if not target.is_file():
        return {}
    out = {}
    for line in target.read_text(encoding="utf-8").split("\n"):
        if line:
            mod_path, *paths = line.split("\t")
            out[mod_path] = tuple(paths)
    return out
