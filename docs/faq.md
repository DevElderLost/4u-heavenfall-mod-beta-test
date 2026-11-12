# Questions and problems

[Back to the README](../README.md)

> **Warning for HD texture packs:** keep **Async custom texture loading** on in the emulator's settings. With it off, Azahar 2126.2 and AzaharPlus 2126.2-A can crash with any pack, with or without the mod, and OpenGL does not prevent it. The fix comes with Azahar 2127.

**My antivirus says the program is a trojan.**

Some antivirus programs have wrongly flagged it (for example as "Bearfoo"), which can happen with new, unsigned programs. To check that your download is the official one, open PowerShell in the folder with the zip and run `Get-FileHash HeavenfallBeta-windows.zip`. Compare the long code it prints with the `sha256` shown beside that file on the [Releases page](https://github.com/popzol/4u-heavenfall-mod-beta/releases/latest); capital letters don't matter. If they match, you have the exact file published here, built by GitHub from this repository's public code. If they differ, delete it and download it again from that page.

**Does this modify my game file?**

No. The program only reads your game file and installs the mod in a separate folder inside your emulator's mod directory.

**Do I need the game's update?**

No. The mod works with or without the game update installed.

**Can I use an HD texture pack?**

Yes. Put the pack in the emulator's custom textures folder before you press **Install** in the program: the few textures the mod changes (icons, the quest HUD) get their own HD copies. If you add the pack later, press **Update**. Your pack's files are not changed. The web installer does not make these copies. If brackets, quotes or long dashes look wrong in texts with a pack, its picture of the game's letters was made from the game's update: delete `tex1_1024x1024_4C512887312E1BC2_11.png` from the pack to get the normal letters back.

**It says there are files from another mod.**

The destination already contains mod files that weren't installed by Heavenfall Beta. The program will ask before deleting them: saying yes deletes everything in that folder, with no backup. Choose **No** if you want to keep the existing files.

**Can I use it on a real 3DS?**

Yes, with custom firmware: the Heavenfall Launcher app installs it as a game of its own ([installing on a real 3DS](install/3ds.md)). Single Screen Mode is for emulators only.

**Should I use these cheats or my emulator's?**

Use the mod's cheats (START, third page, Mod Settings); emulator cheats will create bugs or crash the game

**I found a bug.**

Please report it in the **#bug-reports** channel on my Discord server, preferably. Alternatively, you can open an issue using the **Issues** tab on GitHub. In either case, please attach the `settings_.json` file from your emulator's mod folder. Check it for personal information before sharing it.
