@ The hooks of the quest's timers' cheats (cheats/quest_timers/quest_timers.py). Each stands in for one instruction or
@ call of the game and hands over
@ to quest_timers.c:
@
@ quest_end_hook      FUN_0065c1b4 (the quest's end, its countdown before the hunters leave): `vldr s1, [r0, #0x5c]`,
@                     the main object's frame time, which the next instruction adds to the countdown's fraction in s0.
@                     s1 becomes quest_end_delta(main).
@ rewards_tick_hook   FUN_00accd24 (the quest result scene, r4): `vadd.f32 s0, s0, s1`, its timer's fraction plus the
@                     frame time. s0 becomes rewards_timer_add(scene, s0, s1).
@ rewards_number_hook FUN_00ab88f4 (the result scene's countdown, r0 the scene), its first instruction `push {r4, lr}`,
@                     reached by a `b`: lr is still its caller's. When rewards_number_hidden(scene) (No Time Limit on,
@                     a step whose timer it stops) it returns to that caller at once, showing nothing; else it runs
@                     that instruction and goes on to the rest of FUN_00ab88f4 with every register as it came.
@
@ The first two keep r0-r3, r12, lr and the VFP's s0-s15 but the one they set (the functions keep values in r1-r3
@ across the hook: FUN_00accd24 its step in r1). The flags are the C's: both functions set them again before they read
@ them. rewards_number_hook stands at a function's entry: s0-s15 and the flags are free there, and the hidden return
@ leaves r0 the scene (FUN_00ab88f4 returns nothing).
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfp
    .arm
    .global _start
    .global quest_end_hook, rewards_tick_hook, rewards_number_hook

_start:
quest_end_hook:
    push    {r0-r3, r12, lr}
    vpush   {d0-d7}
    bl      quest_end_delta           @ r0: the main object
    vpop    {d0-d7}
    vmov    s1, r0
    pop     {r0-r3, r12, lr}
    bx      lr

rewards_tick_hook:
    push    {r0-r3, r12, lr}
    vpush   {d0-d7}
    mov     r0, r4                    @ the scene
    vmov    r1, s0                    @ its fraction
    vmov    r2, s1                    @ the frame time
    bl      rewards_timer_add
    vpop    {d0-d7}
    vmov    s0, r0
    pop     {r0-r3, r12, lr}
    bx      lr

rewards_number_hook:
    push    {r0-r3, r12, lr}
    bl      rewards_number_hidden     @ r0: the scene
    cmp     r0, #0
    pop     {r0-r3, r12, lr}
    bxne    lr                        @ hidden: FUN_00ab88f4 returns to its caller
    push    {r4, lr}                  @ the game's instruction
    b       rewards_countdown_body    @ and the rest of FUN_00ab88f4
