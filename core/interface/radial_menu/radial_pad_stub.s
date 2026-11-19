@ The item wheel's hold on ZR (interface/radial_menu/radial_menu.py patch_radial_wheel).
@
@ FUN_005b8284, the pad update's read (called by FUN_00694ccc once per frame, before the game layout and the GUI's
@ buttons are made from the raw words), calls FUN_005b8460(pad object, pad + 0x2C, status) at 0x5B8308, the raw read,
@ and returns right after it. That `bl` is replaced by a `bl` to this stub, which makes the call with the arguments as
@ they came and then calls radial_pad(pad + 0x2C) (radial_wheel.c), which may take ZR's bit out of the raw words:
@   - r1 and lr are saved (two words: the stack stays 8-byte aligned); r0-r3 and r12 hold nothing the caller reads
@     after the call; r4-r11 are callee-saved, so the game function and the C leave them alone;
@   - radial_pad is reached by a `b` with lr back to the instruction after the hooked `bl`.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    push    {r1, lr}
    bl      pad_raw_read            @ FUN_005b8460(pad object, pad + 0x2C, status)
    pop     {r0, lr}                @ r0: pad + 0x2C, the raw words' base
    b       radial_pad
