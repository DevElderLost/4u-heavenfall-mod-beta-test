/* The list of an option's values, the screen a row of Mod Settings opens (interface/mod_settings/mod_settings.c): the
game's big list, a page of up to ten values in a frame of as many rows (a list of
 * 13: 10, then 3) and the pager when there are more, the value in use marked and under the cursor when it opens. Up
 * and Down go round the page's values, Left and Right turn the pages (on the same row, or the page's last). A uses the
 * row's value at once, for this character (mod_option_choose; mod_frame applies it the next frame). B goes back.
 *
 * Build: a unit of the block mod_settings_code (tools/build/build_code_space.py).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define PAGE_ROWS 10            /* mod_settings.py LIST_ROWS */
#define KEY_UP 1
#define KEY_DOWN 2
#define KEY_LEFT 4
#define KEY_RIGHT 8
#define KEY_A 0x10
#define KEY_B 0x20
#define SOUND_DECIDE 1          /* FUN_0031294c */
#define TEXT_HELP 0             /* mod_option_text */
#define TEXT_ROW 1
#define TEXT_MARKED 2

struct option_list_state {
    u8 option;                  /* the option on the screen */
    u8 row;                     /* the cursor: a place in its values */
    u8 page;                    /* the page on the screen */
    u8 pad;
};

extern struct option_list_state option_list_state;
extern void *sound_control;

void sound_play(void *control, int sound);                      /* FUN_0031294c */
int start_step(int value, int count, u32 keys, u32 minus, u32 plus);    /* FUN_005e70bc: wraps, with the move sound */
void mod_list_open(void);                                       /* mod_settings.c */
void mod_list_title(int message);
void mod_list_help(int message);
void mod_list_slot_text(int row, int message, int text);
void mod_list_blank(int row);
void mod_list_rows(int rows);
void mod_list_frame(int row_on_page, int page, int pages);
int mod_option_saved(void);                                     /* mod_options.c */
int mod_option_value(int id);
int mod_option_count(int id);
int mod_option_name(int id, int value);
int mod_option_text(int which);
void mod_option_choose(int id, int value);

static int pages(void)
{
    return (mod_option_count(option_list_state.option) + PAGE_ROWS - 1) / PAGE_ROWS;
}

/* The values on page `page` */
static int rows_on(int page)
{
    int rows = mod_option_count(option_list_state.option) - page * PAGE_ROWS;

    return rows > PAGE_ROWS ? PAGE_ROWS : rows;
}

static void draw_rows(void)
{
    int id = option_list_state.option;
    int selected = mod_option_value(id);
    int count = mod_option_count(id);
    int first = option_list_state.page * PAGE_ROWS;
    int row;

    mod_list_rows(rows_on(option_list_state.page));
    for (row = 0; row < PAGE_ROWS; row++)
        if (first + row < count)
            mod_list_slot_text(row, mod_option_text(first + row == selected ? TEXT_MARKED : TEXT_ROW),
                               mod_option_name(id, first + row));
        else
            mod_list_blank(row);
}

static void show_frame(void)
{
    mod_list_frame(option_list_state.row - option_list_state.page * PAGE_ROWS, option_list_state.page, pages());
}

/* A on a row that opens the values of option `id`: 0 without a save, and nothing has opened */
int option_screen_open(int id, int title)
{
    if (!mod_option_saved())
        return 0;
    mod_list_open();
    option_list_state.option = id;
    option_list_state.row = mod_option_value(id);
    option_list_state.page = option_list_state.row / PAGE_ROWS;
    mod_list_title(title);
    draw_rows();
    mod_list_help(mod_option_text(TEXT_HELP));
    show_frame();
    return 1;
}

/* Each frame of the screen: 1 goes back to the small list */
int option_screen_frame(u32 pressed, u32 keys)
{
    if (!mod_option_saved() || (pressed & KEY_B))
        return 1;
    if (pressed & KEY_A) {
        sound_play(sound_control, SOUND_DECIDE);
        mod_option_choose(option_list_state.option, option_list_state.row);
        draw_rows();
    } else if (keys & (KEY_UP | KEY_DOWN)) {        /* round the page's values */
        int first = option_list_state.page * PAGE_ROWS;

        option_list_state.row = first + start_step(option_list_state.row - first, rows_on(option_list_state.page), keys,
                                                   KEY_UP, KEY_DOWN);
    } else if ((keys & (KEY_LEFT | KEY_RIGHT)) && pages() > 1) {
        int row = option_list_state.row - option_list_state.page * PAGE_ROWS;
        int page = start_step(option_list_state.page, pages(), keys, KEY_LEFT, KEY_RIGHT);

        if (row >= rows_on(page))
            row = rows_on(page) - 1;
        option_list_state.page = page;
        option_list_state.row = page * PAGE_ROWS + row;
        draw_rows();
    }
    show_frame();
    return 0;
}
