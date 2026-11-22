/* Heavenfall Beta's save taken to MH4U's: the portable rules of the
 * 3DS app's "Take my save to MH4U", over files already read. Beta's game keeps plain MH4U files (`system`, `user1-3`) in
 * its title's save; the app writes exactly those into the original game's save archive, a slot at a time, and never
 * anything else there. This file knows the files, what a slot shows, whether a slot is clean (the one place that
 * says so) and the record of the last move, which the restore reads. */
#ifndef HF_TO_MH4U_H
#define HF_TO_MH4U_H

#include <stddef.h>
#include <stdint.h>

#include "savecrypt.h"

enum { HF_TO_MH4U_SLOTS = 3, HF_TO_MH4U_FILES = 4 };   /* user1-3, then system (the shared data) */

typedef struct {
    const char *name;
    uint32_t size;
} HfToFile;

/* The file of index 0-2 (`user<n>`) or 3 (`system`), NULL for any other index: the only files either flow writes. */
const HfToFile *hf_to_file(int index);
/* The index of a file by name, -1 for any name the flows never write. */
int hf_to_file_index(const char *name);

/* What a slot's `userN` shows. */
typedef struct {
    int present;                 /* the file is there (any size) */
    int readable;                /* the right size and it decrypts (else the game calls it corrupt) */
    int hunter;                  /* it holds a character */
    int clean;                   /* hf_to_clean: nothing of Heavenfall Beta's is in it */
    char name[40];               /* UTF-8 */
    uint32_t play_time;          /* seconds */
} HfToSide;

/* `raw` (the encrypted file, left as it is) read into `out`. 0, or -1 for no memory. */
int hf_to_side(const HfBlowfish *bf, const uint8_t *raw, uint32_t size, HfToSide *out);

/* 1 when a plain (decrypted) `userN` is plain MH4U's: the right size and MH4U knows every byte (core/save/c/heav.c
 * hf_heav_mh4u_clean: nothing set apart for the extras' sidecars, no whole mark, nothing an older Heavenfall left).
 * The only clean check of "Take my save to MH4U". A build without the save core (core/save/c) says 0 for every
 * file. */
int hf_to_clean(const uint8_t *plain, uint32_t size);

/* "H:MM" of a play time in seconds. */
void hf_to_time_text(uint32_t seconds, char *out, size_t cap);

/* 1 when taking Beta's hunter would put MH4U's back in time: MH4U's slot has a hunter with more play time. */
int hf_to_going_back(const HfToSide *beta, const HfToSide *mh4u);

/* The record the restore reads: which backup set the last move made and the files it wrote (with whether MH4U had each
 * before), "HFT1\n<stamp>\n<name> <existed>\n...END\n". */
#define HF_TO_RECORD_MAX 256
typedef struct {
    char stamp[18];
    int count;
    int index[HF_TO_MH4U_FILES];     /* hf_to_file index */
    int existed[HF_TO_MH4U_FILES];
} HfToRecord;
/* The text's length, 0 when it does not fit. */
uint32_t hf_to_record_text(const HfToRecord *r, char *out, size_t cap);
/* 1 when `text` (`size` bytes, not necessarily terminated) is a whole record, else 0 (a damaged or foreign file). */
int hf_to_record_parse(const char *text, uint32_t size, HfToRecord *out);

#endif
