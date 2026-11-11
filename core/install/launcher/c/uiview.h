/* What the launcher's two screens show (portable C99). The app's main thread fills
 * it (under the drawing lock, bumping `serial`); the drawing thread copies it under the lock and draws the copy, with
 * citro2d or, in the simple display mode, as text on the consoles (uitext.c, tested on the PC). Every text is UTF-8;
 * only the text drawer converts it to the console font (hf_cp437). */
#ifndef HF_UIVIEW_H
#define HF_UIVIEW_H

#include "uimodel.h"

#define HF_VIEW_BUTTONS 7   /* More's seven: four rows of the graphic layout, the simple display's rows 1-27 */
#define HF_VIEW_LABEL 64
#define HF_VIEW_LINE 192
#define HF_VIEW_ROWS 14
#define HF_VIEW_NOTES 4096

/* A line's colour, as the PC program's (core/gui/qt/theme.py, generated into the app's hf_tuning.h). */
typedef enum { HF_TONE_PLAIN = 0, HF_TONE_GOOD, HF_TONE_NEW, HF_TONE_WARN, HF_TONE_BAD, HF_TONE_MUTED } HfTone;

typedef enum {
    HF_SCREEN_HOME = 0,   /* top: heading, state line, detail, rows (versions), the notes' first lines; bottom: buttons */
    HF_SCREEN_MENU,       /* top: heading, state, detail and rows (a page's text or a table); bottom: a list of buttons */
    HF_SCREEN_NOTES,      /* top: the notes from notes_scroll on; bottom: buttons */
    HF_SCREEN_TASK        /* top: heading, the steps, the bar, the time left, a note; bottom: task.cancel and footer */
} HfScreen;

typedef struct {
    char label[HF_VIEW_LABEL];
    int id;                /* the caller's own id: given back when the button is chosen */
    int primary;           /* drawn as the big golden one */
    int enabled;           /* a disabled button is drawn muted and cannot be chosen */
} HfViewButton;

typedef struct {
    HfScreen screen;
    char heading[HF_VIEW_LABEL];               /* the edition's name, or the page's title */
    char state[HF_VIEW_LINE];                  /* the state line */
    HfTone tone;                               /* its colour */
    char detail[HF_VIEW_LINE];                 /* under it: what to do ("" none) */
    char rows[HF_VIEW_ROWS][HF_VIEW_LINE];     /* text lines; a '\t' splits a label from its value (a table) */
    int row_count;
    char notes_title[HF_VIEW_LABEL];           /* "What's new in 0.3.0" ("" no notes) */
    char notes[HF_VIEW_NOTES];                 /* plain lines, '\n' between (hf_notes_plain) */
    int notes_scroll;                          /* the first line shown */
    HfViewButton buttons[HF_VIEW_BUTTONS];
    int button_count;
    int selected;                              /* the button the D-pad is on */
    struct {
        char stage_names[HF_STAGES][HF_VIEW_LABEL];   /* Downloading, Installing, Finishing */
        int stage;                                    /* the one running (HF_STAGES: none yet) */
        unsigned permille;                            /* the bar */
        char eta[HF_VIEW_LABEL];                      /* "About 12 min left" */
        char note[HF_VIEW_LINE];                      /* a line under the bar (going on without MH XX...) */
        char cancel[HF_VIEW_LINE];                    /* what B does now, or that this step cannot be cancelled */
    } task;
    struct {
        int on;                                       /* drawn over the screen until the main thread clears it */
        char text[HF_VIEW_LINE * 2];
        char keys[HF_VIEW_LABEL];                     /* "A: yes   B: no" */
        HfTone tone;
    } message;
    char footer[HF_VIEW_LINE];                 /* the bottom screen's last line: "SELECT: Español   START: exit" */
    int busy;                                  /* a spinner beside the state line: something runs */
    unsigned serial;                           /* bumped by every change: the drawer skips frames that did not change */
} HfView;

#endif
