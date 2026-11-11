/* The Felynes' looks of layered equipment: a unit of the block
 * layered_selector.
 *
 * A cat's look lives in its own save record, at + LOOK_AT, 4 bytes of padding the game never reads: three 10-bit model
 * numbers (head, body, weapon; 0 none) and a 2-bit mark. Every whole-record copy of the game takes it along (the board
 * compacting the cards), a dismissal clears it, and a new or received cat starts without one (felyne_new_record).
 *
 * The game asks the equipment tables for a piece's model number by the piece's id: the calls below, for the player's cats,
 * go to stubs that make the call and then give the number of the cat's look (equipment/layered/layered_equipment.py,
 * FELYNE_CALLS names each one). Three families, by what tells which cat it is:
 *   lobby    an actor (its status + STATUS_RECORD: the record it was made from, whole). Its kind says what it is:
 *            KIND_NAKED and past KIND_LAST_PREVIEW wear nothing, the facility's preview kinds only the screen's look.
 *   quest    a compact record (0x68 bytes, no look) or an actor made from one: its slot in the game control tells it. Alone,
 *            slot 0 the main cat and 1 the second; with two players, the local player's slot the main cat.
 *   record   the record itself (a cutscene's, the hunter select screen's).
 */

#include "layered.h"

GAME u32 felyne_model_weapon(u32 equipment, u32 id);                       /* FUN_002f6c98 */
GAME u32 felyne_suit(u32 equipment, const u8 *pair);                       /* FUN_002f8930 */
GAME u32 felyne_head_case(u32 equipment, const u8 *pair);                  /* FUN_002f8a34 */
GAME void felyne_effect(u32 manager, const u8 *actor, u32 model, const u8 *pair);  /* FUN_0069998c */
GAME u32 felyne_quest_effect(u32 manager, const u8 *actor, u32 model, const u8 *pair);  /* FUN_00699d5c */
GAME void felyne_scene_effect(u32 manager, u32 model, const u8 *pair, const u8 *record);  /* FUN_006997c4 */
GAME void felyne_scene_joints(u32 manager, u32 actor, const u8 *pair, const u8 *record);  /* FUN_0069a484 */
GAME const u8 *felyne_main_record(u32 save);                               /* FUN_00c2065c */
GAME const u8 *felyne_second_record(void);                                 /* FUN_00697028: 0 without the main cat */
GAME u32 felyne_main_active(void);                                         /* FUN_00a2d8d4 */
GAME void felyne_actor_update(u32 obj, u32 actor, const u8 *record);       /* FUN_00a3725c */
GAME u32 felyne_town_actor(u32 obj, u32 which);                            /* FUN_00a5e49c */
GAME u32 felyne_second_actor(u32 obj);                                     /* FUN_009fd784 */
GAME void felyne_try_on(u32 obj, u32 part, u32 id, const u8 *record, u32 mode);   /* FUN_00a266a4 */
GAME u32 felyne_try_on_ready(u32 obj);                                     /* FUN_00a64e10 */
GAME void felyne_try_on_close(u32 obj, u32 keep);                          /* FUN_00a11c54 */
GAME void felyne_try_on_turn(u32 obj, u32 on);                             /* FUN_00a26910 */
GAME void preview_frame_bind(u32 frame);                                   /* FUN_0059e5d0 */
GAME void preview_frame_show(u32 frame, u32 mode);                         /* FUN_0059f56c */
GAME void preview_frame_reset(u32 frame);                                  /* FUN_0059e8f8 */

struct select { u32 infos; const u8 *slots; };   /* layered_selector.c: the hunter select screen */
extern struct select layered_select;

#define LOOK_AT 0x74             /* the record's padding: the look word */
#define RECORD_SIZE 0xE8
#define LOOK_MARK 1u             /* the word's top two bits */
#define LOOK_NUMBERS 0x3FFFFFFFu
#define ACTOR_STATUS 0xE2C       /* a lobby actor -> its status */
#define STATUS_KIND 0x5E
#define STATUS_RECORD 0x160
#define OWNER_AT 0x46B           /* a kind-0 actor's record buffer: the owner's lobby index (0 the local player)  */
#define KIND_NAKED 0xF           /* FUN_00c35ec4: the board's cats, their gear ids zeroed */
#define KIND_FIRST_PREVIEW 0x10  /* obj + 0x1894C: the facility's preview cats */
#define KIND_LAST_PREVIEW 0x13
#define QUEST_STATUS 0xE28       /* a quest actor -> its status: + 0x24 the owner, + 0x25 its index */
#define QUEST_OWNER 0x24
#define QUEST_INDEX 0x25
#define GAME_PLAYERS 0x308       /* the game control: the players of a quest, */
#define GAME_CATS 0x309          /* its cats, */
#define GAME_OWNERS 0x30A        /* the owner of each, */
#define GAME_COMPACTS 0x238      /* and their compact records */
#define COMPACT_SIZE 0x68
#define GAME_LOCAL 0x2F          /* the local player's index */
#define GAME_STAGE 0x2B
#define LOBBY_STAGE 2
#define OBJ_MAIN_CHANGED 0x97CD  /* the facility object: FUN_00a1a464 sets it when the main cat's gear changed, */
#define OBJ_TRY_ON_ACTOR 0x18954 /* the preview cat */
#define TRY_ON_NONE 3            /* FUN_00a266a4's part: tries nothing on */
#define TRY_ON_BIG 1             /* its mode: the hunter preview's rectangle */
#define STATUS_SETTLE_A 0xEC     /* FUN_00a8a7f0 after a change: the status' timers, */
#define STATUS_SETTLE_B 0xF0
#define SETTLE_TIME 0x40800000u  /* 4.0f */
#define SELECT_SLOTS 3
#define SLOT_SIZE 0x15204        /* layered_selector.c: a slot's buffer */
#define SAVE_AT 0x125C0
#define SAVE_MAGIC 0x4C

#define F (&felyne_looks_data)

/* ----- the stubs ------------------------------------------------------------------------------------------ */

/* A stub of a getter's call, its arguments in r0-r3: the call, then `resolver(real number, what \source put in r4, part)`
   (r4 kept). */
__asm__(
    "   .section .text.felyne_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .macro CALL_SITE name, callee, source, part, resolver\n"
    "   .global \\name\n"
    "\\name:\n"
    "   push    {r4, lr}\n"
    "   \\source\n"
    "   ldr     r12, =\\callee\n"
    "   blx     r12\n"
    "   mov     r1, r4\n"
    "   mov     r2, #\\part\n"
    "   pop     {r4, lr}\n"
    "   b       \\resolver\n"
    "   .endm\n"
    /* the lobby: an actor in r4, r5 or r7 */
    "   CALL_SITE felyne_head_r5, felyne_model_armor, \"mov r4, r5\", 0, felyne_actor_model\n"
    "   CALL_SITE felyne_body_r5, felyne_model_body, \"mov r4, r5\", 1, felyne_actor_model\n"
    "   CALL_SITE felyne_weapon_r5, felyne_model_weapon, \"mov r4, r5\", 2, felyne_actor_model\n"
    "   CALL_SITE felyne_head_r4, felyne_model_armor, \"mov r4, r4\", 0, felyne_actor_model\n"
    "   CALL_SITE felyne_body_r4, felyne_model_body, \"mov r4, r4\", 1, felyne_actor_model\n"
    "   CALL_SITE felyne_weapon_r7, felyne_model_weapon, \"mov r4, r7\", 2, felyne_actor_model\n"
    "   CALL_SITE felyne_head_r7, felyne_model_armor, \"mov r4, r7\", 0, felyne_actor_model\n"
    "   CALL_SITE felyne_body_r7, felyne_model_armor, \"mov r4, r7\", 1, felyne_actor_model\n"
    "   CALL_SITE felyne_suit_lobby, felyne_suit, \"mov r4, r4\", 0, felyne_suit_actor\n"
    /* FUN_00697348: its actor is gone by its suit check, felyne_show_note kept it */
    "   CALL_SITE felyne_suit_show, felyne_suit, \"ldr r4, =felyne_ui; ldr r4, [r4, #16]\", 0, felyne_suit_actor\n"
    /* the hunter select screen: r6 the actor's record */
    "   CALL_SITE felyne_select_weapon, felyne_model_weapon, \"mov r4, r6\", 2, felyne_look_or_real\n"
    "   CALL_SITE felyne_select_head, felyne_model_armor, \"mov r4, r6\", 0, felyne_look_or_real\n"
    "   CALL_SITE felyne_select_body, felyne_model_body, \"mov r4, r6\", 1, felyne_look_or_real\n"
    /* a quest: r6 the compact record, or the quest preloader's at r4 + 0x468, or the actor */
    "   CALL_SITE felyne_quest_weapon, felyne_model_weapon, \"mov r4, r6\", 2, felyne_compact_model\n"
    "   CALL_SITE felyne_quest_head, felyne_model_armor, \"mov r4, r6\", 0, felyne_compact_model\n"
    "   CALL_SITE felyne_quest_body, felyne_model_armor, \"mov r4, r6\", 1, felyne_compact_model\n"
    "   CALL_SITE felyne_preload_weapon, felyne_model_pair, \"ldr r4, [r4, #0x468]\", 2, felyne_compact_model\n"
    "   CALL_SITE felyne_preload_head, felyne_model_pair, \"ldr r4, [r4, #0x468]\", 0, felyne_compact_model\n"
    "   CALL_SITE felyne_preload_body, felyne_model_pair_body, \"ldr r4, [r4, #0x468]\", 1, felyne_compact_model\n"
    "   CALL_SITE felyne_quest_body_again, felyne_model_body, \"mov r4, r5\", 1, felyne_quest_actor_model\n"
    "   CALL_SITE felyne_quest_sound, felyne_model_weapon, \"ldr r4, [r7, #0x40]\", 2, felyne_sound_model\n"
    "   CALL_SITE felyne_suit_quest, felyne_suit, \"mov r4, r4\", 0, felyne_suit_quest_actor\n"
    "   CALL_SITE felyne_suit_frame, felyne_suit, \"mov r4, r5\", 0, felyne_suit_quest_actor\n"
    "   CALL_SITE felyne_helm_case, felyne_head_case, \"mov r4, r4\", 0, felyne_helm_case_quest\n"
    /* a cutscene: r5 the record; the head and body read their number from the piece's record (r0 = the piece) */
    "   CALL_SITE felyne_scene_weapon, felyne_model_weapon, \"mov r4, r5\", 2, felyne_record_model\n"
    "   CALL_SITE felyne_scene_suit, felyne_suit, \"mov r4, r5\", 0, felyne_suit_record\n"
    "   CALL_SITE felyne_scene_sound, felyne_model_weapon, \"mov r4, r4\", 2, felyne_index_model\n"
    /* FUN_00bc6d88, the main cat's preload for a cutscene: r1 the piece's pair in the main record */
    "   CALL_SITE felyne_scene_preload_weapon, felyne_model_pair, \"sub r4, r1, #0x34\", 2, felyne_record_model\n"
    "   CALL_SITE felyne_scene_preload_head, felyne_model_pair, \"sub r4, r1, #0x3C\", 0, felyne_record_model\n"
    "   CALL_SITE felyne_scene_preload_body, felyne_model_pair_body, \"sub r4, r1, #0x38\", 1, felyne_record_model\n"
    "   .global felyne_scene_head, felyne_scene_body, felyne_select_record, felyne_show_note\n"
    "felyne_scene_head:\n"              /* "ldrh r0, [r0]" after FUN_002f286c */
    "   ldrh    r0, [r0]\n"
    "   mov     r1, r5\n"
    "   mov     r2, #0\n"
    "   b       felyne_record_model\n"
    "felyne_scene_body:\n"
    "   ldrh    r0, [r0]\n"
    "   mov     r1, r5\n"
    "   mov     r2, #1\n"
    "   b       felyne_record_model\n"
    /* FUN_00bdfba0, "ldr r0, [r4]" right after copying a slot's cat into its actor: r6 that copy, r9 the slot */
    "felyne_select_record:\n"
    "   push    {r4, lr}\n"
    "   mov     r0, r6\n"
    "   mov     r1, r9\n"
    "   bl      felyne_select_note\n"
    "   pop     {r4, lr}\n"
    "   ldr     r0, [r4]\n"
    "   bx      lr\n"
    /* FUN_00697348, "ldr r0, [r1, #0xe2c]" at its start: r1 its actor, noted for its suit check */
    "felyne_show_note:\n"
    "   ldr     r12, =felyne_ui\n"
    "   str     r1, [r12, #16]\n"
    "   ldr     r0, [r1, #0xe2c]\n"
    "   bx      lr\n"
    "   .ltorg\n"
    "   .text\n");

/* ----- the look word -------------------------------------------------------------------------------------- */

static u32 word_of(const u8 *record)
{
    const u8 *b = record + LOOK_AT;
    return b[0] | b[1] << 8 | b[2] << 16 | (u32)b[3] << 24;
}

static void set_word(u8 *record, u32 word)
{
    u8 *b = record + LOOK_AT;
    b[0] = word;
    b[1] = word >> 8;
    b[2] = word >> 16;
    b[3] = word >> 24;
}

/* The word's numbers, none in a word without the mark (a padding that holds something else). */
static u32 numbers_of(const u8 *record)
{
    u32 word = word_of(record);
    return word >> 30 == LOOK_MARK ? word & LOOK_NUMBERS : 0;
}

static u32 number_in(u32 numbers, u32 part)
{
    return numbers >> (part * FELYNE_NUMBER_BITS) & FELYNE_NUMBER_MASK;
}

static u32 marked(u32 numbers)
{
    return numbers ? numbers | LOOK_MARK << 30 : 0;
}

/* Is `model` a look of `part` this build has? A save may hold a number its files lack: the game would wait for them
forever. */
static int known(u32 part, u32 model)
{
    return model < F->ids && F->known[part][model >> 3] >> (model & 7) & 1;
}

/* The number of `part` in a look word that came from another player, or 0 (a word without the mark, a number lacking). */
static u32 word_look(u32 word, u32 part)
{
    u32 model = word >> 30 == LOOK_MARK ? number_in(word & LOOK_NUMBERS, part) : 0;
    return known(part, model) ? model : 0;
}

/* The number of the record's look of `part`, or 0. */
static u32 look_of(const u8 *record, u32 part)
{
    u32 model = number_in(numbers_of(record), part);
    return known(part, model) ? model : 0;
}

/* ----- which cat ------------------------------------------------------------------------------------------ */

static int enabled(void)
{
    return layered_state.enabled;
}

/* A hunter select screen's record: `felyne_select_note` has weighed the slot's own switch. */
static int selected(const u8 *record)
{
    if (!layered_select.slots)
        return 0;
    for (u32 i = 0; i < SELECT_SLOTS; i++)
        if (felyne_ui.select[i] == record)
            return 1;
    return 0;
}

/* A lobby actor's look, by the rule at the top of this file. */
static u32 actor_look(const u8 *actor, u32 part)
{
    const u8 *status = *(const u8 *const *)(actor + ACTOR_STATUS);
    const u8 *record = status ? *(const u8 *const *)(status + STATUS_RECORD) : 0;
    if (!record)
        return 0;
    if (selected(record))
        return look_of(record, part);
    u32 kind = status[STATUS_KIND];
    if (kind >= KIND_FIRST_PREVIEW) {
        if (kind > KIND_LAST_PREVIEW || !felyne_ui.preview)
            return 0;
    } else if (kind == KIND_NAKED) {
        return 0;
    } else if (!enabled() && !(kind == 0 && record[OWNER_AT])) {   /* another player's cat: its word is there only when valid */
        return 0;
    }
    return look_of(record, part);
}

/* The number of `part` the cat of a quest's slot wears, or 0: our own cats by the record and the switch, another player's
   by the quest's snapshot (layered_online.c; the compact carries no look). */
static u32 quest_look(u32 owner, u32 slot, u32 part)
{
    const u8 *game = game_control;
    const u8 *record = 0;
    if (!game)
        return 0;
    if (game[GAME_PLAYERS] < 2)
        record = slot == 0 ? felyne_main_record(save_control) : slot == 1 ? felyne_second_record() : 0;
    else if ((u8)game[GAME_LOCAL] == owner)
        record = felyne_main_record(save_control);
    else
        return word_look(layered_quest_cat(owner), part);
    return record && enabled() ? look_of(record, part) : 0;
}

static u32 quest_actor_look(const u8 *actor, u32 part)
{
    const u8 *status = actor ? *(const u8 *const *)(actor + QUEST_STATUS) : 0;
    return status ? quest_look(status[QUEST_OWNER], status[QUEST_INDEX], part) : 0;
}

static u32 replaced(u32 real, u32 look)
{
    return look ? look : real;
}

/* The resolvers of CALL_SITE (r1 what the stub noted, r2 the part). */
ARM u32 felyne_actor_model(u32 real, const u8 *actor, u32 part)
{
    return replaced(real, actor_look(actor, part));
}

ARM u32 felyne_look_or_real(u32 real, const u8 *record, u32 part)
{
    return replaced(real, look_of(record, part));
}

ARM u32 felyne_record_model(u32 real, const u8 *record, u32 part)
{
    return replaced(real, enabled() ? look_of(record, part) : 0);
}

ARM u32 felyne_compact_model(u32 real, const u8 *compact, u32 part)
{
    const u8 *game = game_control;
    if (game)
        for (u32 slot = 0; slot < game[GAME_CATS]; slot++)
            if (compact == game + GAME_COMPACTS + slot * COMPACT_SIZE) {
                return replaced(real, quest_look(game[GAME_OWNERS + slot], slot, part));
            }
    return real;
}

ARM u32 felyne_quest_actor_model(u32 real, const u8 *actor, u32 part)
{
    return replaced(real, quest_actor_look(actor, part));
}

/* FUN_0030e8c0: the sound of the weapon of an actor, in a quest only: a lobby actor's status holds no owner. */
ARM u32 felyne_sound_model(u32 real, const u8 *actor, u32 part)
{
    const u8 *game = game_control;
    return game && game[GAME_STAGE] != LOBBY_STAGE ? replaced(real, quest_actor_look(actor, part)) : real;
}

/* FUN_0030ab34: r4 0 the main cat, else the second. */
ARM u32 felyne_index_model(u32 real, u32 index, u32 part)
{
    const u8 *record = index ? felyne_second_record() : felyne_main_record(save_control);
    return replaced(real, record && enabled() ? look_of(record, part) : 0);
}

/* ----- pieces the game goes by the id of ------------------------------------------------------------------- */

/* The game's functions asked of a piece's id
   read a pair [kind, 0, id], kind 0 body, 1 head, 2 weapon. Under a look they read the look's piece: the one wearing that
   number when the game has a case for it (F->cases), else id 0, which no function has a case for. */
struct piece_pair { u8 kind, pad; u16 id; };

static u32 case_piece(u32 part, u32 number)
{
    for (u32 i = 0; i < FELYNE_CASES; i++)
        if (F->cases[i].number == number && F->cases[i].part == part)
            return F->cases[i].piece;
    return 0;
}

static u32 part_of(const u8 *pair)
{
    return pair[0] == 0 ? FELYNE_BODY : pair[0] == 1 ? FELYNE_HEAD : FELYNE_WEAPON;
}

static const u8 *case_pair(struct piece_pair *own, const u8 *real, u32 look)
{
    if (!look)
        return real;
    own->kind = real[0];
    own->pad = 0;
    own->id = case_piece(part_of(real), look);
    return (const u8 *)own;
}

/* A whole-suit body hides the base's other parts and the helm: the body's look decides it, a look of the head alone
   does not (a suit draws its own head). */
static u32 suit_under(u32 real, u32 body_look)
{
    struct piece_pair own = {0, 0, 0};
    if (!body_look)
        return real;
    own.id = case_piece(FELYNE_BODY, body_look);
    return own.id ? felyne_suit(0, (const u8 *)&own) : 0;
}

ARM u32 felyne_suit_actor(u32 real, const u8 *actor, u32 part)
{
    (void)part;
    return suit_under(real, actor_look(actor, FELYNE_BODY));
}

ARM u32 felyne_suit_quest_actor(u32 real, const u8 *actor, u32 part)
{
    (void)part;
    return suit_under(real, quest_actor_look(actor, FELYNE_BODY));
}

ARM u32 felyne_suit_record(u32 real, const u8 *record, u32 part)
{
    (void)part;
    return suit_under(real, enabled() ? look_of(record, FELYNE_BODY) : 0);
}

/* FUN_00697d2c: the helm that opens and closes with the cat's actions. */
ARM u32 felyne_helm_case_quest(u32 real, const u8 *actor, u32 part)
{
    struct piece_pair own = {1, 0, 0};
    u32 look = quest_actor_look(actor, part);
    if (!look)
        return real;
    own.id = case_piece(FELYNE_HEAD, look);
    return felyne_head_case(0, (const u8 *)&own);
}

/* A piece's effect (a model group hidden, a colour, joints), in the lobby (FUN_006980bc), a quest (FUN_00697d2c,
   FUN_0097a938) and a cutscene (FUN_001a0ab8). */
ARM void felyne_effect_gate(u32 manager, const u8 *actor, u32 model, const u8 *pair)
{
    struct piece_pair own;
    felyne_effect(manager, actor, model, case_pair(&own, pair, actor_look(actor, part_of(pair))));
}

ARM u32 felyne_quest_effect_gate(u32 manager, const u8 *actor, u32 model, const u8 *pair)
{
    struct piece_pair own;
    return felyne_quest_effect(manager, actor, model, case_pair(&own, pair, quest_actor_look(actor, part_of(pair))));
}

ARM void felyne_scene_effect_gate(u32 manager, u32 model, const u8 *pair, const u8 *record)
{
    struct piece_pair own;
    felyne_scene_effect(manager, model, case_pair(&own, pair, enabled() ? look_of(record, part_of(pair)) : 0), record);
}

ARM void felyne_scene_joints_gate(u32 manager, u32 actor, const u8 *pair, const u8 *record)
{
    struct piece_pair own;
    felyne_scene_joints(manager, actor, case_pair(&own, pair, enabled() ? look_of(record, part_of(pair)) : 0), record);
}

/* FUN_00bdfba0, a slot's cat copied into its actor: that copy's record is noted, and loses its look when the slot's own
   switch is off (the slot's file holds it: no save is loaded yet). */
ARM void felyne_select_note(u8 *record, u32 slot)
{
    if (slot >= SELECT_SLOTS)
        return;
    felyne_ui.select[slot] = record;
    const u8 *slots = layered_select.slots;
    const u8 *saved = slots ? slots + slot * SLOT_SIZE + SAVE_AT : 0;
    if (!saved || saved[1] != SAVE_MAGIC || !saved[0])
        set_word(record, 0);
}

/* FUN_00c1db2c, a new cat's record written (hired, received): it starts without a look, whatever the source held. */
ARM void felyne_new_record(u8 *record, const u8 *source, u32 size)
{
    mem_copy(record, source, size);
    set_word(record, 0);
}

/* ----- the screens ---------------------------------------------------------------------------------------- */

u32 felyne_active(const u8 **cats)
{
    u32 count = 0;
    if (felyne_main_active()) {
        const u8 *second = felyne_second_record();
        cats[count++] = felyne_main_record(save_control);
        if (second)
            cats[count++] = second;
    }
    return count;
}

/* The chosen cat, read each time: 0 if there is no longer one. */
static const u8 *chosen(void)
{
    const u8 *cats[FELYNE_MAX_ACTIVE];
    u32 count = felyne_active(cats);
    return felyne_ui.cat < count ? cats[felyne_ui.cat] : 0;
}

u32 felyne_numbers(void)
{
    const u8 *cat = chosen();
    u32 numbers = 0;
    if (cat)
        for (u32 part = 0; part < FELYNE_PARTS; part++)
            numbers |= look_of(cat, part) << (part * FELYNE_NUMBER_BITS);
    return numbers;
}

void felyne_set_numbers(u32 numbers)
{
    u8 *cat = (u8 *)chosen();
    if (!cat)
        return;
    set_word(cat, marked(numbers));
    if (numbers)
        layered_state.enabled = 1;
    felyne_ui.dirty = 1;
}

/* The game's forge does this after a change of a cat's gear (FUN_00a1a464): the cat in the area, if any, takes it. */
void felyne_refresh(u32 obj)
{
    const u8 *cats[FELYNE_MAX_ACTIVE];
    u32 count = felyne_active(cats), actor;
    if (count > 0) {
        *(u8 *)(obj + OBJ_MAIN_CHANGED) = 1;
        actor = felyne_town_actor(obj, 0);
        if (actor)
            felyne_actor_update(obj, actor, cats[0]);
    }
    if (count > 1) {
        actor = felyne_second_actor(obj);
        if (actor)
            felyne_actor_update(obj, actor, cats[1]);
    }
}

/* `copy`, the chosen cat's record, wearing `numbers`. */
static int preview_record(u8 *copy, u32 numbers)
{
    const u8 *cat = chosen();
    if (!cat)
        return 0;
    layered_copy(copy, cat, RECORD_SIZE);
    set_word(copy, marked(numbers));
    return 1;
}

void felyne_preview_open(u32 obj, u32 numbers)
{
    u8 copy[RECORD_SIZE] __attribute__((aligned(8)));
    u32 frame = obj + OBJ_FRAME;
    if (!preview_record(copy, numbers))
        return;
    felyne_ui.preview = 1;
    felyne_try_on(obj, TRY_ON_NONE, 0, copy, TRY_ON_BIG);
    preview_frame_bind(frame);
    preview_frame_show(frame, 1);
    preview_frame_reset(frame);
}

int felyne_preview_loaded(u32 obj)
{
    return felyne_try_on_ready(obj);
}

/* Another look to show, once the models are loaded: the preview cat takes it (FUN_00a8a7f0's ending). */
void felyne_preview_look(u32 obj, u32 numbers)
{
    u8 copy[RECORD_SIZE] __attribute__((aligned(8)));
    u32 actor = *(u32 *)(obj + OBJ_TRY_ON_ACTOR);
    if (!actor || !preview_record(copy, numbers))
        return;
    felyne_actor_update(obj, actor, copy);
    u8 *status = *(u8 **)(actor + ACTOR_STATUS);
    *(u32 *)(status + STATUS_SETTLE_A) = SETTLE_TIME;
    *(u32 *)(status + STATUS_SETTLE_B) = SETTLE_TIME;
    status[1] = 0;
    status[5] = 0;
}

void felyne_preview_controls(u32 obj)
{
    felyne_try_on_turn(obj, 1);
}

void felyne_preview_end(u32 obj)
{
    felyne_ui.preview = 0;
    felyne_try_on_close(obj, 1);
    preview_frame_close(obj + OBJ_FRAME);
}

/* ----- the look word online (layered_online.c) ------------------------------------------------------------- */

/* The word the main cat sends the other players, or 0: no look, the switch off, or no main cat that may go on quests. */
u32 felyne_online_word(void)
{
    if (!enabled() || !felyne_main_active())
        return 0;
    const u8 *cat = felyne_main_record(save_control);
    u32 numbers = 0;
    if (cat)
        for (u32 part = 0; part < FELYNE_PARTS; part++)
            numbers |= look_of(cat, part) << (part * FELYNE_NUMBER_BITS);
    return marked(numbers);
}

/* Does this build have every number of a word that came from another player (a marked word with a look, none lacking)? */
int felyne_word_known(u32 word)
{
    if (word >> 30 != LOOK_MARK || !(word & LOOK_NUMBERS))
        return 0;
    for (u32 part = 0; part < FELYNE_PARTS; part++) {
        u32 model = number_in(word & LOOK_NUMBERS, part);
        if (model && !known(part, model))
            return 0;
    }
    return 1;
}

/* A built record of another player's cat takes its owner's word. */
void felyne_give_word(u8 *record, u32 word)
{
    set_word(record, word);
}
