/* The libctru side of the network: the sockets, libcurl with mbedTLS as
 * the transport of core/install/launcher/c/hfnet.h, downloads to the SD card, and the app's own update. All the rules
 * (releases, resuming, checksums, the plan) are in the portable C the PC tests build; this file only wraps the
 * console's services and can be checked only on a console.
 *
 * The call order of a screen: ctr_net_init(); ctr_net_transport(&tr); hf_latest_release(&tr, HF_API_BASE, ...);
 * hf_plan(...); ctr_net_fetch(...) for each file; ctr_self_* for the app's own file; ctr_net_exit(). */
#ifndef CTR_NET_H
#define CTR_NET_H

#include <3ds.h>
#include <stdint.h>

#include "hf_edition.h"
#include "hfnet.h"

/* Starts the sockets (a 256 KB buffer), libcurl and mbedTLS' CA list (romfs:/cacert.pem: romfsInit must have run); 0 on
 * success, else a Result or a negative code. Each successful call is paired with a ctr_net_exit: the network stops
 * when its last user leaves. Thread-safe (the start's check runs on a thread of its own). Sleep is the caller's: an
 * update keeps the console awake itself. */
int ctr_net_init(void);
void ctr_net_exit(void);

/* The libctru/libcurl transport. HTTPS only (also for redirects), certificates checked against the bundled list. */
void ctr_net_transport(HfTransport *tr);
/* The same, stopped as soon as *abort_flag is nonzero: a transfer under way ends at curl's next progress step, the
 * tries and waits left end at once (HF_NET_FAIL). */
void ctr_net_transport_abortable(HfTransport *tr, volatile int *abort_flag);

/* The folder of an edition's downloads, sdmc:/3ds/heavenfall/<slug>/ (made if missing). */
int ctr_net_folder(const HfEdition *edition, char *out, size_t cap);

/* Downloads a found release asset into the edition's folder as <name>.part, checks size and SHA-256, and renames it to
 * <name>; the full path goes to `path`. A cancelled or cut download leaves the .part to resume from. `progress` is a
 * TitleProgress-like callback (called every chunk: poll the buttons and aptMainLoop there; nonzero cancels). Returns
 * an HF_* code (HF_E_DISK when the SD card has no room). */
int ctr_net_fetch(const HfEdition *edition, const HfAsset *asset, const HfTransport *tr,
                  int (*progress)(void *ctx, uint64_t done, uint64_t total), void *ctx, char *path, size_t cap);

/* ---- the app's own update ---- */

typedef enum { CTR_FORM_CIA, CTR_FORM_3DSX } CtrForm;
/* How this app runs: as an installed title or as a homebrew file (envIsHomebrew). */
CtrForm ctr_app_form(void);

/* The 3dsx's own file back in place after an update cut by a power loss (own.old without own); call at start. */
void ctr_self_recover(const char *own_path);
/* A verified .3dsx replaces the running app's file `own_path` (argv[0]): own -> own.old, new -> own, own.old deleted.
 * The running copy stays in memory; the new one runs at the next launch. 0 on success, else errno (EINVAL: argv[0]
 * is no .3dsx on the card, hf_own_3dsx_ok; nothing renamed). */
int ctr_self_replace_3dsx(const char *downloaded, const char *own_path);
/* A verified CIA installed through AM over the running title (SD card). 0 on success, else *result holds AM's code
 * (-3: the CIA is not the launcher's title, hf_cia_is_launcher; nothing given to AM). */
int ctr_self_install_cia(const char *cia_path, Result *result);

#endif
