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

makes `work/exe/dist/HeavenfallBeta/` (`HeavenfallBeta.exe`, `heavenfall-beta-cli.exe` and their files) and `work/exe/dist/HeavenfallBeta-windows.zip`,
then checks the finished folder. `--work DIR` builds elsewhere; `--no-zip` skips the zip.

## Publishing a release

Push a tag that starts with `v`:

```
git tag v0.1.0
git push origin v0.1.0
```

The workflow in `.github/workflows/release.yml` lints the code, builds `HeavenfallBeta-windows.zip` on Windows and attaches
it to the release of that tag (creating the release when there is none). Running the workflow by hand (Actions >
Release > Run workflow) only builds, and keeps the zip as an artifact of the run. Keep the version in
`pyproject.toml` and `core/__init__.py` equal to the tag.

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
| `docs/` | This documentation |
