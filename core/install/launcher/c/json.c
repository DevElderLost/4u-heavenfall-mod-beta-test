/* See json.h. */
#include "json.h"

#include <string.h>

#define MAX_DEPTH 24

typedef struct {
    const char *s;
    size_t n, i;
    JsonTok *t;
    int max, count;
} Parser;

static void spaces(Parser *p) {
    while (p->i < p->n && (p->s[p->i] == ' ' || p->s[p->i] == '\t' || p->s[p->i] == '\n' || p->s[p->i] == '\r'))
        p->i++;
}

static int add(Parser *p, JsonType type, size_t start) {
    JsonTok *t;
    if (p->count >= p->max)
        return JSON_E_TOKENS;
    t = &p->t[p->count];
    t->type = type;
    t->start = (int)start;
    t->end = (int)start;
    t->size = 0;
    t->next = p->count + 1;
    return p->count++;
}

static int hexval(char c) {
    return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
}

static int string_token(Parser *p) {
    size_t start = ++p->i;
    int id = add(p, JT_STRING, start);
    if (id < 0)
        return id;
    while (p->i < p->n) {
        unsigned char c = (unsigned char)p->s[p->i];
        if (c == '"') {
            p->t[id].end = (int)p->i++;
            return id;
        }
        if (c < 0x20)
            return JSON_E_SYNTAX;
        if (c == '\\') {
            char e;
            if (++p->i >= p->n)
                return JSON_E_SYNTAX;
            e = p->s[p->i];
            if (e == 'u') {
                int k;
                for (k = 1; k <= 4; k++)
                    if (p->i + k >= p->n || hexval(p->s[p->i + k]) < 0)
                        return JSON_E_SYNTAX;
                p->i += 4;
            } else if (!e || !strchr("\"\\/bfnrt", e)) {
                return JSON_E_SYNTAX;
            }
        }
        p->i++;
    }
    return JSON_E_SYNTAX;
}

static int number_ok(const char *w, size_t len) {
    size_t k = 0;
    if (k < len && w[k] == '-')
        k++;
    if (k >= len || w[k] < '0' || w[k] > '9')
        return 0;
    if (w[k] == '0' && k + 1 < len && w[k + 1] >= '0' && w[k + 1] <= '9')
        return 0;
    while (k < len && w[k] >= '0' && w[k] <= '9')
        k++;
    if (k < len && w[k] == '.') {
        size_t d = ++k;
        while (k < len && w[k] >= '0' && w[k] <= '9')
            k++;
        if (k == d)
            return 0;
    }
    if (k < len && (w[k] == 'e' || w[k] == 'E')) {
        size_t d;
        k++;
        if (k < len && (w[k] == '+' || w[k] == '-'))
            k++;
        d = k;
        while (k < len && w[k] >= '0' && w[k] <= '9')
            k++;
        if (k == d)
            return 0;
    }
    return k == len;
}

static int prim_token(Parser *p) {
    size_t start = p->i, len;
    const char *w;
    int id, ok;
    while (p->i < p->n && p->s[p->i] && strchr("+-.0123456789eEabcdefghijklmnopqrstuvwxyz", p->s[p->i]))
        p->i++;
    if (p->i == start)
        return JSON_E_SYNTAX;
    len = p->i - start;
    w = p->s + start;
    ok = (len == 4 && !memcmp(w, "true", 4)) || (len == 4 && !memcmp(w, "null", 4)) ||
         (len == 5 && !memcmp(w, "false", 5)) || number_ok(w, len);
    if (!ok)
        return JSON_E_SYNTAX;
    id = add(p, JT_PRIM, start);
    if (id >= 0)
        p->t[id].end = (int)p->i;
    return id;
}

static int value(Parser *p, int depth) {
    int id, child, object;
    char close;
    spaces(p);
    if (p->i >= p->n)
        return JSON_E_SYNTAX;
    if (p->s[p->i] == '"')
        return string_token(p);
    if (p->s[p->i] != '{' && p->s[p->i] != '[')
        return prim_token(p);
    if (depth >= MAX_DEPTH)
        return JSON_E_DEPTH;
    object = p->s[p->i] == '{';
    close = object ? '}' : ']';
    id = add(p, object ? JT_OBJECT : JT_ARRAY, p->i);
    if (id < 0)
        return id;
    p->i++;
    spaces(p);
    if (p->i < p->n && p->s[p->i] == close) {
        p->i++;
    } else {
        for (;;) {
            spaces(p);
            if (object) {
                if (p->i >= p->n || p->s[p->i] != '"')
                    return JSON_E_SYNTAX;
                child = string_token(p);
                if (child < 0)
                    return child;
                spaces(p);
                if (p->i >= p->n || p->s[p->i] != ':')
                    return JSON_E_SYNTAX;
                p->i++;
            }
            child = value(p, depth + 1);
            if (child < 0)
                return child;
            p->t[id].size++;
            spaces(p);
            if (p->i < p->n && p->s[p->i] == ',') {
                p->i++;
                continue;
            }
            if (p->i < p->n && p->s[p->i] == close) {
                p->i++;
                break;
            }
            return JSON_E_SYNTAX;
        }
    }
    p->t[id].end = (int)p->i;
    p->t[id].next = p->count;
    return id;
}

int json_parse(const char *js, size_t len, JsonTok *toks, int max) {
    Parser p;
    int root;
    p.s = js; p.n = len; p.i = 0; p.t = toks; p.max = max; p.count = 0;
    root = value(&p, 0);
    if (root < 0)
        return root;
    spaces(&p);
    return p.i == p.n ? p.count : JSON_E_SYNTAX;
}

int json_find(const char *js, const JsonTok *toks, int obj, const char *key) {
    int i, n;
    size_t klen = strlen(key);
    if (obj < 0 || toks[obj].type != JT_OBJECT)
        return -1;
    i = obj + 1;
    for (n = 0; n < toks[obj].size; n++) {
        int v = toks[i].next;
        if ((size_t)(toks[i].end - toks[i].start) == klen && !memcmp(js + toks[i].start, key, klen))
            return v;
        i = toks[v].next;
    }
    return -1;
}

static void put_utf8(unsigned c, char *out, size_t *o) {
    if (c < 0x80) {
        out[(*o)++] = (char)c;
    } else if (c < 0x800) {
        out[(*o)++] = (char)(0xC0 | c >> 6);
        out[(*o)++] = (char)(0x80 | (c & 0x3F));
    } else {
        out[(*o)++] = (char)(0xE0 | c >> 12);
        out[(*o)++] = (char)(0x80 | ((c >> 6) & 0x3F));
        out[(*o)++] = (char)(0x80 | (c & 0x3F));
    }
}

int json_string(const char *js, const JsonTok *tok, char *out, size_t cap) {
    size_t o = 0;
    int i;
    if (tok->type != JT_STRING || cap < 5)
        return -1;
    for (i = tok->start; i < tok->end; i++) {
        char c = js[i];
        if (o + 4 >= cap) /* room for the longest piece and the NUL */
            return -1;
        if (c != '\\') {
            out[o++] = c;
            continue;
        }
        c = js[++i];
        switch (c) {
        case 'b': out[o++] = '\b'; break;
        case 'f': out[o++] = '\f'; break;
        case 'n': out[o++] = '\n'; break;
        case 'r': out[o++] = '\r'; break;
        case 't': out[o++] = '\t'; break;
        case 'u': {
            unsigned v = 0;
            int k;
            for (k = 1; k <= 4; k++)
                v = v << 4 | (unsigned)hexval(js[i + k]);
            i += 4;
            if (v >= 0xD800 && v < 0xE000)
                v = '?'; /* a surrogate half: nothing the release's fields use */
            put_utf8(v, out, &o);
            break;
        }
        default: out[o++] = c;
        }
    }
    out[o] = 0;
    return 0;
}

static int utf8_len(unsigned char lead) {
    return lead >= 0xF0 ? 4 : lead >= 0xE0 ? 3 : lead >= 0xC0 ? 2 : 1;
}

/* The code point `v` as UTF-8 into piece[]; its length. */
static size_t encode_utf8(unsigned v, char piece[4]) {
    if (v < 0x80) {
        piece[0] = (char)v;
        return 1;
    }
    if (v < 0x800) {
        piece[0] = (char)(0xC0 | v >> 6);
        piece[1] = (char)(0x80 | (v & 0x3F));
        return 2;
    }
    if (v < 0x10000) {
        piece[0] = (char)(0xE0 | v >> 12);
        piece[1] = (char)(0x80 | ((v >> 6) & 0x3F));
        piece[2] = (char)(0x80 | (v & 0x3F));
        return 3;
    }
    piece[0] = (char)(0xF0 | v >> 18);
    piece[1] = (char)(0x80 | ((v >> 12) & 0x3F));
    piece[2] = (char)(0x80 | ((v >> 6) & 0x3F));
    piece[3] = (char)(0x80 | (v & 0x3F));
    return 4;
}

static unsigned hex4(const char *s) {
    unsigned v = 0;
    int k;
    for (k = 0; k < 4; k++)
        v = v << 4 | (unsigned)hexval(s[k]);
    return v;
}

int json_string_trunc(const char *js, const JsonTok *tok, char *out, size_t cap) {
    size_t o = 0;
    int i;
    if (tok->type != JT_STRING || cap < 1)
        return -1;
    for (i = tok->start; i < tok->end;) {
        char piece[4];
        size_t n = 0, k;
        unsigned char c = (unsigned char)js[i];
        if (c != '\\') {
            int len = utf8_len(c);
            if (i + len > tok->end)
                len = tok->end - i;
            for (k = 0; k < (size_t)len; k++)
                piece[n++] = js[i + (int)k];
            i += len;
        } else {
            char e = js[i + 1];
            i += 2;
            switch (e) {
            case 'b': piece[n++] = '\b'; break;
            case 'f': piece[n++] = '\f'; break;
            case 'n': piece[n++] = '\n'; break;
            case 'r': piece[n++] = '\r'; break;
            case 't': piece[n++] = '\t'; break;
            case 'u': {
                unsigned v = hex4(js + i);
                i += 4;
                if (v >= 0xD800 && v < 0xDC00 && i + 6 <= tok->end && js[i] == '\\' && js[i + 1] == 'u') {
                    unsigned lo = hex4(js + i + 2);
                    if (lo >= 0xDC00 && lo < 0xE000) {
                        v = 0x10000 + ((v - 0xD800) << 10) + (lo - 0xDC00);
                        i += 6;
                    }
                }
                if (v >= 0xD800 && v < 0xE000)
                    v = '?'; /* a lone surrogate half */
                n = encode_utf8(v, piece);
                break;
            }
            default: piece[n++] = e;
            }
        }
        if (o + n + 1 > cap)
            break;
        for (k = 0; k < n; k++)
            out[o++] = piece[k];
    }
    out[o] = 0;
    return (int)o;
}

int json_uint(const char *js, const JsonTok *tok, uint64_t *out) {
    uint64_t v = 0;
    int i;
    if (tok->type != JT_PRIM || tok->end == tok->start)
        return -1;
    for (i = tok->start; i < tok->end; i++) {
        unsigned d = (unsigned)(js[i] - '0');
        if (d > 9 || v > (UINT64_MAX - d) / 10)
            return -1;
        v = v * 10 + d;
    }
    *out = v;
    return 0;
}
