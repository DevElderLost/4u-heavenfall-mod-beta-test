"""The console release's shared file and the check of its patch sets, run by the release workflow with the runner's
own Python (standard library only):

    python tools/release/console_sets.py [--sets console] [--version V] --shared-out dist/<app>-3ds-shared.hfpack

Makes the release's shared file (core/install/title/shared_file.py) from this checkout's songs into --shared-out and
checks every patch set the edition file names in --sets: present, a release's set (format 3) whose whole-set hash
holds, of this version and of the edition, of the region, MH XX and cheats its name says, made from this checkout's
`core/` files (its source stamp, recomputed from the files git lists) and reading this shared file or none. Each
problem is printed; the exit code is 1 when there is any.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.install.title.shared_file import (  # noqa: E402  (standard library only)
    checkout_tree_digest, shared_files, shared_name, write_shared)

EDITION_FILE = "core/game/data/curated/edition.json"
MAGIC = b"HFPS"
FORMAT_SHARED = 3                    # core/install/title/patchset.py
HEADER = 0x100
FLAG_CHEATS = 1
REGIONS = {"eur": 0, "usa": 1}
PATCH_KEY = re.compile(r"patch_(eur|usa)(_xx)?(_cheats)?")


def program_version(root: Path) -> str:
    found = re.search(r'^__version__\s*=\s*"([^"]+)"', (root / "core" / "__init__.py").read_text(encoding="utf-8"),
                      re.M)
    if not found:
        raise SystemExit("no __version__ in core/__init__.py")
    return found.group(1)


def expected_sets(edition: dict) -> dict[str, tuple[int, bool, bool]]:
    """{set name: (region, MH XX, cheats)} of every patch set the edition file names."""
    out = {}
    for key, name in edition["console_release"].items():
        match = PATCH_KEY.fullmatch(key)
        if match:
            out[name] = (REGIONS[match.group(1)], bool(match.group(2)), bool(match.group(3)))
    return out


def check_set(name: str, blob: bytes, want: tuple[int, bool, bool], app_name: str, version: str, stamp: bytes,
              shared: bytes) -> list[str]:
    """What is wrong with the set `name` (its bytes `blob`): [] when nothing."""
    region, xx, cheats = want
    if len(blob) < HEADER or blob[:4] != MAGIC:
        return [f"{name} is not a patch set"]
    form, made_region = struct.unpack_from("<II", blob, 4)
    if form != FORMAT_SHARED:
        return [f"{name} is format {form}, not a release's set (format {FORMAT_SHARED})"]
    if hashlib.sha256(blob[:0x60] + blob[0x80:]).digest() != blob[0x60:0x80]:
        return [f"{name} is damaged (its hash does not hold)"]
    text = lambda at: blob[at:at + 16].split(b"\0", 1)[0].decode("utf-8", "replace")  # noqa: E731
    title = struct.unpack_from("<Q", blob, 0x80)[0]
    named, _size, made_from, flags = struct.unpack_from("<32sQ32sI", blob, 0xB0)
    problems = []
    if text(0x50) != version:
        problems.append(f"{name} is version {text(0x50)}, the program's is {version}")
    if text(0x40) != app_name:
        problems.append(f"{name} is of the edition {text(0x40)}, not {app_name}")
    if made_region != region:
        problems.append(f"{name} holds the set of the other region")
    if bool(title) != xx:
        problems.append(f"{name}: its name and its header differ on MH XX")
    if bool(flags & FLAG_CHEATS) != cheats:
        problems.append(f"{name}: its name and its header differ on the cheats")
    if made_from != stamp:
        problems.append(f"{name} was made from other code than this tree's core/ (stamp {made_from.hex()[:16]}, the "
                        f"tree's {stamp.hex()[:16]})")
    if named not in (bytes(32), shared):
        problems.append(f"{name} reads another shared file than the one made from this tree's songs")
    return problems


def check_folder(folder: Path, edition: dict, version: str, stamp: bytes, shared: bytes) -> list[str]:
    """Every problem of the patch sets of `folder`."""
    problems = []
    for name, want in sorted(expected_sets(edition).items()):
        path = folder / name
        if not path.is_file():
            problems.append(f"{name} is missing: every set of the edition file is needed")
            continue
        problems += check_set(name, path.read_bytes(), want, edition["app_name"], version, stamp, shared)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="the checkout (default: this one)")
    parser.add_argument("--sets", type=Path, help="the patch sets' folder (default: console/ of the checkout)")
    parser.add_argument("--version", help="the release's version (default: core/__init__.py's)")
    parser.add_argument("--shared-out", type=Path, required=True, help="where the shared file is written")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    edition = json.loads((root / EDITION_FILE).read_text(encoding="utf-8"))
    blob = write_shared(shared_files(root))
    if args.shared_out.name != shared_name(edition["console_release"]["app_cia"]):
        print(f"{args.shared_out.name} is not the shared file's release name "
              f"{shared_name(edition['console_release']['app_cia'])}", file=sys.stderr)
        return 1
    args.shared_out.parent.mkdir(parents=True, exist_ok=True)
    args.shared_out.write_bytes(blob)
    stamp = checkout_tree_digest(root)
    problems = check_folder(args.sets or root / "console", edition, args.version or program_version(root), stamp,
                            hashlib.sha256(blob).digest())
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"shared file {args.shared_out} ({len(blob)} bytes); source stamp {stamp.hex()}; "
          f"{'problems: ' + str(len(problems)) if problems else 'every set checked'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
