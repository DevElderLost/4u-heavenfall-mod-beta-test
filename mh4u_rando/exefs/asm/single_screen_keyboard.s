@ Single-screen mode: the name keyboard (the game's embedded 3DS software keyboard) driven with the pad, as a virtual
@ finger on its touch input (exefs/single_screen_keyboard.py).
@
@ FUN_0066762c(manager) is the keyboard's input manager, run every frame by the keyboard's update. It reads the touch
@ point from the game's pad object (halfwords +0xB6 x, +0xB8 y; both non-zero = touching), the three raw button words
@ (held +0x8C, pressed +0x94, released +0x98) and converts them for the keys. The read of x at 0x667668
@ (`ldrh r4, [r0, #0xB6]`) becomes a branch here, which makes that read and then, while the keyboard runs and no real
@ finger is on the screen:
@  * keeps the finger on a key, the "hover" (the variable keyboard_finger): the control (key, tab or button) in the key
@    manager's list (keyboard + 0x508, nodes at control + 4); one that is gone (the keyboard was closed and opened
@    again) or not set is replaced by the eligible control nearest to the curated start point;
@  * moves it to the neighbouring control on a D-pad or circle pad press (the nearest one in that direction, the
@    distance across counted twice) and shows it with the look of a touch, by the control's class (its update, vtable
@    slot 0x18): the keys, buttons and text area (FUN_0067977c(control, 0) and the pressed colours, the sequence of a
@    key's touch-down without its callback), the mode tabs (one colour pane tinted with the curated colour, restored
@    to what their state wears), the arrows and suggestion words (their press animation); the released look on the
@    one it leaves;
@  * while A is held, puts a touch in the middle of the hovered control (a fresh touch-down types a key; held, a key
@    that repeats does); B does the same on the control of the curated name `delete`, START on `ok`;
@  * takes the D-pad, circle pad, A, B and START out of the button words the manager converts: the keyboard moves its
@    text cursor with the D-pad, and a button the finger uses must not do something else too.
@ A control is eligible when its enabled byte (+0x18) is set, its state (+0x14) is below 5 (5 is the greyed look), its
@ name is not one of the curated skipped, its layout draws a group that is shown on the top screen (the draw list at
@ layout + 0x120, linked by +0x48; flag 0x400 and screen 0 in bits 14-17 of group + 0x44; the group at layout + 0x30
@ says nothing) and its first hit rectangle lies on the screen. The rectangle is found as FUN_00667cf8 does: the entry named control +
@ 0x20 in the list at layout + 0x2A0 (layout = control + 0x54), whose first element's rectangle (+0x20 x0, +0x24 y0,
@ +0x28 x1, +0x2C y1) is tested against (160 - x + layout x, 120 - y + layout y); the touch for its middle is
@ x = 160 + layout x - (x0 + x1) / 2, y likewise. Doubled screen coordinates are used (the rectangles end on halves).
@
@ Live at the hook: r0 the pad object (dead after), r2 = manager + 8 and r3 the manager (kept), r5 y, r6-r8 the button
@ words, s0 / s1 (stored right after). The function saved r4-r8 and lr itself. d0-d7 are saved here (the game's own
@ calls below clobber them); r2, r3, r9-r11 and lr are pushed. The curated name / start data is the patcher's.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfpv2
    .arm
    .global _start

    .equ RUNNING, 1                   @ keyboard + 0x520
    .equ HELD_A, 0x2000               @ the game's raw button bits
    .equ HELD_B, 0x4000
    .equ HELD_START, 0x8
    .equ SHOWN, 0x400                 @ a layout's drawn group flag (group + 0x44): shown
    .equ SCREEN_SHIFT, 14             @ ... and bits 14-17 its screen (0 the top one)

_start:
    .global keyboard_finger_hook
keyboard_finger_hook:
    ldrh    r4, [r0, #0xB6]           @ the replaced instruction (x of the touch)
    push    {r2, r3, r9-r11, lr}
    vpush   {d0-d7}
    ldr     r9, =keyboard_pointer
    ldr     r9, [r9]
    cmp     r9, #0
    beq     done
    ldr     r0, [r9, #0x520]
    cmp     r0, #RUNNING
    bne     done
    cmp     r4, #0                    @ a real finger (x and y both non-zero) passes through untouched
    cmpne   r5, #0
    bne     done
    ldr     r10, [r9, #0x508]
    cmp     r10, #0
    beq     done
    ldr     r11, =keyboard_finger
    ldr     r0, [r11]
    bl      in_list
    cmp     r0, #0
    bne     have
    bl      pick_start                @ no hover, or a stale one: the nearest control to the start
    str     r0, [r11]
    mov     r1, #0
    str     r1, [r11, #4]
    cmp     r0, #0
    beq     mask
have:
    @ a direction pressed this frame (the circle pad's bits, 12 higher, shifted onto the D-pad's)
    orr     r0, r7, r7, lsr #12
    mov     r3, #0
    tst     r0, #0x80                 @ left
    movne   r3, #4
    tst     r0, #0x40                 @ down
    movne   r3, #3
    tst     r0, #0x20                 @ right
    movne   r3, #2
    tst     r0, #0x10                 @ up
    movne   r3, #1
    cmp     r3, #0
    beq     buttons
    ldr     r0, [r11]
    mov     r1, r3
    bl      pick_next
    cmp     r0, #0
    beq     buttons
    mov     r9, r0                    @ the new hover
    ldr     r0, [r11, #4]
    cmp     r0, #0
    ldrne   r0, [r11]
    movne   r1, #1
    blne    set_look                  @ the released look on the control it leaves
    str     r9, [r11]
    mov     r0, #0
    str     r0, [r11, #4]
buttons:
    tst     r6, #HELD_A
    ldrne   r0, [r11]
    bne     press
    tst     r6, #HELD_B
    beq     start_key
    adr     r0, name_delete
    bl      find_by_name
    b       press
start_key:
    tst     r6, #HELD_START
    beq     lit
    adr     r0, name_ok
    bl      find_by_name
press:
    cmp     r0, #0
    beq     mask
    bl      centre
    cmp     r0, #0
    beq     mask
    mov     r4, r1, asr #1            @ the touch: raw halfwords
    mov     r5, r2, asr #1
    mov     r0, #0
    str     r0, [r11, #4]             @ the game's own looks take over; the lit one comes back after the release
    b       mask
lit:
    ldr     r1, [r11, #4]
    cmp     r1, #0
    bne     mask
    ldr     r0, [r11]
    bl      can_light                 @ not in the middle of a press or release
    cmp     r0, #0
    beq     mask
    ldr     r0, [r11]
    mov     r1, #0
    bl      set_look
    mov     r1, #1
    str     r1, [r11, #4]
mask:
    ldr     r0, =0x000F60F8           @ A, B, START, D-pad (0xF0) and circle pad (0xF0000)
    bic     r6, r6, r0
    bic     r7, r7, r0
    bic     r8, r8, r0
done:
    vpop    {d0-d7}
    pop     {r2, r3, r9-r11, lr}
    b       keyboard_input_resume
    .ltorg

@ The patcher's (curated single_screen.json, "keyboard"), here because adr reaches only a few hundred bytes: the names of
@ the controls B and START touch, 16 bytes zero padded (the game compares 16 bytes), and the start point (raw touch
@ coordinates).
    .global name_delete
name_delete:
    .space  16
    .global name_ok
name_ok:
    .space  16
    .global start_x
start_x:
    .word   0
start_y:
    .word   0
@ The moves (curated "keyboard": slack, across_weight, centre_weight): the slack in doubled pixels, then the weights.
    .global nav_slack
nav_slack:
    .word   0
nav_across:
    .word   0
nav_centre:
    .word   0
@ The hovered mode tab's colour (0xAABBGGRR), and the names of the controls the finger never rests on (skip_count of
@ the 16-byte names in skip_names).
    .global tab_colour
tab_colour:
    .word   0
    .global skip_count
skip_count:
    .word   0
    .global skip_names
skip_names:
    .space  64

@ Constants of centre (a vldr reaches only 1020 bytes).
zero:
    .float  0.0
width2:
    .float  320.0                     @ 2 * 160, the touch screen's half width, doubled
height2:
    .float  240.0

@ r0 = a control -> r0 = 1 if it is in the key manager's list (r10), else 0. Clobbers r1-r3.
in_list:
    cmp     r0, #0
    beq     in_list_no
    add     r1, r0, #4
    add     r2, r10, #0xC
    ldr     r3, [r10, #0x10]
in_list_next:
    cmp     r3, r2
    beq     in_list_no
    cmp     r3, r1
    moveq   r0, #1
    bxeq    lr
    ldr     r3, [r3, #4]
    b       in_list_next
in_list_no:
    mov     r0, #0
    bx      lr

@ r0 = a 16-byte name -> r0 = the control of the list named that, or 0. Clobbers r1-r3, r12.
find_by_name:
    push    {r4, r5}
    ldr     r1, [r10, #0x10]
find_next:
    add     r2, r10, #0xC
    cmp     r1, r2
    beq     find_none
    mov     r12, #0
find_word:
    add     r3, r1, #0x1C             @ the node is control + 4; the name at control + 0x20
    ldr     r4, [r3, r12]
    ldr     r5, [r0, r12]
    cmp     r4, r5
    bne     find_skip
    add     r12, r12, #4
    cmp     r12, #16
    blo     find_word
    sub     r0, r1, #4
    pop     {r4, r5}
    bx      lr
find_skip:
    ldr     r1, [r1, #4]
    b       find_next
find_none:
    mov     r0, #0
    pop     {r4, r5}
    bx      lr

@ r0 = a control -> r0 = 1 if it can be touched, with r1 / r2 = the doubled raw touch coordinates of the middle of its
@ hit rectangle (x2, y2), r3 = the control and r12 = its half extents in the same units (width << 16 | height); else
@ r0 = 0. Touchable: enabled, not greyed, its layout's group shown and its rectangle on the screen. Uses s0-s9.
    .global centre
centre:
    push    {r4-r6, lr}
    mov     r4, r0
    ldrb    r0, [r4, #0x18]
    cmp     r0, #0
    beq     centre_no
    ldr     r0, [r4, #0x14]
    cmp     r0, #5
    bhs     centre_no
    ldr     r5, [r4, #0x54]           @ its layout
    cmp     r5, #0
    beq     centre_no
    bl      is_skipped
    cmp     r0, #0
    bne     centre_no
    ldr     r0, [r5, #0x120]          @ the groups the layout draws: one shown on the top screen puts it on screen
centre_group:
    cmp     r0, #0
    beq     centre_no
    ldr     r1, [r0, #0x44]
    tst     r1, #SHOWN
    beq     centre_after
    mov     r1, r1, lsr #SCREEN_SHIFT
    ands    r1, r1, #0xF              @ the group's screen: 0 is the top one
    beq     centre_drawn
centre_after:
    ldr     r0, [r0, #0x48]
    b       centre_group
centre_drawn:
    add     r0, r5, #0x2A0
    add     r1, r4, #0x20
    bl      gui_named_group
    cmp     r0, #0
    beq     centre_no
    ldr     r1, [r0, #0x1C]           @ the entry's first element
    add     r0, r0, #0x18
    cmp     r1, r0
    beq     centre_no
    ldr     r1, [r1, #0xC]
    ldr     r2, [r1, #0x10]
    and     r2, r2, #0xFF
    cmp     r2, #3                    @ a hit rectangle
    bne     centre_no
    ldr     r6, [r1, #8]
    vldr    s4, zero
    vldr    s5, zero
    ldr     r0, [r5, #0x160]          @ the layout's position (FUN_00b048e8), none when this is 0
    cmp     r0, #0
    beq     centre_math
    ldr     r0, [r5, #0x154]
    ldr     r0, [r0]
    vldr    s4, [r0, #0x28]
    vldr    s5, [r0, #0x2C]
centre_math:
    vldr    s0, [r6, #0x20]
    vldr    s1, [r6, #0x28]
    vldr    s2, [r6, #0x24]
    vldr    s3, [r6, #0x2C]
    vsub.f32 s8, s1, s0               @ the rectangle's width and height: in doubled pixels they are the half ones
    vsub.f32 s9, s3, s2
    vabs.f32 s8, s8
    vabs.f32 s9, s9
    vcvt.s32.f32 s8, s8
    vcvt.s32.f32 s9, s9
    vadd.f32 s0, s0, s1               @ x0 + x1
    vadd.f32 s2, s2, s3               @ y0 + y1
    vadd.f32 s4, s4, s4
    vadd.f32 s5, s5, s5
    vldr    s6, width2
    vldr    s7, height2
    vadd.f32 s6, s6, s4
    vadd.f32 s7, s7, s5
    vsub.f32 s6, s6, s0
    vsub.f32 s7, s7, s2
    vcvt.s32.f32 s6, s6
    vcvt.s32.f32 s7, s7
    vmov    r1, s6
    vmov    r2, s7
    cmp     r1, #2                    @ on the screen (a rectangle parked at the layout's middle is not)
    blt     centre_no
    cmp     r2, #2
    blt     centre_no
    ldr     r0, =638
    cmp     r1, r0
    bgt     centre_no
    ldr     r0, =478
    cmp     r2, r0
    bgt     centre_no
    vmov    r0, s8
    vmov    r12, s9
    orr     r12, r12, r0, lsl #16     @ the half extents: width << 16 | height
    mov     r0, #1
    mov     r3, r4
    pop     {r4-r6, pc}
centre_no:
    mov     r0, #0
    mov     r3, r4
    pop     {r4-r6, pc}

pick_start:
    mov     r0, #0
    mov     r1, #0
    @ falls into pick_next with no hover and no direction

@ r0 = the hovered control (0: none), r1 = direction (0 none, 1 up, 2 right, 3 down, 4 left) -> r0 = the eligible
@ control best placed in that direction, or 0. A candidate lies in a direction when its extent ends no more than the
@ curated slack before the hover's edge; its score is the gap ahead (between the two extents, 0 when they overlap) plus
@ nav_across times the gap across plus nav_centre times the distance between the middles across (the least wins).
@ No direction (the start): the sum of the two distances between the middles. Keeps r10, r11.
pick_next:
    push    {r4-r9, r11, lr}
    sub     sp, sp, #12               @ [sp] the hover's half width, [sp + 4] its half height, [sp + 8] a candidate
    mov     r4, r0
    mov     r5, r1
    mov     r0, #0
    str     r0, [sp]
    str     r0, [sp, #4]
    cmp     r4, #0
    beq     ref_start
    mov     r0, r4
    bl      centre
    cmp     r0, #0
    beq     ref_start                 @ the hover cannot be touched now: from the start point
    mov     r6, r1
    mov     r7, r2
    mov     r0, r12, lsr #16
    str     r0, [sp]
    mov     r12, r12, lsl #16
    mov     r12, r12, lsr #16
    str     r12, [sp, #4]
    b       scan
ref_start:
    mov     r5, #0
    mov     r4, #0
    ldr     r6, start_x
    mov     r6, r6, lsl #1
    ldr     r7, start_y
    mov     r7, r7, lsl #1
scan:
    mov     r8, #0                    @ best control
    mvn     r9, #0x80000000           @ its score
    ldr     r11, [r10, #0x10]
scan_next:
    add     r0, r10, #0xC
    cmp     r11, r0
    beq     scan_end
    sub     r0, r11, #4
    ldr     r11, [r11, #4]
    cmp     r0, r4
    beq     scan_next
    bl      centre
    cmp     r0, #0
    beq     scan_next
    str     r3, [sp, #8]
    sub     r1, r1, r6                @ dx
    sub     r2, r2, r7                @ dy
    cmp     r5, #0
    beq     score_start
    mov     r3, r12, lsr #16
    ldr     r0, [sp]
    add     r3, r3, r0                @ the half widths' sum
    mov     r12, r12, lsl #16
    mov     r12, r12, lsr #16
    ldr     r0, [sp, #4]
    add     r12, r12, r0              @ the half heights' sum
    cmp     r5, #1
    beq     dir_up
    cmp     r5, #2
    beq     dir_right
    cmp     r5, #3
    beq     dir_down
    rsb     r0, r1, #0                @ left: ahead = -dx, across dy; extents along the widths, across the heights
    mov     r1, r2
    mov     r2, r3
    mov     r3, r12
    b       score_dir
dir_up:
    rsb     r0, r2, #0                @ up: ahead = -dy, across dx; along the heights, across the widths
    mov     r2, r12
    b       score_dir
dir_right:
    mov     r0, r1                    @ right: ahead = dx, across dy
    mov     r1, r2
    mov     r2, r3
    mov     r3, r12
    b       score_dir
dir_down:
    mov     r0, r2                    @ down: ahead = dy, across dx
    mov     r2, r12
score_dir:                            @ r0 ahead, r1 across (signed), r2 the sum of the half extents along, r3 across
    sub     r0, r0, r2                @ the gap ahead: the middles' distance less both half extents
    ldr     r2, nav_slack
    adds    r2, r0, r2
    blt     scan_next                 @ more than the slack behind the hover's edge: not in this direction
    cmp     r0, #0
    movlt   r0, #0
    cmp     r1, #0
    rsblt   r1, r1, #0                @ the middles' distance across
    subs    r3, r1, r3                @ the gap across: that less both half extents, or 0
    movlt   r3, #0
    ldr     r2, nav_across
    mla     r0, r3, r2, r0
    ldr     r2, nav_centre
    mla     r0, r1, r2, r0
    ldr     r3, [sp, #8]
    b       scored
score_start:
    cmp     r1, #0
    rsblt   r1, r1, #0
    cmp     r2, #0
    rsblt   r2, r2, #0
    add     r0, r1, r2
    ldr     r3, [sp, #8]
scored:
    cmp     r0, r9
    movlt   r9, r0
    movlt   r8, r3
    b       scan_next
scan_end:
    mov     r0, r8
    add     sp, sp, #12
    pop     {r4-r9, r11, pc}

@ r4 = a control -> r0 = 1 if its name is one of the curated skipped ones (skip_names), else 0. Clobbers r0-r3, r12.
is_skipped:
    ldr     r0, skip_count
    adr     r1, skip_names
skip_loop:
    cmp     r0, #0
    beq     skip_no
    sub     r0, r0, #1
    mov     r12, #0
skip_word:
    add     r2, r4, #0x20
    ldr     r2, [r2, r12]
    ldr     r3, [r1, r12]
    cmp     r2, r3
    bne     skip_next
    add     r12, r12, #4
    cmp     r12, #16
    blo     skip_word
    mov     r0, #1
    bx      lr
skip_next:
    add     r1, r1, #16
    b       skip_loop
skip_no:
    mov     r0, #0
    bx      lr

@ r0 = a control -> r0 = 1 if the hover look may be put on it: its state is idle (0, or 4 on a mode tab: the selected one),
@ not in the middle of a press or release. Clobbers r1-r3.
can_light:
    ldr     r1, [r0, #0x14]
    cmp     r1, #0
    moveq   r0, #1
    bxeq    lr
    cmp     r1, #4
    bne     light_no
    ldr     r2, [r0]
    ldr     r2, [r2, #0x18]
    ldr     r3, =keyboard_tab_update
    cmp     r2, r3
    moveq   r0, #1
    bxeq    lr
light_no:
    mov     r0, #0
    bx      lr

@ r0 = a control, r1 = 0 the pressed look / 1 the released look. By the control's class (its update, vtable slot 0x18):
@  * the keys, buttons and text area: what a touch-down (FUN_006702e4) or a release (FUN_006703ac) does to a key,
@    without the state change, the sound or the callback;
@  * the mode tabs (FUN_00670a40): they keep other fields where the keys' look pointers are, which crashed the keys'
@    look, and one colour pane: the pressed colour is the selected tab's too, so the hover is the curated colour, and
@    the release puts back what the tab's state wears (idle +0x44, selected +0x98, greyed +0x3C);
@  * the arrows and the suggestion words (FUN_0067381c, FUN_00678724): the press animation the class plays at a
@    touch-down (control + 0x5C, FUN_00678dc4) and the rewind it does at the release (FUN_0066a124), both null-safe;
@  * any other class: none.
set_look:
    push    {r4-r6, lr}
    mov     r4, r0
    mov     r6, r1
    ldr     r2, [r4]
    ldr     r2, [r2, #0x18]
    ldr     r3, =keyboard_key_update
    cmp     r2, r3
    beq     look_key
    ldr     r3, =keyboard_tab_update
    cmp     r2, r3
    beq     look_tab
    ldr     r3, =keyboard_arrow_update
    cmp     r2, r3
    beq     look_anim
    ldr     r3, =keyboard_area_update
    cmp     r2, r3
    bne     look_done
look_anim:
    mov     r0, r4
    ldr     r1, [r4, #0x5C]
    cmp     r6, #0
    bne     anim_back
    bl      keyboard_anim_play
    b       look_done
anim_back:
    bl      keyboard_anim_rewind
    b       look_done
look_tab:
    cmp     r6, #0
    ldreq   r1, tab_colour
    beq     tab_paint
    ldr     r0, [r4, #0x14]
    mov     r2, #0x44
    cmp     r0, #4
    moveq   r2, #0x98
    cmp     r0, #5
    moveq   r2, #0x3C
    ldr     r1, [r4, r2]
tab_paint:
    mov     r0, r4
    mov     r2, r1
    bl      paint
    b       look_done
look_key:
    cmp     r6, #0
    moveq   r5, #0x4C                 @ the pressed colours at control + 0x4C
    movne   r5, #0x44                 @ the idle ones at control + 0x44
    mov     r0, r4
    moveq   r1, #0
    movne   r1, #2
    bl      keyboard_look
    ldr     r1, [r4, r5]
    add     r2, r4, r5
    ldr     r2, [r2, #4]
    mov     r0, r4
    bl      paint
look_done:
    pop     {r4-r6, pc}

@ r0 = a control, r1 / r2 = the colours of its two colour panes (control + 0x34 and +0x38, when they exist): each pane
@ is marked changed and its colour fields (the object two links down, +0x3C and +0x40) set.
paint:
    push    {r4-r6, lr}
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    mov     r3, #0
paint_next:
    add     r0, r4, r3, lsl #2
    ldr     r0, [r0, #0x34]
    cmp     r0, #0
    beq     paint_skip
    mov     r12, #1
    strb    r12, [r0, #0x10]
    ldr     r0, [r0, #8]
    cmp     r0, #0
    beq     paint_skip
    ldr     r0, [r0, #8]
    cmp     r0, #0
    beq     paint_skip
    cmp     r3, #0
    moveq   r1, r5
    movne   r1, r6
    str     r1, [r0, #0x40]
    str     r1, [r0, #0x3C]
paint_skip:
    add     r3, r3, #1
    cmp     r3, #2
    blo     paint_next
    pop     {r4-r6, pc}

    .ltorg
