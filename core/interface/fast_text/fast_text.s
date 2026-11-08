@ Fast text (option fast_text): holding B runs through the
@ conversation windows (ui005_kaiwa) at high speed.
@
@ FUN_005a9310 (message_update) drives the text of those windows every frame, and is the
@ only caller of the typewriter (FUN_00ae48d8, which takes the frame's delta time in s0) and
@ of its "go on" (FUN_00ae4ba8). Its first argument is the GUI buttons pressed this frame
@ (pad + 0x348). Each of its three `bl message_update` becomes `bl` to this routine, which,
@ while B is held (GUI held pad + 0x340, bit 0x20):
@   - passes B pressed every other call and nothing in between, so every page shows for at
@     least two frames. B, not A: B only goes on past a page break, while A at the end of the
@     message moves the window to the next line of the message file (the character's next
@     conversation), and the caller, which closes the window on a real press only, would show
@     line after line;
@   - passes nothing while the last call returned 3 (the end of the message): the caller
@     closes the window when the player presses A or B again;
@   - puts 1000.0 as the frame's delta (*(0x1057194) + 0x5C) during the call, the value
@     message_update itself gives the typewriter with the game's instant text setting (0x1D),
@     so pages appear at once; the frame's delta is put back afterwards.
@ Choices (yes / no prompts, menus) read the pad themselves, so they never see the B.
@
@ In: r0-r3 = message_update's arguments. Out: its result in r0.
@ fast_text_state: +0 calls while B is held, +4 the last call's result.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start, fast_text_entry

    .equ PAD, pad_control             @ the pad object
    .equ GUI_HELD, 0x340
    .equ B, 0x20                      @ GUI bit of B (game layout 0x40, raw 0x4000)
    .equ END, 3                       @ message_update's result at the end of the message
    .equ CLOCK, game_main             @ its +0x5C is the frame's delta time (float)
    .equ DELTA, 0x5C
    .equ INSTANT, 0x447A0000          @ 1000.0

_start:
fast_text_entry:
    ldr     r12, =PAD
    ldr     r12, [r12]
    cmp     r12, #0
    beq     original
    ldr     r12, [r12, #GUI_HELD]
    tst     r12, #B
    beq     original
    push    {r4-r6, lr}
    ldr     r4, =fast_text_state
    ldr     r5, [r4]
    add     r5, r5, #1
    str     r5, [r4]
    mov     r0, #0
    ldr     r6, [r4, #4]
    cmp     r6, #END
    beq     call
    tst     r5, #1
    moveq   r0, #B
call:
    ldr     r5, =CLOCK
    ldr     r5, [r5]
    cmp     r5, #0
    beq     plain
    ldr     r6, [r5, #DELTA]
    ldr     r12, =INSTANT
    str     r12, [r5, #DELTA]
    bl      message_update
    str     r6, [r5, #DELTA]
    str     r0, [r4, #4]
    pop     {r4-r6, pc}
plain:
    bl      message_update
    str     r0, [r4, #4]
    pop     {r4-r6, pc}
original:
    b       message_update
