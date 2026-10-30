# PyInstaller spec of the app (python tools/build_exe.py runs it; every list comes from tools/build_exe.py, the names from
# data/curated/edition.json). One folder, two programs: <app>.exe (windowed, the app) and <cli>.exe (the command line).
import os
import sys

sys.path.insert(0, SPECPATH)
import build_exe as cfg  # noqa: E402

ICON = os.environ.get(cfg.ICON_ENV) or None


def analysis(script, gui):
    return Analysis(
        [str(cfg.LAUNCHERS / script)],
        pathex=[str(cfg.ROOT)],
        datas=cfg.data_files(),
        hiddenimports=cfg.package_modules(gui),
        excludes=cfg.excludes(gui),
        noarchive=False,
    )


app = analysis("duality.py", gui=True)
cli = analysis("duality_cli.py", gui=False)
for part in (app, cli):
    part.binaries = [entry for entry in part.binaries if not cfg.dropped(entry[0])]
    part.datas = [entry for entry in part.datas if not cfg.dropped(entry[0])]

app_exe = EXE(PYZ(app.pure), app.scripts, [], exclude_binaries=True, name=cfg.APP_NAME, console=False, icon=ICON,
              upx=False)
cli_exe = EXE(PYZ(cli.pure), cli.scripts, [], exclude_binaries=True, name=cfg.CLI_NAME, console=True, icon=ICON,
              upx=False)
COLLECT(app_exe, app.binaries, app.datas, cli_exe, cli.binaries, cli.datas, name=cfg.APP_NAME, upx=False)
