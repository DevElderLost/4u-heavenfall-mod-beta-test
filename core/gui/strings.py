"""User-facing strings of the main window (option texts live in options.py)."""

import re

from core.app.edition import edition
from core.gui.i18n import T

APP_NAME = edition().name       # the title of the message boxes

FILES = T("ARCHIVOS", "FILES")
OUTPUT_DIR = T("Carpeta de salida", "Output folder")

SEED = T("SEMILLA", "SEED")
SEED_PLACEHOLDER = T("Aleatoria", "Random")
SEED_TIP = T("Con la misma semilla y los mismos ajustes se obtiene siempre el mismo resultado. "
             "Déjala vacía para generar una nueva.",
             "The same seed and settings always give the same result. Leave it empty to get a new one.")
NEW_SEED = T("Nueva semilla", "New seed")

PRESETS = T("PRESETS", "PRESETS")
LOAD_PRESET = T("Cargar", "Load")
SAVE_PRESET = T("Guardar", "Save")
DEFAULTS = T("Por defecto", "Defaults")

RANDOMIZE = T("RANDOMIZAR", "RANDOMIZE")

APPEARANCE_MODES = {"system": T("Sistema", "System"), "light": T("Claro", "Light"), "dark": T("Oscuro", "Dark")}

ACTIVITY = T("ACTIVIDAD", "ACTIVITY")
FAILED = T("Error durante la randomización.", "Randomization failed.")

LOG_WARNING = T("AVISO", "WARNING")
LOG_PRESET_LOADED = T("Preset cargado: {path}", "Preset loaded: {path}")
LOG_PRESET_SAVED = T("Preset guardado: {path}", "Preset saved: {path}")

ERROR_PRESET = T("No se pudo cargar el preset:\n{error}", "Could not load the preset:\n{error}")


GAME = T("PARTIDA", "GAME")
LOAD_GAME = T("Cargar partida…", "Load game…")
LOAD_GAME_TIP = T("El settings_<semilla>.json de la partida: el de tu carpeta del mod o el que te envíe tu amigo "
                  "después de un arreglo.",
                  "The game's settings_<seed>.json file: the one in your mod folder, or the one a friend sends you "
                  "after a fix.")
NO_GAME = T("Ninguna partida cargada.", "No game loaded.")
GAME_INFO = T("Semilla {seed}\nRevisión {revision} · código {code}\nVersión {version}",
              "Seed {seed}\nRevision {revision} · code {code}\nVersion {version}")
NO_CODE = T("sin código", "no code")
PREVIEW = T("PREVISUALIZAR", "PREVIEW")
PREVIEWING = T("Comprobando…", "Checking…")
APPLY_FIX = T("APLICAR ARREGLO", "APPLY FIX")
APPLYING = T("Aplicando…", "Applying…")

REROLL_ALL = T("Re-sortear todas las misiones", "Reroll all quests")
REROLL_ALL_TIP = T("Cada vez que sumas uno, todas las misiones salen de nuevo (el equipo no cambia). Volver al número "
                   "anterior recupera las misiones de antes.",
                   "Each time you raise this number, all quests are drawn again (the equipment does not change). "
                   "Setting it back to the previous number restores the previous quests.")
REROLL_ALL_DESCRIPTION = T("Si las misiones en general no os gustan.",
                           "Use this if you are not happy with the quests overall.")
REROLL_TIMES = T("Veces", "Times")
REROLL_QUEST = T("Re-sortear una misión", "Reroll one quest")
REROLL_QUEST_DESCRIPTION = T(
    "Para una misión imposible o que no os gusta: solo esa misión sale de nuevo; las demás y el equipo quedan "
    "igual. Se puede repetir (cada vez sale distinta) y deshacer.",
    "For a quest that is impossible or that you do not like: only that quest is drawn again; the other quests and "
    "the equipment stay the same. You can repeat it (each time gives a different result) and undo it.")
QUEST_SEARCH_TIP = T("Escribe el número o parte del nombre (en inglés) de la misión y elige una de la lista.",
                     "Type the quest number or part of its name, then choose it from the list.")
REROLL = T("Re-sortear", "Reroll")
NO_REROLLS = T("Ninguna misión re-sorteada.", "No quest rerolled.")
KEY_QUEST = T("obligatoria", "required")
HISTORY = T("Historial", "History")
HISTORY_DESCRIPTION = T("Los arreglos aplicados a esta partida.", "Fixes applied to this game.")
NO_HISTORY = T("Sin arreglos todavía.", "No fixes yet.")
BACKUPS = T("Copias de seguridad", "Backups")
BACKUPS_DESCRIPTION = T("El mod tal como estaba antes de cada arreglo (carpeta backups/). Restaurar una copia guarda "
                        "antes el mod actual, así que también se puede deshacer.",
                        "The mod as it was before each fix (in the backups/ folder). Restoring a backup saves the "
                        "current mod first, so it can also be undone.")
NO_BACKUPS = T("Sin copias todavía.", "No backups yet.")
RESTORE = T("Restaurar", "Restore")
BACKUP_LABEL = T("{name} · código {code}", "{name} · code {code}")
FIX_NOTE = T("Los demás ajustes (misiones, equipo) también se pueden cambiar: «Previsualizar» dice qué cambia antes "
             "de tocar nada. Las opciones de «Extra» y «Partida nueva» son de cada jugador.",
             "Other settings (quests, equipment) can also be changed: \"Preview\" shows what will change before "
             "anything is modified. The \"Extra\" and \"New game\" options belong to each player.")

LOG_FIX_RECEIVED = T("Revisión {revision} verificada: este PC produce el mismo código ({code}).",
                     "Revision {revision} verified: this PC produces the same code ({code}).")
LOG_FIX_NEW = T("Revisión nueva {revision}, código {code}.", "New revision {revision}, code {code}.")
LOG_FIX_CHANGES = T("Ajustes que cambian:", "Changed settings:")
LOG_FIX_QUESTS = T("Misiones que cambian ({count}):", "Changed quests ({count}):")
LOG_FIX_QUEST = T("  {id} {title}: {old} → {new}", "  {id} {title}: {old} → {new}")
LOG_FIX_MAP = T(" (mapa: {old} → {new})", " (map: {old} → {new})")
LOG_FIX_EQUIPMENT = T("Equipo que cambia: {groups}", "Changed equipment: {groups}")
LOG_FIX_NOTHING = T("No cambia nada respecto al mod de la carpeta.", "No changes compared to the mod in the folder.")
EQUIPMENT_GROUPS = {"weapons": T("armas", "weapons"), "weapon upgrades": T("mejoras de armas", "weapon upgrades"),
                    "armor": T("armaduras", "armor"), "recipes": T("recetas", "recipes"),
                    "sharpness": T("filos", "sharpness"), "felyne": T("Felyne", "Felyne")}
FIX_WARNINGS = {
    "no_checksum": T("La partida de la carpeta se hizo antes de que existieran los códigos de comprobación: no se "
                     "puede garantizar que solo cambie el arreglo. Si jugáis varios, aplicad todos el mismo "
                     "settings_<semilla>.json arreglado: desde entonces lleva su código.",
                     "The game in the folder was created before verification codes existed, so it cannot be "
                     "confirmed that only the fix will change. If several people play it, all of them should apply "
                     "the same fixed settings_<seed>.json; from then on, it will include its code."),
    "no_base": T("No hay partida en la carpeta del mod: se escribe el mod completo.",
                 "There is no game in the mod folder: the complete mod will be written."),
}
FIX_ERRORS = {
    "seed": T("La carpeta del mod tiene la semilla {base} y el archivo la {target}. Un arreglo conserva la semilla: "
              "elige la carpeta de esa partida.",
              "The mod folder contains seed {base}, but the file contains seed {target}. A fix keeps the same "
              "seed: choose the folder of that game."),
    "op_equipment": T("«Permitir equipo OP» no se puede quitar en una partida empezada: el equipo fabricado con él "
                      "puede superar los límites del juego, y el juego rechazaría todas las misiones.",
                      "\"Allow OP equipment\" cannot be turned off in a game in progress: equipment made with it may "
                      "exceed the game's limits, and the game would then reject every quest."),
    "base_mismatch": T("Esta versión ({version}) no reproduce la partida de la carpeta (hecha con la "
                       "{base_version}). Usa esa versión para arreglarla; no se ha cambiado nada.",
                       "This version ({version}) cannot reproduce the game in the folder, which "
                       "was made with version {base_version}. Use that version to fix it. Nothing was changed."),
    "target_mismatch": T("Este PC no produce lo mismo que el archivo (código {expected}, aquí {actual}). El archivo "
                         "se hizo con la versión {target_version} y esta es la {version}; usad la misma versión y "
                         "la misma ROM. No se ha cambiado nada.",
                         "This PC does not produce the same result as the file (expected code {expected}, got "
                         "{actual}). The file was made with version {target_version}, and this is version "
                         "{version}. Everyone must use the same version and the same ROM. Nothing was changed."),
    "apply_mismatch": T("El mod escrito no coincide con la vista previa (código {expected}, escrito {actual}). Se ha "
                        "restaurado el mod anterior.",
                        "The written mod does not match the preview (expected code {expected}, got {actual}). The "
                        "previous mod has been restored."),
    "backup_region": T("La copia {name} tiene un mod para el juego {built} y este destino es para el {title}: no se "
                       "ha restaurado nada.",
                       "Backup {name} contains a mod for game {built}, but this destination is for {title}. "
                       "Nothing was restored."),
}
ERROR_NO_GAME = T("Carga primero la partida (su settings_<semilla>.json).",
                  "Load the game first (its settings_<seed>.json file).")
ERROR_FIX = T("No se puede aplicar el arreglo:\n{error}", "Could not apply the fix:\n{error}")
CONFIRM_RESTORE = T("Se va a sustituir el mod de la carpeta:\n{path}\n\npor la copia {name} (revisión {revision}, "
                    "código {code}). El mod actual se copia antes en backups/. Cierra el juego en el emulador y "
                    "vuelve a abrirlo después.\n\n¿Restaurar la copia?",
                    "The mod in this folder:\n{path}\n\nwill be replaced by backup {name} (revision {revision}, "
                    "code {code}). The current mod will be copied to backups/ first. Close the game in the "
                    "emulator and start it again afterwards.\n\nRestore this backup?")

# ---- Qt fix panel (gui/qt/fix_panel.py) ----
FROM_INSTALLED = T("Del juego instalado", "From installed game")
FROM_INSTALLED_TIP = T("Carga la partida de Randomizer que ya está instalada en el destino (emulador o tarjeta SD).",
                       "Loads the Randomizer game already installed at the destination (emulator or SD card).")
GAME_SOURCE = {"installed": T("Origen: juego instalado", "Source: installed game"),
               "file": T("Origen: archivo {name}", "Source: file {name}")}
FIX_LOADING = T("Cargando…", "Loading…")
FIX_INSTALLED_NONE = T("No hay ninguna partida de Randomizer instalada en el destino.",
                       "No Randomizer game is installed at the destination.")
FIX_NO_RESULT = T("Pulsa «Previsualizar» para ver qué cambia.", "Press \"Preview\" to see what changes.")
FIX_NEED_FILES = T("Elige la ROM de MH4U en la página Instalar.", "Choose the MH4U ROM on the Install page.")
FIX_NEED_XX = T("Tus opciones necesitan Monster Hunter XX (japonés): elige su archivo en la página Instalar.",
                "Your options need Monster Hunter XX (Japanese): choose its file on the Install page.")
FIX_NEED_TARGET = T("No hay destino: elige el emulador o la tarjeta SD en la página Instalar.",
                    "No destination selected: choose the emulator or the SD card on the Install page.")
FIX_INPUTS = T("Faltan archivos del juego:\n{problems}", "Some game files are missing:\n{problems}")
# Why a game file was refused (game/executable/containers.py MESSAGES: the English texts are the same, a test checks
# it).
EXTRACT_ERRORS = {
    "encrypted": T("el archivo está cifrado; indica su archivo de claves (aes_keys.txt o 3dskeys.txt) o descífralo "
                   "primero (p. ej. con GodMode9)",
                   "the file is encrypted; give its key file (aes_keys.txt or 3dskeys.txt) or decrypt it first "
                   "(e.g. with GodMode9)"),
    "missing_keys": T("el archivo está cifrado y el archivo de claves no tiene la clave que necesita",
                      "the file is encrypted and the key file does not have the key it needs"),
    "not_a_game_file": T("no es un juego de 3DS descifrado (.3ds, .cci, .cxi, .app, .cia, .zcci, .zcxi o .zcia)",
                         "not a decrypted 3DS game file (.3ds, .cci, .cxi, .app, .cia, .zcci, .zcxi or .zcia)"),
    "truncated": T("el archivo está incompleto (una descarga o copia cortada)",
                   "the file is incomplete (the download or copy was interrupted)"),
    "unsupported_compression": T("este archivo comprimido está en una versión del formato que el programa no sabe leer",
                                 "this compressed file uses a format version that this program cannot read"),
    "damaged": T("el archivo está dañado (no se pueden leer sus datos comprimidos)",
                 "the file is damaged (its compressed data cannot be read)"),
    "no_executable": T("este archivo no tiene ejecutable (ExeFS)", "this file has no executable (ExeFS)"),
    "no_romfs": T("este archivo no tiene RomFS", "this file has no RomFS"),
    "invalid_romfs": T("RomFS no válido (sin cabecera IVFC)", "invalid RomFS (no IVFC header)"),
}
# Why a game file was refused for the game it was picked for (install/build.py GAME_PROBLEMS, by the same keys: the
# English texts are the same, a test checks it). The install page translates them inside the problems it lists.
GAME_PROBLEMS = {
    "wrong_mh4u": T("no es Monster Hunter 4 Ultimate europeo ni americano",
                    "this is not the European or American Monster Hunter 4 Ultimate"),
    "wrong_mhgen": T("no es Monster Hunter Generations europeo ni americano",
                     "this is not the European or American Monster Hunter Generations"),
    "is_update": T("es la actualización del juego, no el juego: elige el juego mismo (el cartucho o la copia de la "
                   "eShop)",
                   "this is the game update, not the game itself: choose the game (cartridge or eShop dump)"),
    "is_mh4u": T("es Monster Hunter 4 Ultimate, no Monster Hunter Generations",
                 "this is Monster Hunter 4 Ultimate, not Monster Hunter Generations"),
    "is_mhgen": T("es Monster Hunter Generations, no Monster Hunter 4 Ultimate",
                  "this is Monster Hunter Generations, not Monster Hunter 4 Ultimate"),
    "wrong_mhxx": T("no es Monster Hunter XX japonés",
                    "this is not the Japanese Monster Hunter XX"),
    "is_mhxx": T("es Monster Hunter XX, no el juego que se pide aquí",
                 "this is Monster Hunter XX, not the game asked for here"),
    "unreadable": T("no se puede leer el archivo (¿está en uso, sin permiso o en una unidad desconectada?)",
                    "the file cannot be read (check that it is not in use, that you have permission to open it, and "
                    "that its drive is connected)"),
}
# The other refusals of the install path: (regular expression of the whole English message, its translation with the
# named groups as fields). install/deploy.py, install/build.py and gui/qt/jobs.py write the English; a test raises the
# real ones and checks each is translated.
INSTALL_ERRORS = [
    (r"(?P<path>.+) is not a mod folder for (?P<titles>.+)",
     T("{path} no es una carpeta de mods para {titles}", "{path} is not a mod folder for {titles}")),
    (r"(?P<path>.+) is inside an emulator's SD card, NAND or save folder",
     T("{path} está dentro de la tarjeta SD, la NAND o las partidas guardadas de un emulador",
       "{path} is inside an emulator's SD card, NAND or save folder")),
    (r"bad path in the marker: (?P<rel>.+)",
     T("ruta no válida en el registro de la instalación: {rel}", "bad path in the marker: {rel}")),
    (r"(?P<rel>.+) leads outside (?P<folder>.+)",
     T("{rel} sale de {folder}", "{rel} leads outside {folder}")),
    (r"(?P<path>.+) holds files this installer did not put there",
     T("{path} contiene archivos que este instalador no puso ahí",
       "{path} holds files this installer did not put there")),
    (r"(?P<path>.+) was not installed by this installer",
     T("{path} no lo instaló este instalador", "{path} was not installed by this installer")),
    (r"(?P<path>.+) is not empty and was not made by this installer",
     T("{path} no está vacía y no la creó este instalador",
       "{path} is not empty and was not made by this installer")),
    (r"the mod in (?P<build>.+) is for (?P<built>\S+), the install is for (?P<title>\S+)",
     T("el mod de {build} es para {built} y la instalación es para {title}",
       "the mod in {build} is for {built}, the install is for {title}")),
    # A game whose executable is no version the mod knows (game/executable/versions.py identify), and a patch the
    # player's version cannot take (game/executable/player_code.py REFUSAL)
    (r"(?P<game>Monster Hunter 4 Ultimate|Monster Hunter Generations): this executable is not a version the mod "
     r"knows \(title (?P<title>[^,]+), sha256 (?P<sha256>[0-9a-f]+)\); use the European or American game, "
     r"unmodified",
     T("{game}: su ejecutable no es una versión que el mod conozca (título {title}, sha256 {sha256}); usa el juego "
       "europeo o el americano, sin modificar",
       "{game}: this executable is not a version the mod knows (title {title}, sha256 {sha256}); use the European "
       "or American game, unmodified")),
    (r"the mod cannot be built for this game version: (?P<detail>.+)",
     T("el mod no se puede construir para esta versión del juego: {detail}",
       "the mod cannot be built for this game version: {detail}")),
]


def install_error(problem: str, language: str) -> str | None:
    """`problem`, a whole English message of INSTALL_ERRORS, in `language`; None for any other message."""
    for pattern, text in INSTALL_ERRORS:
        match = re.fullmatch(pattern, problem)
        if match:
            return text.format(language, **match.groupdict())
    return None


PROBLEM_WORDS = {
    "the file was not found": T("no se encontró el archivo", "the file was not found"),
    "(title ": T("(título ", "(title "),     # after the refusal of a game the mod does not know
}


def describe_problem(problem: str, language: str) -> str:
    """One refusal in the player's language: a whole message of the install path (INSTALL_ERRORS), else its known
    pieces (a game file's refusals by kind)."""
    translated = install_error(problem, language)
    if translated is not None:
        return translated
    from core.game.executable.containers import MESSAGES
    from core.install.build import GAME_PROBLEMS as ENGLISH
    words = {**PROBLEM_WORDS, **{MESSAGES[kind]: text for kind, text in EXTRACT_ERRORS.items()},
             **{ENGLISH[kind]: text for kind, text in GAME_PROBLEMS.items()}}
    for english, text in words.items():
        problem = problem.replace(english, text(language))
    return problem


# The region a game file is from, shown beside its picker
REGIONS = {"eur": T("Europa", "Europe"), "usa": T("América", "America"), "jpn": T("Japón", "Japan")}
FIX_APPLIED_INSTALLED = T("Arreglo instalado: revisión {revision}, código {code}. Envía {file} a quien juegue contigo.",
                          "Fix installed: revision {revision}, code {code}. Send {file} to everyone you play with.")
FIX_RESTORED_INSTALLED = T("Copia {name} restaurada e instalada.", "Backup {name} restored and installed.")
CONFIRM_INSTALL_FIX = T(
    "Se va a instalar en:\n{path}\n\nAntes se guarda una copia de la partida actual en backups/. Cierra el juego "
    "en el emulador y vuelve a abrirlo después. Tu partida guardada no se toca.\n\n{warnings}{replace}¿Continuar?",
    "The fix will be installed in:\n{path}\n\nA backup of the current game will be saved in backups/ first. Close "
    "the game in the emulator and start it again afterwards. Your save data will not be modified.\n\n"
    "{warnings}{replace}Continue?")
CONFIRM_REPLACE_UNKNOWN = T("Esa carpeta tiene archivos que no son de este instalador: se borrarán.\n\n",
                            "That folder contains files that were not added by this installer. They will be "
                            "deleted.\n\n")
CONFIRM_REPLACE_INSTALL = T("Ahora tiene el mod sin randomizar: se sustituirá por esta partida.\n\n",
                            "It currently contains the non-randomized mod. It will be replaced by this game.\n\n")
FIX_FAILED = T("El arreglo ha fallado.", "The fix failed.")
FIX_BACKUP_NONE = T("Elige una copia primero.", "Choose a backup first.")

PRESET_FILES = T("Preset", "Preset")
