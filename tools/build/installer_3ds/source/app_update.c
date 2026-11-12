/* The Update flow in the documented order: the latest release
 * and its notes, the plan, the notes' page and the battery's warning, then on the task page the app's own update first
 * and the patch set -> the dump -> the title, the version recorded, the chime and Play now. A failure says what
 * happened and what to do. When the app updated itself and the mod waits for the new app, it leaves resume.json and
 * relaunches (a CIA) or asks to be opened again (a .3dsx), and the new app goes on by itself. The set is the one with
 * MH XX when the player's XX dump is the revision its header names, else the plain one. The online (friends patch)
 * page lives here too. The probe build (make PROBE=1) takes the mod's release from
 * sdmc:/3ds/heavenfall/<edition>/test_release/ (copied there from its romfs when it carries one) and only tries the
 * real GitHub API with a small real download. */
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "app.h"
#include "ctr_net.h"
#include "ctr_title.h"
#include "dump.h"
#include "hf_tuning.h"
#include "hfnet.h"
#include "settitle.h"
#include "updplan.h"

#define SUPPORTED_SET_FORMAT ((unsigned)PS_FORMAT_SECOND)   /* the newest set format the applier reads */

static int net_ok;

/* HfXxWhy in the log's words. */
static const char *const XX_WHY[] = {"no MH XX dump", "the dump is the revision the XX set names",
                                     "the release has no XX set of the region", "the dump is another revision",
                                     "this version's XX set did not fit the memory"};

static void put(char *dst, size_t cap, const char *text) { snprintf(dst, cap, "%s", text ? text : ""); }

/* `text` after what `buf` holds, `sep` between. */
static void append(char *buf, size_t cap, const char *sep, const char *text) {
    size_t n = strlen(buf);
    if (n + 1 < cap) snprintf(buf + n, cap - n, "%s%s", n ? sep : "", text);
}

int app_asset(void) { return ctr_app_form() == CTR_FORM_CIA ? HF_W_CIA : HF_W_3DSX; }

static int net_begin(HfTransport *tr) {
    u64 t = osGetTime();
    int rc = ctr_net_init();
    LOG("network: init %d", rc);
    hf_log_phase(&app.log, osGetTime(), "network init", t, 0);
    net_ok = rc == 0;
    if (rc) return rc;
    ctr_net_transport(tr);
    return 0;
}

static void net_end(void) {
    if (net_ok) ctr_net_exit();
    net_ok = 0;
}

/* ---- why an update stopped, and what to do ---- */

/* The kind's sentence, what to do (the room's MB filled in) and, with the advice's code, the code in small in the
 * footer for the log's reader. `had_title`: the old title stays, and the message says so. */
static void advise(HfFailKind kind, int rc, int had_title) {
    HfAdvice adv;
    char text[HF_VIEW_LINE * 2] = "", todo[HF_VIEW_LINE], value[24] = "", code[64] = "";
    hf_failure_advice(kind, &adv);
    if (kind == HF_FAIL_ROOM) {
        if (room_missing_mb) snprintf(value, sizeof value, "%lu MB", (unsigned long)room_missing_mb);
        else adv.todo = -1;   /* the card's file failed, not its room: the sentence alone */
    }
    append(text, sizeof text, "", T(adv.what));
    if (adv.todo >= 0) {
        hf_text_fill(T((HfText)adv.todo), value, todo, sizeof todo);
        append(text, sizeof text, "\n", todo);
    }
    {   /* the old title stays, or the install had removed it before AM's import (AM imports over none) */
        int note = hf_stop_note(kind, had_title, install_old_removed);
        if (note >= 0) append(text, sizeof text, "\n", T((HfText)note));
    }
    if (adv.show_code) {
        snprintf(code, sizeof code, "%s %d", T(HT_CODE), rc);
        if (install_am_result) {
            char am[24];
            snprintf(am, sizeof am, "AM 0x%08lX", (unsigned long)install_am_result);
            append(code, sizeof code, ", ", am);
        }
    }
    LOG("update stopped: kind %d, code %d, AM 0x%08lX, %lu MB missing", (int)kind, rc, (unsigned long)install_am_result,
        (unsigned long)room_missing_mb);
    task_end(0);
    ui_message_ex(text, kind == HF_FAIL_CANCEL ? HF_TONE_PLAIN : HF_TONE_BAD, code);
}

static void show_failure(int rc, int had_title) { advise(hf_fail_kind(rc, (uint32_t)install_am_result), rc, had_title); }

/* ---- the release ---- */

int release_latest(const HfTransport *tr, const HfEdition *e, HfRelease *rel, char *notes, size_t notes_cap) {
    const char *wanted[HF_W_COUNT];
    int http = 0, rc;
    u64 t = osGetTime();
    hf_edition_wanted(e, wanted);
    memset(rel, 0, sizeof *rel);
    if (notes && notes_cap) notes[0] = 0;
    rc = hf_latest_release(tr, HF_API_BASE, e->repository, e->name, wanted, HF_W_COUNT, rel, notes, notes_cap, &http);
    LOG("release: %s -> %d (http %d), tag '%s', assets %d%d%d%d%d%d, notes %lu bytes", e->repository, rc, http,
        rc == HF_OK ? rel->tag : "", rel->assets[0].found, rel->assets[1].found, rel->assets[2].found,
        rel->assets[3].found, rel->assets[4].found, rel->assets[5].found,
        (unsigned long)(rc == HF_OK && notes ? strlen(notes) : 0));
    hf_log_phase(&app.log, osGetTime(), "latest release", t, 0);
    return rc;
}

/* The card's folder the probe's release and sets were last read from (release_local): test_release/, or its next/. */
static char probe_dir[320];

/* `dir`/release.json parsed (a releases/latest answer, its notes too); an HF_REL_* code, -1 when missing. */
static int release_file(const HfEdition *e, const char *dir, HfRelease *rel, char *notes, size_t notes_cap) {
    char path[360], *json;
    const char *wanted[HF_W_COUNT];
    FILE *f;
    long n;
    int rc;
    hf_edition_wanted(e, wanted);
    snprintf(path, sizeof path, "%s/release.json", dir);
    f = fopen(path, "rb");
    if (!f) { LOG("probe: no %s", path); return -1; }
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    json = (char *)malloc(n > 0 ? (size_t)n + 1 : 1);
    if (!json || (n > 0 && fread(json, 1, (size_t)n, f) != (size_t)n)) { free(json); fclose(f); return -1; }
    fclose(f);
    rc = hf_release_parse(json, (size_t)n, e->repository, wanted, HF_W_COUNT, rel, notes, notes_cap);
    free(json);
    LOG("probe: local release %s '%s' parsed: %d", path, rc == HF_REL_OK ? rel->tag : "", rc);
    return rc;
}

static const char *bare_tag(const char *tag) { return tag[0] == 'v' ? tag + 1 : tag; }

int probe_test_app(HfRelease *rel, char *dir, size_t cap) {
    static uint8_t head[16 * 1024];
    const char *name = HF_EDITIONS[app.edition].asset_cia;
    char path[400], version[24];
    struct stat st;
    FILE *f;
    size_t n, k;
    if (!app.probe || ctr_app_form() != CTR_FORM_CIA || hf_path_test_release(app_edition()->slug, dir, cap)) return 0;
    k = strlen(dir);
    if (k < 12 || strcmp(dir + k - 12, "test_release") || k - 12 + 8 >= cap) return 0;
    memcpy(dir + k - 12, "test_app", 9);   /* beside test_release/ */
    snprintf(path, sizeof path, "%s/%s", dir, name);
    if (stat(path, &st) || !(f = fopen(path, "rb"))) return 0;
    n = fread(head, 1, sizeof head, f);
    fclose(f);
    if (!hf_cia_launcher_version(head, n, version, sizeof version)) {
        LOG("probe: %s is no launcher CIA", path);
        return 0;
    }
    memset(rel, 0, sizeof *rel);
    snprintf(rel->tag, sizeof rel->tag, "v%s", version);
    rel->assets[HF_W_CIA].found = 1;
    rel->assets[HF_W_CIA].size = (uint64_t)st.st_size;
    snprintf(rel->assets[HF_W_CIA].name, sizeof rel->assets[HF_W_CIA].name, "%s", name);
    return 1;
}

/* The mod's release in a probe build: test_release/release.json and the sets beside it; once that version is
 * installed as the split title (with MH XX when its dump came since, hf_xx_came), test_release/next/'s, the probe's
 * second release: an update that reinstalls only the mod's title. The second one stays
 * the latest once installed (a reinstall takes it again). Takes the edition, so the start's check thread can read it
 * as the player's latest release (the installed version it compares is gathered before the check starts). */
int release_local(const HfEdition *e, HfRelease *rel, char *notes, size_t notes_cap) {
    const Status *s = &app.status;
    char dir[300], next[320], first[HF_TAG_MAX];
    int rc, region = s->region >= 0 ? s->region : REGION_EUR;
    if (hf_path_test_release(e->slug, dir, sizeof dir)) return -1;
    snprintf(probe_dir, sizeof probe_dir, "%s", dir);
    rc = release_file(e, dir, rel, notes, notes_cap);
    if (rc != HF_REL_OK || !rel->tag[0] || !s->installed[0] || s->layout != 2) return rc;
    snprintf(first, sizeof first, "%s", rel->tag);
    if (!strcmp(bare_tag(first), s->installed) && status_xx_came(first, rel->assets[hf_w_patch(region, 1)].found))
        return rc;   /* MH XX came: the first release again, with it */
    snprintf(next, sizeof next, "%s/next", dir);
    if (release_file(e, next, rel, notes, notes_cap) != HF_REL_OK ||
        (strcmp(bare_tag(first), s->installed) && strcmp(bare_tag(rel->tag), s->installed)))
        return release_file(e, dir, rel, notes, notes_cap);   /* no second release, or neither installed: the first */
    snprintf(probe_dir, sizeof probe_dir, "%s", next);
    return HF_REL_OK;
}

static uint32_t head_format(const uint8_t *head) {
    return (uint32_t)head[4] | (uint32_t)head[5] << 8 | (uint32_t)head[6] << 16 | (uint32_t)head[7] << 24;
}

/* The first `len` bytes of a release's set (its header): from the probe's test release on the card, else with a Range
 * request. An HF_* code. Called from the start's check thread too: nothing of the app's state but its constants. */
static int set_head(const HfTransport *tr, const HfEdition *e, const HfAsset *a, uint8_t *head, size_t len) {
    char path[400];
    FILE *f;
    size_t n;
    if (!app.probe) return hf_read_set_head(tr, a->url, e->name, head, len);
    if (!probe_dir[0]) return HF_E_ARG;   /* release_local names the folder first */
    snprintf(path, sizeof path, "%s/%s", probe_dir, a->name);
    if (!(f = fopen(path, "rb"))) return HF_E_NETWORK;
    n = fread(head, 1, len, f);
    fclose(f);
    return n == len && !memcmp(head, "HFPS", 4) ? HF_OK : HF_E_FORMAT;
}

int release_xx_check(const HfTransport *tr, int edition, const HfRelease *rel, int region, int xx,
                     const uint8_t xx_hash[32], HfPlanIn *in, XxCheck *out) {
    const HfAsset *a = &rel->assets[hf_w_patch(region, 1)];
    uint8_t head[HF_SET_HEAD_MAX];
    int rc;
    in->xx_dump = xx == XX_FOUND || xx == XX_OTHER_VERSION;
    in->xx_set_in_release = a->found;
    in->xx_set_matches = 0;
    in->xx_set_format = 0;
    if (!in->xx_dump || !a->found) return HF_OK;
    rc = set_head(tr, &HF_EDITIONS[edition], a, head, sizeof head);
    if (rc == HF_OK) {
        in->xx_set_format = head_format(head);
        in->xx_set_matches = hf_set_names_game(head, sizeof head, xx_hash);
        if (out) {
            out->known = 1;
            out->edition = edition;
            memcpy(out->hash, xx_hash, sizeof out->hash);
            out->matches = in->xx_set_matches;
        }
    }
    LOG("MH XX: header of %s: %d, format %u, names the dump %d", a->name, rc, (unsigned)in->xx_set_format,
        in->xx_set_matches);
    return rc;
}

/* ---- the steps ---- */

/* A release file into the edition's folder; when the card has no room, the MB it lacks. */
static int fetch(const HfTransport *tr, const HfAsset *a, char *path, size_t cap) {
    int rc = ctr_net_fetch(app_edition(), a, tr, ui_progress, NULL, path, cap);
    if (rc == HF_E_DISK) room_missing_mb = hf_room_missing_mb(ctr_sd_free(), a->size, (uint64_t)HF_TUNE_SD_SPARE_MB << 20);
    return rc;
}

/* The probe's real download: the smallest app file of the real release (TLS, redirects and the digest, timed). */
static void probe_small_download(const HfTransport *tr, const HfRelease *real) {
    const HfAsset *best = NULL;
    char path[300];
    u64 t = osGetTime();
    int i, rc;
    for (i = HF_W_CIA; i <= HF_W_3DSX; i++)
        if (real->assets[i].found && (!best || real->assets[i].size < best->size)) best = &real->assets[i];
    if (!best || best->size > (8u << 20)) { LOG("probe: no small real file to download"); return; }
    ui_phase(HT_PHASE_PROBE_DOWNLOAD);
    rc = ctr_net_fetch(app_edition(), best, tr, ui_progress, NULL, path, sizeof path);
    LOG("probe: real download %s (%lu bytes): %d", best->name, (unsigned long)best->size, rc);
    hf_log_phase(&app.log, osGetTime(), "real download", t, best->size);
    if (rc == 0) remove(path);
}

/* The app's own update from `rel`: downloaded, or (`local_dir`) a probe's file where it is on the card, kept. A probe
 * installs only such a file; the real release's launcher it downloads only (the network and the digest). */
static int app_step(const HfTransport *tr, const HfRelease *rel, const char *local_dir) {
    const HfAsset *a = &rel->assets[app_asset()];
    char path[300];
    struct stat st;
    int rc;
    u64 t = osGetTime();
    ui_phase(HT_PHASE_APP_DOWNLOAD);
    if (local_dir) {
        snprintf(path, sizeof path, "%s/%s", local_dir, a->name);
        rc = stat(path, &st) || (uint64_t)st.st_size != a->size ? TITLE_E_IO : 0;
        LOG("app: the test release's %s (%lu bytes): %d", path, (unsigned long)a->size, rc);
    } else {
        rc = fetch(tr, a, path, sizeof path);
        LOG("app: download %s (%lu bytes): %d", a->name, (unsigned long)a->size, rc);
        hf_log_phase(&app.log, osGetTime(), "download of the app", t, a->size);
    }
    if (rc) return rc;
    if (app.probe && !local_dir) {   /* the real release's launcher: the download proved the network and the digest */
        remove(path);
        return 0;
    }
    ui_phase(HT_PHASE_APP_INSTALL);
    if (ctr_app_form() == CTR_FORM_CIA) {
        Result res = 0;
        t = osGetTime();
        rc = ctr_self_install_cia(path, &res);
        LOGR("self install (CIA)", res);
        hf_log_phase(&app.log, osGetTime(), "self install", t, a->size);
        install_am_result = res;
    } else {
        rc = ctr_self_replace_3dsx(path, app.own_path);
        LOG("self replace (3dsx): %d", rc);
    }
    if (!local_dir) remove(path);   /* installed, refused or cut: a download is not kept (the next try fetches it) */
    return rc ? TITLE_E_IO : 0;
}

/* The set the plan takes, downloaded once for the game data and the mod. */
static struct {
    char path[400];
    int have;                   /* the file is on the card (the probe's: in its test release) */
    int xx;                     /* it is the XX set */
} set_file;

/* A set of the release onto the card (the probe's: its test release is used where it is). */
static int set_fetch(const HfTransport *tr, const HfRelease *mod_rel, int region, int use_xx) {
    const HfAsset *set = &mod_rel->assets[hf_w_patch(region, use_xx)];
    int rc;
    set_file.have = 0;
    set_file.xx = use_xx;
    if (app.probe) {
        snprintf(set_file.path, sizeof set_file.path, "%s/%s", probe_dir, set->name);
    } else {
        u64 t = osGetTime();
        ui_phase(use_xx ? HT_PHASE_SET_DOWNLOAD_XX : HT_PHASE_SET_DOWNLOAD);
        rc = fetch(tr, set, set_file.path, sizeof set_file.path);
        LOG("set: download %s (%lu bytes): %d", set->name, (unsigned long)set->size, rc);
        hf_log_phase(&app.log, osGetTime(), "download of the set", t, set->size);
        if (rc) return rc;
    }
    set_file.have = 1;
    return 0;
}

/* The set of the plan on the card. When MH XX's dump is there and the release has the region's XX set, that set is
 * fetched even when the dump's revision is not the one it names: its files are compared one by one with the dump's
 * (xx_files_check) before anything is written, and equal files make it the plan's; a file that differs leaves the XX
 * set out with its note (HF_XX_OTHER_VERSION). */
static int set_ready(const HfTransport *tr, const HfRelease *mod_rel, int region, const HfPlanIn *in, HfPlan *plan) {
    int rc, try_xx, match = 0;
    if (set_file.have) return 0;
    try_xx = in->xx_dump && in->xx_set_in_release && (plan->use_xx || plan->xx_why == HF_XX_OTHER_VERSION);
    if (try_xx) {
        rc = set_fetch(tr, mod_rel, region, 1);
        if (rc) return rc;
        if ((rc = xx_files_check(set_file.path, &match))) return rc;
        if (match) {
            if (plan->xx_why == HF_XX_OTHER_VERSION) {
                LOG("mod: MH XX is another printing, but its files are the set's: used");
                if (install_xx_by_files) ui_notice(HT_XX_FILES_NOTE);
                app.xx_check.matches = 1;
            }
            plan->use_xx = 1;
            plan->xx_why = HF_XX_USED;
            return 0;
        }
        LOG("mod: a file of MH XX differs from the XX set's: the XX set is left out");
        hf_hex(app.status.xx_hash, install_xx_differs);   /* recorded: this version does not try it again */
        if (!app.probe) remove(set_file.path);
        set_file.have = 0;
        if (plan->use_xx && !hf_plan_drop_xx(in, plan)) return TITLE_E_GAME;   /* no plain set to go on with */
        plan->use_xx = 0;
        plan->xx_why = HF_XX_OTHER_VERSION;
    }
    return set_fetch(tr, mod_rel, region, plan->use_xx);
}

/* One title of the plan from the set: the game data (HF_STEP_GAME) or the mod (HF_STEP_MOD). */
static int title_set_step(const HfTransport *tr, const HfRelease *mod_rel, int region, const HfPlanIn *in, HfPlan *plan,
                          HfTitleKind kind) {
    int rc = set_ready(tr, mod_rel, region, in, plan);
    if (rc) return rc;
    LOG("%s: the %s set %s (MH XX: %s)", kind == HF_TITLE_GAME ? "game data" : "mod", plan->use_xx ? "XX" : "plain",
        set_file.path, XX_WHY[plan->xx_why]);
    if (plan->xx_why == HF_XX_OTHER_VERSION) ui_notice(HT_XX_OTHER_NOTE);
    else if (plan->xx_why == HF_XX_NOT_IN_RELEASE) ui_notice(HT_XX_NO_SET_NOTE);
    else if (plan->xx_why == HF_XX_NO_ROOM) ui_notice(HT_XX_NO_ROOM_NOTE);
    rc = install_set(set_file.path, mod_rel->tag, plan->use_xx, plan->xx_why == HF_XX_NO_ROOM, kind);
    /* kept after other failures, so the next try resumes it; an XX set that did not fit is not tried again; the game
     * data's set is the mod's too */
    if (((rc == 0 && kind == HF_TITLE_MOD) || (rc == TITLE_E_MEM && plan->use_xx)) && !app.probe) {
        remove(set_file.path);
        set_file.have = 0;
    }
    return rc;
}

/* An XX set that runs out of memory (refused at the set's open, nothing installed) gives way to the plain set of the
 * same release, recorded (installed.json "xx_no_room") so this version does not try it again. */
static int title_step(const HfTransport *tr, const HfRelease *mod_rel, int region, const HfPlanIn *in, HfPlan *plan,
                      HfTitleKind kind) {
    int rc = title_set_step(tr, mod_rel, region, in, plan, kind);
    if (rc == TITLE_E_MEM && plan->use_xx && hf_plan_drop_xx(in, plan)) {
        LOG("mod: the XX set did not fit the memory: the plain set instead");
        set_file.have = 0;
        task_route_again();
        rc = title_set_step(tr, mod_rel, region, in, plan, kind);
    }
    return rc;
}

/* ---- before and after the work ---- */

enum { ID_BACK = 1, ID_GO };   /* the notes' and the done page's buttons */

/* The release's notes, Up and Down to scroll: 1 to go on with the update, 0 back. */
static int notes_page(const char *tag) {
    const char *p;
    int lines = 1, scroll = 0, id;
    UiEvent ev;
    HfView *v;
    for (p = app.notes; *p; p++) lines += *p == '\n';
    v = ui_begin();
    ui_reset(v, HF_SCREEN_NOTES);
    put(v->heading, sizeof v->heading, app_edition()->name);
    snprintf(v->notes_title, sizeof v->notes_title, "%s %s", T(HT_NOTES_TITLE), tag);
    put(v->notes, sizeof v->notes, app.notes);
    ui_button(v, T(HT_BTN_UPDATE), ID_GO, 1, 1);
    ui_button(v, T(HT_BTN_BACK), ID_BACK, 0, 1);
    v->selected = 0;
    put(v->footer, sizeof v->footer, T(HT_NOTES_KEYS));
    ui_end();
    while (app_loop(&ev)) {
        if (ev.keys & (KEY_DUP | KEY_DDOWN)) {
            int to = scroll + (ev.keys & KEY_DDOWN ? 1 : -1);
            if (to >= 0 && to < lines) {
                scroll = to;
                v = ui_begin();
                v->notes_scroll = scroll;
                ui_end();
            }
            continue;
        }
        if (ev.keys & KEY_START) return 0;
        id = ui_choose(&ev);
        if (id == ID_GO) return 1;
        if (id == ID_BACK || id == UI_BACK) return 0;
    }
    return 0;
}

/* The battery (PTMU): low and no charger, the player is asked first with the install's expected time. 1: go on. */
static int battery_ok(uint32_t expect_s) {
    u8 level = 0;
    bool adapter = false;
    int known = -1;
    char dur[24], question[HF_VIEW_LINE * 2];
    if (R_SUCCEEDED(ptmuInit())) {
        if (R_SUCCEEDED(PTMU_GetBatteryLevel(&level))) known = level;
        if (R_FAILED(PTMU_GetAdapterState(&adapter))) adapter = false;
        ptmuExit();
    }
    LOG("battery: level %d, charger %d, expected %lu s", known, (int)adapter, (unsigned long)expect_s);
    if (!hf_battery_warn(known, adapter, (int)HF_TUNE_BATTERY_LOW_LEVEL)) return 1;
    hf_duration_text(expect_s, dur, sizeof dur);
    hf_text_fill(T(HT_BATTERY_LOW), dur, question, sizeof question);
    return ui_confirm(question);
}

/* The done page: the title is ready, Play now or Back. 1 when the title was started (the app leaves). A save the
 * install could not put back (app_saves.c) is offered first when the title's save opens; else the page says how it
 * comes back. */
static int done_page(int first) {
    char text[HF_VIEW_LINE];
    UiEvent ev;
    HfView *v;
    int id, waits = app.status.save_restore[0] && saves_restore_flow(1) == SAVE_NOT_RUN;
    hf_text_fill(T(HT_DONE_READY), app_edition()->name, text, sizeof text);
    v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    put(v->heading, sizeof v->heading, app_edition()->name);
    put(v->state, sizeof v->state, text);
    v->tone = HF_TONE_GOOD;
    put(v->detail, sizeof v->detail, waits ? T(HT_SAVE_RESTORE_RUN_FIRST) : first ? T(HT_DONE_SAVE_HINT) : "");
    snprintf(v->rows[0], HF_VIEW_LINE, "%s\t%s", T(HT_HOME_INSTALLED_LABEL), app.status.installed);
    v->row_count = 1;
    ui_button(v, T(HT_BTN_PLAY_NOW), ID_GO, 1, 1);
    ui_button(v, T(HT_BTN_BACK), ID_BACK, 0, 1);
    v->selected = 0;
    ui_end();
    while (app_loop(&ev)) {
        if (ev.keys & KEY_START) return 0;
        id = ui_choose(&ev);
        if (id == ID_GO && start_edition() == 0) return 1;
        if (id == ID_BACK || id == UI_BACK) return 0;
    }
    return 0;
}

/* ---- the last install's times: timings.json ---- */

int timings_read(HfTimings *t) {
    char path[300], text[512];
    long n;
    if (hf_path_timings(app_edition()->slug, path, sizeof path) || (n = read_small(path, text, sizeof text)) < 0)
        return 0;
    return hf_timings_parse(text, (size_t)n, t) == 0;
}

static void timings_write(void) {
    HfTimings t;
    char path[300], text[512];
    int n;
    task_measured(&t);
    LOG("timings: download %lu ms for %lu bytes, install %lu ms for %lu bytes, finish %lu ms",
        (unsigned long)t.ms[0], (unsigned long)t.bytes[0], (unsigned long)t.ms[1], (unsigned long)t.bytes[1],
        (unsigned long)t.ms[2]);
    if (!t.ms[HF_STAGE_INSTALL] || !t.bytes[HF_STAGE_INSTALL]) return;   /* nothing measured to plan with */
    n = hf_timings_format(&t, text, sizeof text);
    if (n < 0 || hf_path_timings(app_edition()->slug, path, sizeof path) || write_whole(path, text, (size_t)n))
        LOG("timings: not written");
}

/* ---- the app's own update going on by itself ---- */

/* The app updated itself and the mod waits for the new app: resume.json names the release, then a CIA relaunches
 * itself and a .3dsx asks to be opened again. 1: the app leaves. */
static int self_relaunch(const char *tag) {
    char path[300], text[96];
    int n = hf_resume_format(tag, text, sizeof text);
    if (n < 0 || hf_path_resume(app_edition()->slug, path, sizeof path) || write_whole(path, text, (size_t)n)) {
        LOG("resume: not written");
        ui_message(T(HT_APP_UPDATED));
        return 1;
    }
    LOG("resume: %s names %s", path, tag);
    if (ctr_app_form() == CTR_FORM_CIA) {
        ui_notice_for(T(HT_APP_RESTARTING), HF_TUNE_RESTART_NOTICE_MS);
        aptSetChainloaderToSelf();
        LOG("relaunch: the chainloader to this title");
        return 1;
    }
    ui_message(T(HT_APP_REOPEN));
    return 1;
}

int resume_found(void) {
    int i, chosen = -1;
    for (i = 0; i < HF_EDITION_COUNT; i++) {
        char path[300], text[256], target[HF_TAG_MAX];
        long n;
        if (hf_path_resume(HF_EDITIONS[i].slug, path, sizeof path)) continue;
        n = read_small(path, text, sizeof text);
        remove(path);   /* first, whatever it holds: a self-update that failed never loops */
        if (n < 0) continue;
        if (hf_resume_parse(text, (size_t)n, target, sizeof target)) {
            LOG("resume: %s is no resume file", path);
            continue;
        }
        LOG("resume: %s names %s, the app is %s", HF_EDITIONS[i].name, target, HF_APP_VERSION);
        if (chosen < 0 && hf_resume_go(target, HF_APP_VERSION)) chosen = i;
    }
    if (chosen < 0) return 0;
    if (chosen != app.edition) {
        app.edition = chosen;
        log_close();
        log_open();
    }
    LOG("resume: the update of %s goes on", app_edition()->name);
    return 1;
}

/* ---- the update ---- */

/* What the plan downloads and installs, for the bar and the expected time: the app's file and the set (not in a
 * probe), and the title (the dump's size until the set gives the exact one). */
static void plan_bytes(const HfPlan *plan, const HfRelease *real, const HfRelease *mod_rel, int region,
                       uint64_t bytes[HF_STAGES], uint64_t *game_bytes) {
    int i, set = 0;
    memset(bytes, 0, HF_STAGES * sizeof bytes[0]);
    *game_bytes = 0;
    for (i = 0; i < plan->count; i++) {
        if (plan->steps[i] == HF_STEP_APP) {
            bytes[HF_STAGE_DOWNLOAD] += real->assets[app_asset()].size;
            continue;
        }
        if (!set++ && !app.probe) bytes[HF_STAGE_DOWNLOAD] += mod_rel->assets[hf_w_patch(region, plan->use_xx)].size;
        if (plan->steps[i] == HF_STEP_GAME) {
            *game_bytes = app.status.dump_bytes ? app.status.dump_bytes : 1;   /* the dump's RomFS, near enough */
        } else {   /* the mod title: its own files only, a guess from the set until the set is open */
            bytes[HF_STAGE_INSTALL] = mod_rel->assets[hf_w_patch(region, plan->use_xx)].size * HF_TUNE_MOD_TITLE_PER_SET;
            if (!bytes[HF_STAGE_INSTALL]) bytes[HF_STAGE_INSTALL] = 1;
        }
    }
}

/* The plan installs a title from the set: it needs the dump. */
static int plan_has_title(const HfPlan *plan) {
    int i;
    for (i = 0; i < plan->count; i++)
        if (plan->steps[i] == HF_STEP_MOD || plan->steps[i] == HF_STEP_GAME) return 1;
    return 0;
}

int update_run(int resuming, int reinstall) {
    HfTransport tr;
    HfRelease real, local, test_app, *mod_rel = &real;
    const HfRelease *app_rel;
    char test_app_dir[300];
    const char *app_dir;
    HfPlanIn in;
    HfPlan plan;
    HfInstalled rec;
    HfTimings last;
    XxCheck xx_seen;
    Status *s = &app.status;
    uint64_t bytes[HF_STAGES], game_bytes = 0, dl_done = 0;
    char *raw;
    int rc, had_title, region, i, app_done = 0, mod_done = 0, leave = 0, have_last, restart_now = 0, app_local;

    check_stop(1);   /* the start's check: joined, its stack and buffers freed before anything is installed */
    install_am_result = 0;
    room_missing_mb = 0;
    install_old_removed = 0;
    task_page(resuming ? HT_RESUMING : HT_WORKING);
    aptSetSleepAllowed(false);   /* closing the lid must not stop a download or the install */
    ui_phase(HT_CHECKING);
    status_gather();
    had_title = s->title_installed;
    install_xx_differs[0] = 0;
    LOG("update: begin%s", resuming ? " (going on after the app's own update)" : reinstall ? " (a reinstall)" : "");

    ui_phase(HT_PHASE_RELEASE);
    if ((rc = net_begin(&tr))) { advise(HF_FAIL_NET, rc, 0); goto out; }
    raw = (char *)malloc(NOTES_RAW_SIZE);   /* freed before anything is installed */
    rc = release_latest(&tr, app_edition(), &real, raw, raw ? NOTES_RAW_SIZE : 0);
    if (rc == HF_OK) {
        snprintf(s->latest, sizeof s->latest, "%s", real.tag);
        app.check = HF_CHECK_DONE;
        if (raw) hf_notes_plain(raw, app.notes, sizeof app.notes);
    }
    free(raw);
    if (rc == HF_E_NONE && !app.probe) { advise(HF_FAIL_NO_RELEASE, rc, 0); goto out; }
    if (rc && rc != HF_E_NONE) { advise(HF_FAIL_NET, rc, 0); goto out; }
    if (app.probe) {
        if (release_local(app_edition(), &local, NULL, 0)) { ui_message("probe: test_release/release.json missing or not a release"); goto out; }
        mod_rel = &local;
    }
    /* the app's own update: a probe's only from its test release (installed, and restarted as the app's); the real
     * release's launcher a probe downloads only */
    app_local = app.probe && mod_rel->assets[app_asset()].found;
    app_rel = app_local ? mod_rel : &real;
    app_dir = app_local ? probe_dir : NULL;
    if (probe_test_app(&test_app, test_app_dir, sizeof test_app_dir)) {   /* a test launcher left on the card first */
        LOG("probe: the test launcher %s/%s, version %s", test_app_dir, test_app.assets[HF_W_CIA].name, test_app.tag);
        app_local = 1;
        app_rel = &test_app;
        app_dir = test_app_dir;
    }
    region = s->region >= 0 ? s->region : REGION_EUR;

    memset(&in, 0, sizeof in);
    in.release_tag = mod_rel->tag;
    in.app_version = HF_APP_VERSION;
    in.mod_version = s->title_installed ? s->installed : NULL;
    in.mod_incomplete = s->title_installed && !s->installed_complete;
    in.app_in_release = app_local || (real.assets[app_asset()].found && rc == HF_OK);
    in.app_tag = app_rel->tag;
    in.set_in_release = mod_rel->assets[hf_w_patch(region, 0)].found;
    in.supported_format = SUPPORTED_SET_FORMAT;
    memset(&rec, 0, sizeof rec);
    set_file.have = 0;
    in.game_stale = hf_game_stale(s->game_installed, read_installed_record(&rec) ? &rec : NULL, s->dump_hash);
    in.mod_layout = s->title_installed ? (rec.layout ? rec.layout : 1) : 0;
    if (s->title_installed) {
        in.mod_xx = rec.xx;
        in.xx_no_room = rec.xx_no_room;
        in.xx_tried = status_xx_tried();
    }
    in.reinstall = reinstall;
    if (in.set_in_release || app.probe) {
        uint8_t head[8];
        int peek = set_head(&tr, app_edition(), &mod_rel->assets[hf_w_patch(region, 0)], head, sizeof head);
        in.set_format = peek == HF_OK ? head_format(head) : 0;
        LOG("set format peek: %d, format %u", peek, (unsigned)in.set_format);
    }
    memset(&xx_seen, 0, sizeof xx_seen);
    if ((rc = release_xx_check(&tr, app.edition, mod_rel, region, s->xx, s->xx_hash, &in, &xx_seen))) {
        advise(HF_FAIL_NET, rc, 0);
        goto out;
    }
    if (xx_seen.known) app.xx_check = xx_seen;
    /* the installed title was built with this very XX dump (its files checked equal when it was): the release of the
     * same version is not rebuilt for the hash alone */
    if (in.xx_dump && !in.xx_set_matches && rec.xx && in.mod_version && !hf_version_newer(in.release_tag, in.mod_version)) {
        char now[65];
        hf_hex(s->xx_hash, now);
        if (!strcmp(now, rec.xx_dump)) in.xx_set_matches = 1;
    }
    if (app.probe && real.tag[0]) probe_small_download(&tr, &real);
    if (app.probe) {   /* the real release's own app is compared by the same plan, but only logged */
        HfPlan real_plan;
        HfPlanIn real_in = in;
        real_in.release_tag = real.tag;
        real_in.set_in_release = 0;
        real_in.xx_set_in_release = 0;
        hf_plan(&real_in, &real_plan);
        LOG("probe: the real release's plan status %d, %d steps", (int)real_plan.status, real_plan.count);
        in.app_in_release = app_local || real.assets[app_asset()].found;
    }
    hf_plan(&in, &plan);
    LOG("plan: status %d, %d steps (%d %d %d), mod after restart %d; game data stale %d, layout %d", (int)plan.status,
        plan.count, plan.steps[0], plan.steps[1], plan.steps[2], plan.mod_after_restart, in.game_stale, in.mod_layout);
    LOG("plan: MH XX dump %d '%s', installed with MH XX %d, XX set in the release %d (format %u, names the dump %d) "
        "-> the %s set: %s", s->xx, s->xx_path, in.mod_xx, in.xx_set_in_release, (unsigned)in.xx_set_format,
        in.xx_set_matches, plan.use_xx ? "XX" : "plain", XX_WHY[plan.xx_why]);

    if (plan.status == HF_PLAN_UP_TO_DATE) {   /* after its own update's restart: say that it was */
        char now[HF_VIEW_LINE];
        hf_text_fill(T(HT_APP_NOW), HF_APP_VERSION, now, sizeof now);
        task_end(0);
        ui_message(resuming ? now : T(HT_UP_TO_DATE));
        goto out;
    }
    if (plan.status == HF_PLAN_NO_SET) { advise(HF_FAIL_NO_SET, 0, 0); goto out; }
    if (plan.status == HF_PLAN_NEEDS_APP) { advise(HF_FAIL_NEEDS_APP, 0, 0); goto out; }
    if (plan.status != HF_PLAN_STEPS) { advise(HF_FAIL_OTHER, (int)plan.status, 0); goto out; }
    if (plan_has_title(&plan) && s->dump != DUMP_FOUND) {
        advise(s->dump == DUMP_ENCRYPTED ? HF_FAIL_DUMP_ENCRYPTED : HF_FAIL_DUMP_MISSING, 0, 0);
        goto out;
    }

    /* before the work: the notes of a new version, the battery */
    plan_bytes(&plan, app_rel, mod_rel, region, bytes, &game_bytes);
    have_last = timings_read(&last);
    if (!resuming && app.notes[0] && (!had_title || hf_version_newer(mod_rel->tag, s->installed) == 1)) {
        if (!notes_page(real.tag[0] ? real.tag : mod_rel->tag)) { LOG("update: back from the notes"); goto out; }
        task_page(HT_WORKING);
    }
    if (!battery_ok(task_expected_s(have_last ? &last : NULL, bytes, game_bytes))) { LOG("update: not on a low battery"); goto out; }

    task_begin(have_last ? &last : NULL, bytes, game_bytes);
    for (i = 0; i < plan.count; i++) {
        task_download(dl_done);
        if (plan.steps[i] == HF_STEP_APP) {
            if (app.probe && !app_rel->assets[app_asset()].found) {
                LOG("probe: the real release has no app file to download");
                continue;
            }
            rc = app_step(&tr, app_rel, app_dir);
            if (rc && hf_plan_on_without_app(&plan)) {   /* the titles go on with this app; its own update next time */
                LOG("app: its own update failed (%d, AM 0x%08lX): the mod goes on with this app", rc,
                    (unsigned long)install_am_result);
                install_am_result = 0;
                continue;
            }
            if (rc) { show_failure(rc, had_title); goto out; }
            dl_done += app_local ? 0 : app_rel->assets[app_asset()].size;
            app_done = 1;
            /* AM has replaced the running CIA: its romfs (the certificates for TLS and AM, the icons, the chime) is the
             * new title's now, so the mod waits for the new app, which goes on by itself (resume.json). */
            if (ctr_app_form() == CTR_FORM_CIA && (!app.probe || app_local)) {
                restart_now = 1;
                break;
            }
        } else {
            HfTitleKind kind = plan.steps[i] == HF_STEP_GAME ? HF_TITLE_GAME : HF_TITLE_MOD;
            rc = title_step(&tr, mod_rel, region, &in, &plan, kind);
            if (rc) { show_failure(rc, had_title); goto out; }
            if (kind == HF_TITLE_MOD) mod_done = 1;
        }
    }
    task_end(1);
    net_end();
    aptSetSleepAllowed(true);
    ui_idle();
    status_gather();
    LOG("update: done (app %d, mod %d)", app_done, mod_done);
    if (app_done && (!app.probe || app_local) && (plan.mod_after_restart || restart_now) && !resuming) {
        leave = self_relaunch(app_rel->tag);   /* a resumed run never writes resume.json again: no loop */
    } else if (mod_done) {
        timings_write();
        ui_chime();
        leave = done_page(!had_title);
    } else {
        ui_message(app_done && (!app.probe || app_local) ? T(HT_APP_UPDATED) : T(HT_UPDATED));
    }

out:
    task_end(0);
    ui_idle();
    net_end();
    aptSetSleepAllowed(true);
    LOG("update: end%s", leave ? ", the app leaves" : "");
    if (!leave) status_gather();
    return leave;
}

/* ---- Online ---- */

const char *online_state_text(int st) {
    return st == HF_FRIENDS_INSTALLED ? T(HT_ONLINE_INSTALLED) : st == HF_FRIENDS_INSTALLABLE ? T(HT_ONLINE_INSTALLABLE) :
           st == HF_FRIENDS_UNSUPPORTED ? T(HT_ONLINE_UNSUPPORTED) : st == HF_FRIENDS_DAMAGED ? T(HT_ONLINE_DAMAGED) : "";
}

void online_run(void) {
    char msg[300] = "";
    int st;
    HfView *v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    put(v->heading, sizeof v->heading, T(HT_BTN_ONLINE));
    put(v->state, sizeof v->state, T(HT_CHECKING));
    v->busy = 1;
    ui_end();
    st = hf_friends_status(msg, sizeof msg);
    LOG("online: status %d %s", st, msg);
    if (app.probe) {   /* the friends module's files for its patch: a probe's, only from this page */
        char dir[300], dump[300] = "";
        if (!hf_path_friends_dump(app_edition()->slug, dir, sizeof dir)) {
            mkdir(dir, 0777);
            LOG("friends dump to %s: %d %s", dir, hf_friends_dump(dir, dump, sizeof dump), dump);
        }
    }
    v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    put(v->heading, sizeof v->heading, T(HT_BTN_ONLINE));
    put(v->state, sizeof v->state, online_state_text(st));
    v->tone = st == HF_FRIENDS_INSTALLED ? HF_TONE_GOOD : st == HF_FRIENDS_DAMAGED ? HF_TONE_BAD
            : st == HF_FRIENDS_UNSUPPORTED ? HF_TONE_WARN : HF_TONE_PLAIN;
    put(v->detail, sizeof v->detail, msg);
    put(v->rows[0], HF_VIEW_LINE, T(HT_ONLINE_NEEDED));
    v->row_count = 1;
    ui_end();
    if (st == HF_FRIENDS_INSTALLABLE && ui_confirm(T(HT_ONLINE_ASK_INSTALL))) {
        msg[0] = 0;
        ui_working(T(HT_ONLINE_WORKING));
        st = hf_friends_install(msg, sizeof msg);
        LOG("online: install %d %s", st, msg);
        ui_message(msg[0] ? msg : T(HT_REBOOT));
    } else if ((st == HF_FRIENDS_INSTALLED || st == HF_FRIENDS_DAMAGED) && ui_confirm(T(HT_ONLINE_ASK_REMOVE))) {
        msg[0] = 0;
        ui_working(T(HT_ONLINE_WORKING));
        st = hf_friends_remove(msg, sizeof msg);
        LOG("online: remove %d %s", st, msg);
        ui_message(msg[0] ? msg : T(HT_REBOOT));
    } else if (st != HF_FRIENDS_INSTALLABLE && st != HF_FRIENDS_INSTALLED && st != HF_FRIENDS_DAMAGED) {
        ui_message(msg);
    }
}

/* ---- the probe's start: its test release onto the card, the friends module's code into the log folder ---- */

/* The whole of a small file (at most `cap` bytes) into `buf`; its length, -1 when it is missing or bigger. */
static long small_file(const char *path, unsigned char *buf, size_t cap) {
    FILE *f = fopen(path, "rb");
    size_t n;
    if (!f) return -1;
    n = fread(buf, 1, cap, f);
    if (n == cap && fgetc(f) != EOF) n = cap + 1;
    fclose(f);
    return n > cap ? -1 : (long)n;
}

/* romfs:/test_release/<sub><name> onto the card's `dir`/<name>; 1 when it is all there. */
static int probe_copy(const char *sub, const char *dir, const char *name) {
    static unsigned char buf[64 * 1024];
    char src[600], dst[600];
    FILE *in, *out = NULL;
    size_t n;
    int copied;
    snprintf(src, sizeof src, "romfs:/test_release/%s%s", sub, name);
    snprintf(dst, sizeof dst, "%s/%s", dir, name);
    in = fopen(src, "rb");
    if (in) out = fopen(dst, "wb");
    copied = in && out;
    while (copied && (n = fread(buf, 1, sizeof buf, in)) > 0) copied = fwrite(buf, 1, n, out) == n;
    if (in) fclose(in);
    if (out && fclose(out)) copied = 0;
    LOG("probe: test release %s%s copied to the card: %d", sub, name, copied);
    return copied;
}

/* Every file of romfs:/test_release/<sub> (folders left out) onto the card's `dir`, release.json last: a cut copy leaves
 * none, and the next start copies again. 1 when it is all there. */
static int probe_copy_folder(const char *sub, const char *dir) {
    char src[400], json[600];
    struct dirent *e;
    struct stat st;
    DIR *d;
    int ok = 1;
    snprintf(src, sizeof src, "romfs:/test_release/%s", sub);
    if (!(d = opendir(src))) return 0;
    snprintf(json, sizeof json, "%s/release.json", dir);
    mkdir(dir, 0777);
    remove(json);
    while ((e = readdir(d))) {
        char path[700];
        if (e->d_name[0] == '.' || !strcmp(e->d_name, "release.json")) continue;
        snprintf(path, sizeof path, "%s%s", src, e->d_name);
        if (!stat(path, &st) && S_ISDIR(st.st_mode)) continue;
        ok &= probe_copy(sub, dir, e->d_name);
    }
    closedir(d);
    if (ok && !probe_copy(sub, dir, "release.json")) remove(json);
    return ok;
}

/* A probe build may carry its test release in the app's romfs (romfs:/test_release): it is copied to the card's
 * test_release/ when the card's release.json is missing or not the app's (a newer probe's sets replace the old ones),
 * so the app installed from a URL needs no file copied by hand. release.json goes last, once every set is there: a cut
 * copy leaves none, and the next start copies again. */
static void probe_release_from_romfs(void) {
    static unsigned char mine_json[16 * 1024], card_json[16 * 1024];
    char dir[300], json[600], next[320];
    struct stat st;
    long mine, theirs;
    if (hf_path_test_release(app_edition()->slug, dir, sizeof dir)) return;
    snprintf(json, sizeof json, "%s/release.json", dir);
    mine = small_file("romfs:/test_release/release.json", mine_json, sizeof mine_json);
    theirs = small_file(json, card_json, sizeof card_json);
    if (mine < 0) { LOG("probe: no test release in the app"); return; }
    if (theirs == mine && !memcmp(mine_json, card_json, (size_t)mine)) {
        LOG("probe: the card has the app's test release");
        return;
    }
    if (!probe_copy_folder("", dir)) return;
    snprintf(next, sizeof next, "%s/next", dir);
    if (!stat("romfs:/test_release/next", &st) && S_ISDIR(st.st_mode)) {   /* the second release */
        probe_copy_folder("next/", next);
    } else {   /* none in the app: an older probe's second release on the card must not be taken for it */
        char old[340];
        snprintf(old, sizeof old, "%s/release.json", next);
        LOG("probe: no second release in the app: the card's is dropped (%d)", remove(old));
    }
}

void probe_startup(void) {
    if (!app.probe) return;
    probe_release_from_romfs();
}
