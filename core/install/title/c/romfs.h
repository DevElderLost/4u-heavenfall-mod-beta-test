/* RomFS image builder, byte-identical to core/install/title/romfs_writer.py (RomfsImage): level 3 (directory and
 * file tables, file data) and the IVFC hash tree above it.
 *
 * Three steps, files never held in memory:
 *   romfs_layout   computes the layout from the file list; reads nothing.
 *   romfs_prepare  pass 1: reads every file once through the TitleRead callback and hashes level 3 in 0x1000
 *                  blocks. The level-2 hashes (32 bytes per 4 KB; ~23 MB for a 2.6 GB game) go to the caller's
 *                  HashStore, not to memory; level 1 (~160 KB) and the master hash stay in memory.
 *   romfs_stream   pass 2: writes the whole image, files read again, level 2 read back from the HashStore.
 */
#ifndef ROMFS_H
#define ROMFS_H

#include "title_io.h"

typedef struct {
    const char *path;   /* UTF-8, "/" or "\" separated, no leading slash needed */
    uint64_t offset;    /* where the file starts inside the source `handle` */
    uint64_t size;
    void *handle;       /* opaque: given back to the TitleRead callback */
} RomfsFile;

/* Where the level-2 hashes live. `append` receives them in order during romfs_prepare (a multiple of 32 bytes per
 * call); `get` reads back any range (prepare reads it sequentially, stream too). Both return 0 on success. */
typedef struct {
    int (*append)(void *ctx, const uint8_t *hashes, size_t n);
    int (*get)(void *ctx, uint64_t offset, uint8_t *buf, size_t n);
    void *ctx;
} HashStore;

/* A growing buffer in memory: the default store for tests and for small images. */
typedef struct { uint8_t *data; size_t len, cap; } HashMem;
void hashstore_mem(HashStore *store, HashMem *mem);
void hashmem_free(HashMem *mem);

/* Where the parts of an image with `level3_size` bytes of level 3 go (romfs_writer.py, HashTree): the IVFC header and
 * master hash, level 3, level 1, level 2, each from a 0x1000 boundary; the game's own RomFS has this form too. */
#define ROMFS_BLOCK 0x1000u
#define ROMFS_HASH 32u
#define ROMFS_MASTER_AT 0x60u
typedef struct {
    uint64_t level3_size, l2_size, l1_size;
    uint32_t master_size, hash_region_size;
    uint64_t l3_start, l1_start, l2_start, size;
} RomfsTree;
void romfs_tree(RomfsTree *t, uint64_t level3_size);
/* The IVFC header, zero padded to the master hash. */
void romfs_ivfc_header(const RomfsTree *t, uint8_t out[ROMFS_MASTER_AT]);
/* SHA-256 of each 0x1000 block of data[0..n) (the last zero padded) into out. */
void romfs_hash_blocks(const uint8_t *data, uint64_t n, uint8_t *out);

/* The level-3 header and four tables of a file list (romfs_writer.py, level3_tables). A file whose fixed[i] is not
 * ROMFS_APPEND keeps that data offset; the others get offsets from append_at on, in the tables' order (folders in
 * pre-order, names sorted), each at 0x10, and are listed in `order` (indices into the list). `fixed` may be NULL. */
#define ROMFS_APPEND UINT64_MAX
typedef struct {
    uint8_t *tables;        /* the header (data offset 0) and the tables */
    uint32_t tables_len;
    size_t *order;          /* the appended files, in data order */
    size_t norder;
    uint64_t data_end;      /* where the appended data ends, its last file padded to 0x10 */
} RomfsTables;
int romfs_tables(RomfsTables *t, const RomfsFile *files, size_t count, const uint64_t *fixed, uint64_t append_at);
/* The tables with the header's data offset set, zero padded to `size` bytes, in a new buffer (free()). */
int romfs_tables_place(const RomfsTables *t, uint32_t data_off, uint64_t size, uint8_t **out);
void romfs_tables_free(RomfsTables *t);

typedef struct RomfsImage RomfsImage;

int romfs_layout(RomfsImage **out, const RomfsFile *files, size_t count, TitleRead read, void *read_ctx);
int romfs_prepare(RomfsImage *im, const HashStore *store, TitleProgress progress, void *progress_ctx);
uint64_t romfs_size(const RomfsImage *im);               /* bytes of the whole image */
uint64_t romfs_level3_size(const RomfsImage *im);
uint32_t romfs_hash_region_size(const RomfsImage *im);   /* bytes the NCCH's RomFS superblock hash covers */
/* SHA-256 of the first hash_region_size bytes of the image (valid after prepare). */
int romfs_region_hash(const RomfsImage *im, uint8_t out[32]);
int romfs_stream(RomfsImage *im, const TitleOut *out);
void romfs_free(RomfsImage *im);

#endif
