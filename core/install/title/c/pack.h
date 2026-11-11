/* The title pack the PC sends to the console (core/install/title_pack.py): the mod in the emulator's form, the title's
 * SMDH, the CIA's certificate chain and the base title's id. Portable C99, bytes only through TitleRead; tests/install/title/test_pack_c.py.
 * A Pack is also the title builder's input (build.h): pack_open fills it from a pack file; the launcher fills it from a
 * patch set (core/install/launcher/c/settitle.c), its files made by the applier as they stream (`gen`).
 *
 * Format (little endian):
 *   header 0x40   "MH4UTITL" | version u32 | region u32 (0 EUR, 1 USA) | title id u64 (the base title's) |
 *                 file count u32 | code length u32 | table length u32 | 0 u32 | total bytes of files u64 | 0
 *   exheader      0x800 bytes: the mod's, not yet retitled
 *   smdh          0x36C0 bytes
 *   certificates  0xA00 bytes: the CIA's chain (core/install/title/certs.bin)
 *   code          the mod's executable (exefs/code.bin)
 *   table         per file: path length u16 | path (UTF-8, "/" separated, from the RomFS root) |
 *                 offset u64 (from the pack's start) | size u64 | SHA-256 of the data
 *   data          the files' bytes, in table order
 */
#ifndef PACK_H
#define PACK_H

#include "ncch.h"
#include "romfs.h"
#include "stream.h"
#include "title_io.h"

#define PACK_MAGIC "MH4UTITL"
#define PACK_VERSION 2u
#define PACK_HEADER 0x40u
#define PACK_SMDH_SIZE 0x36C0u
#define PACK_CERTS_SIZE 0xA00u
#define PACK_PATCH_MOUNT "patch:"

typedef struct {
    uint64_t title_id;
    uint32_t region;
    uint64_t total;             /* bytes of the files */
    uint8_t exheader[EXHEADER_SIZE];
    uint8_t smdh[PACK_SMDH_SIZE];
    uint8_t certs[PACK_CERTS_SIZE];
    uint8_t *code;
    size_t code_len;
    uint8_t *exefs_image;       /* optional, a base title's: the ExeFS image whose .code is `code` made in place
                                 * (title_build_exefs_room); the build borrows it, the caller frees it after the build */
    size_t exefs_image_len;
    RomfsFile *files;           /* `handle` is the pack's handle, `offset` from its start */
    uint8_t (*sha)[32];         /* of each file, same order; NULL when not known before the files are made */
    PieceGen gen;               /* NULL: the files are read; else file i's bytes come from gen(gen_ctx, files[i].handle) */
    void *gen_ctx;
    size_t nfiles;
    char *pool;                 /* the paths */
} Pack;

/* TITLE_OK, TITLE_E_FORMAT (not a pack, another version, a table that does not fit the file) or TITLE_E_IO. */
int pack_open(Pack *p, TitleRead read, void *ctx, void *handle, uint64_t pack_size);
void pack_close(Pack *p);
/* Whether the executable reads an update title's files (it names the "patch:" mount): only then an update works. */
int pack_has_patch(const Pack *p);

#endif
