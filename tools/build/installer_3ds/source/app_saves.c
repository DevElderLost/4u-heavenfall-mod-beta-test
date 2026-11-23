/* The save copy: the original MH4U save (cartridge or digital) into the edition's title, after both are backed up to
 * sdmc:/3ds/heavenfall/<edition>/saves/<date>/ (as Checkpoint opens save archives: ARCHIVE_USER_SAVEDATA with the media
 * type and the title id). The edition's save opens only after its first run, so after the first install the copy
 * waits for it (installed.json's save_pending): the app offers it at its next start, once the save opens, and More
 * and the guide run it at any time. Done or declined, it is no longer pending.
 * An edition whose game plays on Heavenfall's own extdata (own_save: the full mod) brings a hunter into that extdata
 * instead (Bring, below; bring.c's rules); Heavenfall Beta keeps the copy into the title as it was, and its More has
 * the way back too: Beta's save into the original game's ("More > MH4U saves", at the end).
 * And the edition's own save across an update, which AM's removal of the title takes away (below). */
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "app.h"
#include "bring.h"
#include "ctr_title.h"
#include "dump.h"
#include "hf_save_files.h"
#include "to_mh4u.h"

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

/* The MH4U whose save the copy flows use: its id and medium. With the game on the cartridge and on the SD card (digital)
 * the player is asked which, once per run (`chosen`, kept while that medium still holds the game); never the cartridge
 * silently. 1 when a game is found. */
static int pick_original(int region, u64 *id, FS_MediaType *media) {
    static int chosen = -1;   /* the medium of the player's answer, -1 not asked yet */
    FS_MediaType found[2];
    int n = original_games_for(region, id, found), i, hit;
    if (n <= 0) return 0;
    if (n == 1) {
        *media = found[0];
        return 1;
    }
    for (i = 0, hit = 0; i < n && chosen >= 0; i++)
        if ((int)found[i] == chosen) hit = 1;
    if (!hit) chosen = (int)(ui_confirm(T(HT_MEDIUM_ASK)) ? found[0] : found[1]);   /* found[0] the cartridge, found[1] the SD card */
    *media = (FS_MediaType)chosen;
    LOG("original game: %s chosen", *media == MEDIATYPE_GAME_CARD ? "the cartridge" : "the digital game");
    return 1;
}

static const char *media_text(FS_MediaType media) {
    return T(media == MEDIATYPE_GAME_CARD ? HT_MH4U_ON_CARTRIDGE : HT_MH4U_ON_DIGITAL);
}

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

/* What a read of a file found: it was read (FILE_READ), it is not there (FILE_ABSENT: FS says "not found" for the
 * path) or it is there but could not be read whole (FILE_BAD: an error of another kind, empty, bigger than
 * RAW_SAVE_MAX, a short read). */
enum { FILE_READ, FILE_ABSENT, FILE_BAD };

/* 1 for the results FS gives for a path with nothing at it (description 100 or 120 of the file system's module). */
static int fs_not_found(Result rc) {
    unsigned d = (unsigned)rc & 0x3FFu, m = ((unsigned)rc >> 10) & 0xFFu;
    return m == 17u && (d == 100u || d == 120u);
}

/* A whole file of the card into a new buffer (at most RAW_SAVE_MAX); NULL when it was not read, `state` saying why
 * (FILE_ABSENT only when FS answered "not found": every other failure is FILE_BAD, which no flow takes as absent). */
static uint8_t *sd_read_state(FS_Archive sd, const char *path, u32 *size, int *state) {
    Handle f = 0;
    u64 n = 0;
    u32 got = 0;
    uint8_t *buf = NULL;
    Result rc;
    *size = 0;
    *state = FILE_BAD;
    rc = FSUSER_OpenFile(&f, sd, fsMakePath(PATH_ASCII, path), FS_OPEN_READ, 0);
    if (R_FAILED(rc)) {
        if (fs_not_found(rc)) *state = FILE_ABSENT;
        else LOG("read %s: 0x%08lX, not taken as absent", path, (unsigned long)rc);
        return NULL;
    }
    if (R_SUCCEEDED(FSFILE_GetSize(f, &n)) && n && n <= RAW_SAVE_MAX && (buf = (uint8_t *)malloc((size_t)n)) &&
        (R_FAILED(FSFILE_Read(f, &got, 0, buf, (u32)n)) || got != n)) {
        free(buf);
        buf = NULL;
    }
    FSFILE_Close(f);
    if (buf) {
        *size = (u32)n;
        *state = FILE_READ;
    }
    return buf;
}

/* As sd_read_state, for a caller that only needs the bytes or nothing. */
static uint8_t *sd_read_whole(FS_Archive sd, const char *path, u32 *size) {
    int state;
    return sd_read_state(sd, path, size, &state);
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

/* The copy into the title's save (Heavenfall Beta's: its game keeps MH4U's files in the title's save archive). */
static int title_copy_flow(int quiet) {
    u64 orig_id, dst_id;
    FS_MediaType orig_media;
    FS_Archive src, dst, sd;
    char stamp[18];
    int region, bad, backed_up, offered;
    Result rc;
    /* the save goes into the installed edition's title; the original of that region is looked for first */
    if ((region = installed_region()) < 0) {
        if (!quiet) ui_message(T(HT_NOT_INSTALLED));
        return SAVE_NOT_RUN;
    }
    if (!pick_original(region, &orig_id, &orig_media)) {
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
    {   /* all three hunters and the shared data are replaced: said plainly, with the backup's place and the MH4U used */
        char dir[PATH_MAX_LEN], q[2 * HF_VIEW_LINE];
        if (hf_path_dir(app_edition()->slug, dir, sizeof dir) || strlen(dir) < 6) snprintf(dir, sizeof dir, "sdmc:3ds/heavenfall");
        snprintf(q, sizeof q, "%s %s/saves. %s.", T(HT_SAVE_OFFER), dir + 5, media_text(orig_media));
        offered = ui_confirm(q);
    }
    if (!offered) {
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

/* ---- Bring ----
 * The edition whose game plays on Heavenfall's own extdata (own_save): a hunter of the original game brought into it.
 * The rules are bring.c's (portable, tested on the PC); here the console's archives behind its HfSaveIo:
 * * the original game's save archive as the save copy opens it (original_game_for, open_save: proven on the console);
 * * an extdata as Checkpoint opens one (3ds/source/archive.cpp, Archive::extdata: ARCHIVE_EXTDATA with the binary path
 *   {MEDIATYPE_SD, id, 0}; Checkpoint's app.rsf has launcher.rsf's FileSystemAccess list and UseExtSaveData false), its
 *   files listed with FSUSER_OpenDirectory / FSDIR_Read as Checkpoint's copyDirectory and the save copy list theirs;
 * * a file written into an extdata as Checkpoint's restore writes one (io.cpp: io::restore deletes the files, then
 *   io::copyFile opens an FSStream with the source's size; fsstream.cpp: FSUSER_OpenFile, failing that
 *   FSUSER_CreateFile with the size and FSUSER_OpenFile again, FSFILE_Write with flags 0, FSFILE_Flush,
 *   FSFILE_Close): an extdata file keeps the size it was made with, so it is deleted and made again with its size.
 *   UTF-16 paths, as Checkpoint's. Only an id hf_extdata_ours takes is ever written; MH4U's are only read, bar
 *   the one cheats file (hf_extdata_file_ok; cheat_flag_* below);
 * * the backup on the card as the app's other files there (sd_write_whole). */

#define BRING_LISTED 64   /* the files of an extdata: the game makes its with room for 0x40 */
enum { BRING_COMMON = HF_SAVE_SLOTS + 1, BRING_BACK };   /* the page's buttons past the slots' 1-3 */

typedef struct {
    char name[HF_BRING_NAME];
    u32 size;
} BringFile;

typedef struct {
    FS_Archive ar[HF_BRING_CONTAINERS];      /* the backup's and the state's are the SD card's */
    int open[HF_BRING_CONTAINERS];
    int listed_ok[HF_BRING_CONTAINERS];      /* the whole listing was read */
    BringFile files[HF_BRING_CONTAINERS][BRING_LISTED];
    int counts[HF_BRING_CONTAINERS];
    u32 heavenfall_id;                       /* the extdata id Heavenfall's archive was opened with */
    char backup[PATH_MAX_LEN];               /* this Bring's backup folder, an ARCHIVE_SDMC path */
    char state[PATH_MAX_LEN];                /* the launcher's own folder (the journal, the moves), an ARCHIVE_SDMC path */
    char last_stamp[18];
    const char *console;                     /* "EUR" / "USA": the moves' record names it */
} Bring;

static Result open_extdata(FS_Archive *ar, u32 id) {
    u32 path[3] = {MEDIATYPE_SD, id, 0};     /* Checkpoint's Archive::extdata */
    FS_Path p = {PATH_BINARY, 12, path};
    Result rc = FSUSER_OpenArchive(ar, ARCHIVE_EXTDATA, p);
    LOG("extdata %08lX: 0x%08lX", (unsigned long)id, (unsigned long)rc);
    return rc;
}

/* "/<name>" as FS takes it in this container: UTF-16 in an extdata (as Checkpoint), ASCII elsewhere (as the save copy). */
static FS_Path bring_path(int c, const char *name, char ascii[HF_BRING_NAME + 2], u16 wide[HF_BRING_NAME + 2]) {
    size_t i;
    snprintf(ascii, HF_BRING_NAME + 2, "/%s", name);
    if (c != HF_BRING_MH4U_EXTDATA && c != HF_BRING_HEAVENFALL) return fsMakePath(PATH_ASCII, ascii);
    for (i = 0; ascii[i]; i++) wide[i] = (u8)ascii[i];
    wide[i] = 0;
    return fsMakePath(PATH_UTF16, wide);
}

static void bring_list(Bring *b, int c) {
    Handle dir;
    FS_DirectoryEntry entries[16];
    u16 root[2] = {'/', 0};
    u32 read = 0, i;
    int overflow = 0;
    Result rc;
    b->counts[c] = 0;
    b->listed_ok[c] = 0;
    rc = FSUSER_OpenDirectory(&dir, b->ar[c], c == HF_BRING_MH4U_SAVE ? fsMakePath(PATH_ASCII, "/")
                                                                       : fsMakePath(PATH_UTF16, root));
    if (R_FAILED(rc)) {
        LOG("bring: container %d not listed: 0x%08lX", c, (unsigned long)rc);
        return;
    }
    while (R_SUCCEEDED(rc = FSDIR_Read(dir, &read, 16, entries)) && read)
        for (i = 0; i < read; i++) {
            char name[PATH_MAX_LEN];
            entry_name(&entries[i], name, sizeof name);
            if (is_dir(&entries[i]) || strlen(name) >= HF_BRING_NAME) continue;   /* none of the game's */
            if (b->counts[c] >= BRING_LISTED) {
                overflow = 1;
                continue;
            }
            snprintf(b->files[c][b->counts[c]].name, HF_BRING_NAME, "%s", name);
            b->files[c][b->counts[c]++].size = (u32)entries[i].fileSize;
        }
    FSDIR_Close(dir);
    b->listed_ok[c] = R_SUCCEEDED(rc) && !overflow;   /* a file left out could be written over unbacked */
    LOG("bring: container %d holds %d files%s", c, b->counts[c], b->listed_ok[c] ? "" : " (the listing failed)");
}

static BringFile *bring_find(Bring *b, int c, const char *name) {
    int i;
    for (i = 0; i < b->counts[c]; i++)
        if (!strcmp(b->files[c][i].name, name)) return &b->files[c][i];
    return NULL;
}

static void bring_listed(Bring *b, int c, const char *name, u32 size, int present) {
    BringFile *f = bring_find(b, c, name);
    if (!present) {
        if (f) *f = b->files[c][--b->counts[c]];
    } else if (f) {
        f->size = size;
    } else if (b->counts[c] < BRING_LISTED) {
        snprintf(b->files[c][b->counts[c]].name, HF_BRING_NAME, "%s", name);
        b->files[c][b->counts[c]++].size = size;
    }
}

static int bring_has(void *ctx, int c) {
    Bring *b = ctx;
    return c >= 0 && c < HF_BRING_CONTAINERS && b->open[c] &&
           (c == HF_BRING_BACKUP || c == HF_BRING_STATE || b->listed_ok[c]);
}

/* The card's path of a file of the backup set or of the launcher's folder. */
static void bring_sd_path(const Bring *b, int c, const char *name, char *out, size_t cap) {
    snprintf(out, cap, "%s/%s", c == HF_BRING_STATE ? b->state : b->backup, name);
}

static int bring_size(void *ctx, int c, const char *name, uint32_t *size) {
    Bring *b = ctx;
    BringFile *f;
    if (c == HF_BRING_BACKUP || c == HF_BRING_STATE) {   /* a file this Bring wrote */
        char path[PATH_MAX_LEN];
        Handle h = 0;
        u64 n = 0;
        int bad;
        if (!b->open[c]) return 1;
        bring_sd_path(b, c, name, path, sizeof path);
        if (R_FAILED(FSUSER_OpenFile(&h, b->ar[c], fsMakePath(PATH_ASCII, path), FS_OPEN_READ, 0))) return 1;
        bad = R_FAILED(FSFILE_GetSize(h, &n)) || n > HF_BRING_MAX_FILE;
        FSFILE_Close(h);
        *size = (u32)n;
        return bad ? -1 : 0;
    }
    if (c < 0 || c >= HF_BRING_CONTAINERS || !b->open[c]) return 1;   /* no container: no file */
    if (!b->listed_ok[c]) return -1;   /* not known: a sidecar or a file to back up could be missed */
    if (!(f = bring_find(b, c, name))) return 1;
    *size = f->size;
    return 0;
}

static int bring_read(void *ctx, int c, const char *name, uint8_t *buf, uint32_t size) {
    Bring *b = ctx;
    char ascii[HF_BRING_NAME + 2], path[PATH_MAX_LEN];
    u16 wide[HF_BRING_NAME + 2];
    Handle h = 0;
    u32 at = 0, got;
    int bad = 0;
    FS_Path p;
    if (c == HF_BRING_BACKUP || c == HF_BRING_STATE) {
        bring_sd_path(b, c, name, path, sizeof path);
        p = fsMakePath(PATH_ASCII, path);
    } else {
        p = bring_path(c, name, ascii, wide);
    }
    if (!b->open[c] || R_FAILED(FSUSER_OpenFile(&h, b->ar[c], p, FS_OPEN_READ, 0))) {
        LOG("bring: %d/%s does not open", c, name);
        return 1;
    }
    while (!bad && at < size) {
        u32 n = size - at < COPY_CHUNK ? size - at : COPY_CHUNK;
        bad = R_FAILED(FSFILE_Read(h, &got, at, buf + at, n)) || got != n;
        at += n;
    }
    FSFILE_Close(h);
    if (bad) LOG("bring: %d/%s does not read", c, name);
    return bad;
}

static int bring_write(void *ctx, int c, const char *name, const uint8_t *buf, uint32_t size) {
    Bring *b = ctx;
    char ascii[HF_BRING_NAME + 2], path[PATH_MAX_LEN];
    u16 wide[HF_BRING_NAME + 2];
    Handle h = 0;
    u32 at = 0, put;
    int bad = 0;
    FS_Path p;
    Result rc;
    if (c == HF_BRING_BACKUP || c == HF_BRING_STATE) {
        bring_sd_path(b, c, name, path, sizeof path);
        bad = !b->open[c] || sd_write_whole(b->ar[c], path, buf, size);
        LOG("bring: %s %s, %lu bytes: %s", c == HF_BRING_STATE ? "state" : "backup", path, (unsigned long)size,
            bad ? "failed" : "done");
        return bad;
    }
    if (c != HF_BRING_HEAVENFALL || !b->open[c] || !hf_extdata_ours(b->heavenfall_id)) {
        LOG("bring: write of %s refused (container %d)", name, c);
        return 1;
    }
    p = bring_path(c, name, ascii, wide);
    if (!bring_find(b, c, name) && R_SUCCEEDED(FSUSER_OpenFile(&h, b->ar[c], p, FS_OPEN_READ, 0))) {
        FSFILE_Close(h);   /* a file the listing missed has no backup: never written over */
        LOG("bring: %s is there but was not listed: refused", name);
        return 1;
    }
    FSUSER_DeleteFile(b->ar[c], p);   /* a missing file answers an error: nothing to delete */
    bring_listed(b, c, name, 0, 0);
    if (R_SUCCEEDED(rc = FSUSER_CreateFile(b->ar[c], p, 0, size))) bring_listed(b, c, name, size, 1);
    if (R_FAILED(rc) || R_FAILED(rc = FSUSER_OpenFile(&h, b->ar[c], p, FS_OPEN_WRITE, 0))) {
        LOG("bring: %s not made: 0x%08lX", name, (unsigned long)rc);
        return 1;
    }
    while (!bad && at < size) {
        u32 n = size - at < COPY_CHUNK ? size - at : COPY_CHUNK;
        bad = R_FAILED(FSFILE_Write(h, &put, at, buf + at, n, 0)) || put != n;
        at += n;
    }
    if (!bad && R_FAILED(FSFILE_Flush(h))) bad = 1;
    FSFILE_Close(h);
    LOG("bring: %s, %lu bytes: %s", name, (unsigned long)size, bad ? "failed" : "written");
    return bad;
}

static int bring_remove(void *ctx, int c, const char *name) {
    Bring *b = ctx;
    char ascii[HF_BRING_NAME + 2];
    u16 wide[HF_BRING_NAME + 2];
    Result rc;
    if (c == HF_BRING_STATE) {   /* the journal: deleted; a file that stays is a failure */
        char path[PATH_MAX_LEN];
        Handle h = 0;
        if (!b->open[c]) return 1;
        bring_sd_path(b, c, name, path, sizeof path);
        rc = FSUSER_DeleteFile(b->ar[c], fsMakePath(PATH_ASCII, path));
        LOG("bring: state %s deleted: 0x%08lX", path, (unsigned long)rc);
        if (R_SUCCEEDED(rc) || R_FAILED(FSUSER_OpenFile(&h, b->ar[c], fsMakePath(PATH_ASCII, path), FS_OPEN_READ, 0)))
            return 0;
        FSFILE_Close(h);
        return 1;
    }
    if (c != HF_BRING_HEAVENFALL || !b->open[c] || !hf_extdata_ours(b->heavenfall_id)) return 1;
    rc = FSUSER_DeleteFile(b->ar[c], bring_path(c, name, ascii, wide));
    LOG("bring: %s deleted: 0x%08lX", name, (unsigned long)rc);
    if (R_SUCCEEDED(rc)) bring_listed(b, c, name, 0, 0);
    return R_FAILED(rc) && bring_find(b, c, name) != NULL;
}

static void bring_close(Bring *b) {
    int c;
    for (c = 0; c < HF_BRING_CONTAINERS; c++)
        if (b->open[c]) FSUSER_CloseArchive(b->ar[c]);
    memset(b->open, 0, sizeof b->open);
}

/* The launcher's folder on the card, where the journal and the moves' record live. */
static void bring_open_state(Bring *b, int region) {
    char dir[PATH_MAX_LEN];
    b->console = region_name(region);
    b->open[HF_BRING_STATE] = !hf_path_dir(app_edition()->slug, dir, sizeof dir) &&
                              R_SUCCEEDED(open_sd(&b->ar[HF_BRING_STATE]));
    if (b->open[HF_BRING_STATE]) snprintf(b->state, sizeof b->state, "%s", dir + 5);   /* without "sdmc:" */
}

static HfSaveIo bring_io(Bring *b) {
    HfSaveIo io = {b, bring_has, bring_size, bring_read, bring_write, bring_remove, b->last_stamp, b->console};
    return io;
}

/* The region's archives: 1 when Heavenfall's extdata opened (the game made it), else 0 (all closed). */
static int bring_open(Bring *b, int region) {
    u64 orig_id;
    FS_MediaType orig_media;
    u32 mh4u = region == REGION_USA ? HF_MH4U_EXTDATA_USA : HF_MH4U_EXTDATA_EUR;
    b->heavenfall_id = region == REGION_USA ? HF_HEAVENFALL_EXTDATA_USA : HF_HEAVENFALL_EXTDATA_EUR;
    if (!hf_extdata_ours(b->heavenfall_id) || R_FAILED(open_extdata(&b->ar[HF_BRING_HEAVENFALL], b->heavenfall_id)))
        return 0;
    b->open[HF_BRING_HEAVENFALL] = 1;
    bring_list(b, HF_BRING_HEAVENFALL);
    if (pick_original(region, &orig_id, &orig_media) &&
        R_SUCCEEDED(open_save(&b->ar[HF_BRING_MH4U_SAVE], orig_media, orig_id))) {
        b->open[HF_BRING_MH4U_SAVE] = 1;
        bring_list(b, HF_BRING_MH4U_SAVE);
    }
    if (R_SUCCEEDED(open_extdata(&b->ar[HF_BRING_MH4U_EXTDATA], mh4u))) {
        b->open[HF_BRING_MH4U_EXTDATA] = 1;
        bring_list(b, HF_BRING_MH4U_EXTDATA);
    }
    b->open[HF_BRING_BACKUP] = R_SUCCEEDED(open_sd(&b->ar[HF_BRING_BACKUP]));
    bring_open_state(b, region);
    return 1;
}

/* A new backup folder (never the last one: a second Bring in the same second waits for the next). 0 on success. */
static int bring_backup_folder(Bring *b) {
    char stamp[18], dir[PATH_MAX_LEN];
    int tries;
    for (tries = 0; tries < 20; tries++) {
        stamp_now(stamp);
        if (strcmp(stamp, b->last_stamp)) break;
        svcSleepThread(100000000LL);
    }
    if (!strcmp(stamp, b->last_stamp) || hf_path_save_at(app_edition()->slug, HF_SAVE_HEAVENFALL, stamp, dir, sizeof dir))
        return 1;
    snprintf(b->last_stamp, sizeof b->last_stamp, "%s", stamp);
    snprintf(b->backup, sizeof b->backup, "%s", dir + 5);   /* without "sdmc:" */
    return 0;
}

static void bring_side_text(const HfBringSide *s, char *out, size_t cap) {
    if (!s->present || (s->readable && !s->hunter)) snprintf(out, cap, "%s", T(HT_BRING_EMPTY));
    else if (!s->readable) snprintf(out, cap, "%s", T(HT_BRING_DAMAGED));
    else snprintf(out, cap, "%s", s->name);
}

static void bring_view(const HfBringSlot slots[HF_SAVE_SLOTS], int selected) {
    HfView *v = ui_begin();
    int s;
    ui_reset(v, HF_SCREEN_MENU);
    snprintf(v->heading, sizeof v->heading, "%s", T(HT_BTN_BRING));
    snprintf(v->state, sizeof v->state, "%s", T(HT_BRING_STATE));
    v->tone = HF_TONE_MUTED;
    for (s = 0; s < HF_SAVE_SLOTS && v->row_count < HF_VIEW_ROWS; s++) {
        char mh4u[48], ours[48];
        bring_side_text(&slots[s].mh4u, mh4u, sizeof mh4u);
        bring_side_text(&slots[s].heavenfall, ours, sizeof ours);
        snprintf(v->rows[v->row_count++], HF_VIEW_LINE, "%s %d\tMH4U: %s   Heavenfall: %s", T(HT_BRING_SLOT), s + 1,
                 mh4u, ours);
    }
    for (s = 0; s < HF_SAVE_SLOTS; s++) {
        char label[HF_VIEW_LABEL];
        snprintf(label, sizeof label, "%s %d", T(HT_BRING_SLOT), s + 1);
        ui_button(v, label, s + 1, 0, slots[s].mh4u.readable && slots[s].mh4u.hunter);
    }
    ui_button(v, T(HT_BRING_COMMON), BRING_COMMON, 0, 1);
    ui_button(v, T(HT_BTN_BACK), BRING_BACK, 0, 1);
    v->selected = selected >= 0 && selected < v->button_count ? selected : 0;
    ui_end();
}

/* What a Bring ended with, said; 1 when it brought something. */
static int bring_said(const HfBringResult *r, int common, const Bring *b) {
    HfText text = HT_BRING_NOT_DONE;
    LOG("bring %s: code %d, joined %d, left over %lu, backed up %d, written %d, rolled back %d, failed '%s'",
        common ? "shared files" : "slot", r->code, r->joined, (unsigned long)r->left_over, r->backed_up, r->written,
        r->rolled_back, r->failed);
    switch (r->code) {
    case HF_BRING_OK:
        ui_message_ex(T(common ? HT_BRING_COMMON_DONE : HT_BRING_DONE), HF_TONE_GOOD, "");
        if (r->left_over) ui_message_ex(T(HT_BRING_LEFT_OVER), HF_TONE_WARN, "");
        return 1;
    case HF_BRING_E_NO_WORLD: text = HT_BRING_NO_WORLD; break;
    case HF_BRING_E_NO_HUNTER: text = HT_BRING_NO_HUNTER; break;
    case HF_BRING_E_NO_JOIN: text = HT_BRING_USE_PC; break;
    case HF_BRING_E_CORRUPT: text = HT_BRING_CORRUPT; break;
    case HF_BRING_E_NOTHING: text = HT_BRING_NOTHING; break;
    case HF_BRING_E_BACKUP: text = HT_SAVE_BACKUP_FAILED; break;
    case HF_BRING_E_WRITE:
        ui_message_ex(T(r->rolled_back ? HT_BRING_FAILED : HT_BRING_FAILED_KEPT), HF_TONE_BAD,
                      r->rolled_back ? "" : b->backup);
        return 0;
    default: break;
    }
    ui_message_ex(T(text), r->code == HF_BRING_E_NOTHING ? HF_TONE_WARN : HF_TONE_BAD, "");
    return 0;
}

static uint32_t bring_seed(void) { return (uint32_t)svcGetSystemTick() ^ (uint32_t)osGetTime() * 2654435761u; }

/* A Bring that was cut (bring.c, hf_bring_recover): the files it wrote put back from its backup set, the player told.
 * 1 when something was put back. */
static int bring_recover(Bring *b, const HfBlowfish *bf) {
    HfSaveIo io = bring_io(b);
    HfBringRecovery v;
    char stamp[HF_BRING_STAMP], dir[PATH_MAX_LEN];
    if (!b->open[HF_BRING_STATE] || !hf_bring_journal_stamp(&io, stamp)) return 0;
    if (hf_path_save_at(app_edition()->slug, HF_SAVE_HEAVENFALL, stamp, dir, sizeof dir)) {
        LOG("recover: the journal names no backup set: '%s'", stamp);
        return 0;
    }
    snprintf(b->backup, sizeof b->backup, "%s", dir + 5);
    hf_bring_recover(&io, bf, &v);
    LOG("recover: set %s, code %d, completed %d, restored %d, kept %d, failed '%s'", stamp, v.code, v.completed,
        v.restored, v.kept, v.failed);
    if (v.code) {
        ui_message_ex(T(HT_BRING_FAILED_KEPT), HF_TONE_BAD, b->backup);
        return 0;
    }
    if (!v.completed && (v.restored || v.kept)) ui_message_ex(T(v.kept ? HT_BRING_CUT_KEPT : HT_BRING_CUT_BACK), HF_TONE_WARN, "");
    return v.restored > 0;
}

/* The page: a slot (asked first when Heavenfall's is taken) or the shared files, until Back. */
static int bring_page(Bring *b, const HfBlowfish *bf) {
    HfSaveIo io = bring_io(b);
    HfBringSlot slots[HF_SAVE_SLOTS];
    HfBringResult r;
    UiEvent ev;
    int s, id, brought = 0, selected = 0;
    for (;;) {
        for (s = 0; s < HF_SAVE_SLOTS; s++)
            if (hf_bring_slot_info(&io, bf, s + 1, &slots[s])) memset(&slots[s], 0, sizeof slots[s]);
        bring_view(slots, selected);
        id = -1;
        while (id == -1 && app_loop(&ev)) id = ui_choose(&ev);
        if (id == -1) return brought ? SAVE_COPIED : SAVE_DECLINED;   /* the console closes */
        if (id == UI_BACK || id == BRING_BACK) break;
        selected = id - 1;   /* the button's place: the slots, then the shared files */
        if (id >= 1 && id <= HF_SAVE_SLOTS) {
            unsigned flags = 0;
            if (hf_bring_taken(&slots[id - 1].heavenfall)) {
                if (!ui_confirm(T(HT_BRING_TAKEN))) continue;
                flags = HF_BRING_REPLACE;
            }
            if (bring_backup_folder(b)) {
                ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
                continue;
            }
            ui_working(T(HT_BRING_WORKING));
            hf_bring_slot(&io, bf, id, flags, bring_seed(), &r);
            brought |= bring_said(&r, 0, b);
        } else if (id == BRING_COMMON) {
            if (!ui_confirm(T(HT_BRING_COMMON_ASK))) continue;
            if (bring_backup_folder(b)) {
                ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
                continue;
            }
            ui_working(T(HT_BRING_WORKING));
            hf_bring_common(&io, &r);
            brought |= bring_said(&r, 1, b);
        }
    }
    installed_save_done();   /* offered and seen: no longer pending */
    return brought ? SAVE_COPIED : SAVE_DECLINED;
}

/* 1 when MH4U's extdata of `region` holds a hunter of the earlier system (`hfuserN`): with Heavenfall's extdata not
 * there, the move waits for the game's first start. Opens and closes MH4U's extdata by itself. */
static int legacy_waiting(Bring *b, int region) {
    u32 mh4u = region == REGION_USA ? HF_MH4U_EXTDATA_USA : HF_MH4U_EXTDATA_EUR;
    int c = HF_BRING_MH4U_EXTDATA, due[HF_SAVE_SLOTS], found;
    HfSaveIo io;
    if (R_FAILED(open_extdata(&b->ar[c], mh4u))) return 0;
    b->open[c] = 1;
    bring_list(b, c);
    bring_open_state(b, region);   /* the record of the moves: a hunter moved before does not wait */
    io = bring_io(b);
    found = hf_bring_legacy_due(&io, due) > 0;
    FSUSER_CloseArchive(b->ar[c]);
    b->open[c] = 0;
    if (b->open[HF_BRING_STATE]) FSUSER_CloseArchive(b->ar[HF_BRING_STATE]);
    b->open[HF_BRING_STATE] = 0;
    return found;
}

/* The edition's region whose Heavenfall extdata opens (the installed title's; installed by the PC program over the
 * original instead, the dump's region first): -1 when none does, then `waiting` says earlier hunters wait for the
 * game's first start. */
static int bring_open_region(Bring *b, int *waiting) {
    int installed = installed_region(), first, k, region = -1;
    first = installed >= 0 ? installed : app.status.region == REGION_USA ? REGION_USA : REGION_EUR;
    *waiting = 0;
    for (k = 0; k < (installed >= 0 ? 1 : 2) && region < 0; k++) {
        int r = k ? (first == REGION_USA ? REGION_EUR : REGION_USA) : first;
        if (bring_open(b, r)) {
            region = r;
        } else {
            *waiting |= legacy_waiting(b, r);
            bring_close(b);
        }
    }
    return region;
}

/* The earlier system's hunters into Heavenfall's extdata by themselves (bring.c, hf_bring_legacy), the files they
 * replace backed up first; the player is told what moved, one line per slot. 1 when something moved. */
static int legacy_run(Bring *b) {
    HfSaveIo io = bring_io(b);
    HfBringLegacy l;
    int slot, due[HF_SAVE_SLOTS];
    if (!hf_bring_legacy_due(&io, due)) return 0;   /* none, or each moved before (the game's delete all changes nothing) */
    if (bring_backup_folder(b)) {
        LOG("legacy: the backup folder could not be named: nothing moved");
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        return 0;
    }
    hf_bring_legacy(&io, &l);
    LOG("legacy: code %d, moved %d%d%d, backed up %d, written %d, rolled back %d, failed '%s'", l.result.code,
        l.moved[0], l.moved[1], l.moved[2], l.result.backed_up, l.result.written, l.result.rolled_back,
        l.result.failed);
    if (l.unrecorded) LOG("legacy: the record of the moves could not be written");
    switch (l.result.code) {
    case HF_BRING_OK: break;
    case HF_BRING_E_BACKUP: ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, ""); return 0;
    case HF_BRING_E_WRITE:
        ui_message_ex(T(l.result.rolled_back ? HT_BRING_FAILED : HT_BRING_FAILED_KEPT), HF_TONE_BAD,
                      l.result.rolled_back ? "" : b->backup);
        return 0;
    default: ui_message_ex(T(HT_BRING_NOT_DONE), HF_TONE_BAD, ""); return 0;
    }
    for (slot = 1; slot <= HF_SAVE_SLOTS; slot++) {
        char label[HF_VIEW_LABEL];
        if (!l.moved[slot - 1]) continue;
        snprintf(label, sizeof label, "%s %d", T(HT_BRING_SLOT), slot);
        ui_message_ex(T(HT_LEGACY_MOVED), HF_TONE_GOOD, label);
    }
    return l.count > 0;
}

/* Said when the earlier hunters wait for Heavenfall's first start (not in a quiet call: the start of the app). */
static void legacy_wait_said(int quiet) {
    LOG("legacy: earlier hunters wait for Heavenfall's first start");
    if (!quiet) ui_message_ex(T(HT_LEGACY_WAIT), HF_TONE_WARN, "");
}

int saves_legacy_move(int quiet) {
    Bring *b;
    HfBlowfish *bf;
    int waiting, region, moved = 0;
    if (!app_edition()->own_save) return 0;   /* Heavenfall Beta plays on MH4U's own files */
    b = (Bring *)calloc(1, sizeof(Bring));
    bf = (HfBlowfish *)malloc(sizeof(HfBlowfish));
    if (!b || !bf) {
        free(b);
        free(bf);
        return 0;
    }
    region = bring_open_region(b, &waiting);
    if (region < 0) {
        if (waiting) legacy_wait_said(quiet);
    } else {
        hf_blowfish_init(bf);
        bring_recover(b, bf);   /* a Bring that was cut comes first: its files back, then the move */
        moved = legacy_run(b);
    }
    bring_close(b);
    free(b);
    free(bf);
    return moved;
}

static int bring_flow(int quiet) {
    Bring *b = (Bring *)calloc(1, sizeof(Bring));
    HfBlowfish *bf = (HfBlowfish *)malloc(sizeof(HfBlowfish));
    int region, result, waiting;
    if (!b || !bf) {
        free(b);
        free(bf);
        if (!quiet) ui_message_ex(T(HT_BRING_NOT_DONE), HF_TONE_BAD, "");
        return SAVE_FAILED;
    }
    region = bring_open_region(b, &waiting);
    if (region < 0) {   /* the game makes its extdata at its first start: the launcher never does */
        LOG("bring: Heavenfall's extdata is not there yet");
        if (waiting) legacy_wait_said(quiet);
        else if (!quiet) ui_message(T(HT_BRING_NO_WORLD));
        result = SAVE_NOT_RUN;
    } else {
        hf_blowfish_init(bf);
        bring_recover(b, bf);   /* a Bring that was cut: its files back from its backup set */
        legacy_run(b);   /* by themselves, whenever the page opens */
        if (!b->open[HF_BRING_MH4U_SAVE]) {
            LOG("bring: no original game's save");
            if (!quiet) ui_message(T(HT_SAVE_NONE));
            result = SAVE_NO_ORIGINAL;
        } else if (quiet && !ui_confirm(T(HT_BRING_OFFER))) {
            LOG("bring: declined");
            installed_save_done();
            result = SAVE_DECLINED;
        } else {
            LOG("bring: region %s, Heavenfall's extdata %08lX", region_name(region), (unsigned long)b->heavenfall_id);
            result = bring_page(b, bf);
        }
    }
    bring_close(b);
    free(b);
    free(bf);
    return result;
}

int saves_copy_flow(int quiet) {
    /* the full mod's game plays on Heavenfall's own extdata; Heavenfall Beta's on the title's save, as before */
    return app_edition()->own_save ? bring_flow(quiet) : title_copy_flow(quiet);
}

/* ---- More > MH4U saves ----
 * Heavenfall Beta's game keeps plain MH4U files in its title's save archive. "Take my save to MH4U" writes a slot's
 * `userN` (or `system`) of it into the original game's save archive (of the edition's region; the player picks the
 * cartridge or the digital one when both are there, `pick_original`): exactly those four names with the sizes MH4U's files have, never a wipe, never a file it does not
 * know. Both saves are backed up on the card first (saves/<stamp>/heavenfall and /original); a record on the card
 * (`to_mh4u`: the backup set and the files written) lets "Restore MH4U's save" put the files back. The write is
 * committed and read back before the player is told it is done; a failure puts MH4U's files back from what was read
 * before. Rules and the clean check are to_mh4u.c's (portable, tested on the PC). */

#define TO_RECORD "to_mh4u"   /* in the launcher's folder on the card: the last move's record */
enum { TO_SHARED = HF_TO_MH4U_SLOTS + 1, TO_BACK };   /* the page's buttons past the slots' 1-3 */

typedef struct {
    FS_Archive beta, mh4u, sd;
    int have_beta, have_mh4u, have_sd;
    int region;
    u64 beta_id, mh4u_id;
    FS_MediaType media;   /* the medium of the MH4U used: shown on the page */
    char last[18];       /* the backup set this page made last: the next is another (never over it) */
} ToWorld;

static void to_close(ToWorld *w) {
    if (w->have_beta) FSUSER_CloseArchive(w->beta);
    if (w->have_mh4u) FSUSER_CloseArchive(w->mh4u);
    if (w->have_sd) FSUSER_CloseArchive(w->sd);
    memset(w, 0, sizeof *w);
}

/* The edition's installed title, the original game of its region and the card, opened; 0 and the reason said when not.
 * The original game's archive must exist (MH4U was run once) and be of the edition's region: the other region's is
 * never written (hf_title_original). `need_beta`: the title's own save too (not for the restore). */
static int to_open(ToWorld *w, int need_beta) {
    FS_MediaType media;
    memset(w, 0, sizeof *w);
    if ((w->region = installed_region()) < 0) {
        ui_message(T(HT_NOT_INSTALLED));
        return 0;
    }
    w->beta_id = edition_title_id(w->region);
    if (!hf_title_ours(w->beta_id)) {
        LOG("to mh4u: %016llX is not Heavenfall's: nothing done", (unsigned long long)w->beta_id);
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        return 0;
    }
    if (!pick_original(w->region, &w->mh4u_id, &media)) {
        ui_message(T(HT_SAVE_NONE));
        return 0;
    }
    if (!hf_title_original(w->mh4u_id, w->region == REGION_USA)) {   /* the other region's MH4U: never written */
        LOG("to mh4u: the original found is %016llX, not this region's", (unsigned long long)w->mh4u_id);
        ui_message_ex(T(HT_TO_MH4U_OTHER_REGION), HF_TONE_BAD, "");
        return 0;
    }
    if (R_FAILED(open_save(&w->mh4u, media, w->mh4u_id))) {
        ui_message(T(HT_TO_MH4U_NO_ARCHIVE));
        return 0;
    }
    w->media = media;
    w->have_mh4u = 1;
    if (need_beta) {
        if (R_FAILED(open_save(&w->beta, MEDIATYPE_SD, w->beta_id))) {
            to_close(w);
            ui_message(T(HT_SAVE_NEED_RUN));
            return 0;
        }
        w->have_beta = 1;
    }
    if (R_FAILED(open_sd(&w->sd))) {
        to_close(w);
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        return 0;
    }
    w->have_sd = 1;
    return 1;
}

/* `buf` as the whole file at `path` of `ar` (the file deleted and made again with its size, as copy_file does). 0 done. */
static int to_put(FS_Archive ar, const char *path, const uint8_t *buf, u32 size) {
    Handle out = 0;
    u32 at = 0;
    int bad = 1;
    FSUSER_DeleteFile(ar, fsMakePath(PATH_ASCII, path));
    if (R_SUCCEEDED(FSUSER_CreateFile(ar, fsMakePath(PATH_ASCII, path), 0, size)) &&
        R_SUCCEEDED(FSUSER_OpenFile(&out, ar, fsMakePath(PATH_ASCII, path), FS_OPEN_WRITE, 0))) {
        bad = 0;
        while (at < size && !bad) {
            u32 n = size - at < COPY_CHUNK ? size - at : COPY_CHUNK, put = 0;
            bad = R_FAILED(FSFILE_Write(out, &put, at, buf + at, n, 0)) || put != n;
            at += n;
        }
        if (!bad && R_FAILED(FSFILE_Flush(out))) bad = 1;
    }
    if (out) FSFILE_Close(out);
    return bad;
}

typedef struct {
    int index;           /* hf_to_file */
    uint8_t *put;        /* what MH4U's file becomes, NULL: the file is deleted */
    uint8_t *pre;        /* what it holds now (NULL: it has none), for the way back */
    u32 pre_size;
} ToChange;

/* One path's state of `ar` against `want` (NULL: must be absent): 1 when it is. */
static int to_is(FS_Archive ar, const char *path, const uint8_t *want, u32 size) {
    u32 got = 0;
    int state;
    uint8_t *now = sd_read_state(ar, path, &got, &state);
    int same = want ? now && got == size && !memcmp(now, want, size) : state == FILE_ABSENT;   /* an unreadable file is not "absent" */
    free(now);
    return same;
}

/* The changes into MH4U's archive: written, committed and read back. A failure puts every file back from `pre` and
 * commits again (*rolled_back: all are as they were). Returns 1 when it failed. The only writer of the original
 * game's save: both titles' ids are asked here (the original of the region, the edition's own). */
static int to_apply(ToWorld *w, ToChange *c, int n, int *rolled_back) {
    int i, bad = 0;
    Result rc;
    *rolled_back = 0;
    if (!hf_title_original(w->mh4u_id, w->region == REGION_USA) || !hf_title_ours(w->beta_id)) return 1;
    for (i = 0; i < n && !bad; i++) {
        char path[24];
        const HfToFile *f = hf_to_file(c[i].index);
        snprintf(path, sizeof path, "/%s", f->name);
        bad = c[i].put ? to_put(w->mh4u, path, c[i].put, f->size)
                       : R_FAILED(FSUSER_DeleteFile(w->mh4u, fsMakePath(PATH_ASCII, path)));
    }
    if (!bad) {
        rc = FSUSER_ControlArchive(w->mh4u, ARCHIVE_ACTION_COMMIT_SAVE_DATA, NULL, 0, NULL, 0);
        LOGR("to mh4u commit", rc);
        bad = R_FAILED(rc);
    }
    for (i = 0; i < n && !bad; i++) {
        char path[24];
        const HfToFile *f = hf_to_file(c[i].index);
        snprintf(path, sizeof path, "/%s", f->name);
        bad = !to_is(w->mh4u, path, c[i].put, f->size);
        if (bad) LOG("to mh4u: %s does not read back", f->name);
    }
    if (bad) {   /* every file back from what was read before the first write */
        int all = 1;
        for (i = n - 1; i >= 0; i--) {
            char path[24];
            const HfToFile *f = hf_to_file(c[i].index);
            snprintf(path, sizeof path, "/%s", f->name);
            if (c[i].pre ? to_put(w->mh4u, path, c[i].pre, c[i].pre_size)
                         : (FSUSER_DeleteFile(w->mh4u, fsMakePath(PATH_ASCII, path)), 0))
                all = 0;
        }
        rc = FSUSER_ControlArchive(w->mh4u, ARCHIVE_ACTION_COMMIT_SAVE_DATA, NULL, 0, NULL, 0);
        LOGR("to mh4u rollback commit", rc);
        for (i = 0; i < n && all; i++) {
            char path[24];
            const HfToFile *f = hf_to_file(c[i].index);
            snprintf(path, sizeof path, "/%s", f->name);
            if (!to_is(w->mh4u, path, c[i].pre, c[i].pre_size)) all = 0;
        }
        *rolled_back = all && R_SUCCEEDED(rc);
    }
    return bad;
}

/* A backup set's name that is not `avoid` (a second move in the same second waits for the next). 0 on success. */
static int to_stamp(char stamp[18], const char *avoid) {
    int tries;
    for (tries = 0; tries < 20; tries++) {
        stamp_now(stamp);
        if (strcmp(stamp, avoid)) return 0;
        svcSleepThread(100000000LL);
    }
    return 1;
}

/* The record's path on the card, without "sdmc:". 0 on success. */
static int to_record_path(char *out, size_t cap) {
    char dir[PATH_MAX_LEN];
    if (hf_path_dir(app_edition()->slug, dir, sizeof dir)) return 1;
    snprintf(out, cap, "%s/%s", dir + 5, TO_RECORD);
    return 0;
}

static void to_failed(const ToWorld *w, int rolled_back, const char *stamp) {
    char dir[PATH_MAX_LEN];
    (void)w;
    if (!rolled_back && !hf_path_save_at(app_edition()->slug, HF_SAVE_ORIGINAL, stamp, dir, sizeof dir)) {
        ui_message_ex(T(HT_TO_MH4U_FAILED_KEPT), HF_TONE_BAD, dir);
        return;
    }
    ui_message_ex(T(HT_TO_MH4U_FAILED), HF_TONE_BAD, "");
}

/* Beta's `index` (a slot's userN or `system`) into MH4U's save. 1 when it went. The player's questions were asked. */
static int to_take(ToWorld *w, int index) {
    const HfToFile *f = hf_to_file(index);
    char path[24], stamp[18], rec_path[PATH_MAX_LEN], rec[HF_TO_RECORD_MAX];
    uint8_t *mine = NULL, *theirs = NULL;
    u32 mine_size = 0, theirs_size = 0;
    ToChange change;
    HfToRecord record;
    uint8_t *old_rec = NULL;   /* the record of the last good move, written back when this one is rolled back */
    u32 old_rec_size = 0;
    int bad, rolled_back = 0, result = 0, mine_state = FILE_BAD, theirs_state = FILE_BAD, old_state;
    if (!f) return 0;
    snprintf(path, sizeof path, "/%s", f->name);
    mine = sd_read_state(w->beta, path, &mine_size, &mine_state);
    theirs = sd_read_state(w->mh4u, path, &theirs_size, &theirs_state);
    /* unknown sizes, or a file that is there but cannot be read (only "not found" is absent): nothing is touched */
    if (!mine || mine_size != f->size || (theirs ? theirs_size != f->size : theirs_state != FILE_ABSENT)) {
        LOG("to mh4u: %s is %lu bytes here and %lu there (read %d / %d)", f->name, (unsigned long)mine_size,
            (unsigned long)theirs_size, mine_state, theirs_state);
        ui_message_ex(T(HT_TO_MH4U_BAD_FILE), HF_TONE_BAD, "");
        goto done;
    }
    ui_working(T(HT_SAVE_BACKING_UP));
    if (to_stamp(stamp, w->last) || backup(w->beta, w->sd, HF_SAVE_HEAVENFALL, stamp) || backup(w->mh4u, w->sd, HF_SAVE_ORIGINAL, stamp)) {
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        goto done;
    }
    snprintf(w->last, sizeof w->last, "%s", stamp);
    memset(&record, 0, sizeof record);
    snprintf(record.stamp, sizeof record.stamp, "%s", stamp);
    record.count = 1;
    record.index[0] = index;
    record.existed[0] = theirs != NULL;
    if (!to_record_path(rec_path, sizeof rec_path)) old_rec = sd_read_state(w->sd, rec_path, &old_rec_size, &old_state);
    if (to_record_path(rec_path, sizeof rec_path) || !hf_to_record_text(&record, rec, sizeof rec) ||
        sd_write_whole(w->sd, rec_path, (const uint8_t *)rec, (u32)strlen(rec))) {   /* the restore's way in */
        if (old_rec) sd_write_whole(w->sd, rec_path, old_rec, old_rec_size);   /* the last good move stays restorable */
        (void)old_state;
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        goto done;
    }
    ui_working(T(HT_TO_MH4U_WORKING));
    change.index = index;
    change.put = mine;
    change.pre = theirs;
    change.pre_size = theirs_size;
    bad = to_apply(w, &change, 1, &rolled_back);
    LOG("to mh4u: %s %s", f->name, bad ? "failed" : "done");
    if (bad) {
        if (rolled_back) {   /* nothing was changed: the record is the last good move's again (none: no record) */
            if (old_rec) sd_write_whole(w->sd, rec_path, old_rec, old_rec_size);
            else FSUSER_DeleteFile(w->sd, fsMakePath(PATH_ASCII, rec_path));
        }
        to_failed(w, rolled_back, stamp);
    } else {
        ui_message_ex(T(HT_TO_MH4U_DONE), HF_TONE_GOOD, "");
        result = 1;
    }
done:
    free(mine);
    free(theirs);
    free(old_rec);
    return result;
}

static void to_side_text(const HfToSide *s, char *out, size_t cap) {
    if (!s->present || (s->readable && !s->hunter)) snprintf(out, cap, "%s", T(HT_BRING_EMPTY));
    else if (!s->readable) snprintf(out, cap, "%s", T(HT_BRING_DAMAGED));
    else {
        char time[16];
        hf_to_time_text(s->play_time, time, sizeof time);
        snprintf(out, cap, "%s %s", s->name, time);
    }
}

static void to_view(const HfToSide beta[HF_TO_MH4U_SLOTS], const HfToSide mh4u[HF_TO_MH4U_SLOTS], int selected,
                    FS_MediaType media) {
    HfView *v = ui_begin();
    int s, differ = 0;
    ui_reset(v, HF_SCREEN_MENU);
    snprintf(v->heading, sizeof v->heading, "%s", T(HT_BTN_TO_MH4U));
    snprintf(v->state, sizeof v->state, "%s %s.", T(HT_TO_MH4U_STATE), media_text(media));
    v->tone = HF_TONE_MUTED;
    for (s = 0; s < HF_TO_MH4U_SLOTS && v->row_count < HF_VIEW_ROWS; s++) {
        char b[56], m[56];
        int d = hf_to_different(&beta[s], &mh4u[s]);   /* two hunters sharing the slot's card file in MH4U's data */
        differ |= d;
        to_side_text(&beta[s], b, sizeof b);
        to_side_text(&mh4u[s], m, sizeof m);
        snprintf(v->rows[v->row_count++], HF_VIEW_LINE, "%s %d%s\tBeta: %s   MH4U: %s", T(HT_BRING_SLOT), s + 1,
                 d ? " (!)" : "", b, m);
    }
    if (differ) snprintf(v->detail, sizeof v->detail, "%s", T(HT_TO_MH4U_DIFFER));
    for (s = 0; s < HF_TO_MH4U_SLOTS; s++) {
        char label[HF_VIEW_LABEL];
        snprintf(label, sizeof label, "%s %d", T(HT_BRING_SLOT), s + 1);
        ui_button(v, label, s + 1, 0, beta[s].readable && beta[s].hunter);
    }
    ui_button(v, T(HT_TO_MH4U_SHARED), TO_SHARED, 0, 1);
    ui_button(v, T(HT_BTN_BACK), TO_BACK, 0, 1);
    v->selected = selected >= 0 && selected < v->button_count ? selected : 0;
    ui_end();
}

/* The page of "Take my save to MH4U" until Back. */
static int to_mh4u_flow(void) {
    ToWorld w;
    HfBlowfish *bf = (HfBlowfish *)malloc(sizeof(HfBlowfish));
    HfToSide beta[HF_TO_MH4U_SLOTS], mh4u[HF_TO_MH4U_SLOTS];
    UiEvent ev;
    int s, id, moved = 0, selected = 0;
    if (!bf) {
        ui_message_ex(T(HT_TO_MH4U_FAILED), HF_TONE_BAD, "");
        return SAVE_FAILED;
    }
    hf_blowfish_init(bf);
    if (!to_open(&w, 1)) {
        free(bf);
        return SAVE_NOT_RUN;
    }
    for (;;) {
        for (s = 0; s < HF_TO_MH4U_SLOTS; s++) {
            char path[24];
            u32 size = 0;
            uint8_t *raw;
            snprintf(path, sizeof path, "/%s", hf_to_file(s)->name);
            raw = sd_read_whole(w.beta, path, &size);
            if (hf_to_side(bf, raw, size, &beta[s])) memset(&beta[s], 0, sizeof beta[s]);
            free(raw);
            raw = sd_read_whole(w.mh4u, path, &size);
            if (hf_to_side(bf, raw, size, &mh4u[s])) memset(&mh4u[s], 0, sizeof mh4u[s]);
            free(raw);
        }
        to_view(beta, mh4u, selected, w.media);
        id = -1;
        while (id == -1 && app_loop(&ev)) id = ui_choose(&ev);
        if (id == -1 || id == UI_BACK || id == TO_BACK) break;   /* (the console closing too) */
        selected = id - 1;
        if (id >= 1 && id <= HF_TO_MH4U_SLOTS) {
            if (!beta[id - 1].clean) {   /* not plain MH4U's: loaded and saved in Beta first */
                ui_message_ex(T(HT_TO_MH4U_NOT_CLEAN), HF_TONE_WARN, "");
                continue;
            }
            if (!ui_confirm(T(HT_TO_MH4U_ASK))) continue;
            if (hf_to_going_back(&beta[id - 1], &mh4u[id - 1]) && !ui_confirm(T(HT_TO_MH4U_BACK))) continue;
            moved |= to_take(&w, id - 1);
        } else if (id == TO_SHARED) {
            if (!ui_confirm(T(HT_TO_MH4U_SHARED_ASK))) continue;
            moved |= to_take(&w, HF_TO_MH4U_SLOTS);
        }
    }
    to_close(&w);
    free(bf);
    return moved ? SAVE_COPIED : SAVE_DECLINED;
}

/* "Restore MH4U's save": the files the last move wrote, from the backup set it made (the record on the card). */
static int to_undo_flow(void) {
    ToWorld w;
    char rec_path[PATH_MAX_LEN], dir[PATH_MAX_LEN], now[18];
    uint8_t *text = NULL;
    u32 text_size = 0;
    HfToRecord rec;
    ToChange change[HF_TO_MH4U_FILES];
    int i, n = 0, bad = 1, rolled_back = 0, result = SAVE_FAILED;
    memset(change, 0, sizeof change);
    if (!to_open(&w, 0)) return SAVE_NOT_RUN;
    if (to_record_path(rec_path, sizeof rec_path) || !(text = sd_read_whole(w.sd, rec_path, &text_size)) ||
        !hf_to_record_parse((const char *)text, text_size, &rec) || !hf_save_stamp_ok(rec.stamp) ||
        hf_path_save_at(app_edition()->slug, HF_SAVE_ORIGINAL, rec.stamp, dir, sizeof dir)) {
        ui_message(T(HT_UNDO_NONE));
        result = SAVE_NOT_RUN;
        goto done;
    }
    for (i = 0; i < rec.count; i++) {   /* the backup set must still hold each file it had, whole */
        const HfToFile *f = hf_to_file(rec.index[i]);
        char path[PATH_MAX_LEN], mine[24];
        u32 got = 0;
        int pre_state;
        snprintf(mine, sizeof mine, "/%s", f->name);
        snprintf(path, sizeof path, "%s/%s", dir + 5, f->name);
        change[n].index = rec.index[i];
        change[n].pre = sd_read_state(w.mh4u, mine, &change[n].pre_size, &pre_state);
        if (!change[n].pre && pre_state != FILE_ABSENT) {   /* there but unreadable: not taken as absent */
            LOG("to mh4u restore: %s cannot be read: nothing is touched", f->name);
            ui_message_ex(T(HT_TO_MH4U_BAD_FILE), HF_TONE_BAD, "");
            result = SAVE_FAILED;
            n++;
            goto done;
        }
        if (rec.existed[i]) {
            change[n].put = sd_read_whole(w.sd, path, &got);
            if (!change[n].put || got != f->size) {
                ui_message(T(HT_UNDO_NONE));
                result = SAVE_NOT_RUN;
                n++;
                goto done;
            }
        }
        n++;
    }
    if (!ui_confirm(T(HT_UNDO_ASK))) {
        result = SAVE_DECLINED;
        goto done;
    }
    ui_working(T(HT_SAVE_BACKING_UP));
    if (to_stamp(now, rec.stamp) || backup(w.mh4u, w.sd, HF_SAVE_ORIGINAL, now)) {   /* what it holds now, in a folder of its own */
        ui_message_ex(T(HT_SAVE_BACKUP_FAILED), HF_TONE_BAD, "");
        goto done;
    }
    ui_working(T(HT_TO_MH4U_WORKING));
    bad = to_apply(&w, change, n, &rolled_back);
    LOG("to mh4u restore from %s: %s", rec.stamp, bad ? "failed" : "done");
    if (bad) {
        to_failed(&w, rolled_back, now);
    } else {
        FSUSER_DeleteFile(w.sd, fsMakePath(PATH_ASCII, rec_path));   /* done: nothing left to put back */
        ui_message_ex(T(HT_UNDO_DONE), HF_TONE_GOOD, "");
        result = SAVE_COPIED;
    }
done:
    for (i = 0; i < n; i++) {
        free(change[i].put);
        free(change[i].pre);
    }
    free(text);
    to_close(&w);
    return result;
}

enum { SV_BRING = 1, SV_TO, SV_UNDO, SV_BACK };

static void saves_view(int selected) {
    HfView *v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    snprintf(v->heading, sizeof v->heading, "%s", T(HT_BTN_SAVES));
    snprintf(v->state, sizeof v->state, "%s", T(HT_SAVES_STATE));
    v->tone = HF_TONE_MUTED;
    ui_button(v, T(HT_BTN_SAVE), SV_BRING, 0, 1);   /* "Bring my MH4U save", the page's first */
    ui_button(v, T(HT_BTN_TO_MH4U), SV_TO, 0, 1);
    ui_button(v, T(HT_BTN_UNDO_TO_MH4U), SV_UNDO, 0, 1);
    ui_button(v, T(HT_BTN_BACK), SV_BACK, 0, 1);
    v->selected = selected >= 0 && selected < v->button_count ? selected : 0;
    ui_end();
}

void saves_mh4u_page(void) {
    UiEvent ev;
    int id, at = 0;
    for (;;) {
        saves_view(at);
        id = -1;
        while (id == -1 && app_loop(&ev)) id = ui_choose(&ev);
        if (id == -1 || id == UI_BACK || id == SV_BACK) return;
        at = id - 1;
        if (id == SV_BRING) saves_copy_flow(0);
        else if (id == SV_TO) to_mh4u_flow();
        else if (id == SV_UNDO) to_undo_flow();
    }
}

/* ---- More's Cheats: the game's cheats file ----
 * The game always carries the Cheats group, hidden and inert, and shows it while the 16-byte file `hfcheat` of its
 * extdata (Heavenfall's own for an edition that plays on it, else MH4U's) says on. Only that one name is ever written
 * into MH4U's extdata (hf_extdata_file_ok), created at 16 bytes when missing, written in place, never deleted. */

/* Opens the installed title's extdata: 1 when it opened (the game has made it). */
static int cheat_flag_archive(FS_Archive *ar, u32 *id) {
    int region = installed_region();
    if (region < 0) {
        LOG("cheats file: no title installed");
        return 0;
    }
    if (app_edition()->own_save) *id = region == REGION_USA ? HF_HEAVENFALL_EXTDATA_USA : HF_HEAVENFALL_EXTDATA_EUR;
    else *id = region == REGION_USA ? HF_MH4U_EXTDATA_USA : HF_MH4U_EXTDATA_EUR;
    return R_SUCCEEDED(open_extdata(ar, *id));
}

static FS_Path cheat_flag_path(u16 wide[HF_CHEAT_FLAG_SIZE]) {
    size_t i;
    wide[0] = '/';
    for (i = 0; HF_CHEAT_FLAG_NAME[i]; i++) wide[i + 1] = (u8)HF_CHEAT_FLAG_NAME[i];
    wide[i + 1] = 0;
    return fsMakePath(PATH_UTF16, wide);
}

/* The file's state in an open extdata: CHEAT_FLAG_ON, OFF (a file that says off or is not valid) or MISSING. */
static int cheat_flag_read(FS_Archive ar) {
    Handle h;
    u16 wide[HF_CHEAT_FLAG_SIZE];
    uint8_t buf[HF_CHEAT_FLAG_SIZE];
    u32 got = 0;
    Result rc = FSUSER_OpenFile(&h, ar, cheat_flag_path(wide), FS_OPEN_READ, 0);
    if (R_FAILED(rc)) {
        LOG("cheats file: not there (0x%08lX)", (unsigned long)rc);
        return CHEAT_FLAG_MISSING;
    }
    rc = FSFILE_Read(h, &got, 0, buf, sizeof buf);
    FSFILE_Close(h);
    if (R_FAILED(rc)) got = 0;
    LOG("cheats file: read %lu bytes", (unsigned long)got);
    return hf_cheat_flag_parse(buf, got) ? CHEAT_FLAG_ON : CHEAT_FLAG_OFF;
}

/* Writes the file in an open extdata of `id`; 1 when written. */
static int cheat_flag_write(FS_Archive ar, u32 id, int on) {
    Handle h;
    u16 wide[HF_CHEAT_FLAG_SIZE];
    uint8_t buf[HF_CHEAT_FLAG_SIZE];
    u32 put = 0;
    int bad;
    Result rc;
    if (!hf_extdata_file_ok(id, HF_CHEAT_FLAG_NAME)) {
        LOG("cheats file: write refused (extdata %08lX)", (unsigned long)id);
        return 0;
    }
    hf_cheat_flag_encode(on, buf);
    rc = FSUSER_OpenFile(&h, ar, cheat_flag_path(wide), FS_OPEN_WRITE, 0);
    if (R_FAILED(rc)) {
        LOG("cheats file: not there, creating it (0x%08lX)", (unsigned long)rc);
        if (R_FAILED(rc = FSUSER_CreateFile(ar, cheat_flag_path(wide), 0, HF_CHEAT_FLAG_SIZE)) ||
            R_FAILED(rc = FSUSER_OpenFile(&h, ar, cheat_flag_path(wide), FS_OPEN_WRITE, 0))) {
            LOG("cheats file: not made: 0x%08lX", (unsigned long)rc);
            return 0;
        }
    }
    bad = R_FAILED(FSFILE_Write(h, &put, 0, buf, sizeof buf, 0)) || put != sizeof buf || R_FAILED(FSFILE_Flush(h));
    FSFILE_Close(h);
    LOG("cheats file: %s written: %s", on ? "on" : "off", bad ? "failed" : "done");
    return !bad;
}

void cheat_flag_refresh(void) {
    FS_Archive ar;
    u32 id = 0;
    HfInstalled rec;
    int have_rec;
    app.status.cheat_flag = CHEAT_FLAG_NO_EXTDATA;
    if (!app.status.title_installed || !cheat_flag_archive(&ar, &id)) return;
    app.status.cheat_flag = cheat_flag_read(ar);
    have_rec = read_installed_record(&rec);
    if (hf_cheat_flag_migrates(have_rec ? &rec : NULL, app.status.cheat_flag != CHEAT_FLAG_MISSING)) {
        LOG("cheats file: the 0.2.1 record had the cheats on: writing the file once");
        if (cheat_flag_write(ar, id, 1)) app.status.cheat_flag = cheat_flag_read(ar);
    }
    FSUSER_CloseArchive(ar);
    LOG("cheats file: state %d", app.status.cheat_flag);
}

int cheat_flag_set(int on) {
    FS_Archive ar;
    u32 id = 0;
    int ok;
    if (!cheat_flag_archive(&ar, &id)) {
        app.status.cheat_flag = CHEAT_FLAG_NO_EXTDATA;
        return 0;
    }
    ok = cheat_flag_write(ar, id, on) && (cheat_flag_read(ar) == CHEAT_FLAG_ON) == (on != 0);
    app.status.cheat_flag = cheat_flag_read(ar);
    FSUSER_CloseArchive(ar);
    LOG("cheats file: asked %d, state %d: %s", on, app.status.cheat_flag, ok ? "ok" : "failed");
    return ok;
}
