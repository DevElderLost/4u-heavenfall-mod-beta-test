/* MH4U's save file cipher (savecrypt.h): core/save/crypt.py, step for step. */
#include "savecrypt.h"

#include <string.h>

static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

static void wr32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static uint32_t f(const HfBlowfish *bf, uint32_t x) {
    return ((bf->s[0][x >> 24] + bf->s[1][(x >> 16) & 0xFF]) ^ bf->s[2][(x >> 8) & 0xFF]) + bf->s[3][x & 0xFF];
}

static void encrypt_block(const HfBlowfish *bf, uint32_t *left, uint32_t *right) {
    uint32_t l = *left, r = *right, t;
    int i;
    for (i = 0; i < 16; i++) {
        l ^= bf->p[i];
        r ^= f(bf, l);
        t = l;
        l = r;
        r = t;
    }
    *left = r ^ bf->p[17];
    *right = l ^ bf->p[16];
}

static void decrypt_block(const HfBlowfish *bf, uint32_t *left, uint32_t *right) {
    uint32_t l = *left, r = *right, t;
    int i;
    for (i = 17; i > 1; i--) {
        l ^= bf->p[i];
        r ^= f(bf, l);
        t = l;
        l = r;
        r = t;
    }
    *left = r ^ bf->p[0];
    *right = l ^ bf->p[1];
}

void hf_blowfish_init(HfBlowfish *bf) {
    static const char key[] = HF_SAVECRYPT_KEY;
    uint32_t left = 0, right = 0, chunk;
    int i, j, box;
    memcpy(bf->p, HF_BLOWFISH_P_INIT, sizeof bf->p);
    memcpy(bf->s, HF_BLOWFISH_S_INIT, sizeof bf->s);
    for (i = 0; i < 18; i++) {   /* the key's bytes as big-endian words, the key repeated */
        chunk = 0;
        for (j = 0; j < 4; j++) chunk = chunk << 8 | (uint8_t)key[(4 * i + j) % HF_SAVECRYPT_KEY_SIZE];
        bf->p[i] ^= chunk;
    }
    for (i = 0; i < 18; i += 2) {
        encrypt_block(bf, &left, &right);
        bf->p[i] = left;
        bf->p[i + 1] = right;
    }
    for (box = 0; box < 4; box++)
        for (i = 0; i < 256; i += 2) {
            encrypt_block(bf, &left, &right);
            bf->s[box][i] = left;
            bf->s[box][i + 1] = right;
        }
}

static void ecb(const HfBlowfish *bf, uint8_t *data, uint32_t size, int decrypt) {
    uint32_t at, l, r;
    for (at = 0; at + 8 <= size; at += 8) {
        l = rd32(data + at);
        r = rd32(data + at + 4);
        if (decrypt) decrypt_block(bf, &l, &r);
        else encrypt_block(bf, &l, &r);
        wr32(data + at, l);
        wr32(data + at + 4, r);
    }
}

/* Every u16 from 4 to the end XORed with the stream key = max(key, 1) * 0xB0 % 0xFF53 (crypt._xor_stream). */
static void xor_stream(uint8_t *data, uint32_t size, uint32_t seed) {
    uint32_t key = seed, at;
    for (at = 4; at + 1 < size; at += 2) {
        key = (key ? key : 1) * HF_SAVECRYPT_XOR_MULTIPLIER % HF_SAVECRYPT_XOR_MODULUS;
        data[at] ^= (uint8_t)key;
        data[at + 1] ^= (uint8_t)(key >> 8);
    }
}

uint32_t hf_save_checksum(const uint8_t *plain, uint32_t size) {
    uint32_t sum = 0, at;
    for (at = 8; at < size; at++) sum += plain[at];
    return sum;
}

static int size_ok(uint32_t size, uint32_t blowfish_from) {
    return size >= 8 && blowfish_from <= size && (size - blowfish_from) % 8 == 0;
}

int hf_save_decrypt(const HfBlowfish *bf, uint8_t *data, uint32_t size, uint32_t blowfish_from, uint32_t *seed) {
    uint32_t header, key;
    if (!size_ok(size, blowfish_from)) return -2;
    ecb(bf, data + blowfish_from, size - blowfish_from, 1);
    header = rd32(data);
    key = header >> 16;
    xor_stream(data, size, key);
    wr32(data, header & 0xFFFF);
    if (seed) *seed = key;
    return rd32(data + 4) == hf_save_checksum(data, size) ? 0 : -1;
}

int hf_save_encrypt(const HfBlowfish *bf, uint8_t *data, uint32_t size, uint32_t blowfish_from, uint32_t seed) {
    if (!size_ok(size, blowfish_from)) return -2;
    seed &= 0xFFFF;
    wr32(data + 4, hf_save_checksum(data, size));
    wr32(data, (rd32(data) & 0xFFFF) | seed << 16);
    xor_stream(data, size, seed);
    ecb(bf, data + blowfish_from, size - blowfish_from, 0);
    return 0;
}
