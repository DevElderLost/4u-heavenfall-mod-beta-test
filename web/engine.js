// The mod's engine: Python for the browser (Pyodide) with Heavenfall Beta's code, and the calls the page needs from
// core/app/web.py. It knows nothing of the page: worker.js runs it in a browser, and it runs the same way anywhere else.

export const GAME_FOLDER = "/game";
export const XX_FOLDER = "/xx";      // MH XX's file, optional
const ZIP_PATH = "/tmp/mod.zip";

export class Engine {
  constructor(py, web) {
    this.py = py;
    this.web = web;
    this.read = { pieces: 0, bytes: 0 };    // what the last build read of the game files
  }

  // Python started from `indexURL`, with the zstandard package and `bundle` (the mod's code as a zip's bytes).
  static async start(loadPyodide, indexURL, bundle) {
    const py = await loadPyodide({ indexURL });
    await py.loadPackage("zstandard", { messageCallback: () => {} });
    py.unpackArchive(bundle, "zip", { extractDir: "/app" });
    py.runPython("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, '/app')");
    return new Engine(py, py.pyimport("core.app.web"));
  }

  // A game's file seen by Python in `folder` (GAME_FOLDER, or XX_FOLDER for MH XX's), through the file system `kind`
  // (a browser's File needs WORKERFS, which reads only the pieces asked for). Returns its path.
  mountGame(kind, options, name, folder = GAME_FOLDER) {
    const { FS } = this.py;
    if (FS.analyzePath(folder).exists) {
      FS.unmount(folder);
    } else {
      FS.mkdirTree(folder);
    }
    this.counted(FS.filesystems[kind].stream_ops);
    FS.mount(FS.filesystems[kind], options, folder);
    return `${folder}/${name}`;
  }

  // Each read of a file of `ops`'s file system counted in this.read: a phone's browser pays for each read of the
  // player's file, so their number is in the page's technical details.
  counted(ops) {
    ops.counter = this.read;
    if (ops.uncounted) return;
    ops.uncounted = ops.read;
    ops.read = function read(...args) {
      const done = ops.uncounted.apply(this, args);
      ops.counter.pieces += 1;
      ops.counter.bytes += done;
      return done;
    };
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

  checkXx(xx, language) {
    return this.plain(this.web.check_xx(xx, language));
  }

  // The mod: `result` (core/app/web.py, build) and `bytes`, the zip (null when it was refused). `xx`: MH XX's file's
  // path, or null. this.read says what it read of the game files.
  build(game, personal, language, stage, xx = null) {
    Object.assign(this.read, { pieces: 0, bytes: 0 });
    const options = this.py.toPy(personal);
    const result = this.plain(this.web.build(game, ZIP_PATH, options, language, stage, xx));
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
