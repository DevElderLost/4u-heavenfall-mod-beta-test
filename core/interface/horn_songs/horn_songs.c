/* The Hunting Horn's songs on the top screen (interface/horn_songs/horn_songs.py): while
 * this player's hunter holds a Hunting Horn in a quest, the list of the songs that horn can play, each with its notes
 * and its name, at the screen's right edge under the minimap; the songs whose start the last notes played match light
 * up, and one whose whole tune was just played lights up more. Where the rows are and how they look is the layout's
 * (layout.py): this code only fills, colours and shows them.
 *
 * horn_frame runs from the quest's shared frame hook (interface/quest_layouts/), after every system's move and before
 * the render. It reads, all from the game:
 *   - the hunter: player_get(*sPlayer, sGameControl +0x2F); its status (+0xE30): the weapon type (+0x1C0, 18 a Hunting
 *     Horn) and the weapon's id (+0x1C2); its work (+0xA29C): the horn's note set (+0x16C, the row of the game's note
 *     triplets) and the notes played, newest first (+0x930..0x933, 0 none; the game clears them when it resets);
 *   - the songs (FUN_00277e68's rule, the equipment menu's list): each of the 75 songs of the game's table whose every
 *     note is one of the horn's three, in the table's order, at most ROWS; a song's notes are newest first in the table,
 *     so the list shows them the other way round, the first one to play first;
 *   - a song's name: the Menu file's message of its name index (the byte table, then the word table), as the menu's;
 *   - a note's picture: the cell of the HUD's own table (FUN_00b8f58c, which draws the notes played): a cell of 16
 *     texels in the row v = 160 of qst00, or for one horn (special_horn) at u + 256 in the row v = 202.
 * The rows are made again when the group or the note set changes; the lights when the notes played change. A row is
 * idle, partial (the last k notes played are its first k: those notes lit) or full (its whole tune is the last notes
 * played, as the game's own match at its first offset): its bar, its name and its notes take that state's colours.
 * A song whose effect the hunter has (the game's table of each song's effect; each effect's slots and least levels,
 * horn_songs.py EFFECT_NEEDS, in the data block; the slots' levels and time left in the work, +0x804 and +0x824) is
 * coloured, green, or purple once the effect is in its encore (played again while on: the game makes a slot's level
 * even; for the health boost, whose level is the health it gives, its time refilled at the same health), blinking in
 * its last seconds: its name or its bar, as Mod Settings' Highlight says (the other keeps its state's colour; the
 * notes always do). The colours are worked out every frame and only what changes is written.
 * The group shows only in a quest with the HUD on (the health bar's group shown), while the option is on and the hunter
 * holds a horn; it is not cached (its flag 0x100 cleared), so plain writes show at once.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM; horn_songs.ld).
 */

typedef unsigned int u32;
typedef signed char s8;
typedef unsigned char u8;

#define ROWS 8                  /* layout.py ROWS: the list's row nulls */
#define NOTES 4                 /* layout.py NOTES: a row's note sprites (a song has at most 4 notes) */
#define SONGS 75                /* the game's song table */
#define CLASSES 50              /* the game's note triplets */
#define NO_CLASS 0xFF
#define EFFECTS 52              /* horn_songs.py EFFECT_NEEDS: the game's song effects */
#define SLOTS 29                /* horn_songs.py SLOTS: the hunter's song effect slots */
#define NEEDS 2                 /* an effect's slots, at most */
#define NO_SLOT 0xFF
#define BOOST_SLOT 3            /* the health boost's slot: its level is the health it gives (FUN_00b40140) */
#define BOOST_LEAST 30          /* a least level this high is a health boost's health */
#define EXTEND_SLOT 26          /* effect 0x2A's slot: playing it refills every slot's time */
#define NO_LEVEL 0xFF           /* horn_state.boost_level: not watched last frame */

enum { IDLE, PARTIAL, FULL };
enum { BACKGROUND, TEXT };      /* horn_songs.py MODES: Mod Settings' Highlight, what an effect colours */
enum { NO_EFFECT, NORMAL, ENCORE };

/* the game's objects and tables (blocks.py GAME_SYMBOLS) */
extern u32 gui_control, health_binder, game_control, player_manager;
extern const u8 horn_song_notes[];      /* SONGS x 4 notes, newest first, 0: none */
extern const u8 horn_note_triplets[];   /* CLASSES x 3 notes */
extern const u8 horn_song_names[];      /* SONGS: the name's index */
extern const u32 horn_name_messages[];  /* a name index -> the Menu file's message */
extern const u8 hud_note_cells[];       /* a note (0-8) -> its cell */
extern const u8 horn_song_effects[];    /* SONGS: the song's effect */
extern int mod_option_value(int id);    /* mod_options.c */
extern int mod_option_count(int id);
u32 player_get(u32 manager, int index);                 /* FUN_00af9ab0 */
void gui_group_show(u32 group, u32 shown);               /* FUN_00ae53e0 */
void gui_group_order(u32 group, u32 layer, u32 priority); /* FUN_00ae63c8 */
void text_common(u32 *ref, int file, int message);      /* FUN_005a9164 */
void text_show(u32 text, u32 visible);                  /* FUN_00ae7618 */
void pane_redraw(u32 group, u32 node);                  /* FUN_00ae6bcc */

struct horn_data {              /* the block horn_songs_data (horn_songs.py data_block) */
    u32 group_hash;             /* ~crc32 of the group's name */
    u32 group_index;            /* its slot in the GUI manager */
    u32 layer, priority;
    u32 option_on;              /* mod_options.py OPTION_IDS */
    u32 message_file;           /* the common file of the songs' names (Menu) */
    u32 text_colour[3];         /* IDLE, PARTIAL, FULL: RGBA bytes */
    u32 bar_colour[3];
    u32 note_colour[2];         /* a note not lit, a lit one */
    float cell;                 /* a note's cell: its side in the texture, 0-1 */
    float normal_v;             /* the row of the notes' cells */
    float special_u, special_v; /* the special horn's: where its cells start */
    u32 special_horn;           /* the weapon id whose notes are the special ones */
    u32 effect_bar[2];          /* NORMAL, ENCORE: the bar of a song whose effect the hunter has (BACKGROUND) */
    u32 effect_text[2];         /* and its name (TEXT) */
    u32 option_mode;            /* mod_options.py OPTION_IDS: Highlight (BACKGROUND / TEXT) */
    float blink_below;          /* the time left (ticks) under which the colour blinks */
    float blink_rate;           /* 1 / half the blink's period (ticks): the effect's colour, then the state's */
    u8 needs[EFFECTS][NEEDS][2]; /* an effect's slots and their least levels (slot NO_SLOT: none) */
};

struct horn_row {
    u8 song, count, state, lit; /* its song, its notes, IDLE / PARTIAL / FULL, its first notes lit */
};

struct horn_state {             /* the variable horn_songs_state */
    u32 group;                  /* the group found last, 0: none */
    u32 played;                 /* the notes played the lights were made for */
    u8 shown, rows;
    u8 note_set;                /* the note triplet the rows were made for, NO_CLASS: none */
    u8 special;                 /* 1: the rows have the special horn's notes */
    u8 green;                   /* the rows showing an effect's colour (a bit per row) */
    u8 purple;                  /* of them, the ones in their encore */
    u8 mode;                    /* BACKGROUND / TEXT: the Highlight the rows were made for */
    u8 boost_level;             /* the health boost's slot last frame: its level (NO_LEVEL: not watched), */
    float boost_time;           /* its time left */
    float extend_time;          /* and EXTEND_SLOT's */
    u8 boost_encore;            /* 1: the health boost's time was refilled at the same health (its encore) */
    u8 unused[3];
    struct horn_row row[ROWS];
};

_Static_assert(sizeof(struct horn_data) == 312, "blocks.py HORN_SONGS_DATA_SIZE, horn_songs.py data_block");
_Static_assert(sizeof(struct horn_state) == 60, "blocks.py HORN_SONGS_STATE_SIZE");

extern const struct horn_data horn_songs_data;
extern struct horn_state horn_songs_state;

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define F(p, off) (*(volatile float *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))
#define H(p, off) (*(volatile unsigned short *)((p) + (off)))

#define SHOWN 0x400             /* group + 0x44: drawn */
#define CACHED 0x100            /* group + 0x44: its vertices are kept between frames */
#define GAME_MODE 0x2B          /* sGameControl: 1 in a quest */
#define QUEST_MODE 1
#define LOCAL_INDEX 0x2F        /* sGameControl: this console's player */
#define HUNTER_STATUS 0xE30     /* uPlayer: its status */
#define HUNTER_WORK 0xA29C      /* uPlayer: its work */
#define WEAPON_TYPE 0x1C0       /* status: the weapon's type */
#define WEAPON_ID 0x1C2         /* status: the weapon's id (u16) */
#define HUNTING_HORN 18
#define NOTE_SET 0x16C          /* work: the horn's note triplet */
#define PLAYED 0x930            /* work: the notes played, newest first */
#define EFFECT_LEVEL 0x804      /* work: each song effect slot's level (u8; FUN_0035716c, FUN_00b40140) */
#define EFFECT_TIME 0x824       /* work: each slot's time left (f32, ticks; FUN_00b17260 counts it down, 0 off) */
#define NODE_DATA 0x08          /* a pane's node: its data, */
#define NODE_DIRTY 0x0C         /* its redraw entry (+ DIRTY_MARK: 3 redraws it), */
#define DIRTY_MARK 0x12
#define NODE_KIND 0x10          /* its kind, */
#define NODE_NEXT 0x14          /* its next sibling (a text's: its holder null), */
#define NODE_CHILD 0x20         /* its first child */
enum { KIND_SPRITE, KIND_NULL, KIND_TEXT };
#define NULL_SHOWN 0x24         /* a null's data: bit 0 */
#define SP_UV 0x30              /* a sprite's data: u, v (then w, h) */
#define SP_COLOURS 0x40         /* its corners' colours */
#define SP_FLAGS 0x58           /* its flags: SP_SHOWN */
#define SP_SHOWN 0x80
#define TX_COLOURS 0x38         /* a text's data: its colours (the fourth is the shadow's) */

static int option(u32 id)
{
    return mod_option_count((int)id) != 0 ? mod_option_value((int)id) : 0;
}

static u32 find_group(void)
{
    const struct horn_data *data = &horn_songs_data;
    u32 gui = gui_control, manager, group;

    if (gui == 0 || (manager = W(gui, 0x100)) == 0 || W(manager, 0x154) == 0)
        return 0;
    if (data->group_index >= W(manager, 0x160))
        return 0;
    group = W(W(manager, 0x154), 4 * data->group_index);
    return group != 0 && W(group, 0) == data->group_hash ? group : 0;
}

static int in_quest(void)
{
    u32 control = game_control, hud = health_binder;

    return control != 0 && B(control, GAME_MODE) == QUEST_MODE && hud != 0 && (W(hud, 0x44) & SHOWN) != 0;
}

/* This console's hunter, holding a Hunting Horn: its status; 0 otherwise */
static u32 horn_status(u32 *work)
{
    u32 control = game_control, manager = player_manager, hunter, status;

    if (control == 0 || manager == 0)
        return 0;
    hunter = player_get(manager, (s8)B(control, LOCAL_INDEX));
    if (hunter == 0 || (status = W(hunter, HUNTER_STATUS)) == 0 || (*work = W(hunter, HUNTER_WORK)) == 0)
        return 0;
    if (B(status, WEAPON_TYPE) != HUNTING_HORN || B(*work, NOTE_SET) >= CLASSES)
        return 0;
    return status;
}

static void changed(u32 group, u32 node)
{
    u32 dirty;

    if (node == 0)
        return;
    dirty = W(node, NODE_DIRTY);
    if (dirty != 0)
        B(dirty, DIRTY_MARK) = 3;
    else
        pane_redraw(group, node);
}

/* A row's panes: its bar (the first sprite), its name (the text) and its notes (the sprites after the text) */
struct row_panes {
    u32 bar, text, note[NOTES];
};

static void row_panes(u32 row_null, struct row_panes *out)
{
    u32 node;
    int notes = 0, after_text = 0;

    out->bar = out->text = 0;
    for (node = W(row_null, NODE_CHILD); node != 0; node = W(node, NODE_NEXT)) {
        u32 kind = B(node, NODE_KIND);

        if (kind == KIND_TEXT && out->text == 0)
            out->text = node, after_text = 1;
        else if (kind == KIND_SPRITE && !after_text && out->bar == 0)
            out->bar = node;
        else if (kind == KIND_SPRITE && after_text && notes < NOTES)
            out->note[notes++] = node;
    }
    while (notes < NOTES)
        out->note[notes++] = 0;
}

static u32 row_null(u32 group, int row)
{
    u32 list = W(group, 8), node;
    int i;

    if (list == 0)
        return 0;
    for (i = 0, node = W(list, NODE_CHILD); node != 0 && i < row; i++)
        node = W(node, NODE_NEXT);
    return node;
}

static void null_show(u32 group, u32 node, u32 shown)
{
    u32 data = W(node, NODE_DATA);

    if (((W(data, NULL_SHOWN) & 1) != 0) == (shown != 0))
        return;
    W(data, NULL_SHOWN) = (W(data, NULL_SHOWN) & ~1u) | (shown ? 1 : 0);
    changed(group, node);
}

static void sprite_colour(u32 group, u32 node, u32 colour)
{
    u32 data = W(node, NODE_DATA);
    int i;

    for (i = 0; i < 4; i++)
        W(data, SP_COLOURS + 4 * i) = colour;
    changed(group, node);
}

/* The song's notes in the order they are played (the table's are newest first): their count */
static int song_notes(int song, u8 *notes)
{
    int i, count = 0;

    for (i = NOTES - 1; i >= 0; i--)
        if (horn_song_notes[song * NOTES + i] != 0)
            notes[count++] = horn_song_notes[song * NOTES + i];
    return count;
}

/* FUN_00277e68's rule: every note of the song is one of the triplet's, and it has one */
static int playable(int song, int note_set)
{
    const u8 *triplet = &horn_note_triplets[note_set * 3];
    int i, any = 0;

    for (i = 0; i < NOTES; i++) {
        u8 note = horn_song_notes[song * NOTES + i];

        if (note == 0)
            continue;
        if (note != triplet[0] && note != triplet[1] && note != triplet[2])
            return 0;
        any = 1;
    }
    return any;
}

static void row_text(u32 group, u32 node, int song, u32 colour)
{
    const struct horn_data *data = &horn_songs_data;
    u32 text = W(node, NODE_DATA), ref[2];
    int i;

    for (i = 0; i < 3; i++)     /* a text's colour goes before its string: the glyphs take it when laid out */
        W(text, TX_COLOURS + 4 * i) = colour;
    ref[0] = group, ref[1] = node;
    text_common(ref, (int)data->message_file, (int)horn_name_messages[horn_song_names[song]]);
    text_show(text, 1);
    changed(group, W(node, NODE_NEXT));
}

static int special_horn(u32 status)
{
    return H(status, WEAPON_ID) == horn_songs_data.special_horn;
}

/* The rows of the note triplet `note_set`: names, notes' cells, the rows past the list hidden */
static void build(u32 group, int note_set, int special)
{
    const struct horn_data *data = &horn_songs_data;
    struct horn_state *state = &horn_songs_state;
    int song, row = 0, i;

    for (song = 0; song < SONGS && row < ROWS; song++) {
        u8 notes[NOTES];
        struct row_panes panes;
        u32 null = row_null(group, row);
        int count;

        if (!playable(song, note_set))
            continue;
        if (null == 0)
            break;
        count = song_notes(song, notes);
        state->row[row].song = (u8)song;
        state->row[row].count = (u8)count;
        state->row[row].state = IDLE;
        state->row[row].lit = 0;
        row_panes(null, &panes);
        if (panes.text != 0)
            row_text(group, panes.text, song, data->text_colour[IDLE]);
        if (panes.bar != 0)
            sprite_colour(group, panes.bar, data->bar_colour[IDLE]);
        for (i = 0; i < NOTES; i++) {
            u32 sprite = panes.note[i], d;
            float cell;

            if (sprite == 0)
                continue;
            d = W(sprite, NODE_DATA);
            if (i < count) {
                cell = (float)hud_note_cells[notes[i]] * data->cell;
                F(d, SP_UV) = special ? data->special_u + cell : cell;
                F(d, SP_UV + 4) = special ? data->special_v : data->normal_v;
                W(d, SP_FLAGS) |= SP_SHOWN;
            } else {
                W(d, SP_FLAGS) &= ~SP_SHOWN;
            }
            changed(group, sprite);
        }
        null_show(group, null, 1);
        row++;
    }
    state->rows = (u8)row;
    for (i = row; i < ROWS; i++) {
        u32 null = row_null(group, i);

        if (null != 0)
            null_show(group, null, 0);
    }
    state->note_set = (u8)note_set;
    state->special = (u8)special;
    state->green = state->purple = 0;   /* the rows are idle, with no effect's colour */
    state->played = ~0u;        /* the lights are made again */
}

/* The health boost's encore, which the game does not keep (the slot's level is the health it gives): its time went up
 * since the last frame at the same health, and not because effect 0x2A refilled every slot (its own slot's time went
 * up too); over when the health changes or the time runs out. */
static void watch_boost(u32 work)
{
    struct horn_state *state = &horn_songs_state;
    float time = F(work, EFFECT_TIME + 4 * BOOST_SLOT), extend = F(work, EFFECT_TIME + 4 * EXTEND_SLOT);
    u8 level = B(work, EFFECT_LEVEL + BOOST_SLOT);

    if (!(time > 0.0f) || level != state->boost_level)
        state->boost_encore = 0;
    else if (time > state->boost_time && !(extend > state->extend_time))
        state->boost_encore = 1;
    state->boost_level = level;
    state->boost_time = time;
    state->extend_time = extend;
}

/* The time left of the song's effect on the hunter whose work is `work` (ticks; the least of its slots'), 0 when it
 * does not have it: every slot of its effect with time left at its least level or more. An instant song has none.
 * `*encore`: every slot in its encore (an even level; the health boost's, watch_boost's). */
static float effect_left(u32 work, int song, int *encore)
{
    const struct horn_data *data = &horn_songs_data;
    u32 effect = horn_song_effects[song];
    float left = 0.0f;
    int i;

    *encore = 0;
    if (effect >= EFFECTS)
        return 0.0f;
    *encore = 1;
    for (i = 0; i < NEEDS; i++) {
        u32 slot = data->needs[effect][i][0], least = data->needs[effect][i][1], level;
        float time;

        if (slot == NO_SLOT)
            continue;
        if (slot >= SLOTS)
            return 0.0f;
        time = F(work, EFFECT_TIME + 4 * slot);
        level = B(work, EFFECT_LEVEL + slot);
        if (!(time > 0.0f) || level < least)
            return 0.0f;
        if (least >= BOOST_LEAST ? !horn_songs_state.boost_encore : (level & 1) != 0)
            *encore = 0;
        if (left == 0.0f || time < left)
            left = time;
    }
    return left;
}

/* The rows showing an effect's colour (their song's effect on, and in its last seconds only in the blink's first
 * half), and in `*purple` the ones of them in their encore */
static u32 effect_rows(u32 work, u32 *purple)
{
    const struct horn_data *data = &horn_songs_data;
    const struct horn_state *state = &horn_songs_state;
    u32 green = 0;
    int row;

    *purple = 0;
    for (row = 0; row < state->rows; row++) {
        int encore, half;
        float left = effect_left(work, state->row[row].song, &encore);

        if (!(left > 0.0f))
            continue;
        half = left >= data->blink_below ? 0 : (int)((data->blink_below - left) * data->blink_rate);
        if ((half & 1) != 0)
            continue;
        green |= 1u << row;
        if (encore)
            *purple |= 1u << row;
    }
    return green;
}

static int row_effect(u32 green, u32 purple, int row)
{
    return (green >> row & 1) == 0 ? NO_EFFECT : (purple >> row & 1) != 0 ? ENCORE : NORMAL;
}

/* A row's bar and name in its state with its effect: the effect's colour on what Highlight says, the state's on
 * the other */
static u32 bar_colour(int state, int effect)
{
    const struct horn_data *data = &horn_songs_data;

    return effect != NO_EFFECT && horn_songs_state.mode == BACKGROUND ? data->effect_bar[effect - 1]
                                                                       : data->bar_colour[state];
}

static u32 text_colour(int state, int effect)
{
    const struct horn_data *data = &horn_songs_data;

    return effect != NO_EFFECT && horn_songs_state.mode == TEXT ? data->effect_text[effect - 1]
                                                                 : data->text_colour[state];
}

/* How the notes played (`played`, newest first) meet the song's: FULL, PARTIAL with `lit` notes, or IDLE */
static int match(int song, const u8 *played, int heard, int *lit)
{
    u8 notes[NOTES];
    int count = song_notes(song, notes), k, j;

    *lit = 0;
    if (count == 0)
        return IDLE;
    /* the last k played (oldest of them first: played[k - 1] ... played[0]) are its first k notes */
    for (k = count < heard ? count : heard; k > 0; k--) {
        for (j = 0; j < k && notes[j] == played[k - 1 - j]; j++)
            ;
        if (j == k)
            break;
    }
    *lit = k;
    return k == count ? FULL : k > 0 ? PARTIAL : IDLE;
}

/* The rows' colours with the effects `green` and `purple`; with `notes`, the lights of the notes played too (else the
 * rows keep their states and only those whose effect changed are looked at). A name is laid out again, and a bar
 * coloured, only when its colour changes. */
static void colour_rows(u32 group, u32 work, u32 green, u32 purple, int notes)
{
    const struct horn_data *data = &horn_songs_data;
    struct horn_state *state = &horn_songs_state;
    u8 played[NOTES];
    int heard = 0, row, i;

    while (notes && heard < NOTES && (played[heard] = B(work, PLAYED + heard)) != 0)
        heard++;
    for (row = 0; row < state->rows; row++) {
        struct horn_row *r = &state->row[row];
        struct row_panes panes;
        int was = row_effect(state->green, state->purple, row), is = row_effect(green, purple, row);
        int lit = r->lit, now = r->state;
        u32 null;

        if (!notes && was == is)
            continue;
        if ((null = row_null(group, row)) == 0)
            break;
        if (notes)
            now = match(r->song, played, heard, &lit);
        row_panes(null, &panes);
        if (panes.text != 0 && text_colour(now, is) != text_colour(r->state, was))
            row_text(group, panes.text, r->song, text_colour(now, is));
        if (panes.bar != 0 && bar_colour(now, is) != bar_colour(r->state, was))
            sprite_colour(group, panes.bar, bar_colour(now, is));
        for (i = 0; notes && i < NOTES; i++)
            if (panes.note[i] != 0)
                sprite_colour(group, panes.note[i], data->note_colour[i < lit]);
        r->state = (u8)now;
        r->lit = (u8)lit;
    }
    state->green = (u8)green;
    state->purple = (u8)purple;
}

static void hide(struct horn_state *state)
{
    state->boost_level = NO_LEVEL;      /* nothing watched while hidden: no encore seen across the gap */
    if (state->group != 0 && state->shown) {
        gui_group_show(state->group, 0);
        state->shown = 0;
    }
}

/* the quest's shared frame hook: sMhMain::frame, after every system's move and before the render */
void horn_frame(void)
{
    const struct horn_data *data = &horn_songs_data;
    struct horn_state *state = &horn_songs_state;
    u32 group = find_group(), status = 0, work = 0, played, green, purple;
    u8 mode;

    if (group != state->group) {        /* a new quest's group, or none */
        state->group = group;
        state->shown = 0;
        state->note_set = NO_CLASS;
        state->boost_level = NO_LEVEL;
        if (group != 0)
            W(group, 0x44) &= ~CACHED;
    }
    if (group == 0)
        return;
    if (option(data->option_on) != 0 && in_quest())
        status = horn_status(&work);
    if (status == 0) {
        hide(state);
        return;
    }
    mode = option(data->option_mode) != 0 ? TEXT : BACKGROUND;
    if (mode != state->mode) {          /* Highlight changed: the rows are made again in the new colours */
        state->mode = mode;
        state->note_set = NO_CLASS;
    }
    if (state->note_set != B(work, NOTE_SET) || state->special != special_horn(status))
        build(group, B(work, NOTE_SET), special_horn(status));      /* another horn (the camp's box) */
    watch_boost(work);
    played = (u32)B(work, PLAYED) | (u32)B(work, PLAYED + 1) << 8 | (u32)B(work, PLAYED + 2) << 16 |
             (u32)B(work, PLAYED + 3) << 24;
    green = effect_rows(work, &purple);
    if (played != state->played) {
        colour_rows(group, work, green, purple, 1);
        state->played = played;
    } else if (green != state->green || purple != state->purple) {
        colour_rows(group, work, green, purple, 0);
    }
    if (!state->shown) {
        gui_group_show(group, 1);
        gui_group_order(group, data->layer, data->priority);
        state->shown = 1;
    }
}
