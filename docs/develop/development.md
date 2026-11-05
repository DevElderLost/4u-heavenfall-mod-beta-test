# Development

How to run Heavenfall Beta from its code, build the Windows program and publish a release. What the code does is in
[how_it_works.md](how_it_works.md); moving the interface is in [editing_the_ui.md](editing_the_ui.md).

## Running from the code

You need Python 3.10 or newer (the pinned packages are tested on 3.13).

```
pip install -r requirements.txt
python -m core.gui                                   # the program
python -m core --rom GAME --out FOLDER               # the same build without a window; --help lists the options
```

The command line builds a mod folder: copy what is inside it into the emulator's `load/mods/<title>/`
(`0004000000126100` for the European game, `0004000000126300` for the American one). The program does that for you,
and only ever touches a mod folder it installed (or asks first).

The program keeps your choices in `~/.heavenfall_beta/gui.json` and builds in `~/.heavenfall_beta/build/`.

## `local.ini`

Only the interface tools need it (`tools/ui/ui.py`, `tools/ui/ui_recorder.py`, `tools/ui/ui_probe.py`). Copy
`local.example.ini` to `local.ini` and fill in your game file, the emulator's RomFS dump and, if needed, the
emulator's folder. `local.ini` is never committed (`.gitignore`). Recordings, pictures and probes go to `work/` and
`output/`, both ignored too.

## Checking the code

```
python -m ruff check .
```

The release workflow runs it as well.

## Building the Windows program

```
pip install -r requirements.txt -r requirements-build.txt
python tools/release/build_exe.py
```

makes `work/exe/dist/HeavenfallBeta/` (`HeavenfallBeta.exe`, `heavenfall-beta-cli.exe`, `HeavenfallBeta-update.exe` and their files) and `work/exe/dist/HeavenfallBeta-windows.zip`,
then checks the finished folder. `--work DIR` builds elsewhere; `--no-zip` skips the zip.

## Publishing a release

Push a tag that starts with `v`:

```
git tag v0.1.3
git push origin v0.1.3
```

The workflow in `.github/workflows/release.yml` lints the code, builds `HeavenfallBeta-windows.zip` on Windows and attaches
it to the release of that tag (creating the release when there is none). Running the workflow by hand (Actions >
Release > Run workflow) only builds, and keeps the zip as an artifact of the run. Keep the version in
`pyproject.toml` and `core/__init__.py` equal to the tag.

## The updater

`HeavenfallBeta-update.exe` sits beside the program in the zip. Opening it asks this repository's latest release
(`repository` in `core/game/data/curated/edition.json`); when it is newer than the program it downloads the zip, checks
its size and SHA-256 against the ones GitHub lists, replaces the program's files (all or none: a program that is open is
left as it is, with a message) and rebuilds the mod installed in each emulator folder with the options it was installed
with (`heavenfall-beta-cli.exe --update-installed`). `--check` only prints the latest published version, `--program-only`
leaves the installed mod alone, `--version` prints its own. A folder that holds no Beta mod is never touched. The code is
`core/install/self_update.py` (standard library only) and `core/install/update_mod.py`.
A release therefore needs: a tag equal to the version in `core/__init__.py`, and the zip built by the workflow attached to it.

## The web page

The same build runs in the player's browser, for devices that cannot run the program (Android, Steam Deck). It is a
static site: no server does any work, and the game file never leaves the device.

```
python tools/release/build_web.py                 # write the site into work/web/site
python tools/release/build_web.py --serve         # ... and serve it on your network, to try it on a phone
python tools/release/build_web.py --pin VERSION   # move to another Pyodide version
```

The tool needs only the standard library. What runs where:

| File | What it does |
|---|---|
| `web/index.html`, `page.js`, `style.css` | The page: its texts in both languages, the options, the install steps |
| `web/worker.js` | Runs the engine outside the page, so the page keeps responding |
| `web/engine.js` | Starts Python (Pyodide), mounts the game so that only the pieces asked for are read, calls `core/app/web.py` |
| `web/pyodide.json` | The Pyodide version and the checksum of every file the site serves |
| `core/app/web.py` | What the page asks of Python: the options, the check of the game, the mod as a zip. The run is the program's own |
| `core/app/pipeline.py` and what it imports | The build: it must keep working without threads, subprocesses or native code other than `zstandard` |

The options come from the program's own list (`core/gui/options.py`), so a new option appears on the page by itself. One
the player also changes during play is listed as `in_game` in `core/game/data/curated/gui_presets.json`: it is a row of the
game's START menu too, and the build writes the value chosen into the mod, as what a character with no choice starts with.

The workflow in `.github/workflows/pages.yml` publishes the site on GitHub Pages for every tag, or by hand (Actions >
Web page > Run workflow). The repository's Settings > Pages > Source must be "GitHub Actions".

## The compiled code

The code added to the game is already compiled, in `core/game/executable/generated/code_space.json`: running or building
the program needs no compiler. The sources of every block (`.s` assembly, `.c` C) sit beside the Python that
patches them (`core/interface/single_screen/executable/`, `core/interface/hud/`, `core/interface/game_gui/`,
`core/cheats/`...), so you can read exactly what runs in the game.

Heavenfall Beta is a module of Heavenfall, a mod for Monster Hunter 4 Ultimate, so some names and comments mention
Heavenfall's other features (the randomizer, other monsters, the 3DS). `core` is the package's historical name.

## The layout of this repository

| Path | What it is |
|---|---|
| `core/` | The package: the program, the run, the patches, the interface tools' library, the data |
| `core/game/data/curated/` | Every decision as data: the interface arrangement (`game_gui/`), the defaults, sizes |
| `tools/ui/ui.py`, `ui_recorder.py`, `ui_probe.py` | The interface tools ([editing_the_ui.md](editing_the_ui.md)) |
| `tools/release/build_exe.py`, `heavenfall.spec`, `exe/` | The Windows build |
| `web/`, `tools/release/build_web.py` | The web page and its site |
| `docs/` | This documentation |
