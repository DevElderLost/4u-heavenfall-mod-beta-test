#include "install.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef _WIN32
#include <direct.h>
#include <io.h>
#define MAKE_DIR(path) _mkdir(path)
#else
#define MAKE_DIR(path) mkdir(path, 0777)
#endif
#ifndef O_BINARY
#define O_BINARY 0
#endif

#define BLOCK (1024 * 1024)
#define PATH_LEN 512
#define MAX_DEPTH 16
#define REMOVE_PER_STEP 24 /* directory entries handled per step while removing a folder */

/* ---- CRC32 (slicing by 4: the byte-wise loop is slow on the old 3DS's 268 MHz) ---- */

static uint32_t crc_tables[4][256];

static void crc_init(void) {
    if (crc_tables[0][1])
        return;
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++)
            c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        crc_tables[0][i] = c;
    }
    for (uint32_t i = 0; i < 256; i++)
        for (int t = 1; t < 4; t++)
            crc_tables[t][i] = crc_tables[0][crc_tables[t - 1][i] & 0xFF] ^ (crc_tables[t - 1][i] >> 8);
}

static uint32_t crc_update(uint32_t crc, const unsigned char *data, size_t size) {
    crc = ~crc;
    for (; size >= 4; data += 4, size -= 4) {
        uint32_t word;
        memcpy(&word, data, 4); /* little endian on the 3DS and the PC */
        crc ^= word;
        crc = crc_tables[3][crc & 0xFF] ^ crc_tables[2][(crc >> 8) & 0xFF] ^ crc_tables[1][(crc >> 16) & 0xFF] ^
              crc_tables[0][crc >> 24];
    }
    while (size--)
        crc = crc_tables[0][(crc ^ *data++) & 0xFF] ^ (crc >> 8);
    return ~crc;
}

/* ---- Removing a folder a few entries at a time ---- */

typedef struct {
    DIR *dirs[MAX_DEPTH];
    char paths[MAX_DEPTH][PATH_LEN];
    int depth;
    int retries; /* a folder still holding entries when its listing ended (removed while listed): listed again */
} Remover;

static int remover_push(Remover *r, const char *path) {
    if (r->depth == MAX_DEPTH)
        return 0;
    if (!(r->dirs[r->depth] = opendir(path)))
        return 0;
    snprintf(r->paths[r->depth], PATH_LEN, "%s", path);
    r->depth++;
    return 1;
}

/* 1: there is work (call remover_step), 0: nothing to remove, -1: error */
static int remover_start(Remover *r, const char *path) {
    struct stat st;
    memset(r, 0, sizeof *r);
    if (stat(path, &st) != 0)
        return errno == ENOENT ? 0 : -1;
    if (!S_ISDIR(st.st_mode))
        return remove(path) == 0 ? 0 : -1;
    return remover_push(r, path) ? 1 : -1;
}

/* 1: more to do, 0: removed, -1: error */
static int remover_step(Remover *r) {
    for (int budget = REMOVE_PER_STEP; budget > 0 && r->depth > 0; budget--) {
        int top = r->depth - 1;
        struct dirent *entry = readdir(r->dirs[top]);
        char child[PATH_LEN];
        if (!entry) {
            closedir(r->dirs[top]);
            r->depth--;
            if (rmdir(r->paths[top]) != 0) {
                char again[PATH_LEN];
                snprintf(again, sizeof again, "%s", r->paths[top]);
                if (++r->retries > 32 || !remover_push(r, again))
                    return -1;
            }
            continue;
        }
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, ".."))
            continue;
        if (snprintf(child, sizeof child, "%s/%s", r->paths[top], entry->d_name) >= PATH_LEN)
            return -1;
        if (remove(child) != 0 && !remover_push(r, child)) /* not a file: a folder */
            return -1;
    }
    return r->depth > 0 ? 1 : 0;
}

static void remover_stop(Remover *r) {
    while (r->depth > 0)
        closedir(r->dirs[--r->depth]);
}

/* ---- The pack, read in blocks of 1 MB ---- */

struct Install {
    InstallStatus status;
    int fd;                 /* the pack */
    unsigned char *ahead;   /* BLOCK bytes read ahead for the small fields (names, sizes, CRCs) */
    size_t ahead_pos, ahead_len;
    unsigned char *block;
    char clean[256];        /* the title's folder, from the root */
    char root[PATH_LEN];
    char staging[PATH_LEN]; /* root + STAGING + "/" */
    Remover remover;
    int removing;           /* which folder the remover works on: 0 none, 1 STAGING, 2 TRASH */
    int sequence;           /* how many of the stage's two folders were started */
    int failed;             /* STAGE_UNDO ends in STAGE_FAILED */
    int out;                /* the file being written, or -1 */
    char name[PATH_LEN];
    uint64_t left;
    uint32_t crc;
};

static int read_all(Install *in, void *destination, size_t size) {
    unsigned char *out = destination;
    while (size > 0) {
        size_t have = in->ahead_len - in->ahead_pos;
        if (have > 0) {
            size_t take = have < size ? have : size;
            memcpy(out, in->ahead + in->ahead_pos, take);
            in->ahead_pos += take;
            out += take;
            size -= take;
        } else if (size >= BLOCK) {
            int got = read(in->fd, out, BLOCK);
            if (got <= 0)
                return 0;
            out += got;
            size -= (size_t)got;
        } else {
            int got = read(in->fd, in->ahead, BLOCK);
            if (got <= 0)
                return 0;
            in->ahead_pos = 0;
            in->ahead_len = (size_t)got;
        }
    }
    return 1;
}

static int read_uint(Install *in, uint64_t *value, int bytes) {
    unsigned char b[8];
    if (!read_all(in, b, (size_t)bytes))
        return 0;
    *value = 0;
    for (int i = bytes - 1; i >= 0; i--)
        *value = (*value << 8) | b[i];
    return 1;
}

static int write_all(int fd, const unsigned char *data, size_t size) {
    while (size > 0) {
        int put = write(fd, data, size);
        if (put <= 0)
            return 0;
        data += put;
        size -= (size_t)put;
    }
    return 1;
}

/* A path from the pack: under the title's folder, no "..", no character a FAT32 name cannot hold */
static int safe_path(const Install *in, const char *path) {
    size_t clean_len = strlen(in->clean);
    if (strncmp(path, in->clean, clean_len) != 0 || path[clean_len] != '/' || !path[clean_len + 1])
        return 0;
    for (const char *p = path; *p; p++)
        if (*p == '\\' || *p == ':' || *p == '*' || *p == '?' || *p == '"' || *p == '<' || *p == '>' || *p == '|')
            return 0;
    for (const char *p = path; (p = strstr(p, "..")) != NULL; p += 2)
        if ((p == path || p[-1] == '/') && (p[2] == '/' || p[2] == 0))
            return 0;
    return 1;
}

/* Make every folder of `full` after its first `keep` characters and before its last "/" */
static int make_parents(const char *full, size_t keep) {
    char buffer[PATH_LEN];
    snprintf(buffer, sizeof buffer, "%s", full);
    for (char *p = buffer + keep; *p; p++) {
        if (*p == '/') {
            *p = 0;
            if (MAKE_DIR(buffer) != 0 && errno != EEXIST)
                return 0;
            *p = '/';
        }
    }
    return 1;
}

static void close_output(Install *in) {
    if (in->out >= 0)
        close(in->out);
    in->out = -1;
}

static void set_error(Install *in, const char *format, const char *a, const char *b) {
    snprintf(in->status.error, sizeof in->status.error, format, a, b);
}

/* Remove a folder of ours (1 STAGING, 2 TRASH); returns 0 when it is gone */
static int start_removing(Install *in, int which) {
    char path[PATH_LEN];
    int started;
    if (which == 1)
        snprintf(path, sizeof path, "%s%s", in->root, STAGING);
    else
        snprintf(path, sizeof path, "%s%s", in->root, TRASH);
    started = remover_start(&in->remover, path);
    in->removing = started ? which : 0; /* kept on an error, to name the folder */
    return started;
}

/* Undo the copy: the staging folder goes, the old mod stays */
static void undo(Install *in, int failed) {
    close_output(in);
    remover_stop(&in->remover);
    in->failed = failed;
    in->status.stage = STAGE_UNDO;
    if (start_removing(in, 1) <= 0)
        in->status.stage = failed ? STAGE_FAILED : STAGE_CANCELLED;
}

/* Stop with an error; before the new mod is in place, the staging folder is removed and the old mod stays */
static void fail(Install *in, const char *format, const char *a, const char *b) {
    set_error(in, format, a, b);
    undo(in, 1);
}

Install *install_begin(const char *pack_file, const char *root, char *err, size_t err_size) {
    Install *in = calloc(1, sizeof *in);
    unsigned char magic[8];
    uint64_t version, count, total, clean_len;
    crc_init();
    if (!in || !(in->ahead = malloc(BLOCK)) || !(in->block = malloc(BLOCK))) {
        snprintf(err, err_size, "out of memory");
        if (in) {
            free(in->ahead);
            free(in);
        }
        return NULL;
    }
    in->out = -1;
    in->fd = -1;
    snprintf(in->root, sizeof in->root, "%s", root);
    snprintf(in->staging, sizeof in->staging, "%s%s/", root, STAGING);
    in->fd = open(pack_file, O_RDONLY | O_BINARY);
    if (in->fd < 0) {
        snprintf(err, err_size, "cannot open %s (%s)", pack_file, strerror(errno));
        install_end(in);
        return NULL;
    }
    if (!read_all(in, magic, 8) || memcmp(magic, "MH4UPACK", 8) != 0) {
        snprintf(err, err_size, "%s is not a mod pack", pack_file);
        install_end(in);
        return NULL;
    }
    if (!read_uint(in, &version, 4) || version != 1 || !read_uint(in, &count, 4) || !read_uint(in, &total, 8) ||
        !read_uint(in, &clean_len, 2) || clean_len >= sizeof in->clean || !read_all(in, in->clean, clean_len)) {
        snprintf(err, err_size, "%s: unknown or damaged header", pack_file);
        install_end(in);
        return NULL;
    }
    in->clean[clean_len] = 0;
    if (strncmp(in->clean, "luma/titles/", 12) != 0 || strlen(in->clean) <= 12 || strstr(in->clean, "..") ||
        strchr(in->clean + 12, '/')) {
        snprintf(err, err_size, "the pack's folder %s is not a title's folder in luma/titles/", in->clean);
        install_end(in);
        return NULL;
    }
    in->status.count = (uint32_t)count;
    in->status.total = total;
    in->status.stage = STAGE_LEFTOVERS;
    return in;
}

/* Copy: start the next file, or one block of the current one */
static void copy_step(Install *in) {
    if (in->out < 0) {
        uint64_t name_len, size;
        char full[PATH_LEN];
        if (in->status.files_done == in->status.count) {
            in->status.stage = STAGE_SWAP;
            return;
        }
        if (!read_uint(in, &name_len, 2) || name_len == 0 || name_len >= sizeof in->name ||
            !read_all(in, in->name, (size_t)name_len)) {
            fail(in, "the pack ends early or is damaged: was it sent in binary mode and in full?%s%s", "", "");
            return;
        }
        in->name[name_len] = 0;
        if (!safe_path(in, in->name)) {
            fail(in, "refused path in the pack: %s%s", in->name, "");
            return;
        }
        if (!read_uint(in, &size, 8)) {
            fail(in, "the pack ends early (%s): was it sent in full?", in->name, "");
            return;
        }
        snprintf(in->status.current, sizeof in->status.current, "%s", in->name + strlen(in->clean) + 1);
        if (snprintf(full, sizeof full, "%s%s", in->staging, in->name) >= PATH_LEN ||
            !make_parents(full, strlen(in->root)) ||
            (in->out = open(full, O_WRONLY | O_CREAT | O_TRUNC | O_BINARY, 0666)) < 0) {
            fail(in, "cannot write %s (%s)", in->name, strerror(errno));
            return;
        }
        in->left = size;
        in->crc = 0;
    }
    if (in->left > 0) {
        size_t want = in->left < BLOCK ? (size_t)in->left : BLOCK;
        if (!read_all(in, in->block, want)) {
            fail(in, "the pack ends early (%s): was it sent in binary mode and in full?", in->name, "");
            return;
        }
        if (!write_all(in->out, in->block, want)) {
            fail(in, "cannot write %s (is the SD card full?)", in->name, "");
            return;
        }
        in->crc = crc_update(in->crc, in->block, want);
        in->left -= want;
        in->status.done += want;
    }
    if (in->left == 0) {
        uint64_t stored;
        int closed = close(in->out);
        in->out = -1;
        if (closed != 0) {
            fail(in, "cannot write %s (is the SD card full?)", in->name, "");
            return;
        }
        if (!read_uint(in, &stored, 4) || (uint32_t)stored != in->crc) {
            fail(in, "%s is damaged in the pack (send it again, in binary mode)", in->name, "");
            return;
        }
        in->status.files_done++;
    }
}

/* The old title folder to TRASH, the new one from STAGING in its place */
static void swap(Install *in) {
    char final[PATH_LEN], trash[PATH_LEN], fresh[PATH_LEN];
    struct stat st;
    int had_old;
    snprintf(final, sizeof final, "%s%s", in->root, in->clean);
    snprintf(trash, sizeof trash, "%s%s", in->root, TRASH);
    snprintf(fresh, sizeof fresh, "%s%s", in->staging, in->clean);
    had_old = stat(final, &st) == 0;
    if (had_old && rename(final, trash) != 0) {
        fail(in, "cannot move the old mod out of %s (%s)", in->clean, strerror(errno));
        return;
    }
    if (!make_parents(final, strlen(in->root)) || rename(fresh, final) != 0) {
        fail(in, "cannot move the new mod into %s (%s)", in->clean, strerror(errno));
        if (had_old)
            rename(trash, final); /* the old mod back */
        return;
    }
    in->status.stage = STAGE_OLD;
}

InstallStage install_step(Install *in) {
    int r;
    switch (in->status.stage) {
    case STAGE_LEFTOVERS: /* STAGING then TRASH, then the copy */
    case STAGE_OLD:       /* TRASH then STAGING, then done */
        r = in->removing ? remover_step(&in->remover) : 0;
        while (r == 0 && in->sequence < 2) {
            int which = (in->status.stage == STAGE_LEFTOVERS) == (in->sequence == 0) ? 1 : 2;
            in->sequence++;
            r = start_removing(in, which); /* 0 when that folder is not there */
        }
        if (r < 0) {
            const char *what = in->removing == 2 ? TRASH : STAGING;
            remover_stop(&in->remover);
            in->removing = 0;
            if (in->status.stage == STAGE_OLD) { /* the new mod is in place: only a leftover folder stays */
                set_error(in, "installed, but %s could not be removed from the SD card%s", what, "");
                in->status.stage = STAGE_DONE;
            } else {
                fail(in, "cannot remove %s (left by an earlier run)%s", what, "");
            }
        } else if (r == 0) {
            in->removing = 0;
            in->sequence = 0;
            in->status.stage = in->status.stage == STAGE_LEFTOVERS ? STAGE_COPY : STAGE_DONE;
        }
        break;
    case STAGE_COPY:
        copy_step(in);
        break;
    case STAGE_SWAP:
        swap(in);
        break;
    case STAGE_UNDO:
        r = remover_step(&in->remover);
        if (r < 0) {
            remover_stop(&in->remover);
            in->status.stage = STAGE_FAILED;
            if (!in->failed)
                set_error(in, "cancelled, but %s could not be removed", STAGING, "");
        } else if (r == 0) {
            in->removing = 0;
            in->status.stage = in->failed ? STAGE_FAILED : STAGE_CANCELLED;
        }
        break;
    default:
        break;
    }
    return in->status.stage;
}

void install_cancel(Install *in) {
    if (in->status.stage == STAGE_LEFTOVERS || in->status.stage == STAGE_COPY)
        undo(in, 0);
}

const InstallStatus *install_status(const Install *in) {
    return &in->status;
}

const char *install_clean_path(const Install *in) {
    return in->clean;
}

void install_end(Install *in) {
    if (!in)
        return;
    close_output(in);
    remover_stop(&in->remover);
    if (in->fd >= 0)
        close(in->fd);
    free(in->ahead);
    free(in->block);
    free(in);
}
