@ Single-screen mode: the World Map (layout ui430, on the top screen) opened and driven with the pad
@ (interface/single_screen/executable/single_screen_world_map.py).
@
@ The pad update FUN_00694ccc runs every frame in every scene; its call `bl FUN_005b8284` (0x694CE0, the raw pad read)
@ is a call to prompt_screen (single_screen_prompt.s), which makes it and places ui006. That call becomes a call here:
@ this block runs prompt_screen, then, still before FUN_00694ccc derives the game and GUI words from the raw ones, reads
@ the raw words the read has just written (pad + 0x8C held, +0x90 the previous frame's held word as the last frame left
@ it, +0x94 pressed, +0x98 released, +0x9C changed, +0xA0 repeat) and, in the lobby (the game control's byte +0x2B is 2):
@  * OPEN: a fresh press of the open button (X) while the player walks freely in the hub does what a tap on the touch
@    menu's World Map button does (FUN_009F5388, 0x9F5AF8): the hub state machine's previous state (scene + 0x172D6)
@    gets its state (scene + 0x172D5: 2, or 0x12 / 0x14, see below) and the state becomes 0xF, with the button's click; the
@    game opens the map on the next frame (FUN_009BBA14, case 0xF, FUN_009DE410: its own busy test FUN_00A09ED4
@    included). "Walks freely" is what the game tests before it takes a tap: the interaction mode scene + 0x9788 is 0,
@    the hub machine is set up (+0x172D4 not 0) and idle (+0x172D5 is 2; or 0x12, the first button's panel; or 0x14, a
@    multiplayer hall's idle state with the member list open: FUN_009BBA14 runs the tap handler FUN_009F5388 in these
@    three and no other), no input lock (halfword +0x97D6 is 0), FUN_00A40520() (the touch menu
@    is up) is not 0 and FUN_00A09ED4(scene) (the buttons other than the first are locked) is 0;
@  * CLOSE: while the map is open (scene + 0x9788 is 0x17) a fresh press of the close button (X) is a press of B for
@    that one frame (raw 0x4000 in the held and pressed words): the map's own B closes it, or backs out of a window;
@  * ONLINE: a fresh press of the online button (Y) in the map's place choice (scene + 0x12034 is 2, +0x12035 is 1, no
@    cursor animation running: +0x1204B is 0) opens the Solo / Local Play / Online window, as the game does for a
@    place of its own id 10 (FUN_00A47E98): the map's state (+0x12034) becomes 5 and its sub state 0. B in the window
@    goes back to the choice, the cursor and place unchanged;
@  * CIRCLE PAD: while the map is open (and `circle_on` is set) the circle pad's raw bits (0x10000 up, 0x20000 right,
@    0x40000 down, 0x80000 left) are also the D-pad's (0x10, 0x20, 0x40, 0x80), which the map reads; the game itself
@    ignores the circle pad there.
@ A button the block used is hidden from the game until it is released: its bit is cleared in the held, pressed,
@ released, changed and repeat words (never +0xA4..+0xB0, the circle pad's axes). FUN_005b8460 computes the pressed
@ word as held & ~old held, the old held word being what this block left in +0x8C, so a hidden button held down would
@ read as pressed again at the next frame: the block therefore marks a hidden button by an unused bit of the held word
@ (MARK_X 0x2000000, MARK_Y 0x4000000: FUN_005b8460 never sets them) and finds the mark in +0x90 the next frame, where
@ the button's pressed bit is not a fresh press. The marks are cleared from the other words every frame. The
@ buttons the block does not use (and every button outside the lobby, or with a null pointer) are left alone.
@ The patcher's data: open_mask, close_mask, online_mask (a raw button bit, X 0x1000 or Y 0x8000) and circle_on.
@
@ Live at the hook: the hook is `bl`: r0-r3 and ip are dead after it (FUN_00694ccc reloads r0 and r1 at 0x694CE4, as
@ for prompt_screen). r4-r11, ip and lr are pushed (10 words: sp stays 8-aligned); no VFP.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ BTN_X, 0x1000                @ the game's raw button bits (pad + 0x8C)
    .equ BTN_Y, 0x8000
    .equ BTN_B, 0x4000
    .equ MARK_X, 0x2000000            @ unused bits of the held word: "this button was hidden last frame"
    .equ MARK_Y, 0x4000000
    .equ MARKS, 0x6000000
    .equ MAP, 0x17                    @ scene + 0x9788 while the world map is open
    .equ CLICK, 0x8D                  @ the touch button's sound
    .equ FREE_HUB, 2                  @ scene + 0x172D5 while the hunter walks freely (offline)
    .equ FREE_HUB_PANEL, 0x12         @ ... with the first button's panel open
    .equ FREE_HUB_LIST, 0x14          @ ... in a multiplayer hall (the member list is open)

_start:
    .global world_map_pad
world_map_pad:
    push    {r4-r11, ip, lr}
    bl      prompt_screen             @ the replaced call: the raw pad read, and ui006
    ldr     r4, =pad_control
    ldr     r4, [r4]
    cmp     r4, #0
    beq     out
    ldr     r0, =game_control
    ldr     r0, [r0]
    cmp     r0, #0
    beq     out
    ldrb    r0, [r0, #0x2B]
    cmp     r0, #2                    @ the lobby
    bne     out
    ldr     r6, =lobby_scene
    ldr     r6, [r6]
    cmp     r6, #0
    beq     out
    ldr     r7, [r4, #0x8C]           @ held
    ldr     r8, [r4, #0x90]           @ the held word of the last frame, as this block left it
    ldr     r9, [r4, #0x94]           @ pressed
    mov     r10, #0                   @ the buttons to hide
    mov     r11, #0                   @ their marks
    mov     r0, #BTN_X
    mov     r1, #MARK_X
    bl      one_button
    mov     r0, #BTN_Y
    mov     r1, #MARK_Y
    bl      one_button
    add     r0, r6, #0x9700
    ldrb    r0, [r0, #0x88]
    cmp     r0, #MAP
    bne     store
    ldr     r0, circle_on
    cmp     r0, #0
    beq     store
    and     r0, r7, #0xF0000          @ the circle pad's four directions are the D-pad's
    orr     r7, r7, r0, lsr #12
    and     r0, r9, #0xF0000
    orr     r9, r9, r0, lsr #12
store:
    bic     r7, r7, r10
    orr     r7, r7, r11
    bic     r9, r9, r10
    bic     r9, r9, #MARKS
    str     r7, [r4, #0x8C]
    str     r9, [r4, #0x94]
    mov     r5, #0x98                 @ released, changed, repeat
more:
    ldr     r0, [r4, r5]
    bic     r0, r0, r10
    bic     r0, r0, #MARKS
    str     r0, [r4, r5]
    add     r5, r5, #4
    cmp     r5, #0xA4
    bne     more
out:
    pop     {r4-r11, ip, pc}

@ One button: r0 its raw bit, r1 its mark; r4 the pad, r6 the scene, r7 held, r8 the old held word, r9 pressed; adds to
@ r10 (hide) and r11 (marks), and to r7 / r9 (a B for a frame). Scratch r2, r3.
one_button:
    push    {r2, lr}
    tst     r7, r0
    beq     done                      @ not held: nothing to hide
    tst     r8, r1
    bne     hide                      @ hidden last frame and still held: not a fresh press
    tst     r9, r0
    beq     held_only
    add     r2, r6, #0x9700
    ldrb    r2, [r2, #0x88]           @ the interaction mode
    cmp     r2, #MAP
    bne     not_map
    ldr     r3, close_mask
    tst     r3, r0
    beq     try_online
    orr     r7, r7, #BTN_B            @ the map is open: a B for this frame
    orr     r9, r9, #BTN_B
    b       hide
try_online:
    ldr     r3, online_mask
    tst     r3, r0
    beq     done
    add     r3, r6, #0x12000
    ldrb    r2, [r3, #0x34]           @ the map's state: choosing a place
    cmp     r2, #2
    ldreqb  r2, [r3, #0x35]
    cmpeq   r2, #1
    ldreqb  r2, [r3, #0x4B]           @ no confirm animation running
    cmpeq   r2, #0
    bne     done
    add     r2, r6, #0x9700
    ldrh    r2, [r2, #0xD6]           @ the input lock
    cmp     r2, #0
    bne     done
    mov     r2, #0
    strb    r2, [r3, #0x35]
    mov     r2, #5
    strb    r2, [r3, #0x34]           @ the Solo / Local Play / Online window
    b       hide
not_map:
    cmp     r2, #0
    bne     done
    ldr     r3, open_mask
    tst     r3, r0
    beq     done
    add     r2, r6, #0x17000
    add     r2, r2, #0x200
    ldrb    r3, [r2, #0xD4]           @ the hub machine is set up
    cmp     r3, #0
    beq     done
    ldrb    r3, [r2, #0xD5]           @ ... and idle: 2 offline, 0x12 with the first button's panel, 0x14 in a hall
    cmp     r3, #FREE_HUB
    cmpne   r3, #FREE_HUB_PANEL
    cmpne   r3, #FREE_HUB_LIST
    bne     done
    add     r3, r6, #0x9700
    ldrh    r3, [r3, #0xD6]           @ no input lock
    cmp     r3, #0
    bne     done
    push    {r0, r1}                  @ the game's calls clobber r0-r3 and ip
    bl      lobby_town_active
    cmp     r0, #0
    beq     refuse
    mov     r0, r6
    bl      lobby_town_busy
    cmp     r0, #0
    bne     refuse
    add     r2, r6, #0x17000
    add     r2, r2, #0x200
    ldrb    r3, [r2, #0xD5]
    strb    r3, [r2, #0xD6]           @ the state to go back to
    mov     r3, #0xF
    strb    r3, [r2, #0xD5]           @ the world map request
    ldr     r0, =sound_control
    ldr     r0, [r0]
    cmp     r0, #0
    movne   r1, #CLICK
    blne    lobby_click
    pop     {r0, r1}
    b       hide
refuse:
    pop     {r0, r1}
    b       done
held_only:
    add     r2, r6, #0x9700
    ldrb    r2, [r2, #0x88]
    cmp     r2, #MAP
    bne     done
    ldr     r3, close_mask
    tst     r3, r0
    beq     done                      @ the map is open: its close button stays hidden while held
hide:
    orr     r10, r10, r0
    orr     r11, r11, r1
done:
    pop     {r2, pc}

    .ltorg
    .global open_mask
open_mask:
    .word   0                         @ the patcher's: the raw bit of the open button
    .global close_mask
close_mask:
    .word   0                         @ ... of the close button
    .global online_mask
online_mask:
    .word   0                         @ ... of the online button
    .global circle_on
circle_on:
    .word   0                         @ the patcher's: 1 when the circle pad is also the D-pad while the map is open
