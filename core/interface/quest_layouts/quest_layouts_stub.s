@ The quest's layouts of our own (interface/quest_layouts/quest_layouts.py): three sites of the game serve every feature
@ that draws a layout of its own in a quest (Damage Numbers, the
@ Hunting Horn's songs). Each keeps what its game function needs, hands over to quest_layouts.c, which walks the
@ table quest_layouts_data, and does the instruction it replaced:
@
@ quest_frame_hook  sMhMain::frame (FUN_00af52a0), `ldr r0, [r4, #0x2bc]` after every system's move and before the
@                   render: each feature's frame, then the load. The instruction before is a `blx`, so r0-r3, r12 and
@                   the flags hold nothing the frame reads again; r4 (sMhMain) is kept by the C.
@ quest_loader      FUN_00c1017c (the quest's layouts), its `mov r4, #0` right after the stage map's load (the
@                   instruction after the one the target face's face_loader.s takes): each feature's layout at its
@                   index of the GUI manager on the top screen, as face_loader.s loads its copy, then the move.
@ quest_free        FUN_00c0f110 (frees the GUI layouts when leaving a quest or a menu), its `mov r10, r1` (the
@                   instruction before the one face_free.s takes): frees each feature's index, keeps r0-r3, then the
@                   move.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ FRAME, 8                     @ what quest_loader pushes: the caller's sp = sp + FRAME

_start:
quest_frame_hook:
    push    {r12, lr}
    bl      quest_frame
    pop     {r12, lr}
    ldr     r0, [r4, #0x2bc]          @ the replaced instruction
    bx      lr

@ In: r6 gui, sl the file loader's variable, [sp + 4] the resource handle, [sp + 8] the language (FUN_00c1017c's
@ frame); r0-r3 and r12 free; r4 is set to 0 at the end, the other registers are the C's to keep.
quest_loader:
    push    {r4, lr}
    mov     r0, r6                    @ the GUI
    ldr     r1, [sl]                  @ the file loader
    add     r2, sp, #(FRAME + 4)      @ the resource handle's variable
    ldr     r3, [sp, #(FRAME + 8)]    @ the language
    bl      quest_load
    pop     {r4, lr}
    mov     r4, #0                    @ the replaced instruction
    bx      lr

@ In: r0 gui, r1 the function's second argument; r2, r3 and r12 kept too.
quest_free:
    push    {r0-r3, r12, lr}
    bl      quest_unload
    pop     {r0-r3, r12, lr}
    mov     r10, r1                   @ the replaced instruction
    bx      lr
