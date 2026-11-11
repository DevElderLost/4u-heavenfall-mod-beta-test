/* The base title's RomFS built around the game's own, byte-identical to core/install/title/kept_romfs.py. The dump's
level 3 stays byte for byte, moved by the smallest
 * multiple of 512 KB that holds the new tables, so the dump's level-2 and level-1 hashes are copied; the mod's files
 * go after it. Only the tables, the seam (the game's last part block, then the mod's files) and the master hash are
 * hashed, so a build reads the game once.
 *
 * Steps: kept_open (layout; reads the dump's headers), kept_begin (the dump's master hash and level 1, checked, and a
 * few level-2 hashes; hashes the tables), the seam pass (kept_seam_pieces through a Stream whose hash stage is
 * kept_seam_hash), kept_finish (level 1 and the master hash); then kept_pieces gives the whole image. kept_prepare does
 * the middle three on the calling thread. */
#ifndef KEPT_H
#define KEPT_H

#include "dump.h"
#include "stream.h"

#define KEPT_SHIFT_UNIT 0x80000u   /* the level 3 one level-1 hash covers */

typedef struct KeptRomfs KeptRomfs;

/* The RomFS of the dump `d` with the `mod` files over it (one whose path is a game file's replaces it). TITLE_E_FORMAT
 * for a RomFS not in the game's form, TITLE_E_HASH when its header does not match the NCCH header's hash,
 * TITLE_E_PATH for a path listed twice. `d` and `mod` must outlive it. */
int kept_open(KeptRomfs **out, const Dump *d, const RomfsFile *mod, size_t nmod, TitleRead read, void *read_ctx);
/* The `mod` files alone in a fresh image, byte-identical to romfs_writer.py's RomfsImage (the split title's mod title):
the tables at level 3's start, then the files in the tables' order, each at 0x10. The
 * same calls as a kept image: kept_begin reads nothing, the seam is the whole level 3 (the tables and the files) and
 * its level-2 hashes are the image's whole level 2 (kept_use_tail, kept_tail_start: level 3's start). TITLE_E_PATH for a
 * path listed twice. `mod` must outlive it. */
int kept_open_fresh(KeptRomfs **out, const RomfsFile *mod, size_t nmod, TitleRead read, void *read_ctx);
/* The mod's files are made as they stream: a file's bytes come from gen(gen_ctx, its handle, ...), not from a read. */
void kept_set_gen(KeptRomfs *k, PieceGen gen, void *gen_ctx);
/* The seam's and the mod's level-2 hashes from the PC's build data (digest.h), `n` of them: then kept_begin and
 * kept_finish need no seam pass. TITLE_E_HASH when their count is not this layout's. */
int kept_use_tail(KeptRomfs *k, const uint8_t *hashes, size_t n);
int kept_begin(KeptRomfs *k);
int kept_seam_pieces(const KeptRomfs *k, PieceList *l);
int kept_seam_hash(void *k, const uint8_t *buf, size_t n);   /* a StreamSinks hash; ctx: the KeptRomfs */
int kept_finish(KeptRomfs *k);
int kept_prepare(KeptRomfs *k, const StreamSetup *setup, TitleProgress progress, void *progress_ctx);

uint64_t kept_size(const KeptRomfs *k);              /* bytes of the whole image */
uint32_t kept_hash_region_size(const KeptRomfs *k);  /* bytes the NCCH's RomFS superblock hash covers */
uint64_t kept_shift(const KeptRomfs *k);
size_t kept_file_count(const KeptRomfs *k);
int kept_region_hash(const KeptRomfs *k, uint8_t out[32]);   /* after kept_finish */
int kept_pieces(const KeptRomfs *k, PieceList *l);           /* the whole image, after kept_finish */
/* Where the seam starts in the image and the level-2 hashes from there to level 3's end (after kept_finish): a write
 * pass that took them from the build data checks the bytes it streams against them. */
uint64_t kept_tail_start(const KeptRomfs *k);
const uint8_t *kept_tail_hashes(const KeptRomfs *k, size_t *n);
void kept_free(KeptRomfs *k);

#endif
