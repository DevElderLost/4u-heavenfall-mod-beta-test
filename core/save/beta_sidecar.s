@ Heavenfall Beta's sidecars: the four call sites' stubs (core/save/beta_sidecar.py, beta_sidecar.c).
@
@ Each site's instruction is replaced by `bl` to its stub here. A stub keeps r0-r3 and r12 (the game's code after the
@ site reads them), calls the C with the site's registers, then does the instruction it replaced:
@
@ * split_user, at 0x2ABEB8 in FUN_002abe04 (`mov r2, r8` before the checksum): r7 the task, r4 the buffer, r8 its size.
@ * split_card, at 0x2ADFE0 in FUN_002adedc (`mov r2, r9` before the checksum): r7 the task, r4 the buffer, r9 the size.
@ * join_user, at 0x2AF2E0 in FUN_002af280 (`bl save_copy_in`, the copy of the checked data): r5 the task + 0x18, r4
@   the buffer; r0-r2 the copy's arguments, kept for it.
@ * join_card, at 0x2ADDE8 in FUN_002adc98 (`bl card_sets_in`, the copy of the item sets): the task from file_task;
@   r0-r2 the copy's arguments, kept for it.
@
@ Each function pushes an even number of registers, so sp is 8-aligned at the site (the C's calls need it).
@ Build: tools/build/build_code_space.py, which places and links it.

    .arch armv6k
    .arm
    .global _start, beta_sidecar_split_user, beta_sidecar_split_card, beta_sidecar_join_user, beta_sidecar_join_card

_start:
beta_sidecar_split_user:
    push    {r0-r3, r12, lr}
    mov     r0, r7
    mov     r1, r4
    mov     r2, r8
    bl      beta_split_user
    pop     {r0-r3, r12, lr}
    mov     r2, r8
    bx      lr

beta_sidecar_split_card:
    push    {r0-r3, r12, lr}
    mov     r0, r7
    mov     r1, r4
    mov     r2, r9
    bl      beta_split_card
    pop     {r0-r3, r12, lr}
    mov     r2, r9
    bx      lr

beta_sidecar_join_user:
    push    {r0-r3, r12, lr}
    sub     r0, r5, #0x18
    mov     r1, r4
    bl      beta_join_user
    pop     {r0-r3, r12, lr}
    b       save_copy_in

beta_sidecar_join_card:
    push    {r0-r3, r12, lr}
    bl      beta_join_card
    pop     {r0-r3, r12, lr}
    b       card_sets_in
