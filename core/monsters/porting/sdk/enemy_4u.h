/* MH4U's monster engine, as the Alatreon port's C code sees it.
 *
 * Offsets are of the update's executable. Engine functions are resolved by name when the block is
 * linked (game/executable/blocks.py, GAME_SYMBOLS), so a source only declares what it calls. The port's
 * decompiled C includes em_api.h, which includes this header for MH4U.
 *
 * Build: tools/build/build_code_space.py.
 */
#ifndef ENEMY_4U_H
#define ENEMY_4U_H

#include "types.h"

/* ---- The object ---- */

#define ENEMY_SIZE         0x8D90  /* a species class: uEnemy plus the species pointer */
#define ENEMY_VTABLE       0x000
#define ENEMY_MOTION_NO    0x244   /* u16: layer 0's motion, 0xFFFF when it does not exist */
#define ENEMY_EM           0xE28   /* u8 *: the enemy work (it lies at 0xE30) */
#define ENEMY_SPECIES      0x8D88  /* species classes: pointer to their variables (= em) */
#define ENEMY_PART_COUNT   0xF8    /* u32: the model's parts (MH Generations 0xFC) */
#define ENEMY_UNIT_DELTA   0x014   /* f32: frames this unit moved on this frame (MH Generations 0x1C) */

static inline u8 *enemy_em(uEnemy *self) { return FIELD(u8 *, self, ENEMY_EM); }

/* ---- The enemy work em ---- */
#define EM_SPECIES_VARS    0x000   /* 0x140 bytes the species owns; uEnemy zeroes them */
#define EM_SPECIES_SIZE    0x140
#define EM_OLD_POS         0x150   /* vector3: the position before this frame's move (8 aligned accesses) */
/* Alatreon's own variables (MH Generations keeps 0x50 bytes in the object). Fatalis' methods, the
 * scaffold, use em+0x00...0x9F, so they go at the end of the species' bytes (G1). */
#define EM_ALATREON_VARS   0x0F0
/* A ported monster's own variables: Alatreon's place unless his header says otherwise before em_api.h (Mizutsune's
 * 0x80 bytes, em082.h) */
#ifndef EM_OWN_VARS
#define EM_OWN_VARS        EM_ALATREON_VARS
#endif
#define EM_ACT_STEP        0x144   /* u8: the current action's step */
#define EM_ACT_SUB         0x145   /* u8: a second step byte (130 aligned accesses in the species) */
#define EM_ACT_SUB2        0x146   /* u8: a third (21 aligned accesses) */
#define EM_MAP_NO          0x14B   /* u8: the map (the command table's 0x2A reads it, 0x9511B4) */
#define EM_AREA_NO         0x14C   /* u8 mAreaNo */
#define EM_RATE            0x160   /* vector3 mRate: the speed enemy_move_by_rate moves by */
#define EM_RATE_G          0x170   /* vector3 mRateG */
#define EM_POS             0x198   /* vector3 mPos */
#define EM_VEC             0x1A8   /* u32[3] mVec: 16-bit angles x, y, z */
#define EM_ANGLE_Y         0x1AC   /* u32 mVec.y: the facing angle (low 16 bits) */
#define EM_ID              0x1C0   /* u8: monster id */
#define EM_STATUS          0x1C8   /* u8 mStatus */
#define EM_STATUS_SUB      0x1C9   /* u8, after mStatus (Fatalis' slot 89 tests it) */
#define EM_ACT_ST          0x1CA   /* u8 mActSt */
#define EM_ACT_RAND        0x1D2   /* u16: a random value per action (the script opcode MH Generations'
                                    * 0x8E2E08 reads at this+0x6AD0, MH4U's 0x94A39C reads here) */
#define EM_CHAIN_OK        0x1D9   /* u8 (MH Generations this+0x6B00; 20 aligned accesses) */
#define EM_TIMER           0x1D4   /* f32 mTimer */
#define EM_HOMING_POS      0x218   /* vector3 mHomingPos[0] */
#define EM_HOMING_KIND     0x278   /* u8: the kind of target 0 (22 aligned accesses; 0x92D0D4's fields) */
#define EM_TURN_SPAN       0x238   /* f32: the turn enemy_turn_step works through (17 aligned accesses) */
#define EM_ACT_NO          0x1CB   /* u8 mActNo */
#define EM_HP              0x3E8   /* s32 mHpVital */
#define EM_FACTOR          0x404   /* f32, reset to 1 by 0x947258 (MH Generations em+0x37C, 0x8DFE30) */
#define EM_FLAGS           0x420   /* u32: set by enemy_flags_set, cleared by enemy_flags_clear */
#define EM_PARTS      0x42C   /* 6 bytes per part: u16 flags, u8 break level (enemy_break_level) */
#define EM_PROG_TYPE       0x7982  /* u8 prog_type */
#define EM_BITS            0x7E80  /* u8: enemy_bits_test tests it */

static inline u8 *enemy_vars(uEnemy *self) { return enemy_em(self) + EM_OWN_VARS; }

/* The variant of a ported monster's class (XX's byte this+0xA305: 0 the base, 4 a Deviant). MH4U keeps no such byte:
 * the answer comes from the monster's id (em+EM_ID), looked up in the base's variants block.
 *
 * What a base's header defines BEFORE em_api.h, only when its spec has variant_slots > 0 (a base without them defines
 * nothing: enemy_variant is the constant 0 and none of the code below is compiled in):
 *   ENEMY_VARIANTS      the block's symbol, `{base prefix}_variants` (em081_variants)
 *   ENEMY_VARIANT_LIST(X, kind, type)   one line per variant: `X(4, em081_v4, kind, type)`, n the variant, the second
 *                       argument the variant's data prefix (`{c_prefix}_v{n}`, spec.data_prefix). The own blocks are
 *                       `{data_prefix}_{kind}`: action_tune, visible_groups, rest, break_thresholds, climb.
 * The own-data getters (enemy_action_tune, enemy_visible_groups, enemy_rest, enemy_break_table, enemy_climb) answer the
 * variant's block, and the base's for variant 0 or a variant the list does not name. */
#ifdef ENEMY_VARIANTS
struct enemy_variant_row { u32 id, variant, attacks, motion9; };
extern const struct enemy_variant_row ENEMY_VARIANTS[];

/* The record of this monster's id, 0 for the base (its id is never in the block) */
static inline const struct enemy_variant_row *enemy_variant_row(uEnemy *self)
{
    const struct enemy_variant_row *row;
    u32 id = FIELD(u8, enemy_em(self), EM_ID);

    for (row = ENEMY_VARIANTS; row->id; row++)
        if (row->id == id)
            return row;
    return 0;
}

static inline u8 enemy_variant(uEnemy *self)
{
    const struct enemy_variant_row *row = enemy_variant_row(self);

    return row ? (u8)row->variant : 0;
}
#else
static inline u8 enemy_variant(uEnemy *self) { (void)self; return 0; }
#endif

/* ENEMY_VARIANT_GETTER(fn, base, kind, type) (with ENEMY_VARIANT_LIST only): `fn(self)` is the pointer to the variant's
 * own `kind` block, else `base` (the base's block). A switch on the variant is the pointer table: it needs no data
 * relocation in the code block. A base with no list gets `fn(self)` as a macro for `base` (below, at each getter), so
 * its code is what it was before variants. */
#ifdef ENEMY_VARIANT_LIST
#define EVD_DECL(n, p, kind, type) extern type p##_##kind[];
#define EVD_CASE(n, p, kind, type) case n: return p##_##kind;
#define ENEMY_VARIANT_GETTER(fn, base, kind, type)                                  \
    ENEMY_VARIANT_LIST(EVD_DECL, kind, type)                                        \
    static inline type *fn(uEnemy *self)                                            \
    {                                                                               \
        switch (enemy_variant(self)) {                                              \
        ENEMY_VARIANT_LIST(EVD_CASE, kind, type)                                    \
        default:                                                                    \
            break;                                                                  \
        }                                                                           \
        return (base);                                                              \
    }
#endif

/* XX numbers a Deviant's second attack file from 1000 (0x3E8); its records follow the first file's in the Deviant's
 * data, so number n is record `attacks + n - 1000` (the variants record's `attacks`: the first file's count).
 * MH4U's enemy_set_record2 (0x933144) indexes the records with no bound (the index only scales by 40 into the
 * records at etd+0x68), so the width is the full u32. A base without variants passes the number on. */
#define ENEMY_ATTACK_SECOND_FILE 1000
static inline u32 enemy_attack_index(uEnemy *self, u32 n)
{
#ifdef ENEMY_VARIANTS
    if (n >= ENEMY_ATTACK_SECOND_FILE) {
        const struct enemy_variant_row *row = enemy_variant_row(self);

        return row ? row->attacks + (n - ENEMY_ATTACK_SECOND_FILE) : 0;
    }
#endif
    (void)self;
    return n;
}

/* XX's quest_special_level (0x895564, (sQuest) -> level): the quest's level for the Deviant's numbers. MH4U has no
 * such function: the level is a byte the quest task writes per new quest, in the block `quest_special_levels`:
 * records of two u16, (quest id, level), ended by id 0. The quest id is `*quest manager + 0xAD50` (a u16: the game
 * keeps it in a word and uses its low half). Every other quest answers 0. */
#define QUEST_ID_4U 0xAD50
#ifdef ENEMY_VARIANTS
extern const u16 quest_special_levels[];

static inline u32 quest_special_level(void *manager)
{
    const u16 *record;
    u16 id = FIELD(u16, manager, QUEST_ID_4U);

    for (record = quest_special_levels; record[0]; record += 2)
        if (record[0] == id)
            return record[1];
    return 0;
}
#else
/* a base with no variants block: the stand-in, 0 */
static inline u32 quest_special_level(void *manager) { (void)manager; return 0; }
#endif

/* The fields em_api.h names, as lvalues */
#define enemy_act_st(self)     FIELD(u8, enemy_em(self), EM_ACT_ST)
#define enemy_act_no(self)     FIELD(u8, enemy_em(self), EM_ACT_NO)
#define enemy_act_rand(self)   FIELD(u16, enemy_em(self), EM_ACT_RAND)
#define enemy_chain_ok(self)   FIELD(u8, enemy_em(self), EM_CHAIN_OK)
#define enemy_factor(self)     FIELD(float, enemy_em(self), EM_FACTOR)
#define enemy_act_step(self)   FIELD(u8, enemy_em(self), EM_ACT_STEP)
#define enemy_act_sub(self)    FIELD(u8, enemy_em(self), EM_ACT_SUB)
#define enemy_act_sub2(self)   FIELD(u8, enemy_em(self), EM_ACT_SUB2)
#define enemy_status_sub(self) FIELD(u8, enemy_em(self), EM_STATUS_SUB)
#define enemy_prog_type(self)  FIELD(u8, enemy_em(self), EM_PROG_TYPE)
#define enemy_status(self)     FIELD(u8, enemy_em(self), EM_STATUS)
#define enemy_bits(self)       FIELD(u8, enemy_em(self), EM_BITS)
#define enemy_part_flags(self, n) FIELD(u16, enemy_em(self), EM_PARTS + 6 * (n))
#define enemy_unit_delta(self) FIELD(float, self, ENEMY_UNIT_DELTA)
#define enemy_rate(self)       ((float *)(enemy_em(self) + EM_RATE))
#define enemy_rate_g(self)     ((float *)(enemy_em(self) + EM_RATE_G))
#define enemy_pos(self)        ((float *)(enemy_em(self) + EM_POS))
#define enemy_old_pos(self)    ((const float *)(enemy_em(self) + EM_OLD_POS))
#define enemy_turn_span(self)  FIELD(float, enemy_em(self), EM_TURN_SPAN)
#define enemy_vec(self)        ((u32 *)(enemy_em(self) + EM_VEC))
#define enemy_homing_pos(self) ((float *)(enemy_em(self) + EM_HOMING_POS))
#define enemy_homing_kind(self) FIELD(u8, enemy_em(self), EM_HOMING_KIND)

/* His move this frame: MH Generations' and XX's em+0x318 (the turn's start body, 0x8D6BEC / XX 0x8C6190, clears it;
 * 0x8BE118 adds to it), MH4U's em+0x3A0: MH4U's start body (0x93E7E4) clears it and its step body (0x92DD04) takes
 * its dot product with the heading from the span where XX's does */
#define EM_TURN_MOVE       0x3A0   /* f32[4] */
#define EM_TURN_YAW        0x3B0   /* u32: the yaw the turn's mode flag 8 turns toward (XX em+0x328) */
#define EM_TURN_MODE       0x3B4   /* u16: the turn's mode (XX em+0x32C) */
static inline const float *enemy_push_vec(uEnemy *self)
{
    return (const float *)(enemy_em(self) + EM_TURN_MOVE);
}
#define enemy_angle_y(self)    FIELD(u32, enemy_em(self), EM_ANGLE_Y)
#define enemy_timer(self)      FIELD(float, enemy_em(self), EM_TIMER)

/* The game's main object (0x1057194 holds it): +0x5C is the frames this frame lasted */
extern u8 *game_main;
#define game_frame_delta()     FIELD(float, game_main, 0x5C)

/* Fields only MH Generations' base class has: a write goes nowhere (G1) */
#define enemy_gen_9ec8(self)   (*((void)(self), &(u8){0}))
#define enemy_gen_a03a(self)   (*((void)(self), &(u8){0}))

/* Action states */
#define ACT_IDLE           0
#define ACT_REACTION       10      /* 10/7: the death fall */
#define ACT_DEAD           11

/* ---- Virtual methods ---- */
#define VTABLE_SLOTS       97
#define SLOT_MOTION_NO     33      /* u32 (uEnemy *): current motion number */
#define SLOT_SPECIES_INIT  39      /* first frame */
#define SLOT_SPECIES_UPDATE 40     /* every frame */
#define SLOT_ACTION        44      /* every frame: run the current action */
#define SLOT_CHOOSE_ACTION 46      /* (uEnemy *, u8 *st, u8 *no) */
#define SLOT_END_ACTION    89      /* back to the idle action */

static inline void *enemy_method_at(uEnemy *self, u32 slot)
{
    return FIELD(void **, self, ENEMY_VTABLE)[slot];
}

static inline u32 enemy_motion_no(uEnemy *self)
{
    return ((u32 (*)(uEnemy *))enemy_method_at(self, SLOT_MOTION_NO))(self);
}

static inline void enemy_end_action(uEnemy *self)
{
    ((enemy_method)enemy_method_at(self, SLOT_END_ACTION))(self);
}

/* MH Generations' out-of-line call of the end of the action (0x8DF264): MH4U's species call the slot */
static inline void enemy_end_action_call(uEnemy *self)
{
    enemy_end_action(self);
}

/* ---- Engine functions ---- */

/* uEnemy's constructor, 0x955FF4: what the factory passes on (id, sub-id, a, set id, slot). */
uEnemy *uEnemy_construct(uEnemy *self, u32 id, u32 sub, u32 a, u32 set_id, u32 slot);

/* setStatus, 0x9167EC: mStatus and its parameters (0 ground). */
void enemy_set_status(uEnemy *self, u32 status);

/* Whether the current motion has finished (bit 2 of this+0x246), 0xB05DF4. */
u32 enemy_motion_ended(uEnemy *self);

/* Model part `n` (this+0xF4 holds them), 0x1A4814. */
void *enemy_part(uEnemy *self, u32 n);

/* ---- MH Generations' functions MH4U takes differently, or lacks (em_api.h) ---- */

/* MH4U's base class applies no mesh groups (Tigrex's MH4U init names none, its MH Generations one does): the emd's
 * part rows with condition 0 say the same (em_data_convert.eye_rows, Visibility.eyes), so nothing to do. */
static inline void enemy_set_material_anims(uEnemy *self, s32 normal, s32 alt, s32 special)
{
    (void)self, (void)normal, (void)alt, (void)special;
}

/* Start record `n` of the unit's records, 0x94E39C. */
void enemy_record_start_4u(uEnemy *self, u32 n, u32 flags, const float *pos);

/* MH Generations' 0x8EB070 also stores a tag byte, which MH4U's records do not have, and ends in 0x8DD2D0: record
 * 900 of his shells' PEL, which a build with the effect player asks (proof/hook_4u.c proof_4u_cut). */
#ifdef PROOF_PLAYER
void proof_4u_cut(void *monster, u32 n, u32 flags);
#endif
static inline void enemy_record_start(uEnemy *self, u32 n, u32 flags, u32 tag, const float *pos)
{
    (void)tag;
    enemy_record_start_4u(self, n, flags, pos);
#ifdef PROOF_PLAYER
    proof_4u_cut(self, n, flags);
#endif
}

/* MH4U's 0x93457C, which MH Generations' 0x8CDF88 is with one more argument. */
ENGINE_VFP void enemy_owner_request_4u(uEnemy *self, u32 a, u32 b, float value);

static inline void enemy_owner_request(uEnemy *self, u32 a, u32 b, u32 c, float value)
{
    (void)c;
    enemy_owner_request_4u(self, a, b, value);
}

/* MH Generations' 0x8BC4E4 reads the motion's speed (this+0x2A4); MH4U has no such function, and its
 * enemy_motion_curve reads the speed at this+0x29C where MH Generations' reads this+0x2A4. */
static inline float enemy_motion_rate(uEnemy *self)
{
    return FIELD(float, self, 0x29C);
}

/* MH Generations' 0x8B4598: MH4U's species add a scaled vector inline. */
static inline void enemy_vec_add_scaled(uEnemy *self, float *v, const float *w, float k)
{
    (void)self;
    v[0] += w[0] * k;
    v[1] += w[1] * k;
    v[2] += w[2] * k;
}

/* ---- Shells ----
 * MH Generations builds a shell from a setup parameter object (enemy_gen.h). MH4U builds uShell<n> by
 * number from a record (0x660E88), and each kind of record has a wrapper, which the species call with the
 * shell manager. A record's sub-kind picks the attack's data, numbered across the game (Crimson Fatalis'
 * fireballs are uShell001's 0x38 and 0x39), and its last number an attack (0xFFFF: none, as in MH
 * Generations' setup parameters). Aligned launches pair the setup parameters with MH4U's shells: base 00
 * with uShell001, 01 with uShell005, 02 with uShell008. Base 11 shares base 01's setup parameter, and no
 * other monster uses base 41: its rains go to Fatalis' shells at points (uShell029). The sub-kinds and
 * records are MH4U's own launches' (Crimson Fatalis, Basarios, Kushala), standing in until his shell data
 * (the rShell parameters of kinds 0xB4...0xB8) is converted; the variant is not passed on. */
extern u8 *shell_manager_4u;

/* uShell001's info: where it starts (an owner's joint and an offset from it) and its turn */
typedef struct {
    u32 joint;                  /* 0xFF: none */
    u32 unused;
    float offset[4];
    u8 b18;
    u8 pad;
    u16 turn_x, turn_y;         /* added to the owner's mVec.x and .y */
    u16 pad2;
} shell_info_4u;

#define SHELL_ATTACK_NONE_4U   0xFFFF

void shell_launch_4u_001(u8 *manager, uEnemy *owner, const shell_info_4u *info, u32 sub, u32 attack);
ENGINE_VFP void shell_launch_4u_005(u8 *manager, uEnemy *owner, const float *pos, u32 sub, u32 attack,
                                    float scale);
void shell_launch_4u_008(u8 *manager, uEnemy *owner, u32 sub, const float *vec);
void shell_launch_4u_029(u8 *manager, u32 a, uEnemy *owner, u32 b, const float *pos, u32 area, u32 attack);

/* The zero point MH Generations' shells start from (its MtVector3 zero) */
static const float vec3_zero_4u[4];
#define vec3_zero()            vec3_zero_4u

/* hook: the product (src/alatreon.c: his classes and his shell files; src/mhgen_port.c, the shared block: the effect
 * player and the port's shell framework) launches his kinds as his own classes on the port's sShell, with MH Generations' setup parameters
 * (em050/shells.c, MH4U's side), registered with it (proof/hook_4u.c). The probes (src/probe_class.c, with the
 * player or not) carry no shell files and keep the stand-ins below, which their telemetry counts: it renames them
 * (its #define of shell_launch_4u_001), which is what tells their build apart. */
#if defined(PROOF_PLAYER) && !defined(shell_launch_4u_001)
#define SHELLS_ON_PORT 1
#endif

#ifdef SHELLS_ON_PORT
void shell_launch_00(uEnemy *self, u32 kind, u32 n);
void shell_launch_01(uEnemy *self, u32 kind, u32 n, const float *pos);
void shell_launch_02(uEnemy *self, u32 kind, u32 n);
void shell_launch_41(uEnemy *self, u32 kind, u32 n, const float *pos);
u32 proof_4u_shell_register(void *monster, u32 kind);
int proof_4u_shell_registered(void *monster, u32 kind);
#else
/* Base 00 (0xB4): uShell001, as Crimson Fatalis' fireball (0x89E788: joint 3, sub-kind 0x38, 0x39 for
 * its second kind) */
static inline void shell_launch_00(uEnemy *self, u32 kind, u32 n)
{
    shell_info_4u info = {3, 0, {0.0f, -91.6f, 132.8f, 0.0f}, 0, 0, 0, 0, 0};

    (void)kind, (void)n;
    shell_launch_4u_001(shell_manager_4u, self, &info, 0x38, SHELL_ATTACK_NONE_4U);
}

/* Base 01 and 11 (0xB5, 0xB7): uShell005 at `pos`, as Basarios' (0x7F3850, sub-kind 1; the scale is
 * its caller's, 1 here) */
static inline void shell_launch_01(uEnemy *self, u32 kind, u32 n, const float *pos)
{
    (void)kind, (void)n;
    shell_launch_4u_005(shell_manager_4u, self, pos, 1, SHELL_ATTACK_NONE_4U, 1.0f);
}

/* Base 02 (0xB6, his dives): uShell008, as Kushala's in the dive its base 02 shell pairs with (0x7CE7A4,
 * sub-kind 0, the vector (0, -60, 60)) */
static inline void shell_launch_02(uEnemy *self, u32 kind, u32 n)
{
    static const float vec[4] = {0.0f, -60.0f, 60.0f, 0.0f};

    (void)kind, (void)n;
    shell_launch_4u_008(shell_manager_4u, self, 0, vec);
}

/* Base 41 (0xB8, the rains): uShell029 at `pos`, as Crimson Fatalis' shells at points around his target
 * (0x89E3B0: 1, 0, his area) */
static inline void shell_launch_41(uEnemy *self, u32 kind, u32 n, const float *pos)
{
    (void)kind, (void)n;
    shell_launch_4u_029(shell_manager_4u, 1, self, 0, pos, FIELD(u8, enemy_em(self), EM_AREA_NO),
                        SHELL_ATTACK_NONE_4U);
}
#endif

/* Whether the quest runs in a network session. MH Generations
 * keeps the flag in its quest manager (+0x7D4, 0xA9D1C4), MH4U in its game control (+0x5D, 0x2B5AC8):
 * both games' monster network sync (MH Generations 0x8B414C, MH4U 0x917E84) tests it first. */
extern u8 *game_control_4u;
s32 game_online_4u(u8 *control);
static inline s32 quest_value_7d4(void) { return game_online_4u(game_control_4u); }

/* MH Generations' 0x8AA1E8, as Fatalis' init does it inline (0x893E1C). */
static inline void *enemy_find_part(uEnemy *self, u32 kind, u32 *index)
{
    u32 n = FIELD(u32, self, ENEMY_PART_COUNT);
    for (u32 i = 0; i < n; i++) {
        void *part = enemy_part(self, i);
        if (part && (FIELD(u32, part, 0x18) << 2) >> 24 == kind) {
            if (index)
                *index = i;
            return part;
        }
    }
    return 0;
}

/* ---- R4: slot 122 ---- */

/* MH Generations' this+0xF20, which its 0x8B6B00 sets to 1 (MH4U's 0xB05184, 20 of 20 votes) */
#define enemy_timer_f20(self)  FIELD(float, self, 0xD30)

/* MH Generations' 0x8AA300 counts down by `rate` times the unit's delta; MH4U's 0xB0709C by the delta
 * alone, and sets the timer to 0 when it runs out. Written here as MH Generations does it. */
static inline u32 enemy_timer_down(uEnemy *self, float *t, float rate)
{
    if (*t <= 0.0f) {
        *t = 0.0f;
        return 1;
    }
    *t -= rate * enemy_unit_delta(self);
    return *t <= 0.0f;
}

/* MH4U's 0x910C6C, which MH Generations' 0x8AF7D8 is with one more argument (0 in Alatreon's calls). */
void enemy_joint_effect_4u(uEnemy *self, s32 joint, u32 kind);

static inline void enemy_joint_effect(uEnemy *self, s32 joint, u32 kind, u32 p4)
{
    (void)p4;
    enemy_joint_effect_4u(self, joint, kind);
}

/* MH Generations' effect request (0x8A1BF4, through uFestaChar's slots), for the angry breath its engine
 * plays for every monster; Alatreon turns that off and requests his own, records 0x460 / 0x461 of his body's
 * effect list. MH4U has no such request: a monster's motion effect component
 * (this+0xC78) plays the records of its two MEFs, the second holding ids 2000-8999. His MEFs hold his records under
 * their ids, and this plays one as a motion event
 * would; a host's MEF without it plays nothing. */
#define ENEMY_MOTION_EFFECTS 0xC78
#define MEF_FIRST_OF_SECOND  2000
#define MEF_IDS_OF_SECOND    7000
void *mef_find_4u(void *mef, u32 id);
void mef_play_4u(u8 *component, const void *record, u32 id);

/* hook: in a build with MH Generations' effect player (src/probe_fx.c), a monster it plays for (proof_fx_on)
 * requests through it, as MH Generations' 0x8A1BF4 does (kind 2, the shells' PEL); any other one through its
 * MEF */
#ifdef PROOF_PLAYER
int proof_fx_on(uEnemy *self);
void *proof_4u_effect_request(void *monster, u32 kind, u32 id);
u32 *proof_fx_motion_bits(uEnemy *self);
u32 proof_4u_mood_bits(void *monster);
#endif

/* MH Generations' 0x8A1BF4 itself: the player's (proof/hook_4u.c builds the request the monster keeps at
 * +0x9EE0 there); nothing in a build without it */
static inline void *gen_effect_request(uEnemy *self, u32 kind, u32 id, void *request)
{
    (void)request;
#ifdef PROOF_PLAYER
    return proof_4u_effect_request(self, kind, id);
#else
    (void)self, (void)kind, (void)id;
    return 0;
#endif
}

static inline void enemy_effect_request(uEnemy *self, u32 id)
{
    u8 *component = (u8 *)self + ENEMY_MOTION_EFFECTS;
    void *mef = FIELD(void *, component, id - MEF_FIRST_OF_SECOND < MEF_IDS_OF_SECOND ? 0xC : 8);
    u8 *record;

#ifdef PROOF_PLAYER
    if (proof_fx_on(self)) {               /* hook */
        gen_effect_request(self, 2, id, 0);
        return;
    }
#endif
    record = mef ? mef_find_4u(mef, id) : 0;
    if (record)
        mef_play_4u(component, record + 8, id);
}

/* MH Generations' shell manager keeps an owner per kind and loads the kind's resource (0x923C74). MH4U's
 * keeps no such list: its species launch without registering. The port's
 * sShell does (hook: the product, SHELLS_ON_PORT; proof/hook_4u.c). */
static inline void shell_register(uEnemy *self, u32 kind)
{
#ifdef SHELLS_ON_PORT
    proof_4u_shell_register(self, kind);
#else
    (void)self, (void)kind;
#endif
}

/* ---- R4b: slots 124 and 77, and the class (em_api.h) ---- */

/* MH Generations' uFestaEnemy constructor takes no arguments. MH4U's factory passes its own to uEnemy's
 * (0x955FF4); then the species points this+0x8D88 at em and clears em's first bytes (what Fatalis'
 * constructor, 0x89F12C, does that is not Fatalis'; monsters/porting/probe_class.c own_construct). */
static inline uEnemy *enemy_construct(uEnemy *self, u32 id, u32 sub, u32 a, u32 set_id, u32 slot)
{
    u8 *em;
    u32 i;

    self = uEnemy_construct(self, id, sub, a, set_id, slot);
    em = enemy_em(self);
    FIELD(u8 *, self, ENEMY_SPECIES) = em;
    for (i = 0; i < EM_SPECIES_SIZE; i++)
        em[i] = 0;
    return self;
}

/* A DTI's allocator, 0x1076CC (MH Generations' 0x11E190: the same code). */
void *dti_allocator(const void *dti);
extern u8 enemy_class_dti[];

/* MH Generations has an operator delete for each module class (0x8F2C10); MH4U's uEnemy deleting
 * destructor frees inline (0x956154): its DTI's allocator, slot 14. */
static inline void enemy_class_free(void *p)
{
    void *allocator = dti_allocator(enemy_class_dti);

    ((void (*)(void *, void *))FIELD(void **, allocator, 0)[14])(allocator, p);
}

/* MH Generations applies groups of meshes in code (0x8AA25C); MH4U draws meshes by the emd part rows
 * (0x948378), which monsters/porting/em_data_convert.py writes from em050/visibility.py: nothing to do, for a monster whose
 * rows say it all (Alatreon). Mizutsune's rest is no row condition (em082/visibility.py): his build applies his
 * groups as MH Generations does, to the same bits (a mesh number's bit at this+0x108, MH Generations' this+0x10C,
 * which the rows also write: 0x942900), from a table of his groups (ENEMY_VISIBLE_GROUPS, before em_api.h): the
 * count of groups, then VISIBLE_GROUP_ENTRIES (number, drawn) byte pairs per group, a number of 0xFF ending one
 * (em082/visibility.py group_table). */
#define ENEMY_MESH_BITS        0x108
#ifndef ENEMY_VISIBLE_GROUP_ENTRIES
#define ENEMY_VISIBLE_GROUP_ENTRIES 10  /* a monster whose groups are longer defines it before em_api.h */
#endif
#define VISIBLE_GROUP_ENTRIES  ENEMY_VISIBLE_GROUP_ENTRIES
#ifdef ENEMY_VISIBLE_GROUPS
extern const u8 ENEMY_VISIBLE_GROUPS[];
/* A variant whose table is wider than the base's: the base's header defines ENEMY_VARIANT_GROUP_ENTRIES(variant), the
 * pairs per group of that variant's table (spec.OwnData.group_entries), before em_api.h (Mizutsune: 10, Soulseer: 16) */
#if defined(ENEMY_VARIANT_GROUP_ENTRIES) && defined(ENEMY_VARIANT_LIST)
#define enemy_group_entries(self) ((u32)ENEMY_VARIANT_GROUP_ENTRIES(enemy_variant(self)))
#else
#define enemy_group_entries(self) ((u32)VISIBLE_GROUP_ENTRIES)
#endif
#ifdef ENEMY_VARIANT_LIST
ENEMY_VARIANT_GETTER(enemy_visible_groups, ENEMY_VISIBLE_GROUPS, visible_groups, const u8)
#else
#define enemy_visible_groups(self) ENEMY_VISIBLE_GROUPS
#endif

static inline void enemy_set_visible_group(uEnemy *self, s32 group)
{
    u32 width = enemy_group_entries(self);
    const u8 *entry = enemy_visible_groups(self) + 1 + 2 * width * group;
    u32 *bits;
    u32 i, n;

    if (group < 0 || group >= enemy_visible_groups(self)[0])
        return;
    for (i = 0; i < width && entry[2 * i] != 0xFF; i++) {
        n = entry[2 * i];
        bits = &FIELD(u32, self, ENEMY_MESH_BITS + 4 * (n >> 5));
        *bits = (*bits & ~(1u << (n & 0x1F))) | ((u32)(entry[2 * i + 1] != 0) << (n & 0x1F));
    }
}
#else
static inline void enemy_set_visible_group(uEnemy *self, s32 group)
{
    (void)self, (void)group;
}
#endif

/* MH Generations' this+0xF74 and its slot 77: MH4U's motion start (0xB07B20, the counterpart of MH
 * Generations' 0x8A997C) clears no such bits and calls no slot. A write goes nowhere. */
#ifdef PROOF_PLAYER
/* hook: with the player, the side's bits (src/probe_fx.c calls em050_motion_bits only for a monster with a
 * side), which uFestaEnemy's slot 77 (0x8A30A8) gives the mood's bits first */
#define enemy_motion_bits(self) (*proof_fx_motion_bits(self))

static inline void enemy_motion_bits_base(uEnemy *self, u32 motion)
{
    (void)motion;
    enemy_motion_bits(self) |= proof_4u_mood_bits(self);
}
#else
#define enemy_motion_bits(self) (*((void)(self), &(u32){0}))

static inline void enemy_motion_bits_base(uEnemy *self, u32 motion)
{
    (void)self, (void)motion;
}
#endif

/* ---- R6: his shells' classes (em050/shell_methods.c) ----
 * MH4U has no shell framework of MH Generations': his classes run on the port's (proof/shell_*.c, which keeps MH
 * Generations' layout of the shell object). Each name enemy_gen.h gives the framework is here the port's function
 * or data of the same MH Generations original (proof/gen_symbols.py), declared as proof/proof.h declares it; MH4U's
 * build links them in with his module (em050/pairs.py PORT_SHELLS): the product builds his classes in his block
 * (src/alatreon.c) and calls them in the shared one (src/mhgen_port.c: the player's sources and the framework's). */
typedef struct uShell uShell;
#define SHELL_SLOT_END     80      /* (uShell *, u32 now): the shell ends; `now` also removes it */

static inline void shell_end(uShell *self, u32 now)
{
    ((void (*)(uShell *, u32))FIELD(void **, self, 0)[SHELL_SLOT_END])(self, now);
}

/* The getters (proof/shell_getters.c: 0xAFCA94-0xAFCFC8) */
u32 proof_shell_variant(u8 *self);
void *proof_shell_owner(u8 *self);
u8 *proof_shell_param_effect(u8 *self, u32 k, s32 v);
s32 proof_shell_param_hit(u8 *self, u32 k);
ENGINE_VFP float proof_shell_param_float(u8 *self, u32 k, s32 v);
s32 proof_shell_param_int(u8 *self, u32 k, s32 v);
s32 proof_shell_param_sound(u8 *self, u32 k);
ENGINE_VFP float proof_shell_common_float(u8 *self, u32 k);
const float *proof_shell_param_vec(u8 *self, u32 k, s32 v);
u32 proof_shell_owner_alive(u8 *self);

static inline u32 shell_variant(uShell *self) { return proof_shell_variant((u8 *)self); }
static inline uEnemy *shell_owner(uShell *self) { return proof_shell_owner((u8 *)self); }
static inline u32 shell_owner_alive(uShell *self) { return proof_shell_owner_alive((u8 *)self); }
/* An effect entry is the address of its pair (list, unique id), which his classes keep in a word of the base */
static inline s32 shell_param_effect(uShell *self, u32 i, s32 variant)
{
    return (s32)proof_shell_param_effect((u8 *)self, i, variant);
}
static inline s32 shell_param_0c(uShell *self, u32 i) { return proof_shell_param_sound((u8 *)self, i); }
static inline s32 shell_param_10(uShell *self, u32 i) { return proof_shell_param_hit((u8 *)self, i); }
static inline s32 shell_param_int(uShell *self, u32 i, s32 variant)
{
    return proof_shell_param_int((u8 *)self, i, variant);
}
static inline float shell_param_float(uShell *self, u32 i, s32 variant)
{
    return proof_shell_param_float((u8 *)self, i, variant);
}
static inline const float *shell_param_vec(uShell *self, u32 i, s32 variant)
{
    return proof_shell_param_vec((u8 *)self, i, variant);
}
static inline float shell_file_float(uShell *self, u32 i) { return proof_shell_common_float((u8 *)self, i); }

/* The bases' constructors and destructors (proof/shell_base*.c), and uShellEnemy's destructor: 0x991F74, uShell's
 * (0x991F70, uShellEnemy's slot 0, is a nop before it) */
u8 *proof_shell00_init(u8 *self);
u8 *proof_shell01_init(u8 *self);
u8 *proof_shell02_init(u8 *shell);
u8 *proof_shell11_init(u8 *self);
u8 *proof_shell41_init(u8 *shell);
u8 *proof_shell00_fini(u8 *self);
u8 *proof_shell01_fini(u8 *self);
u8 *proof_shell41_fini(u8 *shell);
u8 *proof_shell_fini(u8 *self);
extern void *const proof_shell02_vtable[];
extern const u8 proof_shell11_vtable[];

static inline uShell *gen_shell_base00_ctor(uShell *self) { return (uShell *)proof_shell00_init((u8 *)self); }
static inline uShell *gen_shell_base01_ctor(uShell *self) { return (uShell *)proof_shell01_init((u8 *)self); }
static inline uShell *gen_shell_base02_ctor(uShell *self) { return (uShell *)proof_shell02_init((u8 *)self); }
static inline uShell *gen_shell_base11_ctor(uShell *self) { return (uShell *)proof_shell11_init((u8 *)self); }
static inline uShell *gen_shell_base41_ctor(uShell *self) { return (uShell *)proof_shell41_init((u8 *)self); }
static inline uShell *gen_shell_base00_dtor(uShell *self) { return (uShell *)proof_shell00_fini((u8 *)self); }
static inline uShell *gen_shell_base01_dtor(uShell *self) { return (uShell *)proof_shell01_fini((u8 *)self); }
static inline uShell *gen_shell_base41_dtor(uShell *self) { return (uShell *)proof_shell41_fini((u8 *)self); }
static inline uShell *gen_shell_enemy_dtor(uShell *self) { return (uShell *)proof_shell_fini((u8 *)self); }
#define gen_shell_base02_vtable  proof_shell02_vtable
#define gen_shell_base11_vtable  proof_shell11_vtable

/* Base 00's slot 77 and its effect at a point (the pair's address, 0 for none), base 02's slot 84 (the hit's
 * info as a word) */
u32 proof_shell00_setup(u8 *self, const u8 *param);
void proof_shell00_effect(u8 *self, const s32 *pair, const float *pos);
void proof_shell02_ground_hit(u8 *shell, float *pos, u8 *info, u32 kind);

static inline u32 gen_shell_base00_setup(uShell *self, const void *param)
{
    return proof_shell00_setup((u8 *)self, param);
}
static inline void gen_shell_base00_effect(uShell *self, s32 effect, const float *pos)
{
    proof_shell00_effect((u8 *)self, (const s32 *)effect, pos);
}
static inline void gen_shell_base02_hit(uShell *self, const float *pos, u32 a, u32 b)
{
    proof_shell02_ground_hit((u8 *)self, (float *)pos, (u8 *)a, b);
}

/* His classes' DTIs (proof/shell_4u.c; MH Generations' are the executable's, 0xDFEBFC-0xDFEC7C) and the one of his
 * base 02 setup parameter (the executable's in both: 0xDFC648) */
extern const u8 proof_em050_sp00_dti[], proof_em050_sp01_dti[], proof_em050_sp02_dti[], proof_em050_sp11_dti[],
    proof_em050_sp41_dti[];
extern const u8 proof_setup02_dti[];
#define gen_sp00_dti             proof_em050_sp00_dti
#define gen_sp01_dti             proof_em050_sp01_dti
#define gen_sp02_dti             proof_em050_sp02_dti
#define gen_sp11_dti             proof_em050_sp11_dti
#define gen_sp41_dti             proof_em050_sp41_dti
#define gen_setup_em_base02_dti  proof_setup02_dti

/* Each class's operator delete (MH Generations 0x5CE7D8-0x5CE898): its DTI's allocator, slot 14 */
static inline void shell_class_free(const u8 *dti, void *p)
{
    void *allocator = dti_allocator(dti);

    ((void (*)(void *, void *))FIELD(void **, allocator, 0)[14])(allocator, p);
}
static inline void gen_sp00_delete(void *p) { shell_class_free(gen_sp00_dti, p); }
static inline void gen_sp01_delete(void *p) { shell_class_free(gen_sp01_dti, p); }
static inline void gen_sp02_delete(void *p) { shell_class_free(gen_sp02_dti, p); }
static inline void gen_sp11_delete(void *p) { shell_class_free(gen_sp11_dti, p); }
static inline void gen_sp41_delete(void *p) { shell_class_free(gen_sp41_dti, p); }

/* Base 11's float array: MtArray's DTI's allocator (0x10E65D4, MH Generations' 0xE2F6AC), slots 8 and 14 */
extern const u8 mt_array_dti[];
#define gen_allocator            dti_allocator
#define gen_shell_array_dti      mt_array_dti

static inline void *shell_array_alloc(u32 size)
{
    void *allocator = gen_allocator(gen_shell_array_dti);

    return ((void *(*)(void *, u32, u32))FIELD(void **, allocator, 0)[8])(allocator, size, 0x10);
}

static inline void shell_array_free(void *p)
{
    void *allocator = gen_allocator(gen_shell_array_dti);

    ((void (*)(void *, void *))FIELD(void **, allocator, 0)[14])(allocator, p);
}

/* MH Generations' zero vectors (0xE2F410 in .bss, 0xC9EA48) */
#define gen_vec3_zero            vec3_zero_4u
#define gen_vec3_zero_ro         vec3_zero_4u

/* A shell launching another of base 01 (cSetupParamEmBase01) with variant `n`, as enemy_gen.h's: the setup
 * parameter built the same way, and the port's sShell (proof_shell_mgr) creating the shell from it, as MH
 * Generations' 0x923400 does (proof/shell_mgr.c proof_shell_mgr_create) */
extern u8 *proof_shell_mgr;
void *proof_setup01_new(u32 size, u32 align);
extern void *const proof_setup01_vtable[];
void *proof_shell_mgr_create(u8 *mgr, u8 *param, u32 flags);

/* sShell's create of a launch's setup parameter; with the product's telemetry (PROOF_SHELL_LOG, src/shell_log.c) a
 * create that gives no shell is recorded with why */
#ifdef PROOF_SHELL_LOG
void proof_4u_shell_failed(u8 *param);
#define shell_create_port(param) \
    do { if (!proof_shell_mgr_create(proof_shell_mgr, param, 0)) proof_4u_shell_failed(param); } while (0)
#else
#define shell_create_port(param) ((void)proof_shell_mgr_create(proof_shell_mgr, param, 0))
#endif

static inline void shell_launch_01_from(uShell *shell, u32 kind, u32 n, const float *pos, const void *angles)
{
    u8 *param = proof_setup01_new(0x40, 0x10);

    if (param) {
        FIELD(const void *, param, 0x00) = proof_setup01_vtable;
        FIELD(u16, param, 0x04) = kind;
        FIELD(u32, param, 0x08) = n;
        FIELD(uEnemy *, param, 0x0C) = shell_owner(shell);
        FIELD(float, param, 0x10) = pos[0];
        FIELD(float, param, 0x14) = pos[1];
        FIELD(float, param, 0x18) = pos[2];
        FIELD(float, param, 0x1C) = 0.0f;
        FIELD(float, param, 0x20) = gen_vec3_zero[0];
        FIELD(float, param, 0x24) = gen_vec3_zero[1];
        FIELD(float, param, 0x28) = gen_vec3_zero[2];
        FIELD(float, param, 0x2C) = 0.0f;
        FIELD(u32, param, 0x30) = FIELD(const u32, angles, 0x0);
        FIELD(u32, param, 0x34) = FIELD(const u32, angles, 0x4);
        FIELD(u32, param, 0x38) = FIELD(const u32, angles, 0x8);
        FIELD(u16, param, 0x3C) = 0xFFFF;
    }
    shell_create_port(param);
}

/* ---- Mizutsune's class and action machine (em082/; enemy_gen.h says what each MH Generations name is) ---- */
#define EM_ACT_KEEP        0x1CE   /* u8: set, setAction (0x90EFAC) keeps the previous pair (MH Generations
                                    * this+0x6ACC) */
#define EM_CHG_SCALE       0x1BC   /* f32 mEmChgScale */
#define EM_SUB_TYPE        0x797E  /* u8 mSubType */
#define EM_PARTS_VITAL_GUARD 0x7A44   /* u8: while set, all_parts_vital (em+0x7A40) takes no damage (0x9204F4) */

#define enemy_motion_now(self) FIELD(u16, self, ENEMY_MOTION_NO)
#define enemy_act_keep(self)   FIELD(u8, enemy_em(self), EM_ACT_KEEP)
#define enemy_area_no(self)    FIELD(u8, enemy_em(self), EM_AREA_NO)
#define enemy_map_no(self)     FIELD(u8, enemy_em(self), EM_MAP_NO)
#define enemy_chg_scale(self)  FIELD(float, enemy_em(self), EM_CHG_SCALE)
#define enemy_sub_type(self)   FIELD(u8, enemy_em(self), EM_SUB_TYPE)
#define enemy_parts_vital_guard(self) FIELD(u8, enemy_em(self), EM_PARTS_VITAL_GUARD)
/* Great Maccao's (em085/; enemy_gen.h says what each is) */
#define EM_SET_ID          0x1C4   /* u16 mEmSetID */
#define EM_SPECIES_FLAGS   0x1B4   /* u32: the species flags word */
#define EM_ACT_SCRIPT      0x594   /* u32: the script enemy_act_script runs (0x9197C0 stores it) */
#define EM_HOLD_TIMER      0x5DC   /* f32: the hold timer */
#define enemy_set_id(self)     FIELD(u16, enemy_em(self), EM_SET_ID)
#define enemy_species_flags32(self) FIELD(u32, enemy_em(self), EM_SPECIES_FLAGS)
#define enemy_act_script_now(self) FIELD(u32, enemy_em(self), EM_ACT_SCRIPT)
#define enemy_hold_timer(self) FIELD(float, enemy_em(self), EM_HOLD_TIMER)
/* MH Generations' unit angle (this+0xC9C), which its unit step keeps with mVec's: MH4U's facing angle stands in
 * (an Arena probe checks 10/0xAF's slide) */
#define enemy_unit_angle_y(self) enemy_angle_y(self)
/* Fields only MH Generations' layer has: its flags, and Hyper, which MH4U has no monster in */
#define enemy_gen_unit_flags(self) (*((void)(self), &(u32){0}))
#define enemy_hyper(self)      (*((void)(self), &(u8){0}))
#define enemy_hyper_kind(self, k) (*((void)(self), (void)(k), &(u8){0}))

/* uFestaEnemy's slot 6 is its layer's start; uEnemy's (0x94CEC4) is empty. Its slot 10 runs the enemy update and
 * slots 102-104; uEnemy's (0x955E5C) the update alone: a species that has slot 102 runs it itself (em082). */
void uEnemy_step(uEnemy *self);
static inline void enemy_base_start(uEnemy *self) { (void)self; }
static inline void enemy_base_step(uEnemy *self) { uEnemy_step(self); }

/* The species' action tune: MH4U has no such file; his build reads his (MH Generations' rFreeUseParam, an image
 * in MH Generations' layout that the product makes, ENEMY_ACTION_TUNE before em_api.h) with the port's getters
 * (proof/shell_getters.c, in the block every ported monster shares). */
#ifdef ENEMY_ACTION_TUNE
extern u8 ENEMY_ACTION_TUNE[];
#ifdef ENEMY_VARIANT_LIST
ENEMY_VARIANT_GETTER(enemy_action_tune, ENEMY_ACTION_TUNE, action_tune, u8)
#else
#define enemy_action_tune(self) ENEMY_ACTION_TUNE
#endif
s32 proof_res_fup_s32(u8 *fup, u32 i);
ENGINE_VFP float proof_res_fup_f32(u8 *fup, u32 i);
const float *proof_res_fup_vec3(u8 *fup, u32 i);

static inline s32 enemy_tune_int(uEnemy *self, u32 n)
{
    (void)self;
    return proof_res_fup_s32(enemy_action_tune(self), n);
}
static inline float enemy_tune_float(uEnemy *self, u32 n)
{
    (void)self;
    return proof_res_fup_f32(enemy_action_tune(self), n);
}
static inline const float *enemy_tune_vec(uEnemy *self, u32 n)
{
    (void)self;
    return proof_res_fup_vec3(enemy_action_tune(self), n);
}
#endif

/* The quest's rank (enemy_xx.h): MH4U's own function and variable, whose numbering is the same where it matters (1 low,
 * 3 high, 5 G, 6 G apex). MH4U's species compare with constants: his break thresholds are XX's 4-byte records as they
 * are, in a block of his (ENEMY_BREAK_THRESHOLDS before em_api.h) the product fills. */
#define ENEMY_QUEST_RANK_G 5
extern void *quest_manager_4u;                      /* the variable holding the quest manager */
s32 quest_rank_4u(void *manager);
#define xx_quest_manager quest_manager_4u
#define quest_rank(manager) quest_rank_4u(manager)

static inline u32 enemy_quest_is_g(void)
{
    return quest_rank(xx_quest_manager) >= ENEMY_QUEST_RANK_G;
}

#ifdef ENEMY_BREAK_THRESHOLDS
extern const u8 ENEMY_BREAK_THRESHOLDS[];
#ifdef ENEMY_VARIANT_LIST
ENEMY_VARIANT_GETTER(enemy_break_table, ENEMY_BREAK_THRESHOLDS, break_thresholds, const u8)
#else
#define enemy_break_table(self) ENEMY_BREAK_THRESHOLDS
#endif

static inline u32 enemy_break_threshold(uEnemy *self, u32 record)
{
    (void)self;
    return enemy_break_table(self)[4 * record + 1 + enemy_quest_is_g()];
}
#endif

/* A walk's climb limit (a float block, em080_climb for Glavenus): the variant's own, else the base's. The monster
 * defines ENEMY_CLIMB before em_api.h; its C reads enemy_climb(self)[0] where it read the block */
#ifdef ENEMY_CLIMB
extern const float ENEMY_CLIMB[];
#ifdef ENEMY_VARIANT_LIST
ENEMY_VARIANT_GETTER(enemy_climb, ENEMY_CLIMB, climb, const float)
#else
#define enemy_climb(self) ENEMY_CLIMB
#endif
#endif

/* MH Generations' shell manager keeps a limit for two owners (0x92410C); MH4U's has none. The port's sShell has
 * the fields (sdk/shell_api.h SMGR_LIMIT), not the function yet: his shells' phase (F) writes it. */
static inline void shell_owner_limit(uEnemy *self, s32 count) { (void)self, (void)count; }

/* The current area's ground height: 0x6C2888 reads the quest's area itself; Zinogre's slot 54 passes his area all
 * the same, as MH Generations' 0x8A5BC0 takes it. */
extern void *stage_4u;
ENGINE_VFP float area_ground_4u(void *stage, u32 area);
static inline float enemy_area_ground(uEnemy *self) { return area_ground_4u(stage_4u, enemy_area_no(self)); }

/* MH Generations' effect request 1310 + n, a Hyper part's: through the monster's effects as any other */
static inline void enemy_effect_1310(uEnemy *self, u32 n) { enemy_effect_request(self, 1310 + n); }

/* MH Generations' slot 212, out of action: MH4U's 0x94D7A8 is the same test (proof_api.h declares it too) */
u32 enemy_out_of_action(void *monster);
static inline u32 enemy_out_of_action_call(uEnemy *self) { return enemy_out_of_action(self); }

/* MH Generations' engine moves its monsters between areas (ENEMY_UNIT_FLAGS 0x40, 0x400 while it does); MH4U's
 * species queue their moves themselves. Not moving until his roaming is ported (phase H). */
static inline u32 enemy_area_moving(uEnemy *self) { (void)self; return 0; }

/* MH Generations' joint callbacks (uFestaEnemy's object at this+0x9FC8, its member function called for the
 * joints): no joint callback of MH4U is known, so nothing; his (em082_joint_callback, 7/9's neck bend) never runs
 * in MH4U. */
static inline void enemy_joint_callbacks(uEnemy *self, const u8 *numbers, u32 count, const u32 method[2])
{
    (void)self, (void)numbers, (void)count, (void)method;
}

/* ---- Mizutsune's choice, frame events, states 0, 1, 10-12 and helpers (enemy_gen.h says what each MH Generations
 * name is) ---- */
#define EM_ACT_ST_OLD      0x1CC   /* u8: the action before this one (setAction 0x90EFAC keeps it) */
#define EM_ACT_NO_OLD      0x1CD
#define EM_MOVE_RATE       0x874   /* f32: his move speed's factor (0x9355C8 multiplies the tuning's +0x30 by it, as
                                    * MH Generations' 0x8CF264 does em+0x8F4) */
#define EM_WALL_SKIP       0x978   /* bool mWallSkipFlag */
#define EM_CEILING_SKIP    0xB00   /* bool mTenjoSkip */
#define EM_FLAG_55B        0x55B   /* u8: the script action sets it where MH Generations' sets em+0x4C9 (0x919EDC,
                                    * 0x8B5C74) */
#define EM_BITS_7993       0x7993  /* u8: enemy_bits_5893's byte */

#define enemy_act_st_old(self) FIELD(u8, enemy_em(self), EM_ACT_ST_OLD)
#define enemy_act_no_old(self) FIELD(u8, enemy_em(self), EM_ACT_NO_OLD)
#define enemy_move_rate(self)  FIELD(float, enemy_em(self), EM_MOVE_RATE)
#define enemy_wall_skip(self)  FIELD(u8, enemy_em(self), EM_WALL_SKIP)
#define enemy_ceiling_skip(self) FIELD(u8, enemy_em(self), EM_CEILING_SKIP)
#define enemy_flag_4c9(self)   FIELD(u8, enemy_em(self), EM_FLAG_55B)
#define enemy_bits_5893_byte(self) FIELD(u8, enemy_em(self), EM_BITS_7993)
/* MH Generations' em+0x5854 is MH4U's em+0x7948: Zinogre's leave sets it at the same step in both games (roEm057
 * 0x10002EE8, uEm048 0x841DF4; phase D6), and MH4U's action change sets it while mAreaMoveActFlag is (0x90EF9C) */
#define EM_GEN_5854        0x7948
#define enemy_gen_5854(self)   FIELD(u8, enemy_em(self), EM_GEN_5854)
/* Asleep, MH4U's species count mTimer down (0x6DEF20 sets it, 0xB0709C counts it), as MH Generations' em+0x5A18 */
#define enemy_sleep_timer(self) enemy_timer(self)

void enemy_sleep_start_4u(uEnemy *self);                                      /* 0x93BAA8 */
ENGINE_VFP void enemy_sleep_heal_4u(uEnemy *self, u32 a, s32 period, float rate);   /* 0x93BAC0 */
void enemy_stamina_add(uEnemy *self, s32 amount);     /* 0x91B7E8 (MH Generations' 0x8B6BB4: the same arguments) */

/* MH Generations reads his rest and stamina numbers from his DTP (its record at +0x84, 0x40 bytes: +0x14, +0x1A
 * ... +0x28, +0x34 = DTP+0xB8, +0x38, +0x3C); MH4U's species pass them as constants. His build reads them from a
 * block in that layout (ENEMY_REST before em_api.h; phase G fills it from his DTP). */
#ifdef ENEMY_REST
extern const u8 ENEMY_REST[];
#ifdef ENEMY_VARIANT_LIST
ENEMY_VARIANT_GETTER(enemy_rest, ENEMY_REST, rest, const u8)
#else
#define enemy_rest(self) ENEMY_REST
#endif
u32 enemy_is_tired(uEnemy *self);      /* em_api.h */

/* MH Generations' 0x8D4830: the healing's timer cleared, and his sleep's length (MH Generations' +0x34) */
static inline void enemy_sleep_start(uEnemy *self)
{
    enemy_sleep_start_4u(self);
    enemy_sleep_timer(self) = FIELD(const float, enemy_rest(self), 0x34);
}

/* MH Generations' 0x8D4964 with `which` 1 (his code passes no other): MH4U's 0x93BAC0 takes the period as an int
 * and the rate as a fraction of his top health (MH Generations' a percent) */
static inline void enemy_sleep_heal(uEnemy *self, u32 which)
{
    if (which == 1)
        enemy_sleep_heal_4u(self, 1, (s32)FIELD(const float, enemy_rest(self), 0x38),
                            FIELD(const float, enemy_rest(self), 0x3C) * 0.01f);
}

/* MH Generations' 0x8F193C: the stamina back. Its bait part (target 0 a bait shell) is MH Generations' shells':
 * MH4U's species take their bait elsewhere */
static inline void enemy_eat(uEnemy *self, u32 kind, u32 flag)
{
    s32 amount = 0;

    (void)flag;
    if (kind < 4)
        amount = FIELD(const s16, enemy_rest(self), 0x1A + 4 * kind + (enemy_is_tired(self) ? 2 : 0));
    enemy_stamina_add(self, amount);
}
#endif

/* MH Generations' layer after he wakes: MH4U's sleeping species call nothing of the kind (0x6DF054) */
static inline void enemy_wake_notify(uEnemy *self) { (void)self; }

/* ---- Mizutsune's attacks, state 7 part A (enemy_gen.h says what each MH Generations name is) ---- */
#define ENEMY_MOTION_FRAME     0x28C   /* f32: layer 0's frame (MH Generations 0x294; 0x936960 reads both) */
#define ENEMY_MOTION_FRAME_OLD 0x290   /* f32: its frame on the previous frame */
#define enemy_motion_frame(self)     FIELD(float, self, ENEMY_MOTION_FRAME)
#define enemy_motion_frame_old(self) FIELD(float, self, ENEMY_MOTION_FRAME_OLD)
/* The model's joints, 0xA8 bytes each, and a joint number's index among them, 0xFF for none (0xB054AC; MH
 * Generations 0x22C, 0x230 and 0xA0 bytes, 0xA7A934) */
#define ENEMY_JOINTS       0x224
#define ENEMY_JOINT_INDEX  0x228
#define ENEMY_JOINT_SIZE   0xA8    /* proof_api.h JOINT_SIZE, MODEL_JOINTS, MODEL_JOINT_MAP */
/* A joint's rotation (x, y, z, w; 0x960244), 8 bytes before MH Generations', as its position (+0x38, MH Generations
 * +0x40); its number: MH Generations' byte 3 of +0x90, taken to be byte 3 of +0x94 here, the word whose byte 1 is the
 * parent's index in both matrix functions (0x960F80 +0x94, 0x955AAC +0x90). Read only by em082_joint_callback, which
 * MH4U's joints never call (enemy_joint_callbacks). */
#define JOINT_QUAT         0x58
#define JOINT_NUMBER       0x97

/* The model's joint of number `number`, or null */
static inline u8 *enemy_joint(uEnemy *self, u32 number)
{
    u32 index = FIELD(u8 *, self, ENEMY_JOINT_INDEX)[number & 0xFF];

    if (index == 0xFF)
        return 0;
    return FIELD(u8 *, self, ENEMY_JOINTS) + ENEMY_JOINT_SIZE * index;
}

/* ---- Glavenus' class and action machine (enemy_gen.h says what each MH Generations name is) ---- */
/* uEnemy's slot 55 is empty (0x93F36C): the area is given to the held effect by his own slot 55 */
static inline void enemy_area_base(uEnemy *self) { (void)self; }
#define EM_GEN_V384     0x40C   /* 1.0 set by uEnemy's init (0x91B9C0), as em+0x384 in MH Generations; only Hellblade changes it (MH4U has none) */
#define enemy_gen_v384(self) FIELD(float, enemy_em(self), EM_GEN_V384)
/* A part record's counter: the s16 at +4 of MH4U's 6-byte record (EM_PARTS + 6 n), the part's stagger health. XX's
 * enemy_part_counter_add (0x8BD24C) adds to it without a clamp (a truncated s16); MH4U's 0x93705C sets it from the etd's
 * region times the quest's parts multiplier, as XX's 0x8C5FAC does */
#define EM_PART_VITAL 4
#define enemy_part_counter(self, n) FIELD(s16, enemy_em(self), EM_PARTS + 6 * (n) + EM_PART_VITAL)
#define enemy_part_add(self, n, delta) ((void)(enemy_part_counter((self), (n)) += (s16)(delta)))

#endif
