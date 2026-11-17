@ The jukebox's card file hooks (music/jukebox/save_patch.py), a unit of the block
@ jukebox.
@
@ jukebox_store_stub  bl from FUN_002adedc (the card file's writer) at 0x2ADFDC, which replaces its `mov r3, #1` after
@                     the game's last copy into the plain file and before the sum's call: r4 the plain file.
@                     jukebox_store(r4), then `mov r3, #1`; r4-r11 kept (the writer sets r0-r2 again after it).
@ jukebox_load_stub   bl from FUN_002ae018 (the card file's read step) at 0x2AE05C, which replaces its `bl
@                     FUN_002adc98` (the reader): r0 the file task. Calls the reader; when it answers 1 (the file's sum
@                     and hunter id accepted, the plain file still at the task's +0x138), jukebox_load(that file).
@                     Returns the reader's answer.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .syntax unified
    .arch armv6k
    .arm
    .global jukebox_store_stub
    .global jukebox_load_stub

    .equ    TASK_FILE, 0x138        @ the file task's buffer: the file read or to write

    .section .text.jukebox_store_stub, "ax", %progbits
jukebox_store_stub:
    push    {r4, lr}
    mov     r0, r4
    bl      jukebox_store
    mov     r3, #1
    pop     {r4, pc}

    .section .text.jukebox_load_stub, "ax", %progbits
jukebox_load_stub:
    push    {r4, lr}
    mov     r4, r0
    bl      card_read
    cmp     r0, #1
    popne   {r4, pc}
    ldr     r0, [r4, #TASK_FILE]
    bl      jukebox_load
    mov     r0, #1
    pop     {r4, pc}
