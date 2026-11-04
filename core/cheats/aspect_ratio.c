/* The shape of the emulator's picture (cheats/aspect_ratio.py): what the hooks of
 * aspect_stub.s ask.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with aspect_ratio.ld where it places the block).
 */

#define BOTTOM_SCREEN_VIEW 7    /* FUN_00aeee7c's view that draws on the bottom screen */
#define CAMERA_ASPECT 0x38      /* the camera's aspect, which uMhCamera's projection reads */
#define VIEW_SHORT_SIDE 240.0f  /* the whole top screen's view, turned as the hardware has it: the screen's height */
#define VIEW_LONG_SIDE 400.0f   /* and its width; the bottom screen's is 320 */
#define CENTRE_X 200
#define CENTRE_Y 120
#define PANEL_MINIMAP 5         /* FUN_00b972d8's panel kind of every map layout and icon */
#define GROUP_X 0x28            /* a GUI group's place */
#define GROUP_Y 0x2C

struct aspect_data {            /* aspect_ratio.py aspect_data */
    float view;                 /* a 3D view's aspect is multiplied by this */
    float gui_width, gui_height; /* the interface's units are multiplied by these */
};

struct rect {                   /* a sub-view's, in the top screen's pixels */
    int left, top, right, bottom;
};

extern const struct aspect_data aspect_data;
extern struct rect aspect_state;

/* FUN_00aeee7c's store of a view's aspect */
void aspect_store(float aspect, int view, char *camera)
{
    *(float *)(camera + CAMERA_ASPECT) = view == BOTTOM_SCREEN_VIEW ? aspect : aspect * aspect_data.view;
}

/* sizes: the s0, s1 FUN_00b70fc0 will get, the sides of the view's rectangle: s0 the screen's height, s1 its width. Only the
 * whole top screen changes: FUN_00af3db0 also serves the bottom screen and the sub-views */
void aspect_gui_sizes(float *sizes)
{
    if (sizes[0] == VIEW_SHORT_SIDE && sizes[1] == VIEW_LONG_SIDE) {
        sizes[0] *= aspect_data.gui_height;
        sizes[1] *= aspect_data.gui_width;
    }
}

/* FUN_00b972d8's store of a panel's place on the top screen. The minimap goes to its corner, the top right, of the wider
 * interface: a layout's x grows to the left and its y upwards. */
void aspect_panel_place(float x, float y, char *group, int kind)
{
    if (kind == PANEL_MINIMAP) {
        x -= CENTRE_X * (aspect_data.gui_width - 1.0f);
        y += CENTRE_Y * (aspect_data.gui_height - 1.0f);
    }
    *(float *)(group + GROUP_X) = x;
    *(float *)(group + GROUP_Y) = y;
}

static int moved(int at, int centre, float factor)
{
    return (int)((float)centre + (float)(at - centre) / factor + 0.5f);
}

/* The rectangle FUN_00aee0f0 is to read, which copies it: the same place of the interface, now that its units changed.
 * The game's own stays as it is: it may be a constant. */
const struct rect *aspect_rect(const struct rect *rect)
{
    aspect_state.left = moved(rect->left, CENTRE_X, aspect_data.gui_width);
    aspect_state.top = moved(rect->top, CENTRE_Y, aspect_data.gui_height);
    aspect_state.right = moved(rect->right, CENTRE_X, aspect_data.gui_width);
    aspect_state.bottom = moved(rect->bottom, CENTRE_Y, aspect_data.gui_height);
    return &aspect_state;
}
