/* From a downloaded patch set to the installed title: the set is applied to the
 * player's dump straight into the title builder, nothing written on the card on the way (settitle.c), and the title
 * goes into AM by the first route AM takes (hf_install_title): piece by piece with the TMD first, its hash from the
 * set's build data, then a CIA with it, then each after a hash pass of the console's own. The game is read once on the
 * first route. Nothing is installed on a cancel or an error: AM's import is aborted and the old title stays. Every
 * attempt, AM's answers and each phase's time and rate go to the log. */
#include <malloc.h>
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "build.h"
#include "ctr_title.h"
#include "hf_tuning.h"
#include "hfnet.h"
#include "patchset.h"
#include "settitle.h"
#include "srcfiles.h"

#define BUFFERS 4                        /* the stream's ring: reading, hashing and writing each hold one */
#define BUFFER_SIZE (1u << 20)
#define KEEP_BUDGET (16ull * 1024 * 1024) /* deflated ARC entries kept between sizing and writing (no build data) */
#define ICON24_SIZE (24 * 24 * 2)
#define ICON48_SIZE (48 * 48 * 2)

Result install_am_result;   /* what AM answered at the step that failed, for the message */
uint32_t room_missing_mb;   /* the MB the card lacked (on_room, or a download's no room): the message's "Free {}" */
int install_old_removed;    /* remove_old took the installed title away (app.h) */
int install_xx_by_files;    /* xx_files_check found the XX dump equal by files, not by its revision hash */
static char install_xx_hash[65];   /* the XX dump the title is built with (hf_hex), for installed.json */
char install_xx_differs[65];

/* ---- AM, as hf_install_title asks for it ---- */

typedef struct {
    CtrParts *parts;
    CtrAm *cia;
    uint64_t title_id;      /* whose pending imports are cleared before a route and after a failed one */
    Result write_result;    /* AM's answer to the write it refused (the route's own begin and finish are res.am) */
} AmState;

/* AM's pending imports of the title deleted (a cut or refused try leaves one, and the next TMD or CIA is answered
 * "already exists", 0xC8E083FC, seen on a real console), with what AM had in the log. */
static void pending_clear(const AmState *a, const char *when) {
    char line[200] = "";
    int rc = ctr_pending_clear(a->title_id, line, sizeof line);
    LOG("AM %s: %s -> %d", when, line, rc);
}

static int32_t failed(Result rc) { return R_FAILED(rc) ? (int32_t)rc : 0; }

static int32_t parts_begin(void *ctx, const TitleBuild *tb) {
    AmState *a = (AmState *)ctx;
    uint8_t ticket[CIA_TICKET_SIZE];
    size_t certs_len = 0;
    const uint8_t *certs = title_build_certs(tb, &certs_len);
    Result rc = 0;
    title_build_ticket(tb, ticket);
    a->parts = ctr_parts_begin(title_build_id(tb), certs, certs_len, ticket, sizeof ticket, &rc);
    return a->parts ? 0 : R_FAILED(rc) ? (int32_t)rc : -1;
}

static int32_t parts_tmd(void *ctx, const uint8_t *tmd, size_t len) {
    return failed(ctr_parts_tmd(((AmState *)ctx)->parts, tmd, len));
}

static int32_t parts_content(void *ctx) {
    CtrParts *p = ((AmState *)ctx)->parts;
    Result rc = ctr_parts_content_begin(p);
    LOG("AM parts: content contexts 0x%08lX, content begin 0x%08lX", (unsigned long)ctr_parts_contexts_result(p),
        (unsigned long)rc);
    return failed(rc);
}

static int32_t parts_finish(void *ctx) {
    AmState *a = (AmState *)ctx;
    Result rc = ctr_parts_content_finish(a->parts);
    if (R_FAILED(rc)) {
        ctr_parts_abort(a->parts);
        a->parts = NULL;
        return (int32_t)rc;
    }
    rc = ctr_parts_commit(a->parts);
    a->parts = NULL;
    return failed(rc);
}

static void parts_abort(void *ctx) {
    AmState *a = (AmState *)ctx;
    ctr_parts_abort(a->parts);
    a->parts = NULL;
    pending_clear(a, "after the aborted import");
}

static int32_t cia_begin(void *ctx) {
    AmState *a = (AmState *)ctx;
    Result rc = 0;
    a->cia = ctr_am_begin(&rc);
    return a->cia ? 0 : R_FAILED(rc) ? (int32_t)rc : -1;
}

static int32_t cia_finish(void *ctx) {
    AmState *a = (AmState *)ctx;
    Result rc = ctr_am_finish(a->cia);
    a->cia = NULL;
    return failed(rc);
}

static void cia_cancel(void *ctx) {
    AmState *a = (AmState *)ctx;
    if (a->cia) ctr_am_cancel(a->cia);
    a->cia = NULL;
    pending_clear(a, "after the cancelled CIA");
}

/* The title as installed now taken away right before AM's import (settitle.h, HfAm.remove_old): AM refuses to import
 * over an installed title, even of a higher version (0xC8E083FC on both routes). As FBI does
 * before every CIA install over a title: AM_DeleteTitle, the ticket, then the SD card's title database checked.
 * AM_DeleteTitle takes the title's save too: install_set backs it up first, through FS and as its raw
 * file, and puts it back after the import (app_saves.c; the copies are deep, and a callback must stay shallow for the
 * stream's threads' stack audit). */
static int32_t remove_old(void *ctx) {
    AmState *a = (AmState *)ctx;
    Result rc;
    if (!hf_title_ours(a->title_id)) return -1;   /* never another title (launcher.h; hf_install_title asked too) */
    if (!ctr_title_installed(a->title_id)) {
        LOG("install: %016llX is not installed: nothing to remove", (unsigned long long)a->title_id);
        return 0;
    }
    rc = AM_DeleteTitle(MEDIATYPE_SD, a->title_id);
    LOG("install: AM_DeleteTitle %016llX: 0x%08lX", (unsigned long long)a->title_id, (unsigned long)rc);
    if (R_FAILED(rc)) return rc;
    install_old_removed = 1;   /* from here a stop leaves no title of this kind: the record and the message say so */
    rc = AM_DeleteTicket(a->title_id);
    LOG("install: AM_DeleteTicket: 0x%08lX", (unsigned long)rc);
    AM_QueryAvailableExternalTitleDatabase(NULL);
    return 0;
}

static int am_write(void *ctx, const void *buf, size_t n) {
    AmState *a = (AmState *)ctx;
    if (a->parts) {
        if (!ctr_parts_write(a->parts, buf, n)) return 0;
        a->write_result = ctr_parts_write_result(a->parts);
    } else if (a->cia) {
        if (!ctr_am_write(a->cia, buf, n)) return 0;
        a->write_result = ctr_am_write_result(a->cia);
    }
    LOG("AM refused a write: 0x%08lX", (unsigned long)a->write_result);
    return HF_E_AM_WRITE;
}

/* ---- the builder's passes on the console's threads, the screen ---- */

static int run_pass(void *ctx, TitleBuild *tb, TitlePass pass, const TitleOut *out) {
    CtrSync cs;
    StreamSync ss;
    StreamSetup setup;
    Stream *s = NULL;
    int rc;
    (void)ctx;
    ctr_sync_init(&cs, &ss);
    setup.buffers = BUFFERS;
    setup.buffer_size = BUFFER_SIZE;
    setup.sync = &ss;
    if ((rc = title_build_begin(tb, pass, out, &setup, ui_progress, NULL, &s))) return rc;
    ctr_stream_run(s);
    return title_build_end(tb, s);
}

static void on_phase(void *ctx, HfText name) {
    (void)ctx;
    ui_phase(name);
}

/* A fallback route: said in the log only (the player sees the bar planned again, not the route), and the rest of the
 * install planned again for the work it repeats. */
static void on_notice(void *ctx, HfText text) {
    (void)ctx;
    LOG("install: %s", hf_text(HF_LANG_EN, text));
    task_route_again();
}

/* The title's exact size, before AM is asked: the room on the card (HF_E_DISK and the MB missing when it lacks), and
 * the bar's plan for it. */
static int on_room(void *ctx, uint64_t bytes) {
    uint64_t free_bytes = ctr_sd_free();
    (void)ctx;
    room_missing_mb = hf_room_missing_mb(free_bytes, bytes, (uint64_t)HF_TUNE_SD_SPARE_MB << 20);
    LOG("install: %lu MB into AM, free %lu MB, missing %lu MB", (unsigned long)(bytes >> 20),
        (unsigned long)(free_bytes >> 20), (unsigned long)room_missing_mb);
    if (room_missing_mb) return HF_E_DISK;
    task_title_size(bytes);
    return 0;
}

/* ---- the title's own files ---- */

static int read_asset(const char *name, uint8_t *out, size_t size) {
    char path[64];
    FILE *f;
    size_t got;
    snprintf(path, sizeof path, "romfs:/%s", name);
    f = fopen(path, "rb");
    if (!f) return 1;
    got = fread(out, 1, size, f);
    fclose(f);
    return got != size;
}

/* The title's SMDH (the game's own, retitled, with the edition's icons) and the CIA's certificate chain. */
static int title_files(const FileApi *api, const Dump *d, uint8_t *smdh, uint8_t *certs) {
    uint8_t *game = (uint8_t *)malloc(HF_SMDH_SIZE), *icon24 = (uint8_t *)malloc(ICON24_SIZE),
            *icon48 = (uint8_t *)malloc(ICON48_SIZE);
    char name_long[80];
    int rc = TITLE_E_FORMAT;
    size_t i;
    if (!game || !icon24 || !icon48) { rc = TITLE_E_MEM; goto out; }
    for (i = 0; i < d->nexefs; i++)
        if (!strcmp(d->exefs[i].name, "icon") && d->exefs[i].len >= HF_SMDH_SIZE)
            rc = api->read(api->ctx, d->handle, d->exefs[i].offset, game, HF_SMDH_SIZE) ? TITLE_E_IO : 0;
    if (rc) { LOG("install: the game's icon file is missing or unreadable: %d", rc); goto out; }
    if (read_asset("certs.bin", certs, PACK_CERTS_SIZE) || read_asset("icon24.bin", icon24, ICON24_SIZE) ||
        read_asset("icon48.bin", icon48, ICON48_SIZE)) {
        LOG("install: the app's own assets (certs, icons) are missing");
        rc = TITLE_E_IO;
        goto out;
    }
    snprintf(name_long, sizeof name_long, "Monster Hunter 4 Ultimate: %s", app_edition()->name);
    if (hf_smdh_make(game, app_edition()->name, name_long, "Heavenfall", icon24, icon48, smdh)) rc = TITLE_E_FORMAT;
out:
    free(game);
    free(icon24);
    free(icon48);
    return rc;
}

/* installed.json, written whole. */
static void record_write(const HfInstalled *rec, int region) {
    char path[256], text[HF_INSTALLED_MAX];
    int n = hf_installed_format(rec, region_name(region), text, sizeof text);
    if (n < 0 || hf_path_installed(app_edition()->slug, path, sizeof path)) return;
    if (write_whole(path, text, (size_t)n)) LOG("installed.json: not written");
}

/* The mod title's record as it stands (the game data's fields kept from `base`, the layout too until the mod is whole). */
static void record(const HfInstalled *base, const char *version, unsigned tmd, int region, int complete, int xx,
                   int no_room, int save_pending, const char *save_restore) {
    HfInstalled rec;
    memset(&rec, 0, sizeof rec);
    if (base) rec = *base;
    snprintf(rec.version, sizeof rec.version, "%s", version);
    rec.tmd = tmd;
    rec.complete = complete;
    rec.xx = xx;
    rec.xx_no_room = no_room;
    rec.save_pending = save_pending;
    snprintf(rec.save_restore, sizeof rec.save_restore, "%s", save_restore);
    if (!xx) snprintf(rec.xx_dump, sizeof rec.xx_dump, "%s", install_xx_differs);
    else if (complete && install_xx_hash[0]) snprintf(rec.xx_dump, sizeof rec.xx_dump, "%s", install_xx_hash);
    if (complete) rec.layout = 2;      /* the mod is whole: the title is the split one */
    else if (!rec.layout) rec.layout = 1;
    record_write(&rec, region);
}

void installed_save_done(void) {
    HfInstalled rec;
    if (!read_installed_record(&rec) || !rec.save_pending) return;
    rec.save_pending = 0;
    record_write(&rec, app.status.installed_region >= 0 ? app.status.installed_region : REGION_EUR);
    app.status.save_pending = 0;
    LOG("installed.json: the save copy is no longer pending");
}

void installed_restore_done(void) {
    HfInstalled rec;
    app.status.save_restore[0] = 0;
    if (!read_installed_record(&rec) || !rec.save_restore[0]) return;
    rec.save_restore[0] = 0;
    record_write(&rec, app.status.installed_region >= 0 ? app.status.installed_region : REGION_EUR);
    LOG("installed.json: the save is back, nothing left to restore");
}

/* ---- the install ---- */

extern u32 __ctru_heap_size;

/* The heap's size and use, for the log: an out-of-memory stop says how much there was, the most it ever held (the
 * arena only grows) and the allocations refused (app_log.c counts them). */
static void log_memory(const char *when) {
    struct mallinfo mi = mallinfo();
    LOG("memory %s: heap %lu KB, in use %lu KB, at most %lu KB; refused %lu (the last of %lu KB)", when,
        (unsigned long)(__ctru_heap_size >> 10), (unsigned long)(mi.uordblks >> 10), (unsigned long)(mi.arena >> 10),
        (unsigned long)app_refused.count, (unsigned long)(app_refused.last >> 10));
}

/* MH XX's dump against an XX set: the RomFS superblock hash is a hint;
 * when it is not the set's, the set's second-game files are compared with the dump's (path, size, SHA-256) before
 * anything is written. *match 1: the dump can be used (install_xx_by_files then says install_set to take it for the
 * set's). Another file is no error: *match 0 and the XX set is left out. A TITLE_* code for the dump or the set that
 * cannot be read. */
int xx_files_check(const char *set_path, int *match) {
    FileApi api;
    void *set_h = NULL, *xx_h = NULL;
    uint64_t set_size = 0, xx_size = 0;
    Dump xx;
    Patchset *ps = NULL;
    uint8_t set_hash[32];
    int rc, xx_ok = 0;
    u64 t = osGetTime();
    *match = 0;
    install_xx_by_files = 0;
    ctr_file_api(&api);
    if (api.open(api.ctx, set_path, &set_h, &set_size) || api.open(api.ctx, app.status.xx_path, &xx_h, &xx_size) ||
        dump_open(&xx, api.read, api.ctx, xx_h)) {
        rc = TITLE_E_IO;
        goto out;
    }
    xx_ok = 1;
    if ((rc = patchset_open(&ps, api.read, api.ctx, set_h, set_size, 0))) goto out;
    if (!patchset_second_game(ps, NULL, set_hash)) goto out;   /* a set without MH XX: nothing to check */
    if (!memcmp(xx.header + DUMP_ROMFS_HASH, set_hash, 32)) {
        *match = 1;
        LOG("MH XX: the dump is the revision the set names");
        goto out;
    }
    ui_phase(HT_PHASE_XX_FILES);
    rc = hf_second_game_by_files(ps, &xx, ui_progress, NULL);
    LOG("MH XX: another revision than the set's; its files checked one by one: %d", rc);
    hf_log_phase(&app.log, osGetTime(), "MH XX files", t, 0);
    if (rc == TITLE_OK) {
        *match = 1;
        install_xx_by_files = 1;
    } else if (rc == TITLE_E_GAME || rc == TITLE_E_HASH) {
        rc = TITLE_OK;   /* a file the set reads is another: the XX set is left out */
    }
out:
    if (ps) patchset_close(ps);
    if (xx_ok) dump_close(&xx);
    if (set_h) api.close(api.ctx, set_h);
    if (xx_h) api.close(api.ctx, xx_h);
    return rc;
}

/* The XX dump opened for the install takes the set's recorded revision: its files were checked equal. */
static int xx_adopt(const FileApi *api, void *set_h, uint64_t set_size, Dump *xx) {
    Patchset *ps = NULL;
    uint8_t hash[32];
    int rc = patchset_open(&ps, api->read, api->ctx, set_h, set_size, 0);
    if (rc) return rc;
    if (patchset_second_game(ps, NULL, hash)) memcpy(xx->header + DUMP_ROMFS_HASH, hash, 32);
    patchset_close(ps);
    return TITLE_OK;
}

int install_set(const char *set_path, const char *version, int xx, int no_room, HfTitleKind kind) {
    FileApi api;
    void *set_h = NULL, *dump_h = NULL, *xx_h = NULL;
    uint64_t set_size = 0, dump_size = 0, xx_size = 0, title_id = 0;
    uint8_t *smdh = (uint8_t *)malloc(HF_SMDH_SIZE), *certs = (uint8_t *)malloc(PACK_CERTS_SIZE);
    uint16_t tmd = 0;
    Dump dump, xx_dump;
    AmState am;
    HfInstallJob job;
    HfInstallResult res;
    HfInstalled prev, cur;
    char raw_stamp[18] = "", restore[18] = "";
    u64 t_all = osGetTime();
    int rc = 0, dump_ok = 0, xx_ok = 0, region = REGION_EUR, had_record = 0, marked = 0, pending = 0, part = 0;
    const int game = kind == HF_TITLE_GAME;

    ctr_file_api(&api);
    memset(&am, 0, sizeof am);
    memset(&job, 0, sizeof job);
    memset(&res, 0, sizeof res);
    memset(&prev, 0, sizeof prev);
    install_am_result = 0;
    room_missing_mb = 0;
    install_old_removed = 0;
    log_memory("at the start");
    if (!smdh || !certs) { rc = TITLE_E_MEM; goto done; }
    if (hf_tmd_version(version, &tmd)) { rc = TITLE_E_FORMAT; goto done; }
    LOG("install: the %s title from set %s (%s), version %s (TMD %u)", game ? "game data" : "mod", set_path,
        xx ? "with MH XX" : "plain", version, (unsigned)tmd);

    if (api.open(api.ctx, app.status.dump_path, &dump_h, &dump_size) || dump_open(&dump, api.read, api.ctx, dump_h)) {
        LOG("install: the dump cannot be read");
        rc = TITLE_E_IO;
        goto done;
    }
    dump_ok = 1;
    region = dump.region;
    title_id = game ? game_title_id(region) : edition_title_id(region);
    install_xx_hash[0] = 0;
    if (xx) {   /* the XX set's second game: bound by the set's open, checked by its title id and RomFS hash */
        if (api.open(api.ctx, app.status.xx_path, &xx_h, &xx_size) || dump_open(&xx_dump, api.read, api.ctx, xx_h)) {
            LOG("install: MH XX's dump %s cannot be read", app.status.xx_path);
            rc = TITLE_E_IO;
            goto done;
        }
        xx_ok = 1;
        hf_hex(xx_dump.header + DUMP_ROMFS_HASH, install_xx_hash);
        LOG("install: MH XX's dump %s, %lu MB", app.status.xx_path, (unsigned long)(xx_size >> 20));
        log_memory("with both dumps open");
    }
    if (api.open(api.ctx, set_path, &set_h, &set_size)) {
        LOG("install: the patch set cannot be read");
        rc = TITLE_E_IO;
        goto done;
    }
    if (xx_ok && install_xx_by_files && (rc = xx_adopt(&api, set_h, set_size, &xx_dump))) goto done;
    LOG("install: dump %lu MB (%s), set %lu KB", (unsigned long)(dump_size >> 20), region_name(region),
        (unsigned long)(set_size >> 10));
    if ((rc = title_files(&api, &dump, smdh, certs))) goto done;

    job.in.kind = kind;
    job.in.title_id = title_id;
    job.in.smdh = smdh;
    job.in.certs = certs;
    job.in.tmd_version = tmd;
    job.in.use_slot = 1;
    job.in.check_set = 1;          /* 1 MB: the card's copy checked once more against the set's own hash */
    job.in.keep_budget = KEEP_BUDGET;
    job.in.progress = ui_progress;
    job.in.xx = xx_ok ? &xx_dump : NULL;
    job.read = api.read;
    job.read_ctx = api.ctx;
    job.set_handle = set_h;
    job.set_size = set_size;
    job.dump = &dump;
    job.am.parts_begin = parts_begin;
    job.am.parts_tmd = parts_tmd;
    job.am.parts_content = parts_content;
    job.am.parts_finish = parts_finish;
    job.am.parts_abort = parts_abort;
    job.am.cia_begin = cia_begin;
    job.am.cia_finish = cia_finish;
    job.am.cia_cancel = cia_cancel;
    job.am.write = am_write;
    job.am.remove_old = remove_old;
    job.am.ctx = &am;
    job.run = run_pass;
    job.phase = on_phase;
    job.notice = on_notice;
    job.room = on_room;
    job.log = &app.log;
    job.now_ms = osGetTime;

    had_record = read_installed_record(&prev);
    /* the save first, while the title is there: the install removes the title right before AM's import (remove_old)
     * and AM's removal takes the save with it. Backed up through FS and as its raw file (app_saves.c); no backup, no
     * install. The backup to bring back is in the record before anything is removed: a stop or a power cut keeps it */
    if (!game && ctr_title_installed(title_id) && saves_backup_installed(title_id, raw_stamp)) {
        LOG("install: the save could not be backed up: nothing removed or installed");
        rc = HF_E_SAVE_BACKUP;
        goto done;
    }
    /* an earlier removal's save still to bring back stays the one to bring back; else this run's */
    snprintf(restore, sizeof restore, "%s", had_record && prev.save_restore[0] ? prev.save_restore : raw_stamp);
    memset(&cur, 0, sizeof cur);
    if (had_record) cur = prev;
    if (game) {   /* the old title (a single one, or the split one) stays as it is: only the game data is marked cut */
        cur.game[0] = 0;
        cur.game_complete = 0;
        if (!had_record) cur.layout = 1;
        record_write(&cur, region);
    } else {   /* the save copy waits only after a first install: a save that stayed is never offered to be replaced */
        pending = hf_save_pending_after(app.status.title_installed, had_record ? &prev : NULL);
        record(had_record ? &prev : NULL, version, tmd, region, 0, xx, no_room, pending, restore);   /* cut until done */
    }
    marked = 1;
    /* AM's pending imports of both titles of the edition (a cut or refused try leaves one: 0xC8E083FC) */
    am.title_id = game_title_id(region);
    pending_clear(&am, "game data, before the install");
    am.title_id = edition_title_id(region);
    pending_clear(&am, "title, before the install");
    am.title_id = title_id;
    task_part_begin(kind);
    part = 1;
    rc = hf_install_title(&job, &res);
    install_am_result = res.am ? (Result)res.am : am.write_result;
    LOG("install: route %s after %d attempt(s): %d", hf_route_name(res.route), res.attempts, rc);
    if (rc) goto done;

    if (game) {
        /* open it as the game will, before the mod goes on top: a title the system cannot read stops the update */
        char line[240] = "";
        ui_phase(HT_PHASE_GAME_CHECK);
        rc = ctr_game_check(title_id, line, sizeof line);
        LOG("install: the game data opened through archive 0x2345678A: %s -> %d", line, rc);
        if (rc) {
            marked = 0;   /* the new game data is in AM but unusable: the record keeps it marked cut */
            goto done;
        }
        hf_hex(dump.header + DUMP_ROMFS_HASH, cur.game);
        cur.game_complete = 1;
        record_write(&cur, region);
        LOG("install: the game data is whole (dump %.8s...)", cur.game);
    } else {
        /* an older update title of ours would override the new base */
        u64 update_id = update_title_id(edition_title_id(region));
        /* the save back: this run's raw file (the title's save as it was right before), else an earlier removal's;
         * the record forgets only the backup that came back */
        const char *use = raw_stamp[0] ? raw_stamp : restore;
        ui_phase(HT_SAVE_RESTORING);
        if (use[0] && !saves_raw_restore(title_id, use) && !strcmp(use, restore)) restore[0] = 0;
        if (ctr_title_installed(update_id)) LOGR("delete old update title", ctr_title_delete(update_id));
        record(had_record ? &prev : NULL, version, tmd, region, 1, xx, no_room, pending, restore);
        LOG("install: done%s", pending ? " (the save copy waits for the title's first run)" : "");
    }

done:
    if (part) task_part_end(kind);
    if (rc) {
        char rec_path[256];
        LOG("install: stopped with %d", rc);
        log_memory("at the stop");
        if (marked && install_old_removed) {   /* the old title went before AM's import: the record stays cut */
            LOG("install: the old title was removed and nothing replaced it: the next update installs it whole");
        } else if (marked) {   /* the old title stays, so its record does too */
            if (had_record) record_write(&prev, region);
            else if (!hf_path_installed(app_edition()->slug, rec_path, sizeof rec_path)) remove(rec_path);
        }
    }
    if (dump_ok) dump_close(&dump);
    if (xx_ok) dump_close(&xx_dump);
    if (set_h) api.close(api.ctx, set_h);
    if (dump_h) api.close(api.ctx, dump_h);
    if (xx_h) api.close(api.ctx, xx_h);
    free(smdh);
    free(certs);
    hf_log_phase(&app.log, osGetTime(), game ? "install of the game data, all" : "install, all", t_all, 0);
    return rc;
}
