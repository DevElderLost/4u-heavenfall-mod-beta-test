@ Gimmick donor (option mhgen_models): a MHGen weapon of
@ the pack moves its parts with the gimmick motions of a MH4U model of its class.
@
@ Every per-model table of the weapons' moving parts (gimmick type, mode, motion records, fixed model ids) reads
@ one copy of the model, which FUN_002d6d80(weapon, ref) sets: r0 = FUN_002f0fd4(_, ref), the model, then
@ `cpy r1, r0` (0x2D6DAC) and `b FUN_00354530` stores r1 at gimmick +0x264. That `cpy` becomes `bl _start`:
@ r0 = the model, r5 = ref (the 0x1C-byte equipment reference, byte 0 the equipment type, 7-20 for weapons),
@ r4 = the weapon object, kept. It returns r1 = gimmick_donor_table[type - 7][model] when that byte is not
@ 0, else the model. Uses r2, r3 only (the caller restores r4-r6 and lr right after).
@
@ gimmick_donor_table: a byte per equipment type (7-20) and model (0-255), written by equipment/mhgen/tables.py.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ FIRST_WEAPON, 7
    .equ CLASSES, 14
    .equ MODELS, 256

_start:
    mov     r1, r0
    ldrb    r2, [r5]
    sub     r2, r2, #FIRST_WEAPON
    cmp     r2, #CLASSES
    bxhs    lr                        @ not a weapon (unsigned: types below 7 too)
    cmp     r0, #MODELS
    bxhs    lr
    ldr     r3, =gimmick_donor_table
    add     r3, r3, r2, lsl #8
    ldrb    r2, [r3, r0]
    cmp     r2, #0
    movne   r1, r2
    bx      lr
