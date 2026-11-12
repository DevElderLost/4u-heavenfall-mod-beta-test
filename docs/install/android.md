# Installing on Android

[Back to the README](../../README.md)

On Android you make the mod in your browser with the web installer, and play it in **Azahar**.

## What you need

1. Azahar for Android.
2. Your own decrypted copy of Monster Hunter 4 Ultimate (European or American) on your device, and optionally Monster Hunter XX (Japanese).
3. A recent version of Chrome or Firefox.

## The web installer

**https://popzol.github.io/4u-heavenfall-mod-beta/** makes the same mod as the program, in your browser, with nothing to install. Your game is never uploaded: everything happens on your device.

1. Open the page and choose your game file. Optionally, also choose your copy of Monster Hunter XX: Layered Gear then has its looks too, and the mod takes longer to make.
2. Change the options if you want, press **Make the mod** and keep the page open until it finishes.
3. Download the zip and extract it. Inside is a folder named `0004000000126100` (European game) or `0004000000126300` (American game).
4. Move that folder into `load/mods/` inside Azahar's user folder. It must end up as `load/mods/0004000000126100/romfs`. The page shows the steps for your device.
5. Choose the **Single Screen** layout in Azahar and open the game.

## Updating or removing the mod

- **To uninstall:** delete the mod's folder from `load/mods/`.
- **To update or change your options:** delete that folder too, then make the mod again and move in the new folder: old files left behind would still be loaded.

The web installer does not make HD copies of the textures the mod changes for an HD texture pack.

Problems? See [questions and problems](../faq.md).
