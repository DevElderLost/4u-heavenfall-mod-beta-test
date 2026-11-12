#include "find.h"

#include <dirent.h>
#include <stdio.h>
#include <string.h>

#include "dump.h"
#include "pack.h"

const char *const FIND_DUMP_DIRS[] = {"sdmc:/gm9/out", "sdmc:/"};
const size_t FIND_DUMP_DIR_COUNT = 2;
const char *const FIND_PACK_DIRS[] = {"sdmc:/", "sdmc:/3ds", "sdmc:/gm9/out"};
const size_t FIND_PACK_DIR_COUNT = 3;

static int join(char *out, size_t cap, const char *dir, const char *name) {
    size_t n = strlen(dir);
    int slash = n && dir[n - 1] != '/';
    return snprintf(out, cap, "%s%s%s", dir, slash ? "/" : "", name) >= (int)cap;
}

static int is_mh4u(uint64_t id) { return id == DUMP_ID_EUR || id == DUMP_ID_USA; }

/* The game asked for: MH4U of either region (0), or the title `want`. */
static int wanted(uint64_t id, uint64_t want) { return want ? id == want : is_mh4u(id); }

int find_dump(const FileApi *api, const char *const *dirs, size_t ndirs, uint64_t want_id, char *out, size_t cap,
              int *seen_other) {
    int encrypted = 0;
    size_t d;
    if (seen_other) *seen_other = 0;
    for (d = 0; d < ndirs; d++) {
        DIR *dir = opendir(dirs[d]);
        struct dirent *e;
        if (!dir) continue;
        while ((e = readdir(dir))) {
            char path[FIND_PATH];
            void *h;
            uint64_t size, id = 0;
            int rc;
            if (e->d_name[0] == '.' || join(path, sizeof path, dirs[d], e->d_name)) continue;
            if (api->open(api->ctx, path, &h, &size)) continue;
            rc = size >= DUMP_IDENTIFY_BYTES ? dump_identify(api->read, api->ctx, h, &id, NULL) : TITLE_E_FORMAT;
            api->close(api->ctx, h);
            if ((rc == TITLE_OK || rc == TITLE_E_ENCRYPTED) && !wanted(id, want_id)) {
                if (rc == TITLE_OK && seen_other && is_mh4u(id) && is_mh4u(want_id)) *seen_other = 1;
                continue;
            }
            if (rc == TITLE_E_ENCRYPTED) encrypted = 1;
            if (rc == TITLE_OK) {
                closedir(dir);
                if (strlen(path) >= cap) return TITLE_E_FORMAT;
                strcpy(out, path);
                return TITLE_OK;
            }
        }
        closedir(dir);
    }
    return encrypted ? TITLE_E_ENCRYPTED : TITLE_E_FORMAT;
}

int find_pack(const FileApi *api, const char *const *dirs, size_t ndirs, char *out, size_t cap) {
    size_t d;
    for (d = 0; d < ndirs; d++) {
        char path[FIND_PATH];
        void *h;
        uint64_t size;
        uint8_t magic[8];
        int ok;
        if (join(path, sizeof path, dirs[d], TITLE_PACK_NAME) || api->open(api->ctx, path, &h, &size)) continue;
        ok = size >= PACK_HEADER && !api->read(api->ctx, h, 0, magic, sizeof magic) && !memcmp(magic, PACK_MAGIC, 8);
        api->close(api->ctx, h);
        if (ok) {
            if (strlen(path) >= cap) return TITLE_E_FORMAT;
            strcpy(out, path);
            return TITLE_OK;
        }
    }
    return TITLE_E_FORMAT;
}
