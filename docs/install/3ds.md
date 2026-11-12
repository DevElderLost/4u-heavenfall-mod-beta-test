# Installing on a real 3DS

[Back to the README](../../README.md)

The **Heavenfall Launcher** app installs Heavenfall Beta on a 3DS or New 3DS, keeps it up to date and starts it. Heavenfall Beta is installed as a game of its own, with its own icon and its own save, next to your Monster Hunter 4 Ultimate, which is never changed. Single Screen Mode is for emulators only; on a console you get the rest of the mod, and Mod Settings (START, third page) changes what a console supports.

## What you need

1. A 3DS or New 3DS with custom firmware (Luma3DS): see [3ds.hacks.guide](https://3ds.hacks.guide/).
2. Your own decrypted copy of Monster Hunter 4 Ultimate (European or American), made with GodMode9 and left on the SD card in `gm9/out`, where GodMode9 saves it. For a cartridge, use its **trimmed** dump; for a digital copy, a decrypted CIA.
3. Optional: your own decrypted copy of Monster Hunter XX (Japanese), made the same way. With it, Layered Gear also has XX's looks and the Wyporium trades their rare materials.
4. About 3 GB of free space on the SD card, besides your copies, and an internet connection.

## Steps

1. **Install the launcher.** In FBI, choose **Remote Install > Scan QR Code** and scan this code:

   ![QR code of the launcher's CIA](launcher_qr.png)

   Or download `HeavenfallBeta-3ds.cia` from the [latest release](https://github.com/popzol/4u-heavenfall-mod-beta/releases/latest) and install it with FBI. (`HeavenfallBeta-3ds.3dsx` is the same app for the Homebrew Launcher.)
2. **Install the game.** Open **Heavenfall Launcher**. If it cannot find your copy yet, its guide shows how to make one with GodMode9. Choose **Install**: it downloads the latest version and builds the game from your copy, showing the time left (about 25 minutes on a New 3DS XL, a few more with Monster Hunter XX). The game's data is installed only this once: it shows in the console's Data Management as add-on content, and the game needs it. Keep the console charging.
   - The screens go dark while it works; any button wakes them, and **Keep the screens on** stops that.
   - Press B twice, or tap **Cancel** twice, to cancel: nothing is installed until it finishes.
   - The HOME button does nothing until it finishes.
3. **Play.** Choose **Play now**, or start Heavenfall Beta from the HOME Menu. After you have played once, the launcher offers to copy your Monster Hunter 4 Ultimate save into Heavenfall Beta, and both saves are backed up on the SD card first. **More** has the copy too.

## Updating

Open the launcher: when a new version is out, its big button says **Update to** and the version. An update takes a few minutes, since the game's data stays. Your Heavenfall Beta save stays too: the launcher backs it up and puts it back.

- If you copy Monster Hunter XX after installing, the launcher says it found it, and **Update** adds it.
- **More** has **Reinstall**, which installs the latest version again.
- The launcher also updates itself, then carries on by itself.
- SELECT switches it between English and Spanish. If the screens stay blank, hold SELECT while the launcher starts for a simpler display; hold R to bring the full one back.

Problems? See [questions and problems](../faq.md).
