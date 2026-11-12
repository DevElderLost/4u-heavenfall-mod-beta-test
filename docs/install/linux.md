# Installing on Linux or macOS

[Back to the README](../../README.md)

On Linux and macOS the program runs from its source code with Python. If you'd rather install nothing, the [web installer](android.md#the-web-installer) works on a PC too.

## What you need

1. [Python](https://www.python.org/downloads/) 3.12 or newer.
2. The **Azahar** emulator ([azahar-emu.org](https://azahar-emu.org/)) or Citra; installed from Flatpak works too.
3. Your own decrypted copy of Monster Hunter 4 Ultimate (European or American), and optionally Monster Hunter XX (Japanese).

## Steps

1. On the [repository's page](https://github.com/popzol/4u-heavenfall-mod-beta), click the green **Code** button, then **Download ZIP**, and extract it.
2. Open a terminal in the extracted folder and run:

   ```bash
   sh run.sh
   ```

   The first time, it downloads what the program needs into a `.venv` folder, which takes a few minutes; after that it opens right away.
3. Follow the program's steps as on Windows, from step 3 of [installing on Windows](windows.md#steps): your game, the destination, your options, **Install**.

If the window doesn't open on Linux and the terminal mentions `xcb-cursor`, install your system's `libxcb-cursor0` package.

**On Windows from source:** run `pip install -r requirements.txt` and then `python -m core.gui` instead.

## Updating or removing the mod

Download the latest source again and run `sh run.sh`; then click **Update** on the Install page. **Uninstall** on the same page removes the mod.

Problems? See [questions and problems](../faq.md).
