# Heavenfall Beta for Android

The installer as an Android app: a Jetpack Compose interface on top of the program's own Python code, which runs
inside the app with [Chaquopy](https://chaquo.com/chaquopy/). It builds the same mod as the Windows program and the
web page (it calls `core/app/web.py`, the module the web page runs in Pyodide), from your own decrypted game file, and
puts it in Azahar's `load/mods/<title>/` folder. The game file is only read, never modified or uploaded.

## Use

1. Install the APK (see below) and open **Heavenfall Beta**.
2. **Install** page: choose your decrypted Monster Hunter 4 Ultimate (`.3ds` or `.cia`, European or American).
3. Choose Azahar's user folder (the one that holds `load/mods`). Azahar shows in the file picker's side menu.
   If your phone does not offer it, use **Save as zip…** and extract the zip in Azahar's user folder with a file
   manager, so that `load/mods/<title>/romfs` exists.
4. **Options** page: single screen, lock-on, HUD size, cheats (the program's own options).
5. Press **Install**, restart emulation, and choose the **Single Screen** layout in Azahar.

Azahar's compressed files (`.zcci`, `.zcxi`, `.zcia`) need the `zstandard` package, which Chaquopy may not have a wheel
for yet on Python 3.13. The app refuses them with a message; use the `.3ds` or `.cia`. To try them, build with
`-Pheavenfall.zstd=true` (it adds the package; the build fails if the wheel does not exist).

## Storage access

The file picker (SAF) is enough to use the app. On Android 11 and newer the Install page also offers **All files
access** (`MANAGE_EXTERNAL_STORAGE`): with it the game is read where it is and the mod is written as plain files, so
the game is not copied and installing again writes only the files that changed (each file is compared by size and
CRC32 with the one already in the folder; files the mod no longer has are deleted). Without it, or for a folder inside
another app's `Android/data` (which Android does not open even with that permission), the picker's URIs are used, with
the same comparison. When the picker gives no real file for the game, one copy is kept in the cache and reused until the
chosen file changes.

## Build

On GitHub: **Actions > Android app > Run workflow**, then download the `HeavenfallBeta-android` artifact (a zip with the
APK). Without a signing key the APK is signed with the runner's debug key, which changes on every run: Android then
asks you to uninstall the old app before installing a new one. To avoid it, create a key once and add these
repository secrets: `ANDROID_KEYSTORE_BASE64` (the `.jks` file in base64), `ANDROID_KEYSTORE_PASSWORD`,
`ANDROID_KEY_ALIAS` and `ANDROID_KEY_PASSWORD`.

On your own machine (JDK 17, Android SDK, Python 3.13 and Gradle 8.10 or newer):

```bash
gradle -p android assembleRelease                       # app/build/outputs/apk/release/
gradle -p android assembleRelease -Pheavenfall.abis=arm64-v8a    # a smaller APK, for phones only
```

## How it fits in

- `app/build.gradle.kts` zips `core/` (with the same skips as `tools/release/build_web.py`) into the APK's assets; the
  app unpacks it on its first start, because the code reads its data files by path.
- `app/src/main/python/heavenfall_android.py` is the only Python written for the app: it takes and returns JSON.
- `HeavenfallBridge.kt` runs it; `InstallViewModel.kt` holds the state; `ui/` is the Compose interface;
  `ModFolder.kt` writes the mod into the folder chosen with the system's folder picker.
- Texts of the options and of the game's problems come from the program (English and Spanish). The app's own
  texts are in `res/values` (English) and `res/values-in` (Indonesian).

Heavenfall Beta is released under the GNU General Public License, version 3 or later (see `LICENSE`).
