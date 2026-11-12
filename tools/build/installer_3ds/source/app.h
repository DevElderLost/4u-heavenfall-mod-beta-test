/* The launcher app: the state its screens share and the calls between its files.
 * The libctru side only; every rule with logic is in core/install/launcher/c/ (tested on the PC). */
#ifndef APP_H
#define APP_H

#include <3ds.h>
#include <stdint.h>
#include <stdio.h>

#include "dump.h"
#include "hf_editions.h"
#include "hfnet.h"
#include "launcher.h"
#include "settitle.h"
#include "ui.h"
#include "uimodel.h"
#include "updplan.h"

#ifndef HF_APP_VERSION
#define HF_APP_VERSION "0.1.0"   /* the running app's version: the release's tag when it is built for a release */
#endif

/* The release's text read for its notes (the raw markdown, before hf_notes_plain): a heap buffer while it is read. */
#define NOTES_RAW_SIZE (16 * 1024)

/* The friends module's patch (another file: ctr_friends.c; the stub's until it lands). msg gets a line for the screen. */
enum { HF_FRIENDS_NOT_NEEDED = 0, HF_FRIENDS_INSTALLED = 1, HF_FRIENDS_INSTALLABLE = 2, HF_FRIENDS_UNSUPPORTED = 3,
       HF_FRIENDS_DAMAGED = 4 };   /* the .ips is one Luma3DS refuses: Remove gives back a good one */
int hf_friends_status(char *msg, size_t n);
int hf_friends_install(char *msg, size_t n);
int hf_friends_remove(char *msg, size_t n);
int hf_friends_dump(const char *dir, char *msg, size_t n);

#define DUMP_NONE 0
#define DUMP_FOUND 1
#define DUMP_ENCRYPTED 2
#define DUMP_OTHER_REGION 3

/* The player's MH XX dump. */
#define XX_NONE 0
#define XX_FOUND 1
#define XX_ENCRYPTED 2
#define XX_OTHER_VERSION 3        /* decrypted, but the release's XX set was made from another revision */

typedef struct {
    int title_installed;          /* the edition's title is in the SD card's list */
    int installed_region;         /* its region (REGION_EUR 0, REGION_USA 1), -1 when not installed */
    char installed[48];           /* from its TMD version, "" when not installed */
    int installed_complete;       /* installed.json agrees and is not marked as cut */
    int save_pending;             /* installed.json: the first install's save copy was neither done nor declined */
    char save_restore[18];        /* installed.json: the backup the removed title's save comes back from, "" none */
    int layout;                   /* installed.json: 1 the old single title, 2 split; 0 no record */
    int game_installed;           /* the game data title (hf_game_title_id) is in the SD card's list */
    int game_complete;            /* installed.json: it was installed whole */
    int game_state;               /* HF_GAME_*: what the screens say of it */
    char dump_hash[65];           /* the MH4U dump's RomFS superblock hash (hf_hex), "" none */
    char installed_xx_dump[65];   /* installed.json xx_dump */
    int installed_xx;             /* installed.json xx */
    int installed_xx_no_room;     /* installed.json xx_no_room */
    char latest[48];              /* the latest release's tag, "" when not read */
    int dump;                     /* DUMP_* */
    char dump_path[512];
    uint64_t dump_bytes;          /* its size (the title's, near enough, before the set is opened) */
    int region;                   /* of the dump (REGION_EUR 0, REGION_USA 1), -1 unknown */
    int xx;                       /* XX_* */
    char xx_path[512];
    uint8_t xx_hash[32];          /* its RomFS superblock hash: which revision it is */
    int luma;                     /* Luma3DS present */
    char luma_version[24];
    uint64_t free_bytes;
} Status;

/* The last XX set header read (the status line's "another version"). */
typedef struct {
    int known;
    int edition;                  /* whose release it was */
    uint8_t hash[32];             /* the XX dump's hash it was checked for */
    int matches;                  /* it names that revision */
} XxCheck;

typedef struct {
    HfLang lang;
    int edition;                  /* index into HF_EDITIONS */
    int probe;                    /* the probe build: HF_PROBE */
    u8 model;                     /* CFG_SystemModel */
    int is_3dsx;
    char own_path[256];           /* argv[0] of a .3dsx */
    FILE *logf;
    HfLog log;
    Status status;
    XxCheck xx_check;
    HfCheck check;                /* the start's look for the latest release, for this edition */
    char notes[HF_VIEW_NOTES];    /* the latest release's notes as plain lines (hf_notes_plain), "" none */
    uint64_t latest_set_bytes;    /* the latest release's plain set for the dump's region (0 unknown): the time estimate */
    int latest_xx_set;            /* the latest release has the region's XX set (the start's check) */
    int latest_app_newer;         /* ... and this form's launcher, newer than this one (the start's check) */
    int xx_skipped;               /* the guide's Skip on MH XX, for this session */
    int guide_shown;              /* the guide opened by itself once this session */
} App;

extern App app;

static inline const HfEdition *app_edition(void) { return &HF_EDITIONS[app.edition]; }
/* A text in the app's language (UTF-8, as the view takes it: only the simple display converts it to the console
 * font's code page 437). */
const char *T(HfText id);

/* The screen tuning (hf_tuning.h) as uimodel.h takes it. */
extern const HfUiTuning app_tuning;

/* app_log.c */
void log_open(void);
void log_close(void);
#define LOG(...) hf_log(&app.log, osGetTime(), __VA_ARGS__)
#define LOGR(what, res) LOG("%s: 0x%08lX", what, (unsigned long)(res))
uint64_t clock_ms(void);
/* Allocations the heap refused (app_log.c, through the linker's --wrap): how many and the size of the last. */
typedef struct {
    unsigned long count;
    size_t last;
} AppRefused;
extern AppRefused app_refused;

/* app_ui.c: the pages on the drawing layer (ui.h): they fill the view, and the waits read its events */
#define UI_BACK (-2)   /* ui_choose: B */
/* The view cleared for `screen` (its serial and a message on it kept), the selection on none: a page fills it next. */
void ui_reset(HfView *v, HfScreen screen);
/* A button at the end of the view's list. */
void ui_button(HfView *v, const char *label, int id, int primary, int enabled);
/* One event against the view's buttons: the id of the button touched, or chosen with A; UI_BACK for B; -1 for none.
 * The D-pad's Up and Down move the selection over the enabled buttons. */
int ui_choose(const UiEvent *ev);
void ui_message(const char *line);   /* a text over the top screen, then A (or its button) to go on */
/* The same in a colour, with `small` (a code for the log's reader; "" none) in the bottom screen's footer meanwhile. */
void ui_message_ex(const char *text, HfTone tone, const char *small);
int ui_confirm(const char *question);   /* A yes, B no (and the console closing); also by touch */
void ui_notice_for(const char *text, u32 ms);   /* a text over the top screen for `ms`, no key */
void ui_working(const char *text);   /* a text over the top screen with the spinner, no key nor button: a step runs */
void ui_working_end(void);           /* the page as it was before ui_working (a message or a new page also ends it) */
void ui_notice(HfText text);         /* a line under the bar (the MH XX notes); no key */
int ui_progress(void *ctx, uint64_t done, uint64_t total);   /* a TitleProgress / HF progress: nonzero cancels (B twice) */
void ui_phase(HfText name);  /* the step now running, with the spinner: the bar's stage follows it */
void ui_idle(void);          /* no step runs: the spinner stops */

/* The update's task page and its single bar (app_ui.c over uimodel.h's progress rules). */
void task_page(HfText state);        /* the task page: the edition, the three stages, no bar yet */
/* The bar starts at 0, planned for these bytes (download: the files to fetch; install: the title) at the last
 * install's rates (`last`, may be NULL) or the tuning's. Cancel (B twice) and the screens' dimming run until task_end. */
void task_begin(const HfTimings *last, const uint64_t bytes[HF_STAGES], uint64_t game_bytes);
void task_download(uint64_t base);   /* the next download starts after `base` bytes of the stage's files */
void task_title_size(uint64_t bytes);   /* the title's size is known: "Installing" is planned again for it */
void task_part_begin(HfTitleKind kind);   /* the install of this title begins (the bar weighs the two by their bytes) */
void task_part_end(HfTitleKind kind);     /* ... ended: its time kept for timings.json */
void task_route_again(void);         /* a fallback route repeats the install: planned again */
void task_end(int done);             /* the bar full when done; the screens on, no more dimming */
void task_measured(HfTimings *out);  /* each stage's time and bytes, for timings.json */
uint32_t task_expected_s(const HfTimings *last, const uint64_t bytes[HF_STAGES], uint64_t game_bytes);   /* the plan's whole time */

/* app_status.c */
void status_gather(void);
uint64_t edition_title_id(int region);          /* the edition's title id for a region */
uint64_t game_title_id(int region);              /* its game data title's id */
int read_installed_record(HfInstalled *rec);    /* installed.json; 0 when missing or broken */
/* The installed version was built plain after this MH XX dump's files were found to differ (hf_xx_came's xx_tried). */
int status_xx_tried(void);
/* hf_xx_came for the installed title and the release `tag` (which has the region's XX set or not). */
int status_xx_came(const char *tag, int xx_set_in_release);
const char *region_name(int region);
/* `len` bytes into `path` whole: a temporary file, then the rename. 0 on success. */
int write_whole(const char *path, const char *text, size_t len);
/* A small file (at most cap - 1 bytes) into `buf`, terminated; its length, -1 when missing or bigger. */
long read_small(const char *path, char *buf, size_t cap);

/* app_install.c: from a downloaded patch set to the installed title; `xx`: the set is the one with MH XX, `no_room`: the
 * plain set taken because this version's XX set did not fit the memory (both recorded in installed.json). After the
 * edition's first install the record says the save copy waits (save_pending). A TITLE_* / HF_* code (0 done). */
int install_set(const char *set_path, const char *version, int xx, int no_room, HfTitleKind kind);
/* The XX set at `set_path` against the player's XX dump, before anything is installed: its
 * RomFS superblock hash when it equals the set's, else the set's second-game files one by one (srcfiles.h). *match is
 * 1 when the dump can be used; with files rather than the hash, install_set takes it for the set's (install_xx_by_files).
 * A TITLE_* code when the dump or the set cannot be read. */
int xx_files_check(const char *set_path, int *match);
extern int install_xx_by_files;
/* The XX dump (hf_hex) whose files were found to differ from the update's XX set, "" none: installed.json's xx_dump of
 * a plain title, so the same version does not try it again (hf_xx_came). */
extern char install_xx_differs[65];
/* installed.json's save_pending cleared (the copy was done or declined). */
void installed_save_done(void);
/* installed.json's save_restore cleared (the save is back). */
void installed_restore_done(void);
extern Result install_am_result;     /* what AM answered at the step that failed */
extern uint32_t room_missing_mb;     /* the MB the card lacked when an install or a download stopped for room */
/* The last install_set removed the installed title before AM's import (AM imports over none): when it then stopped,
 * the player has no title of that kind until the next update (hf_stop_note says so). */
extern int install_old_removed;

/* app_update.c */
/* The Update flow (notes, battery, the task page, the failure's advice, Play now). `resuming`: the app updated itself
 * and goes on; `reinstall`: More's Reinstall, the mod's title again whatever the version. 1 when the app must leave (a
 * title started, the app relaunching or to be reopened). */
int update_run(int resuming, int reinstall);
/* The release file of this app's form: HF_W_CIA or HF_W_3DSX. */
int app_asset(void);
/* The latest release of edition `e` into `rel`, its notes into `notes` (NULL: not wanted). An HF_* code. Logged. */
int release_latest(const HfTransport *tr, const HfEdition *e, HfRelease *rel, char *notes, size_t notes_cap);
/* A probe build's test launcher: a CIA of the launcher's title left in the edition's test_app/ folder (the edition's
 * app_cia name), as a release of its CIA's own version with that one asset: 1, else 0 (none, not the launcher's, the
 * .3dsx form). Its folder for the app's step. Read from the start's check thread too. */
int probe_test_app(HfRelease *rel, char *dir, size_t cap);
/* A probe build's release from test_release/ on the card, notes included (0, else a HF_REL_* or -1). */
int release_local(const HfEdition *e, HfRelease *rel, char *notes, size_t notes_cap);
/* The region's XX set against a player's MH XX dump (xx: XX_*, its hash): the plan's XX inputs into `in`, and the
 * answer into `out` when the header was read. An HF_* code when it was not. */
int release_xx_check(const HfTransport *tr, int edition, const HfRelease *rel, int region, int xx,
                     const uint8_t xx_hash[32], HfPlanIn *in, XxCheck *out);
/* The resume file of any edition: deleted, and 1 (the edition chosen) when the update goes on with this app. */
int resume_found(void);
int timings_read(HfTimings *t);   /* the edition's timings.json: 1 when it holds the last install's times */
void probe_startup(void);    /* the probe build: dumps the friends module's code into the log folder */
void online_run(void);
const char *online_state_text(int st);   /* the friends patch's state as a line ("" when it needs none) */

/* app_check.c: the start's look for the latest release, on a thread of its own (256 KB of stack for TLS) */
void check_start(void);      /* for app.edition; app.check is HF_CHECK_RUNNING until its answer is applied */
int check_running(void);
int check_poll(void);        /* its answer applied when it ended: 1 then (the page is drawn again) */
/* Stops it (`abort`: at once) and joins it: its stack and buffers are freed; a finished answer is applied. Called
 * before an update, the information page, a title's start, the edition's switch and the exit. */
void check_stop(int abort);

/* app_home.c */
void language_load(void);
void language_switch(void);
int home_run(void);          /* the home screen until the app leaves */

/* app_wizard.c: the first-run guide; 1 when the app must leave */
int wizard_run(void);

/* app_saves.c: the MH4U save into the edition's title (`quiet`: no message when there is nothing to copy yet). Done or
 * declined clears installed.json's save_pending. */
enum { SAVE_COPIED = 0, SAVE_DECLINED, SAVE_FAILED, SAVE_NO_ORIGINAL, SAVE_NOT_RUN };
int saves_copy_flow(int quiet);
/* The save of the edition's installed title copied to the card's backups (before an install removes the title). 0 when
 * done or when the title has no save yet; nonzero when the copy failed. */
int saves_backup_installed(u64 title_id, char stamp[18]);
/* After an install removed and put back the title: the raw save
 * file kept beside backup `stamp` written back at its place, then checked against the backup through FS. 0 when the
 * save is back as it was; nonzero when not (AM's new file is then written back: the game makes its save at its first
 * run, and saves_restore_flow brings the backup once it opens). */
int saves_raw_restore(u64 title_id, const char *stamp);
/* installed.json's save_restore (the backup of a save an install took away) into the title's save, once that opens
 * (the game's first run made it). `quiet`: no message while it does not open yet. SAVE_* as saves_copy_flow. */
int saves_restore_flow(int quiet);

/* app_start.c */
int original_game(u64 *id, FS_MediaType *media);   /* the original MH4U on the cartridge or the SD card */
int original_game_for(int region, int region_first, u64 *id, FS_MediaType *media);   /* app_start.c */
int start_edition(void);        /* 0 and the app should exit; else a message was shown */
int start_original(void);

#endif
