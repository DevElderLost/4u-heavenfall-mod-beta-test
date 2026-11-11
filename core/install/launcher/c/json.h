/* A small strict JSON reader (portable C99, own code): tokens into a caller's array, nothing allocated. It reads what
 * GitHub's releases API answers; it is not a general library. A token's `next` is the index after its subtree, so a
 * walk over an array's items is `for (i = arr + 1; i < toks[arr].next; i = toks[i].next)`. */
#ifndef HF_JSON_H
#define HF_JSON_H

#include <stddef.h>
#include <stdint.h>

typedef enum { JT_OBJECT, JT_ARRAY, JT_STRING, JT_PRIM } JsonType;

typedef struct {
    JsonType type;
    int start, end;  /* the text's bytes: a string's without its quotes */
    int size;        /* an object's pairs, an array's items */
    int next;        /* the token after this one's subtree */
} JsonTok;

enum { JSON_E_SYNTAX = -1, JSON_E_TOKENS = -2, JSON_E_DEPTH = -3 };

/* Parses one document (nothing may follow it but spaces); the number of tokens, the root being token 0, or a JSON_E_*. */
int json_parse(const char *js, size_t len, JsonTok *toks, int max);
/* The value token of `key` in the object token `obj`, or -1. A key is compared as written (no escapes). */
int json_find(const char *js, const JsonTok *toks, int obj, const char *key);
/* A string token's text, unescaped, NUL-terminated into out; -1 when it is no string or does not fit. */
int json_string(const char *js, const JsonTok *tok, char *out, size_t cap);
/* A string token's text, unescaped like json_string (\uXXXX to UTF-8, a surrogate pair as one letter, a lone half as '?'),
 * cut when it does not fit: only at a whole UTF-8 letter, so the text stays valid. NUL-terminated into out; its length,
 * or -1 when the token is no string or cap is 0. */
int json_string_trunc(const char *js, const JsonTok *tok, char *out, size_t cap);
/* A non-negative integer token (digits only, no fraction or exponent); -1 otherwise. */
int json_uint(const char *js, const JsonTok *tok, uint64_t *out);

#endif
