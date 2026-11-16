@ The item wheel's hook (interface/radial_menu/radial_menu.py patch_radial_wheel).
@
@ FUN_00b1cdf0, the local hunter's input update in a quest (once per frame), calls FUN_00b3d160(hunter) at 0xB1D0A4
@ (the item mode's button actions), between FUN_00b27fc8 (busy states) and FUN_00b3cc64 (D-pad and C-stick). That `bl`
@ is replaced by a `bl` to this stub, which keeps every register the game function and its caller expect:
@   - r0-r3, r12 and lr are saved, radial_wheel(hunter) (radial_wheel.c, r0 = the hunter) is called, and they come back;
@   - r4-r11 are callee-saved, so the C leaves them alone;
@   - the stack stays 8-byte aligned (six words are pushed);
@   - FUN_00b3d160 is reached by a `b`, so it returns to the instruction after the hooked `bl`, with the arguments and
@     the return address it would have had.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    push    {r0-r3, r12, lr}
    bl      radial_wheel
    pop     {r0-r3, r12, lr}
    b       item_mode_buttons       @ FUN_00b3d160(hunter)
