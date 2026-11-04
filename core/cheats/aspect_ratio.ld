/* Links aspect_ratio.c as one block: its functions and constants; the stubs (aspect_stub.s) call them by name.
   tools/build/build_code_space.py passes the link address (LINK_ADDRESS) and the symbols it uses. */
SECTIONS
{
    .text LINK_ADDRESS : { *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.ARM.*) *(.comment) *(.note*) }
}
