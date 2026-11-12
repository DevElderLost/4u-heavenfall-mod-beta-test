/* A title's build data, the formats of core/install/title/title_digest.py: the content's size and SHA-256 computed on
 * the PC, the level-2 hashes of the bytes the console makes, and what they were made from (the dump's revision, the
 * executable, the exheader, the SMDH, every mod file's size and SHA-256). A release's patch set carries it in its
 * title-build slot; with it the console writes the TMD before the content and streams the content once, hashing only
 * the mod's bytes to check them (build.h, title_build_use_digest). Portable C99.
 *
 * Format 2: the single title's (its level-2 hashes: the seam's and the mod's files'). Format 3: the split title's: the
 * edition's title with the mod's files alone (its level-2 hashes: its whole level
 * 3), and the game data title's id with, per dump the PC knew, that title's content size and SHA-256. */
#ifndef DIGEST_H
#define DIGEST_H

#include "title_io.h"

#define DIGEST_MAGIC "HFTD"
#define DIGEST_FORMAT 2u             /* the single title's */
#define DIGEST_FORMAT_SPLIT 3u       /* the split title's */
#define DIGEST_HEADER 0xC0u

typedef struct {
    const char *path;        /* into the parsed buffer's copy, NUL terminated */
    uint64_t size;
    uint8_t sha256[32];
} DigestFile;

typedef struct {
    uint8_t romfs_hash[32];          /* the dump's NCCH header at 0x1E0 */
    uint64_t content_size;           /* the game data title's content made from that dump */
    uint8_t content_sha256[32];
} DigestGame;

typedef struct {
    uint32_t format;                 /* DIGEST_FORMAT or DIGEST_FORMAT_SPLIT */
    uint64_t title_id;
    uint64_t content_size;
    uint8_t content_sha256[32];
    uint8_t game_romfs_hash[32];     /* the dump's NCCH header at 0x1E0 */
    uint8_t code_sha256[32];
    uint8_t exheader_sha256[32];     /* the mod's, before retitling */
    uint8_t smdh_sha256[32];
    DigestFile *files;               /* sorted by path (byte order) */
    size_t nfiles;
    char *pool;
    uint8_t *tail;                   /* the level-2 hashes (kept_use_tail), 32 bytes each */
    size_t ntail;
    uint64_t game_title_id;          /* format 3: the game data title's; 0 otherwise */
    DigestGame *games;               /* format 3: one per dump */
    size_t ngames;
} TitleDigest;

/* TITLE_OK or TITLE_E_FORMAT (another format, cut short, bytes after the hashes, files out of order). */
int digest_parse(TitleDigest *d, const uint8_t *buf, size_t len);
/* The file with this path, or NULL. */
const DigestFile *digest_find(const TitleDigest *d, const char *path);
/* The game data made from the dump whose RomFS superblock hash is `romfs_hash`, or NULL (format 2: always NULL). */
const DigestGame *digest_game(const TitleDigest *d, const uint8_t romfs_hash[32]);
void digest_free(TitleDigest *d);

#endif
