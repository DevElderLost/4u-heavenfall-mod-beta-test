@ Minimap icons for the HUD size option.
@
@ The map icon functions place each icon from FUN_006c40e0 (world position ->
@ map position, centred: -W/2..W/2) with u = (x + W/2) / W. The map layouts are
@ shrunk by data towards the map's top-right corner (u = 1, v = 0), so this
@ wrapper maps the result the same way before the icon functions use it:
@     u' = 1 - s * (1 - u)   ->   x' = s * x + (W/2) * (1 - s)
@     v' = s * v             ->   z' = s * z - (W/2) * (1 - s)
@ W is the map size, an int at stage + 0x150 (what FUN_006c5678 returns).
@ The call sites of the icon functions are redirected here (bl); the two
@ floats at the end (labels scale and half_rest) are written by
@ core/interface/hud/code_patch.py.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .fpu vfp
    .arm
    .global _start

    .equ PROJECT, minimap_project     @ FUN_006c40e0 (update executable)
    .equ MAP_SIZE, 0x150

_start:
    push    {r4, r5, r6, lr}
    mov     r4, r0                    @ out: x, y, z, w
    mov     r5, r1                    @ stage
    bl      PROJECT
    mov     r6, r0
    ldr     r0, [r5, #MAP_SIZE]       @ W
    vmov    s0, r0
    vcvt.f32.s32 s0, s0
    vldr    s1, scale                 @ s
    vldr    s2, half_rest             @ (1 - s) / 2
    vmul.f32 s0, s0, s2               @ (W/2) * (1 - s)
    vldr    s3, [r4]
    vmul.f32 s3, s3, s1
    vadd.f32 s3, s3, s0
    vstr    s3, [r4]
    vldr    s4, [r4, #8]
    vmul.f32 s4, s4, s1
    vsub.f32 s4, s4, s0
    vstr    s4, [r4, #8]
    mov     r0, r6
    pop     {r4, r5, r6, pc}

scale:
    .float 1.0
half_rest:
    .float 0.0
