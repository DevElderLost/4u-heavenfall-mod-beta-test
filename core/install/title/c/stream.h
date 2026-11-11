/* A stream of bytes made of pieces (memory, a range of a source, zeros, or bytes a generator makes as they stream) that
 * goes through three stages over a ring of large buffers: reading (the pieces into the buffers, in order), hashing (a
 * callback on every buffer, in order) and writing (a TitleWrite, then the progress callback). The stages can run on different threads, which the caller supplies with
 * its own lock and condition (StreamSync): one thread may run several stages, each stage runs on one thread. Without
 * a StreamSync everything runs on the calling thread (stream_work with STREAM_ALL), which the PC tests use. Portable
 * C99. */
#ifndef STREAM_H
#define STREAM_H

#include "title_io.h"

enum { PIECE_MEM = 0, PIECE_SRC = 1, PIECE_ZERO = 2, PIECE_GEN = 3 };

/* A generated piece's maker: pushes exactly the piece's bytes, in order, through out->write (out->progress is NULL) and
 * returns 0 or an error code. It runs on the reading stage's thread, which waits inside out->write while the ring is
 * full (or runs the other stages it holds), so a file a patch set's applier makes never needs a copy on the card. */
typedef int (*PieceGen)(void *ctx, void *handle, const TitleOut *out);

typedef struct {
    int kind;
    const uint8_t *mem;      /* PIECE_MEM: must outlive the stream */
    void *handle;            /* PIECE_SRC: given to the TitleRead callback; PIECE_GEN: to the generator */
    uint64_t offset;         /* PIECE_SRC */
    uint64_t len;
    PieceGen gen;            /* PIECE_GEN */
    void *gen_ctx;
} Piece;

typedef struct {
    Piece *v;
    size_t n, cap;
    uint64_t total;          /* bytes of all the pieces */
} PieceList;

int pieces_mem(PieceList *l, const void *mem, uint64_t len);
int pieces_src(PieceList *l, void *handle, uint64_t offset, uint64_t len);
int pieces_zero(PieceList *l, uint64_t len);
int pieces_gen(PieceList *l, PieceGen gen, void *gen_ctx, void *handle, uint64_t len);
void pieces_free(PieceList *l);

/* The caller's lock and condition variable. `wait` is called with the lock held: it releases it, sleeps until a
 * `wake`, and takes it again (a spurious wake-up is fine). `wake` is called with the lock held and wakes every
 * waiter. */
typedef struct {
    void (*lock)(void *ctx);
    void (*unlock)(void *ctx);
    void (*wait)(void *ctx);
    void (*wake)(void *ctx);
    void *ctx;
} StreamSync;

/* A hash or write callback's nonzero return stops the stream: a negative one (a TITLE_E_* code) becomes the stream's
 * result, a positive one TITLE_E_IO. */
typedef struct {
    int (*hash)(void *ctx, const uint8_t *buf, size_t n);   /* the hashing stage; NULL: none */
    void *hash_ctx;
    TitleWrite write;                                        /* the writing stage; NULL: none */
    void *write_ctx;
    TitleProgress progress;                                  /* after each buffer is written; NULL: none */
    void *progress_ctx;
} StreamSinks;

typedef struct {
    size_t buffers;          /* at least 1; 3 or 4 keep three threads busy */
    size_t buffer_size;      /* bytes per buffer; a multiple of 0x200 (the SD card's sector) works best */
    const StreamSync *sync;  /* NULL: one thread runs all the stages */
} StreamSetup;

enum { STREAM_READ = 1, STREAM_HASH = 2, STREAM_WRITE = 4, STREAM_ALL = 7 };

typedef struct Stream Stream;

/* The pieces are copied; their memory is not. */
int stream_open(Stream **out, const PieceList *pieces, TitleRead read, void *read_ctx, const StreamSinks *sinks,
                const StreamSetup *setup);
/* Runs the `stages` until the stream ends, fails or is cancelled; returns the stream's result. Without a StreamSync
 * `stages` must be STREAM_ALL. A stage claimed by another call is TITLE_E_ARG. The reading stage goes through all the
 * pieces at once, waiting for a free buffer (or running the other stages the same call holds) when the ring is full. */
int stream_work(Stream *s, unsigned stages);
int stream_result(const Stream *s);
uint64_t stream_total(const Stream *s);
void stream_close(Stream *s);

#endif
