/* The installed title's NCCH; see ncch.h. Mirrors core/install/title/ncch.py. */
#include "ncch.h"

#include <stdlib.h>
#include <string.h>

#include "sha256.h"

#define EXEFS_HEADER 0x200u
#define EXHEADER_HASHED 0x400u
#define SAVE_DATA_SIZE 0x1C0u
#define JUMP_ID 0x1C8u
#define LOCAL_PROGRAM_ID 0x200u
#define ACCESS_DESC_PROGRAM_ID 0x600u
#define ACCESS_DESC_SIGNED 0x400u         /* the access descriptor's signature and the NCCH header's public key */
#define ACCESS_DESC_SIGNED_SIZE 0x200u
#define SCI_FLAGS 0xDu
#define REMASTER_VERSION 0xEu
#define FLAG_SD_APPLICATION 0x02u
#define PRODUCT_KIND 0x154u               /* "CTR-" then P a game, U an update */
#define UPDATE_REMASTER_VERSION 1u
#define FLAG_NO_CRYPTO 0x04u
#define FLAG_FIXED_KEY 0x01u
#define FLAG_SEED 0x20u
#define ROMFS_ALIGNMENT_CAP 0x10000u
#define CFA_ROMFS_ALIGNMENT 0x1000u
#define CONTENT_TYPE_DATA 0x01u           /* the header's 0x18D: data, no executable, application content */
#define PRODUCT_KIND_ADDON 'M'

int exefs_size(const ExefsFile *files, size_t count, size_t *len) {
    size_t total = EXEFS_HEADER, n;
    if (!files || !len || count == 0 || count > EXEFS_MAX_FILES) return TITLE_E_ARG;
    for (n = 0; n < count; n++) {
        size_t nl = files[n].name ? strlen(files[n].name) : 0;
        if (nl == 0 || nl > 8) return TITLE_E_FORMAT;
        total += (size_t)title_align(files[n].len, MEDIA_UNIT);
    }
    *len = total;
    return TITLE_OK;
}

int exefs_fill(const ExefsFile *files, size_t count, uint8_t *img, size_t len) {
    size_t total, n, at = EXEFS_HEADER;
    int rc = exefs_size(files, count, &total);
    if (rc) return rc;
    if (!img || total != len) return TITLE_E_ARG;
    for (n = 0; n < count; n++) {
        uint8_t *entry = img + n * 16;
        memset(entry, 0, 16);
        memcpy(entry, files[n].name, strlen(files[n].name));
        put_le32(entry + 8, (uint32_t)(at - EXEFS_HEADER));
        put_le32(entry + 12, (uint32_t)files[n].len);
        sha256_buf(files[n].data, files[n].len, img + 0xC0 + (EXEFS_MAX_FILES - 1 - n) * 0x20);
        if (files[n].len && files[n].data != img + at) memcpy(img + at, files[n].data, files[n].len);
        at += (size_t)title_align(files[n].len, MEDIA_UNIT);
    }
    return TITLE_OK;
}

int exefs_build(const ExefsFile *files, size_t count, uint8_t **out, size_t *len) {
    size_t total;
    uint8_t *img;
    int rc;
    if (!out || !len) return TITLE_E_ARG;
    if ((rc = exefs_size(files, count, &total))) return rc;
    img = (uint8_t *)calloc(total, 1);
    if (!img) return TITLE_E_MEM;
    if ((rc = exefs_fill(files, count, img, total))) {
        free(img);
        return rc;
    }
    *out = img;
    *len = total;
    return TITLE_OK;
}

void ncch_common_exheader(uint8_t *exheader) {
    exheader[SCI_FLAGS] &= (uint8_t)~FLAG_SD_APPLICATION;
    memset(exheader + ACCESS_DESC_SIGNED, 0, ACCESS_DESC_SIGNED_SIZE);
}

int ncch_retitle_exheader(uint8_t *exheader, size_t len, uint64_t title_id, uint64_t program_id) {
    if (!exheader || len != EXHEADER_SIZE) return TITLE_E_FORMAT;
    ncch_common_exheader(exheader);
    put_le64(exheader + JUMP_ID, title_id);
    put_le64(exheader + LOCAL_PROGRAM_ID, program_id ? program_id : title_id);
    put_le64(exheader + ACCESS_DESC_PROGRAM_ID, program_id ? program_id : title_id);
    if (ncch_is_update(title_id)) {                          /* as the official update's */
        put_le16(exheader + REMASTER_VERSION, UPDATE_REMASTER_VERSION);
        exheader[SCI_FLAGS] |= FLAG_SD_APPLICATION;
    }
    return TITLE_OK;
}

int ncch_is_update(uint64_t title_id) { return (title_id >> 32) == NCCH_UPDATE_HIGH; }
int ncch_is_addon(uint64_t title_id) { return (title_id >> 32) == NCCH_ADDON_HIGH; }

uint64_t ncch_save_data_size(const uint8_t *exheader) {
    return (uint64_t)get_le32(exheader + SAVE_DATA_SIZE) | (uint64_t)get_le32(exheader + SAVE_DATA_SIZE + 4) << 32;
}

static uint32_t mu(uint64_t size) { return (uint32_t)(title_align(size, MEDIA_UNIT) / MEDIA_UNIT); }

/* The RomFS's superblock hash into the header (0x1E0). */
static int region_hash(const NcchParams *p, uint8_t *h) {
    if (p->romfs) return romfs_region_hash(p->romfs, h + 0x1E0);
    memcpy(h + 0x1E0, p->romfs_region_hash, 32);
    return TITLE_OK;
}

/* A CFA (ncch.py `Cfa`): the header made from the template's maker code, NCCH version, product code (kind M) and
 * platform alone, so either copy of a game gives the same bytes; the RomFS at 0x1000. */
static int cfa_init(Ncch *n, const NcchParams *p, uint64_t rsize, uint32_t rregion) {
    const uint8_t *t = p->template_header;
    uint8_t *h = n->header;
    n->at_romfs = CFA_ROMFS_ALIGNMENT;
    n->size = title_align(n->at_romfs + rsize, MEDIA_UNIT);
    memset(h, 0, NCCH_HEADER_SIZE);
    memcpy(h + 0x100, "NCCH", 4);
    put_le32(h + 0x104, (uint32_t)(n->size / MEDIA_UNIT));
    put_le64(h + 0x108, p->title_id);                        /* partition id */
    memcpy(h + 0x110, t + 0x110, 4);                         /* maker code, NCCH version */
    put_le64(h + 0x118, p->title_id);                        /* program id */
    memcpy(h + 0x150, t + 0x150, 16);                        /* product code */
    h[PRODUCT_KIND] = PRODUCT_KIND_ADDON;
    h[0x18C] = t[0x18C];                                     /* platform */
    h[0x18D] = CONTENT_TYPE_DATA;
    h[0x18E] = t[0x18E];                                     /* content unit size */
    h[0x18F] = FLAG_NO_CRYPTO;
    put_le32(h + 0x1B0, (uint32_t)(n->at_romfs / MEDIA_UNIT)); put_le32(h + 0x1B4, mu(rsize));
    put_le32(h + 0x1B8, rregion / MEDIA_UNIT);
    return region_hash(p, h);
}

int ncch_init(Ncch *n, const NcchParams *p) {
    uint8_t *h;
    uint64_t at, template_romfs, step;
    uint32_t off_plain, off_logo;
    int i;
    uint64_t rsize;
    uint32_t rregion;
    if (!n || !p || !p->template_header || (p->exheader && !p->exefs)) return TITLE_E_ARG;
    if (!p->exheader && (p->exefs || p->exefs_len || p->plain_len || p->logo_len)) return TITLE_E_ARG;
    if (!p->romfs && !p->romfs_region_hash) return TITLE_E_ARG;
    if (memcmp(p->template_header + 0x100, "NCCH", 4)) return TITLE_E_FORMAT;
    if ((p->plain_len && !p->plain) || (p->logo_len && !p->logo)) return TITLE_E_ARG;
    rsize = p->romfs ? romfs_size(p->romfs) : p->romfs_size;
    rregion = p->romfs ? romfs_hash_region_size(p->romfs) : p->romfs_hash_region;
    if (rregion % MEDIA_UNIT || !rregion || rregion > rsize) return TITLE_E_FORMAT;
    memset(n, 0, sizeof *n);
    n->p = *p;
    n->romfs_bytes = rsize;
    if (!p->exheader) return cfa_init(n, p, rsize, rregion);

    /* regions in the template's order (ties: the logo first, as sorting the kind names does) */
    off_plain = get_le32(p->template_header + 0x190);
    off_logo = get_le32(p->template_header + 0x198);
    {
        int have_plain = p->plain_len != 0, have_logo = p->logo_len != 0;
        int logo_first = have_logo && (!have_plain || off_logo <= off_plain);
        if (logo_first) {
            n->region_logo[n->nregions] = 1;
            n->region_data[n->nregions] = p->logo; n->region_len[n->nregions++] = p->logo_len;
            if (have_plain) { n->region_data[n->nregions] = p->plain; n->region_len[n->nregions++] = p->plain_len; }
        } else if (have_plain) {
            n->region_data[n->nregions] = p->plain; n->region_len[n->nregions++] = p->plain_len;
            if (have_logo) {
                n->region_logo[n->nregions] = 1;
                n->region_data[n->nregions] = p->logo; n->region_len[n->nregions++] = p->logo_len;
            }
        }
    }
    at = NCCH_HEADER_SIZE + EXHEADER_SIZE;
    for (i = 0; i < n->nregions; i++) {
        n->at_region[i] = at;
        at += title_align(n->region_len[i], MEDIA_UNIT);
    }
    n->at_exefs = at;
    at += title_align(p->exefs_len, MEDIA_UNIT);
    template_romfs = (uint64_t)get_le32(p->template_header + 0x1B0) * MEDIA_UNIT;
    step = template_romfs ? (template_romfs & (~template_romfs + 1)) : MEDIA_UNIT;
    if (step > ROMFS_ALIGNMENT_CAP) step = ROMFS_ALIGNMENT_CAP;
    if (step < MEDIA_UNIT) step = MEDIA_UNIT;
    n->at_romfs = title_align(at, step);
    n->size = title_align(n->at_romfs + rsize, MEDIA_UNIT);

    h = n->header;
    memcpy(h, p->template_header, NCCH_HEADER_SIZE);
    memset(h, 0, 0x100);                                     /* signature */
    put_le32(h + 0x104, (uint32_t)(n->size / MEDIA_UNIT));
    put_le64(h + 0x108, p->title_id);                        /* partition id */
    memset(h + 0x114, 0, 4);                                 /* content lock seed hash */
    put_le64(h + 0x118, p->title_id);                        /* program id */
    if (ncch_is_update(p->title_id)) h[PRODUCT_KIND] = 'U';
    if (p->logo_len) sha256_buf(p->logo, p->logo_len, h + 0x130); else memset(h + 0x130, 0, 0x20);
    sha256_buf(p->exheader, EXHEADER_HASHED, h + 0x160);
    put_le32(h + 0x180, EXHEADER_HASHED);
    h[0x18F] = (uint8_t)((h[0x18F] | FLAG_NO_CRYPTO) & ~(FLAG_FIXED_KEY | FLAG_SEED));
    memset(h + 0x190, 0, 16);
    for (i = 0; i < n->nregions; i++) {
        uint8_t *f = h + (n->region_logo[i] ? 0x198 : 0x190);
        put_le32(f, (uint32_t)(n->at_region[i] / MEDIA_UNIT));
        put_le32(f + 4, mu(n->region_len[i]));
    }
    put_le32(h + 0x1A0, (uint32_t)(n->at_exefs / MEDIA_UNIT)); put_le32(h + 0x1A4, mu(p->exefs_len));
    put_le32(h + 0x1A8, 1);                                  /* the ExeFS hash region: its header */
    put_le32(h + 0x1B0, (uint32_t)(n->at_romfs / MEDIA_UNIT)); put_le32(h + 0x1B4, mu(rsize));
    put_le32(h + 0x1B8, rregion / MEDIA_UNIT);
    sha256_buf(p->exefs, EXEFS_HEADER, h + 0x1C0);
    return region_hash(p, h);
}

typedef struct { const TitleOut *o; uint64_t base, total; } Shift;

static int shifted_progress(void *ctx, uint64_t done, uint64_t total) {
    Shift *s = (Shift *)ctx;
    (void)total;
    return s->o->progress ? s->o->progress(s->o->progress_ctx, s->base + done, s->total) : 0;
}

static int put(const TitleOut *o, const void *buf, size_t n) {
    return n && o->write(o->ctx, buf, n) ? TITLE_E_IO : TITLE_OK;
}

static int pad(const TitleOut *o, uint64_t at, uint64_t to) { return to > at ? title_write_zeros(o, to - at) : TITLE_OK; }

int ncch_stream(const Ncch *n, const TitleOut *out) {
    uint64_t at = NCCH_HEADER_SIZE + EXHEADER_SIZE;
    int rc, i;
    Shift shift;
    TitleOut inner;
    if (!n || !out || !out->write || !n->p.romfs || !n->p.exheader) return TITLE_E_ARG;   /* a CFA: build.c */
    if ((rc = put(out, n->header, NCCH_HEADER_SIZE)) || (rc = put(out, n->p.exheader, EXHEADER_SIZE))) return rc;
    for (i = 0; i < n->nregions; i++) {
        if ((rc = pad(out, at, n->at_region[i])) || (rc = put(out, n->region_data[i], n->region_len[i]))) return rc;
        at = n->at_region[i] + n->region_len[i];
    }
    if ((rc = pad(out, at, n->at_exefs)) || (rc = put(out, n->p.exefs, n->p.exefs_len))) return rc;
    if ((rc = pad(out, n->at_exefs + n->p.exefs_len, n->at_romfs))) return rc;
    shift.o = out; shift.base = n->at_romfs; shift.total = n->size;
    inner = *out;
    inner.progress = out->progress ? shifted_progress : NULL;
    inner.progress_ctx = &shift;
    if ((rc = romfs_stream(n->p.romfs, &inner))) return rc;
    return pad(out, n->at_romfs + romfs_size(n->p.romfs), n->size);
}
