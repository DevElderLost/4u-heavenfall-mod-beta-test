// The page's worker: the engine runs here so the page keeps responding. Messages are handled one at a time, in order.
//   in:   start {build}; check {file, language}; build {file, personal, language}
//   out:  started {seconds}; checked {result}; stage {stage}; built {result, blob, seconds, memory}; failed {message}
import { Engine } from "./engine.js";

let engine;

async function start({ build }) {
  const began = performance.now();
  const folder = new URL(`${build.pyodide}/`, self.location);
  const { loadPyodide } = await import(new URL("pyodide.mjs", folder).href);
  const bundle = await (await fetch(new URL(build.bundle, self.location))).arrayBuffer();
  engine = await Engine.start(loadPyodide, folder.href, bundle);
  self.postMessage({ type: "started", seconds: (performance.now() - began) / 1000 });
}

function mounted(file) {
  return engine.mountGame("WORKERFS", { files: [file] }, file.name);
}

function check({ file, language }) {
  self.postMessage({ type: "checked", result: engine.check(mounted(file), language) });
}

function build({ file, personal, language }) {
  const began = performance.now();
  const stage = (name) => self.postMessage({ type: "stage", stage: name });
  const { result, bytes } = engine.build(mounted(file), personal, language, stage);
  const blob = bytes && new Blob([bytes], { type: "application/zip" });
  self.postMessage({ type: "built", result, blob, seconds: (performance.now() - began) / 1000,
                     memory: engine.memory() });
}

const HANDLERS = { start, check, build };
let queue = Promise.resolve();

self.onmessage = ({ data }) => {
  queue = queue.then(() => HANDLERS[data.type](data)).catch((error) => {
    self.postMessage({ type: "failed", message: String(error?.message ?? error) });
  });
};
