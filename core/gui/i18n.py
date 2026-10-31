"""Interface languages.

Every user-facing string is a `T` holding all translations (core/app/i18n.py, shared with the game GUI tools), so
adding a language means adding one field there and filling it everywhere (the GUI tests check that no translation is
empty). This module must not import tkinter.
"""

from core.app.i18n import EMPTY, T  # noqa: F401 (the GUI's modules take them from here)

LANGUAGE_NAMES = {"es": "Español", "en": "English"}
DEFAULT_LANGUAGE = "es"


def language_for_locales(tags) -> str:
    """The interface language for the system's language tags, most preferred first ("es-ES", "es_MX", "en-US"...):
    Spanish when the first one is Spanish, English for anything else (also none)."""
    for tag in tags:
        text = str(tag).strip().lower().replace("_", "-")
        if text:
            return "es" if text.split("-")[0] == "es" else "en"
    return "en"
