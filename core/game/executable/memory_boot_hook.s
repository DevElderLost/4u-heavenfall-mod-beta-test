@ The heap sizes at boot: the hook in FUN_001047c0 (game/executable/memory_boot.py).
@
@ memory_boot_hook   a `bl` in place of FUN_001047c0's `sub r0, r4, r5` (0x104804). There r6 = min(APPMEMALLOC,
@     cap), r4 = r6 less what the process already uses, r5 = the device memory (the literal, plus 0xA00000 on a New
@     3DS) and r0 = FUN_001067a8's answer (1 on a New 3DS). It returns r0 = memory_boot_sizes(r6, r4, r0, &r5) (the
@     root heap's size) and r5 = the device memory's size (memory_boot.c). The function then rounds both down to
@     pages, commits the root heap (FUN_001058ac) and allocates the device memory (FUN_001059a8). r1-r3, r12 and the
@     flags hold nothing there (a call follows), and the next instruction writes r4.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    push    {r4, lr}                  @ 8 bytes: the stack stays on 8
    sub     sp, sp, #8
    str     r5, [sp]                  @ *device: the game's device memory
    mov     r3, sp
    mov     r2, r0                    @ new3ds
    mov     r1, r4                    @ avail
    mov     r0, r6                    @ app
    bl      memory_boot_sizes
    ldr     r5, [sp]
    add     sp, sp, #8
    pop     {r4, pc}
