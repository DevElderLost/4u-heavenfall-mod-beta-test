/* See srcfiles.h. */
#include "srcfiles.h"

#include <string.h>

int hf_second_game_by_files(Patchset *ps, Dump *xx, TitleProgress progress, void *progress_ctx) {
    uint64_t title_id;
    uint8_t hash[32];
    size_t i, n;
    int rc;
    if (!ps) return TITLE_E_ARG;
    if (!patchset_second_game(ps, &title_id, hash)) return TITLE_OK;
    if (!xx || xx->title_id != title_id) return TITLE_E_GAME;
    n = patchset_source_count(ps);
    for (i = 0; i < n; i++) {
        PatchsetSourceInfo info;
        PatchsetBinding b;
        const RomfsFile *f;
        if ((rc = patchset_source_info(ps, i, &info))) return rc;
        if (info.kind != PS_SRC_SECOND) continue;
        f = dump_find(xx, info.path);
        if (!f || f->size != info.size) return TITLE_E_GAME;
        memset(&b, 0, sizeof b);
        b.handle = f->handle;
        b.offset = f->offset;
        b.size = f->size;
        if ((rc = patchset_bind(ps, i, &b)) || (rc = patchset_verify_source(ps, i, progress, progress_ctx))) return rc;
    }
    memcpy(xx->header + DUMP_ROMFS_HASH, hash, 32);
    return TITLE_OK;
}
