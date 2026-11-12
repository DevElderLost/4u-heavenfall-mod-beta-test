/* See stream.h. */
#include "stream.h"

#include <stdlib.h>
#include <string.h>

#define STAGES 3

struct Stream {
    Piece *pieces;
    size_t npieces;
    uint64_t total;
    TitleRead read;
    void *read_ctx;
    StreamSinks sinks;
    StreamSync sync;
    int has_sync;
    size_t nbuf, bufsize;
    uint8_t *mem;               /* nbuf * bufsize */
    int *due;                   /* per slot: the stage its buffer waits for (0 read, 1 hash, 2 write) */
    uint64_t *seq;              /* per slot: the buffer number it holds or waits to hold */
    size_t *len;                /* per slot: the bytes in it */
    uint64_t nbuffers;          /* buffers in the whole stream */
    uint64_t cursor[STAGES];    /* each stage's next buffer */
    unsigned claimed;
    int rc;
    /* only the reading stage touches these: the buffer it fills */
    int open;                   /* a buffer is being filled */
    size_t slot, at;            /* its slot and the bytes in it */
    uint64_t written;           /* only the writing stage */
};

/* ---- pieces ---------------------------------------------------------------------------------------------------- */

static int push(PieceList *l, int kind, const uint8_t *mem, void *handle, uint64_t offset, uint64_t len) {
    Piece *p;
    if (!l) return TITLE_E_ARG;
    if (!len) return TITLE_OK;
    if (kind == PIECE_ZERO && l->n && l->v[l->n - 1].kind == PIECE_ZERO) {
        l->v[l->n - 1].len += len;
        l->total += len;
        return TITLE_OK;
    }
    if (l->n == l->cap) {
        size_t cap = l->cap ? l->cap * 2 : 64;
        Piece *g = (Piece *)realloc(l->v, cap * sizeof *g);
        if (!g) return TITLE_E_MEM;
        l->v = g;
        l->cap = cap;
    }
    p = &l->v[l->n++];
    memset(p, 0, sizeof *p);
    p->kind = kind;
    p->mem = mem;
    p->handle = handle;
    p->offset = offset;
    p->len = len;
    l->total += len;
    return TITLE_OK;
}

int pieces_mem(PieceList *l, const void *mem, uint64_t len) {
    return len && !mem ? TITLE_E_ARG : push(l, PIECE_MEM, (const uint8_t *)mem, NULL, 0, len);
}
int pieces_src(PieceList *l, void *handle, uint64_t offset, uint64_t len) {
    return push(l, PIECE_SRC, NULL, handle, offset, len);
}
int pieces_zero(PieceList *l, uint64_t len) { return push(l, PIECE_ZERO, NULL, NULL, 0, len); }

int pieces_gen(PieceList *l, PieceGen gen, void *gen_ctx, void *handle, uint64_t len) {
    int rc;
    if (!gen) return TITLE_E_ARG;
    if (!len) return TITLE_OK;
    if ((rc = push(l, PIECE_GEN, NULL, handle, 0, len))) return rc;
    l->v[l->n - 1].gen = gen;
    l->v[l->n - 1].gen_ctx = gen_ctx;
    return TITLE_OK;
}

void pieces_free(PieceList *l) {
    if (!l) return;
    free(l->v);
    memset(l, 0, sizeof *l);
}

/* ---- the ring -------------------------------------------------------------------------------------------------- */

int stream_open(Stream **out, const PieceList *pieces, TitleRead read, void *read_ctx, const StreamSinks *sinks,
                const StreamSetup *setup) {
    Stream *s;
    size_t i;
    if (!out || !pieces || !setup || !setup->buffers || !setup->buffer_size) return TITLE_E_ARG;
    for (i = 0; i < pieces->n; i++)
        if ((pieces->v[i].kind == PIECE_SRC && !read) || (pieces->v[i].kind == PIECE_GEN && !pieces->v[i].gen))
            return TITLE_E_ARG;
    if (setup->sync && (!setup->sync->lock || !setup->sync->unlock || !setup->sync->wait || !setup->sync->wake))
        return TITLE_E_ARG;
    *out = NULL;
    s = (Stream *)calloc(1, sizeof *s);
    if (!s) return TITLE_E_MEM;
    s->npieces = pieces->n;
    s->pieces = (Piece *)malloc((pieces->n ? pieces->n : 1) * sizeof *s->pieces);
    s->nbuf = setup->buffers;
    s->bufsize = setup->buffer_size;
    s->mem = (uint8_t *)malloc(s->nbuf * s->bufsize);
    s->due = (int *)calloc(s->nbuf, sizeof *s->due);
    s->seq = (uint64_t *)malloc(s->nbuf * sizeof *s->seq);
    s->len = (size_t *)calloc(s->nbuf, sizeof *s->len);
    if (!s->pieces || !s->mem || !s->due || !s->seq || !s->len) {
        stream_close(s);
        return TITLE_E_MEM;
    }
    if (pieces->n) memcpy(s->pieces, pieces->v, pieces->n * sizeof *s->pieces);
    for (i = 0; i < s->nbuf; i++) s->seq[i] = i;
    s->total = pieces->total;
    s->nbuffers = (s->total + s->bufsize - 1) / s->bufsize;
    s->read = read;
    s->read_ctx = read_ctx;
    if (sinks) s->sinks = *sinks;
    if (setup->sync) {
        s->sync = *setup->sync;
        s->has_sync = 1;
    }
    *out = s;
    return TITLE_OK;
}

static void lock(Stream *s) { if (s->has_sync) s->sync.lock(s->sync.ctx); }
static void unlock(Stream *s) { if (s->has_sync) s->sync.unlock(s->sync.ctx); }
static void wake(Stream *s) { if (s->has_sync) s->sync.wake(s->sync.ctx); }

static int sink_rc(int rc) { return rc < 0 ? rc : rc ? TITLE_E_IO : TITLE_OK; }

/* The hashing (1) or writing (2) stage on one buffer. */
static int run_stage(Stream *s, int stage, size_t slot) {
    uint8_t *buf = s->mem + slot * s->bufsize;
    int rc;
    if (stage == 1) return s->sinks.hash ? sink_rc(s->sinks.hash(s->sinks.hash_ctx, buf, s->len[slot])) : TITLE_OK;
    if (s->sinks.write && (rc = sink_rc(s->sinks.write(s->sinks.write_ctx, buf, s->len[slot])))) return rc;
    s->written += s->len[slot];
    if (s->sinks.progress && s->sinks.progress(s->sinks.progress_ctx, s->written, s->total)) return TITLE_E_CANCEL;
    return TITLE_OK;
}

/* With the lock held: a stage of `stages` whose next buffer is ready (the later stages first: they free buffers), or
 * -1. */
static int ready_stage(Stream *s, unsigned stages, size_t *slot) {
    int i;
    for (i = STAGES - 1; i >= 0; i--) {
        size_t k;
        if (!(stages & (1u << i)) || s->cursor[i] >= s->nbuffers) continue;
        k = (size_t)(s->cursor[i] % s->nbuf);
        if (s->due[k] == i && s->seq[k] == s->cursor[i]) {
            *slot = k;
            return i;
        }
    }
    return -1;
}

/* With the lock held: the stage done on its buffer (or failed), the buffer handed on. */
static void stage_done(Stream *s, int stage, size_t slot, int rc) {
    if (rc) {
        if (!s->rc) s->rc = rc;
    } else {
        s->cursor[stage]++;
        if (stage == STAGES - 1) {
            s->due[slot] = 0;
            s->seq[slot] += s->nbuf;
        } else {
            s->due[slot] = stage + 1;
        }
    }
    wake(s);
}

/* With the lock held: runs one ready stage of `stages` (its lock released meanwhile); 1 if one ran. */
static int run_one(Stream *s, unsigned stages) {
    size_t slot = 0;
    int stage = ready_stage(s, stages, &slot), rc;
    if (stage < 0) return 0;
    unlock(s);
    rc = run_stage(s, stage, slot);
    lock(s);
    stage_done(s, stage, slot, rc);
    return 1;
}

/* ---- the reading stage: every piece into the buffers, in order ------------------------------------------------- */

typedef struct {
    Stream *s;
    unsigned stages;            /* the calling thread's: the others it may run while it waits */
} Reader;

/* A buffer to fill: the one open, or the next once it is free. */
static int take_buffer(Reader *r) {
    Stream *s = r->s;
    uint64_t number, left;
    int rc = TITLE_OK;
    if (s->open) return TITLE_OK;
    lock(s);
    number = s->cursor[0];
    if (number >= s->nbuffers) rc = TITLE_E_SIZE;          /* more bytes than the pieces announced */
    while (!rc) {
        size_t slot = (size_t)(number % s->nbuf);
        if (s->rc) {
            rc = s->rc;
        } else if (s->due[slot] == 0 && s->seq[slot] == number) {
            s->slot = slot;
            break;
        } else if (!run_one(s, r->stages & ~(unsigned)STREAM_READ)) {
            if (!s->has_sync) rc = TITLE_E_ARG;              /* cannot happen with every stage on one thread */
            else s->sync.wait(s->sync.ctx);
        }
    }
    unlock(s);
    if (rc) return rc;
    left = s->total - number * s->bufsize;
    s->len[s->slot] = left < s->bufsize ? (size_t)left : s->bufsize;
    s->at = 0;
    s->open = 1;
    return TITLE_OK;
}

static void hand_on(Stream *s) {
    lock(s);
    stage_done(s, 0, s->slot, TITLE_OK);
    unlock(s);
    s->open = 0;
}

/* `n` bytes of one kind into the buffers: from memory, zeros, or a source. */
static int put(Reader *r, int kind, const uint8_t *mem, void *handle, uint64_t offset, uint64_t n) {
    Stream *s = r->s;
    while (n) {
        uint8_t *dst;
        size_t k;
        int rc = take_buffer(r);
        if (rc) return rc;
        k = s->len[s->slot] - s->at;
        if (k > n) k = (size_t)n;
        dst = s->mem + s->slot * s->bufsize + s->at;
        if (kind == PIECE_MEM) memcpy(dst, mem, k);
        else if (kind == PIECE_ZERO) memset(dst, 0, k);
        else if (s->read(s->read_ctx, handle, offset, dst, k)) return TITLE_E_IO;
        s->at += k;
        if (mem) mem += k;
        offset += k;
        n -= k;
        if (s->at == s->len[s->slot]) hand_on(s);
    }
    return TITLE_OK;
}

typedef struct {
    Reader *r;
    uint64_t left;
} GenOut;

static int gen_write(void *ctx, const void *buf, size_t n) {
    GenOut *g = (GenOut *)ctx;
    int rc;
    if (n > g->left) return TITLE_E_SIZE;
    if ((rc = put(g->r, PIECE_MEM, (const uint8_t *)buf, NULL, 0, n))) return rc;
    g->left -= n;
    return TITLE_OK;
}

static int read_all(Stream *s, unsigned stages) {
    Reader r;
    size_t i;
    int rc = TITLE_OK;
    r.s = s;
    r.stages = stages;
    for (i = 0; !rc && i < s->npieces; i++) {
        const Piece *p = &s->pieces[i];
        if (p->kind == PIECE_GEN) {
            TitleOut out;
            GenOut g;
            g.r = &r;
            g.left = p->len;
            memset(&out, 0, sizeof out);
            out.write = gen_write;
            out.ctx = &g;
            rc = p->gen(p->gen_ctx, p->handle, &out);
            if (!rc && g.left) rc = TITLE_E_SIZE;
        } else {
            rc = put(&r, p->kind, p->mem, p->handle, p->offset, p->len);
        }
    }
    if (!rc && (s->open || s->cursor[0] != s->nbuffers)) rc = TITLE_E_SIZE;
    return rc;
}

int stream_work(Stream *s, unsigned stages) {
    int rc;
    if (!s || !stages || (stages & ~(unsigned)STREAM_ALL)) return TITLE_E_ARG;
    if (!s->has_sync && stages != STREAM_ALL) return TITLE_E_ARG;
    lock(s);
    if (s->claimed & stages) {
        unlock(s);
        return TITLE_E_ARG;
    }
    s->claimed |= stages;
    unlock(s);
    if (stages & STREAM_READ) {
        rc = read_all(s, stages);
        if (rc) {
            lock(s);
            if (!s->rc) s->rc = rc;     /* an error of another stage stays the stream's result */
            wake(s);
            unlock(s);
        }
    }
    lock(s);
    for (;;) {
        int i, left = 0;
        if (s->rc) break;
        for (i = 1; i < STAGES; i++)
            if ((stages & (1u << i)) && s->cursor[i] < s->nbuffers) left = 1;
        if (!left) break;
        if (!run_one(s, stages & ~(unsigned)STREAM_READ)) {
            if (!s->has_sync) {
                s->rc = TITLE_E_ARG;               /* cannot happen with every stage on one thread */
                break;
            }
            s->sync.wait(s->sync.ctx);
        }
    }
    rc = s->rc;
    s->claimed &= ~stages;
    wake(s);
    unlock(s);
    return rc;
}

int stream_result(const Stream *s) {
    if (!s) return TITLE_E_ARG;
    if (s->rc) return s->rc;
    return s->cursor[STAGES - 1] == s->nbuffers && s->cursor[0] == s->nbuffers ? TITLE_OK : TITLE_E_ARG;
}

uint64_t stream_total(const Stream *s) { return s ? s->total : 0; }

void stream_close(Stream *s) {
    if (!s) return;
    free(s->pieces);
    free(s->mem);
    free(s->due);
    free(s->seq);
    free(s->len);
    free(s);
}
