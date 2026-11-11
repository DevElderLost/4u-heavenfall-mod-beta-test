/* RomFS image builder; see romfs.h. Mirrors core/install/title/romfs_writer.py step by step. */
#include "romfs.h"

#include <stdlib.h>
#include <string.h>

#include "sha256.h"

#define NONE 0xFFFFFFFFu
#define BLOCK 0x1000u
#define HASH_SIZE 32u
#define MASTER_HASH_OFFSET 0x60u
#define HASH_REGION_ALIGN 0x200u
#define FILE_ALIGN 0x10u
#define HEADER_SIZE 0x28u
#define READ_CHUNK 0x40000u

typedef struct {
    char *name;
    uint16_t *u16;
    uint32_t n16;
    int32_t parent;
    uint32_t offset, first_child, nchild, first_file, nfile, pos;
} Dn;

typedef struct {
    char *name;
    uint16_t *u16;
    uint32_t n16;
    uint32_t dir, meta;
    size_t src;
    uint64_t data;
} Fn;

struct RomfsImage {
    uint8_t *metadata;
    uint64_t metadata_len;
    uint64_t level3_size, l1_size, l2_size, size;
    uint32_t master_size, hash_region_size;
    uint64_t l3_start, l1_start, l2_start;
    RomfsFile *data;          /* in data order */
    size_t ndata;
    TitleRead read;
    void *read_ctx;
    uint8_t *scratch;
    uint8_t *l1, *master;
    HashStore store;
    int prepared;
};

static const uint8_t ZEROS[BLOCK];

int title_write_zeros(const TitleOut *out, uint64_t n) {
    while (n) {
        size_t k = n < sizeof ZEROS ? (size_t)n : sizeof ZEROS;
        if (out->write(out->ctx, ZEROS, k)) return TITLE_E_IO;
        n -= k;
    }
    return TITLE_OK;
}

/* ---- hash store in memory ------------------------------------------------------------------------------------ */

static int mem_append(void *ctx, const uint8_t *h, size_t n) {
    HashMem *m = (HashMem *)ctx;
    if (m->len + n > m->cap) {
        size_t cap = m->cap ? m->cap : 4096;
        uint8_t *p;
        while (cap < m->len + n) cap *= 2;
        p = (uint8_t *)realloc(m->data, cap);
        if (!p) return 1;
        m->data = p; m->cap = cap;
    }
    memcpy(m->data + m->len, h, n);
    m->len += n;
    return 0;
}

static int mem_get(void *ctx, uint64_t off, uint8_t *buf, size_t n) {
    HashMem *m = (HashMem *)ctx;
    if (off + n > m->len) return 1;
    memcpy(buf, m->data + off, n);
    return 0;
}

void hashstore_mem(HashStore *store, HashMem *mem) {
    memset(mem, 0, sizeof *mem);
    store->append = mem_append; store->get = mem_get; store->ctx = mem;
}

void hashmem_free(HashMem *mem) { free(mem->data); memset(mem, 0, sizeof *mem); }

/* ---- the hash tree's layout --------------------------------------------------------------------------------- */

void romfs_tree(RomfsTree *t, uint64_t level3_size) {
    t->level3_size = level3_size;
    t->l2_size = (level3_size + BLOCK - 1) / BLOCK * HASH_SIZE;
    t->l1_size = (t->l2_size + BLOCK - 1) / BLOCK * HASH_SIZE;
    t->master_size = (uint32_t)((t->l1_size + BLOCK - 1) / BLOCK * HASH_SIZE);
    t->hash_region_size = (uint32_t)title_align(MASTER_HASH_OFFSET + t->master_size, HASH_REGION_ALIGN);
    t->l3_start = title_align(MASTER_HASH_OFFSET + t->master_size, BLOCK);
    t->l1_start = t->l3_start + title_align(level3_size, BLOCK);
    t->l2_start = t->l1_start + title_align(t->l1_size, BLOCK);
    t->size = t->l2_start + title_align(t->l2_size, BLOCK);
}

void romfs_ivfc_header(const RomfsTree *t, uint8_t out[ROMFS_MASTER_AT]) {
    uint64_t l2_logical = title_align(t->l1_size, BLOCK), l3_logical = title_align(l2_logical + t->l2_size, BLOCK);
    memset(out, 0, ROMFS_MASTER_AT);
    memcpy(out, "IVFC", 4);
    put_le32(out + 4, 0x10000); put_le32(out + 8, t->master_size);
    put_le64(out + 12, 0); put_le64(out + 20, t->l1_size); put_le32(out + 28, 12);
    put_le64(out + 36, l2_logical); put_le64(out + 44, t->l2_size); put_le32(out + 52, 12);
    put_le64(out + 60, l3_logical); put_le64(out + 68, t->level3_size); put_le32(out + 76, 12);
    put_le32(out + 84, 0x5C);
}

void romfs_hash_blocks(const uint8_t *data, uint64_t n, uint8_t *out) {
    uint64_t at;
    uint8_t last[BLOCK];
    for (at = 0; at < n; at += BLOCK, out += HASH_SIZE) {
        if (n - at >= BLOCK) {
            sha256_buf(data + at, BLOCK, out);
        } else {
            memset(last, 0, BLOCK);
            memcpy(last, data + at, (size_t)(n - at));
            sha256_buf(last, BLOCK, out);
        }
    }
}

/* ---- names and hashes ---------------------------------------------------------------------------------------- */

static uint32_t bucket_count(uint32_t entries) {
    static const uint32_t primes[] = {2, 3, 5, 7, 11, 13, 17};
    uint32_t n = entries;
    if (entries < 3) return 3;
    if (entries < 19) return entries | 1;
    for (;;) {
        int bad = 0, i;
        for (i = 0; i < 7; i++) if (n % primes[i] == 0) bad = 1;
        if (!bad) return n;
        n++;
    }
}

static uint32_t name_hash(uint32_t parent, const uint16_t *u16, uint32_t n16, uint32_t buckets) {
    uint32_t h = parent ^ 123456789u, i;
    for (i = 0; i < n16; i++) {
        h = (h >> 5) | (h << 27);
        h ^= u16[i];
    }
    return h % buckets;
}

/* UTF-8 -> UTF-16 code units; 0 on success. */
static int to_utf16(const char *s, size_t len, uint16_t **out, uint32_t *n16) {
    uint16_t *u = (uint16_t *)malloc((len + 1) * sizeof *u);
    const uint8_t *p = (const uint8_t *)s;
    size_t i = 0, k;
    uint32_t n = 0;
    if (!u) return TITLE_E_MEM;
    while (i < len) {
        uint32_t c = p[i], extra;
        if (c < 0x80) extra = 0;
        else if ((c & 0xE0) == 0xC0) { c &= 0x1F; extra = 1; }
        else if ((c & 0xF0) == 0xE0) { c &= 0x0F; extra = 2; }
        else if ((c & 0xF8) == 0xF0) { c &= 0x07; extra = 3; }
        else { free(u); return TITLE_E_PATH; }
        if (i + extra >= len) { free(u); return TITLE_E_PATH; }
        for (k = 1; k <= extra; k++) {
            if ((p[i + k] & 0xC0) != 0x80) { free(u); return TITLE_E_PATH; }
            c = c << 6 | (p[i + k] & 0x3F);
        }
        i += extra + 1;
        if (c >= 0x10000) {
            c -= 0x10000;
            u[n++] = (uint16_t)(0xD800 | (c >> 10));
            u[n++] = (uint16_t)(0xDC00 | (c & 0x3FF));
        } else {
            u[n++] = (uint16_t)c;
        }
    }
    *out = u; *n16 = n;
    return TITLE_OK;
}

static uint32_t name_size(uint32_t n16) { return (uint32_t)title_align(2u * n16, 4); }

/* ---- sorting (merge sort of indices with a context comparator) ----------------------------------------------- */

typedef int (*Cmp)(const void *ctx, uint32_t a, uint32_t b);

static void msort(uint32_t *v, uint32_t *tmp, size_t n, Cmp cmp, const void *ctx) {
    size_t mid, i, j, k;
    if (n < 2) return;
    mid = n / 2;
    msort(v, tmp, mid, cmp, ctx);
    msort(v + mid, tmp, n - mid, cmp, ctx);
    i = 0; j = mid; k = 0;
    while (i < mid && j < n) tmp[k++] = cmp(ctx, v[j], v[i]) < 0 ? v[j++] : v[i++];
    while (i < mid) tmp[k++] = v[i++];
    while (j < n) tmp[k++] = v[j++];
    memcpy(v, tmp, n * sizeof *v);
}

typedef struct { const Dn *dn; const Fn *fn; } Ctx;

static int cmp_dirs(const void *c, uint32_t a, uint32_t b) {
    const Dn *d = ((const Ctx *)c)->dn;
    if (d[a].parent != d[b].parent) return d[a].parent < d[b].parent ? -1 : 1;
    return strcmp(d[a].name, d[b].name);
}

static int cmp_files(const void *c, uint32_t a, uint32_t b) {
    const Fn *f = ((const Ctx *)c)->fn;
    if (f[a].dir != f[b].dir) return f[a].dir < f[b].dir ? -1 : 1;
    return strcmp(f[a].name, f[b].name);
}

/* ---- layout -------------------------------------------------------------------------------------------------- */

static void free_nodes(Dn *dn, size_t nd, Fn *fn, size_t nf) {
    size_t i;
    for (i = 0; i < nd; i++) { free(dn[i].name); free(dn[i].u16); }
    for (i = 0; i < nf; i++) { free(fn[i].name); free(fn[i].u16); }
    free(dn); free(fn);
}

/* Directory `parent`'s child called name[0..len), created when absent. Returns its index or -1. */
static int32_t find_dir(Dn **dn, size_t *nd, size_t *cap, int32_t parent, const char *name, size_t len) {
    size_t i;
    Dn *n;
    for (i = 1; i < *nd; i++)
        if ((*dn)[i].parent == parent && strlen((*dn)[i].name) == len && !memcmp((*dn)[i].name, name, len))
            return (int32_t)i;
    if (*nd == *cap) {
        Dn *g = (Dn *)realloc(*dn, *cap * 2 * sizeof **dn);
        if (!g) return -1;
        *dn = g; *cap *= 2;
    }
    n = &(*dn)[*nd];
    memset(n, 0, sizeof *n);
    n->name = (char *)malloc(len + 1);
    if (!n->name) return -1;
    memcpy(n->name, name, len);
    n->name[len] = 0;
    n->parent = parent;
    if (to_utf16(n->name, len, &n->u16, &n->n16)) { free(n->name); n->name = NULL; return -1; }
    return (int32_t)(*nd)++;
}

int romfs_tables(RomfsTables *t, const RomfsFile *files, size_t count, const uint64_t *fixed, uint64_t append_at) {
    Dn *dn = NULL;
    Fn *fn = NULL;
    size_t nd = 1, cap = 16, nf = 0, i, k;
    uint32_t *sd = NULL, *sf = NULL, *tmp = NULL, *order = NULL, *stack = NULL;
    uint8_t *meta = NULL;
    uint32_t *dtab = NULL, *ftab = NULL;
    int rc = TITLE_E_MEM;
    uint32_t dir_meta_size = 0, file_meta_size = 0, dir_buckets, file_buckets, ndirs;
    uint32_t dir_hash_off, dir_meta_off, file_hash_off, file_meta_off, tables_len;
    uint64_t data_at = append_at;
    Ctx ctx;

    if (!t || (count && !files)) return TITLE_E_ARG;
    memset(t, 0, sizeof *t);
    dn = (Dn *)calloc(cap, sizeof *dn);
    fn = (Fn *)calloc(count ? count : 1, sizeof *fn);
    if (!dn || !fn) goto fail;
    dn[0].name = (char *)calloc(1, 1);
    if (!dn[0].name || to_utf16("", 0, &dn[0].u16, &dn[0].n16)) goto fail;
    dn[0].parent = -1;

    for (i = 0; i < count; i++) {
        const char *p = files[i].path;
        int32_t cur = 0;
        size_t at = 0, plen = p ? strlen(p) : 0;
        int placed = 0;
        if (!p) { rc = TITLE_E_PATH; goto fail; }
        while (at < plen) {
            size_t s = at, e, u;
            while (s < plen && (p[s] == '/' || p[s] == '\\')) s++;
            if (s >= plen) break;
            e = s;
            while (e < plen && p[e] != '/' && p[e] != '\\') e++;
            u = e;
            while (u < plen && (p[u] == '/' || p[u] == '\\')) u++;
            if (u >= plen) {  /* the last part: the file's name */
                size_t len = e - s;
                fn[nf].name = (char *)malloc(len + 1);
                if (!fn[nf].name) goto fail;
                memcpy(fn[nf].name, p + s, len);
                fn[nf].name[len] = 0;
                rc = to_utf16(fn[nf].name, len, &fn[nf].u16, &fn[nf].n16);
                if (rc) { free(fn[nf].name); fn[nf].name = NULL; goto fail; }
                fn[nf].dir = (uint32_t)cur;
                fn[nf].src = i;
                nf++;
                placed = 1;
            } else {
                cur = find_dir(&dn, &nd, &cap, cur, p + s, e - s);
                if (cur < 0) { rc = TITLE_E_PATH; goto fail; }
            }
            at = e;
        }
        if (!placed) { rc = TITLE_E_PATH; goto fail; }
    }
    rc = TITLE_E_MEM;
    ndirs = (uint32_t)nd;
    ctx.dn = dn; ctx.fn = fn;

    sd = (uint32_t *)malloc(nd * sizeof *sd);
    sf = (uint32_t *)malloc((nf ? nf : 1) * sizeof *sf);
    tmp = (uint32_t *)malloc((nd > nf ? nd : (nf ? nf : 1)) * sizeof *tmp);
    order = (uint32_t *)malloc(nd * sizeof *order);
    stack = (uint32_t *)malloc(nd * sizeof *stack);
    t->order = (size_t *)malloc((nf ? nf : 1) * sizeof *t->order);
    if (!sd || !sf || !tmp || !order || !stack || !t->order) goto fail;
    for (i = 1; i < nd; i++) sd[i - 1] = (uint32_t)i;
    for (i = 0; i < nf; i++) sf[i] = (uint32_t)i;
    msort(sd, tmp, nd - 1, cmp_dirs, &ctx);
    msort(sf, tmp, nf, cmp_files, &ctx);

    for (i = 0; i + 1 < nd; i++) {
        Dn *d = &dn[sd[i]], *par = &dn[d->parent];
        d->pos = (uint32_t)i;
        if (!par->nchild) par->first_child = (uint32_t)i;
        par->nchild++;
    }
    for (i = 0; i < nf; i++) {
        Dn *d = &dn[fn[sf[i]].dir];
        if (i && fn[sf[i]].dir == fn[sf[i - 1]].dir && !strcmp(fn[sf[i]].name, fn[sf[i - 1]].name)) {
            rc = TITLE_E_PATH; goto fail;   /* the same file twice */
        }
        if (!d->nfile) d->first_file = (uint32_t)i;
        d->nfile++;
    }
    /* A name that is both a file and a folder of the same directory. */
    for (i = 0; i < nd; i++) {
        uint32_t a = 0, b = 0;
        while (a < dn[i].nchild && b < dn[i].nfile) {
            int c = strcmp(dn[sd[dn[i].first_child + a]].name, fn[sf[dn[i].first_file + b]].name);
            if (!c) { rc = TITLE_E_PATH; goto fail; }
            if (c < 0) a++; else b++;
        }
    }

    /* Pre-order, siblings sorted by name. */
    {
        size_t top = 0, n = 0;
        stack[top++] = 0;
        while (top) {
            uint32_t d = stack[--top];
            order[n++] = d;
            for (k = dn[d].nchild; k > 0; k--) stack[top++] = sd[dn[d].first_child + k - 1];
        }
    }
    {
        uint32_t offset = 0;
        for (i = 0; i < nd; i++) {
            dn[order[i]].offset = offset;
            offset += 0x18 + name_size(dn[order[i]].n16);
        }
        dir_meta_size = offset;
        offset = 0;
        for (i = 0; i < nd; i++) {
            const Dn *d = &dn[order[i]];
            for (k = 0; k < d->nfile; k++) {
                Fn *f = &fn[sf[d->first_file + k]];
                f->meta = offset;
                if (fixed && fixed[f->src] != ROMFS_APPEND) {
                    f->data = fixed[f->src];
                } else {
                    f->data = data_at;
                    t->order[t->norder++] = f->src;
                    data_at += title_align(files[f->src].size, FILE_ALIGN);
                }
                offset += 0x20 + name_size(f->n16);
            }
        }
        file_meta_size = offset;
    }

    dir_buckets = bucket_count(ndirs);
    file_buckets = bucket_count((uint32_t)nf);
    dir_hash_off = HEADER_SIZE;
    dir_meta_off = dir_hash_off + 4 * dir_buckets;
    file_hash_off = dir_meta_off + dir_meta_size;
    file_meta_off = file_hash_off + 4 * file_buckets;
    tables_len = file_meta_off + file_meta_size;

    meta = (uint8_t *)calloc(tables_len, 1);
    dtab = (uint32_t *)malloc(dir_buckets * sizeof *dtab);
    ftab = (uint32_t *)malloc(file_buckets * sizeof *ftab);
    if (!meta || !dtab || !ftab) goto fail;
    for (i = 0; i < dir_buckets; i++) dtab[i] = NONE;
    for (i = 0; i < file_buckets; i++) ftab[i] = NONE;

    for (i = 0; i < nd; i++) {
        const Dn *d = &dn[order[i]];
        uint8_t *e = meta + dir_meta_off + d->offset;
        uint32_t parent = d->parent >= 0 ? dn[d->parent].offset : 0, sibling = NONE, child = NONE, cfile = NONE, b;
        if (d->parent >= 0 && d->pos + 1 < nd - 1 && dn[sd[d->pos + 1]].parent == d->parent)
            sibling = dn[sd[d->pos + 1]].offset;
        if (d->nchild) child = dn[sd[d->first_child]].offset;
        if (d->nfile) cfile = fn[sf[d->first_file]].meta;
        b = name_hash(parent, d->u16, d->n16, dir_buckets);
        put_le32(e, parent); put_le32(e + 4, sibling); put_le32(e + 8, child); put_le32(e + 12, cfile);
        put_le32(e + 16, dtab[b]); put_le32(e + 20, 2u * d->n16);
        dtab[b] = d->offset;
        for (k = 0; k < d->n16; k++) put_le16(e + 0x18 + 2 * k, d->u16[k]);
    }
    for (i = 0; i < nd; i++) {
        const Dn *d = &dn[order[i]];
        for (k = 0; k < d->nfile; k++) {
            size_t at = d->first_file + k, j;
            const Fn *f = &fn[sf[at]];
            uint8_t *e = meta + file_meta_off + f->meta;
            uint32_t sibling = NONE, b;
            if (k + 1 < d->nfile) sibling = fn[sf[at + 1]].meta;
            b = name_hash(d->offset, f->u16, f->n16, file_buckets);
            put_le32(e, d->offset); put_le32(e + 4, sibling); put_le64(e + 8, f->data);
            put_le64(e + 16, files[f->src].size); put_le32(e + 24, ftab[b]); put_le32(e + 28, 2u * f->n16);
            ftab[b] = f->meta;
            for (j = 0; j < f->n16; j++) put_le16(e + 0x20 + 2 * j, f->u16[j]);
        }
    }
    put_le32(meta, HEADER_SIZE); put_le32(meta + 4, dir_hash_off); put_le32(meta + 8, 4 * dir_buckets);
    put_le32(meta + 12, dir_meta_off); put_le32(meta + 16, dir_meta_size); put_le32(meta + 20, file_hash_off);
    put_le32(meta + 24, 4 * file_buckets); put_le32(meta + 28, file_meta_off); put_le32(meta + 32, file_meta_size);
    put_le32(meta + 36, 0);                                 /* the data offset: the caller's */
    for (i = 0; i < dir_buckets; i++) put_le32(meta + dir_hash_off + 4 * i, dtab[i]);
    for (i = 0; i < file_buckets; i++) put_le32(meta + file_hash_off + 4 * i, ftab[i]);

    t->tables = meta; meta = NULL;
    t->tables_len = tables_len;
    t->data_end = data_at;
    rc = TITLE_OK;

fail:
    if (rc) romfs_tables_free(t);
    free(meta); free(dtab); free(ftab); free(sd); free(sf); free(tmp); free(order); free(stack);
    free_nodes(dn, nd, fn, nf);
    return rc;
}

void romfs_tables_free(RomfsTables *t) {
    if (!t) return;
    free(t->tables); free(t->order);
    memset(t, 0, sizeof *t);
}

int romfs_tables_place(const RomfsTables *t, uint32_t data_off, uint64_t size, uint8_t **out) {
    uint8_t *meta;
    if (!t || !out || data_off < t->tables_len || size < t->tables_len) return TITLE_E_ARG;
    meta = (uint8_t *)calloc(size ? (size_t)size : 1, 1);
    if (!meta) return TITLE_E_MEM;
    memcpy(meta, t->tables, t->tables_len);
    put_le32(meta + 36, data_off);
    *out = meta;
    return TITLE_OK;
}

int romfs_layout(RomfsImage **out, const RomfsFile *files, size_t count, TitleRead read, void *read_ctx) {
    RomfsTables t;
    RomfsImage *im;
    uint32_t data_off;
    size_t i;
    int rc;
    if (!out || !read || (count && !files)) return TITLE_E_ARG;
    *out = NULL;
    if ((rc = romfs_tables(&t, files, count, NULL, 0))) return rc;
    im = (RomfsImage *)calloc(1, sizeof *im);
    if (!im) { romfs_tables_free(&t); return TITLE_E_MEM; }
    data_off = (uint32_t)title_align(t.tables_len, FILE_ALIGN);
    rc = romfs_tables_place(&t, data_off, data_off, &im->metadata);
    im->data = (RomfsFile *)malloc((t.norder ? t.norder : 1) * sizeof *im->data);
    im->scratch = (uint8_t *)malloc(READ_CHUNK);
    if (rc || !im->data || !im->scratch) {
        romfs_tables_free(&t);
        romfs_free(im);
        return rc ? rc : TITLE_E_MEM;
    }
    for (i = 0; i < t.norder; i++) im->data[i] = files[t.order[i]];   /* data order: the tables' order */
    im->ndata = t.norder;
    im->metadata_len = data_off;
    im->level3_size = data_off + t.data_end;
    romfs_tables_free(&t);
    {
        RomfsTree tree;
        romfs_tree(&tree, im->level3_size);
        im->l2_size = tree.l2_size;
        im->l1_size = tree.l1_size;
        im->master_size = tree.master_size;
        im->hash_region_size = tree.hash_region_size;
        im->l3_start = tree.l3_start;
        im->l1_start = tree.l1_start;
        im->l2_start = tree.l2_start;
        im->size = tree.size;
    }
    im->read = read; im->read_ctx = read_ctx;
    *out = im;
    return TITLE_OK;
}

/* ---- level 3 stream and the hash tree ------------------------------------------------------------------------ */

static int report(const TitleOut *o, uint64_t done, uint64_t total) {
    return o->progress && o->progress(o->progress_ctx, done, total) ? TITLE_E_CANCEL : TITLE_OK;
}

/* The level 3 bytes in order, files read in chunks; progress counts from `base` of `total`. */
static int emit_level3(RomfsImage *im, const TitleOut *o, uint64_t base, uint64_t total) {
    uint64_t done = im->metadata_len;
    size_t i;
    int rc;
    if (o->write(o->ctx, im->metadata, (size_t)im->metadata_len)) return TITLE_E_IO;
    for (i = 0; i < im->ndata; i++) {
        const RomfsFile *f = &im->data[i];
        uint64_t left = f->size, at = f->offset, pad;
        while (left) {
            size_t n = left < READ_CHUNK ? (size_t)left : READ_CHUNK;
            if (im->read(im->read_ctx, f->handle, at, im->scratch, n)) return TITLE_E_IO;
            if (o->write(o->ctx, im->scratch, n)) return TITLE_E_IO;
            left -= n; at += n; done += n;
            rc = report(o, base + done, total);
            if (rc) return rc;
        }
        pad = (FILE_ALIGN - f->size % FILE_ALIGN) % FILE_ALIGN;
        if (pad) {
            if (o->write(o->ctx, ZEROS, (size_t)pad)) return TITLE_E_IO;
            done += pad;
        }
    }
    return done == im->level3_size ? TITLE_OK : TITLE_E_SIZE;
}

/* Hashes what is written to it in 0x1000 blocks into the store. */
typedef struct {
    const HashStore *st;
    uint8_t block[BLOCK];
    size_t fill;
    uint8_t out[BLOCK];
    size_t outfill;
    uint64_t hashes;
} Hasher;

static int hasher_push(Hasher *h, const uint8_t *block) {
    sha256_buf(block, BLOCK, h->out + h->outfill);
    h->outfill += HASH_SIZE;
    h->hashes++;
    if (h->outfill == sizeof h->out) {
        h->outfill = 0;
        return h->st->append(h->st->ctx, h->out, sizeof h->out);
    }
    return 0;
}

static int hasher_write(void *ctx, const void *buf, size_t n) {
    Hasher *h = (Hasher *)ctx;
    const uint8_t *p = (const uint8_t *)buf;
    while (n) {
        if (!h->fill && n >= BLOCK) {
            if (hasher_push(h, p)) return 1;
            p += BLOCK; n -= BLOCK;
        } else {
            size_t k = BLOCK - h->fill < n ? BLOCK - h->fill : n;
            memcpy(h->block + h->fill, p, k);
            h->fill += k; p += k; n -= k;
            if (h->fill == BLOCK) {
                h->fill = 0;
                if (hasher_push(h, h->block)) return 1;
            }
        }
    }
    return 0;
}

static int hasher_finish(Hasher *h) {
    if (h->fill) {
        memset(h->block + h->fill, 0, BLOCK - h->fill);
        h->fill = 0;
        if (hasher_push(h, h->block)) return 1;
    }
    return h->outfill ? h->st->append(h->st->ctx, h->out, h->outfill) : 0;
}

int romfs_prepare(RomfsImage *im, const HashStore *store, TitleProgress progress, void *progress_ctx) {
    Hasher *h;
    TitleOut o;
    uint8_t *buf;
    uint64_t at;
    int rc;
    if (!im || !store || !store->append || !store->get) return TITLE_E_ARG;
    if (im->prepared) return TITLE_OK;
    h = (Hasher *)calloc(1, sizeof *h);
    buf = (uint8_t *)malloc(BLOCK);
    free(im->l1); free(im->master);
    im->l1 = (uint8_t *)malloc((size_t)im->l1_size);
    im->master = (uint8_t *)malloc(im->master_size);
    if (!h || !buf || !im->l1 || !im->master) { free(h); free(buf); return TITLE_E_MEM; }
    h->st = store;
    o.write = hasher_write; o.ctx = h; o.progress = progress; o.progress_ctx = progress_ctx;
    rc = emit_level3(im, &o, 0, im->level3_size);
    if (!rc && hasher_finish(h)) rc = TITLE_E_IO;
    if (!rc && h->hashes * HASH_SIZE != im->l2_size) rc = TITLE_E_SIZE;
    /* level 1: hashes of level 2 read back from the store */
    for (at = 0; !rc && at < im->l2_size; at += BLOCK) {
        size_t n = im->l2_size - at < BLOCK ? (size_t)(im->l2_size - at) : BLOCK;
        if (store->get(store->ctx, at, buf, n)) { rc = TITLE_E_IO; break; }
        memset(buf + n, 0, BLOCK - n);
        sha256_buf(buf, BLOCK, im->l1 + at / BLOCK * HASH_SIZE);
    }
    if (!rc) {
        romfs_hash_blocks(im->l1, im->l1_size, im->master);
        im->store = *store;
        im->prepared = 1;
    }
    free(h); free(buf);
    return rc;
}

uint64_t romfs_size(const RomfsImage *im) { return im->size; }
uint64_t romfs_level3_size(const RomfsImage *im) { return im->level3_size; }
uint32_t romfs_hash_region_size(const RomfsImage *im) { return im->hash_region_size; }

/* The IVFC header, master hash and zeros up to `to` bytes (to >= 0x60 + master_size) into out. */
static void header_region(const RomfsImage *im, uint8_t *out, size_t to) {
    RomfsTree tree;
    romfs_tree(&tree, im->level3_size);
    memset(out, 0, to);
    romfs_ivfc_header(&tree, out);
    memcpy(out + MASTER_HASH_OFFSET, im->master, im->master_size);
}

int romfs_region_hash(const RomfsImage *im, uint8_t out[32]) {
    uint8_t *buf;
    if (!im || !im->prepared) return TITLE_E_ARG;
    buf = (uint8_t *)malloc(im->hash_region_size);
    if (!buf) return TITLE_E_MEM;
    header_region(im, buf, im->hash_region_size);
    sha256_buf(buf, im->hash_region_size, out);
    free(buf);
    return TITLE_OK;
}

int romfs_stream(RomfsImage *im, const TitleOut *out) {
    uint8_t *head;
    uint8_t *buf;
    uint64_t at;
    int rc;
    if (!im || !im->prepared || !out || !out->write) return TITLE_E_ARG;
    head = (uint8_t *)malloc((size_t)im->l3_start);
    if (!head) return TITLE_E_MEM;
    header_region(im, head, (size_t)im->l3_start);
    rc = out->write(out->ctx, head, (size_t)im->l3_start) ? TITLE_E_IO : TITLE_OK;
    free(head);
    if (rc) return rc;
    rc = emit_level3(im, out, im->l3_start, im->size);
    if (rc) return rc;
    if ((rc = title_write_zeros(out, im->l1_start - im->l3_start - im->level3_size))) return rc;
    if (out->write(out->ctx, im->l1, (size_t)im->l1_size)) return TITLE_E_IO;
    if ((rc = title_write_zeros(out, im->l2_start - im->l1_start - im->l1_size))) return rc;
    buf = (uint8_t *)malloc(BLOCK);
    if (!buf) return TITLE_E_MEM;
    rc = TITLE_OK;
    for (at = 0; !rc && at < im->l2_size; at += BLOCK) {
        size_t n = im->l2_size - at < BLOCK ? (size_t)(im->l2_size - at) : BLOCK;
        if (im->store.get(im->store.ctx, at, buf, n) || out->write(out->ctx, buf, n)) rc = TITLE_E_IO;
    }
    free(buf);
    if (rc) return rc;
    if ((rc = title_write_zeros(out, im->size - im->l2_start - im->l2_size))) return rc;
    return report(out, im->size, im->size);
}

void romfs_free(RomfsImage *im) {
    if (!im) return;
    free(im->metadata); free(im->data); free(im->scratch); free(im->l1); free(im->master);
    free(im);
}
