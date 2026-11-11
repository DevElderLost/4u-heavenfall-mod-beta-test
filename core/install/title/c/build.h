/* One title, from the dump and the pack to the CIA's bytes: the steps of core/install/title/build_title.py
 * (build_cia, build_update_cia, build_game_cia, build_mod_cia) over the C writers. tests/install/title/test_install_c.py,
 * test_fast_c.py and tests/install/launcher/test_set_title.py compare the CIAs with the Python ones byte for byte.
 *
 * The split title is two builds of their own kind:
 *   PLAN_GAME  the game data: a CFA over the dump's RomFS as it is (one piece of the dump), an add-on content title
 *              (the pack gives only its title id, region and certificates). Nothing to prepare; the build data's game
 *              entry for the dump's RomFS superblock hash gives the content hash, else a hash pass reads the dump.
 *   PLAN_MOD   the edition's title with the mod's files alone in a fresh RomFS (kept_open_fresh): the same passes as
 *              the base title, the mod's files made once per pass; the build data (format 3) gives the content hash
 *              and the level-2 hashes of the whole RomFS, so one pass writes it.
 *
 * The base title keeps the game's RomFS and its hashes (kept.h), so it
 * reads the game once. Its work goes in passes, each a Stream the caller runs on its own threads (stream.h):
 *   PREPARE  reads and hashes the seam and the mod's files (the dump's own hashes are copied); then the NCCH is ready.
 *            After title_build_use_digest it reads only the dump's hash levels: the build data has the rest.
 *   HASH     the content's SHA-256, for a TMD that goes before the content; reads the whole content, writes nothing.
 *            Not needed after title_build_use_digest.
 *   CIA      the whole CIA through out->write (one read of the game); needs the content hash. After
 *            title_build_use_digest its hashing stage checks the mod's bytes against the build data (TITLE_E_HASH).
 *   CONTENT  the content (the NCCH) alone through out->write, for AM's piece-by-piece install; when the content hash is
 *            not known yet it is computed on the way (a TMD written after the content).
 * The update title is a few MB: its calls (prepare, hash, write) run its three passes over the old writer at once. */
#ifndef BUILD_H
#define BUILD_H

#include "cia.h"
#include "digest.h"
#include "dump.h"
#include "kept.h"
#include "pack.h"
#include "plan.h"
#include "stream.h"

typedef struct TitleBuild TitleBuild;

typedef enum { TITLE_PASS_PREPARE, TITLE_PASS_HASH, TITLE_PASS_CIA, TITLE_PASS_CONTENT } TitlePass;

/* Lists the files (nothing is read but the dump's RomFS headers). `base` is the base title's manifest, needed for
 * PLAN_UPDATE. The dump, the pack and `base` must outlive the build. TITLE_E_GAME when the pack is for the other
 * region; TITLE_E_NOPATCH for an update whose executable cannot read one; TITLE_E_FORMAT / TITLE_E_HASH for a dump
 * whose RomFS the base title cannot keep, or (PLAN_GAME) whose RomFS header is not its NCCH header's. */
/* Room for a base title's ExeFS image over `dump` with a `.code` of `code_len` bytes: a zeroed buffer of the image's size
 * (`*image`, `*len`; the caller frees it) and where the executable goes in it (`*code_off`). The caller makes the
 * mod's executable there and gives the buffer as Pack.exefs_image with Pack.code = *image + *code_off: the image is not
 * built from a second copy of the executable (17 MB less at the open's peak). */
int title_build_exefs_room(const Dump *dump, size_t code_len, uint8_t **image, size_t *len, size_t *code_off);
int title_build_open(TitleBuild **out, TitleRead read, void *read_ctx, Dump *dump, const Pack *pack, PlanKind kind,
                     const Manifest *base);
uint64_t title_build_id(const TitleBuild *tb);          /* the title's id */
size_t title_build_file_count(const TitleBuild *tb);
uint64_t title_build_estimate(const TitleBuild *tb);    /* about the CIA's size, known before any read */

/* A base, mod or game data title's pass as a Stream for the caller's threads: begin, stream_work on each thread, end.
 * `out` is the writer of CIA and CONTENT (its progress is not used: the stream's sinks report progress), NULL for the
 * others. The game data's PREPARE streams nothing. An update title has no passes (TITLE_E_ARG). */
int title_build_begin(TitleBuild *tb, TitlePass pass, const TitleOut *out, const StreamSetup *setup,
                      TitleProgress progress, void *progress_ctx, Stream **stream);
int title_build_end(TitleBuild *tb, Stream *stream);    /* the pass's result; closes the stream */

/* The passes on the calling thread. Pass 1: hashes (`store`: the update title's level-2 hashes; the base title keeps
 * its own in memory, about 32 bytes per 4 KB of the mod). TITLE_E_SIZE when the title would not fit a FAT32 file. */
int title_build_prepare(TitleBuild *tb, const HashStore *store, TitleProgress progress, void *progress_ctx);
uint64_t title_build_size(const TitleBuild *tb);        /* the CIA's exact size, after prepare */
/* Pass 2: the NCCH's SHA-256, which the TMD holds (not needed after title_build_use_digest). */
int title_build_hash(TitleBuild *tb, TitleProgress progress, void *progress_ctx);
/* Pass 3: the whole CIA, title_build_size bytes, through out->write. */
int title_build_write(TitleBuild *tb, const TitleOut *out);

/* Before prepare: the PC's build data (digest.h), when it was made from these very inputs (the title, the dump's
 * revision, the executable, the exheader, the SMDH, every mod file's size and, when the pack has them, SHA-256), gives
 * the content hash and the mod's level-2 hashes: prepare then hashes nothing but the tables, and the write passes check
 * the mod's bytes against those hashes as they stream (TITLE_E_HASH at the first 4 KB that differ; prepare's
 * TITLE_E_HASH when the content's size is not the data's). TITLE_E_HASH here for data made from other inputs. After
 * any TITLE_E_HASH the build is closed and opened again without the data. `d` may be freed after the call.
 * The base title takes format 2, the mod title format 3; the game data takes format 3's game entry for the dump's RomFS
 * superblock hash and the game data's title id (TITLE_E_HASH without one: a dump the PC did not know). */
int title_build_use_digest(TitleBuild *tb, const TitleDigest *d);
/* The TMD's title version (major << 10 | minor << 4 | micro; 0, the default: 0 for a base title). */
void title_build_set_version(TitleBuild *tb, uint16_t tmd_version);
int title_build_has_hash(const TitleBuild *tb);
int title_build_content_hash(const TitleBuild *tb, uint8_t out[32]);
uint64_t title_build_content_size(const TitleBuild *tb);   /* the NCCH's size, after prepare */
/* For AM's piece-by-piece install: the ticket, the TMD (needs the content hash) and the certificate chain. */
void title_build_ticket(const TitleBuild *tb, uint8_t out[CIA_TICKET_SIZE]);
int title_build_tmd(const TitleBuild *tb, uint8_t out[CIA_TMD_SIZE]);
const uint8_t *title_build_certs(const TitleBuild *tb, size_t *len);
void title_build_close(TitleBuild *tb);

#endif
