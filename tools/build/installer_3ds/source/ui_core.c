/* The drawing, the view's lock, the event queue, the APT hook and the screens' backlight (ui.h).
 *
 * Who draws (as FBI and Universal-Updater do): the main thread, in its aptMainLoop loop (app_loop), so HOME, the power
 * button and sleep find no other thread on the GPU when libctru and citro3d hand it over. While the main thread blocks
 * in long work (ui_work: an install, a download, a save copy) a drawing thread draws and reads the buttons instead, and
 * HOME is refused; a suspend or a sleep meanwhile (the power button, the lid) stops it with a bounded join in the APT
 * hook, before the handover, and ui_apt starts it again after. The next interactive loop stops it and allows HOME.
 *
 * Locks: `view_lock` guards the shared view and is held only to change or copy it; `gpu_lock` is held over one step
 * (the buttons read, a frame drawn) by whichever thread draws. `lcd_lock` guards the backlight's state. None is taken
 * while another is held, except `lcd_lock` and `view_lock` inside `gpu_lock`. */
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#include "app.h"
#include "hf_tuning.h"
#include "ui_draw.h"

/* Written before citro3d starts, deleted once the graphics drew HF_TUNE_SAFE_MODE_FRAMES frames: found at the next
 * start, it means that start's graphics never drew, and the simple display is used. It holds the app's version: an
 * updated app tries the graphics again, and so does a start with R held (it deletes the marker). */
#define DISPLAY_CHECK_FILE "sdmc:/3ds/heavenfall/display_check"
#define QUEUE 16
#define DRAW_STACK (32 * 1024)
#define HANDOVER_JOIN_NS (1000ULL * 1000000ULL)   /* the drawing thread's step is one frame: a second is plenty */
#define WATCH_STACK (64 * 1024)   /* LOG formats on the stack: about 31 KB, with the libraries' reserve */
#define WATCH_LINES 15
#define SPIN_MS 125                  /* the spinner's step */
#define DPAD (KEY_DUP | KEY_DDOWN | KEY_DLEFT | KEY_DRIGHT)

static HfView shared;                /* the main thread's (under view_lock) */
static HfView shown;                 /* the drawing thread's copy, last drawn: a touch reads its layout */
static int have_shown;
static LightLock view_lock, gpu_lock, lcd_lock, queue_lock;
static LightEvent queue_event;
static UiEvent queue[QUEUE];
static int queue_head, queue_count;

static Thread drawer;
static volatile int drawer_run;
static int working;                  /* ui_work .. the next interactive loop: the drawing thread draws, HOME is refused */
static int apt_stopped;              /* the APT hook stopped the drawing thread: ui_apt starts it again */
static int drawer_logged;
static volatile int resumed;         /* back from a suspend or sleep: the next read of the buttons is dropped */
static volatile int force;           /* draw the next frame even if the view did not change */
static volatile int screens_on = 1;
static volatile u64 last_input;
static int simple, lcd_ok, marker;
static int up;                       /* ui_init ran and ui_exit not yet: nothing is drawn after ui_exit */
static unsigned good_frames, drawn_tick;
static u64 last_frame;
static aptHookCookie hook_cookie, late_cookie;
static Thread watcher;
static volatile int watch_run;

/* ---- the backlight ---- */

/* gsp::Lcd opened only around each change, as ftpd does: a session held from the start kept the system waiting when
 * HOME handed the screens over (the console froze after citro3d's hook, with no other thread drawing). */
static int lcd_power(int on) {
    if (R_FAILED(gspLcdInit())) return 0;
    if (on) GSPLCD_PowerOnBacklight(GSPLCD_SCREEN_BOTH);
    else GSPLCD_PowerOffBacklight(GSPLCD_SCREEN_BOTH);
    gspLcdExit();
    return 1;
}

static void backlight(int on) {
    LightLock_Lock(&lcd_lock);
    if (lcd_ok && on != screens_on && lcd_power(on)) {
        screens_on = on;
        if (on) force = 1;
    }
    LightLock_Unlock(&lcd_lock);
}

void ui_screens(int on) { backlight(on); }
int ui_screens_on(void) { return screens_on; }
u64 ui_last_input_ms(void) { return last_input; }
int ui_simple(void) { return simple; }

/* ---- the event queue ---- */

static void queue_push(const UiEvent *ev) {
    LightLock_Lock(&queue_lock);
    if (queue_count == QUEUE) {          /* the oldest goes */
        queue_head = (queue_head + 1) % QUEUE;
        queue_count--;
    }
    queue[(queue_head + queue_count++) % QUEUE] = *ev;
    LightLock_Unlock(&queue_lock);
    LightEvent_Signal(&queue_event);
}

static void step(void);

int ui_next_event(UiEvent *ev) {
    int got = 0;
    if (!drawer && up) step();   /* no drawing thread: the caller's loop draws (the main thread, as in FBI) */
    LightLock_Lock(&queue_lock);
    if (queue_count) {
        *ev = queue[queue_head];
        queue_head = (queue_head + 1) % QUEUE;
        queue_count--;
        got = 1;
    }
    LightLock_Unlock(&queue_lock);
    if (!got) {
        ev->keys = 0;
        ev->button = -1;
        ev->ms = 0;
    }
    return got;
}

int ui_wait_event(UiEvent *ev, u32 timeout_ms) {
    if (ui_next_event(ev)) return 1;
    if (drawer) LightEvent_WaitTimeout(&queue_event, (s64)timeout_ms * 1000000LL);
    else svcSleepThread((s64)timeout_ms * 1000000LL);
    return ui_next_event(ev);
}

void ui_flush_events(void) {
    LightLock_Lock(&queue_lock);
    queue_count = 0;
    LightLock_Unlock(&queue_lock);
    LightEvent_Clear(&queue_event);
}

/* ---- the drawing thread ---- */

static void read_buttons(void) {
    UiEvent ev;
    u32 down;
    hidScanInput();
    down = hidKeysDown() | (hidKeysDownRepeat() & DPAD);
    if (resumed) {                       /* what was held through the HOME Menu is no press */
        resumed = 0;
        force = 1;
        return;
    }
    if (!down) return;
    last_input = osGetTime();
    if (!screens_on) {                   /* a key on dark screens only wakes them */
        backlight(1);
        return;
    }
    ev.keys = down;
    ev.button = -1;
    ev.ms = last_input;
    if ((down & KEY_TOUCH) && have_shown) {
        touchPosition t;
        hidTouchRead(&t);
        ev.button = simple ? console_touch(&shown, t.px, t.py) : gpu_touch(&shown, t.px, t.py);
    }
    queue_push(&ev);
}

static void frame(void) {
    u64 now = osGetTime();
    unsigned fps = shown.screen == HF_SCREEN_TASK ? HF_TUNE_FPS_TASK : HF_TUNE_FPS_MENU, tick;
    int changed;
    if (!screens_on || (fps && now - last_frame < 1000u / fps)) return;
    LightLock_Lock(&view_lock);
    changed = !have_shown || shared.serial != shown.serial;
    if (changed) memcpy(&shown, &shared, sizeof shown);
    LightLock_Unlock(&view_lock);
    have_shown = 1;
    tick = shown.busy ? (unsigned)(now / SPIN_MS) : 0;
    if (!changed && !force && tick == drawn_tick && (simple || good_frames >= HF_TUNE_SAFE_MODE_FRAMES)) return;
    force = 0;
    if (simple) {
        console_draw(&shown, tick, hf_text(app.lang, HT_SIMPLE_DISPLAY));
    } else {
        gpu_draw(&shown, tick);
        if (good_frames < HF_TUNE_SAFE_MODE_FRAMES && ++good_frames == HF_TUNE_SAFE_MODE_FRAMES && marker) {
            remove(DISPLAY_CHECK_FILE);
            marker = 0;
        }
    }
    last_frame = now;
    drawn_tick = tick;
}

/* One step: the buttons read, a frame drawn when it is due. */
static void step(void) {
    LightLock_Lock(&gpu_lock);
    read_buttons();
    frame();
    LightLock_Unlock(&gpu_lock);
}

static void draw_main(void *arg) {
    (void)arg;
    while (drawer_run) {
        svcSleepThread(1000000000LL / HF_TUNE_INPUT_HZ);
        if (drawer_run) step();
    }
}

/* The drawing thread asked to end and joined, at most `timeout_ns`: 1 when it is gone. One that does not end in time is
 * left (asked to end: it does at its next step) and freed at the next start. */
static int drawer_stop(u64 timeout_ns) {
    if (!drawer) return 1;
    drawer_run = 0;
    if (R_DESCRIPTION(threadJoin(drawer, timeout_ns)) == RD_TIMEOUT) {
        LOG("display: the drawing thread did not end within %lu ms", (unsigned long)(timeout_ns / 1000000ULL));
        return 0;
    }
    threadFree(drawer);
    drawer = NULL;
    return 1;
}

/* New 3DS: core 2; Old 3DS: core 0; at the main thread's priority - 1. None: the main thread draws in its calls. */
static void drawer_start(void) {
    s32 prio = 0x30;
    bool n3ds = false;
    int core = 2;
    if (drawer && !drawer_stop(0)) return;   /* an earlier one has not ended yet */
    svcGetThreadPriority(&prio, CUR_THREAD_HANDLE);
    APT_CheckNew3DS(&n3ds);
    drawer_run = 1;
    drawer = n3ds ? threadCreate(draw_main, NULL, DRAW_STACK, prio - 1, 2, false) : NULL;
    if (!drawer) {
        core = 0;
        drawer = threadCreate(draw_main, NULL, DRAW_STACK, prio - 1, 0, false);
    }
    if (drawer_logged) return;
    drawer_logged = 1;
    if (drawer) LOG("display: the drawing thread for long work on core %d, priority 0x%lX", core, (unsigned long)(prio - 1));
    else LOG("display: no drawing thread: the main thread draws in its loops and progress calls");
}

/* An interactive loop: the main thread draws, and HOME is allowed. */
static void interactive(void) {
    if (!working) return;
    working = 0;
    drawer_stop(HANDOVER_JOIN_NS);
    aptSetHomeAllowed(true);
}

void ui_work(void) {
    if (working || !up) return;
    working = 1;
    aptSetHomeAllowed(false);
    drawer_start();
}

/* ---- the main thread's side ---- */

HfView *ui_begin(void) {
    LightLock_Lock(&view_lock);
    return &shared;
}

void ui_end(void) {
    shared.serial++;
    LightLock_Unlock(&view_lock);
}

int ui_apt(void) {
    int run = aptMainLoop();
    if (apt_stopped) {
        apt_stopped = 0;
        if (run && working && up) drawer_start();
    }
    return run;
}

int app_loop(UiEvent *ev) {
    interactive();
    if (!ui_apt()) {
        ev->keys = 0;
        ev->button = -1;
        return 0;
    }
    ui_wait_event(ev, 1000u / HF_TUNE_INPUT_HZ);
    return 1;
}

/* A probe's watch over a suspend or a sleep: a line a second (at most WATCH_LINES), so when the screens freeze the log
 * says whether this process still ran (the system waiting for something) or nothing did. Never on the GPU. */
static void watch_main(void *arg) {
    u64 began = osGetTime();
    int i;
    (void)arg;
    for (i = 0; i < WATCH_LINES && watch_run; i++) {
        svcSleepThread(1000000000LL);
        if (watch_run) LOG("apt: still away, %lu ms", (unsigned long)(osGetTime() - began));
    }
}

static void watch_start(void) {
    if (!app.probe || watcher) return;
    watch_run = 1;
    watcher = threadCreate(watch_main, NULL, WATCH_STACK, 0x3F, 0, false);
}

static void watch_stop(void) {
    if (!watcher) return;
    watch_run = 0;
    if (R_DESCRIPTION(threadJoin(watcher, 2 * HANDOVER_JOIN_NS)) == RD_TIMEOUT) return;   /* it ends by itself */
    threadFree(watcher);
    watcher = NULL;
}

/* Runs inside aptMainLoop on the main thread, before citro3d's own hook (aptHook puts the newest first): the screens on
 * (HOME and the power menu must show), and before a suspend or a sleep the drawing thread, if long work runs it, ended:
 * the GPU is handed over with no other thread on it. Each step is logged: a freeze there says where it stopped. */
static void apt_hook(APT_HookType hook, void *param) {
    (void)param;
    if (hook == APTHOOK_ONSUSPEND || hook == APTHOOK_ONSLEEP || hook == APTHOOK_ONEXIT) backlight(1);
    if (hook == APTHOOK_ONSUSPEND || hook == APTHOOK_ONSLEEP) {
        int had = drawer != NULL;
        if (had) apt_stopped = 1;
        LOG("apt: %s; the drawing thread %s", hook == APTHOOK_ONSUSPEND ? "to the HOME Menu" : "to sleep",
            !had ? "is not running" : drawer_stop(HANDOVER_JOIN_NS) ? "ended" : "did not end");
        watch_start();
    } else if (hook == APTHOOK_ONRESTORE || hook == APTHOOK_ONWAKEUP) {
        watch_stop();
        resumed = 1;
        force = 1;
        LOG("apt: back from %s", hook == APTHOOK_ONRESTORE ? "the HOME Menu" : "sleep");
    } else if (hook == APTHOOK_ONEXIT) {
        watch_stop();
        LOG("apt: asked to close");
    }
}

/* Registered before citro3d starts, so it runs after citro3d's own hook: the log says that one ended too. */
static void apt_late(APT_HookType hook, void *param) {
    (void)param;
    if (hook == APTHOOK_ONSUSPEND || hook == APTHOOK_ONSLEEP) LOG("apt: citro3d's hook done, the GPU is handed over");
}

/* ---- the start's choice ---- */

/* 1 when the marker of a start whose graphics never drew is there for this version (it stays: the graphics are not
 * tried again until the app is updated); a marker of another version goes. */
static int marker_found(void) {
    char text[32] = "";
    FILE *f = fopen(DISPLAY_CHECK_FILE, "rb");
    size_t n;
    if (!f) return 0;
    n = fread(text, 1, sizeof text - 1, f);
    fclose(f);
    text[n] = 0;
    if (!strcmp(text, HF_APP_VERSION)) return 1;
    remove(DISPLAY_CHECK_FILE);
    return 0;
}

static void marker_write(void) {
    FILE *f;
    mkdir("sdmc:/3ds", 0777);
    mkdir("sdmc:/3ds/heavenfall", 0777);
    f = fopen(DISPLAY_CHECK_FILE, "wb");
    if (!f) return;
    fputs(HF_APP_VERSION, f);
    marker = fclose(f) == 0;
}

void ui_init(void) {
    char why[96] = "";
    u32 held;
    LightLock_Init(&view_lock);
    LightLock_Init(&gpu_lock);
    LightLock_Init(&lcd_lock);
    LightLock_Init(&queue_lock);
    LightEvent_Init(&queue_event, RESET_ONESHOT);
    aptHook(&late_cookie, apt_late, NULL);   /* before citro3d's: it runs after it */
    memset(&shared, 0, sizeof shared);
    shared.task.stage = HF_STAGES;
    shared.selected = -1;
    last_input = osGetTime();
    lcd_ok = R_SUCCEEDED(gspLcdInit());   /* only a look: is it there (each change opens it again) */
    if (lcd_ok) gspLcdExit();
    hidScanInput();
    held = hidKeysHeld();
    if (held & KEY_SELECT) {
        simple = 1;
        snprintf(why, sizeof why, "SELECT held at the start");
    } else if (!(held & KEY_R) && marker_found()) {
        simple = 1;
        snprintf(why, sizeof why, "the last start's graphics never drew (%s)", DISPLAY_CHECK_FILE);
    } else {
        if (held & KEY_R) {   /* the safe mode's way out: the marker goes and the graphics are tried again */
            remove(DISPLAY_CHECK_FILE);
            snprintf(why, sizeof why, "R held at the start: the marker cleared");
        }
        marker_write();
        if (gpu_init(why, sizeof why)) {
            simple = 1;
            if (marker) remove(DISPLAY_CHECK_FILE);
            marker = 0;
        }
    }
    if (simple) console_init();
    LOG("display: %s%s%s; backlight control %d", simple ? "simple" : "graphic", why[0] ? ", " : "", why, lcd_ok);
    aptHook(&hook_cookie, apt_hook, NULL);
    up = 1;
    ui_work();   /* the start gathers the status: the drawing thread draws meanwhile */
}

/* Once: a title's start closes the layer before its jump, and the app's end calls it again. */
void ui_exit(void) {
    if (!up) return;
    up = 0;
    backlight(1);
    drawer_stop(2 * HANDOVER_JOIN_NS);
    watch_stop();
    working = 0;
    aptSetHomeAllowed(true);
    aptUnhook(&hook_cookie);
    aptUnhook(&late_cookie);
    if (!simple) gpu_fini();
    if (marker && good_frames) remove(DISPLAY_CHECK_FILE);   /* it drew: a quick exit is no failed start */
    marker = 0;
    lcd_ok = 0;
}
