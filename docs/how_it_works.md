# How Heavenfall Beta works

This page explains, for people who want to read or change the code, what Heavenfall Beta does to Monster Hunter 4 Ultimate
and how one press of **Install** becomes a mod in the emulator. Moving a menu yourself is in
[editing_the_ui.md](editing_the_ui.md); running and building the program is in [development.md](development.md).

## The short version

The 3DS has two screens. MH4U shows the hunt on the top one and puts many menus on the bottom (touch) one. An
emulator can show only the top screen ("Single Screen" layout), but then those menus are invisible. Heavenfall Beta builds a
**mod folder** that the emulator loads over the game: changed interface files (where each menu is drawn) and a
changed executable (small pieces of new code). The player's game file is only read, never written.

```
your game (.3ds/.cia/.zcci/.zcia)
   |  read: the executable (code.bin) and the interface files (RomFS)
   v
pipeline.run  -- interface files: smaller HUD, single-screen layouts -->  romfs/<lang>/data/*.arc
              -- executable patches, carried to your game version -->  exefs/code.bin, exheader.bin
   |
   v
install: copied into <emulator>/load/mods/<title>/   (0004000000126100 European, 0004000000126300 American)
```

## What the mod folder holds

* `romfs/<lang>/data/*.arc`: the game's archives that hold interface layouts, with some layouts changed. A **layout**
  (`.lyt` inside the archive) is a tree of panes: groups, nulls (invisible frames that move what is under them),
  pictures and texts, each with a position, a scale and a screen. Changing those numbers moves a menu.
  `mh4u_rando/hud/lyt.py` reads and writes them.
* `exefs/code.bin` and `exheader.bin`: the game's executable with the patches, and its header (made larger when the
  patches need room past the end of the original program).
* `settings_.json`: the options used, so a bug report says how the mod was built.
* `heavenfall_beta_mod.json`: the installer's marker, listing every file it put there, so an update or uninstall touches
  only its own files.

## One install, step by step

1. **The window** (`mh4u_rando/gui/qt/`): the Install page finds the game and the emulator, the Options page holds
   the options. The options themselves are described in `mh4u_rando/gui/options.py` (texts in English and Spanish);
   which ones Heavenfall Beta shows and their starting values are data: `mh4u_rando/data/curated/gui_presets.json` and
   `gui_defaults.json`.
2. **The build** (`mh4u_rando/install/build.py`): checks that the file is MH4U (European or American, not the
   update) and calls `pipeline.run` into a build folder under `~/.heavenfall_beta/build/`.
3. **The run** (`mh4u_rando/pipeline.py`):
   * reads the executable from the game file (`exefs/player_code.py`) and lays it out as the *canonical* executable
     (below);
   * writes the interface files: the smaller HUD (`hud/`), then single-screen mode's layouts
     (`single_screen.py`), which are made last because they place whole layouts, with what the HUD step changed;
   * patches the executable in this order: the memory split, the cheats, the HUD and lock-on code, single-screen
     mode;
   * carries every patch back onto the player's own executable and writes it with its header.
4. **The copy** (`mh4u_rando/install/deploy.py`): the new files go into a folder beside the target first and replace
   the previous install in one step; anything this program did not install is never touched without asking.

The same run without the window: `python -m mh4u_rando --rom GAME --out FOLDER` (options: `--help`).

## The executable: one version to write patches for

There are several versions of the game's executable: European and American, with and without the game's update.
Functions sit at different addresses in each. Heavenfall Beta writes every patch once, for **one** version, the European
update's executable (the *canonical* one), and never needs the update itself:

* `exefs/versions.py` knows each version by its hash and has a **version map** for it
  (`exefs/generated/versions/*.json`): which runs of code moved, by how much, and where the branches and pointers
  are.
* `to_canonical` lays the player's executable out like the canonical one; every patcher then works on that image,
  unchanged for every version.
* `exefs/rebase.py` carries back only the words the patchers changed, each to its place in the player's version, with
  branches and pointers translated. A patch that would land where the player's version has no code stops the run with
  a clear error instead of a broken game.

### New code: the free space and the extension

Some patches only change a few bytes the game already has (a screen number, a constant). Others need **new code**:
small functions in ARM assembly or C that the game jumps to through a *hook* (one instruction replaced by a branch to
our code). New code needs room in the executable:

* `exefs/blocks.py` declares every piece of new code or data (a *block*) and every new variable, by name. Nobody
  writes an address by hand.
* `exefs/generated/code_space.json` is the result: where each block sits and its machine code, already compiled. The
  run copies blocks from there, so building the mod needs no compiler. The blocks' sources are in
  `mh4u_rando/exefs/asm/` and `mh4u_rando/hud/asm/` (`.s` assembly, `.c` C).
* Most new code lives in the **extension**: new pages added after the end of the original program
  (`exefs/code_space.py`, `Layout.extend`). A small start-up block (`ext_bootstrap.s`) makes those pages executable
  when the game boots; the header (`exefs/exheader.py`) is made larger to load them.
* `exefs/memory_split.py` moves a little memory from one of the game's heaps to another at boot, so the larger
  program still boots with the emulator's New 3DS mode off.

## Single-screen mode

What the player sees: the touch screen's menus on the top screen. How:

* **Which screen a layout is on.** Each layout is loaded for a screen given by a byte in the game's lists of layouts;
  `exefs/single_screen.py` changes those bytes (and the code that would force some layouts back to the bottom), each
  byte checked first. A block hooks the one function that sets a group's draw priority, so moved menus are drawn in
  front of what the top screen already shows.
* **Where each part goes: the arrangement.** Which screen of the game is showing, and where each of its parts goes
  there, is data: `mh4u_rando/data/curated/game_gui/` (the *arrangement*). It names **blocks** (groups of a layout that
  move together) and **screens** (a rule saying which groups are shown, for example "the Guild Card is open and no
  edit window", and the place of each block there). Every value is absolute: the final x, y and scale, never "move it
  10 pixels". [editing_the_ui.md](editing_the_ui.md) explains every field.
* **The engine in the game.** `gamegui/build.py` and `gamegui/engine.py` turn the arrangement into a table, and wrap
  each block's groups in a new null inside the layout files. A C block, `exefs/asm/game_gui_engine.c`, runs every
  frame: it finds the screen whose rule matches the groups the game shows, and writes each wrapper's place, screen,
  priority and visibility. It never reads back what it wrote, so a wrong frame is corrected by the next one.
* **Features that are more than a place**, each with its own layout changes and small blocks: the yes / no boxes and
  the description panel (`single_screen_prompt.s`), the keyboard driven with the pad (`single_screen_keyboard.s`),
  the World Map on X and the framed town map on L (`single_screen_world_map.s`, `hud/single_screen_minimap.py`), the
  Guild Card's hint and photo mode (`single_screen_card_info.s`; the photo mode lives in the engine), the list of
  hunters in a Gathering Hall (`hud/single_screen_players.py`), character creation on the top screen (blocks
  `single_screen_creation*`).
* `mh4u_rando/single_screen.py` makes every RomFS file of the mode, in order.
* `mh4u_rando/data/curated/single_screen.json` holds the mode's other numbers (room sizes, frames of some menus,
  fills).

## The smaller HUD

`hud/` scales every layout drawn over the game on the top screen during quests (clock, health, stamina, sharpness,
item selector, minimap...) towards its own corner, in steps of 90, 80, 70 or 60 %, by changing the layout files. A few
things the game places from its code (the minimap's icons, the mount gauge) need executable patches
(`hud/code_patch.py`, block `minimap_wrapper`).

## Locking on with L

Holding L and pressing D-pad up locks on to a large monster, as a tap on the touch screen's target panel does: block
`dpad_filter` keeps the D-pad from acting while L is held (so it does not move the camera) and notes each press of
D-pad up; block `target_button` then makes the game's own target test switch the target, sound included. The target's
face shows on the top screen (blocks `face_*`, `target_face.c`). Patches: `hud/code_patch.py`, `patch_interface`.

## The cheats

Five well-known cheat codes, built into the executable so they work without the emulator's cheat list
(`exefs/cheats.py`): 3D off (with or without the game's dot pattern), no bloom or depth of field, a fixed frame rate,
the camera's field of view and longer online waits. Some are bytes changed once; the others are values the game would
overwrite, so block `cheats` (`exefs/asm/cheats.s`) writes them every frame. At its neutral value an option changes
nothing at all.

## The interface tools

`tools/ui_recorder.py`, `tools/ui.py` and the `mh4u_rando/gamegui/` package record the game's real interface from the
emulator, draw it as pictures, check an arrangement and build probes to try it. They are the subject of
[editing_the_ui.md](editing_the_ui.md). They speak English (`gamegui/strings.py`; `--lang es` for Spanish).

## Where things are

| Folder or file | What it holds |
|---|---|
| `mh4u_rando/pipeline.py` | The run: game in, mod folder out |
| `mh4u_rando/__main__.py` | The command line |
| `mh4u_rando/settings.py`, `presets.py` | The options, their defaults and checks |
| `mh4u_rando/single_screen.py` | Single-screen mode's interface files, in order |
| `mh4u_rando/exefs/` | Reading the game file, the executable, versions, free space, every executable patch |
| `mh4u_rando/exefs/asm/`, `hud/asm/` | Sources of the new code (already compiled into `exefs/generated/code_space.json`) |
| `mh4u_rando/hud/` | Layout files (`lyt.py`), the smaller HUD, single-screen mode's layout changes |
| `mh4u_rando/gamegui/` | The arrangement, the engine's table, the recorder, the pictures and the checker |
| `mh4u_rando/arc/` | The game's archives (`.arc`) and texts |
| `mh4u_rando/gui/` | The window (PySide6) and its texts |
| `mh4u_rando/install/` | Finding games and emulators, building, installing and removing safely |
| `mh4u_rando/data/curated/` | Every number and list that is a decision (arrangement, defaults, sizes) |
| `mh4u_rando/edition.py`, `data/curated/edition.json` | This program's name, pages, platforms and folders |
| `tools/` | The interface tools and the Windows build |
