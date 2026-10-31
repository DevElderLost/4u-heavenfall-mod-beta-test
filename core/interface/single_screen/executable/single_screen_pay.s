@ Single-screen mode: the Canteen's pay choice (Pagar con dinero / Pagar con puntos / Volver) moves between its buttons
@ with the pad's left and right (interface/single_screen/executable/single_screen.py).
@
@ The pay choice's cursor is FUN_009fcd68(owner, &cursor, count, pressed): A (0x10) confirms, B (0x20) cancels, else
@ `bl FUN_005e70bc(cursor, count, pressed, 1, 2)` (0x9FCDBC, the stack holds the 2) steps the cursor with a wrap when
@ `pressed` holds bit 1 (up, previous) or bit 2 (down, next); left (bit 4) and right (bit 8) are in `pressed` and do
@ nothing. FUN_009fcd68 has one caller, the pay choice (FUN_00a92e54, the Canteen's cooking page 2), so this is the one
@ place in the game it changes. In single-screen mode the three buttons stand in a row on the top screen, where up /
@ down would be the wrong keys.
@
@ That call becomes a call here: left and right set the up and down bits of `pressed` (left -> bit 1, right -> bit 2,
@ every other bit as it was) and the step is tail-called with everything else untouched (r0 the cursor, r1 the count,
@ r3 the previous mask, the stack the next mask), so it returns to FUN_009fcd68 itself.
@
@ Live: r0-r3 and the stack as above; after the call the caller reads r0 (the new cursor) and no other of r1-r3 or ip.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

_start:
    .global pay_pad
pay_pad:
    and     ip, r2, #0xC              @ left (4) and right (8)
    orr     r2, r2, ip, lsr #2        @ as up (1) and down (2)
    b       cursor_step               @ FUN_005e70bc: returns to the caller of this stub
