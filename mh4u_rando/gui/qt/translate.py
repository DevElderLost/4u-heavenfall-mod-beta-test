"""Language switch without rebuilding widgets.

Every translatable widget registers `(widget, setter, text)` once; `Translator.set_language` re-runs the setters.
`text` is a `T` or a callable taking the language code and returning a string (for texts that depend on a state).
"""

from collections.abc import Callable

from ..i18n import DEFAULT_LANGUAGE, T

Text = T | Callable[[str], str]


def _alive(widget) -> bool:
    try:
        from shiboken6 import isValid
    except ImportError:  # pragma: no cover
        return True
    return isValid(widget)


class Translator:
    def __init__(self, language: str = DEFAULT_LANGUAGE):
        self.language = language
        self._entries: list[tuple[object, Callable[[str], None], Text]] = []

    def text(self, text: Text) -> str:
        return text(self.language)

    def bind(self, widget, setter: Callable[[str], None], text: Text) -> None:
        """Set `setter(text)` now and again on every language change (until the widget is destroyed)."""
        self._entries.append((widget, setter, text))
        setter(self.text(text))

    def set_language(self, language: str) -> None:
        self.language = language
        self.refresh()

    def refresh(self) -> None:
        self._entries = [entry for entry in self._entries if _alive(entry[0])]
        for _, setter, text in self._entries:
            setter(self.text(text))


translator = Translator()
