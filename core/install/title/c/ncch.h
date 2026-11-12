/* The installed title's NCCH (CXI): ExeFS image, retitled exheader and the container; byte-identical to
 * core/install/title/ncch.py. Not encrypted (NoCrypto flag), not signed (zero signature). The RomFS is a
 * RomfsImage already prepared (romfs_prepare): the header carries its hash region's SHA-256. Without an exheader the
 * NCCH is a CFA (ncch.py `Cfa`, an add-on content title's: the game data of ): its header
 * and the RomFS at 0x1000, nothing else. */
#ifndef NCCH_H
#define NCCH_H

#include "romfs.h"
#include "title_io.h"

#define NCCH_HEADER_SIZE 0x200u
#define EXHEADER_SIZE 0x800u
#define MEDIA_UNIT 0x200u
#define EXEFS_MAX_FILES 10u

typedef struct {
    const char *name;        /* 1 to 8 ASCII characters */
    const uint8_t *data;
    size_t len;
} ExefsFile;

/* The ExeFS image of `files` (header of entries and reverse-order SHA-256, each file at a multiple of 0x200) in a
 * new buffer the caller frees with free(). */
int exefs_build(const ExefsFile *files, size_t count, uint8_t **out, size_t *len);
/* The same in two steps, for a caller that makes a file's bytes in place: the image's size, then the image written
 * into `img` (`len` bytes, zeroed: the padding is not written). A file whose `data` already points at its place in
 * `img` is not copied. */
int exefs_size(const ExefsFile *files, size_t count, size_t *len);
int exefs_fill(const ExefsFile *files, size_t count, uint8_t *img, size_t len);

/* `exheader` (0x800 bytes, edited in place) with `title_id` as the jump id and `program_id` (0: the same as
 * title_id) as the ARM11 local capabilities' program id and the access descriptor's copy of it. An update title passes
 * its base's id, as the official update's exheader does. First ncch_common_exheader: the copy of the game does not
 * matter. */
int ncch_retitle_exheader(uint8_t *exheader, size_t len, uint64_t title_id, uint64_t program_id);
/* `exheader` (0x800 bytes, edited in place) without what the cartridge and the eShop copies of one game differ in, as
 * ncch.common_exheader: the SD application flag cleared, the access descriptor's signature and NCCH key zeros. */
void ncch_common_exheader(uint8_t *exheader);
/* An update title's id (high word 0004000E): its exheader, NCCH header and TMD take the official update's marks. */
#define NCCH_UPDATE_HIGH 0x0004000Eu
int ncch_is_update(uint64_t title_id);
/* An add-on content title's id (high word 0004008C): a CFA, its own ticket id. */
#define NCCH_ADDON_HIGH 0x0004008Cu
int ncch_is_addon(uint64_t title_id);
uint64_t ncch_save_data_size(const uint8_t *exheader);

typedef struct {
    const uint8_t *template_header;   /* the game's NCCH header, 0x200 bytes */
    uint64_t title_id;
    const uint8_t *exheader;          /* 0x800 bytes, already retitled; NULL: a CFA (no ExeFS, no regions) */
    const uint8_t *exefs;             /* from exefs_build; NULL for a CFA */
    size_t exefs_len;
    RomfsImage *romfs;                /* prepared; or NULL and the three below */
    uint64_t romfs_size;              /* a RomFS streamed elsewhere (kept.c): its size, hash region and that */
    uint32_t romfs_hash_region;       /* region's SHA-256; ncch_stream refuses such an Ncch (build.c streams it */
    const uint8_t *romfs_region_hash; /* by pieces) */
    const uint8_t *plain;             /* regions of the game; len 0 for none */
    size_t plain_len;
    const uint8_t *logo;
    size_t logo_len;
} NcchParams;

typedef struct {
    NcchParams p;
    uint8_t header[NCCH_HEADER_SIZE];
    uint64_t size;                    /* bytes of the whole NCCH */
    uint64_t romfs_bytes;
    uint64_t at_exefs, at_romfs;
    uint64_t at_region[2];            /* in order of appearance */
    const uint8_t *region_data[2];
    size_t region_len[2];
    int region_logo[2];
    int nregions;
} Ncch;

/* Computes the layout and the header. The parameters' buffers must outlive the Ncch. */
int ncch_init(Ncch *n, const NcchParams *p);
/* Writes the whole NCCH, `size` bytes: the RomFS is streamed (second pass over the sources). */
int ncch_stream(const Ncch *n, const TitleOut *out);

#endif
