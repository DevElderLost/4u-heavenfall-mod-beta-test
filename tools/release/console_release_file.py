"""The release's own copy of its releases/latest answer, for the 3DS launcher: when the GitHub API gives no answer (its
hourly limit per address is spent behind an address many share), the
launcher reads this file from github.com instead, with the same rules (each asset's name, size, `sha256:` digest and
download URL of the edition's repository).

    python tools/release/console_release_file.py --repo OWNER/NAME --tag vX.Y.Z [--changelog CHANGELOG.md]
        --out FILE FILES...

The text (`body`, the launcher's notes) is the changelog's section of the tag's version, as the release's own text
(tools/release/changelog_section.py); none when the section is missing. The release workflow runs it with the
runner's own Python, so it needs nothing but the standard library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

try:
    from tools.release.changelog_section import section
except ImportError:   # run as a script: its own folder is on the path
    from changelog_section import section


def answer(repository: str, tag: str, files: list[Path], notes: str = "") -> dict:
    """A releases/latest answer listing `files` as the assets of `tag` in `repository`."""
    assets = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assets.append({"name": path.name, "size": path.stat().st_size, "digest": f"sha256:{digest}",
                       "browser_download_url": f"https://github.com/{repository}/releases/download/{tag}/{path.name}"})
    if len({a["name"] for a in assets}) != len(assets):
        raise ValueError("two files with one name")
    return {"tag_name": tag, "name": tag, "body": notes, "assets": assets}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--changelog", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    notes = ""
    if args.changelog:
        try:
            notes = section(args.changelog.read_text(encoding="utf-8"), args.tag)
        except ValueError as error:
            print(f"{args.changelog}: {error}; the file has no text", file=sys.stderr)
    files = [path for path in args.files if path.resolve() != args.out.resolve()]
    args.out.write_text(json.dumps(answer(args.repo, args.tag, files, notes), indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
