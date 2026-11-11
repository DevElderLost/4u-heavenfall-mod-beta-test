/* One edition the 3DS app can update (a row of the generated hf_editions.h). Portable C99. */
#ifndef HF_EDITION_H
#define HF_EDITION_H

typedef struct {
    const char *slug;        /* its folder under sdmc:/3ds/heavenfall/ */
    const char *name;        /* the product's name; also the User-Agent */
    const char *repository;  /* "<owner>/<name>" on GitHub */
    const char *title_eur;   /* the console titles' ids, 16 hex digits */
    const char *title_usa;
    const char *asset_cia;   /* the release files: the app as a CIA, as a .3dsx, and the patch set of each region */
    const char *asset_3dsx;
    const char *asset_patch_eur;
    const char *asset_patch_usa;
    const char *asset_patch_eur_xx;   /* the patch sets with MH XX (made from the player's XX dump too) */
    const char *asset_patch_usa_xx;
} HfEdition;

/* The assets hf_latest_release is asked for, in this order (HfRelease.assets[] has the same order). */
enum { HF_W_CIA, HF_W_3DSX, HF_W_PATCH_EUR, HF_W_PATCH_USA, HF_W_PATCH_EUR_XX, HF_W_PATCH_USA_XX, HF_W_COUNT };

static inline void hf_edition_wanted(const HfEdition *e, const char *out[HF_W_COUNT]) {
    out[HF_W_CIA] = e->asset_cia;
    out[HF_W_3DSX] = e->asset_3dsx;
    out[HF_W_PATCH_EUR] = e->asset_patch_eur;
    out[HF_W_PATCH_USA] = e->asset_patch_usa;
    out[HF_W_PATCH_EUR_XX] = e->asset_patch_eur_xx;
    out[HF_W_PATCH_USA_XX] = e->asset_patch_usa_xx;
}

/* The release file of the patch set for a region (0 EUR, 1 USA), with MH XX or without. */
static inline int hf_w_patch(int region, int xx) {
    return xx ? (region == 1 ? HF_W_PATCH_USA_XX : HF_W_PATCH_EUR_XX) : (region == 1 ? HF_W_PATCH_USA : HF_W_PATCH_EUR);
}

#endif
