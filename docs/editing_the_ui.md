# Editing the interface

Everything single-screen mode puts on the top screen sits where a few data files say. To move a menu you change a
number in those files, look at a picture of the result, and try it in the emulator. This page explains the files, the
tools and the whole loop. What the mod does in general is in [how_it_works.md](how_it_works.md); running from the
code is in [development.md](development.md).

## The ideas in one minute

* The game draws its interface from **layouts** (`uiNNN`, for example `ui502` is the Guild Card). A layout is a tree:
  its top-level **groups** (root groups, such as `ui502_kihon`) hold the pictures and texts.
* The game shows and hides groups as you move through menus. Which groups are shown tells which **screen** of the game
  you are on: "the Guild Card open, no edit window", "the quest list", and so on.
* A **block** is a set of root groups of one layout that move together, such as "the Guild Card" or "its wooden
  background". Blocks have ids like `ui502.tarjeta` (layout, a dot, a word).
* A **screen** in the files has a **rule** (which groups must be shown, may be shown, must not be shown) and the
  **place** of each block while it is showing.
* Every value is **absolute**: the final x, y and scale, never "10 pixels more". A block's final place on a screen is
  the screen's value; where the screen says nothing, the block's own default; where that says nothing too, where the
  game draws it.
* Coordinates are pixels of the screen: the top screen is 400 x 240, the touch screen 320 x 240; x grows to the right,
  y downwards. `x`, `y` are the top-left corner of the block's visible box.

The files' names (blocks, screens) are in Spanish, as the person who made them reads the game; each has an English name
too (`names_en.json`), which the tools show.

## The files

All of them are in `core/game/data/curated/game_gui/`:

| File | What it holds | Edit it? |
|---|---|---|
| `blocks.json` | Every block: its layout, groups and default place | Yes |
| `screens/<theme>.json` | Every screen: its number, rule and blocks' places (one file per theme: title, town, facilities, palico, quests, help, guild_help, multiplayer, courier, monnyan, loading) | Yes |
| `names_en.json` | The English name of every screen, block and screen to record | When you add one |
| `fixes.json` | Changes to a layout that are no place: panes hidden, a background stretched, a pane nudged inside its group, a fill | Rarely |
| `settings.json` | The limits (scale 0.25 to 2.0, a corner at most 120 pixels outside its screen) and the photo mode's buttons | Rarely |
| `check.json` | The checker's limits, and the recorded screens that are left unarranged on purpose | Sometimes |
| `coverage.json` | The screens the recorder's window lists as still to record | Optional |
| `recorder.json`, `render.json` | The recorder's timings, the pictures' colours and zoom | No |

### A block (`blocks.json`)

```json
{"id": "ui502.tarjeta", "name": "Tarjeta del gremio", "layout": "ui502",
 "groups": ["ui502_kihon", "ui502_buki_siyou", "..."],
 "default": {"x": 40, "y": 3, "scale": 1, "screen": "top", "priority": 56}},
{"id": "ui502.fondo", "name": "Tarjeta del gremio: fondo de madera", "layout": "ui502",
 "groups": ["ui502_bg"], "default": {"hidden": true}, "backdrop": true}
```

* `groups`: the root groups that move together; a group belongs to one block at most.
* `default`: its place on every screen that does not set one (a [placement](#a-placement)).
* `backdrop: true`: a background; other blocks may lie over it without counting as an overlap.
* `overlay: true`: a window or menu that opens over another screen and may cover what is under it.
* `part`: instead of whole groups, a few panes of its one group that move on their own (siblings in a row under one
  null right under the group), for example the Guild Card's "X Greeting On/Off" button:
  `{"id": "ui502.saludo", "groups": ["ui502_kihon"], "part": ["ui502_FL_X_button", "ui502_x", "ui502_m_m"], ...}`.
  The block that holds the whole group keeps the rest; a part sets only `x`, `y`, `scale` and `hidden`, and with none
  of x, y and scale it follows its whole block.

### A screen (`screens/<theme>.json`)

```json
{"id": "guild_card", "number": "78", "name": "Tarjeta del gremio", "mode": "single_screen",
 "when": {"all": ["ui502_bg"], "none": ["ui503_BG", "ui504_BG", "ui502_M_dialy"]},
 "photo": ["ui505_guild_bg", "ui505_message"],
 "blocks": {"ui502.tarjeta": {}, "ui502.fondo": {}}}
```

* `number`: what people call it ("78 Guild Card"), and its blocks are "78.1", "78.2"... in the order listed. Unique.
* `when`: the rule. Every group of `all` is shown, at least one of `any` (when given), none of `none`. A recorded
  screen must match exactly one screen (the checker says when not).
* `blocks`: block id to its place here; `{}` keeps the block's default (it is listed for its number).
* `mode`: `single_screen`, the mode the mod builds (`normal`, for two-screen play, is in the format but unused).
* `photo` (optional): the screen has a photo mode, and these groups stay drawn while it is on; it starts with the
  `toggle` button of `settings.json` (Y), or this screen's `photo_toggle` (the Edit Card screen uses X, because the
  game uses Y there), and any button ends it. Before giving a button to the photo mode, check what the game does with
  it on that screen.

### A placement

| Field | Meaning |
|---|---|
| `x`, `y` | The top-left corner of the block's visible box, in pixels of its screen |
| `scale` | Its size: 1 is the game's, 0.5 half (between 0.25 and 2.0) |
| `screen` | `top` or `bottom` |
| `priority` | Its draw order, 0 to 255: higher is in front |
| `hidden` | `true` hides it on this screen |

Any field can be left out: it then comes from the block's default, else from the game.

## The loop: record, look, change, check, try

### 0. Once: running from the code and `local.ini`

Run the tools from a copy of this repository (development.md, "Running from the code"). Then copy
`local.example.ini` to `local.ini` and fill in:

* `mh4u_rom`: your game file, European or American;
* `mh4u_romfs`: the game's files dumped by the emulator. In Azahar: right-click the game in the list, **Dump RomFS**;
  it goes to `%APPDATA%/Azahar/dump/romfs/<title>/`. The pictures are drawn from it;
* `emulator_dir`, if your emulator's user folder is not `%APPDATA%/Azahar`.

### 1. Install a recording probe

The recorder copies the game's interface from the emulator's memory between two frames, so it needs to know when a
frame starts and ends. A **recording probe** is your usual mod plus two small counters the game updates every frame:

```
python tools/ui/ui.py probe rec --install
```

builds the next round, `output/ui/rec_1`, `rec_2`..., with your Options page's choices and single-screen mode on, and
installs it into the emulator. Add `--two-screen` to record the game's own interface on both screens (single-screen
mode off). It installs only into an empty mod folder or over an earlier probe: uninstall your usual Heavenfall Beta install
first (the program's Uninstall button). Then restart the emulation (Emulation > Restart).

### 2. Record

```
python tools/ui/ui_recorder.py
```

opens the recorder's window. Play to the screens you care about. The window shows each emulator window's state
("Recording" when it copies), the screen it is on, how many screens it recorded and which listed screens are still
to record. It only reads the emulator's memory; it never writes to it.

* **Ctrl+P** in the emulator saves a screenshot; the recorder pairs it with the copy of that moment and files a
  **request** with the note you typed in the window. "Mark this screen" files one without a picture.
* Recordings go to `work/ui/recordings/`, requests to `work/ui/peticiones/` (the folder keeps its Spanish name).
* Save states work too, without a probe: `python tools/ui/ui_recorder.py --state slot1.cst slot2.cst`.

### 3. Look

```
python tools/ui/ui.py gallery            # output/ui/galeria/index.html: every recorded screen, original and arranged
python tools/ui/ui.py show 78            # a screen: its rule, its blocks' final places, its recordings and pictures
python tools/ui/ui.py render 78 --arranged   # PNGs of a screen as the mod places it (output/ui/pictures)
python tools/ui/ui.py pending            # the requests not answered yet, newest first
```

The arranged pictures outline each block with its number. They are drawn from the recording and the game's files,
the same way the engine in the game places things, so you can work without starting the game each time.
`python tools/ui/ui.py compare 78 screenshot.png --arranged` measures how far a picture is from a real screenshot.

### 4. Change

Either edit the JSON in a text editor, or let the tool do it (it refuses anything relative or out of range):

```
python tools/ui/ui.py set 78 ui502.tarjeta x=40 y=3 scale=0.9
python tools/ui/ui.py set 78 ui502.tarjeta scale=none        # give the field back to the block's default
```

Then render again and look.

### 5. Check

```
python tools/ui/ui.py check
```

checks, over every recorded screen: each matches exactly one screen of the files; no moved block overlaps another
(measured on the pictures' pixels) unless one is a background or an overlay on top; nothing leaves its screen by more
than a few pixels; every group a block or rule names exists in the game's files; the game's memory pools for interface
pieces still fit every scene. It ends with code 0 when there is no problem. Missing English names are warnings.
`--json` gives the same report as JSON. The pools need the game update's decrypted executable as
`work/inputs/code_update.bin` and are skipped without it ("Not checked: pools...").

### 6. Try it in the game

Build and install again: press **Update** in the program (run from the code, `python -m core.gui`, so it uses
your files), or build the next probe with `python tools/ui/ui.py probe rec --install`. Restart the emulation.

## Adding a screen or a block

1. Record the screen (above). `python tools/ui/ui.py show <signature>` (the recorded screen's name the gallery shows)
   lists its groups and the screens it matches.
2. A new block: add it to `blocks.json` with an id `<layout>.<word>`, a name, its layout and groups, and its English
   name in `names_en.json` (`"blocks"`). Use the game's own English words (Guild Card, Gathering Hall, Palico Board...).
3. A new screen: add it to the theme's file with a new number, a rule that only it matches, and its blocks; its
   English name goes in `names_en.json` (`"screens"`).
4. `python tools/ui/ui.py check`, then try it.

## When something goes wrong

| You see | It means |
|---|---|
| Recorder: "Install the recording probe" | The installed mod has no frame counters: install a probe (step 1) and restart the emulation |
| Recorder: "The emulator runs as administrator..." | Open the emulator as a normal user |
| Recorder: "No exact copy this turn (retrying)" for a long time | The game leaves too little time between frames; it keeps trying |
| `tools/ui/ui.py`: "no layouts" | `local.ini` has no `mh4u_romfs`, or the folder is not a RomFS dump |
| Checker: "matches no screen" | A recorded screen no rule takes: give it a screen, or list it in `check.json`'s `unarranged` |
| Checker: "matches N screens" | Two rules take the same screen: make one of them stricter |
| Checker: "overlap by N pixels" | Two blocks cover each other on that screen: move one, or mark a real background as `backdrop` |
| Probe: "is not one of our probes" | Your usual install is in the mod folder: uninstall it first |

## How the game ends up drawing it

The build wraps each block's groups in a new invisible null inside the layout files, and turns the screens into a
table. A small engine added to the game runs every frame: it finds the screen whose rule matches the groups the game
shows, and writes each wrapper's place, screen, priority and visibility, all absolute, so nothing can drift. Details:
[how_it_works.md](how_it_works.md), "Single-screen mode".
