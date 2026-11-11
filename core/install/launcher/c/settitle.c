/* See settitle.h. */
#include "settitle.h"

#include <stdlib.h>
#include <string.h>

#define ROMFS_PREFIX "romfs/"
#define ROMFS_PREFIX_LEN 6u
#define CODE_PATH "exefs/code.bin"
#define EXHEADER_PATH "exheader.bin"
#define RETRY_WITHOUT_SLOT 1

struct HfSetTitle {
    HfTitleKind kind;
    Patchset *ps;
    Pack pack;
    size_t *index;          /* the set's file index of each RomFS file: a file's handle points at its entry */
    uint8_t *exefs_img;     /* the title's ExeFS image, the mod's executable made in place (the build borrows it) */
    TitleBuild *tb;
    unsigned verify;        /* the applier's PS_VERIFY_* flags as the files stream */
    int slot, slot_rc;
    uint64_t mod_bytes;
};

/* A RomFS file's bytes, made by the applier as the title streams (a PieceGen). */
static int set_gen(void *ctx, void *handle, const TitleOut *out) {
    HfSetTitle *t = (HfSetTitle *)ctx;
    return patchset_apply_file(t->ps, *(const size_t *)handle, out, t->verify);
}

typedef struct {
    uint8_t *buf;
    size_t cap, used;
} MemOut;

static int mem_write(void *ctx, const void *data, size_t n) {
    MemOut *m = (MemOut *)ctx;
    if (n > m->cap - m->used) return TITLE_E_SIZE;
    memcpy(m->buf + m->used, data, n);
    m->used += n;
    return 0;
}

/* A file of the set into `buf` (`size` bytes exactly), its output hash checked. */
static int apply_to(Patchset *ps, size_t i, uint8_t *buf, size_t size) {
    MemOut m;
    TitleOut o;
    int rc;
    m.buf = buf;
    m.cap = size;
    m.used = 0;
    memset(&o, 0, sizeof o);
    o.write = mem_write;
    o.ctx = &m;
    rc = patchset_apply_file(ps, i, &o, PS_VERIFY_OUTPUT);
    return rc ? rc : m.used == size ? TITLE_OK : TITLE_E_SIZE;
}

void hf_set_title_close(HfSetTitle *t) {
    if (!t) return;
    title_build_close(t->tb);
    patchset_close(t->ps);
    free(t->pack.files);
    free(t->index);
    free(t->exefs_img);
    free(t);
}

/* Whether the slot lists the set's RomFS files: every one of them, a plain file with the set's size and hash (an ARC's
 * size and bytes are checked as it is made). */
static int slot_lists_the_set(Patchset *ps, const TitleDigest *dg, const size_t *index, size_t n) {
    size_t j;
    if (dg->nfiles != n) return 0;
    for (j = 0; j < n; j++) {
        PatchsetFileInfo info;
        const DigestFile *f;
        if (patchset_file_info(ps, index[j], &info)) return 0;
        f = digest_find(dg, info.path + ROMFS_PREFIX_LEN);
        if (!f) return 0;
        if (info.kind == PS_FILE_PLAIN && (f->size != info.size || (info.has_hash && memcmp(f->sha256, info.sha256, 32))))
            return 0;
    }
    return 1;
}

/* A line of the open's steps in the install's log, when the input carries one. */
#define NOTE(in, ...) do { if ((in)->log) hf_log((in)->log, (in)->now_ms ? (in)->now_ms() : 0, __VA_ARGS__); } while (0)

/* The set opened (every file, or only those `paths` names) and bound to MH4U's dump, and to MH XX's for a set made with
 * it; `note` says so in the log (the first open of an attempt: the second binds the same dumps). */
static int open_bound(Patchset **ps, TitleRead read, void *ctx, void *set_handle, uint64_t set_size, int check, Dump *d,
                      const HfSetTitleIn *in, const char *const *paths, size_t npaths, int note) {
    int rc = paths ? patchset_open_files(ps, read, ctx, set_handle, set_size, check, paths, npaths)
                   : patchset_open(ps, read, ctx, set_handle, set_size, check);
    if (paths) NOTE(in, "open: the set's executable and exheader read (%lu sources): %d",
                    (unsigned long)(rc ? 0 : patchset_source_count(*ps)), rc);
    else NOTE(in, "open: the set read (%lu files): %d", (unsigned long)(rc ? 0 : patchset_file_count(*ps)), rc);
    if (rc) return rc;
    if (patchset_region(*ps) != d->region) {
        NOTE(in, "open: the set is for the other region");
        return TITLE_E_GAME;
    }
    if ((rc = patchset_bind_dump(*ps, d))) {
        NOTE(in, "open: the set's sources are not in this dump: %d", rc);
        return rc;
    }
    if (patchset_second_game(*ps, NULL, NULL)) {   /* a set made with MH XX reads its dump too */
        rc = patchset_bind_second_dump(*ps, in->xx);
        if (note || rc)
            NOTE(in, "open: an MH XX set: %s: %d", !in->xx ? "no MH XX dump given" : rc ? "not the MH XX dump it was "
                 "made with (another revision, or a file missing or of another size)" : "MH XX's dump bound", rc);
    } else if (in->xx && note) {
        NOTE(in, "open: a set without MH XX: MH XX's dump not used");
    }
    return rc;
}

/* The mod's executable and exheader, made first from a set opened with only their records (and the sources they read):
 * the ExeFS image the mod's is made in, then the game's executable decompressed in place above it, then the game's
 * dropped (its room goes back to the heap's top: no hole is left below the image, which lives through the install).
 * The rest of the set is read after it, so its tables are never in memory beside the two executables. */
static int make_executable(HfSetTitle *t, TitleRead read, void *ctx, void *set_handle, uint64_t set_size, Dump *d,
                           const HfSetTitleIn *in) {
    static const char *const files[] = {CODE_PATH, EXHEADER_PATH};
    PatchsetFileInfo info;
    Patchset *ps = NULL;
    size_t i, code_i = 2, exh_i = 2, code_off = 0;     /* 2: not in the set */
    uint64_t code_len = 0;
    int rc = open_bound(&ps, read, ctx, set_handle, set_size, in->check_set, d, in, files, 2, 1);
    for (i = 0; !rc && i < patchset_file_count(ps); i++) {
        if ((rc = patchset_file_info(ps, i, &info))) break;
        if (!strcmp(info.path, CODE_PATH)) {
            code_i = i;
            code_len = info.size;
        } else if (info.size == EXHEADER_SIZE) {
            exh_i = i;
        }
    }
    if (!rc && (code_i == 2 || exh_i == 2 || !code_len)) rc = TITLE_E_FORMAT;
    if (!rc && (rc = title_build_exefs_room(d, (size_t)code_len, &t->exefs_img, &t->pack.exefs_image_len, &code_off)))
        NOTE(in, "open: no memory for the mod's executable (%lu KB): %d", (unsigned long)(code_len >> 10), rc);
    if (!rc && (rc = patchset_executable(ps, 1)))   /* the game's, with the MH XX parts the mod's copies from */
        NOTE(in, "open: the game's executable cannot be read: %d", rc);
    if (!rc) {
        t->pack.exefs_image = t->exefs_img;
        t->pack.code = t->exefs_img + code_off;     /* made where the ExeFS image holds it: no second copy */
        t->pack.code_len = (size_t)code_len;
        rc = apply_to(ps, code_i, t->pack.code, (size_t)code_len);
        patchset_executable(ps, 0);
        NOTE(in, "open: the mod's executable (%lu KB) made: %d", (unsigned long)(code_len >> 10), rc);
        if (!rc && (rc = apply_to(ps, exh_i, t->pack.exheader, EXHEADER_SIZE)))
            NOTE(in, "open: the exheader made: %d", rc);
    }
    patchset_close(ps);
    return rc;
}

static int open_once(HfSetTitle **out, TitleRead read, void *ctx, void *set_handle, uint64_t set_size, Dump *d,
                     const HfSetTitleIn *in, int use_slot, int *slot_rc) {
    HfSetTitle *t;
    TitleDigest dg;
    int have = 0, rc;
    size_t i, n, j;
    memset(&dg, 0, sizeof dg);
    t = (HfSetTitle *)calloc(1, sizeof *t);
    if (!t) return TITLE_E_MEM;
    if ((rc = make_executable(t, read, ctx, set_handle, set_size, d, in)) ||
        (rc = open_bound(&t->ps, read, ctx, set_handle, set_size, 0, d, in, NULL, 0, 0)))   /* checked by the first */
        goto fail;
    if (in->keep_budget) patchset_keep_budget(t->ps, in->keep_budget);
    n = patchset_file_count(t->ps);
    rc = TITLE_E_MEM;
    t->index = (size_t *)calloc(n ? n : 1, sizeof *t->index);
    t->pack.files = (RomfsFile *)calloc(n ? n : 1, sizeof *t->pack.files);
    if (!t->index || !t->pack.files) goto fail;
    for (i = 0, j = 0; i < n; i++) {
        PatchsetFileInfo info;
        if ((rc = patchset_file_info(t->ps, i, &info))) goto fail;
        if (!strcmp(info.path, CODE_PATH) || !strcmp(info.path, EXHEADER_PATH)) continue;   /* made already */
        if (strncmp(info.path, ROMFS_PREFIX, ROMFS_PREFIX_LEN) || !info.path[ROMFS_PREFIX_LEN]) {
            rc = TITLE_E_FORMAT;
            goto fail;
        }
        t->index[j++] = i;
    }

    if (use_slot) {     /* the slot's data, when it lists these files; its bytes dropped once read */
        size_t len = 0;
        const uint8_t *data = patchset_build_data(t->ps, &len);
        if (!data || !len) {
            *slot_rc = HF_SLOT_EMPTY;
        } else if ((*slot_rc = digest_parse(&dg, data, len)) == TITLE_OK) {
            /* the single title takes format 2, the mod's title format 3 (the split's) */
            if (dg.format != (in->kind == HF_TITLE_MOD ? DIGEST_FORMAT_SPLIT : DIGEST_FORMAT)) *slot_rc = TITLE_E_FORMAT;
            else if (!(have = slot_lists_the_set(t->ps, &dg, t->index, j))) *slot_rc = TITLE_E_HASH;
        }
    }
    patchset_drop_build_data(t->ps);
    for (i = 0; i < j; i++) {   /* every file's size: the slot's for an ARC, or its entries deflated */
        PatchsetFileInfo info;
        RomfsFile *f = &t->pack.files[i];
        if ((rc = patchset_file_info(t->ps, t->index[i], &info))) goto fail;
        if (info.kind == PS_FILE_ARC && have) rc = patchset_set_size(t->ps, t->index[i],
                                                                     digest_find(&dg, info.path + ROMFS_PREFIX_LEN)->size);
        else if (info.kind == PS_FILE_ARC) rc = patchset_measure(t->ps, t->index[i], in->progress, in->progress_ctx);
        if (rc || (rc = patchset_file_info(t->ps, t->index[i], &info))) goto fail;
        f->path = info.path + ROMFS_PREFIX_LEN;
        f->size = info.size;
        f->handle = &t->index[i];
        t->mod_bytes += info.size;
    }
    t->pack.title_id = in->title_id;
    t->pack.region = (uint32_t)d->region;
    t->pack.total = t->mod_bytes;
    memcpy(t->pack.smdh, in->smdh, PACK_SMDH_SIZE);
    memcpy(t->pack.certs, in->certs, PACK_CERTS_SIZE);
    t->pack.nfiles = j;
    t->pack.gen = set_gen;
    t->pack.gen_ctx = t;
    /* the slot's level-2 hashes check every byte; else the set's hashes, the ARC entries copied as stored included (a
     * damaged dump's entry would go into the title unchecked) */
    t->verify = have ? 0 : PS_VERIFY_ALL;
    t->kind = in->kind;
    rc = title_build_open(&t->tb, read, ctx, d, &t->pack, in->kind == HF_TITLE_MOD ? PLAN_MOD : PLAN_BASE, NULL);
    NOTE(in, in->kind == HF_TITLE_MOD ? "open: the mod title's layout (ExeFS, the RomFS of the mod's files): %d"
                                      : "open: the title's layout (ExeFS, RomFS tables, the game's hash levels): %d", rc);
    if (rc) goto fail;
    title_build_set_version(t->tb, in->tmd_version);
    if (have && (*slot_rc = title_build_use_digest(t->tb, &dg)) != TITLE_OK) {
        NOTE(in, "open: the slot is not this title's: %d", *slot_rc);
        rc = RETRY_WITHOUT_SLOT;   /* the ARCs were given the slot's sizes: start again without them */
        goto fail;
    }
    t->slot = have;
    digest_free(&dg);
    *out = t;
    return TITLE_OK;
fail:
    digest_free(&dg);
    hf_set_title_close(t);
    return rc;
}

/* The game data (HF_TITLE_GAME): nothing of the set is made; the set is read only for its slot's game entry (none
 * without a set: `set_handle` NULL). */
static int open_game(HfSetTitle **out, TitleRead read, void *ctx, void *set_handle, uint64_t set_size, Dump *d,
                     const HfSetTitleIn *in) {
    HfSetTitle *t;
    TitleDigest dg;
    int have = 0, rc = TITLE_OK;
    memset(&dg, 0, sizeof dg);
    t = (HfSetTitle *)calloc(1, sizeof *t);
    if (!t) return TITLE_E_MEM;
    t->kind = HF_TITLE_GAME;
    t->slot_rc = in->use_slot ? HF_SLOT_EMPTY : TITLE_E_ARG;
    if (in->use_slot && set_handle) {
        Patchset *ps = NULL;
        size_t len = 0;
        const uint8_t *data;
        rc = patchset_open(&ps, read, ctx, set_handle, set_size, in->check_set);
        NOTE(in, "open: the set read for its slot (%lu files): %d", (unsigned long)(rc ? 0 : patchset_file_count(ps)),
             rc);
        if (!rc && patchset_region(ps) != d->region) {
            NOTE(in, "open: the set is for the other region");
            rc = TITLE_E_GAME;
        }
        if (!rc && (data = patchset_build_data(ps, &len)) != NULL && len) {
            t->slot_rc = digest_parse(&dg, data, len);
            have = t->slot_rc == TITLE_OK;
        }
        patchset_close(ps);
        if (rc) goto fail;
    }
    t->pack.title_id = in->title_id;
    t->pack.region = (uint32_t)d->region;
    memcpy(t->pack.certs, in->certs, PACK_CERTS_SIZE);
    rc = title_build_open(&t->tb, read, ctx, d, &t->pack, PLAN_GAME, NULL);
    NOTE(in, "open: the game data, the dump's RomFS as it is (%lu MB): %d",
         (unsigned long)(rc ? 0 : title_build_estimate(t->tb) >> 20), rc);
    if (rc) goto fail;
    title_build_set_version(t->tb, in->tmd_version);
    if (have && (t->slot_rc = title_build_use_digest(t->tb, &dg)) != TITLE_OK) {
        NOTE(in, "open: the slot names no game data for this dump's RomFS: %d", t->slot_rc);
        have = 0;
    }
    t->slot = have;
    digest_free(&dg);
    *out = t;
    return TITLE_OK;
fail:
    digest_free(&dg);
    hf_set_title_close(t);
    return rc;
}

int hf_set_title_open(HfSetTitle **out, TitleRead read, void *read_ctx, void *set_handle, uint64_t set_size, Dump *d,
                      const HfSetTitleIn *in) {
    int slot_rc = TITLE_E_ARG, unused = 0, rc;
    if (!out || !read || !d || !in || !in->certs || (unsigned)in->kind > HF_TITLE_MOD) return TITLE_E_ARG;
    if (in->kind != HF_TITLE_GAME && !in->smdh) return TITLE_E_ARG;
    *out = NULL;
    if (in->kind == HF_TITLE_GAME) return open_game(out, read, read_ctx, set_handle, set_size, d, in);
    rc = open_once(out, read, read_ctx, set_handle, set_size, d, in, in->use_slot, &slot_rc);
    if (rc == RETRY_WITHOUT_SLOT) rc = open_once(out, read, read_ctx, set_handle, set_size, d, in, 0, &unused);
    if (!rc) (*out)->slot_rc = slot_rc;
    return rc;
}

TitleBuild *hf_set_title_build(HfSetTitle *t) { return t ? t->tb : NULL; }
int hf_set_title_slot(const HfSetTitle *t) { return t && t->slot; }
int hf_set_title_slot_rc(const HfSetTitle *t) { return t ? t->slot_rc : TITLE_E_ARG; }
size_t hf_set_title_file_count(const HfSetTitle *t) { return t ? t->pack.nfiles : 0; }
uint64_t hf_set_title_mod_bytes(const HfSetTitle *t) { return t ? t->mod_bytes : 0; }

/* ---- AM's routes ---- */

static const char *const ROUTE_NAMES[HF_ROUTE_COUNT] = {
    "none", "AM parts, TMD first with the set's hash", "CIA with the set's hash", "AM parts after a hash pass",
    "CIA after a hash pass"};

int hf_route_uses_slot(HfRoute r) { return r == HF_ROUTE_PARTS_SLOT || r == HF_ROUTE_CIA_SLOT; }
int hf_route_is_parts(HfRoute r) { return r == HF_ROUTE_PARTS_SLOT || r == HF_ROUTE_PARTS_HASHED; }
const char *hf_route_name(HfRoute r) { return (unsigned)r < HF_ROUTE_COUNT ? ROUTE_NAMES[r] : "?"; }

void hf_routes_init(HfRoutes *r, int slot_usable) {
    memset(r, 0, sizeof *r);
    r->slot = slot_usable != 0;
    r->parts = r->cia = 1;
}

HfRoute hf_routes_next(HfRoutes *r) {
    HfRoute route;
    if (r->stop || (!r->parts && !r->cia)) return HF_ROUTE_NONE;
    if (r->parts) route = r->slot ? HF_ROUTE_PARTS_SLOT : HF_ROUTE_PARTS_HASHED;
    else route = r->slot ? HF_ROUTE_CIA_SLOT : HF_ROUTE_CIA_HASHED;
    if (r->tried & (1u << route)) return HF_ROUTE_NONE;
    r->tried |= 1u << route;
    return route;
}

void hf_routes_failed(HfRoutes *r, HfRoute route, HfFail why) {
    if (why == HF_FAIL_STOP || route == HF_ROUTE_NONE) {
        r->stop = 1;
    } else if (why == HF_FAIL_SLOT || (why == HF_FAIL_AM_FINISH && hf_route_uses_slot(route))) {
        r->slot = 0;
    } else if (hf_route_is_parts(route)) {
        r->parts = 0;
    } else {
        r->cia = 0;
    }
}

HfFail hf_route_failure(HfRoute route, int rc, int am_step) {
    if (rc == TITLE_E_CANCEL) return HF_FAIL_STOP;
    if (am_step == 1) return HF_FAIL_AM;
    if (am_step == 2) return HF_FAIL_AM_FINISH;
    if (rc == TITLE_E_HASH && hf_route_uses_slot(route)) return HF_FAIL_SLOT;   /* a byte not the slot's */
    return HF_FAIL_STOP;
}

/* ---- the install ---- */

static uint64_t now(const HfInstallJob *job) { return job->now_ms ? job->now_ms() : 0; }

#define LOGJ(...) do { if (job->log) hf_log(job->log, now(job), __VA_ARGS__); } while (0)

static void timed(const HfInstallJob *job, const char *what, uint64_t began, uint64_t bytes) {
    if (job->log) hf_log_phase(job->log, now(job), what, began, bytes);
}

static void phase(const HfInstallJob *job, HfText name) {
    if (job->phase) job->phase(job->ui_ctx, name);
}

/* The route's AM steps around a write pass. am_step: 1 AM refused before the content was whole, 2 at the finish. */
static int attempt(const HfInstallJob *job, HfSetTitle *t, HfRoute route, HfInstallResult *res) {
    TitleBuild *tb = t->tb;
    const HfAm *am = &job->am;
    int parts = hf_route_is_parts(route), rc;
    uint64_t began = now(job), size;
    int32_t a = 0;
    TitleOut out;
    phase(job, HT_PHASE_PREPARE);
    rc = job->run(job->run_ctx, tb, TITLE_PASS_PREPARE, NULL);
    timed(job, t->kind == HF_TITLE_GAME ? "prepare: nothing (the game data is the dump's RomFS as it is)"
               : t->slot ? "prepare: the tables, the dump's hash levels (the slot has the rest)"
                         : "prepare: the tables, the dump's hash levels, the mod's files made and hashed",
          began, t->slot ? 0 : t->mod_bytes);
    if (rc) return rc;
    size = title_build_content_size(tb);
    LOGJ("title: content %lu MB, CIA %lu MB", (unsigned long)(size >> 20),
         (unsigned long)(title_build_size(tb) >> 20));
    if (job->room && (rc = job->room(job->ui_ctx, parts ? size : title_build_size(tb)))) {
        LOGJ("no room on the card for %lu MB: %d", (unsigned long)((parts ? size : title_build_size(tb)) >> 20), rc);
        return rc;
    }
    if (!title_build_has_hash(tb)) {
        began = now(job);
        phase(job, HT_PHASE_HASH);
        rc = job->run(job->run_ctx, tb, TITLE_PASS_HASH, NULL);
        timed(job, "hash pass: the whole content read and hashed", began, size);
        if (rc) return rc;
    }
    memset(&out, 0, sizeof out);
    out.write = am->write;
    out.ctx = am->ctx;
    if (am->remove_old && !res->removed) {   /* the installed title away first: AM imports over none (settitle.h) */
        res->removed = 1;
        a = am->remove_old(am->ctx);
        LOGJ("AM: the installed title removed first (its content, ticket and save; the app puts the save back): 0x%08lX",
             (unsigned long)(uint32_t)a);
        if (a) {   /* no route installs over a title AM keeps: the install stops (am_step 0, HF_FAIL_STOP) */
            res->am = a;
            return TITLE_E_IO;
        }
    }
    began = now(job);
    if (parts) {
        uint8_t tmd[CIA_TMD_SIZE];
        if ((rc = title_build_tmd(tb, tmd))) return rc;
        a = am->parts_begin(am->ctx, tb);
        LOGJ("AM parts: certificates, ticket, title begin: 0x%08lX", (unsigned long)(uint32_t)a);
        if (!a) {
            a = am->parts_tmd(am->ctx, tmd, sizeof tmd);
            LOGJ("AM parts: TMD: 0x%08lX", (unsigned long)(uint32_t)a);
        }
        if (!a) {
            a = am->parts_content(am->ctx);
            LOGJ("AM parts: content begin: 0x%08lX", (unsigned long)(uint32_t)a);
        }
        timed(job, "AM parts: begin, ticket, TMD", began, 0);
    } else {
        a = am->cia_begin(am->ctx);
        LOGJ("AM CIA: begin: 0x%08lX", (unsigned long)(uint32_t)a);
    }
    if (a) {
        res->am = a;
        res->am_step = 1;
        if (parts) am->parts_abort(am->ctx);
        return TITLE_E_IO;
    }
    began = now(job);
    phase(job, title_build_has_hash(tb) && t->slot ? HT_PHASE_WRITE : HT_PHASE_WRITE_2);
    rc = job->run(job->run_ctx, tb, parts ? TITLE_PASS_CONTENT : TITLE_PASS_CIA, &out);
    timed(job, parts ? "write: the content into AM (the game read once)" : "write: the CIA into AM (the game read once)",
          began, parts ? size : title_build_size(tb));
    if (rc) {
        LOGJ("write stopped: %d", rc);
        if (rc == HF_E_AM_WRITE) res->am_step = 1;
        if (parts) am->parts_abort(am->ctx);
        else am->cia_cancel(am->ctx);
        return rc;
    }
    began = now(job);
    phase(job, HT_PHASE_AM);
    a = parts ? am->parts_finish(am->ctx) : am->cia_finish(am->ctx);
    LOGJ("AM %s finish and commit: 0x%08lX", parts ? "parts" : "CIA", (unsigned long)(uint32_t)a);
    timed(job, "AM finish (its checks and the commit)", began, 0);
    if (a) {
        res->am = a;
        res->am_step = 2;
        return TITLE_E_IO;
    }
    return TITLE_OK;
}

int hf_install_title(const HfInstallJob *job, HfInstallResult *res) {
    HfRoutes routes;
    HfRoute route;
    HfSetTitle *t = NULL;
    int fresh = 0, rc = TITLE_E_ARG;
    if (!job || !res || !job->run || !job->am.write) return TITLE_E_ARG;
    memset(res, 0, sizeof *res);
    if (!hf_title_ours(job->in.title_id)) {   /* never another title's removal, ticket or import (launcher.h) */
        LOGJ("title %08lX%08lX is not Heavenfall's: nothing is removed or installed",
             (unsigned long)(job->in.title_id >> 32), (unsigned long)(job->in.title_id & 0xFFFFFFFFu));
        res->rc = TITLE_E_ARG;
        return TITLE_E_ARG;
    }
    hf_routes_init(&routes, job->in.use_slot);
    while ((route = hf_routes_next(&routes)) != HF_ROUTE_NONE) {
        int want = hf_route_uses_slot(route);
        res->attempts++;
        res->am_step = 0;
        res->am = 0;   /* a route's own answer only: a write refused by AM is the app's to fill (HfAm.write) */
        LOGJ("route %d: %s", res->attempts, hf_route_name(route));
        if (!t || !fresh || hf_set_title_slot(t) != want) {
            HfSetTitleIn in = job->in;
            uint64_t began = now(job);
            hf_set_title_close(t);
            t = NULL;
            in.use_slot = want;
            in.log = job->log;
            in.now_ms = job->now_ms;
            phase(job, want ? HT_PHASE_OPEN : HT_PHASE_OPEN_SIZING);
            rc = hf_set_title_open(&t, job->read, job->read_ctx, job->set_handle, job->set_size, job->dump, &in);
            timed(job, want ? "open the set, make the executable" : "open the set, make the executable, size the ARCs",
                  began, 0);
            if (rc) {
                LOGJ("the set does not open for this dump: %d", rc);
                hf_routes_failed(&routes, route, HF_FAIL_STOP);
                continue;
            }
            LOGJ("set: %u files, %lu MB of mod files; slot %s (%d)", (unsigned)hf_set_title_file_count(t),
                 (unsigned long)(hf_set_title_mod_bytes(t) >> 20), hf_set_title_slot(t) ? "used" : "not used",
                 hf_set_title_slot_rc(t));
            fresh = 1;
        }
        if (want && !hf_set_title_slot(t)) {   /* the slot is not this title's: the same build, hashed here */
            LOGJ("route %d: the slot does not fit (%d): no one-pass route", res->attempts, hf_set_title_slot_rc(t));
            if (job->notice) job->notice(job->ui_ctx, HT_ROUTE_SLOT);
            hf_routes_failed(&routes, route, HF_FAIL_SLOT);
            res->attempts--;
            continue;
        }
        fresh = 0;
        rc = attempt(job, t, route, res);
        LOGJ("route %d: %s -> %d (AM step %d, 0x%08lX)", res->attempts, hf_route_name(route), rc, res->am_step,
             (unsigned long)(uint32_t)res->am);
        hf_set_title_close(t);
        t = NULL;
        if (!rc) {
            res->route = route;
            break;
        }
        {
            HfFail why = hf_route_failure(route, rc, res->am_step);
            hf_routes_failed(&routes, route, why);
            if (why != HF_FAIL_STOP && job->notice)
                job->notice(job->ui_ctx, why == HF_FAIL_SLOT ? HT_ROUTE_SLOT : why == HF_FAIL_AM ? HT_ROUTE_AM
                                                                                                : HT_ROUTE_RETRY);
        }
    }
    hf_set_title_close(t);
    res->rc = rc;
    return rc;
}
