/* The chime (ui.h): romfs:/chime.wav (16-bit mono PCM, made by
 * tools/build/build_launcher_assets.py) through ndsp. The DSP starts only for it and stops after, and its buffer lives
 * in linear memory only while it plays; without the DSP's firmware on the card (dspfirm.cdc) it is silent. */
#include <3ds.h>
#include <stdio.h>
#include <string.h>

#include "ui.h"

#define CHIME_PATH "romfs:/chime.wav"
#define CHIME_MAX (64 * 1024)
#define WAIT_MS 10

static u32 le32(const u8 *p) { return (u32)p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24; }
static u16 le16(const u8 *p) { return (u16)(p[0] | p[1] << 8); }

/* The 16-bit mono PCM samples of a WAV file: their offset and bytes, its rate. 0, or -1 for anything else. */
static int pcm16_mono(const u8 *wav, size_t len, size_t *at, size_t *bytes, u32 *rate) {
    size_t pos = 12;
    int format = 0;
    if (len < 12 || memcmp(wav, "RIFF", 4) || memcmp(wav + 8, "WAVE", 4)) return -1;
    while (pos + 8 <= len) {
        u32 size = le32(wav + pos + 4);
        if (size > len - pos - 8) return -1;
        if (!memcmp(wav + pos, "fmt ", 4) && size >= 16) {
            format = le16(wav + pos + 8) == 1 && le16(wav + pos + 10) == 1 && le16(wav + pos + 22) == 16;
            *rate = le32(wav + pos + 12);
        } else if (!memcmp(wav + pos, "data", 4)) {
            *at = pos + 8;
            *bytes = size & ~1u;
            return format && *rate ? 0 : -1;
        }
        pos += 8 + size + (size & 1);
    }
    return -1;
}

void ui_chime(void) {
    FILE *f = fopen(CHIME_PATH, "rb");
    long len;
    u8 *wav = NULL;
    size_t at = 0, bytes = 0;
    u32 rate = 0;
    float mix[12];
    ndspWaveBuf wb;
    u64 until;
    if (!f) return;
    fseek(f, 0, SEEK_END);
    len = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (len > 0 && len <= CHIME_MAX) wav = (u8 *)linearAlloc((size_t)len);
    if (!wav || fread(wav, 1, (size_t)len, f) != (size_t)len || pcm16_mono(wav, (size_t)len, &at, &bytes, &rate) ||
        R_FAILED(ndspInit())) {
        fclose(f);
        if (wav) linearFree(wav);
        return;
    }
    fclose(f);
    ndspSetOutputMode(NDSP_OUTPUT_STEREO);
    ndspChnReset(0);
    ndspChnSetInterp(0, NDSP_INTERP_LINEAR);
    ndspChnSetRate(0, (float)rate);
    ndspChnSetFormat(0, NDSP_FORMAT_MONO_PCM16);
    memset(mix, 0, sizeof mix);
    mix[0] = mix[1] = 1.0f;
    ndspChnSetMix(0, mix);
    memset(&wb, 0, sizeof wb);
    wb.data_vaddr = wav + at;
    wb.nsamples = (u32)(bytes / 2);
    DSP_FlushDataCache(wav, (u32)len);
    ndspChnWaveBufAdd(0, &wb);
    until = osGetTime() + (u64)wb.nsamples * 1000 / rate + 500;
    while (*(volatile u8 *)&wb.status != NDSP_WBUF_DONE && osGetTime() < until) svcSleepThread(WAIT_MS * 1000000LL);
    ndspChnReset(0);
    ndspExit();
    linearFree(wav);
}
