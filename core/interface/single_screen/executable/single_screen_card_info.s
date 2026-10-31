@ Single-screen mode: the guild card's groups on the top screen, and its hint
@ (interface/single_screen/executable/single_screen_card_info.py).
@
@ The Tarjeta del gremio is the lobby's ui502, placed and loaded for the top screen by the layout side and the loader
@ (interface/single_screen/executable/single_screen_multiplayer.py), where it covers the only screen the player sees. Y on it is the photo mode's
@ (the game GUI engine: game_gui_engine.c, gui_engine_pad, chained after this block in the pad update's call), so this
@ block never reads a button. The pad update's call (0x694CE0) is this block, which first makes the call it replaces
@ (the Palico menus' frames block, which runs the minimap's, the "[X] Map" hint's, the world map's, the prompt block and
@ the raw pad read), then, every frame:
@  1. the groups are found afresh, never kept: the GUI manager's list (*(*(gui + 0x100) + 0x154), 0x600 pointers) is
@     scanned once, and each hash of card_hashes (the hint, the group that says the card is open, three groups that stop
@     the hint, then up to 16 groups of the card; 0 unused) gets the first group whose name hash (group + 0) is it. A
@     null gui, manager or list: none found;
@  2. ACTIVE (r7) is 1 when the game control's byte +0x2B is 2 (the lobby), the open group (ui502_bg) is found and the
@     game shows it, and none of the stop groups (a window over the card, the card list, the monster page where the game
@     uses Y itself) is shown: the card is up alone, where Y is the photo mode's;
@  3. the card's groups go to the top screen (*(gui + 0x245)): bits 14-17 of group + 0x44, then FUN_00ae65b0(group), only
@     for a group whose screen differs. What the game shows or hides of them follows on the screen they are on; a bind
@     that puts them elsewhere (the card's touch screen) is undone the next frame;
@  4. the hint group (on the top screen, hidden there otherwise) is shown while ACTIVE and hidden in every other case,
@     with FUN_00ae53e0 only when its shown bit differs; when it was shown just now its word is filled in exactly as the
@     minimap's block does (single_screen_minimap.s step 5): the lobby message file's FUN_005a882c.
@ The patcher's data: card_hashes, card_text_hash (the hint's text pane; 0 fills nothing), card_message_file and
@ card_message_id.
@
@ Live at the pad update's hook: the hook is `bl`: r0-r3 and ip are dead after it. r4-r11, ip and lr are pushed (10
@ words) and 112 bytes of stack taken: sp stays 8-aligned; no VFP.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ SLOTS, 0x600
    .equ SHOWN, 0x400
    .equ SCREEN_BITS, 0x3C000         @ bits 14-17 of group + 0x44: the screen the group is drawn on
    .equ HINT, 0                      @ sp + the hashes' offsets: the hint,
    .equ WHEN, 4                      @ the group that says the card is open,
    .equ UNLESS, 8                    @ three groups that stop the hint,
    .equ GROUPS, 20                   @ up to 16 groups of the card
    .equ ROOM, 84                     @ the hashes, in bytes
    .equ KEYS, 84                     @ sp + KEYS: (hint hash, 0), (pane hash, 0) for the text's ref
    .equ FRAME, 112

_start:
    .global card_info_pad
card_info_pad:
    push    {r4-r11, ip, lr}
    bl      frames_pad                @ the replaced call
    sub     sp, sp, #FRAME
    mov     r0, #0
    mov     r1, #0
wipe:
    str     r0, [sp, r1]
    add     r1, r1, #4
    cmp     r1, #ROOM
    bne     wipe
    ldr     r5, =gui_control          @ 1. the groups
    ldr     r5, [r5]
    cmp     r5, #0
    beq     scanned
    ldr     r0, [r5, #0x100]
    cmp     r0, #0
    beq     scanned
    ldr     r0, [r0, #0x154]
    cmp     r0, #0
    beq     scanned
    ldr     r6, =card_hashes
    mov     r2, #SLOTS
scan:
    ldr     r3, [r0], #4
    cmp     r3, #0
    beq     next
    ldr     ip, [r3]
    cmp     ip, #0
    beq     next                      @ a group without a name matches no unused hash
    mov     r1, #0
match:
    ldr     lr, [r6, r1]
    cmp     lr, ip
    bne     other
    ldr     lr, [sp, r1]
    cmp     lr, #0
    streq   r3, [sp, r1]              @ the first group of the name
other:
    add     r1, r1, #4
    cmp     r1, #ROOM
    bne     match
next:
    subs    r2, r2, #1
    bne     scan
scanned:
    mov     r7, #0                    @ 2. ACTIVE
    ldr     r0, =game_control
    ldr     r0, [r0]
    cmp     r0, #0
    beq     moves
    ldrb    r0, [r0, #0x2B]
    cmp     r0, #2                    @ the lobby
    bne     moves
    ldr     r0, [sp, #WHEN]           @ the card
    cmp     r0, #0
    beq     moves
    ldr     r0, [r0, #0x44]
    tst     r0, #SHOWN                @ the game shows the card
    beq     moves
    mov     r7, #1
    mov     r1, #UNLESS
stops:
    ldr     r0, [sp, r1]
    cmp     r0, #0
    ldrne   r0, [r0, #0x44]
    tstne   r0, #SHOWN
    movne   r7, #0                    @ a window, the list or the monster page is up
    add     r1, r1, #4
    cmp     r1, #GROUPS
    bne     stops
moves:
    mov     r6, #GROUPS               @ 3. the card's groups, on the top screen
follow:
    ldr     r0, [sp, r6]
    cmp     r0, #0
    beq     followed
    ldrb    r2, [r5, #0x245]          @ the top screen's value
    and     r2, r2, #0xF
    ldr     r1, [r0, #0x44]
    mov     r3, r1, lsr #14
    and     r3, r3, #0xF
    cmp     r3, r2
    beq     followed
    bic     r1, r1, #SCREEN_BITS
    orr     r1, r1, r2, lsl #14
    str     r1, [r0, #0x44]
    bl      gui_group_changed
followed:
    add     r6, r6, #4
    cmp     r6, #ROOM
    bne     follow
    ldr     r3, [sp, #HINT]           @ 4. the hint
    cmp     r3, #0
    beq     out
    ldr     r1, [r3, #0x44]
    ldrb    r0, [r5, #0x245]
    and     r0, r0, #0xF
    mov     r2, r1, lsr #14
    and     r2, r2, #0xF
    cmp     r2, r0
    movne   r7, #0                    @ not on the top screen: never shown
    tst     r1, #SHOWN
    movne   r1, #1
    moveq   r1, #0
    cmp     r1, r7
    beq     out                       @ already as wanted
    mov     r0, r3
    mov     r1, r7
    bl      gui_group_show
    cmp     r7, #0
    beq     out                       @ hidden just now: nothing to fill
    ldr     r1, card_text_hash
    cmp     r1, #0
    beq     out
    ldr     r0, =card_hashes
    ldr     r0, [r0, #HINT]           @ the hint's hash
    mov     r2, #0
    str     r0, [sp, #KEYS]
    str     r2, [sp, #KEYS + 4]
    str     r1, [sp, #KEYS + 8]
    str     r2, [sp, #KEYS + 12]
    mov     r0, r5                    @ FUN_00c0efa8(gui, &group, &pane): the text pane's ref, or 0
    add     r1, sp, #KEYS
    add     r2, sp, #KEYS + 8
    bl      gui_text_ref
    movs    r6, r0
    beq     out
    ldr     r0, [r6, #4]              @ the pane: shown, as FUN_00a5985c does
    mov     r1, #1
    ldr     r0, [r0, #8]
    bl      text_show
    mov     r0, r6
    ldr     r1, card_message_file
    ldr     r2, card_message_id
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
    beq     out
    ldr     r2, [r0, #0x21C]
    sub     r1, r1, #1
    str     r1, [r0, #0x218]
    str     r6, [r2, r1, lsl #2]
out:
    add     sp, sp, #FRAME
    pop     {r4-r11, ip, pc}

    .ltorg
    .global card_hashes
card_hashes:
    .space  ROOM                      @ the patcher's: the name hashes of the hint, the open group, the stops, the groups
    .global card_text_hash
card_text_hash:
    .word   0                         @ the patcher's: the name hash of the hint's text pane
    .global card_message_file
card_message_file:
    .word   0                         @ the patcher's: the lobby message file of the word
    .global card_message_id
card_message_id:
    .word   0                         @ the patcher's: its message
