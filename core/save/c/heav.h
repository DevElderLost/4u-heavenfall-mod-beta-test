/* What an older Heavenfall left in MH4U's own plain userN / cardN: gear and Felyne gear past MH4U's counts, their
marks, the cleared bits and log entries of
 * Heavenfall's quests, the new monster ids' records. The game (Heavenfall Beta) sets them apart into the slot's
 * sidecar hfheavN and cleans the file; hf_heav_join below puts them back. The twin of core/save/heav.py, which emits
 * heav_tables.h.
 *
 * Freestanding as extras.c: no libc, no globals, no data of its own, byte-wise access, no divide; the stack holds
 * about 3 KB (a CRC table, an entry's data, the book cards' CRCs). A file is a whole plain userN (HF_EXTRAS_USER_SIZE)
 * or cardN (HF_EXTRAS_CARD_SIZE), told apart by its size; the sidecar is HF_HEAV_SIZE bytes. Negative results are
 * HF_EXTRAS_E_ARG, _E_SIZE, _E_FULL, and nothing changed. */

#ifndef HEAVENFALL_SAVE_HEAV_H
#define HEAVENFALL_SAVE_HEAV_H

#include <stdint.h>

#include "extras.h"
#include "heav_tables.h"

/* 1 when the file holds something of the table (hf_heav_clean would change it), else 0. */
int hf_heav_has(const uint8_t *file, uint32_t size);

/* The file as MH4U knows it, in place: a piece past the counts as the first of its type (its index kept), a Felyne
 * piece as Derring, the marks and quest bits past MH4U's cleared, Heavenfall's quests out of the logs, the new ids'
 * records zero. The places changed. */
int hf_heav_clean(uint8_t *file, uint32_t size);

/* 1 when MH4U knows every byte of the file: nothing of the extras' (fields, whole mark: hf_extras_*_has) and nothing
 * of this table; else 0. A userN's tail is never read. */
int hf_heav_mh4u_clean(const uint8_t *file, uint32_t size);

/* What hf_heav_clean would change, appended to the sidecar `heav` of slot `slot` as one block (a sidecar whose header
 * is not valid or names another slot is started anew). HF_HEAV_NOTHING: nothing to set apart; HF_HEAV_ALREADY: the
 * sidecar holds it all (clean without a write); HF_EXTRAS_E_FULL: no room (keep the file whole); in these three the
 * sidecar is not touched. HF_HEAV_APPENDED: the sidecar to write, then clean. The file is never changed. */
int hf_heav_append(const uint8_t *file, uint32_t size, uint8_t *heav, uint32_t heav_size, uint32_t slot);

/* Bring: the sidecar's content for the file's hunter back into the file (after the extras' join), in place. The
 * pieces that found no room (>= 0); 0 without a valid sidecar. The sidecar is not changed. */
int hf_heav_join(uint8_t *file, uint32_t size, const uint8_t *heav, uint32_t heav_size);

/* The sidecar's valid blocks (0 when its header is not valid). */
int hf_heav_blocks(const uint8_t *heav, uint32_t heav_size);

#endif /* HEAVENFALL_SAVE_HEAV_H */
