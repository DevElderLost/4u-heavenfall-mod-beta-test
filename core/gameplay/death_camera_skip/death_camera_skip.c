/* START skips a slain monster's death camera (option skip_death_camera;
gameplay/death_camera_skip/death_camera_skip.py).
 *
 * The camera manager's frame (FUN_00c006f4) keeps two event camera slots. The death camera is a sequence of kind 0xD in
 * the second one, and while it plays the manager calls FUN_00c03d70(manager, slot, 1) once a frame (0xC00858). When that
 * call returns 0 the manager ends the camera by itself (0xC008F8): the slot is freed with its camera list and the
 * hunter's camera comes back.
 *
 *   death_camera_step(manager, slot, n)   instead of that call (through the START menu's gate gate_death_camera, which
 *       makes the game's call while the option is off). For a slot playing the death camera it keeps
 *       death_camera_skip_state at START_FRAMES, and when START was pressed this frame (the pad's GUI buttons, the ones
 *       the Game Menu reads) it returns 0 without the game's frame. Any other camera, or no START, gets the game's call.
 *
 * death_camera_skip_state tells select_kick_gate (gameplay/select_kick/select_kick.c), which runs in the Game Menu's
 * logic, that START belongs to the death camera: it keeps START from opening the menu and counts the state down, so the
 * press that ends the camera only ends it, whichever of the two runs first in a frame.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with death_camera_skip.ld where it places the
 * block); the game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

/* An event camera slot of the camera manager */
#define SLOT_KIND         0xCC      /* u8: the camera's kind */
#define KIND_DEATH        0xD       /* the monster's death camera */

/* The pad object (*pad_control) */
#define PAD_GUI_PRESSED   0x348     /* u32: the GUI buttons pressed this frame */
#define GUI_START         0x400

#define START_FRAMES      2         /* this frame and the next: the menu's logic may run before or after the camera */

extern u8 *const pad_control;               /* the variable holding the pad object */
extern volatile u32 death_camera_skip_state;

/* Game function */
u32 camera_play(u8 *manager, u8 *slot, u32 n);      /* FUN_00c03d70: one frame of an event camera, 0 when it is over */

#define U32(p, off) (*(volatile u32 *)((p) + (off)))
#define U8(p, off)  (*(volatile u8 *)((p) + (off)))

__attribute__((used, section(".text.entry"))) u32 death_camera_step(u8 *manager, u8 *slot, u32 n)
{
    u8 *pad = pad_control;
    if (U8(slot, SLOT_KIND) == KIND_DEATH) {
        death_camera_skip_state = START_FRAMES;
        if (pad && (U32(pad, PAD_GUI_PRESSED) & GUI_START))
            return 0;
    }
    return camera_play(manager, slot, n);
}
