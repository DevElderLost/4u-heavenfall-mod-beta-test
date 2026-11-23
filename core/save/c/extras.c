/* Heavenfall's save extras: split and join (extras.h). The twin of core/save/extras.py:
 * both follow HF_EXTRAS_FIELDS (extras_tables.h, generated from it).
 *
 * The table is code, not data: `field_get` expands HF_EXTRAS_FIELDS into one row after another, so the object holds
 * no data section and needs no relocation. GCC is kept from turning loops into memset / memcpy calls and branches
 * into jump tables or lookup tables (the pragma below; the same as -fno-tree-loop-distribute-patterns
 * -fno-jump-tables -fno-tree-switch-conversion). */

#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC optimize("no-tree-loop-distribute-patterns", "no-jump-tables", "no-tree-switch-conversion")
#endif

#include "extras.h"

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;

#define PLACED 0x4000u                  /* an entry's place bit during a join only: put into the file, or skipped */

struct field {
    u32 file, kind, at, size, count, stride, groups, rule, first, check_at, check_size, value, image_at;
};

struct shape { u32 size, magic, image_size, entries_at, capacity; };

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

/* zlib's CRC32, a byte at a time through a table built on the stack (1 KB: no data of its own) */
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

static u32 crc_end(const struct crc *c) { return ~c->value; }

static u32 crc_of(struct crc *c, const u8 *p, u32 n)
{
    crc_begin(c);
    crc_add(c, p, n);
    return crc_end(c);
}

static u32 crc32(const u8 *p, u32 n)
{
    struct crc c;
    crc_table(&c);
    return crc_of(&c, p, n);
}

/* An image's CRC: every byte of it but the CRC's own four */
static u32 image_crc(struct crc *c, const u8 *image, u32 size)
{
    crc_begin(c);
    crc_add(c, image, HF_EXTRAS_CRC_AT);
    crc_add(c, image + HF_EXTRAS_CRC_AT + 4, size - HF_EXTRAS_CRC_AT - 4);
    return crc_end(c);
}

/* A Felyne record's fingerprint: what play does not change (extras.py FINGERPRINT) */
static u32 fingerprint(struct crc *c, const u8 *record)
{
    crc_begin(c);
    crc_add(c, record + HF_EXTRAS_PRINT_A_AT, HF_EXTRAS_PRINT_A_SIZE);
    crc_add(c, record + HF_EXTRAS_PRINT_B_AT, HF_EXTRAS_PRINT_B_SIZE);
    return crc_end(c);
}

/* CRC32 of book card `i`'s record without its block of looks (extras.py _book_crc) */
static u32 book_crc(struct crc *c, const u8 *plain, const struct field *f, u32 i)
{
    const u8 *record = plain + f->at - f->check_at + f->stride * i;
    crc_begin(c);
    crc_add(c, record, f->check_at);
    crc_add(c, record + f->check_at + f->size, f->check_size - f->check_at - f->size);
    return crc_end(c);
}

/* ---- the table ---------------------------------------------------------------------------------------------------- */

/* Row `wanted` of the table into *f: 1, or 0 past the last */
static int field_get(u32 wanted, struct field *f)
{
    u32 row = 0;
#define HFX_ROW(file_, kind_, at_, size_, count_, stride_, groups_, rule_, first_, check_at_, check_size_, value_, \
                image_at_) \
    if (row++ == wanted) { \
        f->file = file_; f->kind = kind_; f->at = at_; f->size = size_; f->count = count_; f->stride = stride_; \
        f->groups = groups_; f->rule = rule_; f->first = first_; f->check_at = check_at_; \
        f->check_size = check_size_; f->value = value_; f->image_at = image_at_; \
        return 1; \
    }
    HF_EXTRAS_FIELDS(HFX_ROW)
#undef HFX_ROW
    return 0;
}

static void shape_of(u32 kind, struct shape *s)
{
    if (kind == HF_EXTRAS_USER) {
        s->size = HF_EXTRAS_USER_SIZE;
        s->magic = HF_EXTRAS_USER_MAGIC;
        s->image_size = HF_EXTRAS_USER_IMAGE_SIZE;
        s->entries_at = HF_EXTRAS_USER_ENTRIES_AT;
        s->capacity = HF_EXTRAS_USER_CAPACITY;
    } else {
        s->size = HF_EXTRAS_CARD_SIZE;
        s->magic = HF_EXTRAS_CARD_MAGIC;
        s->image_size = HF_EXTRAS_CARD_IMAGE_SIZE;
        s->entries_at = HF_EXTRAS_CARD_ENTRIES_AT;
        s->capacity = HF_EXTRAS_CARD_CAPACITY;
    }
}

static u32 slots_of(const struct field *f) { return f->groups * f->count; }

/* The item field of `kind` whose entries' places hold `place` into *f: 1, or 0 */
static int item_field(u32 kind, u32 place, struct field *f)
{
    u32 row;
    for (row = 0; field_get(row, f); row++)
        if (f->file == kind && f->kind == HF_EXTRAS_ITEMS && f->first <= place && place - f->first < slots_of(f))
            return 1;
    return 0;
}

/* The item box of `kind` into *f: 1, or 0 (a card file has none) */
static int box_field(u32 kind, struct field *f)
{
    u32 row;
    for (row = 0; field_get(row, f); row++)
        if (f->file == kind && f->kind == HF_EXTRAS_ITEMS && f->rule == HF_EXTRAS_BOX)
            return 1;
    return 0;
}

/* The box's slots the game shows and fills (FUN_00c1daf0): 1200, 100 more for each expansion bit; at most `box`'s */
static u32 box_shown(const u8 *plain, const struct field *box)
{
    u32 flags = rd32(plain + HF_EXTRAS_BOX_SHOWN_AT), shown = HF_EXTRAS_BOX_STEPS;
    shown += (flags & HF_EXTRAS_BOX_GROWN_A) != 0;
    shown += (flags & HF_EXTRAS_BOX_GROWN_B) != 0;
    shown *= HF_EXTRAS_BOX_STEP;
    return shown < slots_of(box) ? shown : slots_of(box);
}

/* Where the slot of `place` is: group (place - first) / count, by subtraction (no divide on the ARM11) */
static u32 slot_at(const struct field *f, u32 place)
{
    u32 group = 0, index = place - f->first;
    while (index >= f->count) {
        index -= f->count;
        group++;
    }
    return f->at + f->stride * group + 4 * index;
}

/* The place of the first slot of `place`'s group */
static u32 group_first(const struct field *f, u32 place)
{
    u32 index = place - f->first;
    while (index >= f->count)
        index -= f->count;
    return place - index;
}

/* The userN file offset of Felyne record `index` (0 the main cat, 1-50 the cards) */
static u32 record_at(u32 index)
{
    struct field f;
    u32 row;
    for (row = 0; field_get(row, &f); row++)
        if (f.kind == HF_EXTRAS_CATS && f.first <= index && index - f.first < f.count)
            return f.at + f.stride * (index - f.first);
    return 0;
}

/* A VALID zone holds a choice: its check bytes hold the value and some other byte is non-zero (the magic alone, which
 * Layered Gear writes at every save, is a session that chose nothing) */
static int zone_valid(const u8 *zone, const struct field *f)
{
    u32 v = 0, i = f->check_size;
    while (i-- > 0)
        v = v << 8 | zone[f->check_at + i];
    if (v != f->value)
        return 0;
    return any(zone, f->check_at) || any(zone + f->check_at + f->check_size, f->size - f->check_at - f->check_size);
}

/* ---- images --------------------------------------------------------------------------------------------------------- */

static u8 *entry_at(u8 *image, const struct shape *s, u32 k) { return image + s->entries_at + HF_EXTRAS_ENTRY_SIZE * k; }

static const u8 *entry_in(const u8 *image, const struct shape *s, u32 k)
{
    return image + s->entries_at + HF_EXTRAS_ENTRY_SIZE * k;
}

static u8 *cat_at(u8 *image, u32 k) { return image + HF_EXTRAS_USER_CATS_AT + HF_EXTRAS_CAT_SIZE * k; }

static u32 place_of(const u8 *e) { return rd16(e) & HF_EXTRAS_PLACE; }

/* hf_extras_image_kind with the caller's CRC table (one table on the stack, not two) */
static int image_kind(const u8 *image, u32 size, struct crc *c)
{
    struct shape s;
    struct field f;
    u32 kind, count, left, cats, k, flagged = 0;
    if (image == 0 || size < HF_EXTRAS_HEADER_SIZE)
        return 0;
    if (rd32(image) == HF_EXTRAS_USER_MAGIC)
        kind = HF_EXTRAS_USER;
    else if (rd32(image) == HF_EXTRAS_CARD_MAGIC)
        kind = HF_EXTRAS_CARD;
    else
        return 0;
    shape_of(kind, &s);
    if (size < s.image_size || rd16(image + 4) != HF_EXTRAS_VERSION)
        return 0;
    if (rd32(image + HF_EXTRAS_CRC_AT) != image_crc(c, image, s.image_size))
        return 0;
    count = rd16(image + HF_EXTRAS_COUNTS_AT);
    left = rd16(image + HF_EXTRAS_COUNTS_AT + 2);
    cats = rd16(image + HF_EXTRAS_CATS_COUNT_AT);
    if (count > s.capacity || left > count || cats > (kind == HF_EXTRAS_USER ? HF_EXTRAS_CAT_CAPACITY : 0u))
        return 0;
    for (k = 0; k < count; k++) {
        const u8 *e = entry_in(image, &s, k);
        if (!item_field(kind, place_of(e), &f) || rd16(e + 2) < HF_EXTRAS_FIRST_NEW_ITEM)
            return 0;
        flagged += rd16(e) >> 15;
    }
    for (k = 0; k < cats; k++)
        if (image[HF_EXTRAS_USER_CATS_AT + HF_EXTRAS_CAT_SIZE * k] >= HF_EXTRAS_CAT_CAPACITY)
            return 0;
    return flagged == left ? (int)kind : 0;
}

int hf_extras_image_kind(const u8 *image, u32 size)
{
    struct crc c;
    crc_table(&c);
    return image_kind(image, size, &c);
}

u32 hf_extras_generation(const u8 *image) { return rd32(image + HF_EXTRAS_GENERATION_AT); }

u32 hf_extras_left_over(const u8 *image) { return rd16(image + HF_EXTRAS_COUNTS_AT + 2); }

int hf_extras_owned_by(const u8 *image, const u8 *identity, u32 slot)
{
    return identity != 0 && same(image + HF_EXTRAS_IDENTITY_IN, identity, HF_EXTRAS_IDENTITY_SIZE) &&
           image[HF_EXTRAS_SLOT_AT] == slot;
}

int hf_extras_pick(const u8 *a, u32 a_size, const u8 *b, u32 b_size, u32 kind, u32 tag, const u8 *identity, u32 slot)
{
    int va = hf_extras_image_kind(a, a_size) == (int)kind, vb = hf_extras_image_kind(b, b_size) == (int)kind;
    int oa = va && hf_extras_owned_by(a, identity, slot), ob = vb && hf_extras_owned_by(b, identity, slot);
    int ma, mb;
    if (oa || ob) {
        va = oa;
        vb = ob;
    }
    if (!va && !vb)
        return HF_EXTRAS_NONE;
    if (!va || !vb)
        return va ? 0 : 1;
    ma = rd32(a + HF_EXTRAS_TAG_AT) == tag;
    mb = rd32(b + HF_EXTRAS_TAG_AT) == tag;
    if (ma != mb)
        return ma ? 0 : 1;
    return hf_extras_generation(b) > hf_extras_generation(a) ? 1 : 0;
}

u32 hf_extras_newest_generation(const u8 *a, u32 a_size, const u8 *b, u32 b_size, u32 kind)
{
    u32 newest = 0;
    if (hf_extras_image_kind(a, a_size) == (int)kind)
        newest = hf_extras_generation(a);
    if (hf_extras_image_kind(b, b_size) == (int)kind && hf_extras_generation(b) > newest)
        newest = hf_extras_generation(b);
    return newest;
}

int hf_extras_write_slot(const u8 *a, u32 a_size, const u8 *b, u32 b_size, u32 kind, int picked)
{
    if (picked == 0 || picked == 1)
        return 1 - picked;
    if (hf_extras_image_kind(a, a_size) != (int)kind)
        return 0;
    if (hf_extras_image_kind(b, b_size) != (int)kind)
        return 1;
    return hf_extras_generation(a) <= hf_extras_generation(b) ? 0 : 1;
}

u32 hf_extras_user_tag(const u8 *user) { return crc32(user + HF_EXTRAS_DATA_AT, HF_EXTRAS_TAIL_AT - HF_EXTRAS_DATA_AT); }

u32 hf_extras_card_tag(const u8 *card) { return crc32(card + HF_EXTRAS_CARD_SETS_AT, HF_EXTRAS_CARD_SETS_SIZE); }

/* ---- the whole mark ------------------------------------------------------------------------------------------------- */

u32 hf_extras_whole_kind(u32 mark)
{
    if (mark >> 16 == HF_EXTRAS_WHOLE_MAGIC)
        return HF_EXTRAS_DROP_ALL;
    if (mark >> 16 == HF_EXTRAS_KEEP_MAGIC)
        return HF_EXTRAS_KEEP_FLAGGED;
    if (mark >> 16 == HF_EXTRAS_LACKS_MAGIC)
        return HF_EXTRAS_LACKS;
    return 0;
}

u32 hf_extras_whole_mark(const u8 *user)
{
    u32 word = rd32(user + HF_EXTRAS_WHOLE_AT);
    return hf_extras_whole_kind(word) != 0 ? word : 0;
}

void hf_extras_set_whole_mark(u8 *user, u32 superseded, u32 how)
{
    u32 magic = how == HF_EXTRAS_LACKS ? HF_EXTRAS_LACKS_MAGIC : how != 0 ? HF_EXTRAS_KEEP_MAGIC : HF_EXTRAS_WHOLE_MAGIC;
    wr32(user + HF_EXTRAS_WHOLE_AT, magic << 16 | (superseded & 0xFFFFu));
}

/* ---- the parent, the card's mark ------------------------------------------------------------------------------------- */

u32 hf_extras_crc32(const u8 *p, u32 n) { return crc32(p, n); }

u32 hf_extras_tail_crc(const u8 *user) { return crc32(user + HF_EXTRAS_TAIL_AT, HF_EXTRAS_USER_SIZE - HF_EXTRAS_TAIL_AT); }

u32 hf_extras_parent_tag(const u8 *image)
{
    return rd32(image) == HF_EXTRAS_USER_MAGIC ? rd32(image + HF_EXTRAS_PARENT_TAG_IN) : 0;
}

u32 hf_extras_parent_tail(const u8 *image)
{
    return rd32(image) == HF_EXTRAS_USER_MAGIC ? rd32(image + HF_EXTRAS_PARENT_TAIL_IN) : 0;
}

int hf_extras_set_parent(u8 *image, u32 size, u32 tag, u32 tail)
{
    struct crc c;
    if (image == 0)
        return HF_EXTRAS_E_ARG;
    crc_table(&c);
    if (image_kind(image, size, &c) != (int)HF_EXTRAS_USER)
        return HF_EXTRAS_E_IMAGE;
    wr32(image + HF_EXTRAS_PARENT_TAG_IN, tag);
    wr32(image + HF_EXTRAS_PARENT_TAIL_IN, tail);
    wr32(image + HF_EXTRAS_CRC_AT, image_crc(&c, image, HF_EXTRAS_USER_IMAGE_SIZE));
    return 0;
}

int hf_extras_card_marked(const u8 *card) { return rd32(card + HF_EXTRAS_CARD_MARK_AT) == HF_EXTRAS_CARD_MARK; }

void hf_extras_set_card_mark(u8 *card) { wr32(card + HF_EXTRAS_CARD_MARK_AT, HF_EXTRAS_CARD_MARK); }

int hf_extras_set_generation(u8 *image, u32 size, u32 generation)
{
    struct crc c;
    struct shape s;
    int kind;
    if (image == 0)
        return HF_EXTRAS_E_ARG;
    crc_table(&c);
    kind = image_kind(image, size, &c);
    if (kind == 0)
        return HF_EXTRAS_E_IMAGE;
    shape_of((u32)kind, &s);
    wr32(image + HF_EXTRAS_GENERATION_AT, generation);
    wr32(image + HF_EXTRAS_CRC_AT, image_crc(&c, image, s.image_size));
    return 0;
}

int hf_extras_mark_covers(u32 mark, u32 generation) { return ((mark - generation) & 0xFFFFu) < 0x8000u; }

/* ---- has, split ----------------------------------------------------------------------------------------------------- */

/* 1 if field f of `plain` holds anything to set apart */
static int field_has(const u8 *plain, const struct field *f)
{
    u32 i;
    if (f->kind == HF_EXTRAS_ZONE || f->kind == HF_EXTRAS_MARK)
        return any(plain + f->at, f->size);
    if (f->kind == HF_EXTRAS_CATS) {
        for (i = 0; i < f->count; i++)
            if (rd32(plain + f->at + f->stride * i + HF_EXTRAS_LOOK_AT) != 0)
                return 1;
        return 0;
    }
    if (f->kind == HF_EXTRAS_BITS)
        return (rd32(plain + f->at) & f->value) != 0;
    if (f->kind == HF_EXTRAS_BOOK) {
        for (i = 0; i < f->count; i++)
            if (any(plain + f->at + f->stride * i, f->size))
                return 1;
        return 0;
    }
    for (i = 0; i < slots_of(f); i++)
        if (rd16(plain + slot_at(f, f->first + i)) >= HF_EXTRAS_FIRST_NEW_ITEM)
            return 1;
    return 0;
}

static int has(u32 kind, const u8 *plain, u32 size)
{
    struct shape s;
    struct field f;
    u32 row;
    shape_of(kind, &s);
    if (plain == 0)
        return HF_EXTRAS_E_ARG;
    if (size != s.size)
        return HF_EXTRAS_E_SIZE;
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind && field_has(plain, &f))
            return 1;
    return 0;
}

int hf_extras_user_has(const u8 *user, u32 size) { return has(HF_EXTRAS_USER, user, size); }

int hf_extras_card_has(const u8 *card, u32 size) { return has(HF_EXTRAS_CARD, card, size); }

/* The newest of the images in (in_a, in_b): 0, 1, or HF_EXTRAS_NONE (none in) */
static int newest_of(const u8 *a, const u8 *b, int in_a, int in_b)
{
    if (in_a && in_b)
        return hf_extras_generation(b) > hf_extras_generation(a) ? 1 : 0;
    return in_a ? 0 : in_b ? 1 : HF_EXTRAS_NONE;
}

int hf_extras_pick_known(const u8 *a, u32 a_size, const u8 *b, u32 b_size, u32 kind, u32 tag, u32 tail, u32 has_any,
                         u32 played, u32 mark, const u8 *identity, u32 slot)
{
    int va = hf_extras_image_kind(a, a_size) == (int)kind, vb = hf_extras_image_kind(b, b_size) == (int)kind;
    int oa = va && hf_extras_owned_by(a, identity, slot), ob = vb && hf_extras_owned_by(b, identity, slot);
    int ma, mb, la, lb, xa, xb;
    if (oa || ob) {
        va = oa;
        vb = ob;
    }
    if (!va && !vb)
        return HF_EXTRAS_NONE;
    ma = va && rd32(a + HF_EXTRAS_TAG_AT) == tag;
    mb = vb && rd32(b + HF_EXTRAS_TAG_AT) == tag;
    if (ma || mb) {
        if (tail == 0)
            return newest_of(a, b, ma, mb);
        /* the one whose parent's tail is the file's (its own file), else not one whose parent's tail is another */
        la = ma && hf_extras_parent_tail(a) == tail;
        lb = mb && hf_extras_parent_tail(b) == tail;
        if (la || lb)
            return newest_of(a, b, la, lb);
        xa = ma && !(hf_extras_parent_tail(a) != 0 && hf_extras_parent_tail(a) != tail);
        xb = mb && !(hf_extras_parent_tail(b) != 0 && hf_extras_parent_tail(b) != tail);
        return xa || xb ? newest_of(a, b, xa, xb) : newest_of(a, b, ma, mb);
    }
    if (kind != HF_EXTRAS_USER)
        return newest_of(a, b, va, vb);
    if (hf_extras_whole_kind(mark) == HF_EXTRAS_KEEP_FLAGGED || hf_extras_whole_kind(mark) == HF_EXTRAS_LACKS) {
        ma = va && ((hf_extras_generation(a) ^ mark) & 0xFFFFu) == 0;
        mb = vb && ((hf_extras_generation(b) ^ mark) & 0xFFFFu) == 0;
        if (ma || mb)
            return newest_of(a, b, ma, mb);
    }
    if (hf_extras_whole_kind(mark) != 0)
        return newest_of(a, b, va, vb);
    /* a file with content: never one of this hunter's images of a later play time (the file is an earlier save put
     * back: what that image holds came from it, and the file holds it still) */
    if (has_any && (oa || ob)) {
        va = va && rd32(a + HF_EXTRAS_PLAY_TIME_IN) <= played;
        vb = vb && rd32(b + HF_EXTRAS_PLAY_TIME_IN) <= played;
        if (!va && !vb)
            return HF_EXTRAS_NONE;
    }
    /* not one whose parent is this very file (its own file never landed) */
    la = va && !(hf_extras_parent_tag(a) != 0 && hf_extras_parent_tag(a) == tag);
    lb = vb && !(hf_extras_parent_tag(b) != 0 && hf_extras_parent_tag(b) == tag);
    if (!la && !lb)
        return has_any ? HF_EXTRAS_NONE : newest_of(a, b, va, vb);
    /* nor, when another remains, one whose parent's tail is the file's (another game wrote over that parent) */
    ma = la && !(tail != 0 && hf_extras_parent_tail(a) == tail);
    mb = lb && !(tail != 0 && hf_extras_parent_tail(b) == tail);
    return ma || mb ? newest_of(a, b, ma, mb) : newest_of(a, b, la, lb);
}

int hf_extras_pick_file(const u8 *a, u32 a_size, const u8 *b, u32 b_size, u32 kind, const u8 *plain,
                        const u8 *identity, u32 slot)
{
    if (plain == 0)
        return HF_EXTRAS_E_ARG;
    if (kind != HF_EXTRAS_USER)
        return hf_extras_pick_known(a, a_size, b, b_size, kind, hf_extras_card_tag(plain), 0, 0, 0, 0, identity, slot);
    return hf_extras_pick_known(a, a_size, b, b_size, kind, hf_extras_user_tag(plain), hf_extras_tail_crc(plain),
                                has(HF_EXTRAS_USER, plain, HF_EXTRAS_USER_SIZE) == 1,
                                rd32(plain + HF_EXTRAS_PLAY_TIME_AT), hf_extras_whole_mark(plain), identity, slot);
}

static u32 count_items(u32 kind, const u8 *plain)
{
    struct field f;
    u32 row, i, n = 0;
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind && f.kind == HF_EXTRAS_ITEMS)
            for (i = 0; i < slots_of(&f); i++)
                n += rd16(plain + slot_at(&f, f.first + i)) >= HF_EXTRAS_FIRST_NEW_ITEM;
    return n;
}

static u32 count_flagged(const u8 *image, const struct shape *s)
{
    u32 k, n = 0, count = rd16(image + HF_EXTRAS_COUNTS_AT);
    for (k = 0; k < count; k++)
        n += rd16(entry_in(image, s, k)) >> 15;
    return n;
}

static void put_entry(u8 *e, u32 place, u32 item, u32 count)
{
    wr16(e, place);
    wr16(e + 2, item);
    wr16(e + 4, count);
}

/* What the split takes and counts */
struct taking { struct crc *crc; u32 items, cats; };

/* Field f moved from `plain` into `image`: its items become entries, its look words cats */
static void field_take(u8 *plain, u8 *image, const struct shape *s, const struct field *f, struct taking *t)
{
    u32 i, at, word;
    if (f->kind == HF_EXTRAS_ZONE) {
        copy(image + f->image_at, plain + f->at, f->size);
        if (f->at <= HF_EXTRAS_CARD_MARK_AT && HF_EXTRAS_CARD_MARK_AT - f->at < f->size &&
            hf_extras_card_marked(plain))
            zero(image + f->image_at + (HF_EXTRAS_CARD_MARK_AT - f->at), 4);     /* the card's mark: in no image */
        zero(plain + f->at, f->size);
    } else if (f->kind == HF_EXTRAS_MARK) {
        zero(plain + f->at, 4);
    } else if (f->kind == HF_EXTRAS_BITS) {
        word = rd32(plain + f->at);
        wr32(image + f->image_at, word & f->value);
        wr32(plain + f->at, word & ~f->value);
    } else if (f->kind == HF_EXTRAS_CATS) {
        for (i = 0; i < f->count; i++) {
            at = f->at + f->stride * i;
            word = rd32(plain + at + HF_EXTRAS_LOOK_AT);
            if (word != 0) {
                u8 *cat = cat_at(image, t->cats++);
                cat[0] = (u8)(f->first + i);
                wr32(cat + 4, fingerprint(t->crc, plain + at));
                wr32(cat + 8, word);
                zero(plain + at + HF_EXTRAS_LOOK_AT, 4);
            }
        }
    } else if (f->kind == HF_EXTRAS_BOOK) {
        for (i = 0; i < f->count; i++) {
            at = f->at + f->stride * i;
            if (any(plain + at, f->size)) {
                u8 *to = image + f->image_at + (f->size + 4) * i;
                copy(to, plain + at, f->size);
                wr32(to + f->size, book_crc(t->crc, plain, f, i));
                zero(plain + at, f->size);
            }
        }
    } else {
        for (i = 0; i < slots_of(f); i++) {
            at = slot_at(f, f->first + i);
            if (rd16(plain + at) >= HF_EXTRAS_FIRST_NEW_ITEM) {
                put_entry(entry_at(image, s, t->items++), f->first + i, rd16(plain + at), rd16(plain + at + 2));
                zero(plain + at, 4);
            }
        }
    }
}

static int split(u32 kind, u8 *plain, u32 size, u32 slot, const u8 *carry, u32 carry_size, u8 *image,
                 u32 image_size, u32 generation)
{
    struct shape s;
    struct field f;
    struct crc c;
    struct taking t;
    const u8 *identity;
    u32 taken, left = 0, k, j, row, count;
    shape_of(kind, &s);
    if (plain == 0 || image == 0 || slot > 0xFFu)
        return HF_EXTRAS_E_ARG;
    if (size != s.size || image_size < s.image_size)
        return HF_EXTRAS_E_SIZE;
    if (overlap(plain, size, image, s.image_size) ||
        (carry != 0 && carry != image && overlap(carry, carry_size, image, s.image_size)))
        return HF_EXTRAS_E_ARG;
    identity = plain + (kind == HF_EXTRAS_USER ? HF_EXTRAS_USER_IDENTITY_AT : HF_EXTRAS_CARD_IDENTITY_AT);
    crc_table(&c);
    if (carry != 0) {
        if (image_kind(carry, carry_size, &c) != (int)kind)
            return HF_EXTRAS_E_IMAGE;
        if (!hf_extras_owned_by(carry, identity, slot))
            return HF_EXTRAS_E_HUNTER;
        left = count_flagged(carry, &s);
    }
    taken = count_items(kind, plain);
    if (taken + left > s.capacity)
        return HF_EXTRAS_E_FULL;
    /* the left-overs first, to [taken, taken + left): in place, gathered to the start then moved up (back to front) */
    if (carry == image) {
        count = rd16(image + HF_EXTRAS_COUNTS_AT);
        for (k = 0, j = 0; k < count; k++)
            if (rd16(entry_in(image, &s, k)) & HF_EXTRAS_LEFT_OVER) {
                if (j != k)
                    copy(entry_at(image, &s, j), entry_in(image, &s, k), HF_EXTRAS_ENTRY_SIZE);
                j++;
            }
        for (k = left; taken != 0 && k-- > 0;)
            copy(entry_at(image, &s, taken + k), entry_in(image, &s, k), HF_EXTRAS_ENTRY_SIZE);
    } else if (carry != 0) {
        count = rd16(carry + HF_EXTRAS_COUNTS_AT);
        for (k = 0, j = taken; k < count; k++)
            if (rd16(entry_in(carry, &s, k)) & HF_EXTRAS_LEFT_OVER)
                copy(entry_at(image, &s, j++), entry_in(carry, &s, k), HF_EXTRAS_ENTRY_SIZE);
    }
    zero(image, s.entries_at);
    zero(entry_at(image, &s, taken + left), s.image_size - s.entries_at - HF_EXTRAS_ENTRY_SIZE * (taken + left));
    t.crc = &c;
    t.items = 0;
    t.cats = 0;
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind)
            field_take(plain, image, &s, &f, &t);
    wr32(image, s.magic);
    wr16(image + 4, HF_EXTRAS_VERSION);
    image[HF_EXTRAS_SLOT_AT] = (u8)slot;
    wr32(image + HF_EXTRAS_GENERATION_AT, generation);
    wr32(image + HF_EXTRAS_TAG_AT, kind == HF_EXTRAS_USER ? crc_of(&c, plain + HF_EXTRAS_DATA_AT,
                                                                   HF_EXTRAS_TAIL_AT - HF_EXTRAS_DATA_AT)
                                                          : crc_of(&c, plain + HF_EXTRAS_CARD_SETS_AT,
                                                                   HF_EXTRAS_CARD_SETS_SIZE));
    copy(image + HF_EXTRAS_IDENTITY_IN, identity, HF_EXTRAS_IDENTITY_SIZE);
    if (kind == HF_EXTRAS_USER) {
        copy(image + HF_EXTRAS_NAME_IN, plain + HF_EXTRAS_NAME_AT, HF_EXTRAS_NAME_SIZE);
        wr32(image + HF_EXTRAS_PLAY_TIME_IN, rd32(plain + HF_EXTRAS_PLAY_TIME_AT));
    }
    wr16(image + HF_EXTRAS_COUNTS_AT, taken + left);
    wr16(image + HF_EXTRAS_COUNTS_AT + 2, left);
    wr16(image + HF_EXTRAS_CATS_COUNT_AT, t.cats);
    wr32(image + HF_EXTRAS_CRC_AT, image_crc(&c, image, s.image_size));
    return (int)(taken + left);
}

int hf_extras_split_user(u8 *user, u32 size, u32 slot, const u8 *carry, u32 carry_size, u8 *image, u32 image_size,
                         u32 generation)
{
    return split(HF_EXTRAS_USER, user, size, slot, carry, carry_size, image, image_size, generation);
}

int hf_extras_split_card(u8 *card, u32 size, u32 slot, const u8 *carry, u32 carry_size, u8 *image, u32 image_size,
                         u32 generation)
{
    return split(HF_EXTRAS_CARD, card, size, slot, carry, carry_size, image, image_size, generation);
}

/* ---- join ------------------------------------------------------------------------------------------------------------ */

/* A little-endian number of n bytes (an OR zone's format) */
static u32 le(const u8 *p, u32 n)
{
    u32 v = 0;
    while (n-- > 0)
        v = v << 8 | p[n];
    return v;
}

/* Each block back to its card: at its own place while the record there still has the block's CRC; else (MH4U moved
 * the card: a delete moves every later card up one place) to the first record with that CRC; only into a zero block.
 * The records' CRCs only when a block waits (a block changes no record's CRC) */
static void book_join(u8 *plain, const u8 *image, const struct field *f, struct crc *c)
{
    u32 crcs[HF_EXTRAS_BOOK_CARDS];
    u8 known[HF_EXTRAS_BOOK_CARDS];
    u8 *mine = plain + f->at;
    const u8 *theirs = image + f->image_at;
    u32 i, j, count = f->count < HF_EXTRAS_BOOK_CARDS ? f->count : HF_EXTRAS_BOOK_CARDS, waiting = 0;
    for (i = 0; i < count; i++) {
        const u8 *from = theirs + (f->size + 4) * i;
        known[i] = 0;
        if (!any(from, f->size))
            continue;
        crcs[i] = book_crc(c, plain, f, i);
        known[i] = 1;
        if (rd32(from + f->size) != crcs[i])
            waiting++;
        else if (!any(mine + f->stride * i, f->size))
            copy(mine + f->stride * i, from, f->size);
    }
    if (waiting == 0)
        return;
    for (j = 0; j < count; j++)
        if (!known[j])
            crcs[j] = book_crc(c, plain, f, j);
    for (i = 0; i < count; i++) {
        const u8 *from = theirs + (f->size + 4) * i;
        if (!any(from, f->size) || rd32(from + f->size) == crcs[i])
            continue;
        for (j = 0; j < count; j++)
            if (crcs[j] == rd32(from + f->size) && !any(mine + f->stride * j, f->size)) {
                copy(mine + f->stride * j, from, f->size);
                break;
            }
    }
}

/* `marked`: the card file carries the "not joined" mark: the zone holding it takes the image's bytes when non-zero */
static void field_join(u8 *plain, const u8 *image, const struct field *f, struct crc *c, int marked)
{
    u8 *mine = plain + f->at;
    const u8 *theirs = image + f->image_at;
    u32 i, ours, its;
    if (f->kind == HF_EXTRAS_ZONE) {
        if (marked && f->at <= HF_EXTRAS_CARD_MARK_AT && HF_EXTRAS_CARD_MARK_AT - f->at < f->size &&
            any(theirs, f->size)) {
            copy(mine, theirs, f->size);            /* the game never had the image's: the image's */
        } else if (f->rule == HF_EXTRAS_OR) {
            ours = f->check_size ? le(mine + f->check_at, f->check_size) : 0;
            its = f->check_size ? le(theirs + f->check_at, f->check_size) : 0;
            if (ours != 0 && its != 0 && ours != its) {
                if (its > ours)
                    copy(mine, theirs, f->size);    /* another layout: the later one's whole, never mixed */
            } else {
                for (i = 0; i < f->size; i++)
                    mine[i] |= theirs[i];
            }
        } else if (f->rule == HF_EXTRAS_VALID) {
            if (!zone_valid(mine, f) && (zone_valid(theirs, f) || !any(mine, f->size)))
                copy(mine, theirs, f->size);
        } else if (!any(mine, f->size)) {
            copy(mine, theirs, f->size);
        }
    } else if (f->kind == HF_EXTRAS_BITS) {
        wr32(mine, rd32(mine) | (rd32(theirs) & f->value));
    } else if (f->kind == HF_EXTRAS_BOOK) {
        book_join(plain, image, f, c);
    }
}

/* Each look word back to its cat: the record of its index if it still has the cat's fingerprint, else the first
 * record with the fingerprint and no word; a cat that already wears a word keeps it; a cat not found loses it */
static void join_cats(u8 *plain, const u8 *image, struct crc *c)
{
    u32 records[HF_EXTRAS_CAT_CAPACITY], prints[HF_EXTRAS_CAT_CAPACITY];
    u8 done[HF_EXTRAS_CAT_CAPACITY];
    u32 i, k, cats = rd16(image + HF_EXTRAS_CATS_COUNT_AT);
    for (i = 0; i < HF_EXTRAS_CAT_CAPACITY; i++) {
        records[i] = record_at(i);
        prints[i] = fingerprint(c, plain + records[i]);
    }
    for (k = 0; k < cats; k++) {
        const u8 *cat = image + HF_EXTRAS_USER_CATS_AT + HF_EXTRAS_CAT_SIZE * k;
        u8 *look = plain + records[cat[0]] + HF_EXTRAS_LOOK_AT;
        done[k] = prints[cat[0]] == rd32(cat + 4);
        if (done[k] && rd32(look) == 0)
            copy(look, cat + 8, 4);
    }
    for (k = 0; k < cats; k++) {
        const u8 *cat = image + HF_EXTRAS_USER_CATS_AT + HF_EXTRAS_CAT_SIZE * k;
        if (done[k])
            continue;
        for (i = 0; i < HF_EXTRAS_CAT_CAPACITY; i++) {
            u8 *look = plain + records[i] + HF_EXTRAS_LOOK_AT;
            if (prints[i] == rd32(cat + 4) && rd32(look) == 0) {
                copy(look, cat + 8, 4);
                break;
            }
        }
    }
}

/* 1 if the item set of `place` holds a pair of `item` */
static int set_holds(const u8 *plain, const struct field *f, u32 place, u32 item)
{
    u32 i, first = group_first(f, place);
    for (i = 0; i < f->count; i++)
        if (rd16(plain + slot_at(f, first + i)) == item)
            return 1;
    return 0;
}

/* Entry e somewhere other than its own slot: onto the box's first stack of its item with room, else the box's first
 * empty slot (a box or pouch entry; the box is the slots the game shows); its set's first empty pair (an item set
 * pair). 1 if placed */
static int place_elsewhere(u8 *plain, u32 kind, const struct field *own, const u8 *e)
{
    struct field box;
    u32 i, at, item = rd16(e + 2), count = rd16(e + 4), first, shown, end;
    if (own->rule == HF_EXTRAS_SET) {
        /* only among the pairs of its own rows: an ammo row's (the first ones) or an item row's */
        first = group_first(own, place_of(e));
        if (place_of(e) - first < HF_EXTRAS_SET_AMMO_PAIRS) {
            i = 0;
            end = HF_EXTRAS_SET_AMMO_PAIRS;
        } else {
            i = HF_EXTRAS_SET_AMMO_PAIRS;
            end = own->count;
        }
        for (; i < end; i++) {
            at = slot_at(own, first + i);
            if (rd32(plain + at) == 0) {
                wr16(plain + at, item);
                wr16(plain + at + 2, count);
                return 1;
            }
        }
        return 0;
    }
    if (!box_field(kind, &box))
        return 0;
    shown = box_shown(plain, &box);
    for (i = 0; i < shown; i++) {
        at = slot_at(&box, box.first + i);
        if (rd16(plain + at) == item && rd16(plain + at + 2) + count <= HF_EXTRAS_MAX_STACK) {
            wr16(plain + at + 2, rd16(plain + at + 2) + count);
            return 1;
        }
    }
    for (i = 0; i < shown; i++) {
        at = slot_at(&box, box.first + i);
        if (rd32(plain + at) == 0) {
            wr16(plain + at, item);
            wr16(plain + at + 2, count);
            return 1;
        }
    }
    return 0;
}

/* The image after a join: its first `count` entries flagged left over exactly when not placed, nothing after them,
 * sealed; the rest of it as it is. Returns the left-overs */
static u32 reflag(u8 *image, const struct shape *s, u32 count, struct crc *c)
{
    u32 k, e, left = 0;
    for (k = 0; k < count; k++) {
        u8 *at = entry_at(image, s, k);
        e = rd16(at);
        if (e & PLACED) {
            wr16(at, e & HF_EXTRAS_PLACE & ~PLACED);
        } else {
            wr16(at, (e & HF_EXTRAS_PLACE) | HF_EXTRAS_LEFT_OVER);
            left++;
        }
    }
    zero(entry_at(image, s, count), s->image_size - s->entries_at - HF_EXTRAS_ENTRY_SIZE * count);
    wr16(image + HF_EXTRAS_COUNTS_AT, count);
    wr16(image + HF_EXTRAS_COUNTS_AT + 2, left);
    wr32(image + HF_EXTRAS_CRC_AT, image_crc(c, image, s->image_size));
    return left;
}

/* The image holding nothing: its header kept */
static void empty(u8 *image, const struct shape *s, struct crc *c)
{
    zero(image + HF_EXTRAS_HEADER_SIZE, s->image_size - HF_EXTRAS_HEADER_SIZE);
    wr16(image + HF_EXTRAS_COUNTS_AT, 0);
    wr16(image + HF_EXTRAS_COUNTS_AT + 2, 0);
    wr16(image + HF_EXTRAS_CATS_COUNT_AT, 0);
    wr32(image + HF_EXTRAS_CRC_AT, image_crc(c, image, s->image_size));
}

static void mark_placed(u8 *e) { wr16(e, rd16(e) | PLACED); }

/* The first `count` entries of the image into the file: pass 0, an item set pair its set already holds is skipped;
 * pass 1, every other entry whose own slot is empty (a box slot only if the game shows it); pass 2, the others in
 * order (place_elsewhere). Each entry put or skipped gets PLACED */
static void place(u8 *plain, u32 kind, u8 *image, const struct shape *s, u32 count)
{
    struct field f;
    u32 k, at, shown = 0;
    if (box_field(kind, &f))
        shown = box_shown(plain, &f);
    for (k = 0; k < count; k++) {
        u8 *e = entry_at(image, s, k);
        item_field(kind, place_of(e), &f);
        if (f.rule == HF_EXTRAS_SET && set_holds(plain, &f, place_of(e), rd16(e + 2)))
            mark_placed(e);
    }
    for (k = 0; k < count; k++) {
        u8 *e = entry_at(image, s, k);
        if (rd16(e) & PLACED)
            continue;
        item_field(kind, place_of(e), &f);
        at = slot_at(&f, place_of(e));
        if (rd32(plain + at) == 0 && (f.rule != HF_EXTRAS_BOX || place_of(e) - f.first < shown)) {
            copy(plain + at, e + 2, 4);
            mark_placed(e);
        }
    }
    for (k = 0; k < count; k++) {
        u8 *e = entry_at(image, s, k);
        if (rd16(e) & PLACED)
            continue;
        item_field(kind, place_of(e), &f);
        if (place_elsewhere(plain, kind, &f, e))
            mark_placed(e);
    }
}

static int join(u32 kind, u8 *plain, u32 size, const u8 *identity, u32 slot, u8 *image, u32 image_size)
{
    struct shape s;
    struct field f;
    struct crc c;
    u32 count, k, j, row, mark, tag = 0, generation;
    int marked;
    shape_of(kind, &s);
    if (plain == 0 || identity == 0 || image == 0 || slot > 0xFFu)
        return HF_EXTRAS_E_ARG;
    if (size != s.size)
        return HF_EXTRAS_E_SIZE;
    if (overlap(plain, size, image, image_size) || overlap(identity, HF_EXTRAS_IDENTITY_SIZE, image, image_size))
        return HF_EXTRAS_E_ARG;
    crc_table(&c);
    if (image_kind(image, image_size, &c) != (int)kind)
        return HF_EXTRAS_E_IMAGE;
    if (!hf_extras_owned_by(image, identity, slot))
        return HF_EXTRAS_E_HUNTER;
    count = rd16(image + HF_EXTRAS_COUNTS_AT);
    mark = kind == HF_EXTRAS_USER ? hf_extras_whole_mark(plain) : 0;
    if (mark != 0) {
        tag = crc_of(&c, plain + HF_EXTRAS_DATA_AT, HF_EXTRAS_TAIL_AT - HF_EXTRAS_DATA_AT);
        if (rd32(image + HF_EXTRAS_TAG_AT) == tag)
            mark = 0;                               /* rewritten by a join of this very file: joined again as it is */
        else if (hf_extras_whole_kind(mark) == HF_EXTRAS_LACKS && ((mark ^ hf_extras_generation(image)) & 0xFFFFu) == 0)
            mark = 0;                               /* the image the file lacks: joined as it is */
    }
    if (mark != 0) {
        generation = hf_extras_generation(image);
        if (!hf_extras_mark_covers(mark, generation) || hf_extras_whole_kind(mark) != HF_EXTRAS_KEEP_FLAGGED ||
            ((mark ^ generation) & 0xFFFFu) != 0) {
            empty(image, &s, &c);                   /* dropped: the file holds them */
            return hf_extras_mark_covers(mark, generation) ? HF_EXTRAS_WHOLE : HF_EXTRAS_WHOLE_NEWER;
        }
        /* "keep flagged": only the entries waiting (flagged) come back; the fields and cats are the file's */
        for (k = 0, j = 0; k < count; k++)
            if (rd16(entry_in(image, &s, k)) & HF_EXTRAS_LEFT_OVER) {
                if (j != k)
                    copy(entry_at(image, &s, j), entry_in(image, &s, k), HF_EXTRAS_ENTRY_SIZE);
                j++;
            }
        zero(image + HF_EXTRAS_HEADER_SIZE, s.entries_at - HF_EXTRAS_HEADER_SIZE);
        wr32(image + HF_EXTRAS_TAG_AT, tag);
        wr16(image + HF_EXTRAS_CATS_COUNT_AT, 0);
        place(plain, kind, image, &s, j);
        return (int)reflag(image, &s, j, &c);
    }
    marked = kind == HF_EXTRAS_CARD && hf_extras_card_marked(plain);
    for (row = 0; field_get(row, &f); row++)
        if (f.file == kind)
            field_join(plain, image, &f, &c, marked);
    if (marked)
        zero(plain + HF_EXTRAS_CARD_MARK_AT, 4);
    if (kind == HF_EXTRAS_USER)
        join_cats(plain, image, &c);
    place(plain, kind, image, &s, count);
    return (int)reflag(image, &s, count, &c);
}

int hf_extras_join_user(u8 *user, u32 size, u32 slot, u8 *image, u32 image_size)
{
    if (user == 0)
        return HF_EXTRAS_E_ARG;
    return join(HF_EXTRAS_USER, user, size, user + HF_EXTRAS_USER_IDENTITY_AT, slot, image, image_size);
}

int hf_extras_join_card(u8 *card, u32 size, const u8 *identity, u32 slot, u8 *image, u32 image_size)
{
    return join(HF_EXTRAS_CARD, card, size, identity, slot, image, image_size);
}
