@ Releases the top-screen copy of the target camera panel.
@
@ The copy's three groups live at the fixed indices COPY_INDEX... of the GUI
@ manager, outside every range the game frees, so they are released here: at
@ the start of FUN_00c0f110 (which frees the GUI layouts when leaving a quest
@ or a menu) the instruction at 0xC0F11C, `ldr r0, [r0, #0x100]` (the
@ manager), becomes `bl` to this routine, which frees those indices with
@ FUN_00b044f4 (it skips empty slots) and returns the manager in r0.
@ face_loader.s calls it too, before creating the copy.
@
@ In: r0 = gui. Out: r0 = *(gui + 0x100). r1-r3 and r12 are free there.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ FREE_GROUP, free_group       @ FUN_00b044f4(manager, index)
    .equ COPY_INDEX, 0x5C0            @ code_patch.COPY_INDEX
    .equ COPY_GROUPS, 3

_start:
    push    {r4, r5, r6, lr}
    ldr     r4, [r0, #0x100]
    cmp     r4, #0
    beq     done
    mov     r5, #COPY_INDEX
    mov     r6, #COPY_GROUPS
next:
    mov     r0, r4
    mov     r1, r5
    bl      FREE_GROUP
    add     r5, r5, #1
    subs    r6, r6, #1
    bne     next
done:
    mov     r0, r4
    pop     {r4, r5, r6, pc}
