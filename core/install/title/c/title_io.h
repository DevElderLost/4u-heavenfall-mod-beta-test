/* Shared types of the installed-title writer (portable C99, no libctru). Every byte goes through callbacks and
 * every failure is a return code; nothing here exits or aborts. Python reference: core/install/title/. */
#ifndef TITLE_IO_H
#define TITLE_IO_H

#include <stddef.h>
#include <stdint.h>

enum {
    TITLE_OK = 0,
    TITLE_E_ARG = -1,     /* a bad argument or a call out of order */
    TITLE_E_MEM = -2,     /* out of memory */
    TITLE_E_IO = -3,      /* a read, write or hash-store callback failed */
    TITLE_E_PATH = -4,    /* an empty or invalid path, a duplicate, a name that is both a file and a folder */
    TITLE_E_SIZE = -5,    /* the sizes announced and the bytes produced differ */
    TITLE_E_FORMAT = -6,  /* an input of the wrong shape (header, exheader, SMDH, ExeFS file) */
    TITLE_E_CANCEL = -7,  /* the progress callback asked to stop */
    TITLE_E_ENCRYPTED = -8,  /* a game file that is not decrypted */
    TITLE_E_GAME = -9,    /* a game, title or region this does not build for */
    TITLE_E_NOPATCH = -10, /* an update was asked for but the executable does not read one */
    TITLE_E_HASH = -11,   /* bytes produced or read do not hash to what the patch set recorded */
    TITLE_E_DAMAGED = -12 /* the dump's RomFS is not what its own hash levels say: a damaged copy (no route helps) */
};

/* Writes n bytes; returns 0 on success. A stream: the writer never needs to seek. */
typedef int (*TitleWrite)(void *ctx, const void *buf, size_t n);
/* Reads n bytes at `offset` of the source `handle`; returns 0 only if all n bytes were read. */
typedef int (*TitleRead)(void *ctx, void *handle, uint64_t offset, void *buf, size_t n);
/* Called as bytes go by; a nonzero return cancels the pass (TITLE_E_CANCEL). May be NULL. */
typedef int (*TitleProgress)(void *ctx, uint64_t done, uint64_t total);

typedef struct {
    TitleWrite write;
    void *ctx;
    TitleProgress progress;
    void *progress_ctx;
} TitleOut;

static inline uint64_t title_align(uint64_t v, uint64_t a) { return (v + a - 1) / a * a; }
static inline void put_le16(uint8_t *p, uint32_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static inline void put_le32(uint8_t *p, uint32_t v) { put_le16(p, v); put_le16(p + 2, v >> 16); }
static inline void put_le64(uint8_t *p, uint64_t v) { put_le32(p, (uint32_t)v); put_le32(p + 4, (uint32_t)(v >> 32)); }
static inline void put_be16(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static inline void put_be32(uint8_t *p, uint32_t v) { put_be16(p, v >> 16); put_be16(p + 2, v); }
static inline void put_be64(uint8_t *p, uint64_t v) { put_be32(p, (uint32_t)(v >> 32)); put_be32(p + 4, (uint32_t)v); }
static inline uint32_t get_le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* Writes n zero bytes through out->write. */
int title_write_zeros(const TitleOut *out, uint64_t n);

#endif
