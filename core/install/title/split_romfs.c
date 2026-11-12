/* The split title's two RomFS (the installed title's build only; install/title/split_romfs.py): `rom:` reads the game
data title, an
 * add-on content title holding the dump's RomFS, and the title's own RomFS, which holds only the mod's files, is the
 * drive `mod:`. Every `rom:` file is looked up in `mod:` first, as the game's update looks up its own RomFS first.
 *
 *   split_romfs_mount(max_files, max_dirs)   instead of FUN_00105b48's call of FUN_00108930 (the game's `rom:` mount,
 *       at boot; its only caller). Once: the game data's id is the running title's low word under 0004008C
 *       (svcGetProcessInfo type 0x10001, Luma3DS' and Azahar's; FUN_001091d8). If its RomFS opens (archive 0x2345678A,
 *       FS:OpenFileDirectly, FUN_0010db9c; closed at once), the game's mount is made with `redirect` set: the SDK's two
 *       opens of the title's own RomFS in it (split_romfs_open_directly) open the game data's. Then the title's own
 *       RomFS is mounted as `mod:` as the update's FUN_00108930 mounts `patch:`: the work size (FUN_0010b974, tables
 *       cached), a buffer from the default allocator (+0x20), cleared (FUN_0010b91c), the archive opened
 *       (FUN_0010d9ac) and its name registered (FUN_0010bc10); the work size ends in the SDK's fatal error when the
 *       file does not open, so the file is opened and closed first. On any failure it gives back what it took (the
 *       archive's +0x30, the allocator's +0x38) and leaves `mod:` unmounted. Without the game data (or the id), the
 *       game's mount is made as it is: `rom:` is the title's own RomFS, as in a title that holds the whole game.
 *
 *   split_romfs_open_directly(...)   instead of the `bl FUN_0010db9c` of FUN_0010b974 and of FUN_0010d9ac, with
 *       FS:OpenFileDirectly's arguments. While `redirect` is set, an open of the title's own RomFS (SelfNCCH, file
 *       path type 0) opens the game data's RomFS: archive 0x2345678A, archive path (its id, media SD), file path (NCCH
 *       data, TMD content index 0, RomFS). Anything else goes to FS:OpenFileDirectly as it is.
 *
 *   split_romfs_open(file, path, mode)   at the entry of nn::fs::FileStream::TryInitialize (FUN_0010baf8; a `b` over
 *       its first instruction). With `mod:` mounted, a UTF-16 path on `rom:` is tried first on `mod:`. On "not found"
 *       (FUN_00dc0ad8) the file object's words +4..+0x10 are cleared, as the update's FUN_0064cbf4 does before each
 *       try, and the `rom:` path is opened. Success and any other error go back to the caller as they are. Any other
 *       path, a path too long for the copy, or no `mod:`, goes straight to the game's function (file_stream_open_game,
 *       split_romfs_stub.s).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with split_romfs.ld where it places the block); the
 * game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;
typedef unsigned long long u64;

/* FS:OpenFileDirectly's arguments */
#define ARCHIVE_SELF_NCCH     3            /* the running title's own NCCH */
#define ARCHIVE_TITLE_CONTENT 0x2345678A   /* any installed title's content by TMD index (SaveDataAndContent) */
#define PATH_EMPTY            1
#define PATH_BINARY           2
#define OPEN_READ             1
#define SELF_NCCH_ROMFS       0            /* SelfNCCH file path type: the title's own RomFS (5: its update's) */
#define MEDIA_SD              1

/* The game data title: an add-on content title with the running title's low word */
#define GAME_DATA_HIGH        0x0004008C
#define CURRENT_PROCESS       0xFFFF8001
#define PROCESS_TITLE_ID      0x10001      /* svcGetProcessInfo type of Luma3DS' kernel extension (also Azahar's) */

#define USE_CACHE             1            /* the RomFS tables are read into the buffer, as for `rom:` */
#define BUFFER_ALIGN          0x10         /* the game's mounts' */

/* split_romfs_state.mounted */
#define NOT_TRIED             0
#define MOUNTED               1
#define NOT_MOUNTED           2

/* A rewritten path's room in UTF-16 units, its terminator included: MtFile builds its paths in 0x109 */
#define PATH_ROOM             0x110
#define DRIVE_LENGTH          4            /* "rom:" and "mod:" */

/* The file object of nn::fs::FileStream (TryInitialize's first argument): FUN_0064cbf4 clears words 1 to 4 before each
   try */
#define FILE_CLEARED_FIRST    1
#define FILE_CLEARED_LAST     4

struct allocator;
struct allocator_vtable {
    u32 other[8];
    void *(*allocate)(struct allocator *self, u32 size, s32 align);       /* +0x20 */
    u32 other_2[5];
    void (*free)(struct allocator *self, void *block);                     /* +0x38 */
};
struct allocator {
    const struct allocator_vtable *vtable;
};
_Static_assert(__builtin_offsetof(struct allocator_vtable, allocate) == 0x20, "FUN_00108930 allocates through +0x20");
_Static_assert(__builtin_offsetof(struct allocator_vtable, free) == 0x38, "FUN_00105fdc frees through +0x38");

struct archive;
struct archive_vtable {
    u32 other[12];
    void (*release)(struct archive *self);                                 /* +0x30 */
};
struct archive {
    const struct archive_vtable *vtable;
};
_Static_assert(__builtin_offsetof(struct archive_vtable, release) == 0x30, "FUN_001093d4 releases through +0x30");

/* Archive 0x2345678A's archive path: the title's id, its media (the SDK's add-on content mount, FUN_00479bc4) */
struct title_path {
    u32 title_low;
    u32 title_high;
    u32 media;
    u32 reserved;
};

struct split_romfs_state {
    u32 mounted;
    void *buffer;
    u32 size;
    const struct title_path *redirect;      /* set during the game's `rom:` mount: the game data's path */
};

extern struct split_romfs_state split_romfs_state;      /* .bss (blocks.py VARIABLES) */
extern struct allocator *const default_allocator;        /* the SDK's default allocator */
extern const u32 fs_user_session;                        /* the FS:USER session's handle */

/* Game functions */
void fs_mount_rom(u32 max_files, u32 max_dirs);                                    /* FUN_00108930 */
s32 svc_get_process_info(u64 *out, u32 process, u32 type);                         /* FUN_001091d8 */
s32 fs_open_file_directly(const u32 *session, u32 *handle, u32 transaction, u32 archive, u32 archive_path_type,
                          const void *archive_path, u32 archive_path_size, u32 file_path_type, const void *file_path,
                          u32 file_path_size, u32 flags, u32 attributes);          /* FUN_0010db9c */
s32 svc_close_handle(u32 handle);                                                  /* FUN_0011185c */
u32 romfs_work_size(u32 max_files, u32 max_dirs, u32 use_cache, const u32 *path);  /* FUN_0010b974 */
void memory_clear(void *address, u32 size);                                        /* FUN_0010b91c */
s32 romfs_archive_open(struct archive **archive, u32 max_files, u32 max_dirs, void *buffer, u32 size, u32 use_cache,
                       const u32 *path);                                           /* FUN_0010d9ac */
s32 fs_register_mount(const char *name, struct archive *archive, u32 a, u32 b);    /* FUN_0010bc10 */
u32 fs_is_not_found(s32 result);                                                   /* FUN_00dc0ad8 */
/* split_romfs_stub.s: the game's nn::fs::FileStream::TryInitialize */
s32 file_stream_open_game(u32 *file, const u16 *path, u32 mode);

static const u32 own_romfs_path[3] = {SELF_NCCH_ROMFS, 0, 0};
/* 0x2345678A's file path: NCCH data (0), TMD content index 0, RomFS (0), no ExeFS name */
static const u32 content_romfs_path[5] = {0, 0, 0, 0, 0};
static const u32 empty_path = 0;
static const char mod_drive[] = "mod:";
static const u16 mod_drive_utf16[DRIVE_LENGTH + 1] = {'m', 'o', 'd', ':', 0};

/* Whether a RomFS opens: FUN_0010b974's own open, which would end in the fatal error */
static u32 romfs_opens(u32 archive, u32 archive_path_type, const void *archive_path, u32 archive_path_size,
                       const u32 *file_path, u32 file_path_size)
{
    u32 handle = 0;
    if (fs_open_file_directly(&fs_user_session, &handle, 0, archive, archive_path_type, archive_path,
                              archive_path_size, PATH_BINARY, file_path, file_path_size, OPEN_READ, 0) < 0)
        return 0;
    svc_close_handle(handle);
    return 1;
}

/* The game data's archive path, from the running title's id; 0 when the kernel does not give it */
static u32 game_data_path(struct title_path *out)
{
    u64 title = 0;
    if (svc_get_process_info(&title, CURRENT_PROCESS, PROCESS_TITLE_ID) < 0)
        return 0;
    out->title_low = (u32)title;
    out->title_high = GAME_DATA_HIGH;
    out->media = MEDIA_SD;
    out->reserved = 0;
    return 1;
}

/* The title's own RomFS as `mod:`, as the update's FUN_00108930 mounts `patch:` */
static void mount_mod(u32 max_files, u32 max_dirs)
{
    if (!romfs_opens(ARCHIVE_SELF_NCCH, PATH_EMPTY, &empty_path, 1, own_romfs_path, sizeof own_romfs_path))
        return;
    u32 size = romfs_work_size(max_files, max_dirs, USE_CACHE, own_romfs_path);
    struct allocator *heap = default_allocator;
    void *buffer = heap->vtable->allocate(heap, size, BUFFER_ALIGN);
    if (!buffer)
        return;
    memory_clear(buffer, size);
    struct archive *archive = 0;
    if (romfs_archive_open(&archive, max_files, max_dirs, buffer, size, USE_CACHE, own_romfs_path) < 0) {
        heap->vtable->free(heap, buffer);
        return;
    }
    if (fs_register_mount(mod_drive, archive, 0, 0) < 0) {
        archive->vtable->release(archive);
        heap->vtable->free(heap, buffer);
        return;
    }
    split_romfs_state.buffer = buffer;
    split_romfs_state.size = size;
    split_romfs_state.mounted = MOUNTED;
}

__attribute__((used, section(".text.entry"))) void split_romfs_mount(u32 max_files, u32 max_dirs)
{
    if (split_romfs_state.mounted != NOT_TRIED) {
        fs_mount_rom(max_files, max_dirs);
        return;
    }
    split_romfs_state.mounted = NOT_MOUNTED;
    struct title_path game_data;
    if (!game_data_path(&game_data) || !romfs_opens(ARCHIVE_TITLE_CONTENT, PATH_BINARY, &game_data, sizeof game_data,
                                                    content_romfs_path, sizeof content_romfs_path)) {
        fs_mount_rom(max_files, max_dirs);
        return;
    }
    split_romfs_state.redirect = &game_data;
    fs_mount_rom(max_files, max_dirs);
    split_romfs_state.redirect = 0;
    mount_mod(max_files, max_dirs);
}

__attribute__((used, section(".text.entry"))) s32 split_romfs_open_directly(
    const u32 *session, u32 *handle, u32 transaction, u32 archive, u32 archive_path_type, const void *archive_path,
    u32 archive_path_size, u32 file_path_type, const u32 *file_path, u32 file_path_size, u32 flags, u32 attributes)
{
    const struct title_path *game_data = split_romfs_state.redirect;
    if (game_data && archive == ARCHIVE_SELF_NCCH && file_path_type == PATH_BINARY
            && file_path_size == sizeof own_romfs_path && file_path[0] == SELF_NCCH_ROMFS)
        return fs_open_file_directly(session, handle, transaction, ARCHIVE_TITLE_CONTENT, PATH_BINARY, game_data,
                                     sizeof *game_data, PATH_BINARY, content_romfs_path, sizeof content_romfs_path,
                                     flags, attributes);
    return fs_open_file_directly(session, handle, transaction, archive, archive_path_type, archive_path,
                                 archive_path_size, file_path_type, file_path, file_path_size, flags, attributes);
}

static u32 on_rom(const u16 *path)
{
    return path[0] == 'r' && path[1] == 'o' && path[2] == 'm' && path[3] == ':';
}

/* `out`: "mod:" and what follows "rom:" in `path`; 0 if it does not fit in PATH_ROOM */
static u32 on_mod(u16 *out, const u16 *path)
{
    u32 n;
    for (n = 0; n < DRIVE_LENGTH; n++)
        out[n] = mod_drive_utf16[n];
    for (path += DRIVE_LENGTH; n < PATH_ROOM; path++)
        if (!(out[n++] = *path))
            return 1;
    return 0;
}

__attribute__((used, section(".text.entry"))) s32 split_romfs_open(u32 *file, const u16 *path, u32 mode)
{
    u16 moved[PATH_ROOM];
    if (split_romfs_state.mounted != MOUNTED || !on_rom(path) || !on_mod(moved, path))
        return file_stream_open_game(file, path, mode);
    s32 result = file_stream_open_game(file, moved, mode);
    if (result >= 0 || !fs_is_not_found(result))
        return result;
    for (u32 i = FILE_CLEARED_FIRST; i <= FILE_CLEARED_LAST; i++)
        file[i] = 0;
    return file_stream_open_game(file, path, mode);
}
