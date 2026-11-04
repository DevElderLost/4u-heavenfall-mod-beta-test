"""Bringing the Windows program to the latest release of its own edition.

`tools/release/exe/heavenfall_update.py` is a console program beside the app: it asks GitHub for the edition's latest
release (`edition.json`: `repository`), downloads the zip, checks its size, its SHA-256 and its contents, replaces the
program's files and starts the new command line to rebuild the installed mod (`install/update_mod.py`).

Standard library only, and only the light modules of the package (the edition file, the saved language, the version):
the updater is a small program of its own with no Qt and no game data. Nothing here changes the URL it asks: the API's
address is a parameter only the tests change, and `main` accepts a download only from the repository's own releases.
Everything is imported before the update starts: a one-file program reads its modules from its own .exe, whose name
holds the new updater once the files are replaced.

An update cannot be left half done. What can be checked is checked before anything changes (another update running, the
program open, room on the disk, the download, the zip). The files go in by renames, with a journal written first: until
the journal is deleted, the commit point, every old file waits as `<name>.old`, and a failure, Ctrl+C or the new version
not starting puts them back; a power cut or a closed window is undone on the next start, before anything else.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import zipfile
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from core import __version__
from core.app.edition import Edition, edition, migrate_legacy_user_folder

try:
    import msvcrt
except ImportError:                 # the program is for Windows; the module's tests also run elsewhere
    msvcrt = None

API = "https://api.github.com"
DOWNLOADS = "https://github.com/{repository}/releases/download/"
TIMEOUT = 30                    # seconds without an answer
CHUNK = 1 << 20
MAX_JSON = 4 << 20              # the API's answer is a few KB
MOVE_TRIES, MOVE_WAIT = 120, 0.5    # a move Windows refuses: the tries, and the seconds between them
OPEN_TRIES = 8                  # the same for the check that the program is closed, before the download
FETCH_TRIES, RETRY_WAIT = 4, 2.0    # a request lost to the network or a server error: the tries, the seconds between
CHECK_SECONDS = 120             # how long the new programs may take to answer
SPACE_FACTOR = 4                # the room asked before the download, in times the zip's size (it and what it holds)
SPACE_MARGIN = 16 << 20         # kept free on the disk
MOD_REBUILT = 10                # the exit code of `<cli>.exe --update-installed` when a mod was rebuilt
OLD = ".old"                    # what a replaced file is called until the update ends (and after, while it is running)
ASIDE = ".discard"              # a file being taken back, until it can be deleted
STAGING = ".update_new"         # the new files, beside the program, until they are put in place
JOURNAL = ".update_journal.json"    # exists while the program's files are being replaced
LOCK = ".update_lock"           # held while an update runs
LOG = "update.log"              # in the edition's user folder: what the last update did
# Names Windows cannot write, whatever their extension
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
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
        self.detail = ""        # what the system answered, for the log


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
    "percent": ("  {percent} %", "  {percent} %"),
    "installing": ("Replacing the program's files. Windows may hold them for up to a minute...",
                   "Reemplazando los archivos del programa. Windows puede retenerlos hasta un minuto..."),
    "verifying": ("Checking that the new version starts...", "Comprobando que la versión nueva arranca..."),
    "recovered": ("The last update was cut short, so the previous version of {name} was put back. Run this again to "
                  "update.",
                  "La última actualización se cortó, así que se ha recuperado la versión anterior de {name}. Ejecuta "
                  "esto de nuevo para actualizar."),
    "program_updated": ("{name} is now {latest}.", "{name} ya es la {latest}."),
    "program_only": ("The installed mod was left as it is (--program-only).",
                     "El mod instalado se ha dejado como estaba (--program-only)."),
    "rebuilding": ("Updating the installed mod...", "Actualizando el mod instalado..."),
    "mod_failed": ("The installed mod could not be updated (code {code}). Run this again, or open {app} and press "
                   "Update.",
                   "No se pudo actualizar el mod instalado (código {code}). Ejecuta esto de nuevo, o abre {app} y "
                   "pulsa Actualizar."),
    "restart": ("Done. Restart the game in the emulator.", "Listo. Reinicia el juego en el emulador."),
    "all_current": ("Everything is up to date.", "Todo está al día."),
    "stopped": ("The update was stopped. Nothing was changed.",
                "Se ha parado la actualización. No se ha cambiado nada."),
    "unexpected": ("Something unexpected went wrong. Run this again; if it happens again, please send this file: {log}",
                   "Ha pasado algo inesperado. Ejecuta esto de nuevo; si vuelve a pasar, envía este archivo: {log}"),
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
    "no_space": ("There is not enough room on the disk: {megabytes} MB are needed. Nothing was changed.",
                 "No hay espacio suficiente en el disco: hacen falta {megabytes} MB. No se ha cambiado nada."),
    "already_running": ("Another update is already running.", "Ya hay otra actualización en marcha."),
    "new_broken": ("The new version does not start on this PC ({what}). The previous one was put back.",
                   "La versión nueva no arranca en este PC ({what}). Se ha recuperado la anterior."),
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


def _open(url: str, product: Edition, accept: str | None = None, offset: int = 0):
    headers = {"User-Agent": product.name}
    if accept:
        headers["Accept"] = accept
    if offset:
        headers["Range"] = f"bytes={offset}-"
    opener = urllib.request.build_opener(_HttpsOnly)
    try:
        return opener.open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT)
    except urllib.error.HTTPError as error:
        if error.code in (403, 429):
            raise UpdateError("rate_limit") from None
        raise UpdateError("http_error", code=error.code) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException) as error:
        raise UpdateError("no_network", reason=getattr(error, "reason", error)) from None


def _passing(error: UpdateError) -> bool:
    """A problem the next try may not have: the network, or a server error."""
    return error.key == "no_network" or (error.key == "http_error" and error.params["code"] >= 500)


def latest_release(product: Edition, api_base: str = API) -> Release | None:
    """The latest published release of `product.repository`, None when it has none (the API answers 404 to a
    repository without releases and to one that is not public)."""
    url = f"{api_base}/repos/{product.repository}/releases/latest"
    for attempt in range(FETCH_TRIES):
        try:
            with _open(url, product, "application/vnd.github+json") as answer:
                data = json.loads(answer.read(MAX_JSON))
            break
        except UpdateError as error:
            if error.key == "http_error" and error.params["code"] == 404:
                return None
            if attempt == FETCH_TRIES - 1 or not _passing(error):
                raise
        except ValueError:
            raise UpdateError("bad_answer") from None
        except (OSError, http.client.HTTPException) as error:
            if attempt == FETCH_TRIES - 1:
                raise UpdateError("no_network", reason=error) from None
        time.sleep(RETRY_WAIT)
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

def download(asset: Asset, product: Edition, destination: Path, progress: Callable[[int], None] | None = None) -> None:
    """The asset into `destination`, checked against the release's size and SHA-256. A cut connection goes on where it
    stopped, a server error is asked again and wrong bytes are fetched from the start, up to FETCH_TRIES in all."""
    digest, got = hashlib.sha256(), 0
    with open(destination, "wb") as out:

        def start_again():
            nonlocal digest, got
            digest, got = hashlib.sha256(), 0
            out.seek(0)
            out.truncate()

        for attempt in range(FETCH_TRIES):
            try:
                with _open(asset.url, product, offset=got) as answer:
                    if got and answer.status != 206:        # the server does not resume: this answer is the whole file
                        start_again()
                    length, arrived = answer.headers.get("Content-Length"), 0
                    while True:
                        try:
                            chunk = answer.read(CHUNK)
                        except (OSError, http.client.HTTPException) as error:
                            raise UpdateError("no_network", reason=error) from None
                        if not chunk:
                            break
                        got += len(chunk)
                        arrived += len(chunk)
                        if got > asset.size:
                            raise UpdateError("bad_size", got=f">{asset.size}", expected=asset.size)
                        digest.update(chunk)
                        try:
                            out.write(chunk)
                        except OSError as error:
                            raise UpdateError("disk", reason=error) from None
                        if progress:
                            progress(got)
                if got < asset.size:
                    if length is not None and arrived == int(length):       # all it had: the release says otherwise
                        raise UpdateError("bad_size", got=got, expected=asset.size)
                    raise UpdateError("no_network", reason="the connection was cut")
                if digest.hexdigest() != asset.sha256:
                    raise UpdateError("bad_hash")
                return
            except UpdateError as error:
                if attempt == FETCH_TRIES - 1 or not (_passing(error) or error.key in ("bad_size", "bad_hash")):
                    raise
                if error.key in ("bad_size", "bad_hash"):
                    start_again()
            time.sleep(RETRY_WAIT)


def _parts(name: str) -> tuple[str, ...]:
    """A zip member's path as parts, ValueError when it can leave the folder it is extracted into."""
    text = name.replace("\\", "/")
    parts = tuple(part for part in text.split("/") if part)
    if text.startswith("/") or not parts or any(part in (".", "..") or ":" in part for part in parts):
        raise ValueError(name)
    for part in parts:      # what Windows cannot write, which would fail the update while it unpacks
        if part != part.rstrip(". ") or re.search(r'[<>"|?*\x00-\x1f]', part) or \
                part.split(".")[0].upper() in RESERVED:
            raise ValueError(name)
    return parts


def inspect_zip(archive: zipfile.ZipFile, product: Edition) -> dict[str, zipfile.ZipInfo]:
    """The zip's files by path below its top folder, after checking that it is a program of `product`: one top
    folder, no path leaving it, no link, <app>.exe, <cli>.exe and _internal/ inside."""
    files: dict[str, zipfile.ZipInfo] = {}
    tops, folded = set(), set()
    for info in archive.infolist():
        try:
            parts = _parts(info.filename)
        except ValueError:
            raise UpdateError("unsafe_zip", path=info.filename[:120]) from None
        if (info.external_attr >> 16) & 0o170000 == 0o120000:       # a symbolic link
            raise UpdateError("unsafe_zip", path=info.filename[:120])
        if info.flag_bits & 1:                                      # encrypted: it could not be read
            raise UpdateError("bad_zip")
        tops.add(parts[0])
        if info.is_dir() or len(parts) == 1:
            if len(parts) == 1 and not info.is_dir():
                raise UpdateError("wrong_zip", name=product.name, missing="folder")
            continue
        rel = "/".join(parts[1:])
        if rel.casefold() in folded:                                # one file on Windows
            raise UpdateError("unsafe_zip", path=info.filename[:120])
        folded.add(rel.casefold())
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
                out.flush()
                os.fsync(out.fileno())      # on the disk before the renames can be: a power cut leaves no empty file
        except (zipfile.BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error):
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
    leftovers = [folder / (name + suffix) for name in program_names(product) for suffix in (OLD, ASIDE)]
    for leftover in [*leftovers, folder / STAGING]:
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


def placement_moves(folder: Path, staging: Path, names: list[str]) -> list[tuple[Path, Path]]:
    """The renames that put `names` in place, in their order: every old file to `<name>.old`, then every new one in."""
    return [*((folder / name, folder / (name + OLD)) for name in names if (folder / name).exists()),
            *((staging / name, folder / name) for name in names)]


def write_journal(folder: Path, names: list[str]) -> None:
    """Note what is about to be replaced, and what of it exists, on the disk before the first rename."""
    temp = folder / (JOURNAL + ".tmp")
    with open(temp, "w", encoding="utf-8") as out:
        json.dump({"names": names, "existed": [name for name in names if (folder / name).exists()]}, out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temp, folder / JOURNAL)


def _set_aside(path: Path) -> None:
    """Take `path` out of the way and delete it if it can be: the running updater cannot be, until the next start."""
    aside = path.with_name(path.name + ASIDE)
    _remove(aside)
    _move(path, aside)
    with contextlib.suppress(OSError):
        _remove(aside)


def _undo(folder: Path, names: list[str], existed: list[str]) -> None:
    """Put the old program back: every `<name>.old` over what took its place, and a file it did not have goes."""
    for name in reversed(names):
        current, old = folder / name, folder / (name + OLD)
        if old.exists():
            if current.exists():
                _set_aside(current)
            _move(old, current)
        elif name not in existed and current.exists():
            _set_aside(current)


def recover(folder: Path, product: Edition, say: Say) -> bool:
    """Undo an update that was cut short (its journal is still there). Only the program's own names are ever touched."""
    path = folder / JOURNAL
    if not path.exists():
        return False
    known = program_names(product)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = [name for name in data["names"] if name in known]
        existed = [name for name in data["existed"] if name in known]
    except (OSError, ValueError, KeyError, TypeError):
        names, existed = known, known       # nothing is taken for a new file, only what has an old copy is put back
    try:
        _undo(folder, names, existed)
        path.unlink()
    except OSError:
        raise UpdateError("locked", app=product.app_name) from None
    say("recovered", name=product.name)
    return True


@contextlib.contextmanager
def _uninterrupted() -> Iterator[None]:
    """Ctrl+C waits for these few renames."""
    try:
        previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    except ValueError:      # not the main thread
        previous = None
    try:
        yield
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def replace_files(folder: Path, staging: Path, names: list[str], app: str, check: Callable[[], None] | None = None
                  ) -> None:
    """Move `staging/<name>` to `folder/<name>` for each name, the old file kept as `<name>.old` until all are in place
    and `check` has passed. Deleting the journal is the commit point. Any failure, or Ctrl+C, puts every old file back:
    an OSError raises UpdateError("locked"), anything else goes on up. An undo that fails too keeps the journal, and the
    next start tries again."""
    for name in names:
        _remove(folder / (name + OLD))
    existed = [name for name in names if (folder / name).exists()]
    moves = placement_moves(folder, staging, names)
    write_journal(folder, names)
    try:
        with _uninterrupted():
            for source, target in moves:
                _move(source, target)
        if check:
            check()
    except BaseException as error:
        with _uninterrupted(), contextlib.suppress(OSError):
            _undo(folder, names, existed)
            (folder / JOURNAL).unlink()
        if isinstance(error, OSError):
            locked = UpdateError("locked", app=app)
            locked.detail = f"{type(error).__name__}: {error}"
            raise locked from None
        raise
    (folder / JOURNAL).unlink()
    for name in existed:
        with contextlib.suppress(OSError):      # the running updater, or a file still open: the next start deletes it
            _remove(folder / (name + OLD))


@contextlib.contextmanager
def update_lock(folder: Path) -> Iterator[None]:
    """Only one update at a time in `folder`; Windows drops the lock when the process ends, however it ends."""
    if msvcrt is None:
        yield
        return
    path = folder / LOCK
    try:
        handle = open(path, "a+b")
    except OSError as error:
        raise UpdateError("disk", reason=error) from None
    try:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise UpdateError("already_running") from None
        try:
            yield
        finally:
            with contextlib.suppress(OSError):
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()
        with contextlib.suppress(OSError):
            path.unlink()


def _require_closed(folder: Path, product: Edition) -> None:
    """Refuse before the download when the program is open: Windows lets no one open a running .exe for writing."""
    for name in (f"{product.app_name}.exe", f"{product.cli_name}.exe"):
        for attempt in range(OPEN_TRIES):
            try:
                with open(folder / name, "r+b"):
                    break
            except FileNotFoundError:
                break
            except OSError:
                if attempt == OPEN_TRIES - 1:
                    raise UpdateError("locked", app=product.app_name) from None
                time.sleep(MOVE_WAIT)


def _require_space(folder: Path, needed: int) -> None:
    if shutil.disk_usage(folder).free < needed + SPACE_MARGIN:
        raise UpdateError("no_space", megabytes=f"{(needed + SPACE_MARGIN) / 1e6:.0f}")


def check_new_program(folder: Path, product: Edition, tag: str, names: list[str]) -> None:
    """The new programs start on this PC: the command line answers --help (it loads the bundle the app uses) and the new
    updater says the release's version, unless the zip carried none."""
    def answer(name: str, flag: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([str(folder / name), flag], cwd=folder, env=_child_environment(),
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                                  timeout=CHECK_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            raise UpdateError("new_broken", what=f"{name}: {error}") from None

    cli = f"{product.cli_name}.exe"
    done = answer(cli, "--help")
    if done.returncode:
        raise UpdateError("new_broken", what=f"{cli}: {done.returncode}")
    updater = f"{product.updater_name}.exe"
    if updater in names:
        done = answer(updater, "--version")
        words = done.stdout.split()
        try:
            same = not done.returncode and parse_version(words[-1]) == parse_version(tag)
        except (IndexError, ValueError):
            same = False
        if not same:
            raise UpdateError("new_broken", what=f"{updater}: {done.stdout.strip()[:80]}")


def _tenths(size: int, say: Say) -> Callable[[int], None]:
    """A download's progress: a line each time another tenth has arrived."""
    last = [0]

    def progress(got: int) -> None:
        tenth = got * 10 // size if size else 10
        if tenth > last[0]:
            last[0] = tenth
            say("percent", percent=tenth * 10)

    return progress


def update_program(product: Edition, folder: Path, current: str, say: Say, api_base: str = API,
                   asset_check: Callable[[str, str], None] | None = require_github_asset,
                   check: Callable[[Path, Edition, str, list[str]], None] | None = check_new_program) -> str:
    """Bring the program in `folder` to the latest release: "none" (nothing published), "current" (it is not newer),
    "updated", or "recovered": an update cut short was undone and nothing else was done, because this updater may be the
    new one, whose version says nothing of the old program it put back. Raises UpdateError; whatever fails, the program
    is as it was."""
    app = folder / f"{product.app_name}.exe"
    if not (app.is_file() or (folder / JOURNAL).exists()):
        raise UpdateError("not_beside", app=product.app_name)
    with update_lock(folder):
        if recover(folder, product, say):
            cleanup_leftovers(folder, product)
            return "recovered"
        if not app.is_file():
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
        _require_closed(folder, product)
        _require_space(folder, asset.size * SPACE_FACTOR)
        staging = folder / STAGING

        def checked(names: list[str]) -> Callable[[], None] | None:
            if not check:
                return None

            def run() -> None:
                say("verifying")
                check(folder, product, release.tag, names)

            return run

        try:
            staging.mkdir()
            archive_path = staging / "download.zip"
            say("downloading", name=product.name, latest=release.tag, megabytes=f"{asset.size / 1e6:.0f}")
            download(asset, product, archive_path, _tenths(asset.size, say))
            say("checking")
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    files = inspect_zip(archive, product)
                    _require_space(folder, sum(info.file_size for info in files.values()))
                    names = extract(archive, files, product, staging / "files")
            except zipfile.BadZipFile:
                raise UpdateError("bad_zip") from None
            archive_path.unlink()
            say("installing")
            replace_files(folder, staging / "files", names, product.app_name, checked(names))
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
    if code not in (0, MOD_REBUILT):
        say("mod_failed", code=code, app=product.app_name)
    return code


def _start_log(path: Path | None, product: Edition) -> None:
    """The file that keeps what this update did, for a player reporting a problem. Never raises."""
    if path is None:
        return
    with contextlib.suppress(OSError):
        migrate_legacy_user_folder(current=product)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def _to_log(path: Path | None, text: str) -> None:
    if path is None:
        return
    with contextlib.suppress(OSError):
        with open(path, "a", encoding="utf-8") as out:
            out.write(text + "\n")


def main(argv: list[str] | None = None, *, api_base: str = API, frozen: bool | None = None,
         executable: Path | None = None, product: Edition | None = None, current: str = __version__,
         ask: Callable[[str], str] = input, lang: str | None = None,
         asset_check: Callable[[str, str], None] | None = require_github_asset,
         check: Callable[[Path, Edition, str, list[str]], None] | None = check_new_program,
         log: Path | bool = True) -> int:
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
    log_path = product.home / LOG if log is True else (log or None)
    with contextlib.suppress(AttributeError, ValueError):      # a console that cannot show a letter stops nothing
        sys.stdout.reconfigure(errors="replace")

    def say(key: str, **params) -> None:
        text = message(key, lang, **params)
        print(text, flush=True)
        _to_log(log_path, text)

    if args.version:
        print(message("version", lang, updater=product.updater_name, version=current), flush=True)
        return 0
    if not (getattr(sys, "frozen", False) if frozen is None else frozen):
        print(message("only_windows", lang), flush=True)
        return 1
    folder = Path(executable or sys.executable).resolve().parent
    code = 0
    try:
        if args.check:
            release = latest_release(product, api_base)
            if release is None:
                print(message("no_release", lang, name=product.name), flush=True)
            else:
                print(message("latest", lang, latest=release.tag, current=current,
                              verdict=message("is_newer" if is_newer(release.tag, current) else "not_newer", lang)),
                      flush=True)
            return 0
        _start_log(log_path, product)
        outcome = update_program(product, folder, current, say, api_base, asset_check, check)
        rebuilt = False
        if outcome == "recovered":
            pass
        elif args.program_only:
            if outcome == "updated":
                say("program_only")
        else:
            result = run_installed_update(product, folder, say)
            rebuilt = result == MOD_REBUILT
            code = 0 if rebuilt else result
    except UpdateError as error:
        if error.detail:
            _to_log(log_path, error.detail)
        say("failed", reason=message(error.key, lang, **error.params))
        code = 1
    except KeyboardInterrupt:
        say("stopped")
        code = 1
    except Exception:
        _to_log(log_path, traceback.format_exc())
        say("unexpected", log=log_path or "-")
        code = 1
    else:
        if code == 0 and outcome != "recovered":
            say("restart" if outcome == "updated" or rebuilt else "all_current")
    say("press_enter")
    try:
        ask("")
    except (EOFError, KeyboardInterrupt):
        pass
    return code
