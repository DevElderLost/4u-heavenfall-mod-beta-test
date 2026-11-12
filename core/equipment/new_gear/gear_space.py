"""How much room the new hunter armor and create recipes have in the executable's extension (blocks.py reads
these; no imports, so that blocks.py can). ."""

# New pieces per armor part. A ported monster brings 3 ranks x 2 hunter styles = 6 pieces per part (Alatreon 2).
ARMOR_ROOM = 32
# New create recipes (24 bytes each) in the armor table (types 1-5) and in the weapons' (types 7-20).
ARMOR_RECIPE_ROOM = 160
WEAPON_RECIPE_ROOM = 192
# Runs of consecutive new recipes per table: a run sits in front of one recipe of the game (or at the end).
RECIPE_RUNS = 16

RECIPE_RECORD = 24
ARMOR_RECORD = 40
# Block sizes
ARMOR_RECORDS_BYTES = 5 * ARMOR_ROOM * ARMOR_RECORD
ARMOR_NEW_BYTES = 8 * 8              # per equipment type 0-7: first new id, table base
RUNS_BYTES = (RECIPE_RUNS + 1) * 8   # per table: runs of 8 bytes and one empty
