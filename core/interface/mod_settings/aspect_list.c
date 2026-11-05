/* The list of aspect ratios, the screen Mod Settings opens (interface/mod_settings/mod_settings.c; docs/cheats/
 * aspect_ratio.md, "The list in the game"): one page of the game's big list, the ratio in use marked and under the cursor
 * when it opens. A uses the row's ratio at once, for this character: the picture changes the next frame. B goes back.
 *
 * Build: a unit of the block mod_settings_code (tools/build/build_code_space.py).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define PAGE_ROWS 8             /* mod_settings.py LIST_ROWS */
#define KEY_UP 1
#define KEY_DOWN 2
#define KEY_A 0x10
#define KEY_B 0x20
#define SOUND_DECIDE 1          /* FUN_0031294c */

struct aspect_list_data {       /* mod_settings.py aspect_list_data */
    u16 help, row, marked;
    u16 names[PAGE_ROWS];       /* the text `row` or `marked` holds on each row */
};

struct aspect_list_state {
    u8 row;                     /* the cursor */
};

extern const struct aspect_list_data aspect_list_data;
extern struct aspect_list_state aspect_list_state;
extern void *sound_control;

void sound_play(void *control, int sound);                      /* FUN_0031294c */
int start_step(int value, int count, u32 keys, u32 minus, u32 plus);    /* FUN_005e70bc: wraps, with the move sound */
void mod_list_open(void);                                       /* mod_settings.c */
void mod_list_title(int message);
void mod_list_help(int message);
void mod_list_slot_text(int row, int message, int text);
void mod_list_blank(int row);
void mod_list_frame(int row_on_page, int page, int pages);
int aspect_saved(void);                                         /* cheats/aspect_ratio.c */
int aspect_ratios(void);
int aspect_selected(void);
void aspect_choose(int place);

static void draw_rows(void)
{
    int selected = aspect_selected();
    int count = aspect_ratios();
    int row;

    for (row = 0; row < PAGE_ROWS; row++)
        if (row < count)
            mod_list_slot_text(row, row == selected ? aspect_list_data.marked : aspect_list_data.row,
                               aspect_list_data.names[row]);
        else
            mod_list_blank(row);
}

/* A on the row that opens the list: 0 without a save, and nothing has opened */
int aspect_screen_open(int title)
{
    if (!aspect_saved())
        return 0;
    mod_list_open();
    aspect_list_state.row = aspect_selected();
    mod_list_title(title);
    draw_rows();
    mod_list_help(aspect_list_data.help);
    mod_list_frame(aspect_list_state.row, 0, 1);
    return 1;
}

/* Each frame of the screen: 1 goes back to the small list */
int aspect_screen_frame(u32 pressed, u32 keys)
{
    if (!aspect_saved() || (pressed & KEY_B))
        return 1;
    if (pressed & KEY_A) {
        sound_play(sound_control, SOUND_DECIDE);
        aspect_choose(aspect_list_state.row);
        draw_rows();
    } else if (keys & (KEY_UP | KEY_DOWN)) {
        aspect_list_state.row = start_step(aspect_list_state.row, aspect_ratios(), keys, KEY_UP, KEY_DOWN);
    }
    mod_list_frame(aspect_list_state.row, 0, 1);
    return 0;
}
