# Editing the interface

Everything Single Screen Mode displays on the top screen is positioned using a set of data files. To move a menu, edit a value in those files, preview the result, and test it in the emulator. This guide explains the files, tools and workflow involved. For an overview of what the mod does, see [how_it_works.md](how_it_works.md). For instructions on running the project from source, see [development.md](development.md).

## Key concepts

- The game draws its interface using **layouts** (`uiNNN`, for example, `ui502` is the Guild Card). Each layout is a tree of elements. Its top-level **groups** (root groups, such as `ui502_kihon`) contain pictures and text.
- The game shows and hides groups as you navigate through menus. The combination of visible groups identifies which **screen** of the game is currently displayed: for example, "the Guild Card is open, with no editing window" or "the quest list".
- A **block** is a set of root groups from the same layout that move together, such as the Guild Card or its wooden background. Blocks have IDs in the format `ui502.tarjeta` (layout name, followed by a dot and a word).
- Each **screen** definition has a **rule** specifying which groups must be visible, which may be visible, and which must be hidden. It also defines the **placement** of each block on that screen.
- All placement values are **absolute**, not relative. They specify the final x, y and scale, rather than how far an element should move. A screen's placement takes priority over a block's default placement. If neither specifies a value, the game uses its own default.
- Coordinates are measured in screen pixels: the top screen is 400 × 240, and the bottom screen is 320 × 240. X increases to the right, and Y increases downwards. `x` and `y` refer to the top-left corner of the block's visible bounding box.

The data files use Spanish names for blocks and screens, as that is how they were originally organized. Each entry also has an English name in `names_en.json`, which is what the tools display.

## The files

All the files are located in `core/game/data/curated/game_gui/`:

| File | Contents | Edit it? |
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

For example, these are two blocks from the Guild Card layout:

```json
{
  "id": "ui502.tarjeta",
  "name": "Tarjeta del gremio",
  "layout": "ui502",
  "groups": ["ui502_kihon", "ui502_buki_siyou", "..."],
  "default": {
    "x": 40,
    "y": 3,
    "scale": 1,
    "screen": "top",
    "priority": 56
  }
}
```

```json
{
  "id": "ui502.fondo",
  "name": "Tarjeta del gremio: fondo de madera",
  "layout": "ui502",
  "groups": ["ui502_bg"],
  "default": {
    "hidden": true
  },
  "backdrop": true
}
```

- `groups`: the root groups that move together. A group can belong to at most one block.
- `default`: the block's default placement on any screen that does not define its own placement (see [A placement](#a-placement)).
- `backdrop: true`: marks the block as a background. Other blocks can overlap it without triggering an overlap warning.
- `overlay: true`: marks a window or menu that opens on top of another screen and may cover whatever is underneath.
- `part`: allows you to move individual panes within a group instead of moving the entire group. These panes must be siblings under the same `null` node, directly beneath the group.

  For example, the Guild Card's "X Greeting On/Off" button:

  ```json
  {
    "id": "ui502.saludo",
    "groups": ["ui502_kihon"],
    "part": ["ui502_FL_X_button", "ui502_x", "ui502_m_m"]
  }
  ```

  The block containing the whole group continues to control everything else. A part can override only `x`, `y`, `scale` and `hidden`. If it does not specify any of `x`, `y` or `scale`, it follows the placement of the block containing its group.

### A screen (`screens/<theme>.json`)

For example:

```json
{
  "id": "guild_card",
  "number": "78",
  "name": "Tarjeta del gremio",
  "mode": "single_screen",
  "when": {
    "all": ["ui502_bg"],
    "none": ["ui503_BG", "ui504_BG", "ui502_M_dialy"]
  },
  "photo": ["ui505_guild_bg", "ui505_message"],
  "blocks": {
    "ui502.tarjeta": {},
    "ui502.fondo": {}
  }
}
```

- `number`: the number used to identify the screen (for example, "78 Guild Card"). Its blocks are numbered "78.1", "78.2", and so on, in the order they are listed. Each screen number must be unique.
- `when`: the visibility rule. Every group listed under `all` must be visible, at least one group under `any` must be visible (when `any` is specified), and no group under `none` may be visible. Each recorded screen must match exactly one screen definition. The checker reports cases where this is not true.
- `blocks`: maps block IDs to their placements on this screen. An empty object (`{}`) keeps the block's default placement.
- `mode`: `single_screen` is the mode used when building the mod. `normal`, intended for regular two-screen play, is also supported by the format but is currently unused.
- `photo` (optional): lists the groups that remain visible while photo mode is active. Photo mode is activated using the `toggle` button in `settings.json` (Y by default), or this screen's `photo_toggle` setting (the Edit Card screen uses X because the game already uses Y there). Pressing any button exits photo mode. Before assigning a button to photo mode, check what the game normally does with that button on the screen.

### A placement

| Field | Meaning |
|---|---|
| `x`, `y` | The top-left corner of the block's visible bounding box, in pixels |
| `scale` | The block's size. `1` is the original game size; `0.5` is half that size (allowed range: 0.25 to 2.0) |
| `screen` | `top` or `bottom` |
| `priority` | Draw order, from 0 to 255. Higher values are drawn in front. |
| `hidden` | Set to `true` to hide the block on this screen |

Any field can be omitted. Its value is then inherited from the block's default placement or, if no default is specified, from the game's original behavior.

## The workflow: record, preview, edit, check and test

### 0. Initial setup: running from source and configuring `local.ini`

First, set up the project by following the instructions in [development.md](development.md), under "Running from the code".

Then copy `local.example.ini` to `local.ini` and configure:

- `mh4u_rom`: your European or American game file.
- `mh4u_romfs`: the game's files dumped by the emulator. In Azahar, right-click the game in the game list and select **Dump RomFS**. The files are saved to `%APPDATA%/Azahar/dump/romfs/<title>/`. The preview tools use them to render the game's interface.
- `emulator_dir`: only if your emulator's user folder is not located at `%APPDATA%/Azahar`.

### 1. Install a recording probe

The recorder copies the game's interface directly from the emulator's memory between frames. To do this, it needs to know when each frame starts and ends.

A **recording probe** is your usual mod with two additional counters that the game updates every frame.

```bash
python tools/ui/ui.py probe rec --install
```

This builds the next recording probe (`output/ui/rec_1`, `rec_2`, and so on), using the options selected on the Options page with Single Screen Mode enabled, and installs it into the emulator.

Add `--two-screen` to record the game's original interface on both screens, with Single Screen Mode disabled.

The probe can only be installed into an empty mod folder or over a previous recording probe. Uninstall your regular Heavenfall Beta installation first using the program's **Uninstall** button.

After installation, restart the emulation (**Emulation > Restart**).

### 2. Record

```bash
python tools/ui/ui_recorder.py
```

This opens the recorder window. Play the game and navigate to the screens you want to record.

The window displays each emulator window's current state (showing "Recording" while a capture is being made), the screen being displayed, the number of screens recorded and which screens in the coverage list are still waiting to be recorded.

The recorder only reads the emulator's memory. It never writes to it.

- Press **Ctrl+P** in the emulator to save a screenshot. The recorder pairs it with the memory capture from that moment and creates a **request** containing the note you entered in the recorder window.
- Click **Mark this screen** to create a request without a screenshot.
- Recordings are saved in `work/ui/recordings/`. Requests are saved in `work/ui/peticiones/` (the folder keeps its original Spanish name).
- You can also record from save states without installing a probe:

  ```bash
  python tools/ui/ui_recorder.py --state slot1.cst slot2.cst
  ```

### 3. Preview

```bash
python tools/ui/ui.py gallery              # output/ui/galeria/index.html: all recorded screens, original and arranged
python tools/ui/ui.py show 78               # screen rule, final block placements, recordings and screenshots
python tools/ui/ui.py render 78 --arranged   # PNG previews of a screen as arranged by the mod
python tools/ui/ui.py pending                # unanswered requests, newest first
```

The arranged previews outline each block and label it with its number. They are rendered using the recordings and the game's files, following the same placement logic as the in-game engine. This means you can work on the interface without having to launch the game every time.

You can also compare an arranged preview against an actual screenshot:

```bash
python tools/ui/ui.py compare 78 screenshot.png --arranged
```

This measures how closely the preview matches the screenshot.

### 4. Edit

You can edit the JSON files directly in a text editor or use the command-line tool. The tool rejects relative values and values outside the allowed ranges.

```bash
python tools/ui/ui.py set 78 ui502.tarjeta x=40 y=3 scale=0.9
python tools/ui/ui.py set 78 ui502.tarjeta scale=none
```

Setting a field to `none` resets it to the block's default value.

Render the screen again to preview your changes.

### 5. Check

```bash
python tools/ui/ui.py check
```

The checker validates every recorded screen:

- Each recording matches exactly one screen definition.
- Blocks do not overlap, based on their visible pixels, unless the overlap is allowed by a background or an overlay.
- No block extends beyond the screen boundaries by more than a few pixels.
- Every group referenced by a block or visibility rule exists in the game's files.
- The game's memory pools for interface elements have enough space for every scene.

The checker exits with code `0` when no problems are found. Missing English names are reported as warnings.

Use `--json` to get the same report in JSON format.

Checking the memory pools requires the game's decrypted update executable at `work/inputs/code_update.bin`. If it is missing, this check is skipped and the report displays `"Not checked: pools..."`.

### 6. Test in the game

Build and install the mod again, then restart the emulation.

You can either click **Update** in the program (when running it from source with `python -m core.gui`) or build another recording probe using:

```bash
python tools/ui/ui.py probe rec --install
```

## Adding a screen or a block

1. Record the screen using the workflow above. Then run `python tools/ui/ui.py show <signature>`, where `<signature>` is the name displayed for the recording in the gallery. This lists its groups and the screen definitions it matches.
2. To add a block, define it in `blocks.json` with an ID in the format `<layout>.<word>`, a name, its layout and its groups. Add its English name to the `"blocks"` section of `names_en.json`. Use the game's own English terminology (Guild Card, Gathering Hall, Palico Board, etc.).
3. To add a screen, define it in the appropriate theme file with a unique number, a rule that matches only that screen and its blocks. Add its English name to the `"screens"` section of `names_en.json`.
4. Run `python tools/ui/ui.py check` and test the result in the emulator.

## Troubleshooting

| Message or situation | Meaning / solution |
|---|---|
| Recorder: "Install the recording probe" | The installed mod does not have the frame counters. Install a recording probe (step 1) and restart emulation. |
| Recorder: "The emulator runs as administrator..." | The emulator is running with administrator privileges. Close it and reopen it as a normal user. |
| Recorder: "No exact copy this turn (retrying)" appears for a long time | The game is leaving too little time between frames for the recorder to capture the interface. It will keep retrying. |
| `tools/ui/ui.py`: "no layouts" | `local.ini` does not contain a valid `mh4u_romfs` path, or the selected folder is not a RomFS dump. |
| Checker: "matches no screen" | No screen rule matches this recording. Add a screen definition for it, or list it under `unarranged` in `check.json`. |
| Checker: "matches N screens" | Multiple screen rules match the same recording. Make the rules more specific so that only one matches. |
| Checker: "overlap by N pixels" | Two blocks overlap on that screen. Move one of them, or mark an actual background block as `backdrop`. |
| Probe: "is not one of our probes" | Your regular mod installation is still in the mod folder. Uninstall it before installing the probe. |

## How the game actually draws the interface

During the build process, each block's groups are wrapped in a new invisible `null` inside the layout files, and the screen definitions are converted into a table.

A small engine added to the game runs every frame. It identifies the screen whose visibility rule matches the groups currently being displayed, then updates each wrapper's placement, screen, priority and visibility. All values are absolute, so elements cannot gradually drift from their intended positions.

For more technical details, see [how_it_works.md](how_it_works.md), under "Single-screen mode".
