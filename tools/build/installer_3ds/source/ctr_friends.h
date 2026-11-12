/* The online patch of the friends module on the console: the running module's code read through Luma3DS' svcs, the
patch found by core/install/launcher/c/
 * friends_patch.c and merged into /luma/sysmodules/0004013000003202.ips beside Nimbus' records. It takes effect at
 * the next start of the console. `msg` gets one short line for the screen (why, or what was done).
 *
 * Status codes (app.h names them HF_FRIENDS_*): 0 not needed (an emulator, no Luma3DS, or Luma's "Enable loading
 * external FIRMs and modules" off), 1 installed and current, 2 installable, 3 unsupported (msg says why). */
#ifndef CTR_FRIENDS_H
#define CTR_FRIENDS_H

#include <stddef.h>

int hf_friends_status(char *msg, size_t n);
/* Installs or brings the patch up to date; returns the status after (1 when done). */
int hf_friends_install(char *msg, size_t n);
/* Takes our records out of the module's .ips (Nimbus' file given back byte for byte, or the file deleted when it held
 * only ours); returns the status after (2 when done, 3 when the file could not be written). Works with Luma's option
 * off too. */
int hf_friends_remove(char *msg, size_t n);
/* Writes the running module's code (friends_code.bin: text, rodata and data pages as mapped) and what was found
 * (friends_info.txt, and friends_current.ips when there is one) into `dir`, for the probe's log. 0 when written. */
int hf_friends_dump(const char *dir, char *msg, size_t n);

#endif
