/* The title pack; see pack.h. */
#include "pack.h"

#include <stdlib.h>
#include <string.h>

#define TABLE_MAX (256u << 20)
#define CODE_MAX (64u << 20)

static uint64_t le64(const uint8_t *p) { return (uint64_t)get_le32(p) | (uint64_t)get_le32(p + 4) << 32; }
static uint32_t le16(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8; }

void pack_close(Pack *p) {
    if (!p) return;
    free(p->code);
    free(p->files);
    free(p->sha);
    free(p->pool);
    memset(p, 0, sizeof *p);
}

int pack_open(Pack *p, TitleRead read, void *ctx, void *handle, uint64_t pack_size) {
    uint8_t head[PACK_HEADER];
    uint8_t *table = NULL;
    uint32_t count, table_len;
    uint64_t at, data_start;
    size_t i, used = 0;
    int rc = TITLE_E_FORMAT;
    if (!p || !read) return TITLE_E_ARG;
    memset(p, 0, sizeof *p);
    if (pack_size < PACK_HEADER) return TITLE_E_FORMAT;
    if (read(ctx, handle, 0, head, sizeof head)) return TITLE_E_IO;
    if (memcmp(head, PACK_MAGIC, 8) || get_le32(head + 8) != PACK_VERSION) return TITLE_E_FORMAT;
    p->region = get_le32(head + 12);
    p->title_id = le64(head + 16);
    count = get_le32(head + 24);
    p->code_len = get_le32(head + 28);
    table_len = get_le32(head + 32);
    p->total = le64(head + 40);
    if (p->region > 1 || p->code_len > CODE_MAX || table_len > TABLE_MAX) return TITLE_E_FORMAT;
    at = PACK_HEADER;
    data_start = at + EXHEADER_SIZE + PACK_SMDH_SIZE + PACK_CERTS_SIZE + (uint64_t)p->code_len + table_len;
    if (data_start > pack_size) return TITLE_E_FORMAT;
    if (read(ctx, handle, at, p->exheader, EXHEADER_SIZE) ||
        read(ctx, handle, at + EXHEADER_SIZE, p->smdh, PACK_SMDH_SIZE) ||
        read(ctx, handle, at + EXHEADER_SIZE + PACK_SMDH_SIZE, p->certs, PACK_CERTS_SIZE))
        return TITLE_E_IO;
    at += EXHEADER_SIZE + PACK_SMDH_SIZE + PACK_CERTS_SIZE;
    p->code = (uint8_t *)malloc(p->code_len ? p->code_len : 1);
    table = (uint8_t *)malloc(table_len ? table_len : 1);
    p->files = (RomfsFile *)calloc(count ? count : 1, sizeof *p->files);
    p->sha = (uint8_t(*)[32])calloc(count ? count : 1, 32);
    p->pool = (char *)malloc((size_t)table_len + count + 1);
    if (!p->code || !table || !p->files || !p->sha || !p->pool) { rc = TITLE_E_MEM; goto fail; }
    if (read(ctx, handle, at, p->code, p->code_len) || read(ctx, handle, at + p->code_len, table, table_len)) {
        rc = TITLE_E_IO;
        goto fail;
    }
    at = 0;
    for (i = 0; i < count; i++) {
        uint32_t n;
        RomfsFile *f = &p->files[i];
        rc = TITLE_E_FORMAT;
        if (table_len - at < 2) goto fail;
        n = le16(table + at);
        if (!n || table_len - at - 2 < (uint64_t)n + 8 + 8 + 32) goto fail;
        memcpy(p->pool + used, table + at + 2, n);
        p->pool[used + n] = 0;
        if (strlen(p->pool + used) != n) goto fail;
        f->path = p->pool + used;
        used += n + 1;
        at += 2 + n;
        f->offset = le64(table + at);
        f->size = le64(table + at + 8);
        memcpy(p->sha[i], table + at + 16, 32);
        at += 48;
        f->handle = handle;
        if (f->offset < data_start || f->offset > pack_size || f->size > pack_size - f->offset) goto fail;
    }
    if (at != table_len) goto fail;
    p->nfiles = count;
    free(table);
    return TITLE_OK;
fail:
    free(table);
    pack_close(p);
    return rc;
}

int pack_has_patch(const Pack *p) {
    size_t n = strlen(PACK_PATCH_MOUNT), i;
    if (!p || !p->code || p->code_len < n) return 0;
    for (i = 0; i + n <= p->code_len; i++)
        if (p->code[i] == PACK_PATCH_MOUNT[0] && !memcmp(p->code + i, PACK_PATCH_MOUNT, n)) return 1;
    return 0;
}
