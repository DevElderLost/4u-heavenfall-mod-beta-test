@ Single-screen mode: the yes / no boxes and the touch menus' description panel (layout ui006) on the top screen
@ (interface/single_screen/executable/single_screen.py).
@
@ ui006 stays loaded on the bottom screen: its help panel is every touch menu's help too. FUN_00694ccc, the pad update,
@ runs every frame in every scene; its call `bl FUN_005b8284` (0x694CE0) becomes a call here, which makes that call
@ and then, once per frame, decides where ui006's ten groups are (the mode):
@   MODE_PROMPT  a yes / no prompt is open (the owner's button slots 0 and 1 hold the kinds 3 ("Sí") and 6 ("No"),
@                FUN_002921cc): all ten groups on the top screen at (0, 0), the layout's own place;
@   MODE_MENU    a creation menu group is shown (ui800 / ui415 on the top screen: its help text and OK / Back buttons
@   are ui006's) and no group of creation_prompt.unless is
@                (BIT_NO_MENU: the Palico board's base, whose clothes chooser is the rooms' copy of ui415; "The Palico
@                menus"): all ten on the top screen, each at the position menu_shift holds for it (x, y floats, the
@                patcher's);
@   MODE_BOTTOM  a group of the curated help_top.stay_bottom is shown (the NPC talk window, the boot's save list, the
@                the chosen look), or no place of help_top fits: everything on the bottom screen at (0, 0);
@   MODE_HELP    the first place of help_top (help_places: when mask, unless mask, x, y) whose when has a shown group
@                (or is empty) and whose unless has none: only the panel groups (help_mask: help00 and help01) on the
@                top screen at the place's x, y, the buttons, the cross and the rest on the bottom at (0, 0) (a place
@                with NO_PANEL leaves the panel down too, and only its extra groups, e.g. "Mi set"'s key hints, go up).
@ The modes after the first are decided by one scan of the GUI manager's group list (manager = *(gui + 0x100), list =
@ *(manager + 0x154), 0x600 pointers): each shown group (bit 0x400 of group + 0x44) is looked up by its name hash in
@ scan_table (hash, bits; a 0 hash ends it, the patcher's: at most 96 names), the bits of what is shown are or'd, plus
@ flag_mask when the byte layered_preview + 9 (the layered selector's frame is open) is set; the places and the modes
@ are decided from that mask alone.
@ The owner is the static object prompt_owner: +0x00..+0x24 the groups (in the order of the binder table
@ prompt_binder_table, 12-byte entries, name hash first), +0x1F8 + 2 * slot the button kinds, +0x21F set once they are bound. A group is
@ moved only when its hash is its table entry's and its screen differs, the binder's way: bits 14-17 of group + 0x44
@ get the GUI's screen value (*(gui + 0x245) top, *(gui + 0x246) bottom), then FUN_00ae65b0(group) (+0x42 = 3 and the
@ revision bumped). The groups whose bit is set in `stay_mask` (the patcher's, by table index; the curated
@ prompt_stay_bottom) are left alone, neither up nor down.
@
@ Live: r0 the replaced call's argument; after it the caller reads none of r0-r3 and ip (0x694CE4 reloads r0 and r1).
@ r4-r11 and ip are pushed (10 words with lr: sp stays 8-aligned); no VFP.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ GROUPS, 10
    .equ YES, 3
    .equ NO, 6
    .equ SLOTS, 0x600
    .equ MODE_BOTTOM, 0
    .equ MODE_PROMPT, 1
    .equ MODE_MENU, 2
    .equ MODE_HELP, 3
    .equ BIT_MENU, 1                  @ scan_table: a creation menu group
    .equ BIT_STAY, 2                  @ scan_table: a group that keeps the panel on the touch screen
    .equ BIT_NO_MENU, 0x40000000      @ scan_table: a group of creation_prompt.unless (no creation menu while shown)
    .equ NO_PANEL, 0x80000000         @ help_places: bit 31 of a place's unless word: the place leaves the panel down
    .equ PLACE_SIZE, 16
    .equ EXTRA_SIZE, 16

_start:
    .global prompt_screen
prompt_screen:
    push    {r4-r11, ip, lr}
    bl      pad_update_body           @ the replaced call
    ldr     r4, =prompt_owner
    ldrb    r0, [r4, #0x21F]
    cmp     r0, #0
    beq     out
    ldr     r5, =gui_control
    ldr     r5, [r5]
    cmp     r5, #0
    beq     out
    ldrb    r6, [r5, #0x246]          @ the bottom screen
    and     r6, r6, #0xF
    ldrb    r11, [r5, #0x245]         @ the top one
    and     r11, r11, #0xF
    mov     r10, #MODE_PROMPT
    ldrb    r0, [r4, #0x1F8]
    ldrb    r1, [r4, #0x1FA]
    cmp     r0, #YES
    cmpeq   r1, #NO
    beq     chosen
    bl      decide                    @ r10 the mode, r9 the positions of a creation menu or a place
chosen:
    ldr     r7, =prompt_binder_table
    mov     r8, #0
next:
    ldr     r0, stay_mask
    mov     r1, #1
    tst     r0, r1, lsl r8
    bne     skip                      @ masked: left alone, up or down
    ldr     r0, [r4, r8, lsl #2]
    cmp     r0, #0
    beq     skip
    ldr     r1, [r0]
    ldr     r2, [r7]
    cmp     r1, r2
    bne     skip                      @ not this slot's group (any more)
    mov     ip, #0                    @ 1: this group is up
    cmp     r10, #MODE_HELP
    bne     whole
    bl      help_group_pos            @ r2: where the place puts this group, 0: it stays down
    cmp     r2, #0
    movne   ip, #1                    @ the panel groups, and the place's extra groups
    moveq   ip, #0
    b       decided
whole:
    cmp     r10, #MODE_BOTTOM
    movne   ip, #1                    @ a prompt or a creation menu: all of them
decided:
    mov     r3, ip, lsl #1            @ r3: bit 1 up, bit 0 something of the group changed
    cmp     ip, #0
    moveq   r2, r6
    movne   r2, r11
    ldr     r1, [r0, #0x44]
    mov     ip, r1, lsr #14
    and     ip, ip, #0xF
    cmp     ip, r2
    beq     place                     @ already there
    bic     r1, r1, #0x3C000
    orr     r1, r1, r2, lsl #14
    str     r1, [r0, #0x44]
    orr     r3, r3, #1
place:
    mov     r1, #0                    @ the wanted position: (0, 0), or the menu's / the place's
    mov     r2, #0
    tst     r3, #2
    beq     compare
    cmp     r10, #MODE_PROMPT
    beq     compare
    mov     ip, r9
    cmp     r10, #MODE_MENU
    addeq   ip, r9, r8, lsl #3        @ MODE_MENU: this group's entry of menu_shift
    cmp     r10, #MODE_HELP
    bne     position
    bl      help_group_pos            @ MODE_HELP: the place's x, y for the panel, the extra's for another group
    mov     ip, r2
position:
    ldr     r1, [ip]
    ldr     r2, [ip, #4]
compare:
    ldr     ip, [r0, #0x28]
    cmp     ip, r1
    bne     move
    ldr     ip, [r0, #0x2C]
    cmp     ip, r2
    beq     moved
move:
    str     r1, [r0, #0x28]
    str     r2, [r0, #0x2C]
    orr     r3, r3, #1
moved:
    tst     r3, #1
    beq     skip
    bl      gui_group_changed
skip:
    add     r7, r7, #12
    add     r8, r8, #1
    cmp     r8, #GROUPS
    blo     next
out:
    pop     {r4-r11, ip, pc}

@ No yes / no prompt: -> r10 the mode, r9 the position table (menu_shift for MODE_MENU, the place's x, y for MODE_HELP).
@ Scratch: r0-r3, ip, r7, r8; r5 the GUI.
decide:
    mov     r9, #0                    @ the bits of what is shown
    ldr     r0, [r5, #0x100]
    cmp     r0, #0
    beq     flag
    ldr     r0, [r0, #0x154]
    cmp     r0, #0
    beq     flag
    ldr     r8, =scan_table
    mov     r2, #SLOTS
slot:
    ldr     r1, [r0], #4
    cmp     r1, #0
    beq     more
    ldr     r3, [r1, #0x44]
    tst     r3, #0x400
    beq     more                      @ not shown
    ldr     r3, [r1]
    mov     r1, r8
compare_hash:
    ldr     r7, [r1], #4
    ldr     ip, [r1], #4
    cmp     r7, #0
    beq     more                      @ the end of the table: not one of ours
    cmp     r7, r3
    bne     compare_hash
    orr     r9, r9, ip
more:
    subs    r2, r2, #1
    bne     slot
flag:
    ldr     r0, =layered_preview + 9  @ the layered selector's frame is open
    ldrb    r0, [r0]
    cmp     r0, #0
    ldrne   r0, flag_mask
    orrne   r9, r9, r0
    tst     r9, #BIT_MENU
    beq     not_menu
    tst     r9, #BIT_NO_MENU          @ the Palico board's base: its clothes chooser is the creation's ui415
    bne     not_menu
    mov     r10, #MODE_MENU
    ldr     r9, =menu_shift
    bx      lr
not_menu:
    mov     r10, #MODE_BOTTOM
    tst     r9, #BIT_STAY
    bxne    lr
    ldr     r0, help_count
    ldr     r1, =help_places
try_place:
    cmp     r0, #0
    bxeq    lr                        @ no place fits: the touch screen
    ldr     r2, [r1]                  @ its when mask (0: always)
    ldr     r3, [r1, #4]              @ its unless mask
    cmp     r2, #0
    beq     when_ok
    tst     r9, r2
    beq     place_next
when_ok:
    tst     r9, r3
    bne     place_next
    add     r9, r1, #8
    mov     r10, #MODE_HELP
    bx      lr
place_next:
    add     r1, r1, #PLACE_SIZE
    sub     r0, r0, #1
    b       try_place

@ MODE_HELP: where the chosen place puts the group of table index r8 -> r2 the address of its x, y (floats), 0: it stays on
@ the touch screen. The panel groups (help_mask) go to the place's own x, y (r9, the place's record + 8), unless the
@ place says NO_PANEL (bit 31 of its unless word, the record's +4: no scan bit reaches it): then they stay down; another
@ group goes to its entry of extra_table (place index, group index, x, y: the patcher's) for this place, if it has one.
@ Scratch: r1, r2, ip; r3 and the rest are kept.
help_group_pos:
    push    {r3}
    ldr     r2, help_mask
    mov     r1, #1
    tst     r2, r1, lsl r8
    beq     other_group
    ldr     r1, [r9, #-4]             @ the place's unless word
    tst     r1, #NO_PANEL
    movne   r2, #0                    @ a place without the panel: help00 and help01 stay down
    moveq   r2, r9                    @ the panel
    b       pos_out
other_group:
    ldr     r1, =help_places
    sub     r1, r9, r1
    sub     r1, r1, #8
    mov     r1, r1, lsr #4            @ the chosen place's index (its records are PLACE_SIZE = 16 bytes)
    ldr     r2, =extra_table
    ldr     r3, extra_count
extra_try:
    cmp     r3, #0
    moveq   r2, #0                    @ no entry: the group stays down
    beq     pos_out
    ldr     ip, [r2]
    cmp     ip, r1
    ldreq   ip, [r2, #4]
    cmpeq   ip, r8
    addeq   r2, r2, #8                @ its x, y
    beq     pos_out
    add     r2, r2, #EXTRA_SIZE
    sub     r3, r3, #1
    b       extra_try
pos_out:
    pop     {r3}
    bx      lr

    .ltorg
    .global stay_mask
stay_mask:
    .word   0                         @ the patcher's: bit n set leaves table entry n's group on its screen
    .global help_mask
help_mask:
    .word   0                         @ the patcher's: bit n set: table entry n is the description panel (help00, help01)
    .global flag_mask
flag_mask:
    .word   0                         @ the patcher's: the scan bits the layered selector's flag sets
    .global help_count
help_count:
    .word   0                         @ the patcher's: how many places help_places holds
    .global menu_shift
menu_shift:
    .space  80                        @ the patcher's: per ui006 table entry the float x, y of the group in a creation menu
    .global help_places
help_places:
    .space  256                       @ the patcher's: up to 16 places: when mask, unless mask, float x, y (16 bytes each)
    .global extra_count
extra_count:
    .word   0                         @ the patcher's: how many entries extra_table holds
    .global extra_table
extra_table:
    .space  256                       @ the patcher's: up to 16 {place index, ui006 table index, float x, y} (16 bytes each)
    .global scan_table
scan_table:
    .space  776                       @ the patcher's: up to 96 {name hash, bits} and a 0 hash (8 bytes each)
