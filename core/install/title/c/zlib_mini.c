/* The one deflate / inflate of the patch set applier: miniz (MIT, vendor/miniz/), compiled the same for the PC and the
 * 3DS, so a stream written on either is the same bytes. See vendor/NOTICE. */
#define MINIZ_NO_STDIO
#define MINIZ_NO_TIME
#define MINIZ_NO_ARCHIVE_APIS
#define MINIZ_NO_ZLIB_COMPATIBLE_NAMES
#include "vendor/miniz/miniz.c"

#include "zlib_mini.h"

size_t zm_deflate_bound(size_t n) { return (size_t)mz_compressBound((mz_ulong)n); }

int zm_deflate(const void *src, size_t n, void *dst, size_t cap, size_t *out_len, int level) {
    size_t got = tdefl_compress_mem_to_mem(dst, cap, src, n,
                                           (int)tdefl_create_comp_flags_from_zip_params(level, MZ_DEFAULT_WINDOW_BITS, 0));
    if (!got) return -1;
    *out_len = got;
    return 0;
}

int zm_inflate(const void *src, size_t n, void *dst, size_t expect) {
    size_t got = tinfl_decompress_mem_to_mem(dst, expect, src, n, TINFL_FLAG_PARSE_ZLIB_HEADER);
    return got == expect ? 0 : -1;
}
