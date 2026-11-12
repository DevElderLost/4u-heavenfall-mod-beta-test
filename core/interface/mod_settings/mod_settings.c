/* The START menu's Mod Settings (interface/mod_settings/mod_settings.py). The stub (mod_settings_stub.s) calls these
functions from the game's menu code.
 *
 * The third page: mod_menu_page fills the page's record each frame, as FUN_005e8050 does for its own pages. Its first row
 * has our action (mod_line_action) and description (mod_menu_description); the rest of the rows stay grey.
 *
 * A on the row: mod_menu_pick makes the menu a sub-screen of our kind, so FUN_005f6ae4 calls mod_menu_frame each frame.
 * The sub-screen has two levels, in mod_settings_state:
 *   - a list: the game's small list (FUN_00611b10, FUN_005e87b4, FUN_0060fbc0, FUN_005e84f0, as its kind 0xE uses them)
 *     with one row per entry of the table's current list. Up and Down go round the page's rows, A opens the row's list
 *     (the same widget, closed and filled again: FUN_005e87b4 sets it up whole) or its screen, B goes back: to the row
 *     of the list above, or from the top list by FUN_005e86b0, FUN_006201dc(1), FUN_0060f220 and return 2, which
 *     FUN_005f6ae4 takes as back to the page. A page has up to ten rows: the game's five lines and ui020's five more
 *     (ten_rows.py), which this code writes and colours. A page of n rows shows exactly n in a frame of n: the game's
 *     own for 2 to 5 rows, ui020's of ours for 1 and 6 to 10, which this code shows in place of the game's while the
 *     list is open (and hides again on every way out: the game's own lists use the same groups). A list of 11 to 20
 *     rows has two pages: Left and Right turn them, and the menu's title bar says "1/2" or "2/2" instead of its "3/3";
 *   - a screen: the aspect ratios (aspect_list.c) or an option's values (option_list.c), on the game's big list. The
 *     mod_list_* functions drive that widget (its groups, title, ten rows, cursor and pager) as FUN_0060bf60 and
 *     FUN_0061ae20 do for Weapon Controls, with ui020's two rows more, in the game's frame of eight rows or ui020's of
 *     ours for the page's rows (mod_list_rows).
 *
 * START at any level closes the whole menu through the game's own code (FUN_00624ddc), which unbinds the list's widgets
 * and runs FUN_0060d058, where mod_menu_closed ends our bind of the pager; a new pick starts on the top list's first
 * row.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM, linked with mod_settings.ld where it places the
 * block); the game's functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef short s16;

#define ACTION 0x14             /* mod_settings.py ACTION */
#define KIND 0x2F               /* mod_settings.py KIND */
#define MAX_LISTS 10            /* mod_settings.py MAX_LISTS */
#define MAX_TABLE 64            /* mod_settings.py MAX_TABLE */
#define SUBLIST_ROWS 5          /* mod_settings.py SUBLIST_ROWS: the game's own lines of its small list */
#define PAGE_LIST_ROWS 10       /* mod_settings.py LIST_PAGE_ROWS: a page of a small list */
#define BIG_GAME_ROWS 8         /* the game's own lines of its big list; ui020 has two more (ten_rows.py) */
#define BIG_ROWS 10             /* mod_settings.py LIST_ROWS */
#define NO_LIST 0xFF            /* mod_settings.py NO_LIST */
#define SCREEN_ASPECT 0         /* mod_settings.py SCREENS */
#define SCREEN_OPTION 1
#define NO_ACTION 0xFF          /* FUN_00600658: a line with no action, the error sound on A */
#define PAGE 2                  /* the third page, +0x11 */

/* The menu's object (0x108B9BC) */
#define M_STATE 0x0             /* u8: 1 a sub-screen */
#define M_SUBSTATE 0x1          /* u8 */
#define M_KIND 0xA              /* u8: the sub-screen's kind */
#define M_PAGE_COUNT 0x10       /* u8: the menu's pages (3: FUN_0060cd50, patched), shown in its title bar */
#define M_PAGE 0x11             /* u8: the page on the screen */
#define MENU_PAGES 3
#define M_ROWS 0xC              /* s16: the page's rows */
#define M_PAGE_ENABLED 0x5A     /* u8: the third page's record (0x2A + page * 0x18) can take A */
#define M_ROW_ENABLED 0xA2      /* u8: its first row's record can take A */
#define M_LINES 0x440           /* the page's line table: 8 of (u16 file, u16 message) */
#define M_LINE_MARKS 0x444      /* a table of marks on the page's lines: none */
#define M_SUB_BASE 0x338        /* float: the small list cursor's y at its first row (FUN_005e87b4; FUN_005e84f0 reads it) */
#define M_PRESSED 0x558         /* u32: the buttons pressed this frame */
#define M_REPEAT 0x56C          /* u32: the buttons with their hold repeat */
#define PAGE_ROWS 6             /* the smallest frame the page's list has; its last two rows are hidden */

#define KEY_UP 1
#define KEY_DOWN 2
#define KEY_LEFT 4
#define KEY_RIGHT 8
#define KEYS_REPEAT 0xF         /* the D-pad's bits of M_REPEAT */
#define KEY_A 0x10
#define KEY_B 0x20

#define SOUND_DECIDE 1          /* FUN_0031294c */
#define SOUND_CANCEL 2
#define SOUND_ERROR 3

#define KIND_TEXT 0             /* FUN_00298560, FUN_0060fbc0: the plain text of the common files */
#define HELP_ON 1               /* FUN_002a4260(1, 0xB), as every sub-screen shows its description */
#define HELP_PRIORITY 0xB

/* The list widgets' binder (start_list_ui) */
#define UI_BIG_CURSOR 0x44      /* the big list's cursor pane: its y at +0x2C */
#define UI_TITLE 0x94           /* the big list's title, a pane ref */
#define UI_ROWS 0x9C            /* the big list's first row, a pane ref */
#define UI_CURSOR_PANE 0xEC     /* the big list's cursor, a pane ref */
#define UI_ICONS 0xF4           /* the big list's icons: (group, null pane) */
#define UI_CURSOR_ANIM 0x14C    /* the cursor's animation */
#define GROUP_FRAME 0xD         /* the big list's groups, in the order FUN_0060bf60 shows them */
#define GROUP_ICON_BACK 0x10
#define GROUP_ROWS 0x12
#define GROUP_CURSOR 0x11
#define GROUP_SMALL_FRAME 7     /* the small list's groups FUN_005e87b4 places: its frames and strips (4 to 5 rows, */
#define GROUP_SMALL_FRAME_3 8   /* 3 rows, 2 rows), lines, cursor */
#define GROUP_SMALL_FRAME_2 9
#define GROUP_SMALL_LINES 0xB
#define GROUP_SMALL_CURSOR 10
#define GROUP_Y 0x2C            /* a group's y (the binder holds a group's pointer at +4 k) */
#define UI_LAST_LINE 0x8C       /* the small list's fifth line's pane ref, m_14 (+0x54 + 8 k, k = 7: table 0xF20320) */
#define ROW_HEIGHT (-18)        /* the cursor's y per row (FUN_0060bf60) */
#define NULL_SHOWN 0x24         /* a null's data: bit 0 shows it */
#define LINE_COLOUR 0x38        /* a text pane's data: its colour; the null after it has it at +0x18 (FUN_005e84f0) */
#define HOLDER_COLOUR 0x18
#define COLOUR_ROW 0xFFC3C3C3u  /* FUN_005e84f0's colours: a row, the row under the cursor, a grey row (FUN_0060caec) */
#define COLOUR_SELECTED 0xFFF0F0F0u
#define COLOUR_OFF 0xFF646464u
#define TEN_SMALL 1             /* mod_settings_state.ten: the small list's panes of ours are up */
#define TEN_BIG 2               /* ... the big list's */

/* ten_rows.py NAMED: the panes found by their name hash in a group's first level */
enum { SMALL_FRAME_4, SMALL_FRAME_5, SMALL_STRIPS, SMALL_STRIPS_OURS, BIG_FRAME, BIG_STRIPS, BIG_BACKS, BIG_STRIPS_OURS,
       BIG_BACKS_OURS, PANES };
#define STRIP_SPRITES 2         /* a row's sprites in a strips null; a backings null has one */

#define TEXT_SLOT 0             /* the string slot a message's number node takes (FUN_005a99a8) */

#define PANE_FIRST_CHILD 0x20   /* a null pane's first child */
#define SPRITE_DATA 0x8         /* a sprite pane's draw data; its bit 0x80 at +0x58 shows it */
#define SPRITE_SHOWN 0x80
#define DATA_SHOW 0x58
#define PANE_REDRAW 0xC         /* a pane's redraw entry, marked with 3 at +0x12 */
#define REDRAW_MARK 0x12
#define PANE_KIND 0x10          /* a pane's kind in the low byte: 0 a sprite */
#define PANE_NEXT 0x14          /* a pane's next sibling */
#define TEXT_HOLDER 0x14        /* a text pane's pane, the one that holds its redraw entry */
#define GUI_ANIM_OWNER 0x110    /* the GUI object: what a cursor's animation binds to */
#define MAIN_DELTA 0x5C         /* the main object: the frame's time, a float */

struct mod_entry {
    u16 name, help;
    u16 title;                  /* its screen's title */
    u8 list;                    /* the list it opens, NO_LIST for a screen */
    u8 screen;
    u8 arg;                     /* the screen's option */
    u8 pad;
};

struct mod_list {
    u8 first, count;            /* its rows in the table */
    u8 parent, parent_row;      /* where B goes: NO_LIST from the top list */
};

struct mod_settings_data {      /* the curated table (mod_settings.py settings_data) */
    u16 lines[8][2];            /* the page's line table */
    u16 line_help;
    u16 placeholder;            /* the grey row's message (the page's rows; the lists have none) */
    u16 file;
    s16 pager_x, pager_y;       /* where the lists' pager goes (FUN_005edcf4) */
    struct mod_list lists[MAX_LISTS];
    struct mod_entry entries[MAX_TABLE];
    u32 panes[PANES];           /* their name hashes */
    u32 small_frames[PAGE_LIST_ROWS];   /* the hash of our small list's frame of n rows at n - 1, 0: the game's frame */
    u32 big_frames[BIG_ROWS];           /* ... the big list's */
    u8 raise[PAGE_LIST_ROWS];   /* how far up a small list goes, by its first page's rows - 1 (single-screen mode, else 0) */
    u16 pad;
};
_Static_assert(sizeof(struct mod_settings_data) == 852, "blocks.py MOD_SETTINGS_DATA_SIZE");
_Static_assert(__builtin_offsetof(struct mod_settings_data, panes) == 724, "blocks.py MOD_SETTINGS_PANE_HASHES");
_Static_assert(__builtin_offsetof(struct mod_settings_data, raise) == 840, "blocks.py MOD_SETTINGS_PANE_HASHES");

enum { LEVEL_LIST, LEVEL_SCREEN };

struct mod_settings_state {
    u8 level;
    u8 cursor;                  /* the row the list is on, in the whole list (its page: cursor / SUBLIST_ROWS) */
    u8 pager;                   /* 1 while our bind of the pager stands */
    u8 list;                    /* the list on the screen, or under the screen */
    u8 screen;                  /* the screen open */
    u8 open;                    /* 1 from the pick until the player leaves: single_screen_prompt.s reads it */
    u8 list_numbers;            /* 1 while the title bar says the page of a list of two pages */
    u8 ten;                     /* TEN_SMALL, TEN_BIG: ui020's panes of ten rows up */
};
_Static_assert(__builtin_offsetof(struct mod_settings_state, open) == 5, "single_screen.py MOD_SETTINGS_OPEN");

extern const struct mod_settings_data mod_settings_data;
extern struct mod_settings_state mod_settings_state;

extern char start_list_ui[];
extern char start_menu[];               /* the menu's object, the one the stubs pass as `menu` */
extern void *common_files[];
extern char *gui_control, *game_main;
extern void *sound_control;

void start_sublist_begin(void);                                 /* FUN_00611b10 */
void start_top_cursor(int shown);                               /* FUN_006201dc */
void start_sublist_open(int action, int rows);                  /* FUN_005e87b4 */
void start_sublist_text(int row, int kind, int file, int message);      /* FUN_0060fbc0 */
void start_sublist_cursor(int row);                             /* FUN_005e84f0: also steps the cursor's animation */
void start_sublist_close(void);                                 /* FUN_005e86b0 */
void start_sublist_end(void);                                   /* FUN_0060f220 */
int start_step(int value, int count, u32 keys, u32 minus, u32 plus);    /* FUN_005e70bc: wraps, with the move sound */
void start_help_show(int on, int priority);                     /* FUN_002a4260 */
void facility_help(int kind, int file, int message);            /* FUN_00298560 */
void start_list_group(char *binder, int group, int shown);      /* FUN_00d94358 */
void text_common(void *pane_ref, int file, int message);        /* FUN_005a9164 */
void text_set(void *pane, void *group, const void *text, int length, const void *format);       /* FUN_00ae4ef0 */
void text_slot(int slot, const void *text, int length);         /* FUN_005a99a8 */
const u32 *message_string(void *file, int message);             /* FUN_00cdfa80: (text, length, length), 0 past the file */
void gui_ref_next(u32 *next, const u32 *ref);                   /* FUN_00d03820: the ref of the next pane */
void gui_anim_bind(void *pane_ref, void *anim, void *owner, int zero);  /* FUN_00585094 */
__attribute__((pcs("aapcs-vfp"))) void gui_anim_step(void *anim, float delta);  /* FUN_00ae1ddc */
void pane_redraw(void *group, void *pane);                      /* FUN_00ae6bcc */
void sound_play(void *control, int sound);                      /* FUN_0031294c */
void start_pager_bind(int x, int y);                            /* FUN_005edcf4 */
void start_pager_release(void);                                 /* FUN_005edc88 */
void start_pager_show(int page, int pages, int a, int b, int c);        /* FUN_005ed704 */
void start_pager_hide(void);                                    /* FUN_005edcbc */
void start_page_numbers(void);                                  /* FUN_00608028: the menu's "page/pages" in its title bar */

int aspect_screen_open(int title);                              /* aspect_list.c */
int aspect_screen_frame(u32 pressed, u32 keys);                  /* aspect_list.c */
int option_screen_open(int option, int title);                  /* option_list.c */
int option_screen_frame(u32 pressed, u32 keys);                 /* option_list.c */

static u32 word_at(const char *object, int at)
{
    return *(const u32 *)(object + at);
}

static char *pointer_at(const char *object, int at)
{
    return *(char *const *)(object + at);
}

static void play(int sound)
{
    sound_play(sound_control, sound);
}

static void mark_redraw(void *group, char *pane)
{
    char *entry = pointer_at(pane, PANE_REDRAW);

    if (entry != 0)
        entry[REDRAW_MARK] = 3;
    else
        pane_redraw(group, pane);
}

/* ---- ui020's panes of every list size (ten_rows.py) */

static char *group_of(int group)
{
    return pointer_at(start_list_ui, 4 * group);
}

/* The pane whose name hash is `hash` in the first level of the binder's group `group`, 0 if it has none */
static char *pane_named(int group, u32 hash)
{
    char *pane = group_of(group) != 0 ? pointer_at(group_of(group), 8) : 0;

    while (pane != 0 && word_at(pane, 0) != hash)
        pane = pointer_at(pane, PANE_NEXT);
    return pane;
}

/* A null of the group's first level shown or hidden; a hash of 0 (a size whose frame is the game's) names none */
static void show_hashed(int group, u32 hash, int shown)
{
    char *pane = hash != 0 ? pane_named(group, hash) : 0;
    u32 *flags;

    if (pane == 0 || pointer_at(pane, SPRITE_DATA) == 0)
        return;
    flags = (u32 *)(pointer_at(pane, SPRITE_DATA) + NULL_SHOWN);
    *flags = shown ? *flags | 1u : *flags & ~1u;
    mark_redraw(group_of(group), pane);
}

static void show_null(int group, int which, int shown)
{
    show_hashed(group, mod_settings_data.panes[which], shown);
}

/* A null of ours that holds a page's rows of strips or backings (`per_row` sprites a row, row by row): shown with the
 * sprites of its first `rows` rows, as FUN_00d94bd4 shows a sprite; 0 rows hides it */
static void show_rows(int group, int which, int rows, int per_row)
{
    char *null = pane_named(group, mod_settings_data.panes[which]);
    char *sprite;
    int row = 0, in_row = 0;

    show_null(group, which, rows > 0);
    if (null == 0 || rows == 0)
        return;
    for (sprite = pointer_at(null, PANE_FIRST_CHILD); sprite != 0; sprite = pointer_at(sprite, PANE_NEXT)) {
        u32 *flags = (u32 *)(pointer_at(sprite, SPRITE_DATA) + DATA_SHOW);

        *flags = row < rows ? *flags | SPRITE_SHOWN : *flags & ~SPRITE_SHOWN;
        mark_redraw(group_of(group), sprite);
        if (++in_row == per_row) {
            in_row = 0;
            row++;
        }
    }
}

/* The ref of the small list's line `row` (5 to 9: ui020's, after the game's fifth) */
static void line_ref(int row, u32 *ref)
{
    u32 next[2];

    ref[0] = word_at(start_list_ui, UI_LAST_LINE);
    ref[1] = word_at(start_list_ui, UI_LAST_LINE + 4);
    while (row-- > SUBLIST_ROWS - 1 && ref[1] != 0) {
        gui_ref_next(next, ref);
        ref[0] = next[0];
        ref[1] = next[1];
    }
}

/* A line's colour, as FUN_005e84f0 colours the game's five */
static void line_colour(int row, u32 colour)
{
    u32 ref[2];
    char *holder;

    line_ref(row, ref);
    if (ref[1] == 0)
        return;
    *(u32 *)(pointer_at((char *)ref[1], SPRITE_DATA) + LINE_COLOUR) = colour;
    holder = pointer_at((char *)ref[1], TEXT_HOLDER);
    *(u32 *)(pointer_at(holder, SPRITE_DATA) + HOLDER_COLOUR) = colour;
    mark_redraw((void *)ref[0], holder);
}

static void line_text(int row, int message)
{
    u32 ref[2];

    line_ref(row, ref);
    if (ref[1] != 0)
        text_common(ref, mod_settings_data.file, message);
}

static void line_blank(int row)
{
    u32 ref[2];

    line_ref(row, ref);
    if (ref[1] == 0)
        return;
    text_set((void *)ref[1], (void *)ref[0], 0, 0, 0);
    mark_redraw((void *)ref[0], pointer_at((char *)ref[1], TEXT_HOLDER));
}

static void raise_group(int group, float by)
{
    if (group_of(group) != 0)
        *(float *)(group_of(group) + GROUP_Y) += by;
}

/* A page of `rows` rows, a size the game has no frame for (1, or 6 to 10), after FUN_005e87b4 set the list up for one
 * row or five: our frame of `rows` rows and our strips of its rows in place of the game's 4- and 5-row frames (which
 * FUN_005e87b4 sets again for its own lists) and strips. For one row FUN_005e87b4 leaves the frames' group hidden: it
 * goes up where it puts the group for four or five rows, the cursor's base */
static void small_ours_up(int rows)
{
    if (rows == 1 && group_of(GROUP_SMALL_FRAME) != 0) {
        start_list_group(start_list_ui, GROUP_SMALL_FRAME, 1);
        *(float *)(group_of(GROUP_SMALL_FRAME) + GROUP_Y) = *(const float *)(start_menu + M_SUB_BASE);
    }
    show_null(GROUP_SMALL_FRAME, SMALL_FRAME_4, 0);
    show_null(GROUP_SMALL_FRAME, SMALL_FRAME_5, 0);
    show_null(GROUP_SMALL_FRAME, SMALL_STRIPS, 0);
    show_hashed(GROUP_SMALL_FRAME, mod_settings_data.small_frames[rows - 1], 1);
    show_rows(GROUP_SMALL_FRAME, SMALL_STRIPS_OURS, rows, STRIP_SPRITES);
    mod_settings_state.ten |= TEN_SMALL;
}

/* Every way out of a page in a frame of ours: our panes hidden, the game's strips back and our lines blank, before a
 * game's list can use the groups (its frames and the groups' places are FUN_005e87b4's to set again) */
static void small_ours_down(void)
{
    int row;

    if (!(mod_settings_state.ten & TEN_SMALL))
        return;
    for (row = 0; row < PAGE_LIST_ROWS; row++)
        show_hashed(GROUP_SMALL_FRAME, mod_settings_data.small_frames[row], 0);
    show_rows(GROUP_SMALL_FRAME, SMALL_STRIPS_OURS, 0, STRIP_SPRITES);
    show_null(GROUP_SMALL_FRAME, SMALL_STRIPS, 1);
    for (row = SUBLIST_ROWS; row < PAGE_LIST_ROWS; row++)
        line_blank(row);
    mod_settings_state.ten &= ~TEN_SMALL;
}

static void close_small(void)
{
    small_ours_down();
    start_sublist_close();
}

/* FUN_005e8050 on the third page, each frame: the rows, the line table, and what can take A */
void mod_menu_page(char *menu)
{
    *(s16 *)(menu + M_ROWS) = PAGE_ROWS;
    *(const void **)(menu + M_LINES) = mod_settings_data.lines;
    *(u32 *)(menu + M_LINE_MARKS) = 0;
    menu[M_PAGE_ENABLED] = 1;
    menu[M_ROW_ENABLED] = 1;
}

/* FUN_00600658, a line its tables do not hold */
int mod_line_action(int page, int row)
{
    return page == PAGE && row == 0 ? ACTION : NO_ACTION;
}

/* FUN_0060fc2c, an action past the game's table */
void mod_menu_description(void)
{
    facility_help(KIND_TEXT, mod_settings_data.file, mod_settings_data.line_help);
}

static const struct mod_list *current_list(void)
{
    return &mod_settings_data.lists[mod_settings_state.list];
}

static const struct mod_entry *current_entry(void)
{
    return &mod_settings_data.entries[current_list()->first + mod_settings_state.cursor];
}

static void show_entry_help(void)
{
    facility_help(KIND_TEXT, mod_settings_data.file, current_entry()->help);
}

static int list_pages(void)
{
    return (current_list()->count + PAGE_LIST_ROWS - 1) / PAGE_LIST_ROWS;
}

static int list_page(void)
{
    return mod_settings_state.cursor / PAGE_LIST_ROWS;
}

/* The list's rows on its page `page` */
static int rows_on(int page)
{
    int rows = current_list()->count - page * PAGE_LIST_ROWS;

    return rows > PAGE_LIST_ROWS ? PAGE_LIST_ROWS : rows;
}

static void pager_release(void)
{
    if (mod_settings_state.pager) {
        start_pager_release();
        mod_settings_state.pager = 0;
    }
}

/* The page numbers in the menu's title bar ("3/3"), which the game writes from the menu's page count and page
 * (FUN_00608028): while a list of two pages is open they say its page ("1/2"), and they go back to the menu's own when
 * the list goes, a screen opens or the menu closes */
static void page_numbers(int page, int pages)
{
    start_menu[M_PAGE_COUNT] = (u8)pages;
    start_menu[M_PAGE] = (u8)page;
    start_page_numbers();
}

static void menu_page_numbers(void)
{
    if (mod_settings_state.list_numbers) {
        page_numbers(PAGE, MENU_PAGES);
        mod_settings_state.list_numbers = 0;
    }
}

static void list_page_numbers(void)
{
    if (list_pages() < 2) {
        menu_page_numbers();
        return;
    }
    page_numbers(list_page(), list_pages());
    mod_settings_state.list_numbers = 1;
}

/* The cursor on its row of the page: the game's function places it (at any row: its base minus 18 a row) and colours
 * the game's five lines; this code colours ui020's lines past them that the page has */
static void small_cursor(void)
{
    int page = list_page(), row = mod_settings_state.cursor - page * PAGE_LIST_ROWS, rows = rows_on(page), line;

    start_sublist_cursor(row);
    for (line = SUBLIST_ROWS; line < rows; line++)
        line_colour(line, line == row ? COLOUR_SELECTED : COLOUR_ROW);
}

/* Single-screen mode: the list goes up as far as its first page needs to stay clear of the description's place
 * (curated, by that page's rows), its frames' group, lines and cursor and the cursor's base together. Every page of a
 * list goes as far, so turning a page does not move it */
static void small_raise(int rows)
{
    int tallest = current_list()->count < PAGE_LIST_ROWS ? current_list()->count : PAGE_LIST_ROWS;
    float by = (float)mod_settings_data.raise[tallest - 1];

    if (by == 0.0f)
        return;
    raise_group(rows == 2 ? GROUP_SMALL_FRAME_2 : rows == 3 ? GROUP_SMALL_FRAME_3 : GROUP_SMALL_FRAME, by);
    raise_group(GROUP_SMALL_LINES, by);
    raise_group(GROUP_SMALL_CURSOR, by);
    *(float *)(start_menu + M_SUB_BASE) += by;
}

/* The small list of the current list, on the page of its cursor. Both this and FUN_005e86b0 set the whole widget, so a list
 * or a page can follow another in the same frame. A page of n rows shows its n rows and nothing more, in a frame of n:
 * the game's list of n for 2 to 5 rows, FUN_005e87b4's of one row or five and our frame for the rest (ui020's lines past
 * the fifth written here) */
static void open_list(void)
{
    const struct mod_settings_data *data = &mod_settings_data;
    const struct mod_list *list = current_list();
    int first = list_page() * PAGE_LIST_ROWS;
    int rows = rows_on(list_page());
    int row;

    start_sublist_open(0, rows > SUBLIST_ROWS ? SUBLIST_ROWS : rows);
    if (data->small_frames[rows - 1] != 0)
        small_ours_up(rows);
    small_raise(rows);
    for (row = 0; row < rows; row++) {
        int message = data->entries[list->first + first + row].name;

        if (row < SUBLIST_ROWS)
            start_sublist_text(row, KIND_TEXT, data->file, message);
        else
            line_text(row, message);
    }
    small_cursor();
    list_page_numbers();
    start_help_show(HELP_ON, HELP_PRIORITY);
    show_entry_help();
}

/* A on the page's row, in the list's frame (FUN_005f6c8c): its sound comes after this, in the game's code */
void mod_menu_pick(char *menu)
{
    mod_settings_state.open = 1;
    menu[M_STATE] = 1;
    menu[M_SUBSTATE] = 0;
    menu[M_KIND] = KIND;
    mod_settings_state.level = LEVEL_LIST;
    mod_settings_state.list = 0;
    mod_settings_state.cursor = 0;
    start_sublist_begin();
    start_top_cursor(0);
    open_list();
}

static void big_ours_down(void);
static void big_blank_more(void);

/* FUN_0060d058, on every close of the menu: the pager's bind ends here when the player left without going back, and
 * ui020's panes of ours go (FUN_005e86b0 closes the small list right after) */
void mod_menu_closed(void)
{
    small_ours_down();
    big_ours_down();
    mod_settings_state.open = 0;
    if (mod_settings_state.list_numbers) {      /* the menu reopens on its own page, with its own count */
        start_menu[M_PAGE_COUNT] = MENU_PAGES;
        start_menu[M_PAGE] = PAGE;
        mod_settings_state.list_numbers = 0;
    }
    pager_release();
}

/* ---- the big list, for the screen an entry opens */

static void show_screen_groups(char *ui, int shown)
{
    start_list_group(ui, GROUP_FRAME, shown);
    start_list_group(ui, GROUP_ICON_BACK, shown);
    start_list_group(ui, GROUP_ROWS, shown);
    start_list_group(ui, GROUP_CURSOR, shown);
}

/* The big list's frame for a page of `rows` rows (1 to 10), each time a screen draws one (aspect_list.c,
 * option_list.c): the game's frame, strips and backings for its eight; for another size our frame of `rows` rows and
 * our strips and backings of its rows in their place */
void mod_list_rows(int rows)
{
    int game = rows == BIG_GAME_ROWS, size;

    show_null(GROUP_FRAME, BIG_FRAME, game);
    show_null(GROUP_FRAME, BIG_STRIPS, game);
    show_null(GROUP_ICON_BACK, BIG_BACKS, game);
    for (size = 1; size <= BIG_ROWS; size++)
        show_hashed(GROUP_FRAME, mod_settings_data.big_frames[size - 1], !game && size == rows);
    show_rows(GROUP_FRAME, BIG_STRIPS_OURS, game ? 0 : rows, STRIP_SPRITES);
    show_rows(GROUP_ICON_BACK, BIG_BACKS_OURS, game ? 0 : rows, 1);
}

/* Every way out of a screen: the game's frame, strips and backings back for its own big lists, ours hidden and the
 * rows past the eighth blank */
static void big_ours_down(void)
{
    if (!(mod_settings_state.ten & TEN_BIG))
        return;
    big_blank_more();
    mod_list_rows(BIG_GAME_ROWS);
    mod_settings_state.ten &= ~TEN_BIG;
}

/* The widget's groups on, its cursor bound and the pager bound, hidden until its first frame; its frame comes with the
 * screen's first page (mod_list_rows) */
void mod_list_open(void)
{
    char *ui = start_list_ui;
    char *owner = pointer_at(gui_control, GUI_ANIM_OWNER);

    close_small();
    menu_page_numbers();        /* the title bar is the menu's again: the screen binds its pager there */
    show_screen_groups(ui, 1);
    mod_settings_state.ten |= TEN_BIG;
    if (owner != 0)
        gui_anim_bind(ui + UI_CURSOR_PANE, pointer_at(ui, UI_CURSOR_ANIM), owner, 0);
    start_pager_bind(mod_settings_data.pager_x, mod_settings_data.pager_y);
    start_pager_hide();
    mod_settings_state.pager = 1;
    start_help_show(HELP_ON, HELP_PRIORITY);
}

void mod_list_close(void)
{
    big_ours_down();
    show_screen_groups(start_list_ui, 0);
    start_pager_hide();
    pager_release();
}

void mod_list_title(int message)
{
    text_common(start_list_ui + UI_TITLE, mod_settings_data.file, message);
}

void mod_list_help(int message)
{
    facility_help(KIND_TEXT, mod_settings_data.file, message);
}

/* The next message's number node shows this message of a common file: its first text, which is all a name has */
static void fill_slot(int file, int message)
{
    void *table = common_files[file];
    const u32 *string = table != 0 ? message_string(table, message) : 0;

    if (string != 0)
        text_slot(TEXT_SLOT, (const void *)string[0], string[2]);
    else
        text_slot(TEXT_SLOT, 0, 0);
}

static void row_ref(int row, u32 *ref)
{
    u32 next[2];

    ref[0] = word_at(start_list_ui, UI_ROWS);
    ref[1] = word_at(start_list_ui, UI_ROWS + 4);
    while (row-- > 0) {
        gui_ref_next(next, ref);
        ref[0] = next[0];
        ref[1] = next[1];
    }
}

/* The sprite of a row's picture, 0 past the null's sprites */
static char *row_sprite(int row)
{
    char *sprite = pointer_at(pointer_at(start_list_ui, UI_ICONS + 4), PANE_FIRST_CHILD);

    while (sprite != 0 && row-- > 0)
        sprite = pointer_at(sprite, PANE_NEXT);
    return sprite != 0 && (word_at(sprite, PANE_KIND) & 0xFF) == 0 ? sprite : 0;
}

static void hide_icon(int row)
{
    char *sprite = row_sprite(row);

    if (sprite != 0) {
        *(u32 *)(pointer_at(sprite, SPRITE_DATA) + DATA_SHOW) &= ~SPRITE_SHOWN;
        mark_redraw(pointer_at(start_list_ui, UI_ICONS), sprite);
    }
}

/* A row with a message holding another message of the menu's file, and no picture */
void mod_list_slot_text(int row, int message, int text)
{
    u32 ref[2];

    row_ref(row, ref);
    fill_slot(mod_settings_data.file, text);
    text_common(ref, mod_settings_data.file, message);
    hide_icon(row);
}

/* A row with nothing, as FUN_0061ae20 leaves the rows past its table */
void mod_list_blank(int row)
{
    u32 ref[2];

    row_ref(row, ref);
    if (ref[1] == 0)
        return;
    text_set((void *)ref[1], (void *)ref[0], 0, 0, 0);
    mark_redraw((void *)ref[0], pointer_at((char *)ref[1], TEXT_HOLDER));
    hide_icon(row);
}

/* ui020's rows past the game's eight blank, before the game's own big lists use the group: they never write them */
static void big_blank_more(void)
{
    int row;

    for (row = BIG_GAME_ROWS; row < BIG_ROWS; row++)
        mod_list_blank(row);
}

/* What the widget needs each frame: the cursor on its row, its animation, the pager */
void mod_list_frame(int row_on_page, int page, int pages)
{
    char *ui = start_list_ui;

    *(float *)(pointer_at(ui, UI_BIG_CURSOR) + 0x2C) = (float)(row_on_page * ROW_HEIGHT);
    gui_anim_step(pointer_at(ui, UI_CURSOR_ANIM), *(const float *)(game_main + MAIN_DELTA));
    start_pager_show(page, pages, 0, 0, 1);
}

/* ---- the frames */

static int screen_frame(char *menu, u32 pressed)
{
    u32 keys = pressed | (word_at(menu, M_REPEAT) & KEYS_REPEAT);
    int back = mod_settings_state.screen == SCREEN_OPTION ? option_screen_frame(pressed, keys)
                                                          : aspect_screen_frame(pressed, keys);

    if (back) {
        mod_list_close();
        play(SOUND_CANCEL);
        mod_settings_state.level = LEVEL_LIST;
        open_list();
    }
    return 0;
}

/* The small list again, on another list and row */
static void go_to_list(int list, int row)
{
    close_small();
    mod_settings_state.list = list;
    mod_settings_state.cursor = row;
    open_list();
}

static int list_frame(char *menu, u32 pressed)
{
    u32 keys = pressed | (word_at(menu, M_REPEAT) & KEYS_REPEAT);
    int page = list_page(), row = mod_settings_state.cursor - page * PAGE_LIST_ROWS;

    if (pressed & KEY_B) {
        play(SOUND_CANCEL);
        if (current_list()->parent != NO_LIST) {
            go_to_list(current_list()->parent, current_list()->parent_row);
            return 0;
        }
        mod_settings_state.open = 0;
        menu_page_numbers();
        close_small();
        start_top_cursor(1);
        start_sublist_end();
        return 2;
    }
    if (pressed & KEY_A) {
        const struct mod_entry *entry = current_entry();

        if (entry->list != NO_LIST) {
            play(SOUND_DECIDE);
            go_to_list(entry->list, 0);
            return 0;
        }
        int opened = 0;

        if (entry->screen == SCREEN_ASPECT)
            opened = aspect_screen_open(entry->title);
        else if (entry->screen == SCREEN_OPTION)
            opened = option_screen_open(entry->arg, entry->title);

        if (opened) {
            play(SOUND_DECIDE);
            mod_settings_state.screen = entry->screen;
            mod_settings_state.level = LEVEL_SCREEN;
            return 0;
        }
        play(SOUND_ERROR);
    }
    if (keys & (KEY_UP | KEY_DOWN)) {               /* round the page's rows */
        row = start_step(row, rows_on(page), keys, KEY_UP, KEY_DOWN);
    } else if ((keys & (KEY_LEFT | KEY_RIGHT)) && list_pages() > 1) {   /* the other page, on the same row or its last */
        page = start_step(page, list_pages(), keys, KEY_LEFT, KEY_RIGHT);
        if (row >= rows_on(page))
            row = rows_on(page) - 1;
        mod_settings_state.cursor = page * PAGE_LIST_ROWS + row;
        close_small();
        open_list();
        return 0;
    }
    if (page * PAGE_LIST_ROWS + row != mod_settings_state.cursor) {
        mod_settings_state.cursor = page * PAGE_LIST_ROWS + row;
        show_entry_help();
    }
    small_cursor();
    return 0;
}

/* FUN_005f6ae4's call for our kind: 0 stays in the sub-screen, 2 goes back to the page */
int mod_menu_frame(char *menu)
{
    u32 pressed = word_at(menu, M_PRESSED);

    if (mod_settings_state.level == LEVEL_SCREEN)
        return screen_frame(menu, pressed);
    return list_frame(menu, pressed);
}
