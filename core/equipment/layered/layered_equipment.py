"""Layered equipment (option layered_equipment): a "Layered Equipment" line in the Smithy's menu opens a selector
of every armor and weapon look of the game, which writes the looks chosen into the variable layered_state; the
local hunter then wears them, the selector shows them on the Smithy's preview hunter, and the save keeps them.

The Smithy's menu is one of the lobby's facility menus (lyt\\lobby\\ui401, drawn by FUN_00a528e0 from per-menu
tables in .rodata). The patch adds the line to the Smithy's three menus in those tables, sends its choice to
the block layered_selector (equipment/layered/layered_selector.c), and gives the facility menu a menu 18 whose lines
the block fills. The look lists are the data block layered_data: MH4U's, and MH
Generations' when its pack is in the run (equipment/mhgen/looks.py; a "Generations" line on the selector's root). The
messages are added to E_makeshop by core/equipment/layered/texts.py, at the indices used here. The Felynes' looks
(felyne_looks.py, felyne_looks.c) add a line to the selector and their own hooks (FELYNE_CALLS). Update's executable
only.
"""

import struct
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from core.equipment.layered.felyne_looks import MESSAGES, NO_LOOKS, FelyneLooks, felyne_data
from core.equipment.layered.layered_rules import Relics, layered_rules, relic_trim
from core.equipment.layered.looks import NO_ARMOR as NO_ARMOR      # layered_state's "no model" (tests read it here)
from core.equipment.layered.looks import STATE_PARTS, STATE_WEAPONS, Looks, load_looks
from core.equipment.layered.menu_layout import forge_screen_data
from core.equipment.layered.prices import load_prices, shown_ranks
from core.equipment.layered.texts import (
    MAKESHOP_FILE, SET_BASE, gen_set_base, message_id, weapon_name_messages,
)
from core.equipment.tables.tables import EquipmentTables
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, branch_word, load_layout

if TYPE_CHECKING:
    from core.equipment.mhgen.looks import GenLooks

# The facility menu (FUN_00a528e0) and its per-menu tables (18 menus).
GAME_MENUS = 18
LAYERED_MENU = 18
MENU_COUNTS = 0xE045A0       # u8 per menu: its lines
MENU_LINES = 0xDF2814        # 7 x (u16 file, u16 message) per menu; file 0 and 3 are common files
MENU_ICONS = 0xE045C2        # 2 x u8 per menu: icon panes (0 = none)
MENU_TEXT = 0xE045F6         # u8 per menu: the text pane of each line
LINE_SIZE, MENU_SIZE = 4, 28
COUNT_LOAD = 0xA52920        # ldrb r0, [r1, r0]
LINES_LOAD = 0xA52C54        # ldr r0, [pc, #0x74] (= MENU_LINES)
TEXT_KIND = 0xA52C70         # cmp r1, #3
ICONS_WORD = 0xA52CB4        # literal pool word = MENU_ICONS
TEXT_WORD = 0xA52CC4         # literal pool word = MENU_TEXT
LINES_WORD = 0xA52CD0        # literal pool word = MENU_LINES (read by LINES_LOAD)
MENU_DRAWN = 0xA52D98        # ldrb r0, [r6, #0x1AC]: the menu drawn, at the end of the drawing (the page bar of 6, 7)
# The game's category menus the selector reuses: weapons (6, 7: 14 classes in two pages) and armor (8).
WEAPON_MENUS, ARMOR_MENU = (6, 7), 8
COMMON_NAME_BASE = 36        # common message 36 + equipment type = the type's name (Common_<lang>)

# The Smithy (FUN_009ad59c): its menus 17 (with Hone), 1 (with Decorations) and 2, and their lines.
SMITHY_MENUS = {17: 6, 1: 5, 2: 4}
SMITHY_COUNTS = {  # its cursor's line count in each, when it opens the menu (state 0)
    0x9AD728: (0xE3A03006, 0xE3A03007),   # mov r3, #6 -> #7 (menu 17)
    0x9AD76C: (0xE3A03005, 0xE3A03006),   # mov r3, #5 -> #6 (menu 1)
    0x9AD7B8: (0xE1A03000, 0xE3A03005),   # mov r3, r0 (4) -> mov r3, #5 (menu 2)
    0x9AD7BC: (0xE1A02000, 0xE3A02005),   # mov r2, r0 (4) -> mov r2, #5
}
SMITHY_MASK = 0x9AD6E4       # moveq r6, #0x10: Decorations locked -> line 4 disabled (the cursor's mask, FUN_009bc954)
SMITHY_MASK_WORD = 0x03A06010
NOP = 0xE320F000
SMITHY_PICK = 0x9AD890       # ldrh r0, [r4, #0x24]: the line chosen with A
SMITHY_OTHER = 0x9AD89C      # b 0x9AE280: the switch's default case (lines past 5)
SMITHY_STATES = 0x9AD668     # jump table of the Smithy's states (12 words)
SMITHY_UNUSED_STATE = 3      # its word is SMITHY_DONE: no code sets state 3
SMITHY_DESC = 0x9AE2FC       # ldrh r2, [r0]: the description of the highlighted line (table 0xEDBD2C)
SMITHY_DONE = 0x9AE280
LDRH_R0_R4_24 = 0xE1D402B4
LDRH_R2_R0 = 0xE1D020B0
ORIGINAL_WORDS = {COUNT_LOAD: 0xE7D10000, LINES_LOAD: 0xE59F0074, TEXT_KIND: 0xE3510003, MENU_DRAWN: 0xE5D601AC,
                  SMITHY_PICK: LDRH_R0_R4_24, SMITHY_MASK: SMITHY_MASK_WORD,
                  SMITHY_DESC: LDRH_R2_R0, ICONS_WORD: MENU_ICONS, TEXT_WORD: MENU_TEXT, LINES_WORD: MENU_LINES,
                  SMITHY_STATES + 4 * SMITHY_UNUSED_STATE: SMITHY_DONE,
                  **{at: words[0] for at, words in SMITHY_COUNTS.items()}}

# Model and save calls the block takes: place -> (the
# block's stub, the game function called there). The stubs call the game function and change its result for the
# local hunter (and the preview hunter), or copy layered_state into the save file / out of a loaded save.
ARMOR_MODEL = 0x2F4258       # FUN_002f4258(equipment, record, gender, fallback): an armor piece's model
WEAPON_MODEL = 0x2F0FD4      # FUN_002f0fd4(equipment, record): a weapon's model
MEM_COPY = 0x10ED68          # FUN_0010ed68(dst, src, size)
SAVE_COPY_OUT = 0xC2789C     # FUN_00c2789c(save, buffer, size): the save data into the file's buffer
HUNTER_SETUP = 0xB099AC      # FUN_00b099ac(hunter, info): a hunter's status from a player info
PART_DYE = 0xB0A978          # FUN_00b0a978(hunter, ref, model): a part model's colour
GAME_CALLS = {
    0xB0AC20: ("layered_armor_lobby", ARMOR_MODEL),     # FUN_00b0ab90: every piece a lobby hunter puts on
    0xAF9800: ("layered_armor_quest", ARMOR_MODEL),     # FUN_00af9408: a quest hunter's model, two branches
    0xAF9914: ("layered_armor_quest", ARMOR_MODEL),
    0xAF9838: ("layered_weapon_quest", WEAPON_MODEL),
    0xAF994C: ("layered_weapon_quest", WEAPON_MODEL),
    0x65EC24: ("layered_weapon_loader", WEAPON_MODEL),  # FUN_0065ebd4: the lobby loader's weapon request
    0x660194: ("layered_weapon_r5", WEAPON_MODEL),      # the lobby loader: weapon still the one loaded?
    0x66023C: ("layered_weapon_status_r7", WEAPON_MODEL),
    0x30C6E0: ("layered_weapon_r9", WEAPON_MODEL),      # FUN_0030c5b0: the weapon's sounds
    0x30C75C: ("layered_weapon_r9", WEAPON_MODEL),
    0x30C8B0: ("layered_weapon_r9", WEAPON_MODEL),
    0x30D2F4: ("layered_weapon_r6", WEAPON_MODEL),
    0x30D3B4: ("layered_weapon_r6", WEAPON_MODEL),
    0x2D6DA8: ("layered_weapon_gimmick", WEAPON_MODEL),  # FUN_002d6d80: the weapon gimmick's model (moving parts)
    # FUN_00bc14cc, the quest preloader (r4; the player's info at r4 + 0x460): the models it loads beforehand.
    0xBC1F30: ("layered_armor_preload", ARMOR_MODEL),   # the helm: which motion file
    0xBC209C: ("layered_armor_preload", ARMOR_MODEL),   # each part's model archive
    0xBC284C: ("layered_armor_preload", ARMOR_MODEL),   # parts 0-3 for FUN_002fb184
    0xBC2900: ("layered_armor_preload", ARMOR_MODEL),
    0xBC29CC: ("layered_armor_preload", ARMOR_MODEL),
    0xBC2A48: ("layered_armor_preload", ARMOR_MODEL),
    0xBC1F4C: ("layered_weapon_preload", WEAPON_MODEL),
    0xBC23B4: ("layered_weapon_preload", WEAPON_MODEL),
    0xBC23D4: ("layered_weapon_preload", WEAPON_MODEL),
    0xBC24BC: ("layered_weapon_preload", WEAPON_MODEL),
    # FUN_00bc07f8 (status r5) and FUN_00bc450c (status r6): the motion file chosen from the helm and weapon.
    0xBC0828: ("layered_armor_motion_r5", ARMOR_MODEL),
    0xBC0840: ("layered_weapon_motion_r5", WEAPON_MODEL),
    0xBC47B4: ("layered_armor_motion_r6", ARMOR_MODEL),
    0xBC47CC: ("layered_weapon_motion_r6", WEAPON_MODEL),
    0x5DD6EC: ("layered_save_load", MEM_COPY),          # FUN_005dd674: save data <- slot buffer (a save loaded)
    0x2ABE68: ("layered_save_store", SAVE_COPY_OUT),    # FUN_002abe04: the save file's buffer <- save data
    0xBDFF60: ("layered_select_hunter", HUNTER_SETUP),  # FUN_00bdfba0: the hunter select screen sets a slot's up
    # FUN_00b0a978(hunter, ref, model), a part's colour from its real piece's dye: the lobby loader's call (a part
    # loaded), FUN_00b0b6cc's five (every part again; the quest hunters' update; its last is a jump, GAME_JUMPS) and
    # the lobby hunters' per-frame pass (FUN_00b0b97c). The block draws a look's own or chosen colour there ("Colours").
    0x660098: ("layered_part_dye", PART_DYE),
    **{at: ("layered_part_dye", PART_DYE) for at in (0xB0B70C, 0xB0B720, 0xB0B738, 0xB0B750)},
    **{at: ("layered_part_dye", PART_DYE) for at in (0xB0BED0, 0xB0BEE4, 0xB0BEFC, 0xB0BF14, 0xB0BF2C)},
}
# Tail calls (`b`, after the caller's registers are popped): the hook stays a `b`, so the stub returns to the caller's
# caller. FUN_00b0b6cc's fifth part colour call.
GAME_JUMPS = {
    0xB0B76C: ("layered_part_dye", PART_DYE),
}
# A Felyne's gear, for the local player's cats (felyne_looks.c): place -> (the block's stub, the game function called
# there). The stubs make the call and give the look's
# number.
FELYNE_WEAPON_ID = 0x2F6C98  # FUN_002f6c98(equipment, id)
FELYNE_ARMOR_ID = 0x2F5F24   # FUN_002f5f24(equipment, type, id)
FELYNE_BODY_ID = 0x2F6C20    # FUN_002f6c20(equipment, 0, id, gender)
FELYNE_PAIR = 0x2F1438       # FUN_002f1438(equipment, [kind, 0, id])
FELYNE_PAIR_BODY = 0x2F1FA8  # FUN_002f1fa8(equipment, [kind, 0, id], gender)
FELYNE_SUIT = 0x2F8930       # FUN_002f8930(equipment, pair)
FELYNE_HEAD_CASE = 0x2F8A34  # FUN_002f8a34(equipment, pair): the helm that opens and closes
FELYNE_EFFECT = 0x69998C     # FUN_0069998c(manager, actor, model, pair)
FELYNE_QUEST_EFFECT = 0x699D5C   # FUN_00699d5c(manager, actor, model, pair)
FELYNE_SCENE_EFFECT = 0x6997C4   # FUN_006997c4(manager, model, pair, record)
FELYNE_SCENE_JOINTS = 0x69A484   # FUN_0069a484(manager, actor, pair, record)
FELYNE_CALLS = {
    # FUN_00696468: a lobby cat loads its pieces, r5 the actor
    0x696564: ("felyne_head_r5", FELYNE_ARMOR_ID),
    0x6965DC: ("felyne_head_r5", FELYNE_ARMOR_ID),
    0x69657C: ("felyne_body_r5", FELYNE_BODY_ID),
    0x6965F4: ("felyne_body_r5", FELYNE_BODY_ID),
    0x6965C0: ("felyne_weapon_r5", FELYNE_WEAPON_ID),
    # FUN_006980bc: which parts of the base model it shows, r4 the actor
    0x6980E8: ("felyne_head_r4", FELYNE_ARMOR_ID),
    0x698100: ("felyne_body_r4", FELYNE_BODY_ID),
    0x6973A0: ("felyne_suit_show", FELYNE_SUIT),         # FUN_00697348: a suit hides the helm (felyne_show_note)
    0x698238: ("felyne_suit_lobby", FELYNE_SUIT),
    0x698340: ("felyne_effect_gate", FELYNE_EFFECT),
    0x698354: ("felyne_effect_gate", FELYNE_EFFECT),
    0x698368: ("felyne_effect_gate", FELYNE_EFFECT),
    # FUN_00c33d24 and the talks' scenes: the body again (FUN_00697660), r4 the actor
    0xC33F60: ("felyne_body_r4", FELYNE_BODY_ID),
    0xC432F8: ("felyne_body_r4", FELYNE_BODY_ID),
    0xC435BC: ("felyne_body_r4", FELYNE_BODY_ID),
    # FUN_00a3725c: a live cat takes a record's gear, r7 the actor
    0xA372AC: ("felyne_weapon_r7", FELYNE_WEAPON_ID),
    0xA372C0: ("felyne_head_r7", FELYNE_ARMOR_ID),
    0xA372DC: ("felyne_body_r7", FELYNE_ARMOR_ID),
    # FUN_00bdfba0: the hunter select screen's cats, r6 the actor's record
    0xBE022C: ("felyne_select_weapon", FELYNE_WEAPON_ID),
    0xBE0240: ("felyne_select_head", FELYNE_ARMOR_ID),
    0xBE0258: ("felyne_select_body", FELYNE_BODY_ID),
    # FUN_0069a810: a quest cat's actor, r6 the compact record; a body with id 0 is the base's, no look reaches it
    0x69A914: ("felyne_quest_weapon", FELYNE_WEAPON_ID),
    0x69A92C: ("felyne_quest_head", FELYNE_ARMOR_ID),
    0x69A94C: ("felyne_quest_body", FELYNE_ARMOR_ID),
    0x697EA0: ("felyne_suit_quest", FELYNE_SUIT),        # FUN_00697d2c, r4 the actor
    0x697FA8: ("felyne_helm_case", FELYNE_HEAD_CASE),
    0x697FF0: ("felyne_quest_effect_gate", FELYNE_QUEST_EFFECT),
    0x69800C: ("felyne_quest_effect_gate", FELYNE_QUEST_EFFECT),
    0x699DBC: ("felyne_suit_quest", FELYNE_SUIT),        # FUN_00699d5c, r4 the actor
    0x97AB4C: ("felyne_suit_frame", FELYNE_SUIT),        # FUN_0097a938, r5 the actor: every frame, the helm's flag
    0x97ABA4: ("felyne_quest_effect_gate", FELYNE_QUEST_EFFECT),
    0x97ABC4: ("felyne_quest_effect_gate", FELYNE_QUEST_EFFECT),
    # FUN_00bc14cc: the quest preloader, its compact record at r4 + 0x468
    0xBC2ED8: ("felyne_preload_body", FELYNE_PAIR_BODY),
    0xBC2EF4: ("felyne_preload_head", FELYNE_PAIR),
    0xBC2F0C: ("felyne_preload_weapon", FELYNE_PAIR),
    0x9A8810: ("felyne_quest_body_again", FELYNE_BODY_ID),   # FUN_00991704: r5 the actor
    0x30EDDC: ("felyne_quest_sound", FELYNE_WEAPON_ID),      # FUN_0030e8c0: the actor at r7 + 0x40
    # FUN_001a0ab8: a cat in a cutscene, r5 the record, and its weapon's sounds (FUN_0030ab34: r4 0 main, else second)
    0x1A0F30: ("felyne_scene_suit", FELYNE_SUIT),
    0x1A1148: ("felyne_scene_effect_gate", FELYNE_SCENE_EFFECT),   # the head's
    0x1A15F4: ("felyne_scene_effect_gate", FELYNE_SCENE_EFFECT),   # the body's
    0x1A1608: ("felyne_scene_joints_gate", FELYNE_SCENE_JOINTS),
    0x1A19E4: ("felyne_scene_effect_gate", FELYNE_SCENE_EFFECT),   # the weapon's
    0x1A17F8: ("felyne_scene_weapon", FELYNE_WEAPON_ID),
    0x30AB74: ("felyne_scene_sound", FELYNE_WEAPON_ID),
    # FUN_00bc6d88: the main cat's preload for a cutscene, r1 the piece's pair in its record
    0xBC6DF8: ("felyne_scene_preload_weapon", FELYNE_PAIR),
    0xBC6EE8: ("felyne_scene_preload_head", FELYNE_PAIR),
    0xBC6FD0: ("felyne_scene_preload_body", FELYNE_PAIR_BODY),
    0xC1DC04: ("felyne_new_record", MEM_COPY),          # FUN_00c1db2c: a new cat's record is written
}
# Hooks of other instructions: place -> (the stub, the word it takes the place of).
FELYNE_WORDS = {
    0x697350: ("felyne_show_note", 0xE5910E2C),          # FUN_00697348: ldr r0, [r1, #0xe2c], r1 its actor
    0x1A0F54: ("felyne_scene_head", 0xE1D000B0),        # ldrh r0, [r0]: the helm's number, after FUN_002f286c
    0x1A12F4: ("felyne_scene_body", 0xE1D000B0),        # ldrh r0, [r0]: the body's
    0xBE0208: ("felyne_select_record", 0xE5940000),     # ldr r0, [r4]: a slot's cat was just copied into its actor
}
# A byte's mask on a model number, gone for the looks' numbers past 255: place -> (the game's word, ours).
FELYNE_NUMBERS = {
    0x1A0F58: (0xE21070FF, 0xE1B07000),                 # ands r7, r0, #0xFF -> movs r7, r0
    0x1A12F8: (0xE200A0FF, 0xE1A0A000),                 # and r10, r0, #0xFF -> mov r10, r0
    0x1A17FC: (0xE20060FF, 0xE1A06000),                 # and r6, r0, #0xFF -> mov r6, r0
    0x30AB7C: (0xE20000FF, 0xE1A00000),                 # and r0, r0, #0xFF -> mov r0, r0
}

# The looks message (equipment/layered/layered_online.c): the game's
# two sends of its own messages (place -> (the block's stub, the callee of the `bl` there)) and its dispatcher's way out
# for the types it does not know (a `b`).
ONLINE_GEAR = 0x248008       # FUN_00247f40, "my gear changed": bl FUN_00248a30(S, buffer, size) to every member
ONLINE_ANSWER = 0x2466D4     # FUN_002463d8, a join request or answer: bl FUN_0024a2a8(S, member, buffer, size)
ONLINE_RECEIVE = 0x2497F0    # FUN_002497d4, the dispatcher: b 0x2498A0, reached by the types 0x18 and up
# The render of other players' looks: FUN_00bc14cc's `bl FUN_002b3664` (the quest snapshot) and FUN_009d9410's
# `bl FUN_00a0050c` (the hall's frame: hunters dressed again)
ONLINE_SNAPSHOT = 0xBC1EFC
ONLINE_FRAME = 0x9D9430
# The Felynes' looks: FUN_002454f8's send of the cat's gear change (kind 8), and the two calls that build a hall
# cat from a compact (FUN_00c35ec4 when it is made, FUN_00a47160 when its owner changed its gear or a look arrived)
ONLINE_FELYNE_GEAR = 0x2455E4
ONLINE_HALL_CATS = (0xC35F88, 0xA47194)
ONLINE_CALLS = {ONLINE_GEAR: ("layered_net_gear", 0x248A30), ONLINE_ANSWER: ("layered_net_answer", 0x24A2A8),
                ONLINE_SNAPSHOT: ("layered_quest_snapshot", 0x2B3664), ONLINE_FRAME: ("layered_town_frame", 0xA0050C),
                ONLINE_FELYNE_GEAR: ("layered_net_gear", 0x248A30),
                **{at: ("layered_hall_cat", 0xC25A3C) for at in ONLINE_HALL_CATS}}
ONLINE_DONE = 0x2498A0
WIRE_MODELS = 256            # the looks message holds a weapon model in a byte

# Where the save file keeps layered_state (its buffer + 8 + SAVE_AT, 0x3C bytes; layered_selector.c SAVE_AT):
# zero in every save checked and read by no code; below 0x12600, the part of the save data the file holds. The
# game's save data in memory never holds it: it is cleared there as soon as a save is loaded. A save of an earlier
# build wrote 0x32 bytes: the colours past them are zero there, the looks' own.
SAVE_AT = 0x125C0
SAVE_MAGIC = 0x4C            # its byte 1 (layered_state.reserved) in the save: the bytes are a layered_state

# The block layered_data (struct data in layered.h): a header with two catalogs (struct catalog: sets, XX's per-part
# models, each class's weapons, their counts, the sets' own colours), MH4U's and XX's, the screens' numbers
# (menu_layout.forge_screen_data), and their records, then the palette of the sets' colours.
DATA_MAGIC = 0x5259414C      # "LAYR"
# sets, parts (0: one model pair per set), weapons of each class; counts; sets, colours (u16 offset, 0: none)
CATALOG = "II14I14H2H"
# magic; the catalogs; the messages of the description, a blank line, the counter and Weapons; the class of each line of
# the game's weapon menus; the message of the weapons' key bar; the game's per-menu tables, extended to menu 18; the
# palette's count of colours and offset
HEADER = struct.Struct("<I" + 2 * CATALOG + "4H14BH38B19BBH")
SET_RECORD = struct.Struct("<3H2B")        # male, female, name, parts (layered_state order), flags (below)
PARTS_RECORD = struct.Struct("<10H")      # an XX set's (male, female) per part
WEAPON_RECORD = struct.Struct("<3HBx")    # model, name, weapon id (0: it has none), rank (1-3)
# A set's own colour per part (layered_state order), male then female: an entry of the palette (RGB, 3 bytes each),
# NO_COLOUR when not known (the real piece's colour shows). MH4U's: the default dye (the armor record's ARMOR_DYE in
# the game's DYE_TABLE) of the look's piece of that part and gender; XX's: its series' (mhgen.looks GenSet.colours).
# Each catalog keeps one byte per set (Colours.codes): below the palette's count, the one entry all of the set's known
# colours are; from there on, a COLOUR_RECORD of the table after the palette (a set whose parts or genders differ);
# NO_COLOUR, none known. Most sets have one colour: a record each would not fit the block with XX's catalog.
COLOUR_RECORD = struct.Struct("<10B")
NO_COLOUR = 0xFF
DYE_TABLE, COLOURS = 0xF57750, 70   # MH4U's default dyes: RGB triplets (FUN_002f869c; new_gear/new_armor.py COLOURS)
ARMOR_DYE = 0x13             # an armor record's byte picking its default dye (new_gear/new_armor.py COLOUR)
DATA_OFFSETS = 0x10000       # the catalogs' colours and the palette are u16 offsets
SET_WHOLE, SET_RANK_SHIFT = 1, 1          # a set's flags: bit 0 worn as a whole; bits 1-2 its rank (1-3)
ICONS_AT, TEXT_AT = 0xDC, 0x102  # the per-menu tables' copies in the header
SCREEN_AT = 0x118            # struct forge_screen
CUSTOM_NAME = 0x8000         # a weapon name that is an E_makeshop message, not the weapon's own
assert HEADER.size == SCREEN_AT and ICONS_AT + 2 * (GAME_MENUS + 1) == TEXT_AT
FELYNE_MESSAGES = {key: message_id(key) for key in MESSAGES}    # the screens' lines of the Felynes


def _word(code: bytes, at: int) -> int:
    return struct.unpack_from("<I", code, at - BASE_ADDRESS)[0]


def supports_layered_equipment(code: bytes) -> bool:
    """True if every place the patch changes holds what the update's executable has there."""
    if len(code) < MENU_COUNTS + GAME_MENUS - BASE_ADDRESS:
        return False
    if any(_word(code, at) != word for at, word in ORIGINAL_WORDS.items()):
        return False
    if code[SMITHY_OTHER - BASE_ADDRESS:SMITHY_OTHER - BASE_ADDRESS + 4] != branch_word(SMITHY_OTHER, SMITHY_DONE):
        return False
    if any(_word(code, at) != word for at, (_, word) in FELYNE_WORDS.items()):
        return False
    if any(_word(code, at) != words[0] for at, words in FELYNE_NUMBERS.items()):
        return False
    if any(bl_target(code, at) != callee for at, (_, callee) in {**GAME_CALLS, **FELYNE_CALLS, **ONLINE_CALLS}.items()):
        return False
    if any(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4] != branch_word(at, callee)
           for at, (_, callee) in GAME_JUMPS.items()):
        return False
    receive = ONLINE_RECEIVE - BASE_ADDRESS
    if code[receive:receive + 4] != branch_word(ONLINE_RECEIVE, ONLINE_DONE):
        return False
    counts = code[MENU_COUNTS - BASE_ADDRESS:MENU_COUNTS - BASE_ADDRESS + GAME_MENUS]
    return all(counts[menu] == lines and _word(code, _line(menu, lines)) == 0 for menu, lines in SMITHY_MENUS.items())


def _line(menu: int, line: int) -> int:
    return MENU_LINES + menu * MENU_SIZE + line * LINE_SIZE


def _menu_types(code: bytes, menus) -> list[int]:
    """Equipment type of each line of the game's category menus (their names are Common message 36 + type)."""
    types = []
    for menu in menus:
        for line in range(code[MENU_COUNTS - BASE_ADDRESS + menu]):
            file, message = struct.unpack_from("<2H", code, _line(menu, line) - BASE_ADDRESS)
            if file != 0:
                raise CodeSpaceError(f"unexpected line {line} of the game's menu {menu}")
            types.append(message - COMMON_NAME_BASE)
    return types


def _catalog(start: int, sets: bytes, parts: bytes, weapons: list[bytes], colours: bytes) -> tuple[list[int], bytes]:
    """The header fields (CATALOG) and the records of one catalog placed at `start`: sets, their parts records
    (if any), the weapons of each class (STATE_WEAPONS), then the sets' colours (a byte each, Colours.codes)."""
    body = bytearray(sets)
    parts_at = start + len(body) if parts else 0
    body += parts
    offsets = []
    for records in weapons:
        offsets.append(start + len(body))
        body += records
    counts = [len(records) // WEAPON_RECORD.size for records in weapons]
    colours_at = start + len(body)
    body += colours
    if colours_at + len(colours) > DATA_OFFSETS:
        raise CodeSpaceError("the look lists outgrow the u16 offsets of their colours (layered.h struct catalog)")
    return [start, parts_at, *offsets, *counts, len(sets) // SET_RECORD.size, colours_at], bytes(body)


class Colours:
    """The sets' own colours: the palette (0xRRGGBB, each once, in the order first named), then the records of the sets
    whose parts or genders differ (each once). Every set's record is named (entry) before any is coded (codes): a
    set's byte tells a palette entry from a record by the palette's final count."""

    def __init__(self) -> None:
        self.palette: dict[int, int] = {}
        self.records: dict[bytes, int] = {}

    def entry(self, colour: int | None) -> int:
        if colour is None:
            return NO_COLOUR
        if colour not in self.palette:
            if self.records:
                raise ValueError("a colour named after the sets were coded")
            if len(self.palette) == NO_COLOUR:
                raise CodeSpaceError(f"more than {NO_COLOUR} own colours: layered.h struct colours holds a byte")
            self.palette[colour] = len(self.palette)
        return self.palette[colour]

    def codes(self, records: list[tuple[int, ...]]) -> bytes:
        """One byte per set (COLOUR_RECORD's comment) for the sets' records of palette entries."""
        out = bytearray()
        for record in records:
            known = set(record) - {NO_COLOUR}
            if len(known) <= 1:
                out.append(known.pop() if known else NO_COLOUR)
                continue
            code = self.records.setdefault(COLOUR_RECORD.pack(*record), len(self.palette) + len(self.records))
            if code >= NO_COLOUR:
                raise CodeSpaceError(f"more than {NO_COLOUR} own colours and colour records: layered.h struct catalog "
                                     "holds a set's in a byte")
            out.append(code)
        return bytes(out)

    def data(self) -> bytes:
        return b"".join(bytes((c >> 16, c >> 8 & 0xFF, c & 0xFF)) for c in self.palette) + b"".join(self.records)


def _mh4u_colours(code: bytes, looks: Looks, palette: Colours) -> list[tuple[int, ...]]:
    """The colour records of MH4U's sets: a look's piece of each part and gender (ArmorLook.pieces: one, or the male's
    and the female's) gives its default dye. `code`: the run's executable, whose tables keep every piece's dye where it
    was (the model shuffle moves models, not colours)."""
    tables = EquipmentTables.read(code)
    dyes = code[DYE_TABLE - BASE_ADDRESS:DYE_TABLE - BASE_ADDRESS + 3 * COLOURS]

    def colour(part: str, piece: int) -> int | None:
        records = tables.armor[part]
        index = records[piece].data[ARMOR_DYE] if piece < len(records) else COLOURS
        return int.from_bytes(dyes[3 * index:3 * index + 3], "big") if index < COLOURS else None

    out = []
    for look in looks.armor:
        entries = []
        for part in STATE_PARTS:
            pieces = look.pieces.get(part, ()) if part in look.parts else ()
            entries += [palette.entry(colour(part, pieces[female if len(pieces) == 2 else 0])) if pieces
                        else NO_COLOUR for female in (0, 1)]
        out.append(tuple(entries))
    return out


def _gen_colours(gen: "GenLooks", palette: Colours) -> list[tuple[int, ...]]:
    """The colour records of XX's sets (GenSet.colours)."""
    return [tuple(palette.entry(c) for part in STATE_PARTS for c in s.colours.get(part, (None, None)))
            for s in gen.sets]


def _wire_model(model: int) -> None:
    """The looks message (layered_online.c) carries a weapon model in one byte."""
    if not 0 <= model < WIRE_MODELS:
        raise CodeSpaceError(f"weapon look model {model} does not fit the looks message (a byte): "
                             "equipment/layered/layered_online.c")


def _rank(look, shown: Mapping[str, int]) -> int:
    """A look's rank for the records (the screens' filter and rank gate): 1 low, 2 high, 3 G; `shown` moves a look up
    (prices.shown_ranks: what it asks first drops at a higher rank)."""
    rank = max(look.rank, shown.get(look.key, 0))
    if not 1 <= rank <= 3:
        raise CodeSpaceError(f"look {look.key} has rank {rank}, not 1-3")
    return rank


def _set_flags(look, shown: Mapping[str, int], whole: bool | None = None) -> int:
    """A set record's flags: whole set in bit 0, the rank from bit 1 (read by layered_forge.c)."""
    return (SET_WHOLE if (look.whole if whole is None else whole) else 0) | _rank(look, shown) << SET_RANK_SHIFT


def _mh4u_records(looks: Looks, relics: Relics, shown: Mapping[str, int]) -> tuple[bytes, list[bytes]]:
    """A relic look cut down to the parts that stay (xx_prices.relic_offers) lists only those and is not a whole set:
    its whole button covers what is left and leaves the other parts as they are."""
    def parts(look) -> tuple[str, ...]:
        return relics.armor.get(look.key, look.parts)

    sets = b"".join(SET_RECORD.pack(look.male, look.female, SET_BASE + index,
                                    sum(1 << STATE_PARTS.index(part) for part in parts(look)),
                                    _set_flags(look, shown, False if look.key in relics.armor else None))
                    for index, look in enumerate(looks.armor))
    custom = iter(weapon_name_messages(looks))
    weapons = []
    for key in STATE_WEAPONS:
        records = bytearray()
        for look in looks.weapons[key]:
            name = CUSTOM_NAME | next(custom) if look.weapon < 0 or look.number else look.weapon
            _wire_model(look.model)
            records += WEAPON_RECORD.pack(look.model, name, max(look.weapon, 0), _rank(look, shown))
        weapons.append(bytes(records))
    return sets, weapons


def _gen_records(looks: Looks, gen: "GenLooks", shown: Mapping[str, int]) -> tuple[bytes, bytes, list[bytes]]:
    """XX's sets (named from gen_set_base on), their models per part, and their weapons, named after the sets."""
    sets, parts = bytearray(), bytearray()
    base = gen_set_base(looks)
    for index, s in enumerate(gen.sets):
        sets += SET_RECORD.pack(0, 0, base + index, sum(1 << STATE_PARTS.index(part) for part in s.look.parts),
                                _set_flags(s.look, shown))
        parts += PARTS_RECORD.pack(*(model for part in STATE_PARTS for model in s.models.get(part, (0, 0))))
    message = base + len(gen.sets)
    weapons = []
    for key in STATE_WEAPONS:
        records = bytearray()
        for look in gen.weapons[key]:
            _wire_model(look.model)
            records += WEAPON_RECORD.pack(look.model, CUSTOM_NAME | message, 0, _rank(look, shown))
            message += 1
        weapons.append(bytes(records))
    return bytes(sets), bytes(parts), weapons


def layered_data(code: bytes, looks: Looks | None = None, gen: "GenLooks | None" = None,
                 curated: Mapping | None = None, relics: Relics | None = None,
                 prices: Mapping | None = None) -> bytes:
    """The block layered_data: header (with the game's per-menu tables extended to menu 18) and the screens' numbers,
    then MH4U's catalog (armor looks, the weapon looks of every class) and, with `gen`, XX's. `relics`: the free looks
    cut down (default: relic_trim of the price table); `prices`: the price table, whose records may move a look up a
    rank (default: generated/layered_prices.json)."""
    looks = looks or load_looks()
    prices = prices if prices is not None else load_prices()
    relics = relics or relic_trim(looks, gen, prices)
    shown = shown_ranks(prices)
    classes = [t - 7 for t in _menu_types(code, WEAPON_MENUS)]
    if sorted(classes) != list(range(len(STATE_WEAPONS))):
        raise CodeSpaceError("the game's weapon category menus are not what the screens expect")
    screen = forge_screen_data(curated)
    start = SCREEN_AT + len(screen)
    colours = Colours()
    with_gen = gen is not None and not gen.empty
    mh4u_colours = _mh4u_colours(code, looks, colours)
    gen_colours = _gen_colours(gen, colours) if with_gen else []    # every colour named before the first set's code
    sets, weapons = _mh4u_records(looks, relics, shown)
    mh4u, body = _catalog(start, sets, b"", weapons, colours.codes(mh4u_colours))
    generations = [0] * len(mh4u)
    if with_gen:
        generations, gen_body = _catalog(start + len(body), *_gen_records(looks, gen, shown),
                                         colours.codes(gen_colours))
        body += gen_body
    palette_at = start + len(body)
    body += colours.data()
    if palette_at + len(colours.data()) > DATA_OFFSETS:
        raise CodeSpaceError("the look lists outgrow the u16 offset of their palette (layered.h struct data)")
    icons = code[MENU_ICONS - BASE_ADDRESS:MENU_ICONS - BASE_ADDRESS + 2 * GAME_MENUS] + bytes(2)
    text = code[MENU_TEXT - BASE_ADDRESS:MENU_TEXT - BASE_ADDRESS + GAME_MENUS] + bytes(1)
    messages = [message_id(key) for key in ("entry_help", "blank", "counter", "weapons")]
    return HEADER.pack(DATA_MAGIC, *mh4u, *generations, *messages, *classes, message_id("help_row_weapons"), *icons,
                       *text, len(colours.palette), palette_at) + screen + body


def patch_layered_equipment(code: bytes, layout: Layout | None = None, looks: Looks | None = None,
                            gen: "GenLooks | None" = None, felynes: FelyneLooks = NO_LOOKS,
                            item_ids: Mapping[str, int] | None = None, prices: Mapping | None = None,
                            ported: Collection[str] | None = None, by_rank: bool = True) -> bytes:
    """`code` (the update's executable, with the ported monsters' gear if the run has it) with the Smithy's Layered Gear
    line and its screens; `gen`: XX's looks, when its pack is in the run; `felynes`: the Felynes' looks, when their
    models are; `item_ids`: the new items of the ported monsters in the run by English name, which a look's recipe may
    name (layered_rules.py); `prices`: the price table (default: generated/layered_prices.json); `ported`: the keys of
    the ported monsters in the run (None: every look with `ported` items that resolve counts as his); `by_rank`: the
    looks of the high and G ranks open with their rank (option layered_by_rank), False: every look from the start."""
    if not supports_layered_equipment(code):
        raise CodeSpaceError("unexpected code at the Smithy's menu: layered equipment needs the update's executable")
    layout = layout or load_layout()
    resolved = looks or load_looks()
    prices = prices if prices is not None else load_prices()
    relics = relic_trim(resolved, gen, prices)
    data = layered_data(code, resolved, gen, relics=relics, prices=prices)
    size = len(layout.block("layered_data").data)
    if len(data) > size:
        raise CodeSpaceError(f"the look lists take {len(data)} bytes, more than the block layered_data ({size}): "
                             "raise its size in game/executable/blocks.py")
    out = bytearray(code)
    layout.place(out, "layered_selector")
    layout.place(out, "layered_data", data + bytes(size - len(data)))
    layout.place(out, "felyne_looks_data", felyne_data(felynes, FELYNE_MESSAGES))
    rules = layered_rules(resolved, gen, felynes, tables=EquipmentTables.read(code), item_ids=item_ids, prices=prices,
                          relics=relics, ported=ported, by_rank=by_rank)
    room = len(layout.block("layered_rules").data)
    if len(rules) > room:
        raise CodeSpaceError(f"the look rules take {len(rules)} bytes, more than the block layered_rules ({room}): "
                             "raise its size in game/executable/blocks.py")
    layout.place(out, "layered_rules", rules + bytes(room - len(rules)))

    def symbol(name: str) -> int:
        return layout.symbol("layered_selector", name)

    def put(at: int, word: int) -> None:
        struct.pack_into("<I", out, at - BASE_ADDRESS, word)

    # The facility menu: menu 18's lines and count, common message files of ours, and the cats' names.
    layout.hook(out, COUNT_LOAD, symbol("layered_menu_count"), original=struct.pack("<I", ORIGINAL_WORDS[COUNT_LOAD]))
    layout.hook(out, LINES_LOAD, symbol("layered_menu_lines"), original=struct.pack("<I", ORIGINAL_WORDS[LINES_LOAD]))
    layout.hook(out, TEXT_KIND, symbol("layered_text_kind"), original=struct.pack("<I", ORIGINAL_WORDS[TEXT_KIND]))
    layout.hook(out, MENU_DRAWN, symbol("layered_menu_drawn"), original=struct.pack("<I", ORIGINAL_WORDS[MENU_DRAWN]))
    data_at = layout.address("layered_data")
    put(ICONS_WORD, data_at + ICONS_AT)
    put(TEXT_WORD, data_at + TEXT_AT)
    # The Smithy's menus get the line, and its cursor one line more.
    for menu, lines in SMITHY_MENUS.items():
        struct.pack_into("<2H", out, _line(menu, lines) - BASE_ADDRESS, MAKESHOP_FILE, message_id("entry"))
        out[MENU_COUNTS - BASE_ADDRESS + menu] = lines + 1
    for at, (_, word) in SMITHY_COUNTS.items():
        put(at, word)
    # Menu 2 (Decorations locked) has 4 lines, so the game's mask bit 4 disables no line of its own, only ours.
    put(SMITHY_MASK, NOP)
    layout.hook(out, SMITHY_PICK, symbol("layered_smithy_pick"), original=struct.pack("<I", LDRH_R0_R4_24))
    layout.hook(out, SMITHY_OTHER, symbol("layered_smithy_open"), link=False,
                original=branch_word(SMITHY_OTHER, SMITHY_DONE))
    put(SMITHY_STATES + 4 * SMITHY_UNUSED_STATE, symbol("layered_smithy_update"))
    layout.hook(out, SMITHY_DESC, symbol("layered_smithy_desc"), original=struct.pack("<I", LDRH_R2_R0))
    # The hunters' models and the save.
    for at, (stub, callee) in GAME_CALLS.items():
        layout.hook(out, at, symbol(stub), calls=callee)
    for at, (stub, callee) in GAME_JUMPS.items():
        layout.hook(out, at, symbol(stub), link=False, original=branch_word(at, callee))
    # The Felynes' gear.
    for at, (stub, callee) in FELYNE_CALLS.items():
        layout.hook(out, at, symbol(stub), calls=callee)
    # The looks message: the game's sends, and the dispatcher's way out for the types it does not know.
    for at, (stub, callee) in ONLINE_CALLS.items():
        layout.hook(out, at, symbol(stub), calls=callee)
    layout.hook(out, ONLINE_RECEIVE, symbol("layered_net_receive_hook"), link=False,
                original=branch_word(ONLINE_RECEIVE, ONLINE_DONE))
    for at, (stub, word) in FELYNE_WORDS.items():
        layout.hook(out, at, symbol(stub), original=struct.pack("<I", word))
    for at, (_, word) in FELYNE_NUMBERS.items():
        put(at, word)
    return bytes(out)
