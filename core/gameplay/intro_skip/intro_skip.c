/* START does what the touch screen's Skip does: a monster's intro cutscene, or a camera the game lets the player skip,
 * ends as when Skip is touched (option skip_monster_intro; gameplay/intro_skip/intro_skip.py).
 *
 * The touch menu bar (ui002; its object touch_bar) decides each frame what its six buttons are (FUN_00298640). While the
 * game offers a skip, its third button is Skip (kind 0xB) and touch_bar + 0xCF says which: 1 an event camera of the
 * camera manager that the game lets the player skip (FUN_00d0ccb4), 2 in a quest, a cutscene the event player lets the
 * player skip (FUN_001a1cb8: only a monster's intro, which FUN_001a0740 marks). FUN_002951fc, the bar's input, calls
 * the handler of that button once a frame, FUN_00292ea4(position, button, kind), which on a touch makes the skip after
 * the same checks again:
 *   1: FUN_00d0ccb4(sCamera) -> FUN_00bfd3f0(sCamera), which ends the camera;
 *   2: in a quest, FUN_001a1cb8(event) -> FUN_001a2d4c(event), the event player's request to skip (it takes it only
 *      with 70 frames or more left, and the player itself still refuses it where the game always plays the intro).
 *
 *   intro_skip_button(position, button, kind)   instead of that call (0x296114 in FUN_002951fc; through the START menu's
 *       gate gate_intro_skip, which makes the game's call while the option is off). It makes the game's call with its
 *       arguments first. Then, for the Skip button, in a quest, when START was pressed this frame (the pad's GUI
 *       buttons, the word the Game Menu copies), it makes the same calls as a touch of Skip, after the same checks, and
 *       keeps START out of the Game Menu for this frame and the next (death_camera_skip_state, which select_kick_gate
 *       in gameplay/select_kick/select_kick.c counts down, whichever of the two runs first in a frame). A bar that
 *       does not offer Skip (a story cutscene, the touch screen locked, a town) gets the game's call only.
 *
 * A skipped cutscene's music and sound: its two streams play on the
 * sound driver's voices of the event queues (bgm_ev_st, se_ev_st). While the event player skips (+0x17), its frame
 * (FUN_0019dfb8) calls FUN_0030cb5c(sound control) each frame, which fades only the streams the sound control still
 * keeps a player record of, by the record's request. The records' poller (FUN_00306e14) drops a record whenever
 * FUN_00bccca8 gives 0 for it, as it does for a voice not active yet: a stream without a record plays on into the
 * fight. Both entries take the call's argument, the sound control, and make the game's call first:
 *   intro_skip_music(sound)   instead of the skip's call of FUN_0030cb5c (0x19EADC; through gate_intro_music). Then
 *       the same fade-out (FUN_00bcac00, the same 1000) for every live voice of the two event queues, by the voice's own
 *       queue and request, record or not. The fight's music (bgm_bat, bgm_st) is on other queues: untouched.
 *   intro_skip_end(sound)     instead of the event's end's call of FUN_0030cd10 (0x19EDC0; through gate_intro_end).
 *       Then, when the event that ends was skipped (+0x17 is still set: FUN_0019d160 leaves it), the same fade-out
 *       once more, for a voice that started after the skip's last call (the jump to the motion's end comes after it).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with intro_skip.ld where it places the block); the
 * game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

/* The touch menu bar's object */
#define BAR_SKIP_OF       0xCF      /* u8: which skip its Skip button stands for */
#define SKIP_CAMERA       1         /* an event camera of the camera manager */
#define SKIP_CUTSCENE     2         /* a cutscene of the event player */
#define KIND_SKIP         0xB       /* a button's kind: Skip */

/* sGameControl, the variable game_control holds */
#define GAME_MODE         0x2B
#define MODE_QUEST        1

/* The pad object (*pad_control) */
#define PAD_GUI_PRESSED   0x348     /* u32: the GUI buttons pressed this frame */
#define GUI_START         0x400

#define START_FRAMES      2         /* this frame and the next: the menu's logic may run before or after the bar */

/* The event player (*event_control) */
#define EVENT_SKIPPING    0x17      /* u8: the event plays to its end as skipped (set from the request at + 0x18) */

/* The sound control (sSoundControl, the argument of both calls): the handles of the event player's two stream queues,
   FUN_00306d6c's queues 3 and 4, which FUN_002fb2b8 loads for each cutscene */
#define SOUND_EVENT_MUSIC 0x1680    /* bgm_ev_st: the cutscene's music */
#define SOUND_EVENT_SOUND 0x1684    /* se_ev_st: the cutscene's sounds */

/* The sound driver (*sound_driver): its stream voices, as FUN_00bccca8 reads them */
#define DRIVER_VOICES     0x5B98
#define DRIVER_VOICE_SIZE 0x3A8
#define DRIVER_VOICE_COUNT 0x900C   /* u32 */
#define VOICE_ACTIVE      0x4       /* u8: what FUN_00bccca8 returns for the voice */
#define VOICE_PHASE       0x5       /* u8 */
#define VOICE_QUEUE       0x8       /* u32: its queue's handle */
#define VOICE_REQUEST     0xC       /* u32: its request in the queue */
#define ANY_SET           0xFFFFFFFF  /* FUN_003069e8's set: any */
#define SKIP_FADE         1000      /* FUN_0030cb5c's fade-out of the event players */

extern u8 touch_bar[];                      /* the touch menu bar's object */
extern u8 *const game_control;              /* the variable holding sGameControl */
extern u8 *const pad_control;               /* the variable holding the pad object */
extern u8 *const camera_control;            /* the variable holding sCamera, the camera manager */
extern u8 *const event_control;             /* the variable holding the event player */
extern u8 *const sound_driver;              /* the variable holding the sound driver */
/* Frames left in which START belongs to a skip: select_kick_gate keeps it from opening the Game Menu */
extern volatile u32 death_camera_skip_state;

/* Game functions */
void touch_bar_button(u32 position, u32 button, u32 kind);  /* FUN_00292ea4: a bar button's frame (kinds 7, 8, 9, 0xB) */
u32 camera_skip_offered(u8 *camera);        /* FUN_00d0ccb4: an event camera the player may skip plays */
void camera_skip(u8 *camera);               /* FUN_00bfd3f0: ends it */
u32 event_skip_offered(u8 *event);          /* FUN_001a1cb8: a cutscene plays and the player may skip it */
void event_skip(u8 *event);                 /* FUN_001a2d4c: asks the event player to skip it */
void cutscene_sound_stop(u8 *sound);       /* FUN_0030cb5c: fades out the event players' streams, stops the sounds */
void event_sound_end(u8 *sound);            /* FUN_0030cd10: the sound control's part of an event's end */
/* FUN_00bcac00(driver, queue, request, set, fade, 0): fades a stream out (a command to the driver) */
void sound_fade_out(u8 *driver, u32 queue, u32 request, u32 set, u32 fade, u32 zero);

#define U32(p, off) (*(volatile u32 *)((p) + (off)))
#define U8(p, off)  (*(volatile u8 *)((p) + (off)))

/* What a touch of Skip does (FUN_00292ea4's end for kind 0xB), with its checks. Nonzero when it made the skip's call. */
static u32 skip_as_touched(void)
{
    u8 *camera = camera_control, *event = event_control;
    switch (U8(touch_bar, BAR_SKIP_OF)) {
    case SKIP_CAMERA:
        if (!camera || !camera_skip_offered(camera))
            return 0;
        camera_skip(camera);
        return 1;
    case SKIP_CUTSCENE:
        if (!event || !event_skip_offered(event))
            return 0;
        event_skip(event);
        return 1;
    }
    return 0;
}

__attribute__((used, section(".text.entry"))) void intro_skip_button(u32 position, u32 button, u32 kind)
{
    u8 *control, *pad;
    touch_bar_button(position, button, kind);
    control = game_control;
    pad = pad_control;
    if (kind != KIND_SKIP || !control || U8(control, GAME_MODE) != MODE_QUEST || !pad
        || !(U32(pad, PAD_GUI_PRESSED) & GUI_START))
        return;
    if (skip_as_touched())
        death_camera_skip_state = START_FRAMES;
}

/* Fades out every live voice of the event player's two stream queues, by its own queue and request. Live as FUN_00bccca8
   counts it: active and in another phase than 2, or not active yet in phase 1 or 5. */
static void stop_cutscene_voices(u8 *sound)
{
    u8 *driver = sound_driver, *voice;
    u32 music, sounds, queue, i, count;
    if (!sound || !driver)
        return;
    music = U32(sound, SOUND_EVENT_MUSIC);
    sounds = U32(sound, SOUND_EVENT_SOUND);
    count = U32(driver, DRIVER_VOICE_COUNT);
    for (i = 0; i < count; i++) {
        voice = driver + DRIVER_VOICES + i * DRIVER_VOICE_SIZE;
        if (U8(voice, VOICE_ACTIVE) ? U8(voice, VOICE_PHASE) == 2
                                    : U8(voice, VOICE_PHASE) != 1 && U8(voice, VOICE_PHASE) != 5)
            continue;
        queue = U32(voice, VOICE_QUEUE);
        if (queue && (queue == music || queue == sounds))
            sound_fade_out(driver, queue, U32(voice, VOICE_REQUEST), ANY_SET, SKIP_FADE, 0);
    }
}

void intro_skip_music(u8 *sound)
{
    cutscene_sound_stop(sound);
    stop_cutscene_voices(sound);
}

void intro_skip_end(u8 *sound)
{
    u8 *event = event_control;
    event_sound_end(sound);
    if (event && U8(event, EVENT_SKIPPING))
        stop_cutscene_voices(sound);
}
