/* What to install, and which files an update title carries. Portable C99; tests/install/title/test_plan_c.py.
 *
 * A base title holds the game's RomFS with the whole mod merged in; an update title holds only what differs from the
 * base. The app keeps the base's manifest on the SD card: the SHA-256 of each file of
 * the mod it installed, as core/install/title/build_title.py mod_manifest. */
#ifndef PLAN_H
#define PLAN_H

#include "dump.h"
#include "pack.h"
#include "title_io.h"

typedef struct {
    char *path;
    uint8_t sha[32];
} ManifestEntry;

typedef struct {
    ManifestEntry *e;   /* sorted by path (byte order) */
    size_t n;
} Manifest;

void manifest_free(Manifest *m);
/* The pack's files and their hashes. */
int manifest_from_pack(Manifest *m, const Pack *p);
/* Lines of "<64 lower case hex> <path>\n". TITLE_E_FORMAT for anything else. */
int manifest_parse(Manifest *m, const char *text, size_t len);
int manifest_write(const Manifest *m, TitleWrite write, void *ctx);
const ManifestEntry *manifest_find(const Manifest *m, const char *path);

typedef struct {
    int base_installed;      /* our base title is in the console's title list */
    int update_installed;    /* our update title is too */
    int have_manifest;       /* the base's manifest is on the card and is the base's */
    int pack_has_patch;      /* pack_has_patch(): the executable reads an update title's files */
} InstallState;

/* What title_build_open builds (build.h): the base title (the game with the mod over it), the update title, and the
 * split title's two: the game data (the dump's RomFS as an add-on content title) and
 * the edition's title with the mod's files alone. */
typedef enum { PLAN_BASE, PLAN_UPDATE, PLAN_GAME, PLAN_MOD } PlanKind;

typedef struct {
    PlanKind kind;
    int delete_update;       /* after installing the base: delete the older update title, it would override the new base */
    int save_manifest;       /* after installing the base: keep its manifest */
} InstallPlan;

/* The update title alone when the base is installed, its manifest is known and the executable reads an update;
 * otherwise the base title. */
InstallPlan plan_install(const InstallState *state);

/* The files an update carries over a base holding `base`: the pack's files that are new or differ, and the game's own
 * copy (from `dump`) of any file the base had and this pack no longer has. `out` is malloc'd (free it); its paths
 * point into the pack and the dump. */
int update_files(const Pack *pack, const Manifest *base, Dump *dump, RomfsFile **out, size_t *count);

/* The update title's id for a base title's id: its low word under 0004000E. */
uint64_t update_title_id(uint64_t base_title_id);

#endif
