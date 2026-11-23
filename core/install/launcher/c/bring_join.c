/* The Beta sidecars joined for a Bring (bring.h hf_bring_join): core/save/bring.py's join over the save core,
 * core/save/c (extras.c: join_files; heav.c: what an older Heavenfall left), which the launcher's Makefile builds from
 * its own folder. A tree without that folder (an edition's repository that does not carry it) builds this file
 * without the core: a Bring that needs a join then says to bring the hunter with the PC program. */
#include "bring.h"

#include <string.h>

#if defined(__has_include)
#if __has_include("heav.h")
#define HF_BRING_HAS_EXTRAS 1
#include "heav.h"
#endif
#endif

#ifdef HF_BRING_HAS_EXTRAS

int hf_bring_join_available(void) { return 1; }

/* One kind's image picked and joined (join_files' loop body). 0 with *left the left-overs, else HF_BRING_E_JOIN. */
static int join_kind(uint32_t kind, uint8_t *plain, uint32_t size, const uint8_t *identity, int slot,
                     uint8_t *const images[2], const uint32_t sizes[2], uint32_t *left) {
    /* by the file itself (join_files' pick_for): never an image whose own file never landed onto that file */
    int picked = hf_extras_pick_file(images[0], images[0] ? sizes[0] : 0, images[1], images[1] ? sizes[1] : 0, kind,
                                     plain, identity, (uint32_t)slot);
    int code;
    *left = 0;
    if (picked != 0 && picked != 1) return 0;   /* no valid image of the kind: nothing to join */
    code = kind == HF_EXTRAS_USER
               ? hf_extras_join_user(plain, size, (uint32_t)slot, images[picked], sizes[picked])
               : hf_extras_join_card(plain, size, identity, (uint32_t)slot, images[picked], sizes[picked]);
    if (code >= 0) *left = (uint32_t)code;   /* the left-overs, flagged in the rewritten image */
    /* another hunter's or slot's image changes nothing; a whole file is taken as it is (its image emptied) */
    else if (code != HF_EXTRAS_E_HUNTER && code != HF_EXTRAS_WHOLE && code != HF_EXTRAS_WHOLE_NEWER)
        return HF_BRING_E_JOIN;
    return 0;
}

int hf_bring_join(uint8_t *user, uint32_t user_size, uint8_t *card, uint32_t card_size, int slot,
                  uint8_t *const user_images[2], const uint32_t user_sizes[2], uint8_t *const card_images[2],
                  const uint32_t card_sizes[2], const uint8_t *heav, uint32_t heav_size, uint32_t *left_over) {
    uint8_t identity[HF_EXTRAS_IDENTITY_SIZE];
    uint32_t user_left = 0, card_left = 0;
    int older = 0;
    if (!user || !left_over || user_size != HF_EXTRAS_USER_SIZE || (card && card_size != HF_EXTRAS_CARD_SIZE) ||
        slot < 1 || slot > 3)
        return HF_BRING_E_JOIN;
    memcpy(identity, user + HF_EXTRAS_USER_IDENTITY_AT, sizeof identity);   /* the hunter's, before the join */
    if (join_kind(HF_EXTRAS_USER, user, user_size, identity, slot, user_images, user_sizes, &user_left) ||
        (card && join_kind(HF_EXTRAS_CARD, card, card_size, identity, slot, card_images, card_sizes, &card_left)))
        return HF_BRING_E_JOIN;
    if (heav && heav_size == HF_HEAV_SIZE) {   /* after the extras: their tags are the files' as MH4U holds them */
        int n = hf_heav_join(user, user_size, heav, heav_size);
        int m = n < 0 || !card ? 0 : hf_heav_join(card, card_size, heav, heav_size);
        if (n < 0 || m < 0) return HF_BRING_E_JOIN;
        older = n + m;
    }
    *left_over = user_left + card_left + (uint32_t)older;
    return 0;
}

#else

int hf_bring_join_available(void) { return 0; }

int hf_bring_join(uint8_t *user, uint32_t user_size, uint8_t *card, uint32_t card_size, int slot,
                  uint8_t *const user_images[2], const uint32_t user_sizes[2], uint8_t *const card_images[2],
                  const uint32_t card_sizes[2], const uint8_t *heav, uint32_t heav_size, uint32_t *left_over) {
    (void)user, (void)user_size, (void)card, (void)card_size, (void)slot, (void)user_images, (void)user_sizes;
    (void)card_images, (void)card_sizes, (void)heav, (void)heav_size;
    if (left_over) *left_over = 0;
    return HF_BRING_E_NO_JOIN;
}

#endif
