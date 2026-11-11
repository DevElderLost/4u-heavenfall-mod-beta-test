// The page: its texts, the options (options.json, drawn here), and the worker that checks the game and builds the mod.
// document.body.dataset.state says where it is: loading, idle, checking, ready, refused, building, built or failed.

const TEXTS = {
  es: {
    otherLanguage: "English",
    tagline: "Crea el mod de pantalla única en tu navegador, sin instalar nada.",
    privacy: "Todo se hace en este dispositivo: tu juego no se sube a ningún sitio.",
    gameTitle: "1. Elige tu juego",
    gameHelp: "Tu copia descifrada de Monster Hunter 4 Ultimate, europea o americana (.3ds, .cia, .zcci o .zcia). "
      + "El archivo no se modifica.",
    choose: "Elegir archivo",
    gameMissing: "¿No ves tu juego?",
    androidMissing: "Abre el menú lateral del selector y entra en el almacenamiento del móvil o en la tarjeta SD.",
    deckMissing: "Si el navegador no ve la tarjeta SD, copia el juego a Descargas o dale permiso con Flatseal, que se "
      + "instala desde Discover.",
    pcMissing: "Búscalo donde lo guardaste: el navegador puede abrir cualquier carpeta de tu PC.",
    engine: "Preparando el motor (la primera vez descarga unos 15 MB)…",
    checking: "Comprobando el juego…",
    gameGood: "✓ Monster Hunter 4 Ultimate, {region}: {name}",
    gameBad: "✗ {problem}",
    optionsTitle: "2. Opciones",
    optionsHelp: "Las opciones por defecto valen para casi todo el mundo: pantalla única, HUD al 70 % e imagen más "
      + "nítida. Cada módulo (pantalla única, equipo superpuesto, otros) tiene su interruptor: apagado, el juego queda "
      + "como el original en todo lo suyo. Los trucos, fijar monstruos con L y mantener A también se cambian dentro del juego: menú START, "
      + "tercera página, Ajustes del mod.",
    optionsShow: "Ver y cambiar opciones",
    reset: "Restablecer",
    buildTitle: "3. Crea el mod",
    build: "Crear el mod",
    needGame: "Elige primero tu juego.",
    stageRom: "Leyendo tu juego…",
    stageWrite: "Creando el mod…",
    stageZip: "Empaquetándolo…",
    elapsed: "{text} {seconds} s. Puede tardar un par de minutos: deja esta página abierta.",
    built: "✓ Mod creado: {files} archivos, {size} MB, en {seconds} s.",
    leftOut: "Se ha dejado fuera: {notices}",
    download: "Descargar {name}",
    changed: "Has cambiado las opciones: vuelve a crear el mod.",
    failed: "✗ No se pudo crear el mod: {message}",
    noMemory: "✗ Este dispositivo se ha quedado sin memoria. Cierra otras aplicaciones y vuelve a intentarlo.",
    noEngine: "✗ No se pudo iniciar el motor. Comprueba tu conexión; si sigue igual, actualiza el navegador o usa una "
      + "versión reciente de Chrome o Firefox.",
    unsupported: "Este navegador no puede ejecutar esta página. Actualízalo o usa una versión reciente de Chrome o "
      + "Firefox.",
    noFiles: "No se han podido cargar los archivos de la página. Comprueba tu conexión y recárgala.",
    installTitle: "4. Instálalo",
    deleteOld: "Si ya tenías el mod, borra antes la carpeta <code>{title}</code> que hay en <code>load/mods</code>: "
      + "al ponerla encima quedarían archivos viejos que el juego seguiría cargando.",
    move: "Mueve allí la carpeta <code>{title}</code>. Tiene que quedar <code>load/mods/{title}/romfs</code>; con una "
      + "carpeta de más por medio, el mod no carga y no avisa.",
    androidSteps: [
      "Descarga el zip y descomprímelo con tu gestor de archivos. Dentro está la carpeta <code>{title}</code>.",
      "Con el gestor de archivos, entra en la carpeta de usuario de Azahar (la que elegiste al abrirlo por primera "
        + "vez) y luego en <code>load/mods</code>. Si <code>mods</code> no existe, créala.",
      "{deleteOld}",
      "{move}",
      "Abre el juego y, en el menú de Azahar durante la partida, elige el diseño de pantalla «Single Screen» "
        + "(pantalla única).",
    ],
    deckSteps: [
      "En el Modo Escritorio, descarga el zip y descomprímelo (clic derecho, Extraer). Dentro está la carpeta "
        + "<code>{title}</code>.",
      "En Azahar, abre <code>File &gt; Open Azahar Folder &gt; User Folder</code> y entra en <code>load/mods</code>. "
        + "Si <code>mods</code> no existe, créala.",
      "{deleteOld}",
      "{move}",
      "En Azahar, elige <code>View &gt; Screen Layout &gt; Single Screen</code> y abre el juego.",
    ],
    pcSteps: [
      "Descarga el zip y descomprímelo. Dentro está la carpeta <code>{title}</code>.",
      "En Azahar, abre <code>File &gt; Open Azahar Folder &gt; User Folder</code> (en Citra, su carpeta de usuario) y "
        + "entra en <code>load/mods</code>. Si <code>mods</code> no existe, créala.",
      "{deleteOld}",
      "{move}",
      "En el emulador, elige <code>View &gt; Screen Layout &gt; Single Screen</code> y abre el juego.",
    ],
    otherRegion: "Esta es la carpeta del juego europeo; la del americano es <code>{other}</code>. Al elegir tu juego "
      + "se muestra la tuya.",
    deckUntested: "Estos pasos aún no se han probado en una Steam Deck real. Si algo no coincide, avisa y adjunta los "
      + "datos técnicos.",
    diagnostics: "Datos técnicos",
    diagnosticsHelp: "Si algo falla, copia esto en tu aviso de error.",
    windows: "En Windows es más cómodo el programa: instala el mod en el emulador por ti y lo quita con un botón.",
    programLink: "Descargar el programa",
    source: "Código fuente",
    license: "Licencia",
    thirdParty: "Otros componentes",
    trademark: "Esta página no incluye ni distribuye archivos del juego. Monster Hunter es una marca de Capcom; este "
      + "proyecto no está afiliado a Capcom ni a Nintendo.",
  },
  en: {
    otherLanguage: "Español",
    tagline: "Make the single-screen mod in your browser, with nothing to install.",
    privacy: "Everything happens on this device: your game is never uploaded.",
    gameTitle: "1. Choose your game",
    gameHelp: "Your decrypted copy of Monster Hunter 4 Ultimate, European or American (.3ds, .cia, .zcci or .zcia). "
      + "The file is never modified.",
    choose: "Choose file",
    gameMissing: "Can't see your game?",
    androidMissing: "Open the picker's side menu and go to your phone's storage or SD card.",
    deckMissing: "If the browser can't see the SD card, copy the game to Downloads or give it permission with Flatseal, "
      + "which you can install from Discover.",
    pcMissing: "Look for it where you saved it: the browser can open any folder on your PC.",
    engine: "Getting the engine ready (the first time downloads about 15 MB)…",
    checking: "Checking the game…",
    gameGood: "✓ Monster Hunter 4 Ultimate, {region}: {name}",
    gameBad: "✗ {problem}",
    optionsTitle: "2. Options",
    optionsHelp: "The default options suit most players: single screen, the HUD at 70% and a sharper picture. Each "
      + "module (single screen, Layered gear, other) has its own switch: off, the game stays as the original in "
      + "everything it holds. The cheats, the lock-on with L and holding A can also be changed inside the game: START menu, third page, "
      + "Mod Settings.",
    optionsShow: "See and change options",
    reset: "Reset",
    buildTitle: "3. Make the mod",
    build: "Make the mod",
    needGame: "Choose your game first.",
    stageRom: "Reading your game…",
    stageWrite: "Making the mod…",
    stageZip: "Packing it…",
    elapsed: "{text} {seconds} s. It may take a couple of minutes: keep this page open.",
    built: "✓ Mod ready: {files} files, {size} MB, in {seconds} s.",
    leftOut: "Left out: {notices}",
    download: "Download {name}",
    changed: "You changed the options: make the mod again.",
    failed: "✗ The mod could not be made: {message}",
    noMemory: "✗ This device ran out of memory. Close other apps and try again.",
    noEngine: "✗ The engine could not start. Check your connection; if it keeps failing, update your browser or use a "
      + "recent version of Chrome or Firefox.",
    unsupported: "This browser cannot run this page. Update it or use a recent version of Chrome or Firefox.",
    noFiles: "The page's files could not be loaded. Check your connection and reload it.",
    installTitle: "4. Install it",
    deleteOld: "If you already had the mod, first delete the <code>{title}</code> folder in <code>load/mods</code>: "
      + "copying over it would leave old files that the game would still load.",
    move: "Move the <code>{title}</code> folder there. It must end up as <code>load/mods/{title}/romfs</code>; with an "
      + "extra folder in between, the mod doesn't load and nothing tells you.",
    androidSteps: [
      "Download the zip and extract it with your file manager. Inside is the <code>{title}</code> folder.",
      "In the file manager, open Azahar's user folder (the one you chose when you first opened it), then "
        + "<code>load/mods</code>. If <code>mods</code> doesn't exist, create it.",
      "{deleteOld}",
      "{move}",
      "Open the game and, in Azahar's in-game menu, choose the \"Single Screen\" screen layout.",
    ],
    deckSteps: [
      "In Desktop Mode, download the zip and extract it (right click, Extract). Inside is the <code>{title}</code> "
        + "folder.",
      "In Azahar, open <code>File &gt; Open Azahar Folder &gt; User Folder</code> and go to <code>load/mods</code>. If "
        + "<code>mods</code> doesn't exist, create it.",
      "{deleteOld}",
      "{move}",
      "In Azahar, choose <code>View &gt; Screen Layout &gt; Single Screen</code> and open the game.",
    ],
    pcSteps: [
      "Download the zip and extract it. Inside is the <code>{title}</code> folder.",
      "In Azahar, open <code>File &gt; Open Azahar Folder &gt; User Folder</code> (in Citra, its user folder) and go to "
        + "<code>load/mods</code>. If <code>mods</code> doesn't exist, create it.",
      "{deleteOld}",
      "{move}",
      "In the emulator, choose <code>View &gt; Screen Layout &gt; Single Screen</code> and open the game.",
    ],
    otherRegion: "This is the European game's folder; the American game's is <code>{other}</code>. Yours appears once "
      + "you choose your game.",
    deckUntested: "These steps haven't been tried on a real Steam Deck yet. If something doesn't match, please report "
      + "it with the technical details.",
    diagnostics: "Technical details",
    diagnosticsHelp: "If something goes wrong, copy this into your bug report.",
    windows: "On Windows the program is easier: it installs the mod into the emulator for you and removes it with one "
      + "button.",
    programLink: "Download the program",
    source: "Source code",
    license: "License",
    thirdParty: "Other components",
    trademark: "This page does not include or distribute any game files. Monster Hunter is a trademark of Capcom; this "
      + "project is not affiliated with Capcom or Nintendo.",
  },
};
const EUR_TITLE = "0004000000126100";
const USA_TITLE = "0004000000126300";
const STAGE_TEXTS = { rom: "stageRom", write: "stageWrite", zip: "stageZip" };
const SAVED_OPTIONS = "heavenfall-beta-options";
const SAVED_LANGUAGE = "heavenfall-beta-language";

const page = {
  language: "en",
  platform: "android",
  build: null,            // build.json
  options: null,          // options.json
  values: {},             // the player's options by field
  file: null,             // the chosen game
  game: null,             // what core/app/web.py said of it (its text is in the language asked)
  worker: null,
  engineSeconds: null,
  building: null,         // while building: {began, text, timer, lock}
  result: null,           // the last mod made
  downloadUrl: null,
  failure: null,
};

const $ = (selector) => document.querySelector(selector);

function text(key, values = {}) {
  return fill(TEXTS[page.language][key], values);
}

function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (whole, name) => (name in values ? values[name] : whole));
}

function setState(state) {
  document.body.dataset.state = state;
  $("#build").disabled = !page.game?.ok || state === "building" || state === "checking";
  $("#game").disabled = state === "building";
  $("#progress").hidden = state !== "building";
}

function setStatus(selector, message, kind = "") {
  const status = $(selector);
  status.textContent = message;
  status.className = `status ${kind}`;
}

function savedJson(key) {
  try {
    return JSON.parse(localStorage.getItem(key)) ?? {};
  } catch {
    return {};
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // a browser with storage turned off: the options just aren't remembered
  }
}

// ---- language and platform ------------------------------------------------------------------------------------------

function firstLanguage() {
  const saved = savedJson(SAVED_LANGUAGE);
  if (saved === "es" || saved === "en") return saved;
  // the rule of the program (core/gui/i18n.py, language_for_locales)
  const tag = (navigator.languages?.[0] ?? navigator.language ?? "").toLowerCase();
  return tag.split("-")[0] === "es" ? "es" : "en";
}

// The device's install steps: a Steam Deck says only that it is Linux, so any Linux that is no Android opens on them.
function firstPlatform() {
  if (/android/i.test(navigator.userAgent)) return "android";
  return /linux|x11/i.test(navigator.userAgent) ? "deck" : "pc";
}

function drawTexts() {
  document.documentElement.lang = page.language;
  for (const element of document.querySelectorAll("[data-text]")) {
    element.textContent = text(element.dataset.text);
  }
  $("#language").textContent = text("otherLanguage");
  drawInstall();
  if (page.options) drawOptions();
  if (!page.file) setStatus("#build-status", text("needGame"));
}

function drawInstall() {
  const title = page.game?.title ?? EUR_TITLE;
  const parts = { title, deleteOld: text("deleteOld", { title }), move: text("move", { title }) };
  const steps = TEXTS[page.language][`${page.platform}Steps`];
  $("#install-steps").replaceChildren(...steps.map((step) => {
    const item = document.createElement("li");
    item.innerHTML = fill(fill(step, parts), parts);
    return item;
  }));
  const note = $("#install-note");
  note.hidden = Boolean(page.game?.title);
  note.innerHTML = text("otherRegion", { other: USA_TITLE });
  $("#install-untested").hidden = page.platform !== "deck";
  $("#install-program").hidden = page.platform !== "pc";
  $("#game-missing").textContent = text(`${page.platform}Missing`);
  for (const tab of document.querySelectorAll(".tab")) {
    tab.setAttribute("aria-pressed", String(tab.dataset.platform === page.platform));
  }
}

// ---- options --------------------------------------------------------------------------------------------------------

function element(tag, properties = {}, ...children) {
  const made = Object.assign(document.createElement(tag), properties);
  made.append(...children.filter((child) => child !== null && child !== undefined));
  return made;
}

function helpOf(help) {
  return help ? element("p", { className: "help", textContent: help }) : null;
}

function allOptions() {
  return page.options[page.language].flatMap((section) => section.groups.flatMap((group) => group.options));
}

function isValid(option, value) {
  if (option.kind === "bool") return typeof value === "boolean";
  if (option.kind === "number") return Number.isInteger(value) && value >= option.minimum && value <= option.maximum;
  return option.choices.some((choice) => choice.value === value);
}

function startingValues() {
  const saved = savedJson(SAVED_OPTIONS);
  return Object.fromEntries(allOptions().map((option) => (
    [option.field, isValid(option, saved[option.field]) ? saved[option.field] : option.default])));
}

// A bool on, or a choice not on its first value (core/gui/options.py, Option.requires).
function isOn(field) {
  const option = allOptions().find((candidate) => candidate.field === field);
  if (!option) return true;
  return option.kind === "choice" ? page.values[field] !== option.choices[0].value : Boolean(page.values[field]);
}

function isEnabled(option) {
  return (!option.requires || isOn(option.requires)) || Boolean(option.also_with && isOn(option.also_with));
}

// A mod already made no longer matches the options.
function optionsChanged() {
  save(SAVED_OPTIONS, page.values);
  refreshOptions();
  if (document.body.dataset.state === "built") {
    forgetMod();
    setStatus("#build-status", text("changed"));
    setState("ready");
  }
}

function optionChanged(field, value) {
  page.values[field] = value;
  optionsChanged();
}

function refreshOptions() {
  for (const option of allOptions()) {
    const box = document.querySelector(`[data-field="${option.field}"]`);
    const enabled = isEnabled(option);
    box.classList.toggle("off", !enabled);
    for (const control of box.querySelectorAll("input, select")) control.disabled = !enabled;
  }
  for (const hint of document.querySelectorAll("[data-hint]")) {
    const shown = JSON.parse(hint.dataset.hint);
    hint.textContent = shown.fields.every(isOn) ? shown.on : shown.off;
  }
}

function drawBool(option) {
  const input = element("input", { type: "checkbox", checked: page.values[option.field] });
  input.addEventListener("change", () => optionChanged(option.field, input.checked));
  return [element("label", { className: "line" }, input, element("span", { textContent: option.label })),
    helpOf(option.help)];
}

function drawSelect(option) {
  const select = element("select", { id: `option-${option.field}` }, ...option.choices.map((choice) => (
    element("option", { value: choice.value, textContent: choice.label }))));
  select.value = page.values[option.field];
  const chosenHelp = element("p", { className: "help" });
  const describe = () => {
    chosenHelp.textContent = option.choices.find((choice) => choice.value === select.value).help;
  };
  describe();
  select.addEventListener("change", () => {
    describe();
    optionChanged(option.field, select.value);
  });
  return [element("label", { className: "field", htmlFor: select.id, textContent: option.label }), helpOf(option.help),
    select, chosenHelp];
}

function drawRadios(option) {
  const radios = option.choices.map((choice) => {
    const input = element("input", { type: "radio", name: option.field, value: choice.value,
                                     checked: page.values[option.field] === choice.value });
    input.addEventListener("change", () => optionChanged(option.field, choice.value));
    return element("label", { className: "line" }, input, element("span", {},
      element("span", { textContent: choice.label }), helpOf(choice.help)));
  });
  return [element("fieldset", {}, element("legend", { textContent: option.label }), helpOf(option.help), ...radios)];
}

function drawNumber(option) {
  const input = element("input", { type: "range", id: `option-${option.field}`, min: option.minimum,
                                   max: option.maximum, step: option.step, value: page.values[option.field] });
  const shown = element("output", { textContent: page.values[option.field] });
  input.addEventListener("input", () => {
    shown.textContent = input.value;
  });
  input.addEventListener("change", () => optionChanged(option.field, Number(input.value)));
  return [element("label", { className: "field", htmlFor: input.id, textContent: option.label }), helpOf(option.help),
    element("div", { className: "number" }, input, shown)];
}

function drawOption(option) {
  const parts = option.kind === "bool" ? drawBool(option)
    : option.kind === "number" ? drawNumber(option)
      : option.compact ? drawSelect(option) : drawRadios(option);
  const box = element("div", { className: "option" }, ...parts);
  box.dataset.field = option.field;
  return box;
}

function drawGroup(group) {
  const hint = group.hint ? element("p", { className: "help" }) : null;
  if (hint) hint.dataset.hint = JSON.stringify(group.hint);
  // a group named as its first option would show the same words twice
  const title = group.title === group.options[0].label ? null
    : element("p", { className: "group-title", textContent: group.title });
  const warning = group.warning ? element("p", { className: "warning", textContent: group.warning }) : null;
  return element("div", { className: "group" }, title, warning, helpOf(group.description), hint,
    ...group.options.map(drawOption));
}

function drawOptions() {
  $("#options").replaceChildren(...page.options[page.language].flatMap((section) => [
    element("h3", { textContent: section.title }), ...section.groups.map(drawGroup)]));
  refreshOptions();
}

// ---- the worker -----------------------------------------------------------------------------------------------------

function stopWorker() {
  page.worker?.terminate();
  page.worker = null;
}

// A new worker starts empty: nothing of an earlier build stays in memory.
function theWorker() {
  if (!page.worker) {
    page.worker = new Worker("worker.js", { type: "module" });
    page.worker.onmessage = ({ data }) => HANDLERS[data.type](data);
    page.worker.onerror = (event) => engineFailed(event.message || "worker");
    page.engineSeconds = null;
    page.worker.postMessage({ type: "start", build: page.build });
  }
  return page.worker;
}

function engineFailed(detail) {
  page.failure = detail;
  stopWorker();
  stopBuilding();
  setStatus(page.game ? "#build-status" : "#game-status", text("noEngine"), "bad");
  setState("failed");
  drawDiagnostics();
}

const HANDLERS = {
  started({ seconds }) {
    page.engineSeconds = seconds;
    if (document.body.dataset.state === "checking") setStatus("#game-status", text("checking"));
    drawDiagnostics();
  },
  checked({ result }) {
    page.game = result;
    if (result.ok) {
      setStatus("#game-status", text("gameGood", { region: result.region, name: page.file.name }), "good");
      setStatus("#build-status", "");
      setState("ready");
    } else {
      setStatus("#game-status", text("gameBad", { problem: result.problem }), "bad");
      setStatus("#build-status", text("needGame"));
      setState("refused");
    }
    drawInstall();
  },
  stage({ stage }) {
    if (page.building) {
      page.building.text = text(STAGE_TEXTS[stage]);
      showElapsed();
    }
  },
  built({ result, blob, seconds, memory }) {
    stopWorker();
    stopBuilding();
    if (!result.ok) {
      page.failure = result.problem;
      setStatus("#build-status", text("failed", { message: result.problem }), "bad");
      setState("failed");
      drawDiagnostics();
      return;
    }
    page.result = { ...result, size: blob.size, seconds, memory };
    page.downloadUrl = URL.createObjectURL(blob);
    const link = $("#download");
    link.href = page.downloadUrl;
    link.setAttribute("download", result.zip_name);
    link.hidden = false;
    showBuilt();
    setState("built");
    drawDiagnostics();
  },
  failed({ message }) {
    if (page.engineSeconds === null) {
      engineFailed(message);
      return;
    }
    page.failure = message;
    stopWorker();
    stopBuilding();
    const key = /memory|MemoryError/i.test(message) ? "noMemory" : "failed";
    setStatus(page.game ? "#build-status" : "#game-status", text(key, { message }), "bad");
    setState("failed");
    drawDiagnostics();
  },
};

function showBuilt() {
  const { files, size, seconds, notices, zip_name: name } = page.result;
  $("#download").textContent = text("download", { name });
  const done = text("built", { files, size: (size / 1e6).toFixed(0), seconds: seconds.toFixed(0) });
  const leftOut = notices.length ? ` ${text("leftOut", { notices: notices.join("; ") })}` : "";
  setStatus("#build-status", done + leftOut, "good");
}

function forgetMod() {
  if (page.downloadUrl) URL.revokeObjectURL(page.downloadUrl);
  page.downloadUrl = null;
  page.result = null;
  $("#download").hidden = true;
}

function checkGame() {
  forgetMod();
  page.game = null;
  page.failure = null;
  setState("checking");
  setStatus("#game-status", page.worker ? text("checking") : text("engine"));
  setStatus("#build-status", "");
  theWorker().postMessage({ type: "check", file: page.file, language: page.language });
  drawInstall();
  drawDiagnostics();
}

function showElapsed() {
  const seconds = Math.round((performance.now() - page.building.began) / 1000);
  setStatus("#build-status", text("elapsed", { text: page.building.text, seconds }));
}

async function startBuilding() {
  forgetMod();
  page.failure = null;
  page.building = { began: performance.now(), text: text("stageRom"), timer: null, lock: null };
  page.building.timer = setInterval(showElapsed, 1000);
  showElapsed();
  setState("building");
  theWorker().postMessage({ type: "build", file: page.file, personal: page.values, language: page.language });
  try {
    // the screen stays on: a phone that sleeps may stop the page; a browser without it just skips this
    const lock = await navigator.wakeLock?.request("screen");
    if (page.building) page.building.lock = lock;
    else lock?.release();
  } catch {
    // refused (low battery, or a page without https): the build still goes on
  }
}

function stopBuilding() {
  if (!page.building) return;
  clearInterval(page.building.timer);
  page.building.lock?.release();
  page.building = null;
}

// ---- diagnostics ----------------------------------------------------------------------------------------------------

function drawDiagnostics() {
  const megabytes = (bytes) => `${(bytes / 1e6).toFixed(0)} MB`;
  const lines = [
    `Heavenfall Beta ${page.build?.version ?? "?"}, Pyodide ${page.build?.pyodide_version ?? "?"}`,
    `Browser: ${navigator.userAgent}`,
    `Memory of this device: ${navigator.deviceMemory ? `${navigator.deviceMemory} GB or more` : "unknown"}`,
    `Screen stays on: ${"wakeLock" in navigator ? "yes" : "no"}. Folder writing: ${"showDirectoryPicker" in window ? "yes" : "no"}.`,
  ];
  if (page.file) lines.push(`Game: ${megabytes(page.file.size)}`);
  if (page.engineSeconds !== null) lines.push(`Engine started in ${page.engineSeconds.toFixed(1)} s`);
  if (page.result) {
    lines.push(`Mod: ${page.result.title}, ${page.result.version}, ${page.result.files} files, `
      + `${megabytes(page.result.size)}, in ${page.result.seconds.toFixed(1)} s, memory ${megabytes(page.result.memory ?? 0)}`);
  }
  if (page.failure) lines.push(`Failure: ${page.failure}`);
  $("#diagnostics-text").textContent = lines.join("\n");
}

// ---- start ----------------------------------------------------------------------------------------------------------

function connect() {
  $("#language").addEventListener("click", () => {
    page.language = page.language === "es" ? "en" : "es";
    save(SAVED_LANGUAGE, page.language);
    drawTexts();
    if (page.result) showBuilt();
    else if (page.file && ["ready", "refused"].includes(document.body.dataset.state)) checkGame();
  });
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => {
      page.platform = tab.dataset.platform;
      drawInstall();
    });
  }
  // emptied each time, or choosing the same file again (after a failure) would change nothing and do nothing
  $("#game").addEventListener("click", (event) => {
    event.target.value = "";
  });
  $("#game").addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (!file) return;
    page.file = file;
    stopWorker();
    checkGame();
  });
  $("#reset").addEventListener("click", () => {
    save(SAVED_OPTIONS, {});
    page.values = startingValues();
    drawOptions();
    optionsChanged();
  });
  $("#build").addEventListener("click", startBuilding);
}

async function start() {
  page.language = firstLanguage();
  page.platform = firstPlatform();
  connect();
  drawTexts();
  drawDiagnostics();
  if (!window.Worker || !window.WebAssembly) {
    $("#unsupported").textContent = text("unsupported");
    $("#unsupported").hidden = false;
    return;
  }
  try {
    const load = async (name) => {
      const answer = await fetch(name, { cache: "no-cache" });
      if (!answer.ok) throw new Error(`${name}: ${answer.status}`);
      return answer.json();
    };
    [page.build, page.options] = await Promise.all([load("build.json"), load("options.json")]);
  } catch (error) {
    page.failure = String(error);
    $("#unsupported").textContent = text("noFiles");
    $("#unsupported").hidden = false;
    drawDiagnostics();
    return;
  }
  page.values = startingValues();
  drawOptions();
  drawDiagnostics();
  setState("idle");
}

start();
