/* The title made from a release's patch set (portable C99, no libctru): the set
 * applied to the player's dump straight into the title builder (build.h), with no copy of the mod on the card. The set's
 * files become the builder's Pack in memory: the executable and the exheader are made into memory, every RomFS file is
 * made by the applier as the title streams (a generated piece, stream.h). When the set's title-build slot (digest.h) was
 * made for these inputs, it gives the ARCs' sizes, the content hash and the mod's level-2 hashes: the title is written
 * in one pass, nothing hashed first, the mod's bytes checked against the slot as they go. Also: the order in which the
 * app tries AM's routes. tests/install/launcher/test_set_title.py runs it on the PC and compares the CIA with the
 * Python build byte for byte. */
#ifndef HF_SETTITLE_H
#define HF_SETTITLE_H

#include "build.h"
#include "launcher.h"
#include "patchset.h"

#define HF_SLOT_EMPTY 1   /* hf_set_title_slot_rc: the set carries no title-build data */

/* Which title is built: the old single title, the game data (the dump's RomFS as an
 * add-on content title, installed once per dump) or the edition's title with the mod's files only. */
typedef enum { HF_TITLE_FULL = 0, HF_TITLE_GAME, HF_TITLE_MOD } HfTitleKind;

typedef struct {
    HfTitleKind kind;            /* which title (HF_TITLE_FULL: the old single title) */
    uint64_t title_id;           /* the title of that kind for the dump's region (hf_game_title_id for the game data) */
    const uint8_t *smdh;         /* PACK_SMDH_SIZE bytes: the title's (launcher.h, hf_smdh_make); unused by the game
                                  * data (NULL is fine) */
    const uint8_t *certs;        /* PACK_CERTS_SIZE bytes: the CIA's certificate chain */
    uint16_t tmd_version;        /* the TMD's title version (hf_tmd_version of the release) */
    int use_slot;                /* take the slot's data when it was made for these inputs */
    int check_set;               /* hash the whole set first (not needed right after a download checked its digest) */
    uint64_t keep_budget;        /* patchset_keep_budget; 0: the set's default */
    TitleProgress progress;      /* while the ARCs are measured (without the slot); nonzero cancels */
    void *progress_ctx;
    const HfLog *log;            /* each step of the open and its result, when given (hf_install_title gives its own) */
    uint64_t (*now_ms)(void);
    /* MH XX's opened dump (dump_open with the set's read callback), or NULL: bound when the set is made with it (format
     * 2, patchset_bind_second_dump), unused by a set of MH4U alone. It must outlive the title. */
    const Dump *xx;
} HfSetTitleIn;

typedef struct HfSetTitle HfSetTitle;

/* Opens the set of `set_size` bytes at `set_handle` for the opened dump `d` (`read` serves both), makes the executable
 * and the exheader, sizes every file (from the slot, or by measuring the ARCs) and opens the title's build over them:
 * HF_TITLE_FULL the game with the mod merged (PLAN_BASE, slot format 2), HF_TITLE_MOD the mod's files alone (PLAN_MOD,
 * slot format 3). HF_TITLE_GAME makes nothing of the set: the game data is the dump's RomFS (PLAN_GAME); the set is
 * read only for its slot's game entry (`set_handle` may be NULL: no slot), and a dump the slot does not name is hashed
 * by the install's hash pass. A slot made for other inputs is set aside (hf_set_title_slot_rc) and the title is built
 * without it. The dump must outlive the title. TITLE_E_GAME for a set of the other region or another game, or a set
 * made with MH XX given no MH XX dump (in->xx) or another one (another revision, a file missing or of another size);
 * TITLE_E_FORMAT for a damaged set; TITLE_E_HASH when the set's executable or exheader comes out wrong (another dump),
 * or (the game data) when the dump's RomFS is not its NCCH header's. */
int hf_set_title_open(HfSetTitle **out, TitleRead read, void *read_ctx, void *set_handle, uint64_t set_size, Dump *d,
                      const HfSetTitleIn *in);
TitleBuild *hf_set_title_build(HfSetTitle *t);
/* 1 when the build takes the slot's data: no hash pass, the mod's bytes checked as they stream. */
int hf_set_title_slot(const HfSetTitle *t);
/* TITLE_OK when used; HF_SLOT_EMPTY; TITLE_E_FORMAT (not build data, or not of this kind's format); TITLE_E_HASH (made
 * for other inputs; the game data: no entry for this dump); TITLE_E_ARG when not asked. */
int hf_set_title_slot_rc(const HfSetTitle *t);
size_t hf_set_title_file_count(const HfSetTitle *t);    /* the mod's RomFS files (the game data: 0) */
uint64_t hf_set_title_mod_bytes(const HfSetTitle *t);   /* their bytes */
void hf_set_title_close(HfSetTitle *t);

/* ---- AM's routes, tried in order until one installs the title ---- */

typedef enum {
    HF_ROUTE_NONE = 0,
    HF_ROUTE_PARTS_SLOT,     /* AM piece by piece, the TMD first with the slot's hash: one pass */
    HF_ROUTE_CIA_SLOT,       /* a CIA into AM, the TMD with the slot's hash: one pass */
    HF_ROUTE_PARTS_HASHED,   /* the content hashed by a pass of its own, then AM piece by piece */
    HF_ROUTE_CIA_HASHED,     /* the content hashed by a pass of its own, then a CIA into AM */
    HF_ROUTE_COUNT
} HfRoute;

typedef enum {
    HF_FAIL_SLOT,            /* the slot is not this title's (refused, or the mod's bytes differ from it) */
    HF_FAIL_AM,              /* AM refused before the content was whole: its begin, the TMD, a write */
    HF_FAIL_AM_FINISH,       /* AM refused the finished content or its commit */
    HF_FAIL_STOP             /* a cancel, the card, the dump, memory: no other route helps */
} HfFail;

typedef struct {
    int slot, parts, cia, stop;
    unsigned tried;
} HfRoutes;

/* The routes for a build that can (slot_usable) or cannot take the slot's data. */
void hf_routes_init(HfRoutes *r, int slot_usable);
/* The next route to try, HF_ROUTE_NONE when none is left: AM piece by piece first, then the CIA; the slot's hash
 * first, then the content hashed. A route is tried once. */
HfRoute hf_routes_next(HfRoutes *r);
/* What a failed attempt rules out: SLOT the slot; AM the route's AM form; AM_FINISH the slot when it was used (AM
 * checks the content against the TMD), else the AM form; STOP everything. */
void hf_routes_failed(HfRoutes *r, HfRoute route, HfFail why);
/* How an attempt's builder result (a TITLE_* code, TITLE_OK when the failure was AM's) and AM's step tell why it
 * failed: am_step 0 no AM failure, 1 AM before the content was whole, 2 AM at the finish or commit. */
HfFail hf_route_failure(HfRoute route, int rc, int am_step);
int hf_route_uses_slot(HfRoute r);
int hf_route_is_parts(HfRoute r);
const char *hf_route_name(HfRoute r);

/* ---- the install: every route in order until one installs the title ---- */

#define HF_E_AM_WRITE (-42)   /* HfAm's write refused: AM's answer, not the card's (after hfnet.h's codes) */

/* AM as the install sees it: the app's wraps libctru (ctr_title.c), the PC tests' write files and check the content's
 * hash against the TMD as AM does. Each call returns 0 or AM's nonzero result; `write` goes into the open import
 * (content 0 or the CIA) and returns 0 or HF_E_AM_WRITE. */
typedef struct {
    int32_t (*parts_begin)(void *ctx, const TitleBuild *tb);   /* certificates, ticket, the title's import */
    int32_t (*parts_tmd)(void *ctx, const uint8_t *tmd, size_t len);
    int32_t (*parts_content)(void *ctx);                       /* content 0's import */
    int32_t (*parts_finish)(void *ctx);                        /* content 0's finish, the title's finish and commit */
    void (*parts_abort)(void *ctx);
    int32_t (*cia_begin)(void *ctx);
    int32_t (*cia_finish)(void *ctx);                          /* AM's finish: its checks, then the commit */
    void (*cia_cancel)(void *ctx);
    /* The title as installed now taken away, as FBI does before every install over one (its content, its ticket and
     * its save, which the app backs up before and puts back after): AM refuses to import over an installed title
     * (0xC8E083FC, "already exists", on the console for both
     * routes, even at a higher version). Called once per install, right before AM's first import: after the set opened and the title was
     * prepared, so a failure before leaves the player's title alone. 0 when there was none or it is gone; AM's
     * answer otherwise (the install stops). May be NULL. */
    int32_t (*remove_old)(void *ctx);
    TitleWrite write;
    void *ctx;
} HfAm;

typedef struct {
    HfSetTitleIn in;             /* in.use_slot: whether the slot's routes may be tried */
    TitleRead read;
    void *read_ctx;
    void *set_handle;
    uint64_t set_size;
    Dump *dump;
    HfAm am;
    /* One pass of the build on the caller's threads (title_build_begin, the stream's stages, title_build_end). */
    int (*run)(void *ctx, TitleBuild *tb, TitlePass pass, const TitleOut *out);
    void *run_ctx;
    void (*phase)(void *ctx, HfText name);         /* the phase the screen shows (a text id); may be NULL */
    void (*notice)(void *ctx, HfText text);       /* a fallback, said on the screen; may be NULL */
    /* Before AM is asked: whether the card has room for `bytes` going into AM (the content, or the CIA). A nonzero
     * return stops the install with that code, nothing begun. May be NULL. */
    int (*room)(void *ctx, uint64_t bytes);
    void *ui_ctx;
    const HfLog *log;                              /* every attempt, AM's answers, each phase with its MB/s; may be NULL */
    uint64_t (*now_ms)(void);
} HfInstallJob;

typedef struct {
    HfRoute route;               /* the route that installed the title, HF_ROUTE_NONE when none did */
    int rc;                      /* TITLE_OK, or the last attempt's code (HF_E_AM_WRITE / TITLE_E_IO for AM's) */
    int am_step;                 /* of the last failure: hf_route_failure's */
    int32_t am;                  /* AM's last nonzero answer */
    int attempts;
    int removed;                 /* HfAm.remove_old was asked (once per install) */
} HfInstallResult;

/* Builds and installs the title from the set, trying the routes in hf_routes_next's order: AM piece by piece with the
 * slot's hash, the CIA with it, then each after a hash pass of its own. Nothing is installed by a route that fails (its
 * import is aborted), so the next starts clean. Returns res->rc. */
int hf_install_title(const HfInstallJob *job, HfInstallResult *res);

#endif
