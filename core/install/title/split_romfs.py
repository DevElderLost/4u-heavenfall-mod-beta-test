"""The split title's two RomFS: `rom:`
reads the game data title, an add-on content title holding the dump's RomFS, and the title's own RomFS, which holds
only the mod's files, is the drive `mod:`, read first. The installed title's build only (pipeline.run's
`title_build`): the emulator's and Luma3DS' mods keep the game's RomFS as `rom:`.

Hooks, all in code the update and the base games share (the version maps carry them):

* FUN_00105b48 (the system's set-up, at boot) calls FUN_00108930, the `rom:` mount, at MOUNT_CALL: the call goes to
  split_romfs_mount (install/title/split_romfs.c). When the game data title of the running title opens, it makes the
  game's mount with the title's own RomFS standing for the game data's, then mounts the title's own as `mod:`; without
  it, the game's mount as it is (a title holding the whole game).
* FUN_0010b974 (a RomFS mount's work size) and FUN_0010d9ac (its archive open) call FS:OpenFileDirectly at OPEN_CALLS:
  the calls go to split_romfs_open_directly, which during the game's mount opens the game data's RomFS (archive
  0x2345678A) in place of the title's own (SelfNCCH).
* nn::fs::FileStream::TryInitialize (FUN_0010baf8), every file the game opens: its first instruction becomes a `b` to
  split_romfs_open, which opens a `rom:` path on `mod:` first and on `rom:` when `mod:` does not have it; block
  split_romfs_stub runs the replaced instruction for the game's own function.

The title's exheader asks for the FS access archive 0x2345678A needs (title_exheader). Each site is checked first.
"""

import struct

from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target, load_layout
from core.game.executable.exheader import FS_CATEGORY_SYSTEM_APPLICATION, allow_fs_access

BLOCK = "split_romfs"
STUB = "split_romfs_stub"
STATE = "split_romfs_state"

MOUNT_CALL = 0x105BCC           # in FUN_00105b48: bl FUN_00108930 (the `rom:` mount)
ROM_MOUNT = 0x108930            # FUN_00108930(max_files, max_dirs)
TRY_INITIALIZE = 0x10BAF8       # nn::fs::FileStream::TryInitialize(file, path, mode)
TRY_INITIALIZE_FIRST = bytes.fromhex("f0412de9")    # its first instruction: push {r4-r8, lr}
OPEN_DIRECTLY = 0x10DB9C        # FUN_0010db9c: FS:OpenFileDirectly
OPEN_CALLS = (0x10B9D8,         # in FUN_0010b974 (the work size): bl FUN_0010db9c
              0x10DA54)         # in FUN_0010d9ac (the archive open): bl FUN_0010db9c

# Archive 0x2345678A needs one FS access bit of 0x1005 (3dbrew "Filesystem services", archive table): Category system
# application, of the three the one that grants least else (ExtSaveData and some queries; Category filesystem tool
# also opens system save data and the SD card raw, Category system settings the secure values)
GAME_DATA_FS_ACCESS = FS_CATEGORY_SYSTEM_APPLICATION

# Constants of split_romfs.c, for its tests
MOD_DRIVE = "mod:"
NOT_TRIED, MOUNTED, NOT_MOUNTED = 0, 1, 2           # split_romfs_state's first word
PATH_ROOM = 0x110               # UTF-16 units of a path rewritten to `mod:`, its terminator included
FILE_CLEARED = range(1, 5)      # the file object's words cleared before the `rom:` try


def supports_split_romfs(code: bytes) -> bool:
    """True if the mount's call, the two RomFS opens' calls and TryInitialize's first instruction are the game's (not
    yet patched)."""
    at = TRY_INITIALIZE - BASE_ADDRESS
    try:
        return (bl_target(code, MOUNT_CALL) == ROM_MOUNT and bytes(code[at:at + 4]) == TRY_INITIALIZE_FIRST
                and all(bl_target(code, site) == OPEN_DIRECTLY for site in OPEN_CALLS))
    except (struct.error, IndexError, ValueError):
        return False


def patch_split_romfs(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (the canonical executable) that mounts the game data title's RomFS as `rom:` and the title's own as
    `mod:` at boot, and opens every `rom:` file on `mod:` first. Refuses an executable whose sites are not the
    game's."""
    if not supports_split_romfs(code):
        raise CodeSpaceError(f"split RomFS: the calls at {MOUNT_CALL:#x}, {OPEN_CALLS[0]:#x}, {OPEN_CALLS[1]:#x} or "
                             f"the instruction at {TRY_INITIALIZE:#x} are not the game's (another executable, or "
                             "already patched)")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    layout.place(out, STUB)
    layout.hook(out, MOUNT_CALL, layout.symbol(BLOCK, "split_romfs_mount"), calls=ROM_MOUNT)
    for site in OPEN_CALLS:
        layout.hook(out, site, layout.symbol(BLOCK, "split_romfs_open_directly"), calls=OPEN_DIRECTLY)
    layout.hook(out, TRY_INITIALIZE, layout.symbol(BLOCK, "split_romfs_open"), original=TRY_INITIALIZE_FIRST,
                link=False)
    return bytes(out)


def title_exheader(exheader: bytes) -> bytes:
    """The game's `exheader` for the installed title's build: it may open the game data title (archive 0x2345678A)."""
    return allow_fs_access(exheader, GAME_DATA_FS_ACCESS)
