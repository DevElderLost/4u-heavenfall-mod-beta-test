# Heavenfall Beta: play Monster Hunter 4 Ultimate on one screen

**A fan mod for Monster Hunter 4 Ultimate (3DS, European or American version) for playing on one screen in an
emulator.** It is a module of Heavenfall, a mod for Monster Hunter 4 Ultimate. The touch screen's menus move to the top screen, a button combination locks on to monsters without
touching the screen, and the HUD can shrink. Five cheats come with it too, in case your emulator's own cheats don't
work.

You choose your options in a small program, press one button, and it installs the mod into your emulator. Your game
file is never modified.

**[Download it from the Releases page](../../releases/latest)** (`HeavenfallBeta-windows.zip`), then follow the
[installation steps](#installation-step-by-step).

> **Status:** beta. It is for the **Azahar** and **Citra** emulators (PC) only: it does
> not work on a real 3DS.

## Contents

* [What the mod adds](#what-the-mod-adds)
* [What you need](#what-you-need)
* [Installation, step by step](#installation-step-by-step)
* [Removing or updating the mod](#removing-or-updating-the-mod)
* [Questions and problems](#questions-and-problems)
* [For developers](#for-developers)
* [Credits and license](#credits-and-license)

## What the mod adds

**Playing on one screen**
* The menus you need from the touch screen show on the top screen: the title screen and main menu, the quest list,
  the Canteen, yes / no questions and menu descriptions.
* Shops, equipment sets, the Melding Pot, Palico menus, help, tutorials and the Arena show on top too, and so do the
  Gathering Hall's menus, Guild Cards, friends, chat and gestures.
* New characters are made on the top screen too, and you name them with the D-pad.
* In towns and Gathering Halls, X opens the World Map on the top screen and L shows the town map.
* In a Gathering Hall, a box at the top left lists each hunter's weapon, name, Hunter Rank and ticket.
* On the Guild Card, Y hides the menus around the hunters so you can take a picture (X while editing the card).
* The touch screen still works if you show it.

**Locking on with L**
* Hold L and press D-pad up to lock on to a large monster or switch to the other one. The monster's face shows on the
  top screen.

**A smaller HUD**
* Everything drawn over the game on the top screen (clock, health, stamina, sharpness, item selector, minimap, talk
  windows...) shrinks towards its corner: 90, 80, 70 or 60 %. It starts at 70 %.

**Cheats, in case your emulator's own don't work**
* 3D off and no glow or distant blur, for a sharper picture: on unless you turn them off.
* A fixed frame rate (30 or 60 FPS), a wider or narrower camera view, and longer waits when joining online rooms: off
  unless you turn them on.

The full list is in the **[changelog](CHANGELOG.md)**.

## What you need

1. **A Windows computer.** On other systems the program runs with Python (see the end of the installation steps).
2. **The Azahar emulator** ([azahar-emu.org](https://azahar-emu.org/)) or Citra.
3. **Your own copy of Monster Hunter 4 Ultimate, European or American version**, decrypted: a `.3ds`, a `.cia`, or
   Azahar's compressed `.zcci` or `.zcia`. You make it from your own cartridge or download with a homebrewed 3DS
   ([how to dump your games](https://3ds.hacks.guide/dumping-titles-and-game-cartridges.html)). This project never
   shares game files. The game's update is not needed, and the mod works the same with it installed or not.

## Installation, step by step

**1. Download the program.** Download `HeavenfallBeta-windows.zip` from the newest release on the
[Releases page](../../releases/latest) and unzip it anywhere (for example on your Desktop).

**2. Open it.** Double-click `HeavenfallBeta.exe`. If Windows says "Windows protected your PC" (the program is not signed),
press **More info**, then **Run anyway**. The program opens in your system's language, English or Spanish; switch
it at the bottom of the left panel.

**3. Check your game file.** On the **Install** page the program looks for your game in your emulator's game folders,
Downloads, Desktop and Documents. If it did not find it, press **Choose…** and pick the file. It shows which region
it found.

**4. Check the destination.** The program finds Azahar or Citra on its own. If it does not, press **Choose folder…**
and pick the emulator's folder.

**5. Choose your options.** The **Options** page has one screen, locking on with L, the HUD size and the cheats.
Hover over any option to read what it does.

**6. Press Install.** It takes a short while. If the emulator was running the game, restart the emulation. If the
button is greyed out, the line under it says what is missing.

**7. Play on one screen.** In Azahar, choose the **Single Screen** layout (View > Screen Layout).

**On another system** (or to run it from the source code): install [Python](https://www.python.org/downloads/) 3.10
or newer, download this page's code (green **Code** button, **Download ZIP**), and in a terminal in that folder run
`pip install -r requirements.txt`, then `python -m core.gui`.

> **Tip:** keep a copy of your save before installing a new mod, just in case.

## Removing or updating the mod

* **To remove it:** press **Uninstall** on the Install page. The game is back to normal. The program only removes
  what it installed.
* **To change your options:** change them on the Options page and press **Update** on the Install page (or **Apply
  now** on the Options page).

## Questions and problems

**Is my game file changed?** No. The program only reads it and installs a separate mod folder.

**Do I need the game's update?** No. The mod is built from the game itself and works the same with the update
installed or not.

**It says there are files of another mod.** The destination already holds a mod this program did not install. It
asks before replacing it; say no if you want to keep that mod.

**Can I use it on a real 3DS?** No. Heavenfall Beta changes how the game is drawn for an emulator's single screen, so it
only works in Azahar or Citra.

**Should I use the cheats here or my emulator's?** Either. If your emulator's own cheat list works for you, turn
this program's cheats off on the Options page. Don't turn on the same cheat in both places.

**I found a bug.** Please open an issue on this page (the **Issues** tab) and attach the `settings_.json` file
from your emulator's mod folder.

## For developers

How the mod works, and how to move any menu of the game yourself, explained for people:

* [How it works](docs/how_it_works.md): what the mod changes in the game and how an install is built.
* [Editing the interface](docs/editing_the_ui.md): record the game's screens, see them as pictures, move their parts
  with plain numbers and try them in the emulator.
* [Development](docs/develop/development.md): running from the code, building the Windows program, publishing a release.

## Credits and license

* Made by popzol.
* Cheats: the field of view code is by mikewii7, the online fix by Klark231; the 3D, glow and frame rate codes come
  from the Monster Hunter 4 Ultimate community.
* Game data reference: [Kiranico](https://mh4u.kiranico.com/).

**License:** [GNU GPL version 3 or later](LICENSE). You may use, change and share this project, including in your own
mods, as long as what you share keeps the credit to popzol, stays under the same license and comes with its source
code.

Monster Hunter is a trademark of Capcom. This is an unofficial fan project, not affiliated with or endorsed by
Capcom.
