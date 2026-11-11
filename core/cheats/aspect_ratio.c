/* The shape of the emulator's picture (cheats/aspect_ratio.py): what the hooks of
 * aspect_stub.s ask. The ratio is read each time, so a choice in the game's list (interface/mod_settings/aspect_list.c)
 * shows at once: the byte of the character's save zone, else the installer's.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with aspect_ratio.ld where it places the block).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define MAX_RATIOS 8
#define SAVE_DATA 0x5C          /* the save object's data starts here */
#define ZONE_WORDS 12           /* the save zone's size (curated mod_settings.json) */
#define ZONE_VERSION 4          /* its u16 */
#define ZONE_ASPECT 9           /* its u8: 0 the installer's ratio, else its place + 1 */
#define HUD_CODES 16            /* interface/hud/anchors.py hud_code: an entry from here on is the HUD's */
#define CORNER_CODES 32         /* anchors.py corner_code: from here on, a corner the data names, from the game's frame */
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
#define GROUP_SECOND_Y 0x38
#define GROUP_FIRST_PANE 0x08
#define PANE_DATA 0x08          /* a run-time pane: its data, which holds a null's place first */
#define PANE_KIND 0x10
#define PANE_FIRST_CHILD 0x20
#define KIND_NULL 1
#define NULL_SCALE_X 0x10
#define CONTEXT_VIEW 0x1BC      /* the draw's context: eye | view << 1 */
#define TOP_SCREEN_VIEW 0
#define FRAME_WIDTH 400.0f
#define SIDE_LEFT (-1)
#define SIDE_CENTRE 0
#define SIDE_RIGHT 1

struct ratio {
    float view;                 /* a 3D view's aspect is multiplied by this */
    float gui_width, gui_height; /* the interface's units are multiplied by these */
};

struct aspect_data {            /* aspect_ratio.py aspect_data */
    u32 zone_at;                /* the save zone in the save data */
    u32 magic;                  /* what marks it written */
    u8 fallback;                /* the installer's ratio, by place: what the files were fitted to */
    u8 count;
    u16 version;                /* the zone's */
    float edge_margin, half_margin, dead_zone; /* interface/hud/anchors.py AnchorRules */
    float sub_view_margin;      /* a sub-view this close to the frame's side goes to it, with its frame */
    struct ratio ratios[MAX_RATIOS];
};

struct anchor {                 /* interface/hud/anchors.py anchor_table */
    unsigned hash;              /* the root group's name */
    short low, high;            /* its box in the frame's pixels at a translate of 0; twice one number: that side, or
                                   from HUD_CODES on the HUD's anchor, whose files are fitted to the installer's ratio,
                                   or from CORNER_CODES on a corner's, whose files are the game's */
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
extern float aspect_way;        /* what game_gui_engine.c adds to a place at the side: the way past the installer's */
extern u32 save_control;        /* the variable holding the save object */

/* The save zone of the character in play, 0 without a save */
static u8 *save_zone(void)
{
    return save_control != 0 ? (u8 *)save_control + SAVE_DATA + aspect_data.zone_at : 0;
}

int aspect_saved(void)
{
    return save_zone() != 0;
}

int aspect_ratios(void)
{
    return aspect_data.count;
}

/* The ratio in use, by place */
int aspect_selected(void)
{
    const u8 *zone = save_zone();

    if (zone != 0 && *(const u32 *)zone == aspect_data.magic) {
        int chosen = zone[ZONE_ASPECT];

        if (chosen != 0 && chosen <= aspect_data.count)
            return chosen - 1;
    }
    return aspect_data.fallback;
}

/* The game's list: this character's ratio from now on, the next frame's picture. A new character's zone is zeros */
void aspect_choose(int place)
{
    u8 *zone = save_zone();
    int word;

    if (zone == 0)
        return;
    if (*(u32 *)zone != aspect_data.magic) {
        for (word = 0; word < ZONE_WORDS; word++)
            ((u32 *)zone)[word] = 0;
        *(u32 *)zone = aspect_data.magic;
        *(u16 *)(zone + ZONE_VERSION) = aspect_data.version;
    }
    zone[ZONE_ASPECT] = place + 1;
}

static const struct ratio *in_use(void)
{
    return &aspect_data.ratios[aspect_selected()];
}

static const struct ratio *installed(void)
{
    return &aspect_data.ratios[aspect_data.fallback];
}

/* FUN_00aeee7c's store of a view's aspect */
void aspect_store(float aspect, int view, char *camera)
{
    *(float *)(camera + CAMERA_ASPECT) = view == BOTTOM_SCREEN_VIEW ? aspect : aspect * in_use()->view;
}

/* sizes: the s0, s1 FUN_00b70fc0 will get, the sides of the view's rectangle: s0 the screen's height, s1 its width. Only the
 * whole top screen changes: FUN_00af3db0 also serves the bottom screen and the sub-views */
void aspect_gui_sizes(float *sizes)
{
    if (sizes[0] == VIEW_SHORT_SIDE && sizes[1] == VIEW_LONG_SIDE) {
        const struct ratio *ratio = in_use();

        sizes[0] *= ratio->gui_height;
        sizes[1] *= ratio->gui_width;
        aspect_way = CENTRE_X * (ratio->gui_width - installed()->gui_width);
    }
}

/* FUN_00b972d8's store of a panel's place on the top screen. The minimap goes to its corner, the top right, of the wider
 * interface: a layout's x grows to the left and its y upwards. */
void aspect_panel_place(float x, float y, char *group, int kind)
{
    if (kind == PANEL_MINIMAP) {
        const struct ratio *ratio = in_use();

        x -= CENTRE_X * (ratio->gui_width - 1.0f);
        y += CENTRE_Y * (ratio->gui_height - 1.0f);
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

/* The side of a group the code moves by writing its first nulls (interface/hud/anchors.py follow_nulls): `low` and
 * `high` are the box under them with them at 0, `x` the group's translate. The walk stops at the first pane that is no
 * null, whose data has another shape. */
static int side_under_nulls(const char *group, float x, float low, float high)
{
    const char *pane = *(const char *const *)(group + GROUP_FIRST_PANE);
    float scale = 1.0f;

    while (pane != 0 && pane[PANE_KIND] == KIND_NULL) {
        const char *data = *(const char *const *)(pane + PANE_DATA);

        x += scale * *(const float *)data;
        scale *= *(const float *)(data + NULL_SCALE_X);
        pane = *(const char *const *)(pane + PANE_FIRST_CHILD);
    }
    return side_of(CENTRE_X - x - scale * (CENTRE_X - low), CENTRE_X - x - scale * (CENTRE_X - high));
}

/* The anchor's signs of a HUD or corner code (anchors.py hud_code, corner_code): x in bits 2-3, y in bits 0-1, each + 1 */
static int code_bits(int code)
{
    return code >= CORNER_CODES ? code - CORNER_CODES : code - HUD_CODES;
}

/* The interface's width and height its files were fitted to: the installer's ratio for the HUD's, the game's frame (1)
 * for a corner's */
static float fitted_width(int code)
{
    return code >= CORNER_CODES ? 1.0f : installed()->gui_width;
}

static float fitted_height(int code)
{
    return code >= CORNER_CODES ? 1.0f : installed()->gui_height;
}

/* FUN_00ae65f8's load of a group's second translate, which it adds to the group's place as it draws the group: that
 * translate, with the group's way to its side of the wider interface. A layout's x grows to the left, a pixel's to the
 * right. The side counts where the game has the group now, so a group the code moves to the other column follows it. The
 * HUD's files are at their sides of the installer's ratio: it takes the way from there; a corner's are the game's. */
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
    if (anchor->low == anchor->high && anchor->low >= HUD_CODES)
        return second + (float)((code_bits(anchor->low) >> 2) - 1) * CENTRE_X
            * (in_use()->gui_width - fitted_width(anchor->low));
    if (anchor->low == anchor->high) {
        side = anchor->low;
    } else {
        float translate = *(const float *)(group + GROUP_X) + second;

        side = anchor->low > anchor->high
            ? side_under_nulls(group, translate, (float)anchor->high, (float)anchor->low)
            : side_of((float)anchor->low - translate, (float)anchor->high - translate);
    }
    return second - (float)side * CENTRE_X * (in_use()->gui_width - 1.0f);
}

/* The same load of the second translate's y: only the HUD and the corners keep to the top and the bottom of a taller
 * interface. A layout's y grows upwards. */
float aspect_group_y(const char *group, const char *context)
{
    float second = *(const float *)(group + GROUP_SECOND_Y);
    const struct anchor *anchor;

    if (((*(const unsigned *)(context + CONTEXT_VIEW) >> 1) & 0x1F) != TOP_SCREEN_VIEW)
        return second;
    anchor = find_anchor(*(const unsigned *)group);
    if (!anchor || anchor->low != anchor->high || anchor->low < HUD_CODES)
        return second;
    return second + (float)((code_bits(anchor->low) & 3) - 1) * CENTRE_Y
        * (in_use()->gui_height - fitted_height(anchor->low));
}

static int moved(float at, int centre, float factor)
{
    return (int)((float)centre + (at - (float)centre) / factor + 0.5f);
}

/* The rectangle FUN_00aee0f0 is to read, which copies it: the same place of the interface, now that its units changed and
 * the frame around it went to its side. The game's own stays as it is: it may be a constant. */
const struct rect *aspect_rect(const struct rect *rect)
{
    const struct ratio *ratio = in_use();
    int left = (float)rect->left <= aspect_data.sub_view_margin;
    int right = (float)rect->right >= FRAME_WIDTH - aspect_data.sub_view_margin;
    float shift = (float)(right - left) * CENTRE_X * (ratio->gui_width - 1.0f);

    aspect_state.left = moved((float)rect->left + shift, CENTRE_X, ratio->gui_width);
    aspect_state.top = moved((float)rect->top, CENTRE_Y, ratio->gui_height);
    aspect_state.right = moved((float)rect->right + shift, CENTRE_X, ratio->gui_width);
    aspect_state.bottom = moved((float)rect->bottom, CENTRE_Y, ratio->gui_height);
    return &aspect_state;
}
