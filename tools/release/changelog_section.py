"""One version's section of a changelog, as a release's text.

    python tools/release/changelog_section.py CHANGELOG.md 0.2.0

prints what stands under the heading "## 0.2.0" (up to the next "## " heading), without the heading and without the
blank lines around it. A missing or empty section is an error (exit status 1): a release must not go out without its
text. A leading "v" on the version is ignored.
"""

from __future__ import annotations

import sys
from pathlib import Path


def section(text: str, version: str) -> str:
    """The lines under "## <version>" until the next "## " heading, trimmed; ValueError when there are none."""
    wanted = version.strip().removeprefix("v")
    lines = text.splitlines()
    start = next((i + 1 for i, line in enumerate(lines)
                  if line.startswith("## ") and line[3:].strip().removeprefix("v") == wanted), None)
    if start is None:
        raise ValueError(f"no section '## {wanted}'")
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = "\n".join(lines[start:end]).strip("\n")
    body = "\n".join(line.rstrip() for line in body.splitlines()).strip()
    if not body:
        raise ValueError(f"the section '## {wanted}' is empty")
    return body + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: changelog_section.py CHANGELOG.md VERSION", file=sys.stderr)
        return 2
    try:
        text = Path(argv[0]).read_text(encoding="utf-8")
        sys.stdout.buffer.write(section(text, argv[1]).encode("utf-8"))
    except (OSError, ValueError) as error:
        print(f"{argv[0]}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
