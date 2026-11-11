/* Layered gear seen online, the network half (docs/equipment/
 * layered_equipment.md): every modded player sends the others its looks in a message of its own, and keeps the ones it
 * receives (by session slot) for the render to read (layered_remote_by_slot). A game without the mod drops the message at the type switch.
 *
 * Message (LOOKS_SIZE bytes): [0] 0, [1] the sender's session slot, [2] type 0x4C, [3] version, +4 the hunter's id,
 * +12 flags (bit 0 looks on, bit 1 cat word valid, bit 2 "please send yours"), +13 gender, +14 five armor models of
 * that gender (layered_state order), +24 the weapon model of each class, +38 the cat word, +42 a sequence number, +43 a
 * checksum that makes bytes [2] to [43] add up to 0. Then the tail, which a build without it never reads (it reads the
 * first LOOKS_HEAD bytes): +44 the five colours (layered_state.dye), +54 a check that makes bytes [44] to [55] add up
 * to 0, +55 0. A message of LOOKS_HEAD bytes (an earlier build's) has no colours: its looks wear their own.
 *
 * Hooks (the patcher points the game at them, equipment/layered/layered_equipment.py ONLINE_*):
 *   layered_net_gear           0x248008  FUN_00247f40, "bl FUN_00248a30": the game's "my gear changed" message to every
 *                                        member; sent as it was, then ours to every member
 *   layered_net_answer         0x2466D4  FUN_002463d8, "bl FUN_0024a2a8": a join request (kind 0) or its answer (kind 1)
 *                                        to one member; sent as it was, then ours to that member (a request carries
 *                                        "please send yours")
 *   layered_net_receive_hook   0x2497F0  FUN_002497d4, "b 0x2498A0": the dispatcher's way out for the types it does not
 *                                        know; ours is handled here, the others go on to the dispatcher's end
 * The screens call layered_net_state_left() when they close: a changed state is sent through the game's own gear
 * message (FUN_00247f40), as the hub does after a gear change, so that the hook above carries the looks.
 */

#include "layered.h"

GAME void session_send_all(u32 session, const void *buffer, u32 size);                   /* FUN_00248a30 */
GAME void session_send_to(u32 session, u32 member, const void *buffer, u32 size);        /* FUN_0024a2a8 */
GAME void gear_send(u32 session);                                                        /* FUN_00247f40 */
GAME u32 game_online(const u8 *game);                                                    /* FUN_002b5ac8 */

extern u32 session_control;      /* the variable holding the session S */

#define MSG_TYPE 0x4C
#define MSG_VERSION 1
#define MSG_ASK 4                /* flags bit 2: "please send yours" */
#define MSG_WIRE_FLAGS 3         /* the flags a receiver keeps (the others are requests, not state) */
#define SESSION_SLOT 0x87B8      /* S: the local member's slot */
#define SLOT_MASK 0x7F          /* [1] of a received message has the sender's bit 0x80 set by the game's senders */
#define SAVE_CARDS 0x85A60       /* the save object: the guild cards, GAME_CARD_SIZE each; the hunter's id at + CARD_ID */
#define SESSION_MEMBER 0x208     /* S: a member's record, from 0 (its info at + 0x87F0) */
#define MEMBER_PRESENT 0x89F2    /* S + slot * SESSION_MEMBER + this: the member is present, and its info valid */
#define MEMBER_VALID 0x89F3
#define CARD_SIZE 0x1200
#define CARD_ID 0x18C
#define GAME_CARD 0xA4           /* the game manager: which card is the local hunter's */
#define DATA_GENDER 0x18         /* the save's data: the character's gender (0 male), set from its load; the game
                                    manager's own player info (+ 0xA8) stays zero until the first quest's departure */

struct looks_msg {
    u8 zero, slot, type, version;
    u8 id[8];
    u8 flags, gender;
    u16 armor[5];
    u8 weapon[CLASSES];
    u8 cat[4];
    u8 seq, check;
    u16 dye[5];                  /* the tail */
    u8 dye_check, pad;
} __attribute__((aligned(4)));   /* on a word, as the game's own message buffers, whatever its senders copy it with */
#define LOOKS_HEAD 44            /* what every build reads */
#define LOOKS_SIZE 56
#define MSG_ARMOR 14
#define MSG_CAT 38
#define MSG_DYE 44
_Static_assert(sizeof(struct looks_msg) == LOOKS_SIZE && __builtin_offsetof(struct looks_msg, armor) == MSG_ARMOR &&
               __builtin_offsetof(struct looks_msg, cat) == MSG_CAT && __builtin_offsetof(struct looks_msg, check) == 43 &&
               __builtin_offsetof(struct looks_msg, dye) == MSG_DYE && __builtin_offsetof(struct looks_msg, dye_check) == 54,
               "the looks message");

struct remote {                  /* the variable layered_remote */
    u32 sent;                    /* the hash of the state last sent to everyone */
    u8 seq, pad[3];              /* the sequence number of the next message */
    struct layered_remote_entry entry[REMOTE_ENTRIES];
};
_Static_assert(sizeof(struct remote) == 216, "layered_remote size (game/executable/blocks.py)");
extern struct remote layered_remote;

#define FNV_PRIME ((1u << 24) + 0x193)   /* FNV-1a's 32-bit prime, written so that no game address is read in it */

static u32 state_hash(void)      /* FNV-1a of layered_state and the cat's word: has it changed since the last message to everyone? */
{
    const u8 *s = (const u8 *)&layered_state;
    u32 h = 0x811C9DC5, cat = felyne_online_word();
    for (u32 i = 0; i < sizeof layered_state; i++)
        h = (h ^ s[i]) * FNV_PRIME;
    for (u32 i = 0; i < 4; i++)
        h = (h ^ (cat >> (8 * i) & 0xFF)) * FNV_PRIME;
    return h;
}

/* ----- sending ----------------------------------------------------------------------------------------------- */

/* Our looks message; 0 if the game is not in a state to tell who we are. */
static int build(struct looks_msg *m, u32 session, u32 flags)
{
    const u8 *game = game_control;
    if (!session || !game || !save_control)
        return 0;
    layered_clear(m, sizeof *m);
    const u8 *id = (const u8 *)(save_control + game[GAME_CARD] * CARD_SIZE + SAVE_CARDS + CARD_ID);
    u32 gender = *(const u8 *)(save_control + SAVE_DATA + DATA_GENDER) != 0;
    m->slot = *(const u8 *)(session + SESSION_SLOT);
    m->type = MSG_TYPE;
    m->version = MSG_VERSION;
    for (u32 i = 0; i < 8; i++)
        m->id[i] = id[i];
    u32 cat = felyne_online_word();
    m->flags = (layered_state.enabled ? REMOTE_LOOKS : 0) | (cat ? REMOTE_CAT : 0) | flags;
    for (u32 i = 0; i < 4; i++)
        m->cat[i] = cat >> (8 * i);
    m->gender = gender;
    for (u32 part = 0; part < 5; part++)
        m->armor[part] = layered_state.armor[part][gender];
    for (u32 index = 0; index < CLASSES; index++)
        m->weapon[index] = layered_state.weapon[index];     /* the models are all below 256 (layered_equipment.py) */
    m->seq = layered_remote.seq++;
    u32 sum = 0;
    for (u32 i = 2; i < LOOKS_HEAD - 1; i++)
        sum += ((const u8 *)m)[i];
    m->check = -sum;
    sum = 0;
    for (u32 part = 0; part < 5; part++) {
        m->dye[part] = layered_state.dye[part];
        sum += (m->dye[part] & 0xFF) + (m->dye[part] >> 8);
    }
    m->dye_check = -sum;
    return 1;
}

/* After the game's message to everyone (the gear message): ours to everyone. */
ARM void layered_net_gear(u32 session, const void *buffer, u32 size)
{
    struct looks_msg m;
    session_send_all(session, buffer, size);
    if (build(&m, session, 0)) {
        layered_remote.sent = state_hash();
        session_send_all(session, &m, LOOKS_SIZE);
    }
}

/* After the game's message to one member (a join request, kind 0, or its answer, kind 1): ours to that member. */
ARM void layered_net_answer(u32 session, u32 member, const u8 *buffer, u32 size)
{
    struct looks_msg m;
    session_send_to(session, member, buffer, size);
    if (buffer[3] <= 1 && build(&m, session, buffer[3] ? 0 : MSG_ASK))
        session_send_to(session, member, &m, LOOKS_SIZE);
}

/* The screens have been left: tell the others about a change of looks (the gear message carries them). */
ARM void layered_net_state_left(void)
{
    const u8 *game = game_control;
    if (session_control && game && game_online(game) && state_hash() != layered_remote.sent)
        gear_send(session_control);
}

/* ----- receiving ----------------------------------------------------------------------------------------------- */

static int same_id(const u8 *a, const u8 *b)
{
    for (u32 i = 0; i < 8; i++)
        if (a[i] != b[i])
            return 0;
    return 1;
}

static u32 le16(const u8 *at)
{
    return at[0] | at[1] << 8;
}

/* Does this build have every look the sender wears (its gender's models, any part or class)? */
static int all_known(const struct layered_remote_entry *e)
{
    for (u32 part = 0; part < 5; part++)
        if (e->armor[part] && !known_armor(part, e->gender, e->armor[part]))
            return 0;
    for (u32 index = 0; index < CLASSES; index++)
        if (e->weapon[index] && !known_weapon(index, e->weapon[index]))
            return 0;
    return 1;
}

/* The colours of a message of `size` bytes whose head is checked: only from a whole tail that adds up, else 0 (the
   looks' own). */
static void tail_dyes(const u8 *m, u32 size, u16 *dye)
{
    u32 sum = 0;
    for (u32 i = LOOKS_HEAD; i < LOOKS_SIZE && size >= LOOKS_SIZE; i++)
        sum += m[i];
    for (u32 part = 0; part < 5; part++)
        dye[part] = size >= LOOKS_SIZE && !(sum & 0xFF) ? le16(m + MSG_DYE + 2 * part) : 0;
}

/* The message `m` of `size` bytes (its head checked) into the entry of its slot. */
static void store(const u8 *m, u32 size, struct layered_remote_entry *e)
{
    struct layered_remote_entry n;
    tail_dyes(m, size, n.dye);
    for (u32 i = 0; i < 8; i++)
        n.id[i] = m[4 + i];
    for (u32 part = 0; part < 5; part++)
        n.armor[part] = le16(m + MSG_ARMOR + 2 * part);
    for (u32 i = 0; i < CLASSES; i++)
        n.weapon[i] = m[24 + i];
    for (u32 i = 0; i < 4; i++)
        n.cat[i] = m[MSG_CAT + i];
    n.flags = m[12] & MSG_WIRE_FLAGS;
    u32 cat = n.cat[0] | n.cat[1] << 8 | n.cat[2] << 16 | (u32)n.cat[3] << 24;
    if (!(n.flags & REMOTE_CAT) || !felyne_word_known(cat)) {      /* no cat look, or one this build lacks: the cat is real, */
        n.flags &= ~REMOTE_CAT;                                      /* and the hunter's looks are judged on their own */
        for (u32 i = 0; i < 4; i++)
            n.cat[i] = 0;
    }
    n.gender = m[13] & 1;
    n.flags |= REMOTE_USED | (all_known(&n) ? REMOTE_KNOWN : 0);
    int same = (e->flags & ~REMOTE_CAT) == (n.flags & ~REMOTE_CAT) && e->gender == n.gender && same_id(e->id, n.id);
    for (u32 part = 0; part < 5; part++)
        same &= e->armor[part] == n.armor[part];
    for (u32 i = 0; i < CLASSES; i++)
        same &= e->weapon[i] == n.weapon[i];
    for (u32 part = 0; part < 5; part++)
        same &= e->dye[part] == n.dye[part];
    int same_cat = (e->flags & REMOTE_CAT) == (n.flags & REMOTE_CAT);
    for (u32 i = 0; i < 4; i++)
        same_cat &= e->cat[i] == n.cat[i];
    n.seq = m[42];
    n.changed = e->changed + !same;
    n.cat_changed = e->cat_changed + !same_cat;
    n.pad = 0;
    layered_copy(e, &n, sizeof n);
}

/* A message the dispatcher did not know (type 0x18 and up): ours is stored under the sender's slot (never our own),
   an asked-for answer goes out, only to a slot that holds a member (the slot is the sender's word: what the game's
   sender does with an empty member is not known; the game's own join answer carries our looks anyway). */
ARM void layered_net_receive(u32 session, u32 station, const u8 *buffer, u32 size)
{
    (void)station;
    if (buffer[2] != MSG_TYPE || size < LOOKS_HEAD || buffer[3] != MSG_VERSION)
        return;
    u32 slot = buffer[1] & SLOT_MASK;
    if (slot >= REMOTE_ENTRIES || slot == *(const u8 *)(session + SESSION_SLOT))
        return;
    u32 sum = 0;
    for (u32 i = 2; i < LOOKS_HEAD; i++)
        sum += buffer[i];
    if (sum & 0xFF)
        return;
    store(buffer, size, &layered_remote.entry[slot]);
    const u8 *member = (const u8 *)(session + slot * SESSION_MEMBER);
    struct looks_msg m;
    if ((buffer[12] & MSG_ASK) && member[MEMBER_PRESENT] && member[MEMBER_VALID] && build(&m, session, 0))
        session_send_to(session, slot, &m, LOOKS_SIZE);
}

__asm__(
    "   .section .text.layered_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global layered_net_receive_hook\n"
    /* FUN_002497d4's r5 = S, r4 = the buffer, r1 and r3 as called (station, size) */
    "layered_net_receive_hook:\n"
    "   mov     r0, r5\n"
    "   mov     r2, r4\n"
    "   bl      layered_net_receive\n"
    "   b       net_receive_done\n"
    "   .text\n");

/* ----- for the render ------------------------------------------------------------------------------------------ */

ARM const struct layered_remote_entry *layered_remote_by_slot(u32 slot)
{
    if (slot >= REMOTE_ENTRIES || !session_control)
        return 0;
    const u8 *member = (const u8 *)(session_control + slot * SESSION_MEMBER);
    const struct layered_remote_entry *e = &layered_remote.entry[slot];
    if (!member[MEMBER_PRESENT] || !member[MEMBER_VALID])
        return 0;
    return (e->flags & REMOTE_USED) && (e->flags & REMOTE_LOOKS) && (e->flags & REMOTE_KNOWN) ? e : 0;
}

/* ----- the looks on the other players' hunters ------------------------------------------------------------------ */

GAME u32 lobby_index(u32 session, u32 slot);                  /* FUN_0024339c: the lobby index of a slot (4 none) */
GAME u32 quest_info(const u8 *game, u32 player);              /* FUN_002b3664: the player info of a quest player */
GAME u32 town_update(u32 town);                               /* FUN_00a0050c: the hall's per-frame update */
GAME void felyne_build(u32 save, u8 *record, const u8 *compact, u32 extra);   /* FUN_00c25a3c */
GAME u32 hall_cat_actor(u32 scene, u32 kind, u32 owner);               /* FUN_009fd790: the hall cat of that owner, or 0 */
GAME void hall_cat_redress(u32 scene, u32 index, const u8 *compact);   /* FUN_00a47160 */

#define LOBBY_SLOTS 0x9010       /* S + this + lobby index: the session slot there (0xFF none) */
#define HALL_INFOS 0xA6C         /* the hall loader + this + index * INFO_SIZE: the hall copy of the member info */
#define HALL_HUNTERS 0x123C      /* the hall loader + this + index * 4: the hunter, or 0 */
#define HALL_STATES 0xA68        /* the hall loader + this: the table of the hunters' 9 load states (STATE_SIZE each) */
#define STATE_SIZE 0x1B8
#define STATE_AT 0x20
#define STATES 9
#define INFO_SIZE 0x190
#define INFO_ID 0x187
#define INFO_WEAPON 0x32         /* the info's weapon record */
#define QUEST_INFOS 0x49C        /* the game manager + slot * INFO_SIZE + this: the quest's copy of a member's info */
#define QUEST_PLAYERS 0x2E10     /* the game manager + this + player * 12: u32 session slot */
#define GAME_MODE 0x2B           /* 2 in the hall */
#define GAME_COUNT 0x2D
#define GAME_LOCAL 0x2F
#define STATUS_KIND 0x30
#define STATUS_PLAYER 0x33
#define STATUS_INFO 0x2C
#define QUEST_PLAYERS_MAX 4

struct quest_look {              /* what a quest needs of one other player's entry (14 bytes) */
    u8 flags;                    /* bit 0 held, bit 1 the gender */
    u8 weapon_class;             /* the class of the weapon its info wears (0xFF none) */
    u8 weapon;                   /* the model of that class */
    u8 pad;
    u16 armor[5];
};
struct render {                  /* the variable layered_render */
    struct quest_look quest[QUEST_PLAYERS_MAX];   /* the quest's snapshot, by player index */
    u32 quest_cat;               /* the snapshot's cat word: the other player's of a quest of two (0 none) */
    u8 seen[REMOTE_ENTRIES];     /* per slot: the entry's `changed` when its hunter was last dressed */
    u8 counted, pending;         /* bit per slot: it counted then / its hunter must be dressed again */
    u8 cat_seen[REMOTE_ENTRIES]; /* per slot: the entry's `cat_changed` when its cat was last dressed */
    u8 cat_counted;              /* bit per slot: its cat counted then */
    u8 cat_player;               /* the player index the snapshot's cat word is of */
};
_Static_assert(sizeof(struct render) == 72, "layered_render size (game/executable/blocks.py)");
extern struct render layered_render;
extern u8 *preview_mode;          /* the lobby scene object (the variable at the address of that name) */

/* The entry of `slot` when it is the member of `info` (its id is the info's): else a stale entry, no looks. */
static const struct layered_remote_entry *entry_for(u32 slot, const u8 *info)
{
    const struct layered_remote_entry *e = layered_remote_by_slot(slot);
    return e && info && same_id(e->id, info + INFO_ID) ? e : 0;
}

/* The entry as a layered_state: the armor of the sender's gender only (it sent no other). */
static void state_of(struct layered_state *out, const struct layered_remote_entry *e)
{
    layered_clear(out, sizeof *out);
    out->enabled = 1;
    for (u32 part = 0; part < 5; part++)
        out->armor[part][e->gender & 1] = e->armor[part];
    for (u32 i = 0; i < CLASSES; i++)
        out->weapon[i] = e->weapon[i];
    for (u32 part = 0; part < 5; part++)
        out->dye[part] = e->dye[part];
}

/* ----- the Felynes ------------------------------------------------------------------------------------------- */

#define SESSION_INFO 0x87F0      /* S + slot * SESSION_MEMBER + this: the member's info, as kind 1 filed it */
#define SESSION_COMPACT 0x8980   /* ... and its Felyne's compact record */

/* The cat word of an entry that holds one, whose member is present and valid and still the hunter of `info` (id); else 0.
   It does not ask for the hunter's looks: a cat is judged apart from its owner. */
static u32 cat_word(u32 slot, const u8 *info)
{
    if (slot >= REMOTE_ENTRIES || !session_control || slot == *(const u8 *)(session_control + SESSION_SLOT))
        return 0;
    const u8 *member = (const u8 *)(session_control + slot * SESSION_MEMBER);
    const struct layered_remote_entry *e = &layered_remote.entry[slot];
    if (!member[MEMBER_PRESENT] || !member[MEMBER_VALID] || !(e->flags & REMOTE_USED) || !(e->flags & REMOTE_CAT) ||
        !info || !same_id(e->id, info + INFO_ID))
        return 0;
    return e->cat[0] | e->cat[1] << 8 | e->cat[2] << 16 | (u32)e->cat[3] << 24;
}

ARM u32 layered_remote_cat(u32 slot)
{
    return slot < REMOTE_ENTRIES && session_control ? cat_word(slot, (const u8 *)(session_control + slot * SESSION_MEMBER + SESSION_INFO)) : 0;
}

/* FUN_00c25a3c's two calls for a hall cat: the game builds the record
   cleared, then a cat made from a member's compact takes that member's word. */
ARM void layered_hall_cat(u32 save, u8 *record, const u8 *compact, u32 extra)
{
    felyne_build(save, record, compact, extra);
    if (!record || !session_control)
        return;
    for (u32 slot = 0; slot < REMOTE_ENTRIES; slot++)
        if (compact == (const u8 *)(session_control + slot * SESSION_MEMBER + SESSION_COMPACT)) {
            felyne_give_word(record, layered_remote_cat(slot));
            return;
        }
}

/* A hall hunter of lobby index 1-3 and kind 1 or 3 (status): the looks of the member in that lobby slot. */
const struct layered_state *layered_hall_looks(const u8 *status, struct layered_state *out)
{
    u32 index = status[STATUS_PLAYER], kind = status[STATUS_KIND];
    if (!session_control || index < 1 || index > 3 || (kind != 1 && kind != 3))
        return 0;
    const struct layered_remote_entry *e =
        entry_for(*(const u8 *)(session_control + LOBBY_SLOTS + index), *(const u8 *const *)(status + STATUS_INFO));
    if (!e)
        return 0;
    state_of(out, e);
    return out;
}

/* The snapshot of the quest the preloader starts (player 0): each other player's entry as it is now. The hunters
   and the preloader read this copy, so that a late message cannot make them ask for different models. */
static void take_snapshot(const u8 *game)
{
    struct quest_look *q = layered_render.quest;
    layered_clear(q, sizeof layered_render.quest);
    layered_render.quest_cat = layered_render.cat_player = 0;
    signed char count = game[GAME_COUNT], local = game[GAME_LOCAL];
    for (signed char p = 0; p < count && p < QUEST_PLAYERS_MAX; p++) {
        u32 slot = *(const u32 *)(game + QUEST_PLAYERS + p * 12);
        if (p == local || slot >= REMOTE_ENTRIES)
            continue;
        const u8 *info = game + slot * INFO_SIZE + QUEST_INFOS;
        if (count == 2 && !layered_render.quest_cat) {           /* cats come with two players only */
            layered_render.quest_cat = cat_word(slot, info);
            layered_render.cat_player = p;
        }
        const struct layered_remote_entry *e = entry_for(slot, info);
        if (!e)
            continue;
        u32 index = info[INFO_WEAPON] - WEAPON_TYPE;
        q[p].flags = 1 | (e->gender & 1) << 1;
        q[p].weapon_class = index < CLASSES ? index : 0xFF;
        q[p].weapon = index < CLASSES ? e->weapon[index] : 0;
        for (u32 part = 0; part < 5; part++)
            q[p].armor[part] = e->armor[part];
    }
}

/* FUN_00bc14cc's `bl FUN_002b3664` (the preloader takes player p's info): the snapshot first, when p is 0. */
ARM u32 layered_quest_snapshot(const u8 *game, u32 player)
{
    if (player == 0)
        take_snapshot(game);
    return quest_info(game, player);
}

/* In a quest of two or more (game mode 1, 3 or 5): the snapshot is worn only
   there, never by a hunter of another scene (a guild card's, the hunter search's) or in a quest played alone. */
static int in_shared_quest(const u8 *game)
{
    u32 mode = game[GAME_MODE];
    return (mode == 1 || mode == 3 || mode == 5) && (signed char)game[GAME_COUNT] >= 2;
}

/* The other player's cat word from the snapshot, when `owner` is that player. */
u32 layered_quest_cat(u32 owner)
{
    const u8 *game = game_control;
    return game && in_shared_quest(game) && layered_render.quest_cat && layered_render.cat_player == owner
               ? layered_render.quest_cat : 0;
}

/* A quest player's looks from the snapshot, as a layered_state, or 0. The colours are the player's entry's as it is
   now (a colour asks for no model, so the snapshot needs none): none when the entry has gone. */
const struct layered_state *layered_quest_looks(u32 player, struct layered_state *out)
{
    const u8 *game = game_control;
    if (!game || !in_shared_quest(game) || player >= QUEST_PLAYERS_MAX || !(layered_render.quest[player].flags & 1))
        return 0;
    const struct quest_look *q = &layered_render.quest[player];
    layered_clear(out, sizeof *out);
    out->enabled = 1;
    for (u32 part = 0; part < 5; part++)
        out->armor[part][q->flags >> 1 & 1] = q->armor[part];
    if (q->weapon_class < CLASSES)
        out->weapon[q->weapon_class] = q->weapon;
    u32 slot = *(const u32 *)(game + QUEST_PLAYERS + player * 12);
    const struct layered_remote_entry *e =
        slot < REMOTE_ENTRIES ? entry_for(slot, game + slot * INFO_SIZE + QUEST_INFOS) : 0;
    for (u32 part = 0; e && part < 5; part++)
        out->dye[part] = e->dye[part];
    return out;
}

/* ----- dressing the hall's hunters again ------------------------------------------------------------------------ */

/* Dress the hunter of `slot` again if it can be done now. 1: done, or nothing to do (no hunter yet: it asks the looks
   when it is made); 0: the hunter is loading, try later. */
static int redress(u32 slot)
{
    u32 index = lobby_index(session_control, slot);
    const u8 *member = (const u8 *)(session_control + slot * SESSION_MEMBER);
    if (index < 1 || index > 3 || !member[MEMBER_PRESENT] || !member[MEMBER_VALID])
        return 1;
    u32 hunter = *(const u32 *)((u32)lobby_hunter_loader + HALL_HUNTERS + index * 4);
    if (!hunter)
        return 1;
    u32 kind = (*(const u8 *const *)(hunter + HUNTER_STATUS))[STATUS_KIND];
    const u8 *states = *(const u8 *const *)((u32)lobby_hunter_loader + HALL_STATES);
    if ((kind != 1 && kind != 3) || !states)
        return 1;
    states += index * STATE_SIZE + STATE_AT;
    for (u32 i = 0; i < STATES; i++)
        if (states[i] >= 2)
            return 0;
    hunter_reload(hunter, 0);
    return 1;
}

/* The cat of `slot` (hall, networked): when its word appeared, changed or went, the cat in the hall is built again with
   it, once; there is nothing to do for a cat that does not exist (it takes the word when it is made). */
static void cat_changed(u32 slot)
{
    struct render *r = &layered_render;
    u32 index = lobby_index(session_control, slot), bit = 1u << slot;
    const struct layered_remote_entry *e = &layered_remote.entry[slot];
    int live = index >= 1 && index <= 3 && layered_remote_cat(slot);
    int moved = live ? !(r->cat_counted & bit) || r->cat_seen[slot] != e->cat_changed : (r->cat_counted & bit);
    r->cat_counted = live ? r->cat_counted | bit : r->cat_counted & ~bit;
    r->cat_seen[slot] = live ? e->cat_changed : 0;
    if (!moved || index < 1 || index > 3)
        return;
    u32 hunter = *(const u32 *)((u32)lobby_hunter_loader + HALL_HUNTERS + index * 4);
    u32 kind = hunter ? (*(const u8 *const *)(hunter + HUNTER_STATUS))[STATUS_KIND] : 0;
    if ((kind == 1 || kind == 3) && hall_cat_actor((u32)preview_mode, 0, index))
        hall_cat_redress((u32)preview_mode, index, (const u8 *)(session_control + slot * SESSION_MEMBER + SESSION_COMPACT));
}

/* Every frame in the hall: which hunters' looks changed (an entry arrived, changed, or stopped counting), then the
   pending ones are dressed again. */
static void redress_changed(void)
{
    struct render *r = &layered_render;
    const u8 *game = game_control;
    if (game && game[GAME_MODE] == 2) {                 /* back in the hall: the last quest's snapshot is over */
        layered_clear(r->quest, sizeof r->quest);
        r->quest_cat = r->cat_player = 0;
    }
    if (!session_control || !game || game[GAME_MODE] != 2 || !game_online(game)) {
        r->pending = 0;
        return;
    }
    u32 own = *(const u8 *)(session_control + SESSION_SLOT);
    for (u32 slot = 0; slot < REMOTE_ENTRIES; slot++) {
        if (slot == own)
            continue;
        u32 index = lobby_index(session_control, slot), bit = 1u << slot;
        const struct layered_remote_entry *e =
            index >= 1 && index <= 3 ? entry_for(slot, (const u8 *)lobby_hunter_loader + HALL_INFOS + index * INFO_SIZE) : 0;
        if (e ? !(r->counted & bit) || r->seen[slot] != e->changed : (r->counted & bit))
            r->pending |= bit;
        r->counted = e ? r->counted | bit : r->counted & ~bit;
        r->seen[slot] = e ? e->changed : 0;
    }
    for (u32 slot = 0; slot < REMOTE_ENTRIES; slot++)
        if ((r->pending >> slot & 1) && redress(slot))
            r->pending &= ~(1u << slot);
    for (u32 slot = 0; slot < REMOTE_ENTRIES; slot++)
        if (slot != own)
            cat_changed(slot);
}

/* FUN_009d9410's `bl FUN_00a0050c` (the town's per-frame update). */
ARM u32 layered_town_frame(u32 town)
{
    u32 result = town_update(town);
    redress_changed();
    return result;
}
