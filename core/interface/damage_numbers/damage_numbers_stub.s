@ Damage Numbers' hooks (interface/damage_numbers/damage_numbers.py). Each
@ keeps what its game function needs, does the call it replaced and hands the damage to damage_numbers.c. The frame,
@ the layout's load and its free go through the quest's shared hooks (interface/quest_layouts/), whose table calls
@ dmg_frame.
@
@ dmg_hit_hook     FUN_00be9c64 (a hit on a monster), its only call of FUN_00921f74(uEnemy, region, total, flag), which
@                  adds the hit's final damage to the monster's damage of the frame (em + 0x4B4 + 2 * region): that
@                  halfword before and after the call gives dmg_hit what the hit dealt, with the hit record (r4), the
@                  hunter (r6) and FUN_00be9c64's stack frame (the caller's sp).
@ dmg_blast_hook   FUN_00920104 (the monster's damage step), its call of FUN_009178e8(uEnemy), the blast that adds its
@                  damage to the region of the last blast hit (em + 0x7AB8): the same halfword before and after.
@ dmg_poison_hook  FUN_00920104's call of FUN_0093ba30(uEnemy, -poison, max) for a poison tick, and
@ dmg_mount_hook   its call for the mount's finish: dmg_status with the damage, then the call (a tail branch).
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ EM, 0xE28                    @ uEnemy: its em
    .equ DAMAGE_HI, 0x400             @ em + DAMAGE_HI + DAMAGE_LO + 2 * region: the frame's damage of the region
    .equ DAMAGE_LO, 0xB4
    .equ BLAST_HI, 0x7A00             @ em + BLAST_HI + BLAST_LO: the region of the last blast hit (u8)
    .equ BLAST_LO, 0xB8
    .equ KIND_POISON, 1               @ damage_numbers.c
    .equ KIND_BLAST, 2
    .equ KIND_MOUNT, 3

_start:
@ r0 = em + 0x4B4 + 2 * r1 (r0 uEnemy, r1 region)
damage_slot:
    ldr     r0, [r0, #EM]
    add     r0, r0, r1, lsl #1
    add     r0, r0, #DAMAGE_HI
    add     r0, r0, #DAMAGE_LO
    bx      lr

dmg_hit_hook:
    push    {r0-r6, lr}               @ the call's r0-r3, then r4-r6 kept (r5 holds the halfword before)
    bl      damage_slot
    ldrsh   r5, [r0]
    ldm     sp, {r0-r3}
    bl      monster_hit_damage        @ FUN_00921f74, the replaced call
    ldm     sp, {r0, r1}
    bl      damage_slot
    ldrsh   r2, [r0]
    sub     r2, r2, r5                @ what the hit dealt
    ldm     sp, {r0, r1}
    mov     r3, r4                    @ the hit record
    add     r12, sp, #32              @ FUN_00be9c64's frame
    push    {r6, r12}                 @ the hunter, the frame
    bl      dmg_hit
    add     sp, sp, #8
    pop     {r0-r6, pc}

dmg_blast_hook:
    push    {r0-r5, r12, lr}
    ldr     r12, [r0, #EM]
    add     r12, r12, #BLAST_HI
    ldrb    r1, [r12, #BLAST_LO]      @ the region it adds to
    mov     r4, r1
    bl      damage_slot
    ldrsh   r5, [r0]
    ldm     sp, {r0-r3}
    bl      blast_damage              @ FUN_009178e8, the replaced call
    ldr     r0, [sp]
    mov     r1, r4
    bl      damage_slot
    ldrsh   r1, [r0]
    sub     r1, r1, r5
    lsl     r1, r1, #16
    asr     r1, r1, #16               @ what the blast dealt
    ldr     r0, [sp]
    mov     r2, #KIND_BLAST
    bl      dmg_status
    pop     {r0-r5, r12, pc}

dmg_poison_hook:
    push    {r0-r3, r12, lr}
    rsb     r1, r1, #0
    mov     r2, #KIND_POISON
    bl      dmg_status
    pop     {r0-r3, r12, lr}
    b       enemy_vital_add           @ FUN_0093ba30, the replaced call

dmg_mount_hook:
    push    {r0-r3, r12, lr}
    rsb     r1, r1, #0
    mov     r2, #KIND_MOUNT
    bl      dmg_status
    pop     {r0-r3, r12, lr}
    b       enemy_vital_add
