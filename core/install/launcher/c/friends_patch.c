/* See friends_patch.h. The patterns and why they hold: */
#include "friends_patch.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PAGE 0x1000u
#define STUB_HEAD 0x2Cu         /* the stub's code; its table follows */
#define STUB_DISPLACED 0x26u    /* where the stub runs the two instructions the BL replaced */
#define HOOK_AT 0x36u           /* in the wrapper */
#define GUARD 0x10u             /* kept clear after the last nonzero byte of the code section */
#define CHAIN_WINDOW 0x80u      /* how far before the "titleid" reference the getter's call may be */
#define CALLEE_WINDOW 0x20u     /* how far into the getter / the thunk their call may be */

static uint16_t h16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t w32(const uint8_t *p) { return (uint32_t)h16(p) | (uint32_t)h16(p + 2) << 16; }
static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void put32(uint8_t *p, uint32_t v) { put16(p, (uint16_t)v); put16(p + 2, (uint16_t)(v >> 16)); }
static uint32_t align_up(uint32_t v, uint32_t a) { return (v + a - 1) & ~(a - 1); }

static void say(char *msg, size_t n, const char *text) {
    if (msg && n)
        snprintf(msg, n, "%s", text);
}

/* ---- Thumb and ARM calls ---------------------------------------------------------------------------------------- */

/* A Thumb BL (to Thumb) or BLX (to ARM) pair at `off`: 1 for BL, 2 for BLX, 0 for neither; *to is the target. */
static int thumb_call(const uint8_t *code, uint32_t off, uint32_t end, uint32_t *to) {
    uint16_t a, b;
    int32_t hi, t;
    int kind;
    if (off + 4 > end)
        return 0;
    a = h16(code + off);
    b = h16(code + off + 2);
    if ((a & 0xF800) != 0xF000)
        return 0;
    if ((b & 0xF800) == 0xF800)
        kind = 1;
    else if ((b & 0xF801) == 0xE800)
        kind = 2;
    else
        return 0;
    hi = a & 0x7FF;
    if (hi & 0x400)
        hi -= 0x800;
    t = (int32_t)off + 4 + hi * 4096 + (int32_t)(b & 0x7FF) * 2;
    if (kind == 2)
        t &= ~3;
    if (t < 0)
        return 0;
    *to = (uint32_t)t;
    return kind;
}

static int bl_to(const uint8_t *code, uint32_t off, uint32_t end, uint32_t target) {
    uint32_t to;
    return thumb_call(code, off, end, &to) == 1 && to == target;
}

static int bl_within(const uint8_t *code, uint32_t from, uint32_t span, uint32_t end, uint32_t target) {
    uint32_t off;
    for (off = from; off < from + span && off + 4 <= end; off += 2)
        if (bl_to(code, off, end, target))
            return 1;
    return 0;
}

/* BL/BLX calls to the Thumb function at `target` in [0, end): Thumb BL pairs and ARM BLX immediates. */
static uint32_t count_calls(const uint8_t *code, uint32_t end, uint32_t target) {
    uint32_t off, count = 0;
    for (off = 0; off + 4 <= end; off += 2) {
        if (bl_to(code, off, end, target))
            count++;
        if (!(off & 3)) {
            uint32_t w = w32(code + off);
            if ((w & 0xFE000000u) == 0xFA000000u) {
                int32_t imm = (int32_t)(w & 0xFFFFFF);
                if (imm & 0x800000)
                    imm -= 0x1000000;
                if ((int64_t)off + 8 + (int64_t)imm * 4 + ((w >> 24) & 1) * 2 == (int64_t)target)
                    count++;
            }
        }
    }
    return count;
}

static void encode_bl(uint32_t at, uint32_t to, uint8_t out[4]) {
    int32_t d = (int32_t)to - (int32_t)(at + 4);
    put16(out, (uint16_t)(0xF000 | (((uint32_t)d >> 12) & 0x7FF)));
    put16(out + 2, (uint16_t)(0xF800 | (((uint32_t)d >> 1) & 0x7FF)));
}

/* ---- the GetProgramLaunchInfo wrapper --------------------------------------------------------------------------- */

#define P_BLX 0x10000u   /* a BLX to ARM code (two halfwords) */
#define P_BL 0x20000u    /* a BL to Thumb code (two halfwords) */
#define P_LIT 0x30000u   /* ldr r1, [pc, #imm]: the command id 0x82F */

/* fs:USER GetProgramLaunchInfo as Nintendo's IPC client code makes it (v19456 at 0x10FD90):
 * wrapper(Handle *session, ProgramInfo *out, u32 process_id) -> Result. The command header comes from a helper
 * (id, 1 normal word, 0 translate words); on success the 16-byte ProgramInfo (program id, media type) is copied from
 * the command buffer to `out` with stmia r4!, and the result is returned from cmdbuf[1]. */
static const uint32_t WRAPPER[] = {
    0xB57C, 0x460C, 0x4605, 0x4616,         /* push {r2-r6,lr}; mov r4,r1; mov r5,r0; mov r6,r2 */
    P_BLX,                                  /* blx getThreadCommandBuffer's TLS read */
    0x3080, 0x9001, 0x2000, 0x4603, 0x9000, /* adds r0,#0x80; str r0,[sp,#4]; movs r0,#0; mov r3,r0; str r0,[sp] */
    P_LIT, 0x2201, 0xA801,                  /* ldr r1,=0x82F; movs r2,#1; add r0,sp,#4 */
    P_BL,                                   /* bl makeHeader */
    0x9801, 0x6046, 0x6828,                 /* ldr r0,[sp,#4]; str r6,[r0,#4]; ldr r0,[r5] */
    P_BLX,                                  /* blx svcSendSyncRequest */
    0x2800, 0xDB05,                         /* cmp r0,#0; blt exit */
    0x9B01, 0x3308, 0xCB0F, 0xC40F,         /* ldr r3,[sp,#4]; adds r3,#8; ldmia r3,{r0-r3}; stmia r4!,{r0-r3} */
    0x9801, 0x6840,                         /* the hook: ldr r0,[sp,#4]; ldr r0,[r0,#4] */
    0xBD7C,                                 /* exit: pop {r2-r6,pc} */
};
#define WRAPPER_LEN 0x3Cu
#define HOOK_ORIG0 0x9801
#define HOOK_ORIG1 0x6840

static const uint8_t TLS_READ[8] = {0x70, 0x0F, 0x1D, 0xEE, 0x1E, 0xFF, 0x2F, 0xE1};  /* mrc p15,0,r0,c13,c0,3; bx lr */
static const uint8_t SEND_SYNC[8] = {0x32, 0x00, 0x00, 0xEF, 0x1E, 0xFF, 0x2F, 0xE1};  /* svc 0x32; bx lr */

static const uint16_t STUB[STUB_HEAD / 2] = {
    0xB430,          /* push {r4,r5} */
    0x4620, 0x3810,  /* mov r0,r4; subs r0,#16: the ProgramInfo just copied */
    0x6804, 0x6845,  /* ldr r4,[r0]; ldr r5,[r0,#4]: its program id */
    0xA308,          /* adr r3, table */
    0xCB06,          /* loop: ldmia r3!,{r1,r2} (from) */
    0x2A00, 0xD008,  /* cmp r2,#0; beq done (the table's end) */
    0x42A1, 0xD104,  /* cmp r1,r4; bne next */
    0x42AA, 0xD102,  /* cmp r2,r5; bne next */
    0xCB06, 0xC006,  /* ldmia r3!,{r1,r2} (to); stmia r0!,{r1,r2} */
    0xE001,          /* b done */
    0x3308, 0xE7F3,  /* next: adds r3,#8; b loop */
    0xBC30,          /* done: pop {r4,r5} */
    HOOK_ORIG0, HOOK_ORIG1,  /* the two instructions the BL replaced */
    0x4770,          /* bx lr */
};

/* Whether `code` at S holds a stub of ours; its length (with the table) in *len. */
static int our_stub_at(const uint8_t *code, uint32_t s, uint32_t page_end, uint32_t *len) {
    uint32_t i, at;
    if ((s & 3) || s + STUB_HEAD + 8 > page_end)
        return 0;
    for (i = 0; i < STUB_HEAD / 2; i++)
        if (h16(code + s + 2 * i) != STUB[i])
            return 0;
    for (at = s + STUB_HEAD; at + 8 <= page_end; at += 16) {
        if (w32(code + at + 4) == 0) {
            *len = at + 8 - s;
            return 1;
        }
        if (at + 16 > page_end)
            break;
    }
    return 0;
}

typedef struct {
    uint32_t at, mem_stub, mem_stub_len;
    int active;
} Wrapper;

/* The wrapper's pattern at `w` (its hook may hold a BL to a stub of ours). */
static int wrapper_at(const uint8_t *code, uint32_t w, uint32_t text_end, uint32_t page_end, Wrapper *found) {
    uint32_t off = w, i, to;
    if (w + WRAPPER_LEN + 4 > text_end)
        return 0;
    for (i = 0; i < sizeof WRAPPER / sizeof WRAPPER[0]; i++) {
        uint32_t want = WRAPPER[i];
        if (want == P_BLX) {
            const uint8_t *body = (i == 4) ? TLS_READ : SEND_SYNC;
            if (thumb_call(code, off, text_end, &to) != 2 || to + 8 > text_end || memcmp(code + to, body, 8))
                return 0;
            off += 4;
        } else if (want == P_BL) {
            if (thumb_call(code, off, text_end, &to) != 1 || to >= text_end)
                return 0;
            off += 4;
        } else if (want == P_LIT) {
            uint16_t ins = h16(code + off);
            uint32_t lit = ((off + 4) & ~3u) + (uint32_t)(ins & 0xFF) * 4;
            if ((ins & 0xFF00) != 0x4900 || lit + 4 > text_end || w32(code + lit) != 0x82F)
                return 0;
            off += 2;
        } else if (off == w + HOOK_AT && want == HOOK_ORIG0 && h16(code + off) != HOOK_ORIG0) {
            uint32_t len;
            if (thumb_call(code, off, text_end, &to) != 1 || to >= page_end || !our_stub_at(code, to, page_end, &len))
                return 0;
            found->active = 1;
            found->mem_stub = to;
            found->mem_stub_len = len;
            off += 4;
            i++;
        } else {
            if (h16(code + off) != want)
                return 0;
            off += 2;
        }
    }
    found->at = w;
    return 1;
}

/* ---- the NASC request builder ----------------------------------------------------------------------------------- */

static int find_chain(const uint8_t *code, uint32_t text_end, uint32_t strings_end, uint32_t wrapper, FrdpPatch *out,
                      char *msg, size_t n) {
    static const char FIELD[] = "titleid";
    uint32_t s, off, refs = 0, ref = 0, pairs = 0;
    for (s = 0; s + sizeof FIELD <= strings_end; s += 4) {
        if (memcmp(code + s, FIELD, sizeof FIELD))
            continue;
        for (off = 0; off + 2 <= text_end; off += 2) {
            uint16_t ins = h16(code + off);
            if ((ins & 0xF800) == 0xA000 && ((off + 4) & ~3u) + (uint32_t)(ins & 0xFF) * 4 == s) {
                refs++;
                ref = off;
            }
        }
    }
    if (refs != 1) {
        snprintf(msg, n, "the NASC field \"titleid\" has %u references in the code (one expected)", (unsigned)refs);
        return FRDP_E_CHAIN;
    }
    for (off = ref >= CHAIN_WINDOW ? ref - CHAIN_WINDOW : 0; off < ref; off += 2) {
        uint32_t getter, thunk, at;
        if (thumb_call(code, off, text_end, &getter) != 1 || getter >= text_end)
            continue;
        for (at = getter; at < getter + CALLEE_WINDOW && at + 4 <= text_end; at += 2) {
            if (thumb_call(code, at, text_end, &thunk) != 1 || thunk >= text_end)
                continue;
            if (bl_within(code, thunk, CALLEE_WINDOW, text_end, wrapper)) {
                if (!pairs || out->getter != getter || out->thunk != thunk)
                    pairs++;
                out->getter = getter;
                out->thunk = thunk;
            }
        }
    }
    if (pairs != 1) {
        snprintf(msg, n, "%u title id getters before the NASC field reach the wrapper (one expected)", (unsigned)pairs);
        return FRDP_E_CHAIN;
    }
    out->builder_ref = ref;
    return FRDP_OK;
}

/* ---- frdp_locate ------------------------------------------------------------------------------------------------ */

static int map_ok(const FrdpMap *map, size_t count) {
    size_t i, j;
    if (!map || !count || count > FRDP_MAX_MAP)
        return 0;
    for (i = 0; i < count; i++) {
        if (!(map[i].from >> 32) || !(map[i].to >> 32) || map[i].from == map[i].to)
            return 0;
        for (j = 0; j < i; j++)
            if (map[j].from == map[i].from)
                return 0;
    }
    return 1;
}

int frdp_locate(const uint8_t *code, size_t len, const FrdpSizes *sizes, const FrdpMap *map, size_t map_count,
                FrdpPatch *out, char *msg, size_t n) {
    uint32_t text_end, page_end, ro_end, w, s, start, stub_len, i;
    Wrapper found, one;
    int count = 0, rc, exact;
    char why[160];
    if (!msg || !n) {
        msg = why;
        n = sizeof why;
    }
    memset(out, 0, sizeof *out);
    if (!code || !sizes || !sizes->text || !map_ok(map, map_count)) {
        say(msg, n, "bad arguments (sizes or title map)");
        return FRDP_E_ARGS;
    }
    page_end = align_up(sizes->text, PAGE);
    ro_end = page_end + align_up(sizes->ro, PAGE);
    if (len < (size_t)ro_end + sizes->data || len > 0x1000000) {
        say(msg, n, "the code is shorter than its sizes say");
        return FRDP_E_ARGS;
    }
    text_end = sizes->text;
    exact = (sizes->text & (PAGE - 1)) != 0;

    memset(&found, 0, sizeof found);
    for (w = 0; w + WRAPPER_LEN <= text_end; w += 2) {
        if (h16(code + w) != WRAPPER[0])
            continue;
        memset(&one, 0, sizeof one);
        if (wrapper_at(code, w, text_end, page_end, &one)) {
            found = one;
            count++;
        }
    }
    if (count != 1) {
        snprintf(msg, n, "%d GetProgramLaunchInfo wrappers match (one expected)", count);
        return FRDP_E_WRAPPER;
    }
    out->wrapper = found.at;
    out->hook = found.at + HOOK_AT;
    out->active = found.active;
    out->callers = count_calls(code, text_end, found.at);

    rc = find_chain(code, text_end, ro_end, found.at, out, msg, n);
    if (rc)
        return rc;
    out->thunk_callers = count_calls(code, text_end, out->thunk);

    /* free room: past the last nonzero byte of the code section's last page (a stub of ours counts as zero) */
    for (s = page_end; s > 0; s--) {
        uint32_t b = s - 1;
        int ours = found.active && b >= found.mem_stub && b < found.mem_stub + found.mem_stub_len;
        if (code[b] && !ours)
            break;
    }
    if (exact && s > text_end) {
        say(msg, n, "the code section's padding is not empty");
        return FRDP_E_ROOM;
    }
    start = s + GUARD;
    if (exact && start < text_end)
        start = text_end;
    start = align_up(start, 16);
    stub_len = STUB_HEAD + 16 * (uint32_t)map_count + 8;
    if (start + stub_len > page_end) {
        snprintf(msg, n, "no room for the stub (%u bytes free at 0x%X)",
                 (unsigned)(page_end > start ? page_end - start : 0), (unsigned)(FRDP_LOAD + start));
        return FRDP_E_ROOM;
    }
    out->stub = start;
    out->stub_len = stub_len;
    for (i = 0; i < STUB_HEAD / 2; i++)
        put16(out->stub_bytes + 2 * i, STUB[i]);
    for (i = 0; i < map_count; i++) {
        uint8_t *e = out->stub_bytes + STUB_HEAD + 16 * i;
        put32(e, (uint32_t)map[i].from);
        put32(e + 4, (uint32_t)(map[i].from >> 32));
        put32(e + 8, (uint32_t)map[i].to);
        put32(e + 12, (uint32_t)(map[i].to >> 32));
    }
    memset(out->stub_bytes + STUB_HEAD + 16 * map_count, 0, 8);
    put16(out->hook_orig, HOOK_ORIG0);
    put16(out->hook_orig + 2, HOOK_ORIG1);
    if (out->stub - out->hook > 0x3FFFF0u) {
        say(msg, n, "the stub is out of a BL's reach");
        return FRDP_E_ROOM;
    }
    encode_bl(out->hook, out->stub, out->hook_bytes);
    if (found.active)
        out->active_same = found.mem_stub == out->stub && found.mem_stub_len == stub_len &&
                           !memcmp(code + out->stub, out->stub_bytes, stub_len) &&
                           !memcmp(code + out->hook, out->hook_bytes, 4);
    snprintf(msg, n,
             "wrapper 0x%X (%u calls), getter 0x%X, stub 0x%X+0x%X%s", (unsigned)(FRDP_LOAD + out->wrapper),
             (unsigned)out->callers, (unsigned)(FRDP_LOAD + out->getter), (unsigned)(FRDP_LOAD + out->stub),
             (unsigned)stub_len, out->active ? (out->active_same ? ", running" : ", an older one running") : "");
    return FRDP_OK;
}

/* ---- the map ---------------------------------------------------------------------------------------------------- */

static int parse_id(const char *hex, uint64_t *out) {
    uint64_t v = 0;
    int i;
    if (!hex)
        return 0;
    for (i = 0; i < 16; i++) {
        char c = hex[i];
        int d = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10
                : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
        if (d < 0)
            return 0;
        v = v << 4 | (uint64_t)d;
    }
    if (hex[16])
        return 0;
    *out = v;
    return 1;
}

size_t frdp_map_editions(const HfEdition *editions, size_t count, FrdpMap *map, size_t cap) {
    size_t i, used = 0;
    for (i = 0; i < count; i++) {
        if (used + 2 > cap || !parse_id(editions[i].title_eur, &map[used].from) ||
            !parse_id(editions[i].title_usa, &map[used + 1].from))
            return 0;
        map[used].to = FRDP_MH4U_EUR;
        map[used + 1].to = FRDP_MH4U_USA;
        used += 2;
    }
    return used;
}

/* ---- IPS -------------------------------------------------------------------------------------------------------- */

#define IPS_EOF 0x454F46u
#define MAX_AVOID 16

typedef struct {
    uint32_t from, to;
} Range;

static size_t put_record(uint8_t *out, size_t cap, size_t at, uint32_t offset, const uint8_t *data, uint32_t size) {
    if (at + 5 + size > cap)
        return 0;
    out[at] = (uint8_t)(offset >> 16);
    out[at + 1] = (uint8_t)(offset >> 8);
    out[at + 2] = (uint8_t)offset;
    out[at + 3] = (uint8_t)(size >> 8);
    out[at + 4] = (uint8_t)size;
    memcpy(out + at + 5, data, size);
    return at + 5 + size;
}

size_t frdp_records(const FrdpPatch *p, uint8_t *out, size_t cap) {
    size_t at;
    if (!p->stub_len || p->stub == IPS_EOF || p->hook == IPS_EOF)
        return 0;
    at = put_record(out, cap, 0, p->stub, p->stub_bytes, p->stub_len);
    if (at)
        at = put_record(out, cap, at, p->hook, p->hook_bytes, 4);
    return at;
}

/* Walks IPS records from `at` to "EOF" (or, with `bare`, to the end of the bytes). Fills ranges; *eof_at; *starts
 * notes whether a record starts at `start_at`. */
static int walk(const uint8_t *ips, size_t len, size_t at, int bare, uint32_t limit, Range *ranges, size_t max,
                size_t *count, size_t *eof_at, size_t start_at, int *starts) {
    size_t used = 0;
    for (;;) {
        uint32_t offset, size;
        if (bare && at == len)
            break;
        if (at + 3 > len)
            return FRDP_E_IPS;
        offset = (uint32_t)ips[at] << 16 | (uint32_t)ips[at + 1] << 8 | ips[at + 2];
        if (offset == IPS_EOF) {
            if (bare)
                return FRDP_E_IPS;
            if (eof_at)
                *eof_at = at;
            break;
        }
        if (starts && at == start_at)
            *starts = 1;
        if (at + 5 > len)
            return FRDP_E_IPS;
        size = (uint32_t)ips[at + 3] << 8 | ips[at + 4];
        at += 5;
        if (!size) {
            if (at + 3 > len)
                return FRDP_E_IPS;
            size = (uint32_t)ips[at] << 8 | ips[at + 1];
            at += 3;
        } else {
            if (at + size > len)
                return FRDP_E_IPS;
            at += size;
        }
        if ((uint64_t)offset + size > limit)
            return FRDP_E_IPS;
        if (ranges && size) {
            if (used == max)
                return FRDP_E_SPACE;
            ranges[used].from = offset;
            ranges[used].to = offset + size;
            used++;
        }
    }
    if (!bare) {
        size_t tail = len - (at + 3);
        if (tail != 0 && tail != 3)
            return FRDP_E_IPS;
        if (tail == 3 && ((uint32_t)ips[at + 3] << 16 | (uint32_t)ips[at + 4] << 8 | ips[at + 5]) > limit)
            return FRDP_E_IPS;
    }
    if (count)
        *count = used;
    return FRDP_OK;
}

static int overlaps(uint32_t from, uint32_t to, const Range *r, size_t n) {
    size_t i;
    for (i = 0; i < n; i++)
        if (from < r[i].to && r[i].from < to)
            return 1;
    return 0;
}

int frdp_ips_check(const uint8_t *ips, size_t len, uint32_t limit, const uint8_t *avoid_records, size_t avoid_len,
                   size_t *eof_at) {
    Range avoid[MAX_AVOID];
    size_t n_avoid = 0, at = 5;
    int rc;
    if (avoid_len) {
        rc = walk(avoid_records, avoid_len, 0, 1, limit, avoid, MAX_AVOID, &n_avoid, NULL, 0, NULL);
        if (rc)
            return rc;
    }
    if (len < 8 || memcmp(ips, "PATCH", 5))
        return FRDP_E_IPS;
    rc = walk(ips, len, 5, 0, limit, NULL, 0, NULL, eof_at, 0, NULL);
    if (rc || !n_avoid)
        return rc;
    for (;;) {  /* the ranges again, against ours */
        uint32_t offset, size;
        offset = (uint32_t)ips[at] << 16 | (uint32_t)ips[at + 1] << 8 | ips[at + 2];
        if (offset == IPS_EOF)
            return FRDP_OK;
        size = (uint32_t)ips[at + 3] << 8 | ips[at + 4];
        if (size) {
            at += 5 + size;
        } else {
            size = (uint32_t)ips[at + 5] << 8 | ips[at + 6];
            at += 8;
        }
        if (size && overlaps(offset, offset + size, avoid, n_avoid))
            return FRDP_E_OVERLAP;
    }
}

int frdp_ips_merge(const uint8_t *base, size_t base_len, const uint8_t *records, size_t records_len, uint32_t limit,
                   uint8_t *out, size_t cap, size_t *out_len) {
    size_t eof_at = 5;
    int rc;
    if (!records_len || walk(records, records_len, 0, 1, limit, NULL, 0, NULL, NULL, 0, NULL))
        return FRDP_E_ARGS;
    if (base && base_len) {
        rc = frdp_ips_check(base, base_len, limit, records, records_len, &eof_at);
        if (rc)
            return rc;
    } else {
        base = (const uint8_t *)"PATCHEOF";
        base_len = 8;
    }
    if (base_len + records_len > cap)
        return FRDP_E_SPACE;
    memcpy(out, base, eof_at);
    memcpy(out + eof_at, records, records_len);
    memcpy(out + eof_at + records_len, base + eof_at, base_len - eof_at);
    *out_len = base_len + records_len;
    return FRDP_OK;
}

int frdp_ips_strip(const uint8_t *ips, size_t len, const uint8_t *records, size_t records_len, uint8_t *out,
                   size_t cap, size_t *out_len) {
    size_t eof_at = 0, at;
    int starts = 0, rc;
    if (!records_len)
        return FRDP_E_ARGS;
    if (len < 8 || memcmp(ips, "PATCH", 5))
        return FRDP_E_IPS;
    rc = walk(ips, len, 5, 0, 0xFFFFFFFFu, NULL, 0, NULL, &eof_at, 0, NULL);
    if (rc)
        return rc;
    if (eof_at < 5 + records_len)
        return FRDP_E_NOT_OURS;
    at = eof_at - records_len;
    walk(ips, len, 5, 0, 0xFFFFFFFFu, NULL, 0, NULL, NULL, at, &starts);
    if (!starts || memcmp(ips + at, records, records_len))
        return FRDP_E_NOT_OURS;
    if (out_len)
        *out_len = len - records_len;
    if (!out)
        return FRDP_OK;
    if (len - records_len > cap)
        return FRDP_E_SPACE;
    memcpy(out, ips, at);
    memcpy(out + at, ips + eof_at, len - eof_at);
    return FRDP_OK;
}

/* ---- the module's .ips on the SD card ---- */

static int std_exists(void *ctx, const char *path) {
    FILE *f = fopen(path, "rb");
    (void)ctx;
    if (f)
        fclose(f);
    return f != NULL;
}

static uint8_t *std_read(void *ctx, const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    uint8_t *data = NULL;
    long size;
    (void)ctx;
    *len = 0;
    if (!f)
        return NULL;
    if (fseek(f, 0, SEEK_END) == 0 && (size = ftell(f)) >= 0 && size <= FRDP_FILE_MAX && fseek(f, 0, SEEK_SET) == 0) {
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

static int std_write(void *ctx, const char *path, const uint8_t *data, size_t len) {
    FILE *f = fopen(path, "wb");
    int bad;
    (void)ctx;
    if (!f)
        return -1;
    bad = fwrite(data, 1, len, f) != len;
    bad |= fclose(f) != 0;
    return bad ? -1 : 0;
}

static int std_remove(void *ctx, const char *path) {
    (void)ctx;
    return remove(path);
}

static int std_rename(void *ctx, const char *from, const char *to) {
    (void)ctx;
    return rename(from, to);
}

void frdp_files_stdio(FrdpFiles *f) {
    f->exists = std_exists;
    f->read = std_read;
    f->write = std_write;
    f->remove = std_remove;
    f->rename = std_rename;
    f->ctx = NULL;
}

/* An IPS file Luma3DS reads, by its form (records anywhere): "PATCH", whole records, "EOF". */
static int whole_ips(const uint8_t *ips, size_t len) {
    size_t eof_at;
    return ips && frdp_ips_check(ips, len, FRDP_IPS_ANY, NULL, 0, &eof_at) == FRDP_OK;
}

void frdp_file_recover(const FrdpFiles *f, const char *path, const char *tmp) {
    uint8_t *t;
    size_t len = 0;
    if (!f->exists(f->ctx, tmp))
        return;
    if (f->exists(f->ctx, path)) {   /* cut while `tmp` was written: the file before stays */
        f->remove(f->ctx, tmp);
        return;
    }
    t = f->read(f->ctx, tmp, &len);   /* cut between the old file's removal and the rename: only a whole one goes in */
    if (whole_ips(t, len))
        f->rename(f->ctx, tmp, path);
    else
        f->remove(f->ctx, tmp);
    free(t);
}

/* `data` swapped in as `path` and read back: FRDP_OK, FRDP_E_IO (`tmp` not written: `path` untouched) or
 * FRDP_E_READBACK (`path` gone or not `data`). */
static int place(const FrdpFiles *f, const char *path, const char *tmp, const uint8_t *data, size_t len) {
    uint8_t *back;
    size_t back_len = 0;
    int same;
    if (f->write(f->ctx, tmp, data, len)) {
        f->remove(f->ctx, tmp);
        return FRDP_E_IO;
    }
    f->remove(f->ctx, path);   /* the card's file system renames onto no existing file */
    if (f->rename(f->ctx, tmp, path)) {
        f->remove(f->ctx, tmp);
        return FRDP_E_READBACK;
    }
    back = f->read(f->ctx, path, &back_len);
    same = back && back_len == len && !memcmp(back, data, len);
    free(back);
    return same ? FRDP_OK : FRDP_E_READBACK;
}

int frdp_file_put(const FrdpFiles *f, const char *path, const char *tmp, const uint8_t *data, size_t len,
                  const uint8_t *old, size_t old_len) {
    int rc = place(f, path, tmp, data, len);
    if (rc != FRDP_E_READBACK)
        return rc;
    if (!old || place(f, path, tmp, old, old_len) != FRDP_OK)   /* the file before, or none: never a damaged one */
        f->remove(f->ctx, path);
    return FRDP_E_READBACK;
}

int frdp_remove_plan(const uint8_t *ips, size_t ips_len, const uint8_t *ours, size_t ours_len, const uint8_t *base,
                     size_t base_len, uint8_t **out, size_t *out_len) {
    uint8_t *stripped;
    size_t n = 0;
    *out = NULL;
    *out_len = 0;
    if (!ips)
        return FRDP_KEEP;
    if (!whole_ips(ips, ips_len)) {   /* Luma3DS would refuse it: the kept file before ours, else none */
        if (!whole_ips(base, base_len) || base_len <= 8 || !(*out = (uint8_t *)malloc(base_len)))
            return FRDP_DELETE;
        memcpy(*out, base, base_len);
        *out_len = base_len;
        return FRDP_WRITE;
    }
    if (!ours || !ours_len)
        return FRDP_KEEP;
    stripped = (uint8_t *)malloc(ips_len + 1);
    if (!stripped || frdp_ips_strip(ips, ips_len, ours, ours_len, stripped, ips_len, &n)) {
        free(stripped);
        return FRDP_KEEP;
    }
    if (n == 8 && !base) {
        free(stripped);
        return FRDP_DELETE;
    }
    *out = stripped;
    *out_len = n;
    return FRDP_WRITE;
}
