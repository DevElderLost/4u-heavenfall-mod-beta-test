/* Bring on the console (bring.h): core/save/bring.py's rules over HfSaveIo. */
#include "bring.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hf_save_files.h"

/* A hunter's fields in a plain `userN` (core/save/hunter.py: the name, 12 UTF-16 letters, and the rank, at the save
 * data, which starts at 8). */
#define DATA_AT 8u
#define NAME_SIZE 0x18u
#define HR_AT 0x2Cu
#define HUNTER_MIN (DATA_AT + 0x38u + 4u)   /* a file shorter than its play time holds no hunter */

#define WHOLE_AT 0x125C4u                   /* the whole mark in the plain user file (extras_tables.h HF_EXTRAS_WHOLE_AT) */
#define WHOLE_MAGIC 0x4857u                 /* its high half: "drop all" */
#define KEEP_MAGIC 0x484Bu                  /* "keep flagged" */
#define LACKS_MAGIC 0x484Cu                 /* "lacks" */
#define CARD_MARK_AT (HF_FILE_CARD1_SIZE - 4u)  /* the card's "not joined" word (extras.py CARD_MARK_AT, CARD_MARK) */
#define CARD_MARK 0x4A4E4648u               /* "HFNJ" */
#define MAX_CHANGES 8                       /* the shared files: system, cardbox, quest1-5, otomo1 */

typedef struct {
    char name[HF_BRING_NAME];
    uint8_t *bytes;
    uint32_t size;
    int existed;                            /* Heavenfall's extdata held the file before: it is in the backup */
} Change;

void hf_bring_user_extras(int slot, int generation, char out[HF_BRING_NAME]) {
    snprintf(out, HF_BRING_NAME, HF_SIDECAR_USER_EXTRAS_FMT, slot, generation ? 'b' : 'a');
}

void hf_bring_card_extras(int slot, int generation, char out[HF_BRING_NAME]) {
    snprintf(out, HF_BRING_NAME, HF_SIDECAR_CARD_EXTRAS_FMT, slot, generation ? 'b' : 'a');
}

void hf_bring_heav_extras(int slot, char out[HF_BRING_NAME]) { snprintf(out, HF_BRING_NAME, HF_SIDECAR_HEAV_FMT, slot); }

static void name_of(char out[HF_BRING_NAME], const char *base, int number) {
    snprintf(out, HF_BRING_NAME, "%s%d", base, number);
}

static void failed_on(HfBringResult *out, const char *name) { snprintf(out->failed, sizeof out->failed, "%s", name); }

/* The hash of what a Bring writes and of the moves' record: FNV-1a over 64 bits (a check against an accident). */
static uint64_t fnv64(const uint8_t *p, uint32_t n) {
    uint64_t h = 0xCBF29CE484222325ull;
    while (n--) h = (h ^ *p++) * 0x100000001B3ull;
    return h;
}

/* A whole file into a new buffer: 0 read, 1 missing (or empty: bring.py skips an empty file), else HF_BRING_E_READ or
 * HF_BRING_E_MEMORY. */
static int load(const HfSaveIo *io, int container, const char *name, uint8_t **buf, uint32_t *size) {
    uint32_t n = 0;
    int rc = io->size(io->ctx, container, name, &n);
    *buf = NULL;
    *size = 0;
    if (rc == 1 || (rc == 0 && n == 0)) return 1;
    if (rc || n > HF_BRING_MAX_FILE) return HF_BRING_E_READ;
    if (!(*buf = (uint8_t *)malloc(n))) return HF_BRING_E_MEMORY;
    if (io->read(io->ctx, container, name, *buf, n)) {
        free(*buf);
        *buf = NULL;
        return HF_BRING_E_READ;
    }
    *size = n;
    return 0;
}

/* UTF-16LE up to its first zero into UTF-8 (a letter outside the BMP's plain range as '?'). */
static void utf16_name(const uint8_t *p, uint32_t letters, char *out, size_t cap) {
    size_t at = 0;
    uint32_t i;
    for (i = 0; i < letters; i++) {
        unsigned c = (unsigned)p[2 * i] | (unsigned)p[2 * i + 1] << 8;
        char tmp[3];
        size_t n;
        if (!c) break;
        if (c < 0x80) {
            tmp[0] = (char)c;
            n = 1;
        } else if (c < 0x800) {
            tmp[0] = (char)(0xC0 | c >> 6);
            tmp[1] = (char)(0x80 | (c & 0x3F));
            n = 2;
        } else if (c < 0xD800 || c > 0xDFFF) {
            tmp[0] = (char)(0xE0 | c >> 12);
            tmp[1] = (char)(0x80 | ((c >> 6) & 0x3F));
            tmp[2] = (char)(0x80 | (c & 0x3F));
            n = 3;
        } else {
            tmp[0] = '?';
            n = 1;
        }
        if (at + n >= cap) break;
        memcpy(out + at, tmp, n);
        at += n;
    }
    out[at] = 0;
}

int hf_bring_side(const HfSaveIo *io, const HfBlowfish *bf, int container, int slot, HfBringSide *out) {
    char name[HF_BRING_NAME];
    uint8_t *raw;
    uint32_t size;
    int rc;
    if (!io || !bf || !out || slot < 1 || slot > HF_SAVE_SLOTS) return HF_BRING_E_ARG;
    memset(out, 0, sizeof *out);
    name_of(name, "user", slot);
    rc = load(io, container, name, &raw, &size);
    if (rc == 1) return 0;
    out->present = 1;
    if (rc == HF_BRING_E_MEMORY) return rc;
    if (rc) return 0;   /* there but unread: not readable, so taken (a Bring would destroy it) */
    out->readable = size >= HUNTER_MIN && hf_save_decrypt(bf, raw, size, 0, NULL) == 0;
    if (out->readable) {
        out->hunter = raw[DATA_AT] || raw[DATA_AT + 1];
        if (out->hunter) {
            utf16_name(raw + DATA_AT, NAME_SIZE / 2, out->name, sizeof out->name);
            out->hr = (uint32_t)raw[DATA_AT + HR_AT] | (uint32_t)raw[DATA_AT + HR_AT + 1] << 8;
        }
    }
    free(raw);
    return 0;
}

int hf_bring_slot_info(const HfSaveIo *io, const HfBlowfish *bf, int slot, HfBringSlot *out) {
    int rc, k;
    if (!out) return HF_BRING_E_ARG;
    memset(out, 0, sizeof *out);
    if ((rc = hf_bring_side(io, bf, HF_BRING_MH4U_SAVE, slot, &out->mh4u)) ||
        (rc = hf_bring_side(io, bf, HF_BRING_HEAVENFALL, slot, &out->heavenfall)))
        return rc;
    for (k = 0; k < 5; k++) {   /* the extras' four, then what an older Heavenfall left */
        char name[HF_BRING_NAME];
        uint32_t size = 0;
        if (k < 4) (k / 2 ? hf_bring_card_extras : hf_bring_user_extras)(slot, k % 2, name);
        else hf_bring_heav_extras(slot, name);
        if (io->size(io->ctx, HF_BRING_MH4U_EXTDATA, name, &size) == 0 && size) out->sidecars = 1;
    }
    return 0;
}

/* ---- the journal of a Bring (bring.h, HfBringRecovery) ---- */

#define JOURNAL_MAGIC "HFJ1"
#define JOURNAL_MAX 1024u

/* The journal's text: "HFJ1\n<stamp>\nSTARTED <k>\n" then "<name> <existed> <size> <hash>\n" for each change, then
 * "END\n"; k is how many files' writes have begun (the last of them may be half written). Its length, 0 when it does
 * not fit. */
static uint32_t journal_text(const HfSaveIo *io, const Change *changes, int n, int started, char *out, size_t cap) {
    size_t at = (size_t)snprintf(out, cap, "%s\n%s\nSTARTED %d\n", JOURNAL_MAGIC, io->stamp ? io->stamp : "", started);
    int i;
    for (i = 0; i < n && at < cap; i++)
        at += (size_t)snprintf(out + at, cap - at, "%s %d %lu %016llx\n", changes[i].name, changes[i].existed,
                               (unsigned long)changes[i].size,
                               (unsigned long long)fnv64(changes[i].bytes, changes[i].size));
    if (at < cap) at += (size_t)snprintf(out + at, cap - at, "END\n");
    return at < cap ? (uint32_t)at : 0;
}

typedef struct {
    char stamp[HF_BRING_STAMP];
    int count, started;
    struct {
        char name[HF_BRING_NAME];
        int existed;
        uint32_t size;
        uint64_t hash;
    } file[MAX_CHANGES];
} Journal;

/* 1 whole journal parsed, 0 none, 2 there but not whole (a cut while it was written: no file was written), -1 unreadable (kept: it may hold the only record of a cut). */
static int journal_read(const HfSaveIo *io, Journal *j) {
    uint8_t *raw = NULL;
    uint32_t size = 0;
    char *p, *line;
    int rc = load(io, HF_BRING_STATE, HF_BRING_JOURNAL, &raw, &size), whole = 0;
    memset(j, 0, sizeof *j);
    if (rc == 1) return 0;
    if (rc) return -1;
    if (size >= JOURNAL_MAX || !(p = (char *)malloc(size + 1))) {
        free(raw);
        return size >= JOURNAL_MAX ? 2 : -1;
    }
    memcpy(p, raw, size);
    p[size] = 0;
    free(raw);
    line = strtok(p, "\n");
    if (line && !strcmp(line, JOURNAL_MAGIC) && (line = strtok(NULL, "\n")) && strlen(line) == HF_BRING_STAMP - 1) {
        memcpy(j->stamp, line, HF_BRING_STAMP);
        if (!(line = strtok(NULL, "\n")) || sscanf(line, "STARTED %d", &j->started) != 1) line = NULL;
        while (line && (line = strtok(NULL, "\n"))) {
            unsigned long long hash;
            unsigned long sz;
            int existed;
            char name[HF_BRING_NAME];
            if (!strcmp(line, "END")) {
                whole = 1;
                break;
            }
            if (j->count >= MAX_CHANGES || sscanf(line, "%15s %d %lu %llx", name, &existed, &sz, &hash) != 4) break;
            memcpy(j->file[j->count].name, name, HF_BRING_NAME);
            j->file[j->count].existed = existed != 0;
            j->file[j->count].size = (uint32_t)sz;
            j->file[j->count++].hash = hash;
        }
    }
    free(p);
    return whole ? 1 : 2;
}

int hf_bring_journal_stamp(const HfSaveIo *io, char stamp[HF_BRING_STAMP]) {
    Journal *j;
    int rc;
    stamp[0] = 0;
    if (!io || !(j = (Journal *)malloc(sizeof *j))) return 0;
    rc = journal_read(io, j);
    if (rc == 1) memcpy(stamp, j->stamp, HF_BRING_STAMP);
    else if (rc == 2) io->remove(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL);   /* not whole: no write had begun */
    free(j);
    return rc == 1;
}

/* A user or card file can be told whole or damaged by its checksum. */
static int checkable(const char *name) {
    return !strncmp(name, "user", 4) || (!strncmp(name, "card", 4) && strcmp(name, HF_FILE_CARDBOX_NAME));
}

/* 1 when `buf` (a checkable file) does not decrypt: a write cut halfway leaves such a file, the game would call it
 * corrupt, so nothing of the player's is in it. */
static int damaged(const HfBlowfish *bf, const char *name, uint8_t *buf, uint32_t size) {
    return bf && hf_save_decrypt(bf, buf, size, !strncmp(name, "card", 4) ? HF_SAVECRYPT_CARD_BLOWFISH_FROM : 0, NULL);
}

/* One journal entry put back when it needs it; 0 done (counted in `out`), else HF_BRING_E_*. */
static int recover_one(const HfSaveIo *io, const HfBlowfish *bf, const Journal *j, int i, HfBringRecovery *out) {
    uint8_t *cur = NULL, *old = NULL;
    uint32_t size = 0, old_size = 0;
    const char *name = j->file[i].name;
    int got = load(io, HF_BRING_HEAVENFALL, name, &cur, &size), old_got = 1, restore = 0, rc = 0;
    if (got > 1 || got < 0) return got;
    if (j->file[i].existed) old_got = load(io, HF_BRING_BACKUP, name, &old, &old_size);
    if (old_got > 1 || old_got < 0) {
        free(cur);
        return old_got;
    }
    if (got == 0 && old_got == 0 && size == old_size && !memcmp(cur, old, size)) {
        /* already as it was */
    } else if (got == 1) {
        restore = j->file[i].existed;   /* gone: back from the backup (a file the Bring made is not wanted) */
    } else if ((size == j->file[i].size && fnv64(cur, size) == j->file[i].hash) ||
               (checkable(name) ? damaged(bf, name, cur, size) : i == j->started - 1)) {
        /* what the Bring wrote, or half of it: a user or card file that does not decrypt, any other file that was the
         * write running at the cut (a file with other content that decrypts is the game's: kept) */
        restore = 1;
    } else {
        out->kept++;   /* the game saved it since: never destroyed */
    }
    if (restore && j->file[i].existed && old_got == 1) {
        out->kept++;   /* the backup set is gone: nothing to put back */
    } else if (restore) {
        rc = j->file[i].existed ? io->write(io->ctx, HF_BRING_HEAVENFALL, name, old, old_size)
                                : io->remove(io->ctx, HF_BRING_HEAVENFALL, name);
        if (rc) rc = HF_BRING_E_WRITE;
        else out->restored++;
    }
    free(cur);
    free(old);
    return rc;
}

int hf_bring_recover(const HfSaveIo *io, const HfBlowfish *bf, HfBringRecovery *out) {
    Journal *j;
    int rc, i, all_new = 1;
    if (!out) return HF_BRING_E_ARG;
    memset(out, 0, sizeof *out);
    if (!io) return out->code = HF_BRING_E_ARG;
    if (!(j = (Journal *)malloc(sizeof *j))) return out->code = HF_BRING_E_MEMORY;
    rc = journal_read(io, j);
    if (rc == 2) io->remove(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL);
    if (rc != 1) {
        free(j);
        return out->code = rc < 0 ? HF_BRING_E_READ : HF_BRING_OK;
    }
    out->found = 1;
    for (i = 0; i < j->count && !out->code; i++) {   /* every file as the Bring wrote it: the Bring had ended */
        uint8_t *cur = NULL;
        uint32_t size = 0;
        int got = load(io, HF_BRING_HEAVENFALL, j->file[i].name, &cur, &size);
        if (got > 1 || got < 0) out->code = got;
        else if (got == 1 || size != j->file[i].size || fnv64(cur, size) != j->file[i].hash) all_new = 0;
        free(cur);
        if (out->code) snprintf(out->failed, sizeof out->failed, "%s", j->file[i].name);
    }
    out->completed = !out->code && all_new;
    for (i = j->count - 1; i >= 0 && !out->code && !out->completed; i--)
        if ((out->code = recover_one(io, bf, j, i, out))) snprintf(out->failed, sizeof out->failed, "%s", j->file[i].name);
    if (!out->code) io->remove(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL);   /* a failure keeps it: tried again */
    free(j);
    return out->code;
}

/* The changes into Heavenfall's extdata: every file it holds now copied into the backup first (none written before
 * all are), the journal written (each file with what it will hold), then the writes in order; a write that fails
 * puts back what was written, from the backup, and deletes a file that was not there. The journal goes when the Bring
 * ended (all written, or all put back); a cut leaves it for hf_bring_recover. The changes' buffers are freed. */
static int apply(const HfSaveIo *io, Change *changes, int n, HfBringResult *out) {
    int i, k, rc = HF_BRING_OK;
    for (i = 0; i < n && rc == HF_BRING_OK; i++) {
        uint8_t *old = NULL;
        uint32_t size = 0;
        int got = load(io, HF_BRING_HEAVENFALL, changes[i].name, &old, &size);
        if (got == 1) continue;   /* nothing to keep: a rollback deletes it */
        if (got || io->write(io->ctx, HF_BRING_BACKUP, changes[i].name, old, size)) {
            failed_on(out, changes[i].name);
            rc = got == HF_BRING_E_MEMORY ? got : HF_BRING_E_BACKUP;
        } else {
            changes[i].existed = 1;
            out->backed_up++;
        }
        free(old);
    }
    if (rc == HF_BRING_OK) {
        char text[JOURNAL_MAX];
        uint32_t len = journal_text(io, changes, n, 0, text, sizeof text);
        if (!len || io->write(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL, (const uint8_t *)text, len)) {
            failed_on(out, HF_BRING_JOURNAL);   /* nothing is written without it: a cut would go unnoticed */
            io->remove(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL);
            rc = HF_BRING_E_BACKUP;
        }
    }
    for (k = 0; k < n && rc == HF_BRING_OK; k++) {
        char text[JOURNAL_MAX];
        uint32_t len = journal_text(io, changes, n, k + 1, text, sizeof text);   /* this write is the one running */
        if (len && !io->write(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL, (const uint8_t *)text, len) &&
            !io->write(io->ctx, HF_BRING_HEAVENFALL, changes[k].name, changes[k].bytes, changes[k].size)) {
            out->written++;
            continue;
        }
        failed_on(out, changes[k].name);
        rc = HF_BRING_E_WRITE;
        out->rolled_back = 1;
        for (i = k; i >= 0; i--) {   /* the one that failed may be half written: it goes back too */
            uint8_t *old = NULL;
            uint32_t size = 0;
            int bad = changes[i].existed
                          ? load(io, HF_BRING_BACKUP, changes[i].name, &old, &size) ||
                                io->write(io->ctx, HF_BRING_HEAVENFALL, changes[i].name, old, size)
                          : io->remove(io->ctx, HF_BRING_HEAVENFALL, changes[i].name);
            free(old);
            if (bad) out->rolled_back = 0;
        }
    }
    if (rc == HF_BRING_OK || (rc == HF_BRING_E_WRITE && out->rolled_back))
        io->remove(io->ctx, HF_BRING_STATE, HF_BRING_JOURNAL);   /* ended: nothing to put back */
    for (i = 0; i < n; i++) free(changes[i].bytes);
    return out->code = rc;
}

static int fail(HfBringResult *out, int code) { return out->code = code; }

static uint32_t word_at(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* Heavenfall Beta's marks are cleared in a plain file: a `userN`'s whole mark ("drop all", "keep flagged", "lacks":
 * written when its sidecar could not be, core/save/extras.py WHOLE_AT), a `cardN`'s "not joined" word (written while
 * Beta's game held none of the card's sidecar). Heavenfall's own game never reads one (the PC's bring._unmark_plain,
 * _unmark_card_plain). 1 when one was there. */
static int unmark(uint8_t *plain, uint32_t size) {
    uint32_t magic;
    if (size == HF_FILE_CARD1_SIZE) {
        if (word_at(plain + CARD_MARK_AT) != CARD_MARK) return 0;
        memset(plain + CARD_MARK_AT, 0, 4);
        return 1;
    }
    if (size != HF_FILE_USER1_SIZE) return 0;
    magic = word_at(plain + WHOLE_AT) >> 16;
    if (magic != WHOLE_MAGIC && magic != KEEP_MAGIC && magic != LACKS_MAGIC) return 0;
    memset(plain + WHOLE_AT, 0, 4);
    return 1;
}

/* A raw copy of MH4U's `userN` or `cardN` without sidecars: byte for byte, unless it carries a mark (cleared, the
 * file encrypted again with its own seed; bring._unmarked). A file that does not decrypt goes as it is. */
static int unmark_raw(const HfBlowfish *bf, uint8_t *file, uint32_t size) {
    uint8_t *plain;
    uint32_t seed = 0, from = size == HF_FILE_CARD1_SIZE ? HF_SAVECRYPT_CARD_BLOWFISH_FROM : 0;
    int marked = 0;
    if ((size != HF_FILE_USER1_SIZE && size != HF_FILE_CARD1_SIZE) || !(plain = (uint8_t *)malloc(size))) return 0;
    memcpy(plain, file, size);
    if (hf_save_decrypt(bf, plain, size, from, &seed) == 0 && unmark(plain, size) &&
        hf_save_encrypt(bf, plain, size, from, seed & 0xFFFF) == 0) {
        memcpy(file, plain, size);
        marked = 1;
    }
    free(plain);
    return marked;
}

int hf_bring_slot(const HfSaveIo *io, const HfBlowfish *bf, int slot, unsigned flags, uint32_t seed,
                  HfBringResult *out) {
    Change changes[2];
    HfBringSide here;
    char user_name[HF_BRING_NAME], card_name[HF_BRING_NAME];
    uint8_t *user = NULL, *card = NULL, *images[2][2] = {{NULL, NULL}, {NULL, NULL}}, *heav = NULL;
    uint32_t user_size = 0, card_size = 0, sizes[2][2] = {{0, 0}, {0, 0}}, heav_size = 0;
    int rc, k, g, sidecars = 0, n = 0;
    if (!out) return HF_BRING_E_ARG;
    memset(out, 0, sizeof *out);
    if (!io || !bf || slot < 1 || slot > HF_SAVE_SLOTS) return fail(out, HF_BRING_E_ARG);
    if (!io->has(io->ctx, HF_BRING_HEAVENFALL)) return fail(out, HF_BRING_E_NO_WORLD);
    if ((rc = hf_bring_side(io, bf, HF_BRING_HEAVENFALL, slot, &here))) return fail(out, rc);
    if (!(flags & HF_BRING_REPLACE) && hf_bring_taken(&here)) return fail(out, HF_BRING_E_TAKEN);
    name_of(user_name, "user", slot);
    name_of(card_name, "card", slot);
    rc = load(io, HF_BRING_MH4U_SAVE, user_name, &user, &user_size);
    if (rc) {
        failed_on(out, user_name);
        return fail(out, rc == 1 ? HF_BRING_E_NO_HUNTER : rc);
    }
    rc = load(io, HF_BRING_MH4U_EXTDATA, card_name, &card, &card_size);
    if (rc == 1) rc = 0;   /* no card: Heavenfall's stays as it is */
    for (k = 0; k < 2 && !rc; k++)
        for (g = 0; g < 2 && !rc; g++) {
            char name[HF_BRING_NAME];
            (k ? hf_bring_card_extras : hf_bring_user_extras)(slot, g, name);
            rc = load(io, HF_BRING_MH4U_EXTDATA, name, &images[k][g], &sizes[k][g]);
            if (rc == 0) sidecars = 1;
            if (rc == 1) rc = 0;
            if (rc) failed_on(out, name);
        }
    if (!rc) {   /* what an older Heavenfall left (bring.py sidecars_of) */
        char name[HF_BRING_NAME];
        hf_bring_heav_extras(slot, name);
        rc = load(io, HF_BRING_MH4U_EXTDATA, name, &heav, &heav_size);
        if (rc == 0) sidecars = 1;
        if (rc == 1) rc = 0;
        if (rc) failed_on(out, name);
    }
    if (rc && !out->failed[0]) failed_on(out, card_name);
    if (!rc && sidecars) {   /* bring.py _prepare: decrypted, joined, encrypted again */
        if (!hf_bring_join_available()) rc = HF_BRING_E_NO_JOIN;
        else if (hf_save_decrypt(bf, user, user_size, 0, NULL) ||
                 (card && hf_save_decrypt(bf, card, card_size, HF_SAVECRYPT_CARD_BLOWFISH_FROM, NULL)))
            rc = HF_BRING_E_CORRUPT;
        else if (!(rc = hf_bring_join(user, user_size, card, card_size, slot, images[0], sizes[0], images[1], sizes[1],
                                      heav, heav_size, &out->left_over))) {
            unmark(user, user_size);   /* the join may answer WHOLE and leave the mark */
            hf_save_encrypt(bf, user, user_size, 0, seed & 0xFFFF);
            if (card) {
                unmark(card, card_size);   /* a card of no image joined keeps its "not joined" word */
                hf_save_encrypt(bf, card, card_size, HF_SAVECRYPT_CARD_BLOWFISH_FROM, seed >> 16);
            }
            out->joined = 1;
        }
    }
    for (k = 0; k < 2; k++)
        for (g = 0; g < 2; g++) free(images[k][g]);
    free(heav);
    if (!rc && !sidecars) {
        unmark_raw(bf, user, user_size);
        if (card) unmark_raw(bf, card, card_size);
    }
    if (rc) {
        free(user);
        free(card);
        return fail(out, rc);
    }
    memset(changes, 0, sizeof changes);
    if (card) {   /* the card first: a cut before the userN file leaves the slot's hunter as it was */
        snprintf(changes[n].name, HF_BRING_NAME, "%s", card_name);
        changes[n].bytes = card;
        changes[n++].size = card_size;
    }
    snprintf(changes[n].name, HF_BRING_NAME, "%s", user_name);
    changes[n].bytes = user;
    changes[n++].size = user_size;
    return apply(io, changes, n, out);
}

int hf_bring_common(const HfSaveIo *io, HfBringResult *out) {
    static const char *const shared[] = {HF_FILE_SYSTEM_NAME, HF_FILE_CARDBOX_NAME, HF_FILE_QUEST1_NAME,
                                         HF_FILE_QUEST2_NAME, HF_FILE_QUEST3_NAME, HF_FILE_QUEST4_NAME,
                                         HF_FILE_QUEST5_NAME, HF_FILE_OTOMO1_NAME};
    Change changes[MAX_CHANGES];
    int i, n = 0, rc = 0;
    if (!out) return HF_BRING_E_ARG;
    memset(out, 0, sizeof *out);
    if (!io) return fail(out, HF_BRING_E_ARG);
    if (!io->has(io->ctx, HF_BRING_HEAVENFALL)) return fail(out, HF_BRING_E_NO_WORLD);
    memset(changes, 0, sizeof changes);
    for (i = 0; i < (int)(sizeof shared / sizeof shared[0]) && !rc; i++) {
        /* system lives in the save archive, the others in MH4U's extdata (files.py's kinds) */
        rc = load(io, i ? HF_BRING_MH4U_EXTDATA : HF_BRING_MH4U_SAVE, shared[i], &changes[n].bytes, &changes[n].size);
        if (rc == 0) snprintf(changes[n++].name, HF_BRING_NAME, "%s", shared[i]);
        else if (rc == 1) rc = 0;
        else failed_on(out, shared[i]);
    }
    if (rc || !n) {
        for (i = 0; i < n; i++) free(changes[i].bytes);
        return fail(out, rc ? rc : HF_BRING_E_NOTHING);
    }
    return apply(io, changes, n, out);
}

/* ---- the earlier hunters already moved (bring.h, hf_bring_legacy_due) ---- */

#define MAX_MOVES 48                        /* the oldest are forgotten past this */

typedef struct {
    char console[8];
    int slot;
    uint64_t hash;
} Move;

typedef struct {
    Move move[MAX_MOVES];
    int count;
} Moves;

/* The record's lines "<console> <slot> <hash>"; a missing or damaged record is an empty one. */
static void moves_read(const HfSaveIo *io, Moves *m) {
    uint8_t *raw = NULL;
    uint32_t size = 0;
    char *p, *line;
    memset(m, 0, sizeof *m);
    if (load(io, HF_BRING_STATE, HF_BRING_MOVES, &raw, &size) || size >= JOURNAL_MAX * 8) {
        free(raw);
        return;
    }
    if (!(p = (char *)malloc(size + 1))) {
        free(raw);
        return;
    }
    memcpy(p, raw, size);
    p[size] = 0;
    free(raw);
    for (line = strtok(p, "\n"); line && m->count < MAX_MOVES; line = strtok(NULL, "\n")) {
        unsigned long long hash;
        int slot;
        char console[8];
        if (sscanf(line, "%7s %d %llx", console, &slot, &hash) != 3 || slot < 1 || slot > HF_SAVE_SLOTS) continue;
        memcpy(m->move[m->count].console, console, sizeof console);
        m->move[m->count].slot = slot;
        m->move[m->count++].hash = hash;
    }
    free(p);
}

static int moved_before(const HfSaveIo *io, const Moves *m, int slot, uint64_t hash) {
    int i;
    for (i = 0; i < m->count; i++)
        if (m->move[i].slot == slot && m->move[i].hash == hash &&
            !strcmp(m->move[i].console, io->console ? io->console : ""))
            return 1;
    return 0;
}

static int moves_write(const HfSaveIo *io, const Moves *m) {
    char text[MAX_MOVES * 40];
    size_t at = 0;
    int i;
    for (i = 0; i < m->count; i++)
        at += (size_t)snprintf(text + at, sizeof text - at, "%s %d %016llx\n", m->move[i].console, m->move[i].slot,
                               (unsigned long long)m->move[i].hash);
    return io->write(io->ctx, HF_BRING_STATE, HF_BRING_MOVES, (const uint8_t *)text, (uint32_t)at);
}

/* The moves made now added to the record (the oldest dropped when it is full). 0 done. */
static int moves_add(const HfSaveIo *io, const uint64_t hashes[HF_SAVE_SLOTS], const int moved[HF_SAVE_SLOTS]) {
    Moves *m = (Moves *)malloc(sizeof *m);
    int slot, bad;
    if (!m) return HF_BRING_E_MEMORY;
    moves_read(io, m);
    for (slot = 1; slot <= HF_SAVE_SLOTS; slot++) {
        Move *at;
        if (!moved[slot - 1] || moved_before(io, m, slot, hashes[slot - 1])) continue;
        if (m->count == MAX_MOVES) {
            memmove(m->move, m->move + 1, sizeof m->move[0] * (MAX_MOVES - 1));
            m->count--;
        }
        at = &m->move[m->count++];
        snprintf(at->console, sizeof at->console, "%s", io->console ? io->console : "");
        at->slot = slot;
        at->hash = hashes[slot - 1];
    }
    bad = moves_write(io, m);
    free(m);
    return bad;
}

/* The slots with an earlier hunter (a file with bytes) not moved before: 1 each; how many. */
int hf_bring_legacy_due(const HfSaveIo *io, int due[HF_SAVE_SLOTS]) {
    Moves *m;
    int slot, count = 0;
    memset(due, 0, sizeof(int) * HF_SAVE_SLOTS);
    if (!io || !io->has(io->ctx, HF_BRING_MH4U_EXTDATA) || !(m = (Moves *)malloc(sizeof *m))) return 0;
    moves_read(io, m);
    for (slot = 1; slot <= HF_SAVE_SLOTS; slot++) {
        char name[HF_BRING_NAME];
        uint8_t *user = NULL;
        uint32_t size = 0;
        int rc;
        snprintf(name, HF_BRING_NAME, HF_LEGACY_USER_FMT, slot);
        rc = load(io, HF_BRING_MH4U_EXTDATA, name, &user, &size);
        if (rc == 1) continue;   /* none (or empty) */
        /* an unreadable file is due: the move then fails and says so */
        due[slot - 1] = rc != 0 || !moved_before(io, m, slot, fnv64(user, size));
        count += due[slot - 1];
        free(user);
    }
    free(m);
    return count;
}

int hf_bring_legacy(const HfSaveIo *io, HfBringLegacy *out) {
    Change changes[2 * HF_SAVE_SLOTS];
    char name[HF_BRING_NAME];
    uint64_t hashes[HF_SAVE_SLOTS] = {0, 0, 0};
    int slot, n = 0, rc = 0, due[HF_SAVE_SLOTS] = {0, 0, 0};
    if (!out) return HF_BRING_E_ARG;
    memset(out, 0, sizeof *out);
    if (!io) return fail(&out->result, HF_BRING_E_ARG);
    if (!io->has(io->ctx, HF_BRING_MH4U_EXTDATA)) return 0;
    if (!hf_bring_legacy_due(io, due)) return 0;
    if (!io->has(io->ctx, HF_BRING_HEAVENFALL)) return fail(&out->result, HF_BRING_E_NO_WORLD);
    memset(changes, 0, sizeof changes);
    for (slot = 1; slot <= HF_SAVE_SLOTS && !rc; slot++) {
        uint32_t size = 0;
        int origin = HF_LEGACY_HF_CARD;
        char legacy[HF_BRING_NAME];
        uint8_t *user = NULL, *card = NULL;
        uint32_t user_size = 0, card_size = 0;
        if (!due[slot - 1]) continue;
        name_of(name, "user", slot);
        if (io->size(io->ctx, HF_BRING_HEAVENFALL, name, &size) != 1) continue;   /* taken (or unreadable: kept) */
        snprintf(legacy, HF_BRING_NAME, HF_LEGACY_USER_FMT, slot);
        if ((rc = load(io, HF_BRING_MH4U_EXTDATA, legacy, &user, &user_size))) {
            failed_on(&out->result, legacy);
            break;
        }
        snprintf(legacy, HF_BRING_NAME, HF_LEGACY_CARD_FMT, slot);
        rc = load(io, HF_BRING_MH4U_EXTDATA, legacy, &card, &card_size);
        if (rc == 1) {
            origin = HF_LEGACY_MH4U_CARD;
            name_of(legacy, "card", slot);
            rc = load(io, HF_BRING_MH4U_EXTDATA, legacy, &card, &card_size);
            if (rc == 1) origin = HF_LEGACY_NO_CARD;
        }
        if (rc == 1) rc = 0;
        if (rc) {
            failed_on(&out->result, legacy);
            free(user);
            break;
        }
        hashes[slot - 1] = fnv64(user, user_size);
        if (card) {   /* the card first, as hf_bring_slot: a cut before the userN file leaves the slot as it was */
            name_of(changes[n].name, "card", slot);
            changes[n].bytes = card;
            changes[n++].size = card_size;
        }
        snprintf(changes[n].name, HF_BRING_NAME, "%s", name);
        changes[n].bytes = user;
        changes[n++].size = user_size;
        out->moved[slot - 1] = origin;
    }
    if (rc || !n) {
        for (slot = 0; slot < n; slot++) free(changes[slot].bytes);
        memset(out->moved, 0, sizeof out->moved);
        return rc ? fail(&out->result, rc) : 0;
    }
    rc = apply(io, changes, n, &out->result);
    if (rc) {
        memset(out->moved, 0, sizeof out->moved);
        return rc;
    }
    for (slot = 0; slot < HF_SAVE_SLOTS; slot++) out->count += out->moved[slot] != 0;
    out->unrecorded = moves_add(io, hashes, out->moved) != 0;   /* the move is made: a record that fails only risks a repeat */
    return 0;
}
