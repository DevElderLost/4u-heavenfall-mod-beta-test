@ Descriptions of the hunter gear's new ids: the Smithy, the
@ equipment box and the shops show a piece's description with FUN_005a8630 (armor) and FUN_005a9264 (weapons):
@
@     message = *(u16 *)(array_of_the_list + 2 * id)        (ldrh r1, [r1]  at 0x5A8684 and 0x5A92CC)
@
@ where the arrays (0xEEF4F8 ..., listed by the pointer table at 0xDF4FE4) hold exactly one entry per id the
@ game has. Both reads come here. For an id below the list's old end the game's array answers as before. For a
@ new id the message is the list's first new description plus its distance from the old end: the descriptions of
@ the new ids are appended to the Exp list in id order (equipment/new_gear/new_texts.py), one per id, so no array is needed
@ for them (the arrays are not copied: the extension has no room for 15 KB of them).
@
@ In:  r1 = the array entry's address, r2 = the id, r3 = the Exp file's number (armor 21-26, weapons 42-55).
@ Out: r1 = the message. r2 and r4 are free there (the callers overwrite r2, and saved r4); lr is the caller's
@      (the hook is a `bl`, the game's function saved its own lr). Flags are not used afterwards.
@ `table`: a word per Exp file number 21 ... 55: the list's old end (ids below it keep the array) in the low half,
@ in the high half the first new description's message minus the old end (mod 2^16). 0xFFFF in the low half
@ leaves a number the game never reads here alone. Filled in by equipment/new_gear/gear_descriptions.py.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .syntax unified
    .arch armv6k
    .arm
    .global _start

    .equ FIRST_FILE, 21

_start:
    adr     r4, table
    add     r4, r4, r3, lsl #2
    ldr     r4, [r4, #-4 * FIRST_FILE]
    mov     r2, r2, lsl #16
    cmp     r2, r4, lsl #16           @ id < old end?
    ldrhlo  r1, [r1]                  @ yes: the game's array
    bxlo    lr
    mov     r2, r2, lsr #16
    add     r1, r2, r4, lsr #16       @ id + (first new message - old end)
    uxth    r1, r1
    bx      lr

table:
    .space  4 * 35                    @ Exp files 21 ... 55
    .ltorg
