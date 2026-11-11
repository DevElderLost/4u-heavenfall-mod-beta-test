/* The launcher's log: sdmc:/3ds/heavenfall/<edition>/launcher.log, every
 * line stamped with the time since the app started, flushed at once so a cut leaves what happened. log_open and
 * log_close run only while the start's check thread is stopped (check_stop). */
#include <string.h>
#include <sys/stat.h>

#include "app.h"

uint64_t clock_ms(void) { return osGetTime(); }

/* ---- refused allocations: the Makefile links malloc, calloc, realloc and memalign through these (-Wl,--wrap) ---- */

AppRefused app_refused;

void *__real_malloc(size_t n);
void *__real_calloc(size_t a, size_t b);
void *__real_realloc(void *p, size_t n);
void *__real_memalign(size_t align, size_t n);

static void *noted(void *p, size_t n) {
    if (!p && n) {
        app_refused.count++;
        app_refused.last = n;
    }
    return p;
}

void *__wrap_malloc(size_t n) { return noted(__real_malloc(n), n); }
void *__wrap_calloc(size_t a, size_t b) { return noted(__real_calloc(a, b), a * b); }
void *__wrap_realloc(void *p, size_t n) { return noted(__real_realloc(p, n), n); }
void *__wrap_memalign(size_t align, size_t n) { return noted(__real_memalign(align, n), n); }

/* Lines come from the main thread and the start's check thread: one line at a time (zero is a valid, unlocked
 * LightLock). */
static LightLock sink_lock;

static void sink(void *ctx, const char *line) {
    FILE *f = (FILE *)ctx;
    LightLock_Lock(&sink_lock);
    fputs(line, f);
    fputc('\n', f);
    fflush(f);
    LightLock_Unlock(&sink_lock);
}

static const char *model_name(u8 model) {
    static const char *const names[] = {"Old 3DS", "Old 3DS XL", "New 3DS", "Old 2DS", "New 3DS XL", "New 2DS XL"};
    return model < 6 ? names[model] : "unknown model";
}

void log_open(void) {
    char dir[256], path[300];
    app.logf = NULL;
    memset(&app.log, 0, sizeof app.log);
    if (hf_path_dir(app_edition()->slug, dir, sizeof dir)) return;
    mkdir("sdmc:/3ds", 0777);
    mkdir("sdmc:/3ds/heavenfall", 0777);
    mkdir(dir, 0777);
    if (hf_path_log(app_edition()->slug, path, sizeof path)) return;
    app.logf = fopen(path, "ab");
    if (!app.logf) return;
    app.log.sink = sink;
    app.log.ctx = app.logf;
    app.log.start_ms = osGetTime();
    LOG("---- launcher %s%s, %s, %s, %s ----", HF_APP_VERSION, app.probe ? " PROBE" : "", app_edition()->name,
        model_name(app.model), app.is_3dsx ? "3dsx" : "cia");
    LOG("console: %s, clock speedup %s, system language %d", model_name(app.model),
        app.model >= 2 ? "available" : "not available", (int)app.lang);
}

void log_close(void) {
    if (!app.logf) return;
    LOG("---- closed ----");
    fclose(app.logf);
    app.logf = NULL;
    app.log.sink = NULL;
}
