/* One edition the 3DS app can update (a row of the generated hf_editions.h). Portable C99. */
#ifndef HF_EDITION_H
#define HF_EDITION_H

#include <stddef.h>
#include <string.h>

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
    const char *asset_patch_eur_cheats;      /* the same four sets with the cheats (the mod made with them; More's */
    const char *asset_patch_usa_cheats;      /* Cheats) */
    const char *asset_patch_eur_xx_cheats;
    const char *asset_patch_usa_xx_cheats;
    const char *asset_shared;         /* the release's shared file, which the sets of format 3 copy files from */
    int own_save;            /* the game plays on Heavenfall's own extdata: the save copy is a Bring (app_saves.c) */
} HfEdition;

/* The assets hf_latest_release is asked for, in this order (HfRelease.assets[] has the same order). */
enum {
    HF_W_CIA, HF_W_3DSX, HF_W_PATCH_EUR, HF_W_PATCH_USA, HF_W_PATCH_EUR_XX, HF_W_PATCH_USA_XX, HF_W_PATCH_EUR_CHEATS,
    HF_W_PATCH_USA_CHEATS, HF_W_PATCH_EUR_XX_CHEATS, HF_W_PATCH_USA_XX_CHEATS, HF_W_SHARED, HF_W_COUNT
};

static inline void hf_edition_wanted(const HfEdition *e, const char *out[HF_W_COUNT]) {
    out[HF_W_CIA] = e->asset_cia;
    out[HF_W_3DSX] = e->asset_3dsx;
    out[HF_W_PATCH_EUR] = e->asset_patch_eur;
    out[HF_W_PATCH_USA] = e->asset_patch_usa;
    out[HF_W_PATCH_EUR_XX] = e->asset_patch_eur_xx;
    out[HF_W_PATCH_USA_XX] = e->asset_patch_usa_xx;
    out[HF_W_PATCH_EUR_CHEATS] = e->asset_patch_eur_cheats;
    out[HF_W_PATCH_USA_CHEATS] = e->asset_patch_usa_cheats;
    out[HF_W_PATCH_EUR_XX_CHEATS] = e->asset_patch_eur_xx_cheats;
    out[HF_W_PATCH_USA_XX_CHEATS] = e->asset_patch_usa_xx_cheats;
    out[HF_W_SHARED] = e->asset_shared;
}

/* The release's own copy of its releases/latest answer (hf_find_release), named after the app's CIA:
 * "<app>-3ds.cia" -> "<app>-3ds-release.json" (core/app/edition.py, ConsoleRelease.release_file). 0, or -1 when the
 * CIA's name does not end in ".cia" or the name does not fit. */
static inline int hf_edition_release_file(const HfEdition *e, char *out, size_t cap) {
    size_t n = e->asset_cia ? strlen(e->asset_cia) : 0;
    if (n < 5 || strcmp(e->asset_cia + n - 4, ".cia") != 0 || n - 4 + sizeof "-release.json" > cap)
        return -1;
    memcpy(out, e->asset_cia, n - 4);
    memcpy(out + n - 4, "-release.json", sizeof "-release.json");
    return 0;
}

/* The release file of the patch set for a region (0 EUR, 1 USA), with MH XX or without, with the cheats or without. */
static inline int hf_w_patch(int region, int xx, int cheats) {
    int usa = region == 1;
    if (cheats)
        return xx ? (usa ? HF_W_PATCH_USA_XX_CHEATS : HF_W_PATCH_EUR_XX_CHEATS)
                  : (usa ? HF_W_PATCH_USA_CHEATS : HF_W_PATCH_EUR_CHEATS);
    return xx ? (usa ? HF_W_PATCH_USA_XX : HF_W_PATCH_EUR_XX) : (usa ? HF_W_PATCH_USA : HF_W_PATCH_EUR);
}

#endif
