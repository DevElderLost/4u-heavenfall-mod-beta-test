/* A GitHub release as the launcher reads it (portable C99): the releases/latest answer, the versions, the PC updater's
 * rules (core/install/self_update.py, `Release.asset` and `latest_release`): the tag (`v` optional) is a version, an
 * asset is taken by its exact name, its `digest` (sha256) and `size` are required and its download URL must be
 * https://github.com/<repository>/releases/download/... */
#ifndef HF_RELEASE_H
#define HF_RELEASE_H

#include <stddef.h>
#include <stdint.h>

#define HF_MAX_WANTED 8      /* assets looked for in one release */
#define HF_NAME_MAX 96
#define HF_URL_MAX 400
#define HF_TAG_MAX 48

enum {
    HF_REL_OK = 0,
    HF_REL_BAD_ANSWER = -20,  /* not the JSON of a release */
    HF_REL_BAD_TAG = -21,     /* the tag is not a version */
    HF_REL_NO_DIGEST = -22,   /* a wanted asset without a sha256 digest */
    HF_REL_BAD_URL = -23,     /* a wanted asset whose URL is not the repository's own https release download */
    HF_REL_MANY = -24         /* two assets with the same wanted name */
};

typedef struct {
    int found;
    char name[HF_NAME_MAX];
    char url[HF_URL_MAX];
    uint64_t size;
    uint8_t sha256[32];
} HfAsset;

typedef struct {
    char tag[HF_TAG_MAX];
    HfAsset assets[HF_MAX_WANTED];  /* one per wanted name, in the order asked */
} HfRelease;

/* Reads the releases/latest JSON of `repository` ("<owner>/<name>"). `wanted` are exact asset names; one that the
 * release lacks has found == 0 (the caller decides whether that matters); a found one passed every rule above. `out` is
 * cleared first. `notes` (NULL: not wanted) gets the release's text ("body"), cut at a whole UTF-8 letter to fit
 * `notes_cap` with its terminator ("" for a release without one). */
int hf_release_parse(const char *json, size_t len, const char *repository, const char *const *wanted, int nwanted,
                     HfRelease *out, char *notes, size_t notes_cap);

/* "v0.1.2" or "0.1.2" as numbers, trailing zeros dropped (1.2 and 1.2.0 are one version); 0 on success, -1 otherwise. */
#define HF_VERSION_PARTS 8
int hf_version_parse(const char *text, uint32_t parts[HF_VERSION_PARTS], int *count);
/* 1 when `latest` is newer than `current`, 0 when not, -1 when either is no version. */
int hf_version_newer(const char *latest, const char *current);

/* 1 when the URL starts with "https://" (what a redirect may lead to). */
int hf_url_is_https(const char *url);

#endif
