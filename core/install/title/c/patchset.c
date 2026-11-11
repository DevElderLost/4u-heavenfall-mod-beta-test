/* The release patch set applier (patchset.h). Format; writer:
 * core/install/title/patchset.py. */
#include "patchset.h"

#include <stdlib.h>
#include <string.h>

#include "blz.h"
#include "sha256.h"
#include "zlib_mini.h"

#define MAGIC "HFPS"
#define CHUNK 65536u                     /* the size of one read or write */
#define PS_MAX_ADD (1u << 20)            /* a literal chunk's raw size */
#define PS_MAX_Z (PS_MAX_ADD + PS_MAX_ADD / 8 + 1024u)
#define OPS_BUF 16384u
#define KEEP_BUDGET (64u << 20)          /* deflated entries an apply keeps between its sizing and its writing pass */
#define PART_BUDGET (1u << 20)           /* inflated base parts a file keeps between its records (an XX file: 0.45 MiB) */
#define NAME_BLOCK 65536u                /* the tables' strings are kept in blocks of this size, not one allocation each */
#define MAX_TABLES (1u << 30)
#define MAX_PARTS (1u << 24)
#define CODE_PATH "exefs/code.bin"
#define ARC_HEADER 0xCu
#define ARC_ENTRY 0x50u
#define ARC_NAME 64u
#define ARC_GAP 0x14u
#define ARC_MAX_SIZE 0x00FFFFFFu

enum { OP_COPY = 1, OP_ADD = 2, OP_ADDZ = 3 };
enum { ENT_REF = 0, ENT_OPS = 1 };

typedef struct { uint32_t type, csize, size, flags; uint64_t off; } ArcEnt;

/* A part of a base: a source whole (entry PS_NONE), or one entry of an ARC source, decompressed. */
typedef struct { uint32_t src, entry; } PsPart;

typedef struct {
    uint32_t kind;
    char *path;
    uint64_t size;
    uint8_t sha[32];
    PatchsetBinding b;
    int bound;
    uint8_t *plain;                      /* the decompressed executable, once read */
    ArcEnt *arc;                         /* the source as an ARC, once read */
    uint32_t narc;
    int arc_loaded;
} PsSrc;

typedef struct {
    uint32_t type_hash, flags, size, mode;
    uint8_t sha[32];
    uint32_t part, nparts;               /* its base, parts [part, part + nparts); a copied entry: its one ARC part */
    uint64_t ops_off, ops_len;
    char *name;
    uint32_t csize;                      /* deflated size of an ENT_OPS entry, or the copied stream's; 0 = not known */
    uint8_t *kept;                       /* its stream, between the sizing and the writing pass */
} PsEnt;

typedef struct {
    uint32_t kind, flags, part, nparts, arc_version, nent;
    char *path;
    uint64_t size;
    int size_known;
    int sized;                           /* every entry's stream size known (arc_size ran) */
    uint8_t sha[32];
    uint64_t ops_off, ops_len;
    PsEnt *ents;
} PsFile;

/* An ARC entry part, inflated, kept while the file it serves is made. `stamp`: the last base that used it. */
typedef struct { uint32_t src, entry, len, stamp; uint8_t *data; } PsCached;

/* A part of the base being read: in memory (`mem`) or read from its source; `at` is where it starts in the join. */
typedef struct { PsSrc *src; const uint8_t *mem; uint64_t at, size; } BasePart;

typedef struct NameBlock { struct NameBlock *next; size_t used, cap; } NameBlock;   /* its strings follow it */

struct Patchset {
    uint8_t exheader[EXHEADER_SIZE];     /* the bound dump's exheader, ncch_common_exheader: either copy of the game */
    TitleRead read;
    void *ctx, *handle;
    uint64_t size, ops_base;
    uint32_t format, region, zlevel;
    char edition[17], version[17];
    uint64_t second_title;               /* format 2: the second game's title id and RomFS superblock hash */
    uint8_t second_hash[32];
    PsSrc *src;
    size_t nsrc;
    PsPart *parts;                       /* every base's parts (format 1: one per base, made at open) */
    size_t nparts, parts_cap;
    PsFile *files;
    size_t nfiles;
    NameBlock *names;
    uint8_t *build;
    size_t build_len;
    uint8_t *chunk, *zbuf, *zout;        /* work buffers; the literal chunks' grown to the largest chunk met */
    size_t zbuf_cap, zout_cap;
    PsCached *pc;                        /* the current file's inflated parts */
    size_t npc, pc_cap, pc_file;
    uint64_t pc_bytes;
    uint32_t pc_stamp;
    BasePart *bp;                        /* the base being read */
    size_t bp_cap;
    uint64_t keep_budget;
};

/* ---- reading the tables ---------------------------------------------------------------------------------------- */

typedef struct { const uint8_t *p, *end; } Cur;

static int cur_take(Cur *c, const uint8_t **out, size_t n) {
    if ((size_t)(c->end - c->p) < n) return TITLE_E_FORMAT;
    *out = c->p;
    c->p += n;
    return TITLE_OK;
}
static int cur_u32(Cur *c, uint32_t *v) {
    const uint8_t *p;
    if (cur_take(c, &p, 4)) return TITLE_E_FORMAT;
    *v = get_le32(p);
    return TITLE_OK;
}
static int cur_u64(Cur *c, uint64_t *v) {
    const uint8_t *p;
    if (cur_take(c, &p, 8)) return TITLE_E_FORMAT;
    *v = (uint64_t)get_le32(p) | (uint64_t)get_le32(p + 4) << 32;
    return TITLE_OK;
}

/* A copy of `n` bytes as a string in the set's name blocks. */
static char *name_keep(Patchset *ps, const uint8_t *p, uint32_t n) {
    NameBlock *b = ps->names;
    char *out;
    if (!b || b->cap - b->used < (size_t)n + 1) {
        size_t cap = (size_t)n + 1 > NAME_BLOCK ? (size_t)n + 1 : NAME_BLOCK;
        b = (NameBlock *)malloc(sizeof *b + cap);
        if (!b) return NULL;
        b->next = ps->names;
        b->used = 0;
        b->cap = cap;
        ps->names = b;
    }
    out = (char *)(b + 1) + b->used;
    memcpy(out, p, n);
    out[n] = 0;
    b->used += (size_t)n + 1;
    return out;
}

/* A string of `n` bytes padded to four, where it is in the tables; NUL inside is refused. */
static int cur_name(Cur *c, uint32_t n, const uint8_t **out) {
    size_t pad = (4 - (n & 3)) & 3;
    if (n > 4096 || cur_take(c, out, n)) return TITLE_E_FORMAT;
    if ((n && memchr(*out, 0, n)) || (size_t)(c->end - c->p) < pad) return TITLE_E_FORMAT;
    c->p += pad;
    return TITLE_OK;
}

/* The files an open keeps: every one (NULL), or the ones named (patchset_open_files). */
typedef struct { const char *const *paths; size_t n; } Want;

static int wanted(const Want *w, const uint8_t *path, uint32_t n) {
    size_t i;
    if (!w) return 1;
    for (i = 0; i < w->n; i++)
        if (strlen(w->paths[i]) == n && !memcmp(w->paths[i], path, n)) return 1;
    return 0;
}

static uint64_t le64(const uint8_t *p) { return (uint64_t)get_le32(p) | (uint64_t)get_le32(p + 4) << 32; }

static void parts_drop(Patchset *ps);

void patchset_close(Patchset *ps) {
    size_t i;
    uint32_t k;
    if (!ps) return;
    for (i = 0; i < ps->nsrc; i++) {
        free(ps->src[i].plain);
        free(ps->src[i].arc);
    }
    for (i = 0; i < ps->nfiles; i++) {
        for (k = 0; k < ps->files[i].nent && ps->files[i].ents; k++) free(ps->files[i].ents[k].kept);
        free(ps->files[i].ents);
    }
    while (ps->names) {
        NameBlock *next = ps->names->next;
        free(ps->names);
        ps->names = next;
    }
    parts_drop(ps);
    free(ps->src);
    free(ps->parts);
    free(ps->files);
    free(ps->build);
    free(ps->chunk);
    free(ps->zbuf);
    free(ps->zout);
    free(ps->bp);
    free(ps);
}

/* A part's source is the set's, and an ARC entry is of a source that may be an ARC (a RomFS file of either game). */
static int part_check(const Patchset *ps, const PsPart *p) {
    uint32_t kind;
    if (p->src >= ps->nsrc) return TITLE_E_FORMAT;
    kind = ps->src[p->src].kind;
    return p->entry == PS_NONE || kind == PS_SRC_FILE || kind == PS_SRC_SECOND ? TITLE_OK : TITLE_E_FORMAT;
}

/* A record's base: format 2's `b` parts from part `a`; format 1's one (source a, entry b), made a part of its own (its
 * source checked with every part's once the sources are read). */
static int record_base(Patchset *ps, uint32_t a, uint32_t b, uint32_t *first, uint32_t *count) {
    PsPart *p;
    *first = PS_NONE;
    *count = 0;
    if (ps->format == PS_FORMAT_SECOND) {
        if (b && (a >= ps->nparts || b > ps->nparts - a)) return TITLE_E_FORMAT;
        *first = b ? a : PS_NONE;
        *count = b;
        return TITLE_OK;
    }
    if (a == PS_NONE) return TITLE_OK;
    if (ps->nparts == ps->parts_cap) {
        size_t cap = ps->parts_cap ? ps->parts_cap * 2 : 256;
        PsPart *grown = (PsPart *)realloc(ps->parts, cap * sizeof *grown);
        if (!grown) return TITLE_E_MEM;
        ps->parts = grown;
        ps->parts_cap = cap;
    }
    p = &ps->parts[ps->nparts];
    p->src = a;
    p->entry = b;
    *first = (uint32_t)ps->nparts++;
    *count = 1;
    return TITLE_OK;
}

/* One ARC entry at `fc` into `e`; with `keep` 0 only stepped over (its name and base not taken). */
static int parse_entry(Patchset *ps, Cur *fc, PsEnt *e, int keep) {
    const uint8_t *sha, *name;
    uint32_t namelen, a, b, reserved;
    int rc;
    if ((rc = cur_u32(fc, &e->type_hash)) || (rc = cur_u32(fc, &e->flags)) || (rc = cur_u32(fc, &e->size)) ||
        (rc = cur_u32(fc, &e->mode)) || (rc = cur_take(fc, &sha, 32)) || (rc = cur_u32(fc, &a)) ||
        (rc = cur_u32(fc, &b)) || (rc = cur_u64(fc, &e->ops_off)) || (rc = cur_u64(fc, &e->ops_len)) ||
        (rc = cur_u32(fc, &namelen)) || (rc = cur_u32(fc, &reserved)) || (rc = cur_name(fc, namelen, &name)))
        return rc;
    if (e->mode > ENT_OPS || e->size > ARC_MAX_SIZE || e->flags > 0xFF || namelen >= ARC_NAME ||
        e->ops_off > ps->size || e->ops_len > ps->size - e->ops_off)
        return TITLE_E_FORMAT;
    if (!keep) return TITLE_OK;
    memcpy(e->sha, sha, 32);
    if (!(e->name = name_keep(ps, name, namelen))) return TITLE_E_MEM;
    if ((rc = record_base(ps, a, b, &e->part, &e->nparts))) return rc;
    return e->mode == ENT_REF && (e->nparts != 1 || ps->parts[e->part].entry == PS_NONE) ? TITLE_E_FORMAT : TITLE_OK;
}

/* One file record at `fc`: kept as the set's next file when `want` names it (at most `cap` kept), else only stepped
 * over. */
static int parse_file(Patchset *ps, Cur *fc, const Want *want, size_t cap) {
    const uint8_t *sha, *path;
    uint32_t pathlen, base, count = PS_NONE, reserved, k;
    PsFile rec, *f = &rec;
    PsEnt skip;
    int rc, keep;
    memset(&rec, 0, sizeof rec);
    if ((rc = cur_u32(fc, &rec.kind)) || (rc = cur_u32(fc, &pathlen)) || (rc = cur_u64(fc, &rec.size)) ||
        (rc = cur_take(fc, &sha, 32)) || (rc = cur_u32(fc, &rec.flags)) || (rc = cur_u32(fc, &base)) ||
        (rc = cur_u64(fc, &rec.ops_off)) || (rc = cur_u64(fc, &rec.ops_len)) || (rc = cur_u32(fc, &rec.arc_version)) ||
        (rc = cur_u32(fc, &rec.nent)))
        return rc;
    if (ps->format == PS_FORMAT_SECOND && ((rc = cur_u32(fc, &count)) || (rc = cur_u32(fc, &reserved)))) return rc;
    if ((rc = cur_name(fc, pathlen, &path))) return rc;
    if (rec.kind > PS_FILE_ARC || !pathlen || rec.ops_off > ps->size || rec.ops_len > ps->size - rec.ops_off ||
        (rec.kind == PS_FILE_PLAIN && rec.nent) || rec.nent > 65535u)
        return TITLE_E_FORMAT;
    keep = wanted(want, path, pathlen);
    if (keep) {         /* the set's from here: what it holds is freed with it */
        if (ps->nfiles == cap) return TITLE_E_FORMAT;       /* a file named twice */
        f = &ps->files[ps->nfiles++];
        *f = rec;
        memcpy(f->sha, sha, 32);
        f->size_known = f->kind == PS_FILE_PLAIN;
        if (!(f->path = name_keep(ps, path, pathlen))) return TITLE_E_MEM;
        if ((rc = record_base(ps, base, count, &f->part, &f->nparts))) return rc;
        if (f->kind == PS_FILE_ARC && !(f->ents = (PsEnt *)calloc(f->nent ? f->nent : 1, sizeof(PsEnt))))
            return TITLE_E_MEM;
    }
    for (k = 0; k < f->nent; k++) {
        memset(&skip, 0, sizeof skip);
        if ((rc = parse_entry(ps, fc, keep ? &f->ents[k] : &skip, keep))) return rc;
    }
    return TITLE_OK;
}

/* Format 2's parts of a set opened for some files: only those their records read, each record's range in turn. */
static void part_move(const PsPart *from, PsPart *to, size_t *n, uint32_t *first, uint32_t count) {
    if (!count) return;
    memcpy(to + *n, from + *first, count * sizeof *to);
    *first = (uint32_t)*n;
    *n += count;
}

/* The records' ranges may overlap, so their sum is counted in 64 bits and refused past MAX_PARTS: on the console's
 * 32-bit size_t a damaged set's sum (65535 entries naming the same thousands of parts) would wrap and the copies below
 * would run past a small block. */
static int parts_keep_read(Patchset *ps) {
    PsPart *kept;
    size_t i, n = 0;
    uint64_t total = 0;
    uint32_t k;
    if (ps->format != PS_FORMAT_SECOND) return TITLE_OK;     /* format 1's are made for the records kept */
    for (i = 0; i < ps->nfiles; i++) {
        total += ps->files[i].nparts;
        for (k = 0; k < ps->files[i].nent; k++) total += ps->files[i].ents[k].nparts;
        if (total > MAX_PARTS) return TITLE_E_FORMAT;
    }
    n = (size_t)total;
    if (!(kept = (PsPart *)malloc(n ? n * sizeof *kept : 1))) return TITLE_E_MEM;
    n = 0;
    for (i = 0; i < ps->nfiles; i++) {
        PsFile *f = &ps->files[i];
        part_move(ps->parts, kept, &n, &f->part, f->nparts);
        for (k = 0; k < f->nent; k++) part_move(ps->parts, kept, &n, &f->ents[k].part, f->ents[k].nparts);
    }
    free(ps->parts);
    ps->parts = kept;
    ps->nparts = ps->parts_cap = n;
    return TITLE_OK;
}

/* One source at `sc`: source `i` of the set, or only stepped over (PS_NONE). */
static int parse_source(Patchset *ps, Cur *sc, uint32_t i) {
    const uint8_t *sha, *path;
    uint32_t kind, pathlen;
    uint64_t size;
    PsSrc *s;
    int rc;
    if ((rc = cur_u32(sc, &kind)) || (rc = cur_u32(sc, &pathlen)) || (rc = cur_u64(sc, &size)) ||
        (rc = cur_take(sc, &sha, 32)) || (rc = cur_name(sc, pathlen, &path)))
        return rc;
    if (kind > (ps->format == PS_FORMAT_SECOND ? PS_SRC_SECOND : PS_SRC_CODE) ||
        ((kind == PS_SRC_EXHEADER || kind == PS_SRC_CODE) && pathlen))
        return TITLE_E_FORMAT;
    if (i == PS_NONE) return TITLE_OK;
    s = &ps->src[i];
    s->kind = kind;
    s->size = size;
    memcpy(s->sha, sha, 32);
    return (s->path = name_keep(ps, path, pathlen)) ? TITLE_OK : TITLE_E_MEM;
}

/* The `nsrc` sources at `sc`: every one, or (`some`: a set opened for some files) only those its parts name, numbered
 * in the set's order and the parts given their numbers. */
static int parse_sources(Patchset *ps, Cur *sc, uint32_t nsrc, int some) {
    uint32_t *to = NULL, i, n = nsrc;
    size_t k;
    int rc = TITLE_OK;
    if (some) {
        if (!(to = (uint32_t *)malloc(nsrc ? nsrc * sizeof *to : 1))) return TITLE_E_MEM;
        for (i = 0; i < nsrc; i++) to[i] = PS_NONE;
        for (k = 0; k < ps->nparts && !rc; k++) {
            if (ps->parts[k].src >= nsrc) rc = TITLE_E_FORMAT;
            else to[ps->parts[k].src] = 0;
        }
        for (i = 0, n = 0; i < nsrc; i++)
            if (to[i] != PS_NONE) to[i] = n++;
    }
    if (!rc && !(ps->src = (PsSrc *)calloc(n ? n : 1, sizeof(PsSrc)))) rc = TITLE_E_MEM;
    if (!rc) ps->nsrc = n;
    for (i = 0; !rc && i < nsrc; i++) rc = parse_source(ps, sc, to ? to[i] : i);
    if (!rc && sc->p != sc->end) rc = TITLE_E_FORMAT;
    for (k = 0; !rc && to && k < ps->nparts; k++) ps->parts[k].src = to[ps->parts[k].src];
    free(to);
    return rc;
}

/* Format 2's parts at `pc`, the `nfiles` file records at `fc` (every one, or those `want` names with only the parts they
 * read), then the `nsrc` sources at `sc` (with `want`, those the parts kept name): each area must end where the next
 * starts, and every part name a source it can read. */
static int parse_tables(Patchset *ps, Cur *sc, Cur *pc, Cur *fc, uint32_t nsrc, uint32_t nfiles, const Want *want) {
    size_t i, cap = want ? want->n : nfiles;
    int rc;
    for (i = 0; ps->format == PS_FORMAT_SECOND && i < ps->nparts; i++)
        if ((rc = cur_u32(pc, &ps->parts[i].src)) || (rc = cur_u32(pc, &ps->parts[i].entry))) return rc;
    if (pc->p != pc->end) return TITLE_E_FORMAT;
    if (!(ps->files = (PsFile *)calloc(cap ? cap : 1, sizeof(PsFile)))) return TITLE_E_MEM;
    for (i = 0; i < nfiles; i++)
        if ((rc = parse_file(ps, fc, want, cap))) return rc;
    if (fc->p != fc->end) return TITLE_E_FORMAT;
    if ((want && (rc = parts_keep_read(ps))) || (rc = parse_sources(ps, sc, nsrc, want != NULL))) return rc;
    for (i = 0; i < ps->nparts; i++)
        if ((rc = part_check(ps, &ps->parts[i]))) return rc;
    return TITLE_OK;
}

/* patchset_open, keeping every file or (want) only those named, with no build data. */
static int open_set(Patchset **out, TitleRead read, void *ctx, void *handle, uint64_t size, int check, const Want *want) {
    uint8_t h[PS_HEADER2_SIZE];
    uint64_t tables_off, field, ops_off, total, build_off, build_len, at, stored, inflated;
    uint32_t format, nsrc, nfiles, nparts = 0, parts_at, files_at;
    uint8_t *tab = NULL;
    Patchset *ps;
    Cur sc, pc, fc;
    int rc;
    if (!out || !read) return TITLE_E_ARG;
    *out = NULL;
    if (size < PS_HEADER_SIZE) return TITLE_E_FORMAT;
    memset(h, 0, sizeof h);
    if (read(ctx, handle, 0, h, PS_HEADER_SIZE)) return TITLE_E_IO;
    format = get_le32(h + 4);
    if (memcmp(h, MAGIC, 4) || (format != PS_FORMAT && format != PS_FORMAT_SECOND)) return TITLE_E_FORMAT;
    if (format == PS_FORMAT_SECOND) {
        if (size < PS_HEADER2_SIZE) return TITLE_E_FORMAT;
        if (read(ctx, handle, PS_HEADER_SIZE, h + PS_HEADER_SIZE, PS_HEADER2_SIZE - PS_HEADER_SIZE)) return TITLE_E_IO;
    }
    total = le64(h + 0x28);
    tables_off = get_le32(h + 0x18);
    field = get_le32(h + 0x1C);          /* format 1: the files' offset; format 2: the tables' stored length */
    ops_off = le64(h + 0x20);
    build_off = get_le32(h + 0x30);
    build_len = get_le32(h + 0x34);
    nsrc = get_le32(h + 0x10);
    nfiles = get_le32(h + 0x14);
    if (total != size || ops_off > total || build_len > total - ops_off || build_off != total - build_len ||
        get_le32(h + 8) > 1 || get_le32(h + 0xC) < 1 || get_le32(h + 0xC) > 9 || nsrc > (1u << 20) ||
        nfiles > (1u << 20))
        return TITLE_E_FORMAT;
    if (format == PS_FORMAT) {           /* sources at 0x80, files at their offset, ops after them: stored as they are */
        if (tables_off != PS_HEADER_SIZE || field < tables_off || ops_off < field) return TITLE_E_FORMAT;
        stored = inflated = ops_off - tables_off;
        parts_at = files_at = (uint32_t)(field - tables_off);
    } else {                             /* one zlib stream at 0x100: the sources, the parts, the files */
        nparts = get_le32(h + 0x38);
        inflated = get_le32(h + 0x3C);
        parts_at = get_le32(h + 0xA8);
        files_at = get_le32(h + 0xAC);
        stored = field;
        if (tables_off != PS_HEADER2_SIZE || ops_off != tables_off + stored || nparts > MAX_PARTS ||
            parts_at > files_at || files_at > inflated || files_at - parts_at != (uint64_t)nparts * 8)
            return TITLE_E_FORMAT;
    }
    if (stored > MAX_TABLES || inflated > MAX_TABLES) return TITLE_E_FORMAT;
    if (check) {
        Sha256 sha;
        uint8_t digest[32], *buf = (uint8_t *)malloc(CHUNK);
        if (!buf) return TITLE_E_MEM;
        sha256_init(&sha);
        sha256_update(&sha, h, 0x60);
        for (at = PS_HEADER_SIZE; at < total;) {
            size_t n = total - at < CHUNK ? (size_t)(total - at) : CHUNK;
            if (read(ctx, handle, at, buf, n)) {
                free(buf);
                return TITLE_E_IO;
            }
            sha256_update(&sha, buf, n);
            at += n;
        }
        free(buf);
        sha256_final(&sha, digest);
        if (memcmp(digest, h + 0x60, 32)) return TITLE_E_FORMAT;
    }
    ps = (Patchset *)calloc(1, sizeof *ps);
    if (!ps) return TITLE_E_MEM;
    ps->read = read;
    ps->ctx = ctx;
    ps->handle = handle;
    ps->size = size;
    ps->ops_base = ops_off;
    ps->format = format;
    ps->region = get_le32(h + 8);
    ps->zlevel = get_le32(h + 0xC);
    memcpy(ps->edition, h + 0x40, 16);
    memcpy(ps->version, h + 0x50, 16);
    ps->second_title = le64(h + 0x80);
    memcpy(ps->second_hash, h + 0x88, 32);
    ps->pc_file = (size_t)-1;
    ps->keep_budget = KEEP_BUDGET;
    ps->nparts = nparts;
    ps->parts_cap = nparts;
    ps->parts = (PsPart *)malloc(nparts ? (size_t)nparts * sizeof(PsPart) : 1);
    ps->chunk = (uint8_t *)malloc(CHUNK);
    rc = !ps->parts || !ps->chunk ? TITLE_E_MEM : TITLE_OK;
    if (!rc && format == PS_FORMAT_SECOND) {    /* the stored stream lives only while it is inflated */
        uint8_t *z = (uint8_t *)malloc(stored ? (size_t)stored : 1);  /* first: the records made later fill its room */
        tab = (uint8_t *)malloc(inflated ? (size_t)inflated : 1);
        if (!z || !tab) rc = TITLE_E_MEM;
        else if (read(ctx, handle, tables_off, z, (size_t)stored)) rc = TITLE_E_IO;
        else if (zm_inflate(z, (size_t)stored, tab, (size_t)inflated)) rc = TITLE_E_FORMAT;
        free(z);
    } else if (!rc) {
        tab = (uint8_t *)malloc(inflated ? (size_t)inflated : 1);
        if (!tab) rc = TITLE_E_MEM;
        else if (stored && read(ctx, handle, tables_off, tab, (size_t)stored)) rc = TITLE_E_IO;
    }
    if (!rc) {
        sc.p = tab;
        sc.end = pc.p = tab + parts_at;
        pc.end = fc.p = tab + files_at;
        fc.end = tab + inflated;
        rc = parse_tables(ps, &sc, &pc, &fc, nsrc, nfiles, want);
    }
    free(tab);
    if (!rc && build_len && !want) {
        ps->build = (uint8_t *)malloc((size_t)build_len);
        if (!ps->build) rc = TITLE_E_MEM;
        else if (read(ctx, handle, build_off, ps->build, (size_t)build_len)) rc = TITLE_E_IO;
        ps->build_len = (size_t)build_len;
    }
    if (rc) {
        patchset_close(ps);
        return rc;
    }
    *out = ps;
    return TITLE_OK;
}

int patchset_open(Patchset **out, TitleRead read, void *ctx, void *handle, uint64_t size, int check) {
    return open_set(out, read, ctx, handle, size, check, NULL);
}

int patchset_open_files(Patchset **out, TitleRead read, void *ctx, void *handle, uint64_t size, int check,
                        const char *const *paths, size_t npaths) {
    Want want;
    if (!paths && npaths) return TITLE_E_ARG;
    want.paths = paths;
    want.n = npaths;
    return open_set(out, read, ctx, handle, size, check, &want);
}

int patchset_format(const Patchset *ps) { return (int)ps->format; }
int patchset_region(const Patchset *ps) { return (int)ps->region; }
const char *patchset_edition(const Patchset *ps) { return ps->edition; }
const char *patchset_version(const Patchset *ps) { return ps->version; }
const uint8_t *patchset_build_data(const Patchset *ps, size_t *len) {
    if (len) *len = ps->build_len;
    return ps->build;
}
void patchset_drop_build_data(Patchset *ps) {
    if (!ps) return;
    free(ps->build);
    ps->build = NULL;
    ps->build_len = 0;
}
int patchset_second_game(const Patchset *ps, uint64_t *title_id, uint8_t romfs_hash[32]) {
    if (ps->format != PS_FORMAT_SECOND) return 0;
    if (title_id) *title_id = ps->second_title;
    if (romfs_hash) memcpy(romfs_hash, ps->second_hash, 32);
    return 1;
}

size_t patchset_source_count(const Patchset *ps) { return ps->nsrc; }
int patchset_source_info(const Patchset *ps, size_t i, PatchsetSourceInfo *info) {
    if (i >= ps->nsrc || !info) return TITLE_E_ARG;
    info->kind = ps->src[i].kind;
    info->path = ps->src[i].path;
    info->size = ps->src[i].size;
    memcpy(info->sha256, ps->src[i].sha, 32);
    return TITLE_OK;
}

/* ---- sources ----------------------------------------------------------------------------------------------------- */

int patchset_bind(Patchset *ps, size_t i, const PatchsetBinding *b) {
    PsSrc *s;
    if (!ps || !b || i >= ps->nsrc) return TITLE_E_ARG;
    s = &ps->src[i];
    if (!b->mem && !b->blz && b->size != s->size) return TITLE_E_GAME;
    if (b->mem && b->size != s->size) return TITLE_E_GAME;
    parts_drop(ps);
    free(s->plain);
    free(s->arc);
    s->plain = NULL;
    s->arc = NULL;
    s->arc_loaded = 0;
    s->b = *b;
    s->bound = 1;
    return TITLE_OK;
}

/* A RomFS file of `d` bound as source `i`. */
static int bind_file(Patchset *ps, size_t i, Dump *d) {
    const RomfsFile *f = dump_find(d, ps->src[i].path);
    PatchsetBinding b;
    if (!f) return TITLE_E_GAME;
    memset(&b, 0, sizeof b);
    b.handle = f->handle;
    b.offset = f->offset;
    b.size = f->size;
    return patchset_bind(ps, i, &b);
}

int patchset_bind_dump(Patchset *ps, const Dump *dump) {
    Dump *d = (Dump *)dump;
    size_t i, k;
    int rc;
    if (!ps || !d) return TITLE_E_ARG;
    if (d->region != (int)ps->region) return TITLE_E_GAME;
    memcpy(ps->exheader, d->exheader, EXHEADER_SIZE);
    ncch_common_exheader(ps->exheader);
    for (i = 0; i < ps->nsrc; i++) {
        PsSrc *s = &ps->src[i];
        PatchsetBinding b;
        memset(&b, 0, sizeof b);
        if (s->kind == PS_SRC_SECOND) continue;          /* patchset_bind_second_dump's */
        if (s->kind == PS_SRC_FILE) {
            if ((rc = bind_file(ps, i, d))) return rc;
            continue;
        }
        if (s->kind == PS_SRC_EXHEADER) {
            b.mem = ps->exheader;
            b.size = EXHEADER_SIZE;
        } else {
            const DumpExefsFile *code = NULL;
            for (k = 0; k < d->nexefs; k++)
                if (!strcmp(d->exefs[k].name, ".code")) code = &d->exefs[k];
            if (!code) return TITLE_E_GAME;
            b.handle = d->handle;
            b.offset = code->offset;
            b.size = code->len;
            b.blz = d->exheader[0x0D] & 1;
        }
        if ((rc = patchset_bind(ps, i, &b))) return rc;
    }
    return TITLE_OK;
}

int patchset_bind_second_dump(Patchset *ps, const Dump *xx) {
    Dump *d = (Dump *)xx;
    size_t i;
    int rc;
    if (!ps) return TITLE_E_ARG;
    if (ps->format != PS_FORMAT_SECOND) return TITLE_OK;
    if (!d || d->title_id != ps->second_title || memcmp(d->header + DUMP_ROMFS_HASH, ps->second_hash, 32))
        return TITLE_E_GAME;
    for (i = 0; i < ps->nsrc; i++)
        if (ps->src[i].kind == PS_SRC_SECOND && (rc = bind_file(ps, i, d))) return rc;
    return TITLE_OK;
}

/* The decompressed executable, read once: its stored bytes read into the start of the buffer they decompress into (in
 * place, as the console's loader does), so no stored copy is held beside it nor leaves a hole below it. */
static int ensure_plain(Patchset *ps, PsSrc *s) {
    uint8_t footer[8];
    int rc;
    if (s->plain) return TITLE_OK;
    if (s->b.size < 8 || s->b.size > s->size) return TITLE_E_GAME;
    if (ps->read(ps->ctx, s->b.handle, s->b.offset + s->b.size - 8, footer, 8)) return TITLE_E_IO;
    if (blz_size(footer, (size_t)s->b.size) != s->size) return TITLE_E_GAME;
    if (!(s->plain = (uint8_t *)malloc((size_t)s->size))) return TITLE_E_MEM;
    if (ps->read(ps->ctx, s->b.handle, s->b.offset, s->plain, (size_t)s->b.size)) rc = TITLE_E_IO;
    else rc = blz_decompress_in_place(s->plain, (size_t)s->b.size, (size_t)s->size) ? TITLE_E_GAME : TITLE_OK;
    if (rc) {
        free(s->plain);
        s->plain = NULL;
    }
    return rc;
}

static int src_read(Patchset *ps, PsSrc *s, uint64_t off, void *buf, size_t n) {
    int rc;
    if (!s->bound) return TITLE_E_ARG;
    if (off > s->size || n > s->size - off) return TITLE_E_FORMAT;
    if (s->b.mem) {
        memcpy(buf, s->b.mem + off, n);
        return TITLE_OK;
    }
    if (s->b.blz) {
        if ((rc = ensure_plain(ps, s))) return rc;
        memcpy(buf, s->plain + off, n);
        return TITLE_OK;
    }
    return ps->read(ps->ctx, s->b.handle, s->b.offset + off, buf, n) ? TITLE_E_IO : TITLE_OK;
}

int patchset_verify_source(Patchset *ps, size_t i, TitleProgress progress, void *progress_ctx) {
    PsSrc *s;
    Sha256 sha;
    uint8_t digest[32];
    uint64_t at;
    if (!ps || i >= ps->nsrc) return TITLE_E_ARG;
    s = &ps->src[i];
    sha256_init(&sha);
    for (at = 0; at < s->size;) {
        size_t n = s->size - at < CHUNK ? (size_t)(s->size - at) : CHUNK;
        int rc = src_read(ps, s, at, ps->chunk, n);
        if (rc) return rc == TITLE_E_FORMAT ? TITLE_E_GAME : rc;
        sha256_update(&sha, ps->chunk, n);
        at += n;
        if (progress && progress(progress_ctx, at, s->size)) return TITLE_E_CANCEL;
    }
    sha256_final(&sha, digest);
    return memcmp(digest, s->sha, 32) ? TITLE_E_HASH : TITLE_OK;
}

/* The source's ARC table, read once. Any version: MH4U's ARCs are 19, MH XX's may be 17, with the same table. */
static int arc_load(Patchset *ps, PsSrc *s) {
    uint8_t head[ARC_HEADER], *table;
    uint32_t n, k;
    int rc;
    if (s->arc_loaded) return TITLE_OK;
    if ((rc = src_read(ps, s, 0, head, sizeof head))) return rc;
    if (memcmp(head, "ARC\0", 4)) return TITLE_E_GAME;
    n = (uint32_t)head[6] | (uint32_t)head[7] << 8;
    table = (uint8_t *)malloc((size_t)n * ARC_ENTRY + 1);
    s->arc = (ArcEnt *)calloc(n ? n : 1, sizeof(ArcEnt));
    if (!table || !s->arc) {
        free(table);
        free(s->arc);
        s->arc = NULL;
        return TITLE_E_MEM;
    }
    rc = src_read(ps, s, ARC_HEADER, table, (size_t)n * ARC_ENTRY);
    for (k = 0; !rc && k < n; k++) {
        const uint8_t *e = table + (size_t)k * ARC_ENTRY + ARC_NAME;
        ArcEnt *a = &s->arc[k];
        a->type = get_le32(e);
        a->csize = get_le32(e + 4);
        a->size = get_le32(e + 8) & ARC_MAX_SIZE;
        a->flags = get_le32(e + 8) >> 24;
        a->off = get_le32(e + 12);
        if (a->off > s->size || a->csize > s->size - a->off) rc = TITLE_E_GAME;
    }
    free(table);
    if (rc) {
        free(s->arc);
        s->arc = NULL;
        return rc;
    }
    s->narc = n;
    s->arc_loaded = 1;
    return TITLE_OK;
}

/* The decompressed data of entry `k` of an ARC source, in a new buffer. */
static int arc_entry_data(Patchset *ps, PsSrc *s, uint32_t k, uint8_t **out) {
    ArcEnt *a;
    uint8_t *z, *data;
    int rc;
    if ((rc = arc_load(ps, s))) return rc;
    if (k >= s->narc) return TITLE_E_FORMAT;
    a = &s->arc[k];
    z = (uint8_t *)malloc(a->csize ? a->csize : 1);
    data = (uint8_t *)malloc(a->size ? a->size : 1);
    if (!z || !data) {
        free(z);
        free(data);
        return TITLE_E_MEM;
    }
    rc = src_read(ps, s, a->off, z, a->csize);
    if (!rc && zm_inflate(z, a->csize, data, a->size)) rc = TITLE_E_GAME;
    free(z);
    if (rc) {
        free(data);
        return rc;
    }
    *out = data;
    return TITLE_OK;
}

/* ---- bases: parts joined -------------------------------------------------------------------------------------------
 * A record's base is its parts' data joined in order; COPY offsets index the join. A whole source is read where it is
 * (the executable from its decompressed copy); an ARC entry is inflated into the part cache, which keeps the current
 * file's parts so a part several of its entries copy from is inflated once: up to PART_BUDGET bytes beside the parts of
 * the record being made, all of it dropped when another file begins. */

static void parts_drop(Patchset *ps) {
    size_t k;
    for (k = 0; k < ps->npc; k++) free(ps->pc[k].data);
    free(ps->pc);
    ps->pc = NULL;
    ps->npc = ps->pc_cap = 0;
    ps->pc_bytes = 0;
    ps->pc_file = (size_t)-1;
}

/* File `i` begins (or goes on): another file's parts are dropped. */
static void parts_for_file(Patchset *ps, size_t i) {
    if (ps->pc_file != i) parts_drop(ps);
    ps->pc_file = i;
}

static PsCached *parts_find(Patchset *ps, const PsPart *p) {
    size_t k;
    for (k = 0; k < ps->npc; k++)
        if (ps->pc[k].src == p->src && ps->pc[k].entry == p->entry) return &ps->pc[k];
    return NULL;
}

/* Room for `room` more bytes: the oldest parts the current base does not use go first. */
static void parts_evict(Patchset *ps, uint64_t room) {
    size_t k = 0;
    while (k < ps->npc && ps->pc_bytes + room > PART_BUDGET) {
        if (ps->pc[k].stamp == ps->pc_stamp) {
            k++;
            continue;
        }
        ps->pc_bytes -= ps->pc[k].len;
        free(ps->pc[k].data);
        memmove(&ps->pc[k], &ps->pc[k + 1], (ps->npc - k - 1) * sizeof *ps->pc);
        ps->npc--;
    }
}

/* An ARC entry part's data, inflated once while its file is made. */
static int parts_get(Patchset *ps, const PsPart *p, const uint8_t **data, uint64_t *len) {
    PsSrc *s = &ps->src[p->src];
    PsCached *c = parts_find(ps, p);
    uint8_t *d;
    int rc;
    if (!c) {
        if ((rc = arc_load(ps, s))) return rc;
        if (p->entry >= s->narc) return TITLE_E_FORMAT;
        parts_evict(ps, s->arc[p->entry].size);
        if (ps->npc == ps->pc_cap) {
            size_t cap = ps->pc_cap ? ps->pc_cap * 2 : 16;
            PsCached *grown = (PsCached *)realloc(ps->pc, cap * sizeof *grown);
            if (!grown) return TITLE_E_MEM;
            ps->pc = grown;
            ps->pc_cap = cap;
        }
        if ((rc = arc_entry_data(ps, s, p->entry, &d))) return rc;
        c = &ps->pc[ps->npc++];
        c->src = p->src;
        c->entry = p->entry;
        c->len = s->arc[p->entry].size;
        c->data = d;
        ps->pc_bytes += c->len;
    }
    c->stamp = ps->pc_stamp;
    *data = c->data;
    *len = c->len;
    return TITLE_OK;
}

typedef struct {
    const BasePart *p;
    uint32_t n;
    uint64_t size;           /* of the join; 0 with no parts */
} Base;

/* The base of `count` parts from `first`, its ARC entries inflated. Valid until the next get_base. */
static int get_base(Patchset *ps, uint32_t first, uint32_t count, Base *b) {
    uint64_t at = 0;
    uint32_t k;
    int rc;
    memset(b, 0, sizeof *b);
    if (!count) return TITLE_OK;
    if (count > ps->bp_cap) {
        BasePart *grown = (BasePart *)realloc(ps->bp, (size_t)count * sizeof *grown);
        if (!grown) return TITLE_E_MEM;
        ps->bp = grown;
        ps->bp_cap = count;
    }
    ps->pc_stamp++;
    for (k = 0; k < count; k++) {        /* the parts already in memory are this base's: none is evicted for another */
        PsCached *c = parts_find(ps, &ps->parts[first + k]);
        if (c) c->stamp = ps->pc_stamp;
    }
    for (k = 0; k < count; k++) {
        const PsPart *p = &ps->parts[first + k];
        BasePart *bp = &ps->bp[k];
        bp->src = &ps->src[p->src];
        bp->mem = NULL;
        bp->at = at;
        if (!bp->src->bound) return TITLE_E_ARG;
        if (p->entry == PS_NONE) bp->size = bp->src->size;
        else if ((rc = parts_get(ps, p, &bp->mem, &bp->size))) return rc;
        at += bp->size;
    }
    b->p = ps->bp;
    b->n = count;
    b->size = at;
    return TITLE_OK;
}

static int base_read(Patchset *ps, const Base *b, uint64_t off, uint8_t *buf, size_t n) {
    uint32_t k = 0;
    int rc;
    if (off > b->size || n > b->size - off) return TITLE_E_FORMAT;
    while (n) {
        const BasePart *p;
        uint64_t in;
        size_t take;
        while (k < b->n && off >= b->p[k].at + b->p[k].size) k++;
        if (k == b->n) return TITLE_E_FORMAT;
        p = &b->p[k];
        in = off - p->at;
        take = p->size - in < n ? (size_t)(p->size - in) : n;
        if (p->mem) memcpy(buf, p->mem + in, take);
        else if ((rc = src_read(ps, p->src, in, buf, take))) return rc;
        buf += take;
        off += take;
        n -= take;
    }
    return TITLE_OK;
}

int patchset_executable(Patchset *ps, int keep) {
    size_t i;
    int rc;
    if (!ps) return TITLE_E_ARG;
    parts_drop(ps);
    for (i = 0; i < ps->nsrc; i++) {
        PsSrc *s = &ps->src[i];
        if (!s->bound || !s->b.blz) continue;
        if (!keep) {
            free(s->plain);
            s->plain = NULL;
        } else if ((rc = ensure_plain(ps, s))) {
            return rc;
        }
    }
    for (i = 0; keep && i < ps->nfiles; i++) {     /* the rest of its base (an MH XX entry) in memory too */
        if (!strcmp(ps->files[i].path, CODE_PATH)) {
            Base b;
            parts_for_file(ps, i);
            return get_base(ps, ps->files[i].part, ps->files[i].nparts, &b);
        }
    }
    return TITLE_OK;
}

/* ---- running a unit's operations ------------------------------------------------------------------------------- */

typedef int (*Sink)(void *ctx, const uint8_t *buf, size_t n);

typedef struct {
    Patchset *ps;
    uint64_t pos, end;
    uint8_t buf[OPS_BUF];
    size_t at, have;
} OpsReader;

static int ops_get(OpsReader *r, uint8_t *dst, size_t n) {
    while (n) {
        size_t take;
        if (r->at == r->have) {
            uint64_t left = r->end - r->pos;
            size_t want = left < OPS_BUF ? (size_t)left : OPS_BUF;
            if (!want) return TITLE_E_FORMAT;
            if (r->ps->read(r->ps->ctx, r->ps->handle, r->ps->ops_base + r->pos, r->buf, want)) return TITLE_E_IO;
            r->pos += want;
            r->at = 0;
            r->have = want;
        }
        take = r->have - r->at < n ? r->have - r->at : n;
        memcpy(dst, r->buf + r->at, take);
        r->at += take;
        dst += take;
        n -= take;
    }
    return TITLE_OK;
}

static int ops_varint(OpsReader *r, uint64_t *v) {
    int shift;
    *v = 0;
    for (shift = 0; shift < 64; shift += 7) {
        uint8_t b;
        int rc = ops_get(r, &b, 1);
        if (rc) return rc;
        *v |= (uint64_t)(b & 0x7F) << shift;
        if (!(b & 0x80)) return TITLE_OK;
    }
    return TITLE_E_FORMAT;
}

static int ops_done(const OpsReader *r) { return r->pos == r->end && r->at == r->have; }

/* A literal chunk's buffer grown to `n` bytes (in steps of CHUNK): sized to the chunks the set has, not the format's
 * largest (the executable's are a few KB: its making does not hold 2 MiB for them). */
static int work_room(uint8_t **buf, size_t *cap, size_t n) {
    if (n <= *cap) return TITLE_OK;
    n = (n + CHUNK - 1) / CHUNK * CHUNK;
    free(*buf);
    *cap = 0;
    if (!(*buf = (uint8_t *)malloc(n))) return TITLE_E_MEM;
    *cap = n;
    return TITLE_OK;
}

/* Runs the operations at `ops_off` (relative to the ops area) of length `ops_len`, which must produce `expect` bytes
 * for `sink`. Copies read from `base`. */
static int run_ops(Patchset *ps, uint64_t ops_off, uint64_t ops_len, const Base *base, uint64_t expect, Sink sink,
                   void *sctx) {
    OpsReader *r = (OpsReader *)malloc(sizeof *r);
    uint64_t produced = 0;
    int64_t cursor = 0;
    int rc = TITLE_OK;
    if (!r) return TITLE_E_MEM;
    r->ps = ps;
    r->pos = ops_off;
    r->end = ops_off + ops_len;
    r->at = r->have = 0;
    while (!rc && !ops_done(r)) {
        uint8_t op;
        uint64_t a, b, left;
        if ((rc = ops_get(r, &op, 1))) break;
        if (op == OP_COPY) {
            int64_t off;
            if ((rc = ops_varint(r, &a)) || (rc = ops_varint(r, &b))) break;
            off = cursor + (int64_t)((a >> 1) ^ ((uint64_t)0 - (a & 1)));
            if (off < 0 || b > expect - produced) {
                rc = TITLE_E_FORMAT;
                break;
            }
            for (left = b; left && !rc;) {
                size_t n = left < CHUNK ? (size_t)left : CHUNK;
                if ((rc = base_read(ps, base, (uint64_t)off + (b - left), ps->chunk, n))) break;
                rc = sink(sctx, ps->chunk, n);
                left -= n;
            }
            cursor = off + (int64_t)b;
            produced += b;
        } else if (op == OP_ADD) {
            if ((rc = ops_varint(r, &a))) break;
            if (a > PS_MAX_ADD || a > expect - produced) {
                rc = TITLE_E_FORMAT;
                break;
            }
            for (left = a; left && !rc;) {
                size_t n = left < CHUNK ? (size_t)left : CHUNK;
                if ((rc = ops_get(r, ps->chunk, n))) break;
                rc = sink(sctx, ps->chunk, n);
                left -= n;
            }
            produced += a;
        } else if (op == OP_ADDZ) {
            if ((rc = ops_varint(r, &a)) || (rc = ops_varint(r, &b))) break;
            if (!a || a > PS_MAX_ADD || a > expect - produced || b > PS_MAX_Z) {
                rc = TITLE_E_FORMAT;
                break;
            }
            if ((rc = work_room(&ps->zbuf, &ps->zbuf_cap, (size_t)b)) ||
                (rc = work_room(&ps->zout, &ps->zout_cap, (size_t)a)) || (rc = ops_get(r, ps->zbuf, (size_t)b)))
                break;
            if (zm_inflate(ps->zbuf, (size_t)b, ps->zout, (size_t)a)) {
                rc = TITLE_E_FORMAT;
                break;
            }
            for (left = 0; left < a && !rc;) {
                size_t n = a - left < CHUNK ? (size_t)(a - left) : CHUNK;
                rc = sink(sctx, ps->zout + left, n);
                left += n;
            }
            produced += a;
        } else {
            rc = TITLE_E_FORMAT;
        }
    }
    free(r);
    if (rc) return rc;
    return produced == expect ? TITLE_OK : TITLE_E_SIZE;
}

/* ---- sinks ------------------------------------------------------------------------------------------------------ */

typedef struct {
    const TitleOut *out;
    Sha256 sha;
    int hashing;
    uint64_t done, total;
} OutSink;

static int out_sink(void *c, const uint8_t *buf, size_t n) {
    OutSink *o = (OutSink *)c;
    while (n) {
        size_t k = n < CHUNK ? n : CHUNK;
        if (o->out->write(o->out->ctx, buf, k)) return TITLE_E_IO;
        if (o->hashing) sha256_update(&o->sha, buf, k);
        o->done += k;
        buf += k;
        n -= k;
        if (o->out->progress && o->out->progress(o->out->progress_ctx, o->done, o->total)) return TITLE_E_CANCEL;
    }
    return TITLE_OK;
}

typedef struct { uint8_t *buf; size_t cap, at; } MemSink;
static int mem_sink(void *c, const uint8_t *buf, size_t n) {
    MemSink *m = (MemSink *)c;
    if (n > m->cap - m->at) return TITLE_E_SIZE;
    memcpy(m->buf + m->at, buf, n);
    m->at += n;
    return TITLE_OK;
}

/* ---- files ------------------------------------------------------------------------------------------------------ */

size_t patchset_file_count(const Patchset *ps) { return ps->nfiles; }
int patchset_file_info(const Patchset *ps, size_t i, PatchsetFileInfo *info) {
    const PsFile *f;
    if (i >= ps->nfiles || !info) return TITLE_E_ARG;
    f = &ps->files[i];
    info->kind = f->kind;
    info->path = f->path;
    info->size = f->size;
    info->size_known = f->size_known;
    info->has_hash = f->kind == PS_FILE_PLAIN && (f->flags & 1);
    memcpy(info->sha256, f->sha, 32);
    return TITLE_OK;
}

/* The deflated stream of an ENT_OPS entry: its data made by the operations (and hashed against the set's, when asked),
 * then deflated. *stream is a new buffer. */
static int ops_entry_stream(Patchset *ps, const PsEnt *e, unsigned flags, uint8_t **stream, size_t *len) {
    MemSink m;
    Base base;
    uint8_t *data, *z;
    size_t cap, zlen = 0;
    int rc;
    if ((rc = get_base(ps, e->part, e->nparts, &base))) return rc;
    data = (uint8_t *)malloc(e->size ? e->size : 1);
    if (!data) return TITLE_E_MEM;
    m.buf = data;
    m.cap = e->size;
    m.at = 0;
    if ((rc = run_ops(ps, e->ops_off, e->ops_len, &base, e->size, mem_sink, &m))) {
        free(data);
        return rc;
    }
    if (flags & PS_VERIFY_OUTPUT) {
        uint8_t digest[32];
        sha256_buf(data, e->size, digest);
        if (memcmp(digest, e->sha, 32)) {
            free(data);
            return TITLE_E_HASH;
        }
    }
    cap = zm_deflate_bound(e->size);
    z = (uint8_t *)malloc(cap);
    if (!z) {
        free(data);
        return TITLE_E_MEM;
    }
    rc = zm_deflate(data, e->size, z, cap, &zlen, (int)ps->zlevel) ? TITLE_E_MEM : TITLE_OK;
    free(data);
    if (rc) {
        free(z);
        return rc;
    }
    *stream = z;
    *len = zlen;
    return TITLE_OK;
}

static uint64_t arc_prefix(const PsFile *f) { return ARC_HEADER + (uint64_t)ARC_ENTRY * f->nent + ARC_GAP; }

/* The source and ARC entry a copied entry (ENT_REF) is, of either game. */
static PsSrc *ref_source(Patchset *ps, const PsEnt *e, uint32_t *entry) {
    const PsPart *p = &ps->parts[e->part];
    *entry = p->entry;
    return &ps->src[p->src];
}

/* Makes every entry's stream size known; with `keep` the deflated streams of the changed entries stay (up to the
 * budget) for the writing pass. */
static int arc_size(Patchset *ps, PsFile *f, unsigned flags, int keep, TitleProgress progress, void *pctx) {
    uint64_t kept = 0, total = arc_prefix(f);
    uint32_t k;
    int rc;
    for (k = 0; k < f->nent; k++) {
        PsEnt *e = &f->ents[k];
        if (e->mode == ENT_REF) {
            uint32_t entry;
            PsSrc *s = ref_source(ps, e, &entry);
            if (!s->bound) return TITLE_E_ARG;
            if ((rc = arc_load(ps, s))) return rc;
            if (entry >= s->narc || s->arc[entry].size != e->size) return TITLE_E_FORMAT;
            e->csize = s->arc[entry].csize;
        } else if (!e->csize) {
            uint8_t *z;
            size_t len;
            if ((rc = ops_entry_stream(ps, e, flags, &z, &len))) return rc;
            e->csize = (uint32_t)len;
            if (keep && kept + len <= ps->keep_budget) {
                e->kept = z;
                kept += len;
            } else {
                free(z);
            }
        }
        total += e->csize;
        if (progress && progress(pctx, k + 1, f->nent)) return TITLE_E_CANCEL;
    }
    if (f->size_known && f->size != total) return TITLE_E_HASH;   /* not the size the caller was given */
    f->size = total;
    f->size_known = 1;
    f->sized = 1;
    return TITLE_OK;
}

int patchset_set_size(Patchset *ps, size_t i, uint64_t size) {
    PsFile *f;
    if (!ps || i >= ps->nfiles) return TITLE_E_ARG;
    f = &ps->files[i];
    if (f->kind == PS_FILE_PLAIN || f->sized) return size == f->size ? TITLE_OK : TITLE_E_HASH;
    f->size = size;
    f->size_known = 1;
    return TITLE_OK;
}

void patchset_keep_budget(Patchset *ps, uint64_t bytes) {
    if (ps) ps->keep_budget = bytes;
}

int patchset_measure(Patchset *ps, size_t i, TitleProgress progress, void *progress_ctx) {
    PsFile *f;
    if (!ps || i >= ps->nfiles) return TITLE_E_ARG;
    f = &ps->files[i];
    if (f->kind == PS_FILE_PLAIN || f->sized) return TITLE_OK;
    parts_for_file(ps, i);
    return arc_size(ps, f, 0, 0, progress, progress_ctx);
}

static int apply_plain(Patchset *ps, PsFile *f, const TitleOut *out, unsigned flags) {
    OutSink o;
    Base base;
    int rc;
    o.out = out;
    o.done = 0;
    o.total = f->size;
    o.hashing = (flags & PS_VERIFY_OUTPUT) && (f->flags & 1);
    sha256_init(&o.sha);
    if ((rc = get_base(ps, f->part, f->nparts, &base))) return rc;
    if ((rc = run_ops(ps, f->ops_off, f->ops_len, &base, f->size, out_sink, &o))) return rc;
    if (o.hashing) {
        uint8_t digest[32];
        sha256_final(&o.sha, digest);
        if (memcmp(digest, f->sha, 32)) return TITLE_E_HASH;
    }
    return TITLE_OK;
}

static int apply_arc(Patchset *ps, PsFile *f, const TitleOut *out, unsigned flags) {
    OutSink o;
    uint8_t *head;
    uint64_t at;
    uint32_t k;
    int rc;
    if (!f->sized && (rc = arc_size(ps, f, flags, 1, NULL, NULL))) return rc;
    o.out = out;
    o.done = 0;
    o.total = f->size;
    o.hashing = 0;
    head = (uint8_t *)calloc(arc_prefix(f), 1);
    if (!head) return TITLE_E_MEM;
    memcpy(head, "ARC\0", 4);
    put_le16(head + 4, f->arc_version);
    put_le16(head + 6, f->nent);
    at = arc_prefix(f);
    for (k = 0; k < f->nent; k++) {
        const PsEnt *e = &f->ents[k];
        uint8_t *row = head + ARC_HEADER + (size_t)k * ARC_ENTRY;
        memcpy(row, e->name, strlen(e->name));
        put_le32(row + ARC_NAME, e->type_hash);
        put_le32(row + ARC_NAME + 4, e->csize);
        put_le32(row + ARC_NAME + 8, e->flags << 24 | e->size);
        put_le32(row + ARC_NAME + 12, (uint32_t)at);
        at += e->csize;
    }
    rc = at > 0xFFFFFFFFull ? TITLE_E_SIZE : out_sink(&o, head, (size_t)arc_prefix(f));
    free(head);
    for (k = 0; !rc && k < f->nent; k++) {
        PsEnt *e = &f->ents[k];
        if (e->mode == ENT_REF) {      /* the game's stream as it is stored, MH4U's or MH XX's */
            uint32_t entry;
            PsSrc *s = ref_source(ps, e, &entry);
            const ArcEnt *a = &s->arc[entry];
            uint64_t done;
            if (flags & PS_VERIFY_COPIES) {
                uint8_t *data, digest[32];
                if ((rc = arc_entry_data(ps, s, entry, &data))) break;
                sha256_buf(data, a->size, digest);
                free(data);
                if (memcmp(digest, e->sha, 32)) rc = TITLE_E_HASH;
            }
            for (done = 0; !rc && done < a->csize;) {
                size_t n = a->csize - done < CHUNK ? (size_t)(a->csize - done) : CHUNK;
                if ((rc = src_read(ps, s, a->off + done, ps->chunk, n))) break;
                rc = out_sink(&o, ps->chunk, n);
                done += n;
            }
        } else {
            uint8_t *z = e->kept;
            size_t len = e->csize;
            e->kept = NULL;
            if (!z && (rc = ops_entry_stream(ps, e, flags, &z, &len))) break;
            if (len != e->csize) rc = TITLE_E_SIZE;
            if (!rc) rc = out_sink(&o, z, len);
            free(z);
        }
    }
    for (k = 0; k < f->nent; k++) {      /* an interrupted run leaves no kept stream behind */
        free(f->ents[k].kept);
        f->ents[k].kept = NULL;
    }
    return rc;
}

int patchset_apply_file(Patchset *ps, size_t i, const TitleOut *out, unsigned flags) {
    PsFile *f;
    if (!ps || !out || !out->write || i >= ps->nfiles) return TITLE_E_ARG;
    f = &ps->files[i];
    parts_for_file(ps, i);
    return f->kind == PS_FILE_PLAIN ? apply_plain(ps, f, out, flags) : apply_arc(ps, f, out, flags);
}
