@ The aspect ratio's hooks (cheats/aspect_ratio.py). Each site's instruction becomes a `bl`
@ to its stub, and lr is free at each: the three functions saved it on entry and none reads it afterwards before writing
@ it. The logic is in aspect_ratio.c.
@
@ Every stub keeps what the game's function goes on with:
@   - r0-r3, r12 and d0-d7 are saved, as the C may use them; r4-r11 and d8-d15 are callee-saved;
@   - the stack stays 8-byte aligned: 6 words and 16 words are pushed, 88 bytes.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfp
    .arm
    .global _start
    .global aspect_view, aspect_gui, aspect_sub_view

    .equ SAVED, 88              @ the bytes saved below

_start:

@ FUN_00aeee7c: vstr s0, [r6, #0x38]. r5 = the view, r6 = its camera. aspect_store does the store.
aspect_view:
    push    {r0-r3, r12, lr}
    vpush   {d0-d7}
    vmov    r0, s0
    mov     r1, r5
    mov     r2, r6
    bl      aspect_store
    vpop    {d0-d7}
    pop     {r0-r3, r12, pc}

@ FUN_00af3db0: bl FUN_00b70fc0(r0 = the matrix, s0, s1 = the sides of the view's rectangle, s2, s3). The saved s0, s1 lie at
@ sp, in that order, for aspect_gui_sizes to change; FUN_00b70fc0 returns to the instruction after the hooked `bl`.
aspect_gui:
    push    {r0-r3, r12, lr}
    vpush   {d0-d7}
    mov     r0, sp
    bl      aspect_gui_sizes
    vpop    {d0-d7}
    pop     {r0-r3, r12, lr}
    b       gui_projection

@ FUN_00c042ec: str r2, [sp, #4]. r2 = the rectangle, read by FUN_00aee0f0 through that stack word.
aspect_sub_view:
    push    {r0-r3, r12, lr}
    vpush   {d0-d7}
    mov     r0, r2
    bl      aspect_rect
    str     r0, [sp, #SAVED + 4]
    vpop    {d0-d7}
    pop     {r0-r3, r12, pc}
