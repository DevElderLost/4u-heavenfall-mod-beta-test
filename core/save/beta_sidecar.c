/* Heavenfall Beta's sidecars (core/save/beta_sidecar.py).
 *
 * Heavenfall Beta plays on MH4U's own `userN` (the save archive) and `cardN` (the extdata), which stay clean retail
 * files on disk, while the game holds the full view in memory. What only Heavenfall knows goes into sidecar files in
 * MH4U's extdata (names and sizes: core/save/files.py), set apart and put back by the extras core
 * (core/save/c/extras.c, linked into this block):
 *
 * * beta_split_user: FUN_002abe04 (the only builder of `userN`) calls it at 0x2ABEB8, after the buffer is built and
 *   before the game's checksum (which also enciphers). The image goes to its sidecar first; the buffer is cleaned only
 *   when that write succeeded. Otherwise the file is written whole, with a whole mark when the view in memory holds
 *   the sidecars on disk.
 * * beta_split_card: FUN_002adedc (the only builder of `cardN`) at 0x2ADFE0, the same way (no mark: the core's join
 *   skips an item set pair its set already holds).
 * * beta_join_user: FUN_002af280 (the title's read of each slot) at 0x2AF2E0, before its copy of the data: the
 *   sidecar's content back into the checked buffer, which the game then copies.
 * * beta_join_card: FUN_002adc98 (the load's read of the slot's card) at 0x2ADDE8, after the identity check, before its
 *   copy of the item sets. The reader has already copied the book's Guild Cards into the save object there, so the
 *   looks the join puts back into the book go there too.
 *
 * Left-overs (what a join could not place: a full box) stay on disk: a join that left something over writes its
 * rewritten image at once as the newest generation + 1 (the flag update), and the next split carries that image's
 * flagged entries; a whole write then marks the file "keep flagged" naming that generation. A flag update that cannot
 * be written keeps its join and drops the left-overs: they are in no file and no image on disk flags them.
 *
 * The sidecars are read and written at once on the calling thread (an inline request: the manager's + 0x155 = 0, as
 * the game's own flush FUN_002af3fc does), the manager's status saved and restored around it. A user operation's
 * buffer is 0x78C00 bytes (FUN_002adb70) and a `userN` takes 0x13E00: its tail holds the userN images, the slot's card
 * images (for the kept file), the kept file, and a copy of the file (the original, or the plain file a failed write
 * puts back). The card operations use beta_sidecar_card (two card images).
 *
 * A launch's first title reads the slots before the boot has given the file manager the extdata's id: the first
 * request sets it as the game's own look at an extdata file does (io_ready). A slot the title still could not join (a
 * sidecar unreadable then) is joined at each save of the session instead (LATE, beta_split_user), so its file goes
 * clean and nothing of the image is lost or doubled.
 *
 * What an older Heavenfall left in MH4U's files (gear past MH4U's counts, their marks, Heavenfall's quests, the new
 * monsters' records: core/save/c/heav.c) is set apart into hfheavN at each of the four sites (heav_strip: after the
 * joins, before the splits) and cleaned out of the file, so neither the game's memory nor MH4U's file holds it; it
 * stays in hfheavN, which this code never joins back (heav.c's hf_heav_join does, for a Bring). A slot the title read with anything MH4U lacks is written back clean at once,
 * once per launch (sweep).
 *
 * Every step is noted in beta_sidecar_state's ring (beta_sidecar.py, read_state), readable from a save state.
 *
 * PC port: plain C; the four stubs in beta_sidecar.s are the only assembly.
 */

#include <stdint.h>

/* no memset / memcpy calls out of the byte loops (no libc here): the same as extras.c */
#pragma GCC optimize("no-tree-loop-distribute-patterns", "no-jump-tables", "no-tree-switch-conversion")

#include "c/extras.h"
#include "c/extras_tables.h"
#include "c/heav.h"

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef int32_t s32;

/* ---- the game ---------------------------------------------------------------------------------------------------- */

/* The file task (*file_task): one object for every file */
#define T_FLAGS        0x28     /* bit 1: the extdata is off */
#define T_BUFFER       0x138    /* the file's buffer (FUN_002adb70: 0x78C00 bytes for every kind) */
#define T_EXTDATA      0x150    /* the extdata's id (FUN_002af698), which FUN_00c195fc gives the manager */
#define T_KIND         0x260    /* 0-2 user1-3, 4-6 card1-3 */
#define FLAG_NO_EXTDATA 2u
#define KIND_CARD      4

/* The file manager (*file_manager) */
#define M_EXTDATA      0x20     /* the extdata id the archive 1 requests mount; -1: none yet (FUN_00c1a798) */
#define M_THREAD       0x138    /* the file thread (+ 0x78: the handler it runs, 0 when idle) */
#define M_STATUS       0x13C    /* u8: 0 done, 1 busy, 2 cancelled */
#define M_RESULT       0x140    /* the last request's result */
#define M_ARCHIVE      0x144    /* u8 */
#define M_CANCEL       0x154    /* u8 */
#define M_POSTED       0x155    /* u8: 1 the requests go to the file thread, 0 they run on the caller's */
#define M_CHECK_FREE   0x156    /* u8 */
#define M_COMMIT       0x157    /* u8 */
#define ARCHIVE_SAVE   0        /* "data:" */
#define ARCHIVE_EXTDATA 1       /* "extdata:" */

/* The save object (*save_control): each slot's own Guild Card, whose identity the card file carries */
#define SAVE_IDENTITY  (0x15260 + 0x7098C)
#define SAVE_SLOT_SIZE 0x1200

#define USER_FILE      HF_EXTRAS_USER_SIZE          /* 0x13E00 */
#define CARD_FILE      HF_EXTRAS_CARD_SIZE          /* 0x78C00 */
#define USER_IMAGE     HF_EXTRAS_USER_IMAGE_SIZE    /* 0x6000 */
#define CARD_IMAGE     HF_EXTRAS_CARD_IMAGE_SIZE    /* 0x5000 */
#define KEPT_SIZE      (USER_IMAGE + CARD_IMAGE)    /* another hunter's user image, then its card image */
#define SETS_AT        HF_EXTRAS_CARD_SETS_AT       /* the card's item and equipment sets (the game copies them) */
#define SETS_SIZE      HF_EXTRAS_CARD_SETS_SIZE
#define SLOTS          3
#define SAVE_BOOK      0x15260  /* the save object's book: Guild Card n at + n * 0x1200 (FUN_002adc98 / 002adedc) */
#define FILE_BOOK      0x18     /* the card file's: Guild Card n at + n * 0x1200 */
#define CARD_STRIDE    0x1200

/* The tail of a user operation's buffer (past USER_FILE) */
#define TAIL_A         (USER_FILE)
#define TAIL_B         (TAIL_A + USER_IMAGE)
#define TAIL_CARD_A    (TAIL_B + USER_IMAGE)
#define TAIL_CARD_B    (TAIL_CARD_A + CARD_IMAGE)
#define TAIL_KEPT      (TAIL_CARD_B + CARD_IMAGE)
#define TAIL_COPY      (TAIL_KEPT + KEPT_SIZE)      /* userN as on disk, then the plain file before the split */
#define TAIL_ORIGINAL  (TAIL_COPY + USER_FILE)      /* the original kept (hfoldN), read back to check it */
#define TAIL_END       (TAIL_ORIGINAL + USER_FILE)

#if TAIL_END > 0x78C00
#error "the userN operation's tail is too small"
#endif

struct entry {                  /* a request's file (FUN_00c19e14) */
    u8 name[0x100];
    u8 *buffer;
    u32 size;
    u8 flags, pad[3];
};

extern u8 *const file_manager;  /* the variables holding the manager, the file task and the save object */
extern u8 *const file_task;
extern u8 *const save_control;

/* the game's functions, ARM code: called through a register from this Thumb block */
#define GAME __attribute__((long_call))
/* the four entries, ARM code: the stubs in beta_sidecar.s reach them with an ARM `bl` (the rest of the block is Thumb) */
#define ARM __attribute__((target("arm"), noinline))
GAME struct entry *file_request_entry(struct entry *entry, const char *name, u8 *buffer, u32 size, u32 flags);
GAME void file_read_sync(u8 *manager, struct entry *entries, u32 count, u32 archive);
GAME void file_write_sync(u8 *manager, struct entry *entries, u32 count, u32 archive, u32 check_free, u32 commit);
GAME void file_delete_sync(u8 *manager, struct entry *entries, u32 count, u32 archive, u32 commit);
GAME int file_exists_sync(u8 *manager, const char *name, u32 archive, u8 *found);
GAME void file_thread_wait(u8 *thread);
GAME void file_extdata_set(u8 *manager, u32 id);
GAME u32 save_sum_cipher(u8 *task, u8 *buffer, u32 size, u32 on);     /* the sum at + 4, then the XOR stream */
GAME void save_blowfish(u8 *task, u8 *buffer, u32 size);              /* Blowfish on */

/* ---- the state --------------------------------------------------------------------------------------------------- */

#define STATE_MAGIC    0x53424648u  /* "HFBS" */
#define STATE_VERSION  2u
#define LOG_RING       64           /* beta_sidecar.py LOG_RING (a power of two) */
#define NO_SLOT        0xFFu

/* struct slot's flags */
#define USER_KNOWN     0x01u    /* the view in memory holds this hunter's user sidecars on disk (or there are none) */
#define CARD_KNOWN     0x02u
#define USER_TAG       0x04u    /* user_tag is the tag of the userN on disk */
#define CARD_TAG       0x08u
#define ORIGINAL       0x10u    /* the file read had content and no sidecar of its own: keep it before it goes clean */
#define USER_ON_DISK   0x20u    /* a user sidecar file of the slot exists */
#define CARD_ON_DISK   0x40u
#define KEPT_OK        0x80u    /* this save's user split found every other hunter's image of the slot in kept */
#define PLAN           0x100u   /* KEPT_OK is this save's (the card split after the userN split) */
#define LATE           0x200u   /* the title could not join this hunter's image (user_late): each split joins it first */
#define PENDING        0x400u   /* the last split wrote its image; whether the game's userN write landed is not known */
#define LATE_LANDED    0x800u   /* LATE, and a split that joined the image late landed: userN no longer goes with it */
#define TITLE_CONTENT  0x1000u  /* the title's userN held content to set apart (and no mark), whatever its join did */
#define TITLE_MARKED   0x2000u  /* the title's userN carried a whole mark */
#define SWEPT          0x4000u  /* the sweep ran for this slot in this launch (written clean or not) */

struct slot {                   /* beta_sidecar.py Slot */
    u32 flags;
    u32 user_tag, card_tag;
    u32 user_newest, card_newest;   /* the newest generation on disk, as last read or written */
    u32 user_left, user_flagged;    /* the left-overs waiting on disk (from the last join), and the generation of
                                     * the image that holds them flagged (the flag update, then each split's) */
    u32 user_late;                  /* LATE: the generation of the image the session's memory never had */
    u32 user_disk;                  /* CRC32 of userN as on disk (enciphered) when the last split read it, 0 unknown */
    u32 pending_tag, pending_tail;  /* PENDING: the tag of the file the last split wrote clean, and its plain tail's CRC */
    u32 pending_flagged;            /* PENDING: user_flagged before that split (its carry's image, still on disk) */
    u32 disk_tail;                  /* the plain tail's CRC (hf_extras_tail_crc) of the userN on disk, 0 unknown */
    u32 pending_gen;                /* PENDING: the generation that split wrote */
    u32 disk_gen;                   /* the generation of the image the userN on disk goes with (no split writes over
                                     * it), 0 not known: the image of user_tag */
    u32 title_mark;                 /* the whole mark of the title's userN */
};

struct note {                   /* beta_sidecar.py Note */
    u8 site, slot, what, bits;
    s32 core;                   /* the extras core's answer */
    s32 io;                     /* the request's result */
    u32 generation;
};

struct state {                  /* beta_sidecar.py STATE_SIZE */
    u32 magic, version, notes, saves;
    struct slot slots[SLOTS];
    u32 card_slot, card_left, card_flagged;     /* the card's left-overs waiting on disk, as user_left: of the slot
                                                 * loaded (NO_SLOT: none) */
    u32 pad;
    struct entry entry;         /* the request */
    char name[16];
    struct note log[LOG_RING];
};

_Static_assert(__builtin_offsetof(struct state, slots) == 0x10 && sizeof(struct slot) == 0x40 &&
               __builtin_offsetof(struct state, card_slot) == 0xD0 && __builtin_offsetof(struct state, log) == 0x1FC &&
               sizeof(struct state) == 0x1FC + 16 * LOG_RING,
               "struct state is beta_sidecar.py's (SLOTS_AT, SLOT_SIZE, CARD_LEFT_AT, LOG_AT) and fills blocks.py's "
               "BETA_SIDECAR_STATE_SIZE");

extern struct state beta_sidecar_state;                          /* the variables (blocks.py) */
#define SENTINEL       16           /* read_file's check of a file's size: bytes past an image */
#define SENTINEL_BYTE  0xA5
extern u8 beta_sidecar_card[2 * CARD_IMAGE + SENTINEL];

/* hfheavN is read into the file buffer's tail past TAIL_END for a userN, into beta_sidecar_card for a cardN (free
 * then: before the card split reads its images, after the card join used them); the sweep keeps the title's view
 * there while it splits and writes the file (its split finds nothing of hfheavN's to read) */
#define TAIL_HEAV      TAIL_END
#define TAIL_SWEEP     TAIL_END
#if TAIL_HEAV + HF_HEAV_SIZE + SENTINEL > 0x78C00 || TAIL_SWEEP + USER_FILE > 0x78C00
#error "the userN operation's tail is too small for hfheavN or the sweep"
#endif
_Static_assert(HF_HEAV_SIZE + SENTINEL <= sizeof beta_sidecar_card, "hfheavN is read into the card images' buffer");

#define S (&beta_sidecar_state)

/* note sites and outcomes (beta_sidecar.py SITES, WHATS) */
#define SITE_SPLIT_USER 1
#define SITE_SPLIT_CARD 2
#define SITE_JOIN_USER  3
#define SITE_JOIN_CARD  4
#define SITE_SWEEP      5
#define SITE_CHEATS     6        /* the cheats' flag read (beta_cheats_flag) */

#define DONE           1        /* split: the sidecar written and the file clean; join: put back */
#define NOTHING        2        /* split: nothing to set apart and no sidecar: none written */
#define NO_IO          3        /* the extdata is off, or no extdata id */
#define REFUSED        4        /* not a file of a slot, or another size */
#define NO_IMAGE       5        /* join: no valid image */
#define OTHER_HUNTER   6        /* join: another hunter's image, nothing changed */
#define AS_IT_IS       7        /* join: a file written whole, taken as it is (HF_EXTRAS_WHOLE) */
#define NEWER_IGNORED  8        /* join: an image newer than the whole file's mark, ignored (HF_EXTRAS_WHOLE_NEWER) */
#define KEEP_JOINED    9        /* join: a file written whole "keep flagged": its image's left-overs back */
#define FLAG_FAILED    10       /* join: the flag update could not be written: the join kept, its left-overs dropped */
#define READ_FAILED    11       /* a sidecar could not be read */
#define KEPT_FAILED    12       /* split: the kept file could not be written */
#define ORIGINAL_FAILED 13      /* split: the original could not be kept */
#define WRITE_FAILED   14       /* split: the sidecar could not be written */
#define CORE_FAILED    15       /* the core refused (a split that does not fit, ...) */
#define NOT_KNOWN      16       /* split: this hunter's sidecar is on disk but not in the view */
#define LATE_JOINED    17       /* split: the image the title could not join joined into the file first, then done */
#define OTHER_FILE     18       /* split card: its sidecar could not be written: written into the other one, done */
#define OLDER_SET_APART 19      /* what an older Heavenfall left set apart into hfheavN, the file cleaned of it */
#define OLDER_KEPT     20       /* hfheavN could not be read or written, or it is full: the file keeps it */
#define NOT_CLEAN      21       /* sweep: the split did not leave the file clean (its own note says why): not written */

/* note bits */
#define BIT_CARRY      0x01     /* split: the left-overs carried; join: the flag update written */
#define BIT_KEPT       0x02     /* the kept file was written */
#define BIT_ORIGINAL   0x04     /* the original was kept */
#define BIT_RETRIED    0x08     /* the sidecar was deleted and written again */
#define BIT_B          0x10     /* the image written (split) or joined (join) is b, else a */
#define BIT_CARRY_LOST 0x20     /* split: the flag update's image was not on disk: its left-overs lost */
#define BIT_DROP_ALL   0x40     /* split: the file written whole with the mark "drop all" */
#define BIT_KEEP       0x80     /* split: the file written whole with the mark "keep flagged" */
#define BIT_LACKS      (BIT_DROP_ALL | BIT_KEEP)    /* both: with the mark "lacks"; split card: the card's mark */

/* ---- bytes -------------------------------------------------------------------------------------------------------- */

static void zero(u8 *p, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        p[i] = 0;
}

static void copy(u8 *dst, const u8 *src, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        dst[i] = src[i];
}

static int same(const u8 *a, const u8 *b, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        if (a[i] != b[i])
            return 0;
    return 1;
}

static u32 rd32(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24; }

#define U32(p, off) (*(volatile u32 *)((p) + (off)))

/* ---- the state and its log ------------------------------------------------------------------------------------- */

static void state_ready(void)
{
    if (S->magic != STATE_MAGIC) {
        zero((u8 *)S, sizeof *S);
        S->magic = STATE_MAGIC;
        S->version = STATE_VERSION;
        S->card_slot = NO_SLOT;
    }
}

static void note(u32 site, u32 slot, u32 what, u32 bits, s32 core, s32 io, u32 generation)
{
    struct note *n = &S->log[S->notes & (LOG_RING - 1)];
    n->site = (u8)site;
    n->slot = (u8)slot;
    n->what = (u8)what;
    n->bits = (u8)bits;
    n->core = core;
    n->io = io;
    n->generation = generation;
    S->notes++;
}

/* ---- names ---------------------------------------------------------------------------------------------------------- */

#define NAME_USER_EXTRAS 0      /* hfxu<slot><a|b> */
#define NAME_CARD_EXTRAS 1      /* hfxc<slot><a|b> */
#define NAME_ORIGINAL    2      /* hfold<slot> */
#define NAME_KEPT        3      /* hfkeep<slot> */
#define NAME_GAME_USER   4      /* user<slot>, the game's own */
#define NAME_HEAV        5      /* hfheav<slot> */

static u32 put(char *out, u32 n, const char *text)
{
    while (*text)
        out[n++] = *text++;
    return n;
}

/* The file's name (core/save/files.py) in S->name; slot 0-2, which 0 (a) or 1 (b) */
static const char *name_of(u32 what, u32 slot, u32 which)
{
    static const char *const stems[] = {"hfxu", "hfxc", "hfold", "hfkeep", "user", "hfheav"};
    char *out = S->name;
    u32 n = put(out, 0, stems[what]);
    out[n++] = (char)('1' + slot);
    if (what == NAME_USER_EXTRAS || what == NAME_CARD_EXTRAS)
        out[n++] = (char)('a' + which);
    out[n] = 0;
    return out;
}

/* ---- file access: an inline request through the game's manager ------------------------------------------------ */

struct saved {
    u32 result;
    u8 status, archive, cancel, posted, check_free, commit;
};

/* The words the game's task polls kept while our request runs (FUN_00c17f58 resets them), once the file thread is
 * idle (so they are final), and the request made inline */
static void io_begin(struct saved *s)
{
    u8 *m = file_manager;
    file_thread_wait(*(u8 **)(m + M_THREAD));
    s->result = U32(m, M_RESULT);
    s->status = m[M_STATUS];
    s->archive = m[M_ARCHIVE];
    s->cancel = m[M_CANCEL];
    s->posted = m[M_POSTED];
    s->check_free = m[M_CHECK_FREE];
    s->commit = m[M_COMMIT];
    m[M_POSTED] = 0;
}

static void io_end(const struct saved *s)
{
    u8 *m = file_manager;
    U32(m, M_RESULT) = s->result;
    m[M_STATUS] = s->status;
    m[M_ARCHIVE] = s->archive;
    m[M_CANCEL] = s->cancel;
    m[M_POSTED] = s->posted;
    m[M_CHECK_FREE] = s->check_free;
    m[M_COMMIT] = s->commit;
}

/* Whether the extdata can be used: the task not in its no-extdata mode and the manager holding the extdata's id. A
 * launch's first title reads the slots (FUN_005d8444 state 5) before anything has set that id (the boot's extdata
 * steps FUN_002ad088 come at state 7): then it is set here as FUN_002af390 sets it before its look at an extdata file,
 * FUN_00c195fc(manager, task + 0x150), which keeps -1 when the extdata does not mount */
static int io_ready(u8 *task)
{
    u8 *m = file_manager;
    struct saved saved;
    if (task == 0 || m == 0 || (U32(task, T_FLAGS) & FLAG_NO_EXTDATA))
        return 0;
    if (U32(m, M_EXTDATA) == 0xFFFFFFFFu && U32(task, T_EXTDATA) != 0xFFFFFFFFu) {
        io_begin(&saved);
        file_extdata_set(m, U32(task, T_EXTDATA));
        io_end(&saved);
    }
    return U32(m, M_EXTDATA) != 0xFFFFFFFFu;
}

#define OP_READ   0
#define OP_WRITE  1
#define OP_DELETE 2

/* One file read, written or deleted at once: 0, or the request's error */
static s32 request(u32 op, u32 archive, const char *name, u8 *buffer, u32 size)
{
    u8 *m = file_manager;
    struct saved saved;
    s32 result;
    io_begin(&saved);
    file_request_entry(&S->entry, name, buffer, size, 0);
    if (op == OP_READ)
        file_read_sync(m, &S->entry, 1, archive);
    else if (op == OP_WRITE)
        file_write_sync(m, &S->entry, 1, archive, 1, 1);    /* as the game's own extdata writes pass them */
    else
        file_delete_sync(m, &S->entry, 1, archive, 1);
    result = (s32)U32(m, M_RESULT);
    if (result == 0 && m[M_STATUS] != 0)
        result = -1;                                        /* cancelled */
    io_end(&saved);
    return result;
}

#define MISSING   0
#define PRESENT   1
#define UNREADABLE 2

/* Whether the file exists: 0 (asked) or the error, `found` set */
static s32 exists(u32 archive, const char *name, u8 *found)
{
    struct saved saved;
    s32 result;
    *found = 1;
    io_begin(&saved);
    result = file_exists_sync(file_manager, name, archive, found);
    io_end(&saved);
    return result;
}

/* The file into `buffer`: PRESENT, MISSING (it does not exist) or UNREADABLE. A file of another size reads as zeros
 * (no image validates them): a short read leaves the cleared buffer, and a longer file overwrites the SENTINEL bytes
 * past `size` (which the buffer has spare; a later read fills them) */

static u32 read_file(const char *name, u8 *buffer, u32 size, s32 *io)
{
    u8 found;
    u32 i;
    zero(buffer, size);
    for (i = 0; i < SENTINEL; i++)
        buffer[size + i] = SENTINEL_BYTE;
    *io = request(OP_READ, ARCHIVE_EXTDATA, name, buffer, size + SENTINEL);
    if (*io == 0) {
        for (i = 0; i < SENTINEL; i++)
            if (buffer[size + i] != SENTINEL_BYTE)
                zero(buffer, size);
        return PRESENT;
    }
    zero(buffer, size);
    return exists(ARCHIVE_EXTDATA, name, &found) == 0 && !found ? MISSING : UNREADABLE;
}

/* A sidecar written once, never deleted: for a file that holds what is in no other file (read whole, so of the right
 * size, where the retry below helps nothing): 0 or the error (B53) */
static s32 write_once(const char *name, u8 *image, u32 size)
{
    return request(OP_WRITE, ARCHIVE_EXTDATA, name, image, size);
}

/* A sidecar written; when that fails, the file deleted and written again (an extdata file keeps the size it was made
 * with: a file of another size refuses every write): 0 or the error. Only over a file whose loss loses nothing (one
 * that read as no image, or whose image is in another file); a file that holds what is in no other: write_once */
static s32 write_sidecar(const char *name, u8 *image, u32 size, u32 *bits)
{
    s32 result = request(OP_WRITE, ARCHIVE_EXTDATA, name, image, size);
    if (result != 0) {
        request(OP_DELETE, ARCHIVE_EXTDATA, name, image, size);
        result = request(OP_WRITE, ARCHIVE_EXTDATA, name, image, size);
        *bits |= BIT_RETRIED;
    }
    return result;
}

/* ---- what an older Heavenfall left ------------------------------------------------------------------------------- */

/* The file's content MH4U lacks set apart into hfheavN (`side`: HF_HEAV_SIZE + SENTINEL bytes), then cleaned out of
 * the file (placeholders in place). 1 when the file holds
 * none of it now, 0 when it keeps it (hfheavN unreadable, full or not written): noted */
static int heav_strip(u32 site, u32 slot, u8 *file, u32 size, u8 *side)
{
    u32 bits = 0;
    s32 io = 0;
    int code, held;
    if (hf_heav_has(file, size) <= 0)
        return 1;
    if (read_file(name_of(NAME_HEAV, slot, 0), side, HF_HEAV_SIZE, &io) == UNREADABLE) {
        note(site, slot, OLDER_KEPT, 0, 0, io, 0);
        return 0;
    }
    io = 0;
    held = hf_heav_blocks(side, HF_HEAV_SIZE) > 0;          /* blocks read: a file of the right size, kept (B53) */
    code = hf_heav_append(file, size, side, HF_HEAV_SIZE, slot + 1);   /* a missing file reads as zeros: a new one */
    if (code == (int)HF_HEAV_APPENDED)
        io = held ? write_once(name_of(NAME_HEAV, slot, 0), side, HF_HEAV_SIZE)
                  : write_sidecar(name_of(NAME_HEAV, slot, 0), side, HF_HEAV_SIZE, &bits);
    if ((code != (int)HF_HEAV_APPENDED && code != (int)HF_HEAV_ALREADY) || io != 0) {
        note(site, slot, OLDER_KEPT, bits, code, io, 0);
        return 0;
    }
    note(site, slot, OLDER_SET_APART, bits, hf_heav_clean(file, size), 0, (u32)hf_heav_blocks(side, HF_HEAV_SIZE));
    return 1;
}

/* ---- the images of a slot ----------------------------------------------------------------------------------------- */

struct pair {
    u8 *image[2];               /* a, b */
    u32 size, kind;
    u32 state[2];               /* MISSING, PRESENT, UNREADABLE */
    s32 io;
};

/* The pair's two images, one after the other at `at` */
static void pair_init(struct pair *p, u8 *at, u32 size, u32 kind)
{
    p->image[0] = at;
    p->image[1] = at + size;
    p->size = size;
    p->kind = kind;
    p->state[0] = p->state[1] = MISSING;
    p->io = 0;
}

/* Both files read: 1, or 0 when one could not be (it exists, or might) */
static int pair_read(struct pair *p, u32 what, u32 slot)
{
    s32 io;
    u32 g;
    p->io = 0;
    for (g = 0; g < 2; g++) {
        p->state[g] = read_file(name_of(what, slot, g), p->image[g], p->size, &io);
        if (p->state[g] == UNREADABLE)
            p->io = io;
    }
    return p->state[0] != UNREADABLE && p->state[1] != UNREADABLE;
}

static int pair_on_disk(const struct pair *p) { return p->state[0] == PRESENT || p->state[1] == PRESENT; }

static u32 pair_newest(const struct pair *p)
{
    return hf_extras_newest_generation(p->image[0], p->size, p->image[1], p->size, p->kind);
}

static int pair_pick(const struct pair *p, u32 tag, const u8 *identity, u32 slot)
{
    return hf_extras_pick(p->image[0], p->size, p->image[1], p->size, p->kind, tag, identity, slot + 1);
}

static int pair_target(const struct pair *p, int picked)
{
    return hf_extras_write_slot(p->image[0], p->size, p->image[1], p->size, p->kind, picked);
}

static int valid(const struct pair *p, int which)
{
    return hf_extras_image_kind(p->image[which], p->size) == (int)p->kind;
}

static int foreign(const struct pair *p, int which, const u8 *identity, u32 slot)
{
    return valid(p, which) && !hf_extras_owned_by(p->image[which], identity, slot + 1);
}

static int own(const struct pair *p, int which, const u8 *identity, u32 slot)
{
    return valid(p, which) && hf_extras_owned_by(p->image[which], identity, slot + 1);
}

static int any_own(const struct pair *p, const u8 *identity, u32 slot)
{
    return own(p, 0, identity, slot) || own(p, 1, identity, slot);
}

/* The newest of another hunter's (or slot's) images, or 0 */
static u8 *newest_foreign(const struct pair *p, const u8 *identity, u32 slot)
{
    int fa = foreign(p, 0, identity, slot), fb = foreign(p, 1, identity, slot);
    if (fa && fb)
        return hf_extras_generation(p->image[1]) > hf_extras_generation(p->image[0]) ? p->image[1] : p->image[0];
    return fa ? p->image[0] : fb ? p->image[1] : 0;
}

/* Which of the pair is this hunter's flag update (generation `generation`, `left` entries flagged): 0, 1, or -1 */
static int flag_image(const struct pair *p, const u8 *identity, u32 slot, u32 generation, u32 left)
{
    int g;
    for (g = 0; g < 2; g++)
        if (own(p, g, identity, slot) && hf_extras_generation(p->image[g]) == generation &&
            hf_extras_left_over(p->image[g]) == left)
            return g;
    return -1;
}

/* ---- the userN file: split ------------------------------------------------------------------------------------------- */

/* The userN file goes whole. With a mark when the view holds this hunter's sidecars and something a later join could
 * double or lose: "keep flagged" naming the flag update's generation when left-overs wait on disk, else "drop all"
 * naming the newest generation. A LATE slot's view lacks the title's image: a file this split joined it into
 * (`joined`: its left-overs, -1 not joined) holds everything but them, "drop all"; one without it is marked "lacks"
 * naming that image (user_late, which no split of the session writes over): the next join puts it back as it is and
 * drops every other image (the session's: their content is in the file). The note's bits */
static u32 user_whole(struct slot *s, u8 *buf, int has, int joined)
{
    if ((s->flags & LATE) && joined >= 0) {
        hf_extras_set_whole_mark(buf, s->user_newest, 0);
        return BIT_DROP_ALL | (joined != 0 ? BIT_CARRY_LOST : 0);
    }
    if (s->flags & LATE) {
        hf_extras_set_whole_mark(buf, s->user_late, HF_EXTRAS_LACKS);
        return BIT_LACKS;
    }
    if (!(s->flags & USER_KNOWN) || !(has > 0 || s->user_left || (s->flags & USER_ON_DISK)))
        return 0;
    if (s->user_left) {
        hf_extras_set_whole_mark(buf, s->user_flagged, 1);
        return BIT_KEEP;
    }
    hf_extras_set_whole_mark(buf, s->user_newest, 0);
    return BIT_DROP_ALL;
}

/* Every other hunter's image of the slot in its kept file (written when it does not hold them yet): 1, or 0 */
static int keep_others(u32 slot, u8 *buf, const struct pair *user, const struct pair *card, u32 *bits, s32 *io)
{
    const u8 *identity = buf + HF_EXTRAS_USER_IDENTITY_AT;
    u8 *other_user = newest_foreign(user, identity, slot), *other_card = newest_foreign(card, identity, slot);
    u8 *kept = buf + TAIL_KEPT;
    if (!other_user && !other_card)
        return 1;
    if (read_file(name_of(NAME_KEPT, slot, 0), kept, KEPT_SIZE, io) == UNREADABLE)
        return 0;
    if ((!other_user || same(kept, other_user, USER_IMAGE)) &&
        (!other_card || same(kept + USER_IMAGE, other_card, CARD_IMAGE)))
        return 1;
    if (other_user)
        copy(kept, other_user, USER_IMAGE);
    if (other_card)
        copy(kept + USER_IMAGE, other_card, CARD_IMAGE);
    *io = request(OP_WRITE, ARCHIVE_EXTDATA, name_of(NAME_KEPT, slot, 0), kept, KEPT_SIZE);
    if (*io != 0)
        return 0;
    *bits |= BIT_KEPT;
    return 1;
}

/* 1 if a kept original is whole: the end of an enciphered file is never zero (a copy cut after its file was made, or
 * in its write, is) */
static int original_whole(const u8 *file)
{
    u32 i;
    for (i = USER_FILE - 16; i < USER_FILE; i++)
        if (file[i] != 0)
            return 1;
    return 0;
}

/* The file as it is on disk (its enciphered bytes) kept once, as the original, before it is first written clean. An
 * original kept before is never written over when it is this file or whole (an earlier original); one cut (made but
 * never written whole) is written again */
static int keep_original(u32 slot, u8 *buf, u32 *bits, s32 *io)
{
    u8 found;
    *io = exists(ARCHIVE_EXTDATA, name_of(NAME_ORIGINAL, slot, 0), &found);
    if (*io != 0)
        return 0;
    *io = request(OP_READ, ARCHIVE_SAVE, name_of(NAME_GAME_USER, slot, 0), buf + TAIL_COPY, USER_FILE);
    if (*io != 0)
        return 0;
    if (found && request(OP_READ, ARCHIVE_EXTDATA, name_of(NAME_ORIGINAL, slot, 0), buf + TAIL_ORIGINAL,
                         USER_FILE) == 0 &&
        (same(buf + TAIL_ORIGINAL, buf + TAIL_COPY, USER_FILE) || original_whole(buf + TAIL_ORIGINAL)))
        return 1;                                   /* this file, or an earlier original: never written over */
    /* none, cut, or unreadable (another size: write_sidecar makes it again); this file has content of its own too */
    *io = write_sidecar(name_of(NAME_ORIGINAL, slot, 0), buf + TAIL_COPY, USER_FILE, bits);
    if (*io != 0)
        return 0;
    *bits |= BIT_ORIGINAL;
    return 1;
}

/* userN as it is on disk (enciphered), read before the game writes over it: whether the last split's file landed
 * (PENDING: userN changed since that split read it; a read that failed, then or now, counts as landed: as before),
 * then the parent tail of this split's image: the CRC of that file's tail, only when it differs from the file's plain
 * tail (as known), since the file the game writes over it keeps it as its own plain tail. 0: not known */
static u32 disk_check(struct slot *s, u32 slot, u8 *buf)
{
    u32 raw = 0, raw_tail = 0;
    int read = request(OP_READ, ARCHIVE_SAVE, name_of(NAME_GAME_USER, slot, 0), buf + TAIL_COPY, USER_FILE) == 0;
    if (read) {
        raw = hf_extras_crc32(buf + TAIL_COPY, USER_FILE);
        raw_tail = hf_extras_tail_crc(buf + TAIL_COPY);
    }
    if (s->flags & PENDING) {
        if (!read || s->user_disk == 0 || raw != s->user_disk) {
            s->user_tag = s->pending_tag;               /* landed: its image goes with the file on disk */
            s->disk_tail = s->pending_tail;
            s->disk_gen = s->pending_gen;
            s->flags |= USER_TAG | ((s->flags & LATE) ? LATE_LANDED : 0);
        } else {
            s->user_flagged = s->pending_flagged;       /* never landed: the image it carried from still goes */
        }
        s->flags &= ~PENDING;
    }
    s->user_disk = raw;
    return read && s->disk_tail != 0 && raw_tail != s->disk_tail ? raw_tail : 0;
}

/* The image the title's join would have picked (hf_extras_pick_file) by what it knew of the file it read: its tag,
 * plain tail, content and mark; for its play time, the session's (`played`, the file being saved: never earlier, so an
 * image later than it is later than the title's file too). Only this hunter's: 0, 1, or -1 (none) */
static int title_pick(const struct slot *s, const struct pair *p, const u8 *identity, u32 slot, u32 played)
{
    const u8 *a = own(p, 0, identity, slot) ? p->image[0] : 0, *b = own(p, 1, identity, slot) ? p->image[1] : 0;
    int g;
    if (s->flags & USER_TAG)
        g = hf_extras_pick_known(a, p->size, b, p->size, p->kind, s->user_tag, s->disk_tail,
                                 (s->flags & TITLE_CONTENT) != 0, played, s->title_mark, identity, slot + 1);
    else
        g = hf_extras_pick(a, p->size, b, p->size, p->kind, 0, identity, slot + 1);     /* no title: the newest */
    return g == 0 || g == 1 ? g : -1;
}

/* The image the userN on disk goes with, which this split must not write over: the one of disk_gen, else the one of
 * the file's tag (else the newest) */
static int disk_image(const struct slot *s, const struct pair *p, const u8 *identity, u32 slot)
{
    int g;
    if (s->disk_gen != 0)
        for (g = 0; g < 2; g++)
            if (own(p, g, identity, slot) && hf_extras_generation(p->image[g]) == s->disk_gen)
                return g;
    return pair_pick(p, (s->flags & USER_TAG) ? s->user_tag : 0, identity, slot);
}

/* The image of this hunter the title could not join (LATE), which each split of the session joins into the file
 * first: its index in the pair, or -1 (none). The first time, the one the title's join would have picked; later the
 * one of that generation (no split of the session writes over it: it is always the one picked) */
static int late_image(struct slot *s, const struct pair *p, const u8 *identity, u32 slot, u32 played)
{
    int g;
    if (!(s->flags & LATE)) {
        g = title_pick(s, p, identity, slot, played);
        if (g < 0)
            return -1;
        s->user_late = hf_extras_generation(p->image[g]);
        s->flags |= LATE;
        return g;
    }
    for (g = 0; g < 2; g++)
        if (own(p, g, identity, slot) && hf_extras_generation(p->image[g]) == s->user_late)
            return g;
    return -1;
}

/* A userN built (FUN_002abe04) or swept split: what it did (the note's), DONE, NOTHING and LATE_JOINED leaving the
 * file clean. ARM as the entry it was (over 2 KB: Thumb would branch within it by `bl`) */
static ARM u32 split_user(u8 *task, u8 *buf, u32 size)
{
    u32 slot = task ? U32(task, T_KIND) : 0xFF, bits = 0, generation, what = DONE, parent_tail;
    struct slot *s;
    struct pair user, card;
    s32 io = 0, core;
    int has, target, carry, late = -1, joined = -1;
    u8 *identity, *image, *carried;

    state_ready();
    if (slot >= SLOTS || size != USER_FILE || buf == 0) {
        note(SITE_SPLIT_USER, slot, REFUSED, 0, 0, 0, 0);
        return REFUSED;
    }
    s = &S->slots[slot];
    S->saves++;
    s->flags = (s->flags & ~KEPT_OK) | PLAN;                /* this save's: the card split after it reads it */
    has = hf_extras_user_has(buf, USER_FILE);
    identity = buf + HF_EXTRAS_USER_IDENTITY_AT;
    if (!io_ready(task)) {
        note(SITE_SPLIT_USER, slot, NO_IO, user_whole(s, buf, has, -1), has, 0, s->user_newest);
        return NO_IO;
    }
    if (heav_strip(SITE_SPLIT_USER, slot, buf, USER_FILE, buf + TAIL_HEAV) == 1)    /* first: the file written */
        has = hf_extras_user_has(buf, USER_FILE);
    pair_init(&user, buf + TAIL_A, USER_IMAGE, HF_EXTRAS_USER);
    pair_init(&card, buf + TAIL_CARD_A, CARD_IMAGE, HF_EXTRAS_CARD);
    if (!pair_read(&user, NAME_USER_EXTRAS, slot) || !pair_read(&card, NAME_CARD_EXTRAS, slot)) {
        note(SITE_SPLIT_USER, slot, READ_FAILED, user_whole(s, buf, has, -1), has, user.io ? user.io : card.io,
             s->user_newest);
        return READ_FAILED;
    }
    s->flags = (s->flags & ~USER_ON_DISK) | (pair_on_disk(&user) ? USER_ON_DISK : 0);
    s->user_newest = pair_newest(&user);
    parent_tail = disk_check(s, slot, buf);
    if (!(s->flags & USER_KNOWN)) {
        /* not joined at the title (the extdata or a sidecar unreadable then): this hunter's image there is joined
         * into the file here, which then goes clean, the new image holding it and the session's content; the
         * session's memory never had it, so every split of the session joins that same image */
        late = late_image(s, &user, identity, slot, rd32(buf + HF_EXTRAS_PLAY_TIME_AT));
        if (late < 0 && (s->flags & LATE)) {
            note(SITE_SPLIT_USER, slot, NOT_KNOWN, user_whole(s, buf, has, -1), has, 0, s->user_newest);
            return NOT_KNOWN;                               /* that image gone from disk (not by the game) */
        }
        if (late < 0) {
            s->flags |= USER_KNOWN;                         /* no image of this hunter: nothing waits */
            s->user_left = 0;
            if (s->flags & TITLE_CONTENT)
                s->flags |= ORIGINAL;                       /* as the title's join would have: kept before going clean */
        } else {
            core = hf_extras_join_user(buf, USER_FILE, slot + 1, user.image[late], USER_IMAGE);
            if (core < 0 && core != HF_EXTRAS_WHOLE && core != HF_EXTRAS_WHOLE_NEWER) {
                note(SITE_SPLIT_USER, slot, CORE_FAILED, user_whole(s, buf, has, -1), core, 0, s->user_newest);
                return CORE_FAILED;
            }
            joined = core > 0 ? core : 0;                   /* its left-overs: the split carries them */
            what = LATE_JOINED;
        }
    }
    if (!keep_others(slot, buf, &user, &card, &bits, &io)) {
        note(SITE_SPLIT_USER, slot, KEPT_FAILED, bits | user_whole(s, buf, has, joined), has, io, s->user_newest);
        return KEPT_FAILED;
    }
    s->flags |= KEPT_OK;
    if (has == 0 && s->user_left == 0 && !pair_on_disk(&user)) {
        note(SITE_SPLIT_USER, slot, NOTHING, bits, 0, 0, s->user_newest);
        return NOTHING;
    }
    if (s->flags & ORIGINAL) {
        if (!keep_original(slot, buf, &bits, &io)) {
            note(SITE_SPLIT_USER, slot, ORIGINAL_FAILED, bits | user_whole(s, buf, has, joined), has, io,
                 s->user_newest);
            return ORIGINAL_FAILED;
        }
        s->flags &= ~ORIGINAL;
    }
    carry = -1;
    if (s->user_left) {
        carry = flag_image(&user, identity, slot, s->user_flagged, s->user_left);
        if (carry < 0) {
            s->user_left = 0;                               /* not on disk any more: nothing to carry */
            bits |= BIT_CARRY_LOST;
        }
    }
    target = pair_target(&user, carry >= 0 ? carry : late >= 0 ? late : disk_image(s, &user, identity, slot));
    image = user.image[target];
    carried = carry >= 0 ? user.image[carry] : joined > 0 ? user.image[late] : 0;
    generation = s->user_newest + 1;
    bits |= (target ? BIT_B : 0) | (carried ? BIT_CARRY : 0);
    copy(buf + TAIL_COPY, buf, USER_FILE);                  /* put back if the sidecar cannot be written */
    core = hf_extras_split_user(buf, USER_FILE, slot + 1, carried, USER_IMAGE, image, USER_IMAGE, generation);
    if (core < 0) {
        note(SITE_SPLIT_USER, slot, CORE_FAILED, bits | user_whole(s, buf, has, joined), core, 0, generation);
        return CORE_FAILED;
    }
    /* its parent: the file on disk it replaces (none known once a late join landed: that file is not the image's) */
    if (s->flags & LATE_LANDED)
        hf_extras_set_parent(image, USER_IMAGE, 0, 0);
    else
        hf_extras_set_parent(image, USER_IMAGE, (s->flags & USER_TAG) ? s->user_tag : 0, parent_tail);
    io = write_sidecar(name_of(NAME_USER_EXTRAS, slot, (u32)target), image, USER_IMAGE, &bits);
    if (io != 0) {
        copy(buf, buf + TAIL_COPY, USER_FILE);
        note(SITE_SPLIT_USER, slot, WRITE_FAILED, bits | user_whole(s, buf, has, joined), core, io, generation);
        return WRITE_FAILED;
    }
    /* the file's tag once its write is known to have landed (the next split's disk_check) */
    s->pending_tag = hf_extras_user_tag(buf);
    s->pending_tail = hf_extras_tail_crc(buf);
    s->pending_flagged = s->user_flagged;
    s->pending_gen = generation;
    s->user_newest = generation;
    if (carry >= 0)
        s->user_flagged = generation;   /* the left-overs wait flagged in this image now: the next split carries them */
    else
        s->user_left = 0;
    s->flags |= PENDING | USER_ON_DISK;
    note(SITE_SPLIT_USER, slot, what, bits, core, 0, generation);
    return what;
}

ARM void beta_split_user(u8 *task, u8 *buf, u32 size) { split_user(task, buf, size); }

/* ---- the card file's parts ---------------------------------------------------------------------------------------- */

/* What a card split takes and a join puts back: the sets (the item fields lie in them), then the table's card zones
 * and the book's looks (extras_tables.h) */
#define CARD_PART(file, kind) ((file) == HF_EXTRAS_CARD && ((kind) == HF_EXTRAS_ZONE || (kind) == HF_EXTRAS_BOOK))
#define PART_SIZE(file, kind, at, size, count, stride, groups, rule, first, check_at, check_size, value, image_at) \
    + (CARD_PART(file, kind) ? (size) * (count) : 0u)
#define ITEMS_IN_SETS(file, kind, at, size, count, stride, groups, rule, first, check_at, check_size, value, image_at) \
    && ((file) != HF_EXTRAS_CARD || (kind) != HF_EXTRAS_ITEMS || \
        ((at) >= SETS_AT && (at) + (stride) * ((groups) - 1) + (size) * (count) <= SETS_AT + SETS_SIZE))
#define BOOK_AS_GAME(file, kind, at, size, count, stride, groups, rule, first, check_at, check_size, value, image_at) \
    && ((kind) != HF_EXTRAS_BOOK || ((stride) == CARD_STRIDE && (at) >= FILE_BOOK && (count) <= 100))
_Static_assert(SETS_SIZE HF_EXTRAS_FIELDS(PART_SIZE) <= CARD_IMAGE, "the card's parts fit an image buffer (the undo)");
_Static_assert(1 HF_EXTRAS_FIELDS(ITEMS_IN_SETS), "a card item field outside the sets: the undo would miss it");
_Static_assert(1 HF_EXTRAS_FIELDS(BOOK_AS_GAME), "the book's looks are not where FUN_002adc98 copies the cards");

/* The card's parts copied into `keep` (back 0), or from it back into the card (1) */
static void card_parts(u8 *card, u8 *keep, int back)
{
    u32 i = 0;
    if (back)
        copy(card + SETS_AT, keep, SETS_SIZE);
    else
        copy(keep, card + SETS_AT, SETS_SIZE);
    keep += SETS_SIZE;
#define PART(file, kind, at, size, count, stride, groups, rule, first, check_at, check_size, value, image_at) \
    if (CARD_PART(file, kind)) { \
        for (i = 0; i < (count); i++, keep += (size)) { \
            if (back) \
                copy(card + (at) + i * (stride), keep, size); \
            else \
                copy(keep, card + (at) + i * (stride), size); \
        } \
    }
    HF_EXTRAS_FIELDS(PART)
#undef PART
    (void)i;
}

/* The book's looks of the card file in the save object's Guild Cards too (the join's site comes after the reader's
 * copy of every card) */
static void book_in(u8 *save, const u8 *card)
{
    u32 i = 0;
#define BOOK(file, kind, at, size, count, stride, groups, rule, first, check_at, check_size, value, image_at) \
    if ((file) == HF_EXTRAS_CARD && (kind) == HF_EXTRAS_BOOK) { \
        for (i = 0; i < (count); i++) \
            copy(save + SAVE_BOOK + (at) - FILE_BOOK + i * (stride), card + (at) + i * (stride), size); \
    }
    HF_EXTRAS_FIELDS(BOOK)
#undef BOOK
    (void)i;
}

/* What heav_strip cleans in a card file (the book's gear and logs, the Felyne cards' gear) in the save object's copies
 * too: the load's reader copied every card before the join's site */
#define SAVE_FELYNE_CARDS 0xCA2E8   /* save + 0x15260 + 0xB5088: the 50 Felyne cards (FUN_002adc98, 0x2ADDC8) */
#define FILE_FELYNE_CARDS 0x72118   /* the card file's */
#define FELYNE_CARDS      50
#define FELYNE_STRIDE     0x130
#define HEAV_PIECE(kind) ((kind) == HF_HEAV_REFS ? HF_HEAV_REF : (kind) == HF_HEAV_LOG ? HF_HEAV_LOG_SIZE : \
                          HF_HEAV_GROUP_SIZE)
#define HEAV_IN_COPIES(file, kind, at, count, stride, groups, group_stride, first, rule) \
    && ((file) != HF_EXTRAS_CARD || ((at) >= FILE_BOOK && (at) + (group_stride) * ((groups) - 1) + (stride) * \
        ((count) - 1) + HEAV_PIECE(kind) <= FILE_BOOK + 100 * CARD_STRIDE) || ((at) >= FILE_FELYNE_CARDS && \
        (at) + (stride) * ((count) - 1) + HEAV_PIECE(kind) <= FILE_FELYNE_CARDS + FELYNE_CARDS * FELYNE_STRIDE))
_Static_assert(1 HF_HEAV_FIELDS(HEAV_IN_COPIES), "a card field of heav.c outside the copies FUN_002adc98 makes");

static void heav_card_in(u8 *save, const u8 *card)
{
    u32 g = 0, i = 0, at;
#define HEAV_IN(file, kind, at_, count, stride, groups, group_stride, first, rule) \
    if ((file) == HF_EXTRAS_CARD) { \
        for (g = 0; g < (groups); g++) \
            for (i = 0; i < (count); i++) { \
                at = (at_) + g * (group_stride) + i * (stride); \
                copy(save + (at >= FILE_FELYNE_CARDS ? SAVE_FELYNE_CARDS + at - FILE_FELYNE_CARDS \
                                                     : SAVE_BOOK + at - FILE_BOOK), card + at, HEAV_PIECE(kind)); \
            } \
    }
    HF_HEAV_FIELDS(HEAV_IN)
#undef HEAV_IN
    (void)g, (void)i, (void)at;
}

/* ---- the card file: split ------------------------------------------------------------------------------------------- */

/* The card file goes whole (written as it is). When the view never held this hunter's card sidecar (the load's join
 * could not run), the file carries the "not joined" mark: its next join takes the image's tail (the Jukebox's
 * playlists) over the file's, which holds the Jukebox's default block (a card the view did hold keeps its own tail: it
 * is the newer). The note's bits */
static u32 card_whole(const struct slot *s, u8 *buf)
{
    if (s->flags & CARD_KNOWN)
        return 0;
    hf_extras_set_card_mark(buf);
    return BIT_LACKS;
}

ARM void beta_split_card(u8 *task, u8 *buf, u32 size)
{
    u32 kind = task ? U32(task, T_KIND) : 0, slot = kind - KIND_CARD, bits = 0, generation, plan, left, what = DONE;
    struct slot *s;
    struct pair card;
    s32 io = 0, core;
    int has, target, carry, other_barred, other_held;
    u8 *identity, *image, *undo;

    state_ready();
    if (kind < KIND_CARD || slot >= SLOTS || size != CARD_FILE || buf == 0) {
        note(SITE_SPLIT_CARD, slot, REFUSED, 0, 0, 0, 0);
        return;
    }
    s = &S->slots[slot];
    plan = s->flags & (PLAN | KEPT_OK);
    s->flags &= ~(PLAN | KEPT_OK);                          /* this save's user split's, read once */
    has = hf_extras_card_has(buf, CARD_FILE);
    identity = buf + HF_EXTRAS_CARD_IDENTITY_AT;
    if (!io_ready(task)) {
        note(SITE_SPLIT_CARD, slot, NO_IO, card_whole(s, buf), has, 0, s->card_newest);
        return;
    }
    if (heav_strip(SITE_SPLIT_CARD, slot, buf, CARD_FILE, beta_sidecar_card) == 1)   /* before its images there */
        has = hf_extras_card_has(buf, CARD_FILE);
    pair_init(&card, beta_sidecar_card, CARD_IMAGE, HF_EXTRAS_CARD);
    if (!pair_read(&card, NAME_CARD_EXTRAS, slot)) {
        note(SITE_SPLIT_CARD, slot, READ_FAILED, card_whole(s, buf), has, card.io, s->card_newest);
        return;
    }
    s->flags = (s->flags & ~CARD_ON_DISK) | (pair_on_disk(&card) ? CARD_ON_DISK : 0);
    s->card_newest = pair_newest(&card);
    if (!(s->flags & CARD_KNOWN)) {
        if (any_own(&card, identity, slot)) {
            note(SITE_SPLIT_CARD, slot, NOT_KNOWN, card_whole(s, buf), has, 0, s->card_newest);
            return;
        }
        s->flags |= CARD_KNOWN;
    }
    left = S->card_slot == slot ? S->card_left : 0;
    if (has == 0 && left == 0 && !pair_on_disk(&card)) {
        note(SITE_SPLIT_CARD, slot, NOTHING, 0, 0, 0, s->card_newest);
        return;
    }
    carry = -1;
    if (left) {
        carry = flag_image(&card, identity, slot, S->card_flagged, left);
        if (carry < 0)
            bits |= BIT_CARRY_LOST;
    }
    target = pair_target(&card, carry >= 0 ? carry : pair_pick(&card, (s->flags & CARD_TAG) ? s->card_tag : 0,
                                                                identity, slot));
    image = card.image[target];
    undo = card.image[!target];
    bits |= (target ? BIT_B : 0) | (carry >= 0 ? BIT_CARRY : 0);
    if (foreign(&card, target, identity, slot) && plan != (PLAN | KEPT_OK)) {
        /* another hunter's image, not known to be in kept (a card written without its user file first) */
        note(SITE_SPLIT_CARD, slot, KEPT_FAILED, bits, has, 0, s->card_newest);
        return;
    }
    /* the other file's questions, asked now: card_parts below writes over its buffer (the undo copy), which then holds
     * no image (B53). With a carry the other file is the carry's (target = 1 - carry): this hunter's, never barred */
    other_barred = foreign(&card, !target, identity, slot) && plan != (PLAN | KEPT_OK);
    other_held = valid(&card, !target);
    generation = s->card_newest + 1;
    if (carry >= 0)
        copy(image, card.image[carry], CARD_IMAGE);         /* carried in place: its buffer then holds the undo copy */
    card_parts(buf, undo, 0);                               /* put back if the sidecar cannot be written */
    core = hf_extras_split_card(buf, CARD_FILE, slot + 1, carry >= 0 ? image : 0, CARD_IMAGE, image, CARD_IMAGE,
                                generation);
    if (core < 0) {
        note(SITE_SPLIT_CARD, slot, CORE_FAILED, bits, core, 0, generation);
        return;
    }
    io = write_sidecar(name_of(NAME_CARD_EXTRAS, slot, (u32)target), image, CARD_IMAGE, &bits);
    if (io != 0) {
        /* the other file rather than a card written whole, whose tail (the Jukebox's block) MH4U's next write of the
         * card would clear: even over the image the card on disk goes with, since a card's join doubles nothing (a
         * set's pair it holds is skipped, a book block goes only to its card, the tail only into a zero one) */
        target = !target;
        bits ^= BIT_B;
        if (other_barred)
            io = -1;                                        /* another hunter's, not known to be in kept */
        else if (other_held)                                /* an image there (the carry's): never deleted (B53) */
            io = write_once(name_of(NAME_CARD_EXTRAS, slot, (u32)target), image, CARD_IMAGE);
        else
            io = write_sidecar(name_of(NAME_CARD_EXTRAS, slot, (u32)target), image, CARD_IMAGE, &bits);
        if (io != 0) {
            card_parts(buf, undo, 1);
            note(SITE_SPLIT_CARD, slot, WRITE_FAILED, bits ^ BIT_B, core, io, generation);
            return;
        }
        what = OTHER_FILE;
    }
    s->card_tag = hf_extras_card_tag(buf);
    s->card_newest = generation;
    s->flags |= CARD_TAG | CARD_ON_DISK;
    if (carry >= 0)
        S->card_flagged = generation;   /* the left-overs wait flagged in this image now: the next split carries them */
    else if (S->card_slot == slot)
        S->card_slot = NO_SLOT;
    note(SITE_SPLIT_CARD, slot, what, bits, core, 0, generation);
}

/* ---- joins ------------------------------------------------------------------------------------------------------ */

/* The title's slot written back clean at once when its file held anything MH4U lacks, so MH4U finds a clean file even
if the hunter is never saved here: the view kept aside, split as a save
 * splits it (its image naming the file on disk as its parent), summed and ciphered as FUN_002abe04 does, written into
 * the save archive as the game writes userN (check_free, commit), then the view put back for the game's copy */
static void sweep(u8 *task, u8 *buf, u32 slot)
{
    struct slot *s = &S->slots[slot];
    u32 what;
    s32 io;
    s->flags |= SWEPT;
    copy(buf + TAIL_SWEEP, buf, USER_FILE);
    what = split_user(task, buf, USER_FILE);
    s->flags &= ~(PLAN | KEPT_OK);                          /* no card split follows this one */
    if (what != DONE && what != NOTHING && what != LATE_JOINED) {
        note(SITE_SWEEP, slot, NOT_CLEAN, 0, (s32)what, 0, s->user_newest);
    } else {
        save_sum_cipher(task, buf, USER_FILE, 1);
        save_blowfish(task, buf, USER_FILE);
        io = request(OP_WRITE, ARCHIVE_SAVE, name_of(NAME_GAME_USER, slot, 0), buf, USER_FILE);
        note(SITE_SWEEP, slot, io == 0 ? DONE : WRITE_FAILED, 0, 0, io, s->user_newest);
    }
    copy(buf, buf + TAIL_SWEEP, USER_FILE);
}

/* After a join that left `left` entries over: its image written at once as the newest + 1 (the flag update), to the
 * file that is not the one picked. The generation written, or 0 when it could not be */
static u32 flag_update(struct pair *p, u32 what, u32 slot, int picked, u32 newest, u32 *bits)
{
    u8 *image = p->image[picked];
    u32 generation = newest + 1;
    if (hf_extras_set_generation(image, p->size, generation) != 0)
        return 0;
    if (write_sidecar(name_of(what, slot, (u32)pair_target(p, picked)), image, p->size, bits) != 0)
        return 0;
    *bits |= BIT_CARRY;
    return generation;
}

ARM void beta_join_user(u8 *task, u8 *buf)
{
    u32 slot = task ? U32(task, T_KIND) : 0xFF, what = DONE, bits = 0, mark, generation = 0, flagged, sealed;
    struct slot *s;
    struct pair user;
    s32 core;
    int has, picked, clean;
    u8 *image;

    state_ready();
    if (slot >= SLOTS || buf == 0) {
        note(SITE_JOIN_USER, slot, REFUSED, 0, 0, 0, 0);
        return;
    }
    s = &S->slots[slot];
    s->flags &= ~(USER_KNOWN | USER_TAG | ORIGINAL | USER_ON_DISK | LATE | PENDING | LATE_LANDED | TITLE_CONTENT |
                  TITLE_MARKED);
    s->user_left = 0;
    s->user_late = 0;
    s->user_disk = 0;
    s->disk_gen = 0;
    s->user_tag = hf_extras_user_tag(buf);                  /* the file's, as on disk */
    s->disk_tail = hf_extras_tail_crc(buf);
    s->flags |= USER_TAG;
    has = hf_extras_user_has(buf, USER_FILE);
    clean = hf_heav_mh4u_clean(buf, USER_FILE) == 1;      /* MH4U knows every byte of the file as read */
    mark = hf_extras_whole_mark(buf);
    s->title_mark = mark;
    /* what a split must know when this join cannot run (LATE: title_pick, and the original of a file with content) */
    s->flags |= mark != 0 ? TITLE_MARKED : has > 0 ? TITLE_CONTENT : 0;
    if (!io_ready(task)) {
        note(SITE_JOIN_USER, slot, NO_IO, 0, has, 0, 0);
        return;
    }
    pair_init(&user, buf + TAIL_A, USER_IMAGE, HF_EXTRAS_USER);
    if (!pair_read(&user, NAME_USER_EXTRAS, slot)) {
        note(SITE_JOIN_USER, slot, READ_FAILED, 0, has, user.io, 0);
        heav_strip(SITE_JOIN_USER, slot, buf, USER_FILE, buf + TAIL_HEAV);
        return;
    }
    s->flags |= pair_on_disk(&user) ? USER_ON_DISK : 0;
    s->user_newest = pair_newest(&user);
    /* by the file itself: never an image whose own file never landed onto the file it was split from */
    picked = hf_extras_pick_file(user.image[0], USER_IMAGE, user.image[1], USER_IMAGE, HF_EXTRAS_USER, buf,
                                 buf + HF_EXTRAS_USER_IDENTITY_AT, slot + 1);
    if (picked != 0 && picked != 1) {
        core = HF_EXTRAS_NONE;
        what = NO_IMAGE;
    } else {
        image = user.image[picked];
        generation = hf_extras_generation(image);
        sealed = rd32(image + HF_EXTRAS_CRC_AT);
        bits |= picked ? BIT_B : 0;
        if (hf_extras_whole_kind(mark) == HF_EXTRAS_KEEP_FLAGGED && rd32(image + HF_EXTRAS_TAG_AT) != s->user_tag)
            what = KEEP_JOINED;
        core = hf_extras_join_user(buf, USER_FILE, slot + 1, image, USER_IMAGE);
        if (core >= 0)
            s->disk_gen = generation;                       /* the image the file on disk goes with: kept by a split */
        if (core > 0 && rd32(image + HF_EXTRAS_CRC_AT) == sealed) {
            s->user_left = (u32)core;                       /* the image on disk flags them already: no update */
            s->user_flagged = generation;
        } else if (core > 0) {
            flagged = flag_update(&user, NAME_USER_EXTRAS, slot, picked, s->user_newest, &bits);
            if (flagged) {
                s->user_left = (u32)core;
                s->user_flagged = s->user_newest = s->disk_gen = flagged;
            } else {
                what = FLAG_FAILED;                         /* the left-overs dropped: no file holds them */
                bits |= BIT_CARRY_LOST;
            }
        } else if (core == HF_EXTRAS_E_HUNTER) {
            what = OTHER_HUNTER;
        } else if (core == HF_EXTRAS_WHOLE) {
            what = AS_IT_IS;
        } else if (core == HF_EXTRAS_WHOLE_NEWER) {
            what = NEWER_IGNORED;
        } else if (core < 0) {
            note(SITE_JOIN_USER, slot, CORE_FAILED, bits, core, 0, generation);
            heav_strip(SITE_JOIN_USER, slot, buf, USER_FILE, buf + TAIL_HEAV);
            return;
        }
    }
    /* a file with content and no sidecar of its own (a public Beta 0.2.0 save): kept before it is written clean */
    if (has > 0 && mark == 0 && (what == NO_IMAGE || what == OTHER_HUNTER))
        s->flags |= ORIGINAL;
    s->flags |= USER_KNOWN;
    note(SITE_JOIN_USER, slot, what, bits, core, 0, generation);
    /* after the join (its pick needs the file as on disk); then, the file read not MH4U's own, the sweep */
    if (heav_strip(SITE_JOIN_USER, slot, buf, USER_FILE, buf + TAIL_HEAV) && !clean && !(s->flags & SWEPT))
        sweep(task, buf, slot);
}

/* The card join's last step: what an older Heavenfall left set apart, the save object's copies cleaned too */
static void join_card_older(u32 slot, u8 *buf, u8 *save)
{
    if (hf_heav_has(buf, CARD_FILE) > 0 && heav_strip(SITE_JOIN_CARD, slot, buf, CARD_FILE, beta_sidecar_card))
        heav_card_in(save, buf);
}

ARM void beta_join_card(void)
{
    u8 *task = file_task, *buf = task ? *(u8 **)(task + T_BUFFER) : 0, *save = save_control, *image;
    u32 kind = task ? U32(task, T_KIND) : 0, slot = kind - KIND_CARD, what = DONE, bits = 0, generation = 0;
    u32 flagged, sealed;
    struct slot *s;
    struct pair card;
    s32 core;
    int picked;
    const u8 *identity;

    state_ready();
    if (kind < KIND_CARD || slot >= SLOTS || buf == 0 || save == 0) {
        note(SITE_JOIN_CARD, slot, REFUSED, 0, 0, 0, 0);
        return;
    }
    s = &S->slots[slot];
    s->flags &= ~(CARD_KNOWN | CARD_TAG | CARD_ON_DISK);
    S->card_slot = NO_SLOT;
    S->card_left = 0;
    s->card_tag = hf_extras_card_tag(buf);
    s->flags |= CARD_TAG;
    if (!io_ready(task)) {
        note(SITE_JOIN_CARD, slot, NO_IO, 0, 0, 0, 0);
        return;
    }
    pair_init(&card, beta_sidecar_card, CARD_IMAGE, HF_EXTRAS_CARD);
    if (!pair_read(&card, NAME_CARD_EXTRAS, slot)) {
        note(SITE_JOIN_CARD, slot, READ_FAILED, 0, 0, card.io, 0);
        join_card_older(slot, buf, save);
        return;
    }
    s->flags |= pair_on_disk(&card) ? CARD_ON_DISK : 0;
    s->card_newest = pair_newest(&card);
    identity = save + SAVE_IDENTITY + slot * SAVE_SLOT_SIZE;    /* the slot's own Guild Card: the userN file's */
    picked = pair_pick(&card, s->card_tag, identity, slot);
    if (picked == HF_EXTRAS_NONE) {
        core = HF_EXTRAS_NONE;
        what = NO_IMAGE;
    } else {
        image = card.image[picked];
        generation = hf_extras_generation(image);
        sealed = rd32(image + HF_EXTRAS_CRC_AT);
        bits |= picked ? BIT_B : 0;
        core = hf_extras_join_card(buf, CARD_FILE, identity, slot + 1, image, CARD_IMAGE);
        if (core >= 0)
            book_in(save, buf);
        if (core > 0 && rd32(image + HF_EXTRAS_CRC_AT) == sealed) {
            S->card_slot = slot;                            /* the image on disk flags them already: no update */
            S->card_left = (u32)core;
            S->card_flagged = generation;
        } else if (core > 0) {
            flagged = flag_update(&card, NAME_CARD_EXTRAS, slot, picked, s->card_newest, &bits);
            if (flagged) {
                S->card_slot = slot;
                S->card_left = (u32)core;
                S->card_flagged = s->card_newest = flagged;
            } else {
                what = FLAG_FAILED;                         /* the left-overs dropped (no mark: see the split) */
                bits |= BIT_CARRY_LOST;
            }
        } else if (core == HF_EXTRAS_E_HUNTER) {
            what = OTHER_HUNTER;
        } else if (core < 0) {
            note(SITE_JOIN_CARD, slot, CORE_FAILED, bits, core, 0, generation);
            join_card_older(slot, buf, save);
            return;
        }
    }
    s->flags |= CARD_KNOWN;
    note(SITE_JOIN_CARD, slot, what, bits, core, 0, generation);
    join_card_older(slot, buf, save);
}

/* ---- the cheats' flag (core/save/files.py CHEATS_FLAG) --------------- */

#define CHEATS_FLAG_NAME    "hfcheat"       /* files.py CHEATS_FLAG, CHEATS_FLAG_SIZE, _MAGIC, _VERSION */
#define CHEATS_FLAG_SIZE    16u
#define CHEATS_FLAG_MAGIC   0x48434648u     /* "HFCH" */
#define CHEATS_FLAG_VERSION 1u
#define THREAD_HANDLER      0x78            /* the file thread: the handler it runs, 0 when idle */
#define STATUS_BUSY         1

/* The game has mounted MH4U's extdata for the session (the boot's extdata steps, FUN_002ad088, or the sidecars' first
 * request, io_ready) and the file thread is idle, so a request now neither mounts anything nor waits */
static int flag_ready(void)
{
    u8 *m = file_manager, *task = file_task, *thread;
    if (m == 0 || task == 0 || (U32(task, T_FLAGS) & FLAG_NO_EXTDATA) || U32(m, M_EXTDATA) == 0xFFFFFFFFu)
        return 0;
    thread = *(u8 **)(m + M_THREAD);
    return thread != 0 && U32(thread, THREAD_HANDLER) == 0 && m[M_STATUS] != STATUS_BUSY;
}

/* mod_options.c's question for a 3DS title's Cheats group (cheats_frame, once per few frames until it has an answer):
 * whether the launcher's flag file allows the cheats. 1 yes; 0 no, final: the file missing, or not a flag that allows
 * them (shorter than the flag, another magic or version, `allowed` other than 1, a last word other than 0); -1 not
 * now: the extdata not mounted yet (or off for the session), the file thread busy, or the file unreadable. `io`: the
 * read's result. The read is the sidecars' inline request (as read_file, SENTINEL bytes more than the flag); the
 * buffer is filled first, so a file shorter than the flag keeps the fill in its last word and allows nothing. Bytes of
 * a longer file past the flag are not looked at. */
ARM int beta_cheats_flag(s32 *io)
{
    u32 words[(CHEATS_FLAG_SIZE + SENTINEL) / 4];
    u8 *flag = (u8 *)words, found;
    u32 i;
    int allowed;

    *io = 0;
    if (!flag_ready())
        return -1;
    state_ready();
    for (i = 0; i < CHEATS_FLAG_SIZE + SENTINEL; i++)
        flag[i] = SENTINEL_BYTE;
    *io = request(OP_READ, ARCHIVE_EXTDATA, CHEATS_FLAG_NAME, flag, CHEATS_FLAG_SIZE + SENTINEL);
    if (*io != 0) {
        if (exists(ARCHIVE_EXTDATA, CHEATS_FLAG_NAME, &found) != 0 || found)
            return -1;                                      /* there but unreadable now: read again later */
        note(SITE_CHEATS, NO_SLOT, NOTHING, 0, 0, *io, 0);
        return 0;
    }
    allowed = rd32(flag) == CHEATS_FLAG_MAGIC && rd32(flag + 4) == CHEATS_FLAG_VERSION && rd32(flag + 8) == 1 &&
              rd32(flag + 12) == 0;
    note(SITE_CHEATS, NO_SLOT, allowed ? DONE : REFUSED, 0, 0, 0, 0);
    return allowed;
}
