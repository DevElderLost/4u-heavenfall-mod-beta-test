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
@ gate_*: a call of the game that another block took (hold A, fast text, fast gathering, the lock-on's D-pad filter) goes
@   here first: with the option off it makes the game's own call, else it goes on to the block's entry. Only the flags
@   change (r12 is kept), so the callee gets its registers and stack arguments as they came.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfp
    .arm
    .global _start
    .global mod_frame_stub, mod_bloom, mod_fov_reset, mod_fov_other, mod_net_waits, mod_net_polls_a, mod_net_polls_b
    .global mod_raw_a, mod_raw_b
    .global gate_hold_a_field, gate_hold_a_rewards, gate_hold_a_claim, gate_fast_text, gate_fast_motion
    .global gate_fast_timer, gate_lock

    @ struct mod_options_state (mod_options.c checks the offsets)
    .equ NET_WAITS, 16
    .equ NET_POLLS, 20
    .equ FOV_ONE, 24
    .equ FOV_OTHER, 28
    .equ RAW_BASE, 32
    @ the options' places in mod_options_state.values (mod_options.py OPTION_IDS)
    .equ OPT_BLOOM, 1
    .equ OPT_LOCK, 6
    .equ OPT_HOLD_A, 7
    .equ OPT_FAST_TEXT, 8
    .equ OPT_FAST_GATHERING, 9
    .equ GAME_FOV_ONE, 0x42480000       @ 50.0, the game's literal of the reset case "not equal" and of FUN_00c06a14
    .equ GAME_FOV_OTHER, 0x42680000     @ 58.0, the reset case "equal"

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
    ldr     r12, [r12, #NET_WAITS]
    cmp     r2, r12
    pop     {r12}
    b       net_waits_return

mod_net_polls_a:
    ldr     r0, =mod_options_state
    ldr     r0, [r0, #NET_POLLS]
    b       net_polls_a_return

mod_net_polls_b:
    ldr     r0, =mod_options_state
    ldr     r0, [r0, #NET_POLLS]
    b       net_polls_b_return

mod_raw_a:
    ldr     r0, =mod_options_state
    ldr     r0, [r0, #RAW_BASE]
    b       raw_a_return

mod_raw_b:
    ldr     r2, =mod_options_state
    ldr     r2, [r2, #RAW_BASE]
    b       raw_b_return

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

    .ltorg
