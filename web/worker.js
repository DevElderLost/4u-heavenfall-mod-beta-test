// The page's worker: the engine runs here so the page keeps responding. Messages are handled one at a time, in order.
//   in:   start {build}; check {file, language}; checkXx {file, language}; build {file, xx, personal, language}
//   out:  started {seconds}; checked {result}; checkedXx {result}; stage {stage};
//         built {result, blob, seconds, memory, read: {pieces, bytes} of the game files}; failed {message}
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

function mounted(file, folder = GAME_FOLDER) {
  return engine.mountGame("WORKERFS", { files: [file] }, file.name, folder);
}

function check({ file, language }) {
  self.postMessage({ type: "checked", result: engine.check(mounted(file), language) });
}

function checkXx({ file, language }) {
  self.postMessage({ type: "checkedXx", result: engine.checkXx(mounted(file, XX_FOLDER), language) });
}

// `xx`: MH XX's File, or null
function build({ file, xx, personal, language }) {
  const began = performance.now();
  const stage = (name) => self.postMessage({ type: "stage", stage: name });
  const { result, bytes } = engine.build(mounted(file), personal, language, stage, xx && mounted(xx, XX_FOLDER));
  const blob = bytes && new Blob([bytes], { type: "application/zip" });
  self.postMessage({ type: "built", result, blob, seconds: (performance.now() - began) / 1000,
                     memory: engine.memory(), read: { ...engine.read } });
}

const HANDLERS = { start, check, checkXx, build };
let queue = Promise.resolve();

self.onmessage = ({ data }) => {
  queue = queue.then(() => HANDLERS[data.type](data)).catch((error) => {
    self.postMessage({ type: "failed", message: String(error?.message ?? error) });
  });
};
