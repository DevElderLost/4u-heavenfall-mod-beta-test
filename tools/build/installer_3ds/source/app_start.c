/* Starting titles: the edition's own installed title and the original MH4U (cartridge or digital, whichever is there).
 * From a CIA app the launcher asks APT for an application jump; from the Homebrew Launcher it sets the chainloader and
 * leaves, which is how the Homebrew Launcher itself starts the next program. Before either, the screens come on and
 * the drawing layer closes (ui_exit): nothing is drawn after a jump. */
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "ctr_net.h"
#include "ctr_title.h"
#include "dump.h"

static int in_list(FS_MediaType media, u64 id) {
    u32 count = 0, read = 0, i;
    u64 *ids;
    int found = 0;
    if (R_FAILED(AM_GetTitleCount(media, &count)) || !count) return 0;
    ids = (u64 *)malloc(count * sizeof *ids);
    if (!ids) return 0;
    if (R_SUCCEEDED(AM_GetTitleList(&read, media, count, ids)))
        for (i = 0; i < read; i++) found |= ids[i] == id;
    free(ids);
    return found;
}

/* The original MH4U of `region` first, then the other; `region_first`: that region on both media before the other one
 * (the save copy, which must match the installed edition), else the cartridge before the SD card (starting the game). */
int original_game_for(int region, int region_first, u64 *id, FS_MediaType *media) {
    static const u64 ids[2] = {DUMP_ID_EUR, DUMP_ID_USA};
    int order[2] = {REGION_EUR, REGION_USA}, a, b;
    static const FS_MediaType medias[2] = {MEDIATYPE_GAME_CARD, MEDIATYPE_SD};
    if (region == REGION_USA) { order[0] = REGION_USA; order[1] = REGION_EUR; }
    for (a = 0; a < 2; a++)
        for (b = 0; b < 2; b++) {
            int r = order[region_first ? a : b], m = region_first ? b : a;
            if (in_list(medias[m], ids[r])) {
                *id = ids[r];
                *media = medias[m];
                LOG("original game: %016llX on %s", (unsigned long long)*id, m == 0 ? "the cartridge" : "the SD card");
                return 1;
            }
        }
    return 0;
}

int original_game(u64 *id, FS_MediaType *media) { return original_game_for(app.status.region, 0, id, media); }

/* The title started: the start's check stopped, then (once the jump is sure to be asked) the screens on and the drawing
 * layer closed, so nothing is drawn after it. 0: the app leaves; 1: a message said why it did not start. */
static int jump(u64 id, FS_MediaType media) {
    LOG("start: %016llX (%s)", (unsigned long long)id, ctr_app_form() == CTR_FORM_CIA ? "application jump" : "chainloader");
    ui_working(T(HT_STARTING_GAME));   /* stopping the check and the jump take a moment */
    check_stop(1);
    if (ctr_app_form() == CTR_FORM_CIA) {
        u8 param[0x300], hmac[0x20];
        Result rc = APT_PrepareToDoApplicationJump(0, id, media);
        LOGR("APT_PrepareToDoApplicationJump", rc);
        if (R_FAILED(rc)) {
            char code[32];
            snprintf(code, sizeof code, "%s 0x%08lX", T(HT_CODE), (unsigned long)rc);
            ui_message_ex(T(HT_FAIL_OTHER), HF_TONE_BAD, code);
            return 1;
        }
        ui_exit();
        memset(param, 0, sizeof param);
        memset(hmac, 0, sizeof hmac);
        rc = APT_DoApplicationJump(param, sizeof param, hmac);
        LOGR("APT_DoApplicationJump", rc);
        return 0;   /* the screens are closed: the app leaves whatever APT answered */
    }
    aptSetChainloader(id, media);
    ui_exit();
    return 0;
}

int start_edition(void) {
    int r;
    if (app.status.game_state == HF_GAME_MISSING) {   /* the split title cannot start without its game data */
        LOG("start: the game data is missing: not started");
        ui_message(T(HT_NO_GAME_START));
        return 1;
    }
    for (r = app.status.region == REGION_USA ? REGION_USA : REGION_EUR;; r = REGION_USA) {
        u64 id = edition_title_id(r);
        if (ctr_title_installed(id)) return jump(id, MEDIATYPE_SD);
        if (r == REGION_USA || app.status.region >= 0) break;
    }
    ui_message(T(HT_NOT_INSTALLED));
    return 1;
}

int start_original(void) {
    u64 id;
    FS_MediaType media;
    if (!original_game(&id, &media)) {
        ui_message(T(HT_NOT_THERE));
        return 1;
    }
    return jump(id, media);
}
