@ The split title's RomFS (install/title/split_romfs.c): the game's
@ nn::fs::FileStream::TryInitialize (FUN_0010baf8), whose first instruction became a `b` to split_romfs_open.
@
@ file_stream_open_game(file, path, mode): runs the replaced instruction and goes on at the function's second one,
@ which returns to the caller with the function's result.
@
@ Build: tools/build/build_code_space.py (devkitARM), which places and links it.

    .arch armv6k
    .arm
    .global _start
    .global file_stream_open_game

_start:
file_stream_open_game:
    push    {r4-r8, lr}               @ the replaced instruction
    b       file_stream_open_body
