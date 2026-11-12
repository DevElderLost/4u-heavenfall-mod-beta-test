/* See hfnet.h. */
#include "hfnet.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "sha256.h"
#include "updplan.h"

static void pause_between(const HfTransport *tr) {
    if (tr->sleep_ms)
        tr->sleep_ms(tr->ctx, HF_RETRY_WAIT_MS);
}

/* ---- the API's answer into memory ---- */

typedef struct {
    char *buf;
    size_t len;
    int status, too_big, bad_url;
} Mem;

static int mem_head(void *ctx, int status, int64_t length, int64_t range_start, const char *final_url) {
    Mem *m = ctx;
    (void)range_start;
    m->status = status;
    if (final_url && !hf_url_is_https(final_url)) {
        m->bad_url = 1;  /* a redirect off https */
        return 1;
    }
    if (length > (int64_t)HF_API_MAX)
        m->too_big = 1;
    return status != 200 || m->too_big;
}

static int mem_body(void *ctx, const void *data, size_t n) {
    Mem *m = ctx;
    if (m->len + n > HF_API_MAX) {
        m->too_big = 1;
        return 1;
    }
    memcpy(m->buf + m->len, data, n);
    m->len += n;
    return 0;
}

int hf_latest_release(const HfTransport *tr, const char *api_base, const char *repository, const char *user_agent,
                      const char *const *wanted, int nwanted, HfRelease *out, char *notes, size_t notes_cap,
                      int *http) {
    char url[300];
    HfRequest req;
    Mem m;
    int attempt, rc = HF_E_NETWORK, dummy;
    if (!http)
        http = &dummy;
    *http = 0;
    if (snprintf(url, sizeof url, "%s/repos/%s/releases/latest", api_base, repository) >= (int)sizeof url)
        return HF_E_ARG;
    m.buf = malloc(HF_API_MAX);
    if (!m.buf)
        return HF_E_ARG;
    memset(&req, 0, sizeof req);
    req.url = url;
    req.user_agent = user_agent;
    req.accept = "application/vnd.github+json";
    for (attempt = 0; attempt < HF_TRIES; attempt++) {
        int net;
        m.len = 0;
        m.status = 0;
        m.too_big = 0;
        m.bad_url = 0;
        net = tr->get(tr->ctx, &req, mem_head, mem_body, &m);
        *http = m.status;
        if (m.bad_url) {
            rc = HF_E_BAD_URL;
            break;
        }
        if (m.too_big) {
            rc = HF_E_TOO_BIG;
            break;
        }
        if (m.status == 404) {
            rc = HF_E_NONE;
            break;
        }
        if (m.status == 403 || m.status == 429) {
            rc = HF_E_RATE;
            break;
        }
        if (m.status == 200 && net == HF_NET_OK) {
            rc = hf_release_parse(m.buf, m.len, repository, wanted, nwanted, out, notes, notes_cap);
            break;
        }
        if (m.status >= 400 && m.status < 500) {
            rc = HF_E_HTTP;
            break;
        }
        rc = m.status >= 500 ? HF_E_HTTP : HF_E_NETWORK;  /* a server error or a cut: ask again */
        if (attempt < HF_TRIES - 1)
            pause_between(tr);
    }
    free(m.buf);
    return rc;
}

/* ---- a download ---- */

typedef struct {
    HfDownload *d;
    Sha256 sha;
    uint64_t got, arrived;
    int64_t length;
    int status;
    int stop;  /* HF_OK, or what made a callback stop the transfer */
} Dl;

static void start_again(Dl *s) {
    sha256_init(&s->sha);
    s->got = 0;
    s->d->file.truncate(s->d->file.ctx, 0);
}

static int dl_head(void *ctx, int status, int64_t length, int64_t range_start, const char *final_url) {
    Dl *s = ctx;
    s->status = status;
    s->length = length;
    s->arrived = 0;
    if (final_url && !hf_url_is_https(final_url)) {
        s->stop = HF_E_BAD_URL;
        return 1;
    }
    if (status == 206) {
        if (s->got && range_start >= 0 && (uint64_t)range_start != s->got) {  /* not where we asked: wrong bytes */
            s->stop = HF_E_BAD_SIZE;
            return 1;
        }
        return 0;
    }
    if (status != 200)
        return 1;
    if (s->got)  /* the server does not resume: this answer is the whole file */
        start_again(s);
    return 0;
}

static int dl_body(void *ctx, const void *data, size_t n) {
    Dl *s = ctx;
    HfDownload *d = s->d;
    if (s->got + n > d->size) {
        s->stop = HF_E_BAD_SIZE;
        return 1;
    }
    sha256_update(&s->sha, data, n);
    if (d->file.append(d->file.ctx, data, n)) {
        s->stop = HF_E_DISK;
        return 1;
    }
    s->got += n;
    s->arrived += n;
    if (d->progress && d->progress(d->progress_ctx, s->got, d->size)) {
        s->stop = HF_E_CANCEL;
        return 1;
    }
    return 0;
}

/* Hashes what the file already holds; 0 on success. */
static int rehash(Dl *s) {
    HfDownload *d = s->d;
    uint64_t have = 0, at = 0;
    static uint8_t buf[1 << 16];
    sha256_init(&s->sha);
    s->got = 0;
    if (d->file.size(d->file.ctx, &have))
        return HF_E_DISK;
    if (have > d->size) {
        if (d->file.truncate(d->file.ctx, 0))
            return HF_E_DISK;
        return 0;
    }
    while (at < have) {
        size_t n = have - at > sizeof buf ? sizeof buf : (size_t)(have - at);
        if (d->file.read(d->file.ctx, at, buf, n))
            return HF_E_DISK;
        sha256_update(&s->sha, buf, n);
        at += n;
    }
    s->got = have;
    return 0;
}

int hf_download(HfDownload *d) {
    Dl s;
    int attempt, rc, last = HF_E_NETWORK;
    if (!d || !d->transport || !d->url || !d->size || !d->file.size || !d->file.read || !d->file.append ||
        !d->file.truncate)
        return HF_E_ARG;
    if (!hf_url_is_https(d->url))
        return HF_E_BAD_URL;
    s.d = d;
    s.stop = HF_OK;
    d->http = 0;
    rc = rehash(&s);
    if (rc)
        return rc;
    for (attempt = 0; attempt < HF_TRIES; attempt++) {
        int net = HF_NET_OK;
        s.stop = HF_OK;
        s.status = 0;
        s.length = -1;
        s.arrived = 0;
        if (d->progress && d->progress(d->progress_ctx, s.got, d->size))
            return HF_E_CANCEL;
        if (s.got < d->size) {
            HfRequest req;
            memset(&req, 0, sizeof req);
            req.url = d->url;
            req.user_agent = d->user_agent;
            req.range_from = s.got;
            net = d->transport->get(d->transport->ctx, &req, dl_head, dl_body, &s);
            d->http = s.status;
            if (s.stop == HF_E_CANCEL || s.stop == HF_E_DISK || s.stop == HF_E_BAD_URL)
                return s.stop;
            if (s.status == 403 || s.status == 429)
                return HF_E_RATE;
            if (s.status == 416 || (s.status >= 400 && s.status < 500))
                return HF_E_HTTP;
        }
        if (s.stop == HF_E_BAD_SIZE) {
            last = HF_E_BAD_SIZE;
            start_again(&s);
        } else if (s.status >= 500 || (net != HF_NET_OK && s.status != 200 && s.status != 206)) {
            last = s.status >= 500 ? HF_E_HTTP : HF_E_NETWORK;
        } else if (s.got < d->size) {
            if (s.length >= 0 && s.arrived == (uint64_t)s.length && net == HF_NET_OK) {
                last = HF_E_BAD_SIZE;  /* all it had: the release says otherwise */
                start_again(&s);
            } else {
                last = HF_E_NETWORK;  /* the connection was cut: go on from here */
            }
        } else {
            uint8_t digest[32];
            Sha256 copy = s.sha;
            sha256_final(&copy, digest);
            if (!memcmp(digest, d->sha256, 32))
                return HF_OK;
            last = HF_E_BAD_HASH;
            start_again(&s);
        }
        if (attempt < HF_TRIES - 1)
            pause_between(d->transport);
    }
    return last;
}

/* ---- the patch set's header ---- */

typedef struct {
    uint8_t *head;
    size_t want, got;
    int status;
} Peek;

static int peek_head(void *ctx, int status, int64_t length, int64_t range_start, const char *final_url) {
    Peek *p = ctx;
    (void)length;
    (void)range_start;
    p->status = status;
    if (final_url && !hf_url_is_https(final_url))
        return 1;
    return status != 206 && status != 200;
}

static int peek_body(void *ctx, const void *data, size_t n) {
    Peek *p = ctx;
    size_t take = p->want - p->got < n ? p->want - p->got : n;
    memcpy(p->head + p->got, data, take);
    p->got += take;
    return p->got >= p->want;  /* a server that ignores Range: stop after the bytes asked for */
}

int hf_read_set_head(const HfTransport *tr, const char *url, const char *user_agent, uint8_t *head, size_t len) {
    HfRequest req;
    Peek p;
    int attempt, net = HF_NET_FAIL;
    if (!head || len < 8 || len > HF_SET_HEAD_MAX)
        return HF_E_ARG;
    if (!hf_url_is_https(url))
        return HF_E_BAD_URL;
    memset(&req, 0, sizeof req);
    req.url = url;
    req.user_agent = user_agent;
    req.range_from = 0;
    req.range_length = len;
    for (attempt = 0; attempt < HF_TRIES; attempt++) {
        memset(&p, 0, sizeof p);
        p.head = head;
        p.want = len;
        net = tr->get(tr->ctx, &req, peek_head, peek_body, &p);
        if (p.got >= len)
            break;
        if (p.status == 403 || p.status == 429)
            return HF_E_RATE;
        if (p.status >= 400 && p.status < 500)
            return HF_E_HTTP;
        if (attempt < HF_TRIES - 1)
            pause_between(tr);
    }
    (void)net;
    if (p.got < len)
        return HF_E_NETWORK;
    if (memcmp(head, "HFPS", 4) != 0)
        return HF_E_FORMAT;
    return HF_OK;
}

int hf_read_set_format(const HfTransport *tr, const char *url, const char *user_agent, uint32_t *format) {
    uint8_t head[8];
    int rc = hf_read_set_head(tr, url, user_agent, head, sizeof head);
    if (rc == HF_OK)
        *format = (uint32_t)head[4] | (uint32_t)head[5] << 8 | (uint32_t)head[6] << 16 | (uint32_t)head[7] << 24;
    return rc;
}
