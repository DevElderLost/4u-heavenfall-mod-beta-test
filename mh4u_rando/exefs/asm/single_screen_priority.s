@ Single-screen mode: the draw order of the layouts moved to the top screen (exefs/single_screen.py).
@
@ FUN_00ae63c8(group, layer, priority) writes a GUI group's layer (bits 27-31) and priority (bits 19-26) of
@ group + 0x18; of two groups on a screen, the higher priority is drawn in front. Its first instruction,
@ `ldr r3, [r0, #0x18]`, becomes a branch here. When the group's name hash (group + 0) is in
@ single_screen_priorities, the table's offset is added to the priority (r2), clamped to 0-255: a layout's groups keep
@ their order among themselves and move in front of the others. Then the replaced instruction, and back.
@
@ Live: r0 the group, r1 the layer, r2 the priority; the function overwrites r3 and ip. Every other register is kept.
@ single_screen_priorities: u32 count, then count pairs {u32 name hash, s32 offset}.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    .global priority_hook
priority_hook:
    push    {r4, r5}
    ldr     r3, =single_screen_priorities
    ldr     r4, [r3], #4              @ the count
    ldr     ip, [r0]                  @ the group's name hash
find:
    subs    r4, r4, #1
    bmi     done
    ldr     r5, [r3], #8
    cmp     r5, ip
    bne     find
    ldr     r5, [r3, #-4]             @ the offset
    adds    r2, r2, r5
    movmi   r2, #0
    cmp     r2, #0xff
    movgt   r2, #0xff
done:
    pop     {r4, r5}
    ldr     r3, [r0, #0x18]           @ the replaced instruction
    b       gui_priority_resume
    .ltorg
