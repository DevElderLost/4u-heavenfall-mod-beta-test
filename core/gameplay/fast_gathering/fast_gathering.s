@ Fast gathering (option fast_gathering): the local hunter gathers,
@ mines, catches bugs, carves and fishes `speed` times faster, on top of the Speed Gatherer skill.
@
@ The skill does two things in the gathering action (FUN_00b56708, act_no 77-84 and 148-150): it raises
@ pbw->mPlayerSpeed (1.1 -> 1.3 / 1.4), which drives the motion, and it shortens pw->mTimer (120 -> 90),
@ a real-time timer the action waits for. This block does both, by `speed`:
@
@ _start: the hunter's frame update sets the model's motion speed with `bl motion_speed` (0xB14B1C:
@ FUN_00b06624(hunter, s0), s0 = mPlayerSpeed (pbw + 0x39C) times a factor; pbw = *(hunter + 0xE30)).
@ That call comes here. While the local hunter's action (pl_st +0x370 = act_st +0x371 = 0, act_no
@ +0x372) is one of `actions`, a mPlayerSpeed that differs from the value this routine last wrote
@ (fast_gathering_state) is the game's own: it is multiplied by `speed` and kept, and so is this frame's
@ s0 (later frames the game computes it from mPlayerSpeed). Out of those actions, a mPlayerSpeed still
@ equal to that value is put back (times `inverse`). Then it goes on to motion_speed.
@
@ timer: the gathering action, right after setting pw->mTimer (pw = *(hunter + 0xA29C), +0x38), asks
@ `bl has_skill` (0xB56A3C: FUN_00d04f5c(hunter, 188 Speed Gatherer)) and takes a quarter off the
@ timer with the skill. That call comes here: for the local hunter the timer is multiplied by `inverse`
@ first, then has_skill runs with r0 / r1 untouched.
@
@ The local hunter: pbw + 0x33 == *(settings) + 0x2F (as in interface/hud/dpad_filter.s).
@ speed, inverse and actions (act_no, 0-terminated) are written by gameplay/fast_gathering/fast_gathering.py.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfpv2
    .arm
    .global _start, fast_gathering_motion, fast_gathering_timer

    .equ SETTINGS_POINTER, game_control
    .equ PLAYER, 0xE30                @ pbw = *(hunter + 0xE30)
    .equ HUNTER_INDEX, 0x33
    .equ PLAYER_SPEED, 0x39C          @ pbw->mPlayerSpeed
    .equ WORK, 0x29C                  @ pw = *(hunter + 0xA000 + 0x29C)
    .equ TIMER, 0x38                  @ pw->mTimer

_start:
fast_gathering_motion:
    push    {r4-r7, lr}
    mov     r4, r0
    ldr     r5, [r4, #PLAYER]
    cmp     r5, #0
    beq     out
    ldr     r1, =SETTINGS_POINTER
    ldr     r1, [r1]
    cmp     r1, #0
    beq     out
    ldrsb   r1, [r1, #0x2F]
    ldrb    r2, [r5, #HUNTER_INDEX]
    cmp     r1, r2
    bne     out                       @ another hunter
    ldr     r6, =fast_gathering_state
    ldr     r7, [r6]                  @ the value last written (0: none)
    ldr     r3, [r5, #PLAYER_SPEED]
    add     r2, r5, #0x300
    ldrh    r1, [r2, #0x70]           @ pl_st | act_st << 8
    cmp     r1, #0
    bne     leave
    ldrh    r1, [r2, #0x72]           @ act_no
    adr     r2, actions
find:
    ldrh    r12, [r2], #2
    cmp     r12, #0
    beq     leave
    cmp     r12, r1
    bne     find
    cmp     r3, r7
    beq     out                       @ already scaled
    vldr    s2, speed
    vmov    s1, r3
    vmul.f32 s1, s1, s2
    vstr    s1, [r5, #PLAYER_SPEED]
    vstr    s1, [r6]
    vmul.f32 s0, s0, s2
    b       out
leave:
    cmp     r7, #0
    beq     out
    cmp     r3, r7
    vmoveq  s1, r3
    vldreq  s2, inverse
    vmuleq.f32 s1, s1, s2
    vstreq  s1, [r5, #PLAYER_SPEED]
    mov     r7, #0
    str     r7, [r6]
out:
    mov     r0, r4
    pop     {r4-r7, lr}
    b       motion_speed

timer:
fast_gathering_timer:
    push    {r0-r3, lr}
    ldr     r2, [r0, #PLAYER]
    cmp     r2, #0
    beq     timer_out
    ldr     r3, =SETTINGS_POINTER
    ldr     r3, [r3]
    cmp     r3, #0
    beq     timer_out
    ldrsb   r3, [r3, #0x2F]
    ldrb    r12, [r2, #HUNTER_INDEX]
    cmp     r3, r12
    bne     timer_out                 @ another hunter
    add     r2, r0, #0xA000
    ldr     r2, [r2, #WORK]
    cmp     r2, #0
    beq     timer_out
    vldr    s0, [r2, #TIMER]
    vldr    s1, inverse
    vmul.f32 s0, s0, s1
    vstr    s0, [r2, #TIMER]
timer_out:
    pop     {r0-r3, lr}
    b       has_skill

speed:
    .float  2.0
inverse:
    .float  0.5
actions:
    .space  32                        @ up to 15 act_no (halfwords), then 0
    .ltorg
