/* BLZ decompression (core/game/executable/extract.py blz_decompress). */
#include "blz.h"

#include <string.h>

size_t blz_size(const uint8_t footer[8], size_t in_len) {
    uint32_t top = get_le32(footer), extra = get_le32(footer + 4);
    size_t header_len = top >> 24, comp_len = top & 0xFFFFFFu;
    if (in_len < 8 || header_len < 8 || header_len > in_len || comp_len > in_len || extra > (256u << 20)) return 0;
    return in_len + extra;
}

int blz_decompress_in_place(uint8_t *buf, size_t in_len, size_t total) {
    uint32_t top;
    size_t src, dst, end;
    if (!buf || in_len < 8 || !total || blz_size(buf + in_len - 8, in_len) != total) return TITLE_E_FORMAT;
    top = get_le32(buf + in_len - 8);
    src = in_len - (top >> 24);
    end = in_len - (top & 0xFFFFFFu);
    memset(buf + in_len, 0, total - in_len);
    dst = total;
    while (src > end) {         /* every byte read lies below `src`; each one made goes at `dst`, never below it */
        uint32_t flags;
        int bit;
        src--;
        flags = buf[src];
        for (bit = 0; bit < 8; bit++) {
            if (src <= end) break;
            if (flags & 0x80) {
                size_t length, distance, k;
                uint32_t pair;
                if (src < 2) return TITLE_E_FORMAT;
                src -= 2;
                pair = (uint32_t)buf[src] | (uint32_t)buf[src + 1] << 8;
                length = (pair >> 12) + 3;
                distance = (pair & 0x0FFFu) + 3;
                if (dst < length) return TITLE_E_FORMAT;
                for (k = 0; k < length; k++) {
                    dst--;
                    if (dst < src || dst + distance >= total) return TITLE_E_FORMAT;
                    buf[dst] = buf[dst + distance];
                }
            } else {
                if (src < 1 || dst < 1) return TITLE_E_FORMAT;
                src--;
                dst--;
                if (dst < src) return TITLE_E_FORMAT;
                buf[dst] = buf[src];
            }
            flags <<= 1;
        }
    }
    return TITLE_OK;
}
