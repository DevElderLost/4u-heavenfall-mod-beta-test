"""Heavenfall Beta's web page: the static site that builds the mod in the player's browser (docs/develop/development.md,
"The web page"). No server is needed: every step runs on the player's device, on the game file chosen there.

    python tools/release/build_web.py [--out DIR] [--cache DIR]   # write the site (default: work/web/site)
    python tools/release/build_web.py --skip-pyodide              # ... without the Python engine: the page only
    python tools/release/build_web.py --serve [--port N]          # ... and serve it on this machine's network
    python tools/release/build_web.py --download-only             # only fetch and check Pyodide's files
    python tools/release/build_web.py --pin VERSION               # move web/pyodide.json to another Pyodide version

Only the standard library. The site holds:

    index.html, page.js, worker.js, engine.js, style.css, logo.png     the page (web/)
    options.json        the program's options in both languages (core/app/web.py)
    build.json          this build's version and where its parts are
    heavenfall-<hash>.zip  the mod's Python code and data, named after its content so a browser downloads it once
    pyodide/<version>/  Python for the browser, each file checked against web/pyodide.json
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import io
import json
import os
import shutil
import socket
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WEB = ROOT / "web"
PINS = WEB / "pyodide.json"
PAGE_FILES = ("index.html", "page.js", "worker.js", "engine.js", "style.css", "THIRD_PARTY.txt")
LOGO = ROOT / "core" / "gui" / "qt" / "assets" / "logo.png"
LICENSE = ROOT / "LICENSE"
# The Pyodide files a page loads; the packages it needs, and theirs, are found in pyodide-lock.json
PYODIDE_FILES = ("pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json")
PACKAGES = ("zstandard",)
# What the page's run never reads: the Qt program and the sources of the code already compiled into code_space.json
BUNDLE_SKIPS_FOLDERS = ("core/gui/qt/", "core/interface/game_gui/recorder/")
BUNDLE_SKIPS_SUFFIXES = (".pyc", ".c", ".h", ".s", ".ld")
MIME_TYPES = {".js": "text/javascript", ".mjs": "text/javascript", ".wasm": "application/wasm",
              ".json": "application/json"}
ZIP_DATE = (1980, 1, 1, 0, 0, 0)       # the same bytes for the same files


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url) as answer:
        return answer.read()


def pinned() -> dict:
    return json.loads(PINS.read_text(encoding="utf-8"))


def pyodide_files(cache: Path) -> Path:
    """The pinned Pyodide version's files in `cache`/<version>, fetched when missing and always checked. Returns its
    folder. A file already there is never written again, and a new one appears whole: several builds may share a cache.
    Raises ValueError for a file whose checksum is not the pinned one."""
    pins = pinned()
    folder = Path(cache) / pins["version"]
    folder.mkdir(parents=True, exist_ok=True)
    for name, digest in pins["files"].items():
        path = folder / name
        fetched = not path.is_file()
        data = _download(pins["base_url"].format(version=pins["version"]) + name) if fetched else path.read_bytes()
        if _sha256(data) != digest:
            raise ValueError(f"{name} is not the pinned file of Pyodide {pins['version']} ({_sha256(data)})")
        if fetched:
            temporary = path.with_name(f"{name}.{os.getpid()}.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)
    return folder


def with_dependencies(packages: dict, wanted: tuple[str, ...]) -> list[str]:
    """`wanted` and everything they depend on, by the lock file's `packages`: Pyodide asks for all of them."""
    found, pending = [], list(wanted)
    while pending:
        name = pending.pop()
        if name not in found:
            found.append(name)
            pending += packages[name]["depends"]
    return found


def pin(version: str) -> None:
    """Point web/pyodide.json at Pyodide `version`, with the checksums of what its site serves today."""
    pins = pinned()
    base = pins["base_url"].format(version=version)
    packages = json.loads(_download(base + "pyodide-lock.json"))["packages"]
    wheels = [packages[name]["file_name"] for name in with_dependencies(packages, PACKAGES)]
    pins |= {"version": version, "files": {name: _sha256(_download(base + name)) for name in [*PYODIDE_FILES, *wheels]}}
    PINS.write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8", newline="\n")


def bundle() -> bytes:
    """The mod's code and data as a zip, the same bytes for the same files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted((ROOT / "core").rglob("*")):
            name = path.relative_to(ROOT).as_posix()
            skipped = name.startswith(BUNDLE_SKIPS_FOLDERS) or name.endswith(BUNDLE_SKIPS_SUFFIXES)
            if path.is_file() and not skipped:
                info = zipfile.ZipInfo(name, ZIP_DATE)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def write_site(out: Path, cache: Path | None) -> dict:
    """The whole site in `out`, emptied first; `cache` None leaves Pyodide out. Returns what build.json says."""
    from core import __version__
    from core.app import web
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in PAGE_FILES:
        shutil.copyfile(WEB / name, out / name)
    shutil.copyfile(LOGO, out / "logo.png")
    shutil.copyfile(LICENSE, out / "LICENSE.txt")
    (out / "options.json").write_text(json.dumps({language: web.options(language) for language in ("es", "en")},
                                                 ensure_ascii=False), encoding="utf-8")
    code = bundle()
    name = f"heavenfall-{_sha256(code)[:12]}.zip"
    (out / name).write_bytes(code)
    pins = pinned()
    info = {"version": __version__, "pyodide": f"pyodide/{pins['version']}", "pyodide_version": pins["version"],
            "bundle": name}
    (out / "build.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    if cache is not None:
        folder = pyodide_files(cache)
        target = out / info["pyodide"]
        target.mkdir(parents=True)
        for file_name in pins["files"]:
            shutil.copyfile(folder / file_name, target / file_name)
    return info


class _Site(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **MIME_TYPES}


def _local_address() -> str:
    """This machine's address on its network (nothing is sent: a UDP socket only picks its route)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))
        return probe.getsockname()[0]


def serve(site: Path, port: int) -> None:
    """The site on this machine's network until Ctrl+C, to try it on a phone before publishing."""
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), functools.partial(_Site, directory=str(site)))
    print(f"Open http://{_local_address()}:{server.server_address[1]}/ (Ctrl+C stops it)", flush=True)
    with server:
        server.serve_forever()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Heavenfall Beta's web page: the static site")
    parser.add_argument("--out", type=Path, default=ROOT / "work" / "web" / "site", help="the site's folder")
    parser.add_argument("--cache", type=Path, default=ROOT / "work" / "web" / "cache",
                        help="Pyodide's files, kept here")
    parser.add_argument("--skip-pyodide", action="store_true", help="the page without its Python engine")
    parser.add_argument("--download-only", action="store_true", help="only fetch and check Pyodide's files")
    parser.add_argument("--pin", metavar="VERSION", help="point web/pyodide.json at another Pyodide version")
    parser.add_argument("--serve", action="store_true", help="serve the site on this machine's network")
    parser.add_argument("--port", type=int, default=8765, help="the port --serve uses")
    args = parser.parse_args(argv)
    if args.pin:
        pin(args.pin)
        return 0
    if args.download_only:
        print(pyodide_files(args.cache))
        return 0
    info = write_site(args.out, None if args.skip_pyodide else args.cache)
    print(f"Site of version {info['version']} in {args.out}", flush=True)
    if args.serve:
        serve(args.out, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
