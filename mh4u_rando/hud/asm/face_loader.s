@ Loads a second instance of the target camera panel (ui601) on the top screen.
@
@ Group indices are taken: FUN_00c1017c puts the quest layouts and the stage
@ map (the minimap) at gui + 0x238 ... gui + 0x23A (363-499), and FUN_00c10928
@ puts the area map at the fixed index 500. A copy inside that range moves the
@ stage map (probe 12: no minimap) or is overwritten by the area map (probe
@ 13: no face). So the copy goes to the fixed indices COPY_INDEX... (the game
@ uses 20-510 and 1526-1535), released by face_free.s.
@
@ The `ldr r7, =0xEFE1E8` at 0xC10430 in FUN_00c1017c, where every stage map
@ path joins, becomes `bl` to this routine: it releases a leftover copy,
@ repeats the loader's sequence for ui601 on screen 0 at COPY_INDEX and does
@ the replaced load.
@
@ Caller state: r6 gui, sl = 0xFB6B7C (pointer to the file loader), [sp + 4]
@ resource handle, [sp + 8] language byte. r0-r3 and r12 are free; r4 is set
@ by the caller right after; r7 receives the replaced literal.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ LOAD_FILE, load_file         @ FUN_002b51c0(loader, &handle, path, language, 0)
    .equ CREATE_GROUPS, create_groups @ FUN_00c0f474(gui, screen, first index, layout) -> groups
    .equ RELEASE, resource_release    @ FUN_00be2768(layout)
    .equ COPY_INDEX, 0x5C0            @ code_patch.COPY_INDEX
    .equ FRAME, 24                    @ what this routine pushes: caller's sp = sp + FRAME

_start:
    push    {r4, r6, r7, lr}
    sub     sp, sp, #8
    mov     r0, r6
    bl      face_free
    mov     r0, #0
    str     r0, [sp]                  @ 5th argument
    ldr     r2, ui601_path
    ldr     r2, [r2]                  @ the quest list's own ui601 path
    ldr     r3, [sp, #(FRAME + 8)]
    add     r1, sp, #(FRAME + 4)
    ldr     r0, [sl]
    bl      LOAD_FILE
    ldr     r0, resources
    ldr     r1, [sp, #(FRAME + 4)]
    mov     r3, #1
    ldr     r0, [r0]
    cmp     r1, #0
    addne   r2, r1, #8
    ldreq   r2, no_name
    ldr     r1, [r0]
    ldr     r12, [r1, #0x38]
    ldr     r1, layout_type
    blx     r12                       @ the layout resource
    movs    r4, r0
    beq     loaded
    mov     r3, r0
    mov     r2, #COPY_INDEX
    mov     r1, #0                    @ top screen
    mov     r0, r6
    bl      CREATE_GROUPS
    mov     r0, r4
    bl      RELEASE
loaded:
    add     sp, sp, #8
    pop     {r4, r6, r7, lr}
    ldr     r7, extra_layouts         @ the replaced instruction
    bx      lr

resources:
    .word resource_manager
no_name:
    .word empty_name
layout_type:
    .word layout_dti
ui601_path:
    .word ui_paths + 12 * 4
extra_layouts:
    .word extra_layout_paths
