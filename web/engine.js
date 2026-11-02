// The mod's engine: Python for the browser (Pyodide) with Heavenfall Beta's code, and the calls the page needs from
// core/app/web.py. It knows nothing of the page: worker.js runs it in a browser, and it runs the same way anywhere else.

const GAME_FOLDER = "/game";
const ZIP_PATH = "/tmp/mod.zip";

export class Engine {
  constructor(py, web) {
    this.py = py;
    this.web = web;
  }

  // Python started from `indexURL`, with the zstandard package and `bundle` (the mod's code as a zip's bytes).
  static async start(loadPyodide, indexURL, bundle) {
    const py = await loadPyodide({ indexURL });
    await py.loadPackage("zstandard", { messageCallback: () => {} });
    py.unpackArchive(bundle, "zip", { extractDir: "/app" });
    py.runPython("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, '/app')");
    return new Engine(py, py.pyimport("core.app.web"));
  }

  // The game's file seen by Python, through the file system `kind` (a browser's File needs WORKERFS, which reads only
  // the pieces asked for). Returns its path.
  mountGame(kind, options, name) {
    const { FS } = this.py;
    if (FS.analyzePath(GAME_FOLDER).exists) {
      FS.unmount(GAME_FOLDER);
    } else {
      FS.mkdirTree(GAME_FOLDER);
    }
    FS.mount(FS.filesystems[kind], options, GAME_FOLDER);
    return `${GAME_FOLDER}/${name}`;
  }

  // A Python dict as a plain object.
  plain(result) {
    const value = result.toJs({ dict_converter: Object.fromEntries });
    result.destroy();
    return value;
  }

  check(game, language) {
    return this.plain(this.web.check_game(game, language));
  }

  // The mod: `result` (core/app/web.py, build) and `bytes`, the zip (null when it was refused).
  build(game, personal, language, stage) {
    const options = this.py.toPy(personal);
    const result = this.plain(this.web.build(game, ZIP_PATH, options, language, stage));
    options.destroy();
    if (!result.ok) {
      return { result, bytes: null };
    }
    const bytes = this.py.FS.readFile(ZIP_PATH);
    this.py.FS.unlink(ZIP_PATH);
    return { result, bytes };
  }

  // The bytes of WebAssembly memory in use by now (it never shrinks, so also its highest).
  memory() {
    return this.py._module?.HEAP8?.length ?? null;
  }
}
