/* The launcher's drawing layer. The view (uiview.h) is drawn with citro2d
 * (ui_gpu.c) or, in the simple display mode, as text on the two consoles (ui_console.c over uitext.c), and the buttons
 * and the touch screen are queued as events. The main thread draws in its loops (app_loop: aptMainLoop each step, as
 * FBI does), so HOME finds no other thread on the GPU; while it blocks in long work (ui_work) a drawing thread draws
 * and reads the buttons instead (a key is seen, and dark screens wake, while AM blocks), and HOME is refused until the
 * next loop. The main thread changes the view between ui_begin and ui_end and takes the events with app_loop or
 * ui_next_event. */
#ifndef UI_H
#define UI_H

#include <3ds.h>

#include "uiview.h"

typedef struct {
    u32 keys;       /* the buttons pressed (hidKeysDown; the D-pad repeats while held), KEY_TOUCH for a touch; 0: none */
    int button;     /* the id of the view's button under the touch (enabled only), -1 for none */
    u64 ms;         /* osGetTime() when it came */
} UiEvent;

/* The start, after gfxInitDefault, romfsInit and log_open, on the main thread: the graphic display, or the simple one
 * when SELECT is held, when the last start's graphics never drew a frame (a marker file on the card), or when the
 * system font, citro3d, citro2d or the logo's texture fails; then the APT hook and the drawing thread. R held at the
 * start deletes the marker and tries the graphics again. The log says which and why. */
void ui_init(void);
/* The end: the screens on, the thread stopped, the GPU released. A second call does nothing; after it nothing is
 * drawn and no button is read. */
void ui_exit(void);

/* The view, locked for a change by the main thread: keep the time between the two short (no I/O). ui_end bumps its
 * serial, so the drawing thread draws it at its next frame. */
HfView *ui_begin(void);
void ui_end(void);

/* The next queued event: 1, or 0 when none is waiting (ev->keys 0, ev->button -1). */
int ui_next_event(UiEvent *ev);
/* The same, waiting up to `timeout_ms` for one. */
int ui_wait_event(UiEvent *ev, u32 timeout_ms);
/* Drops the queued events (a message waits only for keys pressed after it shows). */
void ui_flush_events(void);

/* aptMainLoop for a loop of its own (a long step's progress): the power button, sleep and the close answer (HOME too
 * outside long work); the drawing thread the APT hook stopped for a suspend or sleep starts again after it. 0 when the
 * app must close. */
int ui_apt(void);
/* The main thread's loop step: long work ends (the drawing thread stopped, HOME allowed), ui_apt, then the next event
 * within one input period, a frame drawn when due (ev->keys 0 when none came). 0 when the app must close. Replaces
 * aptMainLoop + hidScanInput + the frame. */
int app_loop(UiEvent *ev);
/* Long work begins (the main thread blocks: an install, a download, a save copy): the drawing thread draws and reads
 * the buttons, and HOME is refused until the next app_loop. A second call does nothing. */
void ui_work(void);

/* The screens' backlight (gsp::Lcd). While they are dark nothing is drawn, and the first key or touch only turns them
 * on (it is not queued). They come back on by themselves at HOME, sleep and the close, before every ui_message and
 * ui_confirm, and at ui_exit. */
void ui_screens(int on);
int ui_screens_on(void);
/* osGetTime() of the last key or touch (the idle timer's input). */
u64 ui_last_input_ms(void);

/* 1 in the simple display mode. */
int ui_simple(void);

/* A short chime (romfs:/chime.wav, 16-bit mono PCM) through the DSP, blocking while it plays (under a second);
 * nothing when the DSP cannot start (no dspfirm.cdc on the card). */
void ui_chime(void);

#endif
