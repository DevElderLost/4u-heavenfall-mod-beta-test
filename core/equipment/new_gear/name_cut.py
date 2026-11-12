"""Shortening the ported gear's names so that they fit the game's boxes (step 5,
"Names that fit"), the same way in the five languages.

The rule: **a word that must be shortened is cut right after a complete syllable and ends with a dot** ("violeta" ->
"viole.", never "viol."). The steps, from the gentlest (`fit`): drop a filler word ("de"), write the monster's name as
its fixed abbreviation (`MONSTERS`: Mizutsune is always "Mizu."; Maccao is never abbreviated, `NEVER_CUT`), then cut
the longest words at a syllable (`cut_word`).
Names the games themselves wrote with a cut inside a syllable ("Mizuts.", "Guardab.") are first written in full again
(`expand`), so that they are cut by the rule or not at all.

The syllabifier (`syllables`) is simple and per language, enough to decide where an abbreviation may stop: a run of
vowels is one syllable nucleus (Spanish and Italian: two strong vowels, or an accented weak one, make two); the
consonants between two nuclei go to the next syllable, except that two of them split in the middle unless they start a
syllable together (consonant + l or r, digraphs such as ch, ll, sch; Italian s + consonant; German sp, st); a final mute
"e" (English, French) joins the syllable before. It is not a hyphenation dictionary: the names it cuts are few and the
tests list them.
"""

from __future__ import annotations

import re
from collections.abc import Callable

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
MIN_STEM = 3                 # an abbreviation keeps at least this many letters before its dot

# The monsters' names when shortened, the same in every language ("Mizutsune" is always "Mizu."). Each one is a whole
# number of syllables of the name (Mi-zu-tsu-ne, A-la-tre-on, Gla-ve-nus). A later monster adds his here.
MONSTERS = {"Mizutsune": "Mizu.", "Alatreon": "Alatre.", "Glavenus": "Glave."}

# Monsters whose name is never abbreviated (Maccao is not abbreviated): a name that does not fit
# loses a syllable of another word instead. A word holding one of these is never cut, in any language ("Maccao-Rest",
# the German compound "GroßMaccaoLederhaut").
NEVER_CUT = ("Maccao",)

# Words dropped first when a name is too long (the joining words of each language).
FILLERS = {"eng": ("of",), "fre": ("de", "du", "des"), "ger": (),
           "ita": ("di", "del", "della", "dei", "delle", "degli"), "spa": ("de", "del")}

# Cuts the games' own texts (MH Generations') made inside a syllable, written in full again before the name is fitted.
# Only the forms the ported monsters' names contain; the tests list any other (a new monster adds his).
EXPANSIONS: dict[str, dict[str, str]] = {
    "eng": {},
    "fre": {"Hallebar.": "Hallebarde", "Gem.dragon": "Gemme dragon", "Macc": "Maccao"},
    "ger": {"VersengSchnurrhaa.": "VersengSchnurrhaare"},
    "ita": {"Alabar.": "Alabarda", "Art.": "Artiglio", "Comandam.": "Comandamento", "Metamorf.": "Metamorfosi",
            "Parabr.": "Parabraccia", "Protez.": "Protezione", "Schin.": "Schinieri", "Paras.": "Parasole",
            "pes.": "pesante", "pirocor.": "pirocorazza", "framm.": "frammento", "Pettor.": "Pettorina"},
    "spa": {"Mizuts.": "Mizutsune", "Guardab.": "Guardabrazos", "Parag.": "Paraguas", "osc.": "oscura",
            "viol.": "violeta", "Guardabr.": "Guardabrazos", "Colm.": "Colmillo", "Pirocapar.": "Pirocaparazón",
            "Infernocapar.": "Infernocaparazón", "pist.": "pistola"},
}

_VOWELS = {"eng": "aeiouy", "fre": "aeiouyàâäéèêëîïôöùûüÿœæ", "ger": "aeiouyäöü", "ita": "aeiouàèéìíòóùú",
           "spa": "aeiouáéíóúü"}
_WEAK = "iuüy"               # Spanish and Italian: a weak vowel makes a diphthong with the vowel next to it
_ACCENTED_WEAK = "íú"        # a stressed weak vowel is a nucleus of its own
_DIGRAPHS = {"eng": ("sh", "ch", "th", "ph", "ck", "gh", "wh", "qu", "ts"),
             "fre": ("ch", "ph", "th", "gn", "qu", "gu", "ts"),
             "ger": ("sch", "ch", "ck", "ph", "th", "qu"),
             "ita": ("ch", "gh", "gn", "gl", "qu", "gu", "ts"),
             "spa": ("ch", "ll", "rr", "qu", "gu", "ts")}
_ONSET_FIRST = "pbtdkcgfv"   # consonants that open a syllable together with a following l or r
_LETTER = r"(?<![^\W\d_])"   # "not after a letter" (lookbehind) for a whole-word match
_NOT_BEFORE_LETTER = r"(?![^\W\d_])"


def _is_vowel(low: str, i: int, lang: str) -> bool:
    c = low[i]
    if c not in _VOWELS[lang]:
        return False
    before = low[i - 1] if i else ""
    after = low[i + 1] if i + 1 < len(low) else ""
    plain = _VOWELS[lang].replace("y", "")
    gue = before == "g" and lang in ("fre", "ita", "spa") and bool(after) and after in "eiéíèê"
    if c == "u" and (before == "q" or gue):          # the u of "qu", "gue", "gui" is silent
        return False
    if c == "y" and lang in ("fre", "ita", "spa"):
        return not ((not i and after in plain and after) or (before in plain and before and after in plain and after))
    return True


def _nuclei(low: str, lang: str) -> list[tuple[int, int]]:
    """The vowel groups (start, end) of a word, split where two vowels are two syllables (hiatus)."""
    flags = [_is_vowel(low, i, lang) for i in range(len(low))]
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(low):
        if not flags[i]:
            i += 1
            continue
        start = i
        i += 1
        while i < len(low) and flags[i]:
            prev, cur = low[i - 1], low[i]
            if lang in ("spa", "ita") and (
                    (prev not in _WEAK and cur not in _WEAK) or cur in _ACCENTED_WEAK or prev in _ACCENTED_WEAK):
                break
            i += 1
        out.append((start, i))
    return out


def _units(consonants: str, lang: str) -> list[str]:
    out, i = [], 0
    while i < len(consonants):
        for digraph in sorted(_DIGRAPHS[lang], key=len, reverse=True):
            if consonants.startswith(digraph, i):
                out.append(digraph)
                i += len(digraph)
                break
        else:
            out.append(consonants[i])
            i += 1
    return out


def _joins(first: str, second: str, lang: str, before: bool) -> bool:
    """Whether two consonant units start a syllable together (pr, bl, dr; Italian s + consonant; German sch + any;
    English and German s + p, t or k after another consonant: "Dragon-spire", "Drachen-spitze"). `before`: another
    consonant comes before the two."""
    if second in ("l", "r") and first in _ONSET_FIRST and (first, second) != ("t", "l"):
        return True
    if first == "s":
        return lang == "ita" or (lang in ("eng", "ger") and before and second in ("p", "t", "k"))
    return first == "sch" and lang == "ger"


def syllables(word: str, lang: str) -> list[str]:
    """`word` (letters only) split into syllables by the language's simple rules; the pieces join back into `word`."""
    low = word.lower()
    nuclei = _nuclei(low, lang)
    if lang in ("eng", "fre") and len(nuclei) > 1:           # a final mute "e" joins the syllable before
        start, _ = nuclei[-1]
        before = low[start - 1] if start else ""
        if low[start:] in ("e", "es") and before and before not in _VOWELS[lang]:
            after_liquid = lang == "eng" and before == "l" and start >= 2 and low[start - 2] not in _VOWELS[lang]
            if not after_liquid:                              # English "ta-ble" keeps its own syllable
                nuclei.pop()
    if len(nuclei) < 2:
        return [word] if word else []
    cuts = []
    for (_, end), (start, _) in zip(nuclei, nuclei[1:]):
        end += lang == "ger" and low[end:end + 1] == "ß"          # German "ß" closes the syllable before it
        units = _units(low[end:start], lang)
        take = 2 if len(units) >= 2 and _joins(units[-2], units[-1], lang, len(units) >= 3) else 1
        cuts.append(start - sum(len(u) for u in units[len(units) - take:]) if units else end)   # no units: hiatus
    edges = [0, *cuts, len(word)]
    return [word[a:b] for a, b in zip(edges, edges[1:]) if b > a]


def clean_cuts(word: str, lang: str) -> list[str]:
    """The abbreviations `word` may have: a whole number of syllables, at least MIN_STEM letters, then a dot; longest
    first."""
    out, stem = [], ""
    for piece in syllables(word, lang)[:-1]:
        stem += piece
        if len(stem) >= MIN_STEM:
            out.append(stem + ".")
    return out[::-1]


def is_clean_cut(token: str, word: str, lang: str) -> bool:
    """Whether `token` ("viole.") is `word` ("violeta") cut after a syllable."""
    return token in clean_cuts(word, lang)


# ----- names ---------------------------------------------------------------------------------------------------------

def expand(name: str, lang: str) -> str:
    """`name` with the games' own mid-syllable abbreviations written in full (`EXPANSIONS`)."""
    for short, full in EXPANSIONS[lang].items():
        end = "" if short.endswith(".") else _NOT_BEFORE_LETTER      # a cut without a dot ("Macc") is a whole word
        name = re.sub(f"{_LETTER}{re.escape(short)}{end}", full, name)
    return name


def shorten_monster(name: str) -> str:
    """`name` with each monster's name as its fixed abbreviation. A colon after the monster ("Mizutsune: pinna") goes,
    the dot taking its place; a monster glued to a capitalised word (German compounds without a hyphen) is joined to it
    by a hyphen."""
    for full, short in sorted(MONSTERS.items(), key=lambda kv: -len(kv[0])):
        name = re.sub(f"{_LETTER}{re.escape(full)}:", short, name)
        name = re.sub(f"{_LETTER}{re.escape(full)}(?=[A-ZÄÖÜ])", short + "-", name)
        name = re.sub(f"{_LETTER}{re.escape(full)}(?![^\\W\\d_])", short, name)
    return name


def cut_word(word: str, lang: str, keep: Callable[[str], bool] | None = None) -> str | None:
    """`word` cut at the longest syllable end for which `keep(cut)` holds (the shortest cut if none does); None when it
    has no cut shorter than itself. A trailing "+" stays after the dot."""
    core = word.rstrip("+")
    options = [cut for cut in clean_cuts(core, lang) if len(cut) < len(core)]
    if not options:
        return None
    tail = word[len(core):]
    return next((cut + tail for cut in options if keep is None or keep(cut + tail)), options[-1] + tail)


def _cuttable(token: str) -> bool:
    core = token.rstrip("+")
    return (len(core) > 5 and core.isalpha() and not re.fullmatch(r"[IVX]+", core)
            and not any(name in core for name in NEVER_CUT))


def fit(name: str, lang: str, fits: Callable[[str], bool]) -> str:
    """`name` shortened until `fits(name)` holds, in the order of the module's docstring: fillers, the monster's name,
    then the longest words at a syllable (hyphenated words part by part). Returns the shortest it could make."""
    name = name.strip()
    if fits(name):
        return name
    words = name.split(" ")
    for i in range(len(words) - 1, 0, -1):
        if words[i] in FILLERS[lang]:
            del words[i]
            if fits(" ".join(words)):
                return " ".join(words)
    tokens = re.split(r"([ \-])", shorten_monster(" ".join(words)))
    done: set[int] = set()
    while not fits("".join(tokens)):
        todo = [i for i, t in enumerate(tokens) if i not in done and _cuttable(t)]
        if not todo:
            break
        i = max(todo, key=lambda k: len(tokens[k]))
        done.add(i)
        cut = cut_word(tokens[i], lang, lambda c, i=i: fits("".join(tokens[:i] + [c] + tokens[i + 1:])))
        if cut is not None:
            tokens[i] = cut
    return _last_resort("".join(tokens), fits)


def _last_resort(name: str, fits: Callable[[str], bool]) -> str:
    """A name no syllable cut makes fit (a word of one syllable, an absurdly long name): its longest word cut by
    letters, as the game does, until it fits, then the name itself. The tests check that none of the ported monsters'
    names comes here."""
    words = name.split(" ")
    while not fits(" ".join(words)):
        long = [i for i, w in enumerate(words) if len(w.rstrip("+").rstrip(".")) > MIN_STEM + 1
                and w.rstrip("+") not in MONSTERS.values() and not any(name in w for name in NEVER_CUT)]
        if not long:
            break
        i = max(long, key=lambda k: len(words[k]))
        tail = "+" if words[i].endswith("+") else ""
        words[i] = words[i].rstrip("+").rstrip(".")[:-1] + "." + tail
    name = " ".join(words)
    while not fits(name) and len(name) > 1:         # nothing else left: the box is never overflowed
        name = name[:-1].rstrip()
    return name


def abbreviations(name: str) -> list[str]:
    """The abbreviations of a name: its words that end with a dot (no "+")."""
    return re.findall(r"[^\W\d_]+\.", name)
