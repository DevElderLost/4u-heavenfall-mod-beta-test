"""The texts of the game GUI tools: the recorder's window and statuses, the checker's report, the
gallery, `tools/ui.py` and the recording probe, in Spanish and English.

The language is the edition's `tools_language` (data/curated/edition.json: Spanish in Heavenfall, English in an
edition such as Heavenfall Beta) unless a command line's `--lang` chose another (`set_language`). Screens, blocks and the
recorder's list of screens to record show their English names in English (`names_en.json`, read by config.py and
recorder/coverage.py), their Spanish ones otherwise. The archived editor (gamegui/editor/) stays in Spanish."""

from ..edition import edition
from ..i18n import T

_chosen: str | None = None


def language() -> str:
    """The tools' language: "es" or "en"."""
    return _chosen or edition().tools_language


def set_language(code: str | None) -> None:
    """Show the tools in `code` ("es" or "en"; None: the edition's again)."""
    global _chosen
    if code is not None and code not in ("es", "en"):
        raise ValueError(f"no tools language {code!r}: es or en")
    _chosen = code


def tr(text: T, **values) -> str:
    """`text` in the tools' language, its {fields} filled from `values`."""
    return text.format(language(), **values) if values else text(language())


def named(thing) -> str:
    """A screen's, block's or coverage entry's name in the tools' language: in English its English name, when it has
    one."""
    return (getattr(thing, "name_en", "") if language() == "en" else "") or thing.name


def title(screen) -> str:
    """A screen as the tools name it: its number and name ("07 Canteen")."""
    return f"{screen.number} {named(screen)}"


MODES = {"single_screen": T("pantalla única", "single screen"), "normal": T("dos pantallas", "two screens")}
SIDES = {"top": T("arriba", "top"), "bottom": T("abajo", "bottom")}


def mode_name(mode: str) -> str:
    return tr(MODES[mode])


def side_name(side: str) -> str:
    return tr(SIDES[side]) if side in SIDES else side


# ---- the recorder's window (recorder/window.py) ----
WINDOW_TITLE = T("Grabadora de la interfaz (MH4U {product})", "Interface recorder (MH4U {product})")
UNNAMED_SCREEN = T("sin nombre ({groups} grupos, {screen})", "unnamed ({groups} groups, {screen})")
NO_STEADY_SCREEN = T("ninguna estable todavía", "none steady yet")
WINDOW_STATE = T("{label}: {status}\n    Pantalla: {screen}\n    Copias exactas: {copies}, rechazadas: {rejected}",
                 "{label}: {status}\n    Screen: {screen}\n    Exact copies: {copies}, rejected: {rejected}")
LOOKING = T("Buscando el emulador…", "Looking for the emulator…")
TO_RECORD = T("Falta por grabar:", "Still to record:")
TO_RECORD_COUNT = T("Falta por grabar ({missing} de {total}):", "Still to record ({missing} of {total}):")
TO_RECORD_NO_LIST = T("Falta por grabar: sin lista de pantallas (coverage.json)",
                      "Still to record: no list of screens (coverage.json)")
NOTE_HINT = T("Nota para la petición (opcional; va con la próxima captura Ctrl+P o con el botón)",
              "Note for the request (optional; goes with the next Ctrl+P screenshot or with the button)")
MARK = T("Marcar esta pantalla", "Mark this screen")
PAUSE = T("Pausar", "Pause")
RESUME = T("Reanudar", "Resume")
SESSION = T("Sesión: {session}", "Session: {session}")
WAITING = T("Esperando al emulador (Citra o Azahar abierto con el juego)…",
            "Waiting for the emulator (Citra or Azahar running the game)…")
RECORDED = T("Pantallas grabadas en esta sesión: {screens} (variantes: {variants}); peticiones: {requests}",
             "Screens recorded in this session: {screens} (variants: {variants}); requests: {requests}")

# ---- the recorder's statuses (recorder/live.py, exact.py) ----
NO_PROBE = T("Instala la sonda de grabación", "Install the recording probe")
NO_MARKS = T("el juego no tiene las marcas de fotograma", "the game has no frame marks")
CONNECTING = T("Conectando…", "Connecting…")
CLOSED = T("Cerrado", "Closed")
AS_ADMIN = T("El emulador se ejecuta como administrador: ábrelo sin serlo",
             "The emulator runs as administrator: open it as a normal user")
OTHER_GAME = T("El emulador ejecuta otro juego (o un ejecutable desconocido)",
               "The emulator runs another game (or an unknown executable)")
GAME_STARTING = T("Esperando a que el juego arranque", "Waiting for the game to start")
CHECKING_PROBE = T("Conectado: comprobando la sonda de grabación…", "Connected: checking the recording probe…")
GUI_MOVING = T("La interfaz se mueve sin parar: reintentando", "The interface keeps moving: retrying")
NO_PAUSE = T("Sin pausa entre fotogramas: el juego no deja tiempo para una copia exacta (se reintenta cada pocos "
             "segundos)", "No pause between frames: the game leaves no time for an exact copy (retried every few "
             "seconds)")
NO_EXACT_COPY = T("Sin copia exacta en este turno (reintentando)", "No exact copy this turn (retrying)")
GUI_NOT_LOADED = T("La interfaz aún no está en memoria", "The interface is not in memory yet")
RECONNECTING = T("Reconectando (reinicio, estado cargado o emulador cerrado)…",
                 "Reconnecting (restart, loaded state or emulator closed)…")
REJECTED_READ = T("Copia rechazada (lectura)", "Copy rejected (reading)")
NO_GUI_YET = T("Sin interfaz todavía", "No interface yet")
REJECTED_CHECKS = T("Copia rechazada: {count} fallos (ver el registro)",
                    "Copy rejected: {count} failures (see the log)")
RECORDING = T("Grabando", "Recording")
RECORDING_SINGLE = T("Grabando (pantalla única, aparte)", "Recording (single screen, kept apart)")
WINDOW_LABEL = T("Ventana {n}", "Window {n}")
REQUEST_SAVED = T("Petición guardada: {name}", "Request saved: {name}")
HEADLESS_WAITING = T("esperando al emulador", "waiting for the emulator")
HEADLESS_COUNTS = T("pantallas {screens}, variantes {variants}", "screens {screens}, variants {variants}")

# ---- the checker (check.py) ----
CHECK_ONE_PROBLEM = T("1 problema en la ordenación ({screens} pantallas grabadas):",
                      "1 problem in the arrangement ({screens} recorded screens):")
CHECK_PROBLEMS = T("{count} problemas en la ordenación ({screens} pantallas grabadas):",
                   "{count} problems in the arrangement ({screens} recorded screens):")
CHECK_OK = T("Sin problemas: {screens} pantallas grabadas comprobadas.",
             "No problems: {screens} recorded screens checked.")
CHECK_NOT_CHECKED = T("Sin comprobar: {note}", "Not checked: {note}")
CHECK_WARNING = T("Aviso: {warning}", "Warning: {warning}")
SEVERAL_SCREENS = T("La pantalla grabada {sig} ({where}) encaja con {count} pantallas: {titles}; debe encajar con "
                    "una sola.",
                    "The recorded screen {sig} ({where}) matches {count} screens: {titles}; it must match only one.")
NO_SCREEN = T("La pantalla grabada {sig} ({where}) no encaja con ninguna pantalla (grupos: {shown}); dale una pantalla "
              "o ponla en la lista de check.json.",
              "The recorded screen {sig} ({where}) matches no screen (groups: {shown}); give it a screen or put it in "
              "check.json's unarranged list.")
LISTED_BUT_MATCHES = T("La pantalla grabada {sig} ({where}) está en la lista de sin pantalla de check.json pero encaja "
                       "con {title}: quítala de la lista.", "The recorded screen {sig} ({where}) is in check.json's "
                       "unarranged list but matches {title}: take it off the list.")
LISTED_NOT_RECORDED = T("La lista de sin pantalla de check.json ({where}) nombra {sig}, que no se ha grabado.",
                        "check.json's unarranged list ({where}) names {sig}, which has not been recorded.")
UNREADABLE = T("No se pudo leer la pantalla grabada {sig}: {error}",
               "Could not read the recorded screen {sig}: {error}")
LOOSE_GROUP = T("el grupo {name} (sin bloque)", "the group {name} (in no block)")
OVERLAP = T("{a} y {b} se solapan en {count} píxeles en la pantalla de {side} ({where}; pantalla grabada {sig}).",
            "{a} and {b} overlap by {count} pixels on the {side} screen ({where}; recorded screen {sig}).")
OUTSIDE = T("{a} se sale {excess} píxeles de la pantalla de {side} ({where}; pantalla grabada {sig}).",
            "{a} goes {excess} pixels past the {side} screen ({where}; recorded screen {sig}).")
BLOCK_GROUP_MISSING = T("El bloque {id} ({name}) nombra {group}, que no es un grupo de {layout} en los ficheros del "
                        "juego.", "Block {id} ({name}) names {group}, which is no group of {layout} in the game's "
                        "files.")
BLOCK_PANE_MISSING = T("El bloque {id} ({name}) nombra {pane}, que no está en {group} en los ficheros del juego.",
                       "Block {id} ({name}) names {pane}, which is not in {group} in the game's files.")
RULE_GROUP_MISSING = T("La regla de {title} ({mode}) nombra {group}, que no está en los ficheros del juego.",
                       "The rule of {title} ({mode}) names {group}, which is not in the game's files.")
PHOTO_GROUP_MISSING = T("El modo foto de {title} ({mode}) mantiene {group}, que no está en los ficheros del juego.",
                        "The photo mode of {title} ({mode}) keeps {group}, which is not in the game's files.")
TOO_MANY_NAMES = T("La ordenación nombra {count} grupos; el motor admite {limit}.",
                   "The arrangement names {count} groups; the engine takes {limit}.")
CANNOT_WRAP = T("El bloque {id} ({name}) no se puede envolver: {group} pasaría el último nivel del cargador ({error}).",
                "Block {id} ({name}) cannot be wrapped: {group} would pass the loader's last level ({error}).")
POOL_FULL = T("El pool de {pool} se llena en {count} escenas: la peor, {scene}, pide {asked} y caben {size} (con la "
              "reserva de check.json).", "The {pool} pool fills up in {count} scenes: the worst, {scene}, asks for "
              "{asked} and {size} fit (with check.json's reserve).")
SCENE = T("escena {kind}", "scene {kind}")
NO_GAME_FILES = T("nombres, solapes y bordes: no hay ficheros del juego (local.ini, mh4u_romfs)",
                  "names, overlaps and edges: no game files (local.ini, mh4u_romfs)")
NO_POOL_INPUTS = T("pools y profundidad: falta el ejecutable de la update o la RomFS (tools/setup_local.py --extract)",
                   "pools and depth: the update's executable (work/inputs/code_update.bin) or the RomFS dump "
                   "(local.ini mh4u_romfs) is missing")
NO_ENGLISH_NAMES = T("sin nombre en inglés en names_en.json: {things}", "no English name in names_en.json: {things}")
SCREENS_WORD = T("pantallas", "screens")
BLOCKS_WORD = T("bloques", "blocks")
TO_RECORD_WORD = T("pantallas por grabar (coverage.json)", "screens to record (coverage.json)")

# ---- placements and screens described (edit.py, tools/ui.py show) ----
HIDDEN = T("oculto", "hidden")
SCALE = T("escala {scale}", "scale {scale}")
PRIORITY = T("prioridad {priority}", "priority {priority}")
GAMES_PLACE = T("donde lo pone el juego", "where the game puts it")
SIDE_SCREEN = T("pantalla de {side}", "{side} screen")
RULE_WORDS = {"all": T("todos:", "all of:"), "any": T("alguno de:", "any of:"), "none": T("ninguno de:", "none of:")}
OWN_PLACE = T("pantalla", "screen")
DEFAULT_PLACE = T("por defecto", "default")
BACKDROP = T(", fondo", ", backdrop")
PICTURE_MISSING = T("  (no existe: {command})", "  (missing: {command})")
RECORDED_LINE = T("  {sig}: sesiones {sessions}; {variants} variantes",
                  "  {sig}: sessions {sessions}; {variants} variants")
SNAPSHOTS = T("    instantáneas: {paths}", "    snapshots: {paths}")
SHOW_SCREEN = T("Pantalla {title} (id {id}, {mode}, screens/{theme}.json)", "Screen {title} (id {id}, {mode}, "
                "screens/{theme}.json)")
SHOW_RULE = T("Regla: {rule}", "Rule: {rule}")
SHOW_BLOCKS = T("Bloques (final):", "Blocks (final):")
NONE_ITEM = T("  ninguno", "  none")
SHOW_MATCHING = T("Pantallas grabadas que encajan ({count}):", "Recorded screens that match ({count}):")
SHOW_RECORDED = T("Pantalla grabada {sig} ({count} grupos): {groups}",
                  "Recorded screen {sig} ({count} groups): {groups}")
SHOW_ALIASES = T("Nombres del grabador: {aliases}", "The recorder's names: {aliases}")
NO_SCREEN_MATCHED = T("ninguna pantalla", "no screen")
SHOW_SHOWN_BLOCKS = T("Bloques que muestra (final):", "Blocks it shows (final):")
SHOW_REQUESTS = T("Peticiones: {requests}", "Requests: {requests}")
ANSWERED = T("atendida", "answered")
PENDING = T("pendiente", "pending")
SHOW_RECORDINGS = T("Grabaciones:", "Recordings:")

# ---- the gallery (gallery.py) ----
GALLERY_TITLE = T("Galería de pantallas", "Screen gallery")
GALLERY_UNNAMED = T("Pantalla sin nombre ({sig})", "Unnamed screen ({sig})")
GALLERY_UNREADABLE = T("no se pudo leer: {error}", "could not be read: {error}")
GALLERY_SUMMARY = T("{count} pantallas grabadas; {changed} cambiadas desde tu última revisión. Modo: {mode}. "
                    "Generada el {when}.",
                    "{count} recorded screens; {changed} changed since your last review. Mode: {mode}. Made on {when}.")
GALLERY_CHANGED = T("· cambiada desde tu última revisión", "· changed since your last review")
GALLERY_SIGNATURE = T("Firma", "Signature")
GALLERY_SESSION = T("sesión", "session")
GALLERY_SESSIONS = T("sesiones", "sessions")
GALLERY_VARIANTS = T("{count} variantes", "{count} variants")
GALLERY_CAPTIONS = {"original_top": T("Original, arriba", "Original, top"),
                    "original_bottom": T("Original, abajo", "Original, bottom"),
                    "arranged_top": T("Ordenada, arriba", "Arranged, top"),
                    "arranged_bottom": T("Ordenada, abajo", "Arranged, bottom")}
GALLERY_HEADERS = (T("Bloque", "Block"), T("Nombre", "Name"), T("Dónde", "Where"))
GALLERY_NO_BLOCKS = T("Ningún bloque de la ordenación se muestra aquí.", "No block of the arrangement shows here.")
GALLERY_GROUPS = T("Grupos mostrados", "Groups shown")

# ---- tools/ui.py and the recording probe (tools/ui_probe.py) ----
PENDING_COUNT = T("{count} peticiones pendientes (la más nueva primero)", "{count} pending requests (newest first)")
PENDING_NOTE = T("  nota: «{note}»", "  note: “{note}”")
PENDING_PICTURE = T("  imagen: {picture}", "  picture: {picture}")
NO_PICTURE = T("ninguna", "none")
PENDING_NO_SNAPSHOT = T("  {window}: sin instantánea ({reason})", "  {window}: no snapshot ({reason})")
PENDING_WINDOW = T("  {window}: pantalla grabada {sig} -> {matches}", "  {window}: recorded screen {sig} -> {matches}")
PENDING_SNAPSHOT = T("    instantánea: {path}", "    snapshot: {path}")
NOT_FOUND = T("no encontrado: {error}", "not found: {error}")
SET_REFUSED = T("rechazado (solo valores absolutos que el formato admite): {error}",
                "refused (only absolute values the format allows): {error}")
SET_NEXT = T("ahora: tools/ui.py render ... --arranged y tools/ui.py check",
             "next: tools/ui.py render ... --arranged and tools/ui.py check")
PROBE_BUILT = T("sonda: {out}", "probe: {out}")
NOT_INSTALLED_NO_EMULATOR = T("no se instala: local.ini no tiene emulator_dir", "not installed: local.ini has no "
                              "emulator_dir")
NOT_INSTALLED = T("no se instala: {error}", "not installed: {error}")
PROBE_INSTALLED = T("instalada en {mods}: reinicia la emulación (Emulación > Reiniciar)",
                    "installed in {mods}: restart the emulation (Emulation > Restart)")
PROBE_NOT_OURS = T("{folder} no es una sonda nuestra (es tu mod u otra cosa): no se toca",
                   "{folder} is not one of our probes (it is your own mod or something else): left as it is")
PROBE_OTHER_SESSION = T("{folder} tiene una sonda hecha fuera de {probes}: no se toca",
                        "{folder} holds a probe made outside {probes}: left as it is")

# ---- the probe check and the requests (recorder/live.py, marks.py) ----
NO_MARKS_DECLARED = T("este ejecutable no declara las marcas de fotograma", "this executable declares no frame marks")
MARKS_NEVER_AGREE = T("las marcas de fotograma avanzan pero nunca coinciden: la sonda deja una espera del fotograma "
                      "entre ellas", "the frame marks move but never agree: the probe leaves a frame wait between them")
MARKS_STILL = T("las marcas de fotograma no avanzan", "the frame marks do not move")
NO_RECENT_COPY = T("ninguna copia exacta reciente", "no recent exact copy")

# ---- the pictures' warnings (render.py) ----
FONT_PAGE = T("página {page} de la fuente", "font page {page}")
TEXT_TEXTURE = T("textura {word} de un texto", "a text's texture {word}")
TEXT_TEXTURE_ANY = T("textura de un texto", "a text's texture")
TEXTURE_NOT_IN_TABLE = T("textura {word} (no está en la tabla del layout)",
                         "texture {word} (not in the layout's table)")
TEXTURE = T("textura", "texture")
GROUP_IN_NO_LAYOUT = T("el grupo {label} no está en ningún layout: no se dibuja", "the group {label} is in no layout: "
                       "not drawn")
NOT_IN_FILES = T("no están en los ficheros, no se dibujan: {items}", "not in the files, not drawn: {items}")
BACKDROP_EMPTY = T("el fondo {name} no muestra nada: no se estira", "the backdrop {name} shows nothing: not stretched")
SHOWN_MATCH_SEVERAL = T("los grupos mostrados encajan con {count} pantallas: {ids}",
                        "the groups shown match {count} screens: {ids}")
BLOCK_NO_BOX = T("bloque {id}: no se ve nada de él al cargar su layout (sin caja de referencia)",
                 "block {id}: nothing of it shows when its layout loads (no reference box)")
