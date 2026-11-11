/* zlib streams (RFC 1950) through miniz, in memory. Deterministic: the same input and level give the same bytes on any
 * machine, which the patch set's recorded hashes rely on. */
#ifndef ZLIB_MINI_H
#define ZLIB_MINI_H

#include <stddef.h>

/* The most `n` bytes can deflate to. */
size_t zm_deflate_bound(size_t n);
/* Deflates `src` (n bytes) into `dst` (capacity `cap`, at least zm_deflate_bound(n)) as a zlib stream at `level` 1-9.
 * 0 on success, with the stream's length in *out_len. */
int zm_deflate(const void *src, size_t n, void *dst, size_t cap, size_t *out_len, int level);
/* Inflates a zlib stream of `n` bytes that must give exactly `expect` bytes into `dst`. 0 on success. */
int zm_inflate(const void *src, size_t n, void *dst, size_t expect);

#endif
