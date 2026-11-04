@ The START menu's Mod Settings: the hooks into the game's menu code (interface/mod_settings/mod_settings.py; docs/
@ interface/mod_settings.md). The logic is in mod_settings.c; each label stands in for one instruction
@ of the game and keeps what the code around it expects.
@
@ stub_page: FUN_005e8050 fills the page's lines; `strhne r9,[r5,#0xC]` runs on a page past the second, with r5 the menu.
@   Calls mod_menu_page(menu) and leaves the flags at "not equal", as the `beq` after the hook expects. r0-r3 and r12 are
@   not read again before the function loads them.
@
@ stub_action: FUN_00600658 gives the action of the line under the cursor; `mov r0,#0xFF; pop {r4,pc}` runs for a line
@   its table does not hold, with r0 the page and r1 the row. r1-r3 and r12 are kept, which the function leaves alone
@   on this way and its callers may rely on.
@
@ stub_pick: FUN_005f6c8c, an action past its table of actions, `b 0x5F746C` with r0 the action, r4 the menu and r5 = 1,
@   the decide sound. Calls mod_menu_pick(menu) on our action; the sound comes from the game's code in every case.
@
@ stub_desc: FUN_0060fc2c, a line's description, its first instruction `str lr,[sp,#-4]!` with r0 the action. An action
@   past the game's table goes to mod_menu_description; 0xFF (hide the description) and the game's own go on as before.
@
@ stub_frame: FUN_005f6ae4, `bl FUN_00607910` with r0 the menu: the frame of the sub-screen of kind +0xA. Our kind runs
@   mod_menu_frame(menu), with the same return values (0 go on, 2 back to the list); any other kind runs the game's.
@
@ stub_close: FUN_0060d058, `bl FUN_005e86b0`: what every close of the menu runs (FUN_00624ddc), whichever screen it was
@   on. Calls mod_menu_closed() first, then the game's function, which it reaches with the return address of the game's
@   call. r0-r3 and r12 are free at a call; the function reloads what it needs.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global stub_page, stub_action, stub_pick, stub_desc, stub_frame, stub_close

    .equ ACTION, 0x14           @ mod_settings.py ACTION
    .equ KIND, 0x2F             @ mod_settings.py KIND
    .equ HIDE, 0xFF             @ FUN_0060fc2c hides the description

_start:
stub_page:
    push    {r3, lr}
    mov     r0, r5
    bl      mod_menu_page
    movs    r2, #2              @ not equal: the page is neither the first nor the second
    pop     {r3, pc}

stub_action:
    push    {r1, r2, r3, r12}
    bl      mod_line_action
    pop     {r1, r2, r3, r12}
    pop     {r4, pc}

stub_pick:
    cmp     r0, #ACTION
    bne     start_pick_sound
    mov     r0, r4
    bl      mod_menu_pick
    b       start_pick_sound

stub_desc:
    cmp     r0, #HIDE
    beq     1f
    cmp     r0, #ACTION
    bcs     mod_menu_description
1:  str     lr, [sp, #-4]!
    b       start_help_body

stub_frame:
    ldrb    r12, [r0, #0xA]
    cmp     r12, #KIND
    bne     start_subscreen
    b       mod_menu_frame

stub_close:
    push    {r3, lr}
    bl      mod_menu_closed
    pop     {r3, lr}
    b       start_sublist_close
