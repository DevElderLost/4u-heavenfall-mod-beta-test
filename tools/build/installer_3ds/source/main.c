/* Heavenfall Launcher: installs and updates the mod (and itself), starts Heavenfall or the original MH4U, guides the
 * first setup, copies the MH4U save and installs the online patch. The drawing
 * thread (ui.h) draws and reads the buttons; the main thread's loops take its events (app_loop), and long steps poll
 * them (ui_progress), so HOME, the power button and B always answer. The start: the display, the resume file of an
 * update the app's own update cut short (it goes on by itself), the status, the start's check on its own thread
 * (app_check.c), then the home screen (app_home.c). */
#include <3ds.h>
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "ctr_net.h"

/* The title writer keeps a few 8 KB buffers on the stack (the CIA header, the pack's SMDH): more than the default 32 KB. */
u32 __stacksize__ = 512 * 1024;

/* libctru gives the linear heap (GPU-visible memory) up to 32 MB by default and the regular heap the rest (about 30 MB
 * in the 64 MB mode): the title build ran out of memory on a real console. The app's linear memory is the two
 * screens' framebuffers (~1 MB), citro3d's command buffer (256 KB), citro2d's vertices (~280 KB), the logo's texture
 * and the chime while it plays, so the regular heap gets everything else (libctru: heap = free memory - this). */
u32 __ctru_linear_heap_size = 6 * 1024 * 1024;

App app;

static int beta_index(void) {
    int i;
    for (i = 0; i < HF_EDITION_COUNT; i++)
        if (!strcmp(HF_EDITIONS[i].slug, "heavenfall_beta")) return i;
    return 0;
}

static void init_app(int argc, char **argv) {
    u8 lang = 1, model = 0;
    memset(&app, 0, sizeof app);
    if (R_SUCCEEDED(cfguInit())) {
        CFGU_GetSystemLanguage(&lang);
        CFGU_GetSystemModel(&model);
        cfguExit();
    }
    app.lang = hf_lang_from_system(lang);
    app.model = model;
    app.edition = beta_index();
#ifdef HF_PROBE
    app.probe = 1;
#endif
    app.is_3dsx = ctr_app_form() == CTR_FORM_3DSX;
    if (app.is_3dsx && argc > 0 && argv && argv[0]) snprintf(app.own_path, sizeof app.own_path, "%s", argv[0]);
    app.status.region = -1;
    app.status.installed_region = -1;
    app.check = HF_CHECK_FAILED;   /* no check asked yet */
}

/* The first frame, while the status is gathered. */
static void starting(void) {
    HfView *v = ui_begin();
    ui_reset(v, HF_SCREEN_HOME);
    snprintf(v->heading, sizeof v->heading, "%s v%s", T(HT_TITLE), HF_APP_VERSION);
    snprintf(v->state, sizeof v->state, "%s", T(HT_CHECKING));
    v->tone = HF_TONE_MUTED;
    v->busy = 1;
    ui_end();
}

int main(int argc, char **argv) {
    int leave = 0;
    gfxInitDefault();
    osSetSpeedupEnable(true);   /* the New 3DS's faster clock; harmless on the old one */
    amInit();
    romfsInit();
    init_app(argc, argv);
    language_load();
    if (app.is_3dsx) ctr_self_recover(app.own_path);
    log_open();
    ui_init();   /* after log_open: the log says which display it took */
    starting();
    probe_startup();
    if (resume_found()) leave = update_run(1, 0);   /* the app updated itself: the mod's update goes on */
    else status_gather();
    if (!leave) {
        if (app.check != HF_CHECK_DONE) check_start();
        home_run();
    }

    if (check_running()) ui_working(T(HT_CLOSING));   /* the check's download stops first: up to a second */
    check_stop(1);
    ui_exit();
    log_close();
    romfsExit();
    amExit();
    osSetSpeedupEnable(false);
    gfxExit();
    return 0;
}
