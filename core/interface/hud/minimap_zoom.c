/* Minimap icons the placement functions do not project, for the HUD size option (interface/hud/code_patch.py).
 *
 * The map layouts are shrunk by data towards the map's top-right corner, and minimap_wrapper.s maps the projected
 * icons the same way: in the "128 u" / "128 v" units the placement functions use (the sprite gets 150 - X, 116 - Y),
 * X' = s X + 128 (1 - s), Y' = s Y. Two cases skip the projection, and this block maps them the same way:
 *
 * minimap_zoom: with the minimap zoomed on the current area (byte +0x129 of the HUD struct) the functions ask
 * FUN_005a5f14(area, &zoom, offset) for the area's zoom (a float) and offset (two shorts, x then y) and place an icon at
 *     X = offset[0] + 128 * (x * zoom + W/2) / W,   Y = offset[1] + 128 * (z * zoom + W/2) / W   (W = 20000).
 * Their eight calls of FUN_005a5f14 (the players', the monsters', the other icons' and the visible circle without the
 * Map item) are a `bl` to minimap_zoom, which calls it and returns
 *     zoom' = s zoom,   offset'[0] = s offset[0] + 64 (1 - s),   offset'[1] = s offset[1] - 64 (1 - s),
 * which gives those X' and Y'.
 *
 * minimap_point: in the Everwood (map 13) the whole-map view shows the players at a fixed point per area, which
 * FUN_005a7bec(out, area) writes as two integers X, Y over the projection (FUN_00b954ec). Its one call is a `bl` to
 * minimap_point, which calls it and returns s X + 128 (1 - s), s Y.
 *
 * The game's values are whole pixels (shorts, integers), so the results are rounded to the nearest one (at most half a
 * pixel off). `s` and 64 (1 - s) are the data block `minimap_zoom_data`, which the patcher fills.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with minimap_zoom.ld where it places the block);
 * the game functions are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef signed int s32;
typedef signed short s16;

struct minimap_zoom_data {
    float scale;
    float shift;
};

extern const struct minimap_zoom_data minimap_zoom_data;
extern void minimap_area_zoom(u32 area, float *zoom, s16 *offset);
extern void minimap_area_point(s32 *point, u32 area);

static s32 nearest(float value)
{
    return (s32)(value < 0.0f ? value - 0.5f : value + 0.5f);
}

__attribute__((used, section(".text.entry"))) void minimap_zoom(u32 area, float *zoom, s16 *offset)
{
    float scale = minimap_zoom_data.scale;
    float shift = minimap_zoom_data.shift;
    minimap_area_zoom(area, zoom, offset);
    *zoom *= scale;
    offset[0] = (s16)nearest(scale * offset[0] + shift);
    offset[1] = (s16)nearest(scale * offset[1] - shift);
}

void minimap_point(s32 *point, u32 area)
{
    float scale = minimap_zoom_data.scale;
    float shift = minimap_zoom_data.shift;
    minimap_area_point(point, area);
    point[0] = nearest(scale * point[0] + 2.0f * shift);
    point[1] = nearest(scale * point[1]);
}
