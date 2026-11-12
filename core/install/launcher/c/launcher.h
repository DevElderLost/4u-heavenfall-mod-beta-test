/* The launcher app's portable logic (C99, no libctru): the mod's version as the
 * title's TMD version, the installed record, the log lines, the paths on the SD card, the texts in both languages and
 * the title's SMDH. The 3DS side (tools/build/installer_3ds/source/) only calls these; tests/install/launcher/
 * test_launcher_app.py builds them with the host gcc. */
#ifndef HF_LAUNCHER_H
#define HF_LAUNCHER_H

#include <stddef.h>
#include <stdint.h>

/* ---- the version as the TMD's title version (u16: major 6 bits, minor 6 bits, micro 4 bits) ---- */

/* "v1.2.3" or "1.2" -> major << 10 | minor << 4 | micro. 0 on success, -1 for anything that is no version, has more than
 * three parts or does not fit (major or minor over 63, micro over 15), or is 0 (a TMD version 0 means "not ours"). */
int hf_tmd_version(const char *text, uint16_t *out);

/* Which region's MH4U dump to take when the card holds both a European and an American one: the installed edition's
 * region, else the console's (CFG's region: 1 USA; 2 EUR and 3 AUS, which sells the European game), else -1 (the
 * first dump found). Regions: 0 EUR, 1 USA. The folder's order can change between runs; a choice made by it would
 * rebuild the game data each time. */
int hf_preferred_dump_region(int installed_region, int cfg_region);

/* The game data's add-on content title of an edition's title: 0004008C and the same low
 * word, as an add-on's id is its application's. */
static inline uint64_t hf_game_title_id(uint64_t app_title_id) {
    return 0x0004008C00000000ull | (app_title_id & 0xFFFFFFFFull);
}
/* The reverse: "1.2.3". */
void hf_tmd_version_text(uint16_t tmd, char *out, size_t cap);

/* 1 when the app may install, remove or write the save of `id` (A): an
 * application (00040000), add-on content (0004008C, the game data) or update (0004000E) whose unique id is in
 * Heavenfall's block past the launcher's own, 0x69691 to 0x6969F, with a low byte of 0. Never the original MH4U, its
 * update, a system title or the launcher (0x69690). Every AM removal, ticket, import and save write asks it first,
 * whatever an edition file says. */
int hf_title_ours(uint64_t id);

#define HF_LAUNCHER_TITLE 0x0004000006969000ull    /* the launcher's own title (launcher.rsf's UniqueId 0x69690) */

/* 1 when a CIA's start (`head`, its first `len` bytes: about 12 KB reach its TMD's title id) is the launcher's title:
 * its ticket and its TMD both name HF_LAUNCHER_TITLE. The app's own CIA update imports nothing else. */
int hf_cia_is_launcher(const uint8_t *head, size_t len);
/* The launcher's CIA (hf_cia_is_launcher) and its version, its TMD's title version as text (hf_tmd_version_text): 1,
 * else 0 and "" (another title, or the head cut before it). A probe's test launcher has no release tag but this. */
int hf_cia_launcher_version(const uint8_t *head, size_t len, char *out, size_t cap);

/* 1 when a .3dsx's argv[0] is a path its self-update may rename (to ".old") and write: a .3dsx file on the card
 * ("sdmc:/", a name before ".3dsx", any case), never a folder, another device, a ".." step, Nintendo 3DS/ or luma/. */
int hf_own_3dsx_ok(const char *path);

/* ---- the installed record, sdmc:/3ds/heavenfall/<slug>/installed.json ---- */

typedef struct {
    char version[48];   /* the release's version, "" when none */
    unsigned tmd;       /* the TMD version written with it */
    int complete;       /* 0: an install was started and not finished */
    int xx;             /* the title was built from the set with MH XX (the player's XX dump) */
    int xx_no_room;     /* this version's XX set did not fit the console's memory: the plain set was installed */
    int save_pending;   /* the first install's save copy was neither done nor declined: offered again at start */
    int layout;         /* 1: the old single title, 2: the split title (a record without it is 1) */
    char game[65];      /* the game data title's dump: its RomFS superblock hash, 64 lowercase hex digits; "" none */
    int game_complete;  /* the game data was installed whole (0: none, or an install was cut) */
    char xx_dump[65];   /* with "xx": the MH XX dump the title was built with, its RomFS superblock hash (hf_hex); the
                           set may name another printing of the game whose files were checked equal at the install.
                           Without: the dump whose files were found to differ from this version's XX set (not tried
                           again until a new version: hf_xx_came). "" none */
    char save_restore[18];  /* the save backup (saves/<stamp>, hf_save_stamp_ok) the title's save must come back from:
                               written before an install removes the title (its save goes with it), cleared once the
                               save is back; "" none */
} HfInstalled;

/* Writes the JSON ({"version", "tmd", "region", "xx", "xx_no_room", "save_pending", "layout", "game", "game_complete",
 * "xx_dump", "save_restore", "complete"}); the length, or -1 when it does not fit or a field is damaged. */
#define HF_INSTALLED_MAX 1024   /* the longest record with its terminator: the app reads and writes it whole */
int hf_installed_format(const HfInstalled *in, const char *region, char *out, size_t cap);
/* Reads it back: 0 on success, -1 for anything else. A record without "xx" (an older launcher's) is a title without
 * MH XX; without "xx_no_room", one whose XX set fitted; without "save_pending", no save copy waiting; without "layout",
 * layout 1 (the old single title), with no game data; without "save_restore", no save to bring back. */
int hf_installed_parse(const char *json, size_t len, HfInstalled *out);

/* Whether an install leaves the save copy waiting (save_pending): what the edition's record says when there is one
 * (`prev`; a copy done or declined stays so after the title was removed and installed again, by a stopped update or
 * by hand: its save stayed on the console, and copying the original over it would replace the player's progress);
 * without a record, only when no title of the edition is installed (a first install). */
int hf_save_pending_after(int title_installed, const HfInstalled *prev);

/* A dump's RomFS superblock hash as the record writes it: 64 lowercase hex digits and the terminator. */
void hf_hex(const uint8_t hash[32], char out[65]);
/* 1 when the game data title must be made: it is not in AM's list (`present` 0), the
 * record (NULL: none) does not say it was installed whole, or it names another dump than `dump_hash` (hf_hex; "" when
 * no dump was found: not compared). */
int hf_game_stale(int present, const HfInstalled *rec, const char *dump_hash);

/* The game data title's RomFS as the game opens it (archive 0x2345678A): where level 3
 * starts in the file's first bytes (`n` of them, 0x60 enough). FS serves it from level 3 on, as libctru's
 * romfsMountFromTitle reads it (level 3's own header of 0x28 bytes at 0: offset 0); a whole image starts with its
 * IVFC header, which says where level 3 is. 0 and the offset, or -1 for anything that is no RomFS. */
int hf_romfs_level3_at(const uint8_t *ivfc, size_t n, uint64_t *at);
/* 1 when `h` (the first `n` bytes of level 3) is a RomFS level 3 header: its length is 0x28. */
int hf_romfs_level3_ok(const uint8_t *h, size_t n);

/* ---- the log: every line has the time since the start; a phase is timed ---- */

typedef struct {
    void (*sink)(void *ctx, const char *line);   /* one line, no newline */
    void *ctx;
    uint64_t start_ms;
} HfLog;

/* "[   12.345] text". `now_ms` is a monotonic clock in milliseconds. */
void hf_log(const HfLog *log, uint64_t now_ms, const char *fmt, ...);
/* "[   12.345] phase: 2345 ms, 1234 MB, 3.4 MB/s" (no rate when bytes is 0 or the time 0). */
void hf_log_phase(const HfLog *log, uint64_t now_ms, const char *phase, uint64_t began_ms, uint64_t bytes);
/* The rate in tenths of MB/s (bytes * 10 / ms / 1048.576), 0 when ms is 0. */
unsigned hf_rate_x10(uint64_t bytes, uint64_t ms);

/* ---- paths ---- */

enum { HF_SAVE_ORIGINAL, HF_SAVE_HEAVENFALL };
int hf_path_dir(const char *slug, char *out, size_t cap);        /* sdmc:/3ds/heavenfall/<slug> */
int hf_path_installed(const char *slug, char *out, size_t cap);  /* .../installed.json */
int hf_path_log(const char *slug, char *out, size_t cap);        /* .../launcher.log */
int hf_path_test_release(const char *slug, char *out, size_t cap);   /* .../test_release (the probe build's release) */
int hf_path_friends_dump(const char *slug, char *out, size_t cap);   /* .../friends_dump (the friends module's code) */
int hf_path_resume(const char *slug, char *out, size_t cap);    /* .../resume.json (uimodel.h, "the resume file") */
int hf_path_timings(const char *slug, char *out, size_t cap);   /* .../timings.json (the last install's times) */
/* .../saves/YYYY-MM-DD_HHMMSS/original or /heavenfall: the backups made before a save is copied or the title is
 * removed by an install. */
int hf_path_save_backup(const char *slug, int which, int year, int month, int day, int hour, int minute, int second,
                        char *out, size_t cap);
/* "YYYY-MM-DD_HHMMSS" (a backup's folder under saves/) into `out`; -1 (and "") for a date out of range. */
int hf_save_stamp(int year, int month, int day, int hour, int minute, int second, char out[18]);
/* 1 when `s` is such a stamp: digits where the stamp has them, nothing more. */
int hf_save_stamp_ok(const char *s);
/* .../saves/<stamp>/original or /heavenfall (hf_path_save_backup by its stamp). */
int hf_path_save_at(const char *slug, int which, const char *stamp, char *out, size_t cap);
/* .../saves/<stamp>/heavenfall.sav: the title's raw save file (hf_save_raw_path), kept beside its backup while an
 * install removes the title and puts it back. */
int hf_path_save_raw(const char *slug, const char *stamp, char *out, size_t cap);
/* The SD card's raw, encrypted save file of an installed application title, as an ARCHIVE_SDMC path:
 * <ctr_root>/title/00040000/<low word, 8 lowercase hex digits>/data/00000001.sav. `ctr_root` is FS's
 * GetSdmcCtrRootPath, "/Nintendo 3DS/<ID0>/<ID1>" (two folders of 32 hex digits). The file's encryption keys on the
 * console and this path, its CMAC on the console and the title id (3dbrew: "SD Filesystem"; "DISA and DIFF",
 * CTR-SIGN), so the same bytes put back at the same path after the title was removed and installed again are the same
 * save. Only Heavenfall's application titles (hf_title_ours, high word 00040000): -1 and "" for anything else. */
int hf_save_raw_path(const char *ctr_root, uint64_t title_id, char *out, size_t cap);

/* ---- texts ---- */

typedef enum { HF_LANG_EN, HF_LANG_ES } HfLang;

/* The texts are UTF-8 with only letters the console's font draws (code page 437: á é í ó ú ñ Ñ ¿ ¡ É ü, no capital
 * Á Í Ó Ú). `utf8` as the screen takes it: one CP437 byte per letter, '?' for a letter the font lacks, cut to fit
 * `cap` with its terminator. The bytes written, without it. */
size_t hf_cp437(const char *utf8, char *out, size_t cap);

typedef enum {
    HT_TITLE, HT_EDITION, HT_REGION, HT_INSTALLED, HT_LATEST, HT_DUMP, HT_LUMA, HT_FREE, HT_NONE, HT_YES, HT_NO,
    HT_NOT_FOUND, HT_UNKNOWN, HT_CHECKING,
    HT_BTN_UPDATE, HT_BTN_PLAY, HT_BTN_PLAY_ORIGINAL, HT_BTN_CHECKS, HT_BTN_ONLINE, HT_BTN_EXIT,
    HT_CANCEL_HINT, HT_NO_SLEEP, HT_UPDATED, HT_UP_TO_DATE, HT_CANCELLED, HT_FAILED, HT_NOTHING_INSTALLED,
    HT_NO_DUMP, HT_NO_SET, HT_NEEDS_APP, HT_NO_NET, HT_NO_RELEASE, HT_APP_UPDATED, HT_NO_ROOM,
    HT_SAVE_OFFER, HT_SAVE_NEED_RUN, HT_SAVE_DONE, HT_SAVE_NONE, HT_ONLINE_NEEDED, HT_ONLINE_INSTALLED,
    HT_ONLINE_INSTALLABLE, HT_ONLINE_UNSUPPORTED, HT_REBOOT, HT_NOT_THERE, HT_NOT_INSTALLED, HT_PROBE, HT_PRESS_A,
    HT_PRESS_B, HT_ROUTE_SLOT, HT_ROUTE_AM, HT_ROUTE_RETRY,
    /* what the screen says while a step runs (the install's phases among them) */
    HT_PHASE_RELEASE, HT_PHASE_APP_DOWNLOAD, HT_PHASE_SET_DOWNLOAD, HT_PHASE_PROBE_DOWNLOAD, HT_PHASE_OPEN,
    HT_PHASE_OPEN_SIZING, HT_PHASE_PREPARE, HT_PHASE_HASH, HT_PHASE_WRITE, HT_PHASE_WRITE_2, HT_PHASE_AM, HT_WORKING,
    /* why an update failed, after HT_FAILED */
    HT_WHY_MEMORY, HT_WHY_DUMP, HT_WHY_SD, HT_WHY_SET, HT_WHY_AM, HT_WHY_NET, HT_WHY_OTHER, HT_CODE,
    HT_LANG_SWITCH, HT_ENCRYPTED, HT_OTHER_REGION, HT_ONLINE_ASK_INSTALL, HT_ONLINE_ASK_REMOVE, HT_CHECKS_KEYS,
    /* the player's MH XX dump: the status line, and why an update goes without it */
    HT_XX, HT_FOUND, HT_XX_OTHER_VERSION, HT_XX_OTHER_NOTE, HT_XX_NO_SET_NOTE, HT_PHASE_SET_DOWNLOAD_XX,
    HT_XX_NO_ROOM_NOTE,
    /* the home screen (uimodel.h hf_home) */
    HT_HOME_UP_TO_DATE, HT_HOME_NEW_VERSION, HT_HOME_NOT_INSTALLED, HT_HOME_REPAIR, HT_HOME_CHECKING,
    HT_HOME_CHECK_FAILED, HT_HOME_NEED_DUMP, HT_HOME_DUMP_ENCRYPTED, HT_HOME_DUMP_OTHER_REGION, HT_HOME_SETUP_HINT,
    HT_HOME_INSTALL_HINT, HT_HOME_INSTALLED_LABEL, HT_HOME_LATEST_LABEL, HT_NOTES_TITLE, HT_NOTES_KEYS,
    /* buttons */
    HT_BTN_INSTALL, HT_BTN_UPDATE_TO, HT_BTN_SETUP, HT_BTN_MORE, HT_BTN_INFO, HT_BTN_SAVE, HT_BTN_LANGUAGE, HT_BTN_BACK,
    HT_BTN_PLAY_NOW, HT_BTN_SKIP, HT_BTN_CHECK_AGAIN, HT_BTN_CONTINUE, HT_BTN_NOTES,
    /* the install's steps and its bar (uimodel.h HfStage) */
    HT_STAGE_DOWNLOAD, HT_STAGE_INSTALL, HT_STAGE_FINISH, HT_TASK_ETA, HT_TASK_ETA_UNKNOWN, HT_CANCEL_AGAIN,
    HT_CANNOT_CANCEL, HT_SCREENS_OFF_HINT, HT_BATTERY_LOW, HT_DONE_READY,
    /* why an update stopped, as a sentence, and what to do (uimodel.h hf_failure_advice) */
    HT_FAIL_DUMP, HT_FAIL_MEMORY, HT_FAIL_SD, HT_FAIL_SET, HT_FAIL_AM, HT_FAIL_OTHER, HT_TODO_ROOM, HT_TODO_NET,
    HT_TODO_DUMP, HT_TODO_RESTART, HT_TODO_RETRY,
    /* the simple display mode, and the self-update going on by itself */
    HT_SIMPLE_DISPLAY, HT_APP_RESTARTING, HT_APP_REOPEN, HT_RESUMING, HT_START_EXIT,
    /* the flows: the app's own install, the simple display's footer, the end of a first install */
    HT_PHASE_APP_INSTALL, HT_SIMPLE_FOOTER, HT_DONE_SAVE_HINT,
    /* the first-run guide's pages (GodMode9's menu names in its own English words) */
    HT_GUIDE_DUMP_TITLE, HT_GUIDE_DUMP_WHY, HT_GUIDE_GM9_START, HT_GUIDE_CART, HT_GUIDE_DIGITAL, HT_GUIDE_GM9_END,
    HT_GUIDE_DECRYPT_TITLE, HT_GUIDE_DECRYPT_OPEN, HT_GUIDE_DECRYPT_CHOOSE, HT_GUIDE_XX_TITLE, HT_GUIDE_XX_WHY,
    HT_GUIDE_XX_ENCRYPTED, HT_GUIDE_INSTALL_TITLE, HT_GUIDE_INSTALL_STEP, HT_GUIDE_SAVE_TITLE, HT_GUIDE_SAVE_RUN,
    HT_GUIDE_SAVE_COPY, HT_GUIDE_DONE_TITLE, HT_GUIDE_DONE_STEP,
    /* what a button does while it runs (ui_working), and the language just chosen */
    HT_SAVE_BACKING_UP, HT_SAVE_COPYING, HT_STARTING_GAME, HT_ONLINE_WORKING, HT_CLOSING, HT_LANG_NOW,
    HT_SAVE_BACKUP_FAILED, HT_SAVE_COPY_FAILED,
    /* the split title: the game data title */
    HT_HOME_GAME_MISSING, HT_HOME_GAME_UPDATE, HT_HOME_GAME_HINT, HT_GAME_DATA, HT_GAME_VALUE_OK, HT_GAME_VALUE_MISSING,
    HT_GAME_VALUE_UPDATE, HT_NO_GAME_START, HT_GAME_NOTE, HT_MOD_NOTE, HT_PHASE_GAME_CHECK, HT_PHASE_XX_FILES,
    HT_FAIL_GAME_CHECK, HT_XX_FILES_NOTE,
    /* the install page's buttons: the screens kept on, and a cancel by touch (two taps, as B twice) */
    HT_BTN_KEEP_SCREENS, HT_BTN_LET_SCREENS, HT_SCREENS_STAY_ON, HT_BTN_CANCEL, HT_BTN_CANCEL_AGAIN,
    /* what the app writes and deletes (A): a damaged online file, an update
     * stopped after the old title went, the save not backed up before an install */
    HT_ONLINE_DAMAGED, HT_OLD_REMOVED, HT_FAIL_SAVE_BACKUP,
    /* the save across an update: AM removes the title with its save, the app puts it back (launcher.md) */
    HT_SAVE_RESTORE_OFFER, HT_SAVE_RESTORE_RUN_FIRST, HT_SAVE_RESTORING, HT_SAVE_RESTORED, HT_SAVE_RESTORE_FAILED,
    /* MH XX copied after the install (hf_xx_came), and More's reinstall */
    HT_HOME_XX_CAME, HT_HOME_XX_HINT, HT_BTN_REINSTALL, HT_REINSTALL_ASK,
    /* the launcher's own update: offered with the game up to date, and said after the restart */
    HT_HOME_APP_NEW, HT_HOME_APP_HINT, HT_APP_NOW,
    /* HOME refused while an update works */
    HT_HOME_LATER,
    HT_COUNT
} HfText;

/* ---- the title's SMDH ---- */

#define HF_SMDH_SIZE 0x36C0u

/* The game's SMDH (HF_SMDH_SIZE bytes) with these ASCII names in every language, no region lock and the two icons as
 * the SMDH stores them (RGB565 in tiles: 24x24 = 1152 bytes, 48x48 = 4608), as core/install/title/smdh.py title_smdh.
 * -1 when the game's is no SMDH or a name is too long or not ASCII. */
int hf_smdh_make(const uint8_t *game_smdh, const char *short_name, const char *long_name, const char *publisher,
                 const uint8_t *icon24, const uint8_t *icon48, uint8_t out[HF_SMDH_SIZE]);

/* The text in this language; never NULL (a bad id gives ""). ASCII only. */
const char *hf_text(HfLang lang, HfText id);
/* The 3DS system language code (CFG_Language: 1 = English .. 5 = Spanish in libctru's order, JP = 0) as ours. */
HfLang hf_lang_from_system(int cfg_language);

#endif
