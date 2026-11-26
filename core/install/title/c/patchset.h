/* The release patch set (.hfpatch): the applier. A set turns the player's decrypted MH4U dump into the mod's files
 * (romfs/ files, exefs/code.bin, exheader.bin) and holds no game bytes: only our changes and references to the
 * dump. Format and rules; the writer is core/install/title/patchset.py.
 * Portable C99, no libctru; every byte goes through the callbacks of title_io.h, errors are return codes.
 *
 * Use: patchset_open, bind every source (patchset_bind_dump, and for a set made with a second game, format 2 to 4,
 * patchset_bind_second_dump; for a set that reads the release's shared file, format 3 or 4, patchset_bind_shared; for
 * a set whose code comes from the update, format 4, patchset_bind_update; or patchset_bind by hand), then for each
 * file patchset_file_info / patchset_file_size and
 * patchset_apply_file, which streams the file's bytes to the TitleOut. An ARC comes out with its changed entries
 * deflated by the one vendored deflate (zlib_mini.c), so a run on the PC and a run on the console give the same bytes.
 *
 * A base (what a file's or an ARC entry's COPY operations read) is a list of parts, each a source whole or one entry of
 * an ARC source, decompressed, joined in order (format 1: at most one part). A file's ARC entry parts are inflated once
 * and kept while that file is made (up to 1 MiB beside the record being made), dropped when another file begins.
 *
 * Reads: `read(ctx, handle, offset, ...)` is one callback for the set (its handle is given to patchset_open) and for
 * the dumps (the handles of the bindings: MH4U's, its update's and MH XX's dumps opened with the same callback and
 * context). */
#ifndef PATCHSET_H
#define PATCHSET_H

#include "dump.h"
#include "title_io.h"

#define PS_FORMAT 1                 /* a set made from MH4U alone */
#define PS_FORMAT_SECOND 2          /* a set made with a second game too (MH XX) */
#define PS_FORMAT_SHARED 3          /* a release's set: format 2's layout, the second game optional, the release's shared
                                     * file, the source stamp: the newest format of the 3DS app's sets */
#define PS_FORMAT_UPDATE 4          /* a release's set for the recompiled game: format 3's, its executable and
                                     * exheader made from MH4U's update, the mod's root files too, no title-build
                                     * slot: the newest format this applier reads */
#define PS_HEADER_SIZE 0x80u
#define PS_HEADER2_SIZE 0x100u      /* format 2's header */
#define PS_HEADER4_SIZE 0x140u      /* format 4's: format 3's, then the update's title id and ExeFS superblock hash */
#define PS_NONE 0xFFFFFFFFu

/* A RomFS file of MH4U; its exheader; its executable (format 4: the update's exheader, as it is, and executable); a
 * RomFS file of the second game (format 2 to 4); a file of the release's shared file (format 3 or 4), read whole. */
enum { PS_SRC_FILE = 0, PS_SRC_EXHEADER = 1, PS_SRC_CODE = 2, PS_SRC_SECOND = 3, PS_SRC_SHARED = 4 };
enum { PS_FILE_PLAIN = 0, PS_FILE_ARC = 1 };
/* Flags of patchset_apply_file. */
enum {
    PS_VERIFY_OUTPUT = 1,   /* hash what the set's operations produce (a plain file, an ARC's changed entries) */
    PS_VERIFY_COPIES = 2,   /* and inflate and hash the ARC entries copied as they are (slow) */
    PS_VERIFY_ALL = 3
};

typedef struct Patchset Patchset;

typedef struct {
    uint32_t kind;          /* PS_SRC_* */
    const char *path;       /* RomFS path of a PS_SRC_FILE, PS_SRC_SECOND or PS_SRC_SHARED, "" otherwise */
    uint64_t size;          /* bytes the operations read: decompressed for the executable */
    uint8_t sha256[32];
} PatchsetSourceInfo;

typedef struct {
    uint32_t kind;          /* PS_FILE_* */
    const char *path;       /* "romfs/...", "exefs/code.bin", "exheader.bin"; format 4: also the mod's root files
                             * ("mod.json", "recomp.json"), every path relative, "/" separated, no "." or ".." */
    uint64_t size;          /* of the output; for an ARC known after patchset_measure / patchset_apply_file */
    int size_known;
    int has_hash;           /* a plain file records the SHA-256 of its output; an ARC does not (the entries have theirs) */
    uint8_t sha256[32];
} PatchsetFileInfo;

/* Where a source's bytes are. `mem` (when set) holds them; otherwise they are `size` bytes at `offset` of `handle`
 * (stored size; with `blz` the stored bytes are BLZ-compressed and the source is what they decompress to). */
typedef struct {
    void *handle;
    uint64_t offset;
    uint64_t size;
    int blz;
    const uint8_t *mem;
} PatchsetBinding;

/* Opens the set of `size` bytes behind `handle`: parses the header and tables (format 2's inflated, then freed). With
 * `check`, reads all of it once and compares its SHA-256 with the header's. TITLE_E_FORMAT for a set that is not one,
 * of a format version past PS_FORMAT_UPDATE, cut or damaged; TITLE_E_PATH for a format 4 set naming a file outside
 * the mod's folder (an absolute path, a "." or ".." component, a backslash, a colon, a control byte); TITLE_E_IO;
 * TITLE_E_MEM. */
int patchset_open(Patchset **ps, TitleRead read, void *ctx, void *handle, uint64_t size, int check);
/* As patchset_open, keeping only the files named (`paths`: "exefs/code.bin", "exheader.bin"...), in the set's order,
 * with the parts and sources they read (numbered anew, in the set's order) and no build data: the executable made
 * before the rest of the set is held. A name the set lacks is left out; one the
 * set lists twice is TITLE_E_FORMAT. The other records are checked only as far as walking over them needs. */
int patchset_open_files(Patchset **ps, TitleRead read, void *ctx, void *handle, uint64_t size, int check,
                        const char *const *paths, size_t npaths);
void patchset_close(Patchset *ps);

int patchset_format(const Patchset *ps);                 /* PS_FORMAT to PS_FORMAT_UPDATE */
int patchset_region(const Patchset *ps);                 /* REGION_EUR or REGION_USA */
const char *patchset_edition(const Patchset *ps);
const char *patchset_version(const Patchset *ps);
/* The title-build data slot (filled by the title builder, opaque here); NULL and 0 when empty. */
const uint8_t *patchset_build_data(const Patchset *ps, size_t *len);
/* Frees the slot's bytes once the caller has read them (digest_parse keeps its own copy). */
void patchset_drop_build_data(Patchset *ps);
/* 1 for a set made with a second game (format 2, or 3 or 4 naming one), giving its title id (MH XX:
 * 0004000000197100) and its RomFS superblock hash (the NCCH header's 0x1E0-0x200: the game's revision) when asked; 0
 * for a set of MH4U alone. */
int patchset_second_game(const Patchset *ps, uint64_t *title_id, uint8_t romfs_hash[32]);
/* 1 for a set that reads the release's shared file (format 3 or 4), giving the file's SHA-256 and size when asked: the
 * app has it on the card, checked against that hash, before the set's title is made; 0 otherwise. */
int patchset_shared(const Patchset *ps, uint8_t sha256[32], uint64_t *size);
/* 1 for a set whose code comes from MH4U's update (format 4), giving the update's title id (0004000E00126300 USA,
 * 0004000E00126100 EUR) and its ExeFS superblock hash (the NCCH header's 0x1C0-0x1E0: the update's revision) when
 * asked; 0 otherwise. */
int patchset_update(const Patchset *ps, uint64_t *title_id, uint8_t exefs_hash[32]);
/* Format 3's and 4's source stamp (32 bytes; all zeros: none) and flags (PS_FLAG_*). */
const uint8_t *patchset_stamp(const Patchset *ps);
uint32_t patchset_flags(const Patchset *ps);
#define PS_FLAG_CHEATS 1u           /* the mod was made with the cheats switch */

size_t patchset_source_count(const Patchset *ps);
int patchset_source_info(const Patchset *ps, size_t i, PatchsetSourceInfo *info);
int patchset_bind(Patchset *ps, size_t i, const PatchsetBinding *b);
/* Binds every MH4U source to its place in the opened dump `d` (its own handle and read callback are the set's):
 * TITLE_E_GAME when the dump's region is not the set's, a source is missing or its size differs. A second game's
 * sources are left to patchset_bind_second_dump; a format 4 set's executable and exheader to patchset_bind_update. */
int patchset_bind_dump(Patchset *ps, const Dump *d);
/* Binds a format 4 set's executable and exheader to the opened update `update` (dump_open_update, with the set's read
 * callback and context): TITLE_E_NO_UPDATE when `update` is NULL, TITLE_E_OTHER_UPDATE when it is not the update the
 * set names (its title id or ExeFS superblock hash differs: another region, another revision) or its executable is of
 * another stored size. A changed byte is found as for the game: patchset_verify_source (TITLE_E_HASH), or the apply's
 * hashes. A set of formats 1 to 3 reads no update: TITLE_OK, `update` unused. `update` must outlive the set's use. */
int patchset_bind_update(Patchset *ps, const Dump *update);
/* Binds a format 2 set's second-game sources to the opened dump `xx` (MH XX's, opened with the set's read callback and
 * context): TITLE_E_GAME when `xx` is NULL, is not the game the set names (its title id or RomFS superblock hash
 * differs: another game, another revision), lacks a file the set reads or has it at another size. A changed byte is
 * found as for MH4U: patchset_verify_source (TITLE_E_HASH), or the apply's hashes. A format 1 set has nothing to bind:
 * TITLE_OK, `xx` unused. `xx` must outlive the set's use. */
int patchset_bind_second_dump(Patchset *ps, const Dump *xx);
/* Binds a format 3 set's shared-file sources to the shared file of `size` bytes behind `handle` (read with the set's
 * callback and context): its header and index are read, and each source is the entry of its name. TITLE_E_FORMAT when
 * `handle` is NULL, the size is not the one the set names, the file is not a shared file, or lacks an entry the set
 * reads or has it at another size. The whole file's SHA-256 is the caller's to check (the app checks it against the
 * set's before it opens the set); a changed byte is found as for the dump: patchset_verify_source (TITLE_E_HASH), or
 * the apply's hashes. A set that reads no shared file has nothing to bind: TITLE_OK, `handle` unused. */
int patchset_bind_shared(Patchset *ps, void *handle, uint64_t size);
/* Reads source `i` once and compares its SHA-256 with the set's: TITLE_E_HASH for another dump. `progress` may be NULL;
 * a nonzero return cancels (TITLE_E_CANCEL). */
int patchset_verify_source(Patchset *ps, size_t i, TitleProgress progress, void *progress_ctx);

size_t patchset_file_count(const Patchset *ps);
int patchset_file_info(const Patchset *ps, size_t i, PatchsetFileInfo *info);
/* Makes an ARC's size known: deflates its changed entries, and keeps only their sizes. Nothing to do for a plain file. */
int patchset_measure(Patchset *ps, size_t i, TitleProgress progress, void *progress_ctx);
/* Gives an ARC the size the title-build data recorded, so the title's layout is known before anything is deflated; the
 * apply (or a measure) then checks it: TITLE_E_HASH when the entries make another size. For a plain file only checks
 * the size (TITLE_E_HASH when it differs). */
int patchset_set_size(Patchset *ps, size_t i, uint64_t size);
/* Bytes of deflated entries an ARC's apply keeps between sizing them and writing them (64 MB by default); past that
 * they are deflated again. */
void patchset_keep_budget(Patchset *ps, uint64_t bytes);
/* The dump's executable decompressed now (`keep` 1: in place in one buffer, before the caller makes room for the mod's)
 * with the rest of the mod executable's base (the MH XX entries the set copies from), or dropped (0: once the mod's
 * executable is made). A console's heap holds two executables, not four. */
int patchset_executable(Patchset *ps, int keep);
/* Streams file `i` to `out` (write, and progress with the bytes done and the file's size; a nonzero progress return
 * cancels: TITLE_E_CANCEL). `flags`: PS_VERIFY_*. TITLE_E_HASH when a verified hash differs. */
int patchset_apply_file(Patchset *ps, size_t i, const TitleOut *out, unsigned flags);

#endif
