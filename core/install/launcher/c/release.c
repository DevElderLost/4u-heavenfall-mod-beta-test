/* See release.h. */
#include "release.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "json.h"

#define MAX_TOKENS 6000  /* a release with a hundred assets is about 3000 tokens */

int hf_url_is_https(const char *url) {
    return strncmp(url, "https://", 8) == 0;
}

int hf_version_parse(const char *text, uint32_t parts[HF_VERSION_PARTS], int *count) {
    int n = 0;
    const char *p = text;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')
        p++;
    if (*p == 'v')
        p++;
    for (;;) {
        uint64_t v = 0;
        int digits = 0;
        while (*p >= '0' && *p <= '9') {
            v = v * 10 + (uint64_t)(*p++ - '0');
            if (++digits > 9)
                return -1;
        }
        if (!digits || n >= HF_VERSION_PARTS)
            return -1;
        parts[n++] = (uint32_t)v;
        if (*p == '.') {
            p++;
            continue;
        }
        break;
    }
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')
        p++;
    if (*p)
        return -1;
    while (n > 1 && parts[n - 1] == 0)
        n--;
    *count = n;
    return 0;
}

int hf_version_newer(const char *latest, const char *current) {
    uint32_t a[HF_VERSION_PARTS], b[HF_VERSION_PARTS];
    int na, nb, i;
    if (hf_version_parse(latest, a, &na) || hf_version_parse(current, b, &nb))
        return -1;
    for (i = 0; i < na && i < nb; i++)
        if (a[i] != b[i])
            return a[i] > b[i];
    return na > nb;
}

static int hexval(char c) {
    return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}

/* "sha256:<64 hex>" into 32 bytes. */
static int parse_digest(const char *text, uint8_t out[32]) {
    int i;
    if (strncmp(text, "sha256:", 7) != 0 || strlen(text + 7) != 64)
        return -1;
    for (i = 0; i < 32; i++) {
        int hi = hexval(text[7 + 2 * i]), lo = hexval(text[8 + 2 * i]);
        if (hi < 0 || lo < 0)
            return -1;
        out[i] = (uint8_t)(hi << 4 | lo);
    }
    return 0;
}

static int fill_asset(const char *js, const JsonTok *t, int item, const char *repository, HfAsset *a, const char *name) {
    char digest[96], prefix[200];
    int d = json_find(js, t, item, "digest"), u = json_find(js, t, item, "browser_download_url");
    int s = json_find(js, t, item, "size");
    if (d < 0 || t[d].type != JT_STRING || json_string(js, &t[d], digest, sizeof digest) || parse_digest(digest, a->sha256))
        return HF_REL_NO_DIGEST;
    if (u < 0 || s < 0 || json_uint(js, &t[s], &a->size) || a->size == 0 ||
        json_string(js, &t[u], a->url, sizeof a->url))
        return HF_REL_BAD_ANSWER;
    snprintf(prefix, sizeof prefix, "https://github.com/%s/releases/download/", repository);
    if (strncmp(a->url, prefix, strlen(prefix)) != 0 || strstr(a->url, "..") || strchr(a->url, ' '))
        return HF_REL_BAD_URL;
    snprintf(a->name, sizeof a->name, "%s", name);
    a->found = 1;
    return HF_REL_OK;
}

int hf_release_parse(const char *json, size_t len, const char *repository, const char *const *wanted, int nwanted,
                     HfRelease *out, char *notes, size_t notes_cap) {
    JsonTok *t;
    int n, tag, assets, i, k, rc = HF_REL_OK;
    uint32_t parts[HF_VERSION_PARTS];
    int count;
    if (nwanted < 0 || nwanted > HF_MAX_WANTED)
        return HF_REL_BAD_ANSWER;
    memset(out, 0, sizeof *out);
    if (notes && notes_cap)
        notes[0] = 0;
    t = malloc(sizeof(JsonTok) * MAX_TOKENS);
    if (!t)
        return HF_REL_BAD_ANSWER;
    n = json_parse(json, len, t, MAX_TOKENS);
    if (n < 1 || t[0].type != JT_OBJECT) {
        free(t);
        return HF_REL_BAD_ANSWER;
    }
    tag = json_find(json, t, 0, "tag_name");
    assets = json_find(json, t, 0, "assets");
    if (tag < 0 || assets < 0 || t[tag].type != JT_STRING || t[assets].type != JT_ARRAY ||
        json_string(json, &t[tag], out->tag, sizeof out->tag)) {
        free(t);
        return HF_REL_BAD_ANSWER;
    }
    if (hf_version_parse(out->tag, parts, &count)) {
        free(t);
        return HF_REL_BAD_TAG;
    }
    if (notes && notes_cap) {
        int body = json_find(json, t, 0, "body");
        if (body >= 0 && t[body].type == JT_STRING)
            json_string_trunc(json, &t[body], notes, notes_cap);
    }
    for (i = assets + 1; i < t[assets].next && rc == HF_REL_OK; i = t[i].next) {
        char name[HF_NAME_MAX];
        int nm;
        if (t[i].type != JT_OBJECT)
            continue;
        nm = json_find(json, t, i, "name");
        if (nm < 0 || json_string(json, &t[nm], name, sizeof name))
            continue;
        for (k = 0; k < nwanted; k++) {
            if (strcmp(name, wanted[k]) != 0)
                continue;
            if (out->assets[k].found)
                rc = HF_REL_MANY;
            else
                rc = fill_asset(json, t, i, repository, &out->assets[k], name);
        }
    }
    free(t);
    return rc;
}
