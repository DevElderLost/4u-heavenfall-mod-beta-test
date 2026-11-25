/* Links felyne_joints.c as one block: code, then constants. tools/build/build_code_space.py passes the link address
   (LINK_ADDRESS) and the symbols it uses. */
SECTIONS
{
    .text LINK_ADDRESS : { *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.ARM.*) *(.comment) *(.note*) }
}
