# Heavenfall Beta: Play Monster Hunter 4 Ultimate on a Single Screen

**A fan-made mod for the European and American versions of Monster Hunter 4 Ultimate (3DS), designed for playing on a single screen in an emulator, and playable on a real 3DS too.**

Heavenfall Beta moves the menus of the bottom screen to the top screen, locks on to monsters without the touchscreen, scales down the HUD and adds Layered Gear, quality-of-life options and built-in cheats. Your game file is never modified.

> **Disclaimer:** Heavenfall Beta is an unofficial fan project, not affiliated with or endorsed by Capcom or Nintendo. It contains no game files: you need your own copy of the game, dumped from your own cartridge or console. It is provided as is, without any warranty (GPL v3). Back up your saves before installing; on a 3DS, custom firmware and homebrew are your own responsibility.

## Links

- **Downloads:** https://github.com/popzol/4u-heavenfall-mod-beta/releases/latest
- **Web installer**, with nothing to install: https://popzol.github.io/4u-heavenfall-mod-beta/
- **Discord server**, for help, bug reports, feedback and news: https://discord.gg/qQwPRc8CDF

## Install it

| Where you play | How |
|---|---|
| **Windows** (Azahar or Citra) | [The Windows program](docs/install/windows.md) |
| **Linux or macOS** (Azahar or Citra) | [The program from a script](docs/install/linux.md), or the web installer |
| **Android** (Azahar) | [The web installer](docs/install/android.md) |
| **Steam Deck** (Azahar) | [The web installer or the Linux script](docs/install/steam_deck.md) |
| **A real 3DS or New 3DS** (custom firmware) | [The Heavenfall Launcher app](docs/install/3ds.md) |

On every platform you need **your own decrypted copy of Monster Hunter 4 Ultimate** (European or American; the update is optional). **Your own decrypted copy of Monster Hunter XX** (Japanese) is optional: with it, Layered Gear also has XX's looks. You can dump your games from a cartridge or a 3DS with custom firmware ([how to dump your games](https://3ds.hacks.guide/dumping-titles-and-game-cartridges.html)).

> **Status:** Beta. It works with **Azahar** and **Citra** on PC, with **Azahar** on Android, and on a real 3DS through the launcher (without Single Screen Mode, which is for emulators only). It has not been tried on a real Steam Deck yet.

## What the mod adds

- **Single Screen Mode** (emulators): every menu of the bottom screen on the top screen.
- **Lock-on with L**, **Kick on Select**, **holding A** to keep gathering, **faster text** and a **faster camera**.
- **A smaller HUD**, from 90% to 60%.
- **Layered Gear** at the Smithy: wear the look of any armor, weapon or Felyne gear over your own, with Monster Hunter XX's looks too, and the Wyporium's Rare Materials Exchange.
- **Built-in cheats**: 3D, glow and blur off, frame rate, field of view and more.

The full list is in **[what the mod adds](docs/features.md)**, and every change in the **[changelog](CHANGELOG.md)**.

## Help

- **[Questions and problems](docs/faq.md)**: antivirus warnings, HD texture packs, other mods, cheats and how to report a bug.
- **Updating or removing the mod:** see your platform's page above.

## For developers

- [How it works](docs/how_it_works.md): what the mod changes in the game and how the installation is built.
- [Editing the interface](docs/editing_the_ui.md): capture the game's screens, reposition their elements and test your changes.
- [Development](docs/develop/development.md): running the program from source, building it and publishing a release.

## Credits and license

- **Developed by:** popzol and BlitzWOLF.
- **Cheats:** the field-of-view (FOV) code is by mikewii7, and the online fix is by Klark231. The visual and frame-rate cheats come from the Monster Hunter 4 Ultimate community.
- **Game data reference:** [Kiranico](https://mh4u.kiranico.com/).
- **Linux start script:** based on the one hndll56 contributed.

**License:** [GNU General Public License v3.0 or later](LICENSE). Monster Hunter is a trademark of Capcom. This is an unofficial fan project, not affiliated with or endorsed by Capcom.
