# Playing Monster Hunter 4 Ultimate without the mod

[Back to the README](../README.md)

Heavenfall Beta plays on MH4U's own save, so your hunters are already in it. A hunter is ready for MH4U once Heavenfall Beta has saved it with room on the SD card: that save leaves MH4U's file clean. When Heavenfall Beta cannot write its own files (a full SD card), it keeps your hunter whole in MH4U's file instead, and MH4U shows the items it does not know as junk until Heavenfall Beta saves that hunter again with room. What only Heavenfall Beta has (Layered Gear, Mod Settings, the Jukebox) stays aside in files of its own and comes back when you install the mod again.

## On an emulator

Citra, Azahar or Lime3DS on Windows, Linux or macOS, and Azahar on Android.

1. Play your hunter in Heavenfall Beta and save it.
2. Uninstall the mod: **Uninstall** on the program's Install page. On Android, delete the mod's folder from `load/mods/` as [the Android page](install/android.md) installs it.
3. Start Monster Hunter 4 Ultimate as it was: your hunters are there.

To come back, install the mod again.

## On a 3DS

Heavenfall Beta is a game of its own there, with its own save. The Heavenfall Launcher's **More** has **MH4U saves**:

- **Take my save to MH4U** puts a hunter of Heavenfall Beta into your original Monster Hunter 4 Ultimate (cartridge or digital copy). It shows both saves' hunters and play time first, and warns when you would go back in time. Then start the original game.
- **Bring my MH4U save** goes the other way, for the whole save: it replaces all three of Heavenfall Beta's hunters and its system files with your original game's save. It does not choose a slot. It asks first, and names the backup folder on the SD card.
- **Restore MH4U's save** puts MH4U's save back as it was before the last **Take my save to MH4U**.

For **Take my save to MH4U** you choose the slot; the system files (the save's settings shared by the three slots, nothing of a hunter) have a button of their own. Both saves are backed up on the SD card before anything changes, in `3ds/heavenfall/heavenfall_beta/saves/`, one folder per date and time: Heavenfall Beta's save as it was before a **Bring** is there too. If MH4U is on a cartridge and also installed on the SD card, the launcher asks which one to use and shows it on the page. A hunter whose save still holds something MH4U does not have is refused: load and save it once in Heavenfall Beta first.

Keep each hunter in the same slot in both games. The two share each slot's Guild Card file, so when a slot holds one hunter in Heavenfall Beta and another in MH4U, each game's save replaces the other hunter's item sets, equipment sets and Guild Card book. The **MH4U saves** page marks such a slot with (!).
