@ Item marks' hook stubs (interface/item_marks/item_marks.py): they hand item_marks.c the item each icon is written
@ with, and the icons drawn with a mark.
@
@ The item setters, FUN_00c0de18 (24 px) and FUN_00c0e268 (16 px), (any, sprite data + 0x10, item):
@ im_big_entry, im_small_entry   their second instruction, `stmdb sp!, {r4, r5, r6, lr}`: it, then the item (r2) into
@                                r6, which the function never uses, and back to the third.
@ im_big_exit, im_small_exit     their one epilogue, `ldmia sp!, {r4, r5, r6, pc}` (the early exit reaches it too):
@                                item_marks_icon(r4 = data + 0x10, r6 = the item), then the epilogue.
@
@ The shape writer FUN_00c118f4(any, data + 0x10, shape, &tint) at the 13 sites that read the item table inline
@ (im_site_<address>): the game's call, then item_marks_icon(data + 0x10, the item the caller keeps: a register it
@ saves or memory it points at). Every site reloads r0-r3 after the call, so they hold nothing.
@
@ The vertex builder FUN_00ae7098(data + 0x10, context, state), called for each sprite drawn:
@ im_seen_walk    in the tree walk FUN_00ae56a4 (r7 the group, r5 the pane);
@ im_seen_queue   in the redraw queue FUN_00ae5514 (r6 the group, r4 the queued node, whose + 0xC is the pane).
@ A sprite whose u carries the mark's signature (item_marks.c MARK) goes to item_marks_seen(group, pane) first; every
@ sprite then goes to the builder with its registers as they came (a tail call: lr is the caller's).
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global im_big_entry, im_big_exit, im_small_entry, im_small_exit, im_seen_walk, im_seen_queue
    .global im_site_602c44, im_site_603010, im_site_603298, im_site_69f854, im_site_6a79a4, im_site_6a7f9c
    .global im_site_aadef4, im_site_ab7e88, im_site_ab85f0, im_site_abacb8, im_site_abb0dc, im_site_ac10fc
    .global im_site_ad19e8

    .equ MARK_MASK, 0x7c              @ item_marks.c MARK_MASK, MARK
    .equ MARK, 0x28
    .equ U, 0x20                      @ u from data + 0x10

_start:
im_big_entry:
    push    {r4, r5, r6, lr}
    mov     r6, r2
    b       item_icon_body

im_small_entry:
    push    {r4, r5, r6, lr}
    mov     r6, r2
    b       item_icon_small_body

im_big_exit:
im_small_exit:
    mov     r0, r4
    mov     r1, r6
    bl      item_marks_icon
    pop     {r4, r5, r6, pc}

@ A site: the caller's call, then the mark. In: r1 data + 0x10; the item loaded into r4 by `load` before the call.
    .macro  site name, load:vararg
\name:
    push    {r1, r4, r5, lr}
    \load
    bl      icon_draw
    ldr     r0, [sp]
    mov     r1, r4
    bl      item_marks_icon
    pop     {r1, r4, r5, pc}
    .endm

    site    im_site_602c44, uxth r4, r7         @ FUN_00602b58, the START menu's pouch rows
    site    im_site_603010, uxth r4, r7
    site    im_site_603298, uxth r4, r7
    site    im_site_69f854, mov r4, r8          @ FUN_0069f61c, the quest pouch (ui206)
    site    im_site_6a79a4, ldr r4, [sp, #0x14] @ FUN_006a7700: its [sp + 4], 16 bytes up
    site    im_site_6a7f9c, ldr r4, [sp, #0x14]
    site    im_site_aadef4, mov r4, r8          @ FUN_00aad98c, the quest rewards
    site    im_site_ab7e88, ldrh r4, [r11]      @ FUN_00ab8188
    site    im_site_ab85f0, ldrh r4, [r11]
    site    im_site_abacb8, mov r4, r8          @ FUN_00aba7c8
    site    im_site_abb0dc, mov r4, r8
    site    im_site_ac10fc, mov r4, r8          @ FUN_00ac0d90
    site    im_site_ad19e8, ldrh r4, [r9]       @ FUN_00ad1604, the items sold or sent

im_seen_walk:
    ldr     r12, [r0, #U]
    and     r12, r12, #MARK_MASK
    cmp     r12, #MARK
    bne     sprite_vertices
    push    {r0-r3, r12, lr}
    mov     r0, r7
    mov     r1, r5
    bl      item_marks_seen
    pop     {r0-r3, r12, lr}
    b       sprite_vertices

im_seen_queue:
    ldr     r12, [r0, #U]
    and     r12, r12, #MARK_MASK
    cmp     r12, #MARK
    bne     sprite_vertices
    push    {r0-r3, r12, lr}
    mov     r0, r6
    ldr     r1, [r4, #0xc]
    bl      item_marks_seen
    pop     {r0-r3, r12, lr}
    b       sprite_vertices
