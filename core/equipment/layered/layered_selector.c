/* Layered gear at the Smithy (option layered_equipment): the entry and the render.
 *
 * The Smithy's menu (FUN_009ad59c, state byte at obj + 0xB708) gets a last line, "Layered Gear", in the game's own tables
 * (equipment/layered/layered_equipment.py). Choosing it puts the Smithy in state 3, which the game never uses, and from
 * then on layered_update() runs every frame in its place:
 *   entry:  [Weapons] [Armor] ([Felyne]) [Relics]   the lobby's facility menu (lyt\lobby\ui401, drawn by FUN_00a528e0
 *                                            from per-menu tables): this block adds menu 18, whose lines are layered_ui.lines
 *   Weapons -> the game's weapon class menus (6, 7) -> the forge screen of that class
 *   Armor   -> the forge screen of armor
 *   Felyne  -> nobody active: a buzzer; one: the forge screen; two: their names on menu 18, then the forge screen
 *   Relics  -> [Weapons] [Armor] on menu 18 -> as the entry's, screens of the relics alone (layered_ui.relics)
 * B goes back a level, and from the entry to the Smithy's menu. The forge-style screens are layered_forge.c.
 *
 * Hooks (ARM, below; the patcher points the game at them):
 *   layered_menu_count     0xA52920  "ldrb r0, [r1, r0]": the lines of a menu
 *   layered_menu_lines     0xA52C54  "ldr r0, =0xDF2814": the (file, message) table of the menus
 *   layered_text_kind      0xA52C70  "cmp r1, #3": Z for common message files (ours: 0x100 | file)
 *   layered_menu_drawn     0xA52D98  "ldrb r0, [r6, #0x1AC]": the menu drawn, at the end of its drawing (the page
 *                                    bar of menus 6, 7: hidden on the screens' class menus; the cats' names)
 *   layered_smithy_pick    0x9AD890  "ldrh r0, [r4, #0x24]": the Smithy menu's chosen line, ours -> 6
 *   layered_smithy_open    0x9AD89C  "b 0x9AE280": the default case of the Smithy menu's choices
 *   layered_smithy_update  0x9AD674  word of the Smithy's state jump table, state 3
 *   layered_smithy_desc    0x9AE2FC  "ldrh r2, [r0]": the description of the highlighted line
 *
 * The looks worn: the game's calls of the model getters
 * FUN_002f4258 (armor) and FUN_002f0fd4 (weapon) for a hunter go to stubs that note the hunter's status (and
 * the armor part) and then to layered_armor_model / layered_weapon_model, which give the local hunter the look
 * of layered_state, and the Smithy's preview hunter what it tries on (layered_preview); the
 * quest preloader's calls go to layered_armor_preload / layered_weapon_preload (the player's info, not a
 * hunter). layered_save_store puts layered_state into the save file's buffer (+ SAVE_AT) and layered_save_load
 * takes it out of a loaded save and clears it there: the game's save data in memory never holds it.
 * Places: GAME_CALLS in equipment/layered/layered_equipment.py.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with layered_selector.ld where it places the
 * block).
 */

#include "layered.h"

GAME u32 menu_cursor_init(u32 obj, void *cursor, u32 count, u32 rows, u32 disabled, u32 a_sound, u32 v_sound,
                          u32 h_sound);                                /* FUN_009bc954 */
GAME u32 menu_cursor_update(u32 obj, void *cursor, u32 extra);         /* FUN_009bc9b4: 1 A, 2 B */
GAME u32 armor_model(u32 equipment, const u8 *record, u32 gender, u32 fallback);  /* FUN_002f4258 */
GAME u32 weapon_model(u32 equipment, const u8 *record);                /* FUN_002f0fd4 */
GAME void hunter_equip(u32 hunter, const u8 *record);                  /* FUN_00b0ab90: armor piece */
GAME void hunter_weapon(u32 hunter, const u8 *record, u32 now);        /* FUN_00b0af84 */
GAME void hunter_load(u32 loader, u32 hunter);                         /* FUN_0065fca8: request the models */
GAME void hunter_setup(u32 hunter, const u8 *info);                    /* FUN_00b099ac: status from the info */
GAME void save_copy_out(u32 save, u8 *buffer, u32 size);               /* FUN_00c2789c: save data -> file */ void part_dye(u32 hunter, const u8 *ref, u32 model);              /* FUN_00b0a978: a part's colour */ void model_colour(u32 model, const u32 *rgba, u32 group);         /* FUN_00b05ae4 */ void hunter_dyes(u32 hunter);                                     /* FUN_00b0b6cc: the five parts' */

/* The game's variables and tables, by their names in game/executable/blocks.py GAME_SYMBOLS (never a raw address: the link's
   relocations move them to another game version) */
extern const u8 menu_line_texts[];
#define GAME_STATE game_control                 /* +0x2B 2 in the lobby, +0x2F the local player's index */
#define EQUIPMENT equipment_control             /* the equipment data object of the getters */
#define LOADER ((u32)lobby_hunter_loader)       /* the lobby's hunter model loader */
#define PREVIEW_HUNTER preview_hunter           /* the Smithy's preview hunter, once created */
#define PRELOAD_PLAYER 0x45C     /* the quest preloader (FUN_00bc14cc): the player index, */
#define PRELOAD_INFO 0x460       /* its info: +0x32 weapon record, +0x4E the 5 armor records */
#define INFO_ARMOR 0x4E
#define SAVE_AT 0x125C0          /* layered_state in the save data (equipment/layered/layered_equipment.py SAVE_AT) */
#define SAVE_MAGIC 0x4C
#define ST_INFO 0x2C             /* status -> the player info it was made from */
#define SELECT_KIND 5            /* status + 0x30 of the title's hunters (the hunter select screen's, the creation's) */
#define GAME_INFO 0xA8           /* the game control -> the player info of the character in play, or being created */
#define SELECT_SLOTS 3
#define SELECT_INFO 0x190        /* the hunter select screen's player info of each slot */
#define SLOT_SIZE 0x15204        /* a slot's buffer: the save data of its file, as read */
#define STATE_ROW 0x21           /* row of the Smithy menu's cursor */
#define WEAPON_MENU 6            /* and 7 */
#define LEVEL_CLASSES 1
_Static_assert(CLASSES_MENU == LEVEL_CLASSES, "layered_menu_drawn");
#define CLASS_ROWS 7
#define LINE_TEXTS menu_line_texts               /* per line (7: the cursor's copy): its first text pane */
#define MENU_TEXTS 0xC           /* the facility menu's panes (FUN_00a528e0): r6 = obj + 0x98D0 holds (a, node) refs */
#define DRAWN_MENU 0x1AC         /* + 0x98D0: obj + 0x9A7C, the menu drawn; + 1 its row */
#define CURSOR_LINE 7
#define NAME_SLOT 0              /* the text renderer's string slot the money uses too (FUN_00c0da68), shown by a
                                    number node (2, 100): our E_makeshop message msg_counter (Common's 0 adds "z") */
#define CAT_NAME 12              /* a Felyne's name at the start of its record: UTF-16, at most this many characters */

struct debug { u16 saves, loads, marked, preloads; };   /* the variable layered_debug, read by the probes */
_Static_assert(sizeof(struct debug) == 8, "layered_debug size (game/executable/blocks.py)");
extern struct debug layered_debug;
struct select {                  /* the variable layered_select: the title's hunter select screen (FUN_00bdfba0) */
    u32 infos;                   /* its slot 0's player info (slot n's: + n * SELECT_INFO) */
    const u8 *slots;             /* its slot 0's buffer (slot n's: + n * SLOT_SIZE); 0: no screen */
};
_Static_assert(sizeof(struct select) == 8, "layered_select size (game/executable/blocks.py)");
extern struct select layered_select;

/* ----- the hooks --------------------------------------------------------------------------------------- */

__asm__(
    "   .section .text.layered_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global layered_menu_count, layered_menu_lines, layered_text_kind, layered_menu_drawn, layered_smithy_pick\n"
    "   .global layered_smithy_open, layered_smithy_update, layered_smithy_desc\n"
    /* r0 = menu, r1 = the game's line counts -> r0 = the menu's lines */
    "layered_menu_count:\n"
    "   cmp     r0, #" STR(LAYERED_MENU) "\n"
    "   ldrlob  r0, [r1, r0]\n"     /* divided syntax, gcc's for this file */
    "   bxlo    lr\n"
    "   ldr     r0, =layered_ui\n"
    "   ldrb    r0, [r0, #" STR(UI_COUNT) "]\n"
    "   bx      lr\n"
    /* r1 = menu -> r0 = base of the line table, 28 bytes a menu */
    "layered_menu_lines:\n"
    "   cmp     r1, #" STR(LAYERED_MENU) "\n"
    "   ldrlo   r0, =menu_lines\n"
    "   ldrhs   r0, =layered_ui + " STR(UI_LINES) " - " STR(LAYERED_MENU) " * 28\n"
    "   bx      lr\n"
    /* r1 = message file of a line -> Z set when it is a common file: 0, 3 (the game's) or COMMON | file */
    "layered_text_kind:\n"
    "   cmp     r1, #3\n"
    "   cmpne   r1, #0\n"
    "   bxeq    lr\n"
    "   cmp     r1, #" STR(COMMON) "\n"
    "   cmpge   r1, r1\n"
    "   bx      lr\n"
    /* r6 = facility object + 0x98D0 -> r0 = the menu drawn (the game then shows its page bar for 6 and 7 only):
       0 for 6 and 7 on the screens' class menus; menu 18 writes the cats' names first. r1-r3 and r12 are free: the
       game's function ends there. */
    "layered_menu_drawn:\n"
    "   ldrb    r0, [r6, #" STR(DRAWN_MENU) "]\n"
    "   cmp     r0, #" STR(LAYERED_MENU) "\n"
    "   beq     drawn_layered\n"
    "   cmp     r0, #" STR(WEAPON_MENU) "\n"
    "   cmpne   r0, #" STR(WEAPON_MENU) " + 1\n"
    "   bxne    lr\n"
    "   ldr     r12, =layered_ui\n"
    "   ldrb    r12, [r12, #" STR(UI_LEVEL) "]\n"
    "   cmp     r12, #" STR(LEVEL_CLASSES) "\n"
    "   moveq   r0, #0\n"
    "   bx      lr\n"
    "drawn_layered:\n"
    "   push    {r4, lr}\n"
    "   mov     r0, r6\n"
    "   bl      layered_menu_names\n"
    "   mov     r0, #" STR(LAYERED_MENU) "\n"
    "   pop     {r4, pc}\n"
    /* Z set when (r1 menu, r0 line) is the Layered Equipment line of a Smithy menu; keeps every register */
    "layered_is_entry:\n"
    "   cmp     r1, #1\n"
    "   cmpeq   r0, #5\n"
    "   bxeq    lr\n"
    "   cmp     r1, #2\n"
    "   cmpeq   r0, #4\n"
    "   bxeq    lr\n"
    "   cmp     r1, #17\n"
    "   cmpeq   r0, #6\n"
    "   bx      lr\n"
    /* r4 = Smithy state, r5 = facility object -> r0 = the chosen line, 6 for ours */
    "layered_smithy_pick:\n"
    "   ldrh    r0, [r4, #0x24]\n"
    "   push    {r1, lr}\n"
    "   add     r1, r5, #0x9800\n"
    "   ldrb    r1, [r1, #0xCC]\n"
    "   bl      layered_is_entry\n"
    "   moveq   r0, #6\n"
    "   pop     {r1, pc}\n"
    /* the Smithy menu's choices past its own (r0 >= 6) */
    "layered_smithy_open:\n"
    "   cmp     r0, #6\n"
    "   bne     smithy_done\n"
    "   mov     r0, r5\n"
    "   mov     r1, r4\n"
    "   bl      layered_open\n"
    "   b       smithy_done\n"
    /* the Smithy's state 3, every frame */
    "layered_smithy_update:\n"
    "   mov     r0, r5\n"
    "   mov     r1, r4\n"
    "   bl      layered_update\n"
    "   b       smithy_done\n"
    /* r0 = the line's description in the game's table, r4 / r5 as above -> r2 = its message */
    "layered_smithy_desc:\n"
    "   ldrh    r2, [r0]\n"
    "   push    {r0, r1, lr}\n"
    "   ldrh    r0, [r4, #0x24]\n"
    "   add     r1, r5, #0x9800\n"
    "   ldrb    r1, [r1, #0xCC]\n"
    "   bl      layered_is_entry\n"
    "   ldreq   r0, =layered_data\n"
    "   ldreqh  r2, [r0, #" STR(DATA_MSG_DESC) "]\n"
    "   pop     {r0, r1, pc}\n"
    /* Model getter calls: the getter's arguments in r0-r3 stay; the hunter's status (and the part) are noted in
       layered_preview, then the call goes on to layered_armor_model / layered_weapon_model. */
    "   .global layered_armor_lobby, layered_armor_quest, layered_weapon_quest, layered_weapon_loader\n"
    "   .global layered_weapon_r5, layered_weapon_r6, layered_weapon_r9, layered_weapon_status_r7\n"
    "   .global layered_armor_preload, layered_weapon_preload, layered_armor_motion_r5, layered_armor_motion_r6\n"
    "   .global layered_weapon_motion_r5, layered_weapon_motion_r6, layered_weapon_gimmick, layered_select_hunter\n"
    "layered_select_hunter:\n"          /* FUN_00bdfba0: r0 hunter, r1 info, r7 the slot's buffer, r9 the slot */
    "   mov     r2, r7\n"
    "   mov     r3, r9\n"
    "   b       layered_select_note\n"
    "layered_armor_preload:\n"          /* FUN_00bc14cc: r4 the preloader */
    "   ldr     r12, =layered_preview\n"
    "   str     r4, [r12, #" STR(P_LOADER) "]\n"
    "   b       preload_armor_model\n"
    "layered_weapon_preload:\n"
    "   ldr     r12, =layered_preview\n"
    "   str     r4, [r12, #" STR(P_LOADER) "]\n"
    "   b       preload_weapon_model\n"
    "layered_armor_motion_r5:\n"        /* FUN_00bc07f8: r5 the status, the helm */
    "   push    {r0, r1}\n"
    "   mov     r0, r5\n"
    "   mov     r1, #4\n"
    "   b       armor_noted\n"
    "layered_armor_motion_r6:\n"        /* FUN_00bc450c: r6 the status, the helm */
    "   push    {r0, r1}\n"
    "   mov     r0, r6\n"
    "   mov     r1, #4\n"
    "   b       armor_noted\n"
    "layered_armor_lobby:\n"            /* FUN_00b0ab90: r4 hunter, r5 part */
    "   push    {r0, r1}\n"
    "   ldr     r0, [r4, #" STR(HUNTER_STATUS) "]\n"
    "   mov     r1, r5\n"
    "   b       armor_noted\n"
    "layered_armor_quest:\n"            /* FUN_00af9408: r7 hunter, r4 part */
    "   push    {r0, r1}\n"
    "   ldr     r0, [r7, #" STR(HUNTER_STATUS) "]\n"
    "   mov     r1, r4\n"
    "armor_noted:\n"
    "   ldr     r12, =layered_preview\n"
    "   str     r0, [r12, #" STR(P_STATUS) "]\n"
    "   str     r1, [r12, #" STR(P_PART) "]\n"
    "   pop     {r0, r1}\n"
    "   b       layered_armor_model\n"
    "layered_weapon_quest:\n"           /* FUN_00af9408: r7 hunter */
    "   push    {r0}\n"
    "   ldr     r0, [r7, #" STR(HUNTER_STATUS) "]\n"
    "   b       weapon_noted\n"
    "layered_weapon_status_r7:\n"       /* r7 -> the status */
    "   push    {r0}\n"
    "   ldr     r0, [r7]\n"
    "   b       weapon_noted\n"
    "layered_weapon_loader:\n"          /* FUN_0065ebd4: r9 = status + 0x1DC (the pending weapon) */
    "   push    {r0}\n"
    "   sub     r0, r9, #0x1DC\n"
    "   b       weapon_noted\n"
    "layered_weapon_r5:\n"
    "   push    {r0}\n"
    "   ldr     r0, [r5, #" STR(HUNTER_STATUS) "]\n"
    "   b       weapon_noted\n"
    "layered_weapon_r6:\n"
    "   push    {r0}\n"
    "   ldr     r0, [r6, #" STR(HUNTER_STATUS) "]\n"
    "   b       weapon_noted\n"
    "layered_weapon_motion_r5:\n"
    "   push    {r0}\n"
    "   mov     r0, r5\n"
    "   b       weapon_noted\n"
    "layered_weapon_motion_r6:\n"
    "   push    {r0}\n"
    "   mov     r0, r6\n"
    "   b       weapon_noted\n"
    "layered_weapon_gimmick:\n"         /* FUN_002d6d80: r4 the weapon, its hunter at + 0xE28 (FUN_00b082f8) */
    "   push    {r0}\n"
    "   ldr     r0, [r4, #0xE28]\n"
    "   cmp     r0, #0\n"
    "   ldrne   r0, [r0, #" STR(HUNTER_STATUS) "]\n"
    "   b       weapon_noted\n"
    "layered_weapon_r9:\n"
    "   push    {r0}\n"
    "   ldr     r0, [r9, #" STR(HUNTER_STATUS) "]\n"
    "weapon_noted:\n"
    "   ldr     r12, =layered_preview\n"
    "   str     r0, [r12, #" STR(P_STATUS) "]\n"
    "   pop     {r0}\n"
    "   b       layered_weapon_model\n"
    "   .ltorg\n"
    "   .text\n");

/* ----- the looks this build has -------------------------------------------------------------------------- */

/* Is `model` a look this build has for the armor part `part` (layered_state order; `female` 1) / for the weapon class
   `index` (equipment type - 7), in either catalog? A save may hold looks the mod running lacks (saved with XX's models,
   loaded without them): their files do not exist and the game waits for them forever (the hunter select screen then
   takes no button). */
/* The first set wearing `model` on `part` for that gender: MH4U's catalog first, then XX's (`*catalog`); -1 none. */
static int find_set(u32 part, u32 female, u32 model, u32 *catalog)
{
    for (u32 c = 0; c < 2; c++) {
        const struct catalog *k = &D->catalogs[c];
        const struct set *s = (const struct set *)(layered_data + k->sets_offset);
        const struct parts *own = k->parts_offset ? (const struct parts *)(layered_data + k->parts_offset) : 0;
        for (u32 pos = 0; pos < k->set_count; pos++) {
            if (own ? own[pos].models[part][female] == model
                    : ((s[pos].parts >> part) & 1) && (female ? s[pos].female : s[pos].male) == model) {
                *catalog = c;
                return pos;
            }
        }
    }
    return -1;
}

int known_armor(u32 part, u32 female, u32 model)
{
    u32 catalog;
    return model == NO_ARMOR || find_set(part, female, model, &catalog) >= 0;   /* NO_ARMOR: the game's own body */
}

int known_weapon(u32 index, u32 model)
{
    for (u32 c = 0; c < 2; c++) {
        const struct catalog *k = &D->catalogs[c];
        const struct weapon *w = (const struct weapon *)(layered_data + k->weapon_offset[index]);
        for (u32 pos = 0; pos < k->weapon_count[index]; pos++)
            if (w[pos].model == model)
                return 1;
    }
    return 0;
}

/* `st` without the looks this build lacks. */
static void keep_known(struct layered_state *st)
{
    for (u32 part = 0; part < 5; part++)
        for (u32 female = 0; female < 2; female++)
            if (st->armor[part][female] && !known_armor(part, female, st->armor[part][female]))
                st->armor[part][female] = 0;
    for (u32 index = 0; index < CLASSES; index++)
        if (st->weapon[index] && !known_weapon(index, st->weapon[index]))
            st->weapon[index] = 0;
}

/* ----- the looks on the hunters ------------------------------------------------------------------------ */

/* The local hunter, as FUN_00d04fbc tells it: in the lobby player 0 unless kind 3, else the local index. */
static int local_status(const u8 *st)
{
    const u8 *game = GAME_STATE;
    if (!game)
        return 0;
    if (game[0x2B] == 2)
        return st[0x30] != 3 && st[0x33] == 0;
    return (signed char)game[0x2F] == st[0x33];
}

/* 1 if `st` is a hunter of the hunter select screen noted in layered_select (a title hunter made from that screen's
   info of its slot); `*looks` then the looks its slot's file holds, read from the slot's buffer, or none. */
static int select_hunter(const u8 *st, const struct layered_state **looks)
{
    const struct select *s = &layered_select;
    u32 slot = st[0x33];
    if (!s->slots || st[0x30] != SELECT_KIND || slot >= SELECT_SLOTS ||
        *(const u32 *)(st + ST_INFO) != s->infos + slot * SELECT_INFO)
        return 0;
    const u8 *saved = s->slots + slot * SLOT_SIZE + SAVE_AT;
    *looks = saved[1] == SAVE_MAGIC && saved[0] ? (const struct layered_state *)saved : 0;
    return 1;
}

/* 1 if `st` is the character creation's hunter (FUN_00b783bc): a title hunter (kind SELECT_KIND) made from the game
   control's own player info, which the creation fills in as the player edits. The hunters of the game that use that
   info (the town's, a quest's) have another kind. A new character starts without looks, and layered_state still
   holds the last session's until a slot is loaded. */
static int creation_hunter(const u8 *st)
{
    const u8 *game = GAME_STATE;
    return game && st[0x30] == SELECT_KIND && *(const u32 *)(st + ST_INFO) == (u32)(game + GAME_INFO);
}

/* The looks a hunter (its status) wears: the screen's preview, a hunter select screen's slot's, the local
   hunter's, another player's (a hall hunter: the entry of its member; a quest hunter: the quest's snapshot, both built
   in `out`), or none (the character creation's included). */
static const struct layered_state *looks_of(const u8 *st, struct layered_state *out)
{
    struct preview *p = &layered_preview;
    const struct layered_state *slot_looks;
    if (!st)
        return 0;
    if (p->active && PREVIEW_HUNTER && st == *(const u8 **)(PREVIEW_HUNTER + HUNTER_STATUS))
        return &p->state;
    if (select_hunter(st, &slot_looks))
        return slot_looks;
    if (creation_hunter(st))
        return 0;
    if (local_status(st))
        return layered_state.enabled ? &layered_state : 0;
    const u8 *game = GAME_STATE;
    if (!game)
        return 0;
    return game[0x2B] == 2 ? layered_hall_looks(st, out) : layered_quest_looks(st[0x33], out);
}

/* Looks already kept to this build's: the screens' (from the lists), the loaded save's (keep_known) and another
   player's (`out`: an entry is kept only when this build has every look). A hunter select screen's slot's are read
   from the file as it is, so each look is checked when used. */
static int checked(const struct layered_state *s, const struct layered_state *out)
{
    return s == &layered_state || s == &layered_preview.state || s == out;
}

/* What the game draws for a part with no armor (a piece of id 0): FUN_002f4258 asked about a copy of the piece with its
   id zeroed gives the hunter's own body, arms and legs, and 0 (nothing loaded, the head's hair shows) for the waist and
   the helm. */
static u32 bare_model(u32 equipment, const u8 *record, u32 gender, u32 fallback)
{
    u8 bare[RECORD];
    layered_copy(bare, record, RECORD);    /* a player info's records are not on a word (+ 0x4E + part * RECORD) */
    bare[2] = bare[3] = 0;
    return armor_model(equipment, bare, gender, fallback);
}

/* The armor getter's calls (layered_armor_lobby / _quest noted the hunter's status and the part). */
ARM u32 layered_armor_model(u32 equipment, const u8 *record, u32 gender, u32 fallback)
{
    u32 model = armor_model(equipment, record, gender, fallback);
    struct layered_state other;
    const struct layered_state *s = looks_of((const u8 *)layered_preview.status, &other);
    u32 part = layered_preview.part;
    if (s && part < 5 && s->armor[part][gender & 1] &&
        (checked(s, &other) || known_armor(part, gender & 1, s->armor[part][gender & 1]))) {
        model = s->armor[part][gender & 1];
        if (model == NO_ARMOR)
            model = bare_model(equipment, record, gender, fallback);
    }
    return model;
}

/* ----- the looks' colours ----------------------------------- */

#define ST_GENDER 0x34           /* status: the hunter's gender, the getters' (bit 0 female) */
#define ST_SKIN 0x40             /* status: the skin colour, what the game gives a part of armor id 0 */
#define MODEL_STATE 4            /* model + 4, bits 0-2: 1 or 2 once its materials can take a colour (FUN_00b0a978) */
#define DYE_GROUP 3              /* the materials a dye colours (FUN_00b05ae4's group; 1 hair, 2 skin) */

/* RGB565 -> the RGBA the game draws (FUN_00b0a978): R in the low byte, every channel stretched to 0-255. */
static u32 dye_rgba(u32 c)
{
    return ((c >> 11) * 0x83A >> 8) | (((c >> 5) & 0x3F) * 0x410 >> 8) << 8 | ((c & 0x1F) * 0x83A >> 8) << 16 |
           0xFF000000u;
}

/* The own colour (RGBA) of the look `model` on `part` for that gender: its set's in the first catalog wearing it
   (MH4U's first, find_set), or 0 when no set knows it. */
static u32 own_colour(u32 part, u32 female, u32 model)
{
    u32 catalog;
    int pos = find_set(part, female, model, &catalog);
    if (pos < 0)
        return 0;
    const struct catalog *k = &D->catalogs[catalog];
    if (!k->colours_offset || !D->palette)
        return 0;
    const u8 *palette = layered_data + D->palette;
    u32 count = D->palette_count, entry = layered_data[k->colours_offset + pos];
    if (entry != NO_COLOUR && entry >= count)    /* a set whose parts or genders differ: its record */
        entry = ((const struct colours *)(palette + count * 3))[entry - count].entry[part][female];
    if (entry == NO_COLOUR)
        return 0;
    const u8 *rgb = palette + entry * 3;
    return rgb[0] | rgb[1] << 8 | rgb[2] << 16 | 0xFF000000u;
}

/* The game's part colour calls (FUN_00b0a978: `ref` the part's real piece, among the status's five, `model` its model).
   A part wearing a look takes the look's colour, never the real piece's dye: the colour chosen for it (dye), else its
   own; Nothing is the hunter's bare body (its skin, as the game's armor id 0). Any other part, the game's call. */
ARM void layered_part_dye(u32 hunter, const u8 *ref, u32 model)
{
    const u8 *st = *(const u8 *const *)(hunter + HUNTER_STATUS);
    u32 at = (u32)ref - (u32)(st + ST_ARMOR), part = at < 5 * RECORD ? small_divide(at, RECORD) : 5;
    u32 female = st[ST_GENDER] & 1;
    struct layered_state other;
    const struct layered_state *s = part < 5 && part * RECORD == at ? looks_of(st, &other) : 0;
    u32 look = s ? s->armor[part][female] : 0;
    u32 colour = !look || !(checked(s, &other) || known_armor(part, female, look)) ? 0
                 : look == NO_ARMOR ? *(const u32 *)(st + ST_SKIN)
                 : s->dye[part] ? dye_rgba(s->dye[part]) : own_colour(part, female, look);
    if (!colour && look != NO_ARMOR) {
        part_dye(hunter, ref, model);
        return;
    }
    u32 state = *(const u32 *)(model + MODEL_STATE) & 7;
    if (state == 1 || state == 2)
        model_colour(model, &colour, DYE_GROUP);
}

/* The screens changed a colour of the preview: its hunter takes them now (FUN_00b0b6cc: the five parts' colours). */
ARM void layered_dye_refresh(void)
{
    if (layered_preview.active && PREVIEW_HUNTER)
        hunter_dyes(PREVIEW_HUNTER);
}

/* The weapon getter's calls: a look of the weapon's own class (equipment type - 7) only. */
ARM u32 layered_weapon_model(u32 equipment, const u8 *record)
{
    u32 model = weapon_model(equipment, record);
    struct layered_state other;
    const struct layered_state *s = looks_of((const u8 *)layered_preview.status, &other);
    u32 index = record[0] - 7u;
    if (s && index < 14 && s->weapon[index] && (checked(s, &other) || known_weapon(index, s->weapon[index])))
        model = s->weapon[index];
    return model;
}

/* The quest preloader's looks: the player's info is the local one when playing alone, else its index decides: the
   local player's, or another's from the quest's snapshot (built in `out`). */
static const struct layered_state *preload_looks(const u8 *loader, struct layered_state *out)
{
    const u8 *game = GAME_STATE;
    if (!game || !loader)
        return 0;
    if ((signed char)game[0x2D] < 2 || loader[PRELOAD_PLAYER] == game[0x2F])
        return layered_state.enabled ? &layered_state : 0;
    return layered_quest_looks(loader[PRELOAD_PLAYER], out);
}

ARM u32 preload_armor_model(u32 equipment, const u8 *record, u32 gender, u32 fallback)
{
    u32 model = armor_model(equipment, record, gender, fallback);
    const u8 *loader = (const u8 *)layered_preview.loader;
    struct layered_state other;
    const struct layered_state *s = preload_looks(loader, &other);
    if (!s)
        return model;
    const u8 *info = *(const u8 *const *)(loader + PRELOAD_INFO);
    for (u32 part = 0; part < 5; part++)
        if (record == info + INFO_ARMOR + part * RECORD && s->armor[part][gender & 1]) {
            layered_debug.preloads++;
            return s->armor[part][gender & 1] == NO_ARMOR ? bare_model(equipment, record, gender, fallback)
                                                          : s->armor[part][gender & 1];
        }
    return model;
}

ARM u32 preload_weapon_model(u32 equipment, const u8 *record)
{
    u32 model = weapon_model(equipment, record);
    struct layered_state other;
    const struct layered_state *s = preload_looks((const u8 *)layered_preview.loader, &other);
    u32 index = record[0] - 7u;
    if (s && index < 14 && s->weapon[index]) {
        layered_debug.preloads++;
        model = s->weapon[index];
    }
    return model;
}

/* The save: layered_state rides in the save file at + SAVE_AT, marked by SAVE_MAGIC in its reserved byte. */
void layered_clear(void *at, u32 size)
{
    volatile u8 *b = at;   /* volatile: no memset call (no library is linked) */
    while (size--)
        *b++ = 0;
}

void layered_copy(void *to, const void *from, u32 size)
{
    volatile u8 *b = to;   /* volatile: no memcpy call (no library is linked) */
    const u8 *a = from;
    while (size--)
        *b++ = *a++;
}

/* A save loaded (save data <- the slot read from its file): take the looks out, leave the data as the game's. */
ARM void layered_save_load(u8 *data, const u8 *slot, u32 size)
{
    mem_copy(data, slot, size);
    layered_debug.loads++;
    if (data[SAVE_AT + 1] == SAVE_MAGIC) {
        layered_copy(&layered_state, data + SAVE_AT, sizeof layered_state);
        keep_known(&layered_state);
        layered_debug.marked++;
    } else {
        layered_clear(&layered_state, sizeof layered_state);
    }
    layered_state.reserved = 0;
    layered_clear(data + SAVE_AT, sizeof layered_state);
    layered_select.slots = 0;    /* the hunter select screen is over */
}

/* The hunter select screen sets a slot's hunter up (FUN_00bdfba0: r7 the slot's buffer, r9 the slot, passed by
   layered_select_hunter): the game's call, then the screen is noted, so that its hunters wear their slots' looks. */
ARM void layered_select_note(u32 hunter, const u8 *info, const u8 *slot, u32 index)
{
    hunter_setup(hunter, info);
    if (index < SELECT_SLOTS) {
        layered_select.infos = (u32)info - index * SELECT_INFO;
        layered_select.slots = slot - index * SLOT_SIZE;
    }
}

/* The save file being written (its buffer <- save data, then the checksum and the cipher): add the looks. */
ARM void layered_save_store(u32 save, u8 *buffer, u32 size)
{
    save_copy_out(save, buffer, size);
    layered_copy(buffer + SAVE_AT, &layered_state, sizeof layered_state);
    buffer[SAVE_AT + 1] = SAVE_MAGIC;
    layered_debug.saves++;
}

/* A lobby hunter puts its pieces on again (as FUN_0065e31c does), so the getters run with the looks of now. */
void hunter_reload(u32 hunter, const u8 *weapon)
{
    const u8 *st = *(const u8 **)(hunter + HUNTER_STATUS);
    for (u32 i = 0; i < 5; i++)
        hunter_equip(hunter, st + ST_ARMOR + i * RECORD);
    hunter_weapon(hunter, weapon ? weapon : st + ST_WEAPON, 1);
    hunter_load(LOADER, hunter);
}

u32 small_divide(u32 a, u32 b)
{
    u32 q = 0;
    while (a >= b) {
        a -= b;
        q++;
    }
    return q;
}

/* ----- the entry list, the classes, the cats --------------------------------------------------------------- */

static void open_cursor(u32 obj, u32 count, u32 rows, u32 index)
{
    struct cursor *c = &layered_ui.cursor;
    menu_cursor_init(obj, c, count, rows, 0, SOUND_DECIDE, SOUND_CURSOR, SOUND_PAGE);
    c->col = small_divide(index, rows);
    c->row = index - c->col * rows;
    c->index = index;
    *(u8 *)(obj + OBJ_SHOWN) = 0xFE;
}

/* Menu 18 shows `count` lines of `messages`, the cursor on `row`. */
static void show_lines(u32 obj, u32 level, const u16 *messages, u32 count, u32 row)
{
    struct ui *u = &layered_ui;
    u->level = level;
    u->count = count;
    for (u32 i = 0; i < count; i++) {
        u->lines[i][0] = MAKESHOP;
        u->lines[i][1] = messages[i];
    }
    open_cursor(obj, count, count, row);
}

/* The entry's last line, Relics: below Felyne, which is there with the Felynes' models in the run. */
static u32 relics_line(void)
{
    return felyne_looks_data.total ? 3 : 2;
}

/* Weapons, Armor, Felyne (with the Felynes' models in the run) and Relics; the normal screens from here. */
static void show_entry(u32 obj, u32 row)
{
    u16 messages[4] = {D->msg_weapons, R->messages[MSG_ARMOR], felyne_looks_data.msg_felynes, 0};
    u32 last = relics_line();
    messages[last] = R->msg_relics;
    layered_ui.relics = 0;
    show_lines(obj, ENTRY, messages, last + 1, row);
}

/* Relics' Weapons and Armor: the screens from here list the relics alone (layered_forge.c, on_screen). */
static void show_relics(u32 obj, u32 row)
{
    u16 messages[2] = {D->msg_weapons, R->messages[MSG_ARMOR]};
    layered_ui.relics = 1;
    show_lines(obj, RELICS, messages, 2, row);
}

/* The two active cats: blank lines, their names written once the menu is drawn (layered_menu_names). */
static void show_cats(u32 obj, u32 row)
{
    u16 blank[FELYNE_MAX_ACTIVE] = {D->msg_blank, D->msg_blank};
    show_lines(obj, CATS, blank, FELYNE_MAX_ACTIVE, row);
}

static void show_classes(u32 obj)
{
    layered_ui.level = CLASSES_MENU;
    open_cursor(obj, CLASSES, CLASS_ROWS, layered_ui.class_index);
}

/* The menu of the level shown, at the cursor. */
static u32 menu_shown(void)
{
    struct ui *u = &layered_ui;
    return u->level == CLASSES_MENU ? WEAPON_MENU + u->cursor.col : LAYERED_MENU;
}

/* The Felyne line chosen: none active stays here, one opens his screen, two ask which. */
static void open_felynes(u32 obj)
{
    const u8 *cats[FELYNE_MAX_ACTIVE];
    u32 count = felyne_active(cats);
    felyne_ui.cat = 0;
    if (!count)
        play(SOUND_ERROR);
    else if (count == 1)
        forge_open(obj, M_FELYNE);
    else
        show_cats(obj, 0);
}

static void choose(u32 obj, u32 index)
{
    struct ui *u = &layered_ui;
    if (u->level == ENTRY || u->level == RELICS) {
        if (index == 0)
            show_classes(obj);
        else if (index == 1)
            forge_open(obj, M_ARMOR);
        else if (index == relics_line())
            show_relics(obj, 0);
        else
            open_felynes(obj);
    } else if (u->level == CATS) {
        felyne_ui.cat = index;
        forge_open(obj, M_FELYNE);
    } else {
        u->class_index = index;
        forge_open(obj, M_WEAPON);
    }
}

static void back(u32 obj, u8 *state)
{
    struct ui *u = &layered_ui;
    if (u->level == CATS) {
        show_entry(obj, 2);
    } else if (u->level == RELICS) {
        show_entry(obj, relics_line());
    } else if (u->level == CLASSES_MENU) {
        if (u->relics)
            show_relics(obj, 0);
        else
            show_entry(obj, 0);
    } else {
        state[0] = 1;  /* the Smithy's menu again, on our line */
        facility_menu_set(obj, u->smithy_menu, u->smithy_row, 0xFF);
        if (*(u32 *)(obj + OBJ_HUNTER))
            hunter_reload(*(u32 *)(obj + OBJ_HUNTER), 0);   /* the real hunter wears the looks chosen */
        layered_net_state_left();                           /* and the other players see them */
        if (felyne_ui.dirty && felyne_looks_data.total)
            felyne_refresh(obj);                            /* and the cats in the area theirs */
    }
}

void forge_back_to_menu(u32 obj)
{
    struct ui *u = &layered_ui;
    const u8 *cats[FELYNE_MAX_ACTIVE];
    if (u->mode == M_WEAPON)
        show_classes(obj);
    else if (u->mode == M_FELYNE && felyne_active(cats) > 1)
        show_cats(obj, felyne_ui.cat);
    else if (u->relics)
        show_relics(obj, 1);
    else
        show_entry(obj, u->mode == M_FELYNE ? 2 : 1);
    /* The game shows ui401's groups again only on a change from no menu: open_cursor's redraw value would skip them. */
    *(u8 *)(obj + OBJ_SHOWN) = NO_MENU;
    facility_menu_set(obj, menu_shown(), u->cursor.row, 0xFF);
}


/* Facility menu line `line` shows a cat's name, by the text renderer's string slot and our message of that slot alone
   (as the counter): a name is no message of the game's. */
static void name_line(u32 menu, u32 line, const u8 *cat)
{
    struct ref *pane = (struct ref *)(menu + MENU_TEXTS) + LINE_TEXTS[line];
    u16 name[CAT_NAME + 1];
    u32 length = 0;
    while (length < CAT_NAME && (cat[2 * length] || cat[2 * length + 1])) {
        name[length] = cat[2 * length] | cat[2 * length + 1] << 8;
        length++;
    }
    name[length] = 0;
    text_slot(NAME_SLOT, name, length);
    text_lobby(pane, MAKESHOP, D->msg_counter);
    text_show(*(u32 *)(pane->node + 8), 1);
    u8 *node = *(u8 **)(pane->node + 0x14), *dirty = *(u8 **)(node + 0xC);
    if (dirty)
        dirty[0x12] = 3;
    else
        pane_redraw(pane->group, (u32)node);
}

/* layered_menu_drawn: menu 18 drawn (r6 = obj + 0x98D0): on the cats' level each line and the cursor's copy show their
   cat's name. */
ARM void layered_menu_names(u32 menu)
{
    const u8 *cats[FELYNE_MAX_ACTIVE];
    if (layered_ui.level != CATS)
        return;
    u32 count = felyne_active(cats), row = *(u8 *)(menu + DRAWN_MENU + 1);
    for (u32 i = 0; i < count; i++)
        name_line(menu, i, cats[i]);
    if (row < count)
        name_line(menu, CURSOR_LINE, cats[row]);
}

/* layered_smithy_open: the Smithy menu's Layered Gear line was chosen. */
ARM void layered_open(u32 obj, u8 *state)
{
    struct ui *u = &layered_ui;
    u->smithy_menu = *(u8 *)(obj + OBJ_MENU);
    u->smithy_row = state[STATE_ROW];
    felyne_ui.dirty = 0;
    state[0] = LAYERED_STATE;
    play(SOUND_DECIDE);
    show_entry(obj, 0);
    facility_menu_set(obj, LAYERED_MENU, 0, 0xFF);
}

/* The help line: of the screen's mode, or of the entry's levels. */
u32 help_message(void)
{
    struct ui *u = &layered_ui;
    const u8 *cats[FELYNE_MAX_ACTIVE];
    if (u->level == FORGE)
        return R->messages[u->mode == M_WEAPON ? MSG_HELP_WEAPONS : u->mode == M_ARMOR ? MSG_HELP_ARMOR : MSG_HELP_FELYNE];
    if (u->level == CATS)
        return felyne_looks_data.msg_choose;
    if (u->level == CLASSES_MENU || u->cursor.index == 0)
        return R->messages[MSG_HELP_WEAPONS];
    if (u->cursor.index == 1)
        return R->messages[MSG_HELP_ARMOR];
    if (u->cursor.index == relics_line())
        return R->msg_help_relics;
    return felyne_active(cats) ? R->messages[MSG_HELP_FELYNE] : felyne_looks_data.msg_none;
}

/* layered_smithy_update: every frame of the Smithy's state 3. */
ARM void layered_update(u32 obj, u8 *state)
{
    struct ui *u = &layered_ui;
    if (u->level == FORGE) {
        forge_update(obj);
        return;
    }
    facility_help(1, MAKESHOP, help_message());
    u32 result = menu_cursor_update(obj, &u->cursor, 0);
    if (result == 2)
        back(obj, state);
    else if (result == 1)
        choose(obj, u->cursor.index);
    if (state[0] != LAYERED_STATE || u->level == FORGE)
        return;
    facility_menu_set(obj, menu_shown(), u->cursor.row, 0xFF);
}
