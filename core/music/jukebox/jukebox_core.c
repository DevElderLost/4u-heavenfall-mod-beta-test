/* The jukebox's state core, a unit of the resident block jukebox_save: what the
 * card's store and load (jukebox_save.c, run in the title, the town and a quest) reach: the defaults (jukebox_reset),
 * the owner's check (jukebox_owner), the load's end (jukebox_loaded) and the round's draw (jukebox_changed,
 * jukebox_draw_round, jukebox_random_below), with the playlist search the draw uses (jukebox_find_song), and the resume
 * list's lookup for the game's requests (jukebox_resume_game: FUN_0030ace0's answer while the town's pack, which holds
 * the block `jukebox`, is out). The town's block `jukebox` (jukebox.c, jukebox_menu.c) calls them; nothing here calls
 * it.
 *
 * Build: tools/build/build_code_space.py (devkitARM), which places and links it.
 */
#include "jukebox_lists.h"

extern u32 sound_driver;                        /* the variable holding the sound driver (blocks.py GAME_SYMBOLS) */
extern const u16 resume_list[];                 /* the requests with a resume position, 0xFFFF after the last */

#define W(p, off) (*(volatile u32 *)((u8 *)(p) + (off)))
#define DRIVER_CLOCK 0x933C                     /* u32: milliseconds */

/* FUN_0030ace0's own answer: the request's index in the resume list, or -1 */
int jukebox_resume_slot(int request)
{
    for (int i = 0; i < JUKEBOX_RESUME_ROOM && resume_list[i] != 0xFFFF; i++)
        if ((u32)resume_list[i] == (u32)request)
            return i;
    return -1;
}

/* FUN_0030ace0 for a game's request (jukebox_resume_index's answer for it, and the hook's while the town's pack is
 * out): its index, the slot cleared first when it held a jukebox song's position */
int jukebox_resume_game(u8 *manager, int request)
{
    int slot = jukebox_resume_slot(request);

    if (slot >= 0 && (S->resume_slots >> slot & 1)) {
        W(manager, JUKEBOX_RESUME_SLOTS + 8 * slot) = 0;
        W(manager, JUKEBOX_RESUME_SLOTS + 4 + 8 * slot) = 0xFFFFFFFF;
        S->resume_slots &= ~(1u << slot);
    }
    return slot;
}

/* a number below `n` (n >= 1): xorshift32, seeded from the sound driver's clock */
int jukebox_random_below(int n)
{
    u32 x = S->random;
    if (x == 0)
        x = (sound_driver ? W(sound_driver, DRIVER_CLOCK) : 0) ^ (S->generation * 0x9E3779B9u) ^ 0x2545F491u;
    if (x == 0)
        x = 1;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    S->random = x;
    return (int)(((unsigned long long)x * (u32)n) >> 32);
}

/* a new round of playlist `p`: in its order or shuffled; `first` (a track id) plays first when the playlist has it,
   else a shuffled round of two or more songs never starts with the song the last round ended on */
void jukebox_draw_round(const struct jukebox_playlist *p, int first)
{
    int n = songs_in(p), at = -1;
    for (int i = 0; i < n; i++)
        S->order[i] = (u8)i;
    if (p->order == JUKEBOX_SHUFFLE)
        for (int i = n - 1; i > 0; i--) {
            int j = jukebox_random_below(i + 1);
            u8 swap = S->order[i];
            S->order[i] = S->order[j];
            S->order[j] = swap;
        }
    for (int i = 0; i < n && at < 0; i++)
        if (p->songs[S->order[i]] == first)
            at = i;
    S->round_count = (u8)n;
    S->position = 0;
    if (at >= 0 && p->order != JUKEBOX_SHUFFLE) {
        S->position = (u8)at;
    } else {
        int swap_with = at;
        if (at < 0 && p->order == JUKEBOX_SHUFFLE && n >= 2 && p->songs[S->order[0]] == S->last_track)
            swap_with = 1 + jukebox_random_below(n - 1);
        if (swap_with > 0) {
            u8 swap = S->order[0];
            S->order[0] = S->order[swap_with];
            S->order[swap_with] = swap;
        }
    }
}

int jukebox_find_song(int list, int track)
{
    struct jukebox_playlist *p = playlist(list);
    for (int i = 0; p && i < songs_in(p); i++)
        if (p->songs[i] == track)
            return i;
    return -1;
}

void jukebox_changed(void)
{
    int active = S->save.options.active;
    struct jukebox_playlist *p = single() ? 0 : playlist(active - 1);
    if (!p) {
        S->round_list = 0;
        S->current = 0;
        S->current_track = JUKEBOX_NO_SONG;
        new_song();
        return;
    }
    int keep = S->round_list == active && S->current ? S->current_track : JUKEBOX_NO_SONG;
    if (keep != JUKEBOX_NO_SONG && jukebox_find_song(active - 1, keep) < 0)
        keep = JUKEBOX_NO_SONG;
    jukebox_draw_round(p, keep);
    S->round_list = (u8)active;
    if (keep == JUKEBOX_NO_SONG) {
        S->current = 0;
        S->current_track = JUKEBOX_NO_SONG;
        new_song();
    }
}

void jukebox_reset(void)
{
    volatile u8 *bytes = (u8 *)&S->save;        /* volatile: no memset call (no library is linked) */
    for (u32 i = 0; i < sizeof S->save; i++)
        bytes[i] = 0;
    S->save.magic = JUKEBOX_MAGIC;
    S->save.version = JUKEBOX_VERSION;
    S->save.options.active = 0;
    S->save.options.keep = D->defaults.keep;
    S->save.options.halls = D->defaults.halls;
    S->save.options.loops = D->defaults.loops;
    S->save.options.fade = D->defaults.fade;
    S->save.options.song = JUKEBOX_NO_SONG;
    S->listen = 0;
    jukebox_changed();
}

void jukebox_owner(const u8 *hunter_id)
{
    int same = S->owned;
    for (int i = 0; i < 8; i++)
        if (S->owner[i] != hunter_id[i])
            same = 0;
    if (same)
        return;
    jukebox_reset();
    for (int i = 0; i < 8; i++)
        S->owner[i] = hunter_id[i];
    S->owned = 1;
}

void jukebox_loaded(void)
{
    if (S->save.options.keep != JUKEBOX_ALWAYS)
        S->save.options.active = 0;
    jukebox_changed();
}
