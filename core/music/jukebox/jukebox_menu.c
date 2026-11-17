/* The jukebox's menu in the house Felyne's menu, a
 * unit of the block jukebox (jukebox.h). The facility's function FUN_00aa8298 keeps its state at obj + 0x1287C (states
 * 0-9 are the game's); its menu is the layout ui414, which has an eighth line the game never shows. The hooks
 * (music/jukebox/menu_patch.py, jukebox_menu_stub.s):
 *
 *   jukebox_lines           FUN_00aa8074 (the facility's entry): after the game's lines, ours (action 7) is the last
 *   jukebox_menu_line       FUN_009db3ac (the menu drawn): our line's frame (group line - 1) and its text
 *   jukebox_help_message    FUN_009db608 (the cursor line's help): ours on our line
 *   jukebox_menu_pick       FUN_00aa8298, A on a line (the menu closed): ours enters state 10
 *   jukebox_facility_state  FUN_00aa8298's state switch: state 10 runs jukebox_menu_frame
 *
 * State 10 drives the game's list ui443 (its panes bound by FUN_0059e3ac at obj + 0x12C8C) as the Gallery and the
 * Song Select do from their own states: ten rows a page in two columns, the ribbon as the title, each row's number pane
 * and mark, the page counter, the help line. The screens:
 *
 *   main        the playlists (name, songs, the mark on the one playing) and Options
 *   playlist    Play / Stop, Add songs, Edit songs, Rename (the name keyboard), Order, Clear (a yes / no window)
 *   categories  the categories that hold a track of the build, then a category's tracks: A adds or removes the track,
 *               Y listens to it; the number is its place in the playlist, the mark says it is there
 *   edit        the playlist's tracks the build has, in order: A carries the track along with the cursor (A or B puts
 *               it down), X removes it, Y listens to it; the mark is on the track carried, or else on the one playing
 *   options     Hall music too, Keep, Loops, Fade-out in the left column: left and right (or A) change the value
 *
 * B goes back one screen; from the first, to the menu on our line. The menu's exit event closes the list, the keyboard
 * and the window and leaves as the menu does. Listening stops when its screen is left.
 */
#include "jukebox.h"

/* the game's functions and variables (blocks.py GAME_SYMBOLS) */
extern u32 sound_control;                               /* the variable holding the sound control */
extern u32 game_control;                                /* the variable holding the game control (the keyboard's) */
void housekeeper_lines(u8 *obj);                        /* FUN_00aa771c */
void sound_play(u32 control, u32 sound);                /* FUN_0031294c */
void gui_group_show(u32 group, u32 shown);              /* FUN_00ae53e0 */
void gui_group_order(u32 group, u32 layer, u32 priority);       /* FUN_00ae63c8 */
void pane_redraw(u32 group, u8 *node);                  /* FUN_00ae6bcc */
void text_lobby(void *ref, u32 file, u32 message);      /* FUN_005a882c */
void text_slot(u32 slot, const u16 *text, u32 length);  /* FUN_005a99a8: what a message's number node shows */
void text_show(u32 pane, u32 visible);                  /* FUN_00ae7618 */
void facility_help(u32 kind, u32 file, u32 message);    /* FUN_00298560 */
u32 facility_pressed(u8 *obj, u32 bits);                /* FUN_009ac3a4 */
u32 facility_dirs(u8 *obj);                             /* FUN_009b3830: every bit pressed or repeating */
void list_bind(u8 *list);                               /* FUN_0059e3ac */
void list_unbind(u8 *list);                             /* FUN_0059e44c */
void ribbon_title(u8 *obj, u32 group, u32 pane, u32 file, u32 message);   /* FUN_00a5985c */
void page_counter(int x, int y, int page, int pages, int zero, int none); /* FUN_00288fac */
void page_arrow_idle(u8 *sprite);                       /* FUN_0029f084 */
void page_arrow_flash(u8 *sprite);                      /* FUN_0029ebac */
void page_turn_next(void);                              /* FUN_0028bae0 */
void page_turn_back(void);                              /* FUN_0028babc */
void touch_owner(void);                                 /* FUN_00289708 */
void touch_owner_close(void);                           /* FUN_00289544 */
void touch_panels(u32 zero);                            /* FUN_0028bfa0 */
void gui_layer_set(u32 layer);                          /* FUN_0029df10 */
void start_help_show(u32 kind, u32 layer);              /* FUN_002a4260 */
void menu_close_frames(void);                           /* FUN_002a0778 */
void window_open(u32 kind, u32 slot, u32 type, u32 first);      /* FUN_002921cc */
void window_update(void);                               /* FUN_002a2414 */
void window_close(u32 kind, u32 slot);                  /* FUN_0029e5bc */
u32 window_input(u8 *obj);                              /* FUN_00aa6480 */
u32 window_answer(u8 *obj, u32 *answer, u32 input, u32 mask);   /* FUN_00a66e60: 1 yes, 2 no */
u32 gui_event(u32 kind);                                /* FUN_00288f4c */
void house_farewell(u8 *obj, u32 line, u32 zero);       /* FUN_009bcb90 */
u32 keyboard_open(u32 manager, u32 type, u32 characters, u32 flag);       /* FUN_002b5788 */
u32 keyboard_start(u32 manager, u32 zero, const u16 *text);             /* FUN_002b59dc */
int keyboard_poll(u32 manager);                         /* FUN_002b58e8: 0 open, 1 accepted, -1 cancelled */
const u16 *keyboard_text(u32 manager);                  /* FUN_002afc2c */
void keyboard_copy(u32 manager, u16 *out, const u16 *text, int width, int limit);      /* FUN_002b5f48 */
void keyboard_close(u32 manager);                       /* FUN_002b5df8 */

/* the house Felyne's facility */
#define FACILITY 0x1287C                /* the lobby object: the facility's state */
#define LIST 0x12C8C                    /* the lobby object: ui443's refs */
#define F_STATE 0
#define F_SUB 1
#define F_SUB2 2
#define F_COUNT 0xC                     /* s32: the menu's lines */
#define F_CURSOR 0x4C                   /* s16: the menu cursor's line */
#define F_ACTIONS 0x228                 /* u8 per line: its action */
#define F_MENU 0x230                    /* ui414's refs */
#define MENU_LINES 8                    /* ui414's lines */
#define M_GROUPS 8                      /* + 4 g: group g (0 frames lines 0 and 1, g >= 1 line g + 1) */
#define M_TEXTS 0x40                    /* + 8 t: line t's text */
#define JUKEBOX_ACTION 7                /* our line's action (the game's are 0-6) */
#define STATE_MENU 1
#define STATE_LEAVING 9
#define STATE_JUKEBOX 10
#define ROOM_FILE 0x13                  /* Room_s among the lobby's message files */
#define HELP_KIND 1
#define GUI_LAYER 0xB
#define EXIT_EVENT 8                    /* the event the menu's own exit check reads */
#define FAREWELL 1

/* ui443's refs, 8 bytes each ({group, node}) */
#define L_GROUPS 0                      /* + 4 g: background, list, ribbon, cursor */
#define L_TEXTS 0x10                    /* text 2 r: row r's number, 2 r + 1: its title */
#define L_NULLS 0xB0                    /* null 2 r: row r */
#define L_SPRITES 0x170                 /* sprite r: row r's mark */
#define NULL_ARROWS 20
#define NULL_CURSOR 21
#define NULL_RIBBON 22                  /* shows the ribbon's ui443_m_arena */
#define NULL_PAGE 23
#define SPRITE_NEXT 10
#define SPRITE_BACK 11
#define GROUP_BACKGROUND 0
#define GROUP_LIST 1
#define GROUP_RIBBON 2
#define GROUP_CURSOR 3
#define LIST_PRIORITY 10
#define RIBBON_GROUP 0x322522A7         /* ui443_midasi */
#define RIBBON_TEXT 0x7DB09813          /* ui443_m_arena */
#define NODE_DATA 8
#define NODE_DIRTY 0xC
#define DIRTY_MARK 0x12
#define NODE_NEXT 0x14                  /* a text's holder */
#define NULL_FLAGS (0x24 / 4)
#define NULL_SHOWN 1
#define SPRITE_FLAGS (0x58 / 4)
#define SPRITE_SHOWN 0x80
#define CURSOR_X 138.0f                 /* the cursor null: x 138 - 138 (row & 1), y 84 - 26 (row >> 1) */
#define CURSOR_Y 84.0f
#define CURSOR_STEP 26.0f

/* the facility's keys (FUN_009ac3a4, FUN_009b3830) and sounds (FUN_00aa6b3c's numbers) */
#define DIR_UP 1
#define DIR_DOWN 2
#define DIR_LEFT 4
#define DIR_RIGHT 8
#define BUTTON_A 0x10
#define BUTTON_B 0x20
#define BUTTON_Y 0x80
#define BUTTON_X 0x4000
#define SOUND_DECIDE 1
#define SOUND_CANCEL 2
#define SOUND_ERROR 3
#define SOUND_CURSOR 4
#define SOUND_KEYBOARD 6
#define SOUND_PAGE 7

/* the windows: the yes / no of the Wyporium's trades, and the two the list's screens close */
#define YES_NO 3
#define YES_NO_BUTTONS 6
#define WINDOW_YES_NO 4
#define ANSWER_ANY 0xFFFF
#define ANSWER_YES 1
#define ANSWER_NO 2
#define FRAME_ONE 1
#define FRAME_FOUR 4

#define KEYBOARD_NAME 1                 /* FUN_002b5788's type and flag as the equipment sets open it */
#define KEYBOARD_FLAG 1

/* the playlist screen's rows */
enum { ROW_PLAY, ROW_ADD, ROW_EDIT, ROW_RENAME, ROW_ORDER, ROW_CLEAR, PLAYLIST_ROWS };
#define OPTIONS 4                       /* JUKEBOX_OPTION_*, one each at rows 0, 2, 4, 6 */
#define OPTION_ROWS (2 * OPTIONS - 1)

#define U (&jukebox_menu)
#define D (&jukebox_data)
#define PAGE JUKEBOX_PAGE_ROWS

struct row {
    u32 message;                        /* the title's message */
    const u16 *text;                    /* what its number node shows, or 0 */
    int number;                         /* the number pane's, -1: hidden */
    int mark;
};

static void sound(u32 id)
{
    sound_play(sound_control, id);
}

/* ----- the menu's line ------------------------------------------------------------------------------------------ */

/* our line in the menu (the last), or -1 */
static int our_line(const u8 *f)
{
    int count = *(const s32 *)(f + F_COUNT);
    if (count < 1 || count > MENU_LINES)
        return -1;
    return f[F_ACTIONS + count - 1] == JUKEBOX_ACTION ? count - 1 : -1;
}

void jukebox_lines(u8 *obj)
{
    housekeeper_lines(obj);
    u8 *f = obj + FACILITY;
    s32 count = *(s32 *)(f + F_COUNT);
    if (count < 0 || count >= MENU_LINES)
        return;
    f[F_ACTIONS + count] = JUKEBOX_ACTION;
    *(s32 *)(f + F_COUNT) = count + 1;
}

void jukebox_menu_line(u8 *obj)
{
    u8 *f = obj + FACILITY, *menu = f + F_MENU;
    int line = our_line(f);
    if (line < 2)                       /* lines 0 and 1 share group 0: ours is never one of them */
        return;
    gui_group_show(*(u32 *)(menu + M_GROUPS + 4 * (line - 1)), 1);
    text_lobby(menu + M_TEXTS + 8 * line, ROOM_FILE, D->messages[JM_LINE]);
}

u32 jukebox_help_message(const u8 *f)
{
    int line = *(const s16 *)(f + F_CURSOR);
    if (line < 0 || line >= MENU_LINES || f[F_ACTIONS + line] != JUKEBOX_ACTION)
        return 0;
    return D->messages[JM_LINE_HELP];
}

int jukebox_menu_pick(int action, u8 *obj)
{
    if (action == JUKEBOX_ACTION) {
        u8 *f = obj + FACILITY;
        sound(SOUND_DECIDE);
        f[F_STATE] = STATE_JUKEBOX;
        f[F_SUB] = 0;
        f[F_SUB2] = 0;
        U->open = 0;
    }
    return action;
}

int jukebox_facility_state(int state, u8 *obj)
{
    if (state == STATE_JUKEBOX)
        jukebox_menu_frame(obj);
    return state;
}

/* ----- the data -------------------------------------------------------------------------------------------------- */

static int playlists(void)
{
    return D->limits.playlists < JUKEBOX_PLAYLISTS ? D->limits.playlists : JUKEBOX_PLAYLISTS;
}

static int categories(void)
{
    return D->categories < JUKEBOX_CATEGORIES ? D->categories : JUKEBOX_CATEGORIES;
}

static int name_chars(void)
{
    return D->limits.name_chars < JUKEBOX_NAME_CHARS ? D->limits.name_chars : JUKEBOX_NAME_CHARS;
}

/* the name message of a track the menu lists; 0: the build lacks it */
static u32 track_name(int track)
{
    for (int i = 0; i < JUKEBOX_MENU_TRACKS && D->menu_tracks[i] != JUKEBOX_NO_SONG; i++)
        if (D->menu_tracks[i] == track)
            return D->track_names + i;
    return 0;
}

static const struct jukebox_playlist *open_list(void)
{
    return jukebox_playlist(U->list);
}

static int songs_of(const struct jukebox_playlist *p)
{
    return p->count < JUKEBOX_SONGS ? p->count : JUKEBOX_SONGS;
}

/* the playlist's index of the edit screen's row `nth` (its tracks the build has, in order), or -1 */
static int song_at(const struct jukebox_playlist *p, int nth)
{
    for (int i = 0; p && i < songs_of(p); i++)
        if (track_name(p->songs[i]) && nth-- == 0)
            return i;
    return -1;
}

static int known_songs(const struct jukebox_playlist *p)
{
    int n = 0;
    for (int i = 0; p && i < songs_of(p); i++)
        n += track_name(p->songs[i]) != 0;
    return n;
}

/* the track of a row of the songs or the edit screen */
static int row_track(int index)
{
    if (U->screen == JUKEBOX_SCREEN_SONGS)
        return D->menu_tracks[D->category[U->category].first + index];
    const struct jukebox_playlist *p = open_list();
    int at = song_at(p, index);
    return at < 0 ? JUKEBOX_NO_SONG : p->songs[at];
}

static int rows_of(int screen)
{
    if (screen == JUKEBOX_SCREEN_MAIN)
        return playlists() + 1;
    if (screen == JUKEBOX_SCREEN_PLAYLIST)
        return PLAYLIST_ROWS;
    if (screen == JUKEBOX_SCREEN_CATEGORIES)
        return categories();
    if (screen == JUKEBOX_SCREEN_SONGS)
        return D->category[U->category].count;
    if (screen == JUKEBOX_SCREEN_EDIT)
        return known_songs(open_list());
    return OPTION_ROWS;
}

static void option_range(int option, int *low, int *high)
{
    *low = 0;
    *high = 1;
    if (option == JUKEBOX_OPTION_LOOPS) {
        *low = D->limits.loops_min;
        *high = D->limits.loops_max;
    } else if (option == JUKEBOX_OPTION_FADE) {
        *low = D->limits.fade_min;
        *high = D->limits.fade_max;
    }
}

/* ----- strings --------------------------------------------------------------------------------------------------- */

/* `value` (0-999) in decimal into `out`, 0 ended; its length */
static u32 decimal(u16 *out, int value)
{
    static const short tens[] = {100, 10, 1};
    u32 length = 0;
    if (value < 0)
        value = 0;
    for (int i = 0; i < 3; i++) {
        int digit = 0;
        while (value >= tens[i]) {
            value -= tens[i];
            digit++;
        }
        if (digit > 9)
            digit = 9;
        if (digit || length || tens[i] == 1)
            out[length++] = (u16)('0' + digit);
    }
    out[length] = 0;
    return length;
}

static u32 text_length(const u16 *text)
{
    u32 n = 0;
    while (n + 1 < JUKEBOX_TEXT_ROOM && text[n])
        n++;
    return n;
}

/* a playlist's name for a row or the title: the typed name through the slot message, or "Playlist N" */
static void playlist_name(int list, u16 *buffer, struct row *row)
{
    const struct jukebox_playlist *p = jukebox_playlist(list);
    int length = 0;
    while (p && length < JUKEBOX_NAME_CHARS && p->name[length]) {
        buffer[length] = p->name[length];
        length++;
    }
    buffer[length] = 0;
    row->message = D->messages[JM_SLOT];
    if (!length) {
        decimal(buffer, list + 1);
        row->message = D->messages[JM_PLAYLIST];
    }
    row->text = buffer;
}

/* ----- the panes ------------------------------------------------------------------------------------------------- */

static u8 *ref_at(u8 *obj, u32 offset)
{
    return obj + LIST + offset;
}

static u8 *node_of(const u8 *ref)
{
    return *(u8 **)(ref + 4);
}

static u32 *data_of(const u8 *ref)
{
    return *(u32 **)(node_of(ref) + NODE_DATA);
}

static void node_changed(const u8 *ref, u8 *node)
{
    u8 *dirty = *(u8 **)(node + NODE_DIRTY);
    if (dirty)
        dirty[DIRTY_MARK] = 3;
    else
        pane_redraw(*(const u32 *)ref, node);
}

static void flag_pane(u8 *ref, int word, u32 bit, int on)
{
    u32 *data = data_of(ref);
    data[word] = on ? data[word] | bit : data[word] & ~bit;
    node_changed(ref, node_of(ref));
}

static void null_show(u8 *obj, int n, int shown)
{
    flag_pane(ref_at(obj, L_NULLS + 8 * n), NULL_FLAGS, NULL_SHOWN, shown);
}

/* a Room_s message into a text pane of the list, shown, in FUN_00a5985c's order (shown, written, its holder marked);
   `slot` is what its number node shows */
static void write_text(u8 *ref, u32 message, const u16 *slot)
{
    text_show((u32)data_of(ref), 1);
    if (slot)
        text_slot(0, slot, text_length(slot));
    text_lobby(ref, ROOM_FILE, message);
    node_changed(ref, *(u8 **)(node_of(ref) + NODE_NEXT));
}

static void hide_text(u8 *ref)
{
    text_show((u32)data_of(ref), 0);
    node_changed(ref, *(u8 **)(node_of(ref) + NODE_NEXT));
}

static void show_group(u8 *obj, int group, u32 priority)
{
    u32 g = *(u32 *)ref_at(obj, L_GROUPS + 4 * group);
    gui_group_show(g, 1);
    gui_group_order(g, 1, priority);
}

/* ----- drawing --------------------------------------------------------------------------------------------------- */

static void option_row(int option, u16 *buffer, struct row *row)
{
    int value = jukebox_option(option);
    if (option == JUKEBOX_OPTION_HALLS) {
        row->message = D->messages[value ? JM_HALLS_ON : JM_HALLS_OFF];
    } else if (option == JUKEBOX_OPTION_KEEP) {
        row->message = D->messages[value == JUKEBOX_ALWAYS ? JM_KEEP_ALWAYS : JM_KEEP_SESSION];
    } else {
        decimal(buffer, value);
        row->text = buffer;
        row->message = D->messages[option == JUKEBOX_OPTION_LOOPS ? JM_LOOPS : JM_FADE];
    }
}

/* what row `r` (the screen's row `index`) shows; 0: nothing */
static int row_content(int index, int r, struct row *row)
{
    static const u8 playlist_rows[PLAYLIST_ROWS] = {JM_PLAY, JM_ADD, JM_EDIT, JM_RENAME, JM_IN_ORDER, JM_CLEAR};
    u16 *buffer = U->texts[r];
    row->text = 0;
    row->number = -1;
    row->mark = 0;
    if (index >= U->count)
        return 0;
    if (U->screen == JUKEBOX_SCREEN_MAIN) {
        if (index == playlists()) {
            row->message = D->messages[JM_OPTIONS];
            return 1;
        }
        playlist_name(index, buffer, row);
        row->number = songs_of(jukebox_playlist(index));
        row->mark = jukebox_playing() == index;
    } else if (U->screen == JUKEBOX_SCREEN_PLAYLIST) {
        int message = playlist_rows[index];
        if (index == ROW_PLAY && jukebox_playing() == U->list)
            message = JM_STOP;
        if (index == ROW_ORDER && open_list()->order == JUKEBOX_SHUFFLE)
            message = JM_SHUFFLE;
        row->message = D->messages[message];
    } else if (U->screen == JUKEBOX_SCREEN_CATEGORIES) {
        row->message = D->category[index].name;
        row->number = D->category[index].count;
    } else if (U->screen == JUKEBOX_SCREEN_OPTIONS) {
        if (r & 1)
            return 0;
        option_row(r >> 1, buffer, row);
    } else {
        int track = row_track(index), at = jukebox_find_song(U->list, track);
        row->message = track_name(track);
        if (U->screen == JUKEBOX_SCREEN_SONGS) {
            row->number = at >= 0 ? at + 1 : -1;
            row->mark = at >= 0;
        } else {
            row->number = index + 1;
            row->mark = U->moving ? index == U->page * PAGE + U->row
                                  : jukebox_playing() == U->list && jukebox_state.current_track == track;
        }
    }
    return 1;
}

static void draw_rows(u8 *obj)
{
    for (int r = 0; r < PAGE; r++) {
        struct row row;
        int shown = row_content(U->page * PAGE + r, r, &row);
        null_show(obj, 2 * r, shown);
        if (!shown)
            continue;
        if (row.number >= 0) {
            decimal(U->numbers[r], row.number);
            write_text(ref_at(obj, L_TEXTS + 8 * (2 * r)), D->messages[JM_SLOT], U->numbers[r]);
        } else {
            hide_text(ref_at(obj, L_TEXTS + 8 * (2 * r)));
        }
        write_text(ref_at(obj, L_TEXTS + 8 * (2 * r + 1)), row.message, row.text);
        flag_pane(ref_at(obj, L_SPRITES + 8 * r), SPRITE_FLAGS, SPRITE_SHOWN, row.mark);
    }
}

static void draw_title(u8 *obj)
{
    struct row row;
    row.text = 0;
    if (U->screen == JUKEBOX_SCREEN_MAIN)
        row.message = D->messages[JM_LINE];
    else if (U->screen == JUKEBOX_SCREEN_PLAYLIST)
        playlist_name(U->list, U->title, &row);
    else if (U->screen == JUKEBOX_SCREEN_CATEGORIES)
        row.message = D->messages[JM_ADD];
    else if (U->screen == JUKEBOX_SCREEN_SONGS)
        row.message = D->category[U->category].name;
    else if (U->screen == JUKEBOX_SCREEN_EDIT)
        row.message = D->messages[JM_EDIT];
    else
        row.message = D->messages[JM_OPTIONS];
    if (row.text)
        text_slot(0, row.text, text_length(row.text));
    ribbon_title(obj, RIBBON_GROUP, RIBBON_TEXT, ROOM_FILE, row.message);
}

static void draw_cursor(u8 *obj)
{
    u8 *ref = ref_at(obj, L_NULLS + 8 * NULL_CURSOR);
    float *place = (float *)data_of(ref);
    place[0] = CURSOR_X - CURSOR_X * (float)(U->row & 1);
    place[1] = CURSOR_Y - CURSOR_STEP * (float)(U->row >> 1);
    node_changed(ref, node_of(ref));
}

static void draw(u8 *obj)
{
    draw_title(obj);
    draw_rows(obj);
    draw_cursor(obj);
    null_show(obj, NULL_ARROWS, U->pages > 1);
    null_show(obj, NULL_PAGE, U->pages > 1);
}

/* ----- the screens ----------------------------------------------------------------------------------------------- */

static void listen_stop(void)
{
    if (U->listening != JUKEBOX_NO_SONG)
        jukebox_listen_stop();
    U->listening = JUKEBOX_NO_SONG;
}

static int rows_on_page(int page)
{
    int n = U->count - page * PAGE;
    return n > PAGE ? PAGE : n;
}

/* `screen` with the cursor on its row `index` (its last row when it has fewer) */
static void go_screen(u8 *obj, int screen, int index)
{
    if (screen != JUKEBOX_SCREEN_SONGS && screen != JUKEBOX_SCREEN_EDIT)
        listen_stop();
    U->screen = (u8)screen;
    U->moving = 0;
    U->count = (u16)rows_of(screen);
    U->pages = 1;
    while (U->pages * PAGE < U->count)
        U->pages++;
    if (index >= U->count)
        index = U->count ? U->count - 1 : 0;
    U->page = 0;
    while (index >= PAGE) {
        index -= PAGE;
        U->page++;
    }
    U->row = (u8)index;
    draw(obj);
}

static void open_menu(u8 *obj)
{
    jukebox_check_owner();
    touch_panels(0);
    list_bind(obj + LIST);
    show_group(obj, GROUP_BACKGROUND, 0);
    show_group(obj, GROUP_LIST, LIST_PRIORITY);
    show_group(obj, GROUP_CURSOR, LIST_PRIORITY);
    show_group(obj, GROUP_RIBBON, LIST_PRIORITY);
    null_show(obj, NULL_RIBBON, 1);
    touch_owner();
    gui_layer_set(GUI_LAYER);
    start_help_show(HELP_KIND, GUI_LAYER);
    U->open = 1;
    U->typing = 0;
    U->asking = 0;
    U->listening = JUKEBOX_NO_SONG;
    U->category = 0;
    U->list = 0;
    go_screen(obj, JUKEBOX_SCREEN_MAIN, jukebox_playing() >= 0 ? jukebox_playing() : 0);
}

static void close_menu(u8 *obj)
{
    if (!U->open)
        return;
    if (U->typing)
        keyboard_close(game_control);
    if (U->asking)
        window_close(YES_NO, 0);
    listen_stop();
    list_unbind(obj + LIST);
    window_close(FRAME_ONE, 0);
    window_close(FRAME_FOUR, 1);
    menu_close_frames();
    touch_owner_close();
    U->open = 0;
    U->typing = 0;
    U->asking = 0;
}

static void back(u8 *obj)
{
    sound(SOUND_CANCEL);
    if (U->screen == JUKEBOX_SCREEN_MAIN) {
        u8 *f = obj + FACILITY;
        close_menu(obj);
        f[F_STATE] = STATE_MENU;
        f[F_SUB] = 0;
    } else if (U->screen == JUKEBOX_SCREEN_PLAYLIST) {
        go_screen(obj, JUKEBOX_SCREEN_MAIN, U->list);
    } else if (U->screen == JUKEBOX_SCREEN_CATEGORIES) {
        go_screen(obj, JUKEBOX_SCREEN_PLAYLIST, ROW_ADD);
    } else if (U->screen == JUKEBOX_SCREEN_SONGS) {
        go_screen(obj, JUKEBOX_SCREEN_CATEGORIES, U->category);
    } else if (U->screen == JUKEBOX_SCREEN_EDIT && U->moving) {
        U->moving = 0;
        draw_rows(obj);
    } else if (U->screen == JUKEBOX_SCREEN_EDIT) {
        go_screen(obj, JUKEBOX_SCREEN_PLAYLIST, ROW_EDIT);
    } else {
        go_screen(obj, JUKEBOX_SCREEN_MAIN, playlists());
    }
}

static int line_up(int row)
{
    row -= 2;
    return row < 0 ? row + PAGE : row;
}

static int line_down(int row)
{
    row += 2;
    return row >= PAGE ? row - PAGE : row;
}

/* the song being moved goes to the cursor's row */
static void move_song(int from)
{
    const struct jukebox_playlist *p = open_list();
    jukebox_move_song(U->list, song_at(p, from), song_at(p, U->page * PAGE + U->row));
}

/* the Song Select's cursor (FUN_009f838c): up and down by a line round the column; left and right inside a line; left
   from the left column turns back a page (to the line's right row), right from the right column turns on a page (to
   the line's left row); right from a left row without a right one goes to the right column's nearest row above, or
   turns on a page when that column is empty. On a turn the row climbs by lines into the new page (FUN_00a5a0ac's
   clamp) and then takes the new row when that page has it. */
static void move(u8 *obj, u32 dirs)
{
    int on = rows_on_page(U->page), cur = U->row, row = cur, page = U->page, turn = 0;
    int from = U->page * PAGE + cur;
    if (on <= 0)
        return;
    if (dirs & DIR_UP) {
        do
            row = line_up(row);
        while (row != cur && row >= on);
    } else if (dirs & DIR_DOWN) {
        do
            row = line_down(row);
        while (row != cur && row >= on);
    } else if (dirs & DIR_LEFT) {
        row = cur & 1 ? cur - 1 : cur + 1;
        turn = cur & 1 ? 0 : -1;
    } else if (dirs & DIR_RIGHT) {
        if (cur & 1) {
            row = cur - 1;
            turn = 1;
        } else if (cur + 1 < on) {
            row = cur + 1;
        } else {
            row = cur + 1;
            do
                row = line_up(row);
            while (row != cur + 1 && row >= on);
            if (row == cur + 1) {
                row = cur;
                turn = 1;
            }
        }
    }
    if (turn > 0)
        page = page + 1 < U->pages ? page + 1 : 0;
    else if (turn < 0)
        page = page ? page - 1 : U->pages - 1;
    if (page == U->page) {
        if (row == cur)
            return;
        int moved = row < on;
        if (moved)
            U->row = (u8)row;
        if (moved && U->moving) {
            move_song(from);
            draw_rows(obj);
        }
        draw_cursor(obj);
        if (moved)
            sound(SOUND_CURSOR);
        return;
    }
    int at = cur;
    on = rows_on_page(page);
    while (at >= on && at >= 0)
        at -= 2;
    if (at < 0)
        at = 0;
    int moved = row != at && row < on;
    sound(SOUND_PAGE);
    U->page = (u8)page;
    U->row = (u8)(moved ? row : at);
    if (U->moving)
        move_song(from);
    draw_rows(obj);
    if (turn > 0) {
        page_turn_next();
        page_arrow_flash(ref_at(obj, L_SPRITES + 8 * SPRITE_NEXT));
    } else {
        page_turn_back();
        page_arrow_flash(ref_at(obj, L_SPRITES + 8 * SPRITE_BACK));
    }
    draw_cursor(obj);
    if (moved)
        sound(SOUND_CURSOR);
}

static void ask_clear(void)
{
    window_open(YES_NO, 0, WINDOW_YES_NO, 1);
    window_open(YES_NO_BUTTONS, 1, WINDOW_YES_NO, 0);
    U->answer = 0;
    U->asking = 1;
    sound(SOUND_DECIDE);
}

static void asking_step(u8 *obj)
{
    facility_help(HELP_KIND, ROOM_FILE, D->messages[JM_CLEAR_PROMPT]);
    window_update();
    u32 answer = window_answer(obj, &U->answer, window_input(obj), ANSWER_ANY);
    if (answer != ANSWER_YES && answer != ANSWER_NO)
        return;
    window_close(YES_NO, 0);
    U->asking = 0;
    if (answer == ANSWER_YES) {
        jukebox_clear(U->list);
        draw(obj);
    }
}

static void rename_start(void)
{
    const struct jukebox_playlist *p = open_list();
    int length = 0;
    if (!p || !keyboard_open(game_control, KEYBOARD_NAME, name_chars(), KEYBOARD_FLAG)) {
        sound(SOUND_ERROR);
        return;
    }
    while (length < JUKEBOX_NAME_CHARS && p->name[length]) {
        U->typed[length] = p->name[length];
        length++;
    }
    U->typed[length] = 0;
    sound(SOUND_KEYBOARD);
    keyboard_start(game_control, 0, U->typed);
    U->typing = 1;
}

static void typing_step(u8 *obj)
{
    int result = keyboard_poll(game_control);
    if (result == 0)
        return;
    U->typing = 0;
    if (result < 0)
        return;
    keyboard_copy(game_control, U->typed, keyboard_text(game_control), name_chars(), name_chars());
    jukebox_rename(U->list, U->typed, (int)text_length(U->typed));
    draw(obj);
}

static void playlist_action(u8 *obj, int index)
{
    const struct jukebox_playlist *p = open_list();
    int screen = -1;
    if (index == ROW_PLAY) {
        if (jukebox_playing() == U->list)
            jukebox_stop();
        else if (known_songs(p))
            jukebox_play(U->list);
        else
            index = -1;
    } else if (index == ROW_ADD) {
        screen = categories() ? JUKEBOX_SCREEN_CATEGORIES : -1;
        index = screen;
    } else if (index == ROW_EDIT) {
        screen = known_songs(p) ? JUKEBOX_SCREEN_EDIT : -1;
        index = screen;
    } else if (index == ROW_RENAME) {
        rename_start();
        return;
    } else if (index == ROW_ORDER) {
        jukebox_set_order(U->list, p->order == JUKEBOX_SHUFFLE ? JUKEBOX_IN_ORDER : JUKEBOX_SHUFFLE);
    } else {
        ask_clear();
        return;
    }
    if (index < 0) {
        sound(SOUND_ERROR);
        return;
    }
    sound(SOUND_DECIDE);
    if (screen >= 0)
        go_screen(obj, screen, 0);
    else
        draw_rows(obj);
}

static void choose(u8 *obj)
{
    int index = U->page * PAGE + U->row;
    if (U->screen == JUKEBOX_SCREEN_MAIN) {
        sound(SOUND_DECIDE);
        if (index == playlists()) {
            go_screen(obj, JUKEBOX_SCREEN_OPTIONS, 0);
        } else {
            U->list = (u8)index;
            go_screen(obj, JUKEBOX_SCREEN_PLAYLIST, ROW_PLAY);
        }
    } else if (U->screen == JUKEBOX_SCREEN_PLAYLIST) {
        playlist_action(obj, index);
    } else if (U->screen == JUKEBOX_SCREEN_CATEGORIES) {
        sound(SOUND_DECIDE);
        U->category = (u8)index;
        go_screen(obj, JUKEBOX_SCREEN_SONGS, 0);
    } else if (U->screen == JUKEBOX_SCREEN_SONGS) {
        int track = row_track(index), at = jukebox_find_song(U->list, track);
        if (at >= 0) {
            jukebox_remove_song(U->list, at);
            sound(SOUND_CANCEL);
        } else if (jukebox_add_song(U->list, track)) {
            sound(SOUND_DECIDE);
        } else {
            sound(SOUND_ERROR);
            return;
        }
        draw_rows(obj);
    } else if (U->screen == JUKEBOX_SCREEN_EDIT) {
        U->moving = !U->moving;
        sound(SOUND_DECIDE);
        draw_rows(obj);
    }
}

static void remove_song(u8 *obj)
{
    int index = U->page * PAGE + U->row, at = song_at(open_list(), index);
    if (U->screen != JUKEBOX_SCREEN_EDIT || U->moving || at < 0)
        return;
    jukebox_remove_song(U->list, at);
    sound(SOUND_CANCEL);
    if (known_songs(open_list()))
        go_screen(obj, JUKEBOX_SCREEN_EDIT, index);
    else
        go_screen(obj, JUKEBOX_SCREEN_PLAYLIST, ROW_EDIT);
}

static void listen(void)
{
    if (U->screen != JUKEBOX_SCREEN_SONGS && U->screen != JUKEBOX_SCREEN_EDIT)
        return;
    int track = row_track(U->page * PAGE + U->row);
    if (U->listening == track) {
        listen_stop();
        sound(SOUND_CANCEL);
    } else if (jukebox_listen(track)) {
        U->listening = (u16)track;
        sound(SOUND_DECIDE);
    } else {
        sound(SOUND_ERROR);
    }
}

/* the options: up and down between them, left and right change the value, round its range */
static void option_keys(u8 *obj, u32 dirs)
{
    int option = U->row >> 1, step = 0, low, high;
    if (dirs & (DIR_UP | DIR_DOWN)) {
        if (dirs & DIR_UP)
            option = option ? option - 1 : OPTIONS - 1;
        else
            option = option + 1 < OPTIONS ? option + 1 : 0;
        U->row = (u8)(2 * option);
        sound(SOUND_CURSOR);
        draw_cursor(obj);
        return;
    }
    if (dirs & DIR_RIGHT)
        step = 1;
    else if (dirs & DIR_LEFT)
        step = -1;
    if (!step)
        return;
    option_range(option, &low, &high);
    int value = jukebox_option(option) + step;
    if (value > high)
        value = low;
    if (value < low)
        value = high;
    jukebox_set_option(option, value);
    sound(SOUND_CURSOR);
    draw_rows(obj);
}

static u32 help(void)
{
    if (U->screen == JUKEBOX_SCREEN_MAIN)
        return JM_HELP_MAIN;
    if (U->screen == JUKEBOX_SCREEN_PLAYLIST)
        return JM_HELP_PLAYLIST;
    if (U->screen == JUKEBOX_SCREEN_CATEGORIES)
        return JM_HELP_CATEGORIES;
    if (U->screen == JUKEBOX_SCREEN_SONGS)
        return JM_HELP_SONGS;
    if (U->screen == JUKEBOX_SCREEN_EDIT)
        return U->moving ? JM_HELP_MOVING : JM_HELP_EDIT;
    return JM_HELP_OPTIONS;
}

/* the Song Select's order (FUN_009f838c): A, B, then up, down, left, right; X and Y after them. FUN_009b3830 answers
   every bit pressed or repeating, so only its directions are kept. */
static void keys(u8 *obj)
{
    u32 dirs = facility_dirs(obj) & (DIR_UP | DIR_DOWN | DIR_LEFT | DIR_RIGHT);
    if (facility_pressed(obj, BUTTON_A) && U->screen == JUKEBOX_SCREEN_OPTIONS)
        option_keys(obj, DIR_RIGHT);
    else if (facility_pressed(obj, BUTTON_A))
        choose(obj);
    else if (facility_pressed(obj, BUTTON_B))
        back(obj);
    else if (U->screen == JUKEBOX_SCREEN_OPTIONS)
        option_keys(obj, dirs);
    else if (dirs)
        move(obj, dirs);
    else if (facility_pressed(obj, BUTTON_X))
        remove_song(obj);
    else if (facility_pressed(obj, BUTTON_Y))
        listen();
}

/* One frame of state 10 (`facility`: the lobby object). */
void jukebox_menu_frame(void *facility)
{
    u8 *obj = facility;
    if (gui_event(EXIT_EVENT)) {
        close_menu(obj);
        obj[FACILITY + F_STATE] = STATE_LEAVING;
        house_farewell(obj, FAREWELL, 0);
        return;
    }
    int opening = !U->open;             /* the first frame: the list opened, no key read yet */
    if (opening)
        open_menu(obj);
    page_arrow_idle(ref_at(obj, L_SPRITES + 8 * SPRITE_NEXT));
    page_arrow_idle(ref_at(obj, L_SPRITES + 8 * SPRITE_BACK));
    if (U->typing) {
        typing_step(obj);
    } else if (U->asking) {
        asking_step(obj);
    } else {
        facility_help(HELP_KIND, ROOM_FILE, D->messages[help()]);
        if (!opening)
            keys(obj);
    }
    if (U->open)                        /* after the keys, while the list stays (the facility's frame, 0x9AC7F8) */
        page_counter(D->counter_x, D->counter_y, U->page, U->pages, 0, 0);
}
