@ The hooks of the options a player changes during play (interface/mod_settings/mod_options.py; docs/interface/
@ mod_settings.md, "Options the page holds"). mod_options.c reads every option once a frame into
@ mod_options_state; each label here stands in for one instruction or one call of the game and reads its option there.
@
@ mod_frame_stub: FUN_00af52a0, the application's update, calls `bl FUN_00644320` (the engine's timing update) first of all,
@   once a frame in every scene. That call comes here: mod_frame runs, then FUN_00644320 with r0-r3 and lr as they came.
@
@ mod_bloom: FUN_002bc258(filter, pass), the bloom and depth of field pass, starts with `push {r4-r11, lr}`. With the option on
@   it returns at once (the function returns nothing and no flag is live at its entry); else it runs that instruction and
@   goes on.
@
@ mod_fov_reset, mod_fov_other: FUN_00bff28c, the camera's reset, loads its field of view with `vldrne s0, [pc, ...]` (50.0)
@   and `vldreq s0, [pc, ...]` (58.0), and FUN_00c06a14 loads 50.0 into s3. Each load takes the mod's value instead (the game's
@   own literal until mod_frame has run), and the flags the loads depend on are kept.
@
@ mod_net_waits, mod_net_polls_a, mod_net_polls_b: the multiplayer node's waits: `cmp r2, #120` (FUN_00533e6c) and
@   `mov r0, #10` (FUN_005348a8, FUN_00535480). Each takes the number from mod_options_state; the compare leaves its flags.
@
@ mod_raw_a, mod_raw_b: FUN_0026e33c and FUN_0027335c load the weapon classes' table (`ldr r0, [pc, ...]`, `ldr r2, [pc,
@   ...]`): the base address comes from mod_options_state, the game's table or one of 100s; no flag changes.
@
@ mod_camera_cap: FUN_00bfd028, the camera's turn by the buttons, adds the frame's time to how long a turn has been held
@   and caps it with `vldr s0, [pc, ...]` (10.0); the turn's speed grows with that time, so the cap is its top speed. The
@   load takes the mod's value instead (the game's own literal until mod_frame has run), and the flags are kept.
@
@ mod_box_kind: FUN_009ec82c(scene, box) stores `box` (r6: 0 the house's box, 1 the Gathering Hall's) in its menu with
@   `strb r6, [r4, #0x2]`, then reads r6 and that byte again: box 0 gets seven lines and the house's set-ups, and only
@   for box 0 does the menu draw the lines past four and the submenus they open. The game's box is kept in
@   mod_options_state for mod_box_lines. With the option on r6 becomes 0 first, so every box is the house's; off, or
@   before mod_frame has run, the game's. The store becomes `bl mod_box_kind`, which returns to the next instruction: lr
@   is free there (the function pushed it on entry), and only the flags change (the function compares again before it
@   uses them).
@
@ mod_box_lines: FUN_009ec82c(scene, box) then stores the menu's count of lines, 7 for box 0 and 4 for box 1, with
@   `strb r1, [r4, #0xa]`. At a box away from home (the game's box was not 0) with the option on the count is its
@   value's: the lines past 4 are Manage Equipment, Equipment Sets and Change Appearance, and the value leaves out
@   Change Appearance, whose screen only the house loads. The house's box keeps the game's
@   7; off, or before mod_frame has run, the game's. Only the flags change (the function compares again before it uses
@   them).
@
@ keyboard_poll_game: FUN_002b58e8, the poll of the game's keyboard, from its second instruction on: the game's poll
@   for the gate and for the system keyboard's block, whose hook replaced the first (`push {r4, r5, r6, lr}`).
@
@ gate_*: a call of the game that another block took (hold A, fast text, fast gathering, the lock-on's D-pad filter, the
@   death camera skip's call of FUN_00c03d70 in the camera manager's frame, the modern camera's calls of FUN_00bfd028
@   and its question in FUN_00b3cc64, its aim's two instructions and calls of FUN_00b1ea04 in FUN_00b2041c, the intro
@   skip's call of FUN_00292ea4 in the touch bar's input) goes here
@   first: with the option off it makes the game's own call, else it goes on to the block's entry. Only the flags
@   change (r12 is kept), so the callee gets its registers and stack arguments as they came.
@
@ modern_stick_game: FUN_00b3cc64's `blx r2` (the hunter's vtable + 0x98, r0 the hunter, r1 1: "is the C-stick
@   tilted") for gate_modern_stick: the game's call, lr the hook's.
@
@ aim_commands_game, aim_scope_game: FUN_00b2041c's (the hunter's aim) `ldr r0, [r2, #0x3e4]` (its commands over the
@   shoulder and the Bow's) and `tst r0, #0x3c` (the scope's C-stick bits) for gate_aim_commands and gate_aim_scope,
@   the modern camera's aim hooks: the game's instruction, then back.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfp
    .arm
    .global _start
    .global mod_frame_stub, mod_bloom, mod_fov_reset, mod_fov_other, mod_net_waits, mod_net_polls_a, mod_net_polls_b
    .global mod_raw_a, mod_raw_b, mod_camera_cap, mod_box_kind, mod_box_lines
    .global gate_hold_a_field, gate_hold_a_rewards, gate_hold_a_claim, gate_fast_text, gate_fast_motion
    .global gate_fast_timer, gate_lock, gate_system_keyboard, keyboard_poll_game, gate_death_camera, gate_intro_skip
    .global gate_intro_music, gate_intro_end
    .global gate_modern_turn, gate_modern_stick, modern_stick_game
    .global gate_aim_commands, gate_aim_scope, gate_aim_view, aim_commands_game, aim_scope_game

    @ struct mod_options_state (mod_options.c checks the offsets)
    @ NET_WAITS and NET_POLLS are halfwords
    .equ NET_WAITS, 24
    .equ NET_POLLS, 26
    .equ FOV_ONE, 28
    .equ FOV_OTHER, 32
    .equ RAW_BASE, 36
    .equ CAMERA_CAP, 52
    .equ BOX_LINES, 60
    .equ BOX_AWAY, 61
    @ the options' places in mod_options_state.values (mod_options.py OPTION_IDS)
    .equ OPT_BLOOM, 1
    .equ OPT_LOCK, 6
    .equ OPT_HOLD_A, 7
    .equ OPT_FAST_TEXT, 8
    .equ OPT_FAST_GATHERING, 9
    .equ OPT_BOX, 11
    .equ OPT_KEYBOARD, 12
    .equ OPT_DEATH_CAMERA, 13
    .equ OPT_MODERN_CAMERA, 19
    .equ OPT_INTRO_SKIP, 21
    .equ GAME_FOV_ONE, 0x42480000       @ 50.0, the game's literal of the reset case "not equal" and of FUN_00c06a14
    .equ GAME_FOV_OTHER, 0x42680000     @ 58.0, the reset case "equal"
    .equ GAME_CAMERA_CAP, 0x41200000    @ 10.0, FUN_00bfd028's cap

_start:
mod_frame_stub:
    push    {r0-r3, r4, lr}
    bl      mod_frame
    pop     {r0-r3, r4, lr}
    b       frame_update

mod_bloom:
    ldr     r12, =mod_options_state
    ldrb    r12, [r12, #OPT_BLOOM]
    cmp     r12, #0
    bxne    lr
    push    {r4-r11, lr}
    b       bloom_body

@ s0 from the value of the case the flags tell, or the game's own literal while the value is zero (mod_frame has not run)
mod_fov_reset:
    push    {r11, r12}
    mrs     r11, cpsr
    ldr     r12, =mod_options_state
    ldrne   r12, [r12, #FOV_ONE]
    ldreq   r12, [r12, #FOV_OTHER]
    cmp     r12, #0
    bne     1f
    msr     cpsr_f, r11
    ldrne   r12, =GAME_FOV_ONE
    ldreq   r12, =GAME_FOV_OTHER
1:  vmov    s0, r12
    msr     cpsr_f, r11
    pop     {r11, r12}
    b       fov_reset_return

mod_fov_other:
    push    {r11, r12}
    mrs     r11, cpsr
    ldr     r12, =mod_options_state
    ldr     r12, [r12, #FOV_ONE]
    cmp     r12, #0
    ldreq   r12, =GAME_FOV_ONE
    vmov    s3, r12
    msr     cpsr_f, r11
    pop     {r11, r12}
    b       fov_other_return

mod_net_waits:
    push    {r12}
    ldr     r12, =mod_options_state
    ldrh    r12, [r12, #NET_WAITS]
    cmp     r2, r12
    pop     {r12}
    b       net_waits_return

mod_net_polls_a:
    ldr     r0, =mod_options_state
    ldrh    r0, [r0, #NET_POLLS]
    b       net_polls_a_return

mod_net_polls_b:
    ldr     r0, =mod_options_state
    ldrh    r0, [r0, #NET_POLLS]
    b       net_polls_b_return

mod_raw_a:
    ldr     r0, =mod_options_state
    ldr     r0, [r0, #RAW_BASE]
    b       raw_a_return

mod_raw_b:
    ldr     r2, =mod_options_state
    ldr     r2, [r2, #RAW_BASE]
    b       raw_b_return

mod_camera_cap:
    push    {r11, r12}
    mrs     r11, cpsr
    ldr     r12, =mod_options_state
    ldr     r12, [r12, #CAMERA_CAP]
    cmp     r12, #0
    ldreq   r12, =GAME_CAMERA_CAP
    vmov    s0, r12
    msr     cpsr_f, r11
    pop     {r11, r12}
    b       camera_cap_return

mod_box_kind:
    push    {r12}
    ldr     r12, =mod_options_state
    strb    r6, [r12, #BOX_AWAY]
    ldrb    r12, [r12, #OPT_BOX]
    cmp     r12, #0
    movne   r6, #0
    strb    r6, [r4, #0x2]
    pop     {r12}
    bx      lr

mod_box_lines:
    push    {r12}
    ldr     r12, =mod_options_state
    ldrh    r12, [r12, #BOX_LINES]  @ the count, and above it the box away from home
    tst     r12, #0xFF00
    andne   r12, r12, #0xFF
    cmpne   r12, #0
    movne   r1, r12
    strb    r1, [r4, #0xa]
    pop     {r12}
    b       box_lines_return

    .macro gate name, option, entry, original
\name:
    push    {r12}
    ldr     r12, =mod_options_state
    ldrb    r12, [r12, #\option]
    cmp     r12, #0
    pop     {r12}
    bne     \entry
    b       \original
    .endm

    gate    gate_hold_a_field, OPT_HOLD_A, hold_a_field, hunter_item_mode
    gate    gate_hold_a_rewards, OPT_HOLD_A, hold_a_rewards, result_scene
    gate    gate_hold_a_claim, OPT_HOLD_A, hold_a_claim, claim_scene
    gate    gate_fast_text, OPT_FAST_TEXT, fast_text_entry, message_update
    gate    gate_fast_motion, OPT_FAST_GATHERING, fast_gathering_motion, motion_speed
    gate    gate_fast_timer, OPT_FAST_GATHERING, fast_gathering_timer, has_skill
    gate    gate_lock, OPT_LOCK, dpad_filter_entry, dpad_actions
    gate    gate_system_keyboard, OPT_KEYBOARD, system_keyboard_poll, keyboard_poll_game
    gate    gate_death_camera, OPT_DEATH_CAMERA, death_camera_step, camera_play
    gate    gate_modern_turn, OPT_MODERN_CAMERA, modern_camera_turn, camera_turn_by_input
    gate    gate_modern_stick, OPT_MODERN_CAMERA, modern_camera_stick, modern_stick_game
    gate    gate_aim_commands, OPT_MODERN_CAMERA, aim_commands_hook, aim_commands_game
    gate    gate_aim_scope, OPT_MODERN_CAMERA, aim_scope_hook, aim_scope_game
    gate    gate_aim_view, OPT_MODERN_CAMERA, modern_aim_view, aim_pitch_view
    gate    gate_intro_skip, OPT_INTRO_SKIP, intro_skip_button, touch_bar_button
    gate    gate_intro_music, OPT_INTRO_SKIP, intro_skip_music, cutscene_sound_stop
    gate    gate_intro_end, OPT_INTRO_SKIP, intro_skip_end, event_sound_end

    @ modern_stick_game is one word: it goes before keyboard_poll_game, never right before the literal pool, so that a
    @ two-word branch put over it (a debugger's, an emulator's) cannot overwrite the gates' literal
modern_stick_game:
    bx      r2

aim_commands_game:
    ldr     r0, [r2, #0x3e4]
    bx      lr

aim_scope_game:
    tst     r0, #0x3c
    bx      lr

keyboard_poll_game:
    push    {r4, r5, r6, lr}
    b       keyboard_poll_body

    .ltorg
