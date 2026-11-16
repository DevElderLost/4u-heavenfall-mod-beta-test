/* Links radial_editor.c as one block (ARM: mod_settings.c calls it by its address).
   tools/build/build_code_space.py passes the link address (LINK_ADDRESS) and the symbols it uses. */
SECTIONS
{
    .text LINK_ADDRESS : { *(.text*) *(.rodata*) }
    /DISCARD/ : { *(.ARM.*) *(.comment) *(.note*) }
}
