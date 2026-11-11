/* The player's dump; see dump.h. Mirrors core/game/executable/{containers,extract,romfs}.py and
 * core/install/title/ncch.py read_game_parts. */
#include "dump.h"

#include <stdlib.h>
#include <string.h>

#define NONE 0xFFFFFFFFu
#define CIA_HEADER 0x2020u
#define CIA_ALIGN 64u
#define TMD_HEADER 0xC4u
#define TMD_TITLE_ID 0x4Cu
#define TMD_INFO_RECORDS 0x900u
#define TMD_CHUNK 0x30u
#define TMD_MAX 0x100000u
#define CONTENT_ENCRYPTED 0x0001u
#define NO_CRYPTO 0x04u
#define EXEFS_HEADER 0x200u
#define IVFC_HEADER 0x60u
#define LEVEL3_HEADER 0x28u
#define TABLE_MAX (64u << 20)      /* a RomFS metadata table bigger than this is not a game's */
#define EXEFS_FILE_MAX (4u << 20)  /* banner and logo */
#define REGION_MAX (16u << 20)

static uint32_t be32(const uint8_t *p) {
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 | (uint32_t)p[2] << 8 | p[3];
}
static uint64_t be64(const uint8_t *p) { return (uint64_t)be32(p) << 32 | be32(p + 4); }
static uint64_t le64(const uint8_t *p) { return (uint64_t)get_le32(p) | (uint64_t)get_le32(p + 4) << 32; }

/* Where the NCCH starts. An encrypted CIA's TMD gives its title id in `cia_title` (its content cannot be read). */
static int locate(TitleRead read, void *ctx, void *h, uint64_t *at, uint64_t *cia_title) {
    uint8_t head[DUMP_IDENTIFY_BYTES];
    if (read(ctx, h, 0, head, sizeof head)) return TITLE_E_IO;
    if (!memcmp(head + 0x100, "NCSD", 4)) {
        *at = (uint64_t)get_le32(head + 0x120) * MEDIA_UNIT;
        return get_le32(head + 0x124) ? TITLE_OK : TITLE_E_FORMAT;
    }
    if (!memcmp(head + 0x100, "NCCH", 4)) { *at = 0; return TITLE_OK; }
    if (get_le32(head) == CIA_HEADER && (head[4] | head[5]) == 0) {
        uint32_t cert = get_le32(head + 8), ticket = get_le32(head + 12), tmd_size = get_le32(head + 16);
        uint64_t tmd_at = title_align(CIA_HEADER, CIA_ALIGN) + title_align(cert, CIA_ALIGN) +
                          title_align(ticket, CIA_ALIGN);
        uint8_t *tmd;
        uint32_t sig, section, record;
        int rc = TITLE_E_FORMAT;
        if (tmd_size <= TMD_CHUNK || tmd_size > TMD_MAX) return TITLE_E_FORMAT;
        tmd = (uint8_t *)malloc(tmd_size);
        if (!tmd) return TITLE_E_MEM;
        if (read(ctx, h, tmd_at, tmd, tmd_size)) { free(tmd); return TITLE_E_IO; }
        sig = be32(tmd);
        section = sig == 0x010000 || sig == 0x010003 ? 0x240 : sig == 0x010001 || sig == 0x010004 ? 0x140
                : sig == 0x010002 || sig == 0x010005 ? 0x80 : 0;
        record = section + TMD_HEADER + TMD_INFO_RECORDS;
        if (section && tmd_size >= record + TMD_CHUNK && ((uint32_t)tmd[section + 0x9E] << 8 | tmd[section + 0x9F])) {
            *cia_title = be64(tmd + section + TMD_TITLE_ID);
            if (((uint32_t)tmd[record + 6] << 8 | tmd[record + 7]) & CONTENT_ENCRYPTED) rc = TITLE_E_ENCRYPTED;
            else if (be64(tmd + record + 8) >= DUMP_IDENTIFY_BYTES) {
                *at = tmd_at + title_align(tmd_size, CIA_ALIGN);
                rc = TITLE_OK;
            }
        }
        free(tmd);
        return rc;
    }
    return TITLE_E_FORMAT;
}

/* The region of a game the dump reader takes: MH4U's base of either region, or MH XX. 0 for any other title. */
static int known_game(uint64_t id, int *region) {
    if (id == DUMP_ID_EUR) *region = REGION_EUR;
    else if (id == DUMP_ID_USA) *region = REGION_USA;
    else if (id == DUMP_ID_XX) *region = REGION_JPN;
    else return 0;
    return 1;
}

/* The game first, then whether it is decrypted: an encrypted copy of another game is not said to be encrypted. */
static int check_ncch(const uint8_t *header, uint64_t *title_id, int *region) {
    uint64_t id;
    int r;
    if (memcmp(header + 0x100, "NCCH", 4)) return TITLE_E_FORMAT;
    id = le64(header + 0x108);
    if (!known_game(id, &r)) return TITLE_E_GAME;
    if (title_id) *title_id = id;
    if (!(header[0x18F] & NO_CRYPTO)) return TITLE_E_ENCRYPTED;
    if (region) *region = r;
    return TITLE_OK;
}

int dump_identify(TitleRead read, void *ctx, void *handle, uint64_t *title_id, uint64_t *ncch_offset) {
    uint8_t header[NCCH_HEADER_SIZE];
    uint64_t at, cia_title = 0;
    int region, rc = locate(read, ctx, handle, &at, &cia_title);
    if (rc == TITLE_E_ENCRYPTED) {
        if (!known_game(cia_title, &region)) return TITLE_E_GAME;
        if (title_id) *title_id = cia_title;
        return rc;
    }
    if (rc) return rc;
    if (read(ctx, handle, at, header, sizeof header)) return TITLE_E_IO;
    rc = check_ncch(header, title_id, NULL);
    if (!rc && ncch_offset) *ncch_offset = at;
    return rc;
}

int dump_romfs_hash(TitleRead read, void *ctx, void *handle, uint8_t hash[32]) {
    uint8_t header[NCCH_HEADER_SIZE];
    uint64_t at;
    int rc = dump_identify(read, ctx, handle, NULL, &at);
    if (rc) return rc;
    if (read(ctx, handle, at, header, sizeof header)) return TITLE_E_IO;
    memcpy(hash, header + DUMP_ROMFS_HASH, 32);
    return TITLE_OK;
}

static int utf16_to_utf8(const uint8_t *src, uint32_t bytes, char **out) {
    uint32_t n = bytes / 2, i;
    char *s, *w;
    if (bytes % 2 || !n) return TITLE_E_FORMAT;
    s = w = (char *)malloc((size_t)n * 3 + 1);
    if (!s) return TITLE_E_MEM;
    for (i = 0; i < n; i++) {
        uint32_t c = src[2 * i] | (uint32_t)src[2 * i + 1] << 8;
        if (c >= 0xD800 && c < 0xDC00) {
            uint32_t d;
            if (i + 1 >= n) { free(s); return TITLE_E_FORMAT; }
            d = src[2 * i + 2] | (uint32_t)src[2 * i + 3] << 8;
            if (d < 0xDC00 || d > 0xDFFF) { free(s); return TITLE_E_FORMAT; }
            c = 0x10000 + ((c - 0xD800) << 10) + (d - 0xDC00);
            i++;
        } else if (c >= 0xDC00 && c <= 0xDFFF) { free(s); return TITLE_E_FORMAT; }
        if (c < 0x80) {
            *w++ = (char)c;
        } else if (c < 0x800) {
            *w++ = (char)(0xC0 | c >> 6);
            *w++ = (char)(0x80 | (c & 0x3F));
        } else if (c < 0x10000) {
            *w++ = (char)(0xE0 | c >> 12);
            *w++ = (char)(0x80 | (c >> 6 & 0x3F));
            *w++ = (char)(0x80 | (c & 0x3F));
        } else {
            *w++ = (char)(0xF0 | c >> 18);
            *w++ = (char)(0x80 | (c >> 12 & 0x3F));
            *w++ = (char)(0x80 | (c >> 6 & 0x3F));
            *w++ = (char)(0x80 | (c & 0x3F));
        }
    }
    *w = 0;
    *out = s;
    return TITLE_OK;
}

typedef struct {
    const uint8_t *dirs, *files;
    uint32_t dirs_len, files_len;
    uint64_t data_start;      /* absolute offset of the file data */
    void *handle;
    Dump *d;
    size_t cap;
    size_t budget;            /* entries still allowed: stops a looping table */
} Walk;

static int add_file(Walk *w, const char *prefix, size_t plen, uint32_t at) {
    const uint8_t *e;
    uint32_t nlen;
    char *name = NULL, *path;
    int rc;
    if (at > w->files_len || w->files_len - at < 0x20) return TITLE_E_FORMAT;
    e = w->files + at;
    nlen = get_le32(e + 0x1C);
    if (nlen > w->files_len - at - 0x20) return TITLE_E_FORMAT;
    if ((rc = utf16_to_utf8(e + 0x20, nlen, &name))) return rc;
    path = (char *)malloc(plen + strlen(name) + 1);
    if (!path) { free(name); return TITLE_E_MEM; }
    memcpy(path, prefix, plen);
    strcpy(path + plen, name);
    free(name);
    if (w->d->nfiles == w->cap) {
        size_t cap = w->cap ? w->cap * 2 : 1024;
        RomfsFile *grown = (RomfsFile *)realloc(w->d->files, cap * sizeof *grown);
        if (!grown) { free(path); return TITLE_E_MEM; }
        w->d->files = grown;
        w->cap = cap;
    }
    w->d->files[w->d->nfiles].path = path;
    w->d->files[w->d->nfiles].offset = w->data_start + le64(e + 8);
    w->d->files[w->d->nfiles].size = le64(e + 16);
    w->d->files[w->d->nfiles].handle = w->handle;
    w->d->nfiles++;
    return TITLE_OK;
}

/* Folders inside folders a RomFS may have (the game's go a few deep): a damaged directory table that points back at
 * itself would otherwise recurse until its entry budget ran out, thousands of levels on a thread's fixed stack. */
#define MAX_DIR_DEPTH 64

static int walk_dir(Walk *w, uint32_t at, const char *prefix, size_t plen, int depth) {
    const uint8_t *e;
    uint32_t child, file;
    int rc;
    if (depth > MAX_DIR_DEPTH) return TITLE_E_FORMAT;
    if (at > w->dirs_len || w->dirs_len - at < 0x18) return TITLE_E_FORMAT;
    e = w->dirs + at;
    child = get_le32(e + 8);
    file = get_le32(e + 12);
    while (child != NONE) {
        const uint8_t *c;
        uint32_t nlen;
        char *name, *sub;
        if (!w->budget--) return TITLE_E_FORMAT;
        if (child > w->dirs_len || w->dirs_len - child < 0x18) return TITLE_E_FORMAT;
        c = w->dirs + child;
        nlen = get_le32(c + 0x14);
        if (nlen > w->dirs_len - child - 0x18) return TITLE_E_FORMAT;
        if ((rc = utf16_to_utf8(c + 0x18, nlen, &name))) return rc;
        sub = (char *)malloc(plen + strlen(name) + 2);
        if (!sub) { free(name); return TITLE_E_MEM; }
        memcpy(sub, prefix, plen);
        strcpy(sub + plen, name);
        strcat(sub, "/");
        rc = walk_dir(w, child, sub, strlen(sub), depth + 1);
        free(sub);
        free(name);
        if (rc) return rc;
        child = get_le32(c + 4);
    }
    while (file != NONE) {
        if (!w->budget--) return TITLE_E_FORMAT;
        if ((rc = add_file(w, prefix, plen, file))) return rc;
        file = get_le32(w->files + file + 4);
    }
    return TITLE_OK;
}

static int read_region(TitleRead read, void *ctx, void *h, uint64_t base, const uint8_t *header, unsigned at,
                       uint8_t **out, size_t *len) {
    uint32_t off = get_le32(header + at), size = get_le32(header + at + 4);
    uint64_t bytes = (uint64_t)size * MEDIA_UNIT;
    *out = NULL;
    *len = 0;
    if (!size) return TITLE_OK;
    if (bytes > REGION_MAX) return TITLE_E_FORMAT;
    *out = (uint8_t *)malloc((size_t)bytes);
    if (!*out) return TITLE_E_MEM;
    if (read(ctx, h, base + (uint64_t)off * MEDIA_UNIT, *out, (size_t)bytes)) {
        free(*out);
        *out = NULL;
        return TITLE_E_IO;
    }
    *len = (size_t)bytes;
    return TITLE_OK;
}

void dump_close(Dump *d) {
    size_t i;
    if (!d) return;
    for (i = 0; i < d->nexefs; i++) free(d->exefs[i].data);
    for (i = 0; i < d->nfiles; i++) free((void *)d->files[i].path);
    free(d->plain);
    free(d->logo);
    free(d->files);
    free((void *)d->index);
    memset(d, 0, sizeof *d);
}

static int read_exefs(Dump *d, TitleRead read, void *ctx, void *h) {
    static const char *const wanted[] = {".code", "icon", "banner", "logo"};
    uint8_t table[EXEFS_HEADER];
    uint32_t off = get_le32(d->header + 0x1A0), size = get_le32(d->header + 0x1A4);
    uint64_t start = d->ncch_offset + (uint64_t)off * MEDIA_UNIT;
    size_t n, k;
    if (!size) return TITLE_E_FORMAT;
    if (read(ctx, h, start, table, sizeof table)) return TITLE_E_IO;
    for (n = 0; n < 10; n++) {
        char name[9];
        uint32_t at = get_le32(table + n * 16 + 8), len = get_le32(table + n * 16 + 12);
        DumpExefsFile *f;
        int known = 0;
        memcpy(name, table + n * 16, 8);
        name[8] = 0;
        for (k = 0; k < 4; k++) known |= !strcmp(name, wanted[k]);
        if (!known) continue;
        f = &d->exefs[d->nexefs++];
        strcpy(f->name, name);
        f->len = len;
        f->offset = start + EXEFS_HEADER + at;
        if (!strcmp(name, ".code") || !strcmp(name, "icon")) continue;
        if (len > EXEFS_FILE_MAX) return TITLE_E_FORMAT;
        f->data = (uint8_t *)malloc(len ? len : 1);
        if (!f->data) return TITLE_E_MEM;
        if (read(ctx, h, start + EXEFS_HEADER + at, f->data, len)) return TITLE_E_IO;
    }
    return TITLE_OK;
}

int dump_open(Dump *d, TitleRead read, void *ctx, void *handle) {
    uint8_t ivfc[IVFC_HEADER], l3[LEVEL3_HEADER];
    uint8_t *dirs = NULL, *files = NULL;
    uint32_t romfs_off, romfs_size, master, block_log, dir_off, dir_len, file_off, file_len, data_off;
    uint64_t start, level3;
    Walk w;
    int rc;
    if (!d || !read) return TITLE_E_ARG;
    memset(d, 0, sizeof *d);
    d->handle = handle;
    if ((rc = locate(read, ctx, handle, &d->ncch_offset, &d->title_id))) return rc;
    if (read(ctx, handle, d->ncch_offset, d->header, sizeof d->header)) return TITLE_E_IO;
    if ((rc = check_ncch(d->header, &d->title_id, &d->region))) return rc;
    if (read(ctx, handle, d->ncch_offset + NCCH_HEADER_SIZE, d->exheader, sizeof d->exheader)) return TITLE_E_IO;
    if ((rc = read_region(read, ctx, handle, d->ncch_offset, d->header, 0x190, &d->plain, &d->plain_len)) ||
        (rc = read_region(read, ctx, handle, d->ncch_offset, d->header, 0x198, &d->logo, &d->logo_len)) ||
        (rc = read_exefs(d, read, ctx, handle)))
        goto fail;

    romfs_off = get_le32(d->header + 0x1B0);
    romfs_size = get_le32(d->header + 0x1B4);
    if (!romfs_size) { rc = TITLE_E_FORMAT; goto fail; }
    start = d->ncch_offset + (uint64_t)romfs_off * MEDIA_UNIT;
    if (read(ctx, handle, start, ivfc, sizeof ivfc)) { rc = TITLE_E_IO; goto fail; }
    if (memcmp(ivfc, "IVFC", 4)) { rc = TITLE_E_FORMAT; goto fail; }
    master = get_le32(ivfc + 8);
    block_log = get_le32(ivfc + 0x4C);
    if (block_log > 24 || master > (1u << 20)) { rc = TITLE_E_FORMAT; goto fail; }
    level3 = start + title_align((uint64_t)IVFC_HEADER + master, (uint64_t)1 << block_log);
    if (read(ctx, handle, level3, l3, sizeof l3)) { rc = TITLE_E_IO; goto fail; }
    dir_off = get_le32(l3 + 12);
    dir_len = get_le32(l3 + 16);
    file_off = get_le32(l3 + 28);
    file_len = get_le32(l3 + 32);
    data_off = get_le32(l3 + 36);
    if (dir_len > TABLE_MAX || file_len > TABLE_MAX || dir_len < 0x18) { rc = TITLE_E_FORMAT; goto fail; }
    dirs = (uint8_t *)malloc(dir_len);
    files = (uint8_t *)malloc(file_len ? file_len : 1);
    if (!dirs || !files) { rc = TITLE_E_MEM; goto fail; }
    if (read(ctx, handle, level3 + dir_off, dirs, dir_len) ||
        (file_len && read(ctx, handle, level3 + file_off, files, file_len))) {
        rc = TITLE_E_IO;
        goto fail;
    }

    memset(&w, 0, sizeof w);
    w.dirs = dirs;
    w.dirs_len = dir_len;
    w.files = files;
    w.files_len = file_len;
    w.data_start = level3 + data_off;
    w.handle = handle;
    w.d = d;
    w.budget = (size_t)(dir_len / 0x18 + file_len / 0x20 + 1);
    rc = walk_dir(&w, 0, "", 0, 0);
    free(dirs);
    free(files);
    if (rc) { dump_close(d); return rc; }
    return TITLE_OK;
fail:
    free(dirs);
    free(files);
    dump_close(d);
    return rc;
}

static int by_path(const void *a, const void *b) {
    return strcmp((*(const RomfsFile *const *)a)->path, (*(const RomfsFile *const *)b)->path);
}

const RomfsFile *dump_find(Dump *d, const char *path) {
    size_t i;
    RomfsFile key;
    const RomfsFile *k = &key;
    const RomfsFile *const *hit;
    memset(&key, 0, sizeof key);
    key.path = path;
    if (!d->index && d->nfiles) {
        d->index = (const RomfsFile **)malloc(d->nfiles * sizeof *d->index);
        if (!d->index) return NULL;
        for (i = 0; i < d->nfiles; i++) d->index[i] = &d->files[i];
        qsort((void *)d->index, d->nfiles, sizeof *d->index, by_path);
    }
    if (!d->index) return NULL;
    hit = (const RomfsFile *const *)bsearch(&k, (void *)d->index, d->nfiles, sizeof *d->index, by_path);
    return hit ? *hit : NULL;
}
