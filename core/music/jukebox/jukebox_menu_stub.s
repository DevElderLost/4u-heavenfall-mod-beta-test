@ The jukebox menu's hook stubs (music/jukebox/menu_patch.py), a unit of the block
@ jukebox. Each is reached by a `bl` that replaces one instruction of the game and returns to the next one, with the
@ registers the game reads after it as the replaced instruction leaves them. The fifth hook, FUN_00aa8074's call of
@ FUN_00aa771c, calls jukebox_lines directly.
@
@ jukebox_menu_line_stub   FUN_009db3ac at 0x9DB590 (`mov r1, #0xb`), the menu drawn: jukebox_menu_line(fp = the
@                          lobby object), then r1 = 0xB.
@ jukebox_help_stub        FUN_009db608 at 0x9DB66C (`mov r2, #0`), the cursor line's help: r2 =
@                          jukebox_help_message(r4 = the facility's state), 0 for the game's lines.
@ jukebox_pick_menu_stub   FUN_00aa8298 at 0xAA83DC (`ldrb r0, [r1, r0]`), A on a line: r0 = jukebox_menu_pick(the
@                          line's action, r5 = the lobby object), the action itself.
@ jukebox_state_stub       FUN_00aa8298 at 0xAA82AC (`cmp r0, #0xa`), the state switch: jukebox_facility_state(r0 =
@                          the state, r5 = the lobby object) runs state 10, then the compare the switch's `ldrlo pc`
@                          reads.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .syntax unified
    .arch armv6k
    .arm
    .global jukebox_menu_line_stub, jukebox_help_stub, jukebox_pick_menu_stub, jukebox_state_stub

    .section .text.jukebox_menu_line_stub, "ax", %progbits
jukebox_menu_line_stub:
    push    {r0, r1, r2, r3, r12, lr}
    mov     r0, r11
    bl      jukebox_menu_line
    pop     {r0, r1, r2, r3, r12, lr}
    mov     r1, #0xb
    bx      lr

    .section .text.jukebox_help_stub, "ax", %progbits
jukebox_help_stub:
    push    {r0, r1, r3, r4, r12, lr}
    mov     r0, r4
    bl      jukebox_help_message
    mov     r2, r0
    pop     {r0, r1, r3, r4, r12, pc}

    .section .text.jukebox_pick_menu_stub, "ax", %progbits
jukebox_pick_menu_stub:
    push    {r1, r2, r3, r4, r12, lr}
    ldrb    r0, [r1, r0]
    mov     r1, r5
    bl      jukebox_menu_pick
    pop     {r1, r2, r3, r4, r12, pc}

    .section .text.jukebox_state_stub, "ax", %progbits
jukebox_state_stub:
    push    {r1, r2, r3, r4, r12, lr}
    mov     r1, r5
    bl      jukebox_facility_state
    pop     {r1, r2, r3, r4, r12, lr}
    cmp     r0, #0xa
    bx      lr
