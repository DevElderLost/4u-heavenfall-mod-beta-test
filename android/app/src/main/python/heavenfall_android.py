"""The Android app's side of Python: the calls the Kotlin code makes into Heavenfall Beta's code.

The app unpacks the mod's code (the `core` package, bundled by android/app/build.gradle.kts) into its own folder and
gives that folder to `attach`. Everything else goes through core/app/web.py, the same module the web page runs in
Pyodide, so the app and the page build exactly the same mod. Every function takes and returns plain strings (JSON):
nothing here knows of Kotlin's types.
"""

import json
import sys
import traceback


def attach(code_dir: str) -> None:
    """Make the unpacked `core` package importable."""
    if code_dir not in sys.path:
        sys.path.insert(0, code_dir)


def options(language: str) -> str:
    """The Options page as JSON: sections, groups and options (core/app/web.py, options)."""
    from core.app import web
    return json.dumps(web.options(language), ensure_ascii=False)


def check(game: str, language: str) -> str:
    """The game file at `game`, as JSON: {ok, problem} or {ok, title, region} (core/app/web.py, check_game)."""
    try:
        from core.app import web
        return json.dumps(web.check_game(game, language), ensure_ascii=False)
    except Exception as error:      # a file that cannot be read at all: the app shows it instead of crashing
        return json.dumps({"ok": False, "problem": f"{type(error).__name__}: {error}"}, ensure_ascii=False)


def build(game: str, zip_path: str, personal_json: str, language: str, listener) -> str:
    """The mod of the game at `game` as the zip `zip_path`, with the options in `personal_json`. `listener` is a
    Kotlin object whose onStage(name) is told each stage ("rom", "write", "zip"). Returns core/app/web.py's `build`
    result as JSON; an error it does not expect comes back as {ok: false, problem, detail}."""
    try:
        from core.app import web
        personal = json.loads(personal_json)
        result = web.build(game, zip_path, personal, language, stage=lambda name: listener.onStage(name))
        return json.dumps(result, ensure_ascii=False)
    except Exception as error:
        return json.dumps({"ok": False, "problem": f"{type(error).__name__}: {error}",
                           "detail": traceback.format_exc()[-2000:]}, ensure_ascii=False)
