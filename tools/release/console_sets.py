"""The release's shared file and the check of its patch sets, run by the release workflow with the runner's own Python
(standard library only):

    python tools/release/console_sets.py [--kind console|android] [--sets DIR] [--version V]
        --shared-out dist/<app>-3ds-shared.hfpack

Makes the release's shared file (core/install/title/shared_file.py) from this checkout's files into --shared-out and
checks every patch set the edition file names for the --kind in --sets: present, a release's set whose whole-set hash
holds, of this version and of the edition, of the region and MH XX its name says, made from this checkout's
`core/` files (its source stamp, recomputed from the files git lists) and reading this shared file or none. A console
set is format 3 (`console_release`, the folder console/); a set for Heavenfall for Android is format 4
(`android_release`, the folder android/), made from the update its edition file names. A set of the other kind is
refused, so the two never mix. Each problem is printed; the exit code is 1 when there is any.
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
FORMAT_SHARED = 3                    # core/install/title/patchset.py: the console's release sets
FORMAT_UPDATE = 4                    # and the recompiled game's
HEADER = 0x100                       # format 3's header
HEADER_UPDATE = 0x140                # format 4's: the update's title id at 0x100
UPDATE_AT = 0x100
SLOT_LENGTH_AT = 0x34                # the title-build slot's length: a set for Android has none
# per kind: the set format, the edition file's section naming its sets, the header's size
KINDS = {"console": (FORMAT_SHARED, "console_release", HEADER), "android": (FORMAT_UPDATE, "android_release",
                                                                              HEADER_UPDATE)}
REGIONS = {"eur": 0, "usa": 1}
PATCH_KEY = re.compile(r"patch_(eur|usa)(_xx)?")


def program_version(root: Path) -> str:
    found = re.search(r'^__version__\s*=\s*"([^"]+)"', (root / "core" / "__init__.py").read_text(encoding="utf-8"),
                      re.M)
    if not found:
        raise SystemExit("no __version__ in core/__init__.py")
    return found.group(1)


def expected_sets(edition: dict, kind: str = "console") -> dict[str, tuple[int, bool]]:
    """{set name: (region, MH XX)} of every patch set the edition file names for `kind`."""
    out = {}
    for key, name in edition[KINDS[kind][1]].items():
        match = PATCH_KEY.fullmatch(key)
        if match:
            out[name] = (REGIONS[match.group(1)], bool(match.group(2)))
    return out


def check_set(name: str, blob: bytes, want: tuple[int, bool], app_name: str, version: str, stamp: bytes,
              shared: bytes, kind: str = "console", update_title: str | None = None) -> list[str]:
    """What is wrong with the set `name` (its bytes `blob`) of `kind`: [] when nothing. `update_title`: the title id
    (hex) of the update an Android set must be made from."""
    region, xx = want
    form, _section, header = KINDS[kind]
    if len(blob) < min(HEADER, header) or blob[:4] != MAGIC:
        return [f"{name} is not a patch set"]
    made_form, made_region = struct.unpack_from("<II", blob, 4)
    if made_form != form:
        other = {FORMAT_SHARED: ", a console set", FORMAT_UPDATE: ", a set for Android"}.get(made_form, "")
        target = "Android" if kind == "android" else "the console"
        return [f"{name} is format {made_form}{other}, not a release's set for {target} (format {form})"]
    if len(blob) < header:
        return [f"{name} is not a patch set"]
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
    if flags:   # every console title carries the Cheats group: no set records a cheats variant
        problems.append(f"{name}: its header has flags {flags:#x}, a set of a release has none")
    if made_from != stamp:
        problems.append(f"{name} was made from other code than this tree's core/ (stamp {made_from.hex()[:16]}, the "
                        f"tree's {stamp.hex()[:16]})")
    if named not in (bytes(32), shared):
        problems.append(f"{name} reads another shared file than the one made from this tree's files")
    if kind == "android":
        made_update = struct.unpack_from("<Q", blob, UPDATE_AT)[0]
        if update_title is None or made_update != int(update_title, 16):
            problems.append(f"{name} is made from the update {made_update:016x}, not the edition's {update_title}")
        if struct.unpack_from("<I", blob, SLOT_LENGTH_AT)[0]:
            problems.append(f"{name} carries a title-build slot, which a set for Android has none of")
    return problems


def check_folder(folder: Path, edition: dict, version: str, stamp: bytes, shared: bytes,
                 kind: str = "console") -> list[str]:
    """Every problem of the `kind` patch sets of `folder`."""
    problems = []
    update_title = edition.get("android_release", {}).get("update_title")
    for name, want in sorted(expected_sets(edition, kind).items()):
        path = folder / name
        if not path.is_file():
            problems.append(f"{name} is missing: every set of the edition file is needed")
            continue
        problems += check_set(name, path.read_bytes(), want, edition["app_name"], version, stamp, shared, kind,
                              update_title)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="the checkout (default: this one)")
    parser.add_argument("--kind", choices=sorted(KINDS), default="console",
                        help="which sets to check: console (format 3) or android (format 4); default console")
    parser.add_argument("--sets", type=Path, help="the patch sets' folder (default: console/ or android/ of the "
                                                  "checkout)")
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
    problems = check_folder(args.sets or root / args.kind, edition, args.version or program_version(root), stamp,
                            hashlib.sha256(blob).digest(), args.kind)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"shared file {args.shared_out} ({len(blob)} bytes); source stamp {stamp.hex()}; "
          f"{'problems: ' + str(len(problems)) if problems else 'every ' + args.kind + ' set checked'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
