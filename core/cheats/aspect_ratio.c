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
#define GROUP_SECOND_X 0x34     /* the second translate FUN_00ae65f8 adds to the place */
#define CONTEXT_VIEW 0x1BC      /* the draw's context: eye | view << 1 */
#define TOP_SCREEN_VIEW 0
#define FRAME_WIDTH 400.0f
#define SIDE_LEFT (-1)
#define SIDE_CENTRE 0
#define SIDE_RIGHT 1

struct aspect_data {            /* aspect_ratio.py aspect_data */
    float view;                 /* a 3D view's aspect is multiplied by this */
    float gui_width, gui_height; /* the interface's units are multiplied by these */
    float edge_margin, half_margin, dead_zone; /* interface/hud/anchors.py AnchorRules */
    int sub_views;              /* a sub-view follows the frame around it */
};

struct anchor {                 /* interface/hud/anchors.py anchor_table */
    unsigned hash;              /* the root group's name */
    short low, high;            /* its box in the frame's pixels at a translate of 0; twice one number: that side */
};

struct anchors {
    unsigned count;
    struct anchor entries[];    /* sorted by hash */
};

struct rect {                   /* a sub-view's, in the top screen's pixels */
    int left, top, right, bottom;
};

extern const struct aspect_data aspect_data;
extern const struct anchors aspect_anchors;
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

/* The side a box from `low` to `high` pixels of the 400 wide frame keeps to: the rule of interface/hud/anchors.py side_of */
static int side_of(float low, float high)
{
    float centre;

    if (low <= aspect_data.edge_margin && high >= FRAME_WIDTH - aspect_data.edge_margin)
        return SIDE_CENTRE;
    if (high <= CENTRE_X + aspect_data.half_margin)
        return SIDE_LEFT;
    if (low >= CENTRE_X - aspect_data.half_margin)
        return SIDE_RIGHT;
    centre = (low + high) * 0.5f - CENTRE_X;
    if (centre < -aspect_data.dead_zone)
        return SIDE_LEFT;
    return centre > aspect_data.dead_zone ? SIDE_RIGHT : SIDE_CENTRE;
}

static const struct anchor *find_anchor(unsigned hash)
{
    unsigned low = 0, high = aspect_anchors.count;

    while (low < high) {
        unsigned middle = low + (high - low) / 2;
        unsigned found = aspect_anchors.entries[middle].hash;

        if (found == hash)
            return &aspect_anchors.entries[middle];
        if (found < hash)
            low = middle + 1;
        else
            high = middle;
    }
    return 0;
}

/* FUN_00ae65f8's load of a group's second translate, which it adds to the group's place as it draws the group: that
 * translate, with the group's way to its side of the wider interface. A layout's x grows to the left, a pixel's to the
 * right. The side counts where the game has the group now, so a group the code moves to the other column follows it. */
float aspect_group_x(const char *group, const char *context)
{
    float second = *(const float *)(group + GROUP_SECOND_X);
    const struct anchor *anchor;
    int side;

    if (((*(const unsigned *)(context + CONTEXT_VIEW) >> 1) & 0x1F) != TOP_SCREEN_VIEW)
        return second;
    anchor = find_anchor(*(const unsigned *)group);
    if (!anchor)
        return second;
    if (anchor->low == anchor->high) {
        side = anchor->low;
    } else {
        float translate = *(const float *)(group + GROUP_X) + second;

        side = side_of((float)anchor->low - translate, (float)anchor->high - translate);
    }
    return second - (float)side * CENTRE_X * (aspect_data.gui_width - 1.0f);
}

static int moved(float at, int centre, float factor)
{
    return (int)((float)centre + (at - (float)centre) / factor + 0.5f);
}

/* The rectangle FUN_00aee0f0 is to read, which copies it: the same place of the interface, now that its units changed and
 * the frame around it went to its side. The game's own stays as it is: it may be a constant. */
const struct rect *aspect_rect(const struct rect *rect)
{
    float shift = 0.0f;

    if (aspect_data.sub_views)
        shift = (float)side_of((float)rect->left, (float)rect->right) * CENTRE_X * (aspect_data.gui_width - 1.0f);
    aspect_state.left = moved((float)rect->left + shift, CENTRE_X, aspect_data.gui_width);
    aspect_state.top = moved((float)rect->top, CENTRE_Y, aspect_data.gui_height);
    aspect_state.right = moved((float)rect->right + shift, CENTRE_X, aspect_data.gui_width);
    aspect_state.bottom = moved((float)rect->bottom, CENTRE_Y, aspect_data.gui_height);
    return &aspect_state;
}
