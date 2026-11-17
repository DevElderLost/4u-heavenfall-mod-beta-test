/* The jukebox's contract: the block saved in the card file, the data block the
 * patcher fills (music/jukebox/patch.py data_block), the state in the extension's variables, and the calls the block's
 * three units share. jukebox.c is the engine (the pick, the tick, the order, the resume list, listening); jukebox_save.c
 * the card's store and load; jukebox_menu.c the house Felyne's menu.
 *
 * Build: tools/build/build_code_space.py (devkitARM), which places and links it.
 */
#ifndef JUKEBOX_H
#define JUKEBOX_H

typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;
typedef short s16;
typedef unsigned char u8;
typedef signed char s8;

/* ---- The saved block, version 1: 848 bytes at the card file's +0x78878 ---- */
#define JUKEBOX_MAGIC 0x584F424AU       /* "JBOX" */
#define JUKEBOX_VERSION 1
#define JUKEBOX_PLAYLISTS 8
#define JUKEBOX_SONGS 40
#define JUKEBOX_NAME_CHARS 10
#define JUKEBOX_NO_SONG 0xFFFF          /* a track id that names no song */

enum { JUKEBOX_IN_ORDER = 0, JUKEBOX_SHUFFLE = 1 };            /* a playlist's order */
enum { JUKEBOX_THIS_SESSION = 0, JUKEBOX_ALWAYS = 1 };         /* options.keep */

struct jukebox_options {
    u8 active;                          /* the playlist playing + 1; 0: none */
    u8 keep;                            /* JUKEBOX_THIS_SESSION: a load starts with no playlist; JUKEBOX_ALWAYS */
    u8 halls;                           /* 1: the halls' music is replaced too */
    u8 loops;                           /* passes of a song's loop before its fade-out */
    u8 fade;                            /* the fade-out, seconds */
    u8 spare[3];
};

struct jukebox_playlist {
    u16 name[JUKEBOX_NAME_CHARS];       /* UTF-16, 0 after the last character; all 0: the default name */
    u8 order;                           /* JUKEBOX_IN_ORDER / JUKEBOX_SHUFFLE */
    u8 count;                           /* songs */
    u8 spare[2];
    u16 songs[JUKEBOX_SONGS];           /* track ids (curated/jukebox.json) */
};

struct jukebox_save {
    u32 magic;                          /* JUKEBOX_MAGIC */
    u16 version;                        /* JUKEBOX_VERSION */
    u16 sum;                            /* of the bytes after the header */
    struct jukebox_options options;
    struct jukebox_playlist playlists[JUKEBOX_PLAYLISTS];
};

_Static_assert(sizeof(struct jukebox_options) == 8, "Layout, version 1: options");
_Static_assert(sizeof(struct jukebox_playlist) == 104, "Layout, version 1: a playlist");
_Static_assert(sizeof(struct jukebox_save) == 848, "Layout, version 1");

/* ---- The data block jukebox_data (music/jukebox/patch.py data_block) ---- */
#define JUKEBOX_PLACES 16               /* room of each list of replaced requests */
#define JUKEBOX_MESSAGES 64             /* room of the menu's message numbers */
#define JUKEBOX_TRACK_ROOM 512          /* track ids the request table holds */
#define JUKEBOX_NO_REQUEST 0xFFFF       /* a list's end; a track the build lacks */

struct jukebox_limits {
    u8 playlists, songs, name_chars;    /* at most the saved layout's 8, 40 and 10 */
    u8 loops_min, loops_max;            /* passes of a loop */
    u8 fade_min, fade_max;              /* the fade-out, seconds */
    u8 spare;
};

/* the menu's lists (jukebox_menu.c) */
#define JUKEBOX_CATEGORIES 8            /* room of the menu's categories */
#define JUKEBOX_MENU_TRACKS 256         /* room of the menu's track list */

struct jukebox_category {
    u16 first;                          /* its first track in menu_tracks */
    u16 count;                          /* its tracks */
    u16 name;                           /* its name's message */
    u16 spare;
};

struct jukebox_data {
    u16 villages[JUKEBOX_PLACES];       /* the places' requests a playlist replaces, JUKEBOX_NO_REQUEST after the last */
    u16 halls[JUKEBOX_PLACES];          /* those it replaces with the option halls */
    struct jukebox_limits limits;
    struct jukebox_options defaults;    /* the options of a new block (active 0) */
    u16 first_request, last_request;    /* the jukebox's own requests in bgm_lob: no place's request is among them */
    u16 tracks;                         /* the entries of requests[] */
    u16 spare;
    u16 messages[JUKEBOX_MESSAGES];     /* the menu's message numbers */
    u16 requests[JUKEBOX_TRACK_ROOM];   /* each track id's request in bgm_lob, JUKEBOX_NO_REQUEST: the build lacks it */
    /* the menu's (jukebox_menu.c; music/jukebox/texts.py, menu_patch.py) */
    s16 counter_x, counter_y;           /* the page counter's place (FUN_00288fac's x and y) */
    u16 track_names;                    /* the name message of menu_tracks[0]; each next track's follows */
    u16 categories;                     /* the entries of category[] */
    struct jukebox_category category[JUKEBOX_CATEGORIES];
    u16 menu_tracks[JUKEBOX_MENU_TRACKS];       /* the build's tracks by category, in the catalogue's order */
};

_Static_assert(sizeof(struct jukebox_data) == JUKEBOX_DATA_SIZE, "blocks.py JUKEBOX_DATA_SIZE, patch.py data_block");

extern const struct jukebox_data jukebox_data;

/* ---- The state, the variable jukebox_state ---- */
struct jukebox_state {
    struct jukebox_save save;           /* the copy of the card's block the game plays and the menu edits */
    u8 owner[8];                        /* the hunter id (the card's +0x10) the copy belongs to */
    u8 owned;                           /* 1: owner holds an id */
    u8 round_list;                      /* the playlist (+ 1) whose round is drawn; 0: none */
    u8 round_count;                     /* the round's songs */
    u8 position;                        /* the round's song playing */
    u8 passes;                          /* passes of its loop counted */
    u8 box_sent;                        /* Dundorma's box: the ambience's way out was sent */
    s8 place_index;                     /* the resume list's index of the request the pick replaced last; -1 none */
    u8 spare;
    u16 current;                        /* the song's request; 0: none */
    u16 current_track;                  /* its track id */
    u16 last_track;                     /* the song the playlist moved on from: a shuffled round never starts with it */
    u16 listen;                         /* the request listened to; 0: none */
    u16 place;                          /* the request the pick replaced last */
    u16 seen;                           /* the request whose voice the tick read last; 0: none */
    u32 generation;                     /* a new value at every song */
    u32 resume_owner;                   /* the generation whose position the resume slots hold */
    u32 resume_slots;                   /* bit n: the resume list's slot n may hold a jukebox song's position */
    u32 serial;                         /* the voice's start serial last read */
    u32 last_position;                  /* its play position then, samples */
    u32 samples, rate;                  /* the song's length (samples) and rate */
    u32 random;                         /* the shuffle's generator */
    u8 order[JUKEBOX_SONGS];            /* the round: indexes into the playlist's songs */
};

_Static_assert(sizeof(struct jukebox_state) == JUKEBOX_STATE_SIZE, "blocks.py JUKEBOX_STATE_SIZE");

extern struct jukebox_state jukebox_state;

/* ---- The engine's calls (jukebox.c) ---- */
enum { JUKEBOX_OPTION_HALLS, JUKEBOX_OPTION_KEEP, JUKEBOX_OPTION_LOOPS, JUKEBOX_OPTION_FADE };

/* The playlists: `list` 0-7. Every edit of the playlist playing calls jukebox_changed itself. */
const struct jukebox_playlist *jukebox_playlist(int list);      /* 0 for a list the limits leave out */
int jukebox_find_song(int list, int track);                     /* the song's index in the playlist, or -1 */
int jukebox_add_song(int list, int track);                      /* 1: added at the end; 0: full, there, or no track */
void jukebox_remove_song(int list, int index);
void jukebox_move_song(int list, int from, int to);             /* the song at `from` goes to `to`, the rest follow */
void jukebox_set_order(int list, int order);                    /* JUKEBOX_IN_ORDER / JUKEBOX_SHUFFLE */
void jukebox_clear(int list);                                   /* no songs, the default name, in order */
void jukebox_rename(int list, const u16 *name, int length);     /* the first JUKEBOX_NAME_CHARS characters */

/* Playing: the pick and the tick do the rest by themselves. */
void jukebox_play(int list);            /* the playlist plays from a new round (and stops the one playing) */
void jukebox_stop(void);                /* no playlist: the places' own music */
int jukebox_playing(void);              /* the playlist playing (0-7), or -1 */
int jukebox_option(int option);         /* JUKEBOX_OPTION_*: its value */
void jukebox_set_option(int option, int value);         /* clamped to its range */
int jukebox_track_request(int track);   /* the build's request of a track id, or 0 when the build lacks it */
int jukebox_listen(int track);          /* every place plays the track until jukebox_listen_stop; 0: no such track */
void jukebox_listen_stop(void);

/* The block as a whole. */
void jukebox_changed(void);             /* the copy changed (an edit, a load): the round is drawn again, the song
                                           playing kept when the playlist still has it */
void jukebox_reset(void);               /* the defaults: no playlist, eight empty playlists, the data's options */
void jukebox_owner(const u8 *hunter_id);        /* a copy of another hunter (or of none) is reset first */
void jukebox_loaded(void);              /* after a load: with JUKEBOX_THIS_SESSION, no playlist plays */

/* The hooks' entries (jukebox.s, patch.py) */
int jukebox_pick(u8 *manager, int request);     /* FUN_00304990's exit: the request it returns */
int jukebox_command_pick(u8 *manager, int which);       /* command 2's first call of FUN_00304990 */
void jukebox_tick(u8 *manager);
int jukebox_resume_index(u8 *manager, int request);     /* FUN_0030ace0 */

/* ---- The card's store and load (jukebox_save.c) ---- */
void jukebox_store(u8 *card);           /* the block into the card file being written */
void jukebox_load(const u8 *card);      /* the block from the card file read */
const u8 *jukebox_hunter(void);         /* the loaded hunter's id (8 bytes), or 0 when no slot is loaded */
void jukebox_check_owner(void);         /* the copy is made the loaded hunter's (jukebox_owner); nothing with none */

/* ---- The house Felyne's menu (jukebox_menu.c) ---- */
void jukebox_menu_frame(void *facility);

/* The menu's messages: indexes of jukebox_data.messages, in the order of music/jukebox/texts.py TEXT_KEYS */
enum {
    JM_LINE, JM_LINE_HELP, JM_SLOT, JM_PLAYLIST, JM_OPTIONS, JM_HELP_MAIN,
    JM_PLAY, JM_STOP, JM_ADD, JM_EDIT, JM_RENAME, JM_IN_ORDER, JM_SHUFFLE, JM_CLEAR, JM_HELP_PLAYLIST,
    JM_CLEAR_PROMPT, JM_HELP_CATEGORIES, JM_HELP_SONGS, JM_HELP_EDIT, JM_HELP_MOVING,
    JM_HALLS_OFF, JM_HALLS_ON, JM_KEEP_SESSION, JM_KEEP_ALWAYS, JM_LOOPS, JM_FADE, JM_HELP_OPTIONS,
    JM_COUNT
};

_Static_assert(JM_COUNT <= JUKEBOX_MESSAGES, "jukebox_data.messages holds the menu's messages");

/* The menu's screens */
enum {
    JUKEBOX_SCREEN_MAIN,                /* the playlists and Options */
    JUKEBOX_SCREEN_PLAYLIST,            /* Play / Stop, Add songs, Edit songs, Rename, Order, Clear */
    JUKEBOX_SCREEN_CATEGORIES,          /* Add songs: the categories */
    JUKEBOX_SCREEN_SONGS,               /* a category's songs */
    JUKEBOX_SCREEN_EDIT,                /* the playlist's songs in order */
    JUKEBOX_SCREEN_OPTIONS
};

#define JUKEBOX_PAGE_ROWS 10            /* ui443's rows */
#define JUKEBOX_TEXT_ROOM 12            /* a string slot's text: a name's characters and its 0 */
#define JUKEBOX_NUMBER_ROOM 4

/* The variable jukebox_menu */
struct jukebox_menu {
    u8 open;                            /* 1: ui443 is bound and the screens run */
    u8 screen;                          /* JUKEBOX_SCREEN_* */
    u8 list;                            /* the playlist open */
    u8 category;                        /* the category open */
    u8 page, pages;                     /* the page shown and the screen's pages */
    u8 row;                             /* the cursor's row on the page */
    u8 moving;                          /* Edit songs: 1 while the song under the cursor is carried */
    u8 asking;                          /* 1: Clear's yes / no window is open */
    u8 typing;                          /* 1: the keyboard is open */
    u8 spare[2];
    u16 count;                          /* the screen's rows */
    u16 listening;                      /* the track listened to; JUKEBOX_NO_SONG: none */
    u32 answer;                         /* the yes / no window's answer */
    u16 texts[JUKEBOX_PAGE_ROWS][JUKEBOX_TEXT_ROOM];       /* each row's title, shown through string slot 0 */
    u16 numbers[JUKEBOX_PAGE_ROWS][JUKEBOX_NUMBER_ROOM];   /* each row's number */
    u16 title[JUKEBOX_TEXT_ROOM];       /* the ribbon's */
    u16 typed[JUKEBOX_TEXT_ROOM];       /* the keyboard's text, cut to the name's room */
};

_Static_assert(sizeof(struct jukebox_menu) == JUKEBOX_MENU_SIZE, "blocks.py JUKEBOX_MENU_SIZE");

extern struct jukebox_menu jukebox_menu;

/* The menu's hooks' entries (jukebox_menu_stub.s, menu_patch.py) */
void jukebox_lines(u8 *obj);                    /* FUN_00aa8074's call of FUN_00aa771c: the lines, ours last */
void jukebox_menu_line(u8 *obj);                /* FUN_009db3ac: our line's frame and text */
u32 jukebox_help_message(const u8 *facility);   /* FUN_009db608: our line's help, 0 for the game's lines */
int jukebox_menu_pick(int action, u8 *obj);     /* FUN_00aa8298, A on a line: ours enters state 10 */
int jukebox_facility_state(int state, u8 *obj); /* FUN_00aa8298's state switch: state 10 runs the menu */

#endif
