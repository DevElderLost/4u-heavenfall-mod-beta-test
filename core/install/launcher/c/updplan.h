/* What one run of "update" does, decided from the latest release and what is installed (portable C99, pure): the app
 * first, then the mod. A patch set whose format version the app does not know is not applied: the answer is "update the
 * app" (when the release carries a newer app), else an error. The mod is the XX set (MH XX's Layered Gear, made from
 * the player's XX dump too) whenever the right XX dump is on the card and the release has the region's XX set, else the
 * plain set; the title is rebuilt when that changes, the version alone unchanged. */
#ifndef HF_UPDPLAN_H
#define HF_UPDPLAN_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    const char *release_tag;   /* the latest release's tag */
    const char *app_version;   /* the running app's version */
    const char *mod_version;   /* the installed mod's version; NULL when no mod is installed (a first install) */
    int mod_incomplete;        /* the mod's marker says an install was cut: rebuild whatever the version */
    int app_in_release;        /* the release carries the app file of this app's form (CIA or .3dsx) */
    int set_in_release;        /* ... and the patch set of the region */
    unsigned set_format;       /* the set's format version (hf_read_set_format); 0: not read yet */
    unsigned supported_format; /* the highest format the app applies */
    /* MH XX (all 0 for a player without it) */
    int mod_xx;                /* the installed title was built from the XX set (installed.json's "xx") */
    int xx_dump;               /* a decrypted MH XX dump is on the card */
    int xx_set_in_release;     /* the release carries the region's XX set */
    int xx_set_matches;        /* its header names the dump's revision (hf_set_names_game); the app reads it first */
    unsigned xx_set_format;    /* the XX set's format version, from the same header */
    int xx_no_room;            /* the installed version's XX set did not fit the console's memory (installed.json) */
    /* the split title */
    int game_stale;            /* the game data title is missing, cut or made from another dump (hf_game_stale) */
    int mod_layout;            /* the installed record's layout (hf_installed_parse); 0 or 2: split, 1: the old single title */
    int xx_tried;              /* the installed version was built plain after this XX dump's files were found to differ
                                  from its XX set (installed.json: "xx" false, "xx_dump" this dump) */
    int reinstall;             /* the player asked for it (More, Reinstall): the mod's title again whatever the version */
    const char *app_tag;       /* the release the app's own update comes from when not the mod's (a probe's test
                                  launcher: its CIA's version); NULL: release_tag */
} HfPlanIn;

/* Run in the order APP, GAME, MOD (the numbers are only names). */
typedef enum { HF_STEP_APP = 1, HF_STEP_MOD = 2, HF_STEP_GAME = 3 } HfStep;

typedef enum {
    HF_PLAN_UP_TO_DATE = 0,   /* nothing to do */
    HF_PLAN_STEPS,            /* do steps[0..count-1] in order */
    HF_PLAN_BAD_TAG,          /* the release's tag or the app's version is not a version */
    HF_PLAN_NO_SET,           /* the mod needs updating and the release has no patch set of this region */
    HF_PLAN_NEEDS_APP         /* the set's format is newer than the app and the release has no newer app for it */
} HfPlanStatus;

/* Which set the mod is made from, and why. */
typedef enum {
    HF_XX_NO_DUMP = 0,        /* no MH XX dump on the card: the plain set */
    HF_XX_USED,               /* the XX set: the dump is the revision it names */
    HF_XX_NOT_IN_RELEASE,     /* the release has no XX set of this region: the plain set */
    HF_XX_OTHER_VERSION,      /* the dump is another revision than the XX set's: the plain set */
    HF_XX_NO_ROOM             /* this version's XX set did not fit the console's memory: the plain set */
} HfXxWhy;

typedef struct {
    HfPlanStatus status;
    HfStep steps[3];
    int count;
    int mod_after_restart;    /* the mod step is not in steps: it waits for the new app (a set the app cannot read) */
    int use_xx;               /* the mod is (or stays) the XX set's */
    HfXxWhy xx_why;
} HfPlan;

void hf_plan(const HfPlanIn *in, HfPlan *out);

/* MH XX came after the installed title was built: 1 when its dump is on the card, the release has the region's XX set,
 * the title was built without it, and for the installed version neither its XX set ran out of memory nor this dump's
 * files were found to differ. An update then builds it in (or compares its files once: another printing). The home
 * screen offers it with the same rule. */
int hf_xx_came(const HfPlanIn *in);

/* The app's own update (HF_STEP_APP) failed: 1 when the plan's titles still go on with this app (they do not wait for
 * the new one), so a self-update AM keeps refusing never stops the mod's updates; the app's step is tried again at the
 * next update. */
int hf_plan_on_without_app(const HfPlan *plan);

/* The XX set ran out of memory on this console: 1 when the plan can take the release's plain set instead (in the
 * release, of a format the app reads; plan->use_xx cleared, xx_why HF_XX_NO_ROOM), 0 when it cannot. The app records
 * it (installed.json "xx_no_room") so the same version does not try its XX set again. */
int hf_plan_drop_xx(const HfPlanIn *in, HfPlan *plan);

/* The bytes of a set's beginning the app reads to check an XX set against the player's XX dump (hf_read_set_head):
 * format 2's header holds the second game's RomFS superblock hash within them. */
#define HF_SET_HEAD_MAX 0x200u

/* 1 when the set's first `len` bytes are a header of format 2 or later that holds this RomFS superblock hash (the
 * dump's NCCH header at 0x1E0, dump_romfs_hash): the set was made from that revision of the second game. 0 otherwise
 * (another revision, a plain set of format 1, not a set). */
int hf_set_names_game(const uint8_t *head, size_t len, const uint8_t romfs_hash[32]);

#endif
