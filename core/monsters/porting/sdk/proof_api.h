/* MH Generations' effect player, ported: the fields of its
 * classes and the engine calls it makes, for both targets. With TARGET_GEN the C is built for the check against
 * MH Generations' own code (research/porting/proof_difftest.py); otherwise for MH4U.
 *
 * The player's own classes keep MH Generations' layout in both games. Only the fields every unit starts with
 * (cUnit) are laid out differently in MH4U, so they are read through unit_flags and unit_delta. */
#ifndef PROOF_API_H
#define PROOF_API_H

#include "types.h"

/* ---- cUnit's first fields ---- */
#ifdef TARGET_GEN
#define UNIT_FLAGS  0x0C
#define UNIT_DELTA  0x1C
#else
#define UNIT_FLAGS  0x04
#define UNIT_DELTA  0x14
#endif
#define unit_flags(u)  FIELD(u32, u, UNIT_FLAGS)     /* the unit state in bits 0-2 */
#define unit_delta(u)  FIELD(float, u, UNIT_DELTA)   /* frames the unit moved on this frame */
#define unit_move_line(u) ((unit_flags(u) >> 3) & 0x7F)   /* mMoveLine: the sUnit line it moves on (bits 3-9) */
#define UNIT_KEEP      0x2000                        /* a flag: a core's delete leaves the state alone */
#define UNIT_DRAW_VIEW 0x03FF0000                    /* in the unit flags: mDrawView, the views it is drawn in */
#define UNIT_VIEW_0    0x00010000                    /* view 0 only (cUnit sets views 0-3) */

/* ---- uCoord's and uModel's fields the player reads on other units (the joints differ) ---- */
#define COORD_PARENT       0x30
#define COORD_POS          0x40                      /* vec3 */
#define COORD_WORLD_POS    0xE0                      /* the world matrix's (+0xB0) translation */
#define COORD_SCALE        0x60                      /* vec3 */
#ifdef TARGET_GEN
#define MODEL_JOINTS       0x22C                     /* the joint records */
#define MODEL_JOINT_MAP    0x230                     /* u8 *: a joint number's record (0xFF: none) */
#define JOINT_SIZE         0xA0
#define JOINT_POS          0x40                      /* vec3: the world position (the matrix at +0x10) */
#else
#define MODEL_JOINTS       0x224                     /* MH4U's getter 0xD028F0 */
#define MODEL_JOINT_MAP    0x228
#define JOINT_SIZE         0xA8
#define JOINT_POS          0x38                      /* the matrix at +0x8 */
#endif

/* ---- the owner (the monster): its area ---- */
#ifdef TARGET_GEN
#define owner_area(o)      FIELD(u8, o, 0xCF4)                       /* mAreaNo (sdk/enemy_gen.h) */
#else
/* A shell of the port as the owner (his effects follow his shells): it keeps MH Generations' uFestaChar layout
 * and is known by its parent interface (+0xC80), the port's vtable, which only the port writes and an MH4U
 * monster never holds (its interface is in its side). It has no em at +0xE28 (0 there), so every owner_* that
 * reads a monster's em reads such a shell's own field at MH Generations' offset instead, as MH Generations'
 * code reads it. */
#define owner_port_shell(o) (FIELD(void *const *, o, OWNER_PARENT) == proof_4u_parent_vtable)
/* its em's mAreaNo (sdk/enemy_4u.h); a shell of the port keeps uFestaChar's */
#define owner_area(o)      (owner_port_shell(o) ? FIELD(u8, o, 0xCF4) : FIELD(u8, FIELD(u8 *, o, 0xE28), 0x14C))
#endif

/* ---- cResource: its state byte, at +0x50 in both games (getters 0xA122D4, 0xBE2788) ---- */
#define RESOURCE_FLAGS     0x50
#define RESOURCE_LOADED    0x01
#define RESOURCE_DROPPED   0x40                      /* set by a core that lets go of it before it loaded */
#define RESOURCE_REFS      0x48                      /* MH4U's reference count (s32; sResource frees it at 0) */

/* A virtual method: slot `n` of `obj`'s vtable, as a `type` (a function pointer type). */
#define VSLOT(type, obj, n)  (((type *)FIELD(void *, obj, 0))[n])

/* ---- cProofEffectSequence: one per monster, plays its PSLs (0x154 bytes) ---- */
typedef struct cProofSeq cProofSeq;
#define SEQ_MOTION         0x18                      /* the playing unit's motion: list in bits 8-11, motion in the low byte */
#define SEQ_MOTION_BEFORE  0x1C                      /* last frame's (-1 after notice 4) */
#define SEQ_FRAME          0x20                      /* f32: the playing unit's frame */
#define SEQ_FRAME_BEFORE   0x24                      /* f32: last frame's */
#define SEQ_PSL(list)      (0x2C + 4 * (list))       /* the PSL resource of motion list `list` */
#define SEQ_TABLE(list)    (0x6C + 4 * (list))       /* a table of sequences by motion that replaces the PSL's */
#define SEQ_COPY           0xAC                      /* a copy of the sequence data, filled when SEQ_COPY_ON */
#define SEQ_COPY_ON        0xB0                      /* u8 */
#define SEQ_USER           0xB4                      /* IProofEffectSequenceUser *: the monster's side */
#define SEQ_BITS_BEFORE    0xBC                      /* the bits of the last frame walked */
#define SEQ_NOTICES        0xC0                      /* notices waiting for the next update */
#define SEQ_WORD(bit)      (0xC4 + 4 * (bit))        /* each bit's state word (the bit table) */
#define SEQ_PLAYING        0x144                     /* u8: 1 while the update walks the bits */
#define SEQ_PLAY_LIST      0x148
#define SEQ_PLAY_MOTION    0x14C
#define SEQ_LAST_EFFECT    0x150
#define SEQ_SLOT_ON        6                         /* (seq, data, bit, 0): the bit turned on */
#define SEQ_SLOT_STAYS     7
#define SEQ_SLOT_OFF       8
#define SEQ_SLOT_COPIED    9                         /* (seq, copy): the sequence data was copied to SEQ_COPY */
#define WORD_STAYS_ON      0x1
#define WORD_TURNED_OFF    0x2
#define WORD_MOTION_CHANGED 0x4
#define WORD_FRAME_BACKWARD 0x8
#define WORD_KEPT          0xFFF0                    /* what a word keeps from frame to frame */
#define NOTICE_MOTION      0x4                       /* a notice that counts as a motion change */
#define SEQ_PEL_HANDLE     0xB8                      /* a PEL the sequence registered (released with it) */
#define SEQ_DATA_ID(bit)   (0x04 + 2 * (bit))        /* in a PSL sequence: the record id of each bit */
typedef void (*seq_bit_fn)(cProofSeq *seq, u32 *data, int bit, int zero);
typedef void (*seq_copied_fn)(cProofSeq *seq, void *copy);

/* A PSL sequence (rProofEffectMotSequenceList, 0x14C bytes; proof_data.py) */
#define SEQDATA_BITS       0x000                     /* the bits it uses */
#define SEQDATA_PAIR_COUNT 0x144
#define SEQDATA_PAIRS      0x148                     /* (bits, frames) pairs */

/* IProofEffectSequenceUser: what the monster gives its sequence */
#define USER_SLOT_READY    0                         /* nonzero when effects can be created */
#define USER_SLOT_FRAME    1                         /* f32 (VFP): the motion's frame */
#define USER_SLOT_MOTION   2                         /* the motion (SEQ_MOTION) */
#define USER_SLOT_CREATE   6                         /* (user, 1, data, bit, setup): the effect, or 0 */
#define USER_SLOT_OBJECT   7                         /* an object whose slot 1 gives its owner (the monster) */
#define OWNER_IDS          0xDB4                     /* in the owner: four ids of playing records (+0x11C...) */
#define OWNER_SLOT_COPIED  58                        /* (owner, copy): a sequence's data was copied */
#define IDS_FIRST          0x11C
#define CORE_WORD          0x17C                     /* in an effect: its bit's word in the sequence */
#define USER_FRAME_AT      0x2A0
typedef float ENGINE_VFP (*user_frame_fn)(void *user);
typedef u32 (*user_motion_fn)(void *user);
typedef void *(*object_fn)(void *obj);
typedef int (*user_ready_fn)(void *user);
typedef void *(*user_create_fn)(void *user, int one, u32 *data, int bit, u8 *setup);
typedef void (*owner_copied_fn)(void *owner, void *copy);

/* ---- MT Framework's allocation: a class's DTI gives its allocator ---- */
#define ALLOC_SLOT_ALLOC   9                         /* (allocator, size, align, kind) */
#define ALLOC_SLOT_FREE    14                        /* (allocator, block) */
#define DTI_KIND           0x1C
typedef void *(*alloc_fn)(void *allocator, u32 size, u32 align, u32 kind);
typedef void (*free_fn)(void *allocator, void *block);
void *dti_allocator(const void *dti);
extern const u8 proof_seq_dti[];                     /* cProofEffectSequence's */
extern const u8 proof_mhseq_dti[];                   /* cMhEffectSequence's */
extern void *const proof_seq_vtable[];
extern void *const proof_mhseq_vtable[];
#define SEQ_SIZE           0x154

/* ---- rProofEffectMotSequenceList: a PSL (proof_data.py) ---- */
#define PSL_BUFFER         0x60                      /* the file, its offsets made pointers */
#define PSL_COUNT          0x06                      /* u16: motions */
#define PSL_ENTRIES        0x08                      /* their entries' pointers */

/* ---- A PEL record's 0xA0 bytes of parameters ---- */
#define PARAMS_SIZE        0xA0
#define PARAMS_VECTORS     3                         /* offset, rotation, scale: vec4s whose w a copy sets to 0 */
#define PARAMS_ID          0x30                      /* u16 */
#define PARAMS_JOINT       0x32                      /* s16 */
#define PARAMS_SCALE       0x20                      /* vec3 */
#define PARAMS_BIND        0x36                      /* u8: how the effect is placed */
#define PARAMS_ROT_ORDER   0x37                      /* u8: the rotation order */
#define PARAMS_END_RULE    0x3A                      /* u8: when the core stops or plays again (0, 1, 2) */
#define PARAMS_RESOURCE_KIND 0x3D                    /* u8: 0 effect list, 1 model */
#define PARAMS_HEIGHT_CHECK 0x40                    /* u8: check the height at the start (slot 24) */
#define PARAMS_UNSCALED    0x42                      /* u8: 0 measures the hunters' distance in the owner's scale */
#define PARAMS_PERIOD      0x44                      /* u16: end rule 2's interval */
#define PARAMS_MASK_B      0x4C                      /* u32 */
#define PARAMS_GROUND      0x52                      /* u8: on the ground */
#define PARAMS_STATE_MASK  0x53                      /* u8: mask B from the monster's state */
#define PARAMS_STATE_STOPS 0x55                      /* u8: stop when that state has STATE_STOPS */
#define PARAMS_LIMIT       0x58                      /* f32: the height limit, and bind 4's range */
#define PARAMS_HUNTERS     0x86                      /* u16: the hunters bind 4 counts, one bit each */
#define PARAMS_ELEMENTS    0x8C                      /* 4 u32: 128 bits a drawn model takes */
#define END_RULE_REPLAY    1                         /* plays it again when over */
#define END_RULE_PERIOD    2                         /* plays it again every PARAMS_PERIOD */
#define PARAMS_COLOR_SLOT  0x64                      /* u16: the color table's slot */
#define PARAMS_COLOR_ENTRY 0x66                      /* u16: its entry */
#define PARAMS_COLOR_B     0x73                      /* u8: the color from table B */
#define BIND_NEAR_HUNTERS  4                         /* drawn only near hunters */
/* The last word: padding in MH Generations (its copy leaves it alone), in MH XX the factor its placement gives the
 * effect's speed (+0x9C, 1.0 unless the record says; 0x64EA50, 0x662FDC). The placement carried into MH4U is XX's. */
#define PARAMS_SPEED       0x9C                      /* f32 */
#ifdef TARGET_GEN
#define PARAMS_COPIED_END  0x9C
#else
#define PARAMS_COPIED_END  0xA0
#endif

/* ---- cProofEffectBaseParam: an effect's setup (0xC8 bytes) ---- */
#define SETUP_SIZE         0xC8
#define SETUP_OVERRIDES_A  0x04                      /* the record fields the setup sets (setup.c's overrides_a) */
#define SETUP_OVERRIDES_B  0x08                      /* and overrides_b */
#define SETUP_FLAGS        0x0C                      /* 2: created by a sequence */
#define SETUP_PARAMS       0x10                      /* a record's parameters */
#define SETUP_POSITION     0xB0                      /* vec3 */
#define SETUP_SCALE        0xBC                      /* f32 */
#define SETUP_OBJECT       0xC0
#define SETUP_RESOURCE     0xC4                      /* a resource the setup holds a reference to */
#define SETUP_FLAG_SEQUENCE 0x2
#define SETUP_FLAG_DETACHED 0x2                      /* the same bit, also set when the core's parent is gone */
#define OVERRIDE_ROTATION  (1u << 1)                 /* in SETUP_OVERRIDES_A: PARAMS_ROTATION is the setup's */
#define OVERRIDE_BIND      (1u << 3)                 /* in SETUP_OVERRIDES_A: PARAMS_BIND is the setup's */
#define OVERRIDE_MASK_B    (1u << 19)                /* PARAMS_MASK_B */
extern void *const proof_setup_vtable[];             /* MH Generations 0xD67CD8 */

/* ---- sProofEffectSequence: the 64 sequences (on cSystem) ---- */
#define MGR_CS             0x04                      /* cSystem's critical section */
#define MGR_LOCKED         0x10                      /* s8: lock the manager */
#define MGR_SEQ(i)         (0x14 + 4 * (i))
#define MGR_SEQUENCES      64
#define HND_INDEX          0x04                      /* in a handle (sProofEffectSequence::cHnd) */
#define SEQ_SLOT_CLONE     2                         /* a sequence's copy, for a new user */
extern void *const proof_mgr_vtable[];
extern void *const proof_hnd_vtable[];
extern const u8 proof_mgr_dti[];
extern void *proof_mgr;                              /* the variable the engine knows the manager by */
extern s8 mt_lock_all;                               /* nonzero: every cSystem takes its lock */
void mt_cs_enter(void *cs);
void mt_cs_leave(void *cs);
void *system_init(void *system);                     /* cSystem's constructor */
void *system_fini(void *system);                     /* and destructor */

/* ---- sFestaProofEffect's budget of live cores ---- */
#define BUDGET_LIVE_MAX    0x90                      /* below this many live cores, any may be created */
#define BUDGET_SLOTS       0x90                      /* cores per group */
#define BUDGET_WORDS       5                         /* a group's bitmask words (160 bits for 144 slots) */
#define BUDGET_BITS(g)     (0x6C + 0x14 * (g))
#define BUDGET_SLOT(g, i)  (0xA8 + 0x240 * (g) + 4 * (i))
#define BUDGET_LOWEST      0x768                     /* 64 words: a de Bruijn table of bit positions */
#define DEBRUIJN_LO        0x27179461u               /* the de Bruijn constant 0x03F566ED27179461 */
#define DEBRUIJN_HI        (DEBRUIJN_LO ^ (DEBRUIJN_LO >> 3 | DEBRUIJN_LO << 29))
#define CORE_SLOT_DELETE   16
extern void *proof_budget;                           /* the variable holding sFestaProofEffect */
extern s32 proof_live_cores;                         /* cores alive (their constructor counts them) */

/* ---- uMHEffectCore on uProofEffectBase: one per effect played (0x330 bytes) ---- */
#define CORE_STATE         0x30                      /* u8: 0 start, 1 playing, 2 ending, 3 replay */
#define CORE_STEP          0x31                      /* u8: the step within it (and two more bytes) */
#define CORE_PEL           0x34                      /* the PEL resource */
#define CORE_LIST_RESOURCE 0x38                      /* the effect list it plays */
#define CORE_MODEL_RESOURCE 0x3C                     /* or the model */
#define CORE_P             0x48                      /* the placement block P */
#define CORE_SETUP         0x70                      /* its setup (P + 0x28) */
#define CORE_PARAMS        (CORE_SETUP + SETUP_PARAMS)   /* the record's parameters it plays */
#define CORE_PARENT        0x130                     /* P + 0xE8: an object whose slot 1 gives the owner */
#define CORE_DRAWN(k)      (0x138 + 4 * (k))         /* its drawn effects (uMHProofEffect) */
#define CORE_MODEL(k)      (0x13C + 4 * (k))         /* its drawn models (CORE_DRAWN(1) is CORE_MODEL(0)) */
#define CORE_KIND          0x140                     /* u8: the record's resource kind: 0 effect list, 1 model */
#define CORE_DRAWN_COUNT   0x144
#define CORE_IN_AREA       0x174                     /* u8 */
#define CORE_DRAWING       0x175                     /* u8: cleared when its drawn effects finish */
#define CORE_TYPE          0x184                     /* mType */
#define CORE_ATTR          0x188                     /* mAttr */
#define CORE_AREA          0x18C                     /* mAreaNo (0xFF: any) */
#define CORE_APP_VISIBLE   0x1A0                     /* u8 mAppVisible */
#define CORE_PRIORITY      0x1A4                     /* mPriority (read as a byte): the budget's group */
#define CORE_BUDGETED      0x1A8                     /* u8: in the budget */
#define CORE_ENTRY(k)      (0x1AC + 0x18 * (k))      /* its sound event entries */
#define CORE_ENTRIES       16
extern void *const proof_core_vtable[];              /* uMHEffectCore's */
extern void *const proof_base_vtable[];              /* uProofEffectBase's */
extern const u8 proof_core_dti[];
extern const u8 proof_base_dti[];
#define CORE_SLOT_OWNER_STATE 29
#define CORE_SLOT_RELEASE  40
#define CORE_SLOT_ANY_DRAWN 42
#define CORE_SLOT_OWNER_AREA 45
typedef u32 (*core_u32_fn)(void *core);
#define CORE_LOADED        0x32                      /* u8 (a step byte): its resource has loaded */
#define CORE_LIST_INDEX    0x40                      /* u32: the PEL list of its record */
#define CORE_RECORD_INDEX  0x44                      /* u32: the record in that list */
#define CORE_CLOCK         0x16C                     /* f32: end rule 2's clock */
#define CORE_CLOCK_PLAYED  0x170                     /* f32: the clock when it last played again */
#define CORE_NOTICE_OFF    0x180                     /* u8: its bit turned off (WORD_TURNED_OFF) */
#define CORE_NOTICE_MOTION 0x181                     /* u8: the motion changed (WORD_MOTION_CHANGED) */
#define CORE_NOTICE_BACK   0x182                     /* u8: the frame went back, after the start (WORD_FRAME_BACKWARD) */
#define CORE_IN_RANGE      0x183                     /* u8: a hunter in range (bind 4) */
#define CORE_LIFE          0x190                     /* f32 mLifeTimer */
#define CORE_TIMER         0x194                     /* f32 mTimer */
#define CORE_TIMER_OLD     0x198                     /* f32 mTimerOld */
#define ATTR_AREA          0x1                       /* mAttr: keep at CORE_IN_AREA whether its area is current */
#define ATTR_UPDATE        0x2                       /* the base's slot 9 runs */
#define ATTR_LIFE          0x4                       /* deleted once mTimer reaches mLifeTimer */
#define CORE_LIFE_DEFAULT  300.0f                    /* a core with no parent's life */
#define AREA_ANY           0xFF
#define WORD_STOP          0x10000                   /* in its bit's word: stop (reason 7) */
#define WORD_END_NOW       0x20000                   /* end at once (its drawn effects deleted) */
#define WORD_BIND_1        0x40000                   /* switch the core and its drawn effects to bind 1 */
#define LINE_CORE_MODES_3_6 0xC                      /* the line a core moves on in game modes 3 and 6 */
#define STATE_START        0
#define STATE_PLAYING      1
#define STATE_ENDING       2
#define STATE_REPLAY       3
#define STEP_FETCH         0                         /* the start's steps (CORE_STEP) */
#define STEP_LOAD          10
#define STEP_PLACE         20
#define STEP_CREATE        30
#define STOP_PARENT        1                         /* the reasons given to slot 39 (it reads none) */
#define STOP_TOO_HIGH      2
#define STOP_STATE         4
#define STOP_OVER          5
#define STOP_NOTICE        6
#define STOP_WORD          7
#define STOP_FAILED        8
#define STATE_STOPS        0x20                      /* in the monster's state mask: slot 27 stops the core */
#define CORE_SLOT_UPDATE   9
#define CORE_SLOT_DRAWN_LINE 20
#define CORE_SLOT_21       21
#define CORE_SLOT_GROUND   22
#define CORE_SLOT_TOO_HIGH 24
#define CORE_SLOT_VIEWER_POS 25
#define CORE_SLOT_IN_RANGE 26
#define CORE_SLOT_STATE_STOPS 27
#define CORE_SLOT_MASK_B   28
#define CORE_SLOT_BUILD_P  31
#define CORE_SLOT_PLACE_EFFECT 32
#define CORE_SLOT_PLACE_MODEL 33
#define CORE_SLOT_NEW_EFFECT 34
#define CORE_SLOT_NEW_MODEL 35
#define CORE_SLOT_START    36
#define CORE_SLOT_PLAYING  37
#define CORE_SLOT_ENDING   38
#define CORE_SLOT_STOP     39
#define CORE_SLOT_DELETE_DRAWN 41
#define CORE_SLOT_JOINT_POS 43
#define CORE_SLOT_ATTR_ON  53
#define PARENT_SLOT_ALIVE  0                         /* the parent's: nonzero while it is there */
#define PARENT_SLOT_OWNER  1                         /* its owner (the monster) */
typedef void (*stop_fn)(void *core, int reason);
typedef void (*attr_fn)(void *core, u32 bits);
typedef void (*build_p_fn)(void *core, u8 *p, const u8 *params);
typedef void (*place_fn)(void *core, void *drawn, void *resource, u8 *p);
typedef void (*joint_pos_fn)(float *out, const void *core, const void *unit, int joint);
typedef float ENGINE_VFP (*ground_fn)(void *core, const float *pos);
typedef void (*viewer_pos_fn)(void *core, float *out, void *hunter);
typedef void (*add_sound_fn)(void *drawn, int kind, void *resource, s32 value, const u8 *param);

/* The placement block P (in the core at CORE_P; in a drawn effect at EFFECT_P, in a drawn model at MODEL_P) */
#define P_KIND             0x00                      /* s8: the bind it places by */
#define P_SETUP            0x28                      /* the setup (cProofEffectBaseParam) */
#define P_PARAMS           (P_SETUP + SETUP_PARAMS)
#define P_POS              0xD8                      /* vec3: where it is, with no parent */
#define P_PARENT           0xE8
#define P_KIND_WORLD       2                         /* the kind WORD_BIND_1 gives a drawn effect */

/* The monster's state, as mask B (slots 27 and 28): from its +0xD08 flags and +0xD30 (its ground record's: the
 * collision triangle's attributes 1 and 2) */
#define OWNER_STATE_FLAGS  0xD08
#define OWNER_STATE_BYTE   0xD30

/* The hunters' slots (proof_hunter_slots): 8 of HUNTER_SLOT_SIZE bytes, each with a record at HUNTER_RECORD */
#define HUNTER_SLOTS       8
#define HUNTER_SLOT_SIZE   0x1A8
#define HUNTER_RECORD      0x18
#define HUNTER_PLAYER      0x04                      /* in the record: the hunter */
#define HUNTER_PRESENT     0x10                      /* u8 */
/* A hunter's (sCamera's camera's) slot: its view matrix, returned by value. MH4U's cameras lack MH Generations'
 * uCamera slot 18 (0x9BA150), so their later slots are one lower: uMhCamera's slot 18 is 0xB71030 (MH
 * Generations' slot 19 0x9C9634), its slot 19 the projection. */
#ifdef TARGET_GEN
#define HUNTER_SLOT_MATRIX 19
#else
#define HUNTER_SLOT_MATRIX 18
#endif
typedef void (*matrix_fn)(float *out, void *hunter);
extern u8 *proof_hunter_slots;                       /* the variable holding them */

/* The record object (cProofEffectDataObject, 0xC0 bytes; "His effect data in the executable") */
#define REC_REF(i)         (0x08 + 0x10 * (i))       /* its resources' references */
#define REC_PARAMS         0x20                      /* the record's 0xA0 bytes of parameters */
#define REF_KIND           0x00                      /* u8: 1 effect list, 2 model */
#define REF_LIST           0x04
#define REF_MODEL          0x08
#define REF_PATH           0x0C                      /* MtString * */
#define REF_KIND_LIST      1
#define REF_KIND_MODEL     2
#define STRING_LENGTH      0x04                      /* in an MtString */
#define STRING_TEXT        0x08
/* The resource manager's load modes, named for what they do (B127). MH4U's slot 14 (FUN_00c163c0) reads
 * the file before it returns with mode 1 (FUN_00c14100) and only registers the resource, to be polled for its loaded
 * bit, with mode 2 (FUN_00c17108). MH Generations' slot 12: the values keep the order the effect player's C was
 * written from (not read for the names, B127's audit). */
#ifdef TARGET_GEN
#define LOAD_ASYNC         1
#define LOAD_SYNC          2
#else
#define LOAD_SYNC          1
#define LOAD_ASYNC         2
#endif
#define RESOURCE_FAILED   0x10                      /* in RESOURCE_FLAGS, without RESOURCE_LOADED */
#ifdef TARGET_GEN
#define RESMGR_SLOT_LOAD   12                        /* (manager, dti, path, mode): the resource */
#else
#define RESMGR_SLOT_LOAD   14                        /* adapter, engine side: MH4U's sResource, 2 slots on */
#endif
typedef void *(*res_load_fn)(void *manager, const void *dti, const char *path, u32 mode);
extern void *resource_manager;                       /* the variable holding sResource */
extern const u8 effect_list_dti[];                   /* rEffectList's DTI */
extern const u8 model_dti[];                         /* rModel's DTI */
extern const char mt_empty_string[];                 /* "" */

/* A PEL (rProofEffectList): list i of record objects */
#define PEL_LIST_COUNT(i)  (0x64 + 0x14 * (i))       /* u32 */
#define PEL_LIST_ARRAY(i)  (0x70 + 0x14 * (i))       /* u8 ** */

/* nMHProofEffect::cSoundEventParam: a core's sound event entry (0x18 bytes) */
#define ENTRY_KIND         0x04                      /* u8: 0 free */
#define ENTRY_RESOURCE     0x08                      /* a reference held */
#define ENTRY_VALUE        0x0C
#define ENTRY_PARAM        0x10                      /* a sound request's +4, +8 and +9 */
#define ENTRY_PARAM_B      0x14
#define ENTRY_PARAM_C      0x15
#define ENTRY_SIZE         0x18
extern void *const proof_entry_vtable[];

/* The drawn effect (uMHProofEffect on uProofEffect on uEffect) and the drawn model */
#define EFFECT_SIZE        0x4E8
#define MODEL_SIZE         0xF58
#define EFFECT_SLOT_STOP   18                        /* (effect, 0, -1) */
#define EFFECT_SLOT_FINISH 66                        /* uProofEffect's first own slot (0x35E29C) */
#define MODEL_SLOT_FINISH  31
typedef void (*effect_stop_fn)(void *effect, int zero, int minus_one);
#define EFFECT_P           0x218                     /* its placement block P */
#define EFFECT_ENTRY(k)    (0x35C + ENTRY_SIZE * (k))  /* its sound event entries */
#define EFFECT_SOUND_SPAN  0x4DC                     /* f32: a kind 2 or 5 entry's ENTRY_PARAM - 1 */
#define EFFECT_SLOT_ADD_SOUND 68
#define MODEL_P            0xC88
#define MODEL_ENTRY(k)     (0xDCC + ENTRY_SIZE * (k))
#define MODEL_SOUND_SPAN   0xF4C
#define MODEL_SLOT_ADD_SOUND 34
#define MODEL_SLOT_SET_RESOURCE 22                   /* uModel's: (model, resource) */
#define MODEL_ROT_ORDER    0x38                      /* u16 */
#define MODEL_POS          0x40                      /* vec4 */
#define MODEL_SCALE        0x60                      /* vec4 */
#define MODEL_ELEMENTS     0x10C                     /* 4 u32: the elements drawn, one bit each */
#define DRAWN_ELEMENTS     128
typedef void (*set_resource_fn)(void *model, void *resource);

/* ---- sUnit: the units, by line ---- */
extern void *sunit;                                  /* the variable holding sUnit */
int sunit_add(void *sunit, u32 line, void *unit, u64 group);   /* a unit onto a line */

/* ---- sGameControl ---- */
extern void *game_control;
/* MH Generations' game modes 3 and 6 (0xA8B22C); in MH4U the adapter's */
int game_mode_3_or_6(void *control);
/* MH Generations' game modes 5, 6 and 8 (0xA8B268), which keep the current area elsewhere; in MH4U the
 * adapter's */
int game_mode_5_6_or_8(void *control);
#ifdef TARGET_GEN
#define game_area(control, alt) ((alt) ? FIELD(u8, control, 0x3D) : FIELD(u8, control, 0x41))
#else
#define game_area(control, alt) ((void)(alt), FIELD(u32, control, 0xC90))   /* as MH4U's 0x2FA04C reads it */
#endif

/* ---- the local hunter (MH Generations 0xAFEA1C; inline in MH4U, so the adapter's) ---- */
extern void *player_manager;                         /* the variable 0xAFEA1C's callers hand it */
void *player_local(void *manager);

/* ---- sProofEffect: the PEL registry ---- */
#define REGISTRY_PELS      0x58                      /* the registered PELs' array, by handle */
extern void *proof_registry;                         /* the variable holding it */
/* the registry chain (registry2.c) */
#define REGISTRY_CS        0x04                      /* cSystem's critical section */
#define REGISTRY_LOCKED    0x10                      /* s8: lock the registry */
#define REGISTRY_COUNT     0x54                      /* u32: the handles' count */
#define REGISTRY_HANDLES   0x5C                      /* the handles, REGISTRY_HANDLE_SIZE bytes each */
#define REGISTRY_HANDLE_SIZE 8
#define REGISTRY_REFS      0x60                      /* u32 *: each handle's references */
#define PEL_HANDLE_INDEX   0x04                      /* in a handle: its index, -1 when free */
#define REC_ID             (REC_PARAMS + PARAMS_ID)  /* u16, in the record object */
#define REC_KIND           (REC_PARAMS + PARAMS_RESOURCE_KIND)   /* u8 */
/* a request to create a core (vtable 0xD79384, 0xD0 bytes; built by 0x46F84C) */
#define REQUEST_TYPE       0x04                      /* u8: mType */
#define REQUEST_PRIORITY   0x05                      /* u8: mPriority, the budget's group */
#define REQUEST_AREA       0x06                      /* u8: mAreaNo (0xFF: any) */
#define REQUEST_SETUP      0x08                      /* its cProofEffectBaseParam */
#define CORE_SIZE          0x330
#define CORE_ALIGN         0x10
#define CORE_UNIQUE_ID     0x19C                     /* mUniqueId: the record's id */
#define CORE_SLOT_FREE     1                         /* the deleting destructor */
#define CORE_SLOT_LINE     18
#define CORE_SLOT_GROUP    19                        /* sUnit's group (u64, high word 0) */
#define CORE_SLOT_SET_TYPE 46
#define CORE_SLOT_SET_AREA 48
#define CORE_SLOT_SET_PRIORITY 50

/* the monster side (monster.c). The request's size,
 * the PSL sequence's PEL of each bit, and what MH Generations' monster gives the player. Its fields and slots
 * below are MH Generations' monster's; MH4U reads them through the owner_* accessors (adapter half 2, below). */
#define REQUEST_SIZE       0xD0
extern void *const proof_request_vtable[];           /* MH Generations 0xD79384 */
#define SEQ_DATA_PEL(bit)  (0x44 + 4 * (bit))        /* in a PSL sequence: u32, the PEL of each bit */
#define PSL_PEL_BODY       3                         /* the body's PEL (`c`) */
#define PSL_PEL_SHELLS     4                         /* the shells' (`u`) */
#define USER_OWNER         0x04                      /* in its user: the monster */
#define USER_SLOT_CREATE_FOR 16                      /* (user, owner, 1, data, bit, setup): the effect, or 0 */
#define OWNER_SLOT_CREATE  73                        /* (owner, list, data, bit, request): the effect, or 0 */
#define OWNER_SLOT_PARENT  74                        /* (owner): its IProofEffectParent */
#define OWNER_SLOT_CREATE_CORE 76                    /* (owner, handle, list, id, request, tied sounds) */
#define OWNER_PARENT       0xC80                     /* its IProofEffectParent<uFestaChar> */
#define OWNER_PEL_BODY     0xEE0                     /* the body's PEL handle */
#define OWNER_TIED_BODY    0xEEC                     /* its rFestaPelTiedSe */
#define OWNER_PEL_SHELLS   0x9ECC                    /* the shells' PEL handle */
#define OWNER_TIED_SHELLS  0x9ED0
#define OWNER_ACT_HALT     0xC                       /* the action state (and number 0xFF) that creates nothing */
#define OWNER_ACT_NONE     0xFF
#ifdef TARGET_GEN
#define owner_act_st(o)    FIELD(u8, o, 0x6AC8)                      /* mActSt (sdk/enemy_gen.h) */
#define owner_act_no(o)    FIELD(u8, o, 0x6AC9)                      /* mActNo */
#else
#define owner_act_st(o)    FIELD(u8, FIELD(u8 *, o, 0xE28), 0x1CA)   /* its em's (sdk/enemy_4u.h) */
#define owner_act_no(o)    FIELD(u8, FIELD(u8 *, o, 0xE28), 0x1CB)
#endif
typedef void *(*user_create_for_fn)(void *user, void *owner, int one, u32 *data, int bit, u8 *setup);
typedef void *(*owner_create_fn)(void *owner, u32 list, u32 *data, int bit, u8 *request);
typedef void *(*owner_create_core_fn)(void *owner, const u8 *handle, u32 list, u32 id, u8 *request, void *tied);

/* ---- engine calls (both games; addresses in proof/gen_symbols.py and game/executable/blocks.py) ---- */
void resource_add_ref(void *resource);
void resource_release(void *resource);
void mt_memcpy(void *dst, const void *src, u32 size);
void mt_memset(void *dst, u32 size, u32 byte);       /* __aeabi_memset */
void mt_delete(void *p);                             /* operator delete */
void mt_delete_array(void *p);                       /* operator delete[] */
void mt_memclr(void *dst, u32 size);                 /* __aeabi_memclr */
ENGINE_VFP float mt_ceilf(float x);
void *unit_init(void *unit);                         /* cUnit's constructor: returns the unit */
void *unit_fini(void *unit);                         /* its destructor (empty in both games) */
/* The runtime's array constructor and destructor: each element's, in order (the destructor's backwards).
 * The constructor returns the array; the destructor, 8 bytes before it. */
typedef u8 *(*array_fn)(u8 *element);
ENGINE_THUMB void *mt_vec_ctor(void *array, array_fn init, u32 size, u32 count);
ENGINE_THUMB void *mt_vec_dtor(void *array, array_fn fini, u32 size, u32 count);
/* The runtime's signed division (__aeabi_idivmod): the quotient in the low word, the remainder in the high */
u64 mt_idivmod(s32 numerator, s32 denominator);

/* ---- engine data ---- */
extern const float mt_vec3_zero[4];                  /* (0, 0, 0, 0), written at start-up */
extern const float mt_vec3_one[4];                   /* (1, 1, 1, 0) */
extern const u32 proof_default_color;                /* a record's color before it is set */

/* ---- the ground under the effect (core slots 22 and 23) ---- */
extern const float mt_vec3_up[4];                    /* (0, 1, 0, 0), written at start-up */
#define PARAMS_GROUND_SOURCE 0x5C                    /* u32, read as a byte: GROUND_RAY, GROUND_HIGHER */
#define GROUND_RAY         0x10                      /* the ground from a ray cast down (collision_ground) */
#define GROUND_HIGHER      0x01                      /* the higher of the two heights */
#define GROUND_RAY_DEPTH   2000.0f                   /* how far below the point the ray reaches */
/* The monster's ground information (MH Generations' layout; MH4U's: owner_* below), and a hit block of the query */
#define OWNER_GROUND       0xD00
#define GROUND_HIT_Y       0x28                      /* f32: the hit's height */
#define GROUND_FLAGS       0x30                      /* u8 (the monster's +0xD30, OWNER_STATE_BYTE) */
#define GROUND_NO_SNAP     0x04                      /* in GROUND_FLAGS: the effect keeps its own height */
#define GROUND_Y           0x88                      /* f32 in OWNER_GROUND: the height the query returns apart */
#define GROUND_HIT_SIZE    0x38
#define OWNER_UP           0xD18                     /* vec3: the ground's normal (slot 23) */
#define UP_TINY            0x34000000                /* the bits of 2^-23: a squared length below it is none */
#define OWNER_SLOT_GROUND_A 39                       /* the monster's (uFestaChar's): the query's last argument */
#define OWNER_SLOT_GROUND_B 40                       /* (owner, 1): its seventh */
typedef u32 (*owner_ground_a_fn)(void *owner);
typedef u32 (*owner_ground_b_fn)(void *owner, int one);
/* sCollision's ground query (MH Generations 0x2F8C38, MH4U 0x2BA968): the ground between `point` and `top`
 * in the area; positive when it hits. The heights go to `height` and the hit blocks (hit2 has 8 bytes more
 * before the block). */
extern void *collision_manager;                      /* the variable holding sCollision */
int collision_ground(void *collision, const float point[4], const float top[4], u32 area, float height[1],
                     u8 hit[56], u32 filter_b, u8 hit2[64], u32 filter_a);

/* ---- building P and placing the drawn effect (core slots 31 and 32), the field list (slot 4)
 * and slot 2 ---- */
#define PARAMS_ROTATION    0x10                      /* vec3 (his in degrees) */
#define PARAMS_FOLLOW      0x38                      /* u8: how it follows (1: P kind 1) */
#define PARAMS_FINISH      0x3B                      /* u8: the effect's EFFECT_FINISH bits (0, 1, 2: 0, 1, 3) */
#define PARAMS_AXIS        0x3E                      /* u8: for the other binds, AXIS_IN_WORLD or kind 4's axis */
#define PARAMS_MASK_A      0x48                      /* u32, and mask B after it: the u64 the placing calls take */
#define PARAMS_EFFECT_112  0x50                      /* u16: the effect's EFFECT_112 when 1-600 */
#define AXIS_IN_WORLD      6
#define REC_SCRIPT         0x18                      /* in the record object: its rProofEffectParamScript, or 0 */
#define P_AXIS             0x08                      /* vec4 in P: kind 4's direction */
#define P_QUAT             0x18                      /* vec4 in P: a quaternion, the identity */
#define P_KIND_JOINT       0                         /* P's kinds (slot 31): on the owner's joint */
#define P_KIND_FOLLOW      1                         /* on the joint, following it */
#define P_KIND_IN_WORLD    3                         /* in the world, at the setup's position */
#define P_KIND_ON_AXIS     4                         /* along P_AXIS */
#define AXIS_OPPOSITE      0xBF7FBE77u               /* the bits of -0.999: a dot product's above it point against */
#define AXIS_ACROSS        0x3C23D70A                /* the bits of 0.01 */
#define HALF_TURN_HALF_ANGLE 1.57079637f             /* pi / 2 (0x3FC90FDB) */
#define EFFECT_PLACED      0x114                     /* in the drawn effect: bits 28-31 how it was placed */
#define EFFECT_PLACED_MASK 0xF0000000u
#define EFFECT_PLACED_JOINT 0x30000000u
#define EFFECT_POS         0x40                      /* vec4 */
#define EFFECT_SCALE       0x60                      /* vec4 */
#define EFFECT_ROT_ORDER   0x38                      /* u16 */
#define EFFECT_112         0x112                     /* u16 */
#define EFFECT_FINISH      0x118                     /* bits 0-3: how it finishes (0x2771A8) */
#define EFFECT_FINISH_MASK 0xFu
extern const float mt_vec3_x[4];                     /* (1, 0, 0, 0), written at start-up */
extern const float mt_vec3_z[4];                     /* (0, 0, 1, 0) */
extern const float mt_quat_identity[4];              /* (0, 0, 0, 1) */
ENGINE_VFP float mt_cosf(float x);
ENGINE_VFP float mt_sinf(float x);
/* uEffect's placing (MH Generations 0x9BF9C8, 0x9BFA4C, 0x9BFB94; MH4U 0xB001F0, 0xB00270, 0xB003AC) and its
 * resource with the element masks (0x9BD1F0; MH4U 0xAFD76C, the same code): `masks` is mask A, then mask B */
void effect_on_joint(void *effect, void *resource, u64 masks, const float quat[4], void *owner, s32 joint,
                     const u8 *params, u32 four);
void effect_in_world(void *effect, void *resource, u64 masks, const float quat[4], const u8 *params, u32 four);
void effect_on_axis(void *effect, void *resource, u64 masks, const float axis[4], const u8 *params, u32 rot_order,
                    u32 up);
void effect_set_list(void *effect, void *resource, u64 masks);

/* MT Framework's MtProperty (0x38 bytes): a field a class's createProperty (slot 4) lists by name, for the
 * engine's tools. MH4U builds the same (its cUnit's, 0x627518). */
typedef struct MtProperty {
    const char *name;
    u16 type;                                        /* PROP_* */
    u16 attr;
    void *owner;
    void *address;
    u32 unknown_10;
    u32 count;                                       /* 1 for an array (PROP_ARRAY) */
    u32 unknown_18;
    u32 get[2];                                      /* pointers to members (8 bytes each): none */
    u32 set[2];
    u32 zero[3];
} MtProperty;
#define PROP_CLASSREF      2
#define PROP_BOOL          3
#define PROP_U8            4
#define PROP_U32           6
#define PROP_S32           10
#define PROP_F32           12
#define PROP_COLOR         15
#define PROP_ARRAY         0x20                      /* in MtProperty.attr */
void property_add(void *list, const u32 property[14]);   /* MtPropertyList's add (0x4402E0; MH4U 0x342A14) */
void unit_create_property(void *unit, void *list);  /* cUnit's slot 4 (0x878AE4; MH4U 0x627518) */
u32 unit_slot2(void *unit);                          /* cUnit's slot 2: 0 (0x879120); MH4U's cUnit has none */

/* ---- the drawn effect (drawn.c) ---- */
#define EFFECT_CORE        0x210                     /* uProofEffect's: the core (as uProofEffectBase) */
#define EFFECT_SETUP       0x240                     /* its setup (P + P_SETUP) */
#define EFFECT_PARAMS      (EFFECT_P + P_PARAMS)     /* the record's parameters it plays */
#define EFFECT_PARENT      (EFFECT_SETUP + SETUP_OBJECT)   /* the setup's object: slot 1 gives the owner */
#define EFFECT_BASE_SCALE  0x308                     /* vec4 (1, 1, 1, 0): the placing's inputs, to +0x344 */
#define EFFECT_BASE_POS    0x318                     /* vec4 */
#define EFFECT_BASE_ANGLES 0x328                     /* vec4 */
#define EFFECT_BASE_338    0x338                     /* vec3 */
#define EFFECT_BASE_344    0x344                     /* f32 */
#define EFFECT_HELD        0x348                     /* u8 */
#define EFFECT_34C         0x34C
#define EFFECT_350         0x350                     /* f32 */
#define EFFECT_REBASE      0x354                     /* u8: slot 67 runs on the next update */
#define EFFECT_REBASE_MODE 0x355                     /* u8: 1 runs it with 0, 2 with 2 */
#define EFFECT_MH_CORE     0x358                     /* uMHProofEffect's: the core again */
#define EFFECT_SOUND_TIME  0x4E0                     /* f32: compared with EFFECT_SOUND_SPAN by entry */
#define EFFECT_PLACE_ARG   0x100                     /* f32: the effect's speed, the engine's (uEffect's slot 33); the
                                                      * placing's float, handed over and taken back */
#ifdef TARGET_GEN
#define EFFECT_PLACE_BASE  EFFECT_PLACE_ARG          /* what the placing is handed: the speed itself */
#else
#define EFFECT_PLACE_BASE  0x4E4                     /* f32: MH XX's +0x348, the speed the record's factor applies to,
                                                      * so that it does not pile up frame by frame; 1.0, or the
                                                      * speed when placed anew. In the padding of MH Generations' layout */
#endif
#define EFFECT_VISIBLE     0x800                     /* in the unit flags */
#define EFFECT_ELEMENTS    0x1F0                     /* uEffect's first element (a cParticle...), next at +8 */
#define EFFECT_SLOT_REBASE 67
#define CORE_SLOT_INDEX2   30                        /* the core's slot 30: the second color path's index */
#define EFFECT_QUAT        0x50                      /* vec4: uEffect's rotation */
/* What the placement (proof_place_math) hands back, 0x64 bytes */
#define PLACED_SIZE        0x64
#define PLACED_POS         0x00                      /* vec3 */
#define PLACED_POS2        0x10                      /* vec3 */
#define PLACED_ANGLES      0x28                      /* vec4 */
#define PLACED_SCALE       0x38                      /* vec3 */
#define PLACED_W           0x0C                      /* the w of the four vec4s, which the caller clears */
#define PLACED_ARG         0x48                      /* f32: the effect's EFFECT_PLACE_ARG */
#define PLACED_HAS_QUAT    0x4C                      /* u8: PLACED_QUAT is the effect's rotation */
#define PLACED_QUAT        0x50                      /* vec4 */
#define PLACED_VISIBLE     0x60                      /* u8 */
#define PLACED_MATRIX      0x61                      /* u8: set the rotation and position (never set by 0x2D2F44) */
#define ELEMENT_NEXT       0x08
#define ELEMENT_SLOT_DTI   5                         /* getDTI */
#define DTI_ID             0x04
#define DTI_PARENT         0x10
#define GENERATOR_COLOR(i) (0x168 + 4 * (i))         /* cParticleGenerator: two pairs of colors written */
#define GENERATOR_COLOR2(i) (0x170 + 4 * (i))
#define GENERATOR_BASE     0x178                     /* u32 *: the colors they start from (or 0) */
#define GENERATOR_BASE2    0x17C
#define NODE_TABLE_ENTRY   0x3C                      /* cParticleNode: bits 24-27 the second path's entry */
#define NODE_COLORS        4
#define PARAMS_COLOR_A     0x56                      /* u8: the color from table A */
#define PARAMS_COLOR2_A    0x57                      /* u8: the second path's from table A */
#define PARAMS_COLOR       0x60                      /* RGBA: the record's color */
#define PARAMS_COLOR_WEIGHT 0x68                     /* f32 */
#define PARAMS_COLOR_ON    0x70                      /* u8: 1 colors the elements */
#define PARAMS_COLOR_MODE  0x71                      /* u8: 0 mix, 1 the effect's blend, 2 multiply, other mix RGB */
#define PARAMS_COLOR2      0x74                      /* RGBA: the second path's color */
#define PARAMS_COLOR2_ON   0x82                      /* u8: 1 the second path (when PARAMS_COLOR_ON is not 1) */
#define PARAMS_COLOR2_C    0x83                      /* u8: the second path's from table C */
#define PARAMS_COLOR2_SLOT 0x84                      /* u16 */
#define COLOR_SLOT_STAGE   7                         /* table B's slot of the stage's color control */
#define OWNER_COLOR_DIM    0xD01                     /* u8 (MH Generations' monster; owner_color_dim): 1 dims RGB */
#define REGISTRY_TABLE_A   0x18                      /* sProofEffect's color tables: a count, its array at +0xC */
#define REGISTRY_TABLE_B   0x2C
#define REGISTRY_TABLE_C   0x40
#define TABLE_ARRAY        0x0C
#define COLORS_COUNT       0x64                      /* in a color table's resource: its entries */
#define COLORS_ENTRIES     0x70                      /* their pointers; an entry's color at +8 */
#define COLORS_COLOR       0x08
extern void *const proof_peffect_vtable[];           /* uProofEffect's */
extern void *const proof_effect_vtable[];            /* uMHProofEffect's */
extern const u8 proof_peffect_dti[];
extern const u8 proof_effect_dti[];
extern const u8 particle_generator_dti[];            /* cParticleGenerator's */
extern const u8 particle_node_dti[];                 /* cParticleNode's */
extern const u32 gen_color_zero;                     /* a zero color word (the one before proof_default_color) */
typedef const u8 *(*get_dti_fn)(void *obj);
typedef void (*rebase_fn)(void *effect, int mode);
void *effect_init(void *effect);                     /* uEffect's constructor (0x9C0538; MH4U 0xB00580) */
void *effect_fini(void *effect);                     /* its slot 0 (0x9C05B8; MH4U 0xB005FC) */
int effect_slot52(void *effect);                     /* its slot 52 (0x9BC570; MH4U 0xAFC6F8) */
void effect_update(void *effect);                    /* its slot 10 (0x9BFCB0; MH4U 0xAFCA0C) */
void unit_angles(void *unit, const float angles[4]); /* a rotation from three angles (0x94A384; MH4U 0x6D4708) */
void unit_set_matrix(void *unit, const float quat[4], const float pos[4], u32 rot_order);   /* 0x274508; 0x24BE24 */
/* not paired with MH4U's yet */
void effect_blend(u32 *out, void *effect, const u32 *color, const u32 *base);   /* 0x274EC8: the effect's blend */
void particle_color(u32 *out, void *node, u32 i);                               /* 0xA95D90: a node's color i */
void particle_set_color(void *node, const u32 *color, u32 i);                   /* 0x3A1D04 */

/* ---- the tied sounds (sounds.c) ---- */
/* rFestaPelTiedSe (the owner's OWNER_TIED_BODY): an MtArray of records, list 1's first */
#define TIED_COUNT         0x64                      /* u32 */
#define TIED_ARRAY         0x70                      /* u8 **: the records */
#define TIED_SPLIT         0x74                      /* u16: where list 1's records end and the others' start */
#define TIED_FIRST_LIST    1
/* a tied record */
#define TIED_REC_LIST      0x06                      /* u8 */
#define TIED_REC_ID        0x08                      /* u16: the PEL record id (a core's mUniqueId) it sounds for */
#define TIED_REC_OWNER     0x0A                      /* u8: the owner kind it plays for, or TIED_ANY_OWNER */
#define TIED_REC_BANK      0x0B                      /* u8: the bank's index */
#define TIED_REC_SOUND     0x0C                      /* u16: the sound id (the entry's value) */
#define TIED_REC_KIND      0x0E                      /* u8: the entry's kind */
#define TIED_REC_PARAM     0x0F                      /* u8: SOUND_PARAM_VALUE */
#define TIED_REC_WHO       0x10                      /* u8: with TIED_ANY_OWNER, which hunters (0 or 2) */
#define TIED_REC_HOW       0x11                      /* u8: SOUND_PARAM_HOW */
#define TIED_REC_VARIANT   0x12                      /* u8: SOUND_PARAM_VARIANT */
#define TIED_ANY_OWNER     8
/* nMHProofEffect::cSoundEventSetupParam (vtable 0xD793A4, 12 bytes): what a core's slot 44 copies into an
 * entry (ENTRY_PARAM, ENTRY_PARAM_B, ENTRY_PARAM_C) */
#define SOUND_PARAM_SIZE   12
#define SOUND_PARAM_VALUE  0x04                      /* u32 */
#define SOUND_PARAM_HOW    0x08                      /* u8: 0 on the owner, 1 at the effect's position, 2 on it;
                                                      * MH XX's 3: unplaced, on it (SOUND_HOW_UNPLACED) */
#define SOUND_HOW_UNPLACED 3
#define SOUND_PARAM_VARIANT 0x09                     /* u8: added to a state variant's sound id (0: none) */
extern void *const proof_sound_param_vtable[];
#define CORE_SLOT_ADD_SOUND 44
#define CORE_SLOT_AREA     49                        /* mAreaNo */
/* The owner (MH Generations' uFestaChar): its kind and its sound set (the banks sound_bank_get reads) */
#define OWNER_KIND         0xCF2                     /* u8 (MH Generations' monster; owner_kind) */
#define OWNER_HUNTER       0
#define OWNER_MONSTER      1
#define OWNER_KIND_2       2
#define OWNER_KIND_4       4
#define OWNER_STAND_IN     6                         /* the unit at COORD_PARENT stands for it, as a hunter */
#define OWNER_SHELL        8                         /* proof_shell_owner gives the owner */
#ifdef TARGET_GEN
#define owner_sound_set(o) ((u8 *)(o) + 0xDB4)
#else
#define owner_sound_set(o) ((u8 *)(o) + 0xD90)  /* the uEnemy's (0x9314E8 fills +0xD90 of the r6 whose +0xE28 is the em) */
#endif
#define OWNER_BANKS        14                        /* MH Generations' banks in a sound set (MH4U's: 11) */
#define HUNTER_SLOT_PLAIN_SOUND 113                  /* MH Generations' hunter: its effects' sounds unplaced */
#define EFFECT_SOUND_JOINT 0x280                     /* u16 handed to 0x46FAE4, which does not read it */
/* sSoundControl, the sound effects (MH Generations *0xDA9A48, MH4U *0xFCCD6C): its own banks (MH
 * Generations' offsets; MH4U's +0xA0 is the same, the others are open) */
extern void *sound_control;
#define CONTROL_BANK_0     0x88
#define CONTROL_BANK_1     0x8C
#define CONTROL_BANK_2     0x90
#define CONTROL_BANK_3     0x98
#define CONTROL_BANK_4     0xA0
#define CONTROL_BANK_5     0xA4
#define SOUND_KIND_EFFECT  0x0C                      /* the queue's request kind for an effect's sound */
#define SOUND_JOINT_NONE   (-1)
#define SOUND_VARIANT_A    0x31F                     /* the variant's base when mask B has VARIANT_A_BITS */
#define SOUND_VARIANT_B    0x333                     /* when it has VARIANT_B_BITS */
#define VARIANT_A_BITS     0x54
#define VARIANT_B_BITS     0x08
typedef int (*hunter_flag_fn)(void *hunter);
void *sound_bank_get(void *set, u32 i);              /* bank i of a sound set (0x639998; MH4U 0x39D330) */
/* the sound queue (0x3F52E8, 0x3F53E8, 0x3F5458; MH4U 0x312100, 0x31218C, 0x312200): a reference to `bank` */
void sound_queue_at_pos(void *control, int kind, void *bank, s32 id, void *a, const float *pos, void *b);
void sound_queue_plain(void *control, int kind, void *bank, s32 id, void *a, void *b);
void sound_queue_on_joint(void *control, int kind, void *bank, s32 id, void *a, void *b, int joint);
#ifndef TARGET_GEN
/* MH4U's unplaced queue (0x312098: way 0, `unit` the sound's; MH XX's 0x3F09A4 also takes the request's key, which
 * MH4U's leaves at -2: the control's next number). MH4U's 0x31218C, which sound_queue_plain names, queues on one
 * unit's joint (way 2) */
void sound_queue_unplaced(void *control, int kind, void *bank, s32 id, void *unit);
/* MH4U's queue itself: sSoundControl +0xD0, 64 requests of 0x24 bytes, each taken and freed by its move (0x2FB3DC)
 * once a frame; a request: +0 in use, +2 the kind, +0x10 the request, +0x20 the bank */
#define SOUND_QUEUE        0xD0
#define SOUND_QUEUE_COUNT  64
#define SOUND_QUEUE_SIZE   0x24
#define SQ_USED            0x00
#define SQ_KIND            0x02
#define SQ_REQUEST         0x10
#define SQ_BANK            0x20
#endif
/* MH Generations only: the adapter's in MH4U. A shell's owner
 * is the shells' getter, proof_shell_owner (0xAFCAA8, proof.h) */
int hunter_f48_bit2(void *hunter);                   /* 0xA831B0: a hunter's +0xF48 bit 2 */

/* ---- adapter, engine side (proof/adapter_4u.c) ---- */
/* uEffect's effect list (rEffectList, the same field in both games) and its blend record: MH4U's list keeps
 * its fields 4 bytes further on (MH Generations' body +0x64 and record +0x8C; MH4U's 0xAFA964, 0xCE64E8) */
#define EFFECT_LIST        0xF4
#define EFL_BODY           0x68                      /* u8 *: the file's body (MH4U) */
#define EFL_BLEND          0x90                      /* u32: the blend record's offset in the body, or 0 (MH4U) */
#define BLEND_ON           0x10                      /* in the record's byte 0 */
#define BLEND_WEIGHT       0x0C                      /* u16: out of 256 */
/* cParticleNode's colors, at the same offsets in both games (MH4U's 0xCDC9EC reads them as 0xA95AE0 does) */
#define NODE_COLOR(i)      (0x128 + 0x10 * (i))      /* 4 floats: R, G, B, A */
#define NODE_FLAGS         0x214
#define NODE_UNIT_COLORS   0x08000000                /* the colors go 0 to 1 (else 0 to 255) */
#define F32_255            0x437F0000                /* 255.0f */
#define F32_1_255          0x3B808081                /* 1 / 255.0f */
#ifndef TARGET_GEN
/* MH4U's local hunter, as its own code gets it (0x293008): player_get(*sPlayer, (s8) game control +0x2F) */
#define GAME_LOCAL_INDEX   0x2F                      /* s8 */
void *player_get(void *manager, s32 index);          /* MH4U 0xAF9AB0 (MH Generations 0xAFED1C) */
#endif

/* ---- adapter half 2, the monster side (proof/monster_4u.c). What the player reads or calls on its owner, the monster.
MH Generations' are fields and slots of
 * uFestaChar / uFestaEnemy (slots 39-111, a layer MH4U's uEnemy lacks). MH4U's are its em's fields with the
 * same code around them, functions paired by their code, or the port's own memory: the side, one per monster,
 * which the list proof_sides finds. ---- */
#ifdef TARGET_GEN
#define owner_state_flags(o)   FIELD(u32, o, OWNER_STATE_FLAGS)
#define owner_state_byte(o)    FIELD(u8, o, OWNER_STATE_BYTE)
#define owner_ground_y(o)      FIELD(float, o, OWNER_GROUND + GROUND_Y)
#define owner_ground_hit_y(o)  FIELD(float, o, OWNER_GROUND + GROUND_HIT_Y)
#define owner_ground_flags(o)  FIELD(u8, o, OWNER_GROUND + GROUND_FLAGS)
#define owner_up(o)            ((const float *)((u8 *)(o) + OWNER_UP))
#define owner_color_dim(o)     FIELD(u8, o, OWNER_COLOR_DIM)
#define owner_loop_frame(o)    FIELD(float, o, USER_FRAME_AT)
#define owner_kind(o)          FIELD(u8, o, OWNER_KIND)
#define owner_ids(o)           ((u32)(o) + OWNER_IDS)
#define owner_ground_a(o)      VSLOT(owner_ground_a_fn, o, OWNER_SLOT_GROUND_A)(o)
#define owner_ground_b(o)      VSLOT(owner_ground_b_fn, o, OWNER_SLOT_GROUND_B)(o, 1)
#define owner_create(o, list, data, bit, request) \
    VSLOT(owner_create_fn, o, OWNER_SLOT_CREATE)(o, list, data, bit, request)
#define owner_parent(o)        VSLOT(object_fn, o, OWNER_SLOT_PARENT)(o)
#define owner_create_core(o, handle, list, id, request, tied) \
    VSLOT(owner_create_core_fn, o, OWNER_SLOT_CREATE_CORE)(o, handle, list, id, request, tied)
#define owner_copied(o, copy)  VSLOT(owner_copied_fn, o, OWNER_SLOT_COPIED)(o, copy)
#define owner_pel(o, shells)   FIELD(const u8 *, o, (shells) ? OWNER_PEL_SHELLS : OWNER_PEL_BODY)
#define owner_tied(o, shells)  FIELD(void *, o, (shells) ? OWNER_TIED_SHELLS : OWNER_TIED_BODY)
#define owner_for_math(o)      (o)
#else
/* MH4U's monster (uEnemy): its em, and in it the ground record its update fills each frame (0x922340, which
 * pairs with MH Generations' 0x8BC580: the same probe 0x2B9FA8 / 0x8A63BC with em+0x5F0 / this+0xD00 as its
 * record). MH4U's record is 0x30 bytes (0x946430 copies it to +0x2C): it has no flags byte at +0x30. */
#define OWNER_EM           0xE28                     /* u8 *: the em (sdk/enemy_4u.h ENEMY_EM) */
#define EM_GROUND          0x5F0                     /* the ground record (MH Generations' monster +0xD00) */
#define EM_GROUND_HEIGHT   0x624                     /* f32: the probe's height (MH Generations' +0xD88) */
#define GROUND_STATE       0x08                      /* u32 in the record: the ground's flags (+0xD08) */
#define GROUND_UP          0x18                      /* vec3: its normal (+0xD18) */
#define GROUND_DIM         0x01                      /* u8 (+0xD01) */
/* The motion layer 0 (MH Generations' at this+0x248, MH4U's at this+0x240: the same layer, 8 bytes on) */
#define MOTION_NO_4U       0x244                     /* u16: list << 8 | motion (MH Generations +0x24C) */
#define MOTION_FRAME_4U    0x290                     /* f32 (+0x298) */
#define MOTION_LOOP_4U     0x298                     /* f32 (+0x2A0, USER_FRAME_AT) */
#define MOTION_SPEED_4U    0x29C                     /* f32 (+0x2A4) */
/* A shell of the port (owner_port_shell) has no em: the ground's fields, the dim byte and the ray's flags (its
 * slots 39 and 40) are its own, where MH Generations reads them (the port's shells fill their ground record at
 * +0xD00 and +0xD88 as MH Generations' do). Only the core and the drawn effect ask a shell; the rest below
 * (the sequence, the engine's requests, the side) have monsters as owners. */
#define owner_em(o)            FIELD(u8 *, o, OWNER_EM)
/* The ground record of the effect's owner, which need not be a monster: a shell of the port has no em (its
 * +0xE28 is 0, which Azahar logged as reads of 0x5F8 and 0x5F1) and its record is its own, at +0xD00 as in MH
 * Generations; a monster without an em reads zeros; proof_4u_ground (monster_4u.c) */
#define GROUND_HEIGHT_4U       (EM_GROUND_HEIGHT - EM_GROUND)
const u8 *proof_4u_ground(const void *owner);
float proof_4u_ground_y(const void *owner);
#define owner_state_flags(o)   FIELD(u32, proof_4u_ground(o), GROUND_STATE)
/* a monster's: MH4U's record ends before it: its builder 0x2B95A4 never reads attribute 2 and no MH4U collision
 * sets it, so 0 is what MH Generations' code would read on MH4U's maps */
#define owner_state_byte(o)    (owner_port_shell(o) ? FIELD(u8, o, OWNER_STATE_BYTE) : (u8)0)
#define owner_ground_y(o)      proof_4u_ground_y(o)
#define owner_ground_hit_y(o)  FIELD(float, proof_4u_ground(o), GROUND_HIT_Y)
#define owner_ground_flags(o)  owner_state_byte(o)   /* the same byte */
#define owner_up(o)            ((const float *)(proof_4u_ground(o) + GROUND_UP))
#define owner_color_dim(o)     FIELD(u8, proof_4u_ground(o), GROUND_DIM)
#define owner_loop_frame(o)    FIELD(float, o, MOTION_LOOP_4U)   /* a sequence's owner: a shell has none */
/* The side's owners are monsters (MH4U's has no kind byte); a shell of the port keeps MH Generations' uFestaChar
 * layout, its kind (8) at OWNER_KIND (owner_port_shell: its parent interface is the port's vtable, which only the
 * port writes and an MH4U monster never holds) */
#define owner_kind(o)          (owner_port_shell(o) ? FIELD(u8, o, OWNER_KIND) : (u8)OWNER_MONSTER)
#define owner_ids(o)           proof_4u_ids(o)
#define owner_ground_a(o)      (owner_port_shell(o) ? VSLOT(owner_ground_a_fn, o, OWNER_SLOT_GROUND_A)(o) \
                                : enemy_hit_flags(o))
#define owner_ground_b(o)      (owner_port_shell(o) ? VSLOT(owner_ground_b_fn, o, OWNER_SLOT_GROUND_B)(o, 1) \
                                : enemy_hit_attr_flags(o))
#define owner_create(o, list, data, bit, request) proof_owner_create(o, list, data, bit, request)
#define owner_parent(o)        proof_4u_parent(o)
#define owner_create_core(o, handle, list, id, request, tied) \
    proof_owner_create_core(o, handle, list, id, request, tied)
#define owner_copied(o, copy)  proof_4u_copied(o, copy)
#define owner_pel(o, shells)   proof_4u_pel(o, shells)
#define owner_tied(o, shells)  proof_4u_tied(o, shells)
#define owner_for_math(o)      proof_4u_math_owner(o)
/* MH Generations' slots 39 and 40 of a monster: the ground query's last and seventh arguments. MH4U calls the
 * same code directly (0x911D34 and 0x91DFC0 against 0xAEF598 and 0xAEF77C) */
u32 enemy_hit_flags(void *monster);
u32 enemy_hit_attr_flags(void *monster);

/* The side (one per monster, from its DTI's allocator; as many as there are monsters that play: proof_sides holds
 * the first, each side the next) */
#define SIDE_MONSTER       0x00
#define SIDE_USER          0x04                      /* IProofEffectSequenceUser: vtable, the monster (USER_OWNER) */
#define SIDE_PARENT        0x0C                      /* IProofEffectParent: vtable, the monster */
#define SIDE_PEL_BODY      0x14                      /* the PEL handles and tied sounds (MH Generations +0xEE0, */
#define SIDE_TIED_BODY     0x18                      /*   +0xEEC, +0x9ECC, +0x9ED0) */
#define SIDE_PEL_SHELLS    0x1C
#define SIDE_TIED_SHELLS   0x20
#define SIDE_MOTION_BITS   0x24                      /* MH Generations' monster +0xF74: the sequence's bits */
#define SIDE_IDS           0x28                      /* 4 ids, -1 free (MH Generations' monster +0xDB4 +0x11C) */
#define SIDE_SEQ           0x38                      /* the sequence's handle (+0xEE4, +0xEE8), for the hook */
#define SIDE_PROXY         0x40                      /* the parent the placement's mathematics reads */
/* What the engine's own requests on his body keep (engine.c): MH Generations' monster +0x9EE0 (the request its
constructor builds, 0x46F84C at 0x8A2630, and its
 * destructor finishes, 0x46F89C at 0x8A2A08), +0x9ED4 (the held effect's core), +0xA02C (0x8DE6D4's effect of
 * the shells' PEL, which MH4U's build never makes: 0 for good), +0xA030 (reaction 0x6E's timer) and its em's
 * +0x583C (+0xA02C's timer), which MH4U's monster has no counterpart of */
#define SIDE_REQUEST       0x2E8                     /* SIDE_PROXY + PROXY_SIZE; REQUEST_SIZE bytes */
#define SIDE_HOLD          0x3B8
#define SIDE_EFFECT        0x3BC
#define SIDE_TIMER_REACT   0x3C0                     /* f32 */
#define SIDE_TIMER_EFFECT  0x3C4                     /* f32 */
#define SIDE_NEXT          0x3C8                     /* the next side of proof_sides' list, 0 for the last */
#define SIDE_ENTRY         0x3CC                     /* his images' entry (entry_4u.c), a reference; 0: none */
#define SIDE_SIZE          0x3D0
#define SIDE_ALIGN         0x10
/* The proxy: MH Generations' layout of what 0x2D2F44 reads of its 12th argument, copied from the monster before each
placement */
#define PROXY_OWNER        0x04                      /* the monster (a cUnit zero word the code does not read) */
#define PROXY_STATE        0x0C                      /* MH Generations' cUnit flags */
#define PROXY_COORD        0x38                      /* uCoord's fields, at the same offsets in both games: */
#define PROXY_COORD_END    0x70                      /*   the order, position, quaternion and scale */
#define PROXY_WORLD_POS    COORD_WORLD_POS           /* vec3, the same in both (0x274508 / 0x24BE24): read for a */
#define PROXY_WORLD_END    (COORD_WORLD_POS + 0xC)   /*   record without a joint in bind 4's following (0x2D67CC) */
#define PROXY_MODEL        0xF0                     /* uModel's mpModel (MH4U 0x9611F8, MH Generations 0x955D34) */
#define PROXY_SPEED        0x2A4                     /* the motion's speed */
#define PROXY_SIZE         0x2A8
#define PROXY_SLOT_JOINT   21                        /* joint n's world matrix (uModel's slot 21 in both) */
/* A shell of the port has no side: its proxy lies in its own model part (+0xF0-0xC7F), which MH4U's build leaves
 * zero and nothing reads (proof/shell_4u.c model_init; only +0x130, MH4U's area, and +0x23C, the layers, are
 * written). Its motion's speed is MH Generations' uModel constructor's 1.0, which nothing changes for a shell. */
#define SHELL_PROXY_4U     0x800
#define SHELL_PROXY_SPEED  1.0f
#ifndef TARGET_GEN
/* The shadow MH4U's build makes where MH XX drops a blob shadow (adapter_4u.c shadow_drop), past the proxy in the same
unread part */
#define SHELL_SHADOW_4U    0xAB0                     /* void *: its uModel, 0 none */
#define SHELL_SHADOW_DROP_4U 0xAB4                   /* u8: a drop came since slot 9 last began */
#endif
typedef float *(*joint_matrix_fn)(void *unit, s32 joint);
/* The sides of the monsters that play (game/executable/blocks.py): the first of a list each side links on (SIDE_NEXT), and
 * how many there are. One per monster, as MH Generations keeps the same fields in each monster: any number of
 * ported monsters at once, of one species or several. */
struct proof_side_list {
    u8 *first;
    u32 count;
};
extern struct proof_side_list proof_sides;
extern void *const proof_4u_user_vtable[];
extern void *const proof_4u_parent_vtable[];
extern void *const proof_4u_proxy_vtable[];
u8 *proof_4u_side(const void *monster);              /* the monster's side, or 0 */
u8 *proof_4u_side_new(void *monster);
void proof_4u_side_delete(void *monster);
void *proof_4u_parent(void *monster);                /* MH Generations' slot 74 */
void proof_4u_copied(void *monster, u32 *copy);      /* slot 58 */
const u8 *proof_4u_pel(void *monster, int shells);
void *proof_4u_tied(void *monster, int shells);
u32 proof_4u_ids(void *monster);
void *proof_4u_math_owner(void *monster);
u32 proof_4u_mood_bits(void *monster);               /* uFestaEnemy's slot 77's bits (0x8A30A8) */
u32 enemy_is_angry(uEnemy *monster);                 /* MH4U 0x954E48 (MH Generations 0xAF0040); as em_api.h */
#define EM_TIRED           0x51C                     /* u8: 2 or 3 tired (MH Generations em+0x4A4, 0xAEF830) */
/* His PEL and PSL images (proof_data.py): a PEL copied to the heap and relocated, a PSL used in place. An image's
 * resource object has no vtable (+0); the port keeps its references itself, or its entry does (IMAGE_ENTRY) */
#define IMAGE_SIZE         0x00                      /* in a packed image's header */
#define IMAGE_ROOT         0x04
#define IMAGE_POINTERS     0x08
#define IMAGE_HEADER       0x10
#define IMAGE_ENTRY        0x40                      /* an image in his archive's entry: the entry, which counts */
#define IMAGE_REFS         0x48                      /* in the copy's resource object (MH4U cResource's count) */
#define IMAGE_ALLOCATOR    0x4C                      /* where the copy came from (0: in place, never freed) */
#define IMAGE_BLOCK        0x44                      /* the copy's block (its root may not be at 0) */
u8 *proof_4u_image_load(const u8 *packed, const void *dti);
void proof_4u_add_ref(void *resource);
void proof_4u_release(void *resource);
#define resource_add_ref   proof_4u_add_ref          /* a port image or MH4U's resource */
#define resource_release   proof_4u_release
/* His images as one entry of his archive (entry_4u.c, image_entry.py): an rQuestInfoTbl, its file whole in a buffer */
#define ENTRY_BUFFER       0x64                      /* rQuestInfoTbl: the file, 16-aligned */
#define ENTRY_BUFFER_SIZE  0x68                      /*   and its size */
#define ENTRY_LOAD_NOW     1                         /* sResource's slot 0x38 mode that reads at once (B127) */
#define ENTRY_PATH         "enemy\\em000\\proof\\em000_images"   /* image_entry.path */
#define ENTRY_PATH_ID      8                         /* his id's three digits */
#define ENTRY_PATH_ID2     20
#define ENTRY_MAGIC_AT     0x00                      /* the file's header (image_entry.HEADER_FORM) */
#define ENTRY_MAGIC        0x45494648                /* "HFIE" */
#define ENTRY_VERSION_AT   0x04
#define ENTRY_VERSION      1
#define ENTRY_BASE         0x08                      /* where its pointers were fixed for (0 in the file) */
#define ENTRY_ROWS         0x0C
#define ENTRY_POINTERS     0x10
#define ENTRY_LIST         0x14                      /* the pointer list's offset */
#define ENTRY_SIZE_AT      0x18
#define ENTRY_HEADER       0x20
#define ENTRY_DIRECTORY    0x20                      /* its rows: */
#define ENTRY_ROW          8
#define ENTRY_ROW_KIND     0                         /*   u8 */
#define ENTRY_ROW_INDEX    1                         /*   u8 */
#define ENTRY_ROW_ROOT     4                         /*   u32: the root's offset (a PEL: its packed image's) */
#define ENTRY_KIND_PEL     1                         /* index 0 body (c), 1 shells (u) */
#define ENTRY_KIND_PSL     2                         /* index: the PSL slot */
#define ENTRY_KIND_TIED    3                         /* index 0 c, 1 u */
#define ENTRY_KIND_SHELL   4                         /* index: his shell kind's row */
#define ENTRY_KIND_LINKED  5                         /* a tied sounds file of his base's his shells name */
extern const u8 quest_info_tbl_dti[];               /* rQuestInfoTbl's DTI */

u8 *proof_4u_entry_get(u32 id);                     /* his entry, with a reference; 0 none */
void *proof_4u_entry_root(const u8 *entry, u32 kind, u32 index);
void proof_4u_entry_keep(void *monster, u8 *entry);
void proof_4u_entry_let_go(void *monster);
void *proof_4u_entry_shell(u32 id, u32 n);           /* his shell kind row n's rShell, with a reference */
#endif

/* ---- hook: what puts the player into his MH4U build ---- */
#define REGISTRY_EMPTY     0x64                      /* the empty handle (index -1) */
#define SEQ_COPY_SIZE      0x14C                     /* the copy of a motion's sequence data (0x66BBC4) */
void *mt_new(u32 size, const void *nothrow);         /* operator new (std::nothrow): the default allocator */
#ifdef TARGET_GEN
extern const u8 proof_nothrow[];                     /* MH Generations' std::nothrow, every caller's r1 */
#define MT_NOTHROW         proof_nothrow
#else
#define MT_NOTHROW         0                         /* MH4U's operator new never reads it */
#endif
/* uMhEffectSequenceManager: the unit on sUnit's line 20 that moves every sequence (0x5C0B98) */
#define UNIT_MGR_SIZE      0x30
#define UNIT_MGR_LINE      20
extern void *const proof_unit_vtable[];
extern const u8 proof_unit_dti[];
/* The local hunter's slot 113 (MH Generations' uPlayerQuest 0xA8DC54: +0x21CA != 0), asked only when an
 * effect's owner is the local hunter; in MH4U the adapter's (MH4U's owners are monsters) */
#ifdef TARGET_GEN
#define hunter_plain_sound(h) VSLOT(hunter_flag_fn, h, HUNTER_SLOT_PLAIN_SOUND)(h)
#else
int hunter_plain_sound(void *hunter);
/* proof/hook_4u.c: the entry points his MH4U build calls (src/probe_fx.c) */
int proof_4u_start(void);                            /* the managers, once: 1 when they are there */
int proof_4u_monster_setup(void *monster, const u8 *pel_body, const u8 *pel_shells, void *const psls[7]);
void proof_4u_monster_delete(void *monster);
u32 *proof_4u_motion_bits(void *monster);            /* the side's motion bits, 0 with no side */
void *proof_4u_effect_request(void *monster, u32 kind, u32 id);   /* MH Generations' 0x8A1BF4 */
/* tied sounds: the side's +0xEEC / +0x9ED0 (MH Generations' 0x8A0E70), resources in place (proof_data.py) */
void proof_4u_monster_tied(void *monster, void *body, void *shells);
/* the engine's effects on his body: the calls MH4U's enemy code makes, hooked (proof_hook.ENGINE_HOOKS) */
void proof_4u_effects(void *monster);                /* 0x913E78: bl 0x919F38 */
void proof_4u_status(void *monster);                 /* 0x913E84: bl 0x945418 */
void proof_4u_bomb(void *monster);                   /* 0x917998, 0x827798: bl 0x934BDC */
void *proof_4u_mode_up(void *component, u32 id, s32 kind);     /* 0x91B1F8: bl 0x390F9C (MEF 1000) */
void *proof_4u_mode_down(void *component, u32 id, s32 kind);   /* 0x91B228: bl 0x390F9C (MEF 1001) */
void proof_4u_step(void *monster);                   /* 0x955E6C: bl 0xB07D60 */
void proof_4u_area_changed(void *monster);           /* his slot 55 */
void proof_4u_break(void *monster, u32 part, u32 x);   /* 0x9207EC, 0x9211AC, 0x93C30C: bl 0x944E80 */
void proof_4u_cut(void *monster, u32 n, u32 flags);  /* after 0x94E39C (sdk/enemy_4u.h) */
#endif

/* ---- the drawn effect's slots 66 and 67 (drawn2.c) ---- */
#define PARAMS_GROUND_UP   0x54                      /* u8: slot 67 asks the core's slot 23 for EFFECT_BASE_338 */
#define CORE_SLOT_UP       23                        /* the ground's normal: (core, out, the point) */
#define EFFECT_SLOT_KILL   16
#define EFFECT_SLOT_28     28                        /* uEffect's slot 28: how finish states 0-2 end */
#define UNIT_ENDS_BY_RULE  0x400                     /* in the unit flags: in state 2, the finish follows the rule */
#define ENTRY_KIND_END     4                         /* a sound entry the finish requests */
typedef void (*core_up_fn)(void *core, float *out, const float *point);
void unit_get_angles(float out[4], const void *unit);   /* angles of +0x50 in order +0x38 (0xAFAFE0; MH4U 0xD00CC0) */
int effect_finish_step(void *effect);                /* by +0x118 & 0xF: 1 in state 1 (0x2771A8; MH4U 0x24EA98) */

/* ---- the drawn effect's slots 6, 9, 16, 35 and 51 (drawn3.c) ---- */
#define ATTR_PLACE_NEXT    0x10                      /* the core's mAttr: an effect added is placed on its next update */
#define EFFECT_ADDED_OFF   0x08000000u               /* in EFFECT_FINISH: cleared when the effect is added */
#define EFFECT_FLAGS_F0    0xF0                      /* uEffect's flags */
#define EFFECT_ADDED_ON    0x200                     /* in EFFECT_FLAGS_F0: set when the effect is added */
#define EFFECT_FADE        0x180                     /* 8 floats: 1 to 0 while a held effect fades out */
#define EFFECT_FADE_COUNT  8
#define FADE_ASKED         1                         /* EFFECT_34C: the finish asked for the fade (slot 66) */
#define FADE_RUNNING       10                        /* EFFECT_34C: fading; EFFECT_350 counts its frames */
#define PARAMS_FADE        0x46                      /* u16: the fade's frames */
#define EFFECT_SPAWNS      0x4800                    /* in the unit flags: both bits let slot 51 make a child */
#define CORE_SLOT_AREA     49                        /* the core's mAreaNo */
#define OWNER_SLOT_EFFECT_ADDED 65                   /* (owner, effect): a drawn effect of it was added */
#define ENTRY_KIND_KILL    3                         /* a sound entry the kill requests */
/* rEffectList's child list (the list a child effect plays): MH Generations' 0x9BC8C8 reads +0x7C where MH4U's
 * same function, 0xAFD20C, reads +0x80 (the list's fields are 4 bytes further on, as EFL_BODY) */
#ifdef TARGET_GEN
#define EFL_CHILD          0x7C
#else
#define EFL_CHILD          0x80
#endif
typedef void (*owner_added_fn)(void *owner, void *effect);
typedef void *(*new_drawn_fn)(void *core);
#ifdef TARGET_GEN
#define owner_effect_added(o, e) VSLOT(owner_added_fn, o, OWNER_SLOT_EFFECT_ADDED)(o, e)
#else
/* the side's owners are monsters, and uFestaEnemy's slot 65 is empty (0x1EC884; his module keeps it) */
#define owner_effect_added(o, e) ((void)(o), (void)(e))
#endif
void effect_move(void *effect);                      /* uEffect's slot 9 (0x9BF6A8; MH4U 0xAFFE6C) */
void *effect_new(u32 size, u32 align);               /* uEffect's operator new (0x9C05E0; MH4U 0xB00624) */
/* sunit_add with `like`'s unit group (0x894E44; MH4U 0x64605C) */
int sunit_add_like(void *sunit, u32 line, void *unit, void *like);

/* ---- the engine's effects on his body (engine.c) ----
 * uFestaEnemy's own requests for records of the body's PEL (`c`), list 2, through 0x8A1B5C with the monster's
 * kept request: his states (status effects, reaction 0x6E, mMode, the ground, a bomb's hit, the held effect).
 * MH Generations' fields are the monster's and its em's (+0xFAC); MH4U's are its em's where code both games share
 * keeps the same state (the pairs are in the doc), or the side's. The monster ids MH Generations' code compares
 * are his there (the resource set's em 50): the player plays for him alone. */
#define ENGINE_LIST        2                         /* the body's PEL's list 2 */
#define ENGINE_FX_BITS_2   0x44C                     /* enemy_bits 2 (1100) */
#define ENGINE_FX_BITS_4   0x44D                     /* enemy_bits 4: paralysis (1101; its tied sound is ef_mahi) */
#define ENGINE_FX_SPECIAL  0x44E                     /* enemy_special_state 1 (1102) */
#define ENGINE_FX_HOLD     0x44F                     /* held: enemy_bits 0x10, the em's flag 0x58A6, its timer 0x53C
                                                      * (1103) */
#define ENGINE_FX_REACTION 0x451                     /* reaction 0x6E (1105) */
#define ENGINE_FX_5978     0x452                     /* em+0x5978 above 0 (1106) */
#define ENGINE_FX_5978_B   0x453                     /* the same for MH Generations' small monsters 7 and 8 (1107) */
#define ENGINE_FX_58E4     0x454                     /* em+0x58E4 above 0 (1108) */
#define ENGINE_FX_BOMB     0x46A                     /* a bomb's hit: + the bomb table's entry (1130-1137) */
#define ENGINE_FX_MODE_UP  0x4B0                     /* mMode 0 -> 2 (1200) */
#define ENGINE_FX_MODE_DOWN 0x4B1                    /* mMode 2 -> 0 (1201) */
#define ENGINE_FX_GROUND   0x5DC                     /* down on the ground while em+0x59B4 is above 0 (1500) */
#define ENGINE_FX_TIRED    0x450                     /* the tired breath (1104: Mizutsune's drool, cm200_006) */
#define ENGINE_FX_ANGRY    0x461                     /* the angry breath, of the shells' PEL (0x460 by slot 161) */
#define ENGINE_FX_ANGRY_ALT 0x460
#define ENGINE_BREATH_ANGRY 30.0f                    /* frames between two breaths */
#define ENGINE_BREATH_TIRED 48.0f
#define ENGINE_HOLD_COLOR  0xFF0000FF                /* the held effect's color for MH Generations' monster 3 */
#define ENGINE_HOLD_COLOR_ON 0x20000                 /* in SETUP_OVERRIDES_A: PARAMS_COLOR is the setup's */
#define GEN_ID_SMALL_7     0x1007                    /* MH Generations' id words (id | 0x1000 for a small monster) */
#define GEN_ID_SMALL_8     0x1008
#define GEN_ID_3           3                         /* and id bytes */
#define GEN_ID_9           9
#define TUNING_BOMBS       0x54                      /* in the species' tuning record: the bomb table */
#define EM_UNIT_FLAG_1     1                         /* in the low byte of the em's unit flags both games test */
#define TURN_SPAN_SMALL    0x34000000                /* the turn span's bits below which +0xA02C's effect ends */
#ifdef TARGET_GEN
#define OWNER_EM_GEN       0xFAC
#define owner_em(o)        FIELD(u8 *, o, OWNER_EM_GEN)
#define EMX_UNIT_FLAGS     0x1A8                     /* u8 */
#define EMX_STATUS         0x1BA                     /* u8 mStatus */
#define EMX_STATUS_SUB     0x1BB                     /* u8 */
#define EMX_TURN_SPAN      0x1F0                     /* s32 (a float read as bits) */
#define EMX_MODE           0x2C0                     /* u8 mMode */
#define EMX_HOLD_TIMER     0x53C                     /* f32 */
#define EMX_HEIGHT         0x554                     /* f32: the ground probe's height */
#define EMX_MONSTER3_4F1   0x4F1                     /* u8 (MH Generations' monster 3) */
#define EMX_TIMER_BITS_2   0x5824                    /* f32 timers */
#define EMX_TIMER_STATE    0x5828
#define EMX_TIMER_58E4     0x582C
#define EMX_TIMER_5978     0x5830
#define EMX_TIMER_ANGRY    0x5834                    /* the breaths' (0x8E4360) */
#define EMX_TIMER_TIRED    0x5838
#define EMX_TIMER_EFFECT   0x583C
#define EMX_TIMER_GROUND   0x5840
#define EMX_FLAG_58A6      0x58A6                    /* u8 */
#define EMX_BOMB_INDEX     0x5970                    /* u8: the bomb table's entry of the last hit */
#define EMX_GROUND_GAUGE   0x59B4                    /* f32 */
#define EMX_TIMER_SPECIAL  0x59E4                    /* f32 */
#define OWNER_SLOT_OUT_OF_ACTION 212                 /* (monster): mActSt 11 or 14, or the action (12, 0xFF) */
#define owner_request(o)       ((u8 *)(o) + 0x9EE0)
#define owner_hold(o)          FIELD(u8 *, o, 0x9ED4)
#define owner_engine_effect(o) FIELD(u8 *, o, 0xA02C)
#define owner_timer_react(o)   FIELD(float, o, 0xA030)
#define owner_timer_effect(o)  FIELD(float, owner_em(o), EMX_TIMER_EFFECT)
#define owner_hold_off(o)      FIELD(u8, o, 0x6CEC)  /* only roEm084 writes it */
#define owner_gen_id_word(o)   FIELD(u16, o, 0x9E98)
#define owner_gen_id_byte(o)   FIELD(u8, o, 0x9E9C)
#define owner_gen_variant(o)   FIELD(u8, o, 0x9E9F)
#define owner_monster3_4f1(o)  FIELD(u8, owner_em(o), EMX_MONSTER3_4F1)
#define owner_out_of_action(o) VSLOT(core_u32_fn, o, OWNER_SLOT_OUT_OF_ACTION)(o)
#define OWNER_SLOT_BREATH  171                       /* (monster): it breathes at all (his: 1) */
#define OWNER_SLOT_BREATH_ALT 161                    /* (monster): the angry breath is 0x460 (his: 0) */
#define owner_breath_on(o)     VSLOT(core_u32_fn, o, OWNER_SLOT_BREATH)(o)
#define owner_breath_alt(o)    VSLOT(core_u32_fn, o, OWNER_SLOT_BREATH_ALT)(o)
#define owner_angry_breath(o)  FIELD(u8, o, 0xA03A)  /* Alatreon's init clears it */
ENGINE_VFP u32 enemy_timer_down(void *monster, float *t, float rate);   /* 0x8AA300 */
#define owner_timer_down(o, t) enemy_timer_down(o, t, 1.0f)
void enemy_effect_area(void *monster);               /* 0x8E0718: +0xA02C's effect takes the monster's area */
#else
#define EMX_UNIT_FLAGS     0x1B4                     /* the low byte of the word MH4U tests */
#define EMX_STATUS         0x1C8
#define EMX_STATUS_SUB     0x1C9
#define EMX_TURN_SPAN      0x238
#define EMX_MODE           0x34C
#define EMX_HOLD_TIMER     0x5DC
#define EMX_HEIGHT         0x624
#define EMX_TIMER_BITS_2   0x791C
#define EMX_TIMER_STATE    0x7920
#define EMX_TIMER_58E4     0x7924
#define EMX_TIMER_5978     0x7928
#define EMX_TIMER_ANGRY    0x792C                    /* MH4U's breath timers (0x919F38: MEF 1020-1025, 1009) */
#define EMX_TIMER_TIRED    0x7930
#define EMX_TIMER_GROUND   0x7934
#define EMX_FLAG_58A6      0x79B1
#define EMX_BOMB_INDEX     0x7AB8
#define EMX_GROUND_GAUGE   0x7E74
#define EMX_TIMER_SPECIAL  0x7EA4
#define GEN_ID_ALATREON    50                        /* his id in MH Generations (word and byte; variant 0) */
#define owner_request(o)       (proof_4u_side(o) + SIDE_REQUEST)
#define owner_hold(o)          FIELD(u8 *, proof_4u_side(o), SIDE_HOLD)
#define owner_engine_effect(o) FIELD(u8 *, proof_4u_side(o), SIDE_EFFECT)
#define owner_timer_react(o)   FIELD(float, proof_4u_side(o), SIDE_TIMER_REACT)
#define owner_timer_effect(o)  FIELD(float, proof_4u_side(o), SIDE_TIMER_EFFECT)
#define owner_hold_off(o)      ((void)(o), (u8)0)    /* only roEm084 sets it in MH Generations */
#define owner_gen_id_word(o)   ((void)(o), (u16)GEN_ID_ALATREON)
#define owner_gen_id_byte(o)   ((void)(o), (u8)GEN_ID_ALATREON)
#define owner_gen_variant(o)   ((void)(o), (u8)0)
#define owner_monster3_4f1(o)  ((void)(o), (u8)0)    /* read only for MH Generations' monster 3 */
u32 enemy_out_of_action(void *monster);              /* MH4U 0x94D7A8 (MH Generations' slot 212, 0xAF0008) */
#define owner_out_of_action(o) enemy_out_of_action(o)
/* the breath's slots are MH Generations' (his module's: 1 and 0); MH4U has no +0xA03A: his port record holds what
 * MH Generations leaves there (proof_port_angry_breath) */
#define owner_breath_on(o)     ((void)(o), 1u)
#define owner_breath_alt(o)    ((void)(o), 0u)
#define owner_angry_breath(o)  proof_port_angry_breath(o)
/* MH Generations' 0x8AA300 at rate 1: counts down by the unit's delta, 1 once it is out (as sdk/enemy_4u.h's
 * enemy_timer_down; MH4U's own 0xB0709C zeroes it then, which the next call does here) */
static inline u32 owner_timer_down(void *o, float *t)
{
    if (*t <= 0.0f) {
        *t = 0.0f;
        return 1;
    }
    *t -= unit_delta(o);
    return *t <= 0.0f;
}
#define enemy_effect_area(o)   ((void)(o))           /* +0xA02C's effect: never made in MH4U's build */
#endif
#define EMF(o, field)      FIELD(float, owner_em(o), field)
#define EMB(o, field)      FIELD(u8, owner_em(o), field)
u32 enemy_bits_test(uEnemy *self, u32 mask);         /* 0x8CFEDC, MH4U 0x936418 (as em_api.h) */
u32 enemy_is_action(uEnemy *self, u32 st, u32 no);   /* 0xAEE338, MH4U 0x94D788 (as em_api.h) */
u32 enemy_special_state(void *monster, u32 mode);   /* 0x8F1D40, MH4U 0x95557C */
u32 enemy_is_tired(uEnemy *monster);                 /* tiredness state 2 or 3: 0xAEF830, MH4U 0x92E998 */
u32 enemy_is_angry(uEnemy *monster);                 /* mFightLevel 1: 0xAF0040, MH4U 0x954E48 */
u32 enemy_positive_58e4(void *monster);              /* em+0x58E4 > 0: 0x8BD5D0, MH4U 0x9239FC (em+0x7A34) */
u32 enemy_positive_5978(void *monster);              /* em+0x5978 > 0: 0x8C9538, MH4U 0x9306E4 (em+0x7AC0) */
u32 enemy_in_control_area(void *monster);            /* mAreaNo is the game's: 0x8EAFA8, MH4U 0x94DEEC */
u8 *enemy_species_tuning(void *monster);             /* the species' tuning record: 0x8A1060, MH4U 0x93863C */

/* ---- the engine's effects of his shells' PEL (`u`), list 2 (engine.c): uFestaEnemy asks them through 0x8A1BF4 with
the monster's kept request: his tail's cut (0x8DD2D0,
 * the end of 0x8EB070) and a part's break (0x8E3F44, from 0x8DD0C8, which also registers the break's reward).
 * The break records are the monster's DTP records (rEnemyDtBaseParts +0x60): MH Generations' 3 bytes [part, level,
 * reward bit, | 0x80 when every part of that bit must break]; XX's 4 bytes [part, level, G rank's level, reward
 * bit] (XX's 0x8CDD4C: the level of byte 2 from quest rank 5 on), which every port's block holds (product.
 * his_thresholds) and MH4U's side reads; MH4U's 0x944E80 reads a table of its emd instead. ---- */
#define ENGINE_FX_CUT      0x384                     /* cut record 0 (900); any other 901 */
#define ENGINE_FX_BREAK    0x3E7                     /* + part * 5 + level (999: horn 1000 and 1001, ... 1031) */
#ifdef TARGET_GEN
#define BREAK_RECORD       3                         /* bytes per DTP record: MH Generations' */
#define BREAK_REWARD       2                         /* the reward byte's place in it */
#else
#define BREAK_RECORD       4                         /* bytes per DTP record: XX's */
#define BREAK_REWARD       3
#define BREAK_RANK_G       5                         /* the quest rank from which byte 2 is the level (XX's 5) */
#endif
#define BREAK_END          0xFF                      /* a part 0xFF ends them; a level 0xFF is never broken */
#define BREAK_ALL          0x80                      /* in the reward byte: every part of the bit must break */
#define NET_BREAK_KIND     5                         /* the network message a reward sends: (monster, 5, 2) */
#define NET_BREAK_ARG      2
typedef void (*part_fn)(void *monster, u32 part);
void enemy_net_send(void *monster, u32 kind, u32 arg);   /* 0x8B414C, MH4U 0x917E84 (em050/pairs.py) */
#ifdef TARGET_GEN
#define EMX_PARTS          0x3A6                     /* u8: part 0's break level, 6 bytes per part */
#define EMX_REWARDS        0x5886                    /* u8: the reward bits registered (s8 when tested) */
#define EMX_REWARD_SUB     0x587E                    /* u8: 0x8A5DA4's second argument */
#define OWNER_SLOT_PART_BROKEN 140                   /* (monster, part): empty in uFestaEnemy and his (0x8D5138) */
#define owner_dtp(o)           FIELD(u8 *, o, 0x6C98)            /* rEnemyDtBaseParts */
#define owner_dtp_count(o, dtp) ((void)(o), FIELD(u8, dtp, 0x84))
#define owner_dtp_records(o)   FIELD(const u8 *, owner_dtp(o), 0x60)
#define owner_break_level_at(o) ((void)(o), 1)                   /* a record's level byte */
/* the quest's record of a broken part: (the monster's id word, em+0x587E, bit, 0, x) */
void gen_part_reward(u32 id, u32 sub, u32 bit, u32 zero, u32 x);   /* 0x8A5DA4 */
#define owner_part_reward(o, bit) gen_part_reward(owner_gen_id_word(o), EMB(o, EMX_REWARD_SUB), bit, 0, 0)
#else
#define EMX_PARTS          0x42E                     /* the same, read at the same place of 0x944E80 */
#define EMX_REWARDS        0x7987
#define EMX_REWARD_ID      0x1C0                     /* u8: the monster's id, 0x6A8920's second argument */
#define OWNER_SLOT_PART_BROKEN 64                    /* uEnemy's (0x93C18C, empty): 0x944E80's last call */
/* A ported monster's record: what the shared code (the player, the
 * shell framework) needs of him, by his id. The product fills one per ported monster in mhgen_port_monsters
 * (product.port_table, proof_blocks.PORT_RECORD: keep both in step); the includer of src/player.c defines
 * proof_port_of and proof_port_at (src/port_table.c for the product, src/probe_fx.c for the probes). */
/* A row of MH Generations' kind table (0xCA2B2C; sdk/shell_api.h KIND_*): the class's DTI (sShell's create builds
 * the shell through its slot 2), its setup parameter's DTI (create compares its id with the parameter's) and the
 * rShell's file id (sShell's register loads it) */
struct proof_shell_kind {
    const void *class_dti, *setup_dti;
    u32 file;
};
/* A ported shell class's DTI and the DTI vtable of its own whose slot 2 (newInstance) builds it: `new_fn`, the
 * class's size (its word +0x18, with heap 13, "Unit/Area", MH4U's own shells' heap) and MT's id of `name`
 * (~crc32(name) & 0x7FFFFFFF), laid out as hook_4u.c's DTIs */
#define PROOF_CLASS_DTI(sym, new_fn, name, parent, size, id)                       \
    "    .global " #sym "_vtable\n"                                                 \
    "    .balign 4\n"                                                               \
    #sym "_vtable:\n"                                                               \
    "    .word proof_4u_nothing, proof_4u_nothing, " #new_fn "\n"                   \
    "    .global " #sym "\n"                                                        \
    "    .balign 4\n"                                                               \
    #sym ":\n"                                                                      \
    "    .word " #sym "_vtable, 1f, 0, 0, " #parent ", 0, " #size " | 0x6800000, " #id "\n" \
    "1:  .asciz \"" name "\"\n"
struct proof_port {
    u32 id;                                          /* his monster id; 0: an empty record */
    const u8 *thresholds;                            /* his DTP break records ({c_prefix}_break_thresholds) */
    const u8 *pel_c, *pel_u;                         /* his packed PEL images ({prefix}_pel_c, _u) */
    void *const *psl_roots;                          /* his PSLs' resource objects ({prefix}_psl_roots) */
    u16 psls;                                        /* how many (up to 7) */
    u8 angry_breath;                                 /* MH Generations' +0xA03A for him (owner_angry_breath) */
    u8 breaks;                                       /* his block's break records (BREAK_RECORD bytes each; XX's
                                                      * DTP count, +0x88); 0: none */
    void *const *tied_roots;                         /* his tied sounds' resource objects: c, u ({prefix}_tied_roots) */
    void (*motion_bits)(uEnemy *self, u32 motion);   /* his own motion bits ({c_prefix}_motion_bits) */
    /* His shells: his kinds' rows of MH Generations' kind table
     * ({prefix}_shell_kinds, in his code block), his rShells' images ({prefix}_shell_roots, row by row), his first
     * kind and how many; 0 without shells. proof/shell_4u.c finds a kind's row and a file's rShell in them. */
    const struct proof_shell_kind *shell_kinds;
    void *const *shell_roots;
    u32 shell_first, shell_count;
    /* 1: his images are the entry of his archive his id names (entry_4u.c; the product), and pel_c, pel_u, psl_roots,
     * tied_roots and shell_roots are 0; 0: those five (a probe's images in the executable) */
    u32 images;
};
const struct proof_port *proof_port_of(void *monster);   /* his record, or 0: not a ported monster */
const struct proof_port *proof_port_at(u32 k);           /* record k (0 to PROOF_PORT_RECORDS - 1), or 0 */
#define PROOF_PORT_RECORDS 76                        /* new_id_data.NEW_IDS */
static inline u8 *proof_port_dtp(void *o)
{
    const struct proof_port *port = proof_port_of(o);

    return port ? (u8 *)port->thresholds : 0;
}
/* MH Generations' +0xA03A for him, the switch of the engine breath's angry part (0x8E4360): uEnemy's constructor
 * sets it to 1 (0x8F2540), some species' inits clear it (Alatreon's), roEm082 never writes it */
static inline u32 proof_port_angry_breath(void *o)
{
    const struct proof_port *port = proof_port_of(o);

    return port ? port->angry_breath : 0;
}
static inline u32 proof_port_breaks(void *o)
{
    const struct proof_port *port = proof_port_of(o);

    return port ? port->breaks : 0;
}
extern void *quest_manager_4u;                       /* the variable holding the quest manager */
s32 quest_rank_4u(void *manager);                    /* 0x69AE70: 1 low, 3 high, 5 G, 6 G apex (XX's numbering) */
#define owner_dtp(o)           proof_port_dtp(o)
#define owner_dtp_count(o, dtp) ((void)(dtp), proof_port_breaks(o))
#define owner_dtp_records(o)   ((const u8 *)proof_port_dtp(o))
#define owner_break_level_at(o) ((void)(o), 1 + (quest_rank_4u(quest_manager_4u) >= BREAK_RANK_G))
void part_reward_4u(void *quest, u32 id, u32 bit, u32 zero, u32 x);   /* 0x6A8920 */
#define owner_part_reward(o, bit) part_reward_4u(quest_manager_4u, EMB(o, EMX_REWARD_ID), bit, 0, 0)
#endif
#define owner_part_broken(o, part) VSLOT(part_fn, o, OWNER_SLOT_PART_BROKEN)(o, part)

#endif
