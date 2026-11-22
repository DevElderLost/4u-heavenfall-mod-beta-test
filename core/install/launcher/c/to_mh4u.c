/* Heavenfall Beta's save taken to MH4U's (to_mh4u.h). */
#include "to_mh4u.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hf_save_files.h"

#if defined(__has_include)
#if __has_include("heav.h")
#define HF_TO_HAS_EXTRAS 1
#include "heav.h"
#endif
#endif

/* A hunter's fields in a plain `userN`: as bring.c (core/save/hunter.py), the save data starting at 8. */
#define DATA_AT 8u
#define NAME_SIZE 0x18u
#define PLAY_AT (DATA_AT + 0x38u)

static const HfToFile FILES[HF_TO_MH4U_FILES] = {
    {HF_FILE_USER1_NAME, HF_FILE_USER1_SIZE},
    {HF_FILE_USER2_NAME, HF_FILE_USER2_SIZE},
    {HF_FILE_USER3_NAME, HF_FILE_USER3_SIZE},
    {HF_FILE_SYSTEM_NAME, HF_FILE_SYSTEM_SIZE},
};

const HfToFile *hf_to_file(int index) { return index >= 0 && index < HF_TO_MH4U_FILES ? &FILES[index] : NULL; }

int hf_to_file_index(const char *name) {
    int i;
    for (i = 0; name && i < HF_TO_MH4U_FILES; i++)
        if (!strcmp(name, FILES[i].name)) return i;
    return -1;
}

#ifdef HF_TO_HAS_EXTRAS
int hf_to_clean(const uint8_t *plain, uint32_t size) {
    return plain && size == HF_FILE_USER1_SIZE && hf_heav_mh4u_clean(plain, size) == 1;
}
#else
int hf_to_clean(const uint8_t *plain, uint32_t size) {
    (void)plain;
    (void)size;
    return 0;
}
#endif

/* UTF-16LE up to its first zero into UTF-8 (a letter outside the plain range as '?'). */
static void utf8_name(const uint8_t *p, uint32_t letters, char *out, size_t cap) {
    size_t at = 0;
    uint32_t i;
    for (i = 0; i < letters; i++) {
        unsigned c = (unsigned)p[2 * i] | (unsigned)p[2 * i + 1] << 8;
        char tmp[3];
        size_t n;
        if (!c) break;
        if (c < 0x80) {
            tmp[0] = (char)c;
            n = 1;
        } else if (c < 0x800) {
            tmp[0] = (char)(0xC0 | c >> 6);
            tmp[1] = (char)(0x80 | (c & 0x3F));
            n = 2;
        } else if (c < 0xD800 || c > 0xDFFF) {
            tmp[0] = (char)(0xE0 | c >> 12);
            tmp[1] = (char)(0x80 | ((c >> 6) & 0x3F));
            tmp[2] = (char)(0x80 | (c & 0x3F));
            n = 3;
        } else {
            tmp[0] = '?';
            n = 1;
        }
        if (at + n >= cap) break;
        memcpy(out + at, tmp, n);
        at += n;
    }
    out[at] = 0;
}

int hf_to_side(const HfBlowfish *bf, const uint8_t *raw, uint32_t size, HfToSide *out) {
    uint8_t *plain;
    memset(out, 0, sizeof *out);
    if (!raw || !size) return 0;
    out->present = 1;
    if (size != HF_FILE_USER1_SIZE) return 0;
    if (!(plain = (uint8_t *)malloc(size))) return -1;
    memcpy(plain, raw, size);
    out->readable = hf_save_decrypt(bf, plain, size, 0, NULL) == 0;
    if (out->readable) {
        out->hunter = plain[DATA_AT] || plain[DATA_AT + 1];
        if (out->hunter) {
            utf8_name(plain + DATA_AT, NAME_SIZE / 2, out->name, sizeof out->name);
            out->play_time = (uint32_t)plain[PLAY_AT] | (uint32_t)plain[PLAY_AT + 1] << 8 |
                             (uint32_t)plain[PLAY_AT + 2] << 16 | (uint32_t)plain[PLAY_AT + 3] << 24;
        }
        out->clean = hf_to_clean(plain, size);
    }
    free(plain);
    return 0;
}

void hf_to_time_text(uint32_t seconds, char *out, size_t cap) {
    snprintf(out, cap, "%lu:%02lu", (unsigned long)(seconds / 3600u), (unsigned long)(seconds / 60u % 60u));
}

int hf_to_going_back(const HfToSide *beta, const HfToSide *mh4u) {
    return mh4u->readable && mh4u->hunter && mh4u->play_time > (beta->hunter ? beta->play_time : 0);
}

uint32_t hf_to_record_text(const HfToRecord *r, char *out, size_t cap) {
    size_t at = (size_t)snprintf(out, cap, "HFT1\n%s\n", r->stamp);
    int i;
    for (i = 0; i < r->count && at < cap; i++) {
        const HfToFile *f = hf_to_file(r->index[i]);
        if (!f) return 0;
        at += (size_t)snprintf(out + at, cap - at, "%s %d\n", f->name, r->existed[i] ? 1 : 0);
    }
    if (at < cap) at += (size_t)snprintf(out + at, cap - at, "END\n");
    return at < cap ? (uint32_t)at : 0;
}

int hf_to_record_parse(const char *text, uint32_t size, HfToRecord *out) {
    char copy[HF_TO_RECORD_MAX + 1], *line, *save;
    int state = 0;
    memset(out, 0, sizeof *out);
    if (!text || !size || size > HF_TO_RECORD_MAX) return 0;
    memcpy(copy, text, size);
    copy[size] = 0;
    for (line = copy; line; line = save) {
        save = strchr(line, '\n');
        if (save) *save++ = 0;
        if (state == 0) {
            if (strcmp(line, "HFT1")) return 0;
            state = 1;
        } else if (state == 1) {
            if (strlen(line) != 17) return 0;
            memcpy(out->stamp, line, 18);
            state = 2;
        } else if (!strcmp(line, "END")) {
            return state == 2 && out->count > 0;
        } else {
            char name[16];
            int existed, idx;
            if (sscanf(line, "%15s %d", name, &existed) != 2 || (existed != 0 && existed != 1) ||
                (idx = hf_to_file_index(name)) < 0 || out->count >= HF_TO_MH4U_FILES)
                return 0;
            out->index[out->count] = idx;
            out->existed[out->count++] = existed;
        }
    }
    return 0;
}
