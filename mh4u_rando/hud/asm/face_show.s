@ Shows / hides the top-screen copy of the target camera panel with the
@ touch-screen panel and the top-screen HUD.
@
@ The game shows and hides its GUI groups with FUN_00ae53e0(group, visible).
@ The first instruction of FUN_00ae53e0, `push {r4, r5, r6}` at 0xAE53E0,
@ becomes `b` to this routine, which looks at the calls that change a group's
@ visibility:
@   - a group of the ui601 binder (0x1085650: panel00, panel01, target00):
@     its copy gets the same (panel00 / panel01 -> the copy of panel00, the
@     only face shown on the top screen; target00 -> the copy of target00),
@     but it is only shown while the HUD is. Every frame the panel update
@     (FUN_00b93788) hides the three groups and shows the needed ones, so the
@     copies end every frame as the touch-screen panel does;
@   - the HUD's health bar (ui202_tairyoku, *(0x1083EDC), in the ui202
@     binder): when it is hidden (FUN_00b8e0b8 while loading an area, menus,
@     cutscenes; FUN_00b826bc then skips the panel update), both copies are
@     hidden. The mirror (target_face.c) shows them again with the HUD.
@ Then it runs the original function.
@
@ FUN_00ae53e0 is a leaf (r0 group, r1 visible; it pushes r4-r6 only), so
@ `body` (the replaced instruction + a branch back) can be called like it.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ GUI_POINTER, gui_control     @ GUI object; + 0x100 = layout manager
    .equ BINDER, target_binder        @ ui601 binder: panel00, panel01, target00
    .equ HUD_REF, health_binder       @ ui202 binder: ui202_tairyoku (code_patch.HUD_REF)
    .equ COPY_INDEX, 0x5C0            @ code_patch.COPY_INDEX

_start:
    ldr     r12, [r0, #0x44]
    and     r12, r12, #0x400
    cmp     r1, #0
    movne   r2, #0x400
    moveq   r2, #0
    cmp     r12, r2
    beq     body                      @ no change
    push    {r0, r1, r4, r5, r6, lr}
    mov     r5, r1                    @ the new visibility
    ldr     r12, hud_ref
    ldr     r12, [r12]
    cmp     r12, r0
    bne     panels
    cmp     r5, #0
    bne     done                      @ the HUD is back: the mirror shows the copies
    mov     r4, #0
    bl      set_copy
    mov     r4, #2
    bl      set_copy
    b       done
panels:
    cmp     r5, #0
    beq     find
    cmp     r12, #0                   @ showing: only while the HUD is shown
    beq     done
    ldr     r12, [r12, #0x44]
    tst     r12, #0x400
    beq     done
find:
    ldr     r12, binder
    mov     r4, #0
next:
    ldr     r2, [r12, r4, lsl #2]
    cmp     r2, r0
    beq     found
    add     r4, r4, #1
    cmp     r4, #3
    blo     next
    b       done
found:
    cmp     r4, #2
    movne   r4, #0                    @ both face panels -> the copy of panel00
    bl      set_copy
done:
    pop     {r0, r1, r4, r5, r6, lr}
body:
    push    {r4, r5, r6}              @ the replaced instruction
    b       group_show_body

@ The copy at slot COPY_INDEX + r4 gets visibility r5 (r0-r3, r6, r12 used).
set_copy:
    mov     r6, lr
    ldr     r12, gui_pointer
    ldr     r12, [r12]
    cmp     r12, #0
    ldrne   r12, [r12, #0x100]
    cmpne   r12, #0
    beq     back
    ldr     r2, [r12, #0x160]         @ slot count
    add     r3, r4, #COPY_INDEX
    cmp     r3, r2
    bhs     back
    ldr     r12, [r12, #0x154]        @ slots
    ldr     r0, [r12, r3, lsl #2]
    cmp     r0, #0
    movne   r1, r5
    blne    body
back:
    bx      r6

binder:
    .word BINDER
hud_ref:
    .word HUD_REF
gui_pointer:
    .word GUI_POINTER
