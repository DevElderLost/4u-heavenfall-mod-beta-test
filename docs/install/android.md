# Installing on Android

[Back to the README](../../README.md)

There are two ways to play on Android:

- **The Heavenfall app**: the game runs on the phone itself, with no emulator. American game only.
- **Azahar**: you make the mod in your browser with the web installer and play it in the emulator. European or American game.

## The Heavenfall app

Heavenfall for Android sets the mod up, keeps it up to date and starts the game. Nothing of the game is in the app: it makes the mod from your own copy of the game and builds the game's code on your phone. It is a modified version of [4u-native](https://github.com/khorne-hub/4u-native) by khorne-hub.

### What you need

1. A 64-bit phone with Android 9 or later.
2. Your own decrypted copy of the **American** Monster Hunter 4 Ultimate (a `.3ds`, `.cci` or `.cxi` file) and of its **1.3.0 update** (a `.cia` file), on the phone.
3. Optionally, your own decrypted copy of Monster Hunter XX (Japanese): Layered Gear then has its looks too.

### Installing

1. Download `Heavenfall-android.apk` from https://github.com/popzol/heavenfall-recomp-android/releases/latest and install it.
2. Open the app and follow its guide: let it read files, and choose the folder that holds your game files. The app checks each file and says what is wrong with it.
3. Press **Install**. The app downloads the mod's files, makes the mod and builds the game's code. Building is the long part: about 40 minutes on a mid-range phone, longer on a modest one. Keep the phone plugged in; you can leave the app and use the phone, a notification shows the progress. A later update with new code rebuilds only what changed, in a few minutes.
4. Press **Play**.

If the phone restarts or you cancel, **Resume** goes on from where it stopped. Before it starts, the app says so if the phone has too little free space or memory.

### Updating

When a new version is out, the button says **Update to** it. One press updates the app, the mod and, only when the mod's code changed, the part of the game's code that changed.

### Good to know

- The app has no options page: the mod comes with Single Screen Mode on and the HUD at its full size, and what the game's own Mod Settings offer (START menu, third page) is changed there.
- The game's code built on your phone and the mod's folder hold the game: keep them to yourself and never share them.
- The app is its own install, with its own save: it shares nothing with Azahar.
- Everything else (controls, graphics, bringing a save in or out) is in the app's settings, as in 4u-native.

## Azahar and the web installer

### What you need

1. Azahar for Android.
2. Your own decrypted copy of Monster Hunter 4 Ultimate (European or American) on your device, and optionally Monster Hunter XX (Japanese).
3. A recent version of Chrome or Firefox.

### The web installer

**https://popzol.github.io/4u-heavenfall-mod-beta/** makes the same mod as the program, in your browser, with nothing to install. Your game is never uploaded: everything happens on your device.

1. Open the page and choose your game file. Optionally, also choose your copy of Monster Hunter XX: Layered Gear then has its looks too, and the mod takes longer to make.
2. Change the options if you want, press **Make the mod** and keep the page open until it finishes.
3. Download the zip and extract it. Inside is a folder named `0004000000126100` (European game) or `0004000000126300` (American game).
4. Move that folder into `load/mods/` inside Azahar's user folder. It must end up as `load/mods/0004000000126100/romfs`. The page shows the steps for your device.
5. Choose the **Single Screen** layout in Azahar and open the game.

### Updating or removing the mod

- **To uninstall:** delete the mod's folder from `load/mods/`. To play Monster Hunter 4 Ultimate without the mod this is all it takes: your hunters are already in MH4U's save, and what only Heavenfall Beta has comes back when you make the mod again ([details](../back_to_mh4u.md)).
- **To update or change your options:** delete that folder too, then make the mod again and move in the new folder: old files left behind would still be loaded.

With an HD texture pack, the game's own pictures keep their HD look; the mod's own marks (the weapon tree's marks, the item wheel, the item stars, the target hint, the damage numbers) show at normal resolution, since the web installer cannot add HD pictures for them.

Problems? See [questions and problems](../faq.md).
