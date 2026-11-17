/* The jukebox's engine (music/jukebox/patch.py): a playlist plays in the villages
 * (and, with the option halls, in the halls) instead of their themes; the game's own code starts, stops and fades it.
 *
 *   - jukebox_pick, from FUN_00304990's exit (the town's theme selector; jukebox.s): the request of the playlist's song
 *     in place of a replaced place's request (jukebox_data.villages, .halls), when that request is in the loaded queue
 *     bgm_lob (strq_request); the request listened to in place of any place's. Command 2 of FUN_00302ba0 then starts
 *     it, and fades the old song out when the pick changes.
 *   - jukebox_command_pick, for command 2's first call of FUN_00304990: jukebox_tick, then that call. The tick first
 *     makes the copy the loaded hunter's (jukebox_check_owner, jukebox_save.c), then reads player 0's voice (its
 *     start serial and play position): a new serial starts the count again, a lower position on the same serial is a
 *     pass of its loop; at the option loops' passes it fades the song out over the option fade
 *     (music_stop) and moves the playlist on in the same frame, unless the playlist has one playable song. A song with
 *     no loop that reached its last second moves the playlist on when its record frees. In Dundorma's box (manager +
 *     0x1835) it sends the ambience's way out (str_map 0x33) once when the pick takes Dundorma's theme over.
 *   - jukebox_resume_index, FUN_0030ace0 (the resume list's lookup) replaced: the game's answer for the game's
 *     requests; for the song playing, the index of the place's request it replaced, so the game saves and seeks its
 *     position as a village theme's. A slot that held a jukebox song's position is cleared before another song or the
 *     place's own request uses it.
 *
 * The playlist plays in order or shuffled (a round with each song once; a round never starts with the song the last
 * one ended on); songs the build or the loaded queue lacks are skipped; with none playable the place keeps its theme.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM; jukebox.ld).
 */
#include "jukebox.h"

/* the game's functions and variables (blocks.py GAME_SYMBOLS) */
extern u32 sound_driver;                        /* the variable holding the sound driver */
extern const u16 resume_list[];                 /* the requests with a resume position, 0xFFFF after the last */
u32 strq_request(u32 handle, u32 request);      /* FUN_00cebbdc: the queue's record of the request, 0: none */
u32 stream_voice_newest(u32 driver, u32 handle, u32 request, int set);      /* FUN_00bd1580: 0 none */
u32 stream_voice_position(u32 driver, u32 handle, u32 request, int set);    /* FUN_00bd2ad0: samples */
void sound_request_play(u32 driver, u32 handle, u32 request, int set, int a, int b);     /* FUN_00bcacbc */
void music_stop(u8 *manager, u8 *record, int state, int ms);                /* FUN_003069e8 */
int town_theme(u8 *manager, int which);         /* FUN_00304990 */

#define W(p, off) (*(volatile u32 *)((u8 *)(p) + (off)))
#define B(p, off) (*(volatile u8 *)((u8 *)(p) + (off)))

/* the sound manager */
#define LOBBY_HANDLE 0x168C             /* u32: the queue bgm_lob */
#define STR_MAP_HANDLE 0x1688           /* u32: the area's ambience queue */
#define PLAYER0 0x169C                  /* player 0's record: +0 in use, +1 state, +4 queue, +8 request */
#define RECORD_STATE 1
#define RECORD_QUEUE 4
#define RECORD_REQUEST 8
#define PLAYING 0xC                     /* the record's state of a town theme */
#define STOPPING 0xD
#define LOBBY_QUEUE 6
#define BOX_FLAG 0x1835                 /* u8: Dundorma's box entered (FUN_00304080) */
#define RESUME_SLOTS 0x178C             /* + 8 n: slot n's flag, + 4 its position (-1: none) */
#define RESUME_ROOM 32                  /* slots the mask covers (the game's list has 19) */
#define DUNDORMA_THEME 0x32
#define BOX_WAY_OUT 0x33                /* str_map's request on leaving the box */
/* the sound driver */
#define DRIVER_CLOCK 0x933C             /* u32: milliseconds */
#define VOICE_SERIAL 0x30               /* a stream voice's start serial */
#define REQUEST_STREAM 0x60             /* a request's stream record: +8 samples, +0x10 rate, +0x1C loop end */
#define STREAM_SAMPLES 0x08
#define STREAM_RATE 0x10
#define STREAM_LOOP_END 0x1C
#define ANY_SET -1

#define S (&jukebox_state)
#define D (&jukebox_data)

static int clamp(int value, int low, int high)
{
    return value < low ? low : value > high ? high : value;
}

static int in_queue(u32 handle, u32 request)
{
    return handle != 0 && request != 0 && strq_request(handle, request) != 0;
}

static int track_request(int track)
{
    if (track < 0 || track >= D->tracks || track >= JUKEBOX_TRACK_ROOM)
        return 0;
    return D->requests[track] == JUKEBOX_NO_REQUEST ? 0 : D->requests[track];
}

static int listed(const u16 *list, int request)
{
    for (int i = 0; i < JUKEBOX_PLACES && list[i] != JUKEBOX_NO_REQUEST; i++)
        if (list[i] == request)
            return 1;
    return 0;
}

static int replaced(int request)
{
    return listed(D->villages, request) || (S->save.options.halls && listed(D->halls, request));
}

static int ours(int request)
{
    return request >= D->first_request && request <= D->last_request;
}

/* FUN_0030ace0's own answer: the request's index in the resume list, or -1 */
static int resume_slot(int request)
{
    for (int i = 0; i < RESUME_ROOM && resume_list[i] != 0xFFFF; i++)
        if ((u32)resume_list[i] == (u32)request)
            return i;
    return -1;
}

static int list_count(void)
{
    return clamp(D->limits.playlists, 0, JUKEBOX_PLAYLISTS);
}

static int song_room(void)
{
    return clamp(D->limits.songs, 0, JUKEBOX_SONGS);
}

static struct jukebox_playlist *playlist(int list)
{
    return list >= 0 && list < list_count() ? &S->save.playlists[list] : 0;
}

static int songs_in(const struct jukebox_playlist *p)
{
    return p->count < song_room() ? p->count : song_room();
}

static int loops(void)
{
    return clamp(S->save.options.loops, D->limits.loops_min > 0 ? D->limits.loops_min : 1, D->limits.loops_max);
}

static int fade_seconds(void)
{
    return clamp(S->save.options.fade, D->limits.fade_min, D->limits.fade_max);
}

/* a number below `n` (n >= 1): xorshift32, seeded from the sound driver's clock */
static int random_below(int n)
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
static void draw_round(const struct jukebox_playlist *p, int first)
{
    int n = songs_in(p), at = -1;
    for (int i = 0; i < n; i++)
        S->order[i] = (u8)i;
    if (p->order == JUKEBOX_SHUFFLE)
        for (int i = n - 1; i > 0; i--) {
            int j = random_below(i + 1);
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
            swap_with = 1 + random_below(n - 1);
        if (swap_with > 0) {
            u8 swap = S->order[0];
            S->order[0] = S->order[swap_with];
            S->order[swap_with] = swap;
        }
    }
}

static void new_song(void)
{
    S->passes = 0;
    S->seen = 0;
    S->generation++;
}

/* the active playlist's song in the loaded queue (`handle`): the one playing, or the next playable one from the
   round's position (a new round when this one ends); 0 when no song of the playlist is playable */
static int settle(u32 handle)
{
    int active = S->save.options.active;
    struct jukebox_playlist *p = playlist(active - 1);
    if (!p || !handle)
        return 0;
    if (S->round_list != active) {
        draw_round(p, JUKEBOX_NO_SONG);
        S->round_list = (u8)active;
        S->current = 0;
    }
    if (S->current && in_queue(handle, S->current))
        return S->current;
    int n = songs_in(p), any = 0;
    for (int i = 0; i < n && !any; i++)
        any = in_queue(handle, track_request(p->songs[i]));
    if (!any)
        return 0;
    for (int round = 0; round < 2; round++) {
        for (int i = S->position; i < S->round_count; i++) {
            int track = p->songs[S->order[i]], request = track_request(track);
            if (in_queue(handle, request)) {
                S->position = (u8)i;
                S->current = (u16)request;
                S->current_track = (u16)track;
                new_song();
                return request;
            }
        }
        if (S->current_track != JUKEBOX_NO_SONG)
            S->last_track = S->current_track;
        draw_round(p, JUKEBOX_NO_SONG);
    }
    return 0;
}

/* the playlist moves on: the next song of the round, or a new round */
static void move_on(void)
{
    struct jukebox_playlist *p = playlist(S->round_list - 1);
    S->last_track = S->current_track;
    S->position++;
    if (S->position >= S->round_count && p)
        draw_round(p, JUKEBOX_NO_SONG);
    S->current = 0;
    S->current_track = JUKEBOX_NO_SONG;
    new_song();
}

static int playable_songs(u32 handle)
{
    struct jukebox_playlist *p = playlist(S->save.options.active - 1);
    int n = 0;
    for (int i = 0; p && i < songs_in(p) && n < 2; i++)
        n += in_queue(handle, track_request(p->songs[i]));
    return n;
}

/* what the selector gives for a place's `request` */
static int wanted(u32 handle, int request)
{
    if (S->listen && in_queue(handle, S->listen))
        return S->listen;
    if (!replaced(request))
        return request;
    int song = settle(handle);
    return song ? song : request;
}

int jukebox_pick(u8 *manager, int request)
{
    if (request < 0)
        return request;
    int pick = wanted(W(manager, LOBBY_HANDLE), request);
    if (pick != request && pick == S->current) {
        S->place = (u16)request;
        S->place_index = (s8)resume_slot(request);
    }
    return pick;
}

void jukebox_tick(u8 *manager)
{
    jukebox_check_owner();
    u32 handle = W(manager, LOBBY_HANDLE);
    u8 *record = manager + PLAYER0;
    if (!B(manager, BOX_FLAG))
        S->box_sent = 0;
    if (!handle)
        return;
    if (B(manager, BOX_FLAG) && !S->box_sent && B(record, 0) && W(record, RECORD_REQUEST) == DUNDORMA_THEME
            && wanted(handle, DUNDORMA_THEME) != DUNDORMA_THEME) {
        sound_request_play(sound_driver, W(manager, STR_MAP_HANDLE), BOX_WAY_OUT, ANY_SET, 0, 0);
        S->box_sent = 1;
    }
    if (S->listen)
        return;
    int song = settle(handle);
    if (!song) {
        S->seen = 0;
        return;
    }
    if (!B(record, 0)) {
        if (S->seen == song && S->samples && S->last_position + S->rate >= S->samples)
            move_on();
        S->seen = 0;
        return;
    }
    if (B(record, RECORD_STATE) != PLAYING || B(record, RECORD_QUEUE) != LOBBY_QUEUE
            || W(record, RECORD_REQUEST) != (u32)song)
        return;
    u32 voice = stream_voice_newest(sound_driver, handle, song, ANY_SET);
    if (!voice)
        return;
    u32 serial = W(voice, VOICE_SERIAL);
    u32 position = stream_voice_position(sound_driver, handle, song, ANY_SET);
    if (S->seen != song || serial != S->serial) {
        u32 found = strq_request(handle, song), stream = found ? W(found, REQUEST_STREAM) : 0;
        S->seen = (u16)song;
        S->serial = serial;
        S->passes = 0;
        S->samples = stream && !W(stream, STREAM_LOOP_END) ? W(stream, STREAM_SAMPLES) : 0;
        S->rate = stream ? W(stream, STREAM_RATE) : 0;
    } else if (position < S->last_position && S->passes < 255) {
        S->passes++;
    }
    S->last_position = position;
    if (S->passes >= loops() && playable_songs(handle) >= 2) {
        int ms = fade_seconds() * 1000;
        music_stop(manager, record, STOPPING, ms > 0 ? ms : 1);
        move_on();
    }
}

__attribute__((section(".text.entry"))) int jukebox_command_pick(u8 *manager, int which)
{
    jukebox_tick(manager);
    return town_theme(manager, which);
}

static void clear_slot(u8 *manager, int slot)
{
    W(manager, RESUME_SLOTS + 8 * slot) = 0;
    W(manager, RESUME_SLOTS + 4 + 8 * slot) = 0xFFFFFFFF;
}

int jukebox_resume_index(u8 *manager, int request)
{
    if (!ours(request)) {
        int slot = resume_slot(request);
        if (slot >= 0 && (S->resume_slots >> slot & 1)) {
            clear_slot(manager, slot);
            S->resume_slots &= ~(1u << slot);
        }
        return slot;
    }
    int slot = S->place_index;
    if (request != S->current || slot < 0)
        return -1;
    if (S->resume_owner != S->generation) {
        for (int i = 0; i < RESUME_ROOM; i++)
            if (S->resume_slots >> i & 1)
                clear_slot(manager, i);
        S->resume_slots = 0;
        S->resume_owner = S->generation;
    }
    if (!(S->resume_slots >> slot & 1)) {
        clear_slot(manager, slot);
        S->resume_slots |= 1u << slot;
    }
    return slot;
}

/* ---- the menu's and the saving's calls ---- */

static void edited(int list)
{
    if (list + 1 == S->save.options.active)
        jukebox_changed();
}

const struct jukebox_playlist *jukebox_playlist(int list)
{
    return playlist(list);
}

int jukebox_find_song(int list, int track)
{
    struct jukebox_playlist *p = playlist(list);
    for (int i = 0; p && i < songs_in(p); i++)
        if (p->songs[i] == track)
            return i;
    return -1;
}

int jukebox_add_song(int list, int track)
{
    struct jukebox_playlist *p = playlist(list);
    if (!p || !track_request(track) || songs_in(p) >= song_room() || jukebox_find_song(list, track) >= 0)
        return 0;
    p->songs[songs_in(p)] = (u16)track;
    p->count = (u8)(songs_in(p) + 1);
    edited(list);
    return 1;
}

void jukebox_remove_song(int list, int index)
{
    struct jukebox_playlist *p = playlist(list);
    if (!p || index < 0 || index >= songs_in(p))
        return;
    int n = songs_in(p);
    for (int i = index; i + 1 < n; i++)
        p->songs[i] = p->songs[i + 1];
    p->songs[n - 1] = 0;
    p->count = (u8)(n - 1);
    edited(list);
}

void jukebox_move_song(int list, int from, int to)
{
    struct jukebox_playlist *p = playlist(list);
    if (!p || from < 0 || to < 0 || from >= songs_in(p) || to >= songs_in(p) || from == to)
        return;
    u16 song = p->songs[from];
    for (int i = from; i < to; i++)
        p->songs[i] = p->songs[i + 1];
    for (int i = from; i > to; i--)
        p->songs[i] = p->songs[i - 1];
    p->songs[to] = song;
    edited(list);
}

void jukebox_set_order(int list, int order)
{
    struct jukebox_playlist *p = playlist(list);
    if (!p)
        return;
    p->order = order == JUKEBOX_SHUFFLE ? JUKEBOX_SHUFFLE : JUKEBOX_IN_ORDER;
    edited(list);
}

void jukebox_clear(int list)
{
    struct jukebox_playlist *p = playlist(list);
    if (!p)
        return;
    volatile u8 *bytes = (u8 *)p;       /* volatile: no memset call (no library is linked) */
    for (u32 i = 0; i < sizeof *p; i++)
        bytes[i] = 0;
    edited(list);
}

void jukebox_rename(int list, const u16 *name, int length)
{
    struct jukebox_playlist *p = playlist(list);
    if (!p)
        return;
    for (int i = 0; i < JUKEBOX_NAME_CHARS; i++)
        p->name[i] = i < length && i < D->limits.name_chars ? name[i] : 0;
}

void jukebox_play(int list)
{
    if (!playlist(list))
        return;
    S->save.options.active = (u8)(list + 1);
    S->round_list = 0;
    S->current = 0;
    S->current_track = JUKEBOX_NO_SONG;
    new_song();
}

void jukebox_stop(void)
{
    S->save.options.active = 0;
    S->round_list = 0;
    S->current = 0;
    S->current_track = JUKEBOX_NO_SONG;
    new_song();
}

int jukebox_playing(void)
{
    return playlist(S->save.options.active - 1) ? S->save.options.active - 1 : -1;
}

int jukebox_option(int option)
{
    if (option == JUKEBOX_OPTION_HALLS)
        return S->save.options.halls;
    if (option == JUKEBOX_OPTION_KEEP)
        return S->save.options.keep;
    if (option == JUKEBOX_OPTION_LOOPS)
        return loops();
    if (option == JUKEBOX_OPTION_FADE)
        return fade_seconds();
    return 0;
}

void jukebox_set_option(int option, int value)
{
    if (option == JUKEBOX_OPTION_HALLS)
        S->save.options.halls = value ? 1 : 0;
    else if (option == JUKEBOX_OPTION_KEEP)
        S->save.options.keep = value ? JUKEBOX_ALWAYS : JUKEBOX_THIS_SESSION;
    else if (option == JUKEBOX_OPTION_LOOPS)
        S->save.options.loops = (u8)clamp(value, D->limits.loops_min, D->limits.loops_max);
    else if (option == JUKEBOX_OPTION_FADE)
        S->save.options.fade = (u8)clamp(value, D->limits.fade_min, D->limits.fade_max);
}

int jukebox_track_request(int track)
{
    return track_request(track);
}

int jukebox_listen(int track)
{
    S->listen = (u16)track_request(track);
    return S->listen != 0;
}

void jukebox_listen_stop(void)
{
    S->listen = 0;
}

void jukebox_changed(void)
{
    int active = S->save.options.active;
    struct jukebox_playlist *p = playlist(active - 1);
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
    draw_round(p, keep);
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
