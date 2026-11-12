/* See build.h. */
#include "build.h"

#include <stdlib.h>
#include <string.h>

#include "sha256.h"

#define FAT32_LIMIT (1ull << 32)
#define CIA_SLACK 0x20000u
#define DEFAULT_BUFFERS 2u
#define DEFAULT_BUFFER (1u << 20)
#define GAME_REGION_CAP (1u << 20)   /* the game data's RomFS hash region read at open (build_title.py DumpRomfs) */

/* Checks the bytes a write pass streams from `start` against the level-2 hashes (one per 4 KB block) the build data
 * gave: TITLE_E_HASH at the first block that differs. */
typedef struct {
    uint64_t pos, start, end;   /* stream offsets: the bytes seen; the checked range */
    const uint8_t *want;
    size_t count, done;
    uint8_t block[ROMFS_BLOCK];
    size_t fill;
} TailCheck;

/* The game data's RomFS checked against the dump's own hash levels as a pass streams it: each 4 KB block of level 3
 * hashed, the hashes of each level-2 block's worth of level 3 hashed again (what level 1 must hold for that block),
 * level 1 compared with them and with the master hash (which game_romfs checked against the NCCH header), level 2
 * with them. FS checks the same levels on every read of the installed title, so a dump that fails here makes a game
 * data title the game fails on; AM checks only the content's hash, which a hash pass of the console's own makes from
 * the damaged bytes. One hash per 512 KB of level 3 is kept. */
typedef struct {
    RomfsTree tree;
    uint64_t romfs;             /* the RomFS's first byte in the pass's stream */
    uint64_t pos;               /* the pass's bytes so far */
    uint8_t *master;            /* tree.master_size bytes: the dump's */
    uint8_t *groups;            /* per level-2 block, the SHA-256 level 1 must give it, made from level 3 */
    uint64_t ngroups, made, l1_done, l2_done;
    Sha256 group;               /* the level-2 block being made from level 3's hashes */
    uint32_t group_fill;
    uint8_t block[ROMFS_BLOCK]; /* a block across two buffers, or a last block zero padded */
    uint32_t fill;
    Sha256 *also;               /* the content's hash, when the pass makes it too */
} GameCheck;

struct TitleBuild {
    PlanKind kind;
    Dump *dump;
    const Pack *pack;
    TitleRead read;
    void *read_ctx;
    uint64_t title_id;
    uint8_t exheader[EXHEADER_SIZE];
    ExefsFile exefs_files[EXEFS_MAX_FILES];
    size_t nexefs;
    uint8_t *exefs;
    size_t exefs_len;
    int exefs_borrowed;         /* the image is the pack's (Pack.exefs_image), not freed here */
    RomfsImage *romfs;          /* the update title's */
    KeptRomfs *kept;            /* the base title's, or the mod title's fresh image (kept_open_fresh) */
    uint64_t game_start, game_size;   /* the game data's: the dump's RomFS, where it is and its bytes */
    uint32_t game_region;       /* its superblock hash's region */
    GameCheck *game_check;      /* the game data's hash levels, checked by the first pass that reads them */
    int game_check_on, game_checked;
    size_t nfiles;
    Ncch ncch;
    int prepared, hashed;
    uint8_t region_hash[32];
    uint8_t hash[32];
    uint16_t title_version;     /* the TMD's (0: the default) */
    int digest_used;            /* the build data gave the content hash and the mod's level-2 hashes */
    uint64_t digest_size;       /* the content size it was made for */
    TailCheck check;            /* a write pass after it: the mod's bytes against those hashes */
    /* the pass under way */
    int pass, in_pass;
    PieceList pieces;
    uint8_t *cia_head, *cia_meta;
    Sha256 sha;
};

/* The ExeFS files of `d` for a title of `kind`: `.code` from (code, code_len), the icon from `smdh`, the rest the dump's. */
static int exefs_list(const Dump *d, PlanKind kind, const uint8_t *code, size_t code_len, const uint8_t *smdh,
                      ExefsFile *out, size_t *count) {
    size_t i, n = 0;
    int have_code = 0, have_icon = 0;
    for (i = 0; i < d->nexefs; i++) {
        have_code |= !strcmp(d->exefs[i].name, ".code");
        have_icon |= !strcmp(d->exefs[i].name, "icon");
    }
    if (!have_code || !have_icon) return TITLE_E_FORMAT;
    for (i = 0; i < d->nexefs; i++) {
        const char *name = d->exefs[i].name;
        ExefsFile *f;
        int is_code = !strcmp(name, ".code"), is_icon = !strcmp(name, "icon");
        if (kind == PLAN_UPDATE && !is_code && !is_icon) continue;   /* the official update's ExeFS has only these */
        f = &out[n++];
        f->name = name;
        f->data = is_code ? code : is_icon ? smdh : d->exefs[i].data;
        f->len = is_code ? code_len : is_icon ? PACK_SMDH_SIZE : d->exefs[i].len;
    }
    *count = n;
    return TITLE_OK;
}

int title_build_exefs_room(const Dump *d, size_t code_len, uint8_t **image, size_t *len, size_t *code_off) {
    ExefsFile files[EXEFS_MAX_FILES];
    size_t n, i, at = NCCH_HEADER_SIZE;
    int rc;
    if (!d || !image || !len || !code_off || d->nexefs > EXEFS_MAX_FILES) return TITLE_E_ARG;
    if ((rc = exefs_list(d, PLAN_BASE, NULL, code_len, NULL, files, &n)) || (rc = exefs_size(files, n, len))) return rc;
    for (i = 0; i < n; i++) {
        if (!strcmp(files[i].name, ".code")) *code_off = at;
        at += (size_t)title_align(files[i].len, MEDIA_UNIT);
    }
    *image = (uint8_t *)calloc(*len, 1);
    return *image ? TITLE_OK : TITLE_E_MEM;
}

static int exefs_for(TitleBuild *tb) {
    const Pack *p = tb->pack;
    int rc = exefs_list(tb->dump, tb->kind, p->code, p->code_len, p->smdh, tb->exefs_files, &tb->nexefs);
    if (rc) return rc;
    if (p->exefs_image) {       /* the executable is in its place already: only the header, the hashes and the rest */
        if ((rc = exefs_fill(tb->exefs_files, tb->nexefs, p->exefs_image, p->exefs_image_len))) return rc;
        tb->exefs = p->exefs_image;
        tb->exefs_len = p->exefs_image_len;
        tb->exefs_borrowed = 1;
        return TITLE_OK;
    }
    return exefs_build(tb->exefs_files, tb->nexefs, &tb->exefs, &tb->exefs_len);
}

/* The passes of build.h run over a Stream: the base title, the mod title and the game data. */
static int streamed(const TitleBuild *tb) { return tb->kept || tb->kind == PLAN_GAME; }

static uint64_t le64_at(const uint8_t *p) { return (uint64_t)get_le32(p) | (uint64_t)get_le32(p + 4) << 32; }

/* The dump's hash levels from its IVFC header (`region`, the hash region game_romfs checked), in the layout romfs.c's
 * RomfsTree gives (the game's own RomFS has it, as a real EUR dump shows); any other form, or one that
 * does not fit the dump's RomFS, is TITLE_E_DAMAGED. */
static int game_check_open(TitleBuild *tb, const uint8_t *region) {
    GameCheck *c;
    RomfsTree t;
    uint64_t level3 = le64_at(region + 0x44);
    if (memcmp(region, "IVFC", 4) || get_le32(region + 4) != 0x10000 || !level3 || level3 > tb->game_size)
        return TITLE_E_DAMAGED;
    romfs_tree(&t, level3);
    if (get_le32(region + 8) != t.master_size || le64_at(region + 0x14) != t.l1_size ||
        le64_at(region + 0x2C) != t.l2_size || get_le32(region + 0x1C) != 12 || get_le32(region + 0x34) != 12 ||
        get_le32(region + 0x4C) != 12 || tb->game_region < ROMFS_MASTER_AT + t.master_size || t.size > tb->game_size)
        return TITLE_E_DAMAGED;
    c = (GameCheck *)calloc(1, sizeof *c);
    if (!c) return TITLE_E_MEM;
    c->tree = t;
    c->ngroups = (t.l2_size + ROMFS_BLOCK - 1) / ROMFS_BLOCK;
    c->master = (uint8_t *)malloc(t.master_size);
    c->groups = (uint8_t *)malloc((size_t)c->ngroups * ROMFS_HASH);
    tb->game_check = c;
    if (!c->master || !c->groups) return TITLE_E_MEM;
    memcpy(c->master, region + ROMFS_MASTER_AT, t.master_size);
    return TITLE_OK;
}

static void game_check_free(GameCheck *c) {
    if (!c) return;
    free(c->master);
    free(c->groups);
    free(c);
}

static void game_check_begin(GameCheck *c, uint64_t romfs_at, Sha256 *also) {
    c->romfs = romfs_at;
    c->pos = 0;
    c->made = c->l1_done = c->l2_done = 0;
    c->group_fill = 0;
    c->fill = 0;
    c->also = also;
    sha256_init(&c->group);
}

/* SHA-256 of a block whose first `valid` bytes count, the rest taken as zeros (a level's last block). */
static void block_hash(GameCheck *c, const uint8_t *b, uint64_t valid, uint8_t out[32]) {
    if (valid >= ROMFS_BLOCK) {
        sha256_buf(b, ROMFS_BLOCK, out);
        return;
    }
    if (b != c->block) memcpy(c->block, b, (size_t)valid);
    memset(c->block + valid, 0, ROMFS_BLOCK - (size_t)valid);
    sha256_buf(c->block, ROMFS_BLOCK, out);
}

/* The level-2 block made from level 3's hashes, zero padded as a level's last block is. */
static void group_end(GameCheck *c) {
    static const uint8_t zero[ROMFS_HASH];
    for (; c->group_fill < ROMFS_BLOCK; c->group_fill += ROMFS_HASH) sha256_update(&c->group, zero, ROMFS_HASH);
    if (c->made < c->ngroups) sha256_final(&c->group, c->groups + c->made * ROMFS_HASH);
    c->made++;
    sha256_init(&c->group);
    c->group_fill = 0;
}

/* One 4 KB block of the RomFS, at RomFS offset `o`: level 3's hashed into its group, level 1's and level 2's checked. */
static int game_block(GameCheck *c, uint64_t o, const uint8_t *b) {
    const RomfsTree *t = &c->tree;
    uint8_t h[ROMFS_HASH];
    if (o >= t->l3_start && o < t->l1_start) {
        uint64_t in = o - t->l3_start;
        block_hash(c, b, t->level3_size - in, h);
        sha256_update(&c->group, h, ROMFS_HASH);
        c->group_fill += ROMFS_HASH;
        if (c->group_fill == ROMFS_BLOCK || in + ROMFS_BLOCK >= t->level3_size) group_end(c);
    } else if (o >= t->l1_start && o < t->l2_start) {
        uint64_t in = o - t->l1_start, valid = t->l1_size - in, e, n = valid < ROMFS_BLOCK ? valid : ROMFS_BLOCK;
        if (c->made != c->ngroups) return TITLE_E_DAMAGED;
        for (e = 0; e < n / ROMFS_HASH; e++)
            if (memcmp(b + e * ROMFS_HASH, c->groups + (in + e * ROMFS_HASH), ROMFS_HASH)) return TITLE_E_DAMAGED;
        block_hash(c, b, valid, h);
        if (memcmp(h, c->master + c->l1_done * ROMFS_HASH, ROMFS_HASH)) return TITLE_E_DAMAGED;
        c->l1_done++;
    } else if (o >= t->l2_start && o < t->size) {
        uint64_t in = o - t->l2_start;
        block_hash(c, b, t->l2_size - in, h);
        if (c->l2_done >= c->ngroups || memcmp(h, c->groups + c->l2_done * ROMFS_HASH, ROMFS_HASH))
            return TITLE_E_DAMAGED;
        c->l2_done++;
    }
    return TITLE_OK;
}

static int game_sink(void *ctx, const uint8_t *buf, size_t n) {
    GameCheck *c = (GameCheck *)ctx;
    uint64_t end = c->romfs + c->tree.size, a = c->pos > c->romfs ? c->pos : c->romfs;
    uint64_t b = c->pos + n < end ? c->pos + n : end;
    int rc = TITLE_OK;
    if (c->also) sha256_update(c->also, buf, n);
    while (!rc && a < b) {
        const uint8_t *p = buf + (a - c->pos);
        uint64_t at = (a - c->romfs) / ROMFS_BLOCK * ROMFS_BLOCK;
        if (!c->fill && b - a >= ROMFS_BLOCK) {     /* a whole block in the buffer: no copy */
            rc = game_block(c, at, p);
            a += ROMFS_BLOCK;
        } else {
            size_t take = ROMFS_BLOCK - c->fill < b - a ? ROMFS_BLOCK - c->fill : (size_t)(b - a);
            memcpy(c->block + c->fill, p, take);
            c->fill += (uint32_t)take;
            a += take;
            if (c->fill == ROMFS_BLOCK) {
                c->fill = 0;
                rc = game_block(c, at, c->block);
            }
        }
    }
    c->pos += n;
    return rc;
}

/* After a whole pass: every level seen and checked. */
static int game_check_end(const GameCheck *c) {
    return c->made == c->ngroups && c->l1_done == c->tree.master_size / ROMFS_HASH && c->l2_done == c->ngroups
           ? TITLE_OK : TITLE_E_DAMAGED;
}

/* The game data's RomFS: the dump's region as the NCCH header places it, its hash region checked against the header,
 * its hash levels read for the check of the first pass that streams it. */
static int game_romfs(TitleBuild *tb) {
    const Dump *d = tb->dump;
    uint8_t *region, hash[32];
    int rc = TITLE_OK;
    tb->game_start = d->ncch_offset + (uint64_t)get_le32(d->header + 0x1B0) * MEDIA_UNIT;
    tb->game_size = (uint64_t)get_le32(d->header + 0x1B4) * MEDIA_UNIT;
    tb->game_region = get_le32(d->header + 0x1B8) * MEDIA_UNIT;
    if (!tb->game_size || !tb->game_region || tb->game_region > tb->game_size || tb->game_region > GAME_REGION_CAP)
        return TITLE_E_FORMAT;
    region = (uint8_t *)malloc(tb->game_region);
    if (!region) return TITLE_E_MEM;
    if (tb->read(tb->read_ctx, d->handle, tb->game_start, region, tb->game_region)) rc = TITLE_E_IO;
    if (!rc) {
        sha256_buf(region, tb->game_region, hash);
        if (memcmp(hash, d->header + 0x1E0, 32)) rc = TITLE_E_HASH;   /* a damaged dump */
    }
    if (!rc) rc = tb->game_region >= ROMFS_MASTER_AT ? game_check_open(tb, region) : TITLE_E_DAMAGED;
    free(region);
    return rc;
}

int title_build_open(TitleBuild **out, TitleRead read, void *read_ctx, Dump *dump, const Pack *pack, PlanKind kind,
                     const Manifest *base) {
    TitleBuild *tb;
    RomfsFile *list = NULL;
    size_t count = 0;
    uint64_t base_id;
    int rc;
    if (!out || !dump || !pack || (kind == PLAN_UPDATE && (!base || pack->gen || !pack->sha))) return TITLE_E_ARG;
    if (kind == PLAN_GAME && !dump->handle) return TITLE_E_ARG;
    *out = NULL;
    if ((int)pack->region != dump->region) return TITLE_E_GAME;
    if (kind == PLAN_UPDATE && !pack_has_patch(pack)) return TITLE_E_NOPATCH;
    tb = (TitleBuild *)calloc(1, sizeof *tb);
    if (!tb) return TITLE_E_MEM;
    tb->kind = kind;
    tb->dump = dump;
    tb->pack = pack;
    tb->read = read;
    tb->read_ctx = read_ctx;
    base_id = pack->title_id;
    tb->title_id = kind == PLAN_UPDATE ? update_title_id(base_id) : base_id;
    if (kind == PLAN_GAME) {    /* the dump's RomFS as it is: no executable, no mod files */
        rc = game_romfs(tb);
        if (rc) { title_build_close(tb); return rc; }
        *out = tb;
        return TITLE_OK;
    }
    memcpy(tb->exheader, pack->exheader, EXHEADER_SIZE);
    rc = ncch_retitle_exheader(tb->exheader, EXHEADER_SIZE, tb->title_id, kind == PLAN_UPDATE ? base_id : 0);
    if (!rc) rc = exefs_for(tb);
    if (!rc && kind == PLAN_UPDATE) {
        rc = update_files(pack, base, dump, &list, &count);
        if (!rc) rc = romfs_layout(&tb->romfs, list, count, read, read_ctx);
        free(list);
    } else if (!rc) {
        rc = kind == PLAN_MOD ? kept_open_fresh(&tb->kept, pack->files, pack->nfiles, read, read_ctx)
                              : kept_open(&tb->kept, dump, pack->files, pack->nfiles, read, read_ctx);
        if (!rc) {
            count = kept_file_count(tb->kept);
            if (pack->gen) kept_set_gen(tb->kept, pack->gen, pack->gen_ctx);
        }
    }
    if (rc) { title_build_close(tb); return rc; }
    tb->nfiles = count;
    *out = tb;
    return TITLE_OK;
}

uint64_t title_build_id(const TitleBuild *tb) { return tb->title_id; }
size_t title_build_file_count(const TitleBuild *tb) { return tb->nfiles; }

uint64_t title_build_estimate(const TitleBuild *tb) {
    uint64_t romfs;
    if (tb->kind == PLAN_GAME) return tb->game_size + NCCH_HEADER_SIZE + CIA_SLACK;
    romfs = tb->kept ? kept_size(tb->kept) : romfs_size(tb->romfs);
    return romfs + tb->exefs_len + tb->dump->plain_len + tb->dump->logo_len + CIA_SLACK;
}

/* The NCCH over the prepared RomFS. */
static int make_ncch(TitleBuild *tb) {
    NcchParams p;
    int rc;
    memset(&p, 0, sizeof p);
    p.template_header = tb->dump->header;
    p.title_id = tb->title_id;
    if (tb->kind == PLAN_GAME) {    /* a CFA over the dump's RomFS: its own superblock hash */
        p.romfs_size = tb->game_size;
        p.romfs_hash_region = tb->game_region;
        p.romfs_region_hash = tb->dump->header + 0x1E0;
        if ((rc = ncch_init(&tb->ncch, &p))) return rc;
        if (tb->ncch.size >= FAT32_LIMIT) return TITLE_E_SIZE;
        tb->prepared = 1;
        return TITLE_OK;
    }
    p.exheader = tb->exheader;
    p.exefs = tb->exefs;
    p.exefs_len = tb->exefs_len;
    if (tb->kept) {
        if ((rc = kept_region_hash(tb->kept, tb->region_hash))) return rc;
        p.romfs_size = kept_size(tb->kept);
        p.romfs_hash_region = kept_hash_region_size(tb->kept);
        p.romfs_region_hash = tb->region_hash;
    } else {
        p.romfs = tb->romfs;
    }
    p.plain = tb->dump->plain;
    p.plain_len = tb->dump->plain_len;
    p.logo = tb->dump->logo;
    p.logo_len = tb->dump->logo_len;
    if ((rc = ncch_init(&tb->ncch, &p))) return rc;
    if (tb->ncch.size >= FAT32_LIMIT) return TITLE_E_SIZE;
    tb->prepared = 1;
    return TITLE_OK;
}

static void cia_options(const TitleBuild *tb, CiaOpts *o) {
    memset(o, 0, sizeof *o);
    o->smdh = tb->kind == PLAN_GAME ? NULL : tb->pack->smdh;   /* the game data: no meta section */
    o->certs = tb->pack->certs;
    o->certs_len = PACK_CERTS_SIZE;
    /* save_size 0: the update's, as the official update's TMD; the game data has no save */
    if (tb->kind == PLAN_UPDATE || tb->kind == PLAN_GAME) o->override_save_size = 1;
    o->title_version = tb->title_version;
}

void title_build_set_version(TitleBuild *tb, uint16_t tmd_version) {
    if (tb) tb->title_version = tmd_version;
}

/* ---- the check of a write pass against the build data's level-2 hashes ------------------------------------------ */

static void check_begin(TitleBuild *tb, uint64_t content_at) {
    TailCheck *c = &tb->check;
    c->want = kept_tail_hashes(tb->kept, &c->count);
    c->start = content_at + tb->ncch.at_romfs + kept_tail_start(tb->kept);
    c->end = c->start + (uint64_t)c->count * ROMFS_BLOCK;
    c->pos = 0;
    c->done = 0;
    c->fill = 0;
}

static int check_sink(void *ctx, const uint8_t *buf, size_t n) {
    TailCheck *c = (TailCheck *)ctx;
    uint64_t a = c->pos > c->start ? c->pos : c->start, b = c->pos + n < c->end ? c->pos + n : c->end;
    if (a < b) {
        const uint8_t *p = buf + (a - c->pos);
        size_t left = (size_t)(b - a);
        while (left) {
            uint8_t got[32];
            if (!c->fill && left >= ROMFS_BLOCK) {          /* a whole block in the buffer: no copy */
                sha256_buf(p, ROMFS_BLOCK, got);
                p += ROMFS_BLOCK;
                left -= ROMFS_BLOCK;
            } else {
                size_t take = ROMFS_BLOCK - c->fill < left ? ROMFS_BLOCK - c->fill : left;
                memcpy(c->block + c->fill, p, take);
                c->fill += take;
                p += take;
                left -= take;
                if (c->fill < ROMFS_BLOCK) continue;
                sha256_buf(c->block, ROMFS_BLOCK, got);
                c->fill = 0;
            }
            if (c->done >= c->count || memcmp(got, c->want + c->done * 32, 32)) return TITLE_E_HASH;
            c->done++;
        }
    }
    c->pos += n;
    return 0;
}

/* ---- the base title's passes ----------------------------------------------------------------------------------- */

/* The NCCH's pieces: header, exheader, regions, ExeFS, the RomFS (kept or fresh; the game data: the dump's, one
 * piece), padding. A CFA (the game data) is its header and the RomFS. */
static int content_pieces(const TitleBuild *tb, PieceList *l) {
    const Ncch *n = &tb->ncch;
    uint64_t at = NCCH_HEADER_SIZE;
    int rc, i;
    if ((rc = pieces_mem(l, n->header, NCCH_HEADER_SIZE))) return rc;
    if (n->p.exheader) {
        if ((rc = pieces_mem(l, n->p.exheader, EXHEADER_SIZE))) return rc;
        at += EXHEADER_SIZE;
        for (i = 0; i < n->nregions; i++) {
            if ((rc = pieces_zero(l, n->at_region[i] - at)) ||
                (rc = pieces_mem(l, n->region_data[i], n->region_len[i])))
                return rc;
            at = n->at_region[i] + n->region_len[i];
        }
        if ((rc = pieces_zero(l, n->at_exefs - at)) || (rc = pieces_mem(l, n->p.exefs, n->p.exefs_len))) return rc;
        at = n->at_exefs + n->p.exefs_len;
    }
    if ((rc = pieces_zero(l, n->at_romfs - at))) return rc;
    rc = tb->kept ? kept_pieces(tb->kept, l) : pieces_src(l, tb->dump->handle, tb->game_start, tb->game_size);
    return rc ? rc : pieces_zero(l, n->size - n->at_romfs - n->romfs_bytes);
}

static int sha_sink(void *ctx, const uint8_t *buf, size_t n) {
    sha256_update((Sha256 *)ctx, buf, n);
    return 0;
}

static void end_pass(TitleBuild *tb) {
    pieces_free(&tb->pieces);
    free(tb->cia_head);
    free(tb->cia_meta);
    tb->cia_head = tb->cia_meta = NULL;
    tb->game_check_on = 0;
    tb->in_pass = 0;
}

int title_build_begin(TitleBuild *tb, TitlePass pass, const TitleOut *out, const StreamSetup *setup,
                      TitleProgress progress, void *progress_ctx, Stream **stream) {
    StreamSinks sinks;
    size_t head_len = 0;
    int rc = TITLE_OK;
    if (!tb || !streamed(tb) || !setup || !stream || tb->in_pass) return TITLE_E_ARG;
    if ((pass == TITLE_PASS_CIA || pass == TITLE_PASS_CONTENT) && (!out || !out->write)) return TITLE_E_ARG;
    if (pass != TITLE_PASS_PREPARE && !tb->prepared) return TITLE_E_ARG;
    if (pass == TITLE_PASS_CIA && !tb->hashed) return TITLE_E_ARG;
    *stream = NULL;
    memset(&sinks, 0, sizeof sinks);
    memset(&tb->pieces, 0, sizeof tb->pieces);
    sinks.progress = progress;
    sinks.progress_ctx = progress_ctx;
    tb->in_pass = 1;
    tb->pass = pass;
    if (pass == TITLE_PASS_PREPARE) {
        if (tb->prepared) { tb->in_pass = 0; return TITLE_E_ARG; }
        if (tb->kept) {         /* the game data has nothing to prepare: an empty pass */
            rc = kept_begin(tb->kept);
            if (!rc) rc = kept_seam_pieces(tb->kept, &tb->pieces);
            sinks.hash = kept_seam_hash;
            sinks.hash_ctx = tb->kept;
        }
    } else if (pass == TITLE_PASS_CIA) {
        CiaOpts o;
        size_t meta_len;
        cia_options(tb, &o);
        rc = cia_head(&tb->ncch, &o, tb->hash, &tb->cia_head, &head_len);
        if (!rc) rc = cia_meta(&tb->ncch, &o, &tb->cia_meta, &meta_len);
        if (!rc) rc = pieces_mem(&tb->pieces, tb->cia_head, head_len);
        if (!rc) rc = content_pieces(tb, &tb->pieces);
        if (!rc) rc = pieces_zero(&tb->pieces, title_align(tb->ncch.size, CIA_ALIGNMENT) - tb->ncch.size);
        if (!rc) rc = pieces_mem(&tb->pieces, tb->cia_meta, meta_len);
        if (!rc && tb->digest_used && tb->kept) check_begin(tb, head_len);
    } else {
        rc = content_pieces(tb, &tb->pieces);
        if (pass == TITLE_PASS_HASH || !tb->hashed) {
            sha256_init(&tb->sha);
            sinks.hash = sha_sink;
            sinks.hash_ctx = &tb->sha;
        } else if (tb->digest_used && tb->kept) {
            check_begin(tb, 0);
        }
    }
    /* the mod's bytes against the build data's level-2 hashes (the game data's are the dump's: AM checks the whole) */
    if (pass != TITLE_PASS_PREPARE && pass != TITLE_PASS_HASH && tb->digest_used && tb->kept) {
        sinks.hash = check_sink;
        sinks.hash_ctx = &tb->check;
    }
    /* the game data against the dump's own hash levels, once: by the hash pass, or by the write when the slot gave the hash */
    if (!rc && tb->game_check && !tb->game_checked && pass != TITLE_PASS_PREPARE) {
        game_check_begin(tb->game_check, head_len + tb->ncch.at_romfs, sinks.hash == sha_sink ? &tb->sha : NULL);
        sinks.hash = game_sink;
        sinks.hash_ctx = tb->game_check;
        tb->game_check_on = 1;
    }
    if (out && pass != TITLE_PASS_PREPARE && pass != TITLE_PASS_HASH) {
        sinks.write = out->write;
        sinks.write_ctx = out->ctx;
    }
    if (!rc) rc = stream_open(stream, &tb->pieces, tb->read, tb->read_ctx, &sinks, setup);
    if (rc) end_pass(tb);
    return rc;
}

int title_build_end(TitleBuild *tb, Stream *stream) {
    int rc;
    if (!tb || !tb->in_pass) {
        stream_close(stream);
        return TITLE_E_ARG;
    }
    rc = stream_result(stream);
    stream_close(stream);
    if (!rc && tb->game_check_on && !(rc = game_check_end(tb->game_check))) tb->game_checked = 1;
    if (!rc) {
        if (tb->pass == TITLE_PASS_PREPARE) {
            rc = tb->kept ? kept_finish(tb->kept) : TITLE_OK;
            if (!rc) rc = make_ncch(tb);
            if (!rc && tb->digest_used) {
                if (tb->ncch.size != tb->digest_size) rc = TITLE_E_HASH;   /* made for another layout */
                else tb->hashed = 1;
            }
        } else if ((tb->pass == TITLE_PASS_CIA || tb->pass == TITLE_PASS_CONTENT) && tb->digest_used && tb->kept) {
            if (tb->check.done != tb->check.count) rc = TITLE_E_SIZE;
        } else if (tb->pass == TITLE_PASS_HASH || (tb->pass == TITLE_PASS_CONTENT && !tb->hashed)) {
            sha256_final(&tb->sha, tb->hash);
            tb->hashed = 1;
        }
    }
    end_pass(tb);
    return rc;
}

static int run_pass(TitleBuild *tb, TitlePass pass, const TitleOut *out, TitleProgress progress, void *ctx) {
    StreamSetup setup;
    Stream *s = NULL;
    int rc;
    setup.buffers = DEFAULT_BUFFERS;
    setup.buffer_size = DEFAULT_BUFFER;
    setup.sync = NULL;
    if ((rc = title_build_begin(tb, pass, out, &setup, progress, ctx, &s))) return rc;
    stream_work(s, STREAM_ALL);
    return title_build_end(tb, s);
}

/* ---- the calls on one thread ----------------------------------------------------------------------------------- */

int title_build_prepare(TitleBuild *tb, const HashStore *store, TitleProgress progress, void *progress_ctx) {
    int rc;
    if (!tb) return TITLE_E_ARG;
    if (streamed(tb)) return tb->prepared ? TITLE_OK : run_pass(tb, TITLE_PASS_PREPARE, NULL, progress, progress_ctx);
    if ((rc = romfs_prepare(tb->romfs, store, progress, progress_ctx))) return rc;
    return make_ncch(tb);
}

uint64_t title_build_size(const TitleBuild *tb) {
    CiaOpts o;
    cia_options(tb, &o);
    return tb->prepared ? cia_size(&tb->ncch, &o) : 0;
}

int title_build_hash(TitleBuild *tb, TitleProgress progress, void *progress_ctx) {
    TitleOut none;
    int rc;
    if (!tb || !tb->prepared) return TITLE_E_ARG;
    if (streamed(tb)) return run_pass(tb, TITLE_PASS_HASH, NULL, progress, progress_ctx);
    memset(&none, 0, sizeof none);
    none.progress = progress;
    none.progress_ctx = progress_ctx;
    if ((rc = cia_content_hash(&tb->ncch, &none, tb->hash))) return rc;
    tb->hashed = 1;
    return TITLE_OK;
}

int title_build_write(TitleBuild *tb, const TitleOut *out) {
    CiaOpts o;
    if (!tb || !tb->hashed || !out) return TITLE_E_ARG;
    if (streamed(tb)) return run_pass(tb, TITLE_PASS_CIA, out, out->progress, out->progress_ctx);
    cia_options(tb, &o);
    return cia_write(&tb->ncch, &o, tb->hash, out);
}

/* ---- the content hash and AM's pieces -------------------------------------------------------------------------- */

static int same_sha(const void *data, size_t n, const uint8_t want[32]) {
    uint8_t got[32];
    sha256_buf(data, n, got);
    return !memcmp(got, want, 32);
}

int title_build_use_digest(TitleBuild *tb, const TitleDigest *d) {
    const Pack *p;
    size_t i;
    int rc;
    if (!tb || !d || !streamed(tb) || tb->prepared || tb->in_pass || tb->digest_used) return TITLE_E_ARG;
    if (tb->kind == PLAN_GAME) {    /* the slot's game data hash, when it names this dump's RomFS */
        const DigestGame *g = digest_game(d, tb->dump->header + 0x1E0);
        if (d->format != DIGEST_FORMAT_SPLIT || d->game_title_id != tb->title_id || !g) return TITLE_E_HASH;
        memcpy(tb->hash, g->content_sha256, 32);
        tb->digest_size = g->content_size;
        tb->digest_used = 1;
        return TITLE_OK;
    }
    p = tb->pack;
    if (d->format != (tb->kind == PLAN_MOD ? DIGEST_FORMAT_SPLIT : DIGEST_FORMAT)) return TITLE_E_HASH;
    if (d->title_id != tb->title_id || d->nfiles != p->nfiles ||
        memcmp(d->game_romfs_hash, tb->dump->header + 0x1E0, 32) || !same_sha(p->code, p->code_len, d->code_sha256) ||
        !same_sha(p->exheader, EXHEADER_SIZE, d->exheader_sha256) ||
        !same_sha(p->smdh, PACK_SMDH_SIZE, d->smdh_sha256))
        return TITLE_E_HASH;
    for (i = 0; i < p->nfiles; i++) {
        const DigestFile *f = digest_find(d, p->files[i].path);
        if (!f || f->size != p->files[i].size || (p->sha && memcmp(f->sha256, p->sha[i], 32))) return TITLE_E_HASH;
    }
    if ((rc = kept_use_tail(tb->kept, d->tail, d->ntail))) return rc;
    memcpy(tb->hash, d->content_sha256, 32);
    tb->digest_size = d->content_size;
    tb->digest_used = 1;
    return TITLE_OK;
}

int title_build_has_hash(const TitleBuild *tb) { return tb && tb->hashed; }

int title_build_content_hash(const TitleBuild *tb, uint8_t out[32]) {
    if (!tb || !tb->hashed) return TITLE_E_ARG;
    memcpy(out, tb->hash, 32);
    return TITLE_OK;
}

uint64_t title_build_content_size(const TitleBuild *tb) { return tb && tb->prepared ? tb->ncch.size : 0; }

void title_build_ticket(const TitleBuild *tb, uint8_t out[CIA_TICKET_SIZE]) { cia_ticket(tb->title_id, out); }

int title_build_tmd(const TitleBuild *tb, uint8_t out[CIA_TMD_SIZE]) {
    CiaOpts o;
    if (!tb || !tb->hashed) return TITLE_E_ARG;
    cia_options(tb, &o);
    cia_tmd(tb->title_id, cia_save_size(&tb->ncch, &o), tb->ncch.size, tb->hash, o.title_version, out);
    return TITLE_OK;
}

const uint8_t *title_build_certs(const TitleBuild *tb, size_t *len) {
    if (len) *len = PACK_CERTS_SIZE;
    return tb->pack->certs;
}

void title_build_close(TitleBuild *tb) {
    if (!tb) return;
    end_pass(tb);
    romfs_free(tb->romfs);
    kept_free(tb->kept);
    game_check_free(tb->game_check);
    if (!tb->exefs_borrowed) free(tb->exefs);
    free(tb);
}
