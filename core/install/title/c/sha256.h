/* SHA-256 (FIPS 180-4), own implementation, public domain; on the 3DS (SHA256_ARMV4) the blocks go through
 * OpenSSL's ARMv4 assembly, sha256_armv4.s, with this same API. */
#ifndef SHA256_H
#define SHA256_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t h[8];
    uint8_t buf[64];
    uint64_t len;
    size_t fill;
} Sha256;

void sha256_init(Sha256 *s);
void sha256_update(Sha256 *s, const void *data, size_t n);
void sha256_final(Sha256 *s, uint8_t out[32]);
void sha256_buf(const void *data, size_t n, uint8_t out[32]);

#endif
