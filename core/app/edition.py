"""Which product this checkout builds: the full mod, or an edition made from it
(editions/<name>/, tools/release/export_edition.py), whose overlay replaces game/data/curated/edition.json. The GUI, the
installer, the developer tools and the Windows build take their names and choices from here, and so do the old names
that players' disks may still hold."""

import json
import os
import shutil
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from core.game.data.paths import CURATED_DIR

EDITION_FILE = CURATED_DIR / "edition.json"
ANDROID_APP_FILE = CURATED_DIR / "android_app.json"     # the Android app's own data, apart from every edition
PAGES = ("install", "options", "randomizer", "saves", "debug")   # the GUI's pages an edition may have (gui/qt/app.py)
PLATFORMS = ("emulator", "console")             # "console": a real 3DS (luma.py)
TOOLS_LANGUAGES = ("es", "en")


REGIONS = ("eur", "usa")                        # the base games a console title is made from (titles.py)
APPLICATION = "00040000"                        # a title id's high word for a 3DS application


@dataclass(frozen=True)
class ConsoleTitle:
    """The mod as an installed title on a real 3DS: its own title id for each region's game, and
    its names on the HOME Menu."""
    title_ids: tuple[tuple[str, str], ...]      # (region, 16 lowercase hex digits), one per REGIONS
    short_name: str
    long_name: str
    publisher: str

    def title_id(self, region: str) -> str:
        return dict(self.title_ids)[region]


def _console_title(values: dict | None, path: Path) -> ConsoleTitle | None:
    """`values` (edition.json's console_title) checked: an application's id for each region, unique id per region,
    variation 0 (only demos and Download Play children use one). That none is a game's own is checked where the
    title is built (install/title/build_title.py): the updater loads this module and must stay light."""
    if values is None:
        return None
    ids = {region: str(title).lower() for region, title in values["title_ids"].items()}
    bad = [title for title in ids.values()
           if len(title) != 16 or any(c not in "0123456789abcdef" for c in title) or not title.startswith(APPLICATION)
           or not title.endswith("00")]
    if sorted(ids) != sorted(REGIONS) or bad or len(set(ids.values())) != len(ids):
        raise ValueError(f"{path}: bad console_title title_ids ({', '.join(bad) or 'one a region'})")
    return ConsoleTitle(tuple((region, ids[region]) for region in REGIONS), values["short_name"],
                        values["long_name"], values["publisher"])


@dataclass(frozen=True)
class ConsoleRelease:
    """The files of the edition's GitHub release that the 3DS app reads:
    the app as a CIA and as a .3dsx, and the patch set of each region, without MH XX and with it (the app takes the XX
    set when the player's MH XX dump is on the card; "MH XX on the console"). The titles' ids are console_title's."""
    app_cia: str
    app_3dsx: str
    patch_eur: str
    patch_usa: str
    patch_eur_xx: str
    patch_usa_xx: str

    def patch(self, region: str, xx: bool = False) -> str:
        key = f"patch_{region}{'_xx' if xx else ''}"
        if region not in ("eur", "usa"):
            raise KeyError(region)
        return getattr(self, key)

    @property
    def release_file(self) -> str:
        """The release's own copy of its releases/latest answer, which the app reads when the GitHub API gives none
        (tools/release/console_release_file.py writes it; the app's hf_edition_release_file names it the same)."""
        return self.app_cia.removesuffix(".cia") + "-release.json"

    @property
    def shared_file(self) -> str:
        """The release's shared file, the files every patch set copies the same bytes from (the release workflow makes
        it: tools/release/console_sets.py; the app's table names it asset_shared). Spelled here as
        core/install/title/shared_file.py's shared_name spells it (the updater, which reads this file, carries no
        module of the title's)."""
        return self.app_cia.removesuffix(".cia") + "-shared.hfpack"

    def patches(self) -> tuple[str, ...]:
        """Every patch set's name: plain and with MH XX, each region."""
        return tuple(self.patch(region, xx) for xx in (False, True) for region in ("eur", "usa"))


_RELEASE_KEYS = ("app_cia", "app_3dsx", "patch_eur", "patch_usa", "patch_eur_xx", "patch_usa_xx")


def _console_release(values: dict | None, path: Path) -> ConsoleRelease | None:
    if values is None:
        return None
    names = [values.get(key) for key in _RELEASE_KEYS]
    if set(values) != set(_RELEASE_KEYS) or len(set(names)) != len(_RELEASE_KEYS) or not all(
            isinstance(n, str) and n and "/" not in n for n in names):
        raise ValueError(f"{path}: bad console_release (exactly {', '.join(_RELEASE_KEYS)}: "
                         f"{len(_RELEASE_KEYS)} different file names)")
    return ConsoleRelease(*names)


@dataclass(frozen=True)
class AndroidRelease:
    """The files of the edition's GitHub release that Heavenfall for Android reads: the patch set of the American game
    without MH XX and with it, the release's own copy of its
    releases/latest answer, and the titles of the game and of its update (the set's executable and exheader come from
    the update). The release's shared file is the console release's. `public`: the edition's repository can be read by
    the app, so the app's editions table lists it."""
    patch_usa: str
    patch_usa_xx: str
    release_file: str
    game_title: str
    update_title: str
    public: bool

    def patch(self, xx: bool = False) -> str:
        return self.patch_usa_xx if xx else self.patch_usa

    def patches(self) -> tuple[str, ...]:
        """Every patch set's name: plain, then with MH XX."""
        return (self.patch_usa, self.patch_usa_xx)


_ANDROID_KEYS = ("patch_usa", "patch_usa_xx", "release_file", "game_title", "update_title", "public")
UPDATE_APPLICATION = "0004000E"                 # a title id's high word for an application's update


def _hex_title(value: object) -> bool:
    return isinstance(value, str) and len(value) == 16 and all(c in "0123456789abcdefABCDEF" for c in value)


def _android_release(values: dict | None, path: Path) -> AndroidRelease | None:
    if values is None:
        return None
    names = [values.get(key) for key in _ANDROID_KEYS[:3]]
    game, update = values.get("game_title"), values.get("update_title")
    if set(values) != set(_ANDROID_KEYS) or len(set(names)) != len(names) or not all(
            isinstance(n, str) and n and "/" not in n for n in names) or not isinstance(values["public"], bool):
        raise ValueError(f"{path}: bad android_release (exactly {', '.join(_ANDROID_KEYS)}: three different file "
                         "names and a true or false public)")
    if not (_hex_title(game) and _hex_title(update) and game.startswith(APPLICATION)
            and update.upper() == UPDATE_APPLICATION + game[8:].upper()):
        raise ValueError(f"{path}: bad android_release titles (the game's, 00040000..., and its update's, "
                         "0004000E... with the same low word)")
    return AndroidRelease(*names, game, update, values["public"])


@dataclass(frozen=True)
class AndroidApp:
    """The app itself: its repository and the files of its GitHub release that it
    updates itself from."""
    repository: str
    apk: str
    release_file: str


def load_android_app(path: Path = ANDROID_APP_FILE) -> AndroidApp:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    values.pop("description", None)
    if set(values) != {"repository", "apk", "release_file"} or not all(
            isinstance(v, str) and v for v in values.values()) or values["repository"].count("/") != 1 or any(
            "/" in values[key] for key in ("apk", "release_file")) or values["apk"] == values["release_file"]:
        raise ValueError(f"{path}: bad android app (exactly repository 'owner/name', apk and release_file: two "
                         "different file names)")
    return AndroidApp(**values)


@dataclass(frozen=True)
class Edition:
    name: str                   # the product in the GUI's sentences ("<name> installed.")
    window_title: str
    app_name: str               # the Windows program, <app_name>.exe (tools/release/build_exe.py)
    cli_name: str               # its command line, <cli_name>.exe
    zip_name: str               # what a GitHub release carries
    app_user_model_id: str      # Windows groups the taskbar button by it
    pages: tuple[str, ...]      # of PAGES, in the sidebar's order
    platforms: tuple[str, ...]  # of PLATFORMS; with one the sidebar shows no switch
    tools_language: str         # the developer tools' texts (the recorder, tools/ui/ui.py), of TOOLS_LANGUAGES
    user_folder: str            # under the home folder: the GUI's preferences, its log and the builds
    marker: str                 # the file that marks our mod in a mod folder (install/deploy.py)
    repository: str             # "<owner>/<name>" on GitHub: where its releases are published (install/self_update.py)
    updater_name: str           # the updater beside the program, <updater_name>.exe (tools/release/exe/)
    # The names this product used before, which players' disks may still hold (empty for an edition that never had any)
    legacy_user_folders: tuple[str, ...] = ()       # copied into user_folder once (migrate_legacy_user_folder)
    legacy_markers: tuple[str, ...] = ()            # a mod folder marked with one is still ours (install/deploy.py)
    legacy_build_markers: tuple[str, ...] = ()      # so do build folders (install/build.py)
    xx_optional: bool = False   # MH XX is never required; the Install page offers its file (state.offers_xx)
    new_maps: bool = False      # the product builds the maps ported from XX whenever XX's file is given
    own_save: bool = False      # the game plays on Heavenfall's own save; the program brings hunters in
    console_title: ConsoleTitle | None = None       # required with the "console" platform
    console_release: ConsoleRelease | None = None   # the release files the 3DS app downloads (launcher)
    android_release: AndroidRelease | None = None   # the ones Heavenfall for Android downloads (with console_release)

    @property
    def xx_offered(self) -> bool:
        """The edition's run uses MH XX's file whenever one is given, whatever the player's options."""
        return self.xx_optional or self.new_maps

    @property
    def home(self) -> Path:
        return Path.home() / self.user_folder

    @property
    def marker_names(self) -> tuple[str, ...]:
        """The marker, then the old ones: the first that exists in a mod folder describes it."""
        return (self.marker, *self.legacy_markers)


def load_edition(path: Path = EDITION_FILE) -> Edition:
    values = json.loads(Path(path).read_text(encoding="utf-8"))
    values.pop("description", None)
    lists = {key: tuple(values[key]) for key in ("pages", "platforms", "legacy_user_folders", "legacy_markers",
                                                  "legacy_build_markers") if key in values}
    console = _console_title(values.pop("console_title", None), path)
    release = _console_release(values.pop("console_release", None), path)
    android = _android_release(values.pop("android_release", None), path)
    edition = Edition(**{**values, **lists}, console_title=console, console_release=release, android_release=android)
    unknown = [key for key in edition.pages if key not in PAGES] + \
        [key for key in edition.platforms if key not in PLATFORMS]
    if unknown or not edition.pages or not edition.platforms or edition.tools_language not in TOOLS_LANGUAGES:
        raise ValueError(f"{path}: bad pages, platforms or tools_language ({', '.join(unknown) or 'empty'})")
    if "console" in edition.platforms and console is None:
        raise ValueError(f"{path}: the console platform needs console_title")
    if release is not None and console is None:
        raise ValueError(f"{path}: console_release needs console_title (the titles the launcher installs)")
    if android is not None:
        if release is None:
            raise ValueError(f"{path}: android_release needs console_release (its shared file is the release's)")
        taken = {*release.patches(), release.release_file, release.shared_file, release.app_cia, release.app_3dsx}
        if taken & {*android.patches(), android.release_file}:
            raise ValueError(f"{path}: android_release names a file console_release names (one release holds both)")
    return edition


@cache
def edition() -> Edition:
    """This checkout's edition (game/data/curated/edition.json)."""
    return load_edition()


def migrate_legacy_user_folder(home: Path | None = None, current: Edition | None = None) -> Path | None:
    """Copy the first old preferences folder (`legacy_user_folders`) that exists into the edition's own
    `user_folder`, once: only while the new folder does not exist, and the old one stays. Returns the folder copied,
    None when nothing was done. The copy is made beside the new folder and renamed into place, so a copy that stops
    (a full disk) leaves no new folder to hide the next try; it never raises."""
    current = current or edition()
    home = Path.home() if home is None else Path(home)
    new = home / current.user_folder
    if new.exists():
        return None
    for name in current.legacy_user_folders:
        old = home / name
        if not old.is_dir():
            continue
        partial = home / (current.user_folder + ".copying")
        try:
            shutil.rmtree(partial, ignore_errors=True)
            shutil.copytree(old, partial)
            os.replace(partial, new)
        except OSError:
            shutil.rmtree(partial, ignore_errors=True)
            return None
        return old
    return None
