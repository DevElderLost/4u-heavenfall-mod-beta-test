/* The start's look for the latest release: on a thread of its own, so the home
 * screen answers at once. It asks the network for the edition's latest release, its notes and its XX set's header, and
 * writes only into its own job (tagged with the edition it was started for); the main thread applies the answer once
 * the thread has ended. The thread's stack is 256 KB (the TLS handshake runs on it); it is joined, its stack and
 * buffers freed, before an update (nothing of it stays on the heap during an install), the information page, a title's
 * start, the edition's switch and the exit. A stop asked while it runs ends its transfers at once (the abortable
 * transport, ctr_net.c). */
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "ctr_net.h"

#define CHECK_STACK (256 * 1024)
#define JOIN_SLICE_NS (50ULL * 1000000ULL)

typedef struct {
    /* what it was started for (copied: the thread reads nothing of the app's state but the log and app.probe) */
    int edition;
    int region;
    int xx;
    uint8_t xx_hash[32];
    /* its answer */
    HfCheck check;
    char latest[HF_TAG_MAX];
    char *notes;              /* plain lines (HF_VIEW_NOTES bytes), NULL for none */
    uint64_t set_bytes;       /* the region's plain set's size */
    int xx_set;               /* the release has the region's XX set */
    int app_newer;            /* ... and this form's launcher, newer than this one */
    XxCheck xx_check;
    volatile int done;
} CheckJob;

static Thread thread;
static CheckJob *job;
static volatile int stop_flag;

static void check_main(void *arg) {
    CheckJob *j = (CheckJob *)arg;
    const HfEdition *e = &HF_EDITIONS[j->edition];
    HfRelease *rel = (HfRelease *)malloc(sizeof *rel);
    char *raw = (char *)malloc(NOTES_RAW_SIZE);
    HfTransport tr;
    HfPlanIn in;
    char test_dir[300];
    u64 t = osGetTime();
    int rc;
    j->check = HF_CHECK_FAILED;
    if (!rel) goto out;
    if ((rc = ctr_net_init())) {
        LOG("check: network init %d", rc);
        goto out;
    }
    ctr_net_transport_abortable(&tr, &stop_flag);
    /* a probe build's latest release is its test release on the card, as its update's is */
    if (app.probe)
        rc = release_local(e, rel, raw, raw ? NOTES_RAW_SIZE : 0) == HF_REL_OK ? HF_OK : HF_E_NETWORK;
    else
        rc = release_latest(&tr, e, rel, raw, raw ? NOTES_RAW_SIZE : 0);
    if (rc == HF_E_NONE) {
        j->check = HF_CHECK_NO_RELEASE;
    } else if (rc == HF_OK) {
        const HfAsset *set = &rel->assets[hf_w_patch(j->region, 0)];
        snprintf(j->latest, sizeof j->latest, "%s", rel->tag);
        j->set_bytes = set->found ? set->size : 0;
        if (raw && raw[0] && (j->notes = (char *)malloc(HF_VIEW_NOTES))) hf_notes_plain(raw, j->notes, HF_VIEW_NOTES);
        memset(&in, 0, sizeof in);
        release_xx_check(&tr, j->edition, rel, j->region, j->xx, j->xx_hash, &in, &j->xx_check);
        j->xx_set = in.xx_set_in_release;
        j->app_newer = rel->assets[app_asset()].found && hf_version_newer(rel->tag, HF_APP_VERSION) == 1;
        if (app.probe && probe_test_app(rel, test_dir, sizeof test_dir))   /* a test launcher left on the card */
            j->app_newer = hf_version_newer(rel->tag, HF_APP_VERSION) == 1;
        j->check = HF_CHECK_DONE;
    }
    ctr_net_exit();
out:
    free(raw);
    free(rel);
    LOG("check: answer %d after %lu ms%s", (int)j->check, (unsigned long)(osGetTime() - t),
        stop_flag ? " (asked to stop)" : "");
    j->done = 1;
}

void check_start(void) {
    s32 prio = 0x30;
    if (thread) return;
    app.check = HF_CHECK_RUNNING;
    job = (CheckJob *)calloc(1, sizeof *job);
    if (!job) {
        app.check = HF_CHECK_FAILED;
        return;
    }
    job->edition = app.edition;
    job->region = app.status.region >= 0 ? app.status.region : REGION_EUR;
    job->xx = app.status.xx;
    memcpy(job->xx_hash, app.status.xx_hash, sizeof job->xx_hash);
    stop_flag = 0;
    svcGetThreadPriority(&prio, CUR_THREAD_HANDLE);
    /* below the main thread's priority, and below libctru's APT thread (0x31): it runs while the main thread waits
     * for the player, and a TLS handshake never keeps HOME or the power button waiting */
    thread = threadCreate(check_main, job, CHECK_STACK, prio < 0x3E ? prio + 2 : 0x3F, -2, false);
    if (!thread) {
        LOG("check: no thread (memory)");
        free(job);
        job = NULL;
        app.check = HF_CHECK_FAILED;
        return;
    }
    LOG("check: started for %s", app_edition()->name);
}

int check_running(void) { return thread != NULL; }

/* The answer into the app's state (the main thread). A stop that cut it keeps only a whole answer. */
static void apply(const CheckJob *j, int cut) {
    if (j->edition != app.edition) return;
    if (cut && j->check != HF_CHECK_DONE) {
        app.check = HF_CHECK_FAILED;
        return;
    }
    app.check = j->check;
    if (j->check != HF_CHECK_DONE) return;
    snprintf(app.status.latest, sizeof app.status.latest, "%s", j->latest);
    snprintf(app.notes, sizeof app.notes, "%s", j->notes ? j->notes : "");
    app.latest_set_bytes = j->set_bytes;
    app.latest_xx_set = j->xx_set;
    app.latest_app_newer = j->app_newer;
    if (j->xx_check.known) {
        app.xx_check = j->xx_check;
        if ((app.status.xx == XX_FOUND || app.status.xx == XX_OTHER_VERSION) &&
            !memcmp(app.status.xx_hash, j->xx_check.hash, sizeof j->xx_check.hash))
            app.status.xx = j->xx_check.matches ? XX_FOUND : XX_OTHER_VERSION;
    }
}

/* Joined in slices with APT answered between them: a stop asked during a name lookup (which curl cannot cut) still lets
 * HOME and the power button answer. A slice that times out answers 0x09401BFE, which is no failure (R_FAILED is false):
 * only its description tells the thread still runs, and the job must not be freed under it. */
static void finish(int cut) {
    while (R_DESCRIPTION(threadJoin(thread, JOIN_SLICE_NS)) == RD_TIMEOUT) ui_apt();
    threadFree(thread);
    thread = NULL;
    apply(job, cut);
    free(job->notes);
    free(job);
    job = NULL;
}

int check_poll(void) {
    if (!thread || !job->done) return 0;
    finish(0);
    return 1;
}

void check_stop(int abort_it) {
    int cut;
    if (!thread) return;
    cut = abort_it && !job->done;
    if (cut) {
        stop_flag = 1;
        LOG("check: asked to stop");
    }
    finish(cut);
}
