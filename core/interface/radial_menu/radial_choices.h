/* The item wheel's choices for the character in play, as radial_wheel.c reads them from the save zone each frame: the
item of each slot (0 none), the position (0 centre, 1 right, 2 bottom
 * left), the size (an index of the curated draw_sizes), whether the wheel is on, whether Auto-Combine is on, the
 * trigger (0 Tilt, 1 Flick, 2 Release, 3 ZR) and the names' text size (an index of the curated draw_text_sizes). A choice the
 * character never made is the curated default (radial_data). */

#ifndef RADIAL_CHOICES_H
#define RADIAL_CHOICES_H

#define WHEEL_SLOTS 8
#define MAX_SIZES 8             /* radial_draw.py MAX_SIZES: the sizes the zone's half byte and the draw data hold */
#define CHOOSE_POSITION 8       /* radial_choose's `which` past the slots */
#define CHOOSE_ENABLED 9
#define CHOOSE_SIZE 10
#define CHOOSE_AUTOCRAFT 11
#define CHOOSE_TRIGGER 12
#define CHOOSE_TEXT 13
#define POSITIONS 3             /* centre, right, bottom left */
#define TRIGGERS 4              /* Tilt, Flick, Release, ZR */
#define MAX_TEXTS 4             /* radial_draw.py MAX_TEXTS: the Text Size row's sizes the draw data holds */

struct choices {
    unsigned short slots[WHEEL_SLOTS];
    unsigned char position;
    unsigned char enabled;
    unsigned char size;
    unsigned char autocraft;
    unsigned char trigger;
    unsigned char text;         /* the names' size: an index of the curated draw_text_sizes */
};

/* The wheel's picture in Edit Slots (radial_draw.c), called by radial_editor.c once a
 * frame while Edit Slots is open and once with layout 0 on every way out: `layout` 0 hides it, 1 centred, 2 small at the
 * left beside the pouch list; `marked` is the gold slot (0xFF none); `preview_item` / `preview_count` what the gold slot
 * shows (0: its saved item). */
void radial_menu_wheel(const struct choices *c, unsigned int layout, unsigned int marked, unsigned int preview_item,
                       unsigned int preview_count);

/* Edit Slots' hold on the C-stick (the variable radial_stick_hold):
 * radial_editor.c sets it to STICK_HOLD each frame one of Edit Slots' levels is open and to 0 at the menu level and
 * every way out; the hunter's input update in a quest (radial_wheel.c) counts it down and, while it is above 0, hides
 * the C-stick from the camera as the open wheel does. Two frames, so the order of the menu's frame and the hunter's
 * does not matter, and a menu gone without a word gives the stick back a frame later. */
#define STICK_HOLD 2
extern unsigned int radial_stick_hold;

#endif
