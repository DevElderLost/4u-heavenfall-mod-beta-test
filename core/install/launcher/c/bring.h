/* Bring on the console: the main edition's game
 * plays on a whole MH4U file set in Heavenfall's own extdata, and the launcher copies a hunter into it from the
 * original game, as the PC program's core/save/bring.py does:
 *
 * * a slot: MH4U's `userN` (the original game's save archive) and `cardN` (MH4U's extdata) become Heavenfall's, byte
 *   for byte; when MH4U's extdata holds Heavenfall Beta's sidecars of the slot (hf_save_files.h's names) the files
 *   are decrypted, joined with them (bring_join.c, over core/save/c/extras.c) and encrypted again;
 * * the shared files (`system`, `cardbox`, `quest1-5`, `otomo1`) only when asked.
 *
 * Heavenfall's extdata is never made here (the game makes it at its first start); MH4U's files are never written; a
 * slot holding a Heavenfall hunter is replaced only with HF_BRING_REPLACE (the player's yes); every file replaced is
 * copied into the backup before the first write, and a write that fails puts the old files back from there.
 *
 * The decisions are portable C over HfSaveIo; app_saves.c gives it the console's archives, the host tests a folder
 * each. Every file is read and written whole (the largest is a card file, 0x78C00 bytes). */
#ifndef HF_BRING_H
#define HF_BRING_H

#include <stddef.h>
#include <stdint.h>

#include "hf_save_files.h"
#include "savecrypt.h"

/* Where a file is. */
enum {
    HF_BRING_MH4U_SAVE,      /* the original game's save archive (read only) */
    HF_BRING_MH4U_EXTDATA,   /* MH4U's extdata (read only) */
    HF_BRING_HEAVENFALL,     /* Heavenfall's own extdata */
    HF_BRING_BACKUP,         /* this Bring's backup folder on the card */
    HF_BRING_STATE,          /* the launcher's own folder on the card (.../<slug>/saves): the journal and the moves */
    HF_BRING_CONTAINERS
};

#define HF_BRING_MAX_FILE 0x80000u   /* the biggest file read (a card file is 0x78C00) */
#define HF_BRING_NAME 16             /* a file name's room, its terminator included */
#define HF_BRING_STAMP 18            /* a backup set's name: "YYYY-MM-DD_HHMMSS" and its terminator */
#define HF_BRING_JOURNAL "bring_journal"   /* in HF_BRING_STATE: a Bring that has begun to write and has not ended */
#define HF_BRING_MOVES "bring_moves"       /* in HF_BRING_STATE: the earlier hunters already moved */

typedef struct {
    void *ctx;
    /* 1 when the container is there (Heavenfall's extdata: the game made it), else 0. */
    int (*has)(void *ctx, int container);
    /* A file's size: 0 found, 1 missing (not in its container, or the container is not there), -1 failed. */
    int (*size)(void *ctx, int container, const char *name, uint32_t *size);
    /* The whole file, exactly `size` bytes: 0 done. */
    int (*read)(void *ctx, int container, const char *name, uint8_t *buf, uint32_t size);
    /* The whole file replaced by `size` bytes (HF_BRING_HEAVENFALL or HF_BRING_BACKUP only): 0 done. */
    int (*write)(void *ctx, int container, const char *name, const uint8_t *buf, uint32_t size);
    /* The file deleted (HF_BRING_HEAVENFALL: a file a failed Bring made where none was; HF_BRING_STATE: its journal):
     * 0 done or missing. */
    int (*remove)(void *ctx, int container, const char *name);
    /* The backup set's folder name under saves/ (the stamp) and the console's name ("EUR", "USA"); the journal and the
     * moves' record carry them. NULL: none. */
    const char *stamp;
    const char *console;
} HfSaveIo;

enum {
    HF_BRING_OK = 0,
    HF_BRING_E_ARG = -1,         /* a slot not 1-3, a null pointer */
    HF_BRING_E_NO_WORLD = -2,    /* Heavenfall's extdata is not there: start Heavenfall once first */
    HF_BRING_E_NO_HUNTER = -3,   /* the original game has no `userN` for the slot */
    HF_BRING_E_TAKEN = -4,       /* Heavenfall's slot holds a hunter (or a file that does not read): ask first */
    HF_BRING_E_CORRUPT = -5,     /* with Beta sidecars, MH4U's `userN` or `cardN` does not decrypt */
    HF_BRING_E_NO_JOIN = -6,     /* with Beta sidecars, a build without the extras core: bring it with the PC program */
    HF_BRING_E_JOIN = -7,        /* the extras core refused the files (a wrong size) */
    HF_BRING_E_READ = -8,        /* a file to bring or to back up did not read */
    HF_BRING_E_BACKUP = -9,      /* the backup failed: nothing was written */
    HF_BRING_E_WRITE = -10,      /* a write failed: rolled_back says whether the old files are back */
    HF_BRING_E_MEMORY = -11,
    HF_BRING_E_NOTHING = -12     /* shared files: MH4U has none to bring */
};

#define HF_BRING_REPLACE 1u      /* the player said yes to replacing the slot's hunter */

typedef struct {
    int code;                    /* HF_BRING_OK or HF_BRING_E_* */
    int joined;                  /* Beta sidecars were found and joined (else the files were copied as they are) */
    uint32_t left_over;          /* what found no room (it stays in the Beta save) */
    int backed_up;               /* the files copied into the backup */
    int written;                 /* the files written into Heavenfall's extdata */
    int rolled_back;             /* after HF_BRING_E_WRITE: 1 every old file is back, 0 not (the backup holds them) */
    char failed[HF_BRING_NAME];  /* the file whose step failed, "" none */
} HfBringResult;

/* What a slot holds on one side, for the page that chooses it. */
typedef struct {
    int present;                 /* the `userN` file exists */
    int readable;                /* it decrypts (else the game calls it corrupt) */
    int hunter;                  /* it holds a character */
    char name[40];               /* the hunter's name (UTF-8; the console converts it for its font) */
    uint32_t hr;                 /* the hunter rank */
} HfBringSide;

typedef struct {
    HfBringSide mh4u, heavenfall;
    int sidecars;                /* MH4U's extdata holds Beta sidecars of the slot */
} HfBringSlot;

/* Taken: a hunter, or a file that does not read (a Bring would destroy it), as bring.py's Side.taken. */
static inline int hf_bring_taken(const HfBringSide *s) { return s->present && (!s->readable || s->hunter); }

/* The side of `container`'s `userN` (HF_BRING_MH4U_SAVE or HF_BRING_HEAVENFALL); 0, or HF_BRING_E_*. */
int hf_bring_side(const HfSaveIo *io, const HfBlowfish *bf, int container, int slot, HfBringSide *out);
/* The slot as the page shows it. 0, or HF_BRING_E_*. */
int hf_bring_slot_info(const HfSaveIo *io, const HfBlowfish *bf, int slot, HfBringSlot *out);

/* MH4U's hunter of `slot` into Heavenfall's extdata (bring.py bring_slot, without making the world). `flags`:
 * HF_BRING_REPLACE. `seed`: the XOR seeds of a joined user file (low 16 bits) and card file (high 16 bits). */
int hf_bring_slot(const HfSaveIo *io, const HfBlowfish *bf, int slot, unsigned flags, uint32_t seed,
                  HfBringResult *out);
/* `system` (the save archive) and `cardbox`, `quest1-5`, `otomo1` (MH4U's extdata) into Heavenfall's extdata, each
 * that MH4U has (bring.py bring_common). Hunters are not touched. */
int hf_bring_common(const HfSaveIo *io, HfBringResult *out);

/* The earlier system's hunters (bring.py migrate_legacy): its game patch kept Heavenfall's hunters as `hfuserN` /
 * `hfcardN` in MH4U's extdata on the card. Each slot with such a hunter and no `userN` in Heavenfall's extdata is moved
 * there byte for byte (`hfcardN`, else MH4U's `cardN`); a taken slot is never overwritten and MH4U's files are never
 * changed or deleted. Heavenfall's extdata missing: nothing moves (HF_BRING_E_NO_WORLD, only when there was a hunter
 * to move). The files it replaces are copied into the backup first; a write that fails is rolled back. */
typedef struct {
    HfBringResult result;        /* HF_BRING_OK (also with nothing to move), HF_BRING_E_NO_WORLD, ... */
    int moved[HF_SAVE_SLOTS];    /* slot n-1 got its hunter: 1 from `hfcardN`, 2 from MH4U's `cardN`, 3 with no card */
    int count;                   /* how many slots moved */
    int unrecorded;              /* the record of the moves could not be written (the move itself is made) */
} HfBringLegacy;
enum { HF_LEGACY_HF_CARD = 1, HF_LEGACY_MH4U_CARD = 2, HF_LEGACY_NO_CARD = 3 };
int hf_bring_legacy(const HfSaveIo *io, HfBringLegacy *out);
/* The slots (1-3) of `due` the move would take: an earlier hunter there that was not moved before (the record of
 * HF_BRING_MOVES holds its console, slot and hash: after the game's "delete all" the same file is not moved again, a
 * different one is, as the PC's save_moves.json). Returns how many. */
int hf_bring_legacy_due(const HfSaveIo *io, int due[HF_SAVE_SLOTS]);

/* A Bring that was cut: before its first write into Heavenfall's
 * extdata (the backup of what it replaces already made) it writes HF_BRING_JOURNAL (the backup set, and each file with
 * the size and hash of what it will write), and removes it after its last write (or its rollback). A journal found at
 * the next start means a cut: each file still holding what the Bring wrote (or half written: a user or card file that
 * does not decrypt) is put back from the backup set; a file with any other content (the game saved since) is left. A
 * journal whose files all hold what the Bring wrote is a Bring that ended: only removed. */
typedef struct {
    int code;                    /* HF_BRING_OK, HF_BRING_E_READ / E_WRITE (the journal stays), HF_BRING_E_MEMORY */
    int found;                   /* a journal was there */
    int completed;               /* the Bring had written everything: nothing put back */
    int restored;                /* the files put back (or deleted, when the Bring made them) */
    int kept;                    /* the files left as they are: the game saved them since, or the backup set is gone */
    char failed[HF_BRING_NAME];
} HfBringRecovery;
/* 1 and the backup set's name when a journal is there (an unreadable or half-written one is removed: nothing was written
 * before it was whole), else 0. */
int hf_bring_journal_stamp(const HfSaveIo *io, char stamp[HF_BRING_STAMP]);
/* The journal's work, with HF_BRING_BACKUP pointing at the set hf_bring_journal_stamp gave. */
int hf_bring_recover(const HfSaveIo *io, const HfBlowfish *bf, HfBringRecovery *out);

/* bring_join.c: 1 when this build has the save core (core/save/c: extras.c and heav.c), else 0. */
int hf_bring_join_available(void);
/* The plain `user` (and `card`, may be NULL) of `slot` joined in place with the Beta sidecars (each may be NULL; the
 * images are changed: pass copies), as core/save/bring.py's join: core/save/extras.py join_files (each kind's image
 * picked by the hunter's identity, the slot and the file's tag), then what an older Heavenfall left, `heav`
 * (hfheavN, may be NULL; not changed: core/save/heav.py join, the file's hunter only; one of another size is not
 * read). *left_over gets the entries that found no room. 0, or HF_BRING_E_JOIN, HF_BRING_E_NO_JOIN without the
 * core. */
int hf_bring_join(uint8_t *user, uint32_t user_size, uint8_t *card, uint32_t card_size, int slot,
                  uint8_t *const user_images[2], const uint32_t user_sizes[2], uint8_t *const card_images[2],
                  const uint32_t card_sizes[2], const uint8_t *heav, uint32_t heav_size, uint32_t *left_over);

/* The sidecars' names (hf_save_files.h): user extras of `slot`, generation 0 (a) or 1 (b), card extras, and what an
 * older Heavenfall left (one per slot). */
void hf_bring_user_extras(int slot, int generation, char out[HF_BRING_NAME]);
void hf_bring_card_extras(int slot, int generation, char out[HF_BRING_NAME]);
void hf_bring_heav_extras(int slot, char out[HF_BRING_NAME]);

#endif
