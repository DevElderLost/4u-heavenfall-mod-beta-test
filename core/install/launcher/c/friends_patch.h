/* The online patch of the friends module (0004013000003202) for Pretendo. Portable C99, no libctru: the 3DS app
(tools/build/installer_3ds/source/ctr_friends.c) hands
 * in the running module's code, the PC tests synthetic code and the emulator's copy of the module.
 *
 * The module asks FS for the program id of a game that logs in (fs:USER GetProgramLaunchInfo, command 0x082F) and
 * sends it as the NASC request's `titleid`. frdp_locate finds that call's wrapper by its code, checks that the NASC
 * request builder takes its title id from it, and makes a patch: a BL in the wrapper's success path to a stub in the
 * free room at the end of the code section, which turns a program id of the map (ours) into its `to` (MH4U's of the
 * same region) and leaves every other id alone. The patch is written as IPS records (the only format Luma3DS applies
 * to a system module without checking a CRC of the whole code), merged into the module's one .ips file (Nimbus') and
 * taken back out of it byte for byte. */
#ifndef FRIENDS_PATCH_H
#define FRIENDS_PATCH_H

#include <stddef.h>
#include <stdint.h>

#include "hf_edition.h"

#define FRDP_TITLE 0x0004013000003202ULL   /* the friends module (its New 3DS bit, 0x20000000, is ignored) */
#define FRDP_MH4U_EUR 0x0004000000126100ULL
#define FRDP_MH4U_USA 0x0004000000126300ULL
#define FRDP_LOAD 0x00100000u              /* the code's load address; patch offsets count from it */
#define FRDP_MAX_MAP 8
#define FRDP_STUB_MAX (0x2C + 16 * FRDP_MAX_MAP + 8)
#define FRDP_RECORDS_MAX (2 * 5 + FRDP_STUB_MAX + 4)

enum {
    FRDP_OK = 0,
    FRDP_E_ARGS = -1,      /* sizes, map or buffers wrong */
    FRDP_E_WRAPPER = -2,   /* the GetProgramLaunchInfo wrapper not found, or found twice */
    FRDP_E_CHAIN = -3,     /* the NASC request's title id does not come from that wrapper */
    FRDP_E_ROOM = -4,      /* no free room at the end of the code section */
    FRDP_E_IPS = -5,       /* an IPS file Luma3DS would refuse (and stop the console on) */
    FRDP_E_OVERLAP = -6,   /* the other patch writes where ours does */
    FRDP_E_SPACE = -7,     /* an output buffer too small */
    FRDP_E_NOT_OURS = -8   /* the file does not hold our records as frdp_ips_merge wrote them */
};

typedef struct {
    uint64_t from, to;
} FrdpMap;

typedef struct {
    uint32_t text, ro, data;   /* the code set's sizes in bytes: exact (exheader) or rounded to pages (the kernel's) */
} FrdpSizes;

typedef struct {
    /* offsets from the start of the code (address - FRDP_LOAD) */
    uint32_t wrapper;          /* the GetProgramLaunchInfo wrapper */
    uint32_t hook;             /* its 4 bytes replaced by a BL to the stub */
    uint32_t stub, stub_len;
    uint32_t builder_ref;      /* the NASC request builder's reference to "titleid" */
    uint32_t getter;           /* the builder's title id getter (wrapper <- thunk <- getter) */
    uint32_t thunk;
    uint32_t callers;          /* BL/BLX to the wrapper in the code section */
    uint32_t thunk_callers;    /* BL/BLX to the thunk */
    int active;                /* the code given already holds a patch of ours (found and read through) */
    int active_same;           /* ... and it is the one made now */
    uint8_t hook_bytes[4];
    uint8_t hook_orig[4];
    uint8_t stub_bytes[FRDP_STUB_MAX];
} FrdpPatch;

/* Finds the patch in the module's code (`len` bytes from FRDP_LOAD: text, rodata and data, each section starting on a
 * page). Every match must be unique and its bytes as expected, or nothing is made. Works on the module as Nintendo
 * made it and on one running our patch (then `active`). `msg` says what was found or why not. */
int frdp_locate(const uint8_t *code, size_t len, const FrdpSizes *sizes, const FrdpMap *map, size_t map_count,
                FrdpPatch *out, char *msg, size_t n);

/* The map from the editions' titles: each EUR id to FRDP_MH4U_EUR, each USA id to FRDP_MH4U_USA. Returns the count,
 * or 0 when an id is not 16 hex digits or there is no room. */
size_t frdp_map_editions(const HfEdition *editions, size_t count, FrdpMap *map, size_t cap);

/* The patch's IPS records (no "PATCH" header, no "EOF"); returns their length, 0 if `cap` is too small. */
size_t frdp_records(const FrdpPatch *p, uint8_t *out, size_t cap);

/* Checks an IPS file the way Luma3DS 13.0 to 13.5 read /luma/sysmodules/<id>.ips: "PATCH", records ending within
 * `limit` (the module's size in whole pages), "EOF", then nothing or a 3-byte size within `limit`. `avoid`: ranges
 * no record may touch (FRDP_E_OVERLAP). Sets *eof_at to the offset of "EOF". */
int frdp_ips_check(const uint8_t *ips, size_t len, uint32_t limit, const uint8_t *avoid_records, size_t avoid_len,
                   size_t *eof_at);

/* `base` (NULL or 0 bytes: none) with our `records` added before its "EOF", into `out`. Refuses a base Luma3DS would
 * refuse and records that touch the base's. */
int frdp_ips_merge(const uint8_t *base, size_t base_len, const uint8_t *records, size_t records_len, uint32_t limit,
                   uint8_t *out, size_t cap, size_t *out_len);

/* Takes `records` back out of a file frdp_ips_merge wrote: `out` is the base byte for byte ("PATCHEOF" when there was
 * none). FRDP_E_NOT_OURS when the records are not there as written (e.g. Nimbus replaced the file). `out` may be NULL
 * to only ask. */
int frdp_ips_strip(const uint8_t *ips, size_t len, const uint8_t *records, size_t records_len, uint8_t *out,
                   size_t cap, size_t *out_len);

/* ---- the module's .ips on the SD card (A) ----
 * Luma3DS stops the console at every boot on a .ips it refuses, so a file the app leaves under the module's name is
 * always whole: written beside it, swapped in, read back. The file calls go through FrdpFiles (stdio on the console,
 * the tests' faults on the PC). */

#define FRDP_IPS_ANY 0x02000000u   /* a limit past every IPS record: frdp_ips_check of the file's form alone */
#define FRDP_FILE_MAX (1024 * 1024)   /* the most a .ips file is read */

enum { FRDP_E_IO = -9, FRDP_E_READBACK = -10 };

typedef struct {
    int (*exists)(void *ctx, const char *path);
    uint8_t *(*read)(void *ctx, const char *path, size_t *len);   /* the whole file (malloc'd), NULL: none or too big */
    int (*write)(void *ctx, const char *path, const uint8_t *data, size_t len);   /* the whole file; 0 when written */
    int (*remove)(void *ctx, const char *path);
    int (*rename)(void *ctx, const char *from, const char *to);
    void *ctx;
} FrdpFiles;

void frdp_files_stdio(FrdpFiles *f);

/* A replacement cut short (frdp_file_put): `tmp` becomes `path` only when `path` is missing and `tmp` is a whole IPS
 * (frdp_ips_check within FRDP_IPS_ANY); any other `tmp` is deleted. */
void frdp_file_recover(const FrdpFiles *f, const char *path, const char *tmp);

/* `data` as `path`, whole: into `tmp`, the old file removed, `tmp` renamed, read back and compared. FRDP_OK;
 * FRDP_E_IO when `tmp` could not be written (nothing changed); FRDP_E_READBACK when the new file is not what was
 * written: the file before (`old`, NULL: there was none) is put back the same way, and when that fails too the file
 * is removed (a console boots without it, never with a damaged one). */
int frdp_file_put(const FrdpFiles *f, const char *path, const char *tmp, const uint8_t *data, size_t len,
                  const uint8_t *old, size_t old_len);

enum { FRDP_KEEP = 0, FRDP_DELETE = 1, FRDP_WRITE = 2 };

/* What taking our patch out leaves as the module's .ips (`ips` the file now, NULL: none; `ours` our records as
 * installed; `base` the file before ours as kept at the install, NULL: none). FRDP_KEEP: nothing to do (no file, or
 * one without our records: Nimbus replaced it). FRDP_DELETE: the file goes (it held only ours, or Luma3DS would refuse
 * it and no whole file before ours is kept). FRDP_WRITE: *out (malloc'd, *out_len bytes) replaces it: the file without
 * our records, or the kept file before ours in place of one Luma3DS would refuse (a cut or damaged write), so the way
 * back (Luma3DS' option off, Remove, the option on) always boots. */
int frdp_remove_plan(const uint8_t *ips, size_t ips_len, const uint8_t *ours, size_t ours_len, const uint8_t *base,
                     size_t base_len, uint8_t **out, size_t *out_len);

#endif
