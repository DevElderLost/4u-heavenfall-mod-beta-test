/* The launcher app's portable logic; see launcher.h. */
#include "launcher.h"

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#include "json.h"
#include "release.h"

/* ---- version ---- */

int hf_preferred_dump_region(int installed_region, int cfg_region) {
    if (installed_region == 0 || installed_region == 1) return installed_region;
    if (cfg_region == 1) return 1;
    if (cfg_region == 2 || cfg_region == 3) return 0;
    return -1;
}

int hf_tmd_version(const char *text, uint16_t *out) {
    uint32_t parts[HF_VERSION_PARTS];
    int count, i;
    uint32_t major, minor = 0, micro = 0;
    if (!text || hf_version_parse(text, parts, &count) || count < 1 || count > 3) return -1;
    major = parts[0];
    if (count > 1) minor = parts[1];
    if (count > 2) micro = parts[2];
    for (i = 0; i < count; i++)
        if (parts[i] > 63) return -1;
    if (major > 63 || minor > 63 || micro > 15 || (!major && !minor && !micro)) return -1;
    if (out) *out = (uint16_t)(major << 10 | minor << 4 | micro);
    return 0;
}

void hf_tmd_version_text(uint16_t tmd, char *out, size_t cap) {
    snprintf(out, cap, "%u.%u.%u", (unsigned)(tmd >> 10), (unsigned)(tmd >> 4 & 63), (unsigned)(tmd & 15));
}

/* ---- installed record ---- */

/* "" or 64 lowercase hex digits. */
static int hf_game_hash_ok(const char *s) {
    size_t i;
    if (!*s) return 1;
    for (i = 0; i < 64; i++)
        if (!((s[i] >= '0' && s[i] <= '9') || (s[i] >= 'a' && s[i] <= 'f'))) return 0;
    return s[64] == 0;
}

int hf_installed_format(const HfInstalled *in, const char *region, char *out, size_t cap) {
    int n;
    if (strchr(in->version, '"') || strchr(in->version, '\\') || strlen(in->version) >= sizeof in->version ||
        !hf_game_hash_ok(in->game) || !hf_game_hash_ok(in->xx_dump) ||
        (in->save_restore[0] && !hf_save_stamp_ok(in->save_restore)))
        return -1;
    n = snprintf(out, cap,
                 "{\"version\": \"%s\", \"tmd\": %u, \"region\": \"%s\", \"xx\": %s, \"xx_no_room\": %s, "
                 "\"save_pending\": %s, \"layout\": %d, \"game\": \"%s\", \"game_complete\": %s, "
                 "\"xx_dump\": \"%s\", \"save_restore\": \"%s\", \"complete\": %s}\n",
                 in->version, in->tmd, region, in->xx ? "true" : "false", in->xx_no_room ? "true" : "false",
                 in->save_pending ? "true" : "false", in->layout ? in->layout : 2, in->game,
                 in->game_complete ? "true" : "false", in->xx_dump, in->save_restore, in->complete ? "true" : "false");
    return n < 0 || (size_t)n >= cap ? -1 : n;
}

/* A JSON true or false into *out; -1 for anything else. */
static int json_bool(const char *json, const JsonTok *t, int *out) {
    if (t->type != JT_PRIM) return -1;
    if (t->end - t->start == 4 && !strncmp(json + t->start, "true", 4)) *out = 1;
    else if (t->end - t->start == 5 && !strncmp(json + t->start, "false", 5)) *out = 0;
    else return -1;
    return 0;
}

int hf_installed_parse(const char *json, size_t len, HfInstalled *out) {
    JsonTok toks[48];
    uint64_t tmd;
    int n = json_parse(json, len, toks, 48), v, t, c, x, r, s, ly, g, gc, xd, sr;
    uint64_t layout;
    char game[80], xx_dump[80], restore[32];      /* json_string wants room past the text */
    memset(out, 0, sizeof *out);
    if (n < 1 || toks[0].type != JT_OBJECT) return -1;
    v = json_find(json, toks, 0, "version");
    t = json_find(json, toks, 0, "tmd");
    c = json_find(json, toks, 0, "complete");
    x = json_find(json, toks, 0, "xx");
    r = json_find(json, toks, 0, "xx_no_room");
    s = json_find(json, toks, 0, "save_pending");
    ly = json_find(json, toks, 0, "layout");
    g = json_find(json, toks, 0, "game");
    gc = json_find(json, toks, 0, "game_complete");
    xd = json_find(json, toks, 0, "xx_dump");
    sr = json_find(json, toks, 0, "save_restore");
    if (sr >= 0 && (json_string(json, &toks[sr], restore, sizeof restore) || (restore[0] && !hf_save_stamp_ok(restore))))
        return -1;
    if (v < 0 || t < 0 || c < 0 || json_string(json, &toks[v], out->version, sizeof out->version) ||
        json_uint(json, &toks[t], &tmd) || tmd > 0xFFFF || json_bool(json, &toks[c], &out->complete) ||
        (x >= 0 && json_bool(json, &toks[x], &out->xx)) ||
        (r >= 0 && json_bool(json, &toks[r], &out->xx_no_room)) ||
        (s >= 0 && json_bool(json, &toks[s], &out->save_pending)) ||
        (ly >= 0 && (json_uint(json, &toks[ly], &layout) || layout < 1 || layout > 2)) ||
        (g >= 0 && (json_string(json, &toks[g], game, sizeof game) || !hf_game_hash_ok(game))) ||
        (gc >= 0 && json_bool(json, &toks[gc], &out->game_complete)) ||
        (xd >= 0 && (json_string(json, &toks[xd], xx_dump, sizeof xx_dump) || !hf_game_hash_ok(xx_dump))))
        return -1;
    out->tmd = (unsigned)tmd;
    if (g >= 0) memcpy(out->game, game, sizeof out->game);
    if (xd >= 0) memcpy(out->xx_dump, xx_dump, sizeof out->xx_dump);
    if (sr >= 0) snprintf(out->save_restore, sizeof out->save_restore, "%s", restore);
    out->layout = ly >= 0 ? (int)layout : 1;     /* no field: the old single title, no game data */
    return 0;
}

void hf_hex(const uint8_t hash[32], char out[65]) {
    static const char digits[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 32; i++) {
        out[2 * i] = digits[hash[i] >> 4];
        out[2 * i + 1] = digits[hash[i] & 15];
    }
    out[64] = 0;
}

int hf_save_pending_after(int title_installed, const HfInstalled *prev) {
    return prev ? prev->save_pending != 0 : !title_installed;
}

int hf_title_ours(uint64_t id) {
    uint32_t high = (uint32_t)(id >> 32), low = (uint32_t)id, unique = low >> 8;
    if (high != 0x00040000u && high != 0x0004008Cu && high != 0x0004000Eu) return 0;
    return (low & 0xFFu) == 0 && unique > 0x69690u && unique <= 0x6969Fu;
}

static uint64_t align64(uint64_t n) { return (n + 63) / 64 * 64; }

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint64_t be64(const uint8_t *p) {
    uint64_t v = 0;
    int i;
    for (i = 0; i < 8; i++) v = v << 8 | p[i];
    return v;
}

/* Where a signed block's body starts (its signature type, the signature, padding to 64), 0 when unknown or cut. */
static uint64_t signed_body(const uint8_t *head, size_t len, uint64_t at) {
    uint32_t kind, size;
    if (at + 4 > len) return 0;
    kind = (uint32_t)head[at] << 24 | (uint32_t)head[at + 1] << 16 | (uint32_t)head[at + 2] << 8 | head[at + 3];
    switch (kind) {
    case 0x10000: case 0x10003: size = 0x200; break;    /* RSA-4096 */
    case 0x10001: case 0x10004: size = 0x100; break;    /* RSA-2048 */
    case 0x10002: case 0x10005: size = 0x3C; break;     /* ECDSA */
    default: return 0;
    }
    return at + align64(4 + size);
}

int hf_cia_is_launcher(const uint8_t *head, size_t len) {
    uint64_t ticket_at, tmd_at, ticket_body, tmd_body;
    if (!head || len < 0x20) return 0;
    ticket_at = align64(le32(head)) + align64(le32(head + 8));
    tmd_at = ticket_at + align64(le32(head + 12));
    ticket_body = signed_body(head, len, ticket_at);
    tmd_body = signed_body(head, len, tmd_at);
    if (!ticket_body || !tmd_body || ticket_body + 0x9C + 8 > len || tmd_body + 0x4C + 8 > len) return 0;
    return be64(head + ticket_body + 0x9C) == HF_LAUNCHER_TITLE && be64(head + tmd_body + 0x4C) == HF_LAUNCHER_TITLE;
}

int hf_cia_launcher_version(const uint8_t *head, size_t len, char *out, size_t cap) {
    uint64_t tmd_at, tmd_body;
    if (out && cap) out[0] = 0;
    if (!out || !cap || !hf_cia_is_launcher(head, len)) return 0;
    tmd_at = align64(le32(head)) + align64(le32(head + 8)) + align64(le32(head + 12));
    tmd_body = signed_body(head, len, tmd_at);
    if (!tmd_body || tmd_body + 0x9C + 2 > len) return 0;
    hf_tmd_version_text((uint16_t)(head[tmd_body + 0x9C] << 8 | head[tmd_body + 0x9D]), out, cap);
    return 1;
}

static int starts_nocase(const char *text, const char *prefix) {
    for (; *prefix; text++, prefix++)
        if (tolower((unsigned char)*text) != tolower((unsigned char)*prefix)) return 0;
    return 1;
}

int hf_own_3dsx_ok(const char *path) {
    size_t n = path ? strlen(path) : 0;
    const char *name;
    if (n < 6 || n > 250 || !starts_nocase(path, "sdmc:/") || strstr(path, "..")) return 0;
    if (starts_nocase(path + 6, "Nintendo 3DS/") || starts_nocase(path + 6, "luma/")) return 0;
    name = strrchr(path, '/') + 1;
    return strlen(name) > 5 && starts_nocase(path + n - 5, ".3dsx");
}

int hf_game_stale(int present, const HfInstalled *rec, const char *dump_hash) {
    if (!present || !rec || !rec->game_complete || !rec->game[0]) return 1;
    return dump_hash && *dump_hash && strcmp(rec->game, dump_hash) != 0;
}

int hf_romfs_level3_at(const uint8_t *ivfc, size_t n, uint64_t *at) {
    uint32_t master;
    if (hf_romfs_level3_ok(ivfc, n)) {   /* level 3 from the start: how FS serves archive 0x2345678A (and SelfNCCH) */
        if (at) *at = 0;
        return 0;
    }
    if (!ivfc || n < 12 || memcmp(ivfc, "IVFC", 4)) return -1;
    if (((uint32_t)ivfc[4] | (uint32_t)ivfc[5] << 8 | (uint32_t)ivfc[6] << 16 | (uint32_t)ivfc[7] << 24) != 0x10000u)
        return -1;
    master = (uint32_t)ivfc[8] | (uint32_t)ivfc[9] << 8 | (uint32_t)ivfc[10] << 16 | (uint32_t)ivfc[11] << 24;
    if (master > 0x100000u) return -1;
    if (at) *at = ((uint64_t)0x60 + master + 0xFFF) & ~(uint64_t)0xFFF;
    return 0;
}

int hf_romfs_level3_ok(const uint8_t *h, size_t n) {
    return h && n >= 4 && h[0] == 0x28 && !h[1] && !h[2] && !h[3];
}

/* ---- log ---- */

unsigned hf_rate_x10(uint64_t bytes, uint64_t ms) {
    if (!ms) return 0;
    return (unsigned)(bytes * 10000 / 1048576 / ms);
}

static void emit(const HfLog *log, uint64_t now_ms, const char *text) {
    char line[640];
    uint64_t t = now_ms >= log->start_ms ? now_ms - log->start_ms : 0;
    snprintf(line, sizeof line, "[%5u.%03u] %s", (unsigned)(t / 1000), (unsigned)(t % 1000), text);
    if (log->sink) log->sink(log->ctx, line);
}

void hf_log(const HfLog *log, uint64_t now_ms, const char *fmt, ...) {
    char text[560];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(text, sizeof text, fmt, ap);
    va_end(ap);
    emit(log, now_ms, text);
}

void hf_log_phase(const HfLog *log, uint64_t now_ms, const char *phase, uint64_t began_ms, uint64_t bytes) {
    char text[300];
    uint64_t ms = now_ms >= began_ms ? now_ms - began_ms : 0;
    unsigned rate = hf_rate_x10(bytes, ms);
    /* the name cut so the time and rate always fit: snprintf's count is the next write's offset */
    int n = snprintf(text, sizeof text, "%.200s: %lu ms", phase, (unsigned long)ms);
    if (n > 0 && (size_t)n < sizeof text && bytes && rate)
        snprintf(text + n, sizeof text - (size_t)n, ", %lu MB, %u.%u MB/s", (unsigned long)(bytes / 1048576), rate / 10,
                 rate % 10);
    emit(log, now_ms, text);
}

/* ---- paths ---- */

#define ROOT "sdmc:/3ds/heavenfall"

/* A refused slug or a path cut by `cap` leaves `out` empty: a caller that logs it never prints unset memory, and a cut
 * path is never used. */
static int refuse(char *out, size_t cap) {
    if (out && cap) out[0] = 0;
    return -1;
}

static int bad_slug(const char *slug) { return !slug || !*slug || strchr(slug, '/') || strstr(slug, ".."); }

static int path(char *out, size_t cap, const char *fmt, const char *slug, const char *tail) {
    int n;
    if (bad_slug(slug)) return refuse(out, cap);
    n = snprintf(out, cap, fmt, slug, tail);
    return n < 0 || (size_t)n >= cap ? refuse(out, cap) : 0;
}

int hf_path_dir(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s%s", slug, ""); }
int hf_path_installed(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s/%s", slug, "installed.json"); }
int hf_path_log(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s/%s", slug, "launcher.log"); }
int hf_path_test_release(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s/%s", slug, "test_release"); }
int hf_path_friends_dump(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s/%s", slug, "friends_dump"); }
int hf_path_resume(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s/%s", slug, "resume.json"); }
int hf_path_timings(const char *slug, char *out, size_t cap) { return path(out, cap, ROOT "/%s/%s", slug, "timings.json"); }

int hf_save_stamp(int year, int month, int day, int hour, int minute, int second, char out[18]) {
    if (year < 2000 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31 || hour < 0 || hour > 23 ||
        minute < 0 || minute > 59 || second < 0 || second > 60) {
        out[0] = 0;
        return -1;
    }
    snprintf(out, 18, "%04d-%02d-%02d_%02d%02d%02d", year, month, day, hour, minute, second);
    return 0;
}

int hf_save_stamp_ok(const char *s) {
    static const char form[] = "0000-00-00_000000";
    size_t i;
    if (!s) return 0;
    for (i = 0; form[i]; i++)
        if (form[i] == '0' ? !(s[i] >= '0' && s[i] <= '9') : s[i] != form[i]) return 0;
    return s[i] == 0;
}

int hf_path_save_at(const char *slug, int which, const char *stamp, char *out, size_t cap) {
    int n;
    if (bad_slug(slug) || !hf_save_stamp_ok(stamp)) return refuse(out, cap);
    n = snprintf(out, cap, ROOT "/%s/saves/%s/%s", slug, stamp, which == HF_SAVE_ORIGINAL ? "original" : "heavenfall");
    return n < 0 || (size_t)n >= cap ? refuse(out, cap) : 0;
}

int hf_path_save_raw(const char *slug, const char *stamp, char *out, size_t cap) {
    int n;
    if (bad_slug(slug) || !hf_save_stamp_ok(stamp)) return refuse(out, cap);
    n = snprintf(out, cap, ROOT "/%s/saves/%s/heavenfall.sav", slug, stamp);
    return n < 0 || (size_t)n >= cap ? refuse(out, cap) : 0;
}

int hf_path_save_backup(const char *slug, int which, int year, int month, int day, int hour, int minute, int second,
                        char *out, size_t cap) {
    char stamp[18];
    if (hf_save_stamp(year, month, day, hour, minute, second, stamp)) return refuse(out, cap);
    return hf_path_save_at(slug, which, stamp, out, cap);
}

/* 1 when `s` starts with `n` hex digits (either case). */
static int hex_run(const char *s, size_t n) {
    size_t i;
    for (i = 0; i < n; i++)
        if (!isxdigit((unsigned char)s[i])) return 0;
    return 1;
}

int hf_save_raw_path(const char *ctr_root, uint64_t title_id, char *out, size_t cap) {
    static const char top[] = "/Nintendo 3DS/";
    const size_t t = sizeof top - 1;
    int n;
    if (!ctr_root || (uint32_t)(title_id >> 32) != 0x00040000u || !hf_title_ours(title_id)) return refuse(out, cap);
    /* "/Nintendo 3DS/" + 32 hex + "/" + 32 hex, nothing more (FS's answer; anything else is not trusted) */
    if (strncmp(ctr_root, top, t) || !hex_run(ctr_root + t, 32) || ctr_root[t + 32] != '/' ||
        !hex_run(ctr_root + t + 33, 32) || ctr_root[t + 65] != 0)
        return refuse(out, cap);
    n = snprintf(out, cap, "%s/title/00040000/%08lx/data/00000001.sav", ctr_root, (unsigned long)(uint32_t)title_id);
    return n < 0 || (size_t)n >= cap ? refuse(out, cap) : 0;
}

/* ---- texts ---- */

static const char *const TEXT[HT_COUNT][2] = {
    [HT_TITLE] = {"Heavenfall Launcher", "Heavenfall Launcher"},
    [HT_EDITION] = {"Edition", "Edición"},
    [HT_REGION] = {"Game region", "Región del juego"},
    [HT_INSTALLED] = {"Installed version", "Versión instalada"},
    [HT_LATEST] = {"Latest version", "Versión más reciente"},
    [HT_DUMP] = {"Game dump", "Volcado del juego"},
    [HT_LUMA] = {"Luma3DS", "Luma3DS"},
    [HT_FREE] = {"Free on the SD card", "Libre en la SD"},
    [HT_NONE] = {"none", "ninguna"},
    [HT_YES] = {"yes", "sí"},
    [HT_NO] = {"no", "no"},
    [HT_NOT_FOUND] = {"not found", "no encontrado"},
    [HT_UNKNOWN] = {"unknown", "desconocida"},
    [HT_CHECKING] = {"Checking...", "Comprobando..."},
    [HT_BTN_UPDATE] = {"Update", "Actualizar"},
    [HT_BTN_PLAY] = {"Play", "Jugar a"},
    [HT_BTN_PLAY_ORIGINAL] = {"Play the original MH4U", "Jugar al MH4U original"},
    [HT_BTN_CHECKS] = {"Checks", "Comprobaciones"},
    [HT_BTN_ONLINE] = {"Online play", "Juego en línea"},
    [HT_BTN_EXIT] = {"Exit", "Salir"},
    [HT_CANCEL_HINT] = {"B: cancel. Do not turn the console off.", "B: cancelar. No apagues la consola."},
    [HT_NO_SLEEP] = {"The console will not sleep meanwhile.", "La consola no entrará en reposo mientras tanto."},
    [HT_UPDATED] = {"Done: the mod is up to date.", "Listo: el mod está actualizado."},
    [HT_UP_TO_DATE] = {"Already up to date.", "Ya está actualizado."},
    [HT_CANCELLED] = {"Cancelled. Nothing was installed.", "Cancelado. No se ha instalado nada."},
    [HT_FAILED] = {"Failed", "Ha fallado"},
    [HT_NOTHING_INSTALLED] = {"Nothing was installed: your current title is untouched.",
                              "No se ha instalado nada: tu título actual sigue igual."},
    [HT_NO_DUMP] = {"No decrypted MH4U dump on the SD card. Make one with GodMode9 (it goes in gm9/out).",
                    "No hay ningún volcado descifrado de MH4U en la SD. Créalo con GodMode9 (va en gm9/out)."},
    [HT_NO_SET] = {"This version has no patch for your game's region.",
                   "Esta versión no tiene parche para la región de tu juego."},
    [HT_NEEDS_APP] = {"This version needs a newer launcher.", "Esta versión necesita un launcher más nuevo."},
    [HT_NO_NET] = {"No internet connection.", "No hay conexión a internet."},
    [HT_NO_RELEASE] = {"No version has been published yet.", "Todavía no se ha publicado ninguna versión."},
    [HT_APP_UPDATED] = {"The launcher was updated: open it again.", "El launcher se ha actualizado: vuelve a abrirlo."},
    [HT_NO_ROOM] = {"Not enough free space on the SD card.", "No hay espacio suficiente en la SD."},
    [HT_SAVE_OFFER] = {"Copy your MH4U save to this title? It replaces this title's save. Both are backed up first.",
                       "¿Copiar tu partida de MH4U a este título? Sustituye la de este título. Antes se hace una copia "
                       "de seguridad de las dos."},
    [HT_SAVE_NEED_RUN] = {"Start the title once so it makes its save, then copy it.",
                          "Abre el título una vez para que cree su partida y después cópiala."},
    [HT_SAVE_DONE] = {"Save copied. The backups are on the SD card.",
                      "Partida copiada. Las copias de seguridad están en la SD."},
    [HT_SAVE_NONE] = {"No MH4U save found (cartridge or digital).",
                      "No se ha encontrado ninguna partida de MH4U (cartucho o digital)."},
    [HT_ONLINE_NEEDED] = {"Online play needs Nimbus (Pretendo).", "Para jugar en línea hace falta Nimbus (Pretendo)."},
    [HT_ONLINE_INSTALLED] = {"Online patch: installed", "Parche en línea: instalado"},
    [HT_ONLINE_INSTALLABLE] = {"Online patch: ready to install", "Parche en línea: se puede instalar"},
    [HT_ONLINE_UNSUPPORTED] = {"Online patch: not supported on this console",
                               "Parche en línea: no compatible con esta consola"},
    [HT_REBOOT] = {"Restart the console for it to take effect.", "Reinicia la consola para que surta efecto."},
    [HT_NOT_THERE] = {"MH4U not found (cartridge or digital).", "No se encuentra MH4U (cartucho o digital)."},
    [HT_NOT_INSTALLED] = {"Not installed yet: press Update first.", "Todavía no está instalado: pulsa Actualizar."},
    [HT_PROBE] = {"Test build: log in sdmc:/3ds/heavenfall", "Versión de prueba: registro en sdmc:/3ds/heavenfall"},
    [HT_PRESS_A] = {"A: yes", "A: sí"},
    [HT_PRESS_B] = {"B: no", "B: no"},
    [HT_ROUTE_SLOT] = {"The release's data does not match this game: checking it here (slower).",
                       "Los datos de la versión no encajan con este juego: se comprueba aquí (más lento)."},
    [HT_ROUTE_AM] = {"The system refused this way of installing: trying another.",
                     "El sistema ha rechazado este método de instalación: se prueba otro."},
    [HT_ROUTE_RETRY] = {"Trying another way to install. Nothing has been installed yet.",
                        "Se prueba otra forma de instalar. Todavía no se ha instalado nada."},
    [HT_PHASE_RELEASE] = {"Looking for the latest version", "Buscando la versión más reciente"},
    [HT_PHASE_APP_DOWNLOAD] = {"Downloading the new launcher", "Descargando el launcher nuevo"},
    [HT_PHASE_SET_DOWNLOAD] = {"Downloading the patch", "Descargando el parche"},
    [HT_PHASE_PROBE_DOWNLOAD] = {"Test download", "Descarga de prueba"},
    [HT_PHASE_OPEN] = {"Reading the patch and your game", "Leyendo el parche y tu juego"},
    [HT_PHASE_OPEN_SIZING] = {"Reading the patch and your game (sizing)", "Leyendo el parche y tu juego (midiendo)"},
    [HT_PHASE_PREPARE] = {"Preparing the title", "Preparando el título"},
    [HT_PHASE_HASH] = {"Checking the title (1 of 2)", "Comprobando el título (1 de 2)"},
    [HT_PHASE_WRITE] = {"Installing the title", "Instalando el título"},
    [HT_PHASE_WRITE_2] = {"Installing the title (2 of 2)", "Instalando el título (2 de 2)"},
    [HT_PHASE_AM] = {"The system is checking the title", "El sistema está comprobando el título"},
    [HT_WORKING] = {"Working: this can take some minutes.", "Trabajando: puede tardar unos minutos."},
    [HT_WHY_MEMORY] = {"not enough memory", "no hay memoria suficiente"},
    [HT_WHY_DUMP] = {"your game dump does not match the patch", "tu volcado del juego no coincide con el parche"},
    [HT_WHY_SD] = {"the SD card could not be read or written", "no se ha podido leer o escribir en la SD"},
    [HT_WHY_SET] = {"the patch file is damaged", "el archivo del parche está dañado"},
    [HT_WHY_AM] = {"the system refused the installation", "el sistema ha rechazado la instalación"},
    [HT_WHY_NET] = {"the download failed", "la descarga ha fallado"},
    [HT_WHY_OTHER] = {"unexpected error", "error inesperado"},
    [HT_CODE] = {"code", "código"},
    [HT_LANG_SWITCH] = {"SELECT: Español", "SELECT: English"},
    [HT_ENCRYPTED] = {"encrypted (decrypt it)", "cifrado (descífralo)"},
    [HT_OTHER_REGION] = {"another region", "de otra región"},
    [HT_ONLINE_ASK_INSTALL] = {"Install the online patch?", "¿Instalar el parche en línea?"},
    [HT_ONLINE_ASK_REMOVE] = {"Remove the online patch?", "¿Quitar el parche en línea?"},
    [HT_CHECKS_KEYS] = {"X: copy the MH4U save    A: back", "X: copiar la partida de MH4U    A: volver"},
    [HT_XX] = {"MH XX", "MH XX"},
    [HT_FOUND] = {"found", "encontrado"},
    [HT_XX_OTHER_VERSION] = {"another version (not used)", "otra versión (no se usa)"},
    [HT_XX_OTHER_NOTE] = {"Your MH XX dump is another version than this update's: installing without MH XX.",
                          "Tu volcado de MH XX es de otra versión que la de esta actualización: se instala sin MH XX."},
    [HT_XX_NO_SET_NOTE] = {"This version has no MH XX patch for your region: installing without MH XX.",
                           "Esta versión no tiene parche con MH XX para tu región: se instala sin MH XX."},
    [HT_PHASE_SET_DOWNLOAD_XX] = {"Downloading the patch with MH XX", "Descargando el parche con MH XX"},
    [HT_XX_NO_ROOM_NOTE] = {"MH XX does not fit in this console's memory: installing without MH XX.",
                            "MH XX no cabe en la memoria de esta consola: se instala sin MH XX."},
    [HT_HOME_UP_TO_DATE] = {"Up to date", "Al día"},
    [HT_HOME_NEW_VERSION] = {"A new version is out:", "Hay una versión nueva:"},
    [HT_HOME_NOT_INSTALLED] = {"Not installed yet", "Todavía no está instalado"},
    [HT_HOME_REPAIR] = {"The last install did not finish", "La última instalación no terminó"},
    [HT_HOME_CHECKING] = {"Looking for updates...", "Buscando actualizaciones..."},
    [HT_HOME_CHECK_FAILED] = {"Could not look for updates (no internet?)",
                              "No se han podido buscar actualizaciones (¿sin internet?)"},
    [HT_HOME_NEED_DUMP] = {"Your copy of MH4U is needed first", "Primero hace falta tu copia de MH4U"},
    [HT_HOME_DUMP_ENCRYPTED] = {"Your copy of MH4U is encrypted", "Tu copia de MH4U está cifrada"},
    [HT_HOME_DUMP_OTHER_REGION] = {"Your copy of MH4U is from another region", "Tu copia de MH4U es de otra región"},
    [HT_HOME_SETUP_HINT] = {"Set up shows you how, step by step.", "Configurar te lo explica paso a paso."},
    [HT_HOME_INSTALL_HINT] = {"It takes about {}: keep the console charging.", "Tarda unos {}: deja la consola cargando."},
    [HT_HOME_INSTALLED_LABEL] = {"Installed", "Instalada"},
    [HT_HOME_LATEST_LABEL] = {"Latest", "Más reciente"},
    [HT_NOTES_TITLE] = {"What's new in", "Novedades de la"},
    [HT_NOTES_KEYS] = {"Up/Down: scroll", "Arriba/Abajo: desplazar"},
    [HT_BTN_INSTALL] = {"Install", "Instalar"},
    [HT_BTN_UPDATE_TO] = {"Update to", "Actualizar a la"},
    [HT_BTN_SETUP] = {"Set up", "Configurar"},
    [HT_BTN_MORE] = {"More", "Más"},
    [HT_BTN_INFO] = {"Information", "Información"},
    [HT_BTN_SAVE] = {"Copy my MH4U save", "Copiar mi partida de MH4U"},
    [HT_BTN_LANGUAGE] = {"Español", "English"},
    [HT_BTN_BACK] = {"Back", "Volver"},
    [HT_BTN_PLAY_NOW] = {"Play now", "Jugar ahora"},
    [HT_BTN_SKIP] = {"Skip", "Saltar"},
    [HT_BTN_CHECK_AGAIN] = {"Check again", "Comprobar de nuevo"},
    [HT_BTN_CONTINUE] = {"Continue", "Continuar"},
    [HT_BTN_NOTES] = {"What's new", "Novedades"},
    [HT_STAGE_DOWNLOAD] = {"Downloading", "Descargando"},
    [HT_STAGE_INSTALL] = {"Installing", "Instalando"},
    [HT_STAGE_FINISH] = {"Finishing", "Terminando"},
    [HT_TASK_ETA] = {"About {} left", "Quedan unos {}"},
    [HT_TASK_ETA_UNKNOWN] = {"Working out the time left...", "Calculando el tiempo que falta..."},
    [HT_CANCEL_AGAIN] = {"Press B again to cancel.", "Pulsa B otra vez para cancelar."},
    [HT_CANNOT_CANCEL] = {"This step cannot be cancelled: it ends soon.",
                          "Este paso no se puede cancelar: termina enseguida."},
    [HT_BTN_KEEP_SCREENS] = {"Keep the screens on", "Mantener pantallas encendidas"},
    [HT_BTN_LET_SCREENS] = {"Let the screens turn off", "Dejar que se apaguen"},
    [HT_SCREENS_STAY_ON] = {"The screens stay on until it ends.", "Las pantallas se quedan encendidas hasta el final."},
    [HT_BTN_CANCEL] = {"Cancel", "Cancelar"},
    [HT_BTN_CANCEL_AGAIN] = {"Tap again to cancel", "Toca otra vez para cancelar"},
    [HT_SCREENS_OFF_HINT] = {"The screens turn off to save battery: press any button to see them.",
                             "Las pantallas se apagan para ahorrar batería: pulsa cualquier botón para verlas."},
    [HT_BATTERY_LOW] = {"The battery is low and this takes about {}: connect the charger. Go on anyway?",
                        "Queda poca batería y esto tarda unos {}: conecta el cargador. ¿Seguir igualmente?"},
    [HT_DONE_READY] = {"Done: {} is ready to play.", "Listo: ya puedes jugar a {}."},
    [HT_FAIL_DUMP] = {"Your copy of MH4U does not match this update.",
                      "Tu copia de MH4U no coincide con esta actualización."},
    [HT_FAIL_MEMORY] = {"There was not enough memory.", "No había memoria suficiente."},
    [HT_FAIL_SD] = {"The SD card could not be read or written.", "No se ha podido leer o escribir en la SD."},
    [HT_FAIL_SET] = {"The downloaded patch is damaged.", "El parche descargado está dañado."},
    [HT_FAIL_AM] = {"The system refused the installation.", "El sistema ha rechazado la instalación."},
    [HT_FAIL_OTHER] = {"Something unexpected went wrong.", "Algo inesperado ha fallado."},
    [HT_TODO_ROOM] = {"Free {} on the SD card and try again.", "Libera {} en la SD y vuelve a intentarlo."},
    [HT_TODO_NET] = {"Connect to the internet in System Settings, then try again.",
                     "Conéctate a internet en la Configuración de la consola y vuelve a intentarlo."},
    [HT_TODO_DUMP] = {"Make a new copy with GodMode9: Set up shows you how.",
                      "Haz una copia nueva con GodMode9: Configurar te lo explica."},
    [HT_TODO_RESTART] = {"Restart the console and try again.", "Reinicia la consola y vuelve a intentarlo."},
    [HT_TODO_RETRY] = {"Try again: it is downloaded anew.", "Vuelve a intentarlo: se descargará de nuevo."},
    [HT_SIMPLE_DISPLAY] = {"Simple display", "Pantalla sencilla"},
    [HT_APP_RESTARTING] = {"The launcher was updated: it opens again by itself.",
                           "El launcher se ha actualizado: se vuelve a abrir solo."},
    [HT_APP_REOPEN] = {"The launcher was updated: open it again and it goes on by itself.",
                       "El launcher se ha actualizado: vuelve a abrirlo y seguirá solo."},
    [HT_RESUMING] = {"Going on with the update...", "Siguiendo con la actualización..."},
    [HT_START_EXIT] = {"START: exit", "START: salir"},
    [HT_PHASE_APP_INSTALL] = {"Installing the new launcher", "Instalando el launcher nuevo"},
    [HT_SIMPLE_FOOTER] = {"R at start: full display. START: exit", "R al iniciar: gráficos. START: salir"},
    [HT_DONE_SAVE_HINT] = {"Play once, then open the launcher again to bring your MH4U save.",
                           "Juega una vez y vuelve a abrir el launcher para traer tu partida de MH4U."},
    [HT_GUIDE_DUMP_TITLE] = {"Copy your MH4U with GodMode9", "Copia tu MH4U con GodMode9"},
    [HT_GUIDE_DUMP_WHY] = {"Heavenfall is made from your own game: a copy of it must be on the SD card.",
                           "Heavenfall se crea a partir de tu propio juego: hace falta una copia en la SD."},
    [HT_GUIDE_GM9_START] = {"1. Turn the console off. Hold START and turn it on: GodMode9 opens.",
                            "1. Apaga la consola. Mantén START y enciéndela: se abre GodMode9."},
    [HT_GUIDE_CART] = {"2. A cartridge: open \"[C:] GAMECART\", press A on \"<TitleID>.trim.3ds\" and choose "
                       "\"Copy to 0:/gm9/out\".",
                       "2. Un cartucho: abre \"[C:] GAMECART\", pulsa A en \"<TitleID>.trim.3ds\" y elige "
                       "\"Copy to 0:/gm9/out\"."},
    [HT_GUIDE_DIGITAL] = {"3. A digital copy: press HOME, then \"Title manager\", \"[A:] SD CARD\", the game, "
                          "\"Manage Title...\" and \"Build CIA (standard)\".",
                          "3. Una copia digital: pulsa HOME y luego \"Title manager\", \"[A:] SD CARD\", el juego, "
                          "\"Manage Title...\" y \"Build CIA (standard)\"."},
    [HT_GUIDE_GM9_END] = {"4. The copy goes to gm9/out. Restart the console, open the launcher and press Check again.",
                          "4. La copia va a gm9/out. Reinicia la consola, abre el launcher y pulsa Comprobar de nuevo."},
    [HT_GUIDE_DECRYPT_TITLE] = {"Decrypt your copy of MH4U", "Descifra tu copia de MH4U"},
    [HT_GUIDE_DECRYPT_OPEN] = {"2. Open \"[0:] SDCARD\", then gm9 and out, and press A on your copy.",
                               "2. Abre \"[0:] SDCARD\", luego gm9 y out, y pulsa A en tu copia."},
    [HT_GUIDE_DECRYPT_CHOOSE] = {"3. Choose \"NCSD image options...\" (a .3ds) or \"CIA image options...\" (a .cia), "
                                 "then \"Decrypt file (...)\".",
                                 "3. Elige \"NCSD image options...\" (un .3ds) o \"CIA image options...\" (un .cia) y "
                                 "luego \"Decrypt file (...)\"."},
    [HT_GUIDE_XX_TITLE] = {"Optional: your MH XX", "Opcional: tu MH XX"},
    [HT_GUIDE_XX_WHY] = {"With a copy of MH XX, Heavenfall adds gear looks and rare materials from MH XX. Copy it the "
                         "same way, or skip this step.",
                         "Con una copia de MH XX, Heavenfall añade aspectos de equipo y materiales raros de MH XX. "
                         "Cópiala igual o sáltate este paso."},
    [HT_GUIDE_XX_ENCRYPTED] = {"Your copy of MH XX is encrypted: decrypt it with these steps.",
                               "Tu copia de MH XX está cifrada: descífrala con estos pasos."},
    [HT_GUIDE_INSTALL_TITLE] = {"Ready to install", "Todo listo para instalar"},
    [HT_GUIDE_INSTALL_STEP] = {"The launcher downloads the patch and makes the game from your copy, which stays as it is.",
                               "El launcher descarga el parche y crea el juego a partir de tu copia, que no cambia."},
    [HT_GUIDE_SAVE_TITLE] = {"Bring your MH4U save", "Trae tu partida de MH4U"},
    [HT_GUIDE_SAVE_RUN] = {"1. Start {} once so it makes its save, then come back here.",
                           "1. Abre {} una vez para que cree su partida y vuelve aquí."},
    [HT_GUIDE_SAVE_COPY] = {"2. Press Copy my MH4U save. Both saves are backed up on the SD card first.",
                            "2. Pulsa Copiar mi partida de MH4U. Antes se guarda una copia de las dos en la SD."},
    [HT_GUIDE_DONE_TITLE] = {"All set", "Todo listo"},
    [HT_GUIDE_DONE_STEP] = {"{} is installed: start it here with Play now, or from the HOME Menu.",
                            "{} está instalado: ábrelo aquí con Jugar ahora o desde el menú HOME."},
    [HT_SAVE_BACKING_UP] = {"Backing up both saves to the SD card...",
                            "Haciendo copia de seguridad de las dos partidas en la SD..."},
    [HT_SAVE_COPYING] = {"Copying your MH4U save... Do not turn the console off.",
                         "Copiando tu partida de MH4U... No apagues la consola."},
    [HT_STARTING_GAME] = {"Starting the game...", "Abriendo el juego..."},
    [HT_ONLINE_WORKING] = {"Changing the online patch...", "Cambiando el parche en línea..."},
    [HT_CLOSING] = {"Closing...", "Cerrando..."},
    [HT_LANG_NOW] = {"Language: English", "Idioma: español"},
    [HT_SAVE_BACKUP_FAILED] = {"The saves could not be backed up, so nothing was copied: both are untouched.",
                               "No se han podido copiar las partidas a la SD, así que no se ha copiado nada: "
                               "las dos siguen igual."},
    [HT_SAVE_COPY_FAILED] = {"The save copy failed. Both saves were backed up to the SD card first.",
                             "No se ha podido copiar la partida. Las dos se guardaron antes en la SD."},
    /* the split title: the game data title */
    [HT_HOME_GAME_MISSING] = {"The game data is missing", "Faltan los datos del juego"},
    [HT_HOME_GAME_UPDATE] = {"The game data needs to be installed", "Hay que instalar los datos del juego"},
    [HT_HOME_GAME_HINT] = {"Press Update: it is made from your MH4U copy, once, and takes a while.",
                           "Pulsa Actualizar: se hace con tu copia de MH4U, una sola vez, y tarda un rato."},
    [HT_GAME_DATA] = {"Game data", "Datos del juego"},
    [HT_GAME_VALUE_OK] = {"installed", "instalados"},
    [HT_GAME_VALUE_MISSING] = {"missing", "faltan"},
    [HT_GAME_VALUE_UPDATE] = {"to be installed", "por instalar"},
    [HT_NO_GAME_START] = {"The game data is missing, so the game cannot start. Press Update to install it.",
                          "Faltan los datos del juego, así que no se puede abrir. Pulsa Actualizar para instalarlos."},
    [HT_GAME_NOTE] = {"Installing the game data from your copy: once, until your copy changes.",
                      "Instalando los datos del juego con tu copia: una sola vez, hasta que tu copia cambie."},
    [HT_MOD_NOTE] = {"Installing the mod", "Instalando el mod"},
    [HT_PHASE_GAME_CHECK] = {"Checking the game data", "Comprobando los datos del juego"},
    [HT_PHASE_XX_FILES] = {"Checking your MH XX files", "Comprobando los archivos de tu MH XX"},
    [HT_FAIL_GAME_CHECK] = {"The game data was installed, but the system cannot open it. The game would not start.",
                            "Los datos del juego se instalaron, pero el sistema no puede abrirlos. "
                            "El juego no arrancaría."},
    [HT_XX_FILES_NOTE] = {"Your MH XX is another printing, but its files are the ones needed: it is used.",
                          "Tu MH XX es otra edición, pero sus archivos son los necesarios: se usa."},
    [HT_ONLINE_DAMAGED] = {"Online patch: its file is damaged (Remove fixes it)",
                           "Parche en línea: su archivo está dañado (Quitar lo arregla)"},
    [HT_OLD_REMOVED] = {"The old version was removed to make room for the new one: update again to install it.",
                        "La versión anterior se quitó para dejar sitio a la nueva: actualiza otra vez para instalarla."},
    [HT_FAIL_SAVE_BACKUP] = {"Your save could not be copied to the SD card first, so nothing was changed.",
                             "No se pudo copiar antes tu partida a la SD, así que no se ha cambiado nada."},
    /* the save across an update (launcher.md, "The save across an update") */
    [HT_SAVE_RESTORE_OFFER] = {"Put your Heavenfall save back now? The update had to remove the title, and the system "
                               "took its save with it. What the title holds now is backed up first.",
                               "¿Devolver ahora tu partida de Heavenfall? La actualización tuvo que quitar el título y el "
                               "sistema se llevó su partida. Antes se guarda una copia de lo que tiene ahora."},
    [HT_SAVE_RESTORE_RUN_FIRST] = {"Your save is safe on the SD card. Start the game once, close it, and open the "
                                   "launcher again: it puts your save back.",
                                   "Tu partida está a salvo en la SD. Abre el juego una vez, ciérralo y vuelve a abrir "
                                   "el launcher: él devuelve tu partida."},
    [HT_SAVE_RESTORING] = {"Putting your save back... Do not turn the console off.",
                           "Devolviendo tu partida... No apagues la consola."},
    [HT_SAVE_RESTORED] = {"Your save is back.", "Tu partida ha vuelto."},
    [HT_SAVE_RESTORE_FAILED] = {"Your save could not be put back. It is still safe on the SD card: the launcher offers "
                                "it again each time it opens.",
                                "No se pudo devolver tu partida. Sigue a salvo en la SD: el launcher te lo vuelve a "
                                "ofrecer cada vez que lo abras."},
    [HT_HOME_XX_CAME] = {"MH XX found", "MH XX encontrado"},
    [HT_HOME_XX_HINT] = {"Press Update to add its gear looks and rare materials.",
                         "Pulsa Actualizar para añadir sus aspectos de equipo y materiales raros."},
    [HT_BTN_REINSTALL] = {"Reinstall", "Reinstalar"},
    [HT_REINSTALL_ASK] = {"Install the latest version again? Your save is backed up first and comes back after.",
                          "¿Instalar otra vez la última versión? Tu partida se copia antes y vuelve después."},
    [HT_HOME_APP_NEW] = {"A new launcher is out", "Hay un launcher nuevo"},
    [HT_HOME_APP_HINT] = {"Press Update: it takes a few seconds.", "Pulsa Actualizar: tarda unos segundos."},
    [HT_APP_NOW] = {"The launcher was updated: version {}.", "El launcher se ha actualizado: versión {}."},
    [HT_HOME_LATER] = {"HOME is off while this works: it comes back at the end.",
                       "HOME no funciona mientras esto trabaja: vuelve al terminar."},
};

const char *hf_text(HfLang lang, HfText id) {
    const char *t;
    if ((unsigned)id >= HT_COUNT || (unsigned)lang > 1) return "";
    t = TEXT[id][lang];
    return t ? t : "";
}

HfLang hf_lang_from_system(int cfg_language) { return cfg_language == 5 ? HF_LANG_ES : HF_LANG_EN; }

/* The letters past ASCII the texts use, by code point, and their code page 437 byte (the console font's). */
static const struct { uint32_t cp; unsigned char b; } CP437[] = {
    {0xE1, 0xA0}, {0xE9, 0x82}, {0xED, 0xA1}, {0xF3, 0xA2}, {0xFA, 0xA3}, {0xF1, 0xA4}, {0xD1, 0xA5},
    {0xBF, 0xA8}, {0xA1, 0xAD}, {0xC9, 0x90}, {0xFC, 0x81}, {0xDC, 0x9A},
};

size_t hf_cp437(const char *utf8, char *out, size_t cap) {
    const unsigned char *s = (const unsigned char *)utf8;
    size_t n = 0;
    if (!cap) return 0;
    while (s && *s && n + 1 < cap) {
        uint32_t cp = *s++;
        int more = cp >= 0xF0 ? 3 : cp >= 0xE0 ? 2 : cp >= 0xC0 ? 1 : 0;
        unsigned char b = '?';
        size_t k;
        if (more) cp &= 0x3Fu >> more;
        for (; more && (*s & 0xC0) == 0x80; more--) cp = cp << 6 | (*s++ & 0x3Fu);
        if (cp >= 0x20 && cp < 0x7F) b = (unsigned char)cp;
        else if (cp == '\n') b = '\n';
        for (k = 0; k < sizeof CP437 / sizeof CP437[0]; k++)
            if (CP437[k].cp == cp) b = CP437[k].b;
        out[n++] = (char)b;
    }
    out[n] = 0;
    return n;
}

/* ---- the title's SMDH ---- */

#define SMDH_TITLES 0x8u
#define SMDH_LANGUAGES 16u
#define SMDH_TITLE_SIZE 0x200u
#define SMDH_REGION_LOCKOUT 0x2018u
#define SMDH_ICON24 0x2040u
#define SMDH_ICON48 0x24C0u

static int put_name(uint8_t *at, const char *name, size_t size) {   /* UTF-16 LE, a zero unit left */
    size_t n = strlen(name), i;
    if (n * 2 + 2 > size) return -1;
    memset(at, 0, size);
    for (i = 0; i < n; i++) {
        if ((unsigned char)name[i] > 0x7E || (unsigned char)name[i] < 0x20) return -1;
        at[i * 2] = (uint8_t)name[i];
    }
    return 0;
}

int hf_smdh_make(const uint8_t *game_smdh, const char *short_name, const char *long_name, const char *publisher,
                 const uint8_t *icon24, const uint8_t *icon48, uint8_t out[HF_SMDH_SIZE]) {
    unsigned lang;
    if (!game_smdh || memcmp(game_smdh, "SMDH", 4) || !icon24 || !icon48) return -1;
    memcpy(out, game_smdh, HF_SMDH_SIZE);
    for (lang = 0; lang < SMDH_LANGUAGES; lang++) {
        uint8_t *base = out + SMDH_TITLES + lang * SMDH_TITLE_SIZE;
        if (put_name(base, short_name, 0x80) || put_name(base + 0x80, long_name, 0x100) ||
            put_name(base + 0x180, publisher, 0x80))
            return -1;
    }
    out[SMDH_REGION_LOCKOUT] = 0xFF;          /* no region lock: 0x7FFFFFFF, little endian */
    out[SMDH_REGION_LOCKOUT + 1] = 0xFF;
    out[SMDH_REGION_LOCKOUT + 2] = 0xFF;
    out[SMDH_REGION_LOCKOUT + 3] = 0x7F;
    memcpy(out + SMDH_ICON24, icon24, 24 * 24 * 2);
    memcpy(out + SMDH_ICON48, icon48, 48 * 48 * 2);
    return 0;
}
