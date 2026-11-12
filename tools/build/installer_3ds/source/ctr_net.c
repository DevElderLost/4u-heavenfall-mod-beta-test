#include "ctr_net.h"

#include <curl/curl.h>
#include <errno.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <unistd.h>

#include "ctr_title.h"
#include "launcher.h"

#define SOC_BUFFER 0x40000        /* the sockets' shared memory, page aligned */
#define CA_FILE "romfs:/cacert.pem"
#define CONNECT_SECONDS 30
#define STALL_SECONDS 30          /* below 1 byte/s for this long: the connection is given up (and tried again) */
#define MAX_REDIRECTS 5
#define CURL_BUFFER (64 * 1024)
#define SD_MARGIN (16u << 20)     /* kept free on the SD card besides the file */
#define HF_ROOT "sdmc:/3ds/heavenfall"

static u32 *soc_buffer;
static int net_users;             /* the callers using the network now (the start's check, an update) */
static LightLock net_lock;        /* guards soc_buffer and net_users (zero is a valid, unlocked LightLock) */

int ctr_net_init(void) {
    Result rc;
    int out = 0;
    LightLock_Lock(&net_lock);
    if (net_users) {
        net_users++;
        goto done;
    }
    soc_buffer = (u32 *)memalign(0x1000, SOC_BUFFER);
    if (!soc_buffer) {
        out = -1;
        goto done;
    }
    rc = socInit(soc_buffer, SOC_BUFFER);
    if (R_FAILED(rc)) {
        free(soc_buffer);
        soc_buffer = NULL;
        out = (int)rc;
        goto done;
    }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) {
        socExit();
        free(soc_buffer);
        soc_buffer = NULL;
        out = -2;
        goto done;
    }
    net_users = 1;
done:
    LightLock_Unlock(&net_lock);
    return out;
}

void ctr_net_exit(void) {
    LightLock_Lock(&net_lock);
    if (net_users && --net_users == 0) {
        curl_global_cleanup();
        socExit();
        free(soc_buffer);
        soc_buffer = NULL;
    }
    LightLock_Unlock(&net_lock);
}

/* ---- the transport ---- */

typedef struct {
    CURL *curl;
    HfOnHead head;
    HfOnBody body;
    void *cb_ctx;
    int status;
    int64_t length, range_start;
    int head_sent, stopped;
} Call;

static int is_redirect(int status) {
    return status == 301 || status == 302 || status == 303 || status == 307 || status == 308;
}

/* The status line starts an answer (again after each redirect); the empty line ends its headers. */
static size_t on_header(char *line, size_t size, size_t nitems, void *userdata) {
    Call *c = (Call *)userdata;
    size_t n = size * nitems;
    if (n >= 5 && !strncmp(line, "HTTP/", 5)) {
        const char *sp = memchr(line, ' ', n);
        c->status = sp ? atoi(sp + 1) : 0;
        c->length = -1;
        c->range_start = -1;
        c->head_sent = 0;
    } else if (n > 15 && !strncasecmp(line, "content-length:", 15)) {
        c->length = atoll(line + 15);
    } else if (n > 14 && !strncasecmp(line, "content-range:", 14)) {
        const char *p = line + 14;
        while (p < line + n && (*p == ' ' || *p == '\t'))
            p++;
        if (!strncasecmp(p, "bytes ", 6))
            c->range_start = atoll(p + 6);
    } else if ((n == 2 && line[0] == '\r') || n == 1) {
        if (c->status && !is_redirect(c->status) && !c->head_sent) {
            char *url = NULL;
            c->head_sent = 1;
            curl_easy_getinfo(c->curl, CURLINFO_EFFECTIVE_URL, &url);
            if (c->head(c->cb_ctx, c->status, c->length, c->range_start, url)) {
                c->stopped = 1;
                return 0;  /* a short count aborts the transfer */
            }
        }
    }
    return n;
}

static size_t on_write(char *data, size_t size, size_t nmemb, void *userdata) {
    Call *c = (Call *)userdata;
    size_t n = size * nmemb;
    if (!c->head_sent || is_redirect(c->status))
        return n;  /* the body of a redirect: not ours */
    if (c->body(c->cb_ctx, data, n)) {
        c->stopped = 1;
        return 0;
    }
    return n;
}

/* An abortable transport's flag (ctr_net_transport_abortable): curl asks this between its steps, and a set flag stops the
 * transfer. */
static int on_xfer(void *clientp, curl_off_t dltotal, curl_off_t dlnow, curl_off_t ultotal, curl_off_t ulnow) {
    (void)dltotal;
    (void)dlnow;
    (void)ultotal;
    (void)ulnow;
    return *(volatile int *)clientp ? 1 : 0;
}

static int curl_get(void *ctx, const HfRequest *req, HfOnHead head, HfOnBody body, void *cb_ctx) {
    Call c;
    volatile int *abort_flag = (volatile int *)ctx;
    CURL *curl;
    struct curl_slist *headers = NULL;
    char range[64];
    CURLcode rc;
    if (abort_flag && *abort_flag)
        return HF_NET_FAIL;   /* asked to stop: every try left ends at once */
    curl = curl_easy_init();
    if (!curl)
        return HF_NET_FAIL;
    memset(&c, 0, sizeof c);
    c.curl = curl;
    c.head = head;
    c.body = body;
    c.cb_ctx = cb_ctx;
    curl_easy_setopt(curl, CURLOPT_URL, req->url);
    curl_easy_setopt(curl, CURLOPT_USERAGENT, req->user_agent ? req->user_agent : "Heavenfall");
    if (req->accept) {
        char accept[96];
        snprintf(accept, sizeof accept, "Accept: %s", req->accept);
        headers = curl_slist_append(headers, accept);
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
    }
    if (req->range_from || req->range_length) {
        if (req->range_length)
            snprintf(range, sizeof range, "%llu-%llu", (unsigned long long)req->range_from,
                     (unsigned long long)(req->range_from + req->range_length - 1));
        else
            snprintf(range, sizeof range, "%llu-", (unsigned long long)req->range_from);
        curl_easy_setopt(curl, CURLOPT_RANGE, range);
    }
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_MAXREDIRS, (long)MAX_REDIRECTS);
    curl_easy_setopt(curl, CURLOPT_PROTOCOLS_STR, "https");
    curl_easy_setopt(curl, CURLOPT_REDIR_PROTOCOLS_STR, "https");
    curl_easy_setopt(curl, CURLOPT_CAINFO, CA_FILE);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, (long)CONNECT_SECONDS);
    curl_easy_setopt(curl, CURLOPT_LOW_SPEED_LIMIT, 1L);
    curl_easy_setopt(curl, CURLOPT_LOW_SPEED_TIME, (long)STALL_SECONDS);
    curl_easy_setopt(curl, CURLOPT_BUFFERSIZE, (long)CURL_BUFFER);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
    curl_easy_setopt(curl, CURLOPT_ACCEPT_ENCODING, NULL);  /* the bytes as they are: the digest is of them */
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, on_header);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA, &c);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, on_write);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &c);
    if (abort_flag) {
        curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, on_xfer);
        curl_easy_setopt(curl, CURLOPT_XFERINFODATA, (void *)abort_flag);
        curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
    }
    rc = curl_easy_perform(curl);
    curl_slist_free_all(headers);
    curl_easy_cleanup(curl);
    if (c.stopped)
        return HF_NET_ABORT;
    return rc == CURLE_OK ? HF_NET_OK : HF_NET_FAIL;
}

#define SLEEP_SLICE_MS 50u

/* The wait before a retry, in slices so a set abort flag ends it at once. */
static void curl_sleep(void *ctx, unsigned ms) {
    volatile int *abort_flag = (volatile int *)ctx;
    while (ms && !(abort_flag && *abort_flag)) {
        unsigned slice = ms < SLEEP_SLICE_MS ? ms : SLEEP_SLICE_MS;
        svcSleepThread((s64)slice * 1000000LL);
        ms -= slice;
    }
}

void ctr_net_transport(HfTransport *tr) {
    tr->get = curl_get;
    tr->sleep_ms = curl_sleep;
    tr->ctx = NULL;
}

void ctr_net_transport_abortable(HfTransport *tr, volatile int *abort_flag) {
    ctr_net_transport(tr);
    tr->ctx = (void *)abort_flag;
}

/* ---- downloads to the SD card ---- */

int ctr_net_folder(const HfEdition *edition, char *out, size_t cap) {
    char path[300];
    if (snprintf(out, cap, HF_ROOT "/%s", edition->slug) >= (int)cap)
        return -1;
    mkdir("sdmc:/3ds", 0777);
    mkdir(HF_ROOT, 0777);
    snprintf(path, sizeof path, "%s", out);
    return mkdir(path, 0777) && errno != EEXIST ? -1 : 0;
}

typedef struct {
    FILE *f;
} Part;

static int part_size(void *c, uint64_t *size) {
    FILE *f = ((Part *)c)->f;
    if (fseek(f, 0, SEEK_END))
        return 1;
    *size = (uint64_t)ftell(f);
    return 0;
}

static int part_read(void *c, uint64_t offset, void *buf, size_t n) {
    FILE *f = ((Part *)c)->f;
    return fseek(f, (long)offset, SEEK_SET) || fread(buf, 1, n, f) != n;
}

static int part_append(void *c, const void *buf, size_t n) {
    FILE *f = ((Part *)c)->f;
    return fseek(f, 0, SEEK_END) || fwrite(buf, 1, n, f) != n;
}

static int part_truncate(void *c, uint64_t size) {
    FILE *f = ((Part *)c)->f;
    return fflush(f) || ftruncate(fileno(f), (off_t)size);
}

int ctr_net_fetch(const HfEdition *edition, const HfAsset *asset, const HfTransport *tr,
                  int (*progress)(void *ctx, uint64_t done, uint64_t total), void *ctx, char *path, size_t cap) {
    char folder[200], part_path[320];
    Part part;
    HfDownload d;
    uint64_t have = 0;
    int rc;
    if (ctr_net_folder(edition, folder, sizeof folder) ||
        snprintf(path, cap, "%s/%s", folder, asset->name) >= (int)cap ||
        snprintf(part_path, sizeof part_path, "%s.part", path) >= (int)sizeof part_path)
        return HF_E_DISK;
    /* A whole download kept after a failed install (app_update.c keeps the set for the next try) goes back to being the
     * .part: the download checks it again and ends at once when it is complete, instead of fetching it all anew. */
    part.f = fopen(part_path, "rb");
    if (part.f)
        fclose(part.f);
    else
        rename(path, part_path);
    part.f = fopen(part_path, "r+b");
    if (!part.f)
        part.f = fopen(part_path, "w+b");
    if (!part.f)
        return HF_E_DISK;
    part_size(&part, &have);
    {   /* compared by subtraction: an asset size from the network near 2^64 must not wrap past the check */
        uint64_t free_bytes = ctr_sd_free(), need = asset->size > have ? asset->size - have : 0;
        if (free_bytes < SD_MARGIN || need > free_bytes - SD_MARGIN) {
            fclose(part.f);
            return HF_E_DISK;
        }
    }
    memset(&d, 0, sizeof d);
    d.transport = tr;
    d.user_agent = edition->name;
    d.url = asset->url;
    d.size = asset->size;
    memcpy(d.sha256, asset->sha256, 32);
    d.file.size = part_size;
    d.file.read = part_read;
    d.file.append = part_append;
    d.file.truncate = part_truncate;
    d.file.ctx = &part;
    d.progress = progress;
    d.progress_ctx = ctx;
    rc = hf_download(&d);
    if (rc == HF_OK && fflush(part.f))
        rc = HF_E_DISK;
    fclose(part.f);
    if (rc == HF_OK) {
        remove(path);
        if (rename(part_path, path))
            rc = HF_E_DISK;
    }
    return rc;
}

/* ---- the app's own update ---- */

CtrForm ctr_app_form(void) {
    return envIsHomebrew() ? CTR_FORM_3DSX : CTR_FORM_CIA;
}

static int with_suffix(const char *path, const char *suffix, char *out, size_t cap) {
    return snprintf(out, cap, "%s%s", path, suffix) >= (int)cap;
}

void ctr_self_recover(const char *own_path) {
    char old[300];
    FILE *f;
    if (!hf_own_3dsx_ok(own_path) || with_suffix(own_path, ".old", old, sizeof old))
        return;
    f = fopen(own_path, "rb");
    if (f) {
        fclose(f);
        remove(old);  /* the update finished; only its leftover is here */
        return;
    }
    if ((f = fopen(old, "rb"))) {  /* cut between the two renames: put the old app back */
        fclose(f);
        rename(old, own_path);
    }
}

int ctr_self_replace_3dsx(const char *downloaded, const char *own_path) {
    char old[300];
    if (!hf_own_3dsx_ok(own_path))     /* a loader's argv[0] that is no .3dsx on the card: nothing renamed */
        return EINVAL;
    if (with_suffix(own_path, ".old", old, sizeof old))
        return ENAMETOOLONG;
    remove(old);
    if (rename(own_path, old))
        return errno;
    if (rename(downloaded, own_path)) {
        int e = errno;
        rename(old, own_path);  /* the old app stays */
        return e;
    }
    remove(old);
    return 0;
}

int ctr_self_install_cia(const char *cia_path, Result *result) {
    FILE *f = fopen(cia_path, "rb");
    static uint8_t buf[256 * 1024];
    CtrAm *am;
    size_t n;
    int failed = 0;
    *result = 0;
    if (!f)
        return ENOENT;
    n = fread(buf, 1, sizeof buf, f);
    if (!hf_cia_is_launcher(buf, n)) {   /* AM imports whatever title a CIA names: only the launcher's goes in */
        fclose(f);
        *result = -3;
        return -1;
    }
    am = ctr_am_begin(result);
    if (!am) {
        fclose(f);
        return -1;
    }
    failed = ctr_am_write(am, buf, n);
    while (!failed && (n = fread(buf, 1, sizeof buf, f)) > 0)
        failed = ctr_am_write(am, buf, n);
    failed |= ferror(f);
    fclose(f);
    if (failed) {
        ctr_am_cancel(am);
        *result = -2;
        return -1;
    }
    *result = ctr_am_finish(am);
    return R_FAILED(*result) ? -1 : 0;
}
