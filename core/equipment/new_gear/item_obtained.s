@ The "ever obtained" bits of new items.
@
@ The save keeps one bit per item id at data + 0xF220 (61 words). FUN_00c1ac90(save, data, id) sets the bit when an
@ item enters the box and FUN_00c1bef8(save, data, id) reads it (the Smithy shows a piece as "???" until a material
@ of its recipe has been obtained once; story checks read it too). Both refuse an id past 0x790, so a new item (ids
@ 0x791 and up, equipment/new_gear/new_items.py) would never count as obtained and its pieces would stay "???" for ever.
@
@ Their first instruction becomes a `b` to the entry below. A new id is looked up in item_obtained_bits (u16 per new
@ id, set by the patcher): the number of the bit it stands on, an id no recipe, drop or kit names, or 0xFFFF for none.
@ Setting writes that bit; reading answers it, or "obtained" (1) when there is none. Any other id runs the replaced
@ instruction and goes on in the game's function.
@
@ In: r0 save, r1 data, r2 item id, lr the caller. Out (get): r0 = 0 or 1. r3 and r12 are free there.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global get_entry
    .global set_entry

    .equ FIRST_NEW, 0x791             @ equipment/tables/item_data.py FIRST_NEW_ID
    .equ NEW_ITEMS, 624               @ ... MAX_NEW_ITEMS
    .equ NO_BIT, 0xFFFF
    .equ BITS, 0xF220                 @ the array's offset in the data

_start:
get_entry:
    ldr     r12, =FIRST_NEW
    subs    r3, r2, r12               @ id - 0x791 (carry clear: below it)
    blo     get_original
    cmp     r3, #NEW_ITEMS
    bhs     get_original
    ldr     r12, =item_obtained_bits
    add     r12, r12, r3, lsl #1
    ldrh    r3, [r12]                 @ the bit's number
    ldr     r12, =NO_BIT
    cmp     r3, r12
    moveq   r0, #1                    @ no bit: counts as obtained
    bxeq    lr
    lsr     r12, r3, #5
    add     r12, r1, r12, lsl #2
    add     r12, r12, #(BITS & 0xF000)
    ldr     r12, [r12, #(BITS & 0xFFF)]
    and     r3, r3, #31
    lsr     r12, r12, r3
    and     r0, r12, #1
    bx      lr
get_original:
    add     r0, r1, #0xF000           @ the replaced instruction
    b       item_get_body

set_entry:
    ldr     r12, =FIRST_NEW
    subs    r3, r2, r12
    blo     set_original
    cmp     r3, #NEW_ITEMS
    bhs     set_original
    ldr     r12, =item_obtained_bits
    add     r12, r12, r3, lsl #1
    ldrh    r3, [r12]
    ldr     r12, =NO_BIT
    cmp     r3, r12
    bxeq    lr                        @ no bit: nothing to set
    lsr     r12, r3, #5
    add     r12, r1, r12, lsl #2
    add     r12, r12, #(BITS & 0xF000)
    and     r3, r3, #31
    mov     r2, #1
    ldr     r0, [r12, #(BITS & 0xFFF)]
    orr     r0, r0, r2, lsl r3
    str     r0, [r12, #(BITS & 0xFFF)]
    bx      lr
set_original:
    push    {r4, r5, lr}              @ the replaced instruction
    b       item_set_body
