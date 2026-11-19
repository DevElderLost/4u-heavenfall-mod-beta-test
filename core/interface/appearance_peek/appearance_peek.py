"""Hold L in Change Appearance to see the hunter: while L is
held the top screen draws no interface, and a cue in a corner ("L Hide Interface") says so.

The executable: the hunter edit's five updates call the box's View Mode (FUN_00a8bb9c) first of all each frame; those
calls go to appearance_peek (appearance_peek.c, a unit of the block mod_settings_code), which hides the interface while
L is held and else lets the game's function answer. Its data (`data_block`) names the cue and its word.

The RomFS: the cue is a root group of our own in ui401 (the lobby's facility menu, which every town area loads, on the
top screen), copies of the forge's own pieces (the key bar tinted black, ui034's L key, a text pane at the key bar's
font); its word is a message appended to the lobby's ItemBox text file of each language. The bar's width is the word's,
measured with the game font's advances. Curated: core/game/data/curated/appearance_peek.json.
"""

import json
import math
import struct
from collections.abc import Iterator, Mapping

from core.game.data.paths import CURATED_DIR
from core.game.executable.blocks import GAME_SYMBOLS
from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout
from core.game.files.arc import parse_arc, write_arc
from core.game.files.gui.lfd import LFD_TYPE_HASH, glyphs
from core.game.files.gui.lyt import name_hash, parse_lyt
from core.game.files.text.lmd import LMD_TYPE_HASH, parse_lmd, write_lmd
from core.interface.hud.build import LANGUAGES, GameFiles

CODE = "mod_settings_code"
DATA = "appearance_peek_data"
ENTRY = "appearance_peek"
# 1 while the hook keeps the top screen's view from the main GUI manager: the game GUI engine (single-screen mode, which
# gives a manager every view it places a group in) leaves that view out then
HIDDEN = "top_screen_hidden"
# The hunter edit's five updates (one per choice of Change Appearance, from the box's jump table at 0x9CA51C) and
# their call of FUN_00a8bb9c(scene, menu, 1), the View Mode, before any key is read.
CALLS = (0xA9EDEC,      # FUN_00a9ed84
         0xA9C0D8,      # FUN_00a9c070
         0xAA38BC,      # FUN_00aa3854
         0xA9A65C,      # FUN_00a9a5f8
         0xA98424)      # FUN_00a983bc
VIEW_MODE = GAME_SYMBOLS["box_view_mode"]
DATA_RECORD = struct.Struct("<2I2H2B2x")    # appearance_peek.c struct peek_data

ITEM_BOX_FILE = 0x16    # ItemBox among the lobby's message files (the table at 0xF007E4)
ITEM_BOX_ARCS = ("core_lobby.arc", "core_arena.arc", "core_result.arc")   # each holds its own copy of ItemBox
GAME_MESSAGES = 212     # ItemBox's own messages, in every language
FONT = "loc\\lyt\\font\\font_loc"       # the game's text font, in core_common.arc
FONT_SIZE_AT = 0x14                     # lfd: the font's size in texels

GROUP = "ui401_peek_cue"
BAR, KEY, WORD = "pk_bar", "pk_key", "pk_m_word"
WORD_ROOM = 24          # characters the word's text pane holds


class AppearancePeekError(ValueError):
    pass


def load_settings(curated: Mapping | None = None) -> Mapping:
    return curated or json.loads((CURATED_DIR / "appearance_peek.json").read_text(encoding="utf-8"))


# ----- the executable -------------------------------------------------------------------------------------------------

def supports_appearance_peek(code: bytes) -> bool:
    """The five updates call the View Mode where the update's executable does."""
    return all(bl_target(code, at) == VIEW_MODE for at in CALLS)


def data_block(message: int, curated: Mapping | None = None) -> bytes:
    """What appearance_peek.c reads: the cue's group and word, the word's message in ItemBox (0: no cue), its draw
    priority and the frames without the edit before it goes."""
    settings = load_settings(curated)
    if not 0 <= message <= 0xFFFF:
        raise AppearancePeekError(f"message {message} out of range")
    return DATA_RECORD.pack(name_hash(GROUP), name_hash(WORD), ITEM_BOX_FILE, message, settings["priority"],
                            settings["misses"])


def patch_appearance_peek(code: bytes, message: int, layout: Layout | None = None,
                          curated: Mapping | None = None) -> bytes:
    """`code` with the five updates' call of the View Mode going to appearance_peek (the block mod_settings_code, which
    patch_mod_options placed), and its data. `message`: the word's message in ItemBox (`peek_message`). Refuses an
    executable where a call is not the game's."""
    if not supports_appearance_peek(code):
        raise CodeSpaceError("the hunter edit's calls of its View Mode are not the update's: already patched or "
                             "another game")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, DATA, data_block(message, curated))
    entry = layout.symbol(CODE, ENTRY)
    for at in CALLS:
        layout.hook(out, at, entry, calls=VIEW_MODE)
    return bytes(out)


# ----- the word -------------------------------------------------------------------------------------------------------

def _item_box(parsed, lang: str):
    name = f"{lang}\\msg\\lobby\\ItemBox_{lang}"
    return next((e for e in parsed.entries if e.name == name and e.type_hash == LMD_TYPE_HASH), None)


def with_word(arc: bytes, lang: str, curated: Mapping | None = None) -> bytes:
    """`arc` with the cue's word appended to its ItemBox of `lang` (unchanged if its last message is the word)."""
    word = load_settings(curated)["words"][lang]
    parsed = parse_arc(arc)
    entry = _item_box(parsed, lang)
    if entry is None:
        raise AppearancePeekError(f"no ItemBox_{lang} in the ARC")
    lmd = parse_lmd(entry.data)
    if lmd.message_count < GAME_MESSAGES:
        raise AppearancePeekError(f"ItemBox_{lang} has {lmd.message_count} messages, fewer than the game's "
                                  f"{GAME_MESSAGES}")
    if lmd.message_count > GAME_MESSAGES and lmd.message(lmd.message_count - 1) == word:
        return arc
    lmd.add_message(word)
    entry.data = write_lmd(lmd)
    return write_arc(parsed)


def peek_message(read, curated: Mapping | None = None) -> int:
    """The word's message in ItemBox, the same in every language and ARC of the files written: `read(path)` gives a
    file's bytes (the written ARCs falling back to the game's). Call it after `peek_files`."""
    found = set()
    for lang in LANGUAGES:
        word = load_settings(curated)["words"][lang]
        for arc_name in ITEM_BOX_ARCS:
            entry = _item_box(parse_arc(read(f"{lang}/data/{arc_name}")), lang)
            lmd = parse_lmd(entry.data) if entry is not None else None
            if lmd is None or lmd.message_count <= GAME_MESSAGES or lmd.message(lmd.message_count - 1) != word:
                raise AppearancePeekError(f"{lang}/data/{arc_name}: ItemBox does not end with the cue's word")
            found.add(lmd.message_count - 1)
    if len(found) != 1:
        raise AppearancePeekError(f"the cue's word is not at one message in every ItemBox: {sorted(found)}")
    return found.pop()


# ----- the cue --------------------------------------------------------------------------------------------------------

def text_width(font: bytes, text: str, size: float) -> int:
    """Pixels `text` takes at the font size `size`: the font's advances scaled from its own size (an unknown character
    as wide as "M")."""
    advances = {glyph.code: glyph.advance for glyph in glyphs(font)}
    texels = struct.unpack_from("<I", font, FONT_SIZE_AT)[0]
    wide = advances.get(ord("M"), texels)
    return math.ceil(sum(advances.get(ord(c), wide) for c in text) * size / texels)


def cue_rects(settings: Mapping, width: int) -> dict[str, tuple[int, int, int, int]]:
    """The cue's panes on the top screen for a word `width` pixels wide: the bar, the L key at its left end (a square
    of the bar's height), the word after it."""
    cue = settings["cue"]
    x, y, height, key = cue["x"], cue["y"], cue["height"], cue["key"]
    word_x = x + key + cue["gap"]
    word_h = cue["font"] + 1
    return {BAR: (x, y, key + cue["gap"] + width + cue["padding"], height),
            KEY: (x, y + (height - key) // 2, key, key),
            WORD: (word_x, y + (height - word_h) // 2, width + cue["padding"], word_h)}


def font_of(common_arc: bytes, lang: str) -> bytes:
    """The text font of `lang`'s core_common.arc."""
    for entry in parse_arc(common_arc).entries:
        if entry.type_hash == LFD_TYPE_HASH and entry.name in (FONT, f"{lang}\\{FONT}"):
            return entry.data
    raise AppearancePeekError(f"no {FONT} in {lang}'s core_common.arc")


def add_cue_panes(data: bytes, sources: Mapping, lang: str, font: bytes, curated: Mapping | None = None) -> bytes:
    """A ui401 layout with the cue's group (unchanged if it has it). `sources`: the language's layouts the panes copy
    (equipment.layered.menu_layout.forge_sources: ui034 is the one used)."""
    from core.equipment.layered.menu_layout import (   # not at import: the equipment package is large
        FRAME_LAYOUT, GROUP_TEMPLATE, KEY_BAR, KEY_TEXT, PaneBuilder,
    )
    layout = parse_lyt(data)
    if any(pane.name == GROUP for pane in layout.panes):
        return bytes(data)
    settings = load_settings(curated)
    rects = cue_rects(settings, text_width(font, settings["words"][lang], settings["cue"]["font"]))
    build = PaneBuilder(layout, sources)
    layout.insert_group(layout.find(GROUP_TEMPLATE), GROUP)
    build.sprite(GROUP, build.template(FRAME_LAYOUT, KEY_BAR), BAR, rects[BAR], tuple(settings["colours"]["bar"]))
    build.sprite(GROUP, build.template(FRAME_LAYOUT, "ui034_L"), KEY, rects[KEY])
    build.text(GROUP, build.template(FRAME_LAYOUT, KEY_TEXT), WORD, rects[WORD], WORD_ROOM, settings["cue"]["font"],
               align=0, colour=tuple(settings["colours"]["word"]))
    return bytes(layout.data)


def peek_files(rom: GameFiles, files: Mapping[str, bytes] | None = None,
               curated: Mapping | None = None) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every language's core_lobby.arc, core_arena.arc and core_result.arc: the cue's word
    appended to ItemBox in each, and the cue's group in the lobby's ui401. An ARC already in `files` (an earlier
    step's) is changed as it is, the others start from the game's."""
    from core.equipment.layered.menu_layout import with_ui401
    files = files or {}
    for lang in LANGUAGES:
        common = files.get(f"{lang}/data/core_common.arc") or rom.read(f"{lang}/data/core_common.arc")
        title = files.get(f"{lang}/data/core_title.arc") or rom.read(f"{lang}/data/core_title.arc")
        font = font_of(common, lang)
        for arc_name in ITEM_BOX_ARCS:
            path = f"{lang}/data/{arc_name}"
            arc = with_word(files.get(path) or rom.read(path), lang, curated)
            if arc_name == "core_lobby.arc":
                arc = with_ui401(arc, lang, common, title,
                                 lambda data, sources, lang=lang, font=font: add_cue_panes(data, sources, lang, font,
                                                                                           curated))
            yield path, arc


__all__ = ["CALLS", "GROUP", "AppearancePeekError", "add_cue_panes", "cue_rects", "data_block", "font_of",
           "load_settings", "patch_appearance_peek", "peek_files", "peek_message", "supports_appearance_peek",
           "text_width", "with_word"]
