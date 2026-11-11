/* The forge-style screens of layered gear: a unit of the
 * block layered_selector, run from layered_update in the Smithy's state 3.
 *
 * One screen for armor, weapons of one class and Felynes: the model and the game's materials box on the left; on the
 * right a rank row, a game row and a list of looks with their buttons. The panes are five hidden root groups of ui401
 * (equipment/layered/menu_layout.py), found by their names' hashes when something changes: nothing is cached, and a key
 * that changes nothing draws nothing. What a look is, when it appears and what it costs come from the blocks layered_data
 * and layered_rules; a look bought is a bit of the zone in the game's own save data. What the model wears is
 * layered_preview: the looks worn plus the try-ons, so a try-on needs no memory but the difference.
 */

#include "layered.h"

#define PAD_HELD 0x340                 /* in the pad object: the GUI's buttons held, */
#define PAD_PRESSED 0x348              /* and those pressed this frame */
#define PAD_GAME_PRESSED 0x310         /* u16: the game layout's buttons pressed this frame */
#define GAME_KICK 0x1                  /* in it, what Select gives in a town (gameplay/select_kick/select_kick.c) */
#define DIR_ALL (DIR_UP | DIR_DOWN | DIR_LEFT | DIR_RIGHT)
#define DIR_VERTICAL (DIR_UP | DIR_DOWN)
#define HELD_MAX 0xFFFF                /* layered_ui.held stops counting there */
extern u8 *pad_control;

GAME u32 facility_pressed(u32 obj, u32 bits);                          /* FUN_009ac3a4 */
GAME void preview_touch(u32 obj);                                      /* FUN_00a272b0: the frame's touch buttons */
GAME void model_frame(void);                                           /* FUN_002727c8: ui034's frame, its L, R and stick */
GAME u32 facility_dirs(u32 obj);                                       /* FUN_009b3830: pressed or repeating */
GAME void text_common(void *ref, u32 file, u32 message);               /* FUN_005a9164 */
GAME void icon_draw(u32 gui, void *sprite, u32 icon, const u32 *colour);  /* FUN_00c118f4: UV and colours */
GAME void materials_box(u32 obj);                                      /* FUN_009f6c10: the rows at *(obj + 0xB8FC) */
GAME void forge_hide(u32 obj);                                         /* FUN_00a1c640 */
GAME void money_write(u32 obj, u32 money, u32 one);                    /* FUN_00a52860 */
GAME void money_show(u32 obj, u32 shown, u32 zero);                    /* FUN_00a5d424 */
GAME void window_open(u32 kind, u32 slot, u32 type, u32 first);        /* FUN_002921cc: type 4 is yes / no */
GAME void window_update(void);                                         /* FUN_002a2414 */
GAME void window_close(u32 kind, u32 slot);                            /* FUN_0029e5bc */
GAME u32 window_input(u32 obj);                                        /* FUN_00aa6480 */
GAME u32 window_answer(u32 obj, u32 at, u32 input, u32 mask);          /* FUN_00a66e60: 1 yes, 2 no */
GAME void hammer_scene(u32 scene, u32 kind);                           /* FUN_009d61e4 */
GAME u32 hammer_scene_busy(u32 scene);                                 /* FUN_009bf778: not 0 once it has ended */
GAME u32 hammer_kind(u32 obj);                                         /* FUN_00a92af0 */
GAME void smithy_panel(u32 obj, u32 shown, u32 zero);                  /* FUN_00296248 */
GAME void smithy_panel_b(u32 obj, u32 shown);                          /* FUN_0029e484 */
GAME void smithy_panel_c(u32 obj, u32 shown);                          /* FUN_00a8e230 */
GAME void money_add(u32 save, int amount);                             /* FUN_00c27764 */
GAME void item_take(u32 obj, u32 item, u32 quantity);                  /* FUN_00aab06c: the box first, then the pouch */
GAME u32 item_count(u32 save, u32 item);                               /* FUN_00c21b18: the pouch and the box */
GAME u32 item_seen(u32 save, const u8 *data, u32 item);                /* FUN_00c1bef8 */
GAME u32 quest_cleared(u32 save, u32 quest);                           /* FUN_00c21fe0: non-zero if cleared */
GAME u32 story_flag(u32 save, u32 flag);                               /* FUN_00c1c278: non-zero if set */
GAME void make_record(u32 equipment, u8 *out, u32 type, u32 id);       /* FUN_002f2aa4 */
GAME void preview_start(u32 obj, const u8 *record, u32 mode);          /* FUN_009edcec: 1 armor, 2 weapon */
GAME u32 preview_ready(u32 obj, u32 hunter);                           /* FUN_00a64e9c: every part loaded */
GAME void viewport_close(u32 viewport);                                /* FUN_00c00ec8 */
GAME void preview_rotate(u32 obj, u32 hunter);                         /* FUN_00aabb8c */
GAME u32 preview_stick(u32 obj);                                       /* FUN_009ad458 */
GAME u32 camera_controls(u32 camera, u32 buttons, u32 stick);          /* FUN_00c05990 */
GAME void camera_control_set(u32 camera, u32 controls);                /* FUN_00c056c4 */
GAME void sub_view_open(u32 camera, u32 target, const int *rect, const u32 *clear, u32 layer,
                        u32 priority);                                 /* FUN_00c042ec */
GAME void palette_colour(u8 *rgba, u32 gui, u32 index);                /* FUN_00c0e3c8: the pigment's palette */
GAME u32 sprite_texture(const struct ref *r);                          /* FUN_00ae5254 */
GAME void texel_colour(u8 *rgba, u32 gui, u32 texture, const int *xy); /* FUN_00d0d76c */

extern u8 *preview_mode;           /* + 0x6C: 1 / 2 while a preview is shown */
extern u32 camera_control;

#define U (&layered_ui)
#define P (&layered_preview)
#define FS (&D->screen)

enum { G_LEFT, G_RIGHT, G_ROWS, G_KEYS, G_CURSOR, G_CUE, GROUPS };
#define MAX_ROWS 9
#define ARMOR_ROWS 5             /* rows with six buttons' panes; the others have one */
#define ROW_BUTTONS 6
#define ALL_GREY 0xFFFu
#define BOX_ROWS 3               /* the game's box on a screen: two materials and the price; all the rows it has, its
                                    panes' counts: */
#define BOX_ALL_ROWS 4
#define BOX_FRAME 4
#define BOX_LINES 5
#define BOX_LINES_KEPT (1 + BOX_ROWS)   /* the title's and the rows' */
#define BOX_TITLE 2
#define BOX_ROW_PANES 4
#define BOX_IS_CUT 1             /* layered_ui.box_cut */
#define BOX_LINE_SHOWN 2
#define BOX_PRICE_ROW 2          /* the box's third row: the price, without the icon and the count's box */
#define BOX_PRICE_SHOWN 8        /* layered_ui.box_cut: the icon's and the count box's bits as the file had them */
#define BOX_GREY 0xFF646464u     /* FUN_009f6c10's colours: a material short, */
#define BOX_WHITE 0xFFF0F0F0u    /* and one there */
#define KITCHEN 0xA              /* Kitchen among the lobby's message files: */
#define MSG_COST 34              /* "Cost" */
#define MSG_COST_ZENNY 36        /* the number in slot TEXT_SLOT, then "z" */
#define GREY_BIT(rank, game) (1u << ((rank) * GAME_VALUES + (game)))
#define CUSTOM_NAME 0x8000       /* a weapon name that is an E_makeshop message, not the weapon's own */
#define WEAPON_NAMES 27          /* LswordName: the first weapon name list among the common files */
#define TEXT_SLOT 0              /* the text renderer's string slot: a price, the counter */
#define MSG_PRICE 0x2B           /* E_makeshop: use the required materials and create for z? */
#define MSG_EQUIP_NOW 44         /* E_makeshop: "Equip now?", the forge's question after a purchase */
#define ITEMBOX 0x16             /* ItemBox among the lobby's message files: the words of the game's View Mode */
#define MSG_CAMERA_HELP 0x9F     /* Move the Circle Pad Up/Down to pan the camera, and Left/Right to rotate the character. */
#define MSG_CAMERA 0xA1          /* Camera: the game's "START Camera" */
#define MSG_SHOW_MENU 0xAF       /* Show Menu: the game's "START Show Menu" */
#define MSG_DYE_HELP 0x9A        /* Select a new color. (the Armor Pigment's colour page) */
#define MSG_DYE_TARGET 0x2B      /* Change All, then Head, Chest, Arms, Waist, Legs: the targets' order */
#define MSG_DEFAULT 0x32         /* Default */
#define MSG_COLOR 0x31           /* Color: SELECT's cue */
#define SOUND_CAMERA_ON 2        /* as FUN_00a93250 enters and leaves the View Mode */
#define SOUND_CAMERA_OFF 6
#define ANSWER_ANY 0xFFFF

#define OBJ_RECIPE 0xB8FC        /* the facility object: the materials box's rows, */
#define OBJ_ANSWER 0xB95C        /* the window's answer, */
#define OBJ_FORGER 0xB968        /* the forge's blacksmith: + 0xE2C + 0x2C its kind */
#define OBJ_CAMERA_TARGET 0x70
#define SMITH_STATUS 0xE2C
#define SMITH_KIND 0x2C
#define SMITH_HAMMER 'H'
#define HAMMER_ALONE 3           /* FUN_009d61e4's kind for that blacksmith; else hammer_kind() picks 1 or 2 */
#define SAVE_MONEY 0x90          /* the save object: zenny; its data: */
#define DATA_GENDER 0x18         /* 0 male */
#define DATA_GEAR_BITS 0xCE14    /* "had it once", as FUN_00c1fe40 reads it */
#define CAMERA_LAYER 0xE         /* as FUN_009edcec */
#define CAMERA_PRIORITY 0x32
#define CAMERA_PRESET 0x166C     /* sCamera: the preset, its keys, its copy to the camera pending (FUN_00c01518) */
#define TARGET_FAR 0x30          /* the camera it serves */
#define TARGET_NEAR 0x34
#define TARGET_FOV 0x3C
#define PREVIEW_ARMOR 1
#define PREVIEW_WEAPON 2
#define ARMOR_PARTS 5

/* A button of an armor look -> its part in layered_state; 0 is the whole look. */
static const u8 button_part[ROW_BUTTONS - 1] = {4, 0, 1, 2, 3};

struct look {
    u32 catalog, at;             /* 0 MH4U, 1 XX; its place in it */
    union {
        const struct set *set;
        const struct weapon *weapon;
        const struct felyne_row *row;
    } on;
    const struct parts *own;     /* an XX set's models */
};

/* ----- the looks ------------------------------------------------------------------------------------------- */

static u32 class_of(void)
{
    return D->chooser_weapons[U->class_index];
}

static u32 first_catalog(void)
{
    return U->mode == M_ARMOR ? D->catalogs[0].set_count : D->catalogs[0].weapon_count[class_of()];
}

static u32 rows_total(void)
{
    if (U->mode == M_FELYNE)
        return R->rows_count;
    return first_catalog() + (U->mode == M_ARMOR ? D->catalogs[1].set_count : D->catalogs[1].weapon_count[class_of()]);
}

static void look_at(u32 pos, struct look *l)
{
    if (U->mode == M_FELYNE) {
        l->at = pos;
        l->on.row = (const struct felyne_row *)(layered_rules + R->felyne_rows) + pos;
        l->catalog = l->on.row->game;
        return;
    }
    u32 first = first_catalog();
    l->catalog = pos >= first;
    l->at = l->catalog ? pos - first : pos;
    const struct catalog *k = &D->catalogs[l->catalog];
    if (U->mode == M_ARMOR) {
        l->on.set = (const struct set *)(layered_data + k->sets_offset) + l->at;
        l->own = k->parts_offset ? (const struct parts *)(layered_data + k->parts_offset) + l->at : 0;
    } else {
        l->on.weapon = (const struct weapon *)(layered_data + k->weapon_offset[class_of()]) + l->at;
    }
}

/* RANK_LOW, RANK_HIGH or RANK_G. */
static u32 rank_of(const struct look *l)
{
    if (U->mode == M_ARMOR)
        return (l->on.set->flags >> SET_RANK_SHIFT) - 1;
    return (U->mode == M_WEAPON ? l->on.weapon->rank : l->on.row->rank) - 1u;
}

static u32 armor_model_of(const struct look *l, u32 part, u32 female)
{
    if (!(l->on.set->parts >> part & 1))
        return NO_ARMOR;
    if (l->own)
        return l->own->models[part][female];
    return female ? l->on.set->female : l->on.set->male;
}

static const u8 *game_data(void)
{
    return (const u8 *)save_control + SAVE_DATA;
}

static u32 hunter_female(void)
{
    return game_data()[DATA_GENDER] != 0;
}

/* Has the hunter's gender a model of this part of the armor look? NO_ARMOR on a part the look has is one: "Nothing"'s
   (looks.py NOTHING_KEY), the game's underwear. */
static int part_fits(const struct look *l, u32 part, u32 female)
{
    return l->on.set->parts >> part & 1 && armor_model_of(l, part, female);
}

/* Has the hunter's gender a model of this armor look at all? */
static int fits_gender(const struct look *l, u32 female)
{
    for (u32 part = 0; part < ARMOR_PARTS; part++)
        if (part_fits(l, part, female))
            return 1;
    return 0;
}

/* A condition list (layered_rules.py): any condition that holds shows the look. */
static int rule_holds(u32 word, u32 female)
{
    const u16 *w = (const u16 *)(layered_rules + R->conds) + word;
    const u8 *data = game_data();
    for (; *w; w++) {
        if (*w == RULE_ALWAYS)
            return 1;
        if (*w & RULE_GEAR) {
            u32 bit = *w & ~RULE_GEAR;
            if (data[DATA_GEAR_BITS + (bit >> 3)] >> (bit & 7) & 1)
                return 1;
        } else if (!(*w & (female ? RULE_MALE : RULE_FEMALE)) && item_seen(save_control, data, *w & RULE_ITEM)) {
            return 1;
        }
    }
    return 0;
}

/* The highest rank the player has reached: RANK_LOW, RANK_HIGH once any entry of the header's first unlock list holds
   (a quest cleared, or a story flag set), RANK_G once any of the second does. */
static u32 unlocked_rank(void)
{
    u32 rank = RANK_LOW;
    for (u32 list = 0; list < RANKS - 1; list++)
        for (u32 i = 0; i < UNLOCK_ROOM && R->unlock[list][i]; i++) {
            u32 entry = R->unlock[list][i];
            u32 done = entry == UNLOCK_OPEN ? 1
                     : entry & UNLOCK_FLAG ? story_flag(save_control, entry & ~UNLOCK_FLAG)
                                           : quest_cleared(save_control, entry);
            if (done && list + 1 > rank)
                rank = list + 1;
        }
    return rank;
}

/* The look's rule: the word index of its condition list, parallel to its catalog (layered_rules.py). */
static u32 rule_of(const struct look *l)
{
    u32 offset = U->mode == M_ARMOR ? R->armor_rules[l->catalog]
               : U->mode == M_WEAPON ? R->weapon_rules[l->catalog][class_of()] : R->felyne_rules;
    return ((const u16 *)(layered_rules + offset))[l->at];
}

/* A look is listed (and so can be tried on) only once its rank is open and its rule holds; on the Relics screens every
   relic of the ranks open is (its rule says it is bought: owned). */
static int look_shown(const struct look *l, u32 female)
{
    if (rank_of(l) > U->unlocked)
        return 0;
    if (U->mode == M_ARMOR && !fits_gender(l, female))
        return 0;
    return U->relics || rule_holds(rule_of(l), female);
}

/* The list's order (look_order.py: by monster, least to most powerful, then rank, game, price): one u16 entry per look,
   its position over both catalogs. */
static const u16 *list_order(void)
{
    u32 offset = U->mode == M_ARMOR ? R->armor_order : U->mode == M_WEAPON ? R->weapon_order[class_of()] : R->felyne_order;
    return (const u16 *)(layered_rules + offset);
}

/* An order entry of this screen: a relic's (ORDER_RELIC) on the Relics screens, any other look's on the others. */
static int on_screen(u32 entry)
{
    return !(entry & ORDER_RELIC) == !U->relics;
}

/* A bit of the result (GREY_BIT) for each pair of filters with no row. */
static u32 grey_mask(void)
{
    u32 filled = 0, female = hunter_female(), total = rows_total();
    const u16 *order = list_order();
    struct look l;
    for (u32 i = 0; i < total; i++) {
        if (!on_screen(order[i]))
            continue;
        look_at(order[i] & ORDER_POSITION, &l);
        u32 rank = rank_of(&l), bits = GREY_BIT(rank, l.catalog) | GREY_BIT(rank, GAME_ALL) | GREY_BIT(RANK_ALL, l.catalog)
                                       | GREY_BIT(RANK_ALL, GAME_ALL);
        if ((filled & bits) != bits && look_shown(&l, female))
            filled |= bits;
    }
    return ~filled & ALL_GREY;
}

/* The rows of the filters in the list's order; a look of ORDER_EVERY ("Nothing") under every filter. In `out` the
   positions of `room` of them from the `first`; the result is how many there are in all, or, when not `count`, the
   scan stops once `out` is full. */
static u32 scan_rows(u32 first, u16 *out, u32 room, int count)
{
    u32 found = 0, female = hunter_female(), total = rows_total();
    const u16 *order = list_order();
    struct look l;
    for (u32 i = 0; i < total; i++) {
        if (!on_screen(order[i]))
            continue;
        u32 pos = order[i] & ORDER_POSITION;
        look_at(pos, &l);
        if (!(order[i] & ORDER_EVERY)
            && ((U->rank != RANK_ALL && rank_of(&l) != U->rank) || (U->game != GAME_ALL && U->game != l.catalog)))
            continue;
        if (!look_shown(&l, female))
            continue;
        if (found >= first && found - first < room)
            out[found - first] = pos;
        found++;
        if (!count && found >= first + room)
            return found;
    }
    return found;
}

/* The look under the cursor. */
static void current(struct look *l)
{
    u16 pos = 0;
    scan_rows(U->index, &pos, 1, 0);
    look_at(pos, l);
}

/* ----- bought, worn --------------------------------------------------------------------------------------- */

/* The owned bits' zone in the game's data (layered_rules.py, ZONE_AT). */
static u8 *owned_zone(void)
{
    return (u8 *)game_data() + R->zone_at;
}

/* A look's owned bit: a model, never its place in the catalog, so a build ordering its looks otherwise reads what an
   earlier one bought. Armor by the block's table (the male model, the female's for a look with none; an XX set's series
   model), a weapon by its class' table and model, a Felyne row by its model number. */
static u8 *owned_at(const struct look *l, u32 *mask)
{
    u8 *zone = owned_zone();
    u32 number;
    if (U->mode == M_ARMOR) {
        zone += R->zone_armor[l->catalog];
        number = ((const u16 *)(layered_rules + R->armor_bits[l->catalog]))[l->at];
    } else if (U->mode == M_WEAPON) {
        zone += R->zone_weapons[class_of()];
        number = l->on.weapon->model;
    } else {
        zone += R->zone_felyne;
        number = l->on.row->number;
    }
    *mask = 1u << (number & 7);
    return zone + (number >> 3);
}

/* What the look costs: its recipe, by the index that runs parallel to the catalog's rules. */
static const struct recipe *recipe_of(const struct look *l)
{
    u32 offset;
    if (U->mode == M_ARMOR)
        offset = R->armor_recipes[l->catalog];
    else if (U->mode == M_WEAPON)
        offset = R->weapon_recipes[l->catalog][class_of()];
    else
        offset = R->felyne_recipes;
    return (const struct recipe *)(layered_rules + R->recipes) + ((const u16 *)(layered_rules + offset))[l->at];
}

/* What the look costs in zenny: a u32 parallel to the catalog's rules (layered_rules.py, zenny.py), at most six digits. */
static u32 price_of(const struct look *l)
{
    u32 offset;
    if (U->mode == M_ARMOR)
        offset = R->armor_zenny[l->catalog];
    else if (U->mode == M_WEAPON)
        offset = R->weapon_zenny[l->catalog][class_of()];
    else
        offset = R->felyne_zenny;
    return ((const u32 *)(layered_rules + offset))[l->at];
}

/* No material and no zenny: the look is free, and the screen shows it as bought (its bit is never set). */
static int is_free(const struct look *l)
{
    const struct recipe *recipe = recipe_of(l);
    return !price_of(l) && !recipe->materials[0].item && !recipe->materials[1].item;
}

/* Bought: its owned bit set, free, or on the Relics screens a relic the hunter has had (its rule holds). */
static int owned(const struct look *l)
{
    u32 mask;
    return *owned_at(l, &mask) & mask || is_free(l) || (U->relics && rule_holds(rule_of(l), hunter_female()));
}

static int money_short(u32 price)
{
    return *(u32 *)(save_control + SAVE_MONEY) < price;
}

/* The forge pays only when the money and each material are there (FUN_009be7bc, mode 0, bits 4 and 8). */
static int can_pay(const struct look *l)
{
    const struct recipe *recipe = recipe_of(l);
    if (money_short(price_of(l)))
        return 0;
    for (u32 i = 0; i < 4; i++)
        if (recipe->materials[i].item && item_count(save_control, recipe->materials[i].item) < recipe->materials[i].quantity)
            return 0;
    return 1;
}

/* What a button of a look covers, as bits of parts (layered_state's order, or the look word's for a Felyne). A whole set
   covers every part: it shows nothing where it has no piece. */
static u32 parts_of(const struct look *l, u32 button)
{
    if (U->mode == M_FELYNE)
        return button ? 1u << (button - 1) : l->on.row->parts;
    if (button)
        return 1u << button_part[button - 1];
    return l->on.set->flags & SET_WHOLE ? (1u << ARMOR_PARTS) - 1 : l->on.set->parts;
}

static int button_enabled(const struct look *l, u32 button)
{
    if (!button || U->mode == M_WEAPON)
        return 1;
    if (U->mode == M_FELYNE)
        return l->on.row->parts >> (button - 1) & 1;
    return part_fits(l, button_part[button - 1], hunter_female());
}

static int armor_is(const struct layered_state *st, const struct look *l, u32 button)
{
    u32 parts = parts_of(l, button);
    for (u32 part = 0; part < ARMOR_PARTS; part++)
        if (parts >> part & 1)
            for (u32 female = 0; female < 2; female++)
                if (st->armor[part][female] != armor_model_of(l, part, female))
                    return 0;
    return 1;
}

/* A part that changes its look (or takes it off) goes back to the look's own colour; one that keeps it keeps its colour. */
static void armor_set(struct layered_state *st, const struct look *l, u32 button, int on)
{
    u32 parts = parts_of(l, button);
    for (u32 part = 0; part < ARMOR_PARTS; part++)
        if (parts >> part & 1)
            for (u32 female = 0; female < 2; female++) {
                u32 model = on ? armor_model_of(l, part, female) : 0;
                if (st->armor[part][female] != model)
                    st->dye[part] = DYE_OWN;
                st->armor[part][female] = model;
            }
}

static u32 cat_fields(u32 parts)
{
    u32 mask = 0;
    for (u32 part = 0; part < FELYNE_PARTS; part++)
        if (parts >> part & 1)
            mask |= FELYNE_NUMBER_MASK << (part * FELYNE_NUMBER_BITS);
    return mask;
}

/* `numbers` with the fields of the button's parts taken from the look, or `other` when not `on`. */
static u32 cat_set(u32 numbers, const struct look *l, u32 button, int on, u32 other)
{
    u32 mask = cat_fields(parts_of(l, button));
    u32 number = l->on.row->number;
    u32 look = number | number << FELYNE_NUMBER_BITS | number << (2 * FELYNE_NUMBER_BITS);
    return (numbers & ~mask) | ((on ? look : other) & mask);
}

static int worn(const struct look *l, u32 button)
{
    if (U->mode == M_WEAPON)
        return layered_state.weapon[class_of()] == l->on.weapon->model;
    if (U->mode == M_FELYNE) {
        u32 numbers = felyne_numbers();
        return cat_set(numbers, l, button, 1, 0) == numbers;
    }
    return armor_is(&layered_state, l, button);
}

/* Does the model wear what the look's button covers, tried on? Not on weapons: there the model follows the cursor. */
static int on_model(const struct look *l, u32 button)
{
    if (U->mode == M_WEAPON)
        return 0;
    if (U->mode == M_FELYNE)
        return cat_set(P->on.cat_numbers, l, button, 1, 0) == P->on.cat_numbers;
    return armor_is(&P->state, l, button);
}

/* The look's button goes on or off what is worn, and what the model wears follows. */
static void wear(const struct look *l, u32 button, int on)
{
    struct preview *p = P;
    if (U->mode == M_WEAPON) {
        u32 model = on ? l->on.weapon->model : 0;
        layered_state.weapon[class_of()] = model;
        p->state.weapon[class_of()] = model;
    } else if (U->mode == M_FELYNE) {
        u32 numbers = cat_set(felyne_numbers(), l, button, on, 0);
        felyne_set_numbers(numbers);
        p->on.cat_numbers = cat_set(p->on.cat_numbers, l, button, on, 0);
    } else {
        armor_set(&layered_state, l, button, on);
        armor_set(&p->state, l, button, on);
        u32 parts = parts_of(l, button);   /* a try-on of the look worn now brings its colour along */
        for (u32 part = 0; part < ARMOR_PARTS; part++)
            if (parts >> part & 1)
                layered_state.dye[part] = p->state.dye[part];
    }
    if (on)
        layered_state.enabled = 1;
    p->pushed = 1;
}

/* ----- the panes ------------------------------------------------------------------------------------------- */

static u32 float_bits(int value)
{
    return kit_float_bits(value);
}

static u32 group_named(u32 hash)
{
    return kit_group(hash);
}

static u32 group_of(u32 which)
{
    return kit_group(FS->groups[which]);
}

static u32 *sprite_of(struct ref *r, u32 group, u32 hash)
{
    return kit_sprite(r, group, FS->hashes[hash]);
}

static void sprite_changed(const struct ref *r)
{
    kit_sprite_changed(r);
}

/* The sprite on, its top left corner at the screen pixel (x, y). */
static u32 *sprite_place(struct ref *r, u32 group, u32 hash, int x, int y, u32 w, u32 h)
{
    return kit_sprite_place(r, group, FS->hashes[hash], x, y, w, h);
}

static void sprite_hide(u32 group, u32 hash)
{
    kit_sprite_hide(group, FS->hashes[hash]);
}

static void sprite_colour(u32 *sprite, u32 colour)
{
    kit_sprite_colour(sprite, colour);
}

static u32 *text_of(struct ref *r, u32 group, u32 hash)
{
    return kit_text(r, group, FS->hashes[hash]);
}

static void text_changed(const struct ref *r)
{
    kit_text_changed(r);
}

static void text_colour(u32 *text, u32 colour)
{
    kit_text_colour(text, colour);
}

static void text_hide(u32 group, u32 hash)
{
    kit_text_hide(group, FS->hashes[hash]);
}

static void screen_group_show(u32 which, u32 shown)
{
    kit_group_show(group_of(which), shown, FS->priority[which]);
}

static void groups_show(u32 shown)
{
    for (u32 i = 0; i < GROUPS; i++)
        screen_group_show(i, shown);
}

/* ----- the game's materials box ---------------------------------------------------------------------------- */

/* Two rows of materials fit under the larger model. The box's panes stay as the layout has them for the real forge, which
   shows four rows: a screen moves them by a difference, and the same difference brings them back wherever they were. */

ARM static u32 float_add(u32 bits, int delta)
{
    union { u32 bits; float value; } number = {bits};
    number.value += delta;
    return number.bits;
}

static void box_sprite(u32 group, u32 hash, int down, int shorter)
{
    struct ref r;
    u32 *sprite = sprite_of(&r, group, hash);
    if (!sprite)
        return;
    sprite[SP_X + 1] = float_add(sprite[SP_X + 1], -down);
    if (shorter)
        sprite[SP_W + 1] = float_add(sprite[SP_W + 1], -down);
    sprite_changed(&r);
}

static void box_text(u32 group, u32 hash, int down)
{
    struct ref r;
    u32 *text = text_of(&r, group, hash);
    if (!text)
        return;
    u32 *holder = (u32 *)text[0];
    holder[1] = float_add(holder[1], -down);
    text[TX_X + 1] = float_add(text[TX_X + 1], -down);
    text_changed(&r);
}

/* The lines past the two rows off, and on again if they were. */
static u32 box_lines_off(u32 group, int cut, u32 state)
{
    for (u32 i = 0; i < BOX_LINES - BOX_LINES_KEPT; i++) {
        struct ref r;
        u32 *line = sprite_of(&r, group, H_BOX_LINES + BOX_LINES_KEPT + i), shown = BOX_LINE_SHOWN << i;
        if (!line)
            continue;
        if (!cut) {
            if (state & shown)
                line[SP_FLAGS] |= SP_SHOWN;
        } else if (line[SP_FLAGS] & SP_SHOWN) {
            state |= shown;
            line[SP_FLAGS] &= ~SP_SHOWN;
        }
        sprite_changed(&r);
    }
    return state;
}

/* The price row's icon and count box off, and on again if they were; its count wider by the curated difference. */
static u32 box_price_row(int cut, u32 state)
{
    u32 group = group_named(FS->hashes[H_BOX_GROUPS + 1 + BOX_PRICE_ROW]), hash = H_BOX_ROWS + BOX_PRICE_ROW * BOX_ROW_PANES;
    struct ref r;
    for (u32 i = 0; i < 2; i++) {
        u32 *sprite = sprite_of(&r, group, hash + i), shown = BOX_PRICE_SHOWN << i;
        if (!sprite)
            continue;
        if (!cut) {
            if (state & shown)
                sprite[SP_FLAGS] |= SP_SHOWN;
        } else if (sprite[SP_FLAGS] & SP_SHOWN) {
            state |= shown;
            sprite[SP_FLAGS] &= ~SP_SHOWN;
        }
        sprite_changed(&r);
    }
    u32 *text = text_of(&r, group, hash + 3);
    if (text) {
        text[TX_W] = float_add(text[TX_W], cut ? FS->price_widen : -(int)FS->price_widen);
        text_changed(&r);
    }
    return state;
}

/* The box cut or whole: the frame keeps its bottom, and the title and the three rows end there. Before the box is drawn, so
   that the texts' strings are laid out where they now are. */
static void box_cut(int cut)
{
    struct ui *u = U;
    if ((u->box_cut & BOX_IS_CUT) == (u32)cut)
        return;
    int down = cut ? FS->box_cut : -(int)FS->box_cut;
    u32 frame = group_named(FS->hashes[H_BOX_GROUPS]);
    for (u32 i = 0; i < BOX_FRAME; i++)
        box_sprite(frame, H_BOX_FRAME + i, down, 1);
    for (u32 i = 0; i < BOX_LINES_KEPT; i++)
        box_sprite(frame, H_BOX_LINES + i, down, 0);
    u32 state = box_lines_off(frame, cut, u->box_cut);
    state = box_price_row(cut, state);
    for (u32 i = 0; i < BOX_TITLE; i++)
        box_text(frame, H_BOX_TITLE + i, down);
    for (u32 row = 0; row < BOX_ROWS; row++) {
        u32 group = group_named(FS->hashes[H_BOX_GROUPS + 1 + row]), hash = H_BOX_ROWS + row * BOX_ROW_PANES;
        box_sprite(group, hash, down, 0);
        box_sprite(group, hash + 1, down, 0);
        box_text(group, hash + 2, down);
        box_text(group, hash + 3, down);
    }
    u->box_cut = cut ? state | BOX_IS_CUT : 0;
}

/* ----- drawing --------------------------------------------------------------------------------------------- */

static const struct fg_mode *mode_of(void)
{
    return &FS->modes[U->mode];
}

static u32 button_index(u32 row, u32 button)
{
    return row < ARMOR_ROWS ? row * ROW_BUTTONS + button : ARMOR_ROWS * ROW_BUTTONS + row - ARMOR_ROWS;
}

static u32 button_hash(u32 row, u32 button)
{
    return H_BUTTON + 3 * button_index(row, button);
}

/* The button's try-on mark: the eye, a sprite of its own, in the order of the buttons. */
static u32 try_on_hash(u32 row, u32 button)
{
    return H_TRY_ON + button_index(row, button);
}

static u32 button_icon(u32 button)
{
    if (U->mode == M_ARMOR)
        return FS->armor_icons[button];
    return U->mode == M_FELYNE ? FS->felyne_icons[button] : FS->weapon_icons[class_of()];
}

static void draw_button(u32 group, u32 row, u32 button, const struct look *l)
{
    const struct fg_mode *m = mode_of();
    u32 hash = button_hash(row, button);
    if (!l || button >= m->buttons) {
        for (u32 i = 0; i < 3; i++)
            sprite_hide(group, hash + i);
        sprite_hide(group, try_on_hash(row, button));
        return;
    }
    int x = m->button_x + button * m->button_pitch, y = m->first_y + row * m->pitch + m->button_dy;
    int enabled = button_enabled(l, button), have = owned(l);
    struct ref r;
    u32 *sprite = sprite_place(&r, group, hash, x, y, FS->plate_w, FS->plate_h);
    if (sprite) {
        sprite_colour(sprite, FS->colours[enabled ? C_PLATE : C_DISABLED_PLATE]);
        sprite_changed(&r);
    }
    sprite = sprite_place(&r, group, hash + 1, x + FS->icon_dx, y + FS->icon_dy, FS->icon_w, FS->icon_h);
    if (sprite) {
        if (enabled) {
            icon_draw(gui_control, (u8 *)sprite + SP_ICON, button_icon(button),
                      &FS->colours[have ? C_BOUGHT : C_NOT_OWNED_ICON]);
        } else {
            sprite[SP_U] = FS->disabled_u;
            sprite[SP_U + 1] = FS->disabled_v;
            sprite_colour(sprite, FS->colours[C_DISABLED_ICON]);
        }
        sprite_changed(&r);
    }
    /* The two marks have a sprite each: what is worn has the E, and only what is not worn can be a try-on (the red eye,
       whose cell and colours the sprite carries from the file). */
    int wearing = enabled && worn(l, button);
    if (wearing) {
        sprite = sprite_place(&r, group, hash + 2, x + FS->mark_dx, y + FS->mark_dy, FS->icon_w, FS->icon_h);
        if (sprite) {
            icon_draw(gui_control, (u8 *)sprite + SP_ICON, FS->mark_icon, &FS->colours[C_MARK]);
            sprite_changed(&r);
        }
    } else {
        sprite_hide(group, hash + 2);
    }
    if (enabled && !wearing && on_model(l, button)) {
        sprite = sprite_place(&r, group, try_on_hash(row, button), x + FS->try_on_dx, y + FS->try_on_dy, FS->try_on_w,
                              FS->try_on_h);
        if (sprite)
            sprite_changed(&r);
    } else {
        sprite_hide(group, try_on_hash(row, button));
    }
}

static void draw_name(u32 group, u32 row, const struct look *l)
{
    const struct fg_mode *m = mode_of();
    struct ref r;
    u32 *text = text_of(&r, group, H_NAME + row);
    if (!text)
        return;
    u32 x = float_bits(HALF_WIDTH - (int)m->name_x), y = float_bits(HALF_HEIGHT - (int)(m->first_y + row * m->pitch + m->name_dy));
    u32 *holder = (u32 *)text[0];
    holder[0] = text[TX_X] = x;
    holder[1] = text[TX_X + 1] = y;
    text[TX_W] = float_bits(m->name_w);
    /* White when bought, or when it can be paid now, as the forge's list (FUN_009ba428: grey when the recipe's
       availability bits are not 0); the icons stay grey until it is bought. */
    text_colour(text, FS->colours[owned(l) || can_pay(l) ? C_BOUGHT : C_NOT_BOUGHT]);
    if (U->mode == M_WEAPON) {
        u32 name = l->on.weapon->name;
        if (name & CUSTOM_NAME)
            text_lobby(&r, MAKESHOP, name & ~CUSTOM_NAME);
        else
            text_common(&r, WEAPON_NAMES + class_of(), name);
    } else {
        text_lobby(&r, MAKESHOP, U->mode == M_ARMOR ? l->on.set->message : l->on.row->message);
    }
    text_show((u32)text, 1);
    text_changed(&r);
}

/* The rows, from what the filters and `top` show. */
static void draw_rows(void)
{
    const struct fg_mode *m = mode_of();
    u32 group = group_of(G_ROWS), back = group_of(G_RIGHT);
    u16 shown[MAX_ROWS];
    U->total = scan_rows(U->top, shown, m->rows, 1);
    for (u32 row = 0; row < MAX_ROWS; row++) {
        struct look look, *l = 0;
        if (row < m->rows && U->top + row < U->total) {
            look_at(shown[row], &look);
            l = &look;
        }
        for (u32 piece = 0; piece < 3; piece++) {
            if (l) {
                struct ref r;
                if (sprite_place(&r, back, H_ROW + row * 3 + piece, FS->piece_x[piece], m->first_y + row * m->pitch,
                                 FS->piece_w[piece], m->pitch))
                    sprite_changed(&r);
            } else {
                sprite_hide(back, H_ROW + row * 3 + piece);
            }
        }
        if (l)
            draw_name(group, row, l);
        else
            text_hide(group, H_NAME + row);
        for (u32 button = 0; button < (row < ARMOR_ROWS ? ROW_BUTTONS : 1); button++)
            draw_button(group, row, button, l);
    }
}

/* The filters' words, each chosen value on its plate. */
static void draw_filters(void)
{
    u32 group = group_of(G_ROWS);
    for (u32 filter = 0; filter < 2; filter++) {
        u32 chosen = filter ? U->game : U->rank, values = filter ? GAME_VALUES : RANK_VALUES;
        for (u32 value = 0; value < values; value++) {
            struct ref r;
            u32 *text = text_of(&r, group, H_FILTER + (filter ? RANK_VALUES : 0) + value);
            u32 rank = filter ? U->rank : value, game = filter ? value : U->game;
            if (!text)
                continue;
            text_colour(text, FS->colours[U->grey & GREY_BIT(rank, game) ? C_GREY : value == chosen ? C_CHOSEN : C_FILTER]);
            /* The rank row's All is the game row's word. */
            text_lobby(&r, MAKESHOP, R->messages[filter ? MSG_GAME_MH4U + value
                                                 : value == RANK_ALL ? MSG_GAME_ALL : MSG_RANK_LOW + value]);
            text_show((u32)text, 1);
            text_changed(&r);
        }
        struct ref r;
        const struct fg_rect *rect = &FS->filters[filter][chosen];
        if (sprite_place(&r, group, H_SELECTED + filter, rect->x, rect->y, rect->w, FS->selected_h))
            sprite_changed(&r);
    }
}

/* The cursor: a bar on the row or the filter, under the words and buttons, and a bracket on the row's button, over them. */
static void draw_cursor(void)
{
    const struct fg_mode *m = mode_of();
    u32 group = group_of(G_CURSOR), top = group_of(G_KEYS), on_row = U->focus == FOCUS_ROW;
    int y = on_row ? m->first_y + (U->index - U->top) * m->pitch : FS->bar_y[U->focus == FOCUS_GAME];
    u32 height = on_row ? m->pitch : FS->bar_h;
    struct ref r;
    for (u32 piece = 0; piece < 3; piece++)
        if (sprite_place(&r, group, H_CURSOR + piece, FS->piece_x[piece], y, FS->piece_w[piece], height))
            sprite_changed(&r);
    for (u32 side = 0; side < 2; side++) {
        if (on_row) {
            int x = m->button_x + U->button * m->button_pitch + FS->bracket[side * 2];
            if (sprite_place(&r, top, H_CURSOR + 3 + side, x, y + m->button_dy + FS->bracket[side * 2 + 1], FS->bracket_w,
                             FS->bracket_h))
                sprite_changed(&r);
        } else {
            sprite_hide(top, H_CURSOR + 3 + side);
        }
    }
}

/* `value` in decimal, its length. */
static u32 number_text(u16 *out, u32 value)
{
    return kit_number_text(out, value);
}

/* The key bar: the keys, and the row among the rows. */
static void draw_keys(void)
{
    u32 group = group_of(G_KEYS), length;
    struct ref r;
    u32 *text = text_of(&r, group, H_HINT);
    if (text) {
        u32 message = U->focus != FOCUS_ROW ? R->messages[MSG_HELP_FILTER]
                      : U->mode == M_WEAPON ? D->msg_row_weapons : R->messages[MSG_HELP_ROW];   /* no Y on weapons */
        text_lobby(&r, MAKESHOP, message);
        text_show((u32)text, 1);
        text_changed(&r);
    }
    text = text_of(&r, group, H_COUNT);
    if (text) {
        length = number_text(U->counter_text, U->index + 1);
        U->counter_text[length++] = '/';
        length += number_text(U->counter_text + length, U->total);
        text_slot(TEXT_SLOT, U->counter_text, length);
        text_lobby(&r, MAKESHOP, D->msg_counter);
        text_show((u32)text, 1);
        text_changed(&r);
    }
}

/* ----- the colour window (SELECT on the Armor screen) --------------------------------------------------------------

   The game's Armor Pigment of the item box (FUN_00a983bc), on the Armor list: a target (the whole set or a piece, the
   list's button), its palette's twelve colours (FUN_00c0e3c8), Default and its colour scale, whose point the D-pad moves
   one unit a press over 0..174 x 0..49 after A on it, reading the texel under it (FUN_00599864). The model shows the
   colour under the cursor at once; A keeps it (on the piece worn, or on the try-on only) and the window stays; B goes
   back to the list with the colours A kept.
   A part is dyed only while it wears a look (not Nothing). The window's state is struct dye_window in layered_ui. */

#define DY (&FS->dye)

static u32 pad_word(u32 at)
{
    return *(const u32 *)(pad_control + at);
}

enum { DR_TARGETS, DR_CHIPS };   /* the window's rows: the targets, the chips' rows, then Default and the scale */

static u32 dye_group(void)
{
    return kit_group(DY->group);
}

static u32 *dye_sprite(struct ref *r, u32 hash, const struct fg_rect *at)
{
    return kit_sprite_place(r, dye_group(), DY->hashes[hash], at->x, at->y, at->w, at->h);
}

static u32 chip_rows(void)
{
    return small_divide(DYE_CHIPS + DY->columns - 1, DY->columns);
}

static u32 row_default(void)
{
    return DR_CHIPS + chip_rows();
}

/* The cells of a row of the window. */
static u32 row_cells(u32 row)
{
    if (row == DR_TARGETS)
        return DYE_TARGETS;
    if (row >= row_default())
        return 1;
    u32 first = (row - DR_CHIPS) * DY->columns;
    return DYE_CHIPS - first < DY->columns ? DYE_CHIPS - first : DY->columns;
}

/* Does the model wear a look on the part, one that takes a colour (not Nothing)? */
static int part_dyeable(u32 part)
{
    u32 model = P->state.armor[part][hunter_female()];
    return model && model != NO_ARMOR;
}

/* The parts a target dyes: the whole set's, or the piece's, those with a look. */
static u32 target_parts(u32 target)
{
    u32 parts = 0;
    for (u32 part = 0; part < ARMOR_PARTS; part++)
        if (part_dyeable(part) && (!target || button_part[target - 1] == part))
            parts |= 1u << part;
    return parts;
}

/* A part the model tries on: what it wears there is not what is worn. */
static int tried_on(u32 part)
{
    return P->state.armor[part][0] != layered_state.armor[part][0] || P->state.armor[part][1] != layered_state.armor[part][1];
}

/* RGBA as a dye: RGB565, black kept apart from the look's own colour. */
static u32 dye_of(const u8 *rgba)
{
    u32 dye = (rgba[0] >> 3) << 11 | (rgba[1] >> 2) << 5 | rgba[2] >> 3;
    return dye ? dye : DYE_BLACK;
}

/* A dye as a pane's colour word. */
static u32 dye_word(u32 dye)
{
    u32 r = dye >> 11, g = dye >> 5 & 0x3F, b = dye & 0x1F;
    return 0xFF000000u | (b << 3 | b >> 2) << 16 | (g << 2 | g >> 4) << 8 | (r << 3 | r >> 2);
}

static u32 chip_colour(u32 chip)
{
    u8 rgba[4];
    palette_colour(rgba, gui_control, chip);
    return dye_of(rgba);
}

/* FUN_00599864: the texel under the point, the point's range centred on the scale's sprite, through its cell. */
ARM static u32 scale_colour(void)
{
    struct dye_window *w = &U->dye;
    struct ref r;
    const float *sprite = (const float *)kit_sprite(&r, dye_group(), DY->hashes[DH_SCALE]);
    u32 texture = sprite ? sprite_texture(&r) : 0;
    if (!texture)
        return w->colour;
    float width = sprite[SP_W] * sprite[SP_W + 2], height = sprite[SP_W + 1] * sprite[SP_W + 3];
    if (width * height == 0.0f)
        return w->colour;
    float u = sprite[SP_U] + ((float)w->x / width + (width - (float)DY->range_x) * 0.5f / width) * sprite[SP_U + 2];
    float v = sprite[SP_U + 1] + ((float)w->y / height + (height - (float)DY->range_y) * 0.5f / height) * sprite[SP_U + 3];
    u = u > 1.0f ? 1.0f : u < 0.0f ? 0.0f : u;
    v = v > 1.0f ? 1.0f : v < 0.0f ? 0.0f : v;
    int xy[2] = {(int)((float)*(const u32 *)(texture + 0xDC) * u), (int)((float)*(const u32 *)(texture + 0xE0) * v)};
    u8 rgba[4];
    texel_colour(rgba, gui_control, texture, xy);
    return dye_of(rgba);
}

/* What the cursor's cell gives: a chip's colour, the look's own (Default), the scale's under the point. */
static u32 cell_colour(void)
{
    struct dye_window *w = &U->dye;
    if (w->row < row_default())
        return chip_colour((w->row - DR_CHIPS) * DY->columns + w->col);
    return w->row == row_default() ? DYE_OWN : scale_colour();
}

/* The model: the target's parts in the colour under the cursor, when it is on a colour; every other part as it was. */
static void dye_preview(void)
{
    struct dye_window *w = &U->dye;
    u32 parts = w->row == DR_TARGETS ? 0 : target_parts(w->target);
    if (parts)
        w->colour = cell_colour();
    for (u32 part = 0; part < ARMOR_PARTS; part++)
        P->state.dye[part] = parts >> part & 1 ? w->colour : w->before[part];
    layered_dye_refresh();
}

/* A cell's rectangle. */
static void cell_rect(u32 row, u32 col, struct fg_rect *at)
{
    const struct fg_rect *fixed = row == row_default() ? &DY->deflt : &DY->scale;
    u32 x = fixed->x, y = fixed->y, w = fixed->w, h = fixed->h;
    if (row == DR_TARGETS) {
        x = DY->target_x + col * DY->target_pitch;
        y = DY->target_y;
        w = FS->plate_w;
        h = FS->plate_h;
    } else if (row < row_default()) {
        x = DY->chip_x + col * DY->chip_dx;
        y = DY->chip_y + (row - DR_CHIPS) * DY->chip_dy;
        w = DY->chip_w;
        h = DY->chip_h;
    }
    at->x = x;
    at->y = y;
    at->w = w;
    at->h = h;
}

static void draw_dye_point(void)
{
    struct dye_window *w = &U->dye;
    struct fg_rect at = {DY->scale.x + ((DY->scale.w - DY->range_x) >> 1) + w->x - (DY->cursor_w >> 1),
                         DY->scale.y + ((DY->scale.h - DY->range_y) >> 1) + w->y - (DY->cursor_h >> 1),
                         DY->cursor_w, DY->cursor_h};
    struct ref r;
    if (dye_sprite(&r, DH_POINT, &at))
        sprite_changed(&r);
}

/* The targets and their colours, the title, the cursor. */
static void draw_dye(void)
{
    struct dye_window *w = &U->dye;
    struct ref r;
    for (u32 target = 0; target < DYE_TARGETS; target++) {
        struct fg_rect at;
        cell_rect(DR_TARGETS, target, &at);
        int enabled = target_parts(target) != 0;
        u32 *sprite = dye_sprite(&r, DH_TARGET + 3 * target, &at);
        if (sprite) {
            sprite_colour(sprite, FS->colours[enabled ? C_PLATE : C_DISABLED_PLATE]);
            sprite_changed(&r);
        }
        struct fg_rect icon = {at.x + FS->icon_dx, at.y + FS->icon_dy, FS->icon_w, FS->icon_h};
        sprite = dye_sprite(&r, DH_TARGET + 3 * target + 1, &icon);
        if (sprite) {
            if (enabled) {
                icon_draw(gui_control, (u8 *)sprite + SP_ICON, FS->armor_icons[target],
                          &FS->colours[target == w->target ? C_BOUGHT : C_NOT_BOUGHT]);
            } else {
                sprite[SP_U] = FS->disabled_u;
                sprite[SP_U + 1] = FS->disabled_v;
                sprite_colour(sprite, FS->colours[C_DISABLED_ICON]);
            }
            sprite_changed(&r);
        }
        u32 part = target ? button_part[target - 1] : 0, dye = P->state.dye[part];
        struct fg_rect swatch = {at.x + DY->swatch_dx, at.y + DY->swatch_dy, DY->swatch_w, DY->swatch_h};
        if (target && enabled && dye != DYE_OWN && (sprite = dye_sprite(&r, DH_TARGET + 3 * target + 2, &swatch))) {
            sprite_colour(sprite, dye_word(dye));
            sprite_changed(&r);
        } else {
            kit_sprite_hide(dye_group(), DY->hashes[DH_TARGET + 3 * target + 2]);
        }
    }
    u32 *text = kit_text(&r, dye_group(), DY->hashes[DH_TITLE]);
    if (text) {
        text_lobby(&r, ITEMBOX, MSG_DYE_TARGET + w->target);
        text_show((u32)text, 1);
        text_changed(&r);
    }
    struct fg_rect at;
    cell_rect(w->row, w->col, &at);
    int x = at.x + DY->bracket[0], y = at.y + DY->bracket[1];
    u32 width = at.w + DY->bracket[2], height = at.h + DY->bracket[3], half = width >> 1;
    for (u32 side = 0; side < 2; side++) {
        struct fg_rect piece = {x + side * half, y, side ? width - half : half, height};
        if (dye_sprite(&r, DH_CURSOR + side, &piece))
            sprite_changed(&r);
    }
}

/* What does not change while the window is on: the chips, Default, the scale, L and R; the key bar's words. */
static void draw_dye_once(void)
{
    struct ref r;
    for (u32 chip = 0; chip < DYE_CHIPS; chip++) {
        struct fg_rect at;
        cell_rect(DR_CHIPS + small_divide(chip, DY->columns), chip - small_divide(chip, DY->columns) * DY->columns, &at);
        u32 *sprite = dye_sprite(&r, DH_CHIP + chip, &at);
        if (sprite) {
            sprite_colour(sprite, dye_word(chip_colour(chip)));
            sprite_changed(&r);
        }
    }
    static const u8 placed[] = {DH_DEFAULT, DH_FRAME, DH_SCALE, DH_KEYS, DH_KEYS + 1};
    const struct fg_rect *rects[] = {&DY->deflt, &DY->scale, &DY->scale, &DY->keys[0], &DY->keys[1]};
    for (u32 i = 0; i < sizeof placed; i++)
        if (dye_sprite(&r, placed[i], rects[i]))
            sprite_changed(&r);
    u32 *text = kit_text(&r, dye_group(), DY->hashes[DH_DEFAULT + 1]);
    if (text) {
        kit_text_place(text, DY->deflt_text.x, DY->deflt_text.y, DY->deflt_text.w);
        text_lobby(&r, ITEMBOX, MSG_DEFAULT);
        text_show((u32)text, 1);
        text_changed(&r);
    }
    draw_dye_point();
    text = text_of(&r, group_of(G_KEYS), H_HINT);
    if (text) {
        text_lobby(&r, MAKESHOP, DY->msg_keys);
        text_show((u32)text, 1);
        text_changed(&r);
    }
    text_hide(group_of(G_KEYS), H_COUNT);
}

/* SELECT's cue, where START's is on the other screens: the plate, the word "SELECT" as the key bar writes its keys
   (the game has no SELECT key; a key pieced from START's read badly), and the game's "Color". */
static void draw_select_cue(int shown)
{
    u32 group = group_of(G_CUE);
    struct ref r;
    for (u32 i = 0; i < 6; i++) {
        u32 hash = DY->hashes[DH_SELECT + i];
        const struct fg_rect *at = &DY->cue[i];
        if (i < 4) {
            if (!shown || i > 0)
                kit_sprite_hide(group, hash);
            else if (kit_sprite_place(&r, group, hash, at->x, at->y, at->w, at->h))
                sprite_changed(&r);
            continue;
        }
        if (!shown) {
            kit_text_hide(group, hash);
            continue;
        }
        u32 *text = kit_text(&r, group, hash);
        if (!text)
            continue;
        kit_text_place(text, at->x, at->y, at->w);
        if (i == 4)
            text_lobby(&r, MAKESHOP, DY->msg_select);
        else
            text_lobby(&r, ITEMBOX, MSG_COLOR);
        if (i == 4)
            text_colour(text, DY->key_word);              /* after its message, which sets the text's colour */
        text_show((u32)text, 1);
        text_changed(&r);
    }
}

/* START's cue: "Camera" on the model's frame on the list (on the Armor list a little higher, SELECT's under it); "Show
   Menu" beside the game's frame in the camera mode. */
static void draw_cue(u32 in_mode)
{
    const struct fg_rect *at = !in_mode && U->mode == M_ARMOR ? DY->start_cue : FS->cue[in_mode];
    u32 group = group_of(G_CUE);
    struct ref r;
    for (u32 piece = 0; piece < 2; piece++)
        if (sprite_place(&r, group, H_CUE + piece, at[piece].x, at[piece].y, at[piece].w, at[piece].h))
            sprite_changed(&r);
    u32 *text = text_of(&r, group, H_CUE + 2);
    if (text) {
        u32 *holder = (u32 *)text[0];
        holder[0] = text[TX_X] = float_bits(HALF_WIDTH - (int)at[2].x);
        holder[1] = text[TX_X + 1] = float_bits(HALF_HEIGHT - (int)at[2].y);
        text[TX_W] = float_bits(at[2].w);
        text_lobby(&r, ITEMBOX, in_mode ? MSG_SHOW_MENU : MSG_CAMERA);
        text_show((u32)text, 1);
        text_changed(&r);
    }
    draw_select_cue(!in_mode && U->mode == M_ARMOR);
}

/* The price row under the materials: "Cost" and the zenny, grey when the money is short as the box's materials are. */
static void draw_price(const struct look *l)
{
    u32 group = group_named(FS->hashes[H_BOX_GROUPS + 1 + BOX_PRICE_ROW]), hash = H_BOX_ROWS + BOX_PRICE_ROW * BOX_ROW_PANES;
    u32 price = price_of(l);
    if (!group)
        return;
    if (owned(l) || !price) {
        gui_group_show(group, 0);
        return;
    }
    gui_group_show(group, 1);
    u32 colour = money_short(price) ? BOX_GREY : BOX_WHITE;
    struct ref r;
    u32 *text = text_of(&r, group, hash + 2);
    if (text) {
        text_colour(text, colour);
        text_lobby(&r, KITCHEN, MSG_COST);
        text_show((u32)text, 1);
        text_changed(&r);
    }
    text = text_of(&r, group, hash + 3);
    if (text) {
        text_colour(text, colour);
        text_slot(TEXT_SLOT, U->price_text, number_text(U->price_text, price));
        text_lobby(&r, KITCHEN, MSG_COST_ZENNY);
        text_show((u32)text, 1);
        text_changed(&r);
    }
}

/* The game's box: a look bought shows its frame with no rows; one to buy, its materials and its price. */
static void draw_materials(u32 obj, const struct look *l)
{
    *(const struct recipe **)(obj + OBJ_RECIPE) = owned(l) ? 0 : recipe_of(l);
    materials_box(obj);
    for (u32 row = BOX_ROWS; row < BOX_ALL_ROWS; row++) {
        u32 group = group_named(FS->hashes[H_BOX_GROUPS + 1 + row]);
        if (group)
            gui_group_show(group, 0);
    }
    draw_price(l);
}

static void draw_money(u32 obj)
{
    money_write(obj, *(u32 *)(save_control + SAVE_MONEY), 1);
    money_show(obj, 1, 0);
}

/* The cursor moved or the list changed. A row without the button takes the nearest one to the left. */
static void refresh(u32 obj, int rows)
{
    struct look l;
    if (rows)
        draw_rows();
    current(&l);
    while (U->button && !button_enabled(&l, U->button))
        U->button--;
    draw_cursor();
    draw_keys();
    draw_materials(obj, &l);
}

/* ----- the preview ----------------------------------------------------------------------------------------- */

/* A record of the class for the preview hunter to hold: the real weapon, or the class' first with an id. Its model is the
   look's while p->state names one. */
static void weapon_record(const u8 *status)
{
    u32 class = class_of();
    if (status[ST_WEAPON] == class + WEAPON_TYPE) {
        layered_copy(P->on.record, status + ST_WEAPON, RECORD);
        return;
    }
    const struct catalog *k = &D->catalogs[0];
    const struct weapon *w = (const struct weapon *)(layered_data + k->weapon_offset[class]);
    u32 id = 0;
    for (u32 i = 0; i < k->weapon_count[class] && !id; i++)
        id = w[i].id;
    make_record(equipment_control, P->on.record, class + WEAPON_TYPE, id);
}

/* FUN_00c042ec, which opened the model's view, gives it another rectangle. It also sets the lens to its defaults and forgets
   the preset: those stay as they are, so the zoom goes on and a preset not yet copied to the camera still is. */
static void preview_rectangle(u32 obj, const int *rectangle)
{
    static const u32 clear = 0;
    u32 target = *(u32 *)(obj + OBJ_CAMERA_TARGET);
    if (!target)
        return;
    u32 *preset = (u32 *)(camera_control + CAMERA_PRESET);
    u32 *far = (u32 *)(target + TARGET_FAR), *near = (u32 *)(target + TARGET_NEAR), *fov = (u32 *)(target + TARGET_FOV);
    u32 preset_was = *preset, far_was = *far, near_was = *near, fov_was = *fov;
    sub_view_open(camera_control, target, rectangle, &clear, CAMERA_LAYER, CAMERA_PRIORITY);
    *preset = preset_was;
    *far = far_was;
    *near = near_was;
    *fov = fov_was;
}

/* The model on, in the rectangle beside the materials box. */
static void preview_open(u32 obj)
{
    struct preview *p = P;
    if (U->mode == M_FELYNE) {
        felyne_preview_open(obj, p->on.cat_numbers);
    } else {
        u32 hunter = *(u32 *)(obj + OBJ_HUNTER);
        if (!hunter)
            return;
        const u8 *status = *(const u8 **)(hunter + HUNTER_STATUS);
        p->active = 1;
        if (U->mode == M_ARMOR) {
            layered_copy(p->on.record, status + ST_ARMOR, RECORD);
            preview_start(obj, p->on.record, PREVIEW_ARMOR);
        } else {
            weapon_record(status);
            preview_start(obj, p->on.record, PREVIEW_WEAPON);
            p->pushed = 1;          /* FUN_009edcec in this mode does not put the record on */
        }
    }
    preview_rectangle(obj, FS->camera);
}

static void preview_close(u32 obj)
{
    if (felyne_ui.preview) {
        felyne_preview_end(obj);
    } else if (P->active) {
        preview_frame_close(obj + OBJ_FRAME);
        preview_mode[0x6C] = 0;
        viewport_close(camera_control);
    }
    P->active = 0;
}

/* Every frame: a change of what the model wears goes on once the last load has ended. */
static void preview_update(u32 obj)
{
    struct preview *p = P;
    if (!p->pushed)
        return;
    if (U->mode == M_FELYNE) {
        if (felyne_preview_loaded(obj)) {
            p->pushed = 0;
            felyne_preview_look(obj, p->on.cat_numbers);
        }
        return;
    }
    u32 hunter = *(u32 *)(obj + OBJ_PREVIEW);
    if (hunter && preview_ready(obj, hunter)) {
        p->pushed = 0;
        hunter_reload(hunter, U->mode == M_WEAPON ? p->on.record : 0);
    }
}

/* The stick turns the model and moves its camera, as the forge's "try on" tab does (FUN_009fc74c). On the list L and R change
   the rank, so only the touch screen's Zoom buttons zoom: FUN_00a272b0 adds L / R to the buttons held while one is touched.
   In the camera mode all that is held counts, as in that tab. */
static void preview_controls(u32 obj)
{
    u32 hunter = *(u32 *)(obj + OBJ_PREVIEW);
    u32 *held = (u32 *)(pad_control + PAD_HELD);
    if (felyne_ui.preview)
        felyne_preview_controls(obj);
    else if (P->active && hunter)
        preview_rotate(obj, hunter);
    else
        return;
    u32 before = *held;
    preview_touch(obj);
    u32 buttons = U->sub == F_CAMERA ? *held : *held & ~before;
    camera_control_set(camera_control, camera_controls(camera_control, buttons, preview_stick(obj)));
}

/* Y, armor and Felynes: the look goes on the model, or, when the model wears it and it is not what is worn, off it. */
static void try_on(const struct look *l)
{
    struct preview *p = P;
    u32 button = U->button;
    if (U->mode == M_FELYNE) {
        u32 on = cat_set(p->on.cat_numbers, l, button, 1, 0);
        p->on.cat_numbers = on == p->on.cat_numbers ? cat_set(on, l, button, 0, felyne_numbers()) : on;
    } else if (armor_is(&p->state, l, button)) {
        u32 parts = parts_of(l, button);
        for (u32 part = 0; part < ARMOR_PARTS; part++)
            if (parts >> part & 1) {
                for (u32 female = 0; female < 2; female++)
                    p->state.armor[part][female] = layered_state.armor[part][female];
                p->state.dye[part] = layered_state.dye[part];
            }
    } else {
        armor_set(&p->state, l, button, 1);
    }
    p->pushed = 1;
}

/* The weapon the model holds of the class becomes `model`. Only a change asks for a reload, and preview_update makes
   it once the last load has ended, so one load at most is ever in flight, with the last model asked for. */
static void preview_weapon(u32 model)
{
    struct preview *p = P;
    u32 class = class_of();
    if (p->state.weapon[class] == model)
        return;
    p->state.weapon[class] = model;
    p->pushed = 1;
}

/* A weapon's list: the model holds the look under the cursor now, with no wait (the screen opening, a new list, A). The
   weapon worn is never shown: the list's own looks are. */
static void preview_row(void)
{
    if (U->mode != M_WEAPON)
        return;
    struct look l;
    current(&l);
    U->hover = FS->preview_frames;
    preview_weapon(l.on.weapon->model);
}

/* Every frame of a weapon's list: once the cursor has rested on a row for the curated wait, the model shows its look.
   Moving the cursor starts the wait again (move_row), so scrolling loads nothing. */
static void preview_hover(void)
{
    struct ui *u = U;
    if (u->mode != M_WEAPON || u->focus != FOCUS_ROW || u->hover >= FS->preview_frames)
        return;
    if (++u->hover < FS->preview_frames)
        return;
    struct look l;
    current(&l);
    preview_weapon(l.on.weapon->model);
}

/* ----- buying ---------------------------------------------------------------------------------------------- */

/* The look on the model only (a purchase before "Equip now?"); what is worn stays as it is. */
static void model_wears(const struct look *l, u32 button)
{
    struct preview *p = P;
    if (U->mode == M_WEAPON)
        p->state.weapon[class_of()] = l->on.weapon->model;
    else if (U->mode == M_FELYNE)
        p->on.cat_numbers = cat_set(p->on.cat_numbers, l, button, 1, 0);
    else
        armor_set(&p->state, l, button, 1);
    p->pushed = 1;
}

/* A: the yes / no window of the forge, with the look's price. */
static void buy_ask(u32 obj, const struct look *l)
{
    if (!can_pay(l)) {
        play(SOUND_ERROR);
        return;
    }
    number_text(U->price_text, price_of(l));
    window_open(3, 0, 4, 1);
    window_open(6, 1, 4, 0);
    *(u32 *)(obj + OBJ_ANSWER) = 0;
    play(SOUND_DECIDE);
    U->sub = F_PROMPT;
    screens_open = 0;
}

/* Yes: as the forge does (FUN_009ca7e8), without making any gear: the model closes, the hammer scene starts, the money and
   the materials go, the panels hide; the look is bought and on. */
static void buy(u32 obj)
{
    struct look l;
    current(&l);
    const struct recipe *recipe = recipe_of(&l);
    u32 kind, mask;
    preview_close(obj);
    if (*(u8 *)(*(u32 *)(*(u32 *)(obj + OBJ_FORGER) + SMITH_STATUS) + SMITH_KIND) == SMITH_HAMMER)
        kind = HAMMER_ALONE;
    else
        kind = hammer_kind(obj) ? 2 : 1;
    hammer_scene((u32)preview_mode, kind);
    money_add(save_control, -(int)price_of(&l));
    play(SOUND_PAY);
    for (u32 i = 0; i < 4; i++)
        if (recipe->materials[i].item)
            item_take(obj, recipe->materials[i].item, recipe->materials[i].quantity);
    box_cut(0);
    forge_hide(obj);
    groups_show(0);
    smithy_panel(obj, 0, 0);
    smithy_panel_b(obj, 0);
    smithy_panel_c(obj, 0);
    *owned_at(&l, &mask) |= mask;
    owned_zone()[R->zone_format_at] = R->zone_format;   /* the zone's layout, for the builds after this one */
    model_wears(&l, U->button);  /* worn only if "Equip now?" is answered yes, after the scene */
    U->sub = F_SCENE_START;
}

/* After the scene, the forge's question (FUN_009ca7e8's "Equip now?"): the same yes / no window as the price's. */
static void equip_ask(u32 obj)
{
    window_open(3, 0, 4, 1);
    window_open(6, 1, 4, 0);
    *(u32 *)(obj + OBJ_ANSWER) = 0;
    U->sub = F_EQUIP;
    screens_open = 0;
}

/* Yes wears the look bought; No leaves it bought and on the model, as a try-on. */
static void equip_prompt(u32 obj)
{
    facility_help(1, MAKESHOP, MSG_EQUIP_NOW);
    window_update();
    u32 answer = window_answer(obj, obj + OBJ_ANSWER, window_input(obj), ANSWER_ANY);
    if (answer != 1 && answer != 2)
        return;
    window_close(3, 0);
    U->sub = F_LIST;
    screens_open = 1;
    if (answer == 1) {
        struct look l;
        current(&l);
        wear(&l, U->button, 1);
    }
    play(SOUND_DECIDE);
    draw_rows();
}

static void buy_prompt(u32 obj)
{
    u32 length = 0;
    while (U->price_text[length])
        length++;
    text_slot(TEXT_SLOT, U->price_text, length);
    facility_help(1, MAKESHOP, MSG_PRICE);
    window_update();
    u32 answer = window_answer(obj, obj + OBJ_ANSWER, window_input(obj), ANSWER_ANY);
    if (answer == 1) {
        buy(obj);
    } else if (answer == 2) {
        window_close(3, 0);
        U->sub = F_LIST;
        screens_open = 1;
    }
}

/* ----- the screen ----------------------------------------------------------------------------------------- */

/* The screen on: its groups, the model, what the filters show, the materials and the money. */
static void screen_on(u32 obj)
{
    groups_show(1);
    preview_open(obj);
    screens_open = 1;
    U->sub = F_LIST;
    box_cut(1);
    draw_filters();
    draw_cue(0);
    refresh(obj, 1);
    draw_money(obj);
}

static void scene_end(u32 obj)
{
    if (!hammer_scene_busy((u32)preview_mode))
        return;
    smithy_panel(obj, 1, 0);
    smithy_panel_c(obj, 1);
    play(SOUND_DONE);
    screen_on(obj);
    equip_ask(obj);
}

int forge_open(u32 obj, u32 mode)
{
    struct ui *u = U;
    struct preview *p = P;
    u->mode = mode;
    u->box_cut = 0;              /* no screen is on, so the box is whole: a game that ended on one loaded it again */
    u->unlocked = unlocked_rank();
    u->grey = grey_mask();
    if (u->grey == ALL_GREY) {
        play(SOUND_ERROR);
        return 0;
    }
    u->rank = RANK_ALL;
    u->game = GAME_ALL;
    u->index = u->top = 0;
    u->button = 0;
    u->focus = FOCUS_ROW;
    u->hover = 0;
    u->held = 0;
    u->level = FORGE;
    facility_menu_set(obj, NO_MENU, 0, 0);
    layered_copy(&p->state, &layered_state, sizeof p->state);
    p->pushed = 0;
    preview_row();               /* a weapon's model holds the first row's look from the start */
    if (mode == M_FELYNE)
        p->on.cat_numbers = felyne_numbers();
    screen_on(obj);
    return 1;
}

/* B: everything off, back to the level the screen came from. */
static void forge_close(u32 obj)
{
    box_cut(0);
    groups_show(0);
    forge_hide(obj);
    money_show(obj, 0, 0);
    preview_close(obj);
    screens_open = 0;
    P->pushed = 0;
    forge_back_to_menu(obj);
}

/* START: as the game's View Mode (FUN_00a93250) the panels go, and as its forge's "try on" tab the model has the whole frame
   (FUN_002727c8), which says what L, R and the stick do. Only START's cue stays, and it says how to come back. */
static void camera_enter(u32 obj)
{
    groups_show(0);
    forge_hide(obj);
    money_show(obj, 0, 0);
    screen_group_show(G_CUE, 1);
    model_frame();
    preview_rectangle(obj, FS->camera_full);
    draw_cue(1);
    play(SOUND_CAMERA_ON);
    U->sub = F_CAMERA;
}

/* START or B: the list as it was. The camera stays where the player left it, as in the View Mode. */
static void camera_leave(u32 obj)
{
    forge_hide(obj);
    groups_show(1);
    preview_rectangle(obj, FS->camera);
    draw_cue(0);
    refresh(obj, 0);
    draw_money(obj);
    play(SOUND_CAMERA_OFF);
    U->sub = F_LIST;
}

static void camera_mode(u32 obj)
{
    facility_help(1, ITEMBOX, MSG_CAMERA_HELP);
    preview_update(obj);
    preview_controls(obj);
    if (facility_pressed(obj, BUTTON_B | BUTTON_START))
        camera_leave(obj);
}

/* SELECT: the colour window on the list's button, or on the first target that has a look; none: nothing to dye. */
static void dye_open(u32 obj)
{
    struct dye_window *w = &U->dye;
    u32 target = target_parts(U->button) ? U->button : 0;
    while (target < DYE_TARGETS && !target_parts(target))
        target++;
    if (target == DYE_TARGETS) {
        play(SOUND_ERROR);
        return;
    }
    w->target = w->col = target;
    w->row = DR_TARGETS;
    w->picking = w->held = 0;
    w->x = DY->start_x;
    w->y = DY->start_y;
    w->colour = DYE_OWN;
    layered_copy(w->before, P->state.dye, sizeof w->before);
    U->sub = F_DYE;
    screen_group_show(G_ROWS, 0);
    screen_group_show(G_CURSOR, 0);
    for (u32 side = 0; side < 2; side++)              /* the button's bracket lives in the key bar's group, still shown */
        sprite_hide(group_of(G_KEYS), H_CURSOR + 3 + side);
    for (u32 piece = 0; piece < MAX_ROWS * 3; piece++)
        sprite_hide(group_of(G_RIGHT), H_ROW + piece);
    kit_group_show(dye_group(), 1, DY->priority);
    draw_dye_once();
    draw_dye();
    play(SOUND_DECIDE);
    (void)obj;
}

/* Back to the list, as it was. */
static void dye_close(u32 obj, u32 sound)
{
    kit_group_show(dye_group(), 0, DY->priority);
    screen_group_show(G_ROWS, 1);
    screen_group_show(G_CURSOR, 1);
    U->sub = F_LIST;
    play(sound);
    refresh(obj, 1);
}

/* A: the colour stays on the target's parts (on the piece worn, or only on the model for a try-on), and the window
   stays open for another piece or colour. */
static void dye_keep(void)
{
    struct dye_window *w = &U->dye;
    u32 parts = target_parts(w->target);
    for (u32 part = 0; part < ARMOR_PARTS; part++) {
        if (!(parts >> part & 1))
            continue;
        w->before[part] = w->colour;
        if (!tried_on(part))
            layered_state.dye[part] = w->colour;
    }
    play(SOUND_DECIDE);
    draw_dye();
}

/* B: back to the list with the colours A kept; a colour only under the cursor goes. */
static void dye_leave(u32 obj)
{
    struct dye_window *w = &U->dye;
    layered_copy(P->state.dye, w->before, sizeof w->before);
    layered_dye_refresh();
    dye_close(obj, SOUND_CANCEL);
}

/* The next target with a look, `step` away; the model shows the colour on it. */
static void dye_target(int step)
{
    struct dye_window *w = &U->dye;
    for (int target = w->target + step; target >= 0 && target < DYE_TARGETS; target += step)
        if (target_parts(target)) {
            w->target = target;
            if (w->row == DR_TARGETS)
                w->col = target;
            play(SOUND_CURSOR);
            dye_preview();
            draw_dye();
            return;
        }
}

/* The cursor to another cell. */
static void dye_move(u32 row, u32 col)
{
    struct dye_window *w = &U->dye;
    u32 cells = row_cells(row);
    w->row = row;
    w->col = row == DR_TARGETS ? w->target : col < cells ? col : cells - 1;
    play(SOUND_CURSOR);
    dye_preview();
    draw_dye();
}

/* The units a step of the scale's point moves: one, then the curated steps' once a direction is held. */
static u32 point_step(void)
{
    struct dye_window *w = &U->dye;
    if (!(pad_word(PAD_HELD) & DIR_ALL) || pad_word(PAD_PRESSED) & DIR_ALL)
        w->held = 0;
    else if (w->held < 0xFF)
        w->held++;
    u32 units = 1;
    for (u32 i = 0; i < HOLD_STEPS && DY->steps[i][0]; i++)
        if (w->held >= DY->steps[i][0])
            units = DY->steps[i][1];
    return units;
}

static u32 point_moved(u32 at, u32 dirs, u32 less, u32 more, u32 units, u32 most)
{
    if (dirs & less)
        return at > units ? at - units : 0;
    if (dirs & more)
        return at + units < most ? at + units : most;
    return at;
}

/* After A on the scale: the D-pad moves the point and the model follows; A keeps the colour and B stops the point
   (the colour under it stays a preview until A). */
static void point_keys(u32 obj, u32 dirs)
{
    struct dye_window *w = &U->dye;
    u32 units = point_step();
    if (facility_pressed(obj, BUTTON_A)) {
        w->picking = 0;
        dye_keep();
    } else if (facility_pressed(obj, BUTTON_B)) {
        w->picking = 0;
        play(SOUND_CANCEL);
    } else if (dirs & DIR_ALL) {
        u32 x = point_moved(w->x, dirs, DIR_LEFT, DIR_RIGHT, units, DY->range_x);
        u32 y = point_moved(w->y, dirs, DIR_UP, DIR_DOWN, units, DY->range_y);
        if (x == w->x && y == w->y)
            return;
        w->x = x;
        w->y = y;
        draw_dye_point();
        dye_preview();
    }
}

static void dye_keys(u32 obj)
{
    struct dye_window *w = &U->dye;
    u32 dirs = facility_dirs(obj), last = row_default() + 1;
    if (w->picking) {
        point_keys(obj, dirs);
    } else if (facility_pressed(obj, BUTTON_B)) {
        dye_leave(obj);
    } else if (facility_pressed(obj, BUTTON_L | BUTTON_R)) {
        dye_target(facility_pressed(obj, BUTTON_R) ? 1 : -1);
    } else if (dirs & DIR_UP) {
        if (w->row != DR_TARGETS)
            dye_move(w->row - 1, w->col);
    } else if (dirs & DIR_DOWN) {
        if (w->row < last)
            dye_move(w->row + 1, w->row == DR_TARGETS ? 0 : w->col);
    } else if (dirs & (DIR_LEFT | DIR_RIGHT)) {
        int step = dirs & DIR_RIGHT ? 1 : -1;
        if (w->row == DR_TARGETS)
            dye_target(step);
        else if (step > 0 ? w->col + 1u < row_cells(w->row) : w->col > 0)
            dye_move(w->row, w->col + step);
    } else if (facility_pressed(obj, BUTTON_A)) {
        if (w->row == DR_TARGETS) {
            dye_move(DR_CHIPS, 0);
        } else if (w->row == last) {
            w->picking = 1;
            w->held = 0;
            play(SOUND_DECIDE);
        } else {
            dye_keep();
        }
    }
}

static void dye_mode(u32 obj)
{
    facility_help(1, ITEMBOX, MSG_DYE_HELP);
    preview_update(obj);
    preview_controls(obj);
    dye_keys(obj);
}

/* A filter's value or the rank changed: the list shows the new pair from its start. */
static void list_changed(u32 obj, u32 sound)
{
    U->index = U->top = 0;
    preview_row();
    play(sound);
    draw_filters();
    refresh(obj, 1);
}

/* The next value of a filter that has rows, if any; `round` goes on past the ends. */
static int filter_step(int is_game, int step, int round)
{
    int values = is_game ? GAME_VALUES : RANK_VALUES, value = is_game ? U->game : U->rank;
    for (int i = 1; i < values; i++) {
        value += step;
        if (value < 0 || value >= values) {
            if (!round)
                return 0;
            value = value < 0 ? values - 1 : 0;
        }
        u32 rank = is_game ? U->rank : (u32)value, game = is_game ? (u32)value : U->game;
        if (!(U->grey & GREY_BIT(rank, game))) {
            if (is_game)
                U->game = value;
            else
                U->rank = value;
            return 1;
        }
    }
    return 0;
}

static void change_filter(u32 obj, int is_game, int step, int round, u32 sound)
{
    if (filter_step(is_game, step, round))
        list_changed(obj, sound);
    else
        play(SOUND_ERROR);
}

static void move_row(u32 obj, u32 index, u32 sound)
{
    const struct fg_mode *m = mode_of();
    u32 top = U->top;
    if (index == U->index)
        return;
    U->index = index;
    U->hover = 0;                /* a weapon's look waits for the cursor to rest */
    if (index < top)
        U->top = index;
    else if (index >= top + m->rows)
        U->top = index - m->rows + 1;
    play(sound);
    refresh(obj, U->top != top);
}

static void move_button(int step)
{
    struct look l;
    int button = U->button;
    current(&l);
    for (button += step; button >= 0 && button < mode_of()->buttons; button += step) {
        if (button_enabled(&l, button)) {
            U->button = button;
            play(SOUND_CURSOR);
            draw_cursor();
            return;
        }
    }
}

static void row_sideways(u32 obj, u32 dirs)
{
    int step = dirs & DIR_RIGHT ? 1 : -1;
    if (U->mode != M_WEAPON) {
        move_button(step);
        return;
    }
    u32 rows = mode_of()->rows, index = U->index;   /* a page */
    if (step > 0)
        index = index + rows < U->total ? index + rows : U->total - 1u;
    else
        index = index >= rows ? index - rows : 0;
    move_row(obj, index, SOUND_PAGE);
}

/* A: remove what is worn, wear what is bought, offer the rest. */
static void row_a(u32 obj)
{
    struct look l;
    current(&l);
    preview_row();               /* a weapon: the row's look on the model now, not after the wait */
    if (worn(&l, U->button)) {
        wear(&l, U->button, 0);
    } else if (owned(&l)) {
        wear(&l, U->button, 1);
    } else {
        buy_ask(obj, &l);
        return;
    }
    play(SOUND_DECIDE);
    draw_rows();
}

/* To a filter or back to the list: the model keeps the row's look. */
static void focus_to(u32 focus)
{
    U->focus = focus;
    play(SOUND_CURSOR);
    draw_cursor();
    draw_keys();
}

/* The frames up or down has been held since it was pressed (a new press starts again at 0), and the rows a step of the
   cursor moves after that many: one, then the curated steps' (forge_screen.cursor). */
static u32 held_rows(void)
{
    struct ui *u = U;
    if (!(pad_word(PAD_HELD) & DIR_VERTICAL) || pad_word(PAD_PRESSED) & DIR_VERTICAL)
        u->held = 0;
    else if (u->held < HELD_MAX)
        u->held++;
    u32 rows = 1;
    for (u32 i = 0; i < HOLD_STEPS && FS->hold[i][0]; i++)
        if (u->held >= FS->hold[i][0])
            rows = FS->hold[i][1];
    return rows;
}

static void list_keys(u32 obj)
{
    struct ui *u = U;
    u32 dirs = facility_dirs(obj), rows = held_rows();
    if (facility_pressed(obj, BUTTON_B)) {
        play(SOUND_CANCEL);
        forge_close(obj);
    } else if (u->mode == M_ARMOR && *(const u16 *)(pad_control + PAD_GAME_PRESSED) & GAME_KICK) {
        dye_open(obj);       /* Select (before START: with the game's option START at Kick, Select is one too) */
    } else if (facility_pressed(obj, BUTTON_START)) {
        camera_enter(obj);
    } else if (facility_pressed(obj, BUTTON_L | BUTTON_R)) {
        change_filter(obj, 0, facility_pressed(obj, BUTTON_R) ? 1 : -1, 1, SOUND_PAGE);
    } else if (facility_pressed(obj, BUTTON_X)) {
        change_filter(obj, 1, 1, 1, SOUND_PAGE);
    } else if (u->focus != FOCUS_ROW) {
        if (dirs & DIR_UP) {
            if (u->focus == FOCUS_GAME)
                focus_to(FOCUS_RANK);
        } else if (dirs & DIR_DOWN) {
            if (u->focus == FOCUS_RANK)
                focus_to(FOCUS_GAME);
            else
                focus_to(FOCUS_ROW);
        } else if (dirs & (DIR_LEFT | DIR_RIGHT)) {
            change_filter(obj, u->focus == FOCUS_GAME, dirs & DIR_RIGHT ? 1 : -1, 0, SOUND_CURSOR);
        }
    } else if (dirs & DIR_UP) {          /* held: `rows` a step, stopping at the ends; only a new press leaves the list */
        if (u->index)
            move_row(obj, u->index > rows ? u->index - rows : 0, SOUND_CURSOR);
        else if (pad_word(PAD_PRESSED) & DIR_UP)
            focus_to(FOCUS_GAME);
    } else if (dirs & DIR_DOWN) {
        if (u->index + 1 < u->total)
            move_row(obj, u->index + rows < u->total ? u->index + rows : u->total - 1u, SOUND_CURSOR);
    } else if (dirs & (DIR_LEFT | DIR_RIGHT)) {
        row_sideways(obj, dirs);
    } else if (facility_pressed(obj, BUTTON_A)) {
        row_a(obj);
    } else if (u->mode != M_WEAPON && facility_pressed(obj, BUTTON_Y)) {   /* weapons: the model follows the cursor */
        struct look l;
        current(&l);
        try_on(&l);
        play(SOUND_DECIDE);
        draw_rows();
    }
}

/* No jump table: Thumb's needs a library function (__gnu_thumb1_case_uqi) the block does not have, and GCC turns
   this chain of ifs into one once enough is inlined here. */
__attribute__((optimize("no-jump-tables")))
void forge_update(u32 obj)
{
    u32 sub = U->sub;
    if (sub == F_PROMPT || sub == F_EQUIP) {
        if (sub == F_PROMPT)
            buy_prompt(obj);
        else
            equip_prompt(obj);
        if (U->sub == sub)
            preview_update(obj);     /* the model goes on loading behind the window */
    } else if (sub == F_SCENE_START) {
        U->sub = F_SCENE;        /* the scene's state settles first, as the forge's state 2 */
    } else if (sub == F_SCENE) {
        scene_end(obj);
    } else if (sub == F_CAMERA) {
        camera_mode(obj);
    } else if (sub == F_DYE) {
        dye_mode(obj);
    } else {
        facility_help(1, MAKESHOP, help_message());
        preview_hover();
        preview_update(obj);
        preview_controls(obj);
        list_keys(obj);
    }
}
