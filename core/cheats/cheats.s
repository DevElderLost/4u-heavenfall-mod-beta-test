@ Cheats' per-frame writes (options cheat_3d_mode, cheat_fps, cheat_fov): the players' Gateway
@ cheats write a value into an object every frame ("if [X] != 0, write V at [X] + offset"). This block does the
@ same, from a table that cheats/cheats.py fills.
@
@ _start: FUN_00af52a0, the application's update (a slot of its vtable, run once per frame in every scene: menus,
@ village, quests), calls `bl frame_update` (FUN_00644320(app), the engine's timing update) first of all. That call
@ comes here. For each entry (index, offset, value) of `entries`, up to the end mark (index -1): the object is the
@ word the variable `globals[index]` holds; when it is not 0, `value` is written at object + offset. Then it goes on to
@ frame_update with r0-r3 and lr as they came.
@
@ Entry: u32 index into `globals` (-1: the end), u32 offset, u32 value. cheats/cheats.py keeps GLOBALS in the order
@ of `globals`, and `entries` holds MAX_ENTRIES of them and an end mark.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    push    {r0-r3}
    adr     r12, entries
    adr     r3, globals
next:
    ldr     r0, [r12], #4             @ index, or -1
    cmn     r0, #1
    beq     done
    ldr     r0, [r3, r0, lsl #2]      @ the variable that holds the object
    ldr     r0, [r0]                  @ the object: 0 until the game builds it
    ldr     r1, [r12], #4             @ offset
    ldr     r2, [r12], #4             @ value
    cmp     r0, #0
    strne   r2, [r0, r1]
    b       next
done:
    pop     {r0-r3}
    b       frame_update

globals:
    .word   gx_main                   @ 0: MtGX's draw object (+0x6BA8 the display mode word)
    .word   game_main                 @ 1: the main object (+0x30 the frame rate)
    .word   camera_control            @ 2: sCamera (+0xED0 the field of view)
entries:
    .rept   5                         @ MAX_ENTRIES and the end mark: all ends until cheats/cheats.py fills them
    .word   -1, 0, 0
    .endr
