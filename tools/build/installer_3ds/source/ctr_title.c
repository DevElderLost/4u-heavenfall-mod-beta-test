#include "ctr_title.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "launcher.h"
#include "uimodel.h"

#define AM_BUFFER (512 * 1024)   /* writes to AM go in blocks: every call is a service request */
#define IO_CHUNK (1u << 20)

typedef struct {
    Handle handle;
} SdFile;

static const char *without_scheme(const char *path) {
    return strncmp(path, "sdmc:", 5) ? path : path + 5;
}

static Result open_direct(Handle *h, const char *path, u32 flags) {
    return FSUSER_OpenFileDirectly(h, ARCHIVE_SDMC, fsMakePath(PATH_EMPTY, ""),
                                   fsMakePath(PATH_ASCII, without_scheme(path)), flags, 0);
}

static int file_open(void *ctx, const char *path, void **handle, uint64_t *size) {
    SdFile *f = (SdFile *)malloc(sizeof *f);
    u64 n = 0;
    (void)ctx;
    if (!f) return 1;
    if (R_FAILED(open_direct(&f->handle, path, FS_OPEN_READ)) || R_FAILED(FSFILE_GetSize(f->handle, &n))) {
        free(f);
        return 1;
    }
    *handle = f;
    *size = n;
    return 0;
}

static void file_close(void *ctx, void *handle) {
    (void)ctx;
    FSFILE_Close(((SdFile *)handle)->handle);
    free(handle);
}

static int file_read(void *ctx, void *handle, uint64_t offset, void *buf, size_t n) {
    Handle h = ((SdFile *)handle)->handle;
    uint8_t *p = (uint8_t *)buf;
    (void)ctx;
    while (n) {
        u32 want = n < IO_CHUNK ? (u32)n : IO_CHUNK, got = 0;
        if (R_FAILED(FSFILE_Read(h, &got, offset, p, want)) || !got) return 1;
        p += got;
        offset += got;
        n -= got;
    }
    return 0;
}

void ctr_file_api(FileApi *api) {
    api->open = file_open;
    api->close = file_close;
    api->read = file_read;
    api->ctx = NULL;
}

int ctr_file_size(const char *path, uint64_t *size) {
    void *h;
    if (file_open(NULL, path, &h, size)) return 1;
    file_close(NULL, h);
    return 0;
}

/* ---- AM ---- */

struct CtrAm {
    Handle handle;
    uint64_t at;
    uint8_t *buf;
    size_t used;
    int failed;
    Result write_result;   /* what AM answered the write it refused */
};

CtrAm *ctr_am_begin(Result *result) {
    CtrAm *am = (CtrAm *)calloc(1, sizeof *am);
    Result rc;
    if (!am) { *result = -1; return NULL; }
    am->buf = (uint8_t *)malloc(AM_BUFFER);
    if (!am->buf) { free(am); *result = -1; return NULL; }
    rc = AM_StartCiaInstall(MEDIATYPE_SD, &am->handle);
    *result = rc;
    if (R_FAILED(rc)) { free(am->buf); free(am); return NULL; }
    return am;
}

static int am_flush(CtrAm *am) {
    u32 written = 0;
    Result rc;
    if (!am->used) return 0;
    if (R_FAILED(rc = FSFILE_Write(am->handle, &written, am->at, am->buf, (u32)am->used, 0)) || written != am->used) {
        am->failed = 1;
        am->write_result = R_FAILED(rc) ? rc : -1;
        return 1;
    }
    am->at += am->used;
    am->used = 0;
    return 0;
}

int ctr_am_write(void *ctx, const void *buf, size_t n) {
    CtrAm *am = (CtrAm *)ctx;
    const uint8_t *p = (const uint8_t *)buf;
    if (am->failed) return 1;
    while (n) {
        size_t room = AM_BUFFER - am->used, k = n < room ? n : room;
        memcpy(am->buf + am->used, p, k);
        am->used += k;
        p += k;
        n -= k;
        if (am->used == AM_BUFFER && am_flush(am)) return 1;
    }
    return 0;
}

Result ctr_am_finish(CtrAm *am) {
    Result rc;
    if (am_flush(am)) {
        AM_CancelCIAInstall(am->handle);
        rc = -2;
    } else {
        rc = AM_FinishCiaInstall(am->handle);
    }
    free(am->buf);
    free(am);
    return rc;
}

Result ctr_am_write_result(const CtrAm *am) { return am ? am->write_result : 0; }

void ctr_am_cancel(CtrAm *am) {
    AM_CancelCIAInstall(am->handle);
    free(am->buf);
    free(am);
}

/* ---- AM piece by piece ---- */

#define PARTS_CHUNK (1u << 20)
#define TMD_UNKNOWN_FLAG true     /* AM_InstallTmdFinish's flag as FBI and probe P0 pass it */

struct CtrParts {
    uint64_t title_id;
    Handle content;
    int content_open;
    uint64_t at;
    int failed;
    Result contexts_result;   /* AM_CreateImportContentContexts's answer when it was asked, for the log */
    Result write_result;      /* what AM answered the write it refused */
};

Result ctr_parts_write_result(const CtrParts *p) { return p ? p->write_result : 0; }

static Result write_handle(Handle h, const void *buf, size_t n, uint64_t at) {
    const uint8_t *p = (const uint8_t *)buf;
    while (n) {
        u32 want = n < PARTS_CHUNK ? (u32)n : PARTS_CHUNK, written = 0;
        Result rc = FSFILE_Write(h, &written, at, p, want, 0);
        if (R_FAILED(rc)) return rc;
        if (written != want) return -1;
        p += want;
        at += want;
        n -= want;
    }
    return 0;
}

/* Bytes of the certificate at p (signature, 0x88-byte header, key), 0 if not one. */
static size_t cert_size(const uint8_t *p, size_t left) {
    u32 sig, sig_len, body, key;
    if (left < 4) return 0;
    sig = (u32)p[0] << 24 | (u32)p[1] << 16 | (u32)p[2] << 8 | p[3];
    sig_len = (sig == 0x10000 || sig == 0x10003) ? 0x200 : (sig == 0x10001 || sig == 0x10004) ? 0x100 : 0;
    if (!sig_len) return 0;
    body = 4 + sig_len + 0x3C;
    if (left < body + 0x44) return 0;
    key = (u32)p[body + 0x40] << 24 | (u32)p[body + 0x41] << 16 | (u32)p[body + 0x42] << 8 | p[body + 0x43];
    body += 0x88 + (key == 0 ? 0x238 : key == 1 ? 0x138 : 0x78);
    return body <= left ? body : 0;
}

/* The chain (CA, the ticket's signer, the TMD's) into the console's certificate store. */
static Result import_certs(const uint8_t *certs, size_t len) {
    size_t a = cert_size(certs, len), b, c;
    if (!a) return -1;
    b = cert_size(certs + a, len - a);
    if (!b) return -1;
    c = cert_size(certs + a + b, len - a - b);
    if (!c) return -1;
    return AM_ImportCertificates((u32)a, (void *)certs, (u32)b, (void *)(certs + a), (u32)c, (void *)(certs + a + b),
                                 0, NULL);
}

CtrParts *ctr_parts_begin(uint64_t title_id, const uint8_t *certs, size_t certs_len, const uint8_t *ticket,
                          size_t ticket_len, Result *result) {
    CtrParts *p;
    Handle h;
    Result rc;
    if (!hf_title_ours(title_id)) {   /* never a ticket or an import of another title (launcher.h) */
        *result = -1;
        return NULL;
    }
    rc = import_certs(certs, certs_len);
    *result = rc;
    if (R_FAILED(rc)) return NULL;
    if (R_FAILED(rc = AM_InstallTicketBegin(&h))) { *result = rc; return NULL; }
    if (R_FAILED(rc = write_handle(h, ticket, ticket_len, 0))) {
        AM_InstallTicketAbort(h);
        *result = rc;
        return NULL;
    }
    if (R_FAILED(rc = AM_InstallTicketFinish(h)) || R_FAILED(rc = AM_InstallTitleBegin(MEDIATYPE_SD, title_id, false))) {
        *result = rc;
        return NULL;
    }
    p = (CtrParts *)calloc(1, sizeof *p);
    if (!p) {
        AM_InstallTitleAbort();
        *result = -1;
        return NULL;
    }
    p->title_id = title_id;
    return p;
}

Result ctr_parts_tmd(CtrParts *p, const uint8_t *tmd, size_t len) {
    Handle h;
    Result rc;
    (void)p;
    if (R_FAILED(rc = AM_InstallTmdBegin(&h))) return rc;
    if (R_FAILED(rc = write_handle(h, tmd, len, 0))) {
        AM_InstallTmdAbort(h);
        return rc;
    }
    return AM_InstallTmdFinish(h, TMD_UNKNOWN_FLAG);
}

/* The TMD's finish with TMD_UNKNOWN_FLAG set makes the content contexts from the TMD itself (Azahar's EndImportTmd
 * takes it as "create_context"); asking again is refused with InvalidState (0xD8A08004, seen on a real console). So
 * the explicit call's answer is kept for the log and the content begins either way. */
Result ctr_parts_content_begin(CtrParts *p) {
    u16 index = 0;
    Result rc;
    p->contexts_result = TMD_UNKNOWN_FLAG ? 0 : AM_CreateImportContentContexts(1, &index);
    rc = AM_InstallContentBegin(&p->content, 0);
    if (R_FAILED(rc) && TMD_UNKNOWN_FLAG) {   /* no contexts after all: make them, then begin again */
        p->contexts_result = AM_CreateImportContentContexts(1, &index);
        if (R_SUCCEEDED(p->contexts_result)) rc = AM_InstallContentBegin(&p->content, 0);
    }
    if (R_SUCCEEDED(rc)) p->content_open = 1;
    return rc;
}

Result ctr_parts_contexts_result(const CtrParts *p) { return p ? p->contexts_result : 0; }

int ctr_parts_write(void *ctx, const void *buf, size_t n) {
    CtrParts *p = (CtrParts *)ctx;
    Result rc = 0;
    if (p->failed || !p->content_open || R_FAILED(rc = write_handle(p->content, buf, n, p->at))) {
        if (!p->failed) p->write_result = R_FAILED(rc) ? rc : -1;
        p->failed = 1;
        return 1;
    }
    p->at += n;
    return 0;
}

Result ctr_parts_content_finish(CtrParts *p) {
    Result rc;
    if (p->failed) return -2;
    rc = AM_InstallContentFinish(p->content);
    p->content_open = 0;
    return rc;
}

Result ctr_parts_commit(CtrParts *p) {
    u64 id = p->title_id;
    Result rc = AM_InstallTitleFinish();
    if (R_SUCCEEDED(rc)) rc = AM_CommitImportTitles(MEDIATYPE_SD, 1, false, &id);
    else AM_InstallTitleAbort();
    free(p);
    return rc;
}

void ctr_parts_abort(CtrParts *p) {
    if (!p) return;
    if (p->content_open) AM_InstallContentCancel(p->content);
    AM_InstallTitleAbort();
    free(p);
}

/* ---- AM's pending imports ---- */

#define PENDING_MASK (AM_STATUS_MASK_INSTALLING | AM_STATUS_MASK_AWAITING_FINALIZATION)
#define PENDING_MAX 4096u   /* more pending titles than a card could hold: AM's answer is not taken */

int ctr_pending_clear(uint64_t title_id, char *log_line, size_t cap) {
    u32 count = 0, read = 0, i;
    u64 *ids;
    int found = 0;
    size_t n;
    Result rc;
    if (!hf_title_ours(title_id)) return -1;   /* another title's import is never touched (launcher.h) */
    rc = AM_GetPendingTitleCount(&count, MEDIATYPE_SD, PENDING_MASK);
    if (log_line && cap) snprintf(log_line, cap, "pending titles: 0x%08lX, %lu", (unsigned long)rc, (unsigned long)count);
    if (R_FAILED(rc) || count > PENDING_MAX) return -1;
    if (!count) return 0;
    if (!(ids = (u64 *)malloc(count * sizeof *ids))) return -1;
    rc = AM_GetPendingTitleList(&read, count, MEDIATYPE_SD, PENDING_MASK, ids);
    for (i = 0; R_SUCCEEDED(rc) && i < read && i < count; i++)
        if (ids[i] == title_id) found = 1;
    free(ids);
    if (!found) return 0;
    {
        AM_PendingTitleEntry info;
        u64 id = title_id;
        memset(&info, 0, sizeof info);
        rc = AM_GetPendingTitleInfo(1, MEDIATYPE_SD, &id, &info);
        n = log_line ? strlen(log_line) : 0;
        if (log_line && n < cap)
            snprintf(log_line + n, cap - n, "; ours: info 0x%08lX, version %u, status 0x%04X", (unsigned long)rc,
                     (unsigned)info.version, (unsigned)info.status);
    }
    rc = AM_DeletePendingTitle(MEDIATYPE_SD, title_id);
    n = log_line ? strlen(log_line) : 0;
    if (log_line && n < cap) snprintf(log_line + n, cap - n, ", deleted 0x%08lX", (unsigned long)rc);
    return R_SUCCEEDED(rc) ? 1 : -1;
}

/* ---- the fast builder's threads ---- */

#define READER_STACK (256 * 1024)   /* the reader also runs the patch set's applier: inflate, its ops buffer */
/* The hasher enters through the same stage_thread, whose worst path (the reader's: 31 KB) plus the libraries' frames
 * passes 32 KB; tests/install/title/test_app_stacks.py sizes every thread. */
#define HASHER_STACK (64 * 1024)

static void sync_lock(void *ctx) { LightLock_Lock(&((CtrSync *)ctx)->lock); }
static void sync_unlock(void *ctx) { LightLock_Unlock(&((CtrSync *)ctx)->lock); }
static void sync_wait(void *ctx) { CondVar_Wait(&((CtrSync *)ctx)->cond, &((CtrSync *)ctx)->lock); }
static void sync_wake(void *ctx) { CondVar_Broadcast(&((CtrSync *)ctx)->cond); }

void ctr_sync_init(CtrSync *c, StreamSync *s) {
    LightLock_Init(&c->lock);
    CondVar_Init(&c->cond);
    s->lock = sync_lock;
    s->unlock = sync_unlock;
    s->wait = sync_wait;
    s->wake = sync_wake;
    s->ctx = c;
}

typedef struct {
    Stream *s;
    unsigned stages;
} StageWork;

static void stage_thread(void *arg) {
    StageWork *w = (StageWork *)arg;
    stream_work(w->s, w->stages);
}

int ctr_stream_run(Stream *s) {
    StageWork reader = {s, STREAM_READ}, hasher = {s, STREAM_HASH};
    Thread tr, th;
    s32 prio = 0x30;
    bool n3ds = false;
    unsigned mine = STREAM_WRITE;
    int rc;
    svcGetThreadPriority(&prio, CUR_THREAD_HANDLE);
    APT_CheckNew3DS(&n3ds);
    /* The reader waits on the SD card most of the time: above the UI's priority. The hasher only computes: below it,
     * or on core 2 of a New 3DS. Which core of an old 3DS suits it best is probe P0's question. */
    tr = threadCreate(stage_thread, &reader, READER_STACK, prio - 1, -2, false);
    th = threadCreate(stage_thread, &hasher, HASHER_STACK, n3ds ? prio : prio + 1, n3ds ? 2 : -2, false);
    if (!tr) mine |= STREAM_READ;
    if (!th) mine |= STREAM_HASH;
    rc = stream_work(s, mine);
    if (tr) { threadJoin(tr, U64_MAX); threadFree(tr); }
    if (th) { threadJoin(th, U64_MAX); threadFree(th); }
    return rc ? rc : stream_result(s);
}

int ctr_title_installed(uint64_t title_id) {
    u32 count = 0, read = 0, i;
    u64 *ids;
    int found = 0;
    if (R_FAILED(AM_GetTitleCount(MEDIATYPE_SD, &count)) || !count) return 0;
    ids = (u64 *)malloc(count * sizeof *ids);
    if (!ids) return 0;
    if (R_SUCCEEDED(AM_GetTitleList(&read, MEDIATYPE_SD, count, ids)))
        for (i = 0; i < read; i++) found |= ids[i] == title_id;
    free(ids);
    return found;
}

Result ctr_title_delete(uint64_t title_id) {
    if (!hf_title_ours(title_id)) return -1;   /* never another title (launcher.h) */
    return AM_DeleteTitle(MEDIATYPE_SD, title_id);
}

uint64_t ctr_sd_free(void) {
    FS_ArchiveResource sd;
    if (R_FAILED(FSUSER_GetArchiveResource(&sd, SYSTEM_MEDIATYPE_SD))) return 0;
    return (uint64_t)sd.freeClusters * sd.clusterSize;
}

/* ---- the game data title, opened as the game will ---- */

int ctr_game_check(uint64_t game_title_id, char *line, size_t cap) {
    /* archive 0x2345678A, as libctru's romfsMountFromTitle opens it: archive path (16 bytes) the title id, the media
     * type and 0; file path (20 bytes) all 0: content 0's RomFS. */
    u32 archive[4] = {(u32)game_title_id, (u32)(game_title_id >> 32), MEDIATYPE_SD, 0};
    u32 file[5] = {0, 0, 0, 0, 0};
    FS_Path apath = {PATH_BINARY, sizeof archive, archive}, fpath = {PATH_BINARY, sizeof file, file};
    Handle fd = 0;
    u8 head[0x60], l3[8];
    u32 got = 0;
    u64 at = 0;
    Result rc = FSUSER_OpenFileDirectly(&fd, (FS_ArchiveID)0x2345678A, apath, fpath, FS_OPEN_READ, 0);
    if (line && cap) snprintf(line, cap, "open 0x%08lX", (unsigned long)rc);
    if (R_FAILED(rc)) return HF_E_GAME_CHECK;
    rc = FSFILE_Read(fd, &got, 0, head, sizeof head);
    if (line && cap) snprintf(line + strlen(line), cap - strlen(line), ", header 0x%08lX (%lu bytes)", (unsigned long)rc,
                              (unsigned long)got);
    if (R_FAILED(rc) || got != sizeof head || hf_romfs_level3_at(head, sizeof head, &at)) {
        FSFILE_Close(fd);
        return HF_E_GAME_CHECK;
    }
    rc = FSFILE_Read(fd, &got, at, l3, sizeof l3);
    FSFILE_Close(fd);
    if (line && cap) snprintf(line + strlen(line), cap - strlen(line), ", level 3 at 0x%lX 0x%08lX (%lu bytes)",
                              (unsigned long)at, (unsigned long)rc, (unsigned long)got);
    return R_FAILED(rc) || got != sizeof l3 || !hf_romfs_level3_ok(l3, sizeof l3) ? HF_E_GAME_CHECK : 0;
}
