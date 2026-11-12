/* See kept.h. Mirrors core/install/title/kept_romfs.py step by step. */
#include "kept.h"

#include <stdlib.h>
#include <string.h>

#include "sha256.h"

#define BLOCK ROMFS_BLOCK
#define HASH ROMFS_HASH
#define L2_PER_L1 (BLOCK / HASH)
#define FILE_ALIGN 0x10u
#define LEVEL3_HEADER 0x28u
#define SUPERBLOCK_HASH 0x1E0u

struct KeptRomfs {
    TitleRead read;
    void *read_ctx;
    void *dump;                 /* the dump's handle */
    uint64_t start;             /* the game's RomFS in the dump */
    RomfsTree game;             /* the dump's levels */
    uint32_t game_data_off;
    uint64_t shift;
    RomfsTree tree;             /* the new image's */
    uint8_t *metadata;          /* `shift` bytes: the header and tables */
    RomfsFile *tail;            /* the mod's files, in data order */
    size_t ntail, nfiles;
    uint64_t copied_l2, copied_l1;
    uint8_t *head;              /* the image's first l3_start bytes: IVFC header, master hash, zeros */
    uint8_t *l2_head;           /* the tables' level-2 hashes: shift / 4 KB of them */
    uint8_t *game_l1;           /* the dump's level 1 */
    uint8_t *seam_l2;           /* the dump's level-2 hashes [copied_l1 * 128, copied_l2) */
    uint8_t *l2_tail;           /* the seam's and the mod's level-2 hashes */
    uint64_t l2_tail_len, l2_tail_cap;
    uint8_t block[BLOCK];       /* the seam hasher's partial block */
    size_t fill;
    uint8_t *l1;
    uint8_t *master;
    PieceGen gen;               /* the mod's files made as they stream, or NULL: read */
    void *gen_ctx;
    int tail_given;             /* l2_tail came from the build data */
    int begun, finished;
    int fresh;                  /* kept_open_fresh: no game; `metadata` is `meta_len` bytes, the seam all of level 3 */
    uint64_t meta_len;
};

static int cmp_path(const void *a, const void *b) {
    return strcmp((*(const RomfsFile *const *)a)->path, (*(const RomfsFile *const *)b)->path);
}

static int in_mod(const RomfsFile *const *sorted, size_t n, const char *path) {
    RomfsFile key;
    const RomfsFile *k = &key;
    key.path = path;
    return n && bsearch(&k, sorted, n, sizeof *sorted, cmp_path) != NULL;
}

/* The dump's RomFS: its header region checked against the NCCH header's hash, the levels in the game's form. */
static int read_game(KeptRomfs *k, const Dump *d) {
    uint8_t region[BLOCK], expect[ROMFS_MASTER_AT], hash[32], l3[LEVEL3_HEADER];
    uint32_t region_size = get_le32(d->header + 0x1B8) * MEDIA_UNIT;
    uint64_t romfs_size = (uint64_t)get_le32(d->header + 0x1B4) * MEDIA_UNIT;
    uint64_t level3_size;
    k->start = d->ncch_offset + (uint64_t)get_le32(d->header + 0x1B0) * MEDIA_UNIT;
    if (!romfs_size || region_size < ROMFS_MASTER_AT || region_size > BLOCK) return TITLE_E_FORMAT;
    if (k->read(k->read_ctx, k->dump, k->start, region, region_size)) return TITLE_E_IO;
    sha256_buf(region, region_size, hash);
    if (memcmp(hash, d->header + SUPERBLOCK_HASH, 32)) return TITLE_E_HASH;
    level3_size = (uint64_t)get_le32(region + 0x44) | (uint64_t)get_le32(region + 0x48) << 32;
    romfs_tree(&k->game, level3_size);
    romfs_ivfc_header(&k->game, expect);
    if (memcmp(region, expect, ROMFS_MASTER_AT) || region_size != k->game.hash_region_size) return TITLE_E_FORMAT;
    if (romfs_size < k->game.size) return TITLE_E_FORMAT;
    if (k->read(k->read_ctx, k->dump, k->start + k->game.l3_start, l3, sizeof l3)) return TITLE_E_IO;
    k->game_data_off = get_le32(l3 + 36);
    if (get_le32(l3) != LEVEL3_HEADER || (uint64_t)get_le32(l3 + 28) + get_le32(l3 + 32) > k->game_data_off ||
        k->game_data_off > level3_size)
        return TITLE_E_FORMAT;
    return TITLE_OK;
}

int kept_open(KeptRomfs **out, const Dump *d, const RomfsFile *mod, size_t nmod, TitleRead read, void *read_ctx) {
    KeptRomfs *k;
    const RomfsFile **sorted = NULL;
    RomfsFile *all = NULL;
    uint64_t *fixed = NULL, data_start, game_l3, l2_tail_count;
    RomfsTables t;
    size_t i, n = 0;
    int rc;
    if (!out || !d || !read || (nmod && !mod) || !d->handle) return TITLE_E_ARG;
    *out = NULL;
    memset(&t, 0, sizeof t);
    k = (KeptRomfs *)calloc(1, sizeof *k);
    if (!k) return TITLE_E_MEM;
    k->read = read;
    k->read_ctx = read_ctx;
    k->dump = d->handle;
    if ((rc = read_game(k, d))) goto fail;
    rc = TITLE_E_MEM;
    sorted = (const RomfsFile **)malloc((nmod ? nmod : 1) * sizeof *sorted);
    all = (RomfsFile *)malloc((d->nfiles + nmod + 1) * sizeof *all);
    fixed = (uint64_t *)malloc((d->nfiles + nmod + 1) * sizeof *fixed);
    if (!sorted || !all || !fixed) goto fail;
    for (i = 0; i < nmod; i++) sorted[i] = &mod[i];
    qsort(sorted, nmod, sizeof *sorted, cmp_path);
    data_start = k->start + k->game.l3_start + k->game_data_off;
    for (i = 0; i < d->nfiles; i++) {
        if (in_mod(sorted, nmod, d->files[i].path)) continue;     /* the mod's file wins */
        if (d->files[i].offset < data_start) { rc = TITLE_E_FORMAT; goto fail; }
        all[n] = d->files[i];
        fixed[n++] = d->files[i].offset - data_start;
    }
    for (i = 0; i < nmod; i++) {
        all[n] = mod[i];
        fixed[n++] = ROMFS_APPEND;
    }
    game_l3 = k->game.level3_size;
    if ((rc = romfs_tables(&t, all, n, fixed, title_align(game_l3, FILE_ALIGN) - k->game_data_off))) goto fail;
    rc = TITLE_E_MEM;
    k->nfiles = n;
    k->shift = title_align(t.tables_len, KEPT_SHIFT_UNIT);
    if ((rc = romfs_tables_place(&t, (uint32_t)(k->shift + k->game_data_off), k->shift, &k->metadata))) goto fail;
    rc = TITLE_E_MEM;
    k->tail = (RomfsFile *)malloc((t.norder ? t.norder : 1) * sizeof *k->tail);
    if (!k->tail) goto fail;
    for (i = 0; i < t.norder; i++) k->tail[i] = all[t.order[i]];
    k->ntail = t.norder;
    romfs_tree(&k->tree, k->shift + k->game_data_off + t.data_end);
    k->copied_l2 = game_l3 / BLOCK;
    k->copied_l1 = game_l3 / KEPT_SHIFT_UNIT;
    l2_tail_count = k->tree.l2_size / HASH - k->shift / BLOCK - k->copied_l2;
    k->l2_tail_cap = l2_tail_count * HASH;
    k->l2_tail = (uint8_t *)malloc(k->l2_tail_cap ? (size_t)k->l2_tail_cap : 1);
    k->head = (uint8_t *)calloc((size_t)k->tree.l3_start, 1);
    if (!k->l2_tail || !k->head) goto fail;
    *out = k;
    k = NULL;
    rc = TITLE_OK;
fail:
    romfs_tables_free(&t);
    free(sorted);
    free(all);
    free(fixed);
    kept_free(k);
    return rc;
}

int kept_open_fresh(KeptRomfs **out, const RomfsFile *mod, size_t nmod, TitleRead read, void *read_ctx) {
    KeptRomfs *k;
    RomfsTables t;
    size_t i;
    int rc;
    if (!out || !read || (nmod && !mod)) return TITLE_E_ARG;
    *out = NULL;
    memset(&t, 0, sizeof t);
    k = (KeptRomfs *)calloc(1, sizeof *k);
    if (!k) return TITLE_E_MEM;
    k->read = read;
    k->read_ctx = read_ctx;
    k->fresh = 1;
    if ((rc = romfs_tables(&t, mod, nmod, NULL, 0))) goto fail;
    k->nfiles = nmod;
    k->meta_len = title_align(t.tables_len, FILE_ALIGN);
    if ((rc = romfs_tables_place(&t, (uint32_t)k->meta_len, k->meta_len, &k->metadata))) goto fail;
    rc = TITLE_E_MEM;
    k->tail = (RomfsFile *)malloc((t.norder ? t.norder : 1) * sizeof *k->tail);
    if (!k->tail) goto fail;
    for (i = 0; i < t.norder; i++) k->tail[i] = mod[t.order[i]];
    k->ntail = t.norder;
    romfs_tree(&k->tree, k->meta_len + t.data_end);
    k->l2_tail_cap = k->tree.l2_size;
    k->l2_tail = (uint8_t *)malloc(k->l2_tail_cap ? (size_t)k->l2_tail_cap : 1);
    k->head = (uint8_t *)calloc((size_t)k->tree.l3_start, 1);
    if (!k->l2_tail || !k->head) goto fail;
    *out = k;
    k = NULL;
    rc = TITLE_OK;
fail:
    romfs_tables_free(&t);
    kept_free(k);
    return rc;
}

int kept_begin(KeptRomfs *k) {
    uint8_t *master = NULL, *check = NULL;
    uint64_t first, n;
    int rc = TITLE_E_MEM;
    if (!k) return TITLE_E_ARG;
    if (k->begun) return TITLE_OK;
    if (k->fresh) {             /* no game: nothing to read, no table blocks apart from the seam */
        k->begun = 1;
        return TITLE_OK;
    }
    first = k->copied_l1 * L2_PER_L1;
    n = (k->copied_l2 - first) * HASH;
    master = (uint8_t *)malloc(k->game.master_size);
    check = (uint8_t *)malloc(k->game.master_size);
    k->game_l1 = (uint8_t *)malloc((size_t)k->game.l1_size);
    k->seam_l2 = (uint8_t *)malloc(n ? (size_t)n : 1);
    k->l2_head = (uint8_t *)malloc((size_t)(k->shift / BLOCK * HASH));
    if (!master || !check || !k->game_l1 || !k->seam_l2 || !k->l2_head) goto done;
    rc = TITLE_E_IO;
    if (k->read(k->read_ctx, k->dump, k->start + ROMFS_MASTER_AT, master, k->game.master_size) ||
        k->read(k->read_ctx, k->dump, k->start + k->game.l1_start, k->game_l1, (size_t)k->game.l1_size) ||
        (n && k->read(k->read_ctx, k->dump, k->start + k->game.l2_start + first * HASH, k->seam_l2, (size_t)n)))
        goto done;
    romfs_hash_blocks(k->game_l1, k->game.l1_size, check);
    rc = TITLE_E_HASH;
    if (memcmp(check, master, k->game.master_size)) goto done;
    romfs_hash_blocks(k->metadata, k->shift, k->l2_head);
    k->begun = 1;
    rc = TITLE_OK;
done:
    free(master);
    free(check);
    return rc;
}

/* A mod file's bytes: read, or made as they stream. */
static int tail_piece(const KeptRomfs *k, PieceList *l, const RomfsFile *f) {
    int rc = k->gen ? pieces_gen(l, k->gen, k->gen_ctx, f->handle, f->size)
                    : pieces_src(l, f->handle, f->offset, f->size);
    return rc ? rc : pieces_zero(l, title_align(f->size, FILE_ALIGN) - f->size);
}

void kept_set_gen(KeptRomfs *k, PieceGen gen, void *gen_ctx) {
    if (!k) return;
    k->gen = gen;
    k->gen_ctx = gen_ctx;
}

int kept_use_tail(KeptRomfs *k, const uint8_t *hashes, size_t n) {
    if (!k || (n && !hashes) || k->begun) return TITLE_E_ARG;
    if ((uint64_t)n * HASH != k->l2_tail_cap) return TITLE_E_HASH;
    memcpy(k->l2_tail, hashes, (size_t)k->l2_tail_cap);
    k->l2_tail_len = k->l2_tail_cap;
    k->tail_given = 1;
    return TITLE_OK;
}

int kept_seam_pieces(const KeptRomfs *k, PieceList *l) {
    uint64_t at, game_l3;
    size_t i;
    int rc;
    if (!k || !l) return TITLE_E_ARG;
    if (k->tail_given) return TITLE_OK;         /* the build data gave its hashes: nothing to read */
    if (k->fresh && (rc = pieces_mem(l, k->metadata, k->meta_len))) return rc;
    game_l3 = k->fresh ? 0 : k->game.level3_size;
    at = k->copied_l2 * BLOCK;
    if (!k->fresh && ((rc = pieces_src(l, k->dump, k->start + k->game.l3_start + at, game_l3 - at)) ||
                      (rc = pieces_zero(l, title_align(game_l3, FILE_ALIGN) - game_l3))))
        return rc;
    for (i = 0; i < k->ntail; i++)
        if ((rc = tail_piece(k, l, &k->tail[i]))) return rc;
    return TITLE_OK;
}

static int push_hash(KeptRomfs *k, const uint8_t *block) {
    if (k->l2_tail_len + HASH > k->l2_tail_cap) return 1;
    sha256_buf(block, BLOCK, k->l2_tail + k->l2_tail_len);
    k->l2_tail_len += HASH;
    return 0;
}

int kept_seam_hash(void *ctx, const uint8_t *buf, size_t n) {
    KeptRomfs *k = (KeptRomfs *)ctx;
    while (n) {
        if (!k->fill && n >= BLOCK) {
            if (push_hash(k, buf)) return 1;
            buf += BLOCK;
            n -= BLOCK;
        } else {
            size_t take = BLOCK - k->fill < n ? BLOCK - k->fill : n;
            memcpy(k->block + k->fill, buf, take);
            k->fill += take;
            buf += take;
            n -= take;
            if (k->fill == BLOCK) {
                k->fill = 0;
                if (push_hash(k, k->block)) return 1;
            }
        }
    }
    return 0;
}

/* SHA-256 of each 0x1000 block of a then b, joined (the last block zero padded), into out. */
static void hash_joined(const uint8_t *a, uint64_t alen, const uint8_t *b, uint64_t blen, uint8_t *out) {
    uint8_t block[BLOCK];
    uint64_t at, total = alen + blen;
    for (at = 0; at < total; at += BLOCK, out += HASH) {
        uint64_t end = at + BLOCK < total ? at + BLOCK : total, p;
        memset(block, 0, BLOCK);
        for (p = at; p < end;) {
            uint64_t k;
            if (p < alen) {
                k = (alen < end ? alen : end) - p;
                memcpy(block + (p - at), a + p, (size_t)k);
            } else {
                k = end - p;
                memcpy(block + (p - at), b + (p - alen), (size_t)k);
            }
            p += k;
        }
        sha256_buf(block, BLOCK, out);
    }
}

int kept_finish(KeptRomfs *k) {
    uint64_t j0, seam_n;
    if (!k || !k->begun) return TITLE_E_ARG;
    if (k->finished) return TITLE_OK;
    if (k->fill) {
        memset(k->block + k->fill, 0, BLOCK - k->fill);
        k->fill = 0;
        if (push_hash(k, k->block)) return TITLE_E_SIZE;
    }
    if (k->l2_tail_len != k->l2_tail_cap) return TITLE_E_SIZE;
    k->l1 = (uint8_t *)malloc(k->tree.l1_size ? (size_t)k->tree.l1_size : 1);
    k->master = (uint8_t *)malloc(k->tree.master_size);
    if (!k->l1 || !k->master) return TITLE_E_MEM;
    j0 = k->shift / KEPT_SHIFT_UNIT;
    if (k->shift) romfs_hash_blocks(k->l2_head, k->shift / BLOCK * HASH, k->l1);
    if (k->copied_l1) memcpy(k->l1 + j0 * HASH, k->game_l1, (size_t)(k->copied_l1 * HASH));
    seam_n = (k->copied_l2 - k->copied_l1 * L2_PER_L1) * HASH;
    if ((j0 + k->copied_l1) * HASH + (seam_n + k->l2_tail_len + BLOCK - 1) / BLOCK * HASH != k->tree.l1_size)
        return TITLE_E_SIZE;
    hash_joined(k->seam_l2, seam_n, k->l2_tail, k->l2_tail_len, k->l1 + (j0 + k->copied_l1) * HASH);
    romfs_hash_blocks(k->l1, k->tree.l1_size, k->master);
    romfs_ivfc_header(&k->tree, k->head);
    memcpy(k->head + ROMFS_MASTER_AT, k->master, k->tree.master_size);
    k->finished = 1;
    return TITLE_OK;
}

int kept_prepare(KeptRomfs *k, const StreamSetup *setup, TitleProgress progress, void *progress_ctx) {
    PieceList l;
    StreamSinks sinks;
    StreamSetup one;
    Stream *s = NULL;
    int rc;
    if (!k || !setup) return TITLE_E_ARG;
    if ((rc = kept_begin(k))) return rc;
    if (k->finished) return TITLE_OK;
    memset(&l, 0, sizeof l);
    memset(&sinks, 0, sizeof sinks);
    sinks.hash = kept_seam_hash;
    sinks.hash_ctx = k;
    sinks.progress = progress;
    sinks.progress_ctx = progress_ctx;
    one = *setup;
    one.sync = NULL;
    rc = kept_seam_pieces(k, &l);
    if (!rc) rc = stream_open(&s, &l, k->read, k->read_ctx, &sinks, &one);
    if (!rc) rc = stream_work(s, STREAM_ALL);
    stream_close(s);
    pieces_free(&l);
    return rc ? rc : kept_finish(k);
}

uint64_t kept_size(const KeptRomfs *k) { return k->tree.size; }
uint32_t kept_hash_region_size(const KeptRomfs *k) { return k->tree.hash_region_size; }
uint64_t kept_shift(const KeptRomfs *k) { return k->shift; }
size_t kept_file_count(const KeptRomfs *k) { return k->nfiles; }

int kept_region_hash(const KeptRomfs *k, uint8_t out[32]) {
    if (!k || !k->finished) return TITLE_E_ARG;
    sha256_buf(k->head, k->tree.hash_region_size, out);    /* l3_start >= hash_region_size bytes, zero padded */
    return TITLE_OK;
}

int kept_pieces(const KeptRomfs *k, PieceList *l) {
    const RomfsTree *t;
    uint64_t game_l3;
    size_t i;
    int rc;
    if (!k || !l || !k->finished) return TITLE_E_ARG;
    t = &k->tree;
    if (k->fresh) {             /* header, the tables, the files, level 1, level 2 (romfs_writer.py RomfsImage) */
        if ((rc = pieces_mem(l, k->head, t->l3_start)) || (rc = pieces_mem(l, k->metadata, k->meta_len))) return rc;
        for (i = 0; i < k->ntail; i++)
            if ((rc = tail_piece(k, l, &k->tail[i]))) return rc;
        if ((rc = pieces_zero(l, t->l1_start - t->l3_start - t->level3_size)) ||
            (rc = pieces_mem(l, k->l1, t->l1_size)) || (rc = pieces_zero(l, t->l2_start - t->l1_start - t->l1_size)) ||
            (rc = pieces_mem(l, k->l2_tail, k->l2_tail_len)) ||
            (rc = pieces_zero(l, t->size - t->l2_start - t->l2_size)))
            return rc;
        return TITLE_OK;
    }
    game_l3 = k->game.level3_size;
    if ((rc = pieces_mem(l, k->head, t->l3_start)) || (rc = pieces_mem(l, k->metadata, k->shift)) ||
        (rc = pieces_src(l, k->dump, k->start + k->game.l3_start, game_l3)) ||
        (rc = pieces_zero(l, title_align(game_l3, FILE_ALIGN) - game_l3)))
        return rc;
    for (i = 0; i < k->ntail; i++)
        if ((rc = tail_piece(k, l, &k->tail[i]))) return rc;
    if ((rc = pieces_zero(l, t->l1_start - t->l3_start - t->level3_size)) ||
        (rc = pieces_mem(l, k->l1, t->l1_size)) || (rc = pieces_zero(l, t->l2_start - t->l1_start - t->l1_size)) ||
        (rc = pieces_mem(l, k->l2_head, k->shift / BLOCK * HASH)) ||
        (rc = pieces_src(l, k->dump, k->start + k->game.l2_start, k->copied_l2 * HASH)) ||
        (rc = pieces_mem(l, k->l2_tail, k->l2_tail_len)) ||
        (rc = pieces_zero(l, t->size - t->l2_start - t->l2_size)))
        return rc;
    return TITLE_OK;
}

uint64_t kept_tail_start(const KeptRomfs *k) { return k->tree.l3_start + k->shift + k->copied_l2 * BLOCK; }

const uint8_t *kept_tail_hashes(const KeptRomfs *k, size_t *n) {
    if (n) *n = (size_t)(k->l2_tail_len / HASH);
    return k->l2_tail;
}

void kept_free(KeptRomfs *k) {
    if (!k) return;
    free(k->metadata);
    free(k->tail);
    free(k->head);
    free(k->l2_head);
    free(k->game_l1);
    free(k->seam_l2);
    free(k->l2_tail);
    free(k->l1);
    free(k->master);
    free(k);
}
