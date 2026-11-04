"""Bringing the Windows program to the latest release of its own edition.

`tools/release/exe/heavenfall_update.py` is a console program beside the app: it asks GitHub for the edition's latest
release (`edition.json`: `repository`), downloads the zip, checks its size, its SHA-256 and its contents, replaces the
program's files and starts the new command line to rebuild the installed mod (`install/update_mod.py`).

Standard library only, and only the light modules of the package (the edition file, the saved language, the version):
the updater is a small program of its own with no Qt and no game data. Nothing here changes the URL it asks: the API's
address is a parameter only the tests change, and `main` accepts a download only from the repository's own releases.
Everything is imported before the update starts: a one-file program reads its modules from its own .exe, whose name
holds the new updater once the files are replaced.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core import __version__
from core.app.edition import Edition, edition

API = "https://api.github.com"
DOWNLOADS = "https://github.com/{repository}/releases/download/"
TIMEOUT = 30                    # seconds without an answer
CHUNK = 1 << 20
MAX_JSON = 4 << 20              # the API's answer is a few KB
MOVE_TRIES, MOVE_WAIT = 40, 0.25    # a move Windows refuses: the tries, and the seconds between them
OLD = ".old"                    # what a replaced file is called until the update ends (and after, while it is running)
STAGING = ".update_new"         # the new files, beside the program, until they are put in place
INTERNAL = "_internal"
NOTICES = ("LICENSE.txt", "THIRD_PARTY.txt")
LANGUAGES = ("en", "es")
Say = Callable[..., None]       # say(key, name=value...): one message of MESSAGES


class UpdateError(Exception):
    """An update that cannot go on; `key` is a message of MESSAGES, `params` fill it."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params


# The player sees these, in English or Spanish; {name} is the product's.
MESSAGES: dict[str, tuple[str, str]] = {
    "version": ("{updater} {version}", "{updater} {version}"),
    "only_windows": ("Only the Windows program can update itself.", "Solo el programa de Windows puede actualizarse."),
    "not_beside": ("This updater must be in the same folder as {app}.exe.",
                   "Este actualizador debe estar en la misma carpeta que {app}.exe."),
    "looking": ("Looking for a newer version of {name}...", "Buscando una versión nueva de {name}..."),
    "no_release": ("{name} has no published version yet.", "{name} aún no tiene ninguna versión publicada."),
    "latest": ("Latest published version: {latest} (yours: {current}). {verdict}",
               "Última versión publicada: {latest} (la tuya: {current}). {verdict}"),
    "is_newer": ("It is newer.", "Es más nueva."),
    "not_newer": ("It is not newer.", "No es más nueva."),
    "up_to_date": ("{name} {current} is already the latest version.",
                   "{name} {current} ya es la última versión."),
    "downloading": ("Downloading {name} {latest} ({megabytes} MB)...",
                    "Descargando {name} {latest} ({megabytes} MB)..."),
    "checking": ("Checking the download...", "Comprobando la descarga..."),
    "installing": ("Replacing the program's files...", "Reemplazando los archivos del programa..."),
    "program_updated": ("{name} is now {latest}.", "{name} ya es la {latest}."),
    "program_only": ("The installed mod was left as it is (--program-only).",
                     "El mod instalado se ha dejado como estaba (--program-only)."),
    "rebuilding": ("Updating the installed mod...", "Actualizando el mod instalado..."),
    "mod_failed": ("The installed mod could not be updated (code {code}). Open {app} and install it again.",
                   "No se pudo actualizar el mod instalado (código {code}). Abre {app} e instálalo de nuevo."),
    "restart": ("Done. Restart the game in the emulator.", "Listo. Reinicia el juego en el emulador."),
    "press_enter": ("Press Enter to close this window.", "Pulsa Enter para cerrar esta ventana."),
    "failed": ("The update failed: {reason}", "La actualización ha fallado: {reason}"),
    "rate_limit": ("GitHub is limiting the requests from this connection. Try again in an hour.",
                   "GitHub está limitando las peticiones de esta conexión. Inténtalo de nuevo dentro de una hora."),
    "http_error": ("GitHub answered with error {code}.", "GitHub ha respondido con el error {code}."),
    "no_network": ("GitHub could not be reached ({reason}). Check your internet connection.",
                   "No se pudo llegar a GitHub ({reason}). Comprueba tu conexión a internet."),
    "bad_answer": ("GitHub's answer could not be understood.", "No se entiende la respuesta de GitHub."),
    "bad_tag": ("The published version {tag!r} is not a version number.",
                "La versión publicada {tag!r} no es un número de versión."),
    "no_asset": ("The release carries no Windows zip.", "La versión publicada no incluye el zip de Windows."),
    "many_assets": ("The release carries several Windows zips ({names}) and none is named {zip_name}.",
                    "La versión publicada tiene varios zips de Windows ({names}) y ninguno se llama {zip_name}."),
    "no_digest": ("The release does not say the zip's checksum, so it cannot be checked.",
                  "La versión publicada no indica la suma de control del zip, así que no se puede comprobar."),
    "bad_url": ("The zip is not on the repository's releases ({url}).",
                "El zip no está en las versiones del repositorio ({url})."),
    "bad_size": ("The download has {got} bytes, not the {expected} the release says.",
                 "La descarga tiene {got} bytes y no los {expected} que indica la versión."),
    "bad_hash": ("The download's checksum is not the release's. It was not used.",
                 "La suma de control de la descarga no es la de la versión. No se ha usado."),
    "bad_zip": ("The download is not a valid zip.", "La descarga no es un zip válido."),
    "unsafe_zip": ("The zip holds a path that leaves its folder ({path}). It was not used.",
                   "El zip tiene una ruta que sale de su carpeta ({path}). No se ha usado."),
    "wrong_zip": ("The zip is not a {name} program ({missing} is missing).",
                  "El zip no es un programa de {name} (falta {missing})."),
    "locked": ("The program's files are in use. Close {app} and anything using its folder, then run this again. "
               "Nothing was changed.",
               "Los archivos del programa están en uso. Cierra {app} y todo lo que use su carpeta, y ejecuta esto de "
               "nuevo. No se ha cambiado nada."),
    "disk": ("The files could not be written ({reason}). Nothing was changed.",
             "No se pudieron escribir los archivos ({reason}). No se ha cambiado nada."),
}


def message(key: str, language: str, **params) -> str:
    return MESSAGES[key][LANGUAGES.index(language) if language in LANGUAGES else 0].format(**params)


def language() -> str:
    """The language the GUI would open in: the one saved in its preferences, else the system's (Spanish for a Spanish
    system, English for any other). Never raises."""
    from core.gui.i18n import language_for_locales
    from core.gui.preferences import PREFERENCES_PATH
    try:
        saved = json.loads(PREFERENCES_PATH.read_text(encoding="utf-8")).get("language")
    except (OSError, ValueError, AttributeError):
        saved = None
    return saved if saved in LANGUAGES else language_for_locales(_system_locales())


def _system_locales() -> list[str]:
    tags: list[str] = []
    if sys.platform == "win32":
        try:
            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                tags.append(buffer.value)
        except (OSError, AttributeError):
            pass
    tags += [os.environ[name] for name in ("LC_ALL", "LC_MESSAGES", "LANG") if os.environ.get(name)]
    return tags


# ---- versions and the release ----------------------------------------------------------------------------------------

def parse_version(text: str) -> tuple[int, ...]:
    """"v0.1.2" or "0.1.2" as (0, 1, 2); ValueError for anything else."""
    found = re.fullmatch(r"v?(\d+(?:\.\d+)*)", str(text).strip())
    if not found:
        raise ValueError(f"not a version: {text!r}")
    numbers = [int(part) for part in found.group(1).split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:      # 1.2 and 1.2.0 are the same version
        numbers.pop()
    return tuple(numbers)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Release:
    tag: str
    assets: tuple[dict, ...]

    def asset(self, zip_name: str) -> Asset:
        """The release's Windows zip: the one named `zip_name`, else the only `*-windows.zip`."""
        zips = [a for a in self.assets if isinstance(a, dict) and isinstance(a.get("name"), str)]
        exact = [a for a in zips if a["name"] == zip_name]
        pick = exact or [a for a in zips if a["name"].endswith("-windows.zip")]
        if not pick:
            raise UpdateError("no_asset")
        if len(pick) > 1:
            raise UpdateError("many_assets", names=", ".join(a["name"] for a in pick), zip_name=zip_name)
        found = pick[0]
        digest = found.get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
            raise UpdateError("no_digest")
        url, size = found.get("browser_download_url"), found.get("size")
        if not isinstance(url, str) or not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise UpdateError("bad_answer")
        return Asset(found["name"], url, size, digest.split(":")[1].lower())


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """A download that starts on https never follows a redirect to anything else."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if req.full_url.startswith("https://") and not newurl.startswith("https://"):
            raise urllib.error.URLError(f"redirect to {newurl.split(':')[0]}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, product: Edition, accept: str | None = None):
    headers = {"User-Agent": product.name}
    if accept:
        headers["Accept"] = accept
    opener = urllib.request.build_opener(_HttpsOnly)
    try:
        return opener.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT)
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise UpdateError("rate_limit") from None
        raise UpdateError("http_error", code=error.code) from None
    except (urllib.error.URLError, OSError) as error:
        raise UpdateError("no_network", reason=getattr(error, "reason", error)) from None


def latest_release(product: Edition, api_base: str = API) -> Release | None:
    """The latest published release of `product.repository`, None when it has none (the API answers 404 to a
    repository without releases and to one that is not public)."""
    url = f"{api_base}/repos/{product.repository}/releases/latest"
    try:
        with _open(url, product, "application/vnd.github+json") as answer:
            data = json.loads(answer.read(MAX_JSON))
    except UpdateError as error:
        if error.key == "http_error" and error.params["code"] == 404:
            return None
        raise
    except (ValueError, OSError):
        raise UpdateError("bad_answer") from None
    tag, assets = data.get("tag_name") if isinstance(data, dict) else None, data.get("assets") \
        if isinstance(data, dict) else None
    if not isinstance(tag, str) or not isinstance(assets, list):
        raise UpdateError("bad_answer")
    try:
        parse_version(tag)
    except ValueError:
        raise UpdateError("bad_tag", tag=tag) from None
    return Release(tag, tuple(assets))


def require_github_asset(url: str, repository: str) -> None:
    """Refuse a download that is not https from the repository's own releases."""
    if not url.startswith(DOWNLOADS.format(repository=repository)):
        raise UpdateError("bad_url", url=url[:120])


# ---- the download and the zip --------------------------------------------------------------------------------------

def download(asset: Asset, product: Edition, destination: Path) -> None:
    """The asset into `destination`, checked against the release's size and SHA-256."""
    digest, got = hashlib.sha256(), 0
    with _open(asset.url, product) as answer, open(destination, "wb") as out:
        while True:
            try:
                chunk = answer.read(CHUNK)
            except OSError as error:
                raise UpdateError("no_network", reason=error) from None
            if not chunk:
                break
            got += len(chunk)
            if got > asset.size:
                raise UpdateError("bad_size", got=f">{asset.size}", expected=asset.size)
            digest.update(chunk)
            try:
                out.write(chunk)
            except OSError as error:
                raise UpdateError("disk", reason=error) from None
    if got != asset.size:
        raise UpdateError("bad_size", got=got, expected=asset.size)
    if digest.hexdigest() != asset.sha256:
        raise UpdateError("bad_hash")


def _parts(name: str) -> tuple[str, ...]:
    """A zip member's path as parts, ValueError when it can leave the folder it is extracted into."""
    text = name.replace("\\", "/")
    parts = tuple(part for part in text.split("/") if part)
    if text.startswith("/") or not parts or any(part in (".", "..") or ":" in part for part in parts):
        raise ValueError(name)
    return parts


def inspect_zip(archive: zipfile.ZipFile, product: Edition) -> dict[str, zipfile.ZipInfo]:
    """The zip's files by path below its top folder, after checking that it is a program of `product`: one top
    folder, no path leaving it, no link, <app>.exe, <cli>.exe and _internal/ inside."""
    files: dict[str, zipfile.ZipInfo] = {}
    tops = set()
    for info in archive.infolist():
        try:
            parts = _parts(info.filename)
        except ValueError:
            raise UpdateError("unsafe_zip", path=info.filename[:120]) from None
        if (info.external_attr >> 16) & 0o170000 == 0o120000:       # a symbolic link
            raise UpdateError("unsafe_zip", path=info.filename[:120])
        tops.add(parts[0])
        if info.is_dir() or len(parts) == 1:
            if len(parts) == 1 and not info.is_dir():
                raise UpdateError("wrong_zip", name=product.name, missing="folder")
            continue
        rel = "/".join(parts[1:])
        if rel in files:
            raise UpdateError("unsafe_zip", path=info.filename[:120])
        files[rel] = info
    if len(tops) != 1:
        raise UpdateError("wrong_zip", name=product.name, missing="folder")
    for needed in (f"{product.app_name}.exe", f"{product.cli_name}.exe"):
        if needed not in files:
            raise UpdateError("wrong_zip", name=product.name, missing=needed)
    if not any(rel.startswith(INTERNAL + "/") for rel in files):
        raise UpdateError("wrong_zip", name=product.name, missing=INTERNAL)
    return files


def program_names(product: Edition) -> list[str]:
    """What an update replaces, in the order it is moved: the folder first (the first to refuse when the program is
    open), then the programs, the notices and the updater."""
    return [INTERNAL, f"{product.app_name}.exe", f"{product.cli_name}.exe", *NOTICES, f"{product.updater_name}.exe"]


def extract(archive: zipfile.ZipFile, files: dict[str, zipfile.ZipInfo], product: Edition, staging: Path) -> list[str]:
    """The files an update replaces, from the checked zip into `staging`; returns the top-level names it holds."""
    wanted = set(program_names(product))
    base = staging.resolve()
    names = set()
    for rel, info in files.items():
        top = rel.split("/")[0]
        if top not in wanted:
            continue
        target = (staging / rel).resolve()
        if base not in target.parents:
            raise UpdateError("unsafe_zip", path=info.filename[:120])
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with archive.open(info) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out, CHUNK)
        except zipfile.BadZipFile:
            raise UpdateError("bad_zip") from None
        except OSError as error:
            raise UpdateError("disk", reason=error) from None
        if target.stat().st_size != info.file_size:
            raise UpdateError("bad_zip")
        names.add(top)
    return [name for name in program_names(product) if name in names]


# ---- putting it in place -------------------------------------------------------------------------------------------

def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def cleanup_leftovers(folder: Path, product: Edition) -> None:
    """Delete what an earlier update left (the replaced files, kept while they could not be deleted: the updater that
    was running, a program that was open) and a staging folder it did not finish with. Never raises."""
    for leftover in [*(folder / (name + OLD) for name in program_names(product)), folder / STAGING]:
        try:
            _remove(leftover)
        except OSError:
            pass


def _move(source: Path, target: Path) -> None:
    """`os.replace`, waiting out a passing hold: a virus scanner or the search indexer keeps newly written files open
    for a moment, and Windows then refuses to rename them or the folder they are in."""
    for attempt in range(MOVE_TRIES):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == MOVE_TRIES - 1:
                raise
            time.sleep(MOVE_WAIT)


def replace_files(folder: Path, staging: Path, names: list[str], app: str) -> None:
    """Move `staging/<name>` to `folder/<name>` for each name, the old file kept as `<name>.old` until all are in
    place. Any failure puts every old file back and raises UpdateError("locked"): nothing is half replaced."""
    kept: list[str] = []        # names whose old file now waits as .old
    placed: list[str] = []
    try:
        for name in names:
            old = folder / (name + OLD)
            _remove(old)
            if (folder / name).exists():
                _move(folder / name, old)
                kept.append(name)
        for name in names:
            _move(staging / name, folder / name)
            placed.append(name)
    except OSError:
        for name in reversed(placed):
            try:
                _remove(folder / name)
            except OSError:
                pass
        for name in reversed(kept):
            try:
                _move(folder / (name + OLD), folder / name)
            except OSError:
                pass
        raise UpdateError("locked", app=app) from None
    for name in kept:
        try:
            _remove(folder / (name + OLD))
        except OSError:
            pass            # the running updater, or a file still open: the next start deletes it


def update_program(product: Edition, folder: Path, current: str, say: Say, api_base: str = API,
                   asset_check: Callable[[str, str], None] | None = require_github_asset) -> str:
    """Bring the program in `folder` to the latest release: "none" (nothing published), "current" (it is not newer)
    or "updated". Raises UpdateError; whatever fails, the program is as it was."""
    if not (folder / f"{product.app_name}.exe").is_file():
        raise UpdateError("not_beside", app=product.app_name)
    cleanup_leftovers(folder, product)
    say("looking", name=product.name)
    release = latest_release(product, api_base)
    if release is None:
        say("no_release", name=product.name)
        return "none"
    if not is_newer(release.tag, current):
        say("up_to_date", name=product.name, current=current)
        return "current"
    asset = release.asset(product.zip_name)
    if asset_check:
        asset_check(asset.url, product.repository)
    staging = folder / STAGING
    try:
        staging.mkdir()
        archive_path = staging / "download.zip"
        say("downloading", name=product.name, latest=release.tag, megabytes=f"{asset.size / 1e6:.0f}")
        download(asset, product, archive_path)
        say("checking")
        try:
            with zipfile.ZipFile(archive_path) as archive:
                files = inspect_zip(archive, product)
                names = extract(archive, files, product, staging / "files")
        except zipfile.BadZipFile:
            raise UpdateError("bad_zip") from None
        archive_path.unlink()
        say("installing")
        replace_files(folder, staging / "files", names, product.app_name)
    except OSError as error:
        raise UpdateError("disk", reason=error) from None
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    say("program_updated", name=product.name, latest=release.tag)
    return "updated"


def _child_environment() -> dict[str, str]:
    """The environment of a program this one-file bundle starts: PyInstaller's bootloader then treats it as a program of
    its own, and the DLL folder it set for this process (which children inherit) is cleared."""
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    return {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}


def run_installed_update(product: Edition, folder: Path, say: Say) -> int:
    """The new command line rebuilds the installed mod; its own messages go to this console."""
    say("rebuilding")
    try:
        code = subprocess.run([str(folder / f"{product.cli_name}.exe"), "--update-installed"], cwd=folder,
                              env=_child_environment()).returncode
    except OSError as error:
        say("failed", reason=error)
        return 1
    if code:
        say("mod_failed", code=code, app=product.app_name)
    return code


def main(argv: list[str] | None = None, *, api_base: str = API, frozen: bool | None = None,
         executable: Path | None = None, product: Edition | None = None, current: str = __version__,
         ask: Callable[[str], str] = input, lang: str | None = None,
         asset_check: Callable[[str, str], None] | None = require_github_asset) -> int:
    """The updater's command line. The parameters are the tests': the program's own start passes none."""
    parser = argparse.ArgumentParser(description="Updates the program and the installed mod to the latest published "
                                                 "version.")
    parser.add_argument("--version", action="store_true", help="print the updater's version and exit (no network)")
    parser.add_argument("--check", action="store_true",
                        help="print the latest published version and whether it is newer; change nothing")
    parser.add_argument("--program-only", action="store_true", help="update the program, not the installed mod")
    args = parser.parse_args(argv)
    product = product or edition()
    lang = lang or language()

    def say(key: str, **params) -> None:
        print(message(key, lang, **params), flush=True)

    if args.version:
        say("version", updater=product.updater_name, version=current)
        return 0
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        say("only_windows")
        return 1
    folder = Path(executable or sys.executable).resolve().parent
    try:
        if args.check:
            release = latest_release(product, api_base)
            if release is None:
                say("no_release", name=product.name)
            else:
                say("latest", latest=release.tag, current=current,
                    verdict=message("is_newer" if is_newer(release.tag, current) else "not_newer", lang))
            return 0
        outcome = update_program(product, folder, current, say, api_base, asset_check)
        code = 0
        if args.program_only:
            if outcome == "updated":
                say("program_only")
        else:
            code = run_installed_update(product, folder, say)
    except UpdateError as error:
        say("failed", reason=message(error.key, lang, **error.params))
        code = 1
    else:
        if code == 0:
            say("restart")
    say("press_enter")
    try:
        ask("")
    except EOFError:
        pass
    return code

