/* The save copy: the original MH4U save (cartridge or digital) into the edition's title, after both are backed up to
 * sdmc:/3ds/heavenfall/<edition>/saves/<date>/ (as Checkpoint opens save archives: ARCHIVE_USER_SAVEDATA with the media
 * type and the title id). The edition's save opens only after its first run, so after the first install the copy
 * waits for it (installed.json's save_pending): the app offers it at its next start, once the save opens, and More
 * and the guide run it at any time. Done or declined, it is no longer pending.
 * And the edition's own save across an update, which AM's removal of the title takes away (below). */
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "app.h"
#include "ctr_title.h"
#include "dump.h"

#define PATH_MAX_LEN 300
#define COPY_CHUNK (64 * 1024)
#define MAX_TREE_DEPTH 8   /* folders inside folders a save may have: each level takes ~10 KB of the main stack */


static Result open_save(FS_Archive *ar, FS_MediaType media, u64 id) {
    u32 low[3] = {(u32)media, (u32)id, (u32)(id >> 32)};
    FS_Path path = {PATH_BINARY, 12, low};
    Result rc = FSUSER_OpenArchive(ar, ARCHIVE_USER_SAVEDATA, path);
    LOG("save archive %016llX (media %d): 0x%08lX", (unsigned long long)id, (int)media, (unsigned long)rc);
    return rc;
}

static Result open_sd(FS_Archive *ar) { return FSUSER_OpenArchive(ar, ARCHIVE_SDMC, fsMakePath(PATH_EMPTY, "")); }

static int is_dir(const FS_DirectoryEntry *e) { return (e->attributes & FS_ATTRIBUTE_DIRECTORY) != 0; }

/* utf16_to_utf8 answers the whole name's length, which may pass what it wrote: the end is clamped to the buffer. */
static void entry_name(const FS_DirectoryEntry *e, char *out, size_t cap) {
    ssize_t n = utf16_to_utf8((uint8_t *)out, e->name, cap - 1);
    out[n <= 0 ? 0 : (size_t)n < cap - 1 ? (size_t)n : cap - 1] = 0;
}

/* The region of the edition's installed title (the dump's first when both are), -1 when none is installed. */
static int installed_region(void) {
    int first = app.status.region == REGION_USA ? REGION_USA : REGION_EUR, k;
    for (k = 0; k < 2; k++) {
        int r = k ? (first == REGION_USA ? REGION_EUR : REGION_USA) : first;
        if (ctr_title_installed(edition_title_id(r))) return r;
    }
    return -1;
}

static void join(char *out, size_t cap, const char *dir, const char *name) {
    snprintf(out, cap, "%s%s%s", dir, strcmp(dir, "/") ? "/" : "", name);
}

static int copy_file(FS_Archive src, const char *spath, FS_Archive dst, const char *dpath, u64 size) {
    Handle in = 0, out = 0;
    uint8_t *buf = (uint8_t *)malloc(COPY_CHUNK);
    u64 at = 0;
    int bad = 1;
    if (!buf) return 1;
    FSUSER_DeleteFile(dst, fsMakePath(PATH_ASCII, dpath));
    if (R_SUCCEEDED(FSUSER_OpenFile(&in, src, fsMakePath(PATH_ASCII, spath), FS_OPEN_READ, 0)) &&
        R_SUCCEEDED(FSUSER_CreateFile(dst, fsMakePath(PATH_ASCII, dpath), 0, size)) &&
        R_SUCCEEDED(FSUSER_OpenFile(&out, dst, fsMakePath(PATH_ASCII, dpath), FS_OPEN_WRITE, 0))) {
        bad = 0;
        while (at < size && !bad) {
            u32 n = size - at < COPY_CHUNK ? (u32)(size - at) : COPY_CHUNK, got = 0, put = 0;
            if (R_FAILED(FSFILE_Read(in, &got, at, buf, n)) || got != n || R_FAILED(FSFILE_Write(out, &put, at, buf, n, 0)) ||
                put != n)
                bad = 1;
            at += n;
        }
        if (!bad && R_FAILED(FSFILE_Flush(out))) bad = 1;
    }
    if (in) FSFILE_Close(in);
    if (out) FSFILE_Close(out);
    free(buf);
    if (bad) LOG("save copy: %s failed", spath);
    return bad;
}

/* The whole tree of `spath` in `src` into `dpath` in `dst` (a missing folder is made). A tree deeper than
 * MAX_TREE_DEPTH is refused (no save of the game has one), so a damaged archive cannot run the stack out. */
static int copy_tree(FS_Archive src, const char *spath, FS_Archive dst, const char *dpath, int depth) {
    Handle dir;
    FS_DirectoryEntry entries[16];
    u32 read = 0;
    int bad = 0;
    if (depth > MAX_TREE_DEPTH) {
        LOG("save copy: %s is deeper than %d folders", spath, MAX_TREE_DEPTH);
        return 1;
    }
    if (strcmp(dpath, "/")) FSUSER_CreateDirectory(dst, fsMakePath(PATH_ASCII, dpath), 0);
    if (R_FAILED(FSUSER_OpenDirectory(&dir, src, fsMakePath(PATH_ASCII, spath)))) return 1;
    while (!bad && R_SUCCEEDED(FSDIR_Read(dir, &read, 16, entries)) && read) {
        u32 i;
        for (i = 0; i < read && !bad; i++) {
            char name[PATH_MAX_LEN], s[PATH_MAX_LEN], d[PATH_MAX_LEN];
            entry_name(&entries[i], name, sizeof name);
            join(s, sizeof s, spath, name);
            join(d, sizeof d, dpath, name);
            bad = is_dir(&entries[i]) ? copy_tree(src, s, dst, d, depth + 1) : copy_file(src, s, dst, d, entries[i].fileSize);
        }
    }
    FSDIR_Close(dir);
    return bad;
}

static void wipe(FS_Archive ar) {
    Handle dir;
    FS_DirectoryEntry entries[16];
    u32 read = 0;
    char names[64][PATH_MAX_LEN];
    int isd[64], n = 0, i;
    if (R_FAILED(FSUSER_OpenDirectory(&dir, ar, fsMakePath(PATH_ASCII, "/")))) return;
    while (n < 64 && R_SUCCEEDED(FSDIR_Read(dir, &read, 16, entries)) && read)
        for (i = 0; i < (int)read && n < 64; i++) {
            char name[PATH_MAX_LEN];
            entry_name(&entries[i], name, sizeof name);
            join(names[n], PATH_MAX_LEN, "/", name);
            isd[n++] = is_dir(&entries[i]);
        }
    FSDIR_Close(dir);
    for (i = 0; i < n; i++) {
        if (isd[i]) FSUSER_DeleteDirectoryRecursively(ar, fsMakePath(PATH_ASCII, names[i]));
        else FSUSER_DeleteFile(ar, fsMakePath(PATH_ASCII, names[i]));
    }
}

static void make_parents(FS_Archive sd, const char *path) {   /* "/a/b/c": makes /a and /a/b */
    char part[PATH_MAX_LEN];
    size_t i;
    for (i = 1; path[i]; i++)
        if (path[i] == '/') {
            memcpy(part, path, i);
            part[i] = 0;
            FSUSER_CreateDirectory(sd, fsMakePath(PATH_ASCII, part), 0);
        }
}

static void stamp_now(char stamp[18]) {
    time_t now = time(NULL);
    struct tm tm;
    localtime_r(&now, &tm);
    hf_save_stamp(tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_hour, tm.tm_min, tm.tm_sec, stamp);
}

static int backup(FS_Archive save, FS_Archive sd, int which, const char *stamp) {
    char path[PATH_MAX_LEN];
    if (hf_path_save_at(app_edition()->slug, which, stamp, path, sizeof path)) return 1;
    LOG("save backup %s", path);
    make_parents(sd, path + 5);
    return copy_tree(save, "/", sd, path + 5, 0);
}

/* ---- the save across an update ----
 * AM imports no title over an installed one, so an install removes the title first (app_install.c, remove_old), and
 * AM's removal takes the title's save with it; the import then makes a new, empty save file. Before the removal the
 * save is backed up through FS (as the save copy does) and its raw file, still encrypted, is copied beside that
 * backup; after the import the raw file goes back to its place, and FS reads it against the backup. */

#define RAW_SAVE_MAX (4u << 20)   /* the title's save file: 512 KB in every release so far */

/* The title's raw save file as an ARCHIVE_SDMC path (hf_save_raw_path under FS's /Nintendo 3DS/<ID0>/<ID1>). */
static int raw_save_path(u64 title_id, char *out, size_t cap) {
    u16 root16[160];
    char root[200];
    ssize_t n;
    Result rc;
    memset(root16, 0, sizeof root16);
    rc = FSUSER_GetSdmcCtrRootPath((u8 *)root16, sizeof root16 - sizeof root16[0]);
    if (R_FAILED(rc)) {
        LOG("save: the SD card's system folder is not known: 0x%08lX", (unsigned long)rc);
        return -1;
    }
    n = utf16_to_utf8((uint8_t *)root, root16, sizeof root - 1);
    root[n <= 0 ? 0 : (size_t)n < sizeof root - 1 ? (size_t)n : sizeof root - 1] = 0;
    if (hf_save_raw_path(root, title_id, out, cap)) {
        LOG("save: no raw save path for %016llX under '%s'", (unsigned long long)title_id, root);
        return -1;
    }
    return 0;
}

/* A whole file of the card into a new buffer (at most RAW_SAVE_MAX); NULL when missing, bigger or unread. */
static uint8_t *sd_read_whole(FS_Archive sd, const char *path, u32 *size) {
    Handle f = 0;
    u64 n = 0;
    u32 got = 0;
    uint8_t *buf = NULL;
    *size = 0;
    if (R_FAILED(FSUSER_OpenFile(&f, sd, fsMakePath(PATH_ASCII, path), FS_OPEN_READ, 0))) return NULL;
    if (R_SUCCEEDED(FSFILE_GetSize(f, &n)) && n && n <= RAW_SAVE_MAX && (buf = (uint8_t *)malloc((size_t)n)) &&
        (R_FAILED(FSFILE_Read(f, &got, 0, buf, (u32)n)) || got != n)) {
        free(buf);
        buf = NULL;
    }
    FSFILE_Close(f);
    if (buf) *size = (u32)n;
    return buf;
}

/* `size` bytes as the whole file at `path` of the card (made with its folders when missing). 0 on success. */
static int sd_write_whole(FS_Archive sd, const char *path, const uint8_t *buf, u32 size) {
    Handle f = 0;
    u32 put = 0;
    int bad = 1;
    if (R_FAILED(FSUSER_OpenFile(&f, sd, fsMakePath(PATH_ASCII, path), FS_OPEN_WRITE, 0))) {
        make_parents(sd, path);
        if (R_FAILED(FSUSER_CreateFile(sd, fsMakePath(PATH_ASCII, path), 0, size)) ||
            R_FAILED(FSUSER_OpenFile(&f, sd, fsMakePath(PATH_ASCII, path), FS_OPEN_WRITE, 0)))
            return 1;
    }
    if (R_SUCCEEDED(FSFILE_SetSize(f, size)) && R_SUCCEEDED(FSFILE_Write(f, &put, 0, buf, size, 0)) && put == size &&
        R_SUCCEEDED(FSFILE_Flush(f)))
        bad = 0;
    FSFILE_Close(f);
    return bad;
}

/* Every file of `dir` (the card) read whole and equal in `save` (FS reads it through its hashes and CMAC). */
static int same_tree(FS_Archive sd, const char *dir, FS_Archive save, const char *spath, int depth) {
    Handle h;
    FS_DirectoryEntry entries[16];
    u32 read = 0;
    int bad = 0, files = 0;
    uint8_t *a = (uint8_t *)malloc(COPY_CHUNK), *b = (uint8_t *)malloc(COPY_CHUNK);
    if (!a || !b || depth > MAX_TREE_DEPTH || R_FAILED(FSUSER_OpenDirectory(&h, sd, fsMakePath(PATH_ASCII, dir)))) {
        free(a);
        free(b);
        return 1;
    }
    while (!bad && R_SUCCEEDED(FSDIR_Read(h, &read, 16, entries)) && read) {
        u32 i;
        for (i = 0; i < read && !bad; i++) {
            char name[PATH_MAX_LEN], d[PATH_MAX_LEN], s[PATH_MAX_LEN];
            Handle fa = 0, fb = 0;
            u64 at = 0, size = entries[i].fileSize, other = 0;
            entry_name(&entries[i], name, sizeof name);
            join(d, sizeof d, dir, name);
            join(s, sizeof s, spath, name);
            if (is_dir(&entries[i])) {
                bad = same_tree(sd, d, save, s, depth + 1);
                continue;
            }
            files++;
            bad = R_FAILED(FSUSER_OpenFile(&fa, sd, fsMakePath(PATH_ASCII, d), FS_OPEN_READ, 0)) ||
                  R_FAILED(FSUSER_OpenFile(&fb, save, fsMakePath(PATH_ASCII, s), FS_OPEN_READ, 0)) ||
                  R_FAILED(FSFILE_GetSize(fb, &other)) || other != size;
            while (!bad && at < size) {
                u32 n = size - at < COPY_CHUNK ? (u32)(size - at) : COPY_CHUNK, ga = 0, gb = 0;
                bad = R_FAILED(FSFILE_Read(fa, &ga, at, a, n)) || R_FAILED(FSFILE_Read(fb, &gb, at, b, n)) || ga != n ||
                      gb != n || memcmp(a, b, n);
                at += n;
            }
            if (fa) FSFILE_Close(fa);
            if (fb) FSFILE_Close(fb);
            if (bad) LOG("save: %s differs from the backup or does not read", s);
        }
    }
    FSDIR_Close(h);
    free(a);
    free(b);
    return bad || (!depth && !files);   /* a backup with no file proves nothing */
}

int saves_backup_installed(u64 title_id, char stamp[18]) {
    FS_Archive save, sd;
    char raw[PATH_MAX_LEN], kept[PATH_MAX_LEN];
    uint8_t *bytes;
    u32 size = 0;
    int bad;
    stamp[0] = 0;
    if (R_FAILED(open_save(&save, MEDIATYPE_SD, title_id))) {
        LOG("save backup before the install: no save yet");
        return 0;
    }
    if (R_FAILED(open_sd(&sd))) {
        FSUSER_CloseArchive(save);
        LOG("save backup before the install: the SD card's archive does not open");
        return 1;
    }
    stamp_now(stamp);
    bad = backup(save, sd, HF_SAVE_HEAVENFALL, stamp);
    FSUSER_CloseArchive(save);
    LOG("save backup before the install: %s", bad ? "failed" : "done");
    /* the raw file too, once FS has let go of it: a failure here leaves the backup above to bring the save back */
    if (!bad && !raw_save_path(title_id, raw, sizeof raw) &&
        !hf_path_save_raw(app_edition()->slug, stamp, kept, sizeof kept)) {
        bytes = sd_read_whole(sd, raw, &size);
        LOG("save: the raw save %s, %lu bytes, kept: %d", raw, (unsigned long)size,
            bytes && !sd_write_whole(sd, kept + 5, bytes, size));
        free(bytes);
    }
    FSUSER_CloseArchive(sd);
    if (bad) stamp[0] = 0;
    return bad;
}

int saves_raw_restore(u64 title_id, const char *stamp) {
    FS_Archive sd, save;
    char raw[PATH_MAX_LEN], kept[PATH_MAX_LEN], dir[PATH_MAX_LEN];
    uint8_t *mine = NULL, *fresh = NULL;
    u32 mine_size = 0, fresh_size = 0;
    int bad = 1;
    Result rc;
    if (!hf_title_ours(title_id) || raw_save_path(title_id, raw, sizeof raw) ||
        hf_path_save_raw(app_edition()->slug, stamp, kept, sizeof kept) ||
        hf_path_save_at(app_edition()->slug, HF_SAVE_HEAVENFALL, stamp, dir, sizeof dir) || R_FAILED(open_sd(&sd)))
        return 1;
    mine = sd_read_whole(sd, kept + 5, &mine_size);
    fresh = sd_read_whole(sd, raw, &fresh_size);   /* AM's new file: written back when the kept one fails */
    LOG("save: the kept raw save %lu bytes, the title's new one %lu bytes", (unsigned long)mine_size,
        (unsigned long)fresh_size);
    if (mine && fresh && mine_size == fresh_size && !sd_write_whole(sd, raw, mine, mine_size)) {
        rc = open_save(&save, MEDIATYPE_SD, title_id);
        if (R_SUCCEEDED(rc)) {
            bad = same_tree(sd, dir + 5, save, "/", 0);
            FSUSER_CloseArchive(save);
        }
        LOG("save: the raw save put back: it opens 0x%08lX, the same as the backup: %d", (unsigned long)rc, !bad);
        if (bad && sd_write_whole(sd, raw, fresh, fresh_size)) LOG("save: AM's new save file not written back");
    }
    if (!bad) FSUSER_DeleteFile(sd, fsMakePath(PATH_ASCII, kept + 5));   /* the backup folder stays */
    FSUSER_CloseArchive(sd);
    free(mine);
    free(fresh);
    LOG("save: back after the install: %s", bad ? "no (the backup brings it once the title's save opens)" : "yes");
    return bad;
}

int saves_restore_flow(int quiet) {
    FS_Archive save, sd;
    char dir[PATH_MAX_LEN], stamp[18];
    u64 id;
    int region, bad;
    if (!hf_save_stamp_ok(app.status.save_restore) || (region = installed_region()) < 0) return SAVE_NOT_RUN;
    snprintf(stamp, sizeof stamp, "%s", app.status.save_restore);
    id = edition_title_id(region);
    if (!hf_title_ours(id) || hf_path_save_at(app_edition()->slug, HF_SAVE_HEAVENFALL, stamp, dir, sizeof dir))
        return SAVE_FAILED;
    if (R_FAILED(open_save(&save, MEDIATYPE_SD, id))) {   /* no save until the game's first run */
        LOG("save restore: the title's save does not open yet");
        if (!quiet) ui_message(T(HT_SAVE_RESTORE_RUN_FIRST));
        return SAVE_NOT_RUN;
    }
    if (!ui_confirm(T(HT_SAVE_RESTORE_OFFER))) {
        FSUSER_CloseArchive(save);
        LOG("save restore: not now (offered again at the next start)");
        return SAVE_DECLINED;
    }
    if (R_FAILED(open_sd(&sd))) {
        FSUSER_CloseArchive(save);
        ui_message_ex(T(HT_SAVE_RESTORE_FAILED), HF_TONE_BAD, "");
        return SAVE_FAILED;
    }
    ui_working(T(HT_SAVE_BACKING_UP));
    {   /* what the title holds now, in a folder of its own (never the one the save comes back from) */
        char now[18];
        stamp_now(now);
        bad = !strcmp(now, stamp) || backup(save, sd, HF_SAVE_HEAVENFALL, now);
    }
    if (!bad) {
        ui_working(T(HT_SAVE_RESTORING));
        wipe(save);
        bad = copy_tree(sd, dir + 5, save, "/", 0);
        if (!bad) {
            Result rc = FSUSER_ControlArchive(save, ARCHIVE_ACTION_COMMIT_SAVE_DATA, NULL, 0, NULL, 0);
            LOGR("save restore commit", rc);
            bad = R_FAILED(rc);
        }
    }
    FSUSER_CloseArchive(sd);
    FSUSER_CloseArchive(save);
    LOG("save restore from %s: %s", stamp, bad ? "failed" : "done");
    if (!bad) installed_restore_done();
    ui_message_ex(T(bad ? HT_SAVE_RESTORE_FAILED : HT_SAVE_RESTORED), bad ? HF_TONE_BAD : HF_TONE_GOOD, "");
    return bad ? SAVE_FAILED : SAVE_COPIED;
}

int saves_copy_flow(int quiet) {
    u64 orig_id, dst_id;
    FS_MediaType orig_media;
    FS_Archive src, dst, sd;
    char stamp[18];
    int region, bad, backed_up;
    Result rc;
    /* the save goes into the installed edition's title; the original of that region is looked for first */
    if ((region = installed_region()) < 0) {
        if (!quiet) ui_message(T(HT_NOT_INSTALLED));
        return SAVE_NOT_RUN;
    }
    if (!original_game_for(region, 1, &orig_id, &orig_media)) {
        if (!quiet) ui_message(T(HT_SAVE_NONE));
        return SAVE_NO_ORIGINAL;
    }
    dst_id = edition_title_id(region);
    if (!hf_title_ours(dst_id)) {   /* only Heavenfall's save is ever written: the original's never (launcher.h) */
        LOG("save copy: %016llX is not Heavenfall's: nothing written", (unsigned long long)dst_id);
        if (!quiet) ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        return SAVE_FAILED;
    }
    if (R_FAILED(open_save(&src, orig_media, orig_id))) {
        if (!quiet) ui_message(T(HT_SAVE_NONE));
        return SAVE_NO_ORIGINAL;
    }
    rc = open_save(&dst, MEDIATYPE_SD, dst_id);
    if (R_FAILED(rc)) {   /* the title has made no save yet: it waits for its first run */
        FSUSER_CloseArchive(src);
        if (!quiet) ui_message(T(HT_SAVE_NEED_RUN));
        return SAVE_NOT_RUN;
    }
    if (!ui_confirm(T(HT_SAVE_OFFER))) {
        FSUSER_CloseArchive(src);
        FSUSER_CloseArchive(dst);
        LOG("save copy: declined");
        installed_save_done();
        return SAVE_DECLINED;
    }
    if (R_FAILED(open_sd(&sd))) {
        FSUSER_CloseArchive(src);
        FSUSER_CloseArchive(dst);
        LOG("save copy: the SD card's archive does not open");
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        return SAVE_FAILED;
    }
    stamp_now(stamp);
    ui_working(T(HT_SAVE_BACKING_UP));   /* seconds of file copies: the spinner shows it runs */
    bad = backup(src, sd, HF_SAVE_ORIGINAL, stamp) || backup(dst, sd, HF_SAVE_HEAVENFALL, stamp);
    backed_up = !bad;
    if (!bad) {   /* both backed up: now the copy */
        ui_working(T(HT_SAVE_COPYING));
        wipe(dst);
        bad = copy_tree(src, "/", dst, "/", 0);
        if (!bad) {
            rc = FSUSER_ControlArchive(dst, ARCHIVE_ACTION_COMMIT_SAVE_DATA, NULL, 0, NULL, 0);
            LOGR("save commit", rc);
            bad = R_FAILED(rc);
        }
    }
    FSUSER_CloseArchive(sd);
    FSUSER_CloseArchive(src);
    FSUSER_CloseArchive(dst);
    LOG("save copy: %s", bad ? "failed" : "done");
    if (!bad) installed_save_done();
    if (!bad) ui_message_ex(T(HT_SAVE_DONE), HF_TONE_GOOD, "");
    else ui_message_ex(T(backed_up ? HT_SAVE_COPY_FAILED : HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
    return bad ? SAVE_FAILED : SAVE_COPIED;
}
