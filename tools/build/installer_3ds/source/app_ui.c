/* The pages on the drawing layer (ui.h): a page's reset and its buttons, the D-pad
 * over them, a message or a question over the top screen, and the update's task page: its three stages and single bar
 * (uimodel.h's progress rules), the time left, B twice to cancel, and the screens' dimming while it runs. Each fills
 * the view under its lock, with no I/O between ui_begin and ui_end; the waits read the drawing thread's events. */
#include <stdio.h>
#include <string.h>

#include "app.h"
#include "hf_tuning.h"
#include "uitext.h"

#define REDRAW_MS 300
#define HASH_SHARE 500   /* permille of the rest of "Installing" a hash pass takes: it reads what the write reads */

enum { ID_OK = 100, ID_YES, ID_NO };   /* a message's buttons (a page's are below 100) */
enum { ID_TASK_SCREENS = 110, ID_TASK_CANCEL };   /* the install page's, by touch */

const HfUiTuning app_tuning = HF_UI_TUNING_INIT;

const char *T(HfText id) { return hf_text(app.lang, id); }

const char *region_name(int region) { return region == REGION_EUR ? "EUR" : region == REGION_USA ? "USA" : "?"; }

static void put(char *dst, size_t cap, const char *text) { snprintf(dst, cap, "%s", text ? text : ""); }

/* ---- a page ---- */

/* ui_working's page: the buttons it put away, given back by ui_working_end unless a new page came meanwhile. */
static struct {
    int on, page_changed, busy, count, selected;
    HfViewButton buttons[HF_VIEW_BUTTONS];
} work;

void ui_reset(HfView *v, HfScreen screen) {
    unsigned serial = v->serial;
    work.page_changed = 1;
    char message[sizeof v->message];
    memcpy(message, &v->message, sizeof message);
    memset(v, 0, sizeof *v);
    memcpy(&v->message, message, sizeof message);
    v->serial = serial;
    v->screen = screen;
    v->tone = HF_TONE_PLAIN;
    v->task.stage = HF_STAGES;
    v->selected = -1;
}

void ui_button(HfView *v, const char *label, int id, int primary, int enabled) {
    HfViewButton *b;
    if (v->button_count >= HF_VIEW_BUTTONS) return;
    b = &v->buttons[v->button_count++];
    put(b->label, sizeof b->label, label);
    b->id = id;
    b->primary = primary;
    b->enabled = enabled;
}

int ui_choose(const UiEvent *ev) {
    HfView *v;
    int id = -1, n;
    if (ev->button >= 0) return ev->button;   /* a touch on an enabled button: its id */
    if (ev->keys & KEY_B) return UI_BACK;
    if (!(ev->keys & (KEY_A | KEY_DUP | KEY_DDOWN | KEY_DLEFT | KEY_DRIGHT))) return -1;
    v = ui_begin();
    n = v->button_count;
    if (ev->keys & KEY_A) {
        if (v->selected >= 0 && v->selected < n && v->buttons[v->selected].enabled) id = v->buttons[v->selected].id;
    } else if (n > 0) {   /* the D-pad moves as the buttons are drawn: up and down, and left and right across columns */
        int dx = ev->keys & KEY_DLEFT ? -1 : ev->keys & KEY_DRIGHT ? 1 : 0, dy = dx ? 0 : ev->keys & KEY_DUP ? -1 : 1;
        v->selected = hf_button_step(v, v->selected, dx, dy);
    }
    ui_end();
    return id;
}

/* ---- messages ---- */

/* A text over the top screen with its keys line and its buttons (the page's own come back after), until one of `keys`
 * or a button: the keys pressed (KEY_A for the first button, KEY_B for the second), 0 when the app closes. `small`
 * (may be "") goes in the footer meanwhile. The screens are turned on first. */
static u32 ask(const char *text, const char *keys_line, u32 keys, int yes_no, HfTone tone, const char *small) {
    HfViewButton saved[HF_VIEW_BUTTONS];
    char saved_footer[HF_VIEW_LINE];
    int saved_count, saved_selected;
    u32 got = 0;
    UiEvent ev;
    HfView *v;
    ui_working_end();
    ui_screens(1);
    ui_flush_events();
    v = ui_begin();
    memcpy(saved, v->buttons, sizeof saved);
    memcpy(saved_footer, v->footer, sizeof saved_footer);
    saved_count = v->button_count;
    saved_selected = v->selected;
    v->message.on = 1;
    put(v->message.text, sizeof v->message.text, text);
    put(v->message.keys, sizeof v->message.keys, keys_line);
    v->message.tone = tone;
    if (small && small[0]) put(v->footer, sizeof v->footer, small);
    memset(v->buttons, 0, sizeof v->buttons);
    v->button_count = 0;
    ui_button(v, yes_no ? T(HT_PRESS_A) : T(HT_BTN_CONTINUE), yes_no ? ID_YES : ID_OK, 1, 1);
    if (yes_no) ui_button(v, T(HT_PRESS_B), ID_NO, 0, 1);
    v->selected = -1;
    ui_end();
    while (app_loop(&ev)) {
        if (ev.button == ID_OK || ev.button == ID_YES) { got = KEY_A; break; }
        if (ev.button == ID_NO) { got = KEY_B; break; }
        if (ev.keys & keys) { got = ev.keys & keys; break; }
    }
    v = ui_begin();
    v->message.on = 0;
    memcpy(v->buttons, saved, sizeof saved);
    memcpy(v->footer, saved_footer, sizeof saved_footer);
    v->button_count = saved_count;
    v->selected = saved_selected;
    ui_end();
    return got;
}

void ui_message_ex(const char *text, HfTone tone, const char *small) {
    char keys[HF_VIEW_LABEL];
    snprintf(keys, sizeof keys, "A: %s", T(HT_BTN_CONTINUE));
    ask(text, keys, KEY_A | KEY_B | KEY_START, 0, tone, small);
}

void ui_message(const char *line) { ui_message_ex(line, HF_TONE_PLAIN, ""); }

int ui_confirm(const char *question) {
    char keys[HF_VIEW_LABEL];
    snprintf(keys, sizeof keys, "%s   %s", T(HT_PRESS_A), T(HT_PRESS_B));
    return (ask(question, keys, KEY_A | KEY_B, 1, HF_TONE_PLAIN, "") & KEY_A) != 0;
}

void ui_notice_for(const char *text, u32 ms) {
    u64 end = osGetTime() + ms;
    UiEvent ev;
    HfView *v;
    ui_working_end();
    ui_screens(1);
    v = ui_begin();
    v->message.on = 1;
    put(v->message.text, sizeof v->message.text, text);
    v->message.keys[0] = 0;
    v->message.tone = HF_TONE_GOOD;
    v->button_count = 0;
    v->selected = -1;
    ui_end();
    while (osGetTime() < end && app_loop(&ev)) {}
    v = ui_begin();
    v->message.on = 0;
    ui_end();
}

void ui_working(const char *text) {
    HfView *v;
    ui_work();
    ui_screens(1);
    v = ui_begin();
    if (!work.on) {   /* the page's own buttons put away (a second call only changes the text) */
        work.on = 1;
        work.page_changed = 0;
        work.busy = v->busy;
        work.count = v->button_count;
        work.selected = v->selected;
        memcpy(work.buttons, v->buttons, sizeof work.buttons);
    }
    v->message.on = 1;
    put(v->message.text, sizeof v->message.text, text);
    v->message.keys[0] = 0;
    v->message.tone = HF_TONE_PLAIN;
    v->busy = 1;   /* the spinner in the box: the drawing thread keeps it turning while the main thread works */
    v->button_count = 0;
    v->selected = -1;
    ui_end();
}

void ui_working_end(void) {
    HfView *v;
    if (!work.on) return;
    work.on = 0;
    v = ui_begin();
    v->message.on = 0;
    if (work.page_changed) {
        v->busy = 0;
    } else {
        v->busy = work.busy;
        memcpy(v->buttons, work.buttons, sizeof v->buttons);
        v->button_count = work.count;
        v->selected = work.selected;
    }
    ui_end();
    ui_flush_events();   /* the keys pressed while it ran answer nothing */
}

/* ---- the task page and its bar ---- */

static struct {
    int active;                     /* task_begin .. task_end: the bar, the cancel, the dimming */
    HfProgress bar;
    HfTimings last;
    int have_last;
    uint64_t bytes[HF_STAGES];      /* the plan's: the files to download, the title (the dump's size until known) */
    uint64_t title_bytes;           /* the title's exact size (task_title_size), 0 until known */
    uint64_t game_bytes;            /* the plan's game data title, 0: not installed this time */
    uint64_t game_exact;            /* its exact size once known */
    int part;                       /* the title being installed: HF_TITLE_GAME / HF_TITLE_MOD, 0 none */
    int game_done;
    u64 part_began;
    uint64_t game_ms;               /* the game data install's time (timings.json) */
    unsigned part_lo, part_hi;      /* the part of "Installing" the running title fills, permille (by their bytes) */
    int stage;                      /* the stage running, -1 before the plan */
    u64 stage_began;
    uint64_t ms[HF_STAGES];         /* each stage's time so far (timings.json) */
    HfText phase;                   /* the phase running */
    int cancellable;                /* it reports progress, so B can stop it */
    int cancel_fresh;               /* a phase without progress ran: the next progress call sets cancel_from */
    u64 cancel_from;                /* B pressed before this (while nothing could be cancelled) does not count */
    HfCancel cancel;
    uint64_t dl_base;               /* the download stage's bytes of the files before the one running */
    unsigned span_lo, span_hi;      /* the part of the rest of "Installing" the running pass fills, permille */
    int hashed;                     /* this attempt ran a hash pass */
    int keep_on;                    /* the player asked to keep the screens on: no dimming until the end */
    u64 last_draw;
} task = {.stage = -1, .span_hi = 1000};

static void plan_expect(const uint64_t bytes[HF_STAGES], uint64_t game_bytes, uint32_t expect[HF_STAGES],
                        const HfTimings *last) {
    hf_timings_expect_titles(last, &app_tuning, bytes, game_bytes, expect);
    if (!bytes[HF_STAGE_INSTALL] && !game_bytes) expect[HF_STAGE_INSTALL] = expect[HF_STAGE_FINISH] = 1;   /* no title */
}

uint32_t task_expected_s(const HfTimings *last, const uint64_t bytes[HF_STAGES], uint64_t game_bytes) {
    uint32_t expect[HF_STAGES];
    uint64_t ms = 0;
    int s;
    plan_expect(bytes, game_bytes, expect, last);
    for (s = 0; s < HF_STAGES; s++) ms += expect[s];
    return (uint32_t)((ms + 999) / 1000);
}

static void dim_check(u64 now) {
    if (!task.active || task.keep_on || !ui_screens_on() ||
        !hf_backlight_should_dim(ui_last_input_ms(), now, app_tuning.backlight_idle_ms))
        return;
    LOG("screens off: no key for %lu s", (unsigned long)((now - ui_last_input_ms()) / 1000));
    ui_screens(0);
}

static void task_draw(u64 now) {
    char dur[24], eta[HF_VIEW_LABEL] = "";
    int armed = hf_cancel_armed(&task.cancel, now, app_tuning.cancel_window_ms);
    HfView *v;
    task.last_draw = now;
    if (task.active) {
        hf_duration_text(hf_progress_eta_s(&task.bar, now), dur, sizeof dur);
        hf_text_fill(T(HT_TASK_ETA), dur, eta, sizeof eta);
    }
    v = ui_begin();
    if (task.active) {
        v->task.stage = task.stage;
        v->task.permille = hf_progress_permille(&task.bar);
        put(v->task.eta, sizeof v->task.eta, eta);
    }
    put(v->task.cancel, sizeof v->task.cancel,
        !task.cancellable ? T(HT_CANNOT_CANCEL) : armed ? T(HT_CANCEL_AGAIN) : T(HT_CANCEL_HINT));
    put(v->footer, sizeof v->footer,
        !task.active ? T(HT_NO_SLEEP) : task.keep_on ? T(HT_SCREENS_STAY_ON) : T(HT_SCREENS_OFF_HINT));
    if (task.active && v->screen == HF_SCREEN_TASK && !v->message.on) {   /* touch only: A and the D-pad do nothing here */
        v->button_count = 0;
        ui_button(v, T(task.keep_on ? HT_BTN_LET_SCREENS : HT_BTN_KEEP_SCREENS), ID_TASK_SCREENS, 0, 1);
        ui_button(v, T(armed ? HT_BTN_CANCEL_AGAIN : HT_BTN_CANCEL), ID_TASK_CANCEL, 0, task.cancellable);
        v->selected = -1;
    }
    ui_end();
}

void task_page(HfText detail) {
    HfView *v;
    int i;
    ui_work();
    v = ui_begin();
    ui_reset(v, HF_SCREEN_TASK);
    put(v->heading, sizeof v->heading, app_edition()->name);
    put(v->detail, sizeof v->detail, T(detail));
    for (i = 0; i < HF_STAGES; i++) put(v->task.stage_names[i], sizeof v->task.stage_names[i], T(HT_STAGE_DOWNLOAD + i));
    put(v->task.eta, sizeof v->task.eta, T(HT_TASK_ETA_UNKNOWN));
    put(v->footer, sizeof v->footer, T(HT_NO_SLEEP));
    v->busy = 1;
    ui_end();
    memset(&task, 0, sizeof task);
    task.stage = -1;
    task.span_hi = 1000;
}

void task_begin(const HfTimings *last, const uint64_t bytes[HF_STAGES], uint64_t game_bytes) {
    uint32_t expect[HF_STAGES];
    u64 now = osGetTime();
    task.have_last = last != NULL;
    if (last) task.last = *last;
    memcpy(task.bytes, bytes, sizeof task.bytes);
    task.game_bytes = game_bytes;
    task.game_exact = 0;
    task.part = 0;
    task.game_done = 0;
    task.game_ms = 0;
    task.part_lo = 0;
    task.part_hi = 1000;
    plan_expect(bytes, game_bytes, expect, last);
    hf_progress_start(&task.bar, expect, HF_STAGE_DOWNLOAD, app_tuning.finish_cap_permille, now);
    task.active = 1;
    task.stage = HF_STAGE_DOWNLOAD;
    task.stage_began = now;
    memset(task.ms, 0, sizeof task.ms);
    task.title_bytes = 0;
    task.dl_base = 0;
    task.span_lo = 0;
    task.span_hi = 1000;
    LOG("task: %lu + %lu bytes (+ %lu of game data), expected %lu + %lu + %lu ms (%s)", (unsigned long)bytes[0], (unsigned long)bytes[1], (unsigned long)game_bytes,
        (unsigned long)expect[0], (unsigned long)expect[1], (unsigned long)expect[2],
        last ? "the last install's rates" : "the first guesses");
    task_draw(now);
}

static void stage_enter(int stage, u64 now) {
    if (task.stage >= 0 && task.stage < HF_STAGES) task.ms[task.stage] += now - task.stage_began;
    task.stage = stage;
    task.stage_began = now;
}

static uint64_t game_est(void) { return task.game_exact ? task.game_exact : task.game_bytes; }
static uint64_t mod_est(void) { return task.title_bytes ? task.title_bytes : task.bytes[HF_STAGE_INSTALL]; }
/* The running title's size (its exact one once known, else the plan's). */
static uint64_t title_estimate(void) { return task.part == HF_TITLE_GAME ? game_est() : mod_est(); }

/* The part of "Installing" the running title fills: the two titles share it by their bytes. */
static void part_range(void) {
    uint64_t g = task.game_bytes ? game_est() : 0, tot = g + mod_est();
    task.part_lo = 0;
    task.part_hi = 1000;
    if (!g || !tot) return;
    if (task.part == HF_TITLE_GAME) task.part_hi = (unsigned)(1000 * g / tot);
    else if (task.part == HF_TITLE_MOD) task.part_lo = (unsigned)(1000 * g / tot);
}

/* The rest of "Installing" planned again for `install_bytes` of work from now in the running title (the other title,
 * when it is still to come, at its estimate); the bar stays where it is. */
static void replan_install(uint64_t install_bytes, u64 now) {
    uint64_t b[HF_STAGES], game = 0;
    uint32_t expect[HF_STAGES];
    memcpy(b, task.bytes, sizeof b);
    if (task.part == HF_TITLE_GAME) {
        game = install_bytes;
        b[HF_STAGE_INSTALL] = mod_est();
    } else {
        b[HF_STAGE_INSTALL] = install_bytes;
    }
    if (!b[HF_STAGE_INSTALL]) b[HF_STAGE_INSTALL] = 1;
    plan_expect(b, game, expect, task.have_last ? &task.last : NULL);
    if (task.stage != HF_STAGE_INSTALL) stage_enter(HF_STAGE_INSTALL, now);
    hf_progress_replan(&task.bar, HF_STAGE_INSTALL, expect, now);
    LOG("task: planned again from Installing: %lu MB, %lu + %lu ms", (unsigned long)(install_bytes >> 20),
        (unsigned long)expect[HF_STAGE_INSTALL], (unsigned long)expect[HF_STAGE_FINISH]);
}

void task_download(uint64_t base) { task.dl_base = base; }

void task_title_size(uint64_t bytes) {
    if (task.part == HF_TITLE_GAME) task.game_exact = bytes;
    else task.title_bytes = bytes;
    part_range();
    if (task.active) replan_install(bytes, osGetTime());
}

void task_part_begin(HfTitleKind kind) {
    task.part = (int)kind;
    task.part_began = osGetTime();
    part_range();
    if (task.active && task.game_bytes) ui_notice(kind == HF_TITLE_GAME ? HT_GAME_NOTE : HT_MOD_NOTE);
    LOG("task: the %s title begins, its share of Installing %u..%u permille", kind == HF_TITLE_GAME ? "game data" : "mod",
        task.part_lo, task.part_hi);
}

void task_part_end(HfTitleKind kind) {
    if (kind == HF_TITLE_GAME) {
        task.game_ms = osGetTime() - task.part_began;
        task.game_done = 1;
    }
    task.part = 0;
}

void task_route_again(void) {
    if (task.active) replan_install(title_estimate(), osGetTime());
}

void task_end(int done) {
    u64 now = osGetTime();
    HfView *v;
    if (task.active) {
        stage_enter(done ? HF_STAGES : task.stage, now);
        if (done) hf_progress_end(&task.bar);
        task.active = 0;
        v = ui_begin();
        if (done) {
            v->task.stage = HF_STAGES;
            v->task.permille = 1000;
            v->task.eta[0] = 0;
        }
        v->task.cancel[0] = 0;
        v->busy = 0;
        ui_end();
    }
    ui_screens(1);
}

void task_measured(HfTimings *out) {
    memset(out, 0, sizeof *out);
    memcpy(out->ms, task.ms, sizeof out->ms);
    out->bytes[HF_STAGE_DOWNLOAD] = task.bytes[HF_STAGE_DOWNLOAD];
    out->bytes[HF_STAGE_INSTALL] = task.title_bytes;
    /* the stage held both installs: the game data's time (with its own finish) is taken out of the mod's */
    if (task.game_done && task.game_ms && task.ms[HF_STAGE_INSTALL] > task.game_ms) {
        out->ms[HF_STAGE_INSTALL] = task.ms[HF_STAGE_INSTALL] - task.game_ms;
        out->game_ms = task.game_ms;
        out->game_bytes = game_est();
    }
}

/* The bar from a progress call: a download's bytes over all the stage's files; a hash or write pass's bytes over its
 * part of "Installing"; any other phase by its time against the plan. */
static void bar_update(uint64_t done, uint64_t total, u64 now) {
    int stage = hf_stage_of_phase(task.phase);
    if (stage == HF_STAGE_DOWNLOAD && task.stage == HF_STAGE_DOWNLOAD) {
        uint64_t all = task.bytes[HF_STAGE_DOWNLOAD], at = task.dl_base + done;
        hf_progress_update(&task.bar, HF_STAGE_DOWNLOAD, at, all > at ? all : at, now);
    } else if (total && (task.phase == HT_PHASE_HASH || task.phase == HT_PHASE_WRITE || task.phase == HT_PHASE_WRITE_2)) {
        uint64_t part = done > total ? total : done;
        /* this pass's share of the title, then the title's share of Installing */
        uint64_t inner = ((uint64_t)task.span_lo * total + (uint64_t)(task.span_hi - task.span_lo) * part) / 1000;
        hf_progress_update(&task.bar, HF_STAGE_INSTALL,
                           ((uint64_t)task.part_lo * total + (uint64_t)(task.part_hi - task.part_lo) * inner) / 1000, total,
                           now);
    } else if (task.stage >= 0 && task.stage < HF_STAGES) {
        hf_progress_update(&task.bar, (HfStage)task.stage, 0, 0, now);
    }
}

int ui_progress(void *ctx, uint64_t done, uint64_t total) {
    u64 now = osGetTime();
    UiEvent ev;
    int cancel = 0, changed = 0;
    (void)ctx;
    ui_work();
    if (!ui_apt()) return 1;
    if (aptCheckHomePressRejected()) {   /* refused while it works: the footer says until when */
        HfView *v = ui_begin();
        put(v->footer, sizeof v->footer, T(HT_HOME_LATER));
        ui_end();
        changed = 1;
        LOG("HOME: refused while the update works");
    }
    if (task.cancel_fresh) {
        task.cancel_fresh = 0;
        task.cancel_from = now;
        changed = 1;
    }
    while (ui_next_event(&ev)) {
        if (ev.button == ID_TASK_SCREENS) {
            task.keep_on = !task.keep_on;
            changed = 1;
            LOG("screens: kept on %d (the player's button)", task.keep_on);
        }
        if (((ev.keys & KEY_B) || (ev.button == ID_TASK_CANCEL && task.cancellable)) && ev.ms >= task.cancel_from) {
            changed = 1;
            if (hf_cancel_press(&task.cancel, ev.ms, app_tuning.cancel_window_ms)) cancel = 1;
        }
    }
    if (cancel) {
        LOG("cancel: B or the Cancel button twice");
        return 1;
    }
    if (task.active) {
        bar_update(done, total, now);
    } else if (total) {
        HfView *v = ui_begin();
        v->task.permille = (unsigned)((done > total ? total : done) * 1000 / total);
        ui_end();
    }
    dim_check(now);
    if (changed || now - task.last_draw >= REDRAW_MS || (total && done >= total)) task_draw(now);
    return 0;
}

/* The phases that call no progress while they run: B cannot stop them. */
static int without_progress(HfText name) {
    return name == HT_PHASE_OPEN || name == HT_PHASE_AM || name == HT_PHASE_RELEASE || name == HT_CHECKING ||
           name == HT_PHASE_APP_INSTALL || name == HT_SAVE_RESTORING;
}

void ui_phase(HfText name) {
    u64 now = osGetTime();
    int stage = hf_stage_of_phase(name);
    HfView *v;
    ui_work();
    /* the game data's own finish stays inside Installing: the bar's "Finishing" is the mod's, after it */
    if (name == HT_PHASE_AM && task.part == HF_TITLE_GAME) stage = task.stage;
    task.phase = name;
    task.cancellable = !without_progress(name);
    if (!task.cancellable) {
        task.cancel.armed = 0;
        task.cancel_fresh = 1;
    }
    if (task.active) {
        if (name == HT_PHASE_OPEN || name == HT_PHASE_OPEN_SIZING || name == HT_PHASE_PREPARE) {
            task.hashed = 0;   /* an attempt begins */
            task.span_lo = 0;
            task.span_hi = 1000;
        } else if (name == HT_PHASE_HASH) {
            task.hashed = 1;
            replan_install(2 * title_estimate(), now);
            task.span_lo = 0;
            task.span_hi = HASH_SHARE;
        } else if (name == HT_PHASE_WRITE || name == HT_PHASE_WRITE_2) {
            task.span_lo = task.hashed ? HASH_SHARE : 0;
            task.span_hi = 1000;
        }
        if (stage > task.stage) {
            stage_enter(stage, now);
            hf_progress_update(&task.bar, (HfStage)stage, 0, 0, now);
        }
    }
    v = ui_begin();
    put(v->state, sizeof v->state, T(name));
    v->tone = HF_TONE_PLAIN;
    v->busy = 1;
    if (!task.active) v->task.permille = 0;
    ui_end();
    task_draw(now);
    dim_check(now);
}

void ui_notice(HfText text) {
    HfView *v = ui_begin();
    put(v->task.note, sizeof v->task.note, T(text));
    ui_end();
    dim_check(osGetTime());
}

void ui_idle(void) {
    HfView *v = ui_begin();
    v->busy = 0;
    ui_end();
}
