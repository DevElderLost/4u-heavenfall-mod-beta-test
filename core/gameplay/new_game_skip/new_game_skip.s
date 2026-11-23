@ Skip the intro (option skip_intro): a new character starts as if the
@ prologue (quest 100, the sand ship) and the Guild registration were done.
@
@ The character creation (FUN_00b7961c, state 5) ends with FUN_00c25b50(save, profile); that call is
@ replaced by `bl` to this routine, which runs it and then, on the save object at SAVE_POINTER, does
@ what the prologue and the registration leave behind, read in order from the data block
@ new_game_data (written by gameplay/new_game_skip/new_game_skip.py):
@   u32 funds (save + 0x5C + 0x34), u16 hunter rank (u8 at save + 0x5C + 0x2C);
@   armor: (type, id, word 4) u16 triples until type 0. Each piece goes in the first free slot of the
@     equipment box (FUN_00c25918; a new save's free slots are zero), is marked obtained
@     (FUN_00c1e274) and becomes the worn piece of its type (u16 box index at save + 0x160 + 2 * type),
@     as FUN_00c26c58 does with the starting equipment; FUN_00c1b26c then copies the worn pieces;
@   quest ids (u16) until 0xFFFF, marked cleared (FUN_00c1f170);
@   story flag ids (u16) until 0xFFFF, set (FUN_00c1b0e8).
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ SAVE_POINTER, save_control   @ the save object (FUN_00c1f50c's argument)
    .equ FUNDS, 0x5C + 0x34
    .equ RANK, 0x5C + 0x2C
    .equ BOX, 0x5C + 0x173E           @ equipment box, records of 0x1C bytes
    .equ WORN, 0x5C + 0x104           @ u16 box index of the worn piece of each type

_start:
    push    {r4-r8, lr}
    bl      new_profile               @ the call this routine replaces (r0, r1 as given)
    ldr     r4, save_pointer
    ldr     r4, [r4]
    cmp     r4, #0
    beq     done
    ldr     r6, data
    ldr     r7, end_mark
    ldr     r0, [r6], #4
    str     r0, [r4, #FUNDS]
    ldrh    r0, [r6], #2
    strb    r0, [r4, #RANK]

armor_next:
    ldrh    r8, [r6], #2              @ type
    cmp     r8, #0
    beq     wear
    mov     r0, r4
    bl      free_box_slot             @ index, or 0xFFFF when the box is full
    add     r2, r4, r8, lsl #1
    add     r2, r2, #WORN
    cmp     r0, r7
    strneh  r0, [r2]
    rsb     r1, r0, r0, lsl #3        @ index * 7
    ldr     r2, box
    add     r1, r2, r1, lsl #2        @ BOX + index * 0x1C
    add     r1, r4, r1                @ the record (2-aligned)
    ldrh    r2, [r6], #2
    ldrh    r3, [r6], #2
    strneb  r8, [r1]
    strneh  r2, [r1, #2]
    strneh  r3, [r1, #4]
    mov     r0, r4
    mov     r2, #0
    blne    mark_obtained
    b       armor_next

wear:
    mov     r0, r4
    add     r1, r4, #0x5C
    mov     r2, #0
    bl      equip_from_box

    ldr     r5, quest_function        @ quest ids, then story flag ids
list_next:
    ldrh    r1, [r6], #2
    cmp     r1, r7
    beq     list_end
    mov     r0, r4
    blx     r5
    b       list_next
list_end:
    ldr     r0, flag_function
    cmp     r5, r0
    movne   r5, r0
    bne     list_next
done:
    pop     {r4-r8, pc}

save_pointer:
    .word   SAVE_POINTER
data:
    .word   new_game_data
quest_function:
    .word   set_quest_cleared
flag_function:
    .word   set_story_flag
end_mark:
    .word   0xFFFF
box:
    .word   BOX
