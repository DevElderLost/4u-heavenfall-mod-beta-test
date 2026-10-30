/* Links target_face.c as one block: the entry first, then the rest of the code and constants.
   tools/build_code_space.py passes the link address (LINK_ADDRESS) and the symbols it uses. */
SECTIONS
{
    .text LINK_ADDRESS : { *(.text.entry) *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.ARM.*) *(.comment) *(.note*) }
}
