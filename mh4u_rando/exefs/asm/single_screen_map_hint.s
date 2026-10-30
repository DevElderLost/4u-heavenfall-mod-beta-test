@ Single-screen mode: the "[X] World Map" hint on the top screen, shown while X would open the World Map and hidden in every
@ other case (exefs/single_screen_map_hint.py).
@
@ The hint is a root group of the lobby's ui430 layout (hud/single_screen_hint.py): the game creates it hidden when the
@ layout loads and no binder names it, so nothing but this block shows or hides it. The pad update's call (0x694CE0) is
@ this block, which first makes the call it replaces (the world map block, which runs the prompt block and takes a
@ press of X), so the state it reads is the one after the press: a press that opened the map this frame hides the hint
@ in the same frame. Then, every frame:
@  1. WANTED (r4) is 1 only when X would open the map, the conditions of the world map block's open (and of the game's
@     own tap on the touch menu's button) one by one, each checked before the next is asked: the game control's byte
@     +0x2B is 2 (the lobby), the lobby scene exists, scene + 0x9788 is 0 (no talk, menu, box or map), the hub machine
@     is set up (+0x172D4 not 0) and idle (+0x172D5 is 2, 0x12 or 0x14: the states FUN_009BBA14 takes a tap in; 0x14 is a
@     multiplayer hall's), the halfword +0x97D6 (the input lock) is 0, FUN_00A40520() is
@     not 0 (the touch menu is up) and FUN_00A09ED4(scene) is 0 (the other buttons are not locked). Both functions only
@     read; the first reads the scene without a null test, hence the order. Anything else is 0: shown nowhere else;
@  2. the group is found afresh every frame, never kept: the GUI manager's list (*(*(gui + 0x100) + 0x154), 0x600
@     pointers) is scanned for the first group whose name hash (group + 0) is hint_hash. A null gui, manager or list,
@     a hash of 0 or no such group: nothing is done. No other group is read past its hash, none is written;
@  3. the group is on the top screen (bits 14-17 of group + 0x44 are *(gui + 0x245)): otherwise it is never shown;
@  4. only when its shown bit (0x400 of group + 0x44) differs from WANTED, FUN_00ae53e0(group, WANTED) shows or hides it
@     (the game's own show / hide: the draw list's link and the bit), as the name boards' block does.
@  5. when it was shown just now (the hidden -> shown edge, once per showing, never every frame) its word is filled in:
@     the game never draws the string a layout file holds in a text pane, it fills every text pane at run time from a
@     message (without it the panel showed without its word). As FUN_00a5985c does for a lobby message: the pane's ref
@     FUN_00c0efa8(gui, &(group
@     hash, 0), &(pane hash, 0)) (0: nothing more is done), the pane shown (FUN_00ae7618), FUN_005a882c(ref, lobby
@     file, message) fills it (the World Map's name is only in the lobby's Lobby_<language>, file 0 of the lobby's path
@     table 0xF007E4; the hint shows only in the lobby, where those files are loaded), the text marked changed (byte 3 at
@     +0x12 of the text's dirty data, or FUN_00ae6bcc(ref a, text data) without one), and the ref goes back to the
@     GUI's pool (count at gui + 0x218 less one, the ref stored there), as the lookup took it. A layout loaded again is
@     a new hidden group, so the next showing fills it again.
@ Its draw order is the game's default for a group no binder names (priority 0x80), in front of the town's top-screen
@ groups (0x11-0x37). The patcher's data: hint_hash (the group's name hash), hint_text_hash (its text pane's),
@ hint_message_file and hint_message_id (the lobby message file and message of the word; hash 0 fills nothing).
@
@ Live at the hook: the hook is `bl`: r0-r3 and ip are dead after it (FUN_00694ccc reloads r0 and r1 at 0x694CE4).
@ r4-r11, ip and lr are pushed (10 words: sp stays 8-aligned; the fill's 16 bytes keep it so); no VFP.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ SLOTS, 0x600
    .equ SHOWN, 0x400
    .equ FREE_HUB, 2                  @ scene + 0x172D5 while the hunter walks freely (offline)
    .equ FREE_HUB_PANEL, 0x12         @ ... with the first button's panel open
    .equ FREE_HUB_LIST, 0x14          @ ... in a multiplayer hall (the member list is open)

_start:
    .global map_hint_pad
map_hint_pad:
    push    {r4-r11, ip, lr}
    bl      world_map_pad             @ the replaced call
    mov     r4, #0                    @ wanted: 0 hidden
    ldr     r0, =game_control
    ldr     r0, [r0]
    cmp     r0, #0
    beq     find
    ldrb    r0, [r0, #0x2B]
    cmp     r0, #2                    @ the lobby
    bne     find
    ldr     r6, =lobby_scene
    ldr     r6, [r6]
    cmp     r6, #0
    beq     find
    add     r0, r6, #0x9700
    ldrb    r1, [r0, #0x88]           @ the interaction mode: 0 free
    cmp     r1, #0
    bne     find
    ldrh    r1, [r0, #0xD6]           @ no input lock
    cmp     r1, #0
    bne     find
    add     r0, r6, #0x17000
    add     r0, r0, #0x200
    ldrb    r1, [r0, #0xD4]           @ the hub machine is set up
    cmp     r1, #0
    beq     find
    ldrb    r1, [r0, #0xD5]           @ ... and idle: 2 offline, 0x12 with the first button's panel, 0x14 in a hall
    cmp     r1, #FREE_HUB
    cmpne   r1, #FREE_HUB_PANEL
    cmpne   r1, #FREE_HUB_LIST
    bne     find
    bl      lobby_town_active         @ the touch menu is up
    cmp     r0, #0
    beq     find
    mov     r0, r6
    bl      lobby_town_busy           @ the touch menu's other buttons are not locked
    cmp     r0, #0
    bne     find
    mov     r4, #1
find:
    ldr     r1, hint_hash
    cmp     r1, #0
    beq     out
    ldr     r5, =gui_control
    ldr     r5, [r5]
    cmp     r5, #0
    beq     out
    ldr     r0, [r5, #0x100]
    cmp     r0, #0
    beq     out
    ldr     r0, [r0, #0x154]
    cmp     r0, #0
    beq     out
    mov     r2, #SLOTS
scan:
    ldr     r3, [r0], #4
    cmp     r3, #0
    beq     next
    ldr     ip, [r3]
    cmp     ip, r1
    beq     found
next:
    subs    r2, r2, #1
    bne     scan
    b       out                       @ no such group
found:
    ldr     r1, [r3, #0x44]
    ldrb    r0, [r5, #0x245]          @ the top screen's value
    and     r0, r0, #0xF
    mov     r2, r1, lsr #14
    and     r2, r2, #0xF
    cmp     r2, r0
    movne   r4, #0                    @ not on the top screen: never shown
    tst     r1, #SHOWN
    movne   r1, #1                    @ the group's state now
    moveq   r1, #0
    cmp     r1, r4
    beq     out                       @ already as wanted
    mov     r0, r3
    mov     r1, r4
    bl      gui_group_show
    cmp     r4, #0
    beq     out                       @ hidden just now: nothing to fill
    ldr     r1, hint_text_hash
    cmp     r1, #0
    beq     out
    sub     sp, sp, #16               @ (group hash, 0), (pane hash, 0)
    ldr     r0, hint_hash
    mov     r2, #0
    str     r0, [sp]
    str     r2, [sp, #4]
    str     r1, [sp, #8]
    str     r2, [sp, #12]
    mov     r0, r5                    @ FUN_00c0efa8(gui, &group, &pane): the text pane's ref, or 0
    mov     r1, sp
    add     r2, sp, #8
    bl      gui_text_ref
    movs    r6, r0
    beq     filled
    ldr     r0, [r6, #4]              @ the pane: shown, as FUN_00a5985c does
    mov     r1, #1
    ldr     r0, [r0, #8]
    bl      text_show
    mov     r0, r6
    ldr     r1, hint_message_file
    ldr     r2, hint_message_id
    bl      text_lobby                @ FUN_005a882c(ref, lobby file, message)
    ldr     r0, [r6, #4]              @ the text marked changed
    ldr     r1, [r0, #0x14]
    ldr     r0, [r6]
    ldr     r2, [r1, #0xC]
    cmp     r2, #0
    movne   r3, #3
    strneb  r3, [r2, #0x12]
    bleq    pane_redraw
    ldr     r0, =gui_control          @ the ref back to the GUI's pool
    ldr     r0, [r0]
    ldr     r1, [r0, #0x218]
    cmp     r1, #0
    beq     filled
    ldr     r2, [r0, #0x21C]
    sub     r1, r1, #1
    str     r1, [r0, #0x218]
    str     r6, [r2, r1, lsl #2]
filled:
    add     sp, sp, #16
out:
    pop     {r4-r11, ip, pc}

    .ltorg
    .global hint_hash
hint_hash:
    .word   0                         @ the patcher's: the name hash of the hint's group
    .global hint_text_hash
hint_text_hash:
    .word   0                         @ the patcher's: the name hash of its text pane
    .global hint_message_file
hint_message_file:
    .word   0                         @ the patcher's: the lobby message file of the word
    .global hint_message_id
hint_message_id:
    .word   0                         @ the patcher's: its message
