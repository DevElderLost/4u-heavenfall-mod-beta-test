# Heavenfall Beta: Play Monster Hunter 4 Ultimate on a Single Screen

**A fan-made mod for the European and American versions of Monster Hunter 4 Ultimate (3DS), designed for playing on a single screen in an emulator.**

Heavenfall Beta is the single-screen module of Heavenfall, a mod for Monster Hunter 4 Ultimate. It moves menus normally displayed on the bottom screen to the top screen, adds a button combination for locking on to monsters without using the touchscreen, and lets you scale down the HUD. It also includes five built-in cheats as a fallback in case your emulator's own cheats don't work.

You choose your options in a small program, press one button, and it installs the mod into your emulator. Your game file is never modified.

**[Download it from the Releases page](../../releases/latest)** (the latest "Heavenfall Single-Screen Mod" release, file `HeavenfallBeta-windows.zip`), then follow the [installation instructions](#installation-step-by-step).

## Join the community

Want to follow development, ask questions, report bugs, or share feedback? Come join the **[Heavenfall Discord server](https://discord.gg/qQwPRc8CDF)**!

It's the best place to get help, discuss the mod and keep up with the latest news.

> **Status:** Beta. Heavenfall Beta is currently compatible with the **Azahar** and **Citra** emulators on PC only. It does not work on a real 3DS.

## Contents

- [What the mod adds](#what-the-mod-adds)
- [What you need](#what-you-need)
- [Installation, step by step](#installation-step-by-step)
- [Removing or updating the mod](#removing-or-updating-the-mod)
- [Questions and problems](#questions-and-problems)
- [For developers](#for-developers)
- [Credits and license](#credits-and-license)

## What the mod adds

**Playing on a single screen**

- Menus normally displayed on the bottom screen are moved to the top screen, including the title screen and main menu, quest list, Canteen, yes/no prompts and menu descriptions.
- Shops, equipment sets, the Melding Pot, Palico menus, help screens, tutorials and the Arena are also displayed on the top screen, along with the Gathering Hall's menus, Guild Cards, friends, chat and gestures.
- Character creation also takes place on the top screen, and you can enter character names using the D-pad.
- In towns and Gathering Halls, X opens the World Map on the top screen, while L displays the town map.
- In a Gathering Hall, a box in the top-left corner displays each hunter's weapon, name, Hunter Rank and ticket.
- On the Guild Card, Y hides the menus surrounding the hunters so you can take pictures (press X while editing the card).
- The touchscreen remains fully functional whenever the bottom screen is visible.

**Locking on with L**

- Hold L and press Up on the D-pad to lock on to a large monster or switch between targets. The target monster's face is displayed on the top screen.

**A smaller HUD**

- The HUD elements displayed over the game (clock, health, stamina, sharpness, item selector, minimap, talk windows during quests, etc.) can be scaled down, moving towards their respective corners. Available sizes are 90%, 80%, 70% and 60%. The default size is 70%.

**Built-in cheats**

- Disable 3D, glow and distant blur for a sharper image. These cheats are enabled by default.
- Other available cheats are disabled by default: a fixed frame rate (30 or 60 FPS), adjustable camera field of view, and longer wait times when joining online rooms.

The full list of changes can be found in the **[changelog](CHANGELOG.md)**.

## What you need

1. **A Windows computer.** On other operating systems, you can run the program using Python (see the end of the installation instructions).
2. **The Azahar emulator** ([azahar-emu.org](https://azahar-emu.org/)) or Citra.
3. **Your own decrypted copy of Monster Hunter 4 Ultimate (European or American version).** Supported formats are `.3ds`, `.cia`, and Azahar's compressed `.zcci` or `.zcia` formats.

   You can dump your own copy from a cartridge or 3DS using a homebrewed console ([how to dump your games](https://3ds.hacks.guide/dumping-titles-and-game-cartridges.html)). This project does not include or distribute any game files.

   The game update is optional; the mod works with or without it installed.

## Installation

**1. Download the program.** Download `HeavenfallBeta-windows.zip` from the latest "Heavenfall Single-Screen Mod" release on the [Releases page](../../releases/latest) and extract it anywhere (for example, on your Desktop).

**2. Open it.** Double-click `HeavenfallBeta.exe`. Since the program is not digitally signed, Windows may display a "Windows protected your PC" warning. If you downloaded it from the official repository, click **More info**, then **Run anyway**. The program automatically selects English or Spanish based on your system language. You can change it at the bottom of the left panel.

**3. Select your game file.** On the **Install** page, the program automatically looks for your game in your emulator's game folders, Downloads, Desktop and Documents. If it can't find it, click **Choose…** and select the file manually. The program will identify which region it belongs to.

**4. Check the destination.** The program automatically detects your Azahar or Citra installation. If it can't find it, click **Choose folder…** and select your emulator's folder.

**5. Choose your options.** The **Options** page lets you configure Single Screen Mode, HUD size and cheats. Hover over any option to see what it does.

**6. Click Install.** Installation may take a few moments. If the emulator was running the game, restart emulation for the changes to take effect. If the Install button is disabled, the message below it explains what's missing.

**7. Play on a single screen.** In Azahar, select the **Single Screen** layout (View > Screen Layout).

**Running on other operating systems or from source:** Install [Python](https://www.python.org/downloads/) 3.10 or newer, download the source code using the green **Code** button on this page and selecting **Download ZIP**, then open a terminal in the extracted folder and run:

```bash
pip install -r requirements.txt
python -m core.gui
```

> **Tip:** Keep a backup of your save before installing a new mod, just in case.

## Removing or updating the mod

- **To uninstall:** Click **Uninstall** on the Install page. This restores the game to its original state. The program only removes the files it installed.
- **To change your options:** Change them on the Options page and click **Update** on the Install page (or **Apply now** on the Options page).

## Questions and problems

**Does this modify my game file?**

No. The program only reads your game file and installs the mod in a separate folder inside your emulator's mod directory.

**Do I need the game's update?**

No. The mod works with or without the game update installed.

**It says there are files from another mod.**

The destination already contains mod files that weren't installed by Heavenfall Beta. The program will ask before replacing them. Choose **No** if you want to keep the existing files.

**Can I use it on a real 3DS?**

No. Heavenfall Beta changes how the game is displayed for single-screen emulation, so it only works with Azahar or Citra.

**Should I use these cheats or my emulator's?**

I recommend using the cheats included with Heavenfall Beta. If you do, make sure to disable any equivalent cheats in your emulator to avoid applying the same cheat twice. You can enable or disable Heavenfall Beta's cheats on the Options page.

**I found a bug.**

Please report it in the **#bug-reports** channel on my Discord server, preferably. Alternatively, you can open an issue using the **Issues** tab on GitHub. In either case, please attach the `settings_.json` file from your emulator's mod folder. Check it for personal information before sharing it.

## For developers

Want to understand how the mod works or learn how to edit the game's menus yourself? These guides should help:

- [How it works](docs/how_it_works.md): what the mod changes in the game and how the installation is built.
- [Editing the interface](docs/editing_the_ui.md): capture the game's screens, view them as images, reposition their elements using simple coordinates and test your changes in the emulator.
- [Development](docs/develop/development.md): running the program from source, building the Windows executable and publishing a release.

## Credits and license

- **Developed by:** popzol and BlitzWOLF.
- **Cheats:** the field-of-view (FOV) code is by mikewii7, and the online fix is by Klark231. The visual and frame-rate cheats come from the Monster Hunter 4 Ultimate community.
- **Game data reference:** [Kiranico](https://mh4u.kiranico.com/).

**License:** This project is licensed under the [GNU General Public License v3.0 or later](LICENSE). See the license for the full terms and conditions.

Monster Hunter is a trademark of Capcom. This is an unofficial fan project, not affiliated with or endorsed by Capcom.
