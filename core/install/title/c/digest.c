/* See digest.h. */
#include "digest.h"

#include <stdlib.h>
#include <string.h>

#define FILE_HEAD 44u   /* u64 size, 32-byte SHA-256, u32 path length */
#define GAMES_HEAD 16u  /* format 3: u64 the game data's title id, u32 entry count, u32 0 */
#define GAME_ENTRY 72u  /* the dump's RomFS superblock hash, u64 content size, its SHA-256 */

static uint64_t le64(const uint8_t *p) { return (uint64_t)get_le32(p) | (uint64_t)get_le32(p + 4) << 32; }

/* Format 3's game entries at `*at`, moved past them. */
static int parse_games(TitleDigest *d, const uint8_t *buf, size_t len, size_t *at) {
    uint32_t count, i;
    if (len - *at < GAMES_HEAD) return TITLE_E_FORMAT;
    d->game_title_id = le64(buf + *at);
    count = get_le32(buf + *at + 8);
    *at += GAMES_HEAD;
    if (count > (len - *at) / GAME_ENTRY) return TITLE_E_FORMAT;
    d->games = (DigestGame *)calloc(count ? count : 1, sizeof *d->games);
    if (!d->games) return TITLE_E_MEM;
    for (i = 0; i < count; i++, *at += GAME_ENTRY) {
        memcpy(d->games[i].romfs_hash, buf + *at, 32);
        d->games[i].content_size = le64(buf + *at + 32);
        memcpy(d->games[i].content_sha256, buf + *at + 40, 32);
    }
    d->ngames = count;
    return TITLE_OK;
}

int digest_parse(TitleDigest *d, const uint8_t *buf, size_t len) {
    size_t at = DIGEST_HEADER, start, i, pool = 0;
    uint32_t count, hashes;
    int rc;
    if (!d || !buf) return TITLE_E_ARG;
    memset(d, 0, sizeof *d);
    if (len < DIGEST_HEADER || memcmp(buf, DIGEST_MAGIC, 4)) return TITLE_E_FORMAT;
    d->format = get_le32(buf + 4);
    if (d->format != DIGEST_FORMAT && d->format != DIGEST_FORMAT_SPLIT) return TITLE_E_FORMAT;
    d->title_id = le64(buf + 0x08);
    d->content_size = le64(buf + 0x10);
    memcpy(d->content_sha256, buf + 0x18, 32);
    memcpy(d->game_romfs_hash, buf + 0x38, 32);
    memcpy(d->code_sha256, buf + 0x58, 32);
    memcpy(d->exheader_sha256, buf + 0x78, 32);
    memcpy(d->smdh_sha256, buf + 0x98, 32);
    count = get_le32(buf + 0xB8);
    hashes = get_le32(buf + 0xBC);
    if (d->format == DIGEST_FORMAT_SPLIT && (rc = parse_games(d, buf, len, &at))) {
        digest_free(d);
        return rc;
    }
    start = at;
    if (count > (len - at) / FILE_HEAD) {
        digest_free(d);
        return TITLE_E_FORMAT;
    }
    for (i = 0; i < count; i++) {           /* the paths' room with their NULs (not the whole slot's: its hashes) */
        uint32_t n;
        if (len - at < FILE_HEAD) break;
        n = get_le32(buf + at + 40);
        if (len - at - FILE_HEAD < n) break;
        pool += (size_t)n + 1;
        at += FILE_HEAD + (size_t)title_align(n, 4);
        if (at > len) break;
    }
    if (i != count) {
        digest_free(d);
        return TITLE_E_FORMAT;
    }
    d->files = (DigestFile *)calloc(count ? count : 1, sizeof *d->files);
    d->pool = (char *)malloc(pool ? pool : 1);
    at = start;
    pool = 0;
    if (!d->files || !d->pool) {
        digest_free(d);
        return TITLE_E_MEM;
    }
    for (i = 0; i < count; i++) {
        uint32_t n;
        if (len - at < FILE_HEAD) break;
        n = get_le32(buf + at + 40);
        if (len - at - FILE_HEAD < n) break;
        d->files[i].size = le64(buf + at);
        memcpy(d->files[i].sha256, buf + at + 8, 32);
        memcpy(d->pool + pool, buf + at + FILE_HEAD, n);
        d->pool[pool + n] = 0;
        d->files[i].path = d->pool + pool;
        pool += n + 1;
        at += FILE_HEAD + (size_t)title_align(n, 4);
        if (at > len || (i && strcmp(d->files[i - 1].path, d->files[i].path) >= 0)) break;
    }
    d->nfiles = i;
    if (i != count || at > len || (len - at) / 32 != hashes || (len - at) % 32) {
        digest_free(d);
        return TITLE_E_FORMAT;
    }
    d->tail = (uint8_t *)malloc(hashes ? (size_t)hashes * 32 : 1);
    if (!d->tail) {
        digest_free(d);
        return TITLE_E_MEM;
    }
    memcpy(d->tail, buf + at, (size_t)hashes * 32);
    d->ntail = hashes;
    return TITLE_OK;
}

const DigestFile *digest_find(const TitleDigest *d, const char *path) {
    size_t lo = 0, hi;
    if (!d || !path) return NULL;
    hi = d->nfiles;
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        int c = strcmp(d->files[mid].path, path);
        if (!c) return &d->files[mid];
        if (c < 0) lo = mid + 1; else hi = mid;
    }
    return NULL;
}

const DigestGame *digest_game(const TitleDigest *d, const uint8_t romfs_hash[32]) {
    size_t i;
    if (!d || !romfs_hash) return NULL;
    for (i = 0; i < d->ngames; i++)
        if (!memcmp(d->games[i].romfs_hash, romfs_hash, 32)) return &d->games[i];
    return NULL;
}

void digest_free(TitleDigest *d) {
    if (!d) return;
    free(d->files);
    free(d->pool);
    free(d->tail);
    free(d->games);
    memset(d, 0, sizeof *d);
}
