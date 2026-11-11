/* The launcher's network logic (portable C99, no libctru), behind a transport: the releases/latest answer, a resumable
download checked by SHA-256, the patch set's format peek. The rules
 * are the PC updater's (core/install/self_update.py): 404 is "nothing published", 403 and 429 the API's rate limit; a
 * cut connection goes on where it stopped (Range), a server that ignores Range starts again, a server error is asked
 * again, wrong bytes are fetched from the start, HF_TRIES tries in all. On the 3DS the transport is libcurl
 * (tools/build/installer_3ds/source/ctr_net.c); the tests serve canned answers. */
#ifndef HFNET_H
#define HFNET_H

#include <stddef.h>
#include <stdint.h>

#include "release.h"

#define HF_TRIES 4              /* tries in all for one answer or one download */
#define HF_RETRY_WAIT_MS 2000   /* before the next try */
#define HF_API_MAX (512 * 1024) /* the releases/latest answer is a few KB; more is refused */
#define HF_API_BASE "https://api.github.com"

enum {
    HF_OK = 0,
    HF_E_NETWORK = -30,  /* no connection, or it was cut and every try failed */
    HF_E_RATE = -31,     /* 403 or 429: the API's rate limit */
    HF_E_HTTP = -32,     /* any other answer; the code is in *http */
    HF_E_NONE = -33,     /* 404: no published version (a repository without releases answers 404 to anyone) */
    HF_E_BAD_SIZE = -34, /* more or fewer bytes than the release says */
    HF_E_BAD_HASH = -35, /* the bytes do not hash to the release's digest */
    HF_E_DISK = -36,     /* the file callbacks failed */
    HF_E_CANCEL = -37,   /* the progress callback asked to stop */
    HF_E_ARG = -38,
    HF_E_TOO_BIG = -39,  /* an API answer over HF_API_MAX */
    HF_E_BAD_URL = -40,  /* a download that does not start on https */
    HF_E_FORMAT = -41    /* not a patch set */
};

/* ---- the transport ---- */

typedef struct {
    const char *url;
    const char *user_agent;
    const char *accept;      /* may be NULL */
    uint64_t range_from;     /* 0: no Range header */
    uint64_t range_length;   /* with range_from: 0 to the end ("bytes=a-"), else "bytes=a-(a+length-1)" */
} HfRequest;

/* Called with the final answer's head (after redirects); nonzero stops the transfer. `content_length` is the body's
 * length or -1, `range_start` the first byte of a 206's Content-Range or -1, `final_url` the URL answered after redirects
 * (NULL when the transport cannot say; anything not https stops the transfer). */
typedef int (*HfOnHead)(void *ctx, int status, int64_t content_length, int64_t range_start, const char *final_url);
/* Called with body bytes as they come; nonzero stops the transfer. */
typedef int (*HfOnBody)(void *ctx, const void *data, size_t n);

enum { HF_NET_OK = 0, HF_NET_FAIL = 1 /* no connection or cut */, HF_NET_ABORT = 2 /* a callback stopped it */ };

typedef struct {
    /* One GET. A redirect is followed only to https (HTTPS-only, also for the first URL's redirects). */
    int (*get)(void *ctx, const HfRequest *req, HfOnHead head, HfOnBody body, void *cb_ctx);
    void (*sleep_ms)(void *ctx, unsigned ms);  /* may be NULL */
    void *ctx;
} HfTransport;

/* ---- the release ---- */

/* The latest release of `repository` (`api_base` is only for tests; the app passes HF_API_BASE) and the wanted assets of
 * it. HF_E_NONE when there is no published version, a HF_REL_* when the answer breaks the rules. *http gets the last
 * status seen (may be NULL). `notes` (NULL: not wanted) gets the release's text, as hf_release_parse. */
int hf_latest_release(const HfTransport *tr, const char *api_base, const char *repository, const char *user_agent,
                      const char *const *wanted, int nwanted, HfRelease *out, char *notes, size_t notes_cap,
                      int *http);

/* ---- a download ---- */

typedef struct {
    int (*size)(void *ctx, uint64_t *size);                          /* what the file holds now */
    int (*read)(void *ctx, uint64_t offset, void *buf, size_t n);    /* 0 on success */
    int (*append)(void *ctx, const void *buf, size_t n);             /* at the end; 0 on success */
    int (*truncate)(void *ctx, uint64_t size);                       /* cuts the file to `size`; 0 on success */
    void *ctx;
} HfFile;

typedef struct {
    const HfTransport *transport;
    const char *user_agent;
    const char *url;
    uint64_t size;
    uint8_t sha256[32];
    HfFile file;                  /* a part of the asset may already be in it (a cut download, an earlier run) */
    int (*progress)(void *ctx, uint64_t done, uint64_t total);  /* nonzero cancels; may be NULL */
    void *progress_ctx;
    int http;                     /* out: the last status seen */
} HfDownload;

/* Fetches the asset into d->file, checked against d->size and d->sha256 before it returns HF_OK. Bytes already in the file
 * are hashed and kept (a cancelled or cut download goes on); a file larger than the asset is cut to nothing. */
int hf_download(HfDownload *d);

/* The first `len` bytes of a patch set (8 to HF_SET_HEAD_MAX of updplan.h: its header, "HFPS" first) read with a Range
 * request, without downloading it. HF_E_FORMAT when they are not a set's; the network's codes otherwise. */
int hf_read_set_head(const HfTransport *tr, const char *url, const char *user_agent, uint8_t *head, size_t len);
/* The format version of a patch set (its header's first 8 bytes: "HFPS", u32 format), as above. */
int hf_read_set_format(const HfTransport *tr, const char *url, const char *user_agent, uint32_t *format);

#endif
