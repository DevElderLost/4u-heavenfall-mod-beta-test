/* Heavenfall's save extras: what only Heavenfall knows, set apart from MH4U's own plain
 * userN / cardN into a sidecar image (split), and put back (join). The game and the 3DS launcher run this C; the PC
 * program runs its Python twin, core/save/extras.py, which agrees with it bit for bit and emits extras_tables.h (the
 * constants, the error codes and the table of what is set apart).
 *
 * Freestanding: no libc, no globals, no allocation, no data of its own; every buffer is the caller's and is read and
 * written a byte at a time (little endian, any alignment), so the code runs at any address. The stack holds at most
 * about 2 KB (a CRC table and the Felynes' fingerprints).
 *
 * Every plain file is decrypted (its whole size: HF_EXTRAS_USER_SIZE, HF_EXTRAS_CARD_SIZE). Nothing is re-summed: the
 * game splits before it computes the file's checksum. A hunter is its identity, the HF_EXTRAS_IDENTITY_SIZE bytes at
 * HF_EXTRAS_USER_IDENTITY_AT of the userN file (at HF_EXTRAS_CARD_IDENTITY_AT of the card file), and a slot (1-3).
 * Negative results are HF_EXTRAS_E_* (nothing changed), HF_EXTRAS_WHOLE / _WHOLE_NEWER (the file unchanged, the image
 * emptied) and HF_EXTRAS_NONE. */

#ifndef HEAVENFALL_SAVE_EXTRAS_H
#define HEAVENFALL_SAVE_EXTRAS_H

#include <stdint.h>

#include "extras_tables.h"

/* HF_EXTRAS_USER or HF_EXTRAS_CARD for a valid image (magic, version, CRC, entries, cats) of at least `size` bytes,
 * else 0. */
int hf_extras_image_kind(const uint8_t *image, uint32_t size);
/* A valid image's generation, and how many of its entries are left over (not in the file, waiting for room). */
uint32_t hf_extras_generation(const uint8_t *image);
uint32_t hf_extras_left_over(const uint8_t *image);
/* 1 if a valid image was split from the hunter `identity` (HF_EXTRAS_IDENTITY_SIZE bytes) in `slot`, else 0. */
int hf_extras_owned_by(const uint8_t *image, const uint8_t *identity, uint32_t slot);

/* Which of the two alternating images goes with a file whose tag is `tag`, of the hunter `identity` in `slot`: among
 * the valid images of `kind` (only those of this hunter and slot if any is), the one with that tag; if none or both
 * have it, the newest. 0 (a), 1 (b) or HF_EXTRAS_NONE. A null image is no image. Another hunter's image comes back
 * only when there is no other: its join then returns HF_EXTRAS_E_HUNTER and the caller sets it aside. */
int hf_extras_pick(const uint8_t *a, uint32_t a_size, const uint8_t *b, uint32_t b_size, uint32_t kind, uint32_t tag,
                   const uint8_t *identity, uint32_t slot);
/* The same with what the images' parents tell (extras.py pick_known), for a file known by its tag, its plain tail's
 * CRC (hf_extras_tail_crc; 0 not known), whether it holds anything to set apart and its whole mark (a card file: 0, 0,
 * 0): among the images with the file's tag, the one whose parent tail is the file's (its own file), else not one whose
 * parent tail is another, unless none remains; for a user file marked "keep flagged" or "lacks", the image of the
 * generation the mark names; for an unmarked user file, never an image whose parent tag is the file's own (that
 * image's file never landed: the file still holds what it took), and none at all if that leaves none and the file
 * holds anything to set apart (a join would double it); then, when another remains, not one whose parent tail is the
 * file's tail (another game wrote over that image's parent); the newest of what is left. 0, 1 or HF_EXTRAS_NONE. */
int hf_extras_pick_known(const uint8_t *a, uint32_t a_size, const uint8_t *b, uint32_t b_size, uint32_t kind,
                         uint32_t tag, uint32_t tail, uint32_t has_any, uint32_t mark, const uint8_t *identity,
                         uint32_t slot);
/* hf_extras_pick_known by the file itself (`plain`: the whole plain file of `kind`). 0, 1, HF_EXTRAS_NONE or
 * HF_EXTRAS_E_ARG. */
int hf_extras_pick_file(const uint8_t *a, uint32_t a_size, const uint8_t *b, uint32_t b_size, uint32_t kind,
                        const uint8_t *plain, const uint8_t *identity, uint32_t slot);
/* The newest valid image's generation, 0 without one: the next split's generation is one more. */
uint32_t hf_extras_newest_generation(const uint8_t *a, uint32_t a_size, const uint8_t *b, uint32_t b_size,
                                     uint32_t kind);
/* Where the next image goes (0 a, 1 b): never over the picked one (`picked` 0 or 1, else none picked), else an
 * invalid slot, else the older. */
int hf_extras_write_slot(const uint8_t *a, uint32_t a_size, const uint8_t *b, uint32_t b_size, uint32_t kind,
                         int picked);

/* A file's tag: CRC32 (zlib's) of a user file from byte 8 up to its tail; of a card file's sets block
 * (HF_EXTRAS_CARD_SETS_AT, HF_EXTRAS_CARD_SETS_SIZE bytes). */
uint32_t hf_extras_user_tag(const uint8_t *user);
uint32_t hf_extras_card_tag(const uint8_t *card);
/* 1 if the file holds anything to set apart (a split would change it), 0 if clean, HF_EXTRAS_E_ARG / _E_SIZE. */
int hf_extras_user_has(const uint8_t *user, uint32_t size);
int hf_extras_card_has(const uint8_t *card, uint32_t size);

/* The whole mark: written into a user file the game writes whole (the sidecar could not be written), with the newest
 * generation on disk it supersedes. "Drop all" (keep_flagged 0): the image's entries are all in the file. "Keep
 * flagged" (keep_flagged 1), only when that generation's image is on disk with current flags (the image a join
 * rewrote, written at once) and holds left-overs: its flagged entries are not in the file and come back at the join.
 * "Lacks" (how HF_EXTRAS_LACKS): the file holds nothing of the image of generation `superseded` (the game never had
 * it: a slot the title could not join, written whole before its late join); the join puts that image back as it is
 * and drops any other. The card file needs none: its join skips an item set pair its set already holds. */
uint32_t hf_extras_whole_mark(const uint8_t *user);                 /* the mark, or 0 */
/* HF_EXTRAS_DROP_ALL, HF_EXTRAS_KEEP_FLAGGED, HF_EXTRAS_LACKS, or 0: no mark */
uint32_t hf_extras_whole_kind(uint32_t mark);
/* how: 0 drop all, HF_EXTRAS_LACKS lacks, any other keep flagged */
void hf_extras_set_whole_mark(uint8_t *user, uint32_t superseded, uint32_t how);
int hf_extras_mark_covers(uint32_t mark, uint32_t generation);      /* 16 bits, serial: it wraps */
/* A valid image made generation `generation` and resealed (a join's rewritten image written at once as the newest
 * + 1). 0, or HF_EXTRAS_E_ARG / _E_IMAGE (nothing changed). */
int hf_extras_set_generation(uint8_t *image, uint32_t size, uint32_t generation);

/* zlib's CRC32 of n bytes; a user file's tail's (HF_EXTRAS_TAIL_AT up to its end). */
uint32_t hf_extras_crc32(const uint8_t *p, uint32_t n);
uint32_t hf_extras_tail_crc(const uint8_t *user);
/* A user image's parent: the tag and the tail's CRC (as on disk, enciphered) of the userN on disk it was split from,
 * each 0 when not known (every image made before them); 0 for a card image. set_parent: a valid user image names
 * them, resealed; 0 or HF_EXTRAS_E_ARG / _E_IMAGE (nothing changed). */
uint32_t hf_extras_parent_tag(const uint8_t *image);
uint32_t hf_extras_parent_tail(const uint8_t *image);
int hf_extras_set_parent(uint8_t *image, uint32_t size, uint32_t tag, uint32_t tail);
/* The card file's "not joined" mark (its last word): a card written while the game held none of its sidecar's content
 * carries it; its join then takes the image's tail (the Jukebox's block) over the file's when the image's is non-zero,
 * and clears the mark. */
int hf_extras_card_marked(const uint8_t *card);
void hf_extras_set_card_mark(uint8_t *card);

/* Split: the file becomes clean and `image` (image_size >= the kind's image size) the new image of `generation` for
 * `slot`, naming the file's hunter: what was taken in the table's order, then `carry`'s entries flagged left over
 * (null: none; it may be `image` itself; it must be this hunter's and slot's). Returns the image's entries, or
 * HF_EXTRAS_E_ARG, _E_SIZE, _E_IMAGE (carry), _E_HUNTER (carry), _E_FULL; on failure neither the file nor the image
 * changed. */
int hf_extras_split_user(uint8_t *user, uint32_t size, uint32_t slot, const uint8_t *carry, uint32_t carry_size,
                         uint8_t *image, uint32_t image_size, uint32_t generation);
int hf_extras_split_card(uint8_t *card, uint32_t size, uint32_t slot, const uint8_t *carry, uint32_t carry_size,
                         uint8_t *image, uint32_t image_size, uint32_t generation);

/* Join: the image's content put back into the file; the image rewritten with every entry kept and exactly the ones
 * that found no room flagged left over (joined again with the same file, it gives the same result; a split carries
 * its flagged entries). Returns the left-overs, or HF_EXTRAS_E_ARG, _E_SIZE, _E_IMAGE, _E_HUNTER (another hunter's or
 * slot's image: nothing changed, set the image aside).
 * A user file with a whole mark: "keep flagged" naming the image's generation, only the flagged entries come back
 * (placed, or left over still), the fields and cats are the file's, and the image keeps only those entries with the
 * file's tag; the result is the left-overs (>= 0, the mark still in the file tells this case). Otherwise the file as
 * it is and the image emptied: HF_EXTRAS_WHOLE (the mark covers the image) or _WHOLE_NEWER. An image whose tag is the
 * marked file's own (rewritten by a join of this file), or the one a "lacks" mark names, is joined as an unmarked
 * file's. A book block goes back to the first card whose record has its CRC (its own place first); an item set
 * entry goes only among its own rows (ammo or items); an OR zone with a format byte is never mixed across formats.
 * The userN file's own identity is its hunter's; a card file joins with the hunter's `identity` (the userN file's). */
int hf_extras_join_user(uint8_t *user, uint32_t size, uint32_t slot, uint8_t *image, uint32_t image_size);
int hf_extras_join_card(uint8_t *card, uint32_t size, const uint8_t *identity, uint32_t slot, uint8_t *image,
                        uint32_t image_size);

#endif /* HEAVENFALL_SAVE_EXTRAS_H */
