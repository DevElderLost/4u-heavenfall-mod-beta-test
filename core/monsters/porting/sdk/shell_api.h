/* MH Generations' shell framework, ported: the
 * layout of the shell object and of the hit records in it, for both targets (TARGET_GEN: the check against MH
 * Generations' own code; otherwise MH4U).
 *
 * One object per shell keeps MH Generations' layout, so the framework's C keeps MH Generations' offsets:
 *   +0x000-0x0EF  uCoord: MH4U's in MH4U (its constructor 0x6D4EDC). Its cUnit head differs (proof_api.h
 *                 unit_flags, unit_delta; UNIT_PROP_10 below; the bases' state bytes, SHELL_STATE); +0x30 on
 *                 is the same in both games;
 *   +0x0F0-0xC7F  MH Generations' uBaseModel and uModel part. His shells have no model (+0xF0 stays 0 in MH
 *                 Generations: nothing of the framework calls uModel's slot 22), and MH4U's port gives none;
 *   +0xC80-0xEEF  uFestaChar (its constructor 0x1ECCC4);
 *   +0xEF0-       uShell, uShellEnemy and the bases, with MH4U's hit records in MH Generations' places.
 * The fields of the shell object are at the same offsets in both builds but cUnit's head and the state bytes;
 * the records' fields past their header move (HIT_ATK_*, em050/shell_fields.py HIT_ATK_MOVED).
 * tests/monsters/alatreon/test_alatreon_shell_api.py checks the names shell_fields.py also gives. */
#ifndef SHELL_API_H
#define SHELL_API_H

#ifdef TARGET_XX
#include "enemy_xx_layout.h"             /* MH XX's values of the blocks' names */
#endif

#include "proof_api.h"
#include "shell_layout.h"

/* ---- cUnit's word +0x10, which uShell's constructor sets to 1 (a cUnit property: its setter, 0x878A9C, is
 * MH4U's 0x6274D0 on +0x08, in the same place of the two property tables 0xCD55CC / 0xE31368) ---- */
#ifdef TARGET_GEN
#define UNIT_PROP_10       0x10
#else
#define UNIT_PROP_10       0x08
#endif

/* ---- the parts and the classes' sizes (their DTIs: MH Generations' static initializers, 0x8509A0's size) ---- */
#define MODEL_PART         0x0F0                     /* the uBaseModel / uModel part */
#define FCHAR_PART         0xC80                     /* uFestaChar's fields */
#ifndef ENEMY_LAYOUT_XX
#define SHELL_PART         0xEF0                     /* uShell's */
#define FCHAR_SIZE         0xEF0                     /* uFestaChar (DTI 0xE01EF8) */
#define SHELL_SIZE         0x1128                    /* uShell (DTI 0xDFE1FC) */
#define SHELL_ENEMY_SIZE   0x1138                    /* uShellEnemy (0xDFD040) */
#endif
#define SHELL_DTI_HEAP     0x6800000                 /* MH4U's DTI word +0x18: heap 13 ("Unit/Area") << 23 */

/* ---- uCoord (the same offsets in both games; its mPos is proof_api.h's COORD_POS) ---- */
#define COORD_QUAT         0x50                      /* vec4: the rotation */
#define COORD_MATRIX       0xB0                      /* the world matrix, 16 floats (base 00 reads its owner's) */

/* ---- the uModel part, MH Generations' layout (read only by uFestaChar's slots below that nothing calls) ---- */
#define MODEL_LAYERS       0x23C                     /* u32: the motion layers (0x94C594 sets it: 1) */
#define MODEL_MOTION       0x24C                     /* u16: layer 0's motion, list << 8 | number */
#define MODEL_FRAME        0x298                     /* f32: layer 0's frame */
#define SHELL_JOINTS       0x22C                     /* the joint records (MH Generations' uModel, in both builds) */
#define SHELL_JOINT_MAP    0x230                     /* u8 *: a joint number's record, 0xFF none */
#define SHELL_JOINT_SIZE   0xA0
#define SHELL_JOINT_MATRIX 0x10                      /* in a record: its world matrix (16 floats) */
#define SHELL_JOINT_POS    0x40                      /* vec3: the matrix's translation */
#define SHELL_4U_DIR       0x114                     /* MH4U only: the direction MH4U's hit code reads of a shell */
#define SHELL_4U_AREA      0x130                     /*   owner (0xBED798) and its area (u8: 0xB702D0, 0xBDC27C) */
#define SHELL_4U_POS       0x100                     /* MH4U only, MH4U's uShell's places where its sphere placing */
#define SHELL_4U_ANGLES    0x110                     /*   reads a shell owner (0xBEEF28, 0xBF0108): the position */
#define SHELL_4U_LAST_POS  0x120                     /*   (vec4), the angles (3 u32; +0x114 is SHELL_4U_DIR) and
                                                        last frame's position (vec4) */

/* ---- uFestaChar (constructor 0x1ECCC4; MH Generations' offsets in both builds) ---- */
#ifndef ENEMY_LAYOUT_XX
#define FCHAR_PARENT       0xC80                     /* IProofEffectParent<uFestaChar>: vtable, the object (+4) */
#define FCHAR_USER         0xC88                     /* IProofEffectSequenceUser<uFestaChar>: vtable, the object */
#define FCHAR_C90          0xC90                     /* s32, -1 */
#define FCHAR_C94          0xC94                     /* u8 */
#define FCHAR_C95          0xC95                     /* u8 */
#define FCHAR_ANGLES       0xC98                     /* 3 u32: the angles x, y, z, 0x10000 a turn (slot 49) */
#define FCHAR_ANGLE_Y      0xC9C                     /* the direction (MH Generations' hit code 0xA278CC reads it) */
#define FCHAR_LAST_POS     0xCA8                     /* vec4: last frame's position (the ground ray starts there) */
#define FCHAR_VELOCITY     0xCB8                     /* vec4: the flight's velocity (0x1EC140) */
#define FCHAR_ACCEL        0xCC8                     /* vec4: its acceleration */
#define FCHAR_CD8          0xCD8                     /* u32 */
#define FCHAR_CE0          0xCE0                     /* vec4 */
#define FCHAR_CF0          0xCF0                     /* u8 */
#define FCHAR_CF1          0xCF1                     /* u8, 0xFF */
#define FCHAR_KIND         0xCF2                     /* u8: the constructor's argument (uShell's: 8); an owner's
                                                        kind where the framework reads its owner's */
#define FCHAR_CF3          0xCF3                     /* u8, 0xFF: slots 36 (get) and 37 (set) */
#define FCHAR_AREA         0xCF4                     /* u8 mAreaNo, 0xFF: slot 38 sets it */
#define FCHAR_CF8          0xCF8                     /* u32: slot 39 */
#define FCHAR_CFC          0xCFC                     /* u32: slot 40 (zeros from +0xCF8 to +0xD38) */
#define FCHAR_D00          0xD00                     /* two blocks of 0x31 bytes (bytes, words, floats), the */
#define FCHAR_D48          0xD48                     /*   second cleared again with +0xD40-0xD87; in a shell the
                                                        first is the ground uShellEnemy's test (0x28D07C) hit */
#define FCHAR_D40          0xD40                     /* 0x48 bytes, cleared */
#endif
#define FCHAR_D40_SIZE     0x48
#ifndef ENEMY_LAYOUT_XX
#define FCHAR_D88          0xD88                     /* f32 (base 01: the start's height, copied as a word) */
#define FCHAR_D8C          0xD8C                     /* f32: slot 41 */
#define FCHAR_D90          0xD90                     /* f32 */
#define FCHAR_D94          0xD94                     /* u32 */
#define FCHAR_D98          0xD98                     /* vec4 */
#define FCHAR_DA8          0xDA8                     /* f32 */
#define FCHAR_CHILD        0xDAC                     /* an object: slot 48 runs its slots 24 (once) and 9, the kill
                                                        its slots 16 and 1 */
#define FCHAR_CHILD_NEW    0xDB0                     /* u8: 1 until slot 48 ran the child's slot 24 */
#define FCHAR_DB1          0xDB1                     /* u8 */
#define FCHAR_SOUND        0xDB4                     /* cFestaSoundSequence (to +0xEE0): the model's motion sounds */
#define FCHAR_PEL          0xEE0                     /* a PEL handle (released with the object; slot 73 plays it) */
#define FCHAR_SEQ          0xEE4                     /* a sequence's handle: its vtable, index (-1) at +0xEE8 */
#define FCHAR_RESOURCE     0xEEC                     /* a resource released with the object */
#endif
#define FCHAR_KIND_SHELL   8                         /* uShell's constructor's FCHAR_KIND */

/* ---- uShell (constructor 0x991D7C) ---- */
#ifndef ENEMY_LAYOUT_XX
#define SHELL_SETUP        0xEF0                     /* the setup parameter (an object: slot 1 deletes it) */
#define SHELL_EF4          0xEF4                     /* u8, 1 */
#define SHELL_EF8          0xEF8                     /* u32: 1 when the owner is a monster (its kind 1); bit 0
                                                        widens uShellEnemy's ray mask */
#define SHELL_EFC          0xEFC                     /* f32: the time alive (0x991C50 keeps last frame's at +0xF00) */
#define SHELL_F00          0xF00                     /* f32 */
#define SHELL_F04          0xF04                     /* u16 */
#define SHELL_RSHELL       0xF08                     /* the rShell (a reference) */
#define SHELL_EFFECTS      0xF0C                     /* the eight EffectLists' PEL handles */
#endif
#define SHELL_EFFECT_COUNT 8
#ifndef ENEMY_LAYOUT_XX
#define SHELL_F2C          0xF2C                     /* u32 */
#define SHELL_ATTACK0      0xF30                     /* MhHitAtk, MH Generations' places (SHELL_HITS) */
#define SHELL_ATTACK1      0xFE8
#define SHELL_ATTACK_STRIDE 0xB8
#endif
#define SHELL_ATTACKS      2
#define SHELL_ATTACK(i)    (SHELL_ATTACK0 + SHELL_ATTACK_STRIDE * (i))
#ifndef ENEMY_LAYOUT_XX
#define SHELL_BODY         0x10A0                    /* MhHitBody (0x6C bytes in both builds; MH XX's is 0x70) */
#define SHELL_110C         0x110C                    /* s16, -1: the id the bases' setups copy from their setup
                                                        parameter and hand slot 78 (base 00 its +0x2E, 01 +0x3C,
                                                        02 +0x24, 41 +0x2C) */
#define SHELL_110E         0x110E                    /* u8 (base 02: it lays its trail, 0x4990B4) */
#define SHELL_1110         0x1110                    /* u32 (base 02: the trail's points) */
#define SHELL_1114         0x1114                    /* u32 (base 02: frames the trail was asked for) */
#define SHELL_ARRAY        0x1118                    /* an array (operator delete[] with the object; base 02's
                                                        trail: 0x20-byte entries, two vec4 each) */
#define SHELL_111C         0x111C                    /* u8, 0x39 */
#define SHELL_111D         0x111D                    /* u8 */
#define SHELL_111E         0x111E                    /* u16 */
#define SHELL_FRAMES       0x1120                    /* u8: frames counted by slot 10 (+0x1121 cleared by it) */

/* ---- uShell's slots the bases and the manager call (MH Generations' numbering, "The shell port plan"); each
 * base's own slots past 82 are in its kinds header ---- */
#define SHELL_SLOT_KILL    16                        /* (shell): the unit dies */
#define SHELL_SLOT_PARENT  74                        /* (shell): its effect parent (uFestaChar's 0x1EC2F0) */
#define SHELL_SLOT_SETUP   77                        /* a shell's setup (its setup parameter): 0 refuses */
#define SHELL_SLOT_ATTACK  78                        /* (shell, i, n, a, b, c, id, scale): an attack record set up
                                                        (uShellEnemy's 0x28CBBC) */
#define SHELL_SLOT_END_NOW 79                        /* (base 01's 0x497D70) */
#define SHELL_SLOT_END     80                        /* (shell, now) */
#define SHELL_SLOT_PARAMS  81                        /* (shell): its class's parameters (his module's; pure in the
                                                        bases) */
#define SHELL_SLOT_BURST   82                        /* (shell, pos, info, kind): where it ends (base 00), a hit (base
                                                        41); (shell) in base 01; base 02's wait for its effects */
#endif
typedef void (*shell_fn)(u8 *shell);
typedef void (*shell_end_fn)(u8 *shell, u32 now);
typedef void (*shell_burst_fn)(u8 *shell, const float *pos, const void *info, u32 kind);   /* (and base 02's 84) */
typedef void ENGINE_VFP (*shell_attack_fn)(u8 *shell, u32 i, s32 n, s32 a, u32 b, u32 c, u32 id, float scale);

/* ---- the hit records (em050/shell_fields.py) ---- */
/* The header, +0x00-0x3B, is the same in MH4U's records (its base constructor 0xB7040C) */
#define HIT_ON             0x05                      /* u8: the record joins sHitcheck's list */
#define HIT_RESULT         0x06                      /* u8: the hit's result, 0xFF none */
#define HIT_AREA           0x07                      /* u8 */
#define HIT_OWNER          0x0C
#define HIT_OWNER_KIND     0x10
#define HIT_SCALE          0x14                      /* f32 */
#define HIT_POINT          0x20                      /* vec3: where it hit */
#define HIT_LINK           0x2C                      /* the next record in sHitcheck's list */
#define HIT_30             0x30
#define HIT_SERIAL         0x34                      /* u16 */
#define HIT_FLAGS          0x36                      /* u16 */
#define HIT_POWER          0x38                      /* u16 */
#define HIT_3A             0x3A                      /* u8 */
#define HIT_DIR            0x3B                      /* u8: the direction's high byte */
#define HIT_RESULT_NONE    0xFF
/* Past it MhHitAtk's fields move (HIT_ATK_MOVED): HIT_ATK_<MH Generations' offset> is MH4U's place in MH4U */
#ifdef TARGET_GEN
#ifndef ENEMY_LAYOUT_XX
#define HIT_ATK_SIZE       0xB8
#define HIT_ATK_3C         0x3C
#define HIT_ATK_40         0x40
#define HIT_ATK_48         0x48
#define HIT_ATK_4C         0x4C
#define HIT_ATK_50         0x50
#define HIT_ATK_52         0x52
#define HIT_ATK_54         0x54
#define HIT_ATK_55         0x55
#define HIT_ATK_56         0x56
#define HIT_ATK_57         0x57
#define HIT_ATK_58         0x58
#define HIT_ATK_59         0x59
#define HIT_ATK_5A         0x5A
#define HIT_ATK_5C         0x5C
#define HIT_ATK_60         0x60
#define HIT_ATK_64         0x64
#define HIT_ATK_68         0x68
#define HIT_ATK_6C         0x6C
#define HIT_ATK_6D         0x6D
#define HIT_ATK_6E         0x6E
#define HIT_ATK_70         0x70
#define HIT_ATK_74         0x74
#define HIT_ATK_78         0x78
#define HIT_ATK_7C         0x7C
#define HIT_ATK_80         0x80
#define HIT_ATK_84         0x84
#define HIT_ATK_8C         0x8C
#define HIT_ATK_90         0x90
#define HIT_ATK_92         0x92
#define HIT_ATK_A8         0xA8
#define HIT_ATK_AC         0xAC
#define HIT_ATK_B0         0xB0
#define HIT_ATK_B1         0xB1
#endif
#else
#define HIT_ATK_SIZE       0x98
#define HIT_ATK_3C         0x64
#define HIT_ATK_40         0x3C
#define HIT_ATK_48         0x40
#define HIT_ATK_4C         0x44
#define HIT_ATK_50         0x48
#define HIT_ATK_52         0x4A
#define HIT_ATK_54         0x4C
#define HIT_ATK_55         0x4D
#define HIT_ATK_56         0x4E
#define HIT_ATK_57         0x4F
#define HIT_ATK_58         0x50
#define HIT_ATK_59         0x51
#define HIT_ATK_5A         0x52
#define HIT_ATK_5C         0x54
#define HIT_ATK_60         0x58
#define HIT_ATK_64         0x5C
#define HIT_ATK_68         0x60
#define HIT_ATK_6C         0x65
#define HIT_ATK_6D         0x66
#define HIT_ATK_6E         0x67
#define HIT_ATK_70         0x68
#define HIT_ATK_74         0x6C
#define HIT_ATK_78         0x70
#define HIT_ATK_7C         0x74
#define HIT_ATK_80         0x78
#define HIT_ATK_84         0x80
#define HIT_ATK_8C         0x84
#define HIT_ATK_90         0x88
#define HIT_ATK_92         0x8A
#define HIT_ATK_A8         0x8C
#define HIT_ATK_AC         0x90
#define HIT_ATK_B0         0x94
#define HIT_ATK_B1         0x95
#endif
#define HIT_ATK_KIND2      HIT_ATK_6E                /* the owner's kind, again */
#define HIT_ATK_OWNER2     HIT_ATK_70                /* the owner, again */
#define HIT_ATK_SPHERES    HIT_ATK_84                /* its spheres (an rHitSize; MH4U's sphere list) */
#ifndef ENEMY_LAYOUT_XX
#define HIT_ATK_GEN_A0     0xA0                      /* s32 of MH Generations' MhHitAtk only (HIT_ATK_GEN_ONLY):
                                                        uShellEnemy's Festa branch, which MH4U's build leaves out */
#endif

/* ---- MH4U only: the owner fields MH4U's hit code reads of a shell (docs "What MH4U reads of a shell"),
 * written where MH Generations writes their places (slots 38 and 49 of uFestaChar) ---- */
#ifdef TARGET_GEN
#define shell_4u_area(s, area)  ((void)(s), (void)(area))
#define shell_4u_hit_frame(s)   ((void)(s))
#else
#define shell_4u_area(s, area)  (FIELD(u8, s, SHELL_4U_AREA) = (area))
/* slot 49: the position, the angles (the direction with them) and the last position where MH4U reads them
 * (shell_4u.c) */
#define shell_4u_hit_frame(s)   proof_4u_shell_hit_frame(s)
void proof_4u_shell_hit_frame(u8 *shell);
#endif

/* ---- uFestaChar's two interfaces (+0xC80, +0xC88): MH Generations' 0xD6C2C0 and 0xD6D0F0; in MH4U the
 * monster side's (monster_4u.c), whose slots read only the object at +4 through MH4U's unit state: the
 * parent's "alive" and "owner" serve a shell as a monster. A shell has no sequence (FCHAR_SEQ stays free), so
 * nothing asks its user interface. ---- */
#ifndef TARGET_GEN
#define proof_fchar_parent_vtable proof_4u_parent_vtable
#define proof_fchar_user_vtable   proof_4u_user_vtable
#endif

/* shells: the core (shell_core.c, shell_getters.c, shell_4u.c's fill and EffectLists[0]) */
#ifndef ENEMY_LAYOUT_XX
#define SHELL_ATTACK_SET   0x1121                    /* u8: 1 when an attack was set up this frame (slot 10) */
#endif
/* the setup parameter (SHELL_SETUP): MH Generations' cSetupParam of the shell's kind */
#define SHELL_PARAM_VARIANT 0x08                     /* u8: the variant (ShellInfoList's entry) */
#define SHELL_PARAM_OWNER  0x0C                      /* the unit that launched it */
#define SHELL_VARIANT_NONE 0xFF
#define SHELL_EFFECT_LIST  2                         /* the PEL's list a shell's effect request plays */
#define SHELL_REQUEST_PRIORITY 3                     /* the request's priority (the budget's group) */
#define SHELL_KIND         2                         /* a hit record's owner kind for a shell */
#define SHELL_LISTS        8                         /* EffectLists', PelTiedSeList's and BodyDataList's entries */
/* His shell files as their images keep them (monsters/porting/shell_data.py):
 * the fields the resources' getters read (em050/shell_fields.py RES_GETTERS) */
#define RSHELL_INFOS       0x60                      /* ShellInfoList, an MtTypedArray */
#define ARRAY_COUNT        0x04                      /* an MtTypedArray's count */
#define ARRAY_DATA         0x10                      /*   and its array of objects */
#define RSHELL_EFFECTS     0x74                      /* EffectLists (8) */
#define RSHELL_TIED        0x94                      /* PelTiedSeList (8) */
#define RSHELL_HIT_DATA    0xB8                      /* HitDataList: an rHitDataShell */
#define RSHELL_HIT_SIZE    0xBC                      /* HitSizeList: an rHitSize */
#define RSHELL_BODY_DATA   0xC0                      /* BodyDataList (8 rBodyData) */
#define RSHELL_COMMON      0xE0                      /* ShellCmnParam: an rFreeUseParam */
#define INFO_SCALE         0x04                      /* cShellInfo: ShellScale (f32) */
#define INFO_EFFECT        0x08                      /*   EffectParam (rShellEffectParam) */
#define INFO_SOUND         0x0C                      /*   SoundParam (rFreeUseParam) */
#define INFO_HIT           0x10                      /*   HitParam (rFreeUseParam) */
#define INFO_SHELL         0x14                      /*   ShellParam (rFreeUseParam) */
#define ESP_COUNT          0x64                      /* rShellEffectParam: mParamList's count */
#define ESP_ENTRIES        0x70                      /*   its entries (cShellEffectParam, the pair at +4) */
#define ESP_PAIR           0x04
#define FUP_S32_COUNT      0x60                      /* rFreeUseParam: the s32, f32 and vec3 counts */
#define FUP_F32_COUNT      0x64
#define FUP_VEC3_COUNT     0x68
#define FUP_S32            0x6C                      /*   and their arrays (a vec3 is 16 bytes) */
#define FUP_F32            0x70
#define FUP_VEC3           0x74
#define FUP_VEC3_SIZE      0x10
#define FILE_COPY          0x60                      /* rHitDataShell, rHitSize, rBodyData: the file's copy */
#define FILE_COUNT         0x08                      /*   whose +8 is the count */
#define FILE_DATA          0x64                      /* HDS: its records; BDD: its data; HTS: its lists */
#define HDS_RECORD         0x30
#define HDS_SPHERE_LIST    0x19                      /* u8 in an HDS record: its rHitSize list */
#define HDS_FLAGS          0x0C                      /* u32 in an HDS record (the attack's element and flags) */
#define HDS_LEVEL          0x2C                      /* u8 in an HDS record: the body damage level (MhHitAtk +0x9E) */
#define HDS_SOURCE_3A      0x06                      /* u8 in an HDS record: MhHitAtk +0x3A (MH Generations: 0 -> 1) */
#define HDS_NO_POWER_SCALE 0x10000000                /* in HDS_FLAGS: the owner's rate leaves the power alone */
#define HDS_CLEAR_FLAG_8   0x40000                   /* in HDS_FLAGS: the record's +8 loses bit 3 */
#define HDS_SET_FLAG_20    0x100000                  /* in HDS_FLAGS: the record's +8 gains bit 5 */
/* The attack setup clears bit 3 of the record's +8 when the record's flags say so (HDS_CLEAR_FLAG_8); MH XX's setup
 * (0x9582AC) also does when the record's +6 byte (HDS_SOURCE_3A) is 4 to 7, 0x12 or 0x13, which the converted file
 * (xx_data.hds_to_gen) cannot say: MH4U's and MH XX's builds apply it, MH Generations' check does not */
#ifdef TARGET_GEN
#ifdef TARGET_XX
#define HDS_CLEAR_8_BY_KIND 1
#else
#define HDS_CLEAR_8_BY_KIND 0
#endif
#else
#define HDS_CLEAR_8_BY_KIND 1
#endif
static inline u32 hds_clears_flag_8(const u8 *source)
{
    u32 kind = FIELD(u8, source, HDS_SOURCE_3A);
    u32 by_kind = HDS_CLEAR_8_BY_KIND && ((kind >= 4 && kind <= 7) || kind == 0x12 || kind == 0x13);

    return (FIELD(u32, source, HDS_FLAGS) & HDS_CLEAR_FLAG_8) || by_kind;
}
#define HTS_LIST_4U        0x0C                      /* the port's (shell_data.py): an HTS list's spheres in MH4U's
                                                        form (40 bytes each, ended by bone 0xFFFF) */
#define HIT_ATK_LEVEL_SHIFT 18                       /* MH4U: the level in bits 18-20 of HIT_ATK_48 */
#define HIT_ATK_LEVEL_MASK 0x7
#define HIT_OWNER_SHELL_ON 0x2000000                 /* in HIT_30: an owner of kind 0 or 2 */
/* The owner, a monster: its attack rate (the shell's power is scaled by it) and its slot 31 (MH Generations'
 * uFestaChar's 0xA7AA08, `return 1`, in the four monster classes; MH4U's monsters have no slot 31). MH4U's own
 * uShell scales the power the same way (0x9A96DC-0x9A9718) with the owner's em +0x3FC */
#ifdef TARGET_GEN
#define owner_attack_rate(o)   FIELD(float, FIELD(u8 *, o, 0xFAC), 0x374)
#define owner_slot31(o)        VSLOT(owner_alive_fn, o, 31)(o)
#else
#define owner_attack_rate(o)   FIELD(float, FIELD(u8 *, o, 0xE28), 0x3FC)
#define owner_slot31(o)        ((void)(o), 1)
#endif
typedef u32 (*owner_alive_fn)(void *owner);

/* shells: the manager (sShell, shell_mgr.c; its DTI 0xDFE03C: 0x5658 bytes on cSystem) */
#define SMGR_SIZE          0x5658
#define SMGR_ON            0x10                      /* u8, 1 (the constructor) */
#define SMGR_FILES         0x14                      /* each kind's rShell (a reference), SHELL_KINDS of them */
#define SMGR_FILE(kind)    (SMGR_FILES + 4 * (kind))
#define SHELL_KINDS        0x128                     /* the kind table's rows */
#define SMGR_OWNERS        0x4B4                     /* each kind's registered owners: 16, 0x40 bytes a kind */
#define SMGR_OWNERS_PER_KIND 16
#define SMGR_OWNER(kind, j) (SMGR_OWNERS + 0x40 * (kind) + 4 * (j))
#define SMGR_LIVE0         0x4EB4                    /* the live shells (0 a free place) */
#define SMGR_LIVE(i)       (SMGR_LIVE0 + 4 * (i))
#define SMGR_LIVE_MAX      0x90
#define SMGR_LIMIT(k)      (0x50F4 + 4 * (k))        /* two owners with a limit on their shells (0x92410C, which */
#define SMGR_LIMITS        2                         /*   his module never calls) */
#define SMGR_LISTS         0x50FC                    /* and their lists of live places (std::vector<u8>, 0xFF free) */
#define SMGR_LIST(k)       (SMGR_LISTS + LIST_SIZE * (k))
#define LIST_DATA          0x00                      /* u8 *: the entries */
#define LIST_COUNT         0x04                      /* u32 */
#define LIST_SIZE          0x08
#define SMGR_OTHER         0x510C                    /* two u8: live places of another monster's shells */
#define SMGR_NONE          0xFF                      /*   (uShellEm001_sp_01's, 0x923E60), 0xFF none */
#define SMGR_WORK          0x5110                    /* nShell::cSerialWork, the network sync's records */
#define SMGR_WORKS         0x38
#define WORK_SIZE          0x18
#define WORK_04            0x04                      /* (a work's fields, as its constructor 0x8FA688 sets them) */
#define WORK_08            0x08
#define WORK_STATE         0x09
#define WORK_0C            0x0C
#define WORK_10            0x10
#define WORK_FLAGS         0x14
#define SMGR_TASK          0x5650                    /* an object (the destructors kill it: its slot 16) */
#define SMGR_GROUND_100    0x5654                    /* u8: shells on ground of kind 100 end (cleared each frame) */
#define SHELL_LINE         0x12                      /* sUnit's line for a shell (0x13 with the create's flag bit 0) */
#define SHELL_LINE_SECOND  0x13
#define SHELL_PARAM_KIND   0x04                      /* u16 in the setup parameter: the kind (the table's row) */
#define KIND_CLASS_DTI     0x00                      /* a row of the kind table (0xCA2B2C): the class's DTI, */
#define KIND_SETUP_DTI     0x04                      /*   its setup parameter's, */
#define KIND_FILE          0x08                      /*   the rShell's file id */
#define KIND_ROW_SIZE      0x0C
#define SHELL_KIND_HIS     0xB4                      /* his five kinds, 0xB4-0xB8 (files 0x7AF0-0x7AF4) */
#define SHELL_HIS_KINDS    5
#define SHELL_FILE_HIS     0x7AF0
/* the shell's fields the manager reads (base 01's setup and the bases' ends write them; S3-A's names) and the
 * state bytes every base keeps. MH Generations keeps them in cUnit's word +4, which its sUnit never reads
 * (0x893FC4, 0x893E9C: the unit state is in the flags, +0xC) and only the unit's own class uses. MH4U's cUnit has
 * no such word: its +4 is the flags (UNIT_FLAGS), so MH4U's build keeps the bytes in the last word of the model
 * part, which nothing else reads. A shell ends for
 * sUnit through the kill (slot 16: unit state 3), which every store of 0xFF goes with. */
#ifdef TARGET_GEN
#define SHELL_STATE        0x04                      /* u8: 0 waits, 1 and 2 fly (base 41: 1 charges), 3 base 41's
                                                        last hit, 0xFE ending (waits for its effects), 0xFF gone */
#else
#define SHELL_STATE        0xC7C                     /* past MH4U's own shell classes (0x278-0x378 bytes) */
#endif
#define SHELL_STATE_WORD   SHELL_STATE               /* the same, read as a word (base 00's move stores 0xFF so) */
#define SHELL_STATE_ENDING 0xFE
#define SHELL_STEP         (SHELL_STATE + 1)     /* u8: base 41's step within state 1 */
#ifndef ENEMY_LAYOUT_XX
#define SHELL_GROUND_KIND  0x111D                    /* u8: the ground's attribute byte (FCHAR_D00 +3) */
#endif
#define SHELL_GROUND_100   100                       /* a ground kind the manager ends shells on (SMGR_GROUND_100) */
/* What MH4U lacks: MH Generations' kind table, file loader, the test of another
 * monster's shells (its module's two imports, 0x124BB8 and 0x124BC0) and its stage gimmicks (0x93C970 on
 * *0xDA9FB8); the port's build takes his five kinds' rows (shell_4u.c), his images (proof_shell_roots), and
 * neither of the other two */
#ifdef TARGET_GEN
#define shell_kind_row(kind)   ((const u8 *)proof_shell_kinds + KIND_ROW_SIZE * (kind))
#define shell_file_load(row)   proof_file_load(proof_file_loader, FIELD(u32, row, KIND_FILE), proof_rshell_dti)
#define shell_other_class(s)   (FIELD(u32, VSLOT(get_dti_fn, s, UNIT_SLOT_DTI)(s), DTI_KIND) \
    == FIELD(u32, proof_em001_shell_dti, DTI_KIND) && (proof_em001_shell_a(s) || proof_em001_shell_b(s)))
#define shell_gimmick_at(area, ground) proof_stage_gimmick_at(proof_stage_gimmicks, area, ground)
#define shell_file_let_go(file) ((void)(file))     /* MH Generations keeps it (0x923400) */
#else
#define shell_kind_row(kind)   proof_4u_shell_kind(kind)
#define shell_file_load(row)   proof_4u_shell_file(FIELD(u32, row, KIND_FILE))
#define shell_file_let_go(file) resource_release(file)   /* the reference a shell not made took (shell_mgr.c) */
#define shell_other_class(s)   ((void)(s), 0)
#define shell_gimmick_at(area, ground) ((void)(area), (void)(ground), 0)
#endif

/* ---- S3 2B: uShellEnemy (vtable 0xD3D608, 0x1138 bytes; shell_enemy.c) and the helpers every base shares ---- */
#define SHELL_SLOPE_DEFAULT 90.0f
#define RAY_MASK           0x40                      /* the ground's mask; | 0x40 << 18 for a monster's shell */
#define RAY_MASK_80        0x80
/* The ground check's block (0x28C924 clears it; 0x28D07C fills it), built on the stack as the bases do */
#define GROUND_INFO_SIZE   0x38
#define GROUND_NOTHING     3                         /* the kind before the check: nothing hit */
/* the ray functions' type (0xAFCB94 and its variants; the shifted ones take an offset) */
typedef int (*shell_ray_fn)(u8 *shell, float hit[4], u8 info[56], u32 c);

/* ---- the owner (a monster): MH Generations' uFestaEnemy, MH4U's uEnemy (sdk/enemy_gen.h, enemy_4u.h; docs
 * "The owner in MH4U"). Its kind (+0xCF2) is proof_api.h's owner_kind; its uCoord fields (COORD_POS, COORD_MATRIX)
 * and slot 21 are the same in both games ---- */
#ifdef TARGET_GEN
#ifndef ENEMY_LAYOUT_XX
#define SHELL_OWNER_EM     0xFAC                     /* u8 *: the enemy work em (ENEMY_EM) */
#define SHELL_OWNER_MOTION 0x24C                     /* u16: the motion playing */
#define SHELL_OWNER_SPEED  0x2A4                     /* f32: the motion's play speed */
#define SHELL_EM_POS       0x040                     /* vec3 mPos */
#define SHELL_EM_VEC       0x050                   /* u32[3] mVec: 16-bit angles x, y, z */
#define SHELL_EM_HOMING    0x1D0                     /* vec3 mHomingPos[0] */
#define SHELL_EM_HEIGHT    0x5C                      /* f32 added to base 00's aim's height */
#define SHELL_EM_GROUND    0x554                     /* f32: the em's ground height (base 01) */
#define SHELL_OWNER_ACT_RAND 0x6AD0                  /* u16: a random value per action (enemy_gen.h ENEMY_ACT_RAND) */
#endif
#define shell_owner_act_rand(owner) FIELD(u16, owner, SHELL_OWNER_ACT_RAND)
#else
#define SHELL_OWNER_EM     0xE28
#define SHELL_OWNER_MOTION 0x244
#define SHELL_OWNER_SPEED  0x29C
#define SHELL_EM_POS       0x198
#define SHELL_EM_VEC       0x1A8
#define SHELL_EM_HOMING    0x218
#define SHELL_EM_HEIGHT    0x180                   /* the sync's (0x8BE8E4 = 0x9252C0) next load after mPos */
#define SHELL_EM_GROUND    0x624                     /* and the one after it (owner_ground_y's) */
#define SHELL_EM_ACT_RAND  0x1D2                     /* u16: MH4U keeps the action's random value in em (EM_ACT_RAND) */
#define shell_owner_act_rand(owner) FIELD(u16, FIELD(u8 *, owner, SHELL_OWNER_EM), SHELL_EM_ACT_RAND)
#endif
#ifndef ENEMY_LAYOUT_XX
#define SHELL_OWNER_FESTA_EVENT 0x9FB0               /* u8: a monster's Festa event is on (uFestaEnemy) */
#endif
#define SHELL_OWNER_SLOT_JOINT 21                    /* joint n's world matrix (-1: the unit's own; MH4U's uModel
                                                        0xD028F0, its +0xB0) */
typedef float *(*shell_joint_matrix_fn)(void *unit, s32 joint);
/* What MH4U has no counterpart for ("His shells' own code", uShellEnemy): MH Generations reads these, MH4U never
 * asks. The Festa event (pairs.py festa_attack_modifier, absent); the hunter's actions a shell flies through
 * (hunter_state_test: MH4U's own shells end on any hit of their first record); the game's frame count, which
 * MH4U's sGameControl does not keep (MH Generations' 0x2ECEE8 adds 1 to its +0x34 each frame): MH4U's build counts
 * the shell manager's frames instead (proof_shell_frames, game/executable/blocks.py; shell_frame_tick in its slot 7), which
 * keeps sShell's oldest-first choice (SHELL_FRAME). */
#ifdef TARGET_GEN
#define SHELL_OWNER_FESTA(owner)   FIELD(u8, owner, SHELL_OWNER_FESTA_EVENT)
#define SHELL_HIT_PASSES(target)   (!FIELD(u8, target, FCHAR_KIND) && hunter_shell_passes(target))
#define game_frames(control)       FIELD(u32, control, 0x34)
#define shell_frame_tick()         ((void)0)
#else
extern u32 proof_shell_frames;
#define SHELL_OWNER_FESTA(owner)   ((void)(owner), 0)
#define SHELL_HIT_PASSES(target)   ((void)(target), 0)
#define game_frames(control)       ((void)(control), proof_shell_frames)
#define shell_frame_tick()         ((void)proof_shell_frames++)
#endif

/* ---- One VFP operation, its operands in the original's order (as place.c's): GCC swaps an add's or a
 * multiply's operands and joins a multiply and an add, and with NaNs the result keeps the first operand's
 * payload ---- */
#define SB_OP2(op, a, b) ({ float r_; __asm__(op " %0, %1, %2" : "=t"(r_) : "t"(a), "t"(b)); r_; })
#define SB_OP3(op, d, a, b) ({ float r_ = (d); __asm__(op " %0, %1, %2" : "+t"(r_) : "t"(a), "t"(b)); r_; })
#define SB_ADD(a, b) SB_OP2("vadd.f32", a, b)
#define SB_SUB(a, b) SB_OP2("vsub.f32", a, b)
#define SB_MUL(a, b) SB_OP2("vmul.f32", a, b)
#define SB_DIV(a, b) SB_OP2("vdiv.f32", a, b)
#define SB_MLA(d, a, b) SB_OP3("vmla.f32", d, a, b)          /* d + a * b */
#define SB_MLS(d, a, b) SB_OP3("vmls.f32", d, a, b)          /* d - a * b */
#define SB_SQRT(x) ({ float r_; __asm__("vsqrt.f32 %0, %1" : "=t"(r_) : "t"(x)); r_; })
/* A float from its bits (the originals' literals) */
#define F32(bits) (((union { u32 u; float f; }){ (bits) }).f)
#define DEG_TO_ANGLE       F32(0x43360B61)          /* 182.04445: 65536 / 360 */
#define ANGLE_TO_DEG       F32(0x3BB40000)          /* 0.0054931640625: 360 / 65536 */
#define ANGLE16_TO_RAD     F32(0x38C90FDB)          /* 9.58738e-05: 2 pi / 65536 */
#define RAD_TO_DEG         F32(0x42652EE0)          /* 57.29578 */
#define RAD_TO_ANGLE       F32(0x4622F983)          /* 10430.378: 65536 / (2 pi) */

#endif
