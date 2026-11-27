/* Types and helpers shared by the port's engine headers (enemy_4u.h, enemy_gen.h). */
#ifndef ALATREON_TYPES_H
#define ALATREON_TYPES_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef int s32;
typedef unsigned long long u64;

/* Both games' engines pass floats in VFP registers, while the C is built soft-float: engine functions that take or
return floats are declared ENGINE_VFP. */
#define ENGINE_VFP __attribute__((pcs("aapcs-vfp")))

/* Engine functions in Thumb code: called through a register (blx), at their address + 1. A bl from ARM
 * code would reach them in the wrong mode. */
#define ENGINE_THUMB __attribute__((long_call))

/* The bits of a float as a signed word: compilers compare floats this way (as integers) where the sign
 * is known, and the C keeps their order of results for every value, NaN included. */
static inline s32 f32_bits(float f)
{
    union { float f; s32 i; } u = { f };
    return u.i;
}

/* `x`, computed on its own: the compiler cannot fold the multiply that gives it into the next add or
 * subtract (vmla, vmls). vmls negates the product, which turns a NaN's sign; the originals multiply and
 * subtract apart. */
static inline float f32_keep(float x)
{
    __asm__("" : "+t"(x));
    return x;
}

/* x / d for a constant d, as compilers do it: the high word of x times `magic`, shifted right by `shift`
 * (umull). The C is built without a library, and GCC may otherwise call one for a division. */
static inline u32 u32_div_magic(u32 x, u32 magic, u32 shift)
{
    return (u32)(((unsigned long long)x * magic) >> 32) >> shift;
}

/* The square root, as the VFP computes it (the C is built without a library) */
static inline float f32_sqrt(float x)
{
    float root;

    __asm__("vsqrt.f32 %0, %1" : "=t"(root) : "t"(x));
    return root;
}

/* A field `type` at `offset` bytes from `base`. */
#define FIELD(type, base, offset) (*(type *)((u8 *)(base) + (offset)))

typedef struct uEnemy uEnemy;
typedef void (*enemy_method)(uEnemy *self);

#endif
