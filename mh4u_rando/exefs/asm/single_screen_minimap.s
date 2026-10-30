@ Single-screen mode: the town minimap on the top screen, turned on and off with a button, and its hint
@ (exefs/single_screen_minimap.py).
@
@ The town's map is the lobby's ui422, loaded on the touch screen (its binder FUN_0059deac puts its five groups there at
@ every bind) and placed by the layout side for the top screen (hud/single_screen.py, curated "ui422"). The pad update's
@ call (0x694CE0) is this block, which first makes the call it replaces (the "[X] Map" hint's block, which runs the world
@ map block, the prompt block and the raw pad read), then, every frame:
@  1. the groups are found afresh, never kept: the GUI manager's list (*(*(gui + 0x100) + 0x154), 0x600 pointers) is
@     scanned once, and each hash of minimap_hashes (the state group, the hint, then up to 8 groups that follow the
@     state; 0 unused) gets the first group whose name hash (group + 0) is it. A null gui, manager or list: none found;
@  2. ACTIVE (r7) is 1 only when the button may turn the minimap: the game control's byte +0x2B is 2 (the lobby), the
@     lobby scene exists, scene + 0x9788 is 0 (no talk, menu, box or map), the halfword +0x97D6 (the input lock) is
@     0, the hub machine is set up (+0x172D4 not 0) and idle (+0x172D5 is 2), the state group and the first following
@     group (the map, ui422_map) are found and the game shows the map (its shown bit, 0x400 of group + 0x44: shown
@     while the hunter walks or talks, hidden in a facility, the Canteen, the world map). In a Gathering Hall the hub
@     stays in 0x14 (the member list open; 0x12 offline after the first touch button), where the game hides the map:
@     there the state group and the map found are enough (minimap_hall shows it, step 4). TALK (r11) is 1 when, on the
@     same way (the lobby, the scene), scene + 0x9788 is 7 (an NPC's talk) or 8 (its follow-up);
@  3. the button (minimap_button, a raw bit: L 0x100, the 3DS's L as FUN_005b8460 gives it, as it gives X 0x1000, the
@     world map's): a fresh press (in the pressed word +0x94, and no MARK in +0x90, the held word the blocks left last
@     frame) while ACTIVE flips the state group's shown bit with FUN_00ae53e0 (the state lives there: the game creates
@     the group hidden with the layout, so the minimap is off when the lobby's layouts load, and never touches it). A
@     button the block used is hidden from the game until it is released: its bit is cleared in the held, pressed,
@     released, changed and repeat words and MARK (0x8000000, which FUN_005b8460 never sets: its bits are the buttons,
@     0x100000-0x800000 the C-stick, 0x1000000 a touch and the circle pad's) is set in the held word, so the next
@     frame's pressed bit (held & ~old, old without the bit) is known not to be fresh; MARK is cleared from the other
@     words every frame. L is the camera's reset in the hubs: the press that turns the minimap never reaches the
@     camera;
@  4. every following group goes to the top screen (*(gui + 0x245)) while the state group is shown and no talk is on
@     (TALK 0), and to the touch screen (*(gui + 0x246)) otherwise (the state hidden or not there, or a talk: the talk
@     window ui005_kaiwa00 would cover the map; the state group is not touched, so the map comes back when the talk
@     ends if it was on). First, when the state group is found, minimap_hall(on) (single_screen_minimap_hall.c) shows
@     or hides the map with the game's own functions in the hall's hub states (nothing in the others). Then
@     bits 14-17 of group + 0x44, then FUN_00ae65b0(group), only for a group whose screen differs
@     (as the prompt block moves ui006). What the game shows or hides of them follows on the screen they are on; a
@     bind that puts them back on the touch screen is undone the next frame. The last one is the town's place name
@     (ui421_midasi_mura, minimap.label): the frames block's label unit (single_screen_label.c) scales and moves its
@     frame null while it is on the top screen;
@  5. the hint group (on the top screen, hidden there otherwise) is shown while ACTIVE and hidden in every other case,
@     with FUN_00ae53e0 only when its shown bit differs; when it was shown just now its word is filled in, as the X
@     hint's block does but with the lobby message file's function FUN_005a882c(ref, lobby file, message) (as
@     FUN_00a5985c does): the pane's ref FUN_00c0efa8(gui, &(hint hash, 0), &(pane hash, 0)) (0: nothing more), the
@     pane shown (FUN_00ae7618), the fill, the text marked changed (byte 3 at +0x12 of the text's dirty data, or
@     FUN_00ae6bcc(ref a, text data) without one), and the ref back to the GUI's pool (gui + 0x218 less one, the ref
@     stored at gui + 0x21C's array).
@ The patcher's data: minimap_hashes, minimap_button, minimap_text_hash (the hint's text pane; 0 fills nothing),
@ minimap_message_file and minimap_message_id.
@
@ Live at the pad update's hook: the hook is `bl`: r0-r3 and ip are dead after it (FUN_00694ccc reloads r0 and r1 at
@ 0x694CE4). r4-r11, ip and lr are pushed (10 words) and 56 bytes of stack taken: sp stays 8-aligned; no VFP.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ SLOTS, 0x600
    .equ SHOWN, 0x400
    .equ SCREEN_BITS, 0x3C000         @ bits 14-17 of group + 0x44: the screen the group is drawn on
    .equ FREE_HUB, 2                  @ scene + 0x172D5 while the hunter walks freely
    .equ MENU_HUB, 0x12               @ ... the town's first touch button, offline (the game hid the map)
    .equ LIST_HUB, 0x14               @ ... a Gathering Hall's member list, online (the game hid the map)
    .equ TALK_MODE, 7                 @ scene + 0x9788 in an NPC's talk (FUN_009ec18c writes it, 0x9EC694)
    .equ TALK_NEXT, 8                 @ ... in the talk's follow-up (the talk dispatcher's exit, 0x9EC144)
    .equ MARK, 0x8000000              @ an unused bit of the held word: "the button was hidden last frame"
    .equ ROOM, 40                     @ the hashes: the state group, the hint, 8 following groups (bytes)
    .equ FOUND, 0                     @ sp + FOUND: the group of each hash, 0 none (ROOM bytes)
    .equ KEYS, 40                     @ sp + KEYS: (hint hash, 0), (pane hash, 0) for the text's ref
    .equ FRAME, 56

_start:
    .global minimap_pad
minimap_pad:
    push    {r4-r11, ip, lr}
    bl      map_hint_pad              @ the replaced call
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
    ldr     r6, =minimap_hashes
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
    mov     r11, #0                   @ TALK
    ldr     r0, =game_control
    ldr     r0, [r0]
    cmp     r0, #0
    beq     active
    ldrb    r0, [r0, #0x2B]
    cmp     r0, #2                    @ the lobby
    bne     active
    ldr     r6, =lobby_scene
    ldr     r6, [r6]
    cmp     r6, #0
    beq     active
    add     r0, r6, #0x9700
    ldrb    r1, [r0, #0x88]           @ the interaction mode: 0 free
    cmp     r1, #TALK_MODE
    cmpne   r1, #TALK_NEXT
    moveq   r11, #1                   @ an NPC's talk or its follow-up
    cmp     r1, #0
    bne     active
    ldrh    r1, [r0, #0xD6]           @ no input lock
    cmp     r1, #0
    bne     active
    add     r0, r6, #0x17000
    add     r0, r0, #0x200
    ldrb    r1, [r0, #0xD4]           @ the hub machine is set up
    cmp     r1, #0
    beq     active
    ldrb    r1, [r0, #0xD5]           @ ... and idle
    cmp     r1, #FREE_HUB
    beq     free
    cmp     r1, #LIST_HUB             @ a hall's states, where the game hides the map ...
    cmpne   r1, #MENU_HUB
    bne     active
    ldr     r0, [sp, #FOUND]          @ ... with the state group and the map: shown or not, minimap_hall turns it
    cmp     r0, #0
    ldrne   r0, [sp, #FOUND + 8]
    cmpne   r0, #0
    movne   r7, #1
    b       active
free:
    ldr     r0, [sp, #FOUND]          @ the state group ...
    cmp     r0, #0
    ldrne   r0, [sp, #FOUND + 8]      @ ... and the map
    cmpne   r0, #0
    beq     active
    ldr     r0, [r0, #0x44]
    tst     r0, #SHOWN                @ the game shows the map
    movne   r7, #1
active:
    ldr     r4, =pad_control          @ 3. the button
    ldr     r4, [r4]
    cmp     r4, #0
    beq     state
    ldr     r8, minimap_button
    ldr     r9, [r4, #0x8C]           @ held
    mov     r10, #0                   @ the bits hidden from the game this frame
    tst     r9, r8
    beq     words                     @ not held
    ldr     r0, [r4, #0x90]
    tst     r0, #MARK
    movne   r10, r8                   @ used and still held
    bne     words
    ldr     r0, [r4, #0x94]
    tst     r0, r8
    beq     words                     @ held, not a fresh press
    cmp     r7, #0
    beq     words                     @ not now: the game's
    ldr     r0, [sp, #FOUND]
    ldr     r1, [r0, #0x44]
    tst     r1, #SHOWN
    moveq   r1, #1
    movne   r1, #0
    bl      gui_group_show            @ the state flips
    mov     r10, r8
words:
    bic     r9, r9, r10
    cmp     r10, #0
    orrne   r9, r9, #MARK
    str     r9, [r4, #0x8C]
    mov     r1, #0x94                 @ pressed, released, changed, repeat
clean:
    ldr     r0, [r4, r1]
    bic     r0, r0, r10
    bic     r0, r0, #MARK
    str     r0, [r4, r1]
    add     r1, r1, #4
    cmp     r1, #0xA4
    bne     clean
state:
    mov     r8, #0                    @ 4. the following groups: on the top screen while the state is on ...
    ldr     r0, [sp, #FOUND]
    cmp     r0, #0
    ldrne   r0, [r0, #0x44]
    andne   r8, r0, #SHOWN
    cmp     r11, #0
    movne   r8, #0                    @ ... and no talk is on (the state is left as it is)
    ldr     r0, [sp, #FOUND]          @ in a hall's states the map shown or hidden as wanted (the state group found)
    cmp     r0, #0
    beq     hall
    mov     r0, r8
    bl      minimap_hall
hall:
    mov     r6, #FOUND + 8
follow:
    ldr     r0, [sp, r6]
    cmp     r0, #0
    beq     followed
    cmp     r8, #0
    ldrneb  r2, [r5, #0x245]          @ the top screen's value
    ldreqb  r2, [r5, #0x246]          @ the touch screen's
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
    ldr     r3, [sp, #FOUND + 4]      @ 5. the hint
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
    ldr     r1, minimap_text_hash
    cmp     r1, #0
    beq     out
    ldr     r0, =minimap_hashes
    ldr     r0, [r0, #4]              @ the hint's hash
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
    ldr     r1, minimap_message_file
    ldr     r2, minimap_message_id
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
    .global minimap_hashes
minimap_hashes:
    .space  ROOM                      @ the patcher's: the name hashes of the state group, the hint, the groups
    .global minimap_button
minimap_button:
    .word   0                         @ the patcher's: the button's raw bit
    .global minimap_text_hash
minimap_text_hash:
    .word   0                         @ the patcher's: the name hash of the hint's text pane
    .global minimap_message_file
minimap_message_file:
    .word   0                         @ the patcher's: the lobby message file of the word
    .global minimap_message_id
minimap_message_id:
    .word   0                         @ the patcher's: its message
