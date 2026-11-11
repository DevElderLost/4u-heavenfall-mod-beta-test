/* The CIA writer; see cia.h. Mirrors core/install/title/cia.py. */
#include "cia.h"

#include <stdlib.h>
#include <string.h>

#include "sha256.h"

#define RSA2048_SHA256 0x010004u
#define SIG_BYTES_2048 0x140u
#define TMD_HEADER 0xC4u
#define TITLE_TYPE_CTR 0x40u
#define DEPENDENCIES 0x40u
#define DEPENDENCIES_SIZE 0x180u
#define CORE_VERSION 0x208u
#define SAVE_DATA_SIZE 0x1C0u

static void text(uint8_t *dst, const char *s) { memcpy(dst, s, strlen(s)); }  /* the rest stays zero */

void cia_ticket(uint64_t title_id, uint8_t out[CIA_TICKET_SIZE]) {
    static const uint32_t index_header[10] = {0x00010014, 0xAC, 0x14, 0x00010014, 0, 0x28, 1, 0x84, 0x84, 0x00030000};
    int i;
    memset(out, 0, CIA_TICKET_SIZE);
    put_be32(out, RSA2048_SHA256);
    text(out + 0x140, "Root-CA00000003-XS0000000c");
    out[0x1BC] = 1;                                                       /* format version */
    /* the ticket id: an add-on content title's is its title id, never its application's (cia.py ticket_id) */
    put_be64(out + 0x1D0, ncch_is_addon(title_id) ? title_id : 0x0004000000000000ull | (title_id & 0xFFFFFFFFull));
    put_be64(out + 0x1DC, title_id);
    for (i = 0; i < 10; i++) put_be32(out + 0x2A4 + 4 * i, index_header[i]);
    out[0x2A4 + 40 + 4] = 0x01;                                           /* content 0 */
}

void cia_tmd(uint64_t title_id, uint64_t save_size, uint64_t content_size, const uint8_t content_hash[32],
             uint16_t title_version, uint8_t out[CIA_TMD_SIZE]) {
    const size_t section = SIG_BYTES_2048, infos_at = section + TMD_HEADER, chunk_at = infos_at + 0x900;
    uint8_t *chunk = out + chunk_at, *infos = out + infos_at;
    memset(out, 0, CIA_TMD_SIZE);
    put_be32(chunk, 0); put_be16(chunk + 4, 0); put_be16(chunk + 6, 0); put_be64(chunk + 8, content_size);
    memcpy(chunk + 16, content_hash, 32);
    put_be16(infos, 0); put_be16(infos + 2, 1);                           /* index offset, command count */
    sha256_buf(chunk, 0x30, infos + 4);
    put_be32(out, RSA2048_SHA256);
    text(out + section, "Root-CA00000003-CP0000000b");
    out[section + 0x40] = 1;                                              /* format version */
    put_be64(out + section + 0x4C, title_id);
    put_be32(out + section + 0x54, TITLE_TYPE_CTR);
    put_le32(out + section + 0x5A, (uint32_t)save_size);                  /* little endian, as makerom */
    if (!title_version && ncch_is_update(title_id)) title_version = CIA_UPDATE_TITLE_VERSION;
    put_be16(out + section + 0x9C, title_version);                        /* title version */
    put_be16(out + section + 0x9E, 1);                                    /* content count */
    sha256_buf(infos, 0x900, out + section + 0xA4);
}

static int hash_write(void *ctx, const void *buf, size_t n) {
    sha256_update((Sha256 *)ctx, buf, n);
    return 0;
}

int cia_content_hash(const Ncch *n, const TitleOut *progress, uint8_t out_hash[32]) {
    Sha256 s;
    TitleOut o;
    int rc;
    if (!n || !out_hash) return TITLE_E_ARG;
    sha256_init(&s);
    o.write = hash_write; o.ctx = &s;
    o.progress = progress ? progress->progress : NULL;
    o.progress_ctx = progress ? progress->progress_ctx : NULL;
    rc = ncch_stream(n, &o);
    if (!rc) sha256_final(&s, out_hash);
    return rc;
}

static uint64_t section_size(const CiaOpts *opts, const Ncch *n) {
    uint64_t certs = opts && opts->certs ? opts->certs_len : CIA_CERT_CHAIN_SIZE;
    uint64_t meta = opts && opts->smdh && n->p.exheader ? CIA_META_SIZE : 0;
    return title_align(CIA_HEADER_SIZE, CIA_ALIGNMENT) + title_align(certs, CIA_ALIGNMENT) +
           title_align(CIA_TICKET_SIZE, CIA_ALIGNMENT) + title_align(CIA_TMD_SIZE, CIA_ALIGNMENT) +
           title_align(n->size, CIA_ALIGNMENT) + title_align(meta, CIA_ALIGNMENT);
}

uint64_t cia_size(const Ncch *n, const CiaOpts *opts) { return section_size(opts, n); }

uint64_t cia_save_size(const Ncch *n, const CiaOpts *opts) {
    if (opts && opts->override_save_size) return opts->save_size;
    return n->p.exheader ? ncch_save_data_size(n->p.exheader) : 0;   /* a CFA: no save data */
}

static void put_section(uint8_t *buf, size_t *at, const void *data, size_t n) {
    memcpy(buf + *at, data, n);
    *at += (size_t)title_align(n, CIA_ALIGNMENT);
}

int cia_head(const Ncch *n, const CiaOpts *opts, const uint8_t content_hash[32], uint8_t **out, size_t *len) {
    uint8_t header[CIA_HEADER_SIZE], ticket[CIA_TICKET_SIZE], tmd[CIA_TMD_SIZE];
    uint8_t *buf;
    size_t size, at = 0;
    if (!n || !content_hash || !opts || !opts->certs || !out || !len) return TITLE_E_ARG;
    cia_ticket(n->p.title_id, ticket);
    cia_tmd(n->p.title_id, cia_save_size(n, opts), n->size, content_hash, opts->title_version, tmd);
    memset(header, 0, sizeof header);
    put_le32(header, CIA_HEADER_SIZE);                  /* then type 0 and version 0 */
    put_le32(header + 8, (uint32_t)opts->certs_len);
    put_le32(header + 12, CIA_TICKET_SIZE);
    put_le32(header + 16, CIA_TMD_SIZE);
    put_le32(header + 20, opts->smdh && n->p.exheader ? CIA_META_SIZE : 0);
    put_le64(header + 24, n->size);
    header[0x20] = 0x80;                                /* content index: content 0 */
    size = (size_t)(title_align(CIA_HEADER_SIZE, CIA_ALIGNMENT) + title_align(opts->certs_len, CIA_ALIGNMENT) +
                    title_align(CIA_TICKET_SIZE, CIA_ALIGNMENT) + title_align(CIA_TMD_SIZE, CIA_ALIGNMENT));
    buf = (uint8_t *)calloc(size, 1);
    if (!buf) return TITLE_E_MEM;
    put_section(buf, &at, header, sizeof header);
    put_section(buf, &at, opts->certs, opts->certs_len);
    put_section(buf, &at, ticket, sizeof ticket);
    put_section(buf, &at, tmd, sizeof tmd);
    *out = buf;
    *len = size;
    return TITLE_OK;
}

int cia_meta(const Ncch *n, const CiaOpts *opts, uint8_t **out, size_t *len) {
    uint8_t *meta;
    if (!n || !opts || !out || !len) return TITLE_E_ARG;
    *out = NULL;
    *len = 0;
    if (!opts->smdh || !n->p.exheader) return TITLE_OK;   /* a CFA has no meta section */
    meta = (uint8_t *)calloc((size_t)title_align(CIA_META_SIZE, CIA_ALIGNMENT), 1);
    if (!meta) return TITLE_E_MEM;
    memcpy(meta, n->p.exheader + DEPENDENCIES, DEPENDENCIES_SIZE);
    memcpy(meta + 0x300, n->p.exheader + CORE_VERSION, 4);
    memcpy(meta + 0x400, opts->smdh, CIA_SMDH_SIZE);
    *out = meta;
    *len = (size_t)title_align(CIA_META_SIZE, CIA_ALIGNMENT);
    return TITLE_OK;
}

int cia_write(const Ncch *n, const CiaOpts *opts, const uint8_t content_hash[32], const TitleOut *out) {
    uint8_t *buf = NULL;
    size_t len = 0;
    int rc;
    if (!n || !content_hash || !out || !out->write || !opts || !opts->certs) return TITLE_E_ARG;
    if ((rc = cia_head(n, opts, content_hash, &buf, &len))) return rc;
    rc = out->write(out->ctx, buf, len) ? TITLE_E_IO : TITLE_OK;
    free(buf);
    if (rc || (rc = ncch_stream(n, out))) return rc;
    if ((rc = title_write_zeros(out, title_align(n->size, CIA_ALIGNMENT) - n->size))) return rc;
    if ((rc = cia_meta(n, opts, &buf, &len))) return rc;
    if (len) rc = out->write(out->ctx, buf, len) ? TITLE_E_IO : TITLE_OK;
    free(buf);
    return rc;
}
