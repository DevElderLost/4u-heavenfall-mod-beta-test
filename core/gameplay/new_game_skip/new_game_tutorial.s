@ Skip the caravan tutorial (option skip_caravan_tutorial): with
@ skip_intro, a new character also has what the retail game leaves after the Caravaneer's talk and his first two
@ deliveries (the steak and the Mega Potion): the first Palico, equipped, the Training quests and quests 101 and 102
@ cleared, and the story flags of those steps.
@
@ The character creation (FUN_00b7961c, state 5) ends with FUN_00c25b50(save, profile); the patch makes that call
@ `bl` to this routine instead of to new_game_skip (which makes the same call and skips the intro). Here: first
@ new_game_skip, then, on the save object at SAVE_POINTER, what the block new_game_tutorial_data lists (written by
@ gameplay/new_game_skip/new_game_skip.py, caravan_tutorial_data()):
@   pokes: u32 offset in the save data (save + 0x5C), u32 length, the bytes, padded to 4 bytes; ends with offset
@     0xFFFFFFFF. Each is copied byte for byte: the Palico's gear box, the main Palico's record and the stringer
@     slots;
@   quest ids (u16) until 0xFFFF, marked cleared (FUN_00c1f170);
@   story flag ids (u16) until 0xFFFF, set (FUN_00c1b0e8).
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start

    .equ SAVE_POINTER, save_control   @ the save object (FUN_00c1f50c's argument)
    .equ DATA, 0x5C                   @ the save data starts at save + 0x5C

_start:
    push    {r4-r8, lr}
    bl      new_game_skip             @ the call the hook replaced: r0, r1 as given; then the intro skip
    ldr     r4, save_pointer
    ldr     r4, [r4]
    cmp     r4, #0
    beq     done
    ldr     r6, data
    ldr     r7, end_mark

poke_next:
    ldr     r0, [r6], #4              @ offset in the save data, or 0xFFFFFFFF
    cmn     r0, #1
    beq     pokes_end
    ldr     r2, [r6], #4              @ length (never 0)
    add     r1, r4, r0
    add     r1, r1, #DATA             @ destination
copy:
    ldrb    r3, [r6], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     copy
    add     r6, r6, #3                @ the next record starts on a word
    bic     r6, r6, #3
    b       poke_next
pokes_end:

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
    .word   new_game_tutorial_data
quest_function:
    .word   set_quest_cleared
flag_function:
    .word   set_story_flag
end_mark:
    .word   0xFFFF
