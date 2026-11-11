/* The libctru side of installing the mod as a title: SD card files with 64-bit offsets (the dump is over 2 GB, past
 * what newlib's stdio seeks), AM's two ways in (a CIA, or piece by piece), the builder's threads, and the installed
 * titles. Everything with real logic is in core/install/title/c/, core/install/launcher/c/ and find.c, which the PC
 * tests build; this file only wraps the console's services and can be checked only on a console. */
#ifndef CTR_TITLE_H
#define CTR_TITLE_H

#include <3ds.h>
#include <stdint.h>

#include "find.h"
#include "romfs.h"
#include "stream.h"
#include "title_io.h"

/* A FileApi over the SD card ("sdmc:/..." paths). */
void ctr_file_api(FileApi *api);
int ctr_file_size(const char *path, uint64_t *size);

/* The CIA, written into AM in order. Write errors are kept: the caller checks ctr_am_result after the stream. */
typedef struct CtrAm CtrAm;
CtrAm *ctr_am_begin(Result *result);
int ctr_am_write(void *ctx, const void *buf, size_t n);   /* a TitleWrite */
Result ctr_am_finish(CtrAm *am);                          /* flushes, then commits the install */
void ctr_am_cancel(CtrAm *am);                            /* gives up: nothing is installed */
Result ctr_am_write_result(const CtrAm *am);              /* AM's answer to the write it refused, 0 */

/* AM's piece-by-piece install (am:net): the certificate
 * chain and the ticket, the title's import, its TMD, content 0, then the title's finish and commit. The app writes the
 * TMD first (its hash from the patch set's build data, or from a hash pass). Errors are kept like ctr_am_write's. */
typedef struct CtrParts CtrParts;
CtrParts *ctr_parts_begin(uint64_t title_id, const uint8_t *certs, size_t certs_len, const uint8_t *ticket,
                          size_t ticket_len, Result *result);
Result ctr_parts_tmd(CtrParts *p, const uint8_t *tmd, size_t len);
Result ctr_parts_content_begin(CtrParts *p);
Result ctr_parts_contexts_result(const CtrParts *p);   /* AM_CreateImportContentContexts's answer, 0 when not asked */
int ctr_parts_write(void *ctx, const void *buf, size_t n);   /* a TitleWrite into content 0 */
Result ctr_parts_content_finish(CtrParts *p);
Result ctr_parts_commit(CtrParts *p);                     /* finishes and commits the title; frees p */
void ctr_parts_abort(CtrParts *p);                        /* nothing is installed; frees p */
Result ctr_parts_write_result(const CtrParts *p);         /* AM's answer to the write it refused, 0 */
/* AM's pending (unfinished) imports of `title_id` on the SD card, deleted: an import left by a cut or refused try makes
 * the next one's TMD or CIA answer "already exists" (0xC8E083FC). The number deleted, -1 when AM did not answer. */
int ctr_pending_clear(uint64_t title_id, char *log_line, size_t cap);

/* The fast builder's threads: a StreamSync over libctru's LightLock and CondVar, and a Stream run with its reading and
 * hashing stages on threads of their own (the reading one also applies the patch set; the hashing one on core 2 of a
 * New 3DS) and its writing stage, whose progress callback draws, on the calling thread. */
typedef struct {
    LightLock lock;
    CondVar cond;
} CtrSync;
void ctr_sync_init(CtrSync *c, StreamSync *s);
int ctr_stream_run(Stream *s);

int ctr_title_installed(uint64_t title_id);               /* in the SD card's title list */
/* The game data title opened as the game opens it (archive 0x2345678A): its RomFS read
 * up to the level-3 header. 0 when it is whole; else HF_E_GAME_CHECK (FS's answer in `line`, for the log). */
int ctr_game_check(uint64_t game_title_id, char *line, size_t cap);
Result ctr_title_delete(uint64_t title_id);
uint64_t ctr_sd_free(void);

#endif
