/* What an older Heavenfall left in MH4U's files (heav.h). The twin of core/save/heav.py: both follow HF_HEAV_FIELDS
(heav_tables.h, generated from it).
 *
 * As extras.c: the table is code (`field_get`), so the object holds no data section; GCC is kept from emitting
 * memset / memcpy calls, jump tables and lookup tables; no divide (a book card's number is counted out). */

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize("no-tree-loop-distribute-patterns", "no-jump-tables", "no-tree-switch-conversion")
#endif

#include "heav.h"

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;

#define ANY_SLOT   0xFFFFFFFFu
#define DATA_MAX   (4u + HF_HEAV_LOG_SIZE)      /* the largest entry: a book card's log after its CRC */
#define BOOK_CARDS 100u

struct field { u32 file, kind, at, count, stride, groups, group_stride, first, rule; };

/* ---- bytes ------------------------------------------------------------------------------------------------------ */

static u32 rd16(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8; }
static u32 rd32(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24; }

static void wr16(u8 *p, u32 v)
{
    p[0] = (u8)v;
    p[1] = (u8)(v >> 8);
}

static void wr32(u8 *p, u32 v)
{
    p[0] = (u8)v;
    p[1] = (u8)(v >> 8);
    p[2] = (u8)(v >> 16);
    p[3] = (u8)(v >> 24);
}

static void zero(u8 *p, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        p[i] = 0;
}

/* Forward: also for a move towards the start (dst <= src) */
static void copy(u8 *dst, const u8 *src, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        dst[i] = src[i];
}

static int any(const u8 *p, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        if (p[i] != 0)
            return 1;
    return 0;
}

static int same(const u8 *a, const u8 *b, u32 n)
{
    u32 i;
    for (i = 0; i < n; i++)
        if (a[i] != b[i])
            return 0;
    return 1;
}

static int overlap(const void *a, u32 a_size, const void *b, u32 b_size)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return x < y + b_size && y < x + a_size;
}

static u32 pad4(u32 n) { return (n + 3u) & ~3u; }

/* zlib's CRC32 through a table on the stack */
struct crc { u32 table[256]; u32 value; };

static void crc_table(struct crc *c)
{
    u32 i, bit, v;
    for (i = 0; i < 256; i++) {
        for (v = i, bit = 0; bit < 8; bit++)
            v = (v >> 1) ^ (0xEDB88320u & (0u - (v & 1u)));
        c->table[i] = v;
    }
}

static void crc_begin(struct crc *c) { c->value = 0xFFFFFFFFu; }

static void crc_add(struct crc *c, const u8 *p, u32 n)
{
    u32 i, v = c->value;
    for (i = 0; i < n; i++)
        v = c->table[(v ^ p[i]) & 0xFFu] ^ (v >> 8);
    c->value = v;
}

static void crc_zeros(struct crc *c, u32 n)
{
    u32 i, v = c->value;
    for (i = 0; i < n; i++)
        v = c->table[v & 0xFFu] ^ (v >> 8);
    c->value = v;
}

static u32 crc_end(const struct crc *c) { return ~c->value; }

/* A Felyne record's fingerprint (extras.py FINGERPRINT) */
static u32 fingerprint(struct crc *c, const u8 *record)
{
    crc_begin(c);
    crc_add(c, record + HF_EXTRAS_PRINT_A_AT, HF_EXTRAS_PRINT_A_SIZE);
    crc_add(c, record + HF_EXTRAS_PRINT_B_AT, HF_EXTRAS_PRINT_B_SIZE);
    return crc_end(c);
}

/* ---- the table -------------------------------------------------------------------------------------------------- */

static int field_get(u32 wanted, struct field *f)
{
    u32 row = 0;
#define HFH_ROW(file_, kind_, at_, count_, stride_, groups_, group_stride_, first_, rule_) \
    if (row++ == wanted) { \
        f->file = file_; f->kind = kind_; f->at = at_; f->count = count_; f->stride = stride_; f->groups = groups_; \
        f->group_stride = group_stride_; f->first = first_; f->rule = rule_; \
        return 1; \
    }
    HF_HEAV_FIELDS(HFH_ROW)
#undef HFH_ROW
    return 0;
}

static u32 gear_count(u32 type)                 /* 0: not a type of the table */
{
#define HFH_GEAR(type_, count_, from_, end_) if (type == type_) return count_;
    HF_HEAV_GEAR(HFH_GEAR)
#undef HFH_GEAR
    return 0;
}

static u32 felyne_count(u32 type)
{
#define HFH_FELYNE(type_, count_) if (type == type_) return count_;
    HF_HEAV_FELYNE(HFH_FELYNE)
#undef HFH_FELYNE
    return 0;
}

static u32 kind_of(u32 size)
{
    return size == HF_EXTRAS_USER_SIZE ? HF_EXTRAS_USER : size == HF_EXTRAS_CARD_SIZE ? HF_EXTRAS_CARD : 0;
}

static u32 total(const struct field *f) { return f->count * f->groups; }

/* Entry `index`'s place (a record: its hunts), and the book card it is in */
static u32 place_of(const struct field *f, u32 index, u32 *card)
{
    u32 n = index - f->first, group = 0;
    if (f->kind == HF_HEAV_RECORDS)
        return f->at + 2u * index;
    while (n >= f->count) {
        n -= f->count;
        group++;
    }
    if (card != 0)
        *card = group;
    return f->at + f->group_stride * group + f->stride * n;
}

static u32 data_size(const struct field *f)
{
    u32 size;
    if (f->kind == HF_HEAV_REFS)
        size = HF_HEAV_REF;
    else if (f->kind == HF_HEAV_LOG)
        size = HF_HEAV_LOG_SIZE;
    else if (f->kind == HF_HEAV_FELYNE_BOX)
        size = 4;
    else if (f->kind == HF_HEAV_FELYNE_WORN)
        size = HF_HEAV_GROUP_SIZE + 4;
    else if (f->kind == HF_HEAV_MARKS)
        size = HF_HEAV_MARK_BYTES;
    else if (f->kind == HF_HEAV_FELYNE_MARKS)
        size = HF_HEAV_FELYNE_MARK_BYTES;
    else if (f->kind == HF_HEAV_QUEST_WORD)
        size = 4;
    else
        size = 8;
    return size + (f->rule == HF_HEAV_BOOK ? 4u : 0u);
}

/* ---- what MH4U lacks -------------------------------------------------------------------------------------------- */

static int ref_past(const u8 *ref)
{
    u32 count = gear_count(ref[0]);
    return count != 0 && rd16(ref + 2) >= count;
}

static void placeholder(const u8 *ref, u8 *out)
{
    out[0] = ref[0];
    out[1] = 0;
    wr16(out + 2, HF_HEAV_PLACEHOLDER_ID);
    zero(out + 4, HF_HEAV_REF - 4);
}

static int felyne_past(const u8 *piece)
{
    u32 count = felyne_count(piece[0]);
    return count != 0 && rd16(piece + 2) >= count;
}

static int group_past(const u8 *group)
{
    u32 k;
    for (k = 0; k < HF_HEAV_GROUP_SIZE; k += 4)
        if (felyne_past(group + k))
            return 1;
    return 0;
}

static void group_clean(u8 *group)
{
    u32 k;
    for (k = 0; k < HF_HEAV_GROUP_SIZE; k += 4)
        if (felyne_past(group + k)) {
            group[k + 1] = 0;
            wr16(group + k + 2, HF_HEAV_DERRING);
        }
}

/* `now` is `was` cleaned */
static int group_is_clean_of(const u8 *now, const u8 *was)
{
    u32 k;
    for (k = 0; k < HF_HEAV_GROUP_SIZE; k += 4) {
        if (felyne_past(was + k)) {
            if (now[k] != was[k] || now[k + 1] != 0 || rd16(now + k + 2) != HF_HEAV_DERRING)
                return 0;
        } else if (!same(now + k, was + k, 4)) {
            return 0;
        }
    }
    return 1;
}

static int quest_ours(u32 quest)
{
    return quest >= HF_HEAV_FIRST_QUEST && quest < HF_HEAV_FIRST_QUEST + HF_HEAV_QUEST_ROOM;
}

static int ours_at(const u8 *log, u32 n) { return quest_ours(rd16(log + n * HF_HEAV_LOG_ENTRY + HF_HEAV_LOG_QUEST)); }

static int log_past(const u8 *log)
{
    u32 n;
    for (n = 0; n < HF_HEAV_LOG_ENTRIES; n++)
        if (ours_at(log, n))
            return 1;
    return 0;
}

static void log_clean(u8 *log)
{
    u32 n, to = 0;
    for (n = 0; n < HF_HEAV_LOG_ENTRIES; n++)
        if (!ours_at(log, n)) {
            if (to != n)
                copy(log + to * HF_HEAV_LOG_ENTRY, log + n * HF_HEAV_LOG_ENTRY, HF_HEAV_LOG_ENTRY);
            to++;
        }
    zero(log + to * HF_HEAV_LOG_ENTRY, (HF_HEAV_LOG_ENTRIES - to) * HF_HEAV_LOG_ENTRY);
}

static int log_is_clean_of(const u8 *now, const u8 *was)
{
    u32 n, to = 0;
    for (n = 0; n < HF_HEAV_LOG_ENTRIES; n++)
        if (!ours_at(was, n)) {
            if (!same(now + to * HF_HEAV_LOG_ENTRY, was + n * HF_HEAV_LOG_ENTRY, HF_HEAV_LOG_ENTRY))
                return 0;
            to++;
        }
    return !any(now + to * HF_HEAV_LOG_ENTRY, (HF_HEAV_LOG_ENTRIES - to) * HF_HEAV_LOG_ENTRY);
}

static void log_clean_crc(struct crc *c, const u8 *log)
{
    u32 n, kept = 0;
    for (n = 0; n < HF_HEAV_LOG_ENTRIES; n++)
        if (!ours_at(log, n)) {
            crc_add(c, log + n * HF_HEAV_LOG_ENTRY, HF_HEAV_LOG_ENTRY);
            kept++;
        }
    crc_zeros(c, (HF_HEAV_LOG_ENTRIES - kept) * HF_HEAV_LOG_ENTRY);
}

/* Type `type`'s bits MH4U lacks in the equipment marks, [*from, *end); 0 when the type is not of the table */
static int mark_range(u32 type, u32 *from, u32 *end)
{
#define HFH_RANGE(type_, count_, from_, end_) if (type == type_) { *from = from_; *end = end_; return 1; }
    HF_HEAV_GEAR(HFH_RANGE)
#undef HFH_RANGE
    return 0;
}

/* The marks: `op` 0 asks whether a bit MH4U lacks is set, 1 clears them, 2 copies them (only) into `out` */
static int marks(u8 *arr, u32 op, u8 *out)
{
    u32 n, t, from, end;
    int found = 0;
    if (op == 2)
        zero(out, HF_HEAV_MARK_BYTES);
    for (t = 0; t <= 20; t++)
        if (mark_range(t, &from, &end))
            for (n = from; n < end; n++) {
                u32 bit = 1u << (n & 7u);
                if (arr[n >> 3] & bit) {
                    found = 1;
                    if (op == 1)
                        arr[n >> 3] &= (u8)~bit;
                    if (op == 2)
                        out[n >> 3] |= (u8)bit;
                }
            }
    return found;
}

static int felyne_marks(u8 *arr, u32 op, u8 *out)
{
    u32 n, t;
    int found = 0;
    if (op == 2)
        zero(out, HF_HEAV_FELYNE_MARK_BYTES);
    for (t = 0; t < 3; t++)
        for (n = HF_HEAV_FELYNE_WINDOW * t + felyne_count(t); n < HF_HEAV_FELYNE_WINDOW * (t + 1); n++) {
            u32 bit = 1u << (n & 7u);
            if (arr[n >> 3] & bit) {
                found = 1;
                if (op == 1)
                    arr[n >> 3] &= (u8)~bit;
                if (op == 2)
                    out[n >> 3] |= (u8)bit;
            }
        }
    return found;
}

static void record_get(const u8 *file, const struct field *f, u32 index, u8 *out)
{
    u32 at = f->at + 2u * index;
    copy(out, file + at, 2);
    copy(out + 2, file + at + HF_HEAV_CAPTURES_FROM, 2);
    copy(out + 4, file + f->at + HF_HEAV_SIZES_FROM + 4u * index, 4);
}

static void record_put(u8 *file, const struct field *f, u32 index, const u8 *data)
{
    u32 at = f->at + 2u * index;
    copy(file + at, data, 2);
    copy(file + at + HF_HEAV_CAPTURES_FROM, data + 2, 2);
    copy(file + f->at + HF_HEAV_SIZES_FROM + 4u * index, data + 4, 4);
}

/* Whether entry `index` holds something MH4U lacks (`file` is only read: the marks' op 0 writes nothing) */
static int past(const u8 *file, const struct field *f, u32 index)
{
    u32 at = place_of(f, index, 0);
    u8 record[8];
    if (f->kind == HF_HEAV_REFS)
        return ref_past(file + at);
    if (f->kind == HF_HEAV_LOG)
        return log_past(file + at);
    if (f->kind == HF_HEAV_FELYNE_BOX)
        return felyne_past(file + at);
    if (f->kind == HF_HEAV_FELYNE_WORN)
        return group_past(file + at);
    if (f->kind == HF_HEAV_MARKS)
        return marks((u8 *)file + at, 0, 0);
    if (f->kind == HF_HEAV_FELYNE_MARKS)
        return felyne_marks((u8 *)file + at, 0, 0);
    if (f->kind == HF_HEAV_QUEST_WORD)
        return (rd32(file + at) & HF_HEAV_QUEST_MASK) != 0;
    record_get(file, f, index, record);
    return any(record, 8);
}

static void clean_at(u8 *file, const struct field *f, u32 index)
{
    u32 at = place_of(f, index, 0);
    if (f->kind == HF_HEAV_REFS)
        placeholder(file + at, file + at);
    else if (f->kind == HF_HEAV_LOG)
        log_clean(file + at);
    else if (f->kind == HF_HEAV_FELYNE_BOX) {
        file[at + 1] = 0;
        wr16(file + at + 2, HF_HEAV_DERRING);
    } else if (f->kind == HF_HEAV_FELYNE_WORN)
        group_clean(file + at);
    else if (f->kind == HF_HEAV_MARKS)
        marks(file + at, 1, 0);
    else if (f->kind == HF_HEAV_FELYNE_MARKS)
        felyne_marks(file + at, 1, 0);
    else if (f->kind == HF_HEAV_QUEST_WORD)
        wr32(file + at, rd32(file + at) & ~HF_HEAV_QUEST_MASK);
    else {
        u8 none[8];
        zero(none, 8);
        record_put(file, f, index, none);
    }
}

/* A book card's record without its looks, as hf_heav_clean leaves it: the CRC32 the sidecar keeps */
static u32 book_clean_crc(struct crc *c, const u8 *file, u32 card)
{
    const u8 *record = file + HF_HEAV_BOOK_AT + HF_HEAV_CARD_RECORD * card;
    struct field f;
    u32 row, pos = 0, k;
    u8 ref[HF_HEAV_REF];
    crc_begin(c);
    for (row = 0; field_get(row, &f); row++) {         /* the book's rows, in the order of their places */
        u32 at;
        if (f.rule != HF_HEAV_BOOK)
            continue;
        at = f.at - HF_HEAV_BOOK_AT;
        crc_add(c, record + pos, at - pos);
        if (f.kind == HF_HEAV_REFS) {
            for (k = 0; k < f.count; k++) {
                const u8 *now = record + at + f.stride * k;
                if (ref_past(now)) {
                    placeholder(now, ref);
                    crc_add(c, ref, HF_HEAV_REF);
                } else {
                    crc_add(c, now, HF_HEAV_REF);
                }
            }
            pos = at + f.stride * f.count;
        } else {
            log_clean_crc(c, record + at);
            pos = at + HF_HEAV_LOG_SIZE;
        }
    }
    crc_add(c, record + pos, HF_HEAV_BOOK_CRC_SIZE - pos);
    return crc_end(c);
}

static u32 book_crc(struct crc *c, const u8 *file, u32 card)
{
    crc_begin(c);
    crc_add(c, file + HF_HEAV_BOOK_AT + HF_HEAV_CARD_RECORD * card, HF_HEAV_BOOK_CRC_SIZE);
    return crc_end(c);
}

/* What an entry keeps of the file's place (heav.py _data); its size */
static u32 entry_data(struct crc *c, const u8 *file, const struct field *f, u32 index, u8 *out)
{
    u32 card = 0, at = place_of(f, index, &card);
    u8 *p = out;
    if (f->rule == HF_HEAV_BOOK) {
        wr32(p, book_clean_crc(c, file, card));
        p += 4;
    }
    if (f->kind == HF_HEAV_REFS)
        copy(p, file + at, HF_HEAV_REF);
    else if (f->kind == HF_HEAV_LOG)
        copy(p, file + at, HF_HEAV_LOG_SIZE);
    else if (f->kind == HF_HEAV_FELYNE_BOX)
        copy(p, file + at, 4);
    else if (f->kind == HF_HEAV_FELYNE_WORN) {
        copy(p, file + at, HF_HEAV_GROUP_SIZE);
        wr32(p + HF_HEAV_GROUP_SIZE, fingerprint(c, file + at - HF_HEAV_GROUP_AT));
    } else if (f->kind == HF_HEAV_MARKS)
        marks((u8 *)file + at, 2, p);
    else if (f->kind == HF_HEAV_FELYNE_MARKS)
        felyne_marks((u8 *)file + at, 2, p);
    else if (f->kind == HF_HEAV_QUEST_WORD)
        wr32(p, rd32(file + at) & HF_HEAV_QUEST_MASK);
    else
        record_get(file, f, index, p);
    return data_size(f);
}

static const u8 *identity_of(const u8 *file, u32 kind)
{
    return file + (kind == HF_EXTRAS_USER ? HF_EXTRAS_USER_IDENTITY_AT : HF_EXTRAS_CARD_IDENTITY_AT);
}

/* ---- the file --------------------------------------------------------------------------------------------------- */

int hf_heav_has(const uint8_t *file, uint32_t size)
{
    struct field f;
    u32 row, i, kind = kind_of(size);
    if (file == 0)
        return HF_EXTRAS_E_ARG;
    if (kind == 0)
        return HF_EXTRAS_E_SIZE;
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind)
            for (i = 0; i < total(&f); i++)
                if (past(file, &f, f.first + i))
                    return 1;
    return 0;
}

int hf_heav_clean(uint8_t *file, uint32_t size)
{
    struct field f;
    u32 row, i, kind = kind_of(size);
    int n = 0;
    if (file == 0)
        return HF_EXTRAS_E_ARG;
    if (kind == 0)
        return HF_EXTRAS_E_SIZE;
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind)
            for (i = 0; i < total(&f); i++)
                if (past(file, &f, f.first + i)) {
                    clean_at(file, &f, f.first + i);
                    n++;
                }
    return n;
}

int hf_heav_mh4u_clean(const uint8_t *file, uint32_t size)
{
    u32 kind = kind_of(size);
    int r;
    if (file == 0)
        return HF_EXTRAS_E_ARG;
    if (kind == 0)
        return HF_EXTRAS_E_SIZE;
    r = kind == HF_EXTRAS_USER ? hf_extras_user_has(file, size) : hf_extras_card_has(file, size);
    if (r != 0)
        return r < 0 ? r : 0;
    r = hf_heav_has(file, size);
    return r < 0 ? r : !r;
}

/* ---- the sidecar ------------------------------------------------------------------------------------------------ */

static int header_valid(struct crc *c, const u8 *heav, u32 slot)
{
    crc_begin(c);
    crc_add(c, heav, 12);
    return rd32(heav) == HF_HEAV_MAGIC && rd16(heav + 4) == HF_HEAV_VERSION && rd32(heav + 12) == crc_end(c) &&
           (slot == ANY_SLOT || heav[6] == slot);
}

/* The end of the valid blocks (where the next one goes); their number in *blocks */
static u32 walk_end(struct crc *c, const u8 *heav, u32 *blocks)
{
    u32 at = HF_HEAV_HEADER_SIZE, n = 0;
    while (at + HF_HEAV_BLOCK_SIZE <= HF_HEAV_SIZE) {
        u32 kind = rd16(heav + at), count = rd16(heav + at + 2), size = rd32(heav + at + 4), pos, k, end;
        if ((kind != HF_EXTRAS_USER && kind != HF_EXTRAS_CARD) || size > HF_HEAV_SIZE - at - HF_HEAV_BLOCK_SIZE)
            break;
        end = at + HF_HEAV_BLOCK_SIZE + size;
        crc_begin(c);
        crc_add(c, heav + at, HF_HEAV_BLOCK_SIZE - 4);
        crc_add(c, heav + at + HF_HEAV_BLOCK_SIZE, size);
        if (crc_end(c) != rd32(heav + at + HF_HEAV_BLOCK_SIZE - 4))
            break;
        for (pos = at + HF_HEAV_BLOCK_SIZE, k = 0; k < count; k++) {
            if (pos + HF_HEAV_ENTRY_SIZE > end || pos + HF_HEAV_ENTRY_SIZE + pad4(rd16(heav + pos + 4)) > end)
                break;
            pos += HF_HEAV_ENTRY_SIZE + pad4(rd16(heav + pos + 4));
        }
        if (k != count || pos != end)
            break;
        n++;
        at = end;
    }
    if (blocks != 0)
        *blocks = n;
    return at;
}

static u32 block_end(const u8 *heav, u32 at) { return at + HF_HEAV_BLOCK_SIZE + rd32(heav + at + 4); }

static int block_of(const u8 *heav, u32 at, u32 kind, const u8 *identity)
{
    return rd16(heav + at) == kind && same(heav + at + 8, identity, HF_EXTRAS_IDENTITY_SIZE);
}

static u32 next_entry(const u8 *heav, u32 e) { return e + HF_HEAV_ENTRY_SIZE + pad4(rd16(heav + e + 4)); }

/* Whether a block of `kind` and `identity` from `from` on (to `end`) holds an entry of `field` and `index` */
static int later_has(const u8 *heav, u32 from, u32 end, u32 kind, const u8 *identity, u32 field, u32 index)
{
    u32 b, e;
    for (b = from; b < end; b = block_end(heav, b))
        if (block_of(heav, b, kind, identity))
            for (e = b + HF_HEAV_BLOCK_SIZE; e < block_end(heav, b); e = next_entry(heav, e))
                if (heav[e] == field && rd16(heav + e + 2) == index)
                    return 1;
    return 0;
}

/* The newest entry of `field` and `index` (its offset, 0: none) */
static u32 newest(const u8 *heav, u32 end, u32 kind, const u8 *identity, u32 field, u32 index)
{
    u32 b, e, found = 0;
    for (b = HF_HEAV_HEADER_SIZE; b < end; b = block_end(heav, b))
        if (block_of(heav, b, kind, identity))
            for (e = b + HF_HEAV_BLOCK_SIZE; e < block_end(heav, b); e = next_entry(heav, e))
                if (heav[e] == field && rd16(heav + e + 2) == index)
                    found = e;
    return found;
}

int hf_heav_blocks(const uint8_t *heav, uint32_t heav_size)
{
    struct crc c;
    u32 n;
    if (heav == 0)
        return HF_EXTRAS_E_ARG;
    if (heav_size != HF_HEAV_SIZE)
        return HF_EXTRAS_E_SIZE;
    crc_table(&c);
    if (!header_valid(&c, heav, ANY_SLOT))
        return 0;
    walk_end(&c, heav, &n);
    return (int)n;
}

int hf_heav_append(const uint8_t *file, uint32_t size, uint8_t *heav, uint32_t heav_size, uint32_t slot)
{
    struct crc c;
    struct field f;
    u8 data[DATA_MAX];
    u32 kind = kind_of(size), row, i, count = 0, body = 0, end = HF_HEAV_HEADER_SIZE, at, n;
    const u8 *identity;
    int valid, already = 1;
    if (file == 0 || heav == 0 || slot > 255 || overlap(file, size, heav, heav_size))
        return HF_EXTRAS_E_ARG;
    if (kind == 0 || heav_size != HF_HEAV_SIZE)
        return HF_EXTRAS_E_SIZE;
    identity = identity_of(file, kind);
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind)
            for (i = 0; i < total(&f); i++)
                if (past(file, &f, f.first + i)) {
                    count++;
                    body += HF_HEAV_ENTRY_SIZE + pad4(data_size(&f));
                }
    if (count == 0)
        return HF_HEAV_NOTHING;
    crc_table(&c);
    valid = header_valid(&c, heav, slot);
    if (valid)
        end = walk_end(&c, heav, 0);
    else
        already = 0;
    for (row = 0; already && field_get(row, &f); row++)
        if (f.file == kind)
            for (i = 0; already && i < total(&f); i++)
                if (past(file, &f, f.first + i)) {
                    u32 e = newest(heav, end, kind, identity, row + 1, f.first + i);
                    n = entry_data(&c, file, &f, f.first + i, data);
                    if (e == 0 || rd16(heav + e + 4) != n || !same(heav + e + HF_HEAV_ENTRY_SIZE, data, n))
                        already = 0;
                }
    if (already)
        return HF_HEAV_ALREADY;
    if (end + HF_HEAV_BLOCK_SIZE + body > HF_HEAV_SIZE)
        return HF_EXTRAS_E_FULL;
    if (!valid) {
        wr32(heav, HF_HEAV_MAGIC);
        wr16(heav + 4, HF_HEAV_VERSION);
        heav[6] = (u8)slot;
        heav[7] = 0;
        wr32(heav + 8, 0);
        crc_begin(&c);
        crc_add(&c, heav, 12);
        wr32(heav + 12, crc_end(&c));
    }
    at = end + HF_HEAV_BLOCK_SIZE;
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind)
            for (i = 0; i < total(&f); i++)
                if (past(file, &f, f.first + i)) {
                    n = entry_data(&c, file, &f, f.first + i, data);
                    heav[at] = (u8)(row + 1);
                    heav[at + 1] = 0;
                    wr16(heav + at + 2, f.first + i);
                    wr16(heav + at + 4, n);
                    wr16(heav + at + 6, 0);
                    copy(heav + at + HF_HEAV_ENTRY_SIZE, data, n);
                    zero(heav + at + HF_HEAV_ENTRY_SIZE + n, pad4(n) - n);
                    at += HF_HEAV_ENTRY_SIZE + pad4(n);
                }
    zero(heav + at, HF_HEAV_SIZE - at);
    wr16(heav + end, kind);
    wr16(heav + end + 2, count);
    wr32(heav + end + 4, body);
    copy(heav + end + 8, identity, HF_EXTRAS_IDENTITY_SIZE);
    wr32(heav + end + 16, kind == HF_EXTRAS_USER ? rd32(file + HF_EXTRAS_PLAY_TIME_AT) : 0);
    zero(heav + end + 20, 8);
    crc_begin(&c);
    crc_add(&c, heav + end, HF_HEAV_BLOCK_SIZE - 4);
    crc_add(&c, heav + end + HF_HEAV_BLOCK_SIZE, body);
    wr32(heav + end + HF_HEAV_BLOCK_SIZE - 4, crc_end(&c));
    return HF_HEAV_APPENDED;
}

/* ---- join (Bring) ----------------------------------------------------------------------------------------------- */

struct join {
    u8 *file;
    const u8 *heav, *identity;
    u32 end, kind;
};

/* The newest entries of `field` (oldest block first, then in order) are those no later block replaces */
#define EACH_NEWEST(j, field, b, e) \
    for (b = HF_HEAV_HEADER_SIZE; b < (j)->end; b = block_end((j)->heav, b)) \
        if (block_of((j)->heav, b, (j)->kind, (j)->identity)) \
            for (e = b + HF_HEAV_BLOCK_SIZE; e < block_end((j)->heav, b); e = next_entry((j)->heav, e)) \
                if ((j)->heav[e] == (field) && \
                    !later_has((j)->heav, block_end((j)->heav, b), (j)->end, (j)->kind, (j)->identity, (field), \
                               rd16((j)->heav + e + 2)))

static int usable(const struct field *f, const u8 *heav, u32 e)
{
    u32 index = rd16(heav + e + 2);
    return index >= f->first && index < f->first + total(f) && rd16(heav + e + 4) == data_size(f);
}

static u32 shown(const u8 *file, u32 base, u32 step)
{
    u32 flags = rd32(file + HF_HEAV_BOX_SHOWN_AT);
    return base + ((flags & HF_HEAV_BOX_GROWN_A) ? step : 0u) + ((flags & HF_HEAV_BOX_GROWN_B) ? step : 0u);
}

/* The box and the Felyne box: each piece to its own slot when that slot holds it, its placeholder, or nothing; then
 * the others to the first empty shown slot. The pieces left over. */
static u32 place_pieces(const struct join *j, const struct field *f, u32 field, u32 size, u32 slots)
{
    u32 b, e, i, left = 0;
    int felyne = f->kind == HF_HEAV_FELYNE_BOX;
    u8 mark[HF_HEAV_REF];
    EACH_NEWEST(j, field, b, e) {
        const u8 *was = j->heav + e + HF_HEAV_ENTRY_SIZE;
        u8 *now;
        if (!usable(f, j->heav, e))
            continue;
        now = j->file + place_of(f, rd16(j->heav + e + 2), 0);
        if (felyne) {
            copy(mark, was, 4);
            mark[1] = 0;
            wr16(mark + 2, HF_HEAV_DERRING);
        } else {
            placeholder(was, mark);
        }
        if (same(now, was, size) || same(now, mark, size) || now[0] == (felyne ? HF_HEAV_FELYNE_FREE : 0u))
            copy(now, was, size);
    }
    EACH_NEWEST(j, field, b, e) {
        const u8 *was = j->heav + e + HF_HEAV_ENTRY_SIZE;
        if (!usable(f, j->heav, e) || same(j->file + place_of(f, rd16(j->heav + e + 2), 0), was, size))
            continue;
        for (i = 0; i < slots; i++) {
            u8 *there = j->file + place_of(f, f->first + i, 0);
            if (there[0] == (felyne ? HF_HEAV_FELYNE_FREE : 0u)) {
                copy(there, was, size);
                break;
            }
        }
        if (i == slots)
            left++;
    }
    return left;
}

int hf_heav_join(uint8_t *file, uint32_t size, const uint8_t *heav, uint32_t heav_size)
{
    struct crc c;
    struct field f, box;
    struct join j;
    u32 crcs[BOOK_CARDS];
    u8 identity[HF_EXTRAS_IDENTITY_SIZE], mark[HF_HEAV_REF], record[8];
    u32 kind = kind_of(size), row, b, e, n, card;
    int left = 0;
    if (file == 0 || (heav != 0 && overlap(file, size, heav, heav_size)))
        return HF_EXTRAS_E_ARG;
    if (kind == 0)
        return HF_EXTRAS_E_SIZE;
    if (heav == 0)
        return 0;
    if (heav_size != HF_HEAV_SIZE)
        return HF_EXTRAS_E_SIZE;
    crc_table(&c);
    if (!header_valid(&c, heav, ANY_SLOT))
        return 0;
    copy(identity, identity_of(file, kind), HF_EXTRAS_IDENTITY_SIZE);
    j.file = file;
    j.heav = heav;
    j.identity = identity;
    j.kind = kind;
    j.end = walk_end(&c, heav, 0);
    if (kind == HF_EXTRAS_CARD)
        for (card = 0; card < BOOK_CARDS; card++)
            crcs[card] = book_crc(&c, file, card);
    field_get(0, &box);
    for (row = 0; field_get(row, &f); row++) {
        u32 field = row + 1;
        if (f.file != kind)
            continue;
        if (f.kind == HF_HEAV_REFS && f.rule == HF_HEAV_BOX) {
            left += (int)place_pieces(&j, &f, field, HF_HEAV_REF, shown(file, HF_HEAV_BOX_SHOWN, HF_HEAV_BOX_STEP));
        } else if (f.kind == HF_HEAV_FELYNE_BOX) {
            left += (int)place_pieces(&j, &f, field, 4, shown(file, HF_HEAV_FELYNE_SHOWN, HF_HEAV_FELYNE_STEP));
        } else if (f.kind == HF_HEAV_MARKS || f.kind == HF_HEAV_FELYNE_MARKS || f.kind == HF_HEAV_QUEST_WORD) {
            u32 bytes = data_size(&f);
            for (b = HF_HEAV_HEADER_SIZE; b < j.end; b = block_end(heav, b))
                if (block_of(heav, b, kind, identity))
                    for (e = b + HF_HEAV_BLOCK_SIZE; e < block_end(heav, b); e = next_entry(heav, e))
                        if (heav[e] == field && usable(&f, heav, e)) {
                            u8 *to = file + place_of(&f, rd16(heav + e + 2), 0);
                            for (n = 0; n < bytes; n++)
                                to[n] |= heav[e + HF_HEAV_ENTRY_SIZE + n];
                        }
        } else {
            EACH_NEWEST(&j, field, b, e) {
                const u8 *was = heav + e + HF_HEAV_ENTRY_SIZE;
                u32 index = rd16(heav + e + 2), at;
                if (!usable(&f, heav, e))
                    continue;
                at = place_of(&f, index, &card);
                if (f.rule == HF_HEAV_BOOK) {
                    if (rd32(was) == crcs[card])
                        copy(file + at, was + 4, data_size(&f) - 4);
                } else if (f.kind == HF_HEAV_REFS && f.rule == HF_HEAV_WORN) {
                    u32 slot = rd16(file + HF_HEAV_WORN_INDICES + 2u * (index - f.first));
                    placeholder(was, mark);
                    if (same(file + at, mark, HF_HEAV_REF) && slot < box.count &&
                        same(file + place_of(&box, box.first + slot, 0), was, HF_HEAV_REF))
                        copy(file + at, was, HF_HEAV_REF);
                } else if (f.kind == HF_HEAV_REFS) {
                    placeholder(was, mark);
                    if (same(file + at, mark, HF_HEAV_REF))
                        copy(file + at, was, HF_HEAV_REF);
                } else if (f.kind == HF_HEAV_LOG) {
                    if (log_is_clean_of(file + at, was))
                        copy(file + at, was, HF_HEAV_LOG_SIZE);
                } else if (f.kind == HF_HEAV_FELYNE_WORN) {
                    if (fingerprint(&c, file + at - HF_HEAV_GROUP_AT) == rd32(was + HF_HEAV_GROUP_SIZE) &&
                        group_is_clean_of(file + at, was))
                        copy(file + at, was, HF_HEAV_GROUP_SIZE);
                } else if (f.kind == HF_HEAV_RECORDS) {
                    record_get(file, &f, index, record);
                    if (!any(record, 8))
                        record_put(file, &f, index, was);
                }
            }
        }
    }
    return left;
}
