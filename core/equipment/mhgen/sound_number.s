@ Sound numbers (option mhgen_models): a pack weapon past the end of
@ its class's sound number table plays the sounds of its own id.
@
@ FUN_0030d08c builds a weapon's sound paths from a sound number, table[model] (a byte per model, a table per
@ class), only for models up to the class's last: `cmp r1, r3` then `bhi` past the lookup. Each of its two
@ lookups has that `bhi` pointed here instead; r1 = the model, r6 = the weapon (both kept).
@ * _start (0x30D324, the weapon's bank, or the bowguns' B bank): does what follows the `bhi` up to the lookup
@   (`mov r3, #1`, `stmia sp, {r3, r6}`), r3 = the model instead of `ldrb r3, [r0, r1]`, and goes on after it.
@ * sf (0x30D3D8, the bowguns' SF bank): the same for `mov r0, #2`, `stmia sp, {r0, r6}`, r2 = the class.
@ A model of 255 or more still skips (0xFF is the tables' "no sound").
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global sf

    .equ NO_SOUND, 0xFF
    .equ SKIP, sound_skip       @ the `bhi` target: no sound path
    .equ BANK_LOOKED_UP, sound_bank_looked_up
    .equ SF_LOOKED_UP, sound_sf_looked_up

_start:
    cmp     r1, #NO_SOUND
    ldrhs   pc, =SKIP
    mov     r3, #1
    stmia   sp, {r3, r6}
    mov     r3, r1
    ldr     pc, =BANK_LOOKED_UP

sf:
    cmp     r1, #NO_SOUND
    ldrhs   pc, =SKIP
    mov     r0, #2
    stmia   sp, {r0, r6}
    ldr     r0, [r6, #0xe30]
    ldrb    r2, [r0, #0x31]
    mov     r3, r1
    ldr     pc, =SF_LOOKED_UP
