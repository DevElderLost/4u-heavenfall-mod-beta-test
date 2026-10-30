"""Translated texts: a `T` holds one text in every language the program speaks, so adding a language means adding one
field here and filling it everywhere (the GUI tests check that no translation is empty). Shared by the GUI
(gui/i18n.py, gui/strings.py) and the game GUI tools (gamegui/strings.py), which must not import the GUI."""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class T:
    es: str
    en: str

    def __call__(self, language: str) -> str:
        return getattr(self, language, self.en)

    def format(self, language: str, **values) -> str:
        return self(language).format(**values)

    def is_complete(self) -> bool:
        return all(getattr(self, f.name) for f in fields(self))


EMPTY = T("", "")
