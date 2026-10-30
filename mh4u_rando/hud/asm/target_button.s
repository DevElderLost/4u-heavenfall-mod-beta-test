@ L + D-pad up switches the large-monster target.
@
@ FUN_00b94854 (target camera panel) already has a button shortcut: when the
@ GUI "pressed" buttons of the pad (pad + 0x348) contain 0x8000 and a setting
@ byte (*0xFB6B7C + 0x2B) is 1, it sets panel + 0x27E = 1, which makes
@ FUN_00b8d074 switch the target exactly like a tap on the panel. The test at
@ 0xB948AC is replaced by `bl` to this function and a branch on r0:
@     r0 != 0 if asm/dpad_filter.s saw L held + D-pad up pressed, or the original test.
@ dpad_filter.s runs in the player's per-frame input update and leaves the
@ request in target_request (a variable in .bss); it is consumed here, so a
@ press switches once. Only r0, r1 and r12 are used (the caller reloads r0).
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ PAD_POINTER, pad_control
    .equ SETTINGS_POINTER, game_control
    .equ PRESSED, 0x348
    .equ SHORTCUT_BUTTON, 0x8000

_start:
    ldr     r12, flag_pointer
    ldr     r0, [r12]
    cmp     r0, #0
    movne   r1, #0
    strne   r1, [r12]
    bxne    lr
original:
    ldr     r12, pad_pointer
    ldr     r12, [r12]
    ldr     r0, [r12, #PRESSED]
    ands    r0, r0, #SHORTCUT_BUTTON
    bxeq    lr
    ldr     r12, settings_pointer
    ldr     r12, [r12]
    ldrb    r0, [r12, #0x2B]
    cmp     r0, #1
    movne   r0, #0
    bx      lr

flag_pointer:
    .word target_request              @ written by dpad_filter.s
pad_pointer:
    .word PAD_POINTER
settings_pointer:
    .word SETTINGS_POINTER
