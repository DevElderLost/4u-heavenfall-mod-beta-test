/* See uimodel.h. */
#include "uimodel.h"

#include <stdio.h>
#include <string.h>

#include "hfnet.h"
#include "json.h"
#include "release.h"
#include "settitle.h"
#include "title_io.h"
#include "uiview.h"

/* ---- the home screen ---- */

static void home(HfHome *h, HfText state, int detail, HfTone tone, HfDo primary, int can_play) {
    h->state = state;
    h->detail = detail;
    h->tone = tone;
    h->primary = primary;
    h->can_play = can_play;
}

static int unknown_version(const char *v) {
    uint32_t parts[HF_VERSION_PARTS];
    int count;
    return !v || hf_version_parse(v, parts, &count) != 0;
}

void hf_home(const HfHomeIn *in, HfHome *out) {
    memset(out, 0, sizeof *out);
    out->detail = -1;
    if (!in->title_installed) {
        switch (in->dump) {
        case HF_DUMP_FOUND: home(out, HT_HOME_NOT_INSTALLED, HT_HOME_INSTALL_HINT, HF_TONE_NEW, HF_DO_INSTALL, 0); break;
        case HF_DUMP_ENCRYPTED: home(out, HT_HOME_DUMP_ENCRYPTED, HT_HOME_SETUP_HINT, HF_TONE_WARN, HF_DO_SETUP, 0); break;
        case HF_DUMP_OTHER_REGION:
            home(out, HT_HOME_DUMP_OTHER_REGION, HT_HOME_SETUP_HINT, HF_TONE_WARN, HF_DO_SETUP, 0);
            break;
        default: home(out, HT_HOME_NEED_DUMP, HT_HOME_SETUP_HINT, HF_TONE_WARN, HF_DO_SETUP, 0); break;
        }
        return;
    }
    if (!in->installed_complete) {
        home(out, HT_HOME_REPAIR, -1, HF_TONE_WARN, HF_DO_UPDATE, 1);
        return;
    }
    if (in->game == HF_GAME_MISSING) {   /* the split title cannot start without it */
        home(out, HT_HOME_GAME_MISSING, HT_HOME_GAME_HINT, HF_TONE_WARN, HF_DO_UPDATE, 0);
        return;
    }
    if (in->game == HF_GAME_UPDATE) {
        home(out, HT_HOME_GAME_UPDATE, HT_HOME_GAME_HINT, HF_TONE_NEW, HF_DO_UPDATE, 1);
        return;
    }
    switch (in->check) {
    case HF_CHECK_DONE:
        if (in->latest && *in->latest &&
            (hf_version_newer(in->latest, in->installed ? in->installed : "") == 1 ||
             (unknown_version(in->installed) && !unknown_version(in->latest)))) {
            home(out, HT_HOME_NEW_VERSION, -1, HF_TONE_NEW, HF_DO_UPDATE, 1);
            out->new_version = 1;
        } else if (in->xx_came) {
            home(out, HT_HOME_XX_CAME, HT_HOME_XX_HINT, HF_TONE_NEW, HF_DO_UPDATE, 1);
        } else if (in->app_newer) {
            home(out, HT_HOME_APP_NEW, HT_HOME_APP_HINT, HF_TONE_NEW, HF_DO_UPDATE, 1);
        } else {
            home(out, HT_HOME_UP_TO_DATE, -1, HF_TONE_GOOD, HF_DO_PLAY, 1);
        }
        break;
    case HF_CHECK_FAILED: home(out, HT_HOME_CHECK_FAILED, -1, HF_TONE_MUTED, HF_DO_PLAY, 1); break;
    case HF_CHECK_NO_RELEASE: home(out, HT_HOME_CHECK_FAILED, HT_NO_RELEASE, HF_TONE_MUTED, HF_DO_PLAY, 1); break;
    default: home(out, HT_HOME_CHECKING, -1, HF_TONE_MUTED, HF_DO_PLAY, 1); break;
    }
}

/* ---- the first-run guide ---- */

HfSetupStep hf_setup_step(const HfSetupIn *in) {
    if (in->title_installed && !in->game_missing) return in->save_pending ? HF_SETUP_SAVE : HF_SETUP_DONE;
    if (in->dump == HF_DUMP_ENCRYPTED) return HF_SETUP_DECRYPT;
    if (in->dump != HF_DUMP_FOUND) return HF_SETUP_DUMP;
    if (in->xx != HF_XXD_FOUND && !in->xx_skipped) return HF_SETUP_XX;
    return HF_SETUP_INSTALL;
}

/* ---- the progress bar ---- */

#define FRAC_ONE 65536u

static uint32_t clamp_stage(HfStage s) { return (uint32_t)s < HF_STAGES ? (uint32_t)s : HF_STAGES - 1; }

/* The bar from the plan, the running step and its progress; held under the cap until the end. */
static void raise(HfProgress *p) {
    uint64_t total = 0, pos = 0;
    uint32_t s, cap = p->cap_permille < 1000 ? p->cap_permille : 999, raw;
    if (p->shown >= 1000) return;
    for (s = (uint32_t)p->plan_from; s < HF_STAGES; s++) {
        total += p->expect_ms[s];
        if (s < (uint32_t)p->stage) pos += p->expect_ms[s];
    }
    pos += (uint64_t)p->expect_ms[p->stage] * p->stage_frac / FRAC_ONE;
    raw = total ? p->base_permille + (uint32_t)((uint64_t)(1000 - p->base_permille) * pos / total) : p->base_permille;
    if (raw > cap) raw = cap;
    if (raw > p->shown) p->shown = raw;
}

void hf_progress_start(HfProgress *p, const uint32_t expect_ms[HF_STAGES], HfStage stage, uint32_t cap_permille,
                       uint64_t now_ms) {
    memset(p, 0, sizeof *p);
    memcpy(p->expect_ms, expect_ms, sizeof p->expect_ms);
    p->stage = p->plan_from = (HfStage)clamp_stage(stage);
    p->stage_began_ms = now_ms;
    p->cap_permille = cap_permille;
}

void hf_progress_update(HfProgress *p, HfStage stage, uint64_t done, uint64_t total, uint64_t now_ms) {
    uint32_t frac;
    stage = (HfStage)clamp_stage(stage);
    if (stage < p->stage) return;
    if (stage > p->stage) {
        p->stage = stage;
        p->stage_began_ms = now_ms;
        p->stage_frac = 0;
    }
    if (total) {
        frac = done >= total ? FRAC_ONE : (uint32_t)(done * FRAC_ONE / total);
    } else {
        uint64_t expect = p->expect_ms[stage], elapsed = now_ms > p->stage_began_ms ? now_ms - p->stage_began_ms : 0;
        frac = expect ? (uint32_t)(elapsed * FRAC_ONE / expect < FRAC_ONE - 1 ? elapsed * FRAC_ONE / expect : FRAC_ONE - 1)
                      : 0;
    }
    if (frac > p->stage_frac) p->stage_frac = frac;
    raise(p);
}

void hf_progress_replan(HfProgress *p, HfStage stage, const uint32_t expect_ms[HF_STAGES], uint64_t now_ms) {
    if (p->shown >= 1000) return;
    memcpy(p->expect_ms, expect_ms, sizeof p->expect_ms);
    p->base_permille = p->shown;
    p->plan_from = p->stage = (HfStage)clamp_stage(stage);
    p->stage_began_ms = now_ms;
    p->stage_frac = 0;
}

unsigned hf_progress_permille(const HfProgress *p) { return p->shown; }

void hf_progress_end(HfProgress *p) { p->shown = 1000; }

uint32_t hf_progress_eta_s(const HfProgress *p, uint64_t now_ms) {
    uint64_t ms, elapsed = now_ms > p->stage_began_ms ? now_ms - p->stage_began_ms : 0;
    uint32_t s, secs;
    if (p->shown >= 1000) return 0;
    if (p->stage_frac && elapsed)
        ms = elapsed * (FRAC_ONE - p->stage_frac) / p->stage_frac;
    else
        ms = (uint64_t)p->expect_ms[p->stage] * (FRAC_ONE - p->stage_frac) / FRAC_ONE;
    for (s = (uint32_t)p->stage + 1; s < HF_STAGES; s++) ms += p->expect_ms[s];
    secs = (uint32_t)((ms + 999) / 1000);
    return secs ? secs : 1;
}

int hf_stage_of_phase(HfText phase) {
    switch (phase) {
    case HT_PHASE_APP_DOWNLOAD:
    case HT_PHASE_SET_DOWNLOAD:
    case HT_PHASE_PROBE_DOWNLOAD:
    case HT_PHASE_SET_DOWNLOAD_XX: return HF_STAGE_DOWNLOAD;
    case HT_PHASE_OPEN:
    case HT_PHASE_OPEN_SIZING:
    case HT_PHASE_PREPARE:
    case HT_PHASE_HASH:
    case HT_PHASE_WRITE:
    case HT_PHASE_GAME_CHECK:
    case HT_PHASE_XX_FILES:
    case HT_PHASE_WRITE_2: return HF_STAGE_INSTALL;
    case HT_PHASE_AM:
    case HT_SAVE_RESTORING: return HF_STAGE_FINISH;   /* the save put back after the import (app_saves.c) */
    default: return -1;
    }
}

size_t hf_duration_text(uint32_t seconds, char *out, size_t cap) {
    int n;
    if (seconds < 60) {
        n = snprintf(out, cap, "%u s", (unsigned)seconds);
    } else {
        uint32_t minutes = (seconds + 59) / 60;
        if (minutes < 60) n = snprintf(out, cap, "%u min", (unsigned)minutes);
        else n = snprintf(out, cap, "%u h %02u min", (unsigned)(minutes / 60), (unsigned)(minutes % 60));
    }
    return n < 0 ? 0 : (size_t)n >= cap ? (cap ? cap - 1 : 0) : (size_t)n;
}

/* ---- the last install's times ---- */

/* v as decimal into the 21-byte buffer (no printf %llu: the C libraries of the host and the console differ). */
static const char *u64_text(uint64_t v, char buf[21]) {
    char *p = buf + 20;
    *p = 0;
    do {
        *--p = (char)('0' + v % 10);
        v /= 10;
    } while (v);
    return p;
}

int hf_timings_format(const HfTimings *t, char *out, size_t cap) {
    char b[8][21];
    int n = snprintf(out, cap, "{\"ms\": [%s, %s, %s], \"bytes\": [%s, %s, %s], \"game\": [%s, %s]}\n",
                     u64_text(t->ms[0], b[0]), u64_text(t->ms[1], b[1]), u64_text(t->ms[2], b[2]),
                     u64_text(t->bytes[0], b[3]), u64_text(t->bytes[1], b[4]), u64_text(t->bytes[2], b[5]),
                     u64_text(t->game_ms, b[6]), u64_text(t->game_bytes, b[7]));
    return n < 0 || (size_t)n >= cap ? -1 : n;
}

/* An array token of HF_STAGES unsigned numbers into out[]. */
static int three_numbers(const char *js, const JsonTok *toks, int arr, uint64_t out[HF_STAGES]) {
    int i, k = 0;
    if (arr < 0 || toks[arr].type != JT_ARRAY || toks[arr].size != HF_STAGES) return -1;
    for (i = arr + 1; i < toks[arr].next; i = toks[i].next)
        if (json_uint(js, &toks[i], &out[k++])) return -1;
    return 0;
}

int hf_timings_parse(const char *json, size_t len, HfTimings *out) {
    JsonTok toks[20];
    HfTimings t;
    int n = json_parse(json, len, toks, 20), g;
    memset(&t, 0, sizeof t);
    if (n < 1 || toks[0].type != JT_OBJECT) return -1;
    if (three_numbers(json, toks, json_find(json, toks, 0, "ms"), t.ms) ||
        three_numbers(json, toks, json_find(json, toks, 0, "bytes"), t.bytes))
        return -1;
    g = json_find(json, toks, 0, "game");   /* an older install's times have none */
    if (g >= 0 && (toks[g].type != JT_ARRAY || toks[g].size != 2 || json_uint(json, &toks[g + 1], &t.game_ms) ||
                   json_uint(json, &toks[g + 2], &t.game_bytes)))
        return -1;
    *out = t;
    return 0;
}

static uint32_t at_least_one(uint64_t ms) { return ms < 1 ? 1 : ms > 0xFFFFFFFFu ? 0xFFFFFFFFu : (uint32_t)ms; }

void hf_timings_expect(const HfTimings *last, const HfUiTuning *tu, const uint64_t bytes[HF_STAGES],
                       uint32_t expect_ms[HF_STAGES]) {
    uint64_t kib[2];
    int s;
    kib[0] = tu->download_kib_s ? tu->download_kib_s : 1;
    kib[1] = tu->install_kib_s ? tu->install_kib_s : 1;
    for (s = 0; s < 2; s++) {
        if (last && last->ms[s] && last->bytes[s])
            expect_ms[s] = at_least_one(bytes[s] * last->ms[s] / last->bytes[s]);
        else
            expect_ms[s] = at_least_one(bytes[s] * 1000 / (kib[s] * 1024));
    }
    expect_ms[HF_STAGE_FINISH] = at_least_one(last && last->ms[HF_STAGE_FINISH] ? last->ms[HF_STAGE_FINISH] : tu->finish_ms);
}

void hf_timings_expect_titles(const HfTimings *last, const HfUiTuning *tu, const uint64_t bytes[HF_STAGES],
                             uint64_t game_bytes, uint32_t expect_ms[HF_STAGES]) {
    uint64_t kib = tu->install_kib_s ? tu->install_kib_s : 1, game_ms;
    hf_timings_expect(last, tu, bytes, expect_ms);
    if (!game_bytes) return;
    if (last && last->game_ms && last->game_bytes) game_ms = game_bytes * last->game_ms / last->game_bytes;
    else game_ms = game_bytes * 1000 / (kib * 1024);
    expect_ms[HF_STAGE_INSTALL] = at_least_one((uint64_t)expect_ms[HF_STAGE_INSTALL] + game_ms);
}

/* ---- B to cancel, the screens' backlight, the battery ---- */

int hf_cancel_press(HfCancel *c, uint64_t now_ms, uint32_t window_ms) {
    if (hf_cancel_armed(c, now_ms, window_ms)) {
        c->armed = 0;
        return 1;
    }
    c->armed = 1;
    c->armed_ms = now_ms;
    return 0;
}

int hf_cancel_armed(const HfCancel *c, uint64_t now_ms, uint32_t window_ms) {
    return c->armed && (now_ms < c->armed_ms || now_ms - c->armed_ms <= window_ms);
}

int hf_backlight_should_dim(uint64_t last_input_ms, uint64_t now_ms, uint32_t idle_ms) {
    return idle_ms && now_ms > last_input_ms && now_ms - last_input_ms >= idle_ms;
}

int hf_battery_warn(int level, int adapter, int low_level) {
    return level >= 0 && level <= low_level && !adapter;
}

/* ---- the resume file ---- */

int hf_resume_format(const char *target_version, char *out, size_t cap) {
    const char *p;
    int n;
    for (p = target_version; *p; p++)
        if (*p == '"' || *p == '\\' || (unsigned char)*p < 0x20) return -1;
    n = snprintf(out, cap, "{\"target\": \"%s\"}\n", target_version);
    return n < 0 || (size_t)n >= cap ? -1 : n;
}

int hf_resume_parse(const char *json, size_t len, char *target, size_t cap) {
    JsonTok toks[8];
    int n = json_parse(json, len, toks, 8), t;
    if (n < 1 || toks[0].type != JT_OBJECT) return -1;
    t = json_find(json, toks, 0, "target");
    if (t < 0 || toks[t].type != JT_STRING || json_string(json, &toks[t], target, cap)) return -1;
    return 0;
}

int hf_resume_go(const char *target_version, const char *app_version) {
    return hf_version_newer(target_version, app_version) == 0 && hf_version_newer(app_version, target_version) == 0;
}

/* ---- room on the card ---- */

uint64_t hf_room_needed(uint64_t title_bytes, uint64_t spare) { return title_bytes + title_bytes / 100 + spare; }

uint32_t hf_room_missing_mb(uint64_t free_bytes, uint64_t title_bytes, uint64_t spare) {
    uint64_t needed = hf_room_needed(title_bytes, spare), mb;
    if (!free_bytes || free_bytes >= needed) return 0;
    mb = (needed - free_bytes + (1u << 20) - 1) >> 20;
    return mb > 0xFFFFFFFFu ? 0xFFFFFFFFu : (uint32_t)mb;
}

/* ---- why an update stopped, and what to do ---- */

HfFailKind hf_fail_kind(int rc, uint32_t am_result) {
    if (rc == TITLE_E_CANCEL || rc == HF_E_CANCEL) return HF_FAIL_CANCEL;
    if (rc == HF_E_DISK) return HF_FAIL_ROOM;
    if (rc == HF_E_NONE) return HF_FAIL_NO_RELEASE;
    if (rc == TITLE_E_MEM) return HF_FAIL_MEMORY;
    if (rc == TITLE_E_ENCRYPTED) return HF_FAIL_DUMP_ENCRYPTED;
    if (rc == TITLE_E_HASH || rc == TITLE_E_GAME || rc == TITLE_E_DAMAGED) return HF_FAIL_DUMP;
    if (rc == TITLE_E_IO) return HF_FAIL_SD;
    if (rc == TITLE_E_FORMAT || rc == HF_E_FORMAT) return HF_FAIL_SET;
    if (rc == HF_E_GAME_CHECK) return HF_FAIL_GAME_CHECK;
    if (rc == HF_E_SAVE_BACKUP) return HF_FAIL_SAVE_BACKUP;
    if (rc == HF_E_AM_WRITE || am_result) return HF_FAIL_SYSTEM;
    if (rc <= HF_E_NETWORK && rc > HF_E_DISK) return HF_FAIL_NET;
    return HF_FAIL_OTHER;
}

void hf_failure_advice(HfFailKind kind, HfAdvice *out) {
    out->todo = -1;
    out->show_code = 0;
    switch (kind) {
    case HF_FAIL_CANCEL: out->what = HT_CANCELLED; break;
    case HF_FAIL_ROOM: out->what = HT_NO_ROOM; out->todo = HT_TODO_ROOM; break;
    case HF_FAIL_NET: out->what = HT_NO_NET; out->todo = HT_TODO_NET; break;
    case HF_FAIL_NO_RELEASE: out->what = HT_NO_RELEASE; break;
    case HF_FAIL_NEEDS_APP: out->what = HT_NEEDS_APP; break;
    case HF_FAIL_NO_SET: out->what = HT_NO_SET; break;
    case HF_FAIL_DUMP_MISSING: out->what = HT_NO_DUMP; out->todo = HT_TODO_DUMP; break;
    case HF_FAIL_DUMP_ENCRYPTED: out->what = HT_HOME_DUMP_ENCRYPTED; out->todo = HT_TODO_DUMP; break;
    case HF_FAIL_DUMP: out->what = HT_FAIL_DUMP; out->todo = HT_TODO_DUMP; break;
    case HF_FAIL_MEMORY: out->what = HT_FAIL_MEMORY; out->todo = HT_TODO_RESTART; out->show_code = 1; break;
    case HF_FAIL_SD: out->what = HT_FAIL_SD; out->todo = HT_TODO_RETRY; out->show_code = 1; break;
    case HF_FAIL_SET: out->what = HT_FAIL_SET; out->todo = HT_TODO_RETRY; out->show_code = 1; break;
    case HF_FAIL_SYSTEM: out->what = HT_FAIL_AM; out->todo = HT_TODO_RESTART; out->show_code = 1; break;
    case HF_FAIL_GAME_CHECK: out->what = HT_FAIL_GAME_CHECK; out->show_code = 1; break;
    case HF_FAIL_SAVE_BACKUP: out->what = HT_FAIL_SAVE_BACKUP; out->todo = HT_TODO_RETRY; out->show_code = 1; break;
    default: out->what = HT_FAIL_OTHER; out->todo = HT_TODO_RETRY; out->show_code = 1; break;
    }
}

int hf_stop_note(HfFailKind kind, int had_title, int old_removed) {
    if (old_removed) return HT_OLD_REMOVED;
    return had_title && kind != HF_FAIL_CANCEL ? (int)HT_NOTHING_INSTALLED : -1;
}

size_t hf_text_fill(const char *text, const char *value, char *out, size_t cap) {
    const char *hole = strstr(text, "{}");
    size_t o = 0;
    if (!cap) return 0;
    for (; *text && o + 1 < cap;) {
        if (text == hole) {
            const char *v;
            for (v = value; *v && o + 1 < cap; v++) out[o++] = *v;
            text += 2;
            hole = NULL;
        } else {
            out[o++] = *text++;
        }
    }
    out[o] = 0;
    return o;
}

/* ---- the release's notes ---- */

typedef struct {
    char *buf;
    size_t len, cap;
} Line;

static void put_ch(Line *l, char c) {
    if (c == ' ' && (!l->len || l->buf[l->len - 1] == ' ')) return;
    if (l->len + 1 < l->cap) l->buf[l->len++] = c;
}

/* One letter of the notes: Latin-1 as UTF-8, the dashes and quotes as ASCII, the rest (emoji, CJK, joiners) dropped. */
static void put_cp(Line *l, unsigned cp) {
    if (cp == 0xA0) cp = ' ';
    else if (cp == 0x2013 || cp == 0x2014 || cp == 0x2212) cp = '-';
    else if (cp == 0x2018 || cp == 0x2019) cp = '\'';
    else if (cp == 0x201C || cp == 0x201D) cp = '"';
    if (cp < 0x20 && cp != '\t') return;
    if (cp == '\t') cp = ' ';
    if (cp < 0x80) {
        put_ch(l, (char)cp);
    } else if (cp >= 0xA1 && cp < 0x100 && cp != 0xAD && l->len + 2 < l->cap) {
        l->buf[l->len++] = (char)(0xC0 | cp >> 6);
        l->buf[l->len++] = (char)(0x80 | (cp & 0x3F));
    }
}

/* The code point at s (n bytes left) and its length; an invalid byte is length 1 and 0xFFFF (dropped). */
static unsigned next_cp(const unsigned char *s, size_t n, int *len) {
    unsigned c = s[0];
    int need = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0, k;
    *len = 1;
    if (c < 0x80) return c;
    if (c < 0xC0 || (size_t)need >= n) return 0xFFFF;
    c &= need == 3 ? 0x07 : need == 2 ? 0x0F : 0x1F;
    for (k = 1; k <= need; k++) {
        if ((s[k] & 0xC0) != 0x80) return 0xFFFF;
        c = c << 6 | (s[k] & 0x3F);
    }
    *len = need + 1;
    return c;
}

static int alnum(char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'); }

static int starts(const char *s, size_t n, const char *prefix) {
    size_t k = strlen(prefix);
    return n >= k && !strncmp(s, prefix, k);
}

/* Inline marks of s[0..n) into the line. */
static void inline_text(Line *l, const char *s, size_t n) {
    size_t i = 0;
    while (i < n) {
        char c = s[i];
        if ((c == '!' && i + 1 < n && s[i + 1] == '[') || c == '[') {
            size_t b = c == '!' ? i + 1 : i, close = b + 1;
            while (close < n && s[close] != ']') close++;
            if (close + 1 < n && s[close] == ']' && s[close + 1] == '(') {
                size_t end = close + 2;
                while (end < n && s[end] != ')') end++;
                if (end < n) {
                    if (c == '[') inline_text(l, s + b + 1, close - b - 1);
                    i = end + 1;
                    continue;
                }
            }
        }
        if (c == 'h' && (i == 0 || !alnum(s[i - 1])) && (starts(s + i, n - i, "http://") || starts(s + i, n - i, "https://"))) {
            while (i < n && s[i] != ' ' && s[i] != '\t') i++;
            continue;
        }
        if (c == '`' || c == '*' || (c == '~' && i + 1 < n && s[i + 1] == '~')) {
            i += c == '~' ? 2 : 1;
            continue;
        }
        if (c == '_' && (i == 0 || !alnum(s[i - 1]) || i + 1 >= n || !alnum(s[i + 1]))) {
            i++;
            continue;
        }
        if (c == '\\' && i + 1 < n && s[i + 1] > ' ' && s[i + 1] < 0x7F && !alnum(s[i + 1])) {
            put_ch(l, s[i + 1]);
            i += 2;
            continue;
        }
        {
            int len;
            unsigned cp = next_cp((const unsigned char *)s + i, n - i, &len);
            if (cp != 0xFFFF) put_cp(l, cp);
            i += (size_t)len;
        }
    }
}

/* A line of three or more of the same -, * or _ (with spaces): a rule. */
static int is_rule(const char *s, size_t n) {
    size_t i, marks = 0;
    char m = 0;
    for (i = 0; i < n; i++) {
        if (s[i] == ' ') continue;
        if (s[i] != '-' && s[i] != '*' && s[i] != '_') return 0;
        if (m && s[i] != m) return 0;
        m = s[i];
        marks++;
    }
    return marks >= 3;
}

/* "- " in front of a list item's text. A full line first loses its last letters (whole ones), so the two bytes never go
 * past the buffer: put_ch and put_cp leave the line at most cap - 1 long. */
static void prefix_dash(Line *l) {
    if (!l->len) return;
    while (l->len && l->len + 3 > l->cap) {
        l->len--;
        while (l->len && ((unsigned char)l->buf[l->len] & 0xC0) == 0x80) l->len--;
    }
    memmove(l->buf + 2, l->buf, l->len);
    l->buf[0] = '-';
    l->buf[1] = ' ';
    l->len += 2;
}

/* The markdown line s[0..n) as one plain line into l. */
static void plain_line(Line *l, const char *s, size_t n) {
    size_t i = 0, d;
    while (i < n && (s[i] == ' ' || s[i] == '\t')) i++;
    if (is_rule(s + i, n - i) || (i < n && s[i] == '|')) return;
    while (i < n && s[i] == '>') {
        i++;
        while (i < n && s[i] == ' ') i++;
    }
    for (d = i; d < n && s[d] == '#'; d++) {}
    if (d > i && d - i <= 6 && d < n && s[d] == ' ') {
        inline_text(l, s + d + 1, n - d - 1);
    } else if (i + 1 < n && (s[i] == '-' || s[i] == '*' || s[i] == '+') && s[i + 1] == ' ') {
        inline_text(l, s + i + 2, n - i - 2);
        prefix_dash(l);
    } else {
        for (d = i; d < n && s[d] >= '0' && s[d] <= '9'; d++) {}
        if (d > i && d + 1 < n && (s[d] == '.' || s[d] == ')') && s[d + 1] == ' ') {
            inline_text(l, s + d + 2, n - d - 2);
            prefix_dash(l);
        } else {
            inline_text(l, s + i, n - i);
        }
    }
    while (l->len && l->buf[l->len - 1] == ' ') l->len--;
}

/* A markdown heading's level (its #s before a space), 0 for any other line. */
static int heading_level(const char *s, size_t n) {
    size_t d = 0;
    while (d < n && s[d] == '#') d++;
    return d && d <= 6 && d < n && s[d] == ' ' ? (int)d : 0;
}

/* A line (heading or item) the changelog marks as not for a console: it ends "(emulator only)" or "(PC only)", a
 * full stop after it allowed. */
static int not_for_console(const char *s, size_t n) {
    static const char *const MARKS[] = {"(emulator only)", "(PC only)"};
    size_t k;
    while (n && (s[n - 1] == ' ' || s[n - 1] == '.' || s[n - 1] == '\t')) n--;
    for (k = 0; k < sizeof MARKS / sizeof MARKS[0]; k++) {
        size_t m = strlen(MARKS[k]);
        if (n >= m && !strncmp(s + n - m, MARKS[k], m)) return 1;
    }
    return 0;
}

/* One plain line into out after the ones there ('\n' between; a blank line first when `gap`). 0 when it does not fit. */
static int put_line(char *out, size_t cap, size_t *o, int *lines, int *gap, const char *s, size_t n) {
    size_t need = (size_t)(*gap ? 1 : 0) + (*lines ? 1 : 0) + n;
    if (*o + need + 1 > cap) return 0;
    if (*gap) {
        out[(*o)++] = '\n';
        (*lines)++;
    }
    if (*lines) out[(*o)++] = '\n';
    memcpy(out + *o, s, n);
    *o += n;
    out[*o] = 0;
    (*lines)++;
    *gap = 0;
    return 1;
}

int hf_notes_plain(const char *markdown, char *out, size_t cap) {
    char tmp[1024], head[256];
    size_t o = 0, head_len = 0;
    int lines = 0, pending = 0, fence = 0, skip_level = 0, head_level = 0, head_gap = 0;
    const char *p = markdown;
    if (!cap) return 0;
    out[0] = 0;
    while (*p) {
        const char *end = strchr(p, '\n');
        size_t n = end ? (size_t)(end - p) : strlen(p);
        Line l;
        const char *t = p;
        size_t tn = n;
        int level;
        p += n + (end ? 1 : 0);
        if (tn && t[tn - 1] == '\r') tn--;
        while (tn && *t == ' ') { t++; tn--; }
        if (tn >= 3 && !strncmp(t, "```", 3)) {
            fence = !fence;
            continue;
        }
        level = fence ? 0 : heading_level(t, tn);
        if (skip_level) {   /* a section marked not for a console, until a heading as high as its own */
            if (!level || level > skip_level) continue;
            skip_level = 0;
        }
        if (!fence && not_for_console(t, tn)) {
            if (level) skip_level = level;
            continue;
        }
        l.buf = tmp;
        l.len = 0;
        l.cap = sizeof tmp;
        if (fence) inline_text(&l, t, tn);
        else plain_line(&l, t, tn);
        while (l.len && l.buf[l.len - 1] == ' ') l.len--;
        if (!l.len) {
            if (lines || head_len) pending = 1;
            continue;
        }
        if (level) {   /* a heading waits for its first line: a section left empty shows no heading */
            if (head_len && head_level < level && !put_line(out, cap, &o, &lines, &head_gap, head, head_len)) break;
            head_len = l.len < sizeof head ? l.len : sizeof head - 1;
            while (head_len && head_len < l.len && ((unsigned char)l.buf[head_len] & 0xC0) == 0x80) head_len--;
            memcpy(head, l.buf, head_len);
            head_level = level;
            head_gap = pending && lines;
            pending = 0;
            continue;
        }
        if (head_len) {   /* the blank line between the heading and this one (pending) stays */
            if (!put_line(out, cap, &o, &lines, &head_gap, head, head_len)) break;
            head_len = 0;
        }
        if (!put_line(out, cap, &o, &lines, &pending, l.buf, l.len)) break;
    }
    return lines;
}
