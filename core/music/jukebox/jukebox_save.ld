/* Links jukebox_save.c and its units (jukebox_core.c, jukebox_save_stub.s) as the resident block jukebox_save: the code and
   constants in one run. tools/build/build_code_space.py passes the link address (LINK_ADDRESS) and the symbols it uses. */
SECTIONS
{
    .text LINK_ADDRESS : { *(.text.entry) *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.ARM.*) *(.comment) *(.note*) }
}
