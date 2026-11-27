@ The stubs of the two places where a quest cat and a cutscene cat take their body piece's skeleton
@ (felyne_joints.c; core/equipment/mhgen/felyne_pack.py, patch_joints).
@
@ felyne_quest_joints_entry   FUN_00699d5c(manager, actor, model, pair)'s first instruction, `push {r4-r9, lr}`,
@                             becomes a `b` here: felyne_quest_joints with the four arguments, then that push and on
@                             to the function's second instruction (felyne_quest_effect_resume).
@ felyne_scene_joints_stub    FUN_001a0ab8's `ldr r1, [sp, #8]` (its body model, for FUN_006997c4), r4 its actor,
@                             becomes a `bl` here: felyne_body_joints(actor, body), then that load. r0, r2, r3, ip
@                             and the flags are set anew after it, before they are read.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start, felyne_quest_joints_entry, felyne_scene_joints_stub

_start:
felyne_quest_joints_entry:
    push    {r0-r3, ip, lr}             @ six words: the stack stays 8-aligned
    bl      felyne_quest_joints
    pop     {r0-r3, ip, lr}
    push    {r4-r9, lr}                 @ the instruction the hook took the place of
    b       felyne_quest_effect_resume

felyne_scene_joints_stub:
    push    {r4, lr}                    @ two words: the stack stays 8-aligned
    mov     r0, r4                      @ the actor
    ldr     r1, [sp, #16]               @ the body: the function's [sp, #8], past our two words
    bl      felyne_body_joints
    pop     {r4, lr}
    ldr     r1, [sp, #8]                @ the instruction the hook took the place of
    bx      lr
