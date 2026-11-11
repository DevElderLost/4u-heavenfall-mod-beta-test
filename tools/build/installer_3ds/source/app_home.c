/* The home screen: the edition, one state line in its colour (hf_home), what to
 * do next, the installed and the latest versions, the first lines of the release's notes, and the buttons: the big one
 * (Install, Update to X, Set up or Play), Play, the original MH4U and More. More's menu has Information (the old
 * status table), the save copy, Reinstall (the installed title again from the latest version), online play, the
 * language and Exit. The start's check (app_check.c) runs meanwhile and
 * fills the page in when it answers. START exits; L and R change the edition when there are several; SELECT the
 * language. */
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#include "app.h"
#include "hf_tuning.h"

/* The language the player chose (over the console's): "es" or "en" in this file. */
#define LANGUAGE_FILE "sdmc:/3ds/heavenfall/language.txt"
#define MB(bytes) ((unsigned long)((bytes) / (1024 * 1024)))

enum { ID_INFO = 20, ID_SAVE, ID_REINSTALL, ID_ONLINE, ID_LANGUAGE, ID_EXIT, ID_BACK };   /* More's (the home's are HfDo values) */

static void put(char *dst, size_t cap, const char *text) { snprintf(dst, cap, "%s", text ? text : ""); }

static void row(HfView *v, HfText label, const char *value) {
    if (v->row_count < HF_VIEW_ROWS) snprintf(v->rows[v->row_count++], HF_VIEW_LINE, "%s\t%s", T(label), value);
}

static void row_text(HfView *v, const char *text) {
    if (v->row_count < HF_VIEW_ROWS && text && text[0]) put(v->rows[v->row_count++], HF_VIEW_LINE, text);
}

/* The bottom screen's last line: the language switch and START; in the simple display, how to leave it. */
static void footer(HfView *v) {
    if (ui_simple()) put(v->footer, sizeof v->footer, T(HT_SIMPLE_FOOTER));
    else snprintf(v->footer, sizeof v->footer, "%s    %s", T(HT_LANG_SWITCH), T(HT_START_EXIT));
}

/* The button the D-pad is on now. */
static int selected_now(void) {
    HfView *v = ui_begin();
    int sel = v->selected;
    ui_end();
    return sel;
}

/* ---- the language ---- */

void language_load(void) {
    char text[8];
    if (read_small(LANGUAGE_FILE, text, sizeof text) < 2) return;
    if (!strncmp(text, "es", 2)) app.lang = HF_LANG_ES;
    if (!strncmp(text, "en", 2)) app.lang = HF_LANG_EN;
}

void language_switch(void) {
    const char *code;
    app.lang = app.lang == HF_LANG_ES ? HF_LANG_EN : HF_LANG_ES;
    code = app.lang == HF_LANG_ES ? "es" : "en";
    mkdir("sdmc:/3ds", 0777);
    mkdir("sdmc:/3ds/heavenfall", 0777);
    if (write_whole(LANGUAGE_FILE, code, 2)) LOG("language: not saved");
    LOG("language: %s", code);
}

/* ---- the home screen ---- */

/* MH XX copied since the installed version, the latest, was built (hf_xx_came): its Update builds it in. */
static int xx_came(void) {
    const Status *s = &app.status;
    return app.check == HF_CHECK_DONE && s->installed[0] && s->latest[0] && !hf_version_newer(s->latest, s->installed) &&
           status_xx_came(s->latest, app.latest_xx_set);
}

/* The big button's label. */
static void primary_label(const HfHome *h, char *out, size_t cap) {
    const Status *s = &app.status;
    switch (h->primary) {
    case HF_DO_INSTALL: put(out, cap, T(HT_BTN_INSTALL)); break;
    case HF_DO_UPDATE:
        if (h->new_version) snprintf(out, cap, "%s %s", T(HT_BTN_UPDATE_TO), s->latest);
        else put(out, cap, T(HT_BTN_UPDATE));
        break;
    case HF_DO_SETUP: put(out, cap, T(HT_BTN_SETUP)); break;
    default: snprintf(out, cap, "%s %s", T(HT_BTN_PLAY), app_edition()->name); break;
    }
}

static void home_view(void) {
    const Status *s = &app.status;
    HfHomeIn in;
    HfHome h;
    HfTimings last;
    char detail[HF_VIEW_LINE] = "", label[HF_VIEW_LABEL], play[HF_VIEW_LABEL], dur[24];
    HfView *v;
    int keep, sel, i;
    memset(&in, 0, sizeof in);
    in.title_installed = s->title_installed;
    in.installed_complete = s->installed_complete;
    in.installed = s->installed;
    in.check = app.check;
    in.latest = s->latest;
    in.dump = s->dump;   /* DUMP_* are HF_DUMP_* */
    in.game = s->game_state;
    in.xx_came = xx_came();
    in.app_newer = app.check == HF_CHECK_DONE && app.latest_app_newer;
    hf_home(&in, &h);
    if (h.detail == HT_HOME_INSTALL_HINT) {   /* the time an install takes, from the last one's rates or the guesses */
        uint64_t bytes[HF_STAGES] = {app.latest_set_bytes, app.latest_set_bytes * HF_TUNE_MOD_TITLE_PER_SET, 0};
        int have = timings_read(&last);
        hf_duration_text(task_expected_s(have ? &last : NULL, bytes, s->dump_bytes ? s->dump_bytes : 1), dur, sizeof dur);
        hf_text_fill(T(HT_HOME_INSTALL_HINT), dur, detail, sizeof detail);
    } else if (h.detail >= 0) {
        put(detail, sizeof detail, T((HfText)h.detail));
    }
    primary_label(&h, label, sizeof label);
    snprintf(play, sizeof play, "%s %s", T(HT_BTN_PLAY), app_edition()->name);

    v = ui_begin();
    keep = v->screen == HF_SCREEN_HOME && !v->message.on ? v->selected : 0;
    ui_reset(v, HF_SCREEN_HOME);
    put(v->heading, sizeof v->heading, app_edition()->name);
    if (h.new_version) snprintf(v->state, sizeof v->state, "%s %s", T(h.state), s->latest);
    else put(v->state, sizeof v->state, T(h.state));
    v->tone = (HfTone)h.tone;
    put(v->detail, sizeof v->detail, detail);
    row(v, HT_HOME_INSTALLED_LABEL, s->title_installed ? (s->installed[0] ? s->installed : T(HT_UNKNOWN)) : T(HT_NONE));
    row(v, HT_HOME_LATEST_LABEL, s->latest[0] ? s->latest : app.check == HF_CHECK_RUNNING ? "..." : T(HT_UNKNOWN));
    if (app.notes[0] && s->latest[0]) {
        snprintf(v->notes_title, sizeof v->notes_title, "%s %s", T(HT_NOTES_TITLE), s->latest);
        put(v->notes, sizeof v->notes, app.notes);
    }
    ui_button(v, label, h.primary, 1, 1);
    if (h.primary != HF_DO_PLAY) ui_button(v, play, HF_DO_PLAY, 0, h.can_play);
    ui_button(v, T(HT_BTN_PLAY_ORIGINAL), HF_DO_ORIGINAL, 0, 1);
    ui_button(v, T(HT_BTN_MORE), HF_DO_MORE, 0, 1);
    sel = keep >= 0 && keep < v->button_count && v->buttons[keep].enabled ? keep : 0;
    for (i = 0; i < v->button_count && !v->buttons[sel].enabled; i++) sel = (sel + 1) % v->button_count;
    v->selected = sel;
    v->busy = check_running();
    footer(v);
    ui_end();
}

/* The first frame of another edition, while its status is gathered. */
static void edition_switch(int step) {
    HfView *v;
    check_stop(1);
    app.edition = (app.edition + (step > 0 ? 1 : HF_EDITION_COUNT - 1)) % HF_EDITION_COUNT;
    log_close();
    log_open();
    app.status.latest[0] = 0;
    app.notes[0] = 0;
    app.latest_set_bytes = 0;
    app.latest_xx_set = 0;
    app.latest_app_newer = 0;
    v = ui_begin();
    ui_reset(v, HF_SCREEN_HOME);
    put(v->heading, sizeof v->heading, app_edition()->name);
    put(v->state, sizeof v->state, T(HT_CHECKING));
    v->busy = 1;
    footer(v);
    ui_end();
    ui_work();   /* the drawing thread turns the spinner while the card is searched */
    status_gather();
    check_start();
    home_view();
}

/* ---- More: the menu and the information page ---- */

/* The information page: the old status table (the check waited for first: B stops it). */
static void info_run(void) {
    const Status *s = &app.status;
    char friends[200] = "", text[64];
    const char *online;
    UiEvent ev;
    HfView *v;
    int st, id;
    if (check_running()) {
        v = ui_begin();
        ui_reset(v, HF_SCREEN_MENU);
        put(v->heading, sizeof v->heading, T(HT_BTN_INFO));
        put(v->state, sizeof v->state, T(HT_CHECKING));
        v->busy = 1;
        footer(v);
        ui_end();
        while (check_running() && app_loop(&ev)) {
            if (check_poll()) break;
            if (ev.keys & KEY_B) break;
        }
        check_stop(1);
    }
    st = hf_friends_status(friends, sizeof friends);
    online = online_state_text(st);
    LOG("information: friends patch %d %s", st, friends);

    v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    put(v->heading, sizeof v->heading, T(HT_BTN_INFO));
    snprintf(text, sizeof text, "%s%s", HF_APP_VERSION, app.probe ? " (PROBE)" : "");
    row(v, HT_TITLE, text);
    row(v, HT_EDITION, app_edition()->name);
    row(v, HT_REGION, s->region >= 0 ? region_name(s->region) : T(HT_UNKNOWN));
    row(v, HT_INSTALLED, s->title_installed ? (s->installed[0] ? s->installed : T(HT_UNKNOWN)) : T(HT_NONE));
    row(v, HT_LATEST, s->latest[0] ? s->latest : T(HT_UNKNOWN));
    row(v, HT_GAME_DATA, s->game_state == HF_GAME_MISSING ? T(HT_GAME_VALUE_MISSING) :
        s->game_state == HF_GAME_UPDATE ? T(HT_GAME_VALUE_UPDATE) : T(HT_GAME_VALUE_OK));
    row(v, HT_DUMP, s->dump == DUMP_FOUND ? T(HT_YES) : s->dump == DUMP_ENCRYPTED ? T(HT_ENCRYPTED) :
        s->dump == DUMP_OTHER_REGION ? T(HT_OTHER_REGION) : T(HT_NOT_FOUND));
    if (s->dump_path[0]) row_text(v, !strncmp(s->dump_path, "sdmc:", 5) ? s->dump_path + 5 : s->dump_path);
    row(v, HT_XX, s->xx == XX_FOUND ? T(HT_FOUND) : s->xx == XX_OTHER_VERSION ? T(HT_XX_OTHER_VERSION) :
        s->xx == XX_ENCRYPTED ? T(HT_ENCRYPTED) : T(HT_NOT_FOUND));
    snprintf(text, sizeof text, "%s%s", s->luma ? "v" : "", s->luma ? s->luma_version : T(HT_NOT_FOUND));
    row(v, HT_LUMA, text);
    snprintf(text, sizeof text, "%lu MB", MB(s->free_bytes));
    row(v, HT_FREE, text);
    row_text(v, online[0] ? online : friends);
    put(v->detail, sizeof v->detail, app.probe ? T(HT_PROBE) : "");
    ui_button(v, T(HT_BTN_BACK), ID_BACK, 1, 1);
    v->selected = 0;
    footer(v);
    ui_end();
    while (app_loop(&ev)) {
        id = ui_choose(&ev);
        if (id == ID_BACK || id == UI_BACK || (ev.keys & KEY_START)) break;
    }
}

/* More's page; `language_changed`: its state line says the language just chosen (the answer to that button). */
static void more_view(int selected, int language_changed) {
    HfView *v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    put(v->heading, sizeof v->heading, T(HT_BTN_MORE));
    if (language_changed) {
        put(v->state, sizeof v->state, T(HT_LANG_NOW));
        v->tone = HF_TONE_GOOD;
    } else {
        snprintf(v->state, sizeof v->state, "%s v%s", T(HT_TITLE), HF_APP_VERSION);
        v->tone = HF_TONE_MUTED;
    }
    put(v->detail, sizeof v->detail, app_edition()->name);
    ui_button(v, T(HT_BTN_INFO), ID_INFO, 0, 1);
    ui_button(v, T(HT_BTN_SAVE), ID_SAVE, 0, 1);
    ui_button(v, T(HT_BTN_REINSTALL), ID_REINSTALL, 0, app.status.title_installed);
    ui_button(v, T(HT_BTN_ONLINE), ID_ONLINE, 0, 1);
    ui_button(v, T(HT_BTN_LANGUAGE), ID_LANGUAGE, 0, 1);
    ui_button(v, T(HT_BTN_EXIT), ID_EXIT, 0, 1);
    ui_button(v, T(HT_BTN_BACK), ID_BACK, 0, 1);
    v->selected = selected >= 0 && selected < v->button_count ? selected : 0;
    footer(v);
    ui_end();
}

/* 1 when the app leaves (Exit, START, the console closing). */
static int more_run(void) {
    UiEvent ev;
    int id, at;
    more_view(0, 0);
    while (app_loop(&ev)) {
        check_poll();   /* the start's answer, kept for the home page */
        if (ev.keys & KEY_START) return 1;
        if (ev.keys & KEY_SELECT) {
            language_switch();
            more_view(selected_now(), 1);
            continue;
        }
        id = ui_choose(&ev);
        at = selected_now();   /* the page an action opens moves the selection: it comes back here */
        switch (id) {
        case ID_INFO: info_run(); break;
        case ID_SAVE: saves_copy_flow(0); break;
        case ID_REINSTALL:   /* back to the home page after it, which says the state it left */
            if (!ui_confirm(T(HT_REINSTALL_ASK))) break;
            LOG("more: reinstall");
            return update_run(0, 1);
        case ID_ONLINE: online_run(); break;
        case ID_LANGUAGE:
            language_switch();
            more_view(selected_now(), 1);
            continue;
        case ID_EXIT: return 1;
        case ID_BACK:
        case UI_BACK: return 0;
        default: continue;
        }
        more_view(at, 0);
    }
    return 1;
}

/* ---- the loop ---- */

/* A button of the home page; 1 when the app leaves. */
static int home_act(int id) {
    switch (id) {
    case HF_DO_INSTALL:
    case HF_DO_UPDATE: return update_run(0, 0);
    case HF_DO_SETUP: return wizard_run();
    case HF_DO_PLAY: return start_edition() == 0;
    case HF_DO_ORIGINAL: return start_original() == 0;
    case HF_DO_MORE: return more_run();
    default: return 0;
    }
}

/* At the start, once: the save an update took away (put back when the title's save opens: saves_restore_flow), the
 * save copy a first install left waiting (offered when the title's save opens), or the guide when nothing is
 * installed and no usable dump is found. 1 when the app leaves. */
static int start_offers(void) {
    const Status *s = &app.status;
    if (s->title_installed && s->save_restore[0]) {
        LOG("start: the save from backup %s is to be put back", s->save_restore);
        saves_restore_flow(0);
        return 0;
    }
    if (s->title_installed && s->save_pending) {
        LOG("start: the save copy is pending");
        saves_copy_flow(1);
        return 0;
    }
    if (!s->title_installed && s->dump != DUMP_FOUND && !app.guide_shown) {
        app.guide_shown = 1;
        LOG("start: nothing installed and no usable dump: the guide");
        return wizard_run();
    }
    return 0;
}

int home_run(void) {
    UiEvent ev;
    int leave;
    home_view();
    leave = start_offers();
    if (!leave) home_view();
    while (!leave && app_loop(&ev)) {
        int id;
        if (check_poll()) home_view();
        if (!ev.keys && ev.button < 0) continue;
        if (ev.keys & KEY_START) return 1;
        if (ev.keys & KEY_SELECT) {
            language_switch();
            home_view();
            continue;
        }
        if ((ev.keys & (KEY_L | KEY_R)) && HF_EDITION_COUNT > 1) {
            edition_switch(ev.keys & KEY_R ? 1 : -1);
            continue;
        }
        id = ui_choose(&ev);
        if (id < 0) continue;
        leave = home_act(id);
        if (!leave) home_view();
    }
    return 1;
}
