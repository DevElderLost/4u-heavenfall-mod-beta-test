@ Single-screen mode: the new game's name boards (layout ui802) shown only on the pages the curated creation_boards
@ names (exefs/single_screen_creation.py).
@
@ The menu owner's command queue (FUN_0022cd40) changes page with `bl FUN_0022cec4(owner, kind)` (0x22CDB4), which for
@ every kind 0 to 0x18 shows the model's name board through FUN_005a27a0 (owner + 0x974 the hunter's, + 0x970 the
@ Felyne's; ui802's other groups are not touched) and nothing ever hides it but the queue's close commands, so the
@ board stays on every page. That call becomes a call here: it makes the page change, and then, for an owner of type 0
@ or 2 (the creation; type 1, the in-town appearance edit, has no ui802) and a kind below 0x19, shows the board of the
@ page's model when the page is one of board_kinds (the patcher's: bit n set = the boards are on page n) and hides
@ both boards otherwise (FUN_00ae53e0(group, 0) unlinks the group from the draw list as the game's own close does).
@ The model of a page: the hunter's for the kinds 0 to 0xE, the Felyne's for 0xF to 0x18. The next page change shows
@ the board again where the game does (kind 0 or 0xF: the main menu).
@
@ Live: r0 the owner, r1 the kind (the caller's `and r1, r0, #0xff`), r2 and r3 as the caller left them (the callee
@ reads them for a few kinds: passed on untouched). After the call the caller reads none of r0-r3 and ip. r4-r6 are
@ pushed (4 words with lr: sp stays 8-aligned).
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ PLAYER_BOARD, 0x974
    .equ OTOMO_BOARD, 0x970
    .equ KINDS, 0x19
    .equ FIRST_OTOMO_KIND, 0xF

_start:
    .global creation_page
creation_page:
    push    {r4-r6, lr}
    mov     r4, r0                    @ the owner
    mov     r5, r1                    @ the kind
    bl      creation_page_body        @ the replaced call
    cmp     r5, #KINDS
    bhs     out                       @ not a page the switch handles
    ldrb    r0, [r4]
    cmp     r0, #0
    cmpne   r0, #2
    bne     out                       @ the in-town edit: no name boards
    ldr     r0, board_kinds
    mov     r0, r0, lsr r5
    and     r6, r0, #1                @ 1: the boards are on this page
    cmp     r5, #FIRST_OTOMO_KIND
    movlo   r5, #0                    @ the page's model: 0 hunter, 1 Felyne
    movhs   r5, #1
    ldr     r0, [r4, #PLAYER_BOARD]
    eor     r1, r5, #1
    and     r1, r1, r6                @ shown: the hunter's page, wanted
    bl      board
    ldr     r0, [r4, #OTOMO_BOARD]
    and     r1, r5, r6                @ shown: the Felyne's page, wanted
    bl      board
out:
    pop     {r4-r6, pc}

@ r0 = a group (or 0), r1 = 1 shown / 0 hidden: FUN_00ae53e0, which returns to our caller
board:
    cmp     r0, #0
    bxeq    lr
    b       gui_group_show

    .global board_kinds
board_kinds:
    .word   0                         @ the patcher's: bit n set shows the boards on page (kind) n
    .ltorg
