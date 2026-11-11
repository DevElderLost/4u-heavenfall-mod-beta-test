/* Installing the mod pack of core/install/luma_pack.py, in small steps the app's main loop runs between frames, so
 * HOME, the power button and B (cancel) always answer. Plain C (no 3DS headers): tests/install/test_luma_pack.py builds it
 * on the PC.
 *
 * The files go first into a staging folder (STAGING under the root); only when every file is written and its CRC32
 * checked does the title's folder (the pack's `clean` path) get swapped for the new one, by two renames. Until then
 * the mod installed before is untouched: a cancel, an error, or the console turned off leaves it as it was, and the
 * next run removes the staging folder. Reads and writes go in blocks of 1 MB with open/read/write (stdio's 1 KB
 * buffer made every read a call to the 3DS file system service: a first version ran at ~0.1 MB/s). */
#ifndef INSTALL_H
#define INSTALL_H

#include <stddef.h>
#include <stdint.h>

#define STAGING "mh4u_installing"
#define TRASH "mh4u_old_mod"

typedef enum {
    STAGE_LEFTOVERS, /* removing what an interrupted run left (STAGING, TRASH) */
    STAGE_COPY,      /* writing the files into STAGING */
    STAGE_SWAP,      /* the old title folder to TRASH, the new one in its place */
    STAGE_OLD,       /* installed; removing TRASH and STAGING */
    STAGE_UNDO,      /* cancelled or failed before the swap: removing STAGING */
    STAGE_DONE,
    STAGE_CANCELLED,
    STAGE_FAILED,
} InstallStage;

typedef struct {
    InstallStage stage;
    uint64_t done, total;     /* bytes written of all */
    uint32_t files_done, count;
    char current[128];        /* the file being written */
    char error[300];          /* why it failed (STAGE_FAILED) */
} InstallStatus;

typedef struct Install Install;

/* Open the pack and check its header; NULL with a message in `err` otherwise. `root` ends with "/". */
Install *install_begin(const char *pack_file, const char *root, char *err, size_t err_size);

/* One step of work (a block of 1 MB, or a few files removed); returns the stage after it */
InstallStage install_step(Install *install);

/* Stop: before the swap, the staging folder is removed and the old mod stays; after it, nothing changes */
void install_cancel(Install *install);

const InstallStatus *install_status(const Install *install);
const char *install_clean_path(const Install *install);

/* Close everything (a run stopped halfway leaves STAGING for the next one to remove) */
void install_end(Install *install);

#endif
