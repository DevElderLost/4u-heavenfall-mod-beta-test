/* The launcher's screen rules (portable C99, pure, no libctru): what the home screen
 * says and offers, the first-run guide's step, the install's single progress bar and its time left, the cancel and
 * backlight timers, the battery warning, the resume file the app leaves when it updates itself, the room an install
 * needs, a failure's advice and the release's notes as plain lines. Tuning values come in through HfUiTuning (the
 * app's generated hf_tuning.h, from core/game/data/curated/launcher_ui.json); the tests pass their own.
 * tests/install/launcher/test_launcher_ui.py builds this with the host gcc. */
#ifndef HF_UIMODEL_H
#define HF_UIMODEL_H

#include <stddef.h>
#include <stdint.h>

#include "launcher.h"

/* ---- tuning ---- */

/* The install's steps as the player sees them: every HT_PHASE_* belongs to one (hf_stage_of_phase). */
#define HF_STAGES 3
typedef enum { HF_STAGE_DOWNLOAD = 0, HF_STAGE_INSTALL = 1, HF_STAGE_FINISH = 2 } HfStage;

typedef struct {
    uint32_t download_kib_s;       /* expected download speed before any measured one */
    uint32_t install_kib_s;        /* expected speed of building and writing the title, before any measured one */
    uint32_t finish_ms;            /* expected time of "Finishing" (AM's finish and commit: no progress) */
    uint32_t finish_cap_permille;  /* "Finishing" is driven by time and stops here until it ends (below 1000) */
    uint32_t cancel_window_ms;     /* B, then B again within this, cancels */
    uint32_t backlight_idle_ms;    /* no key for this long during an install: the screens go dark */
    int battery_low_level;         /* PTMU level (0-5) at or under which, without the charger, the player is warned */
    uint64_t sd_spare_bytes;       /* room left on the card past the title */
} HfUiTuning;

/* ---- what the app found (the app's DUMP_* and XX_* have these values) ---- */

enum { HF_DUMP_NONE = 0, HF_DUMP_FOUND = 1, HF_DUMP_ENCRYPTED = 2, HF_DUMP_OTHER_REGION = 3 };
enum { HF_XXD_NONE = 0, HF_XXD_FOUND = 1, HF_XXD_ENCRYPTED = 2, HF_XXD_OTHER_VERSION = 3 };

/* The start's look for the latest release (a thread of its own). */
typedef enum {
    HF_CHECK_RUNNING = 0,   /* not answered yet */
    HF_CHECK_DONE,          /* `latest` holds the latest release's tag */
    HF_CHECK_FAILED,        /* no answer (no network, the API refused) */
    HF_CHECK_NO_RELEASE     /* the repository has no release yet */
} HfCheck;

/* ---- the home screen ---- */

/* The game data title as the home screen needs it. */
enum {
    HF_GAME_OK = 0,
    HF_GAME_UPDATE,    /* to be made (the old single title has none, or the dump is another printing): the title plays */
    HF_GAME_MISSING    /* the split title without its game data: it cannot start */
};

/* What a button does; the big one (`primary`) is one of the first four. */
typedef enum { HF_DO_NONE = 0, HF_DO_PLAY, HF_DO_UPDATE, HF_DO_INSTALL, HF_DO_SETUP, HF_DO_ORIGINAL, HF_DO_MORE } HfDo;

typedef struct {
    int title_installed;      /* the edition's title is on the card */
    int installed_complete;   /* its record says the last install finished */
    const char *installed;    /* its version ("" unknown) */
    HfCheck check;
    const char *latest;       /* the latest release's tag, when check is HF_CHECK_DONE */
    int dump;                 /* HF_DUMP_* */
    int game;                 /* HF_GAME_*: the game data title's state */
    int xx_came;              /* MH XX can be built into the installed version, the latest (hf_xx_came) */
    int app_newer;            /* the latest release carries this form's launcher (CIA or .3dsx), newer than this one */
} HfHomeIn;

typedef struct {
    HfText state;             /* the state line */
    int new_version;          /* the state line takes the latest version after it (HT_HOME_NEW_VERSION) */
    int detail;               /* an HfText under it (what to do next), -1 for none */
    int tone;                 /* HF_TONE_* (uiview.h): the state line's colour */
    HfDo primary;             /* the big button; HF_DO_UPDATE's label takes the latest version (HT_BTN_UPDATE_TO) */
    int can_play;             /* the edition's title is installed: Play is offered */
} HfHome;

/* The home screen's state line and big button:
 * - not installed, a usable dump: "not installed yet", Install;
 * - not installed, no usable dump: why (none, encrypted, another region), Set up;
 * - installed, a cut install: "did not finish", Update;
 * - installed, a newer release: "a new version is out: X", Update to X;
 * - installed, the latest, MH XX copied since (xx_came): "MH XX found", Update;
 * - installed, the latest, the release's launcher newer than this one: "a new launcher is out", Update;
 * - installed, the latest: "up to date", Play;
 * - installed, the check running or failed or no release: that, Play.
 * An installed title whose update needs a dump the card lacks still offers Update: its failure explains. */
void hf_home(const HfHomeIn *in, HfHome *out);

/* ---- the first-run guide ---- */

typedef enum {
    HF_SETUP_DUMP = 0,    /* copy MH4U with GodMode9 */
    HF_SETUP_DECRYPT,     /* the copy found is encrypted: make a decrypted one */
    HF_SETUP_XX,          /* optional: copy MH XX the same way (Skip) */
    HF_SETUP_INSTALL,     /* install */
    HF_SETUP_SAVE,        /* start the game once, then copy the MH4U save into it */
    HF_SETUP_DONE
} HfSetupStep;

typedef struct {
    int dump;                 /* HF_DUMP_* */
    int xx;                   /* HF_XXD_* */
    int xx_skipped;           /* the player chose to go on without MH XX */
    int title_installed;
    int save_pending;         /* installed.json: the save copy was not done nor declined */
    int game_missing;         /* the title is split and its game data is not installed: install again */
} HfSetupIn;

HfSetupStep hf_setup_step(const HfSetupIn *in);

/* ---- the install's single progress bar ---- */

typedef struct {
    uint32_t expect_ms[HF_STAGES];   /* the plan's expected time of each step */
    HfStage stage;                   /* the step now running */
    uint64_t stage_began_ms;
    uint32_t stage_frac;             /* its progress, 0..65536 */
    uint32_t base_permille;          /* where the bar stood when the plan was made */
    HfStage plan_from;               /* the plan's first step */
    uint32_t shown;                  /* the bar, permille: never goes down */
    uint32_t cap_permille;           /* HfUiTuning.finish_cap_permille */
} HfProgress;

/* A new bar at 0 for steps expected to take `expect_ms` (hf_timings_expect), starting with `stage`. */
void hf_progress_start(HfProgress *p, const uint32_t expect_ms[HF_STAGES], HfStage stage, uint32_t cap_permille,
                       uint64_t now_ms);
/* The step now running and its progress (`total` 0: a step with no progress of its own, driven by time against its
 * expected duration and held below its end). A later stage than the current one starts it. */
void hf_progress_update(HfProgress *p, HfStage stage, uint64_t done, uint64_t total, uint64_t now_ms);
/* The work left changed (a fallback route repeats the install with a hash pass, a size became known): the bar stays
 * where it is and the rest of it is spread over the new expected times from `stage` on. */
void hf_progress_replan(HfProgress *p, HfStage stage, const uint32_t expect_ms[HF_STAGES], uint64_t now_ms);
/* The bar (0..1000), never lower than before; 1000 only after hf_progress_end. */
unsigned hf_progress_permille(const HfProgress *p);
void hf_progress_end(HfProgress *p);
/* Seconds left: the running step's from its measured rate once it has moved (else expected), plus the later steps'
 * expected times. 0 when done. */
uint32_t hf_progress_eta_s(const HfProgress *p, uint64_t now_ms);
/* The step a phase text belongs to (HT_PHASE_*), -1 for a text that is no install phase (the release's lookup). */
int hf_stage_of_phase(HfText phase);
/* "45 s", "12 min", "1 h 05 min" (rounded up to the minute past 60 s): no words to translate. */
size_t hf_duration_text(uint32_t seconds, char *out, size_t cap);

/* ---- the last install's times: sdmc:/3ds/heavenfall/<slug>/timings.json (hf_path_timings) ---- */

typedef struct {
    uint64_t ms[HF_STAGES];      /* how long each step took (0: not measured) */
    uint64_t bytes[HF_STAGES];   /* over how many bytes (the set's download, the title's write; finish: 0) */
    uint64_t game_ms;            /* the game data title's install (its own AM finish too), 0: not measured */
    uint64_t game_bytes;         /* over how many bytes (the game data's RomFS) */
} HfTimings;

int hf_timings_format(const HfTimings *t, char *out, size_t cap);   /* the length, -1 when it does not fit */
int hf_timings_parse(const char *json, size_t len, HfTimings *out); /* 0, or -1 for anything else */
/* Each step's expected time for these sizes (download: the set's bytes; install: the title's bytes): at the last
 * install's rates when it measured them (`last` may be NULL), else the tuning's. Never 0. */
void hf_timings_expect(const HfTimings *last, const HfUiTuning *tu, const uint64_t bytes[HF_STAGES],
                       uint32_t expect_ms[HF_STAGES]);
/* The same for an update with the game data title as well: `bytes[HF_STAGE_INSTALL]` is the
 * mod title's, `game_bytes` the game data's (0: not installed this time). Each title has its own rate (the last
 * install's, else the tuning's); the game data's time holds its own finish, so "finishing" is the mod's alone. */
void hf_timings_expect_titles(const HfTimings *last, const HfUiTuning *tu, const uint64_t bytes[HF_STAGES],
                             uint64_t game_bytes, uint32_t expect_ms[HF_STAGES]);

/* ---- B to cancel, the screens' backlight, the battery ---- */

typedef struct {
    int armed;
    uint64_t armed_ms;
} HfCancel;

/* B was pressed at `now_ms`: 1 when this press cancels (a second one within the window), 0 when it only arms it. */
int hf_cancel_press(HfCancel *c, uint64_t now_ms, uint32_t window_ms);
/* 1 while "press B again to cancel" shows. */
int hf_cancel_armed(const HfCancel *c, uint64_t now_ms, uint32_t window_ms);

/* 1 when the screens go dark: an install runs and no key came for `idle_ms`. (A key while they are dark only wakes
 * them: the drawing thread does not pass it on.) */
int hf_backlight_should_dim(uint64_t last_input_ms, uint64_t now_ms, uint32_t idle_ms);

/* 1 when the player is warned before an install: the battery level (0-5; -1 unknown) at or under `low_level` and the
 * charger not plugged in. */
int hf_battery_warn(int level, int adapter, int low_level);

/* ---- the resume file: sdmc:/3ds/heavenfall/<slug>/resume.json (hf_path_resume) ----
 * The app updated itself and the mod's update waits for the new app: it writes the version it installed and leaves.
 * At the next start the app deletes the file first, then goes on with the mod's update only when it is that version
 * (a failed self-update never loops). */

int hf_resume_format(const char *target_version, char *out, size_t cap);   /* the length, -1 */
int hf_resume_parse(const char *json, size_t len, char *target, size_t cap);   /* 0, -1 */
int hf_resume_go(const char *target_version, const char *app_version);    /* 1: go on with the update */

/* ---- room on the card ---- */

/* The free bytes an install of `title_bytes` needs: the title, 1 % for the file system and the spare room. */
uint64_t hf_room_needed(uint64_t title_bytes, uint64_t spare);
/* 0 when it fits (or free_bytes is 0: unknown), else the MB missing, rounded up. */
uint32_t hf_room_missing_mb(uint64_t free_bytes, uint64_t title_bytes, uint64_t spare);

/* ---- why an update stopped, and what to do ---- */

/* The check open after the game data title's install failed (the app logs FS's answer). */
#define HF_E_GAME_CHECK (-60)
/* The edition's save could not be backed up to the card before an install that removes its title: nothing done. */
#define HF_E_SAVE_BACKUP (-61)

typedef enum {
    HF_FAIL_CANCEL = 0, HF_FAIL_ROOM, HF_FAIL_NET, HF_FAIL_NO_RELEASE, HF_FAIL_NEEDS_APP, HF_FAIL_NO_SET,
    HF_FAIL_DUMP_MISSING, HF_FAIL_DUMP_ENCRYPTED, HF_FAIL_DUMP, HF_FAIL_MEMORY, HF_FAIL_SD, HF_FAIL_SET, HF_FAIL_SYSTEM,   /* AM (not HF_FAIL_AM: settitle.h has that name) */
    HF_FAIL_GAME_CHECK,   /* the game data was installed, but the system cannot open it as the game will */
    HF_FAIL_SAVE_BACKUP,  /* the save not backed up before the install: nothing was changed */
    HF_FAIL_OTHER
} HfFailKind;

/* A TITLE_* (core/install/title/c/title_io.h) or HF_E_* (hfnet.h, settitle.h) code, and AM's result when it answered
 * (0 none), as one of the kinds above (the old app_update.c failure_reason, plus cancel and room). */
HfFailKind hf_fail_kind(int rc, uint32_t am_result);

typedef struct {
    HfText what;     /* what happened, a sentence */
    int todo;        /* an HfText: what to do (may take a value, hf_text_fill), -1 for none */
    int show_code;   /* the code goes in small under it (for the log's reader) */
} HfAdvice;

void hf_failure_advice(HfFailKind kind, HfAdvice *out);

/* The line a stopped update adds under its advice (an HfText, -1 none): HT_OLD_REMOVED when the install had removed
 * the installed title before AM's import (AM imports over none) and stopped after it, a cancel too; else
 * HT_NOTHING_INSTALLED when a title was installed and stays (not on a cancel, whose sentence says it). */
int hf_stop_note(HfFailKind kind, int had_title, int old_removed);

/* `text` with its "{}" replaced by `value` (only the first; a text without one is copied). The length written. */
size_t hf_text_fill(const char *text, const char *value, char *out, size_t cap);

/* ---- the release's notes ---- */

/* GitHub markdown (the release's text) as plain lines for the screen, '\n' between: headings without their #, list
 * items as "- ", bold, italic and code marks dropped, "[text](url)" as its text, bare URLs and images dropped, runs of
 * blank lines as one, no blank line first or last; letters past U+00FF dropped except the dashes and quotes, which
 * become ASCII. The number of lines. */
int hf_notes_plain(const char *markdown, char *out, size_t cap);

#endif
