/* The CIA writer, byte-identical to core/install/title/cia.py: certificate chain, ticket, TMD, the NCCH as
 * content 0 and the meta section, nothing encrypted. The ticket's and TMD's signatures are zeroed; the certificate
 * chain is the caller's (Nintendo's public one, core/install/title/certs.bin, which the title pack carries).
 *
 * Streams only (the console's install handle cannot seek back), so the TMD needs the NCCH's SHA-256 before the
 * NCCH goes out. Two passes over the NCCH:
 *   cia_content_hash  streams the NCCH into SHA-256, writing nothing.
 *   cia_write         writes the CIA, the TMD already right.
 */
#ifndef CIA_H
#define CIA_H

#include "ncch.h"
#include "title_io.h"

#define CIA_HEADER_SIZE 0x2020u
#define CIA_ALIGNMENT 64u
#define CIA_SMDH_SIZE 0x36C0u
#define CIA_CERT_CHAIN_SIZE 0xA00u
#define CIA_TICKET_SIZE 0x350u
#define CIA_TMD_SIZE 0xB34u
#define CIA_META_SIZE 0x3AC0u
#define CIA_UPDATE_TITLE_VERSION (1u << 10)   /* 1.0.0: major 1, the exheader's remaster version */

typedef struct {
    const uint8_t *certs;   /* the certificate chain's bytes (required) */
    size_t certs_len;
    const uint8_t *smdh;    /* CIA_SMDH_SIZE bytes for the meta section; NULL (or a CFA content) for no meta */
    int override_save_size;  /* nonzero: the TMD gets save_size instead of the exheader's (an update title: 0) */
    uint64_t save_size;
    uint16_t title_version;  /* the TMD's; 0: the default (a base title 0, an update 1.0.0) */
} CiaOpts;

void cia_ticket(uint64_t title_id, uint8_t out[CIA_TICKET_SIZE]);
/* `title_version` 0: the default, as CiaOpts. */
void cia_tmd(uint64_t title_id, uint64_t save_size, uint64_t content_size, const uint8_t content_hash[32],
             uint16_t title_version, uint8_t out[CIA_TMD_SIZE]);

/* Pass 1: SHA-256 of the NCCH. Progress goes to out->progress; out->write is not used. */
int cia_content_hash(const Ncch *n, const TitleOut *progress, uint8_t out_hash[32]);
/* Pass 2: the whole CIA through out->write (TITLE_E_ARG without opts->certs). Its total size is cia_size. */
int cia_write(const Ncch *n, const CiaOpts *opts, const uint8_t content_hash[32], const TitleOut *out);
uint64_t cia_size(const Ncch *n, const CiaOpts *opts);
/* The bytes before the content (header, certificates, ticket, TMD, each padded to 64) and after it (the meta
 * section padded to 64, none without an SMDH), in new buffers (free()); the content's own padding to 64 goes
 * between. For a CIA streamed by pieces (build.c). */
int cia_head(const Ncch *n, const CiaOpts *opts, const uint8_t content_hash[32], uint8_t **out, size_t *len);
int cia_meta(const Ncch *n, const CiaOpts *opts, uint8_t **out, size_t *len);
uint64_t cia_save_size(const Ncch *n, const CiaOpts *opts);   /* the TMD's */

#endif
