@ The jukebox's hook stub (music/jukebox/patch.py), a unit of the block jukebox.
@
@ jukebox_pick_stub   bl from FUN_00304990's exit (0x304B70, the town's theme selector; it replaces `mov r0, r4`):
@                     r4 the stage's request, r5 the sound manager. Returns in r0 jukebox_pick(manager, request), which
@                     the selector's own `pop {r4-r8, pc}` then returns; r1-r3 and r12 stay as the selector left them.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .syntax unified
    .arch armv6k
    .arm
    .global jukebox_pick_stub

    .section .text.jukebox_pick_stub, "ax", %progbits
jukebox_pick_stub:
    push    {r1, r2, r3, r4, r12, lr}
    mov     r0, r5
    mov     r1, r4
    bl      jukebox_pick
    pop     {r1, r2, r3, r4, r12, pc}
