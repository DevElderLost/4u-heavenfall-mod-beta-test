/* See updplan.h. */
#include "updplan.h"

#include <string.h>

#include "release.h"

#define SET_MAGIC "HFPS"
#define SET_FORMAT_XX 2u    /* the first format with a second game (MH XX) */

static int same_version(const HfPlanIn *in) {
    return in->mod_version && hf_version_newer(in->release_tag, in->mod_version) == 0;
}

int hf_xx_came(const HfPlanIn *in) {
    if (!in->mod_version || in->mod_xx || !in->xx_dump || !in->xx_set_in_release) return 0;
    return !(same_version(in) && (in->xx_no_room || in->xx_tried));
}

void hf_plan(const HfPlanIn *in, HfPlan *out) {
    int app_newer, mod_needed, blocked, xx, set_in, game_needed;
    unsigned format;
    memset(out, 0, sizeof *out);
    xx = in->xx_dump && in->xx_set_in_release && in->xx_set_matches;
    out->xx_why = !in->xx_dump ? HF_XX_NO_DUMP : !in->xx_set_in_release ? HF_XX_NOT_IN_RELEASE
                : !in->xx_set_matches ? HF_XX_OTHER_VERSION : HF_XX_USED;
    if (xx && in->xx_no_room && same_version(in)) {
        xx = 0;     /* this version's XX set did not fit: its plain title stays until a new version */
        out->xx_why = HF_XX_NO_ROOM;
    }
    out->use_xx = xx;
    set_in = xx ? 1 : in->set_in_release;
    format = xx ? in->xx_set_format : in->set_format;
    app_newer = hf_version_newer(in->app_tag ? in->app_tag : in->release_tag, in->app_version);
    if (app_newer < 0 || hf_version_newer(in->release_tag, in->app_version) < 0) {
        out->status = HF_PLAN_BAD_TAG;
        return;
    }
    if (in->mod_version == NULL || in->mod_incomplete)
        mod_needed = 1;
    else    /* a version not understood: rebuild; MH XX coming (another printing: its files compared) or going: rebuild */
        mod_needed = hf_version_newer(in->release_tag, in->mod_version) != 0 || !in->mod_xx != !xx || hf_xx_came(in);
    /* the split title: the game data is made again when it is missing, cut or of another dump (the old single title
     * has none: its record names none); the mod always follows it, and the old single title is rebuilt as the mod */
    game_needed = in->game_stale;
    mod_needed = mod_needed || game_needed || in->mod_layout == 1 || in->reinstall;
    app_newer = app_newer && in->app_in_release;
    blocked = mod_needed && set_in && format > in->supported_format;
    if (app_newer)
        out->steps[out->count++] = HF_STEP_APP;
    if (mod_needed && !set_in) {
        if (!out->count)
            out->status = HF_PLAN_NO_SET;
        else
            out->status = HF_PLAN_STEPS;
        return;
    }
    if (blocked) {
        if (!app_newer) {
            out->status = HF_PLAN_NEEDS_APP;
            return;
        }
        out->mod_after_restart = 1;
    } else if (mod_needed) {
        if (game_needed)
            out->steps[out->count++] = HF_STEP_GAME;
        out->steps[out->count++] = HF_STEP_MOD;
    }
    out->status = out->count ? HF_PLAN_STEPS : HF_PLAN_UP_TO_DATE;
}

int hf_plan_on_without_app(const HfPlan *plan) {
    int i;
    if (plan->mod_after_restart)
        return 0;
    for (i = 0; i < plan->count; i++)
        if (plan->steps[i] != HF_STEP_APP)
            return 1;
    return 0;
}

int hf_plan_drop_xx(const HfPlanIn *in, HfPlan *plan) {
    if (!plan->use_xx || !in->set_in_release || in->set_format > in->supported_format)
        return 0;
    plan->use_xx = 0;
    plan->xx_why = HF_XX_NO_ROOM;
    return 1;
}

int hf_set_names_game(const uint8_t *head, size_t len, const uint8_t romfs_hash[32]) {
    size_t at;
    uint32_t format;
    if (!head || len < 8 + 32 || memcmp(head, SET_MAGIC, 4)) return 0;
    format = (uint32_t)head[4] | (uint32_t)head[5] << 8 | (uint32_t)head[6] << 16 | (uint32_t)head[7] << 24;
    if (format < SET_FORMAT_XX) return 0;
    for (at = 8; at + 32 <= len; at++)
        if (!memcmp(head + at, romfs_hash, 32)) return 1;
    return 0;
}
