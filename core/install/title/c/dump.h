/* The player's decrypted MH4U dump, or MH XX's (GodMode9's output): a card image (.3ds, .cci: NCSD, partition 0), a CIA
 * (content 0) or a bare NCCH. Reads its header, exheader, regions, ExeFS files and lists every RomFS file as (path, absolute
 * offset, size), like core/game/executable/romfs.py RomFS.entries(). Portable C99, bytes only through TitleRead; the
 * tests build it on the PC (tests/install/title/test_dump_c.py). */
#ifndef DUMP_H
#define DUMP_H

#include "ncch.h"
#include "romfs.h"
#include "title_io.h"

#define DUMP_ID_EUR 0x0004000000126100ull   /* the base game, EUR */
#define DUMP_ID_USA 0x0004000000126300ull   /* the base game, USA */
#define DUMP_ID_XX 0x0004000000197100ull    /* MH XX (JPN): the second game of an XX set */
#define DUMP_IDENTIFY_BYTES 0x200u
#define DUMP_ROMFS_HASH 0x1E0u              /* the NCCH header's RomFS superblock hash: the game's revision */

/* REGION_JPN is MH XX's: no set or pack is of it, so an XX dump is never taken for the MH4U a title is built from. */
enum { REGION_EUR = 0, REGION_USA = 1, REGION_JPN = 2 };

typedef struct {
    char name[9];
    uint8_t *data;     /* NULL for ".code" and "icon": the title takes those from the mod, the game's are not read */
    size_t len;
    uint64_t offset;   /* where the file's bytes start in the dump (as stored: ".code" may be BLZ-compressed) */
} DumpExefsFile;

typedef struct {
    uint64_t ncch_offset;     /* where the NCCH starts in the file */
    void *handle;             /* the dump's handle, as dump_open got it */
    uint64_t title_id;
    int region;               /* REGION_EUR or REGION_USA; REGION_JPN for MH XX */
    uint8_t header[NCCH_HEADER_SIZE];
    uint8_t exheader[EXHEADER_SIZE];
    uint8_t *plain, *logo;    /* the NCCH's regions, NULL when the game has none */
    size_t plain_len, logo_len;
    DumpExefsFile exefs[EXEFS_MAX_FILES];   /* of ".code", "icon", "banner", "logo", in the game's order */
    size_t nexefs;
    RomfsFile *files;         /* every RomFS file; `handle` is the dump's handle */
    size_t nfiles;
    const RomfsFile **index;  /* by path, built by dump_find */
} Dump;

/* Cheap check of a file (reads its first bytes and, for a CIA, its TMD): where the NCCH starts and its title id.
 * TITLE_OK, TITLE_E_FORMAT (not a game container), TITLE_E_GAME (not a base MH4U of either region nor MH XX),
 * TITLE_E_ENCRYPTED (one of them, not decrypted: `title_id` is set) or TITLE_E_IO. `title_id`/`ncch_offset` may be
 * NULL. */
int dump_identify(TitleRead read, void *ctx, void *handle, uint64_t *title_id, uint64_t *ncch_offset);

/* The RomFS superblock hash of a decrypted game dump_identify takes (its NCCH header at DUMP_ROMFS_HASH): which
 * revision of the game it is, as an XX set's header names it. dump_identify's codes. */
int dump_romfs_hash(TitleRead read, void *ctx, void *handle, uint8_t hash[32]);

/* Everything above and the file list. On failure `d` holds nothing to free. */
int dump_open(Dump *d, TitleRead read, void *ctx, void *handle);
void dump_close(Dump *d);

/* The file with this path (exact, "/" separated), or NULL. Valid for a Dump after dump_open; builds an index on the first
 * call. */
const RomfsFile *dump_find(Dump *d, const char *path);

#endif
