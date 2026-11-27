@ The hooks of the Cheats group's damage multipliers (cheats/damage_multipliers/damage_multipliers.py; docs/cheats/
@ cheats.md, "Damage multipliers"). Each hands the game's numbers to damage_multipliers.c and puts its answer where the
@ game's function goes on with it:
@
@ damage_dealt_hook   FUN_00921f74's call of FUN_0092bf98(uEnemy, total, flag, 1) (the hit's final damage): the call,
@                     then damage_dealt with the region (FUN_00921f74's r6), the hit record (r4, FUN_00be9c64's) and
@                     the attacker (FUN_00be9c64's r6, which FUN_00921f74 saved at its sp + 8). Damage Numbers' hook of
@                     the call of FUN_00921f74 keeps both, so the number it shows is the multiplied damage.
@ damage_taken_check  FUN_00b1ac40(hunter, change, out), its `mov r1, r10` before its call of FUN_00b6b4bc: r10 (the
@                     change its Guts test reads after the call) and r1 take damage_taken's answer; r0 kept.
@ health_add_kept     that call of FUN_00b6b4bc: its change is the answer already, so FUN_00b6b4bc's first two words
@                     run here and the rest of it after them, past damage_taken_add.
@ damage_taken_add    FUN_00b6b4bc(hunter, change), its `mov r5, r1`: r5 (the change it adds) takes damage_taken's
@                     answer; r0 kept. Its first word pushed nine, so three here keep the stack's eight bytes.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global damage_dealt_hook, damage_taken_check, health_add_kept, damage_taken_add

    .equ SAVED_R6, 24                   @ our four words, then FUN_00921f74's saved r4, r5, r6

_start:
damage_dealt_hook:
    push    {r0, r1, r4, lr}
    bl      monster_damage_rate         @ FUN_0092bf98, the replaced call
    ldr     r12, [sp, #SAVED_R6]        @ the attacker
    ldr     r1, [sp]                    @ uEnemy
    mov     r2, r6                      @ the region
    mov     r3, r4                      @ the hit record
    sub     sp, sp, #8
    str     r12, [sp]
    bl      damage_dealt
    add     sp, sp, #16                 @ the argument and the call's r0, r1
    pop     {r4, pc}

damage_taken_check:
    push    {r0, lr}
    mov     r0, r4
    mov     r1, r10
    bl      damage_taken
    mov     r10, r0
    mov     r1, r0
    pop     {r0, pc}

health_add_kept:
    push    {r4-r11, lr}                @ FUN_00b6b4bc's first two words
    mov     r5, r1
    b       hunter_health_body          @ its third (0xB6B4C4) on

damage_taken_add:
    push    {r0, r1, lr}
    bl      damage_taken
    mov     r5, r0
    pop     {r0, r1, pc}
