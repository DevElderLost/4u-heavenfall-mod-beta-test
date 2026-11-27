@ The guarded entry into a pack (risk 3), a unit of
@ the packs' loader's block. The game's calls that the network callback can make go into the port machinery's pack
@ through a guarded stub (game/executable/packs.py guarded_stub): `add r12, pc, #0` then `b pack_guarded`, with r12 at
@ the stub's four words {the pack's function, the game's (the call's old target), the state byte's address, the busy
@ word's}. Whatever thread makes the call, the busy word counts it while it runs: raised before the state byte is read,
@ lowered after the call returns. The scene gate (pack_loader.c) clears the state byte first and frees the pack only
@ once the busy word is 0, so a call that read the byte set finishes before the pack goes, and one that reads it after
@ goes to the game's function. r0-r3 reach the function as the game left them (the calls take at most four arguments
@ in registers, none on the stack: sdk/proof_api.h), r0-r1 come back.
    .arm
    .text
    .global pack_guarded
    .type pack_guarded, %function
pack_guarded:
    push    {r4-r6, lr}
    mov     r4, r12                 @ the stub's words
    ldr     r5, [r4, #12]           @ the busy word
1:  ldrex   r6, [r5]
    add     r6, r6, #1
    strex   r12, r6, [r5]
    cmp     r12, #0
    bne     1b
    mov     r12, #0
    mcr     p15, 0, r12, c7, c10, 5 @ data memory barrier: the count is seen before the state byte is read
    ldr     r12, [r4, #8]
    ldrb    r12, [r12]
    tst     r12, #1
    ldrne   r12, [r4]               @ in: the pack's function
    ldreq   r12, [r4, #4]           @ out: the game's
    blx     r12
    mov     r12, #0
    mcr     p15, 0, r12, c7, c10, 5 @ the call's accesses before the count goes down
2:  ldrex   r6, [r5]
    sub     r6, r6, #1
    strex   r12, r6, [r5]
    cmp     r12, #0
    bne     2b
    pop     {r4-r6, pc}
    .size pack_guarded, . - pack_guarded

@ The opening of a screen's pack: an opening stub
@ (game/executable/packs.py opening_stub) saves r12 and lr, puts the pack's slot in r12 and calls this, which keeps
@ every other register and the flags, calls pack_loader.c's pack_open(slot) on an 8-aligned stack and returns; the
@ stub then goes on into the pack or to the game's fallback by the state byte, as an entry stub does.
    .global pack_opening
    .type pack_opening, %function
pack_opening:
    push    {r0-r6, lr}
    mrs     r4, cpsr
    mov     r5, sp
    bic     r6, r5, #7
    mov     sp, r6
    mov     r0, r12
    bl      pack_open
    mov     sp, r5
    msr     cpsr_fs, r4
    pop     {r0-r6, pc}
    .size pack_opening, . - pack_opening
