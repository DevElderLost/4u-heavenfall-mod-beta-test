/* See ctr_friends.h. Only the console's side is here: Luma3DS' state, reading the running module, the SD card's files.
 * The patch itself (patterns, stub, IPS merge and strip) is the portable friends_patch.c the PC tests check. */
#include "ctr_friends.h"

#include <3ds.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "friends_patch.h"
#include "hf_editions.h"

#define IPS_PATH "sdmc:/luma/sysmodules/0004013000003202.ips"
#define IPS_TMP "sdmc:/luma/sysmodules/0004013000003202.ips.hftmp"
#define FOREIGN_BPS "sdmc:/luma/sysmodules/0004013000003202.bps"
#define FOREIGN_UPS "sdmc:/luma/sysmodules/0004013000003202.ups"
#define STATE_DIR "sdmc:/3ds/heavenfall/friends"
#define STATE_OURS STATE_DIR "/ours.bin"   /* our records as merged */
#define STATE_BASE STATE_DIR "/base.ips"   /* the module's .ips before ours (Nimbus'); absent when there was none */
#define LUMA_MIN SYSTEM_VERSION(13, 0, 0)  /* the first Luma3DS that applies /luma/sysmodules/<id>.ips */
#define LUMA_EXT_MODULES 1                 /* config bit: "Enable loading external FIRMs and modules" */
#define IPS_MAX (1024 * 1024)
#define MAX_CODE (16 * 1024 * 1024)

enum { ST_NOT_NEEDED = 0, ST_INSTALLED = 1, ST_INSTALLABLE = 2, ST_UNSUPPORTED = 3, ST_DAMAGED = 4 };

/* ---- Luma3DS -------------------------------------------------------------------------------------------------- */

/* Luma3DS' svcMapProcessMemoryEx (0xA0): maps `size` bytes of `src` at `src_va` into `dst` at `dst_va`. r5 is the
 * flags of 13.5 (0: shared), ignored before. Luma3DS' svc handler takes it from any process. */
static Result luma_map(Handle dst, u32 dst_va, Handle src, u32 src_va, u32 size) {
    register u32 r0 __asm__("r0") = dst;
    register u32 r1 __asm__("r1") = dst_va;
    register u32 r2 __asm__("r2") = src;
    register u32 r3 __asm__("r3") = src_va;
    register u32 r4 __asm__("r4") = size;
    register u32 r5 __asm__("r5") = 0;
    __asm__ volatile("svc 0xA0" : "+r"(r0), "+r"(r1), "+r"(r2), "+r"(r3), "+r"(r4), "+r"(r5) : : "r12", "memory");
    return (Result)r0;
}

/* svcUnmapProcessMemoryEx (0xA1). */
static Result luma_unmap(Handle process, u32 va, u32 size) {
    register u32 r0 __asm__("r0") = process;
    register u32 r1 __asm__("r1") = va;
    register u32 r2 __asm__("r2") = size;
    __asm__ volatile("svc 0xA1" : "+r"(r0), "+r"(r1), "+r"(r2) : : "r3", "r12", "memory");
    return (Result)r0;
}

/* 1 on Luma3DS (its svcGetSystemInfo(0x20000) answers 1), 0 elsewhere; *emulator when Citra/Azahar say so. */
static int on_luma(int *emulator) {
    s64 out = 0;
    Result r = svcGetSystemInfo(&out, 0x20000, 0);
    *emulator = r != 1 && R_SUCCEEDED(r) && out == 1;
    return r == 1;
}

static int exists(const char *path) {
    struct stat st;
    return stat(path, &st) == 0;
}

/* -1 to go on, or the status that stops here. */
static int gate(char *msg, size_t n) {
    s64 version = 0, config = 0;
    int emulator;
    if (!on_luma(&emulator)) {
        snprintf(msg, n, "%s", emulator ? "Emulator: no patch needed" : "No Luma3DS: no patch possible");
        return ST_NOT_NEEDED;
    }
    svcGetSystemInfo(&version, 0x10000, 0);
    if ((u32)version < LUMA_MIN) {
        snprintf(msg, n, "Luma3DS 13.0 or newer needed");
        return ST_UNSUPPORTED;
    }
    svcGetSystemInfo(&config, 0x10000, 3);
    if (!((config >> LUMA_EXT_MODULES) & 1)) {
        snprintf(msg, n, "Luma: turn on external FIRMs and modules");
        return ST_NOT_NEEDED;
    }
    if (exists(FOREIGN_BPS) || exists(FOREIGN_UPS)) {
        snprintf(msg, n, "Another friends patch (.bps/.ups) is there");
        return ST_UNSUPPORTED;
    }
    return -1;
}

/* ---- the running module ------------------------------------------------------------------------------------- */

typedef struct {
    uint8_t *code;
    size_t len;
    FrdpSizes sizes;
    u64 title;
    u32 text_addr, ro_addr, rw_addr;
} Module;

static u32 free_va(u32 size) {
    u32 va;
    for (va = 0x0F000000; va >= 0x08000000; va -= 0x00100000) {
        MemInfo mi;
        PageInfo pi;
        if (R_SUCCEEDED(svcQueryMemory(&mi, &pi, va)) && mi.state == MEMSTATE_FREE &&
            va + size <= mi.base_addr + mi.size)
            return va;
    }
    return 0;
}

static s64 info(Handle h, u32 type) {
    s64 v = 0;
    return R_SUCCEEDED(svcGetProcessInfo(&v, h, type)) ? v : 0;
}

/* The friends process' code set (text, rodata, data and bss pages, as mapped), copied out; Luma3DS only. */
static int read_module(Module *m, char *msg, size_t n) {
    u32 pids[128], va, total, text, ro, rw;
    s32 count = 0, i;
    Handle h = 0;
    Result rc;
    int emulator;
    memset(m, 0, sizeof *m);
    if (!on_luma(&emulator)) {
        snprintf(msg, n, "No Luma3DS: the module cannot be read");
        return -1;
    }
    if (R_FAILED(svcGetProcessList(&count, pids, 128)))
        count = 0;
    for (i = 0; i < count && !h; i++) {
        Handle p;
        s64 title = 0;
        if (R_FAILED(svcOpenProcess(&p, pids[i])))
            continue;
        if (R_SUCCEEDED(svcGetProcessInfo(&title, p, 0x10001)) && ((u64)title & ~0xF0000000ULL) == FRDP_TITLE) {
            h = p;
            m->title = (u64)title;
        } else {
            svcCloseHandle(p);
        }
    }
    if (!h) {
        snprintf(msg, n, "The friends module is not running");
        return -1;
    }
    text = (u32)info(h, 0x10002);
    ro = (u32)info(h, 0x10003);
    rw = (u32)info(h, 0x10004);
    m->text_addr = (u32)info(h, 0x10005);
    m->ro_addr = (u32)info(h, 0x10006);
    m->rw_addr = (u32)info(h, 0x10007);
    total = text + ro + rw;
    if (!text || m->text_addr != FRDP_LOAD || m->ro_addr != m->text_addr + text || m->rw_addr != m->ro_addr + ro ||
        total > MAX_CODE) {
        svcCloseHandle(h);
        snprintf(msg, n, "Friends module layout not as expected");
        return -1;
    }
    va = free_va(total);
    m->code = va ? (uint8_t *)malloc(total) : NULL;
    rc = m->code ? luma_map(CUR_PROCESS_HANDLE, va, h, m->text_addr, total) : -1;
    if (R_SUCCEEDED(rc)) {
        memcpy(m->code, (const void *)va, total);
        luma_unmap(CUR_PROCESS_HANDLE, va, total);
    }
    svcCloseHandle(h);
    if (R_FAILED(rc)) {
        free(m->code);
        m->code = NULL;
        snprintf(msg, n, "Friends module not readable (%08lX)", (unsigned long)rc);
        return -1;
    }
    m->len = total;
    m->sizes.text = text;
    m->sizes.ro = ro;
    m->sizes.data = rw;
    return 0;
}

/* The module's title version on NAND (AM), 0 when unknown. */
static unsigned module_version(u64 title) {
    AM_TitleEntry entry;
    u64 id = title ? title : FRDP_TITLE;
    unsigned version = 0;
    if (R_SUCCEEDED(amInit())) {
        if (R_SUCCEEDED(AM_GetTitleInfo(MEDIATYPE_NAND, 1, &id, &entry)))
            version = entry.version;
        amExit();
    }
    return version;
}

/* ---- the SD card's files ------------------------------------------------------------------------------------ */

static uint8_t *read_file(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    uint8_t *data = NULL;
    long size;
    *len = 0;
    if (!f)
        return NULL;
    if (fseek(f, 0, SEEK_END) == 0 && (size = ftell(f)) >= 0 && size <= IPS_MAX && fseek(f, 0, SEEK_SET) == 0) {
        data = (uint8_t *)malloc((size_t)size + 1);
        if (data && fread(data, 1, (size_t)size, f) == (size_t)size) {
            *len = (size_t)size;
        } else {
            free(data);
            data = NULL;
        }
    }
    fclose(f);
    return data;
}

static int write_file(const char *path, const uint8_t *data, size_t len) {
    FILE *f = fopen(path, "wb");
    int bad;
    if (!f)
        return -1;
    bad = fwrite(data, 1, len, f) != len;
    bad |= fclose(f) != 0;
    return bad ? -1 : 0;
}

/* The module's .ips is only ever written whole and read back, the file before put back when it does not read back
 * (frdp_file_put); a replacement cut short is finished with a whole file or dropped (frdp_file_recover): Luma3DS stops
 * the console at every start on a .ips it refuses. */
static void recover(void) {
    FrdpFiles f;
    frdp_files_stdio(&f);
    frdp_file_recover(&f, IPS_PATH, IPS_TMP);
}

static int put_ips(const uint8_t *data, size_t len, const uint8_t *old, size_t old_len) {
    FrdpFiles f;
    frdp_files_stdio(&f);
    return frdp_file_put(&f, IPS_PATH, IPS_TMP, data, len, old, old_len);
}

/* 1 when the module's .ips is one Luma3DS refuses by its form (cut, damaged): the console stops at start with it. */
static int ips_damaged(void) {
    size_t len = 0, eof_at;
    uint8_t *ips = read_file(IPS_PATH, &len);
    int bad = ips && frdp_ips_check(ips, len, FRDP_IPS_ANY, NULL, 0, &eof_at) != FRDP_OK;
    free(ips);
    return bad;
}

/* When gate() stops the checks (Luma3DS' option off, no Luma3DS, an old one, a foreign patch), a damaged .ips or one
 * holding our patch still gets Remove: the way back is Luma3DS' option off, Remove, the option on. */
static int on_card(int st, char *msg, size_t n) {
    char why[96];
    if (ips_damaged()) {
        snprintf(msg, n, "The friends .ips is damaged: Remove gives back a good one");
        return ST_DAMAGED;
    }
    if (exists(IPS_PATH) && exists(STATE_OURS)) {
        snprintf(why, sizeof why, "%s", msg);
        snprintf(msg, n, "Installed (%s)", why);
        return ST_INSTALLED;
    }
    return st;
}

/* ---- what is there ------------------------------------------------------------------------------------------ */

typedef struct {
    Module m;
    FrdpPatch p;
    uint8_t recs[FRDP_RECORDS_MAX];
    size_t recs_len;
    uint8_t *ips;      /* the module's .ips now, or NULL */
    size_t ips_len;
    uint8_t *base;     /* what ours go into: the .ips without any records of ours (NULL: none) */
    size_t base_len;
} Seen;

static void forget(Seen *s) {
    free(s->m.code);
    free(s->ips);
    free(s->base);
    memset(s, 0, sizeof *s);
}

static int strip_into(const uint8_t *ips, size_t len, const uint8_t *recs, size_t recs_len, uint8_t **out,
                      size_t *out_len) {
    *out = (uint8_t *)malloc(len + 1);
    if (!*out || frdp_ips_strip(ips, len, recs, recs_len, *out, len, out_len)) {
        free(*out);
        *out = NULL;
        return -1;
    }
    return 0;
}

static int look(Seen *s, char *msg, size_t n) {
    FrdpMap map[FRDP_MAX_MAP];
    size_t count, eof_at, old_len = 0;
    uint8_t *old;
    int rc, nimbus;
    char why[160];
    memset(s, 0, sizeof *s);
    recover();
    if ((rc = gate(msg, n)) >= 0)
        return on_card(rc, msg, n);
    if (ips_damaged()) {   /* Luma3DS refuses it: only Remove, which gives back the file before ours or none */
        snprintf(msg, n, "The friends .ips is damaged: Remove gives back a good one");
        return ST_DAMAGED;
    }
    if (read_module(&s->m, msg, n))
        return on_card(ST_UNSUPPORTED, msg, n);
    count = frdp_map_editions(HF_EDITIONS, HF_EDITION_COUNT, map, FRDP_MAX_MAP);
    if (frdp_locate(s->m.code, s->m.len, &s->m.sizes, map, count, &s->p, why, sizeof why) ||
        !(s->recs_len = frdp_records(&s->p, s->recs, sizeof s->recs))) {
        snprintf(msg, n, "Friends module not recognized: %s", why);
        return ST_UNSUPPORTED;
    }
    s->ips = read_file(IPS_PATH, &s->ips_len);
    if (s->ips && frdp_ips_check(s->ips, s->ips_len, (uint32_t)s->m.len, NULL, 0, &eof_at)) {
        snprintf(msg, n, "The friends .ips file is damaged");
        return ST_UNSUPPORTED;
    }
    if (s->ips && !strip_into(s->ips, s->ips_len, s->recs, s->recs_len, &s->base, &s->base_len)) {
        nimbus = s->base_len > 8;
        snprintf(msg, n, "%s%s", s->p.active_same ? "Running" : "Installed: restart the console",
                 nimbus ? "" : "; Nimbus missing");
        return ST_INSTALLED;
    }
    if (s->ips) {  /* an older patch of ours in it comes out first */
        old = read_file(STATE_OURS, &old_len);
        if (!old || strip_into(s->ips, s->ips_len, old, old_len, &s->base, &s->base_len)) {
            s->base = (uint8_t *)malloc(s->ips_len);
            if (!s->base) {
                free(old);
                snprintf(msg, n, "Out of memory");
                return ST_UNSUPPORTED;
            }
            memcpy(s->base, s->ips, s->ips_len);
            s->base_len = s->ips_len;
        }
        free(old);
        rc = frdp_ips_check(s->base, s->base_len, (uint32_t)s->m.len, s->recs, s->recs_len, &eof_at);
        if (rc == FRDP_E_OVERLAP) {
            snprintf(msg, n, "The friends .ips writes where ours would");
            return ST_UNSUPPORTED;
        }
        if (rc) {
            snprintf(msg, n, "The friends .ips file is damaged");
            return ST_UNSUPPORTED;
        }
    }
    nimbus = s->base && s->base_len > 8;
    snprintf(msg, n, "Can be installed%s", nimbus ? "" : "; Nimbus missing");
    return ST_INSTALLABLE;
}

/* ---- the API ------------------------------------------------------------------------------------------------ */

int hf_friends_status(char *msg, size_t n) {
    Seen s;
    int st = look(&s, msg, n);
    forget(&s);
    return st;
}

int hf_friends_install(char *msg, size_t n) {
    Seen s;
    uint8_t *merged;
    size_t merged_len = 0;
    int rc, st = look(&s, msg, n);
    if (st != ST_INSTALLABLE) {
        forget(&s);
        return st;
    }
    merged = (uint8_t *)malloc(s.base_len + s.recs_len + 16);
    if (!merged || frdp_ips_merge(s.base, s.base_len, s.recs, s.recs_len, (uint32_t)s.m.len, merged,
                                  s.base_len + s.recs_len + 16, &merged_len)) {
        free(merged);
        forget(&s);
        snprintf(msg, n, "The patch could not be merged");
        return ST_UNSUPPORTED;
    }
    mkdir("sdmc:/3ds", 0777);
    mkdir("sdmc:/3ds/heavenfall", 0777);
    mkdir(STATE_DIR, 0777);
    mkdir("sdmc:/luma", 0777);
    mkdir("sdmc:/luma/sysmodules", 0777);
    /* the state first, so a removal always finds what to take out and what to give back */
    if (write_file(STATE_OURS, s.recs, s.recs_len) ||
        (s.base ? write_file(STATE_BASE, s.base, s.base_len) : (remove(STATE_BASE), 0))) {
        rc = FRDP_E_IO;
    } else {   /* read back; the file before is put back when it does not read back */
        rc = put_ips(merged, merged_len, s.ips, s.ips_len);
    }
    st = rc == FRDP_OK ? ST_INSTALLED : rc == FRDP_E_IO ? ST_INSTALLABLE : ST_UNSUPPORTED;
    snprintf(msg, n, "%s", rc == FRDP_OK ? "Installed: restart the console"
                           : rc == FRDP_E_IO ? "The SD card could not be written"
                                             : "The .ips did not read back: the file before it was put back");
    free(merged);
    forget(&s);
    return st;
}

int hf_friends_remove(char *msg, size_t n) {
    uint8_t *ips, *ours, *base, *out = NULL;
    size_t ips_len, ours_len, base_len, out_len = 0;
    int bad = 0, action;
    Seen s;
    memset(&s, 0, sizeof s);
    recover();
    ips = read_file(IPS_PATH, &ips_len);
    ours = read_file(STATE_OURS, &ours_len);
    base = read_file(STATE_BASE, &base_len);
    if (!ours && ips) {  /* no state: the records the running module gives now */
        char why[160];
        look(&s, why, sizeof why);
        if (s.recs_len && (ours = (uint8_t *)malloc(s.recs_len))) {
            memcpy(ours, s.recs, s.recs_len);
            ours_len = s.recs_len;
        }
        forget(&s);
    }
    /* our records out (Nimbus' file back byte for byte), a file Luma3DS would refuse replaced by the one before ours or
     * deleted (friends_patch.h, frdp_remove_plan); a write that does not read back leaves no file (the console boots) */
    action = frdp_remove_plan(ips, ips_len, ours, ours_len, base, base_len, &out, &out_len);
    if (action == FRDP_DELETE)
        bad = remove(IPS_PATH) != 0;
    else if (action == FRDP_WRITE)
        bad = put_ips(out, out_len, NULL, 0) != FRDP_OK;
    if (!bad) {
        remove(STATE_OURS);
        remove(STATE_BASE);
    }
    snprintf(msg, n, "%s", bad ? "The SD card could not be written" : action != FRDP_KEEP ? "Removed: restart the console"
                                                                         : "Not installed: nothing to remove");
    free(ips);
    free(ours);
    free(base);
    free(out);
    return bad ? ST_UNSUPPORTED : ST_INSTALLABLE;
}

int hf_friends_dump(const char *dir, char *msg, size_t n) {
    Module m;
    char path[300], why[160] = "", text[1024];
    FrdpMap map[FRDP_MAX_MAP];
    FrdpPatch p;
    s64 version = 0, config = 0;
    uint8_t *ips;
    size_t ips_len, count;
    int rc, len;
    if (read_module(&m, msg, n))
        return -1;
    snprintf(path, sizeof path, "%s/friends_code.bin", dir);
    if (write_file(path, m.code, m.len)) {
        free(m.code);
        snprintf(msg, n, "Could not write %s", path);
        return -1;
    }
    count = frdp_map_editions(HF_EDITIONS, HF_EDITION_COUNT, map, FRDP_MAX_MAP);
    rc = frdp_locate(m.code, m.len, &m.sizes, map, count, &p, why, sizeof why);
    svcGetSystemInfo(&version, 0x10000, 0);
    svcGetSystemInfo(&config, 0x10000, 3);
    ips = read_file(IPS_PATH, &ips_len);
    len = snprintf(text, sizeof text,
                   "title %016llX version %u\ntext 0x%lX at 0x%lX\nrodata 0x%lX at 0x%lX\ndata+bss 0x%lX at 0x%lX\n"
                   "luma %08lX config %08lX\nlocate %d: %s\nips %s (%u bytes)\nbps %d ups %d\n",
                   (unsigned long long)m.title, module_version(m.title), (unsigned long)m.sizes.text,
                   (unsigned long)m.text_addr, (unsigned long)m.sizes.ro, (unsigned long)m.ro_addr,
                   (unsigned long)m.sizes.data, (unsigned long)m.rw_addr, (unsigned long)(u32)version,
                   (unsigned long)(u32)config, rc, why, ips ? "present" : "absent", (unsigned)ips_len,
                   exists(FOREIGN_BPS), exists(FOREIGN_UPS));
    snprintf(path, sizeof path, "%s/friends_info.txt", dir);
    rc = write_file(path, (const uint8_t *)text, len > 0 && len < (int)sizeof text ? (size_t)len : strlen(text));
    if (ips) {
        snprintf(path, sizeof path, "%s/friends_current.ips", dir);
        rc |= write_file(path, ips, ips_len);
    }
    if (rc)
        snprintf(msg, n, "Friends module: dump incomplete");
    else
        snprintf(msg, n, "Friends module: 0x%lX bytes dumped", (unsigned long)m.len);
    free(ips);
    free(m.code);
    return rc ? -1 : 0;
}
