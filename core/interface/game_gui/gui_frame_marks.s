@ The game GUI recorder's frame marks (tools/ui/ui_probe.py): one wrapper
@ around the frame's wait for the GPU, FUN_00bf5fec(gx) (GAME_SYMBOLS gx_frame_wait; canonical addresses), where the
@ main thread spends almost all of each frame's time. The game's code that changes the GUI runs between two waits,
@ so the recorder copies the GUI while the main thread waits.
@
@ frame_wait: called instead of the wait from its two calls: the render (FUN_00bfa6c0, `bl` at 0xBFA718, when the
@   GX's flag 0x200 is set) and the GX end (FUN_00bfa460, `b` at 0xBFA470, otherwise). Copies started into
@   gui_frame_marks + 4 (done), calls the wait with the caller's r0-r3, adds one to gui_frame_marks + 0 (started) and
@   returns the wait's r0 / r1. r4-r6 are pushed with lr (the stack stays 8-byte aligned); only r5 and r12 are used.
@ So started == done while the main thread waits and started == done + 1 while it runs the frame: the recorder keeps a
@ copy only when the two read the same before and after it (core/interface/game_gui/recorder/exact.py). The product never
@ writes the marks.
@
@ Build: a block of the layout (game/executable/blocks.py, gui_frame_marks_probe), packed after every other block; only
@ tools/ui/ui_probe.py places it, so the probe needs no ARM toolchain.

    .arch armv6k
    .arm
    .global _start

_start:
frame_wait:
    push    {r4, r5, r6, lr}
    ldr     r12, marks_wait
    ldr     r5, [r12]
    str     r5, [r12, #4]             @ done = started: the frame's GUI work is over
    bl      gx_frame_wait
    ldr     r12, marks_wait
    ldr     r5, [r12]
    add     r5, r5, #1
    str     r5, [r12]                 @ started + 1: the next frame's work begins
    pop     {r4, r5, r6, pc}
marks_wait:
    .word   gui_frame_marks
