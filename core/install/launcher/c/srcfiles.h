/* MH XX's dump checked by file (portable C99, no libctru). A format 2
 * set names the RomFS superblock hash of the XX dump it was made from, but a later printing of the game can hold the
 * very files the set reads. The hash is a hint: when it differs, the set's second-game sources are checked one by one
 * (path, size, SHA-256) before anything is written. */
#ifndef HF_SRCFILES_H
#define HF_SRCFILES_H

#include "patchset.h"

/* Binds the second-game sources of the opened format 2 set `ps` to `xx`'s files and reads each once, comparing its
 * SHA-256 with the set's. TITLE_OK when all are equal: `xx`'s recorded superblock hash then becomes the set's (so
 * patchset_bind_second_dump, and the install that opens the set again, accept it; `xx` must be a Dump the caller
 * owns). TITLE_E_GAME for another game (title id), a file missing or of another size; TITLE_E_HASH for a file of
 * the same size with other bytes; TITLE_E_CANCEL when `progress` returns nonzero; the read errors. A format 1 set
 * (nothing to check): TITLE_OK, `xx` unused. */
int hf_second_game_by_files(Patchset *ps, Dump *xx, TitleProgress progress, void *progress_ctx);

#endif
