@ With L held, the D-pad does not move the camera; L + D-pad up asks for a
@ target switch.
@
@ FUN_00b1cdf0, the player's input update in a quest (once per frame), copies
@ p + 0x3D0 into the actions p + 0x3CC and then ORs more actions into them:
@ FUN_00b28f54 the item mode (0xA00, actions 9 and 11, while L is held),
@ FUN_00b3d160 L + A / Y / X, and FUN_00b3cc64 the D-pad and the C-stick: the
@ D-pad from the game-layout buttons held (p + 0x3A0) and pressed this frame
@ (p + 0x3A4), up 0x2000, down 0x1000, left 0x800, right 0x400, into actions
@ 1-8 (the camera moves on 2 / 4 / 6 / 8); the C-stick from its analog state.
@ Its call at 0xB1D0B0 is replaced by `bl` to this wrapper (r0 = the hunter).
@ For the local hunter in item mode (action 11 or L held, game bit 0x8), the
@ D-pad bits are hidden from FUN_00b3cc64, so only the C-stick sets actions,
@ and target_request = D-pad up pressed this frame (else 0), which asm/target_button.s
@ consumes. The button words are restored afterwards.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ DPAD_ACTIONS, dpad_actions   @ FUN_00b3cc64(hunter)
    .equ SETTINGS_POINTER, game_control
    .equ PLAYER, 0xE30                @ p = *(hunter + 0xE30)
    .equ HUNTER_INDEX, 0x33           @ p + 0x33 == *(settings) + 0x2F: the local hunter
    .equ HELD, 0x3A0
    .equ PRESSED, 0x3A4
    .equ ACTIONS, 0x3CC
    .equ ITEM_MODE, 0x800             @ action 11
    .equ L_BUTTON, 0x8
    .equ DPAD, 0x3C00
    .equ DPAD_UP, 0x2000

_start:
    push    {r4-r8, lr}
    mov     r4, r0
    ldr     r5, [r0, #PLAYER]
    ldr     r1, settings_pointer
    ldr     r1, [r1]
    ldrsb   r1, [r1, #0x2F]
    ldrb    r2, [r5, #HUNTER_INDEX]
    cmp     r1, r2
    bne     plain                     @ another hunter: untouched
    ldr     r12, flag_pointer
    ldr     r1, [r5, #ACTIONS]
    ldr     r6, [r5, #HELD]
    ldr     r7, [r5, #PRESSED]
    tst     r1, #ITEM_MODE
    tsteq   r6, #L_BUTTON
    moveq   r0, #0
    streq   r0, [r12]
    beq     plain
    and     r0, r7, #DPAD_UP
    str     r0, [r12]
    bic     r0, r6, #DPAD
    str     r0, [r5, #HELD]
    bic     r0, r7, #DPAD
    str     r0, [r5, #PRESSED]
    mov     r0, r4
    bl      DPAD_ACTIONS
    str     r6, [r5, #HELD]
    str     r7, [r5, #PRESSED]
    pop     {r4-r8, pc}
plain:
    mov     r0, r4
    pop     {r4-r8, lr}
    b       DPAD_ACTIONS

settings_pointer:
    .word SETTINGS_POINTER
flag_pointer:
    .word target_request              @ read by target_button.s
