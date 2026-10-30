@ Single-screen mode: the 3D model of the new game's character creation in the strip left of the menus
@ (exefs/single_screen_creation.py).
@
@ FUN_00B74748(scene, mode) writes the camera's goal for the creation's six modes: the eye (scene + 0xB8 / 0xBC /
@ 0xC0), then the target (+0xC8 / 0xCC / 0xD0) read from the stack's table at r2, and the fov. Its instruction
@ `ldr r3, [r2]` (0xB74850, the target x, stored to +0xC8 right after) becomes a branch here. For a mode of 0 to 5 the
@ eye z (+0xC0) is overwritten with the data block's, and r3 gets the block's target x; any other mode runs the
@ replaced instruction. The data block single_screen_creation_camera holds, per mode, {float target x, float eye z},
@ written by Python from the curated creation_camera.
@
@ Live: r0 the scene, r1 the mode (read again at 0xB74864), r2 the target (read again), ip the eye x (stored at
@ 0xB74888: kept); r3 and the flags are free (the function is a leaf; the next flag user, vcmpe, sets its own). r4 is
@ pushed.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    .global creation_hook
creation_hook:
    cmp     r1, #5
    ldrhi   r3, [r2]                  @ not a creation mode: the replaced instruction
    bhi     creation_resume
    push    {r4}
    ldr     r4, =single_screen_creation_camera
    add     r4, r4, r1, lsl #3
    ldr     r3, [r4, #4]
    str     r3, [r0, #0xc0]           @ the eye z
    ldr     r3, [r4]                  @ the target x
    pop     {r4}
    b       creation_resume
    .ltorg
