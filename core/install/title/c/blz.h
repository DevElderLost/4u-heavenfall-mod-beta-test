/* Nintendo's bottom-up LZ77 ("BLZ") of a compressed ExeFS .code; the same result as core/game/executable/extract.py
 * blz_decompress. Portable C99. */
#ifndef BLZ_H
#define BLZ_H

#include "title_io.h"

/* The size a stored .code of `in_len` bytes decompresses to, from its last 8 bytes `footer`; 0 when it is not a BLZ
 * stream's footer. */
size_t blz_size(const uint8_t footer[8], size_t in_len);

/* Decompresses in place, as the console's loader does: `buf` holds the `in_len` stored bytes (with their 8-byte footer)
 * at its start and has room for `total` (blz_size's), which the bytes are made into from the end down. TITLE_OK, or
 * TITLE_E_FORMAT: a footer that does not give `total`, a back-reference outside the data, or a byte made over one still
 * to be read (a stream the loader could not decompress either). */
int blz_decompress_in_place(uint8_t *buf, size_t in_len, size_t total);

#endif
