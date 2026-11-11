/* What the screens show: the installed title's version (from its TMD) and record, the dumps (MH4U's and MH XX's),
 * Luma3DS and the free space; and the card's small files (read whole, written whole). */
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "ctr_title.h"
#include "dump.h"

uint64_t edition_title_id(int region) {
    return strtoull(region == REGION_USA ? app_edition()->title_usa : app_edition()->title_eur, NULL, 16);
}

uint64_t game_title_id(int region) { return hf_game_title_id(edition_title_id(region)); }

long read_small(const char *path, char *buf, size_t cap) {
    FILE *f;
    size_t n;
    char tmp[320];
    if (!cap) return -1;
    /* write_whole removes the file before it renames the new one in: a power cut between the two leaves only the whole
     * .tmp, which becomes the file (a .tmp cut while it was written leaves the old file there, so it is not used). */
    if (!(f = fopen(path, "rb")) && snprintf(tmp, sizeof tmp, "%s.tmp", path) < (int)sizeof tmp && !rename(tmp, path))
        f = fopen(path, "rb");
    if (!f) return -1;
    n = fread(buf, 1, cap - 1, f);
    if (n == cap - 1 && fgetc(f) != EOF) n = cap;
    fclose(f);
    if (n >= cap) {
        buf[0] = 0;
        return -1;
    }
    buf[n] = 0;
    return (long)n;
}

int write_whole(const char *path, const char *text, size_t len) {
    char tmp[320];
    FILE *f;
    int bad;
    if (snprintf(tmp, sizeof tmp, "%s.tmp", path) >= (int)sizeof tmp || !(f = fopen(tmp, "wb"))) return -1;
    bad = fwrite(text, 1, len, f) != len;
    bad |= fclose(f) != 0;
    if (bad) {
        remove(tmp);
        return -1;
    }
    remove(path);   /* the card's file system renames onto no existing file */
    return rename(tmp, path) ? -1 : 0;
}

/* installed.json's contents for this edition; 0 when it is missing or broken. */
int read_installed_record(HfInstalled *rec) {
    char path[256], text[HF_INSTALLED_MAX];
    long n;
    memset(rec, 0, sizeof *rec);
    if (hf_path_installed(app_edition()->slug, path, sizeof path) || (n = read_small(path, text, sizeof text)) < 0)
        return 0;
    return hf_installed_parse(text, (size_t)n, rec) == 0;
}

/* The edition's installed title: the dump's region first, as the update installs it and the start and the save copy
 * take it (with both regions installed, the other one's version would ask for the same update again and again). */
static void find_installed(Status *s) {
    int first = s->region == REGION_USA ? REGION_USA : REGION_EUR, k;
    s->title_installed = 0;
    s->installed_region = -1;
    for (k = 0; k < 2; k++) {
        int r = k ? (first == REGION_USA ? REGION_EUR : REGION_USA) : first;
        u64 id = edition_title_id(r);
        AM_TitleEntry entry;
        if (ctr_title_installed(id) && R_SUCCEEDED(AM_GetTitleInfo(MEDIATYPE_SD, 1, &id, &entry))) {
            s->title_installed = 1;
            s->installed_region = r;
            hf_tmd_version_text(entry.version, s->installed, sizeof s->installed);
            return;
        }
    }
}

static void find_dump_file(Status *s) {
    FileApi api;
    void *h;
    uint64_t size, id = 0;
    int rc, other = 0;
    u8 cfg_region = 0xFF;
    int prefer, installed, eur, usa;
    s->dump = DUMP_NONE;
    s->region = -1;
    ctr_file_api(&api);
    if (R_SUCCEEDED(cfguInit())) {
        if (R_FAILED(CFGU_SecureInfoGetRegion(&cfg_region))) cfg_region = 0xFF;
        cfguExit();
    }
    /* with both regions' dumps on the card, the installed edition's region (asked of AM here: this runs before
     * find_installed, which then follows the dump's region), else the console's: a stable choice */
    eur = ctr_title_installed(edition_title_id(REGION_EUR));
    usa = ctr_title_installed(edition_title_id(REGION_USA));
    installed = eur && !usa ? REGION_EUR : usa && !eur ? REGION_USA : -1;
    prefer = hf_preferred_dump_region(installed, cfg_region == 0xFF ? -1 : (int)cfg_region);
    rc = prefer < 0 ? TITLE_E_FORMAT
                    : find_dump(&api, FIND_DUMP_DIRS, FIND_DUMP_DIR_COUNT, prefer == REGION_USA ? DUMP_ID_USA : DUMP_ID_EUR,
                                s->dump_path, sizeof s->dump_path, NULL);
    if (rc != TITLE_OK)
        rc = find_dump(&api, FIND_DUMP_DIRS, FIND_DUMP_DIR_COUNT, 0, s->dump_path, sizeof s->dump_path, &other);
    LOG("status: dump wanted of region %d (installed %d, console %d)", prefer, installed,
        cfg_region == 0xFF ? -1 : (int)cfg_region);
    if (rc == TITLE_E_ENCRYPTED) { s->dump = DUMP_ENCRYPTED; return; }
    if (rc) return;
    s->dump = DUMP_FOUND;
    if (!api.open(api.ctx, s->dump_path, &h, &size)) {
        s->dump_bytes = size;
        if (!dump_identify(api.read, api.ctx, h, &id, NULL)) s->region = id == DUMP_ID_USA ? REGION_USA : REGION_EUR;
        {
            uint8_t hash[32];
            if (!dump_romfs_hash(api.read, api.ctx, h, hash)) hf_hex(hash, s->dump_hash);
        }
        api.close(api.ctx, h);
    }
}

/* The player's MH XX dump in the same folders, and its revision. "Another version" once a release's XX set was read
 * and does not name it (app_update.c, the start's check). */
static void find_xx_dump(Status *s) {
    FileApi api;
    void *h;
    uint64_t size;
    int rc;
    s->xx = XX_NONE;
    ctr_file_api(&api);
    rc = find_dump(&api, FIND_DUMP_DIRS, FIND_DUMP_DIR_COUNT, DUMP_ID_XX, s->xx_path, sizeof s->xx_path, NULL);
    if (rc == TITLE_E_ENCRYPTED) { s->xx = XX_ENCRYPTED; return; }
    if (rc || api.open(api.ctx, s->xx_path, &h, &size)) return;
    rc = dump_romfs_hash(api.read, api.ctx, h, s->xx_hash);
    api.close(api.ctx, h);
    if (rc) return;
    s->xx = app.xx_check.known && app.xx_check.edition == app.edition && !app.xx_check.matches &&
            !memcmp(app.xx_check.hash, s->xx_hash, sizeof s->xx_hash) ? XX_OTHER_VERSION : XX_FOUND;
}

int status_xx_tried(void) {
    const Status *s = &app.status;
    char now[65];
    if (!s->title_installed || s->installed_xx || !s->installed_xx_dump[0] || (s->xx != XX_FOUND && s->xx != XX_OTHER_VERSION))
        return 0;
    hf_hex(s->xx_hash, now);
    return !strcmp(now, s->installed_xx_dump);
}

int status_xx_came(const char *tag, int xx_set_in_release) {
    const Status *s = &app.status;
    HfPlanIn in;
    if (!s->title_installed || !s->installed[0]) return 0;
    memset(&in, 0, sizeof in);
    in.release_tag = tag;
    in.mod_version = s->installed;
    in.mod_xx = s->installed_xx;
    in.xx_dump = s->xx == XX_FOUND || s->xx == XX_OTHER_VERSION;
    in.xx_set_in_release = xx_set_in_release;
    in.xx_no_room = s->installed_xx_no_room;
    in.xx_tried = status_xx_tried();
    return hf_xx_came(&in);
}

static void find_luma(Status *s) {
    s64 out = 0;
    s->luma = 0;
    if (R_SUCCEEDED(svcGetSystemInfo(&out, 0x10000, 0))) {
        s->luma = 1;
        snprintf(s->luma_version, sizeof s->luma_version, "%d.%d.%d", (int)(out >> 24 & 0xFF), (int)(out >> 16 & 0xFF),
                 (int)(out >> 8 & 0xFF));
    }
}

/* The game data title: in AM's list, whole by the record, made from this dump. The old single
 * title (layout 1, or a title with no record) has none and plays; a split title without it cannot start. */
static void find_game(Status *s, const HfInstalled *rec) {
    int r = s->installed_region >= 0 ? s->installed_region : s->region >= 0 ? s->region : REGION_EUR;
    s->game_installed = ctr_title_installed(game_title_id(r));
    s->game_complete = rec && rec->game_complete;
    s->game_state = HF_GAME_OK;
    if (!s->title_installed) return;
    if (hf_game_stale(s->game_installed, rec, s->dump_hash))
        s->game_state = s->layout == 2 && (!s->game_installed || !s->game_complete) ? HF_GAME_MISSING : HF_GAME_UPDATE;
}

void status_gather(void) {
    Status *s = &app.status;
    HfInstalled rec;
    char latest[48];
    int have_rec;
    memcpy(latest, s->latest, sizeof latest);   /* the network is asked elsewhere */
    memset(s, 0, sizeof *s);
    memcpy(s->latest, latest, sizeof latest);
    find_dump_file(s);      /* first: its region picks the installed title */
    find_installed(s);
    have_rec = read_installed_record(&rec);
    s->installed_complete = s->title_installed && have_rec && rec.complete;
    s->save_pending = s->title_installed && have_rec && rec.save_pending;
    if (have_rec) snprintf(s->save_restore, sizeof s->save_restore, "%s", rec.save_restore);
    s->layout = have_rec ? rec.layout : 0;
    s->installed_xx = s->title_installed && have_rec && rec.xx;
    s->installed_xx_no_room = s->title_installed && have_rec && rec.xx_no_room;
    if (have_rec) snprintf(s->installed_xx_dump, sizeof s->installed_xx_dump, "%s", rec.xx_dump);
    find_game(s, have_rec ? &rec : NULL);
    find_xx_dump(s);
    find_luma(s);
    s->free_bytes = ctr_sd_free();
    LOG("status: layout %d, game data installed %d complete %d state %d, dump romfs %.8s...", s->layout,
        s->game_installed, s->game_complete, s->game_state, s->dump_hash);
    LOG("status: installed '%s' (record complete %d, save pending %d), dump %d '%s' region %d, MH XX %d '%s' romfs "
        "%02x%02x%02x%02x..., luma %d %s, free %lu MB", s->installed, s->installed_complete, s->save_pending, s->dump,
        s->dump_path, s->region, s->xx, s->xx_path, s->xx_hash[0], s->xx_hash[1], s->xx_hash[2], s->xx_hash[3], s->luma,
        s->luma_version, (unsigned long)(s->free_bytes / 1048576));
    if (s->save_restore[0]) LOG("status: the title's save comes back from backup %s", s->save_restore);
}
