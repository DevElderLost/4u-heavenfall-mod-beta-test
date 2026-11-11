/* Finding the player's decrypted MH4U dump (and MH XX's) and the title pack on the SD card, by their headers and not
 * their names. Plain C (the files are opened through the caller's FileApi, so the PC builds it): tests/install/title/
 * test_install_c.py. */
#ifndef FIND_H
#define FIND_H

#include <stddef.h>
#include <stdint.h>

#include "title_io.h"

#define TITLE_PACK_NAME "mh4u_title.pack"   /* core/install/title_pack.py PACK_NAME */
#define FIND_PATH 512

typedef struct {
    int (*open)(void *ctx, const char *path, void **handle, uint64_t *size);   /* 0 on success */
    void (*close)(void *ctx, void *handle);
    TitleRead read;
    void *ctx;
} FileApi;

/* The places the dump is looked for, in order (GodMode9 writes to gm9/out), and the pack. */
extern const char *const FIND_DUMP_DIRS[];
extern const size_t FIND_DUMP_DIR_COUNT;
extern const char *const FIND_PACK_DIRS[];
extern const size_t FIND_PACK_DIR_COUNT;

/* The first file of `dirs` (not looking into sub-folders) that is a decrypted game with this title id: 0 for a base
 * MH4U of either region, DUMP_ID_EUR or DUMP_ID_USA for one region, DUMP_ID_XX for MH XX. TITLE_OK with the path in
 * `out`; TITLE_E_ENCRYPTED when a file was that game but not decrypted and none was usable; TITLE_E_FORMAT when there is
 * none. `seen_other` (may be NULL) is set when MH4U of the other region was found. */
int find_dump(const FileApi *api, const char *const *dirs, size_t ndirs, uint64_t want_id, char *out, size_t cap,
              int *seen_other);

/* The first file called TITLE_PACK_NAME of `dirs` that starts with the pack's magic. TITLE_OK or TITLE_E_FORMAT. */
int find_pack(const FileApi *api, const char *const *dirs, size_t ndirs, char *out, size_t cap);

#endif
