"""The weapon tree's panes by name: the root groups the screen adds to
`lyt\\lobby\\ui401` and the panes each holds. The layout (tree_layout.py) creates them and the code's data block
(weapon_tree.py) carries the hashes of their names in the order of `hash_names()`, which weapon_tree.h's indices follow.
"""

GROUP_FRAME = "ui401_wt_frame"     # the list's frame and the header's bar
GROUP_ROWS = "ui401_wt_rows"       # the rows' bands
GROUP_NODES = "ui401_wt_nodes"     # the cells and the header's texts
GROUP_CURSOR = "ui401_wt_cursor"
GROUP_KEYS = "ui401_wt_keys"       # the key bar, its words, the edges' arrows and the price beside the money
GROUP_CHOICE = "ui401_wt_choice"   # the window "upgrade or craft": shown only while it asks
GROUPS = (GROUP_FRAME, GROUP_ROWS, GROUP_NODES, GROUP_CURSOR, GROUP_KEYS, GROUP_CHOICE)
TREE_GROUPS = GROUPS[:-1]          # the ones the screen shows while it is open

MAX_ROWS = 7                       # the cells the layout holds: the window's rows and columns are at most these
MAX_COLUMNS = 7
BAND_PIECES = 3                    # a row's band: the list's row bar, in its three pieces

FRAME = ("wt_waku0", "wt_waku1", "wt_waku2", "wt_waku3", "wt_naka", "wt_head0", "wt_head1")
NAME_TEXT = "wt_m_name"            # the weapon under the cursor
COUNT_TEXT = "wt_m_count"          # "3/41": the cursor's row and the rows
HINT_TEXT = "wt_m_hint"
KEY_BAR = "wt_keybar"
ARROWS = ("wt_arrow_l", "wt_arrow_r", "wt_arrow_u", "wt_arrow_d")
# The price beside the money: the money window's second box (ui024's) copied, its left end, middle and right end, then
# the word "Cost" and the price
PRICE_BOX = ("wt_pr_l", "wt_pr_m", "wt_pr_r")
COST_TEXT = "wt_m_cost"
PRICE_TEXT = "wt_m_price"
CURSOR_BRACKET = ("wt_cur_b0", "wt_cur_b1")                           # the game's bracket: left half, right half
CURSOR_FRAME = ("wt_cur_f0", "wt_cur_f1", "wt_cur_f2", "wt_cur_f3")   # a thin frame: top, bottom, left, right

# The window "upgrade or craft" (a weapon with a create recipe and a copy of a parent in the box), back to front: its
# fill, a thin edge (top, bottom, left, right), the title's bar in its two pieces, each option's row bar and, over it,
# the list's cursor bar (the code shows the one of the option chosen), the title and the two options' words.
CHOICE_OPTIONS = 2                 # row 0 upgrade, row 1 craft
CHOICE_BACK = "wt_ch_back"
CHOICE_EDGE = ("wt_ch_e0", "wt_ch_e1", "wt_ch_e2", "wt_ch_e3")
CHOICE_HEAD = ("wt_ch_head0", "wt_ch_head1")
CHOICE_TITLE = "wt_m_ch_title"


def choice_row_pane(option: int, piece: int) -> str:
    return f"wt_ch_row{option}_{piece}"


def choice_cursor_pane(option: int, piece: int) -> str:
    return f"wt_ch_cur{option}_{piece}"


def choice_word_pane(option: int) -> str:
    return f"wt_m_ch_{option}"


def choice_panes() -> tuple[str, ...]:
    """The choice window's panes, in the layout's order (weapon_tree.h CH_*)."""
    rows = tuple(choice_row_pane(option, piece) for option in range(CHOICE_OPTIONS) for piece in range(BAND_PIECES))
    cursors = tuple(choice_cursor_pane(option, piece) for option in range(CHOICE_OPTIONS)
                    for piece in range(BAND_PIECES))
    words = tuple(choice_word_pane(option) for option in range(CHOICE_OPTIONS))
    return (CHOICE_BACK,) + CHOICE_EDGE + CHOICE_HEAD + rows + cursors + (CHOICE_TITLE,) + words


def text_panes() -> tuple[str, ...]:
    """Every text pane (each takes a null of the layout's pool)."""
    return (NAME_TEXT, COUNT_TEXT, HINT_TEXT, CHOICE_TITLE) + tuple(
        choice_word_pane(option) for option in range(CHOICE_OPTIONS)) + (COST_TEXT, PRICE_TEXT)

# A cell's pieces, in the order they are drawn: the plate, the link from the parent, the trunk of a branch in its two
# halves (TRUNK: from the cell's top to mid height; TRUNK_LOW: from mid height to the bottom, each lit or dim by
# itself, so a branch can be lit down to a child and dim below it), the icon, the forge mark (a small hammer on a weapon
# with a create recipe), the worn mark, the box mark (in the worn mark's corner: a copy in the box and none worn), the
# element mark (the weapon's element or status icon, upper right) and the new mark.
PLATE, LINK, TRUNK, TRUNK_LOW, ICON, FORGE, WORN, BOX, ELEMENT, NEW = CELL_PIECES = (
    "p", "l", "t", "d", "i", "h", "e", "b", "a", "n")


def band_pane(row: int, piece: int) -> str:
    return f"wt_band{row}_{piece}"


def cell_pane(row: int, column: int, piece: str) -> str:
    return f"wt_{piece}{row}_{column}"


def group_panes() -> dict[str, tuple[str, ...]]:
    """Each group's panes, in the order the layout holds them (the later drawn in front)."""
    bands = tuple(band_pane(row, piece) for row in range(MAX_ROWS) for piece in range(BAND_PIECES))
    cells = tuple(cell_pane(row, column, piece) for piece in CELL_PIECES for row in range(MAX_ROWS)
                  for column in range(MAX_COLUMNS))
    return {
        GROUP_FRAME: FRAME,
        GROUP_ROWS: bands,
        GROUP_NODES: cells + (NAME_TEXT, COUNT_TEXT),
        GROUP_CURSOR: CURSOR_BRACKET + CURSOR_FRAME,
        GROUP_KEYS: (KEY_BAR, HINT_TEXT) + ARROWS + PRICE_BOX + (COST_TEXT, PRICE_TEXT),
        GROUP_CHOICE: choice_panes(),
    }


def hash_names() -> list[str]:
    """Every name the code looks up, in the data block's order: the groups, then each group's panes."""
    names = list(GROUPS)
    for group in GROUPS:
        names.extend(group_panes()[group])
    return names
