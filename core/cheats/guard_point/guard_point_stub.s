@ The hook of the cheat Charge Blade Guard Point (cheats/guard_point/guard_point.py).
@
@ guard_point_hook  FUN_00b1c6f0(hunter, group, number, flags), the start of the hunter's action: its first
@                   instruction, `push {r4-r12, lr}`, reached by a `b`, so lr is still its caller's. r2 becomes
@                   guard_point_action(hunter, group, number) (guard_point.c: the game's number, or the morph after an
@                   attack for the Charge Blade's morph from guarding); then the game's instruction runs and the rest
@                   of FUN_00b1c6f0 goes on with every other register as it came.
@
@ It stands at a function's entry: s0-s15 and the flags are free there (the C does no floating point). The push of six
@ words keeps the stack 8-byte aligned for the call.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global guard_point_hook

_start:
guard_point_hook:
    push    {r0-r3, r12, lr}
    bl      guard_point_action        @ r0 the hunter, r1 the group, r2 the number
    str     r0, [sp, #8]              @ the number to start: r2 once popped
    pop     {r0-r3, r12, lr}
    push    {r4-r12, lr}              @ the game's instruction
    b       hunter_start_action_body  @ and the rest of FUN_00b1c6f0
