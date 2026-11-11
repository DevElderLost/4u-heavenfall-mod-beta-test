/* The screen kit (screen_kit.h): the generic pane helpers of the forge-style screens, moved out of layered_forge.c so
 * that the Rare Materials Exchange builds with the same code. Nothing here knows a screen: a pane is a hash, a group is
 * a hash, and a number is a number. */

#include "screen_kit.h"

u32 kit_float_bits(int value)
{
    u32 sign = 0, exponent = 127 + 23, mantissa;
    if (!value)
        return 0;
    if (value < 0) {
        sign = 0x80000000u;
        value = -value;
    }
    mantissa = value;
    while (mantissa < 1u << 23) {
        mantissa <<= 1;
        exponent--;
    }
    return sign | exponent << 23 | (mantissa & ((1u << 23) - 1));
}

u32 kit_group(u32 hash)
{
    u32 manager = *(u32 *)(gui_control + GUI_LAYOUTS), key[2] = {hash, 0};
    return group_at(manager, group_find(manager, key));
}

u32 *kit_sprite(struct ref *r, u32 group, u32 hash)
{
    u32 key[2] = {hash, 0};
    r->node = 0;
    if (group)
        group_sprite_ref(r, group, key);
    return r->node ? *(u32 **)(r->node + NODE_DATA) : 0;
}

u32 *kit_text(struct ref *r, u32 group, u32 hash)
{
    u32 key[2] = {hash, 0};
    r->node = 0;
    if (group)
        group_text_ref(r, group, key);
    return r->node ? *(u32 **)(r->node + NODE_DATA) : 0;
}

void kit_sprite_changed(const struct ref *r)
{
    u8 *dirty = *(u8 **)(r->node + NODE_DIRTY);
    if (dirty)
        dirty[DIRTY_MARK] = 3;
    else
        pane_redraw(r->group, (u32)r->node);
}

void kit_text_changed(const struct ref *r)
{
    u8 *holder = *(u8 **)(r->node + NODE_NEXT), *dirty = *(u8 **)(holder + NODE_DIRTY);
    if (dirty)
        dirty[DIRTY_MARK] = 3;
    else
        pane_redraw(r->group, (u32)holder);
}

u32 *kit_sprite_place(struct ref *r, u32 group, u32 hash, int x, int y, u32 w, u32 h)
{
    u32 *sprite = kit_sprite(r, group, hash);
    if (sprite) {
        sprite[SP_X] = kit_float_bits(HALF_WIDTH - x);
        sprite[SP_X + 1] = kit_float_bits(HALF_HEIGHT - y);
        sprite[SP_W] = kit_float_bits(w);
        sprite[SP_W + 1] = kit_float_bits(h);
        sprite[SP_FLAGS] |= SP_SHOWN;
    }
    return sprite;
}

void kit_sprite_hide(u32 group, u32 hash)
{
    struct ref r;
    u32 *sprite = kit_sprite(&r, group, hash);
    if (sprite && sprite[SP_FLAGS] & SP_SHOWN) {
        sprite[SP_FLAGS] &= ~SP_SHOWN;
        kit_sprite_changed(&r);
    }
}

void kit_sprite_colour(u32 *sprite, u32 colour)
{
    for (u32 i = 0; i < 4; i++)
        sprite[SP_COLOURS + i] = colour;
}

void kit_text_colour(u32 *text, u32 colour)
{
    for (u32 i = 0; i < 3; i++)      /* the fourth is the shadow's */
        text[TX_COLOURS + i] = colour;
}

void kit_text_hide(u32 group, u32 hash)
{
    struct ref r;
    u32 *text = kit_text(&r, group, hash);
    if (text) {
        text_show((u32)text, 0);
        kit_text_changed(&r);
    }
}

void kit_text_place(u32 *text, int x, int y, u32 w)
{
    u32 *holder = (u32 *)text[0];
    holder[0] = text[TX_X] = kit_float_bits(HALF_WIDTH - x);
    holder[1] = text[TX_X + 1] = kit_float_bits(HALF_HEIGHT - y);
    text[TX_W] = kit_float_bits(w);
}

void kit_group_show(u32 group, u32 shown, u32 priority)
{
    if (!group)
        return;
    gui_group_show(group, shown);
    if (shown)
        gui_group_order(group, GUI_LAYER, priority);
}

u32 kit_number_text(u16 *out, u32 value)
{
    static const u32 tens[] = {100000, 10000, 1000, 100, 10, 1};
    u32 length = 0;
    for (u32 i = 0; i < sizeof tens / sizeof tens[0]; i++) {
        u32 digit = 0;
        while (value >= tens[i]) {
            value -= tens[i];
            digit++;
        }
        if (digit || length || tens[i] == 1)
            out[length++] = '0' + digit;
    }
    out[length] = 0;
    return length;
}
