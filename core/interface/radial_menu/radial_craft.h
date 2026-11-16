/* The item wheel's Auto-Combine (radial_craft.c), as radial_wheel.c asks it: which slots can be combined, and the
 * combine of a picked one. */

#ifndef RADIAL_CRAFT_H
#define RADIAL_CRAFT_H

#include "radial_choices.h"

#define CRAFT_NONE 0                    /* radial_craft: nothing done (the item is not craftable) */
#define CRAFT_MADE 1                    /* combined: the result added */
#define CRAFT_FAILED 2                  /* the roll failed: Garbage added */

/* Bit k: slot k's item can be combined now (the checks of radial_craft.c) */
unsigned int radial_craftable(unsigned int hunter, const struct choices *choices);

/* Combines `item` once when it can be combined: CRAFT_NONE, CRAFT_MADE or CRAFT_FAILED */
unsigned int radial_craft(unsigned int hunter, unsigned int item);

#endif
