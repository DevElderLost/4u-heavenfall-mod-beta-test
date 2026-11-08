"""Edits of the message files of `<lang>/data/core_common.arc`, in the five languages.

Every name, description and menu text of the game's common interface lives in a message file (LMD) of this archive, and
the game finds a message by its index, with no limit in the executable (the lookup only checks the index against the
file's own message count). A message therefore needs no table: a text appended to a list has the index of the list's
old end, and the messages between the end and a farther index are filled with empty ones.

`CommonTexts` collects the edits of every feature that changes these files and applies them to a core_common.arc in
memory, so the archive is parsed and written once per language by whoever writes it: `apply`, or `files` over a reader
of the mod's files so far (each feature works on the copy the one before wrote). A feature with rules of its own for a
list (the gear's descriptions, which the executable finds by their count) extends the class and overrides
`check_list`.
"""

from collections.abc import Callable, Mapping
from pathlib import Path

from core.game.files.arc import parse_arc, write_arc
from core.game.files.text.lmd import LMD_TYPE_HASH, Lmd, parse_lmd, write_lmd

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")  # the RomFS language folders
COMMON_ARC = "{lang}/data/core_common.arc"

Texts = Mapping[str, str]   # language (eng, fre, ger, ita, spa) -> text; a missing language shows the English one


class CommonTextError(ValueError):
    pass


def complete_texts(texts: Texts, what: str) -> dict[str, str]:
    if "eng" not in texts:
        raise CommonTextError(f"{what}: the English text is the fallback of the other languages and must be given")
    unknown = set(texts) - set(LANGUAGES)
    if unknown:
        raise CommonTextError(f"{what}: unknown languages {sorted(unknown)}")
    return {lang: texts.get(lang) or texts["eng"] for lang in LANGUAGES}


class CommonTexts:
    """Edits of the message files in core_common.arc, per language: kept in memory, applied by `apply`.

    Messages are set by message file (its stem, e.g. "emExp", "itemName", "Menu") and index with `put`. Setting a
    message twice keeps the last text. Applying appends the messages past a list's end (the ones between, empty) and
    rewrites the ones inside it."""

    def __init__(self) -> None:
        # language -> message file stem -> message index -> text
        self._messages: dict[str, dict[str, dict[int, str]]] = {lang: {} for lang in LANGUAGES}

    def __bool__(self) -> bool:
        return any(self._messages[lang] for lang in LANGUAGES)

    def put(self, stem: str, index: int, texts: Texts) -> None:
        """Message `index` of the file `stem` (e.g. "emExp", "itemName") in every language."""
        if index < 0:
            raise CommonTextError(f"{stem}: message {index}")
        for lang, text in complete_texts(texts, f"{stem} {index}").items():
            self._messages[lang].setdefault(stem, {})[index] = text

    def update(self, other: "CommonTexts") -> None:
        for lang in LANGUAGES:
            for stem, messages in other._messages[lang].items():
                self._messages[lang].setdefault(stem, {}).update(messages)

    def stems(self) -> list[str]:
        """The message files with edits."""
        return sorted({stem for lang in LANGUAGES for stem in self._messages[lang]})

    def check_list(self, stem: str, lang: str, lmd: Lmd) -> None:
        """Raises CommonTextError if the message file `stem` of `lang` (parsed as `lmd`) cannot take the edits. The
        generic class accepts every list; a subclass with lists the executable reads by their count refuses a list
        that grew."""

    def apply(self, arc: bytes, lang: str) -> bytes:
        """`arc`, the core_common.arc of `lang`, with the edits made. Returned unchanged without edits."""
        edits = self._messages[lang]
        if not edits:
            return arc
        parsed = parse_arc(arc)
        entries = {e.name.split("\\")[-1]: e for e in parsed.entries if e.type_hash == LMD_TYPE_HASH}
        for stem, messages in edits.items():
            entry = entries.get(f"{stem}_{lang}")
            if entry is None:
                raise CommonTextError(f"no message file {stem}_{lang} in {COMMON_ARC.format(lang=lang)}")
            lmd = parse_lmd(entry.data)
            self.check_list(stem, lang, lmd)
            for index in sorted(messages):
                if index < lmd.message_count:
                    lmd.set_message(index, messages[index])
                    continue
                while lmd.message_count < index:
                    lmd.add_message("")
                lmd.add_message(messages[index])
            entry.data = write_lmd(lmd)
        return write_arc(parsed)

    def files(self, read: Callable[[str], bytes]) -> dict[str, bytes]:
        """{RomFS path: new core_common.arc} of the languages with edits. `read` gives each file as the mod has it
        so far (the base game's copy, or the one an earlier feature wrote: the HUD, the icons, a ported monster's
        name), so every feature keeps what the ones before wrote."""
        out = {}
        for lang in LANGUAGES:
            if self._messages[lang]:
                path = COMMON_ARC.format(lang=lang)
                out[path] = self.apply(read(path), lang)
        return out


def common_text_paths(mod_dir: Path) -> list[Path]:
    """Every file `CommonTexts.files` can leave in a mod folder (core_common.arc of each language: other features
    write the same files, so a run removes them all before writing; pipeline.write_interface_files)."""
    return [Path(mod_dir) / "romfs" / COMMON_ARC.format(lang=lang) for lang in LANGUAGES]


def remove_common_text_files(mod_dir: Path) -> None:
    for path in common_text_paths(mod_dir):
        path.unlink(missing_ok=True)
