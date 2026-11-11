/* The first-run guide: one page per step of hf_setup_step (uimodel.h): copy MH4U
 * with GodMode9, decrypt an encrypted copy, MH XX (optional: Skip, kept for the session), install, bring the MH4U save,
 * done. Each page has its steps as lines with GodMode9's own English menu names, "Check again" (the status gathered
 * anew) and Back. Opened from Set up on the home screen, and by itself once when nothing is installed and no usable
 * dump is found. */
#include <stdio.h>
#include <string.h>

#include "app.h"
#include "hf_tuning.h"

enum { W_BACK = 1, W_CHECK, W_SKIP, W_INSTALL, W_SAVE, W_PLAY };

static void put(char *dst, size_t cap, const char *text) { snprintf(dst, cap, "%s", text ? text : ""); }

static void line(HfView *v, HfText text) {
    if (v->row_count < HF_VIEW_ROWS) put(v->rows[v->row_count++], HF_VIEW_LINE, T(text));
}

static void line_filled(HfView *v, HfText text, const char *value) {
    if (v->row_count < HF_VIEW_ROWS) hf_text_fill(T(text), value, v->rows[v->row_count++], HF_VIEW_LINE);
}

/* GodMode9's steps: copying a game (a cartridge or a digital copy), or decrypting an encrypted copy. */
static void gm9_copy(HfView *v) {
    line(v, HT_GUIDE_GM9_START);
    line(v, HT_GUIDE_CART);
    line(v, HT_GUIDE_DIGITAL);
    line(v, HT_GUIDE_GM9_END);
}

static void gm9_decrypt(HfView *v) {
    line(v, HT_GUIDE_GM9_START);
    line(v, HT_GUIDE_DECRYPT_OPEN);
    line(v, HT_GUIDE_DECRYPT_CHOOSE);
    line(v, HT_GUIDE_GM9_END);
}

static HfSetupStep current_step(void) {
    const Status *s = &app.status;
    HfSetupIn in;
    memset(&in, 0, sizeof in);
    in.dump = s->dump;
    /* a copy of another revision is the player's part done: the update says why it goes without it */
    in.xx = s->xx == XX_OTHER_VERSION ? HF_XXD_FOUND : s->xx;
    in.xx_skipped = app.xx_skipped;
    in.title_installed = s->title_installed;
    in.save_pending = s->save_pending;
    in.game_missing = s->game_state == HF_GAME_MISSING;
    return hf_setup_step(&in);
}

static void page(HfSetupStep step) {
    char hint[HF_VIEW_LINE] = "", text[HF_VIEW_LINE], dur[24];
    HfTimings last;
    HfView *v;
    if (step == HF_SETUP_INSTALL) {   /* the time it takes (I/O before the view's lock) */
        uint64_t bytes[HF_STAGES] = {app.latest_set_bytes, app.latest_set_bytes * HF_TUNE_MOD_TITLE_PER_SET, 0};
        int have = timings_read(&last);
        hf_duration_text(task_expected_s(have ? &last : NULL, bytes, app.status.dump_bytes ? app.status.dump_bytes : 1),
                         dur, sizeof dur);
        hf_text_fill(T(HT_HOME_INSTALL_HINT), dur, hint, sizeof hint);
    }
    v = ui_begin();
    ui_reset(v, HF_SCREEN_MENU);
    switch (step) {
    case HF_SETUP_DUMP:
        put(v->heading, sizeof v->heading, T(HT_GUIDE_DUMP_TITLE));
        put(v->state, sizeof v->state, T(HT_HOME_NEED_DUMP));
        v->tone = HF_TONE_WARN;
        put(v->detail, sizeof v->detail, T(HT_GUIDE_DUMP_WHY));
        gm9_copy(v);
        ui_button(v, T(HT_BTN_CHECK_AGAIN), W_CHECK, 1, 1);
        break;
    case HF_SETUP_DECRYPT:
        put(v->heading, sizeof v->heading, T(HT_GUIDE_DECRYPT_TITLE));
        put(v->state, sizeof v->state, T(HT_HOME_DUMP_ENCRYPTED));
        v->tone = HF_TONE_WARN;
        gm9_decrypt(v);
        ui_button(v, T(HT_BTN_CHECK_AGAIN), W_CHECK, 1, 1);
        break;
    case HF_SETUP_XX:
        put(v->heading, sizeof v->heading, T(HT_GUIDE_XX_TITLE));
        if (app.status.xx == XX_ENCRYPTED) {
            put(v->state, sizeof v->state, T(HT_GUIDE_XX_ENCRYPTED));
            v->tone = HF_TONE_WARN;
        }
        put(v->detail, sizeof v->detail, T(HT_GUIDE_XX_WHY));
        if (app.status.xx == XX_ENCRYPTED) gm9_decrypt(v);
        else gm9_copy(v);
        ui_button(v, T(HT_BTN_CHECK_AGAIN), W_CHECK, 1, 1);
        ui_button(v, T(HT_BTN_SKIP), W_SKIP, 0, 1);
        break;
    case HF_SETUP_INSTALL:
        put(v->heading, sizeof v->heading, T(HT_GUIDE_INSTALL_TITLE));
        put(v->state, sizeof v->state, T(HT_HOME_NOT_INSTALLED));
        v->tone = HF_TONE_NEW;
        put(v->detail, sizeof v->detail, hint);
        line(v, HT_GUIDE_INSTALL_STEP);
        ui_button(v, T(HT_BTN_INSTALL), W_INSTALL, 1, 1);
        ui_button(v, T(HT_BTN_CHECK_AGAIN), W_CHECK, 0, 1);
        break;
    case HF_SETUP_SAVE:
        put(v->heading, sizeof v->heading, T(HT_GUIDE_SAVE_TITLE));
        line_filled(v, HT_GUIDE_SAVE_RUN, app_edition()->name);
        line(v, HT_GUIDE_SAVE_COPY);
        ui_button(v, T(HT_BTN_SAVE), W_SAVE, 1, 1);
        ui_button(v, T(HT_BTN_PLAY_NOW), W_PLAY, 0, 1);
        ui_button(v, T(HT_BTN_CHECK_AGAIN), W_CHECK, 0, 1);
        break;
    default:
        put(v->heading, sizeof v->heading, T(HT_GUIDE_DONE_TITLE));
        hf_text_fill(T(HT_GUIDE_DONE_STEP), app_edition()->name, text, sizeof text);
        put(v->state, sizeof v->state, text);
        v->tone = HF_TONE_GOOD;
        ui_button(v, T(HT_BTN_PLAY_NOW), W_PLAY, 1, 1);
        ui_button(v, T(HT_BTN_CHECK_AGAIN), W_CHECK, 0, 1);
        break;
    }
    ui_button(v, T(HT_BTN_BACK), W_BACK, 0, 1);
    v->selected = 0;
    put(v->footer, sizeof v->footer, app_edition()->name);
    ui_end();
}

static void checking(void) {
    HfView *v = ui_begin();
    put(v->state, sizeof v->state, T(HT_CHECKING));
    v->tone = HF_TONE_MUTED;
    v->busy = 1;
    ui_end();
    ui_work();   /* the drawing thread turns the spinner while the card is searched */
    status_gather();
}

int wizard_run(void) {
    UiEvent ev;
    HfSetupStep step;
    int id;
    LOG("guide: opened");
    for (;;) {
        step = current_step();
        LOG("guide: step %d", (int)step);
        page(step);
        for (;;) {
            if (!app_loop(&ev)) return 1;
            check_poll();   /* the start's answer, kept for the home page */
            if (ev.keys & KEY_START) return 0;
            id = ui_choose(&ev);
            if (id == W_BACK || id == UI_BACK) return 0;
            if (id == W_CHECK) {
                checking();
                break;
            }
            if (id == W_SKIP) {
                app.xx_skipped = 1;
                LOG("guide: MH XX skipped");
                break;
            }
            if (id == W_INSTALL) {
                if (update_run(0, 0)) return 1;
                break;
            }
            if (id == W_SAVE) {
                saves_copy_flow(0);
                break;
            }
            if (id == W_PLAY && start_edition() == 0) return 1;
        }
    }
}
