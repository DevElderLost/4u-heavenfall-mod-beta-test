/* Hold L in Change Appearance to see the hunter (interface/appearance_peek/appearance_peek.py; docs/gameplay/
 * item_box.md, "Hiding the interface with L"): while L is held the top screen draws no interface, and a cue in a corner
 * says so.
 *
 * Each of the hunter edit's five updates (FUN_00a9ed84, FUN_00a9c070, FUN_00aa3854, FUN_00a9a5f8, FUN_00a983bc, one
 * per choice of Change Appearance) calls the box's View Mode, FUN_00a8bb9c(scene, menu, 1), before anything else reads
 * a key, and returns at once when it answers 1. Those five calls come here instead:
 *   - with L held (the GUI's held word), the scene taking keys, outside the View Mode and at the house's kind of box,
 *     the layout manager stops drawing on the top screen (its mDrawView loses view 0, as the View Mode itself does) and
 *     the answer is 1: no key of the edit acts while it is hidden, and the Circle Pad still turns the hunter
 *     (FUN_00a1e654 runs before the call);
 *   - else the top screen is drawn again if this hid it, and the game's FUN_00a8bb9c answers.
 * The cue (the root group the run adds to ui401, the lobby's facility menu, every town area's) is shown while the edit
 * runs; it is drawn on the top screen, so it goes with the rest while L is held and in the View Mode. mod_frame calls
 * appearance_peek_frame once a frame: when the edit has not run for `misses` frames (it closed, or the scene went), the
 * cue is hidden and the top screen given back.
 *
 * A unit of the block mod_settings_code (blocks.py), with the screen kit. */

#include "../screen_kit/screen_kit.h"

#define PAD_HELD 0x340          /* the pad object: the GUI's buttons held */
#define BUTTON_L 0x100
#define SCENE_KEYS 0x97D6       /* the town scene: a u16, not 0 while it takes no key (FUN_009ac3a4 reads it) */
#define MENU_BOX 2              /* the box menu: its kind of box (0 the house's), */
#define MENU_VIEW 3             /* and its View Mode (0 off; FUN_00a93250 toggles it) */
#define DRAW_VIEWS 4            /* the layout manager (a cUnit): its flags, bits 16-25 the views it draws in */
#define TOP_VIEW 0x10000u       /* view 0, the top screen */

struct peek_data {              /* appearance_peek.py data_block */
    u32 cue_group;              /* the hash of the cue's root group (0: no cue) */
    u32 cue_text;               /* the hash of its word's text pane */
    u16 file;                   /* the lobby message file of the word (ItemBox) */
    u16 message;                /* the word's message there (0: none) */
    u8 priority;                /* the cue's draw priority */
    u8 misses;                  /* frames without the edit before the cue goes */
    u8 pad[2];
};

struct peek_state {             /* the variable appearance_peek_state */
    u8 seen;                    /* the edit ran since the last frame */
    u8 shown;                   /* the cue is shown */
    u8 pad;
    u8 missed;                  /* frames the edit has not run */
};

_Static_assert(sizeof(struct peek_data) == 16, "appearance_peek.py DATA");
_Static_assert(sizeof(struct peek_state) == 4, "blocks.py: the variable appearance_peek_state");

extern const struct peek_data appearance_peek_data;
extern struct peek_state appearance_peek_state;
extern u32 top_screen_hidden;   /* 1 while this took view 0 from the layout manager: the game GUI engine (single-screen
                                   mode), which adds every view it places a group in, leaves it out then */
extern u32 pad_control;
GAME u32 box_view_mode(u32 scene, u8 *menu, u32 mode);                 /* FUN_00a8bb9c */
GAME void text_lobby(void *ref, u32 file, u32 message);                /* FUN_005a882c */

static u32 manager(void)
{
    return gui_control ? *(u32 *)(gui_control + GUI_LAYOUTS) : 0;
}

static void top_view(int drawn)
{
    u32 m = manager();

    if (drawn && top_screen_hidden) {
        if (m)
            *(u32 *)(m + DRAW_VIEWS) |= TOP_VIEW;
        top_screen_hidden = 0;
    } else if (!drawn && m) {           /* every frame: anything else that gives the view back is undone */
        *(u32 *)(m + DRAW_VIEWS) &= ~TOP_VIEW;
        top_screen_hidden = 1;
    }
}

static void cue_show(int shown)
{
    const struct peek_data *d = &appearance_peek_data;
    struct peek_state *s = &appearance_peek_state;
    struct ref r;
    u32 group, *text;

    s->shown = (u8)shown;
    if (!d->cue_group || !d->message || !manager() || !(group = kit_group(d->cue_group)))
        return;
    kit_group_show(group, (u32)shown, d->priority);
    if (shown && (text = kit_text(&r, group, d->cue_text)) != 0) {
        text_lobby(&r, d->file, d->message);
        text_show((u32)text, 1);
        kit_text_changed(&r);
    }
}

static int l_held(u32 scene, const u8 *menu)
{
    u32 pad = pad_control;
    return pad && menu[MENU_BOX] == 0 && menu[MENU_VIEW] == 0 && *(const u16 *)(scene + SCENE_KEYS) == 0
        && (*(const u32 *)(pad + PAD_HELD) & BUTTON_L);
}

/* The five updates' call of FUN_00a8bb9c(scene, menu, mode). */
u32 appearance_peek(u32 scene, u8 *menu, u32 mode)
{
    struct peek_state *s = &appearance_peek_state;

    s->seen = 1;
    s->missed = 0;
    if (!s->shown)
        cue_show(1);
    if (l_held(scene, menu)) {
        top_view(0);
        return 1;
    }
    top_view(1);
    return box_view_mode(scene, menu, mode);
}

/* mod_frame's, once a frame before the scene's update. */
void appearance_peek_frame(void)
{
    struct peek_state *s = &appearance_peek_state;

    if (s->seen) {
        s->seen = 0;
        return;
    }
    if (!s->shown && !top_screen_hidden)
        return;
    if (++s->missed < appearance_peek_data.misses)
        return;
    cue_show(0);
    top_view(1);
    s->missed = 0;
}
