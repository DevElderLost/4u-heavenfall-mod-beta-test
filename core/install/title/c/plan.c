/* See plan.h. Mirrors build_title.py (mod_manifest, update_files, update_title_id). */
#include "plan.h"

#include <stdlib.h>
#include <string.h>

#define UPDATE_HIGH 0x0004000E00000000ull

static int by_path(const void *a, const void *b) {
    return strcmp(((const ManifestEntry *)a)->path, ((const ManifestEntry *)b)->path);
}

void manifest_free(Manifest *m) {
    size_t i;
    if (!m) return;
    for (i = 0; i < m->n; i++) free(m->e[i].path);
    free(m->e);
    memset(m, 0, sizeof *m);
}

static int finish(Manifest *m) {
    size_t i;
    qsort(m->e, m->n, sizeof *m->e, by_path);
    for (i = 1; i < m->n; i++)
        if (!strcmp(m->e[i - 1].path, m->e[i].path)) { manifest_free(m); return TITLE_E_PATH; }
    return TITLE_OK;
}

int manifest_from_pack(Manifest *m, const Pack *p) {
    size_t i;
    memset(m, 0, sizeof *m);
    m->e = (ManifestEntry *)calloc(p->nfiles ? p->nfiles : 1, sizeof *m->e);
    if (!m->e) return TITLE_E_MEM;
    for (i = 0; i < p->nfiles; i++) {
        m->e[i].path = (char *)malloc(strlen(p->files[i].path) + 1);
        if (!m->e[i].path) { m->n = i; manifest_free(m); return TITLE_E_MEM; }
        strcpy(m->e[i].path, p->files[i].path);
        memcpy(m->e[i].sha, p->sha[i], 32);
    }
    m->n = p->nfiles;
    return finish(m);
}

static int hex(int c) {
    return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}

int manifest_parse(Manifest *m, const char *text, size_t len) {
    size_t at = 0, cap = 0, i;
    memset(m, 0, sizeof *m);
    while (at < len) {
        const char *end = memchr(text + at, '\n', len - at);
        size_t line = end ? (size_t)(end - (text + at)) : len - at;
        ManifestEntry *e;
        if (line < 66 || text[at + 64] != ' ') { manifest_free(m); return TITLE_E_FORMAT; }
        if (m->n == cap) {
            size_t ncap = cap ? cap * 2 : 1024;
            ManifestEntry *grown = (ManifestEntry *)realloc(m->e, ncap * sizeof *grown);
            if (!grown) { manifest_free(m); return TITLE_E_MEM; }
            m->e = grown;
            cap = ncap;
        }
        e = &m->e[m->n];
        for (i = 0; i < 32; i++) {
            int hi = hex(text[at + 2 * i]), lo = hex(text[at + 2 * i + 1]);
            if (hi < 0 || lo < 0) { manifest_free(m); return TITLE_E_FORMAT; }
            e->sha[i] = (uint8_t)(hi << 4 | lo);
        }
        e->path = (char *)malloc(line - 65 + 1);
        if (!e->path) { manifest_free(m); return TITLE_E_MEM; }
        memcpy(e->path, text + at + 65, line - 65);
        e->path[line - 65] = 0;
        m->n++;
        at += line + 1;
    }
    return finish(m);
}

int manifest_write(const Manifest *m, TitleWrite write, void *ctx) {
    static const char digits[] = "0123456789abcdef";
    size_t i, k;
    for (i = 0; i < m->n; i++) {
        char hexed[65];
        for (k = 0; k < 32; k++) {
            hexed[2 * k] = digits[m->e[i].sha[k] >> 4];
            hexed[2 * k + 1] = digits[m->e[i].sha[k] & 15];
        }
        hexed[64] = ' ';
        if (strchr(m->e[i].path, '\n')) return TITLE_E_PATH;
        if (write(ctx, hexed, 65) || write(ctx, m->e[i].path, strlen(m->e[i].path)) || write(ctx, "\n", 1))
            return TITLE_E_IO;
    }
    return TITLE_OK;
}

const ManifestEntry *manifest_find(const Manifest *m, const char *path) {
    ManifestEntry key;
    key.path = (char *)path;
    return m->n ? (const ManifestEntry *)bsearch(&key, m->e, m->n, sizeof *m->e, by_path) : NULL;
}

InstallPlan plan_install(const InstallState *s) {
    InstallPlan plan;
    memset(&plan, 0, sizeof plan);
    if (s->base_installed && s->have_manifest && s->pack_has_patch) {
        plan.kind = PLAN_UPDATE;
    } else {
        plan.kind = PLAN_BASE;
        plan.delete_update = s->update_installed;
        plan.save_manifest = 1;
    }
    return plan;
}

uint64_t update_title_id(uint64_t base_title_id) { return UPDATE_HIGH | (base_title_id & 0xFFFFFFFFull); }

int update_files(const Pack *pack, const Manifest *base, Dump *dump, RomfsFile **out, size_t *count) {
    RomfsFile *list;
    Manifest now;
    size_t i, n = 0;
    int rc;
    *out = NULL;
    *count = 0;
    if ((rc = manifest_from_pack(&now, pack))) return rc;
    list = (RomfsFile *)malloc((pack->nfiles + base->n + 1) * sizeof *list);
    if (!list) { manifest_free(&now); return TITLE_E_MEM; }
    for (i = 0; i < pack->nfiles; i++) {
        const ManifestEntry *old = manifest_find(base, pack->files[i].path);
        if (!old || memcmp(old->sha, pack->sha[i], 32)) list[n++] = pack->files[i];
    }
    for (i = 0; i < base->n; i++) {
        const RomfsFile *game;
        if (manifest_find(&now, base->e[i].path)) continue;
        game = dump_find(dump, base->e[i].path);
        if (game) list[n++] = *game;
    }
    manifest_free(&now);
    *out = list;
    *count = n;
    return TITLE_OK;
}
