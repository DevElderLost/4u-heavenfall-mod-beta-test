/* The playlists' small helpers that the engine (jukebox.c, the town's block `jukebox`) and the state's core
 * (jukebox_core.c, the resident block `jukebox_save`) both use: each is a few instructions, so each block holds its
 * own copy and neither calls the other for them. The bigger shared functions are jukebox_core.c's (jukebox.h).
 *
 * Build: tools/build/build_code_space.py (devkitARM), which places and links it.
 */
#ifndef JUKEBOX_LISTS_H
#define JUKEBOX_LISTS_H

#include "jukebox.h"

#define S (&jukebox_state)
#define D (&jukebox_data)

static inline int clamp(int value, int low, int high)
{
    return value < low ? low : value > high ? high : value;
}

static inline int list_count(void)
{
    return clamp(D->limits.playlists, 0, JUKEBOX_PLAYLISTS);
}

static inline int song_room(void)
{
    return clamp(D->limits.songs, 0, JUKEBOX_SONGS);
}

static inline struct jukebox_playlist *playlist(int list)
{
    return list >= 0 && list < list_count() ? &S->save.playlists[list] : 0;
}

static inline int songs_in(const struct jukebox_playlist *p)
{
    return p->count < song_room() ? p->count : song_room();
}

static inline int single(void)
{
    return S->save.options.active == JUKEBOX_SINGLE;
}

static inline void new_song(void)
{
    S->passes = 0;
    S->seen = 0;
    S->generation++;
}

#endif
