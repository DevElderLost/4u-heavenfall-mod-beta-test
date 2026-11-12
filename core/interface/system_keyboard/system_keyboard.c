/* Typing with the system keyboard (option system_keyboard; interface/system_keyboard/system_keyboard.py).
 *
 * system_keyboard_poll(manager) stands in for FUN_002b58e8, the game's poll of its own keyboard (the callers, 22 of
 * them, call it once a frame after FUN_002b5788 opened the keyboard). It runs the 3DS system keyboard, the library
 * applet 0x401, as the game runs its other applets (FUN_00578ee0, the Circle Pad Pro's): PrepareToStartLibraryApplet
 * (FUN_0056f340), StartLibraryApplet (FUN_0056ea78) with the applet's configuration and a memory block for the text,
 * and the wait for its answer (FUN_0010ab9c), which returns when the applet closes. The emulator shows its text box
 * and pauses the game meanwhile. The text goes to the manager's buffer, where the game's keyboard leaves it, and the
 * poll answers as the game's does: 1 a text, -1 cancelled or blank.
 *
 * The game's own keyboard answers instead (keyboard_poll_game, the game's poll) while the display is busy (the game
 * starts an applet only when FUN_00ad4ecc says it is not) or when the applet cannot be prepared: the player can always
 * type. The configuration and the memory block use the static buffer of the eShop's applet (FUN_00476b68, its only
 * user, which also blocks until its applet closes): its first page holds the configuration, the next the text.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with system_keyboard.ld where it places the block);
 * the game's functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef unsigned long long u64;

#define APPLET_KEYBOARD 0x401
#define PREPARED 0xC8A0CFFCu    /* FUN_0056f340's answer FUN_00578ee0 also goes on with */
#define PERM_RW 3
#define PAGE 0x1000
#define NONE 0xFFFFFFFFu        /* an offset of the shared memory that is not used */
#define CONFIG_VERSION 5        /* the configuration's version (the SDK's and libctru's) */

/* The keyboard manager (FUN_002b5788's first argument) */
#define M_KEYBOARD 0x2FBC       /* the game's keyboard, 0 without one */
#define M_OPEN 0x2FC0           /* u8: FUN_002b58e8 clears it, and sets it while the keyboard stays open */
#define M_MAX_LENGTH 0x2FC4     /* u32: the text's most characters (FUN_002b5788) */
#define M_TEXT 0x2FC8           /* u16[29]: the text the callers read (FUN_002afc2c), zeroed by FUN_002b5788 */
#define TEXT_ROOM 28            /* M_TEXT's characters before its terminator */
#define K_CONFIG 0x1C           /* the game keyboard's copy of its configuration (FUN_003acdd4): its type first */

/* The display (gx_main) and the main object (game_main): FUN_00ad4fa0 starts an applet only when neither says no */
#define DISPLAY_STATE 0x6BA8
#define DISPLAY_BUSY 0x10000000 /* FUN_00ad4ecc */
#define MAIN_BUSY 0x54          /* u8 */

#define BUTTONS_TWO 1           /* cancel and OK */
#define VALID_NOT_BLANK 2       /* not empty, not only spaces */
#define RESULT_OK 2             /* the second of two buttons */
#define TYPE_WESTERN 3          /* the last type of keyboard */

struct keyboard_config {        /* the applet's configuration, as the emulator reads it (SoftwareKeyboardConfig) */
    u32 type;
    u32 num_buttons_m1;
    u32 valid_input;
    u32 password_mode;
    s32 is_parental_screen;
    s32 darken_top_screen;
    u32 filter_flags;
    u32 save_state_flags;
    u16 max_text_length;        /* 0x20 */
    u16 dict_word_count;
    u16 max_digits;
    u16 button_text[3][17];
    u16 numpad_keys[2];
    u16 hint_text[65];          /* 0x90 */
    u8 predictive_input;        /* 0x112 */
    u8 multiline;
    u8 fixed_width;
    u8 allow_home;
    u8 allow_reset;
    u8 allow_power;
    u8 unknown;
    u8 default_qwerty;
    u8 button_submits_text[4];  /* 0x11A */
    u16 language;               /* 0x11E */
    u32 initial_text_offset;    /* 0x120 */
    u32 dict_offset;
    u32 initial_status_offset;
    u32 initial_learning_offset;
    u32 shared_memory_size;     /* 0x130 */
    u32 version;
    s32 return_code;            /* 0x138 */
    u32 status_offset;
    u32 learning_offset;
    u32 text_offset;            /* 0x144: bytes into the shared memory */
    u16 text_length;            /* 0x148: characters */
    u32 callback_result;
    u16 callback_msg[257];      /* 0x150 */
    u8 skip_at_check;           /* 0x352 */
    u8 padding[0xAB];
};

_Static_assert(sizeof(struct keyboard_config) == 0x400, "the applet reads 0x400 bytes");
_Static_assert(__builtin_offsetof(struct keyboard_config, max_text_length) == 0x20, "max_text_length");
_Static_assert(__builtin_offsetof(struct keyboard_config, predictive_input) == 0x112, "predictive_input");
_Static_assert(__builtin_offsetof(struct keyboard_config, button_submits_text) == 0x11A, "button_submits_text");
_Static_assert(__builtin_offsetof(struct keyboard_config, initial_text_offset) == 0x120, "initial_text_offset");
_Static_assert(__builtin_offsetof(struct keyboard_config, return_code) == 0x138, "system_keyboard.py");
_Static_assert(__builtin_offsetof(struct keyboard_config, text_offset) == 0x144, "system_keyboard.py");
_Static_assert(__builtin_offsetof(struct keyboard_config, text_length) == 0x148, "system_keyboard.py");
_Static_assert(__builtin_offsetof(struct keyboard_config, callback_msg) == 0x150, "callback_msg");

struct memory_block {           /* the SDK's memory block (FUN_0047ee44 fills it, FUN_0047eff4 closes it) */
    u32 unknown[2];
    void *address;              /* 8 */
    u32 size;                   /* 0xC */
    u32 unknown10;
    u32 handle;                 /* 0x14 */
    u8 mapped;                  /* 0x18: 0, the block is ours */
    u8 padding[7];
};

_Static_assert(__builtin_offsetof(struct memory_block, handle) == 0x14, "FUN_0047eff4 closes +0x14");

extern s32 apt_prepare_library_applet(u32 applet);
extern s32 apt_start_library_applet(u32 applet, void *parameter, u32 size, u32 handle);
extern s32 apt_receive_parameter(u32 *sender, void *parameter, u32 size, u32 *handle, u32 *signal, u32 flags,
                                 u64 wait);
extern s32 svc_create_memory_block(u32 *handle, void *address, u32 size, u32 own, u32 other);
extern void memory_block_close(struct memory_block *block);
extern s32 keyboard_poll_game(u8 *manager);   /* the game's poll (mod_options_stub.s) */
extern u8 eshop_applet_buffer[];
extern const u64 applet_wait_time;
extern u32 gx_main, game_main;

static void clear(void *at, u32 size)
{
    u8 *byte = at;

    while (size--)
        *byte++ = 0;
}

static int ready(void)
{
    if (gx_main == 0 || game_main == 0)
        return 0;
    if (*(const u32 *)(gx_main + DISPLAY_STATE) & DISPLAY_BUSY)
        return 0;
    return *(const u8 *)(game_main + MAIN_BUSY) == 0;
}

static void configure(struct keyboard_config *config, u32 type, u32 length)
{
    config->type = type <= TYPE_WESTERN ? type : 0;
    config->num_buttons_m1 = BUTTONS_TWO;
    config->valid_input = VALID_NOT_BLANK;
    config->max_text_length = length;
    config->button_submits_text[BUTTONS_TWO] = 1;
    config->initial_text_offset = NONE;
    config->dict_offset = NONE;
    config->initial_status_offset = NONE;
    config->initial_learning_offset = NONE;
    config->shared_memory_size = PAGE;
    config->version = CONFIG_VERSION;
    config->return_code = -1;
    config->status_offset = NONE;
    config->learning_offset = NONE;
    config->text_offset = 0;
}

/* The applet's answer into the manager's text: 1 a text, -1 cancelled or blank */
static int take_text(u8 *manager, const struct keyboard_config *config, const u8 *shared, u32 length)
{
    u16 *text = (u16 *)(manager + M_TEXT);
    const u16 *typed;
    u32 count, i;
    int words = 0;

    if (config->return_code != RESULT_OK || config->text_offset >= PAGE)
        return -1;
    typed = (const u16 *)(shared + (config->text_offset & ~1u));
    count = config->text_length;
    if (count > length)
        count = length;
    if (count > (PAGE - (config->text_offset & ~1u)) / 2)
        count = (PAGE - (config->text_offset & ~1u)) / 2;
    for (i = 0; i < count && typed[i] != 0; i++) {
        text[i] = typed[i];
        if (typed[i] != 0x20 && typed[i] != 0x3000)
            words = 1;
    }
    text[i] = 0;
    return words ? 1 : -1;
}

/* 1 or -1 as take_text, 0: the applet could not be prepared or started */
static int type_text(u8 *manager, u32 keyboard)
{
    struct keyboard_config *config = (struct keyboard_config *)eshop_applet_buffer;
    u8 *shared = eshop_applet_buffer + PAGE;
    struct memory_block block;
    u32 length = *(const u32 *)(manager + M_MAX_LENGTH);
    u32 sender = 0, handle = 0;
    s32 prepared;

    if (length == 0 || length > TEXT_ROOM)
        length = TEXT_ROOM;
    clear(eshop_applet_buffer, 2 * PAGE);
    configure(config, *(const u32 *)(keyboard + K_CONFIG), length);
    clear(&block, sizeof block);
    if (svc_create_memory_block(&block.handle, shared, PAGE, PERM_RW, PERM_RW) < 0)
        return 0;
    block.address = shared;
    block.size = PAGE;
    prepared = apt_prepare_library_applet(APPLET_KEYBOARD);
    if (prepared < 0 && (u32)prepared != PREPARED) {
        memory_block_close(&block);
        return 0;
    }
    if (apt_start_library_applet(APPLET_KEYBOARD, config, sizeof *config, block.handle) < 0) {
        memory_block_close(&block);     /* not started (FUN_0056ea78's 0xC8A0CC04): no answer will come */
        return 0;
    }
    apt_receive_parameter(&sender, config, sizeof *config, &handle, 0, 0, applet_wait_time);
    memory_block_close(&block);
    return take_text(manager, config, shared, length);
}

__attribute__((used, section(".text.entry"))) s32 system_keyboard_poll(u8 *manager)
{
    u32 keyboard = *(const u32 *)(manager + M_KEYBOARD);
    int typed;

    if (keyboard == 0 || !ready())
        return keyboard_poll_game(manager);
    typed = type_text(manager, keyboard);
    if (typed == 0)
        return keyboard_poll_game(manager);
    *(manager + M_OPEN) = 0;
    return typed;
}
