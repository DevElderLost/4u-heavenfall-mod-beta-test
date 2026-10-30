@ Single-screen mode: the character creation's Aceptar / Atrás buttons are moved between with the pad's left and right
@ (exefs/single_screen_creation.py).
@
@ The creation menu owner's cursor is FUN_0022b96c(owner, mode, pad, cells, columns), called by its pad reader
@ FUN_0022a0f4. On a main page (mode 1: the hunter's 9 cells, the Felyne's 7) the cursor is the owner's byte +4 (1 a cell,
@ 2 Aceptar, 3 Atrás) with the row at +0xB: the cells' rows, then Aceptar's row, then Atrás' row, stepped by the pad's
@ up (bit 1) and down (bit 2) with a wrap; left (4) and right (8) only move the column of a cell and do nothing on the
@ buttons. In single-screen mode the two ui006 buttons stand side by side on the top screen (Aceptar left, Atrás right: the
@ curated creation_prompt.shift), so up / down between them would be the wrong keys.
@
@ The two calls of mode 1 (FUN_0022a0f4, the hunter's page and the Felyne's) become calls here, which change the pad (and
@ at most the owner's row) only while the cursor is on a button, and tail-call the game's step:
@   on Aceptar: right -> down (Atrás);  down -> the row of Atrás is passed first, so the step goes on to the grid's top;
@   on Atrás:   left  -> up (Aceptar);  up   -> the row of Aceptar is passed first, so the step goes on to the grid's last row.
@ Left on Aceptar, right on Atrás, the confirm and cancel bits and every cursor on a cell are the game's.
@
@ Live: r0 the owner, r1 the mode, r2 the pad, r3 the cell count, the stack the column count; after the call the caller
@ reads r0 (the result: 1 a cell, 2 Aceptar, 3 Atrás, 0 nothing) and no other of r1-r3 or ip.
@
@ Build: tools/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ MODE_MAIN, 1
    .equ KIND, 4                      @ the owner's cursor kind
    .equ ROW, 0xB                     @ the cursor's row
    .equ ACCEPT, 2
    .equ BACK, 3
    .equ UP, 1
    .equ DOWN, 2
    .equ LEFT, 4
    .equ RIGHT, 8

_start:
    .global creation_pad
creation_pad:
    cmp     r1, #MODE_MAIN
    bne     step                      @ another page's grid: the game's
    ldrb    ip, [r0, #KIND]
    cmp     ip, #ACCEPT
    beq     on_accept
    cmp     ip, #BACK
    bne     step                      @ a cell
on_back:
    tst     r2, #LEFT
    bicne   r2, r2, #(UP | DOWN | LEFT | RIGHT)
    orrne   r2, r2, #UP               @ left: Aceptar
    bne     step
    tst     r2, #UP
    beq     step
    ldrb    ip, [r0, #ROW]
    sub     ip, ip, #1                @ up: from Aceptar's row, to the grid
    strb    ip, [r0, #ROW]
    b       step
on_accept:
    tst     r2, #RIGHT
    bicne   r2, r2, #(UP | DOWN | LEFT | RIGHT)
    orrne   r2, r2, #DOWN             @ right: Atrás
    bne     step
    tst     r2, #DOWN
    beq     step
    ldrb    ip, [r0, #ROW]
    add     ip, ip, #1                @ down: from Atrás' row, past the end, to the grid
    strb    ip, [r0, #ROW]
step:
    b       creation_cursor           @ FUN_0022b96c: returns to the caller of this stub
