/* Layered gear on the Guild Card: a unit of the block
 * layered_selector.
 *
 * The card's 3D hunter is a lobby hunter (status + 0x30 kind 2, + 0x33 index 4) that FUN_009fbd08 builds from the static
 * info `card_hunter_info`, which FUN_009b9f30 fills from the card shown (its `bl` at 0x9FBD80, layered_card_info). Its
 * models go through the getters' stubs like every lobby hunter's, so looks_of only has to tell it apart and say what it
 * wears: the own card the looks worn now, another hunter's card the looks its card carries.
 *
 * The looks travel inside the card: CARD_LOOKS_SIZE bytes at + CARD_LOOKS, a range of the 0x1200 no code of the game
 * reads or writes, which the game sends with the card and every receiver keeps whole in its book. layered_card_store()
 * keeps the own card's block equal to what the hunter wears, every town
 * frame; a card of a game without the mod has zeros there (no magic: real gear), and a block naming a look this build
 * lacks shows all the card's real gear, never a mix (the game would wait for a file that does not exist).
 */

#include "layered.h"

GAME void card_to_info(u32 screen, const u8 *card, u8 *info);   /* FUN_009b9f30: the card shown -> its hunter's info */
extern u8 card_hunter_info[];    /* the static info FUN_009fbd08 builds the card's hunter from */

#define SAVE_CARDS 0x85A60       /* the save object: the own cards, CARD_SIZE each, one per slot */
#define CARD_SIZE 0x1200
#define GAME_CARD 0xA4           /* the game manager: the slot in play, so its card */
#define DATA_GENDER 0x18         /* the save's data: the character's gender (0 male) */
#define CARD_KIND 2              /* status + 0x30 of the card's hunter (no other hunter has it) */
#define CARD_INDEX 4             /* status + 0x33 */
#define ST_KIND 0x30
#define ST_INDEX 0x33
#define ST_INFO 0x2C
#define CARD_LOOKS 0x11D0        /* the block in the card */
#define LOOKS_MAGIC_0 'H'
#define LOOKS_MAGIC_1 'L'
#define LOOKS_VERSION 1
#define LOOKS_ON 1               /* flags bit 0: the hunter wears its looks (clear: real gear, Layered Gear's switch off) */

struct card_looks {              /* */
    u8 magic[2], version, flags;
    u8 gender, pad;              /* 1 female: the armor models are that gender's */
    u16 armor[5];                /* layered_state order; 0 none, NO_ARMOR */
    u8 weapon[CLASSES];          /* the model of each class (all below 256: layered_equipment.py _wire_model) */
    u16 dye[5];                  /* layered_state.dye */
    u8 cat[4];                   /* reserved for the main cat's look word: 0 */
    u8 pad2[3], check;           /* the 48 bytes add up to 0 modulo 256 */
};
#define CARD_LOOKS_SIZE 0x30
_Static_assert(sizeof(struct card_looks) == CARD_LOOKS_SIZE && __builtin_offsetof(struct card_looks, armor) == 6
               && __builtin_offsetof(struct card_looks, weapon) == 0x10 && __builtin_offsetof(struct card_looks, dye) == 0x1E
               && __builtin_offsetof(struct card_looks, check) == 0x2F, "the card's looks");

struct card {                    /* the variable layered_card */
    const u8 *shown;             /* the card the card's hunter was last built from (FUN_009b9f30's) */
    u32 pad;
};
_Static_assert(sizeof(struct card) == 8, "layered_card size (game/executable/blocks.py)");
extern struct card layered_card;

/* The own card of the slot in play, or 0 with no save or game. */
static u8 *own_card(void)
{
    const u8 *game = game_control;
    if (!game || !save_control)
        return 0;
    return (u8 *)save_control + SAVE_CARDS + game[GAME_CARD] * CARD_SIZE;
}

static u32 byte_sum(const u8 *at, u32 size)
{
    u32 sum = 0;
    while (size--)
        sum += *at++;
    return sum & 0xFF;
}

/* What the hunter wears now, as its card carries it. */
static void card_build(struct card_looks *b)
{
    layered_clear(b, sizeof *b);
    u32 female = *(const u8 *)(save_control + SAVE_DATA + DATA_GENDER) != 0;
    b->magic[0] = LOOKS_MAGIC_0;
    b->magic[1] = LOOKS_MAGIC_1;
    b->version = LOOKS_VERSION;
    b->gender = female;
    if (layered_state.enabled && layered_shown()) {
        b->flags = LOOKS_ON;
        for (u32 part = 0; part < 5; part++) {
            b->armor[part] = layered_state.armor[part][female];
            b->dye[part] = layered_state.dye[part];
        }
        for (u32 i = 0; i < CLASSES; i++)
            b->weapon[i] = (u8)layered_state.weapon[i];
    }
    b->check = (u8)-byte_sum((const u8 *)b, CARD_LOOKS_SIZE - 1);
}

/* Every town frame (layered_town_frame): the own card's block is what the hunter wears, so a card sent or saved carries
   it. Written only when it changed. */
void layered_card_store(void)
{
    u8 *card = own_card();
    if (!card)
        return;
    struct card_looks b;
    card_build(&b);
    u8 *at = card + CARD_LOOKS;
    const u8 *built = (const u8 *)&b;
    for (u32 i = 0; i < CARD_LOOKS_SIZE; i++)
        if (at[i] != built[i]) {
            layered_copy(at, &b, CARD_LOOKS_SIZE);
            return;
        }
}

/* FUN_009fbd08's `bl FUN_009b9f30` (a card's hunter is built): the game's call, and the card is noted. */
ARM void layered_card_info(u32 screen, const u8 *card, u8 *info)
{
    layered_card.shown = card;
    card_to_info(screen, card, info);
}

/* Is `st` the card's hunter? */
int layered_card_hunter(const u8 *st)
{
    return st[ST_KIND] == CARD_KIND && st[ST_INDEX] == CARD_INDEX && *(const u32 *)(st + ST_INFO) == (u32)card_hunter_info;
}

/* The looks of the card's hunter: the own card's, the looks worn now; another card's, its block in `out`; or 0 (no
   block, a bad one, looks off, or a look this build lacks: the card's real gear). The switch is the caller's. */
const struct layered_state *layered_card_looks(struct layered_state *out)
{
    const u8 *card = layered_card.shown;
    if (!card)
        return 0;
    if (card == own_card())
        return layered_state.enabled ? &layered_state : 0;
    struct card_looks b;
    layered_copy(&b, card + CARD_LOOKS, CARD_LOOKS_SIZE);
    if (b.magic[0] != LOOKS_MAGIC_0 || b.magic[1] != LOOKS_MAGIC_1 || b.version != LOOKS_VERSION
        || byte_sum((const u8 *)&b, CARD_LOOKS_SIZE) || !(b.flags & LOOKS_ON))
        return 0;
    u32 female = b.gender & 1;
    layered_clear(out, sizeof *out);
    for (u32 part = 0; part < 5; part++) {
        if (b.armor[part] && !known_armor(part, female, b.armor[part]))
            return 0;
        out->armor[part][female] = b.armor[part];
        out->dye[part] = b.dye[part];
    }
    for (u32 i = 0; i < CLASSES; i++) {
        if (b.weapon[i] && !known_weapon(i, b.weapon[i]))
            return 0;
        out->weapon[i] = b.weapon[i];
    }
    out->enabled = 1;
    return out;
}
