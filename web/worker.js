// The page's worker: the engine runs here so the page keeps responding. Messages are handled one at a time, in order.
//   in:   start {build}; checkKeys {keys}; check {file, keys, language}; checkXx {file, keys, language};
//         build {file, xx, keys, personal, language}
//   out:  started {seconds}; checkedKeys {result}; checked {result}; checkedXx {result}; stage {stage};
//         built {result, blob, seconds, memory}; failed {message}
// `keys`: the player's key files (aes_keys.txt or 3dskeys.txt, maybe seeddb.bin) as an array of Files, empty for none:
// an encrypted game is read with them.
import { Engine, GAME_FOLDER, XX_FOLDER } from "./engine.js";

let engine;

async function start({ build }) {
  const began = performance.now();
  const folder = new URL(`${build.pyodide}/`, self.location);
  const { loadPyodide } = await import(new URL("pyodide.mjs", folder).href);
  const bundle = await (await fetch(new URL(build.bundle, self.location))).arrayBuffer();
  engine = await Engine.start(loadPyodide, folder.href, bundle);
  self.postMessage({ type: "started", seconds: (performance.now() - began) / 1000 });
}

// The key files in use by Python: set again only when they are not the ones set last.
let keysInUse = "";
function useKeys(keys = []) {
  const id = keys.map((file) => `${file.name}:${file.size}:${file.lastModified}`).join("|");
  if (id === keysInUse && engine.keysMounted === keys.length > 0) return null;
  keysInUse = id;
  return engine.useKeys(keys);
}

function checkKeys({ keys }) {
  keysInUse = "";
  self.postMessage({ type: "checkedKeys", result: useKeys(keys) });
}

function mounted(file, folder = GAME_FOLDER) {
  return engine.mountGame("WORKERFS", { files: [file] }, file.name, folder);
}

function check({ file, keys, language }) {
  useKeys(keys);
  self.postMessage({ type: "checked", result: engine.check(mounted(file), language) });
}

function checkXx({ file, keys, language }) {
  useKeys(keys);
  self.postMessage({ type: "checkedXx", result: engine.checkXx(mounted(file, XX_FOLDER), language) });
}

// `xx`: MH XX's File, or null
function build({ file, xx, keys, personal, language }) {
  const began = performance.now();
  useKeys(keys);
  const stage = (name) => self.postMessage({ type: "stage", stage: name });
  const { result, bytes } = engine.build(mounted(file), personal, language, stage, xx && mounted(xx, XX_FOLDER));
  const blob = bytes && new Blob([bytes], { type: "application/zip" });
  self.postMessage({ type: "built", result, blob, seconds: (performance.now() - began) / 1000,
                     memory: engine.memory(), read: { ...engine.read } });
}

const HANDLERS = { start, checkKeys, check, checkXx, build };
let queue = Promise.resolve();

self.onmessage = ({ data }) => {
  queue = queue.then(() => HANDLERS[data.type](data)).catch((error) => {
    self.postMessage({ type: "failed", message: String(error?.message ?? error) });
  });
};
