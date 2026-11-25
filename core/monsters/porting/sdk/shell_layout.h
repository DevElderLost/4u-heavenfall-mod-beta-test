/* The layout of MH Generations' shell bases (uShellEmBase00/01/02/11/41) and MH XX's base 56, as names: each field's offset in the
 * object, the bases' sizes and the few of uShellEnemy's a base's C reads. This is the only place the names are
 * defined: sdk/shell_api.h, sdk/shell_kinds_b.h and effect_player/shell_kinds_a.h include it, and a monster's shell
 * C (em050/shell_methods.c) includes it alone, without the effect player's declarations. MH Generations' values;
 * a TARGET_XX build gets MH XX's (xx_target.py reads the blocks, enemy_xx_layout.h gives the values). */
#ifndef SHELL_LAYOUT_H
#define SHELL_LAYOUT_H

#ifdef TARGET_XX
#include "enemy_xx_layout.h"             /* MH XX's values of the blocks' names */
#endif

#include "types.h"

/* ---- the classes' sizes (their DTIs: MH Generations' static initializers, 0x8509A0's size) ---- */
#ifndef ENEMY_LAYOUT_XX
#define SHELL_BASE00_SIZE  0x11C0                    /* uShellEmBase00 (0xDFC570) */
#define SHELL_BASE01_SIZE  0x11B8                    /* uShellEmBase01 (0xDFC5B0) */
#define SHELL_BASE02_SIZE  0x11F0                    /* uShellEmBase02 (0xDFC628) */
#define SHELL_BASE11_SIZE  0x11C8                    /* uShellEmBase11 (0xDFC768), on base 01 */
#define SHELL_BASE41_SIZE  0x11E0                    /* uShellEmBase41 (0xDFCE08) */
#define SHELL_BASE56_SIZE  0x11A0                    /* uShellEmBase56: MH XX's only (DTI 0xD7A920, 0x12B0 bytes
                                                        there); uShellEnemy's size and XX's 0x68 bytes of its own */
#define SHELL_BASE03_SIZE  0x1258                    /* uShellEmBase03 (0xDFC668; XX 0x1368: its ground record is
                                                        8 bytes shorter there) */
#define SHELL_BASE14_SIZE  0x1220                    /* uShellEmBase14, on base 00: its 0x60 bytes (XX DTI 0xD79F10) */
#define SHELL_BASE15_SIZE  0x12B8                    /* uShellEmBase15, on base 03: its 0x60 bytes (XX DTI 0xD79F30) */
#define SHELL_BASE50_SIZE  0x1210                    /* uShellEmBase50, on base 00: its 0x50 bytes (XX DTI 0xD7A740) */
#define SHELL_BASE25_SIZE  0x1168                    /* uShellEmBase25, on uShellEnemy: XX's 0x30 bytes of its own
                                                        (XX 0x1278, DTI 0xD7A110); MH XX's only */
#define SHELL_BASE26_SIZE  0x11C0                   /* uShellEmBase26, on uShellEnemy: XX's 0x88 bytes of its own
                                                        (XX 0x12D0; MH Generations' class has 0x58, 0x1190) */
#define SHELL_BASE45_SIZE  0x11B8                    /* uShellEmBase45, on uShellEnemy: XX's 0x80 bytes of its own
                                                        (XX 0x12C8, DTI 0xD7A640); MH XX's only */
#define SHELL_BASE46_SIZE  0x11A0                    /* uShellEmBase46, on uShellEnemy: XX's 0x68 bytes of its own
                                                        (XX 0x12B0, DTI 0xD7A680); MH XX's only */
#endif

/* ---- uShell and uShellEnemy: the fields the bases read (shell_enemy.c) ---- */
#ifndef ENEMY_LAYOUT_XX
#define SHELL_FRAME        0x1124                    /* u32: the game's frame count at the setup (sShell ends the
                                                        oldest first) */
#define SHELL_ENDED        0x112D                    /* u8: set when the shell ends */
#endif

#ifndef ENEMY_LAYOUT_XX
#define SHELL_KIND_NO      0x1128                    /* u32: the base's number (00: 0, 01: 1, 11: 0xB, 02: 2, 41:
                                                        0x29; uShellEnemy's constructor -1): the Festa modifier's */
#define SHELL_GROUND_ON    0x112C                    /* u8: uShellEnemy tests the ground (0 off) */
#define SHELL_HIT_GROUND   0x112E                    /* u8: 1 tests the ground even after record 0 hit (base 02's
                                                        setup sets it) */
#define SHELL_RAY_NARROW   0x112F                    /* u8: 1 gives the ray 0x10 for its seventh argument (else 0x30) */
#define SHELL_RAY_80       0x1130                    /* u8: 1 takes the rays of mask 0x80 (0xAFD0B4, 0xAFD124) */
#define SHELL_SLOPE_MAX    0x1134                    /* f32 degrees: ground steeper than this ends the shell as a
                                                        wall (kind 0) */
#endif

/* ---- base 00 (uShellEmBase00, 0x11C0 bytes) ---- */
#ifndef ENEMY_LAYOUT_XX
#define B00_START          0x1138    /* const s32 *: the effect pair played at the start */
#define B00_END_0          0x113C    /* the pairs where it ends, by kind 0, 1, 2 */
#define B00_END_1          0x1140
#define B00_END_2          0x1144
#define B00_ATTACK         0x1148    /* s32: its attack record (-1 none) */
#define B00_JOINT          0x114C    /* s32: the owner's joint it starts at (-1: the owner's matrix) */
#define B00_CAMERA_0       0x1150    /* s32: camera ids where it ends (kinds 0, 1; -1 none) */
#define B00_CAMERA_1       0x1154
#define B00_FLAGS          0x1158    /* u32: the bits below */
#define B00_PITCH          0x115C    /* f32 degrees */
#define B00_YAW            0x1160
#define B00_SPEED_Z        0x1164    /* f32: the velocity's z (s0 of 0x496430) */
#define B00_SPEED_Y        0x1168    /* and its y (s1) */
#define B00_LIFE           0x116C    /* f32: frames it may fly (0: until it hits) */
#define B00_PITCH_RANGE    0x1170    /* f32 x2, degrees */
#define B00_YAW_RANGE      0x1178
#define B00_OFFSET         0x1180    /* const float *: where it starts, from the owner's point */
#define B00_AIM            0x1184    /* const float *: the point it aims at, from the owner */
#define B00_AIM_OFFSET     0x1188    /* const float *: the aim's offset, turned toward it (0x496280) */
#define B00_ACCEL          0x118C    /* const float *: its acceleration (y, z) */
#define B00_LIFE_LEFT      0x1190    /* f32 */
#define B00_TARGET         0x1194    /* s8: the owner's target point (SHP_TARGET) */
#define B00_START_CORE     0x1198    /* its effects' cores (the start's, the end's) */
#define B00_END_CORE       0x119C
#define B00_AIMED          0x11A0    /* vec4: the point it aimed at (0x496280) */
#define B00_11BC           0x11BC    /* f32, cleared by the constructor */
#endif

/* ---- base 03 (uShellEmBase03, on base 00, 0x1258 bytes in MH Generations): its fields start where base 00's end. The
 * ground record's size differs between the games, so from B03_STATE on the distances are MH Generations' (the
 * framework's, which only MH Generations and MH4U build). ---- */
#define B03_END_PAIR       (SHELL_BASE00_SIZE + 0x00)   /* const s32 *: the pair its slot 83 plays */
#define B03_FLAGS          (SHELL_BASE00_SIZE + 0x04)   /* u32: homing, slopes, walls, a life from the distance */
#define B03_TURN           (SHELL_BASE00_SIZE + 0x08)   /* f32 degrees */
#define B03_LIFE_MIN       (SHELL_BASE00_SIZE + 0x0C)
#define B03_LIFE_MAX       (SHELL_BASE00_SIZE + 0x10)
#define B03_START_UP       (SHELL_BASE00_SIZE + 0x14)   /* f32: the setup's ground ray, from this above it */
#define B03_START_DOWN     (SHELL_BASE00_SIZE + 0x18)   /* to this below */
#define B03_FOLLOW_UP      (SHELL_BASE00_SIZE + 0x1C)   /* f32: the flight's ground ray, from this above it */
#define B03_FOLLOW_DOWN    (SHELL_BASE00_SIZE + 0x20)   /* to this below */
#define B03_START_VELOCITY (SHELL_BASE00_SIZE + 0x28)   /* vec4 */
#define B03_INFO           (SHELL_BASE00_SIZE + 0x38)   /* the ground record the flight's rays fill */
#define B03_STATE          (SHELL_BASE00_SIZE + 0x70)   /* u8 */
#define B03_SAVED_VELOCITY (SHELL_BASE00_SIZE + 0x78)   /* vec4 */
#define B03_SAVED_ANGLES   (SHELL_BASE00_SIZE + 0x88)   /* three words */
#define B03_TARGET_HEIGHT  (SHELL_BASE00_SIZE + 0x94)   /* f32 */
#define B03P_POINT         0x30                         /* its setup parameter: vec3, the point */
#define B03P_HAS_POINT     0x40                         /* u8: 1 with a point */

/* ---- base 14 (uShellEmBase14, on base 00; MH XX's vtable 0xCCA070): a line along the ground. Its head starts on the
 * ground under its start and, once B14_DELAY has passed, runs on at its velocity for B14_GROW frames; it holds for
 * B14_HOLD frames, then its tail follows at B14_TAIL_VELOCITY and the shell ends when the tail passes the head. Its
 * fields start where base 00's end, the same distances in MH XX ---- */
#define B14_HEAD_PAIR      (SHELL_BASE00_SIZE + 0x00)   /* const s32 *: the effect pair started with the attack */
#define B14_START_PAIR     (SHELL_BASE00_SIZE + 0x04)   /* const s32 *: the pair played at the setup */
#define B14_LINE_PAIR      (SHELL_BASE00_SIZE + 0x08)   /* const s32 *: the line's pair, started with the attack */
#define B14_RESCALE        (SHELL_BASE00_SIZE + 0x0C)   /* s32: -1 rescales the line only while the head runs */
#define B14_10             (SHELL_BASE00_SIZE + 0x10)   /* s32, -1: no slot of the base reads it */
#define B14_DELAY          (SHELL_BASE00_SIZE + 0x14)   /* f32: frames before the attack starts */
#define B14_GROW           (SHELL_BASE00_SIZE + 0x18)   /* f32: frames the head runs */
#define B14_HOLD           (SHELL_BASE00_SIZE + 0x1C)   /* f32: frames before the tail follows */
#define B14_UNIT           (SHELL_BASE00_SIZE + 0x20)   /* f32: the line's length at scale 1 (100) */
#define B14_SHRINK         (SHELL_BASE00_SIZE + 0x24)   /* f32: frames the tail takes to reach the head's end */
#define B14_RAY_UP         (SHELL_BASE00_SIZE + 0x28)   /* f32: the setup's ground ray, from this added (200) */
#define B14_RAY_DOWN       (SHELL_BASE00_SIZE + 0x2C)   /* to this added (-200) */
#define B14_HEIGHT         (SHELL_BASE00_SIZE + 0x30)   /* f32: its height above the ground, turned with the ground */
#define B14_AGE            (SHELL_BASE00_SIZE + 0x34)   /* f32: frames since the setup */
#define B14_WAIT           (SHELL_BASE00_SIZE + 0x38)   /* f32: B14_DELAY at the setup; 0 once the attack started */
#define B14_HEAD_CORE      (SHELL_BASE00_SIZE + 0x3C)   /* its effects' cores: B14_HEAD_PAIR's, */
#define B14_LINE_CORE      (SHELL_BASE00_SIZE + 0x40)   /* B14_LINE_PAIR's, */
#define B14_START_CORE     (SHELL_BASE00_SIZE + 0x44)   /* B14_START_PAIR's */
#define B14_STOPPED        (SHELL_BASE00_SIZE + 0x48)   /* u8: 1 once the head has run B14_GROW frames */
#define B14_TAIL_VELOCITY  (SHELL_BASE00_SIZE + 0x50)   /* vec4: the tail's velocity */
#define B14F_TURN_BY_OWNER 8                            /* bit of B00_FLAGS: the offset turns by the owner's angles
                                                           (vec_turn_angles); else by B00_PITCH and B00_YAW */

/* ---- base 15 (uShellEmBase15, on base 03; MH XX's vtable 0xCCA1E0): a shell that sways from side to side about
 * the path base 03 gives it, each swing as wide as its random generator says, pausing at each side when B15_PAUSE.
 * Its fields start where base 03's end (MH XX's base 03 is 8 bytes shorter, its size the layout's) ---- */
#define B15_PERIOD         (SHELL_BASE03_SIZE + 0x00)   /* s32: every this many swings is B15_PERIOD_WIDTH wide (-1) */
#define B15_MIRROR         (SHELL_BASE03_SIZE + 0x04)   /* s32: other than -1, it starts the other way, another seed */
#define B15_WIDTH_MAX      (SHELL_BASE03_SIZE + 0x08)   /* f32: a swing's width is random between these two */
#define B15_WIDTH_MIN      (SHELL_BASE03_SIZE + 0x0C)
#define B15_SIDE_SPEED     (SHELL_BASE03_SIZE + 0x10)   /* f32: its speed sideways */
#define B15_STEER          (SHELL_BASE03_SIZE + 0x14)   /* f32: how hard it steers into each swing */
#define B15_PERIOD_WIDTH   (SHELL_BASE03_SIZE + 0x18)   /* f32: the width of every B15_PERIOD-th (0: B15_WIDTH_MAX) */
#define B15_PAUSE          (SHELL_BASE03_SIZE + 0x1C)   /* f32: frames it pauses at each side (0: none) */
#define B15_PATH           (SHELL_BASE03_SIZE + 0x20)   /* vec4: the point it sways about */
#define B15_SIDE           (SHELL_BASE03_SIZE + 0x30)   /* f32: how far to the side it is */
#define B15_SIDE_MAX       (SHELL_BASE03_SIZE + 0x34)   /* f32: this swing's half width */
#define B15_SIDE_RATE      (SHELL_BASE03_SIZE + 0x38)   /* f32: its speed sideways now, signed */
#define B15_RANDOM         (SHELL_BASE03_SIZE + 0x3C)   /* void *: its random generator (0x10 bytes, its own) */
#define B15_SWINGS         (SHELL_BASE03_SIZE + 0x40)   /* u32: swings so far */
#define B15_PAUSE_LEFT     (SHELL_BASE03_SIZE + 0x44)   /* f32 */
#define B15_SIDE_ANGLES    (SHELL_BASE03_SIZE + 0x48)   /* u32[3] (x, y, z): the side, and the course after a pause,
                                                           are turned by these */
#define B15_ANGLES         (SHELL_BASE03_SIZE + 0x54)   /* u32[3]: its pitch and yaw after a pause */
#define B15_SEED_MIRROR    0x12345678                   /* added to the seed when B15_MIRROR */
#define B15_RANDOM_SIZE    0x10

/* ---- base 50 (uShellEmBase50, on base 00; MH XX's vtable 0xCCCE4C): a shell that runs straight out from where it
 * starts, along its angles, for B50_DIST over B50_DURATION frames, its speed and scale eased by two slots of its own;
 * B50_HOLD frames after that it ends. Its fields start where base 00's end, the same distances in MH XX
 * ---- */
#define B50_MODE           (SHELL_BASE00_SIZE + 0x00)   /* s32: -1 one speed from B50_DIST and B50_SPREAD, 0 three given */
#define B50_SCALE_FROM     (SHELL_BASE00_SIZE + 0x04)   /* f32: its scale at the start (0) */
#define B50_SCALE_TO       (SHELL_BASE00_SIZE + 0x08)   /* f32: at the end of its run (1) */
#define B50_DIST           (SHELL_BASE00_SIZE + 0x0C)   /* f32: mode -1's run (20) */
#define B50_DURATION       (SHELL_BASE00_SIZE + 0x10)   /* f32: frames of its run (10) */
#define B50_SPREAD         (SHELL_BASE00_SIZE + 0x14)   /* f32: mode -1: the speeds are the mean's (1 -/+ this) */
#define B50_HOLD           (SHELL_BASE00_SIZE + 0x18)   /* f32: frames it stays after its run */
#define B50_SPEEDS         (SHELL_BASE00_SIZE + 0x1C)   /* f32[3]: mode 0's speeds at the start, the middle, the end */
#define B50_AGE            (SHELL_BASE00_SIZE + 0x28)   /* f32: frames since the setup */
#define B50_SPEED_START    (SHELL_BASE00_SIZE + 0x2C)   /* f32: the setup's speeds: at the start, */
#define B50_SPEED_MID      (SHELL_BASE00_SIZE + 0x30)   /* the middle (mode 0), */
#define B50_SPEED_END      (SHELL_BASE00_SIZE + 0x34)   /* the end */
#define B50_SPEED          (SHELL_BASE00_SIZE + 0x38)   /* f32: its speed now */
#define B50_ORIGIN         (SHELL_BASE00_SIZE + 0x40)   /* vec4: where it started */
#define B50P_30            0x30      /* its setup parameter (0x38 bytes): f32 -1, which base 50 does not read */
#define SETUP50_SIZE       0x38

/* ---- base 56 (uShellEmBase56, on uShellEnemy; MH XX's only: vtable 0xCCD690), base 00 trimmed: its first nine
 * fields are base 00's. MH Generations has no such class, so its fields are placed back from its size, the same
 * distances in MH XX and in MH4U's framework ---- */
#define B56_START          (SHELL_BASE56_SIZE - 0x68)   /* const s32 *: the effect pair played at the start */
#define B56_END_0          (SHELL_BASE56_SIZE - 0x64)   /* the pairs where it ends, by kind 0, 1, 2 */
#define B56_END_1          (SHELL_BASE56_SIZE - 0x60)
#define B56_END_2          (SHELL_BASE56_SIZE - 0x5C)
#define B56_ATTACK         (SHELL_BASE56_SIZE - 0x58)   /* s32: its attack record (-1 none) */
#define B56_JOINT          (SHELL_BASE56_SIZE - 0x54)   /* s32: the owner's joint it starts at (-1: the owner's matrix) */
#define B56_CAMERA_0       (SHELL_BASE56_SIZE - 0x50)   /* s32: camera ids where it ends (kinds 0, 1; -1 none) */
#define B56_CAMERA_1       (SHELL_BASE56_SIZE - 0x4C)
#define B56_FLAGS          (SHELL_BASE56_SIZE - 0x48)   /* u32: the bits B56F_* */
#define B56_SPEED          (SHELL_BASE56_SIZE - 0x44)   /* f32: its velocity's z */
#define B56_LIFE           (SHELL_BASE56_SIZE - 0x40)   /* f32: frames it may fly (0: until it hits) */
#define B56_OFFSET         (SHELL_BASE56_SIZE - 0x3C)   /* const float *: where it starts, from the owner's point */
#define B56_AIM            (SHELL_BASE56_SIZE - 0x38)   /* const float *: the point it aims at, from the owner */
#define B56_HYPER          (SHELL_BASE56_SIZE - 0x34)   /* s8, -1: MH XX's Hyper index, which the setup copies into
                                                           uShellEnemy's (XX +0x123E); MH4U has no such field */
#define B56_START_CORE     (SHELL_BASE56_SIZE - 0x30)   /* its effects' cores (the start's, the end's) */
#define B56_END_CORE       (SHELL_BASE56_SIZE - 0x2C)
#define B56_LIFE_LEFT      (SHELL_BASE56_SIZE - 0x28)   /* f32 */
#define B56_TARGET         (SHELL_BASE56_SIZE - 0x24)   /* u8: its setup parameter's (never read) */
#define B56_POINT          (SHELL_BASE56_SIZE - 0x20)   /* vec4: the point it aims at */
#define B56_VEC            (SHELL_BASE56_SIZE - 0x10)   /* vec4: the constructor clears its w; never read */
#define B56F_HOMING        0         /* the point is from the owner's homing point; else from its position */
#define B56F_TURN_BY_ANGLES 1        /* the offset turns by the angles; else by the start matrix */
#define B56F_NO_FACE       2         /* it does not face its velocity */
#define B56F_SCALED        3         /* the offset scales with the owner */
#define B56F_SIZED         4         /* the shell takes the owner's scale */
#define B56F_NO_GROUND     5         /* uShellEnemy does not test the ground */
#define B56P_TARGET        0x10      /* its setup parameter (0x14 bytes): u8 */
#define B56P_SERIAL        0x12      /* u16: SHELL_110C */
#define SETUP56_SIZE       0x14

/* ---- base 01 (uShellEmBase01, 0x11B8 bytes) and base 11 on it (uShellEmBase11, 0x11C8) ---- */
#ifndef ENEMY_LAYOUT_XX
#define B01_START_0        0x1138    /* const s32 *: the two effect pairs played at the start */
#define B01_START_1        0x113C
#define B01_HIT_END        0x1140    /* the pair played when it ends hitting (0x497D80), once */
#define B01_END            0x1144    /* the pair played at its end (slot 80) */
#define B01_ATTACK_0       0x1148    /* s32: its two attack records (-1 none) */
#define B01_ATTACK_1       0x114C
#define B01_BODY           0x1150    /* s32: its body record (-1 none) */
#define B01_JOINT          0x1154    /* s32: the owner's joint it starts at (-1: the owner's position) */
#define B01_CAMERA         0x1158    /* s32: a camera id (-1 none) */
#define B01_FLAGS          0x115C
#define B01_LIFE_SET       0x1160    /* f32: frames it lives (copied into B01_LIFE) */
#define B01_RAY_UP         0x1164    /* f32: the ground ray from this above (0: 1,000,000) */
#define B01_RAY_DOWN       0x1168    /* to this below */
#define B01_116C           0x116C    /* f32, 1.0 from the constructor */
#define B01_1170           0x1170
#define B01_HEIGHT_MAX     0x1174    /* f32: with flag 7, the owner may stand at most this above its ground */
#define B01_OFFSET         0x1178    /* const float *: where it starts, from its base point */
#define B01_TURN           0x117C    /* const float *: degrees added to the parameter's angles */
#define B01_LIFE           0x1180    /* f32 */
#define B01_AGE            0x1184    /* f32 */
#define B01_1188           0x1188
#define B01_OWNER_24C      0x118C    /* the owner's motion (SHELL_OWNER_MOTION) at the setup */
#define B01_START_CORE     0x1190    /* two cores (B01_START_0/1's) */
#define B01_HIT_CORE       0x1198
#define B01_END_CORE       0x119C
#define B01_POINT          0x11A0    /* vec4 */
#define B01_11AC           0x11AC
#define B01_SCALE          0x11B0    /* f32: its scale (times the owner's size with flag 11) */
#endif

#ifndef ENEMY_LAYOUT_XX
#define B11_TIMES          0x11B4    /* float *: when (frames) it launches each shell (slot 87) */
#define B11_COUNT          0x11B8
#define B11_IN_FRAMES      0x11BC    /* 0: the times are divided by the owner's speed at the setup */
#define B11_NEXT           0x11C0    /* the next time's index */
#endif

/* ---- base 02 (uShellEmBase02, 0x49A2F4) and base 41 (uShellEmBase41, 0x4B2C38) ---- */
#ifndef ENEMY_LAYOUT_XX
#define SHELL02_SOUND_TIME 0x1138                    /* f32: frames to the next sound */
#define SHELL02_LIFE       0x113C                    /* f32: frames left, at the owner's motion speed */
#define SHELL02_FOLLOW     0x1140                    /* f32: frames left of the joint following */
#define SHELL02_MOTION     0x1144                    /* u32: the owner's motion at the setup */
#define SHELL02_ANCHOR     0x1148                    /* vec4: the owner's joint (+ offset) it follows */
#define SHELL02_HIT_POS    0x1158                    /* vec4: where the ground was hit, else the position */
#define SHELL02_CORE_A     0x1168                    /* uMHEffectCore *: its effect on the joint */
#define SHELL02_CORE_B     0x116C                    /* uMHEffectCore *: its effect on the ground */
#define SHELL02_HIT_ANGLES 0x1170                    /* vec4: 0x28CD20's angles at the ground */
#define SHELL02_FROM       0x1180                    /* vec4: the position before this frame's following */
#define SHELL02_LAST_FROM  0x1190                    /* vec4: FCHAR_LAST_POS before it */
#define SHELL02_HIT_KIND   0x11A0                    /* u8: what the ground check found (3: nothing) */
#define SHELL02_PAIR_A     0x11A4                    /* const s32 *: (list, PEL id) of core A */
#define SHELL02_PAIR_B     0x11A8                    /* const s32 *: (list, PEL id) of core B */
#define SHELL02_SOUND      0x11AC                    /* s32: the sound's id, -1 none */
#define SHELL02_SOUND_SPAN 0x11B0                    /* f32: frames between two sounds */
#define SHELL02_ATTACK     0x11B4                    /* s32: the attack record, -1 none */
#define SHELL02_JOINT      0x11B8                    /* s32: the owner's joint, -1 its own matrix */
#define SHELL02_SCALE      0x11BC                    /* f32 */
#define SHELL02_LIFE_SET   0x11C0                    /* f32: SHELL02_LIFE at the setup */
#define SHELL02_FOLLOW_SET 0x11C4                    /* f32: SHELL02_FOLLOW at the setup */
#define SHELL02_TURN_AT    0x11C8                    /* f32: the life left from which the owner's angle turns it */
#define SHELL02_YAW_MIN    0x11CC                    /* f32: degrees */
#define SHELL02_YAW_MAX    0x11D0                    /* f32: degrees */
#define SHELL02_FLAGS      0x11D4                    /* u32: bits 0-3 (bit references, 0xB14824) */
#define SHELL02_OFFSET     0x11D8                    /* const float *: the offset from the joint */
#define SHELL02_DIR        0x11DC                    /* const float *: the direction from the anchor */
#define SHELL02_TURN       0x11E0                    /* const float *: two angles, degrees */
#define SHELL02_YAW_FROM   0x11E4                    /* const float *: added to the em's mPos */
#define SHELL02_YAW_TO     0x11E8                    /* const float *: added to the em's mHomingPos */
#define SHELL02_SIZE       0x11EC
#define SHELL02_SLOT_WAIT      82
#define SHELL02_SLOT_NO_MOTION 83                    /* empty in the base */
#define SHELL02_SLOT_GROUND    84
#define SHELL02_SLOT_MATRIX    85                    /* empty in the base */
#define SHELL02_SLOT_ENDED     86                    /* empty in the base */
#define SHELL02_SLOT_FOLLOW    87
#define SHELL02_SLOT_SOUND     88
#define SHELL02_SLOT_MOTION    89

/* ---- base 41 (uShellEmBase41, 0x4B2C38) ---- */
#define SHELL41_CHARGE0    0x1138                    /* f32: step 0's frames */
#define SHELL41_CHARGE1    0x113C                    /* f32: step 1's frames */
#define SHELL41_BODY_TIME  0x1140                    /* u32: written into the body record's +0x30 */
#define SHELL41_PAIRS      0x1144                    /* 9 const s32 *: the effects' (list, PEL id) pairs */
#define SHELL41_ATTACK     0x1168                    /* s32: the attack record, -1 none */
#define SHELL41_BODY_DATA  0x116C                    /* s32: the body data for the last hit */
#define SHELL41_JOINT      0x1170                    /* s32: the owner's joint, -1 its position */
#define SHELL41_FLAGS      0x1174                    /* u32: bits 0-2 (bit references) */
#define SHELL41_TURN       0x1178                    /* f32[2]: degrees, added to the em's mVec x and y */
#define SHELL41_SPEED      0x1180                    /* f32[2] */
#define SHELL41_FLY_TIME   0x1188                    /* f32: state 2's frames */
#define SHELL41_LAST_TIME  0x118C                    /* f32: state 3's frames */
#define SHELL41_OFFSET     0x1190                    /* const float *: the start's offset */
#define SHELL41_ACCEL      0x1194                    /* const float *: the flight's a */
#define SHELL41_JUMP       0x1198                    /* const float *: added to the position at the last hit */
#define SHELL41_TIMER      0x119C                    /* f32: the state's frames left */
#define SHELL41_CORES      0x11A4                    /* uMHEffectCore **: 9 (an MtArray: count at +0x11A8) */
#define SHELL41_CORE_COUNT 0x11A8
#define SHELL41_START_ANG  0x11B0                    /* vec4: unit_get_angles at the setup */
#define SHELL41_SIZE       0x11E0
#endif

/* ---- base 26 (uShellEmBase26, MH XX's 0x4800F0): a shell that circles a
 * centre (the owner's joint, or its position facing its homing point) on an ellipse that grows, turning faster or
 * slower inside a window of frames and rising inside another; it lives while one of its attack records is on. Its
 * 0x88 bytes after uShellEnemy's, at the same distances in XX and MH4U ---- */
#define B26_OWN            (SHELL_BASE26_SIZE - 0x88)
#define B26_START          (B26_OWN + 0x00)   /* const s32 *: the effect pair played at the setup */
#define B26_PAIR           (B26_OWN + 0x04)   /* const s32 *: the pair its class plays at a point (proof_shell26_effect) */
#define B26_RECORD_0       (B26_OWN + 0x08)   /* s32: attack record 0, -1 none */
#define B26_RECORD_1       (B26_OWN + 0x0C)   /* s32: attack record 1, -1 none */
#define B26_JOINT          (B26_OWN + 0x10)   /* s32: the owner's joint at the centre, -1 its position */
#define B26_ANGLE_0        (B26_OWN + 0x14)   /* f32: the start's angle on the ellipse, degrees */
#define B26_RADIUS_X0      (B26_OWN + 0x18)   /* f32: the ellipse's start radii, x and z */
#define B26_RADIUS_Z0      (B26_OWN + 0x1C)
#define B26_HEIGHT         (B26_OWN + 0x20)   /* f32: the start's height above the centre */
#define B26_GROW           (B26_OWN + 0x24)   /* f32: the x radius's growth a frame (z grows in proportion) */
#define B26_YAW_OFFSET     (B26_OWN + 0x28)   /* f32: degrees, added to the yaw */
#define B26_SPEED_0        (B26_OWN + 0x2C)   /* f32: the turn's start speed, degrees a frame */
#define B26_ACCEL          (B26_OWN + 0x30)   /* f32: its change a frame, degrees, inside the window */
#define B26_ACCEL_FROM     (B26_OWN + 0x34)   /* f32: the window's frames (after, up to and with) */
#define B26_ACCEL_TO       (B26_OWN + 0x38)
#define B26_LIMIT_0        (B26_OWN + 0x3C)   /* f32: degrees, the speed's limit with bit B26F_LIMIT_0 */
#define B26_LIMIT_1        (B26_OWN + 0x40)   /* f32: degrees, the speed's limit with bit B26F_LIMIT_1 */
#define B26_RISE           (B26_OWN + 0x44)   /* f32: height gained a frame inside its window */
#define B26_RISE_FROM      (B26_OWN + 0x48)
#define B26_RISE_TO        (B26_OWN + 0x4C)
#define B26_BITS          (B26_OWN + 0x50)   /* u32: the bits B26F_* */
#define B26_AGE            (B26_OWN + 0x54)   /* f32: frames since the setup; the end's wait from the end */
#define B26_START_CORE     (B26_OWN + 0x58)   /* B26_START's core */
#define B26_PAIR_CORE      (B26_OWN + 0x5C)   /* B26_PAIR's core */
#define B26_RADIUS_X       (B26_OWN + 0x60)   /* f32: the ellipse's radii now */
#define B26_RADIUS_Z       (B26_OWN + 0x64)
#define B26_ANGLE          (B26_OWN + 0x68)   /* f32: radians */
#define B26_SPEED          (B26_OWN + 0x6C)   /* f32: radians a frame */
#define B26_YAW            (B26_OWN + 0x70)   /* u32: the ellipse's yaw, 16-bit angle */
#define B26_CENTRE         (B26_OWN + 0x78)   /* vec4 */
#define B26F_LIMIT_0       0         /* B26_LIMIT_0 bounds the speed */
#define B26F_LIMIT_1       1         /* B26_LIMIT_1 bounds the speed */

/* ---- base 25 (uShellEmBase25, MH XX's 0x47F744): a shell put on the
 * ground before its owner, at its homing point's distance within bounds (the offset turned by the owner's angles toward
 * that point), still; it lives B25_LIFE frames, or while one of its attack records is on when that is 0. Its 0x30 bytes
 * after uShellEnemy's (the last four padding), at the same distances in XX and MH4U ---- */
#define B25_OWN            (SHELL_BASE25_SIZE - 0x30)
#define B25_START          (B25_OWN + 0x00)   /* const s32 *: the effect pair played at the setup */
#define B25_RECORD         (B25_OWN + 0x04)   /* s32: attack record set up at the setup, -1 none */
#define B25_LIFE           (B25_OWN + 0x08)   /* f32: frames it lives; 0: while an attack record is on */
#define B25_NEAR           (B25_OWN + 0x0C)   /* f32: the distance's bounds before its owner (the homing point's) */
#define B25_FAR            (B25_OWN + 0x10)
#define B25_OFFSET         (B25_OWN + 0x14)   /* const float *: added to the point, turned by its angles */
#define B25_18             (B25_OWN + 0x18)   /* const float *: the zero vector; read by nothing */
#define B25_LIFE_LEFT      (B25_OWN + 0x1C)   /* f32: B25_LIFE at the setup */
#define B25_AGE            (B25_OWN + 0x20)   /* f32: frames of its life; the end's wait from the end */
#define B25_MOTION         (B25_OWN + 0x24)   /* u32: the owner's motion (ENEMY_MOTION_NO) at the setup; read by none */
#define B25_CORE           (B25_OWN + 0x28)   /* B25_START's core */
#define B25_KIND_NO        0x19      /* SHELL_KIND_NO */
#define B25_RAY            500.0f    /* the setup's ground ray: from this above the point to this below */

/* ---- base 45 (uShellEmBase45, MH XX's 0x48EC34): a shell that starts
 * at a joint of its owner (or its position, or a given point), aimed within bounds at the owner's homing point, and
 * flies at its speed with an acceleration, turning toward a point of the owner while its life lasts; then it sinks,
 * shrinking, for B45_SINK frames. Its 0x80 bytes after uShellEnemy's, at the same distances in XX and MH4U. The
 * file-entry names of its class (em037/shells.h) are these ---- */
#define B45_OWN            (SHELL_BASE45_SIZE - 0x80)
#define B45_START          (B45_OWN + 0x00)   /* const s32 *: the effect pair played at the setup (core 0) */
#define B45_EFFECT_1       (B45_OWN + 0x04)   /* const s32 *: pairs its class fills; the base plays none of them */
#define B45_EFFECT_2       (B45_OWN + 0x08)
#define B45_EFFECT_4       (B45_OWN + 0x0C)
#define B45_EFFECT_3       (B45_OWN + 0x10)
#define B45_RECORD_0       (B45_OWN + 0x14)   /* s32: attack record set up at the setup, -1 none */
#define B45_RECORD_1       (B45_OWN + 0x18)   /* s32: attack record set up when it starts to sink, -1 none */
#define B45_JOINT          (B45_OWN + 0x1C)   /* s32: the owner's joint it starts at, -1 the owner's position */
#define B45_FLAGS          (B45_OWN + 0x20)   /* u32: the bits B45F_* */
#define B45_PITCH          (B45_OWN + 0x24)   /* f32: degrees added to the start's pitch */
#define B45_YAW            (B45_OWN + 0x28)   /* f32: degrees added to the start's yaw */
#define B45_SPEED_Z        (B45_OWN + 0x2C)   /* f32: the velocity's z and y before the angles turn it */
#define B45_SPEED_Y        (B45_OWN + 0x30)
#define B45_PITCH_HI       (B45_OWN + 0x34)   /* f32: degrees, the aim's bounds around the start's angles */
#define B45_PITCH_LO       (B45_OWN + 0x38)
#define B45_YAW_HI         (B45_OWN + 0x3C)
#define B45_YAW_LO         (B45_OWN + 0x40)
#define B45_LIFE           (B45_OWN + 0x44)   /* f32: frames of flight */
#define B45_SINK           (B45_OWN + 0x48)   /* f32: frames of the sink after it */
#define B45_TURN           (B45_OWN + 0x4C)   /* f32: the turn's rate toward B45_AIM's point */
#define B45_OFFSET         (B45_OWN + 0x50)   /* const float *: the start's offset, turned by the start's angles */
#define B45_ACCEL          (B45_OWN + 0x54)   /* const float *: the acceleration's y and z, turned by the yaw */
#define B45_AIM            (B45_OWN + 0x58)   /* const float *: the owner's point it turns toward (the owner's
                                                 angles turn it); the zero vector: it flies straight */
#define B45_FACE           (B45_OWN + 0x5C)   /* const float *: the angles (degrees, on the em's) it faces after
                                                 the setup unless B45F_KEEP_ANGLES */
#define B45_LIFE_LEFT      (B45_OWN + 0x60)   /* f32: frames left of the flight, the sink or the end's wait */
#define B45_CORES          (B45_OWN + 0x64)   /* uMHEffectCore **: 5 (an MtArray: count at B45_CORE_COUNT) */
#define B45_CORE_COUNT     (B45_OWN + 0x68)
#define B45_VEC            (B45_OWN + 0x70)   /* vec4: zeroed by the constructor, read by nothing */
#define B45F_PARAM_ANGLES  0         /* the start's angles are the setup parameter's, else aimed */
#define B45F_KEEP_ANGLES   1         /* the setup keeps the aimed angles (no B45_FACE) */
#define B45_CORE_SLOTS     5
#define B45_KIND_NO        0x2D      /* SHELL_KIND_NO */

/* ---- base 46 (uShellEmBase46, MH XX's 0x48FEAC): a shell that flies from the setup parameter's point at its angles,
 * aimed within bounds at a point of the parameter's object; it turns toward the ground under that point (or, aimed at
 * a bound, where its line meets the ground), or falls when it found none, while its life lasts. Its 0x68 bytes after
 * uShellEnemy's, at the same distances in XX and MH4U ---- */
#define B46_OWN            (SHELL_BASE46_SIZE - 0x68)
#define B46_START          (B46_OWN + 0x00)   /* const s32 *: the effect pair played at the setup (core 0) */
#define B46_END_0          (B46_OWN + 0x04)   /* const s32 *: the end's pair by kind: 0 (a hunter, core 1), */
#define B46_END_1          (B46_OWN + 0x08)   /*   1 (the ground, core 2) */
#define B46_END_2          (B46_OWN + 0x0C)   /*   and 2 (its life, core 1) */
#define B46_RECORD         (B46_OWN + 0x10)   /* s32: attack record set up at the setup, -1 none */
#define B46_14             (B46_OWN + 0x14)   /* s32, -1; and B46_18, 0: read by nothing */
#define B46_18             (B46_OWN + 0x18)
#define B46_SPEED_Z        (B46_OWN + 0x1C)   /* f32: the velocity's z and y before the angles turn it */
#define B46_SPEED_Y        (B46_OWN + 0x20)
#define B46_PITCH_HI       (B46_OWN + 0x24)   /* f32: degrees, the aim's bounds around the start's angles */
#define B46_PITCH_LO       (B46_OWN + 0x28)
#define B46_YAW_HI         (B46_OWN + 0x2C)
#define B46_YAW_LO         (B46_OWN + 0x30)
#define B46_LIFE           (B46_OWN + 0x34)   /* f32: frames of flight */
#define B46_TURN           (B46_OWN + 0x38)   /* f32: the turn's rate toward B46_TARGET */
#define B46_AIM            (B46_OWN + 0x3C)   /* const float *: added to the object's position for the ground ray */
#define B46_ACCEL          (B46_OWN + 0x40)   /* const float *: the acceleration's y and z, turned by the yaw */
#define B46_AIM_OFFSET     (B46_OWN + 0x44)   /* const float *: the aim's offset, turned by the aim's yaw */
#define B46_LIFE_LEFT      (B46_OWN + 0x48)   /* f32: frames left of the flight or the end's wait */
#define B46_CORES          (B46_OWN + 0x4C)   /* uMHEffectCore **: 4 (an MtArray: count at B46_CORE_COUNT) */
#define B46_CORE_COUNT     (B46_OWN + 0x50)
#define B46_TARGET         (B46_OWN + 0x58)   /* vec4: the point it turns toward; the zero vector: it falls */
#define B46_CORE_SLOTS     4
#define B46_KIND_NO        0x2E      /* SHELL_KIND_NO */
/* bases 45 and 46's setup parameters (0x30 and 0x38 bytes: nShell::cSetupParam's, then these) */
#define B45P_POINT         0x10      /* vec3: the start, unless it is the zero vector */
#define B45P_ANGLES        0x20      /* u32 x3: the start's angles with B45F_PARAM_ANGLES */
#define B45P_HOMING        0x2C      /* u8: the owner's homing point the aim takes */
#define B45P_SERIAL        0x2E      /* u16: SHELL_110C */
#define B46P_OBJECT        0x10      /* u8 *: the object it aims at (its position at +0x40), or 0 */
#define B46P_POS           0x18      /* vec3: the start */
#define B46P_ANGLES        0x28      /* u32 x3: the start's angles */
#define B46P_SERIAL        0x34      /* u16: SHELL_110C */

#endif
