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
  `core/game/files/gui/lyt.py` reads and writes them.
* `exefs/code.bin` and `exheader.bin`: the game's executable with the patches, and its header (made larger when the
  patches need room past the end of the original program).
* `settings_.json`: the options used, so a bug report says how the mod was built.
* `heavenfall_beta_mod.json`: the installer's marker, listing every file it put there, so an update or uninstall touches
  only its own files.

## One install, step by step

1. **The window** (`core/gui/qt/`): the Install page finds the game and the emulator, the Options page holds
   the options chosen at install. The options themselves are described in `core/gui/options.py` (texts in English and
   Spanish); which ones Heavenfall Beta shows, which the game's START menu holds too (`in_game`) and their starting
   values are data: `core/game/data/curated/gui_presets.json` and `gui_defaults.json`. Its `install.modules` makes the
   page's four tabs, one per module (single screen, Layered Gear, cheats, quality of life), each starting with its switch:
   every other option of the tab is greyed out while the switch is off.
2. **The build** (`core/install/build.py`): checks that the file is MH4U (European or American, not the
   update) and calls `pipeline.run` into a build folder under `~/.heavenfall_beta/build/`.
3. **The run** (`core/app/pipeline.py`):
   * gives every field of a module that is off its `Settings` default, the game's own (`presets.apply_modules`), and
     leaves that module's rows out of the START menu's page; Select and Start belong to the single-screen module and the
     Rare Materials Exchange to Layered Gear's;
   * reads the executable from the game file (`game/executable/player_code.py`) and lays it out as the *canonical* executable
     (below);
   * writes the interface files: the smaller HUD (`interface/hud/`), the texts of the START menu's page, then
     single-screen mode's layouts (`interface/single_screen/run.py`), which are made last because they place whole layouts,
     with what the other steps changed;
   * patches the executable in this order: Layered Gear's new items (in every run, its module on or off), the memory
     split, Select and Start, the START menu's page with the options it
     holds (and their defaults for a character with no choice), the aspect ratio, the HUD and lock-on code, single-screen
     mode;
   * carries every patch back onto the player's own executable and writes it with its header.
4. **The copy** (`core/install/deploy.py`): the new files go into a folder beside the target first and replace
   the previous install in one step; anything this program did not install is never touched without asking.

The same run without the window: `python -m core --rom GAME --out FOLDER` (options: `--help`). In a browser, on devices
that cannot run the program: the web page ([development.md](develop/development.md), "The web page"), which makes the
mod on the player's device and leaves step 4 to the player.

## The executable: one version to write patches for

There are several versions of the game's executable: European and American, with and without the game's update.
Functions sit at different addresses in each. Heavenfall Beta writes every patch once, for **one** version, the European
update's executable (the *canonical* one), and never needs the update itself:

* `game/executable/versions.py` knows each version by its hash and has a **version map** for it
  (`game/executable/generated/versions/*.json`): which runs of code moved, by how much, and where the branches and pointers
  are.
* `to_canonical` lays the player's executable out like the canonical one; every patcher then works on that image,
  unchanged for every version.
* `game/executable/rebase.py` carries back only the words the patchers changed, each to its place in the player's version, with
  branches and pointers translated. A patch that would land where the player's version has no code stops the run with
  a clear error instead of a broken game.

### New code: the free space and the extension

Some patches only change a few bytes the game already has (a screen number, a constant). Others need **new code**:
small functions in ARM assembly or C that the game jumps to through a *hook* (one instruction replaced by a branch to
our code). New code needs room in the executable:

* `game/executable/blocks.py` declares every piece of new code or data (a *block*) and every new variable, by name. Nobody
  writes an address by hand.
* `game/executable/generated/code_space.json` is the result: where each block sits and its machine code, already compiled. The
  run copies blocks from there, so building the mod needs no compiler. The blocks' sources (`.s` assembly, `.c` C)
  sit beside the Python that patches them, in each feature's folder.
* Most new code lives in the **extension**: new pages added after the end of the original program
  (`game/executable/code_space.py`, `Layout.extend`). A small start-up block (`ext_bootstrap.s`) makes those pages executable
  when the game boots; the header (`game/executable/exheader.py`) is made larger to load them.
* `game/executable/memory_split.py` moves a little memory from one of the game's heaps to another at boot, so the larger
  program still boots with the emulator's New 3DS mode off.

## Single-screen mode

What the player sees: the touch screen's menus on the top screen. How:

* **Which screen a layout is on.** Each layout is loaded for a screen given by a byte in the game's lists of layouts;
  `interface/single_screen/executable/single_screen.py` changes those bytes (and the code that would force some layouts back to the bottom), each
  byte checked first. A block hooks the one function that sets a group's draw priority, so moved menus are drawn in
  front of what the top screen already shows.
* **Where each part goes: the arrangement.** Which screen of the game is showing, and where each of its parts goes
  there, is data: `core/game/data/curated/game_gui/` (the *arrangement*). It names **blocks** (groups of a layout that
  move together) and **screens** (a rule saying which groups are shown, for example "the Guild Card is open and no
  edit window", and the place of each block there). Every value is absolute: the final x, y and scale, never "move it
  10 pixels". [editing_the_ui.md](editing_the_ui.md) explains every field.
* **The engine in the game.** `interface/game_gui/build.py` and `interface/game_gui/engine.py` turn the arrangement into a table, and wrap
  each block's groups in a new null inside the layout files. A C block, `interface/game_gui/game_gui_engine.c`, runs every
  frame: it finds the screen whose rule matches the groups the game shows, and writes each wrapper's place, screen,
  priority and visibility. It never reads back what it wrote, so a wrong frame is corrected by the next one.
* **Features that are more than a place**, each with its own layout changes and small blocks: the yes / no boxes and
  the description panel (`single_screen_prompt.s`), the keyboard driven with the pad (`single_screen_keyboard.s`),
  the World Map on X and the framed town map on L (`single_screen_world_map.s`, `interface/single_screen/layout/single_screen_minimap.py`), the
  Guild Card's hint and photo mode (`single_screen_card_info.s`; the photo mode lives in the engine), the list of
  hunters in a Gathering Hall (`interface/single_screen/layout/single_screen_players.py`), character creation on the top screen (blocks
  `single_screen_creation*`).
* `core/interface/single_screen/run.py` makes every RomFS file of the mode, in order.
* `core/game/data/curated/single_screen.json` holds the mode's other numbers (room sizes, frames of some menus,
  fills).

## The smaller HUD

`core/interface/hud/` scales every layout drawn over the game on the top screen during quests (clock, health, stamina, sharpness,
item selector, minimap...) towards its own corner, in steps of 90, 80, 70 or 60 %, by changing the layout files. A few
things the game places from its code (the minimap's icons, the mount gauge) need executable patches
(`interface/hud/code_patch.py`, blocks `minimap_wrapper` and `minimap_zoom`: the latter for the minimap zoomed on the
current area and the Everwood's whole map).

## The START menu's page: Mod Settings

A third page in the game's START menu (`interface/mod_settings/`) holds what a player changes during play: the cheats, the
lock-on with L, holding A, fast text, the camera's turn speed and the equipment at every item box. The list is data (`core/game/data/curated/mod_settings.json`); each option has a list of values
and a byte in the character's save, so every character keeps its own choices. A block runs once a frame and acts on them
(`mod_options.c`), and the options that hook the game go through a gate that makes the game's own call when the option is
off (`mod_options_stub.s`). A character with no choice yet, the title screen and character creation take the value chosen on
the program's Options page (it starts at `gui_defaults.json`'s), written into the mod by the run (`mod_options.py`); an
option with a `default` of its own in that file (skipping the death camera or a monster's intro) is the page's only, with
that value. In
single-screen mode the page's description panel stands at the bottom left, in a quest too: a place of `help_top` that waits for
the byte `mod_settings_state` + 5, up only while the page is open. Its lists show up to ten rows a page, each page in a
frame of as many rows as it has: the game's list widgets (five and eight lines, frames of 2 to 5 rows and of 8) with the panes
`interface/mod_settings/ten_rows.py` adds to `ui020` (more lines, a frame of every other size from 1 to 10, row strips
shown row by row, hidden until the page shows them); Up and Down go round a page's rows, Left and Right turn the pages. In
single-screen mode a list of nine or ten rows goes up as far as keeps its last row clear of the description.

## Locking on with L

Holding L and pressing D-pad up locks on to a large monster, as a tap on the touch screen's target panel does: block
`dpad_filter` keeps the D-pad from acting while L is held (so it does not move the camera) and notes each press of
D-pad up; block `target_button` then makes the game's own target test switch the target, sound included. The target's
face shows on the top screen (blocks `face_*`, `target_face.c`). Patches: `interface/hud/code_patch.py`, `patch_interface`.

## Select and Start

The game turns a held Select into Start, so both open the menu and no button kicks. The game's own option "START"
(page 2 of its Options: Menu or Kick) now says what Select does, with nothing to set in the program. With Menu, the
game's default, only Start opens the menu and Select kicks (the touch screen's Special Attack). With Kick, in a quest
Start kicks and Select opens and closes the menu; in a town both open it. At the title Select does nothing. Block
`select_kick`
(`gameplay/select_kick/select_kick.c`, patch in `select_kick.py`) takes over three calls of the game: the pad step's two
calls that turn Select into Start, one on each of its paths (with an extra pad answering, the New 3DS's ZL, ZR and
C-stick or a Circle Pad Pro, and without one, an Old 3DS alone or a New 3DS with its C-stick off), which the block makes only in a town with the option at
Kick, and the menu's read of the option that stops
Start from opening the menu in a quest, which lets a Select press through when the option is Kick. The touch screen's
kick and Start in the menus are untouched.

## Skipping the death camera

When the last monster falls, the camera manager plays its death camera (a camera sequence of kind 0xD) and calls
FUN_00c03d70 once a frame while it plays; a 0 from that call makes the manager end the camera itself. Block
`death_camera_skip` (`gameplay/death_camera_skip/death_camera_skip.c`, patch in `death_camera_skip.py`) takes that call
through the Mod Settings gate: with the option on (the default) it answers 0 when Start was pressed. While the camera plays
it also sets `death_camera_skip_state`, which `select_kick`'s menu gate counts down, so that press does not open the menu.

## Better Camera

Its code is called `modern_camera`; Mod Settings shows it as Better Camera, a row that opens a list of three: the option
`modern_camera` (Use Better Camera: Yes or No), Max Speed and Acceleration.

The game turns the camera by four buttons: FUN_00b3cc64 turns the D-pad and the C-stick into "camera up, down, left,
right", and FUN_00bfd028 turns the camera's angles by them, one axis a frame. Block `modern_camera`
(`gameplay/modern_camera/modern_camera.c`, patch in `modern_camera.py`) takes two places through Mod Settings' gates.
FUN_00b3cc64's question "is the C-stick tilted" goes to `modern_camera_stick`, which gives the game's own answer (the
stick sets the game's buttons for every other reader) and, when the game takes the stick for the camera (not while a
gunner looks through the scope), keeps its direction and length. The cameras' three calls of FUN_00bfd028 go to
`modern_camera_turn`, which makes the game's call with the stick's buttons hidden (the D-pad turns as before) and then
turns both angles by the kept stick: a dead zone, a response curve, a top speed per axis times Max Speed, and
an exponential speeding up and slowing down over the frame's time (its time constants divided by Acceleration), within the game's pitch limit and its invert
settings.

The aims (a bowgun over the shoulder or through the scope, the Bow) are FUN_00b2041c's, which turns them by digital
commands, one step a frame. Three more places inside it go through gates: its loads of the commands over the shoulder
and the Bow's go to `aim_commands_hook`, which takes the C-stick's command out of the register (not the D-pad's); its
test of the scope's C-stick bits goes to `aim_scope_hook`, which hides them; both then turn the aim's yaw and pitch by
the stick with the camera's dead zone, each aim's own curve, smoothing and top speed (the scope's curve stronger and its
turn slower to start and settle, since its view is the aim itself), Max Speed and Acceleration as for the camera, the game's Aim Speed, the scope's zoom, the
aim's limits and invert settings. Its calls of FUN_00b1ea04 go to `modern_aim_view`, which makes the pitch's angle from
the whole pitch, not its integer part. A bowgun with the Scope part keeps the game's scope, where the C-stick zooms
and the circle pad aims. Only the hunter this console plays is turned. Max Speed and Acceleration are options of the page
whose values carry a float (`floats` in `curated/mod_settings.json`); the block reads the one in use through
`mod_option_payload`. The tuning is `curated/modern_camera.json`. With Better Camera disabled, every gate makes the game's own call or instruction.

## Skipping a monster's intro

The touch screen's menu bar turns its third button into Skip while the game lets the player skip something: an event
camera whose kind is flagged skippable (FUN_00d0ccb4), or in a quest a cutscene whose skip flag is set (FUN_001a1cb8; the
flag is set at the quest's start only for the monsters with an intro cutscene, so story cutscenes never get it). The
bar's input calls the frame of each of its buttons, FUN_00292ea4, from one place. Block `intro_skip`
(`gameplay/intro_skip/intro_skip.c`, patch in `intro_skip.py`) takes that call through the Mod Settings gate: it makes
the game's call, then, with the option on (the default), in a quest, for the Skip button with Start pressed, it makes what
a touch of Skip makes, after the same checks (FUN_00bfd3f0 ends the camera; FUN_001a2d4c asks the cutscene's player to
skip, which the player takes or refuses as for a touch). When it skipped it sets `death_camera_skip_state` as the death
camera skip does, so that press does not open the menu.

A skipped cutscene's music and sounds stop, for Start and a touch alike. While the cutscene's player skips, its frame
(FUN_0019dfb8) calls FUN_0030cb5c, which fades out only the event streams the sound control still keeps a player record
of; a stream without one would play on into the fight. The block takes that call and the one at the event's end
(FUN_0030cd10) through the same option's gates: after the game's call it fades out (FUN_00bcac00, as the game does)
every live voice of the sound driver on the two event queues, by the voice's own queue and request; at the end only
when the event was skipped. The fight's music is on other queues and plays as the game starts it.

## Skipping the prologue

The character creation (FUN_00b7961c) ends with a call to FUN_00c25b50, the new profile, at 0xB79B2C. The option
`skip_intro` (off by default, in the quality-of-life module) turns that call into one to block `new_game_skip`
(`gameplay/new_game_skip/new_game_skip.s`, patch in `new_game_skip.py`), which makes the same call and then leaves the
new save as the game leaves it after the prologue on the sand ship: 1500z, the starting armor in the box and worn, the
prologue's quest cleared and the prologue's story flags, with the arrival seen (flag 0x5BA). Its data, block
`new_game_data`, is written by `new_game_data(prologue_only=True)` (`install.intro_skip_stop` of the presets). The flags
of the arrival's events, the registration and the Gathering Hall's introduction stay off and the Hunter Rank 0, so the
town plays them: the Caravaneer's first talk, then the registration. Only a character created with the option on
changes; the caravan and its tutorial stay the game's.

## Holding A

Block `hold_a` (`gameplay/hold_a/hold_a.c`, patch in `hold_a.py`) hooks three calls of the game. In a quest, with the
weapon sheathed and the circle pad at rest, holding A presses it again at the game menus' own repeat rate. In the quest
rewards and the Wyporium's Claim Items, holding A does the same, and after a cell empties the cursor moves to the next
one with an item. A change of step (a full pouch, a question) leaves the cursor where it is and asks for a new press, so
nothing is confirmed by accident.

## The weapon tree

The weapon tree (`interface/weapon_tree/`) takes the place of Forge Weapons' list. Its panes are six new groups of
the facility menu's layout (`tree_layout.py`: the screen's five and the window that asks "upgrade or craft"), copies
of the game's own sprites, and its words go after the game's in the Smithy's messages (`tree_texts.py`: among them,
copies of the game's own help lines and price questions with the verb in capitals). Its code (`weapon_tree.c`) runs as a state of the Smithy the game never uses: when a class is
chosen it reads the class's weapons, upgrade records and create recipes with the game's own readers, places the
weapons the hunter has discovered as a tree, and draws the game's stats panels for the weapon under the cursor, with
its price beside the money in a copy of the money window's own second box. A
replays the game's own forge or upgrade, call by call, so the price, the materials, the box and the statistics change
as they do in the game; both then play the forge's hammer scene and ask "Equip now?", an upgrade too (the game's own
Upgrade has no scene). Nothing is computed when the mod is made: the tree is what the game's tables hold. Every
size and colour is in `core/game/data/curated/weapon_tree.json`. The row Smithy View of Mod Settings stands before
the tree's two entries (a class in Forge Weapons, a weapon in Upgrade): on List the game's own code runs.

## The Jukebox

The Jukebox (`music/jukebox/`) puts one song or playlists of the game's music in the towns. `jukebox_build` (`build.py`) gives
the files and `patch_executable` the three patches, both called by the run. For every song the lobby's music queue
(`core_lobby.arc`, in each language) gets a request that copies Val Habar's theme, so the game's fades and room levels
treat it as a town theme; the songs' stream entries and levels come from `generated/jukebox_streams.json`, so the run
reads little of the game. The Housekeeper's menu texts go into the copies of `Room_s`. With MH XX's game and the
option `jukebox_xx`, XX's themes (`xx_all` in `curated/jukebox.json`) are read from it, rewritten in MH4U's layout and
shipped, at their own requests' levels in XX's queues (`xx_tracks.py`); one that sounds as a song the build has is left
out.

The code is one block (`jukebox.c`, with `jukebox_save.c` for the card file and `jukebox_menu.c` for the menu). It
replaces the town theme selector's answer with the one song's or the playlist's request, counts the passes of a
playlist's song's loop to fade it out and move on (the one song loops), keeps the song and the playlists in a block of
the card file, and adds the Jukebox line and its screens to the
house Felyne's menu with the game's own lists and windows (no new texture, so HD texture packs need nothing).

## Layered Gear and the Wyporium

Layered Gear (`equipment/layered/`) adds the Smithy's Layered Equipment line: the forge-style screens, the look lists of
the game's own gear, the prices and the rule that decides which looks show. SELECT on the Armor screen opens a colour
window built on the item box's Armor Pigment (its palette, its colour scale and its words), free and shown on the model
as the cursor moves. The entry's last line, Relics, opens the same Weapons and Armor screens listing the relics alone,
every one of the ranks open, for sale (`equipment/layered/relic_prices.py`, `core/game/data/curated/layered_relics.json`):
a numbered relic whose first look of the same name is a normal look costs exactly that look, a relic of a monster (or of
a family of monsters) what their dearest look of the same kind costs at its rank (of the other kind when they have none
of its kind; a price of its own rank, curated, when they have none of its rank), one of no monster its rank's ore, a
crystal or a bone and four times its tier's zenny; a relic the hunter has had is bought already. The Rare Materials Exchange
(`gameplay/wyporium/rare_exchange.py`) adds a line and two screens to the Wyporium. Both write texts into the game's
archives and add code to the executable. Given Monster Hunter XX's decrypted game, a run also converts the models of XX's
weapons and armor into a pack of archives (`equipment/mhgen/`), adds the Layered Gear looks that use them and adds the
trades of the rare materials of XX's monsters that MH4U lacks to the Wyporium's list (`gameplay/wyporium/trades.py`).
Without it the run has only MH4U's looks and the exchange. Those materials and Foreign Scrap are new items
(`equipment/layered/xx_materials.py`, their records committed in `core/game/data/curated/xx_item_records.json`) that every
run defines, Layered Gear's module on or off and XX's game given or not: a save that holds one keeps reading it, never
the junk record of an id past the game's table.

A look shows its own piece's colour (MH4U's default dye of that piece, or XX's colour tables for XX's looks), not the
dye of the real armor worn under it, unless the player picks a colour for that part; the game's part colour function
is hooked for it (`layered_part_dye` in `equipment/layered/layered_selector.c`).

In local play each player's looks travel in a message of their own (`equipment/layered/layered_online.c`), sent with
the game's own gear and join messages; an unmodded game drops it unread. The other players' hunters and Felynes wear
those looks, and their colours, in the hall and in quests; a game that lacks any of a player's looks shows that
player's real gear.

## The save

MH4U's `userN` and `cardN` stay clean. Four hooks in the executable (`core/save/beta_sidecar.c`, `.s`, `.ld`,
`beta_sidecar.py`; the set-apart rules in `core/save/c/extras.c`) split a file when the game writes it and join it
when the game reads it: what MH4U does not know (ids of the new items, Mod Settings, Layered Gear's state, the card's
Jukebox block and more) goes into a sidecar image of the slot in MH4U's extdata, written first; the file is written
only after. The sidecar is read and written with an inline request to the game's own file manager, so it needs the
extension (the exheader) and the save archive's mount, which is why this edition never uses the own-extdata patch of
the full mod. If the sidecar cannot be written the file is written whole with a mark, and the next join sorts it out.
A file from the earlier Beta (no sidecar) is taken as it is; the first save keeps it unchanged in `hfoldN`. What an
older Heavenfall left in a file (gear past MH4U's counts, their marks, Heavenfall's quests in the log and the quest
bits, the new monsters' hunt records; `core/save/c/heav.c`) goes into one more sidecar of the slot, `hfheavN`, and the
file keeps MH4U's own values in its place (the type's first piece, a Derring piece for Felynes), so every index stays
valid. A slot whose file MH4U would not know byte for byte is split and written back clean when the title reads it,
once per launch. Every install copies the saves first (`core/save/backup.py`); a build from a bare executable has no
hooks.

## The cheats

Six well-known cheat codes, built into the executable so they work without the emulator's cheat list, chosen on the START
menu's page (`interface/mod_settings/mod_options.py`, above): 3D off (with or without the game's dot pattern), no bloom or
depth of field, a fixed frame rate, the camera's field of view, longer online waits and weapons' true attack in the menus. The
values the game would overwrite are written every frame; the others are read from the mod's variable where the game reads
them, or go through a gate. At its neutral value an option leaves the game as it is. The aspect ratio
(`cheats/aspect_ratio.py`, still in testing, behind the switch `cheat_aspect_allowed` on the Options page) is not one of
them: it hooks the 3D views' aspect, the interface's projection and the sub-views' rectangles, so nothing looks stretched on a wider or
narrower picture. The HUD keeps to the picture's edges; every other group of the interface goes to its side from a table built in each
run (`interface/hud/anchors.py`), and the backdrops grow to cover the picture. Its list in the game, a third page of the START menu
(`interface/mod_settings/`), keeps the choice in the character's save; every hook reads it each time.

## The interface tools

`tools/ui/ui_recorder.py`, `tools/ui/ui.py` and the `core/interface/game_gui/` package record the game's real interface from the
emulator, draw it as pictures, check an arrangement and build probes to try it. They are the subject of
[editing_the_ui.md](editing_the_ui.md). They speak English (`interface/game_gui/strings.py`; `--lang es` for Spanish).

## Where things are

| Folder or file | What it holds |
|---|---|
| `core/app/pipeline.py` | The run: game in, mod folder out |
| `core/app/cli.py` | The command line |
| `core/app/settings.py`, `presets.py` | The options, their defaults and checks |
| `core/interface/single_screen/run.py` | Single-screen mode's interface files, in order |
| `core/interface/single_screen/` | Single-screen mode: `layout/` (its layout changes), `executable/` (its patches and their C and assembly) |
| `core/interface/hud/` | The smaller HUD and the lock-on code |
| `core/interface/game_gui/` | The arrangement, the engine's table, the recorder, the pictures and the checker |
| `core/gameplay/select_kick/`, `core/gameplay/hold_a/`, `core/gameplay/death_camera_skip/`, `core/gameplay/intro_skip/`, `core/gameplay/modern_camera/` | Select and Start; holding A; skipping the death camera; skipping a monster's intro; the modern camera |
| `core/save/` | The save's sidecars (`beta_sidecar.*`, `c/extras.*`) and the saves' backup before an install |
| `core/interface/mod_settings/` | The START menu's page, its options and their values |
| `core/equipment/layered/`, `core/equipment/mhgen/`, `core/gameplay/wyporium/` | Layered Gear, the models of MH XX's looks, the Wyporium's trades and exchange |
| `core/music/` | The Jukebox: its build, patches and C, and the game's audio formats it reads |
| `core/cheats/` | The emulator cheats and the aspect ratio |
| `core/game/executable/` | Reading the game file, the executable, versions and their maps, free space, the blocks (compiled into `generated/code_space.json`) |
| `core/game/files/` | The game's file formats: archives (`.arc`), layouts (`lyt.py`), texts |
| `core/gui/` | The window (PySide6) and its texts |
| `core/install/` | Finding games and emulators, building, installing and removing safely |
| `core/game/data/curated/` | Every number and list that is a decision (arrangement, defaults, sizes) |
| `core/app/edition.py`, `game/data/curated/edition.json` | This program's name, pages, platforms and folders |
| `tools/` | The interface tools and the Windows build |
