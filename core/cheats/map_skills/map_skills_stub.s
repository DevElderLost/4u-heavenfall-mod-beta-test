@ The hooks of Capture Guru and Autotracker always on (cheats/map_skills/map_skills.py). Each stands in for a call `bl
@ FUN_00d04f58(hunter, skill)`, the game's
@ "has skill", in a function of the minimap:
@
@ capture_guru_hook   FUN_00b9b390 (a large monster's mark on the minimap), skill 0xBF;
@ autotracker_hook    FUN_00b9651c (whether the minimap shows the large monsters), skill 0xBD.
@
@ With the cheat on (map_skills.c map_skill_on) it answers 1 with r1-r3 and r12 as they came, as the Gateway code's
@ `mov r0, #1` does; off, it goes on to the game's call with every register as it came, which returns to the caller.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global capture_guru_hook, autotracker_hook

    .equ CAPTURE_GURU, 0                @ map_skills.c: the cheats' places in map_skills_data
    .equ AUTOTRACKER, 1

    .macro skill name, which
\name:
    push    {r0-r3, r12, lr}
    mov     r0, #\which
    bl      map_skill_on
    cmp     r0, #0
    pop     {r0-r3, r12, lr}
    beq     has_skill_entry           @ off: the game's call
    mov     r0, #1                    @ on: the hunter has the skill
    bx      lr
    .endm

_start:
    skill   capture_guru_hook, CAPTURE_GURU
    skill   autotracker_hook, AUTOTRACKER
