/* The quest's layouts of our own (interface/quest_layouts/quest_layouts.py): the table quest_layouts_data names, per
feature, its frame function, the index of its group in the GUI
 * manager and its layout's path in core_quest.arc; quest_layouts_stub.s calls these three from the game's sites.
 *
 *   - quest_frame: sMhMain::frame, after every system's move and before the render: each feature's frame;
 *   - quest_load: FUN_00c1017c, with the quest's other layouts: each feature's layout, its groups created at its index
 *     on the top screen (as the target face's copy is loaded: face_loader.s);
 *   - quest_unload: FUN_00c0f110, leaving a quest or a menu: each feature's index freed (FUN_00b044f4 skips an empty
 *     slot).
 * An entry with no frame function is empty: the features a mod does not carry leave theirs so.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM; quest_layouts.ld).
 */

typedef unsigned int u32;

#define ENTRIES 4               /* quest_layouts.py ENTRIES */
#define PATH 24                 /* quest_layouts.py PATH: the path, NUL ended */
#define GUI_LAYOUTS 0x100       /* the GUI object -> its layout manager */
#define TOP_SCREEN 0
#define RESOURCE_GET 0x38       /* sResource's vtable: the load of a resource by its type and name */
#define HANDLE_NAME 8           /* a file handle: its name */

struct quest_layout {
    u32 frame;                  /* void (*)(void), 0: an empty entry */
    u32 index;                  /* its group's slot in the GUI manager */
    char path[PATH];            /* its layout in core_quest.arc, without the language */
};

struct quest_layouts {          /* the block quest_layouts_data (quest_layouts.py data_block) */
    struct quest_layout entry[ENTRIES];
};

_Static_assert(sizeof(struct quest_layouts) == 128, "blocks.py QUEST_LAYOUTS_DATA_SIZE");

extern const struct quest_layouts quest_layouts_data;
extern u32 resource_manager;    /* the variable holding sResource */
extern const char empty_name[];  /* the name a resource without one is asked by */
extern const u32 layout_dti[];   /* the layout resource's type */

void load_file(u32 loader, u32 *handle, const char *path, u32 language, u32 zero);     /* FUN_002b51c0 */
void create_groups(u32 gui, u32 screen, u32 index, u32 layout);                         /* FUN_00c0f474 */
void resource_release(u32 resource);                                                    /* FUN_00be2768 */
void free_group(u32 manager, u32 index);                                                /* FUN_00b044f4 */

typedef void (*frame_function)(void);
typedef u32 (*resource_get)(u32 manager, const u32 *type, const char *name, u32 flags);

#define W(p, off) (*(volatile u32 *)((p) + (off)))

void quest_frame(void)
{
    int i;

    for (i = 0; i < ENTRIES; i++)
        if (quest_layouts_data.entry[i].frame != 0)
            ((frame_function)quest_layouts_data.entry[i].frame)();
}

void quest_unload(u32 gui)
{
    u32 manager = gui != 0 ? W(gui, GUI_LAYOUTS) : 0;
    int i;

    if (manager == 0)
        return;
    for (i = 0; i < ENTRIES; i++)
        if (quest_layouts_data.entry[i].frame != 0)
            free_group(manager, quest_layouts_data.entry[i].index);
}

/* `loader` the file loader, `handle` the variable of FUN_00c1017c's frame its loads go through, `language` its own */
void quest_load(u32 gui, u32 loader, u32 *handle, u32 language)
{
    int i;

    quest_unload(gui);
    for (i = 0; i < ENTRIES; i++) {
        const struct quest_layout *entry = &quest_layouts_data.entry[i];
        u32 manager, layout;
        const char *name;

        if (entry->frame == 0)
            continue;
        load_file(loader, handle, entry->path, language, 0);
        manager = resource_manager;
        name = *handle != 0 ? (const char *)(*handle + HANDLE_NAME) : empty_name;
        layout = ((resource_get)W(W(manager, 0), RESOURCE_GET))(manager, layout_dti, name, 1);
        if (layout == 0)
            continue;
        create_groups(gui, TOP_SCREEN, entry->index, layout);
        resource_release(layout);
    }
}
