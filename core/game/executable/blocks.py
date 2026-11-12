"""What goes in the executable's free space: every block and variable, declared once.

tools/build/build_code_space.py builds the sources, places everything in the regions of `code_space.REGIONS`
and writes generated/code_space.json. Never give a block an address: the builder chooses it.

A source refers to other blocks, variables, the game functions of GAME_SYMBOLS and the bounds of a
region (`<region>_start`, `<region>_end`) by name (an undefined symbol in the source); the builder
resolves those names when it links.
"""

from dataclasses import dataclass

# Room of the key quest table (interface/key_quests/executable/key_quests.py): u16 ids and an end mark.
KEY_QUEST_ROOM = 128

# Single-screen mode (interface/single_screen/executable/single_screen.py): the draw order table's room, {name hash,
# offset} pairs after a count.
SINGLE_SCREEN = "single_screen"
SINGLE_SCREEN_ROOM = 160
SINGLE_SCREEN_TABLE_SIZE = 4 + 8 * SINGLE_SCREEN_ROOM
CREATION_CAMERA_SIZE = 6 * 8     # the character creation's six camera modes: {target x, eye z} floats
# The menus' frames (interface/single_screen/executable/single_screen_frames.py): the scene count, 16 scenes {all, any,
# none}, 16 sets x 16 scenes of parameters {cx, cy, scale, scale - 1} and 160 names {hash, rules, set, null hash} with a
# 0 hash after them
SINGLE_SCREEN_FRAME_TABLE_SIZE = 4 + 12 * 16 + 16 * 16 * 16 + 16 * (160 + 1)
# The minimap's place name (interface/single_screen/executable/single_screen_frames.py,
# interface/single_screen/executable/single_screen_label.c): its group's name hash, its frame null's name hash and the
# null's {cx, cy, scale, scale - 1} on the top screen
SINGLE_SCREEN_LABEL_TABLE_SIZE = 8 + 16 + 4
# The game GUI engine (interface/game_gui/game_gui_engine.c; interface/game_gui/engine.py builds its table): the table's
# room, which the build fills from the arrangement (header, names, targets, screens, rules, places); raising it is a
# rebuild of the layout
GAME_GUI = "game_gui"
GAME_GUI_TABLE_SIZE = 0xC000


@dataclass(frozen=True)
class BlockSpec:
    """Code (`source`: a path under core/; .s assembled, .c compiled and linked with the .ld of the
    same name) or data (`size` bytes, zero in the layout, written by the patcher with Layout.place).
    `region`: "auto" (any code region, the first where it fits) or the name of one.
    `thumb`: compile a .c source as Thumb (about 35 % smaller); its entry and float code stay ARM and
    game functions are called with long_call.
    `units`: more C sources (paths under core/) compiled one by one and linked into the block with its
    source, each keeping its own static names.
    `defines`: C macros (`NAME=value`) the source is compiled with, for the values a patcher's Python owns."""
    name: str
    feature: str
    source: str | None = None
    size: int = 0
    align: int = 4
    region: str = "auto"
    thumb: bool = False
    units: tuple[str, ...] = ()
    defines: tuple[str, ...] = ()


@dataclass(frozen=True)
class VariableSpec:
    """Memory in .bss, zero when the game starts. `debug` variables are only used by diagnostic builds:
    they go after the others and may overlap each other."""
    name: str
    feature: str
    size: int
    align: int = 4
    debug: bool = False
    region: str = "bss_tail"
    gap: bool = False       # placed first, in the gap its region's first aligned variable leaves (it must fit)


# The ported monsters' new items (equipment/new_gear/new_items.py): packed after everything else, so a mod without them
# keeps the pages it had.
ITEMS = "ported_items"

# The ported monsters' armor and create recipes (equipment/new_gear/new_armor.py, new_recipes.py).
GEAR = "ported_gear"

# Features packed after every other block, in this order (tools/build/build_code_space.py): a build's extension only
# takes the pages up to its last block there (code_space.Layout.extend), so a mod without these keeps a page or so of
# it. What the ported monsters share first, then each one's own, then what they bring (their items, their hunter gear:
# new weapons, new armor and recipes; their Felyne gear), then Bubbleblight (Mizutsune's status in the hunter's code,
# gameplay/bubbleblight/bubbleblight.py), last, so the mods without Mizutsune keep every address.
BUBBLEBLIGHT = "bubbleblight"
# The game GUI engine (2 KB of code and its 48 KB table) goes first of them: after every small option's blocks, so a
# mod without single-screen mode carries none of its pages, and before the ported monsters', so a mod with only
# single-screen mode carries none of theirs.
# Alatreon and Mizutsune (BUILT[:2]) keep their place; every monster after them is packed after Bubbleblight, so the
# mods of the first two keep every address, items and gear included (checked file by file at seed 1234). The cheats'
# block (cheats/cheats.py) goes last of all, so it moves nothing either, and the area move watchdog's after it
# (monsters/routes/patch.py), whose mods are the ones with routes or a ported monster.
MOVE_WATCH = "area_move_watch"
# The ported monsters' severed tail thrown and cooled as in MH Generations (gameplay/tail_fall/tail_fall.py), after
# everything else
TAIL_FALL = "tail_fall"
# The game GUI recorder's frame counters (tools/ui/ui_probe.py): only
# the recording probe places them, never a mod, so they go after everything else and move nothing; built into the
# layout, so the probe needs no ARM toolchain (an edition's developers have none)
GUI_FRAME_MARKS = "game_gui_recorder"
# The debug cheat insta kill (cheats/cheats.py): after the recorder's marks, so it moves no other block either
INSTA_KILL = "cheat_insta_kill"
# The Wyporium's Rare Materials Exchange (gameplay/wyporium/rare_exchange.c): after all of them, so it moves nothing
RARE_EXCHANGE = "rare_exchange"
# One more item in each Meownster Hunters expedition's haul (gameplay/meownster_scrap/meownster_scrap.c): after it too
MEOWNSTER_SCRAP = "meownster_scrap"
# The aspect ratios (cheats/aspect_ratio.py): the ratio's 3 factors. A mod without the
# option carries none of its pages.
ASPECT_RATIO = "cheat_aspect_ratio"
# The START menu's Mod Settings (interface/mod_settings/mod_settings.py), which every
# mod made from the executable carries: the options a player changes during play and the aspect ratio's list. Its
# data block (settings_data) holds the curated table, the list's (aspect_list_data) its texts, mod_options_data the
# options (their values, defaults and what each writes), mod_raw_table the true attack's table of 100s.
MOD_SETTINGS = "mod_settings"
MOD_SETTINGS_DATA_SIZE = 852
MOD_SETTINGS_PANE_HASHES = (724, 840)   # where struct mod_settings_data holds ui020's pane name hashes (ten_rows.py)
ASPECT_LIST_DATA_SIZE = 28
MOD_OPTIONS_DATA_SIZE = 16 + 24 * 164
MOD_RAW_TABLE_SIZE = 64
ASPECT_DATA_SIZE = 124
ASPECT_ANCHORS_SIZE = 0x3000
# The split title's two RomFS, `rom:` from the game data title and `mod:` from the title's own (install/title/
# split_romfs.py): only the installed title's build places it. Packed right after Mod
# Settings, which every mod carries, so that build does not take the aspect ratio's pages; its variable goes after the
# debug ones with Bubbleblight's (tools/build/build_code_space.py pack_variables).
SPLIT_ROMFS = "split_romfs"
# Damage Numbers (interface/damage_numbers/damage_numbers.py): the hooks' stubs, the C
# and its data (struct dmg_data). Packed last, so it moves no other block; its state is in the extension's variables.
DAMAGE_NUMBERS = "damage_numbers"
DAMAGE_NUMBERS_DATA_SIZE = 932
DAMAGE_NUMBERS_STATE_SIZE = 1480
# The modern camera (gameplay/modern_camera/modern_camera.py): its code, its tuning
# (struct modern_camera_data) and its state in the extension's variables (struct modern_camera_state). Packed before
# Mod Settings, so the installed title's update RomFS and the aspect ratio stay last.
MODERN_CAMERA = "modern_camera"
MODERN_CAMERA_DATA_SIZE = 120
MODERN_CAMERA_STATE_SIZE = 72
# The quest's layouts of our own (interface/quest_layouts/quest_layouts.py): the frame, load and free hooks Damage
# Numbers and the horn's songs share, their code and their table
# (struct quest_layouts).
QUEST_LAYOUTS = "quest_layouts"
QUEST_LAYOUTS_DATA_SIZE = 128
# The Hunting Horn's songs (interface/horn_songs/horn_songs.py): the C and its data
# (struct horn_data); its state is in the extension's variables.
HORN_SONGS = "horn_songs"
HORN_SONGS_DATA_SIZE = 76
HORN_SONGS_STATE_SIZE = 44


def _declared() -> tuple[tuple[str, ...], tuple[BlockSpec, ...]]:
    """PACKED_LAST and BLOCKS, made on first use (`__getattr__`): they take sizes and lists from the ported monsters'
    and the equipment's modules, which a module that only needs a constant or GAME_SYMBOLS (the single-screen mode,
    an edition without the ported monsters) never loads. The list stays at the margin as
    before."""
    from core.monsters.porting.called_small import c_defines as pack_defines
    from core.monsters.porting.hf_records import C_DEFINES as RECORDS_DEFINES, STUBS_SIZE as RECORDS_STUBS
    from core.monsters.porting.new_id_data import C_DEFINES as NEW_ID_DEFINES
    from core.monsters.porting.new_id_data import block_specs as new_id_blocks
    from core.monsters.porting.proof_blocks import SHARED, monster_block_specs, shared_block_specs
    from core.monsters.porting.spec import BUBBLE_BIND_BLOCK, BUBBLE_FX_BLOCK, BUBBLE_FX_SIZE, BUILT
    from core.equipment.new_gear import gear_space as gear
    from core.equipment.tables import item_data
    from core.equipment.new_gear import new_weapon_room
    from core.equipment.mhgen.felyne_pack import FELYNE_IDS, FIRST_MODEL, SOUND_SLOT
    from core.equipment.new_gear.felyne_data import FEATURE as FELYNE
    from core.equipment.new_gear.felyne_data import block_specs as felyne_blocks
    from core.gameplay.quests.quest_lists import HALL_LIST_LENGTH, NEW_QUEST_ROOM, SAVE_LIST_LENGTH
    from core.gameplay.wyporium import trades as wyporium_trades
    from core.gameplay.tail_fall.tail_fall import ANIMATION_SIZE as TAIL_FALL_ANIMATION_SIZE
    from core.gameplay.tail_fall.tail_fall import DATA_SIZE as TAIL_FALL_DATA_SIZE
    packed_last = (GAME_GUI, SHARED, *(spec.key for spec in BUILT[:2]), ITEMS, new_weapon_room.FEATURE, GEAR,
                   FELYNE, BUBBLEBLIGHT, *(spec.key for spec in BUILT[2:]), MOVE_WATCH, TAIL_FALL,
                   GUI_FRAME_MARKS, INSTA_KILL, wyporium_trades.FEATURE, RARE_EXCHANGE, MEOWNSTER_SCRAP, MODERN_CAMERA,
                   MOD_SETTINGS, SPLIT_ROMFS, ASPECT_RATIO)
    return packed_last, (
    # Makes the extension executable at the game's entry; placed with the first block in "ext"
    # (code_space.Layout.extend).
    BlockSpec("ext_bootstrap", "extension", "game/executable/ext_bootstrap.s", region="text_tail"),
    BlockSpec("minimap_wrapper", "hud_scale", "interface/hud/minimap_wrapper.s"),
    # The minimap icons the placement functions do not project (the zoomed area view's zoom and offsets, the
    # Everwood's fixed points, scaled) and its two floats (scale, 64 (1 - scale)), which
    # code_patch.patch_minimap_icons fills
    BlockSpec("minimap_zoom", "hud_scale", "interface/hud/minimap_zoom.c", region="ext"),
    BlockSpec("minimap_zoom_data", "hud_scale", size=8, region="ext"),
    # The talk windows at the HUD size only in a quest (each frame, after the GUI's pop-up update) and their data: the
    # quest game modes' bits and per window its name hash, its null's and the null's x, y and scale in a quest
    # (code_patch.patch_talk_size)
    BlockSpec("talk_size", "hud_scale", "interface/hud/talk_size.c", region="ext"),
    BlockSpec("talk_size_data", "hud_scale", size=4 + 6 * 20, region="ext"),
    BlockSpec("target_button", "touchless_target", "interface/hud/target_button.s"),
    BlockSpec("dpad_filter", "touchless_target", "interface/hud/dpad_filter.s"),
    BlockSpec("face_loader", "target_face", "interface/hud/face_loader.s"),
    BlockSpec("face_free", "target_face", "interface/hud/face_free.s"),
    BlockSpec("face_show", "target_face", "interface/hud/face_show.s"),
    BlockSpec("face_params", "target_face", size=16),  # float x, y, scale (code_patch.face_params), dead shade
    BlockSpec("target_face", "target_face", "interface/hud/target_face.c", thumb=True),
    BlockSpec("new_game_skip", "skip_intro", "gameplay/new_game_skip/new_game_skip.s"),
    BlockSpec("new_game_data", "skip_intro", size=0x64),  # gameplay/new_game_skip/new_game_skip.py, new_game_data()
    # skip_caravan_tutorial runs new_game_skip and then writes the caravan tutorial's results. text_tail is full: in the
    # extension, like fast_text, so no older block moves.
    BlockSpec("new_game_tutorial", "skip_caravan_tutorial", "gameplay/new_game_skip/new_game_tutorial.s", region="ext"),
    BlockSpec("new_game_tutorial_data", "skip_caravan_tutorial", size=0x180, region="ext"),  # caravan_tutorial_data()
    BlockSpec("cutscene_map_check", "intro_cutscenes", "gameplay/intro_cutscenes/cutscene_map_check.s"),
    # In the extension, so the older blocks keep their places.
    BlockSpec("fast_text", "fast_text", "interface/fast_text/fast_text.s", region="ext"),
    BlockSpec("fast_gathering", "fast_gathering", "gameplay/fast_gathering/fast_gathering.s", region="ext"),
    # Holding A repeats it (gameplay/hold_a/hold_a.py): three entries, one for the hunter's
    # input and one for each panel that takes items one at a time
    BlockSpec("hold_a", "hold_a", "gameplay/hold_a/hold_a.c", region="ext"),
    # The system keyboard (interface/system_keyboard/system_keyboard.py): the poll
    # of the game's keyboard runs the 3DS system keyboard's applet
    BlockSpec("system_keyboard", "system_keyboard", "interface/system_keyboard/system_keyboard.c", region="ext"),
    # Select and Start follow the game's option START (gameplay/select_kick/select_kick.py): two entries, one for the
    # SDK's pad step and one for the Game Menu's per-frame logic
    BlockSpec("select_kick", "select_kick", "gameplay/select_kick/select_kick.c", region="ext"),
    # Heavenfall's own save files (save/game_redirect.py): the logic in
    # C, the two hooks' entries in assembly
    BlockSpec("save_redirect", "save_redirect", "save/game_redirect.c", region="ext"),
    BlockSpec("save_redirect_entry", "save_redirect", "save/game_redirect.s", region="ext"),
    # START skips a slain monster's death camera (gameplay/death_camera_skip/death_camera_skip.py): one entry, for the
    # camera manager's call of a camera sequence's frame
    BlockSpec("death_camera_skip", "skip_death_camera", "gameplay/death_camera_skip/death_camera_skip.c", region="ext"),
    # START does what the touch screen's Skip does (gameplay/intro_skip/intro_skip.py):
    # three entries, for the touch bar input's call of a button's frame and the event player's two calls of the sound
    # control
    BlockSpec("intro_skip", "skip_monster_intro", "gameplay/intro_skip/intro_skip.c", region="ext"),
    # The virtual map of monster_routes (monsters/routes/patch.py): its hooks, its
    # (species, real map) entries (patch.ENTRY bytes each, patch.MAX_ENTRIES, plus the end marker) and their
    # translations (patch.TABLE bytes each, patch.MAX_TABLES).
    BlockSpec("virtual_map", "monster_routes", "monsters/routes/virtual_map.s", region="ext"),
    BlockSpec("virtual_maps", "monster_routes", size=4 * 320 + 4, region="ext"),
    BlockSpec("virtual_map_tables", "monster_routes", size=32 * 128, region="ext"),
    # The Smithy's layered gear screens (layered_selector.c, layered_forge.c) and its catalogs (equipment/layered/
    # layered_equipment.py, layered_data()), with the Felynes' looks (felyne_looks.c, felyne_looks_data:
    # felyne_looks.py).
    # 8-aligned: its size depends on its address mod 8 (alignment padding inside the C block).
    BlockSpec("layered_selector", "layered_equipment", "equipment/layered/layered_selector.c", region="ext", thumb=True,
              align=8, units=("equipment/layered/layered_forge.c", "equipment/layered/felyne_looks.c",
                     "equipment/layered/layered_online.c",
                     "interface/screen_kit/screen_kit.c")),
    BlockSpec("layered_data", "layered_equipment", size=0x9000, region="ext"),
    # The Wyporium's Rare Materials Exchange: its menu line and screens (gameplay/wyporium/rare_exchange.c), and its
    # rows and pools (gameplay/wyporium/exchange_data.py).
    BlockSpec("rare_exchange", RARE_EXCHANGE, "gameplay/wyporium/rare_exchange.c", region="ext", thumb=True, align=8),
    BlockSpec("rare_exchange_data", RARE_EXCHANGE, size=0x1000, region="ext"),
    # The Meownster Hunters' extra item: the hook's code and the two item ids with their count (meownster_scrap.py)
    BlockSpec("meownster_scrap", MEOWNSTER_SCRAP, "gameplay/meownster_scrap/meownster_scrap.c", region="ext"),
    BlockSpec("meownster_scrap_data", MEOWNSTER_SCRAP, size=8, region="ext"),
    BlockSpec("felyne_looks_data", "layered_equipment", size=0x100, region="ext"),
    # When each look appears and what it costs (equipment/layered/layered_rules.py): rules parallel to the catalogs of
    # layered_data, the Felyne rows, the recipes; 0x12000
    # since each look's zenny is a u32.
    BlockSpec("layered_rules", "layered_equipment", size=0x12000, region="ext"),
    # The descriptions of the ported monsters' new hunter gear (equipment/new_gear/gear_descriptions.py): the hook of
    # the two description readers and its
    # table (a word per Exp file, 35).
    BlockSpec("gear_desc", "ported_gear_texts", "equipment/new_gear/gear_desc.s", region="ext"),
    # MHGen's models (equipment/mhgen/tables.py, equipment/mhgen/equipment_pack.py): the gimmick donor hook and the
    # per-model tables moved to hold the pack's ids.
    BlockSpec("gimmick_donor", "mhgen_models", "equipment/mhgen/gimmick_donor.s", region="ext"),
    BlockSpec("sound_number", "mhgen_models", "equipment/mhgen/sound_number.s", region="ext"),
    BlockSpec("gimmick_donor_table", "mhgen_models", size=14 * 256, region="ext"),
    BlockSpec("cloth_tables", "mhgen_models", size=2 * 800, region="ext"),        # equipment_pack.CLOTH_IDS
    BlockSpec("armor_sound_tables", "mhgen_models", size=8 * 800, region="ext"),  # tables.ARMOR_SOUND_IDS
    BlockSpec("hair_tables", "mhgen_models", size=2 * 800 * 4, region="ext"),     # tables.HAIR_IDS
    BlockSpec("gun_effects", "mhgen_models", size=3 * 256, region="ext"),         # tables.EFFECT_TABLES
    BlockSpec("rod_effects", "mhgen_models", size=3 * 256, region="ext"),
    # tables.HAIR_ROW_ROOM rows of 0x70 bytes, plus the bytes to reach the game's row grid
    BlockSpec("hair_rows", "mhgen_models", size=224 * 0x70 + 0x70 - 4, region="ext"),
    # MHGen's Felyne models at numbers of their own (equipment/mhgen/felyne_pack.py), FELYNE_IDS (336): the head and
    # body masks (FELYNE_IDS u16 each), the helm cloth bits (FELYNE_IDS
    # bytes) and the weapons' sound table (FELYNE_IDS pointers) moved
    # to hold the new numbers, and the new weapons' sound paths (SOUND_SLOT bytes per number from FIRST_MODEL to
    # FELYNE_IDS - 1)
    BlockSpec("felyne_head_masks", "felyne_models", size=2 * FELYNE_IDS, region="ext"),
    BlockSpec("felyne_body_masks", "felyne_models", size=2 * FELYNE_IDS, region="ext"),
    BlockSpec("felyne_head_cloth", "felyne_models", size=FELYNE_IDS, region="ext"),
    BlockSpec("felyne_sound_table", "felyne_models", size=4 * FELYNE_IDS, region="ext"),
    BlockSpec("felyne_sound_paths", "felyne_models", size=(FELYNE_IDS - FIRST_MODEL) * SOUND_SLOT, region="ext"),
    # New quests with ids of their own (gameplay/quests/new_quests.py): the availability
    # hook, its (id, unlocking quest) pairs, and the Gathering Hall's load list and the save's quest list moved to hold
    # the new ids (NEW_QUEST_ROOM at most, the free bits of the save)
    BlockSpec("quest_unlock", "new_quests", "gameplay/quests/quest_unlock.s", region="ext"),
    BlockSpec("new_quest_unlocks", "new_quests", size=4 * (NEW_QUEST_ROOM + 1), region="ext"),
    BlockSpec("hall_quest_list", "new_quests", size=2 * (HALL_LIST_LENGTH + NEW_QUEST_ROOM + 2), region="ext"),
    BlockSpec("save_quest_list", "new_quests", size=2 * (SAVE_LIST_LENGTH + NEW_QUEST_ROOM + 2), region="ext"),
    # Black and Crimson Fatalis and Alatreon at low health (gameplay/monster_phases/monster_phases.py): their speed,
    # their World music by phase and the slain theme at the quest's end; the options and requests the patcher fills in
    # (8 bytes)
    BlockSpec("monster_phases", "monster_phases", "gameplay/monster_phases/monster_phases.s", region="ext"),
    BlockSpec("monster_phase_options", "monster_phases", size=8, region="ext"),
    # The quest list's key quest marks (interface/key_quests/executable/key_quests.py):
    # the row refresh's hook, the key quests' ids (u16 and an end mark) and the name hashes of the rows' star nulls (8
    # u32)
    BlockSpec("key_quests", "key_quests", "interface/key_quests/executable/key_quests.s", region="ext"),
    BlockSpec("key_quest_ids", "key_quests", size=2 * (KEY_QUEST_ROOM + 1), region="ext"),
    BlockSpec("key_mark_hashes", "key_quests", size=32, region="ext"),
    # The Caravan's quest girl in a randomized game (interface/quest_counter/executable/quest_counter.py): the talk
    # function's hook
    BlockSpec("quest_counter", "quest_counter", "interface/quest_counter/executable/quest_counter.s", region="ext"),
    # Single-screen mode (interface/single_screen/executable/single_screen.py): the
    # draw order hook and its table of {name hash, priority offset} pairs, and the yes / no boxes moved to the top
    # screen while a prompt is open
    BlockSpec("single_screen_priority", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_priority.s",
              region="ext"),
    BlockSpec("single_screen_priorities", SINGLE_SCREEN, size=SINGLE_SCREEN_TABLE_SIZE, region="ext"),
    BlockSpec("single_screen_prompt", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_prompt.s",
              region="ext"),
    # ... and the Canteen's pay buttons driven with left / right: the pay choice's cursor step takes the pad's left and
    # right as up and down
    BlockSpec("single_screen_pay", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_pay.s",
              region="ext"),
    # ... and the touch-panel layout B on every save (interface/single_screen/executable/single_screen_layout.py): the
    # quest HUD's load of the saved panels asks
    # this block for the record, which writes layout B first when the record is not B
    BlockSpec("single_screen_panels", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_panels.c",
              region="ext"),
    # ... and the creation's Aceptar / Atrás buttons driven with left / right: the menu cursor's call on the main pages
    # takes the pad's left and right as down and up on
    # the buttons
    BlockSpec("single_screen_creation_pad", SINGLE_SCREEN,
              "interface/single_screen/executable/single_screen_creation_pad.s", region="ext"),
    # ... and the character creation's camera: the hook of
    # the goal target x and its table of {target x, eye z} per camera mode
    BlockSpec("single_screen_creation", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_creation.s",
              region="ext"),
    BlockSpec("single_screen_creation_camera", SINGLE_SCREEN, size=CREATION_CAMERA_SIZE, region="ext"),
    # ... and the name boards (ui802) shown only on the pages the curated creation_boards names: the hook of the
    # creation menu's page change, with the pages' mask
    BlockSpec("single_screen_board", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_board.s",
              region="ext"),
    # ... and the name keyboard's virtual finger (interface/single_screen/executable/single_screen_keyboard.py): the
    # hook in the keyboard's input manager, with the curated
    # key names and start point
    BlockSpec("single_screen_keyboard", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_keyboard.s",
              region="ext"),
    # ... and the World Map opened and driven with the pad
    # (interface/single_screen/executable/single_screen_world_map.py):
    # chained into the pad update's call to single_screen_prompt, with the curated buttons
    BlockSpec("single_screen_world_map", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_world_map.s",
              region="ext"),
    # ... and its "[X] Map" hint (interface/single_screen/executable/single_screen_map_hint.py): chained in front, it
    # calls the world map block and shows or hides
    # the hint's group (the curated name's hash)
    BlockSpec("single_screen_map_hint", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_map_hint.s",
              region="ext"),
    # ... and the town minimap on the top screen (interface/single_screen/executable/single_screen_minimap.py): chained
    # in front of the hint, it turns the map on and off
    # with the curated button (L), moves the map's groups and shows its own hint
    BlockSpec("single_screen_minimap", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_minimap.s",
              region="ext"),
    # ... and the minimap in a Gathering Hall: called by the minimap block every frame, it shows and hides the map with
    # the game's own functions in the
    # hub states where the game hides it (0x12, 0x14)
    BlockSpec("single_screen_minimap_hall", SINGLE_SCREEN,
              "interface/single_screen/executable/single_screen_minimap_hall.c", region="ext"),
    # ... and the Palico menus' frames (interface/single_screen/executable/single_screen_frames.py): chained in front of
    # the minimap, it scales and moves the
    # frame null of each framed group by the curated scenes ... and the players' box
    # (interface/single_screen/executable/single_screen_players.c, a unit of this block): after the frames, it keeps the
    # hall's member list up while
    # the hunter walks ... and the town minimap's place name (interface/single_screen/executable/single_screen_label.c,
    # a unit of this block): after the players' box, it scales and
    # moves the name's frame null while its group is on the top screen
    BlockSpec("single_screen_frames", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_frames.c",
              region="ext",
              units=("interface/single_screen/executable/single_screen_players.c",
                     "interface/single_screen/executable/single_screen_label.c")),
    BlockSpec("single_screen_frame_table", SINGLE_SCREEN, size=SINGLE_SCREEN_FRAME_TABLE_SIZE, region="ext"),
    BlockSpec("single_screen_label_table", SINGLE_SCREEN, size=SINGLE_SCREEN_LABEL_TABLE_SIZE, region="ext"),
    # ... and the guild card's groups on the top screen and its hint
    # (interface/single_screen/executable/single_screen_card_info.py): chained in front of the frames' block, it keeps
    # the card's groups on the top screen and
    # shows "[Y] Toggle Display" while the photo mode's Y acts
    BlockSpec("single_screen_card_info", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_card_info.s",
              region="ext"),
    # ... and the Arena's team and weapon choice on the pad (interface/single_screen/executable/single_screen_arena.py):
    # a cursor between the weapon choice and the four buttons of
    # ui497, A pressing a button as a touch does, B closing the mode it opened; the button above each of the five weapon
    # sets is its table (5 bytes, padded)
    BlockSpec("single_screen_arena", SINGLE_SCREEN, "interface/single_screen/executable/single_screen_arena.c",
              region="ext"),
    BlockSpec("single_screen_arena_up", SINGLE_SCREEN, size=8, region="ext"),
    # The game GUI engine: every frame, before the render, it applies the arrangement to every GUI manager with absolute
    # values
    # (wrapper nulls' places, priorities), and the draw's view test draws a group in the screen its place names
    BlockSpec("game_gui_engine", GAME_GUI, "interface/game_gui/game_gui_engine.c", region="ext"),
    BlockSpec("game_gui_table", GAME_GUI, size=GAME_GUI_TABLE_SIZE, region="ext"),
    # Bubbleblight (gameplay/bubbleblight/bubbleblight.py): the
    # hunter's code (hit, status, tick, resets), and the entry points of the effects task (bubble_changed) and the large
    # bubbles (bubble_large), each in a block of its own
    BlockSpec("bubbleblight", BUBBLEBLIGHT, "gameplay/bubbleblight/bubbleblight.s", region="ext"),
    BlockSpec("bubble_fx", BUBBLEBLIGHT, "gameplay/bubbleblight/bubble_fx.s", region="ext"),
    BlockSpec("bubble_large", BUBBLEBLIGHT, "gameplay/bubbleblight/bubble_large.s", region="ext"),
    # ... and the party list's status icon, one more entry of the rotating icon B (bubble_icon: the mask and the cell
    # hooks; bubble_icon_table: B's table copied with the bubbles' entry, 28 entries of 8 bytes)
    BlockSpec("bubble_icon", BUBBLEBLIGHT, "gameplay/bubbleblight/bubble_icon.s", region="ext"),
    BlockSpec("bubble_icon_table", BUBBLEBLIGHT, size=28 * 8, region="ext"),
    # The ported MH Generations monsters (core/monsters/).
    # What they share (feature SHARED, in whenever one of them is on): MH Generations' effect player and its glue
    # (monsters/porting/mhgen_port.c), the ported monsters' records, the
    # player's classes' vtables and the placement carried from MH Generations' executable
    # (monsters/porting/proof_blocks.py shared_block_specs, product.py, proof_hook.place), and the new monster ids
    # (monsters/porting/new_id.py): their code (monsters/porting/new_id.c), the
    # factory's cases, the stubs and the id tables extended to 200 ids
    *(BlockSpec(name, SHARED, source, size=size, align=align, region="ext")
      for name, source, size, align in shared_block_specs()),
    *(BlockSpec(name, SHARED, source, size=size, region="ext", defines=NEW_ID_DEFINES if source else ())
      for name, source, size in new_id_blocks()),
    # The ported monsters' pages of the hunting log: the stub that opens a page once its monster was hunted or captured
    # (gameplay/hunting_log/hunting_log.py)
    BlockSpec("hunting_log_unlock", "hunting_log", size=52, region="ext"),     # hunting_log.UNLOCK_STUB bytes
    # The hunt records of the monster ids 128-255 in Heavenfall's own save file (core/monsters/porting/hf_records.py):
    # their code, and the stubs the patcher fills (the nine
    # functions' entries and the four hooks of the save)
    BlockSpec("hf_records_code", SHARED, "monsters/porting/hf_records.c", region="ext", defines=RECORDS_DEFINES),
    BlockSpec("hf_records_stubs", SHARED, size=RECORDS_STUBS, region="ext"),
    # Each one's own (feature his spec's key, for each of spec.BUILT, Mizutsune's for his probes;
    # proof_blocks.monster_block_specs): his class's code (Alatreon's monsters/alatreon/alatreon.c, Mizutsune's
    # monsters/mizutsune/mizutsune.c) and the data the patcher fills (product.py): his id, his vtable (97 slots), his
    # break thresholds, his resource and carve sets, his shells' points, his data from his MH Generations module,
    # the paths of his etd / emd, his PEL / PSL / tied sounds images and their resource objects, his shell files
    # as MH Generations' loaders leave them (one image in place per kind, and their rShells' addresses) and his
    # shell classes' vtables (monsters/porting/shell_data.py)
    # (a pack's leader and the small monsters he leads get the pack's numbers as macros: porting/called_small.py)
    *(BlockSpec(name, spec.key, source, size=size, align=align, region="ext",
                units=spec.code_units if name == spec.code_block else (),
                defines=pack_defines(spec.id) if name == spec.code_block else ())
      for spec in BUILT for name, source, size, align in monster_block_specs(spec)),
    # Mizutsune's Bubbleblight on the hunter (gameplay/bubbleblight/bubble_fx.py): the paths of the two effect lists
    # that list 1's null words get. Feature the key of
    # the first monster that has Bubbleblight: packed with his blocks.
    *(BlockSpec(BUBBLE_FX_BLOCK, spec.key, size=BUBBLE_FX_SIZE, region="ext")
      for spec in [next((one for one in BUILT if one.bubbleblight), None)] if spec is not None),
    # ... and the large bubbles' bind in the hunter's code (gameplay/bubbleblight/bubble_bind.py): the entry the small
    # bubbles' code calls, the motion
    # remap and the reaction guard
    *(BlockSpec(BUBBLE_BIND_BLOCK, spec.key, "gameplay/bubbleblight/bubble_bind.s", region="ext")
      for spec in [next((one for one in BUILT if one.bubbleblight), None)] if spec is not None),
    # The ported monsters' new items (equipment/new_gear/new_items.py):
    # the item table copied with room for item_data.MAX_NEW_ITEMS records, the 17 icon tints, the code that gives a new
    # id an "ever obtained" bit and the u16 bit numbers it reads (one per new id), and the carve lists: the pointer
    # array copied with room for MAX_CARVE_TABLES windows of four, and the lists they point to
    BlockSpec("item_table", ITEMS, size=item_data.TABLE_BYTES, region="ext"),
    BlockSpec("item_colours", ITEMS, size=4 * len(item_data.COLOURS), region="ext"),
    BlockSpec("item_obtained", ITEMS, "equipment/new_gear/item_obtained.s", region="ext"),
    BlockSpec("item_obtained_bits", ITEMS, size=2 * item_data.MAX_NEW_ITEMS, region="ext"),
    BlockSpec("carve_pointers", ITEMS, size=item_data.CARVE_POINTER_BYTES, region="ext"),
    BlockSpec("carve_lists", ITEMS, size=item_data.CARVE_LIST_BYTES, region="ext"),
    # the part-break reward lists (equipment/new_gear/new_breaks.py): the pointer array copied with room for
    # MAX_BREAK_TABLES places of BREAK_TABLE_ENTRIES entries, and the lists they point to
    BlockSpec("break_pointers", ITEMS, size=item_data.BREAK_POINTER_BYTES, region="ext"),
    BlockSpec("break_lists", ITEMS, size=item_data.BREAK_LIST_BYTES, region="ext"),
    # What the ported monsters bring, packed after them: new hunter weapons (equipment/new_gear/new_weapons.py; docs/
    # equipment_data.md, "New weapons"): the hooks of the readers of the weapon tables, a row per equipment type,
    # the new stat and upgrade records (new_weapon_room.ROOM per class) and the new sharpness profiles
    BlockSpec("new_weapon_code", new_weapon_room.FEATURE, "equipment/new_gear/new_weapons.s", region="ext"),
    BlockSpec("new_weapon_rows", new_weapon_room.FEATURE, size=new_weapon_room.ROWS_BYTES, region="ext"),
    BlockSpec("new_weapon_stats", new_weapon_room.FEATURE, size=new_weapon_room.STATS_BYTES, region="ext"),
    BlockSpec("new_weapon_upgrades", new_weapon_room.FEATURE, size=new_weapon_room.UPGRADE_BYTES, region="ext"),
    BlockSpec("new_sharpness", new_weapon_room.FEATURE, size=new_weapon_room.SHARPNESS_BYTES, region="ext"),
    # The save's marks of the new ids past a class's own bits (equipment/new_gear/weapon_marks.py; docs/equipment/
    # equipment_data.md, "The save"): the function that gives an id its bit, its table and the six accessors' stubs
    BlockSpec("weapon_marks_code", new_weapon_room.FEATURE, "equipment/new_gear/weapon_marks.c", region="ext",
              defines=new_weapon_room.MARK_DEFINES),
    BlockSpec("weapon_marks_table", new_weapon_room.FEATURE, size=new_weapon_room.MARK_TABLE_BYTES, region="ext"),
    BlockSpec("weapon_marks_stubs", new_weapon_room.FEATURE, size=new_weapon_room.MARK_STUBS_BYTES, region="ext"),
    # The ported monsters' hunter equipment (equipment/new_gear/new_armor.py, new_recipes.py): the armor lookup's and
    # the create recipes' hooks; the new armor records (gear.ARMOR_ROOM per part, parts in layout.ARMOR_PARTS order) and
    # each type's first new id and table base; the new create recipes (gear.*_RECIPE_ROOM) and the runs where they sit
    # in the game's lists
    BlockSpec("new_armor", GEAR, "equipment/new_gear/new_armor.s", region="ext"),
    BlockSpec("new_recipes", GEAR, "equipment/new_gear/new_recipes.s", region="ext"),
    BlockSpec("gear_armor_new", GEAR, size=gear.ARMOR_NEW_BYTES, region="ext"),
    BlockSpec("gear_armor_records", GEAR, size=gear.ARMOR_RECORDS_BYTES, region="ext"),
    BlockSpec("gear_armor_runs", GEAR, size=gear.RUNS_BYTES, region="ext"),
    BlockSpec("gear_weapon_runs", GEAR, size=gear.RUNS_BYTES, region="ext"),
    BlockSpec("gear_armor_recipes", GEAR, size=gear.ARMOR_RECIPE_ROOM * gear.RECIPE_RECORD, region="ext"),
    BlockSpec("gear_weapon_recipes", GEAR, size=gear.WEAPON_RECIPE_ROOM * gear.RECIPE_RECORD, region="ext"),
    # New Felyne gear (equipment/new_gear/new_felyne.py): the
    # bodies' and heads' stats and the body and weapon recipes, moved here with room for the new pieces
    # (felyne_data.block_specs)
    *(BlockSpec(name, FELYNE, size=size, region="ext") for name, size in felyne_blocks()),
    # A Felyne wearing a new piece is written to the save file wearing a Derring piece, and the real one is put back at
    # load (gameplay/felyne_save/felyne_save.py): both
    # hooks and their table
    BlockSpec("felyne_save", FELYNE, "gameplay/felyne_save/felyne_save.s", region="ext"),
    # The area move watchdog of monster_routes and the ported monsters (monsters/routes/patch.py): the hook, and the
    # limit in frames it counts a move up to
    BlockSpec("area_move_watch", MOVE_WATCH, "monsters/routes/area_move_watch.s", region="ext"),
    BlockSpec("area_move_limit", MOVE_WATCH, size=4, region="ext"),
    # A ported monster's severed tail (gameplay/tail_fall/tail_fall.py): the two hooks in the cut piece's update, the
    # monster's id with the motion's keys as floats, and the name
    # of the material animation that cools the piece
    BlockSpec("tail_fall", TAIL_FALL, "gameplay/tail_fall/tail_fall.c", region="ext"),
    BlockSpec("tail_fall_data", TAIL_FALL, size=TAIL_FALL_DATA_SIZE, region="ext"),
    BlockSpec("tail_fall_animation", TAIL_FALL, size=TAIL_FALL_ANIMATION_SIZE, region="ext"),
    # The recording probe's wrapper of the frame's wait for the GPU (tools/ui/ui_probe.py, patch_frame_marks): it keeps
    # the variable gui_frame_marks
    BlockSpec("gui_frame_marks_probe", GUI_FRAME_MARKS, "interface/game_gui/gui_frame_marks.s", region="ext"),
    # The debug cheat insta kill (cheats/cheats.py): the hunter's attack
    # multiplied and capped, and its two words (multiplier, cap) from curated gui_presets.json
    BlockSpec("insta_kill", INSTA_KILL, "cheats/insta_kill.c", region="ext"),
    BlockSpec("insta_kill_data", INSTA_KILL, size=8, region="ext"),
    # The Wyporium's trade table with the trades of MH XX's new materials (gameplay/wyporium/trades.py): the game's
    # rows, the new ones and the terminator, with
    # room for one new row per material
    BlockSpec(wyporium_trades.BLOCK, wyporium_trades.FEATURE, size=wyporium_trades.BLOCK_SIZE, region="ext"),
    # Whether a row of the table is open (gameplay/wyporium/trade_rows.c): a new row opens with its rank, by the lists
    # of what opens each rank (trades.py, `rows_data`)
    BlockSpec(wyporium_trades.CODE_BLOCK, wyporium_trades.FEATURE, "gameplay/wyporium/trade_rows.c", region="ext"),
    BlockSpec(wyporium_trades.DATA_BLOCK, wyporium_trades.FEATURE, size=wyporium_trades.DATA_SIZE, region="ext"),
    # The aspect ratios (cheats/aspect_ratio.py): the hooks' stubs, the logic, the factors
    BlockSpec("mod_settings_stub", MOD_SETTINGS, "interface/mod_settings/mod_settings_stub.s", region="ext"),
    BlockSpec("mod_settings_code", MOD_SETTINGS, "interface/mod_settings/mod_settings.c", region="ext",
              units=("interface/mod_settings/aspect_list.c", "interface/mod_settings/mod_options.c",
                     "interface/mod_settings/option_list.c")),
    BlockSpec("mod_settings_data", MOD_SETTINGS, size=MOD_SETTINGS_DATA_SIZE, region="ext"),
    BlockSpec("mod_options_stub", MOD_SETTINGS, "interface/mod_settings/mod_options_stub.s", region="ext"),
    BlockSpec("mod_options_data", MOD_SETTINGS, size=MOD_OPTIONS_DATA_SIZE, region="ext"),
    BlockSpec("mod_raw_table", MOD_SETTINGS, size=MOD_RAW_TABLE_SIZE, region="ext"),
    BlockSpec("aspect_list_data", MOD_SETTINGS, size=ASPECT_LIST_DATA_SIZE, region="ext"),
    # The split title's RomFS (install/title/split_romfs.py): the mount, the game data's open and the lookup, and the
    # game's nn::fs::FileStream::TryInitialize with its first instruction (the lookup's hook takes it)
    BlockSpec("split_romfs", SPLIT_ROMFS, "install/title/split_romfs.c", region="ext"),
    BlockSpec("split_romfs_stub", SPLIT_ROMFS, "install/title/split_romfs_stub.s", region="ext"),
    BlockSpec("aspect_stub", ASPECT_RATIO, "cheats/aspect_stub.s", region="ext"),
    BlockSpec("aspect_code", ASPECT_RATIO, "cheats/aspect_ratio.c", region="ext"),
    BlockSpec("aspect_data", ASPECT_RATIO, size=ASPECT_DATA_SIZE, region="ext"),
    BlockSpec("aspect_anchors", ASPECT_RATIO, size=ASPECT_ANCHORS_SIZE, region="ext"),
    BlockSpec("damage_numbers_stub", DAMAGE_NUMBERS, "interface/damage_numbers/damage_numbers_stub.s", region="ext"),
    BlockSpec("damage_numbers_code", DAMAGE_NUMBERS, "interface/damage_numbers/damage_numbers.c", region="ext"),
    BlockSpec("damage_numbers_data", DAMAGE_NUMBERS, size=DAMAGE_NUMBERS_DATA_SIZE, region="ext"),
    # The C-stick turns the camera and the aims analogically: the entries for FUN_00b3cc64's question "is the C-stick
    # tilted", for the cameras' calls of FUN_00bfd028 and for the aim's hooks in FUN_00b2041c, and the curated tuning
    # (modern_camera.py data_block)
    BlockSpec(MODERN_CAMERA, MODERN_CAMERA, "gameplay/modern_camera/modern_camera.c", region="ext",
              defines=(f"DATA_SIZE={MODERN_CAMERA_DATA_SIZE}", f"STATE_SIZE={MODERN_CAMERA_STATE_SIZE}")),
    BlockSpec("modern_camera_data", MODERN_CAMERA, size=MODERN_CAMERA_DATA_SIZE, region="ext"),
    BlockSpec("quest_layouts_stub", QUEST_LAYOUTS, "interface/quest_layouts/quest_layouts_stub.s", region="ext"),
    BlockSpec("quest_layouts_code", QUEST_LAYOUTS, "interface/quest_layouts/quest_layouts.c", region="ext"),
    BlockSpec("quest_layouts_data", QUEST_LAYOUTS, size=QUEST_LAYOUTS_DATA_SIZE, region="ext"),
    BlockSpec("horn_songs_code", HORN_SONGS, "interface/horn_songs/horn_songs.c", region="ext"),
    BlockSpec("horn_songs_data", HORN_SONGS, size=HORN_SONGS_DATA_SIZE, region="ext"),
)


def __getattr__(name: str):
    if name in ("PACKED_LAST", "BLOCKS"):
        globals()["PACKED_LAST"], globals()["BLOCKS"] = _declared()
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


VARIABLES = (
    # single_screen_keyboard.s: the key the virtual finger is on (+0) and whether its lit look is on (+4); in the 8
    # bytes bss_tail's first aligned variable leaves unused (no other room)
    # The rectangle of the sub-view being opened, moved with the interface (cheats/aspect_ratio.c); FUN_00aee0f0 copies
    # it
    VariableSpec("aspect_state", ASPECT_RATIO, 16),
    VariableSpec("aspect_way", ASPECT_RATIO, 4),
    VariableSpec("mod_settings_state", MOD_SETTINGS, 8),
    VariableSpec("aspect_list_state", MOD_SETTINGS, 4),
    VariableSpec("option_list_state", MOD_SETTINGS, 4),
    VariableSpec("mod_options_state", MOD_SETTINGS, 64),
    VariableSpec("fps_carry_state", MOD_SETTINGS, 4),     # mod_options.c: the frame rate's credit, a float
    VariableSpec("keyboard_finger", SINGLE_SCREEN, 8, align=8),
    VariableSpec("target_request", "touchless_target", 4),  # dpad_filter.s -> target_button.s
    VariableSpec("fast_text_state", "fast_text", 8),        # fast_text.s: calls while B is held, last result
    VariableSpec("fast_gathering_state", "fast_gathering", 4),  # fast_gathering.s: the mPlayerSpeed it last wrote
    VariableSpec("select_kick_state", "select_kick", 4),     # select_kick.c: Select held (1), seen by the menu (2)
    VariableSpec("save_redirect_state", "save_redirect", 4),  # game_redirect.c: bit n: file kind n is read from MH4U's
    # death_camera_skip.c, intro_skip.c -> select_kick.c: frames left in which START belongs to the death camera or to
    # the touch screen's Skip
    VariableSpec("death_camera_skip_state", "skip_death_camera", 4),
    # bubbleblight.s: the local hunter's bubbles (+0 state, +4 timer, +8 unused) and bubble_bind.s' slide velocity
    # (x, z) of the large bubbles at +8 / +12 (`bubble_state + 8`): one variable, because bss_tail had 4 bytes left
    VariableSpec("bubble_state", BUBBLEBLIGHT, 16),
    # split_romfs.c: `mod:` mounted (+0: 0 not tried yet, 1 mounted, 2 not mounted), its buffer (+4) and size (+8), the
    # game data's archive path while the game mounts `rom:` (+12, else 0)
    VariableSpec("split_romfs_state", SPLIT_ROMFS, 16),
    # The looks worn: written by the selector, read by the
    # render.
    VariableSpec("layered_state", "layered_equipment", 0x3C),
    VariableSpec("layered_ui", "layered_equipment", 0x64),     # layered.h: struct ui
    VariableSpec("layered_preview", "layered_equipment", 0x68),  # layered.h: struct preview
    # single_screen_prompt.s reads it (HELP_FLAGS): non-zero while a forge-style screen of Layered Gear is on, which
    # closes the help strips (layered.h screens_open); the Rare Materials Exchange does not use it
    VariableSpec("screens_open", SINGLE_SCREEN, 4),
    VariableSpec("layered_debug", "layered_equipment", 8),     # layered_selector.c: struct debug (probes)
    # struct select: the title's hunter select screen, its hunters wear their slots' looks (bss_tail is full: its
    # 8 bytes came from layered_debug, whose counters became u16)
    VariableSpec("layered_select", "layered_equipment", 8),
    # The looks the other players sent (layered.h struct remote: the hash of what was sent, the sequence, 4 entries)
    VariableSpec("layered_remote", "layered_equipment", 216),
    # The render of the other players' looks (layered.h struct render): the quest's snapshot of their entries and what
    # each hall hunter was last dressed with
    VariableSpec("layered_render", "layered_equipment", 72),
    VariableSpec("felyne_ui", "layered_equipment", 20),        # felyne_looks.h: struct felyne_ui
    VariableSpec("exchange_ui", RARE_EXCHANGE, 72),           # rare_exchange.c: struct xui
    # The game GUI recorder's frame counters (u32 started, done): only the
    # recording probe writes them (tools/ui/ui_probe.py, block gui_frame_marks_probe), never the product. Not a debug
    # variable: the product's own telemetry writes the debug place (Alatreon's shell log); its room came from halving
    # that log's ground ring.
    VariableSpec("gui_frame_marks", "game gui recorder (the recording probe)", 8),
    # The game GUI engine's state (interface/game_gui/game_gui_engine.c, struct state): frames run, the screen chosen
    # (index + 1) for the draw's hook, the watched group's + 0x44 (probes) and the groups of the table met in the last
    # frame
    VariableSpec("game_gui_state", GAME_GUI, 16),
    # The photo mode (interface/game_gui/game_gui_engine.c, struct photo): on (+0, the Guild Card's GUI hidden but the
    # characters, the sky and the greeting), and the raw pad bits it hid from the game last frame (+4)
    VariableSpec("game_gui_photo", GAME_GUI, 8),
    VariableSpec("face_dump", "target_face (FACE_DEBUG)", 0x20, align=0x10, debug=True),
    # +0 next entry, +4 call count, +0x10 last values (16 bytes), +0x20 ring of 88 entries of 32 bytes (100 until
    # the merge of xx and main, whose variables left bss_tail no room for more).
    VariableSpec("input_log", "research/probes/asm/input_event_log.s", 0x20 + 88 * 0x20, align=0x10, debug=True),
    # calls per candidate (canary_probe.py)
    VariableSpec("canary_hits", "research/probes/asm/canary.s", 12 * 4, debug=True),
    # Header 0x20, ring of 128 events of 8 bytes, snapshot (0x250 bytes) and 24 page checksums (save_flag_probe.py).
    VariableSpec("save_flag_log", "research/probes/asm/save_flag_log.s", 0x20 + 128 * 8 + 0x250 + 24 * 4, align=0x10,
                 debug=True),
    # Header 0x30, rings of 50 speed entries and 38 music entries of 32 bytes (hunt_probe.py; 56 and 42 until the merge
    # of xx and main, whose variables left bss_tail no room for more).
    VariableSpec("hunt_log", "research/probes/asm/hunt_log.s", 0x30 + (50 + 38) * 0x20, align=0x10, debug=True),
    # The Alatreon probes' telemetry (core/monsters/porting/sdk/telemetry.h, struct probe_log).
    VariableSpec("alatreon_probe", "alatreon (probes, research/probes/alatreon_probe.py)", 0xA20, align=0x10,
                 debug=True),
    # His shells' telemetry in the product (probe F2; core/monsters/porting/shell_log.c, struct shell_log): no
    # probe builds it, so it may share the probes' place.
    VariableSpec("alatreon_shell_log", "alatreon (probe F2, src/shell_log.c)", 0xB50, align=0x10, debug=True),
    # Probe N1 of a new monster id (core/monsters/porting/newid_probe.c, struct newid_log): its telemetry,
    # and the new ids' em data slots (0x404 bytes with 76 new ids: newid_telemetry.SIZE).
    VariableSpec("newid_probe", "new monster id (probe N1, research/probes/newid_probe.py)", 0x500, align=0x10,
                 debug=True),
    # The quest manager's kill records of the new monster ids 124-199, 8 bytes each (core/monsters/porting/new_id.py,
    # KILL_SITES): 76 * 8. In the extension's variables (the patcher calls Layout.reserve).
    VariableSpec("new_id_kills", "new monster id (core/monsters/porting/new_id.py)", 0x260, align=0x10,
                 region="ext_vars"),
    # The em data slots of the new monster ids, 2 words each (new_id.extend_tables, `slots`): 76 * 8.
    VariableSpec("new_id_em_data", "new monster id (core/monsters/porting/new_id.py)", 0x260, align=0x10,
                 region="ext_vars"),
    # The active hunt records of ids 128-255 (128 x 8 bytes) and each save slot's, kept from its file (3 x 0x400): the
    # patcher calls Layout.reserve (core/monsters/porting/hf_records.py)
    VariableSpec("hf_records", "new monster id (core/monsters/porting/hf_records.py)", 0x400, align=0x10,
                 region="ext_vars"),
    VariableSpec("hf_records_slots", "new monster id (core/monsters/porting/hf_records.py)", 0xC00, align=0x10,
                 region="ext_vars"),
    # The log of Heavenfall's own save files: every call of the file task's two operations (core/save/game_redirect.c
    # struct save_log: 16 + 160 notes of 16 bytes); patch_game_redirect calls Layout.reserve
    VariableSpec("save_redirect_log", "save_redirect", 0xA10, align=0x10, region="ext_vars"),
    # Damage Numbers' events, numbers and monsters (damage_numbers.c struct dmg_state); patch_damage_numbers reserves it
    VariableSpec("damage_numbers_state", DAMAGE_NUMBERS, DAMAGE_NUMBERS_STATE_SIZE, align=0x10, region="ext_vars"),
    # The modern camera's kept C-stick, each camera input's turn and the aim's (modern_camera.c struct
    # modern_camera_state); patch_modern_camera reserves it
    VariableSpec("modern_camera_state", MODERN_CAMERA, MODERN_CAMERA_STATE_SIZE, region="ext_vars"),
    # The horn's songs' rows and lights (horn_songs.c struct horn_state); patch_horn_songs reserves it
    VariableSpec("horn_songs_state", HORN_SONGS, HORN_SONGS_STATE_SIZE, align=0x10, region="ext_vars"),
    # gameplay/monster_phases/monster_phases.s: the phases of 77, 78 and 124 and the monster whose theme played last
    VariableSpec("monster_phase", "monster_phases", 4),
    # adapter, engine side: the effect player's own managers, which MH4U lacks (core/monsters/porting/sdk/proof_api.h):
    # the variables holding sProofEffect, sFestaProofEffect and
    # sProofEffectSequence, and the count of live cores.
    VariableSpec("proof_registry", "mhgen_port (core/monsters/porting/effect_player)", 4),
    VariableSpec("proof_budget", "mhgen_port (core/monsters/porting/effect_player)", 4),
    VariableSpec("proof_mgr", "mhgen_port (core/monsters/porting/effect_player)", 4),
    VariableSpec("proof_live_cores", "mhgen_port (core/monsters/porting/effect_player)", 4),
    # adapter half 2, the monster side (core/monsters/porting/effect_player/monster_4u.c): the sides of the monsters
    # that play effects, any number of them: the first of their list and how many (sdk/proof_api.h struct
    # proof_side_list)
    VariableSpec("proof_sides", "mhgen_port (core/monsters/porting/effect_player)", 2 * 4),
    # the shells' frame count, which MH4U's sGameControl does not keep (sdk/shell_api.h game_frames): the shell
    # manager's frame adds one (proof/shell_mgr.c)
    VariableSpec("proof_shell_frames", "mhgen_port (core/monsters/porting/effect_player)", 4),
    # the variable holding the shells' manager sShell, which MH4U lacks (MH Generations keeps it at 0xDA95F0;
    # proof/shell_mgr.c, sdk/enemy_4u.h shell_launch_01_from)
    VariableSpec("proof_shell_mgr", "mhgen_port (core/monsters/porting/effect_player)", 4),
)

# Game functions the sources call by name (addresses in the update's executable).
GAME_SYMBOLS = {
    "clear_bss": 0x100024,        # called first by the executable's entry (0x100000)
    "panel_update": 0xB94854,     # FUN_00b94854, target camera panel update
    "group_show": 0xAE53E0,       # FUN_00ae53e0(group, visible)
    "group_show_body": 0xAE53E4,  # its second instruction (face_show.s runs the first itself)
    "gui_group_order": 0xAE63C8,  # FUN_00ae63c8(group, layer, priority): bits 27-31 and 19-26 of +0x18, then marked
    "pane_redraw": 0xAE6BCC,
    "gx_frame_wait": 0xBF5FEC,    # FUN_00bf5fec(gx): the frame's wait for the GPU, then the buffers' swap
    "new_profile": 0xC25B50,        # FUN_00c25b50(save, profile), last call of the character creation
    "set_story_flag": 0xC1B0E8,     # FUN_00c1b0e8(save, id)
    "set_quest_cleared": 0xC1F170,  # FUN_00c1f170(save, quest id)
    "free_box_slot": 0xC25918,      # FUN_00c25918(save): first free equipment box slot, or 0xFFFF
    "mark_obtained": 0xC1E274,      # FUN_00c1e274(save, equipment record, 0)
    "equip_from_box": 0xC1B26C,     # FUN_00c1b26c(save, save + 0x5C, 0): worn pieces from their box indices
    "event_seen": 0x1A01B8,       # FUN_001a01b8(event object, event id): non-zero if already seen
    "area_number": 0x69DBF0,      # FUN_0069dbf0(stage, area): the area number scripts see (the Everwood's own)
    "weak_request": 0x93E0AC,     # FUN_0093e0ac(monster, area): ask to go to `area` when weak
    "follow_request": 0x942358,   # FUN_00942358(monster, area, ...): ask to follow a monster or go to `area`
    "enemy_data": 0x688854,       # FUN_00688854(manager, species, variant): its loaded emd, 8 bytes in (routes +0x30)
    "map_rows": 0x68CBC4,         # FUN_0068cbc4(manager, route list, map): the map's row pointers, or 0
    "map_area_counts": 0xE087B4,  # u8 per map id: its areas (the row pointers of each route list)
    "message_update": 0x5A9310,   # FUN_005a9310(pressed, ?, out, manual): the conversation windows' text
    "motion_speed": 0xB06624,     # FUN_00b06624(hunter, speed in s0): the hunter model's motion speed
    "has_skill": 0xD04F5C,        # FUN_00d04f5c(hunter, skill): non-zero if the hunter has that skill active
    # Bubbleblight (gameplay/bubbleblight/bubbleblight.s; gameplay/bubbleblight/bubbleblight.py)
    "hit_resume": 0xBE9624,       # FUN_00be8dfc's instruction after the load of the hit's status words (0xBE9620)
    "status_apply": 0xB37FE0,     # FUN_00b37fe0(hunter): the hit's statuses; its result is non-zero if one took
    "timer_step": 0xB0709C,       # FUN_00b0709c(hunter, &timer): timer -= the frame delta; 1 when it is <= 0
    "player_reset": 0xB3BAF4,     # FUN_00b3baf4(hunter): the player's reset
    "hunter_init": 0xB0C034,      # FUN_00b0c034(hunter): the constructor's reset of the hunter's fields
    "cure_all_body": 0xB15D50,    # FUN_00b15d4c's second instruction (the cure-all: Nulberry; the hook runs the first)
    "attack_buff": 0xB6AEB4,      # FUN_00b6aeb4(hunter, 1, bonus): the attack bonus (pw+0x276), as the Might Seed's
    "buff_duration": 0xB3B2D8,    # FUN_00b3b2d8(hunter, duration in s0) -> s0: the skills' scaling of an item's time
    "heal": 0xB24580,             # FUN_00b24580(hunter, health, 0): heals, with the food skills' scaling
    "status_icon_resume": 0xB8A5D0,  # FUN_00b8a524: after the cell hook of bubble_icon.s (0xB8A5CC, a strb)
    "hunter_masks": 0xB31630,     # FUN_00b31630(hunter) -> the mask pw + 0x800 (the party list's type 2 entries)
    # Bubbleblight's look and sound (gameplay/bubbleblight/bubble_fx.s): the path FUN_00b3f560 takes for the
    # waterblight's effect
    "effect_request_init": 0xC0CA90,  # FUN_00c0ca90(request): the 0x68-byte effect request with its defaults
    "effect_send": 0xC088D8,      # FUN_00c088d8(*0x10572A4, request) -> effect: makes the effect and attaches it
    "rate_gate": 0xC093F0,        # FUN_00c093f0(s0 now, s1 before, s2 period, s3 phase): 1 when the period was crossed
    "hunter_sound": 0xB15C94,     # FUN_00b15c94(hunter, request id, 0): a sound request of the hunter's bank
    # The lobby's facility menu (lyt\lobby\ui401) and the Smithy.
    "facility_menu_set": 0xA1EA8C,   # FUN_00a1ea8c(obj, menu, row, bright lines)
    "menu_cursor_init": 0x9BC954,    # FUN_009bc954(obj, cursor, count, rows, disabled, a / v / h sounds)
    "menu_cursor_update": 0x9BC9B4,  # FUN_009bc9b4(obj, cursor, 0): 1 A, 2 B
    "facility_pressed": 0x9AC3A4,    # FUN_009ac3a4(obj, GUI bits): pressed this frame
    "facility_dirs": 0x9B3830,       # FUN_009b3830(obj): D-pad bits, pressed or repeating
    "facility_help": 0x298560,       # FUN_00298560(kind, file, message): the help line
    "sound_play": 0x31294C,          # FUN_0031294c(*0xFCCD6C, sound)
    "smithy_done": 0x9AE280,         # the end of the Smithy's per-frame state switch
    "gui_sprite": 0xA397F4,          # FUN_00a397f4(obj, group hash, pane hash, visible): shows / hides a sprite
    "gui_null": 0xA39138,            # FUN_00a39138(obj, group hash, pane hash, visible): shows / hides a null
    "gui_text_ref": 0xC0EFA8,        # FUN_00c0efa8(*0x1057534, &(group hash, 0), &(pane hash, 0)): a text's ref
    "preview_rotate": 0xAABB8C,      # FUN_00aabb8c(obj, preview hunter): turns it with the stick (held 0x400 / 0x800)
    "preview_stick": 0x9AD458,       # FUN_009ad458(obj): the stick's bits (pad + 0x350), 0 while a window is open
    "preview_touch": 0xA272B0,       # FUN_00a272b0(obj): the frame's touch buttons; Zoom adds L / R to pad + 0x340
    "camera_controls": 0xC05990,     # FUN_00c05990(sCamera, buttons, stick): zoom (L / R) and move bits
    "camera_control_set": 0xC056C4,  # FUN_00c056c4(sCamera, bits): sCamera + 0x166D, read by the preview camera
    "text_slot": 0x5A99A8,           # FUN_005a99a8(slot, UTF-16 string, characters): kept for common message 0, 0
    "text_common": 0x5A9164,         # FUN_005a9164(pane ref, common file, message)
    "text_lobby": 0x5A882C,          # FUN_005a882c(pane ref, lobby file, message)
    "text_show": 0xAE7618,           # FUN_00ae7618(text pane, visible)
    # Hunters' models, the Smithy's preview and the save (layered equipment).
    "armor_model": 0x2F4258,         # FUN_002f4258(equipment, record, gender, fallback): an armor piece's model
    "weapon_model": 0x2F0FD4,        # FUN_002f0fd4(equipment, record): a weapon's model
    "mem_copy": 0x10ED68,            # FUN_0010ed68(dst, src, size)
    "make_record": 0x2F2AA4,         # FUN_002f2aa4(equipment, out, type, id): an equipment record
    "hunter_equip": 0xB0AB90,        # FUN_00b0ab90(hunter, record): a lobby hunter puts an armor piece on
    "hunter_weapon": 0xB0AF84,       # FUN_00b0af84(hunter, record, 1): ... and a weapon
    "hunter_load": 0x65FCA8,         # FUN_0065fca8(0x109D8C4, hunter): requests the models that changed
    "hunter_setup": 0xB099AC,        # FUN_00b099ac(hunter, info): a hunter's status from a player info
    "part_dye": 0xB0A978,            # FUN_00b0a978(hunter, ref, model): a part model's colour, from the real piece
    "model_colour": 0xB05AE4,        # FUN_00b05ae4(model, &rgba, group): a colour on the model's materials of a group
    "hunter_dyes": 0xB0B6CC,         # FUN_00b0b6cc(hunter): FUN_00b0a978 on the five parts
    "preview_start": 0x9EDCEC,       # FUN_009edcec(obj, record, mode): the Smithy's preview (1 armor, 2 weapon)
    "preview_ready": 0xA64E9C,       # FUN_00a64e9c(obj, hunter): every part of the hunter loaded
    "preview_frame_close": 0x59F680,  # FUN_0059f680(obj + 0x104E8)
    "viewport_close": 0xC00EC8,      # FUN_00c00ec8(*0x105729C)
    "save_copy_out": 0xC2789C,       # FUN_00c2789c(save, buffer, 0x12600): save data -> the file's buffer
    "file_checksum": 0x2ABCAC,       # FUN_002abcac(files, buffer, size, write): the save file's checksum
    # Heavenfall's own save files (save/game_redirect.py)
    "file_manager": 0x104DEB0,       # the variable holding the file thread's manager (+0x20 the extdata id)
    "file_exists": 0xC19CE8,         # FUN_00c19ce8(manager, name, archive, &found): the file exists (0 = no error)
    "file_extdata_set": 0xC195FC,    # FUN_00c195fc(manager, id): the extdata the archive 1 operations mount
    "save_task_resume": 0x2ACAA4,    # FUN_002acaa0 after its first instruction (the archive 0 file operations)
    "extdata_task_resume": 0x2ABA08,  # FUN_002aba04 after its first instruction (the archive 1 file operations)
    # The forge-style screens: the forge's
    # materials box and money box, its yes / no window, the hammer scene, payment and the GUI's panes by hash; all in
    # the runs of the base games and the update (eur_base, usa_base, usa_update)
    "materials_box": 0x9F6C10,       # FUN_009f6c10(obj): the materials box (rows at *(obj + 0xB8FC))
    "forge_hide": 0xA1C640,          # FUN_00a1c640(obj): hides the Smithy's panels (ui407, ui402, ui034, the money box)
    "model_frame": 0x2727C8,         # FUN_002727c8(): shows ui034's model frame with its L, R and stick words
    "money_write": 0xA52860,         # FUN_00a52860(obj, money, 1): writes the sum in the money box
    "money_show": 0xA5D424,          # FUN_00a5d424(obj, shown, 0): shows / hides the money box (obj + 0xA010)
    "window_open": 0x2921CC,         # FUN_002921cc(kind, slot, 4[, 1]): the yes / no window of the Smithy (ui006)
    "window_update": 0x2A2414,       # FUN_002a2414(): draws the window every frame
    "window_close": 0x29E5BC,        # FUN_0029e5bc(3, 0)
    "window_answer": 0xA66E60,       # FUN_00a66e60(obj, &answer, input, 0xFFFF): 1 yes, 2 no
    "window_input": 0xAA6480,        # FUN_00aa6480(obj): the window's input
    "hammer_scene": 0x9D61E4,        # FUN_009d61e4(scene, kind): the forging scene (3 when the weapon is a hammer)
    "hammer_scene_busy": 0x9BF778,   # FUN_009bf778(scene): not 0 once the scene has ended
    "hammer_kind": 0xA92AF0,         # FUN_00a92af0(obj): 0 or not, picks the scene's kind
    "money_add": 0xC27764,           # FUN_00c27764(save, amount): the player's zenny (negative pays)
    "item_take": 0xAAB06C,           # FUN_00aab06c(obj, item, quantity): takes the box first, then the pouch
    "item_count": 0xC21B18,          # FUN_00c21b18(save, item): the pouch and the box together
    "item_seen": 0xC1BEF8,           # FUN_00c1bef8(save, data, item): the item has been obtained once
    # The Wyporium's Rare Materials Exchange (gameplay/wyporium/rare_exchange.c): the trade
    # list's drawing and number columns, the box's room, the give, and the places of the Wyporium's FUN_009b6d84 its
    # hooks return to
    "trade_draw": 0x9E2B20,          # FUN_009e2b20(obj, what): 9 the list's groups, 10 its rows, 0xB the item panel
    "trade_hide": 0xA8C1FC,          # FUN_00a8c1fc(obj, which): 0 hides every group of the trade list (ui407, ui402)
    "trade_row_number": 0xA72A80,          # FUN_00a72a80(obj, row, value, kind, money): the row's number column
    "trade_text_colour": 0xAE0F24,         # FUN_00ae0f24(text ref, &rgba)
    "trade_icon_hide": 0xD942D4,         # FUN_00d942d4(sprite ref, shown)
    "item_room": 0xA02C60,           # FUN_00a02c60(_, item, place): room left for it (place non-zero: the item box)
    "item_give": 0xC1EA50,           # FUN_00c1ea50(save, item, quantity, lobby + 0xA3D4): into the item box
    "trade_buttons": 0xA51A24,       # FUN_00a51a24(obj, layout, flags): the bottom buttons (2 list, 4 confirm, 9 done)
    "item_box_close": 0xA981C4,      # FUN_00a981c4(obj): closes the item box viewer the done step opened
    "wyporium_menu_a": 0x9EB38C,     # FUN_009eb38c(obj, cursor, 0): the menu's cursor, 1 on A on a bright line
    "wyporium_tail": 0x9B7A38,       # FUN_009b6d84: the end of the state switch (state changes, the old state's cases)
    "wyporium_menu": 0x9B729C,       # the menu and its help written for the line highlighted
    "wyporium_chain": 0x9B7018,      # the help chain by line, after its first compare
    "wyporium_leave": 0x9B7B80,      # the new state's cases, after the old state's
    "icon_draw": 0xC118F4,           # FUN_00c118f4(*0x1057534, pane + 0x10, icon, &colour)
    # The item box's Armor Pigment
    "palette_colour": 0xC0E3C8,      # FUN_00c0e3c8(&rgba, gui, i): colour i of the 12 of the pigment's palette
    "sprite_texture": 0xAE5254,      # FUN_00ae5254(ref): the texture a sprite draws (0 if none)
    "texel_colour": 0xD0D76C,        # FUN_00d0d76c(&rgba, gui, texture, xy): a texel of a texture the game can read
    "sub_view_open": 0xC042EC,       # FUN_00c042ec(sCamera, target, &rect, &clear, layer, priority): opens a sub-view
    "smithy_panel": 0x296248,        # FUN_00296248(obj, shown, 0)
    "smithy_panel_b": 0x29E484,      # FUN_0029e484(obj, shown)
    "smithy_panel_c": 0xA8E230,      # FUN_00a8e230(obj, shown)
    "group_sprite_ref": 0xAE5B2C,    # FUN_00ae5b2c(ref, group, key): a sprite of a group
    "group_text_ref": 0xAE5D34,      # FUN_00ae5d34(ref, group, key): a text of a group
    "group_find": 0xB045A8,          # FUN_00b045a8(*(gui + 0x100), key): the index of a group by name hash
    "group_at": 0xB048F0,            # FUN_00b048f0(*(gui + 0x100), index): that group
    # The monster engine, for the Alatreon port (core/monsters/porting/sdk/enemy_4u.h)
    "fatalis_construct": 0x89F12C,    # the Fatalis family's constructor (ids 77, 78, 79, 117)
    "fatalis_vtable": 0xE69CA4,       # ... its vtable
    "zinogre_construct": 0x8599E8,    # Zinogre's family's constructor (ids 48, 49, 114; Mizutsune's host, spec.ZINOGRE)
    "deviljho_construct": 0x818650,   # Deviljho's family's constructor (ids 42, 43, 113; Glavenus' host, spec.DEVILJHO)
    "gypceros_construct": 0x703364,   # Gypceros' family's constructor (ids 9, 10; Great Maccao's host, spec.GYPCEROS)
    "jaggi_construct": 0x8660B8,      # Jaggi's constructor (id 56 alone; Maccao's host, spec.JAGGI)
    "seregios_construct": 0x8B65B4,   # Seregios' family's constructor (ids 88, 122; Valstrax's host, spec.SEREGIOS)
    "rathian_construct": 0x6EC8D4,    # Rathian's family's constructor (ids 1-6; Astalos' host, spec.RATHIAN)
    "uenemy_vtable": 0xE6B058,
    "uEnemy_construct": 0x955FF4,
    "enemy_set_status": 0x9167EC,
    "enemy_play_motion": 0x9190C4,
    "enemy_motion_ended": 0xB05DF4,
    # ... the functions Alatreon's decompiled code calls (sdk/em_api.h)
    "anim_find": 0xCFBA14,
    "part_play_anim": 0x636B64,
    "enemy_parts_changed": 0x1A64C0,
    "enemy_part": 0x1A4814,
    "enemy_break_level": 0x94741C,
    "enemy_bits_test": 0x936418,
    "enemy_bits_5893": 0x938620,
    "enemy_act_script": 0x9197C0,
    "enemy_set_action_0_7": 0x911AD0,
    "enemy_set_float_5c": 0x916140,
    "enemy_data_float_10": 0x93E7B4,
    "enemy_em5915_set_1": 0x930790,
    "enemy_play_motion_blend2": 0x945DB0,
    "enemy_is_angry": 0x954E48,
    "enemy_flags_set": 0x922F9C,
    "enemy_flags_clear": 0x92E87C,
    "enemy_record_start_4u": 0x94E39C,
    "enemy_motion_set": 0x94F440,
    "enemy_motion_play": 0x94E350,
    "enemy_motion_at": 0x91AB1C,
    "enemy_motion_speed": 0x922C78,
    "enemy_base_speed": 0x93D8A8,
    "enemy_rise": 0x92E9D4,
    "enemy_neutral_again_3": 0x94DCBC,
    "enemy_neutral_again_6": 0x9559A8,
    "enemy_rate_clear": 0x916260,
    "enemy_move_by_rate": 0x955478,
    "enemy_next_action": 0x94EF9C,
    "angle_sin": 0x568BF0,
    "angle_cos": 0x568BB8,
    "enemy_set_record2": 0x933144,
    "enemy_set_record2_0": 0x914DFC,
    "enemy_owner_request_4u": 0x93457C,
    "enemy_turn_start": 0x92DC88,
    "enemy_turn_step": 0x92DD04,
    "enemy_turn_table_start": 0x911C44,
    "enemy_turn_table_step": 0x92F720,
    "enemy_rates_clear": 0x91B3F4,
    "enemy_move_by_rate_turned": 0x91150C,
    "enemy_face_homing": 0x91DB84,
    "enemy_fall_start": 0x93CDA8,
    "enemy_fall_step": 0x93CE98,
    "enemy_climb_start": 0x938F10,
    "enemy_climb_step": 0x938FA4,
    "enemy_on_ground": 0x91ADB4,
    "enemy_motion_curve": 0x922288,
    "enemy_turn_over_frames": 0x9175A8,
    "angle_of": 0x568C8C,
    "enemy_scale": 0x911CB4,
    "enemy_no_cancel": 0x922CD8,
    "enemy_no_damage_motion": 0x93C6C8,
    "enemy_attack_end": 0x90F934,
    "enemy_update_target": 0x92D0D4,
    "enemy_point_around": 0x934F7C,
    "enemy_size_ratio": 0x923FC8,
    "enemy_motion_index": 0x90F994,
    "enemy_rate_accelerate": 0x9110C8,
    "enemy_move_turned_at": 0x91B468,
    "enemy_joint_pos": 0x93093C,
    "enemy_is_action": 0x94D788,
    "enemy_motion_at_1": 0x93906C,
    "enemy_part_record_alt": 0x93415C,
    "enemy_part_record_reset": 0x936EA8,
    "enemy_joint_effect_4u": 0x910C6C,
    "enemy_parts_any": 0x91A884,
    "enemy_destruct": 0x956180,       # uEnemy's destructor
    "enemy_class_dti": 0x10B8770,     # uEnemy's DTI (his own class is built on uEnemy's vtable)
    "dti_allocator": 0x1076CC,
    "unit_init": 0x627D14,            # cUnit's constructor (MH Generations 0x879140)
    "unit_fini": 0x627DA0,            # its destructor, empty (0x8791D0)
    "mt_vec_ctor": 0x1001F5,          # the runtime's array constructor, Thumb (0x2EF8E8)
    "mt_vec_dtor": 0x1013E5,          # and destructor, Thumb (0x2F5D80)
    "game_main": 0x1057194,           # the variable holding the main object
    # A new monster id (core/monsters/porting/new_id.c)
    "factory_fail": 0x69144C,          # FUN_00690228's failing default: no object
    "quest_monster_flags": 0x6A74F8,   # FUN_006a74f8(quest, u8 flags[124]): the quest's monsters
    "enemy_data_load": 0x6894B8,       # FUN_006894b8(manager, id, variant): loads its etd/emd
    "monster_data_manager": 0xF32004,  # the variable holding sEnemy: the monsters' data, the spawn requests
    # New quests (gameplay/quests/quest_unlock.s)
    "quest_cleared": 0xC21FE0,         # FUN_00c21fe0(save, quest id): non-zero if cleared
    "story_flag": 0xC1C278,            # FUN_00c1c278(save, flag): non-zero if the story flag is set (layered ranks)
    "quest_available_body": 0xA15B64,  # FUN_00a15b60's second instruction (the hook runs the first)
    # Monster phases (gameplay/monster_phases/monster_phases.s)
    "monster_theme": 0x30E16C,         # FUN_0030e16c(manager, monster id, u8 *queue, u32 *request)
    "music_play": 0x309D5C,            # FUN_00309d5c(manager, player, state, queue, [request, instance, force])
    "quest_music_start": 0x301BF8,     # FUN_00301bf8(manager): the sound manager's reset at a quest's start
    # The hunt probe (research/probes/asm/hunt_log.s)
    "music_update": 0x308744,          # FUN_00308744(manager): the music state machine, once a frame
    "music_stop": 0x3069E8,            # FUN_003069e8: stops a player
    "rage_recompute": 0x922D1C,        # FUN_00922d1c(monster): rage / Frenzy multipliers
    # New hunter equipment (equipment/new_gear/new_recipes.s)
    "recipe_body": 0x2F2110,           # FUN_002f210c's second instruction (the hook runs the first, cmp r1, #0)
}

# Alatreon's shells in MH4U (core/monsters/porting/sdk/enemy_4u.h): MH4U
# builds uShell<n> from a record (shell_create_4u); the species call each record's wrapper.
GAME_SYMBOLS |= {
    # A Felyne's gear (equipment/layered/felyne_looks.c)
    "felyne_model_weapon": 0x2F6C98,    # FUN_002f6c98(equipment, id): a weapon's model number
    "felyne_model_armor": 0x2F5F24,     # FUN_002f5f24(equipment, type: 0 body, 1 head, id)
    "felyne_model_body": 0x2F6C20,      # FUN_002f6c20(equipment, 0, id, gender): id 0 the base's body
    "felyne_model_pair": 0x2F1438,      # FUN_002f1438(equipment, [kind, 0, id])
    "felyne_model_pair_body": 0x2F1FA8,  # FUN_002f1fa8(equipment, [kind, 0, id], gender)
    "felyne_suit": 0x2F8930,            # FUN_002f8930(equipment, pair): a body that is a whole suit
    "felyne_head_case": 0x2F8A34,       # FUN_002f8a34(equipment, pair): the helm that opens and closes
    "felyne_effect": 0x69998C,          # FUN_0069998c(manager, actor, model, pair): a piece's effect by its real id
    "felyne_quest_effect": 0x699D5C,    # FUN_00699d5c(manager, actor, model, pair): the same in a quest
    "felyne_scene_effect": 0x6997C4,    # FUN_006997c4(manager, model, pair, record): the same in a cutscene
    "felyne_scene_joints": 0x69A484,    # FUN_0069a484(manager, actor, pair, record): a suit's joints in a cutscene
    "felyne_main_record": 0xC2065C,     # FUN_00c2065c(save): the main cat's record
    "felyne_second_record": 0x697028,   # FUN_00697028(): the second cat's record, or 0
    "felyne_main_active": 0xA2D8D4,     # FUN_00a2d8d4(): the main cat may go on quests
    "felyne_actor_update": 0xA3725C,    # FUN_00a3725c(obj, actor, record): a live cat takes a record's gear
    "felyne_town_actor": 0xA5E49C,      # FUN_00a5e49c(obj, 0): the main cat in the area, or 0
    "felyne_second_actor": 0x9FD784,    # FUN_009fd784(obj): the second cat in the area, or 0
    "felyne_try_on": 0xA266A4,          # FUN_00a266a4(obj, part, id, record, mode): opens the Felyne preview
    "felyne_try_on_ready": 0xA64E10,    # FUN_00a64e10(obj): its cats are loaded
    "felyne_try_on_close": 0xA11C54,    # FUN_00a11c54(obj, 1): closes it
    "felyne_try_on_turn": 0xA26910,     # FUN_00a26910(obj, 1): the stick turns it, moves and zooms its camera
    "preview_frame_bind": 0x59E5D0,     # FUN_0059e5d0(frame): the preview's frame widget, bound once
    "preview_frame_show": 0x59F56C,     # FUN_0059f56c(frame, mode)
    "preview_frame_reset": 0x59E8F8,    # FUN_0059e8f8(frame)
}
GAME_SYMBOLS |= {
    "shell_manager_4u": 0xEF3CF0,       # the variable holding the shell manager
    "shell_create_4u": 0x660E88,        # FUN_00660e88(manager, n, record): uShell<n>
    "shell_launch_4u_001": 0x661BEC,    # (manager, owner, info, sub-kind, attack): uShell001
    "shell_launch_4u_005": 0x661D18,    # (manager, owner, pos, sub-kind, attack; scale in s0): uShell005
    "shell_launch_4u_008": 0x661E50,    # (manager, owner, sub-kind, vector): uShell008
    "shell_launch_4u_029": 0x66242C,    # (manager, a, owner, b, pos, area, attack): uShell029
}

# Alatreon's body effects (core/monsters/porting/sdk/enemy_4u.h enemy_effect_request): a monster's motion effect
# component (this+0xC78) plays the records of its two MEFs.
GAME_SYMBOLS |= {
    "mef_find_4u": 0x398F70,            # FUN_00398f70(mef, id): the record object (its record at +8), or 0
    "mef_play_4u": 0x391B50,            # FUN_00391b50(component, record, id): plays it as a motion event does
}

# The network session flag Alatreon reads (core/monsters/porting/sdk/enemy_4u.h quest_value_7d4): MH Generations keeps
# it in its quest manager (+0x7D4), MH4U in its game control.
GAME_SYMBOLS |= {
    "game_control_4u": 0xFB6B7C,        # the variable holding the game control (master_id +0x2F, host_id +0x2E)
    "game_online_4u": 0x2B5AC8,         # FUN_002b5ac8(control): its +0x5D, 0 or 1
}

# MH Generations' effect player, ported (core/monsters/porting/sdk/proof_api.h): the engine functions it calls, under
# the names its C uses (MH Generations': proof/gen_symbols.py).
GAME_SYMBOLS |= {
    "resource_add_ref": 0xBE2734,       # FUN_00be2734(resource): takes a reference
    "resource_release": 0xBE2768,       # FUN_00be2768(resource): drops one
    "mt_memcpy": 0x10ED68,              # FUN_0010ed68(dst, src, size)
    "mt_ceilf": 0xD131E8,               # FUN_00d131e8(s0): ceilf
    "mt_memset": 0x111DF8,              # __aeabi_memset(dst, size, byte)
    "mt_delete": 0x300B04,              # operator delete (one of its three copies)
    "mt_delete_array": 0x2FF4E8,        # operator delete[] (a copy of the same code)
    "mt_memclr": 0x2FF080,              # __aeabi_memclr(dst, size)
    "mt_memset_core": 0x10B920,         # where mt_memset goes on (identical code to MH Generations' 0x2F74B4)
    "mt_cs_enter": 0x10C064,            # a critical section entered
    "mt_cs_leave": 0x10C0C8,            # and left
    "system_init": 0x10724C,            # cSystem's constructor (identical code)
    "system_fini": 0x107288,            # cSystem's destructor (identical code)
    "mt_lock_all": 0x1057180,           # s8 that makes every cSystem lock (MH Generations 0xDB7BB8: both read it
                                        # as ldrsb next to the object's +0x10, 94 and 78 times)
    "mt_vec3_zero": 0x10E6378,          # (0, 0, 0, 0), written at start-up (the math constants block)
    "mt_vec3_one": 0x10E6388,           # (1, 1, 1, 0)
    "game_control": 0xFB6B7C,           # sGameControl (game_control_4u; MH Generations' *0xDA7F80: both hold the
                                        # current area, MH4U at +0xC90)
    "proof_default_color": 0x104DF94,   # a zero color word; MH Generations 0xDAE8E4 (22 readers each)
    "sunit_add": 0x64608C,              # FUN_0064608c(sUnit, line, unit, u64 group): a unit onto a line (0x894E74)
    "sunit": 0x10572F8,                 # the variable holding sUnit (MH Generations 0xDB7EA0)
    "mt_idivmod": 0x2FE210,             # __aeabi_idivmod (MH Generations 0x2F1DD8)
    "collision_ground": 0x2BA968,       # sCollision's ground query (MH Generations 0x2F8C38)
    "collision_manager": 0x10574FC,     # the variable holding sCollision (MH Generations 0xDB80A4)
    "mt_vec3_up": 0x10E63B8,            # (0, 1, 0, 0), written at start-up (MH Generations 0xE2F450)
    "mt_cosf": 0xD13278,                # cosf (MH Generations 0xB15B68)
    "mt_sinf": 0xD145AC,                # sinf (0xB17950)
    "mt_vec3_x": 0x10E63A8,             # (1, 0, 0, 0), written at start-up (0xE2F440)
    "mt_vec3_z": 0x10E63C8,             # (0, 0, 1, 0) (0xE2F460)
    "mt_quat_identity": 0x10E6568,      # (0, 0, 0, 1) (0xE2F600, past the constants block, at the same offset)
    "effect_on_joint": 0xB001F0,        # uEffect placed on a joint (0x9BF9C8)
    "effect_in_world": 0xB00270,        # in the world (0x9BFA4C)
    "effect_on_axis": 0xB003AC,         # the third placement (0x9BFB94)
    "effect_set_list": 0xAFD76C,        # its resource and element masks (0x9BD1F0, the same code)
    "property_add": 0x342A14,           # MtPropertyList's add (0x4402E0)
    "unit_create_property": 0x627518,   # cUnit's createProperty, slot 4 (0x878AE4)
    # the drawn effect
    "effect_init": 0xB00580,            # uEffect's constructor (0x9C0538)
    "effect_fini": 0xB005FC,            # uEffect's slot 0, its destructor (0x9C05B8)
    "effect_slot52": 0xAFC6F8,          # uEffect's slot 52 (0x9BC570)
    "effect_update": 0xAFCA0C,          # uEffect's slot 10 (0x9BFCB0)
    "unit_angles": 0x6D4708,            # a unit's rotation from three angles (0x94A384)
    "unit_set_matrix": 0x24BE24,        # a unit's rotation and position (0x274508)
    "gen_color_zero": 0x104DF90,        # a zero color word (0xDAE8E0; engine_pairs.json)
    "particle_generator_dti": 0x110C4F8,   # cParticleGenerator's DTI (0xE31028; the same initializer)
    "particle_node_dti": 0x110C7B8,     # cParticleNode's DTI (0xE31048)
    # the tied sounds
    "sound_control": 0xFCCD6C,          # the variable holding sSoundControl (0xDA9A48; engine_pairs.json)
    "sound_bank_get": 0x39D330,         # bank i of a sound set, i < 11 at +0x64 (0x639998: 14 at +0x60)
    "sound_queue_at_pos": 0x312100,     # a sound request queued at a position (0x3F52E8)
    "sound_queue_plain": 0x31218C,      # unplaced (0x3F53E8)
    "sound_queue_on_joint": 0x312200,   # on a unit's joint (0x3F5458)
}

# adapter, engine side (core/monsters/porting/effect_player/adapter_4u.c)
GAME_SYMBOLS |= {
    "resource_manager": 0x10572EC,      # the variable holding sResource (0xDB7E90); its load is slot 14, not 12
    "effect_list_dti": 0x10E75F0,       # rEffectList's DTI (0xE31288; the static initializer names it)
    "model_dti": 0x10E7530,             # rModel's DTI (0xE311E8)
    "mt_empty_string": 0xDF4FE0,        # the "" MtString::operator= loads (0xDE9A74; engine_pairs.json)
    "player_manager": 0xFB83E8,         # the variable holding sPlayer (0xDA5588; engine_pairs.json)
    "player_get": 0xAF9AB0,             # FUN_00af9ab0(sPlayer, i): hunter i, or 0 (0xAFED1C; engine_pairs.json)
    "proof_hunter_slots": 0x105729C,    # the variable holding sCamera, whose 8 slots of 0x1A8 bytes (0xDB7E18)
}

# adapter half 2, the monster side (core/monsters/porting/effect_player/monster_4u.c): what MH Generations' monster
# slots 39 and 40 do, MH4U's monster code calls directly
GAME_SYMBOLS |= {
    "enemy_hit_flags": 0x911D34,        # the ground query's last argument (slot 39, uFestaEnemy 0xAEF598)
    "enemy_hit_attr_flags": 0x91DFC0,   # its seventh (slot 40, uFestaEnemy 0xAEF77C)
}

# hook (core/monsters/porting/effect_player/hook_4u.c, proof_hook.py): the
# player's classes on MH4U's (their DTIs' parents, the base vtables their slots inherit), and the allocator
GAME_SYMBOLS |= {
    "mt_new": 0xD11E88,                 # operator new, nothrow (MH Generations 0xB1472C; engine_pairs.json)
    "dti_vtable": 0xE64D28,             # MtDTI's vtable, which its constructor 0x5BFABC writes (0xE06554)
    "object_dti": 0x10C1B0C,            # MtObject's DTI: cUnit's DTI's parent (MH Generations 0xE0AD68)
    "system_dti": 0x10E697C,            # cSystem's: sUnit's DTI's parent (0xE30024)
    "unit_dti": 0x10E699C,              # cUnit's, named by its initializer 0xD5ADB4 (0xE30044)
    "ueffect_dti": 0x10E7FB0,           # uEffect's, named by its initializer 0xD2E3C8 (0xE319C0)
    "unit_vtable": 0xE64E78,            # cUnit's, which its constructor (unit_init) writes (0xD6D7F8)
    "ueffect_vtable": 0xE6B990,         # uEffect's, 66 slots (0xD6F6B0)
    # a model's motion start (MH Generations 0x8A997C, "Slots
    "motion_start_4u": 0xB07B20,
                                        # 124 and 77"): its first instruction is hooked, proof_hook.MOTION_START
}

# The engine calls of core/monsters/porting/effect_player/drawn2.c
GAME_SYMBOLS |= {
    "unit_get_angles": 0xD00CC0,        # a unit's angles from its quaternion (MH Generations 0xAFAFE0)
    "effect_finish_step": 0x24EA98,     # uEffect's finish by its +0x118 (0x2771A8)
}

# The engine calls of core/monsters/porting/effect_player/drawn3.c
GAME_SYMBOLS |= {
    "effect_move": 0xAFFE6C,            # uEffect's slot 9 (MH Generations 0x9BF6A8)
    "effect_new": 0xB00624,             # uEffect's operator new (0x9C05E0)
    "sunit_add_like": 0x64605C,         # sunit_add with another unit's group (0x894E44)
}

# The engine's effects on his body (core/monsters/porting/effect_player/engine.c, the glue in hook_4u.c): what MH4U's
# enemy code calls where MH Generations' asks
# his body's PEL (the calls the glue stands in for), and the engine functions MH Generations' routines call, paired
GAME_SYMBOLS |= {
    "enemy_effects_4u": 0x919F38,       # the enemy update's effects (slot 48, the ground, the breath, MEF update)
    "enemy_status_effects_4u": 0x945418,    # the status effects (0x8DD300's place in the enemy update)
    "enemy_bomb_effect_4u": 0x934BDC,   # a bomb's hit (MH Generations' slot 203, 0x8CE66C)
    "mef_request_4u": 0x390F9C,         # FUN_00390f9c(component, id, s32): a record of the monster's MEF
    "mef_update_4u": 0x3933EC,          # FUN_003933ec(component): the motion effects of the frames just played
    "uchar_step_4u": 0xB07D60,          # uEnemy's slot 10 calls it after the enemy update (0x8A2124's place)
    "enemy_out_of_action": 0x94D7A8,    # MH Generations' slot 212 (0xAF0008; em050/pairs.py)
    "enemy_special_state": 0x95557C,    # 0x8F1D40 (the same constants)
    "enemy_positive_58e4": 0x9239FC,    # em+0x7A34 > 0 (0x8BD5D0, em+0x58E4 > 0: the same code)
    "enemy_positive_5978": 0x9306E4,    # em+0x7AC0 > 0 (0x8C9538, em+0x5978 > 0: the same code)
    "enemy_in_control_area": 0x94DEEC,  # mAreaNo is the game's (0x8EAFA8)
    "enemy_species_tuning": 0x93863C,   # the species' tuning record (0x8A1060; sdk/em_api.h)
    # his shells' PEL, list 2: a part's break (0x8DD0C8) and what it calls
    "enemy_break_4u": 0x944E80,         # (monster, part, x): MH4U's break routine (0x8DD0C8's place and code)
    "part_reward_4u": 0x6A8920,         # (quest, id, bit, 0, x): the quest's record of a broken part (0x8A5DA4)
    "quest_manager_4u": 0xFBEFFC,       # the variable holding the quest manager (MH Generations' *0xDA7134)
    "enemy_net_send": 0x917E84,         # (monster, 5, 2) after a reward (0x8B414C; em050/pairs.py)
}
# Shells, the hit records (part 1: core/monsters/porting/effect_player/shell_object.c, shell_4u.c): the hit records'
# constructors and destructor (em050/pairs.py SHELL_PAIRS
# "same" rows) and MH4U's uCoord, which the port's shell object stands on (its constructor writes the vtable 0xE65B14;
# slots 0 and 4 from it)
GAME_SYMBOLS |= {
    "hit_atk_init": 0xB70308,           # MhHitAtk's constructor (MH Generations 0x9C86FC)
    "hit_atk_fini": 0xB70404,           # its destructor, empty (0x9C8888 releases its rHitSize)
    "hit_body_init": 0xBDC318,          # MhHitBody's constructor (0xA0880C)
    "ucoord_init_4u": 0x6D4EDC,         # uCoord's constructor (MH Generations 0x94AB9C)
    "ucoord_fini_4u": 0x6D4FB0,         # its slot 0: b cUnit's (0x94AC70)
    "ucoord_create_property_4u": 0x6D3A30,  # its slot 4 (0x94974C)
    "ucoord_dti_4u": 0x10E78B0,         # its DTI (slot 5 0xD00CB4 returns it; MH Generations 0xE31520)
    "ucoord_vtable_4u": 0xE65B14,       # its vtable, 22 slots (0xD6E760)
}

# Shells, the hit records (part 2: core/monsters/porting/effect_player/shell_core.c, shell_4u.c): the hit records'
# functions the core calls (em050/pairs.py SHELL_PAIRS
# "same" rows) and MH4U's attack fill, which the fill adapter runs (SHELL_PAIRS hit_atk_fill_shell)
GAME_SYMBOLS |= {
    "hit_atk_push": 0xB700E4,           # MhHitAtk's slot 7 (MH Generations 0x9C80AC)
    "hit_body_push": 0xBDC1E4,          # MhHitBody's slot 7 (0xA0872C)
    "hit_body_setup": 0xBDC1F8,         # MhHitBody's setup (0xA08740)
    "hit_atk_fill_4u": 0xB700F8,        # (record, kind, owner, source, spheres, +8, +0x66): uShell's 0x9A9624's fill
}

# ==== shells: what MH Generations' shell bases 00, 01 and 11 call of the engine (engine_pairs.json and the shell pairs,
# em050/pairs.py SHELL_PAIRS) ====
GAME_SYMBOLS |= {
    "enemy_copy_joint_matrix": 0x930894,   # 0x8C96B8: a joint's world matrix (engine_pairs.json, verified)
    "bit_ref_copy": 0xD11F98,              # 0xB14824: a bit reference's copy (the same five instructions)
    "mt_mat_identity": 0x10E6448,          # 0xE2F4E0: the identity matrix, written at start-up
    "collision_ray_attr": 0x2B96E4,        # 0x2F6C38: a ray's hit attribute (engine_pairs.json, verified)
}
# ==== end of shell bases 00, 01 and 11 ====

# ==== shell bases 41 and 02 (core/monsters/porting/effect_player/shell_base41.c, shell_base02.c). Pairs of
# engine_pairs.json (verified), as its rows give them (the
# bit reference copy and the identity matrix are bit_ref_copy and mt_mat_identity above) ====
GAME_SYMBOLS |= {
    "enemy_copy_joint_matrix": 0x930894,    # a joint's world matrix copied (MH Generations 0x8C96B8; votes 6/7)
    "collision_ground_y": 0x2BAD24,         # the ground's height under a point (0x2F9354; votes 6/6)
    "sound_request_unit": 0x312484,         # a sound at a unit's position (0x3F5708; votes 5/5)
    # the owner's playing bank-0 sound moved to a point (0x3EDBF8: the same code; SHELL_PAIRS owner_sound_bank,
    # candidate: no species of both games calls it)
    "owner_sound_bank_play": 0x301074,
}
# ==== end of shell bases 41 and 02 ====
# Shells, the manager (core/monsters/porting/effect_player/shell_mgr.c):
# MtArray's DTI, whose allocator sShell's lists and base 11's float array take. Verified: the same static initializer,
# 0xB3C128 / 0xD43DC4, instruction for instruction ("MtArray", parent MtObject's DTI, size 0x14;
# tests/monsters/alatreon/test_alatreon_shell_classes.py), and each game hands nearly every load of it to the DTI's
# allocator getter (1183 of 1193 in MH Generations, 320 of 326 in MH4U)
GAME_SYMBOLS |= {
    "mt_array_dti": 0x10E65D4,          # MtArray's DTI (MH Generations 0xE2F6AC)
}
# ==== shells: what uShellEnemy and the shared helpers call of the engine (em050/pairs.py SHELL_PAIRS,
# engine_pairs.json) ====
GAME_SYMBOLS |= {
    "mt_acosf": 0xD12B58,                  # 0xB15448: acosf (SHELL_PAIRS acosf, same)
    "mt_atan2f": 0xD12DBC,                 # 0xB156AC: atan2f (engine_pairs.json, verified; inside matrix_to_euler)
    "mt_asinf": 0xD12C84,                  # 0xB15574: asinf (engine_pairs.json, verified; the same)
    "mtx_from_axes": 0xAAD40C,             # 0x9A7C40: a frame's matrix from its front and up (engine_pairs.json)
    "matrix_to_euler": 0xD076B0,           # 0xB0084C: a matrix's angles (engine_pairs.json; proof_math.TARGETS)
}
# ==== end of uShellEnemy and the helpers ====

# Mizutsune's state 2 (core/monsters/mizutsune/em082 state2*.c):
# the MH4U pairs em082/pairs.py GEN_ENGINE_PAIRS gives (MH Generations' address in the comment)
GAME_SYMBOLS |= {
    "enemy_set_action": 0x935AC8,       # 0x8CFA84: setAction(st, no, 2) unless dead
    "enemy_cmd_next": 0x9399C0,         # 0x8D2AA4: the command table chooses now (0x945E60, mode 1)
    "enemy_contact_angle": 0x9276B4,    # 0x8C0710: a collision contact's angle (0x943A18)
    "enemy_contact_find": 0x9128E4,     # 0x8B017C
    "enemy_ground_beyond": 0x924040,    # 0x8BDD20: the ground height at a point beyond an angle
    "enemy_turn_by_joint": 0x9446B4,    # 0x8DC768
}

# Mizutsune's class and action machine (core/monsters/mizutsune/em082, sdk/em_api.h and enemy_4u.h): the MH4U pairs
# em082/pairs.py GEN_ENGINE_PAIRS gives (MH Generations'
# address in the comment)
GAME_SYMBOLS |= {
    "uEnemy_step": 0x955E5C,            # uEnemy's slot 10 (0x8F22FC is uFestaEnemy's)
    "enemy_is_tired": 0x92E998,         # 0xAEF830
    "enemy_motion_at_frame": 0x941DBC,  # 0x8DA7A0
    "enemy_set_parts_vital": 0x93CFD4,  # 0x8D5DA8
    "enemy_flag_4c7_clear": 0x939090,   # 0x8D24CC
    "enemy_bits_5893_low": 0x940B50,    # 0x8D916C
    "enemy_drop_item": 0x911F58,        # 0x8CA1B8
    "area_ground_4u": 0x6C2888,         # (stage, area): the current area's ground height (0x8A5BC0 takes the area)
    "stage_4u": 0xFCF45C,               # the variable holding the stage object 0x6C2888 reads (MH Generations'
                                        # stage gimmicks, *0xDA9FB8)
    "enemy_motion_at_frame_1": 0x94A50C,    # 0x8E3304
    "enemy_landed": 0x93E4E8,           # 0x8D679C
    "enemy_joint_motion_delta": 0x936960,   # 0x8D0164
    "enemy_sleep_on": 0x91B130,         # 0x8D5724
    "enemy_sleep_off": 0x93C970,        # 0x8D56EC
    "enemy_sleep_start_4u": 0x93BAA8,   # 0x8D4830 takes his sleep's length from the DTP itself
    "enemy_sleep_heal_4u": 0x93BAC0,    # 0x8D4964 reads the period and the rate from the DTP itself
    "enemy_stamina_add": 0x91B7E8,      # 0x8B6BB4
}
# Mizutsune's attacks, state 7 part A
GAME_SYMBOLS |= {
    "enemy_play_motion_if_new": 0x920058,   # 0x8B4CB8 (MH XX's 0x8A6F64: his 1/0x14)
    "enemy_turn_by_joint": 0x9446B4,    # 0x8DC768
    "enemy_set_action": 0x935AC8,       # 0x8CFA84
    "enemy_set_end_flag": 0x927730,     # 0x8C0730
    "enemy_joint_motion_pos": 0xB06408,     # 0x8A9BC8
    "joint_set_quat": 0x960244,         # 0x954ECC
    "joint_update_matrix": 0x960F80,    # 0x955AAC
}
# Mizutsune's attacks, state 7 part B
GAME_SYMBOLS |= {
    "enemy_motion_started": 0x91AD14,   # 0x8B6050
    "enemy_turn_toward_over_frames": 0x93F1FC,  # 0x8C8C4C
    "enemy_turn_share": 0x92FBC4,       # 0x8C8CC4
    "enemy_angle_step": 0x91AB28,       # 0x8B5E88
}
# Mizutsune's state 3
GAME_SYMBOLS |= {
    "enemy_move_accel_turned": 0x9165CC,    # 0x8B29A0
    "enemy_rates_zero": 0x90E4D8,       # 0x8AD5A0
}
# The large bubbles' bind in the hunter's code (gameplay/bubbleblight/bubble_bind.s)
GAME_SYMBOLS |= {
    "hunter_motion": 0xB0C700,          # FUN_00b0c700(hunter, motion; s0 blend): plays a motion
    "hunter_motion_new": 0xB0C838,      # FUN_00b0c838(hunter, motion; s0): ... unless it is the one playing
    "hunter_act_start": 0xB23C98,       # FUN_00b23c98(hunter, act_st, act_no, flags): starts an action
    "hit_reaction_next": 0xB195E8,      # the hit's reaction block, 0xB195E4's second instruction (mov r0, r4)
    "hit_reaction_done": 0xB19690,      # ... the end of the hit's reaction: nothing started
    "slide_resume": 0xB12040,           # the act_st-6 dispatcher's exit (FUN_00b10edc), after the hooked 0xB1203C
    "hunter_is_local": 0xD04FBC,        # FUN_00d04fbc(hunter): the local player's hunter
    "vector_turn": 0xAAD5B0,            # FUN_00aad5b0(vec, angle): turns (x, z) of vec[0] / vec[2] by the angle
    "hunter_push": 0xB2A9B8,            # FUN_00b2a9b8(hunter; s0): the Snowman's push along the facing
    "hunter_dive": 0xB543AC,            # FUN_00b543ac(hunter): the dive (act_st 1, act 0xE), steps 0-3
    "glide_resume": 0xB545D4,           # the dive's epilogue (vpop {d8,d9}) after the hooked 0xB545D0 (add sp, 0x14)
    "hunter_is_snowman": 0xD06158,      # FUN_00d06158(hunter): in the Snowman (family A)
}

# Mizutsune's shells
GAME_SYMBOLS |= {
    "mt_new_array": 0xD11E20,           # 0xB146E8: operator new[] (std::nothrow, unread), the same 17 instructions
}

# New items (equipment/new_gear/item_obtained.s): the second instruction of the "ever obtained" bit's reader and writer,
# after the replaced first one
GAME_SYMBOLS |= {
    "item_get_body": 0xC1BEFC,          # FUN_00c1bef8(save, data, id)
    "item_set_body": 0xC1AC94,          # FUN_00c1ac90(save, data, id)
}

# Glavenus' launchers: the next serial number of a shell launch and the
# manager that counts them (MH Generations 0xA26078, 0xDA4178)
GAME_SYMBOLS |= {
    "global_next_serial": 0xBE9A0C,
    "global_serial_manager": 0xFB6FB8,
}

# Glavenus' states 2, 3, 6 and 8 (core/monsters/glavenus/em080/em080.h):
# engine functions of engine_pairs.json with an MH4U address, under the names his C uses
GAME_SYMBOLS |= {
    "enemy_set_action_0_7": 0x911AD0,           # 0x8AFAAC
    "enemy_hunter_in_reach_ahead": 0x912334,    # 0x8AFEF4
    "enemy_set_float_5c": 0x916140,             # 0x8B270C
    "enemy_hunter_check": 0x92B2E8,             # 0x8C475C
    "enemy_data_float_10": 0x93E7B4,            # 0x8D6BDC
    "enemy_data30_scaled": 0x9355C8,            # 0x8CF264
    "enemy_data_entry_4u": 0x91DF20,            # 0xAEDF50 (MH4U's record is *(result + 0x48))
    "enemy_snap_y_to_joint_status1": 0x94283C,  # 0x8DADC4
}

# Glavenus' states 9 and 13 (core/monsters/glavenus/em080/em080.h): engine
# functions of engine_pairs.json with an MH4U address, under the names his C uses
GAME_SYMBOLS |= {
    "enemy_camera_quake": 0x93E620,             # 0x8D6910
    "enemy_emset_mark_3": 0x948580,             # 0x8E0EA0
    "enemy_vital_add": 0x93BA30,                # 0x8D47D4
    "enemy_tired_add": 0x944C6C,                # 0x8DCE38
    "enemy_snap_to_ground": 0x942258,           # 0x8DAB48 (the rush and the flagged jump)
    "vec3_rotate_yaw": 0xAAD5B0,                # 0x9A7D98
}

# Glavenus' state 7, part B (core/monsters/glavenus/em080/em080.h): two
# engine functions of engine_pairs.json
GAME_SYMBOLS |= {
    "enemy_find_hunter_with": 0x918F70,         # 0x8B4BB0
    "enemy_homing_setup_packed": 0x935FC4,      # 0x8CFDEC
}

# Valstrax' four calls B1 marks "same" (core/monsters/valstrax/em086/pairs.py; each read in the update's code beside
# Generations' function in the comment: the same fields, the same callees)
GAME_SYMBOLS |= {
    "enemy_homing_setup": 0x916BCC,             # 0x8B2DB0: the homing slot's record addresses, then 0x92ED9C
    "enemy_hp_below_border": 0x90F9A0,          # 0x8AED00: mHpVital / mMaxHpVital <= the border rate
    "enemy_set_action_1": 0x91F744,             # 0x8B9B94: unless dead, setAction(st, no, 1, player) (0x90EFAC)
    "model_set_buffer_count": 0x957B84,         # 0x94C594: the model's array of 0x34-byte records, count at +0x234
}

# Three more of his "same" calls (phase D2, read in the update's code): slot 126's alpha, sound and em55d flag
GAME_SYMBOLS |= {
    "sound_request": 0x304C34,                  # 0x3EF4C4: owner (r4) + 0xD90 the sound bank, then the sound lookups
    "enemy_set_alpha": 0x90F7CC,                # 0x8AE474: two alpha floats at +0x7E78 / 0x7E7C (em+0xE28 data)
    "enemy_em55d_flag_80": 0x93A994,            # 0x8D3B74: 0x80 when the byte +0x629 (em+0xE28 data) is 1
}

# One more of his "same" calls (phase D7, research/engine_pairs/engine_pairs.json: verified, 13 of 13 votes): 7/0x30
# and 7/0x31 lower his drawn model by his base speed while in the air
GAME_SYMBOLS |= {
    "enemy_set_draw_ofs_y_by_size": 0x95542C,   # 0x8F1BF0: (this, y) draw_ofs.y (this+0xD14) = y x enemy_size_ratio
}

# Three more of his "same" calls (phase D3, read in the update's code): the motion state test and two turn tables
GAME_SYMBOLS |= {
    "motion_state_ended": 0xD02B48,             # 0xADF7DC: (state[+6] & 4) -> 1, else 0 (halfword here, byte in XX)
    "enemy_turn_table_start_1": 0x91DB5C,       # 0x8AAC3C: calls the turn-table start (0x92F420) with the extra arg 1
    "enemy_turn_table_step_1": 0x91DB7C,        # 0x8AAC5C: r2 = 1, then a tail call to the step (0x92F728)
}

# Valstrax' state 10 (phase D5, read in the update's code): layer 1's weight
GAME_SYMBOLS |= {
    "enemy_set_layer1_weight": 0xB054E0,        # 0x89A5B0: stores s0 at this+0x370+0x48 (+0x378 in XX)
}

# Valstrax' MH4U engine calls (phase G2e; each read in the update's code in Ghidra
# beside XX's function in the comment)
GAME_SYMBOLS |= {
    "mt_tanf": 0xD147B0,                        # 0xAFCCE0: tanf (s0), the shape of XX's, after sinf
    "enemy_aim_at_homing_point": 0x92FCBC,      # 0x8B7E20: (this, pitch step, yaw step) angle_step on em+0x1A8 / 0x1AC
    "enemy_camera_quake_roar": 0x93DEF0,        # 0x8C59A0: (this, entry, b): 0xC037BC(camera, this, kind 5 or 0x13)
    "enemy_camera_quake_end_5_13": 0x93DEB0,    # 0x8C5974: (this, now): ends the quakes of kinds 5 and 0x13
    "sound_stop": 0x2FFF74,                     # 0x3E828C: (manager, id, monster): the bank +0xD90's id, then the stop
    "enemy_get_hunter": 0x92C960,               # 0x8BE6A4: (this, kind, n): hunter n of the player manager, or 0
    "enemy_cat_comrade_pick": 0x92C90C,         # 0x8B89F0: (this, kind, n): the Palico of a target record, or 0
    "ground_query_4u": 0x2BA114,                # 0x895878 with sCollision first: (sCollision, this, top, bottom, area,
                                                # hit, a, flags, info) -> s0 the ground's height
    "enemy_timer_f20_reset": 0xB05184,          # 0x8A8E8C: this+0xD30 = 1.0 (this+0x1020 in XX)
}

# Valstrax' landing deafening (core/monsters/valstrax/em086/engine_4u.c), read in the update's code beside XX's in the
# comment
GAME_SYMBOLS |= {
    "sound_driver": 0x10572D4,                  # the variable holding the sound driver (XX *0xD3ED94 +0x18's): four
                                                # filter groups, 0x18 bytes from +0x9040: +0xC on, +0x10 type, +0x14 Hz
    "sound_layer_request": 0x307758,            # 0x3EAD80: (sSoundControl, layer, bank, id, owner) s0 the priority:
                                                # layer +0x20 + n * 0x14 fades in unless its priority is higher
    "sound_layer_stop": 0x2FAFC4,               # 0x3E43E0: (sSoundControl, code, bank, id, owner): codes 1, 3, 2, 4
                                                # fade layers 1-4 out when bank, id and owner match
    "sound_layer_volume_body_4u": 0x2FA198,     # 0x3E2BE8's pair (sSoundControl, layer) s0 -> s0, after its push
    "math_log10f_4u": 0xD13AA0, "math_powf_4u": 0xD13E38,   # s0 -> s0, (s0, s1) -> s0 (XX 0xAFB550, 0xAFC3B8)
}

# Valstrax's slot 175 and his wings' joint object (em086/engine_hooks_4u.c; "Fix: gaps from xx_not_ported")
GAME_SYMBOLS |= {
    "enemy_damage_part_store_4u": 0x920584,     # the damage function's store of a part's durability
    "enemy_damage_species_test_4u": 0x92053C,   # its Gogmazios test, after the load the hook replaces (0x920538)
    "joint_set_callback_4u": 0x95FAA4,          # XX 0x94D7A8: (joint, object)
    "enemy_joint_callback_4u": 0x91917C,        # uEnemy's joint object's update (this+0x8D30, joint, model): the bends
    "joint_callback_dti_4u": 0xD02710,          # that object's class's DTI (its slot 5)
}

# The game's code and data that the HUD, equipment and save sources once wrote as numbers (.equ / #define / .word):
# named here so their link keeps a relocation for them, which moves them to another game version
# (tests/game/executable/test_code_space_relocs.py refuses a raw address
# in a source)
GAME_SYMBOLS |= {
    "camera_control": 0x105729C,        # the variable holding sCamera (proof_hunter_slots); + 0xED5 the locked target
    "pad_control": 0x10572E0,           # the variable holding the pad object (+0x340 the GUI buttons held)
    "save_control": 0xFCF7EC,           # the variable holding the save object (its data starts 0x5C in)
    "gui_control": 0x1057534,           # the variable holding the GUI object (+ 0x100 the layout manager)
    # The looks message (equipment/layered/layered_online.c)
    "session_control": 0xFB82D0,        # the variable holding the session S (S + 0x87B8: the own slot)
    "session_send_all": 0x248A30,       # FUN_00248a30(S, buffer, size): to every other member, flags 0x10
    "session_send_to": 0x24A2A8,        # FUN_0024a2a8(S, member, buffer, size): to one member, flags 0x10
    "gear_send": 0x247F40,              # FUN_00247f40(S): "my gear changed" (type 0x15 kind 7), also applied to itself
    "game_online": 0x2B5AC8,            # FUN_002b5ac8(game manager): non-zero when networked
    "lobby_index": 0x24339C,            # FUN_0024339c(S, slot): the lobby index of a session slot (4 none)
    "quest_info": 0x2B3664,             # FUN_002b3664(game manager, player): a quest player's info
    "town_update": 0xA0050C,            # FUN_00a0050c(town): the hall's per-frame update
    "felyne_build": 0xC25A3C,           # FUN_00c25a3c(save, record, compact): a Felyne's record built from a compact
    "hall_cat_redress": 0xA47160,       # FUN_00a47160(scene, lobby index, compact): a hall cat takes its compact again
    "hall_cat_actor": 0x9FD790,         # FUN_009fd790(scene, 0, lobby index): the hall cat of that owner, or 0
    "net_receive_done": 0x2498A0,       # the end of FUN_002497d4, the game's message dispatcher
    "effect_control": 0x10572A4,        # the variable holding the effect manager (FUN_00b3f560 loads it)
    "effect_request_vtable": 0xE7F918,  # an effect request's vtable (the literal at 0xB3F95C)
    "hud_object": 0x108260C,            # the HUD object (bubble_icon.s)
    "intro_cutscenes": 0xF027B0,        # {u16 monster, u8 map, u8 area, ptr, ptr arc name}, ends with arc 0
    "equipment_control": 0xF3ED1C,      # the variable holding the equipment data object of the getters
    "lobby_hunter_loader": 0x109D8C4,   # the lobby's hunter model loader
    "preview_hunter": 0x109EB10,        # the variable holding the Smithy's preview hunter, once created
    "preview_mode": 0xEDBE90,           # the variable holding the preview's state: + 0x6C 1 / 2 while one is shown
    "menu_line_pictures": 0xE045B2,     # u8 per facility menu line (7: the cursor's copy): its first picture
    "menu_line_texts": 0xE045E6,        # ... and its first text pane
    "menu_lines": 0xDF2814,             # the facility menus' line table, 28 bytes a menu
    "armor_recipes": 0xF400FC,          # the game's create recipe tables (the literals of FUN_002f210c)
    "weapon_recipes": 0xF51DFC,
    "dpad_actions": 0xB3CC64,           # FUN_00b3cc64(hunter)
    "free_group": 0xB044F4,             # FUN_00b044f4(manager, index)
    "load_file": 0x2B51C0,              # FUN_002b51c0(loader, &handle, path, language, 0)
    "create_groups": 0xC0F474,          # FUN_00c0f474(gui, screen, first index, layout) -> groups
    "empty_name": 0xE06604,             # the empty name face_loader.s passes for a resource without one
    "layout_dti": 0x10E9058,            # the layout resource's type
    "ui_paths": 0xEFE17C,               # the quest list's GUI paths (+ 12 * 4: ui601's)
    "extra_layout_paths": 0xEFE1E8,     # the literal FUN_00c1017c loads at 0xC10430 (face_loader.s extra_layouts)
    "target_binder": 0x1085650,         # ui601's binder: panel00, panel01, target00
    # ui202's binder: ui202_tairyoku, the health bar (interface/hud/code_patch.HUD_REF)
    "health_binder": 0x1083EDC,
    "minimap_project": 0x6C40E0,        # FUN_006c40e0
    "minimap_area_zoom": 0x5A5F14,      # FUN_005a5f14(area, &zoom, offset): the zoomed area view's zoom and offset
    "minimap_area_point": 0x5A7BEC,     # FUN_005a7bec(point, area): the Everwood's fixed point of an area (whole map)
    "gui_popup_update": 0x5A805C,       # FUN_005a805c(): the GUI's per-frame update of its pop-up groups
    # equipment/mhgen/sound_number.s: FUN_0030d08c's `bhi` target (no sound path) and the instructions after its lookups
    "sound_skip": 0x30D740,
    "sound_bank_looked_up": 0x30D334,
    "sound_sf_looked_up": 0x30D3F4,
    # equipment/new_gear/new_weapons.s: the instruction after each stat lookup's replaced tail, melee then ranged, and
    # the ends of the upgrade, Insect Glaive
    # and sharpness lookups
    "weapon_back_m1": 0x2F2444, "weapon_back_m2": 0x2F3ED8, "weapon_back_m3": 0x2F78C4, "weapon_back_m4": 0x2F7B8C,
    "weapon_back_m5": 0x2F8AAC, "weapon_back_m6": 0x2F4634,
    "weapon_back_r1": 0x2F1758, "weapon_back_r2": 0x2F23E4, "weapon_back_r3": 0x2F3F4C, "weapon_back_r4": 0x2F43B8,
    "weapon_back_r5": 0x2F4480, "weapon_back_r6": 0x2F4564, "weapon_back_r8": 0x2F5DF0, "weapon_back_r9": 0x2F5EEC,
    "weapon_back_r10": 0x2F7880, "weapon_back_r11": 0x2F7BEC, "weapon_back_r12": 0x2F8AFC,
    "upgrade_lookup_done": 0x2F142C,    # FUN_002f1340: mov r0, r3; pop {r4, pc}
    "glaive_old_record": 0x2F4B0C,      # FUN_002f4ac0: the game's record of ids below 0x87
    "glaive_record_zero": 0x2F4B00,     # ... and its record 0
    "sharpness_lookup_done": 0x2F0FC8,  # FUN_002f0f34: pop {r4, r5, pc}
}

# The single-screen mode's blocks (interface/single_screen/executable/single_screen.py)
GAME_SYMBOLS |= {
    "gui_priority_resume": 0xAE63CC,    # FUN_00ae63c8(group, layer, priority): after its first instruction
    "gui_group_changed": 0xAE65B0,      # FUN_00ae65b0(group): +0x42 = 3, the revision bumped (after a change)
    "pad_update_body": 0x5B8284,        # FUN_005b8284(pad): the pad update's first call (0x694CE0)
    "prompt_owner": 0x109CDC8,          # ui006's owner: its ten groups, button kinds at +0x1F8, bound at +0x21F
    "prompt_binder_table": 0xDF9E8C,    # ui006's binder table (FUN_0058d75c): 12-byte entries, name hash first
    "creation_resume": 0xB74854,        # FUN_00B74748(scene, mode): after the goal target x load (hook 0xB74850)
    "creation_page_body": 0x22CEC4,     # FUN_0022cec4(owner, kind): the creation menu's page change (0x22CDB4)
    "gui_group_show": 0xAE53E0,         # FUN_00ae53e0(group, shown): shows or hides a GUI group (bit 0x400 of +0x44)
    "monster_hit_damage": 0x921F74,     # FUN_00921f74(uEnemy, region, total, flag): a hit's damage into the frame's
    "blast_damage": 0x9178E8,           # FUN_009178e8(uEnemy): a blast's damage into the region of the last blast hit
    "cursor_step": 0x5E70BC,            # FUN_005e70bc(cursor, count, pressed, prev, next): a cursor step
    "creation_cursor": 0x22B96C,        # FUN_0022b96c(owner, mode, pad, cells, columns): the creation menu's cursor
}

# The name keyboard's virtual finger (interface/single_screen/executable/single_screen_keyboard.s)
GAME_SYMBOLS |= {
    "keyboard_pointer": 0x104DEB4,      # the variable holding the embedded software keyboard (sSoftwareKeyboard)
    "keyboard_input_resume": 0x66766C,  # FUN_0066762c (the keyboard's input manager): after the touch x read (0x667668)
    "gui_named_group": 0x66C854,        # FUN_0066c854(list, name): the entry of a layout's list with that 16-byte name
    "keyboard_look": 0x67977C,          # FUN_0067977c(control, mode): a keyboard control's look (0 pressed, 2 released)
    "keyboard_key_update": 0x679D54,    # FUN_00679d54(control): slot 0x18 of the vtable of the key-like controls (the
    #                                     keys, the buttons, the text area; not the mode tabs nor the arrows)
    "keyboard_tab_update": 0x670A40,    # FUN_00670a40(control): slot 0x18 of the mode tabs' class (one colour pane)
    "keyboard_arrow_update": 0x67381C,  # FUN_0067381c(control): slot 0x18 of the page and suggestion arrows' class
    "keyboard_area_update": 0x678724,   # FUN_00678724(control): slot 0x18 of the suggestion words' class
    "keyboard_anim_play": 0x678DC4,     # FUN_00678dc4(control, animation): starts a control's press animation
    "keyboard_anim_rewind": 0x66A124,   # FUN_0066a124(control, animation): rewinds it to the idle pose (null-safe)
}

# The World Map on the pad (interface/single_screen/executable/single_screen_world_map.s)
GAME_SYMBOLS |= {
    "lobby_scene": 0xEDBE90,            # the variable holding the lobby scene object (the town menu, the world map)
    "lobby_town_active": 0xA40520,      # FUN_00a40520(): the hub's touch menu is up (the hunter free, no queued event)
    "lobby_town_busy": 0xA09ED4,        # FUN_00a09ed4(scene): the touch menu's buttons but the first are locked
    "lobby_click": 0x30013C,            # FUN_0030013c(sound control, sound): the touch buttons' click (0x8D)
}

# The players' box (interface/single_screen/executable/single_screen_players.c)
GAME_SYMBOLS |= {
    "members_refresh": 0xA6EEA0,        # FUN_00a6eea0(scene): fills the member list's four cards (hub state 0x14)
    "group_depth": 0x28BEAC,            # FUN_0028beac(group, 0xff): a group's shift for the touch bar (0xff: its place)
    "online_mode": 0x2B1040,            # FUN_002b1040(): the session's mode, 0 none, 1 local room, 2 online
}

# The touch-panel layout B on every save (interface/single_screen/executable/single_screen_panels.c): the saved panel
# record and the game's own write of layout A or B
GAME_SYMBOLS |= {
    "panel_record": 0xC1CC9C,           # FUN_00c1cc9c(save, index): the saved touch-panel record (16 bytes each from 0)
    "panel_layout_write": 0xC26754,     # FUN_00c26754(save, layout): record 0 as layout A (0) or B (1); r4 = layout
}

# The town minimap in a Gathering Hall (interface/single_screen/executable/single_screen_minimap_hall.c): what the hub
# machine calls to show the map (its state 1) and to
# hide it (on the way to 0x12 and 0x14)
GAME_SYMBOLS |= {
    "lobby_stage": 0x2B5AD8,            # FUN_002b5ad8(game): the lobby stage's kind (game + 0x2F8A; halls 3, 5, 7, 10)
    "town_map_show": 0xA407F8,          # FUN_00a407f8(scene): the map's five groups shown (and placed for kind 2)
    "town_map_place": 0xA13270,         # FUN_00a13270(scene, kind): the stage's map picture and its marks
    "town_map_label": 0xA136C0,         # FUN_00a136c0(scene, kind): the place name's balloon (ui421) and its word
    "town_map_icons": 0x9DABB8,         # FUN_009dabb8(scene, kind): the facilities' icons on the map
    "town_map_hide": 0xAAB4DC,          # FUN_00aab4dc(scene): the five hidden, the marks' animation stopped, ui420's
    #                                     second group hidden
}

# The Arena's pad (interface/single_screen/executable/single_screen_arena.c): the select scene's two calls the block
# stands in for (FUN_00654850's weapon choice calls them in turn
# each frame)
GAME_SYMBOLS |= {
    "arena_touch_original": 0x65178C,   # FUN_0065178c(scene): the touch list's results (+0x1B44 / 48 / 4C)
    "arena_pad_original": 0x650C44,     # FUN_00650c44(scene): the pad of the mode shown
}

# The game GUI engine (interface/game_gui/game_gui_engine.c): the
# vtables that tell a unit of sUnit's lines is a GUI manager (the uLayout family; interface/game_gui/structs.py
# MANAGER_VTABLES)
GAME_SYMBOLS |= {
    "ulayout_vtable": 0xE6BB40,                 # uLayout (DTI 0x10E9118)
    "ulayout_monnyan_vtable": 0xE60E14,         # uLayoutMonnyan: the Meownster Hunters' trip
    "uswkbd_layout_vtable": 0xE5EF3C,           # uSwkbdLayout: the software keyboard, a manager per key row
    "ulayout_scheduler_vtable": 0xE61D68,       # uLayoutScheduler
    "ulyt_anime_scheduler_vtable": 0xE62AC0,    # uLytAnimeScheduler
    "ulyt_message_scheduler_vtable": 0xE63520,  # uLytMessageScheduler
}

# The cheats (cheats/cheats.s): the engine's timing update, and MtGX's draw object (the variable
# holds it; FUN_00bfbb0c builds it, +0x6BA8 is the display mode word its last argument sets, +0x6BA4 the twin the
# display setup tests bit by bit)
GAME_SYMBOLS |= {
    "frame_update": 0x644320,           # FUN_00644320(app): the engine's timing update, once per frame (frame limiter)
    "gx_main": 0x10572CC,               # the variable holding MtGX's draw object
    "gui_projection": 0xB70FC0,         # FUN_00b70fc0(matrix): the GUI's 2D projection from s0, s1 (aspect_stub.s)
    # FUN_002f8f34(table, hunter, stat, flag): a stat of the hunter's equipment (6: the weapon's attack); insta_kill.c
    "hunter_gear_stat": 0x2F8F34,
}

# The options a player changes during play (interface/mod_settings/mod_options.c, mod_options_stub.s): where each hook
# goes back to (the instruction after the one it replaced), the bloom pass's body, and the weapon classes' table
GAME_SYMBOLS |= {
    "bloom_body": 0x2BC25C,             # FUN_002bc258 after its first instruction (push {r4-r11, lr})
    "fov_reset_return": 0xBFF448,       # FUN_00bff28c after its two loads of the field of view
    "fov_other_return": 0xC06C8C,       # FUN_00c06a14 after its load of the field of view
    "net_waits_return": 0x533F44,       # FUN_00533e6c after `cmp r2, #120`
    "net_polls_a_return": 0x534B58,     # FUN_005348a8 after `mov r0, #10`
    "net_polls_b_return": 0x5356E0,     # FUN_00535480 after `mov r0, #10`
    "raw_a_return": 0x26E394,           # FUN_0026e33c after its load of the weapon classes' table
    "raw_b_return": 0x27336C,           # FUN_0027335c after its load of the table
    "camera_cap_return": 0xBFD170,      # FUN_00bfd028 after its load of the turn's cap (10.0)
    "box_lines_return": 0x9EC8A8,       # FUN_009ec82c after its store of the box menu's count of lines
    "keyboard_poll_body": 0x2B58EC,     # FUN_002b58e8 (the poll of the game's keyboard) after its first instruction
}

# The system keyboard (interface/system_keyboard/system_keyboard.c): the SDK's calls of a library applet, as the game
# makes them for the Circle Pad Pro's (FUN_00578ee0), and the eShop applet's static buffer (FUN_00476b68, its only user)
GAME_SYMBOLS |= {
    "apt_prepare_library_applet": 0x56F340,  # FUN_0056f340(applet): PrepareToStartLibraryApplet, retried while busy
    "apt_start_library_applet": 0x56EA78,    # FUN_0056ea78(applet, parameter, size, handle): StartLibraryApplet
    "apt_receive_parameter": 0x10AB9C,       # FUN_0010ab9c: waits for the applet's answer (its parameter)
    "svc_create_memory_block": 0x111864,     # FUN_00111864(&handle, address, size, own, other): svc 0x1E
    "memory_block_close": 0x47EFF4,          # FUN_0047eff4(block): closes the SDK's memory block
    "applet_wait_time": 0x1057558,           # u64: the wait FUN_00578ee0 hands FUN_0010ab9c
    "eshop_applet_buffer": 0x10FA000,        # the eShop applet's parameter (page 0) and shared memory (from 0x1000)
    "class_multipliers": 0xED24A0,      # the weapon classes' display multipliers, in percent (16 words)
}

# The START menu's Mod Settings (interface/mod_settings/mod_settings_stub.s, mod_settings.c; docs/interface/
# mod_settings.md): the game's list widgets and where the hooks go back to. It also uses pane_redraw, facility_help,
# sound_play, sound_control, game_main, gui_control, text_slot and text_common, declared elsewhere
GAME_SYMBOLS |= {
    "start_pick_sound": 0x5F746C,       # FUN_005f6c8c: the decide sound (sound in r5) of an action past its table
    "start_help_body": 0x60FC30,        # FUN_0060fc2c: after its first instruction
    "start_subscreen": 0x607910,        # FUN_00607910(menu): the frame of the game's sub-screens
    "start_list_ui": 0x108F608,         # the object binding the START menu's list widgets (ui020)
    "start_page_numbers": 0x608028,     # FUN_00608028(): the menu's "page/pages" in its title bar, from +0x10, +0x11
    "start_list_group": 0xD94358,       # FUN_00d94358(binder, group, shown): marks a widget group (+0x50, a bit each)
    "start_sublist_begin": 0x611B10,    # FUN_00611b10(): what the game's small lists do before opening
    "start_top_cursor": 0x6201DC,       # FUN_006201dc(shown): the page's cursor runs or stops
    "start_sublist_open": 0x5E87B4,     # FUN_005e87b4(action, rows): opens the small list beside the line of the action
    "start_sublist_text": 0x60FBC0,     # FUN_0060fbc0(row, 0, file, message): a row's text
    "start_sublist_cursor": 0x5E84F0,   # FUN_005e84f0(row): moves the cursor and steps its animation, once per frame
    "start_sublist_close": 0x5E86B0,    # FUN_005e86b0(): closes the small list and restores its colours
    "start_sublist_end": 0x60F220,      # FUN_0060f220(): after the small list closes
    "start_step": 0x5E70BC,             # FUN_005e70bc(value, count, keys, minus, plus): steps and wraps, move sound
    "start_help_show": 0x2A4260,        # FUN_002a4260(1, 0xB): shows the description's frame
    "gui_ref_next": 0xD03820,           # FUN_00d03820(&next, &ref): the pane ref after a text pane's
    "gui_anim_bind": 0x585094,          # FUN_00585094(&pane ref, animation, owner, 0): binds a cursor's animation
    "gui_anim_step": 0xAE1DDC,          # FUN_00ae1ddc(animation, s0 the frame's time)
    "start_pager_bind": 0x5EDCF4,       # FUN_005edcf4(x, y): binds the big lists' pager, a counted bind
    "start_pager_release": 0x5EDC88,    # FUN_005edc88(): ends one bind
    "start_pager_show": 0x5ED704,       # FUN_005ed704(page, pages, 0, 0, 1): one frame of "page/pages"; 1 page, nothing
    "start_pager_hide": 0x5EDCBC,       # FUN_005edcbc(): hides the pager's panes
    "text_set": 0xAE4EF0,               # FUN_00ae4ef0(pane, group, text, length, format): 0, 0 blanks a text pane
    "common_files": 0x109A080,          # the table of the common message files, by file number
    "message_string": 0xCDFA80,         # FUN_00cdfa80(file's table, message): the string entry of its first node
}

# The Caravan's quest girl (interface/quest_counter/executable/quest_counter.s)
GAME_SYMBOLS |= {
    "npc_talk": 0x9E29D8,               # FUN_009e29d8(scene, talk, table): starts an NPC's talk
}

# The area move watchdog (monsters/routes/area_move_watch.s): the engine's own crossing
# into the next area when a monster walks to an exit, the position of an entry point, the area change (mode in r1), and
# the end of the action
GAME_SYMBOLS |= {
    "area_cross": 0x930264,             # FUN_00930264(monster): at its exit, the next area's entry point, area changed
    "point_position": 0x936894,         # FUN_00936894(monster, area << 8 | position, out): its position in an area
    "change_area": 0x918A30,            # FUN_00918a30(monster, mode): mAreaNo = mNextArea, the move's state reset
    "action_end": 0x927730,             # FUN_00927730(monster, 0): the action is over (em+0x1DC = 1)
    "script_return": 0x918454,          # FUN_00918454(monster): returns from the script running (one frame popped)
}

# Great Maccao's calls that have an MH4U function of the same code (core/monsters/great_maccao/em085/pairs.py
# `mh4u_names`, the "same" and "like" rows): what
# `research/porting/gen_difftest.py --link-mh4u` links the C against. The XX address is in the comment; uCnsTinyChain is
# the chain of cloth-like joints (Gogmazios and Great Maccao have one: this+0xB788 in XX, em+0x7B00 in MH4U). Two rows
# are candidates in the pairs (XX -> Generations not verified): the last two of the group below
GAME_SYMBOLS |= {
    "tiny_chain_release": 0x2503C0,     # 0x2545F4: uCnsTinyChain's slot 16 (release)
    "tiny_chain_node": 0x31F724,        # 0x3FDF14: node n (this+0xA0)[n], 12 bytes
    "tiny_chain_set_resource": 0x32083C,    # 0x3FEE34: the chain's resource set (MH4U calls it at 0x9312A0)
    "tiny_chain_move": 0x320D38,        # 0x3FF318: slot 9 of its vtable
    "tiny_chain_set_flag_310": 0x32165C,    # 0x3FFC44: this+0x310 = 1
    "tiny_chain_construct": 0x3219D4,   # 0x3FFFB0: the constructor
    "tiny_chain_destruct": 0x321DA0,    # 0x400378: slot 0 of its vtable, the destructor
    "tiny_chain_update": 0xC28A80,      # 0xA20228: slot 24 of its vtable (MH4U calls it at 0x955EB0)
    "enemy_mgr_spawn_units": 0x68251C,  # 0x1C7568: (sEnemy, set id, id, variant, [sp] area, b, now, total, flags, c,
    # position, rotation): wakes up to min(now, total - alive) of the quest's waiting small monsters
    "model_set_motion_speed": 0xB06624,     # 0x1E38D0: (model, float speed) stored at +0x29C (XX +0x2A4)
    "enemy_ceiling_clamp": 0x9236FC,    # 0x8AF95C: (this, float margin): 1 when mPos.y was clamped under the ceiling
    "gen_area_ground": 0x6C2888,        # 0x894F98: Mizutsune's area_ground_4u (the same function; XX's is a thunk)
    "enemy_tuning_table18_entry": 0x92C850,     # 0x88F8B0: (this, i): &tuning->table[i], 16-byte entries (candidate)
    "enemy_base_release": 0x94CCDC,     # 0x8DCFBC: uEnemy's slot 16 (release), which his release calls (candidate)
    # Phase G2: the G rank test of his break thresholds. XX's quest_rank(*sQuest) is 0xAD9604; MH4U's gives the quest's
    # monster rank on *quest_manager_4u (1 low, 3 high, 5 G, 6 G apex)
    "quest_rank_4u": 0x69AE70,
}

# Maccao's calls whose MH4U function phase G2 linked (core/monsters/maccao/ems046/pairs.py ENGINE_PAIRS, the MH4U
# side of research/engine_pairs/engine_pairs.json: verified, but enemy_em5883_set_1 and enemy_homing_setup, candidates).
# The XX address is in the comment
GAME_SYMBOLS |= {
    "enemy_mgr_species_kind": 0x6834B4,     # 0x1C2FA0: (sEnemy, id, sub type) -> the species' kind
    "enemy_mgr_kind_record": 0x683590,      # 0x1C3084: (sEnemy, kind, variant) -> its 0x50-byte record, or 0
    "enemy_set_action_1": 0x91F744,         # 0x8AC0A4: setAction(st, no, 1, player) unless dead (state 11)
    "enemy_restart_flag_clear": 0x932EE4,   # 0x8BBD60: (this, 0): em+0x1DC = 0
    "enemy_em5883_set_1": 0x922090,         # 0x8AEAE0: em+0x7984 = 1 once, and notice 3 to sEnemy
    "enemy_em5883_set_2": 0x9150FC,         # 0x8A3A78: em+0x7984 = 2 (none for the ids of rocks and objects)
    "enemy_em58e4_positive": 0x9239FC,      # 0x8AFDC8: em+0x7A34 > 0 (enemy_positive_58e4)
    "enemy_em588c_set": 0x91B0C8,           # 0x8A878C: (this, a, b) into em+0x79AF / 0x79B0 (XX's 4th: unread)
    "enemy_set_alpha": 0x90F7CC,            # 0x8A036C: (this, s0 target, s1 speed) into em+0x7E78, 0x7E7C, 0x7E74
    "enemy_homing_setup": 0x916BCC,         # 0x8A4F44: (this, kind, a, b, slot): homing target `slot`'s setup
    "game_random_4u": 0x2B568C,             # 0x2C8FCC's adapter: (sGameControl, stream) -> a random u16
    "gen_wake_manager": 0xF32004,           # 0xD2CAA0: sEnemy's pointer (monster_data_manager), enemy_gen.h's name
    # His leader's pack in MH4U (porting/sdk/pack.h)
    "enemy_is_live": 0x9124F0,              # (uEnemy): non-zero for a live monster, FUN_0068239c's test of sEnemy's 32
    "enemy_mgr_records": 0x10B04F0,         # sEnemy's 0x80 records of 0x80 bytes: the quest's monsters, waiting or not
    "enemy_hit_linked": 0xB6FCA8,           # (hit, victim): 1 when the victim is the attacker's linked monster
                                            # (em+0x78E8), the victims' loop's test before a monster is hit ("Phase P2")
}

# The ported monsters' severed tail (gameplay/tail_fall/tail_fall.c):
# the cut piece's state machine and its angles-to-quaternion step, which slot 10 of the piece's class (FUN_00c2f9e8)
# calls, and the piece's record
GAME_SYMBOLS |= {
    "piece_step": 0xC2D364,             # FUN_00c2d364(piece, monster, flag): the cut piece's state machine
    "piece_angles": 0xB059F0,           # FUN_00b059f0(unit): the unit's quaternion (+0x50) from its angles (+0xD20)
    "piece_record": 0x94C45C,           # FUN_0094c45c(monster, flag): the piece's record in the monster's emd, or 0
}

# Holding A repeats it (gameplay/hold_a/hold_a.c): the hunter's item mode call, the quest
# result scene and the Wyporium's claim panel (hunter_is_local, above, tells the hunter this console plays)
GAME_SYMBOLS |= {
    "hunter_item_mode": 0xB28F54,       # FUN_00b28f54(hunter): item mode (L held), called by the hunter's input update
    "result_scene": 0xACCD24,           # FUN_00accd24(scene, ?, ?): the quest result scene, once per frame
    "claim_scene": 0x5E5CB8,            # FUN_005e5cb8(panel): the Wyporium's claim items panel, once per frame
}

# Select and Start follow the game's option START (gameplay/select_kick/select_kick.c): the SDK's Select-to-Start step,
# the settings byte reader and the Game Menu's object
GAME_SYMBOLS |= {
    "sdk_select_to_start": 0x571E58,    # FUN_00571e58(status): Select becomes Start in the 3DS pad status
    "hid_select_to_start": 0x571E4C,    # FUN_00571e4c(status): the same, held at +0 (the path without an extra pad)
    "game_setting": 0x2B02FC,           # FUN_002b02fc(settings, index): the settings byte `index`
    "start_menu": 0x108B9BC,            # the Game Menu's object (FUN_0012580c returns it)
}

# START skips a slain monster's death camera (gameplay/death_camera_skip/death_camera_skip.c)
GAME_SYMBOLS |= {
    "camera_play": 0xC03D70,            # FUN_00c03d70(manager, slot, n): one frame of an event camera, 0 when over
}

# Astalos' MH4U engine calls whose function is the same code (phase G2n; the comment
# holds the MH XX address; each pair is a verified row of em081/pairs.py, engine_pairs.json, and the bytes the test of
# tests/monsters/astalos/test_astalos_pairs.py reads)
GAME_SYMBOLS |= {
    "enemy_set_action_kept": 0x92B178,  # 0x8B3820: (this, act_st, act_no): the set action unless mActSt is 0xB
    # 0x8A4840: (this, v): em+0x180 += v x unit_delta, then em+0x1C7 = 1 (em+0x5C, 0x1B9 in XX)
    "enemy_height_step": 0x915D7C,
    # 0x8A6E38: (this): layer 1's weight 0 and the floats em+0x394.. zeroed (em+0x308.. in XX)
    "enemy_clear_em_308": 0x918F28,
    # 0x89A65C: (model, joint, m[16]): the joint record's quaternion from the matrix, +0x58 (+0x60 in XX)
    "model_joint_set_mtx": 0xB05754,
    "enemy_move_turned_land": 0x9165A4,  # 0x8A4AFC: (this, s0): enemy_move_by_rate_turned, then enemy_ground_landed
    # 0x8A6DA0: (this, target, step): em+0x394 toward target by step x unit_delta, clamped to -1..1
    "enemy_approach_f308": 0x918E80,
    "enemy_play_motion_layered": 0x919058,  # 0x8A6F0C: a motion on layer 0 and layer 1 (engine_pairs.json)
    "enemy_motion_no_is": 0x91B250,  # 0x8A8898: (this, no): the motion number is `no`
    "enemy_em4c1_set_2": 0x91B268,  # 0x8A88B0: (this): the byte em+0x539 = 2 (em+0x4C1 in XX)
    # 0x8B673C: (this, max, min, speed): the distance to the homing point / speed, clamped
    "enemy_homing_frames_clamped": 0x92E440,
    # 0x8B68A4: (this, flags): re-picks the route point by his facing every n calls
    "enemy_pick_route_point_by_yaw": 0x92E530,
    # 0x8BD78C: (this, step, offset, point): 1 when facing the point plus offset, after turning
    "enemy_turn_to_point": 0x934AC8,
    # 0x8BF178: (this, motion+, motion-, f, sign): layer 1's motion by em+0x394
    "enemy_play_layer1_motion_by_f308": 0x935FF0,
    "enemy_homing_run_start": 0x938780,  # 0x8C0B4C: (this, rec): plays the record's motion and saves mPos
    # 0x8C0BF8: (this, rec, r2): runs toward the homing point, its layer motions blended
    "enemy_homing_run_step": 0x93886C,
    # 0x8C2E68: (this, fixed, out[4], kind, ...): the position to home on by the homing kind
    "enemy_homing_target_pos": 0x93AAB4,
    # 0x8C5E28: (this, now): stops the quake when the homing hunter 0 is the local player
    "enemy_camera_quake_stop": 0x93E590,
    "enemy_set_timer_310": 0x9427FC,  # 0x8CB244: (this, n, f): layer 1's weight 0, then em+0x39C = n
    # 0x8CD098: a vector turned by his joint's delta (0x936960) added to his position
    "enemy_move_by_turned_vector": 0x94461C,
    # 0x8D1024: (this): the factor em+0x404 = 1.0 and a second factor = 1.0 (em+0x7908)
    "enemy_reset_factors": 0x947258,
    # 0x8DE50C: (this, s16 angle, step, clamp): angle + step x unit_delta, kept within -0x3F49..0x4000
    "enemy_angle_add_scaled_clamp": 0x94D73C,
    "enemy_set_draw_ofs_scaled": 0x94E358,  # 0x8DE7E0: (this, v): draw offset (em+0xD10) = v x enemy_size_ratio, w = 0
    # 0x8E58E0: (this, step): mPos.y toward the homing point's y by step, or onto it when closer
    "enemy_approach_homing_y": 0x955A94,
    # two names of an address already named above or by Valstrax's phase G2e
    "mt_powf": 0xD13E38,                        # 0xAFC3B8: math_powf_4u's address, the name his C and the table use
    "em081_move_turned_ground": 0x91B468,       # 0x8A8EDC: enemy_move_turned_at's address (D14's second name: it
                                                # returns the ground clamp's result, the dive tests it)
    # the shells' bases 14 and 15 (effect_player/gen_symbols.py PENDING_4U's three found here: the same instructions)
    "mt_atanf": 0xD1302C,                       # 0xAFAAE8: atanf (s0), XX's blocks in the same order, same constants
    "random_init": 0xB72354,                    # 0x9924F4: (generator, seed): the xorshift's four words, 100 steps;
                                                # XX's instructions with two registers swapped
    "random_next": 0xB723EC,                    # 0x9924B8: (generator): its next 32 bits, the same fifteen words
    # an adapter's callee (stage_area_position, 0x895240: em081.h)
    "stage_area_position_4u": 0x6C3AF8,         # (sStage, area, out[4]): the area's x, y, z (s16 at sStage+0x166 + 24 x
                                                # the area number) as floats; the adapter sets out[3] = 0
    # phase G2e (em081/engine_4u.c): a joint's matrix his slots call directly, and the line check's callee
    "festachar_joint_matrix": 0xB052EC,         # 0x1E32B0: (out, model, joint) the joint's 4x4 matrix from its record's
                                                # quaternion and translation; XX's adds a warning call, MH4U's records
                                                # are 0xA8 bytes (XX 0xA0)
    "collision_line_4u": 0x2B9CD4,              # 0x2CF17C: (sCollision, this, from, to, area, out, normal, record, b),
                                                # s0 the radius; XX's two virtual calls on `this` are direct uEnemy
                                                # calls (0x911D34, 0x91DFC0); its Rathian calls it at 0x6D6034
}

# The C-stick turns the camera analogically (gameplay/modern_camera/modern_camera.c)
GAME_SYMBOLS |= {
    "camera_turn_by_input": 0xBFD028,   # FUN_00bfd028(camera, input, flags): sMhCamera::turnByInput, the turn by
    #                                     the camera's buttons; 0xFF no button, 0 the pitch turned, 1 the yaw
    "is_gunner": 0xD04DD4,              # FUN_00d04dd4(hunter, kind): the weapon is a bowgun (kind 0), ranged (1), the
    #                                     Bow (2)
    "aim_speed": 0xB3FE50,              # FUN_00b3fe50(hunter, kind): the Aim Speed option's factor (a float in s0) for
    #                                     the scope (0), over the shoulder (1), the Bow (2)
    "camera_zoom": 0xC00038,            # FUN_00c00038(camera, &zooming, &zoom): the scope's zoom, 0 to 1 (the widest)
    "aim_pitch_view": 0xB1EA04,         # FUN_00b1ea04(hunter, pitch, up, down): the aim's pitch angle (weapon work +
    #                                     0x50E) from its pitch steps; up, down (s0, s1) the degrees of 100 steps
}

# START does what the touch screen's Skip does (gameplay/intro_skip/intro_skip.c): the
# touch menu bar, its Skip button's handler, the skip checks and calls the handler makes; the calls that stop a
# skipped cutscene's music and sounds
GAME_SYMBOLS |= {
    "touch_bar": 0x109A350,             # the touch menu bar's object (ui002; + 0xCF which skip its Skip button makes)
    "touch_bar_button": 0x292EA4,       # FUN_00292ea4(position, button, kind): a bar button's frame (kind 7, 8, 9, 0xB)
    "event_control": 0xFB5EDC,          # the variable holding the event player (cutscenes)
    "event_skip_offered": 0x1A1CB8,     # FUN_001a1cb8(event): a cutscene plays and the player may skip it
    "event_skip": 0x1A2D4C,             # FUN_001a2d4c(event): asks the event player to skip (70 frames or more left)
    "camera_skip_offered": 0xD0CCB4,    # FUN_00d0ccb4(sCamera): an event camera the player may skip plays
    "camera_skip": 0xBFD3F0,            # FUN_00bfd3f0(sCamera): ends it
    "cutscene_sound_stop": 0x30CB5C,    # FUN_0030cb5c(sound control): a skipped event's sound: fades the event
    #                                     players' streams out (by their records), stops the sounds
    "event_sound_end": 0x30CD10,        # FUN_0030cd10(sound control): the sound control's part of an event's end
    "sound_fade_out": 0xBCAC00,         # FUN_00bcac00(driver, queue, request, set, fade, 0): fades a stream out
}

# The split title's RomFS (install/title/split_romfs.c, split_romfs_stub.s): the SDK's pieces of a RomFS mount, as the
# update's FUN_00108930 mounts `patch:`, the running title's id, and
# nn::fs::FileStream::TryInitialize
GAME_SYMBOLS |= {
    "fs_mount_rom": 0x108930,           # FUN_00108930(max_files, max_dirs): mounts `rom:` once (the update: `patch:`)
    "svc_get_process_info": 0x1091D8,   # FUN_001091d8(&out, process, type): svc 0x2B, the 64-bit answer in *out
    "fs_open_file_directly": 0x10DB9C,  # FUN_0010db9c(&session, &handle, 0, archive, its path's type, path, size, the
    #                                     file path's type, path, size, flags, attributes): FS:OpenFileDirectly
    "fs_user_session": 0x1057D98,       # the FS:USER session's handle (FUN_0010b974 and FUN_0010d9ac pass its address)
    "svc_close_handle": 0x11185C,       # FUN_0011185c(handle): svc 0x23
    "romfs_work_size": 0x10B974,        # FUN_0010b974(max_files, max_dirs, use_cache, path): a RomFS mount's buffer
    "memory_clear": 0x10B91C,           # FUN_0010b91c(address, size): zeroes
    "romfs_archive_open": 0x10D9AC,     # FUN_0010d9ac(&archive, max_files, max_dirs, buffer, size, use_cache, path)
    "fs_register_mount": 0x10BC10,      # FUN_0010bc10(name, archive, 0, 0): a drive in the SDK's 32 mounts, <0 if taken
    "default_allocator": 0x10BDC88,     # the variable holding the SDK's default allocator (+0x20 allocate, +0x38 free)
    "file_stream_open_body": 0x10BAFC,  # nn::fs::FileStream::TryInitialize (FUN_0010baf8) after its first instruction
    "fs_is_not_found": 0xDC0AD8,        # FUN_00dc0ad8(result): an FS "not found" (module 17, descriptions 100-179)
}

# The Hunting Horn's songs (interface/horn_songs/horn_songs.c): the
# tables the equipment menu's list (FUN_00277e68) and the notes' match (FUN_00cbab58) read, and the HUD's note pictures
GAME_SYMBOLS |= {
    "horn_song_notes": 0xF31E3A,        # u8[75][4]: each song's notes, newest first, 0 none (FUN_00cbab58)
    "horn_note_triplets": 0xF31DA4,     # u8[50][3]: a horn's three notes by its note set (work +0x16C; FUN_00cbd81c)
    "horn_song_names": 0xED256A,        # u8[75]: a song's name index (FUN_00277e68 at 0x278120)
    "horn_name_messages": 0xED2858,     # u32[]: a name index's message of the Menu file (common file 3)
    "hud_note_cells": 0xB90EFC,         # u8[9]: a note's cell in the HUD's picture (FUN_00b8f58c's literal)
}
