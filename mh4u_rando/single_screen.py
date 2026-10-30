"""Single-screen mode in a run: every RomFS file it writes, in their order, and what its
executable patch takes from them. The full mod's run and an edition's both build it here."""

from collections.abc import Mapping
from dataclasses import dataclass

from .gamegui.build import single_screen_build
from .hud.build import GameFiles
from .hud.single_screen import keyboard_backdrop_files, single_screen_files
from .hud.single_screen_card import card_info_files
from .hud.single_screen_hint import map_hint_files
from .hud.single_screen_minimap import minimap_files
from .hud.single_screen_players import players_files


@dataclass
class SingleScreenFiles:
    files: dict[str, bytes]         # RomFS path -> ARC, over the copies the run's other interface steps made
    offsets: dict[int, int]         # the draw order offsets (exefs/single_screen.patch_single_screen)
    engine_table: bytes | None      # the game GUI engine's table of the arranged screens (None: nothing arranged)


def single_screen_romfs(rom: GameFiles, prior: Mapping[str, bytes]) -> SingleScreenFiles:
    """The mode's files. `prior`: what the run's other interface steps made (HUD, icons, texts, key marks); the mode
    places whole layouts with what they added, so it comes after them."""
    screens, offsets = single_screen_files(rom, prior)
    screens |= keyboard_backdrop_files(rom)     # the name keyboard's own background, as wide as the screen
    # the "[X] Map" hint, a group in the placed world map layout (hud/single_screen_hint.py)
    screens |= map_hint_files(rom, {**prior, **screens})
    # the town minimap's state group and its "[L] Minimap" hint (hud/single_screen_minimap.py)
    screens |= minimap_files(rom, {**prior, **screens})
    # the guild card's hide state and its "[Y] Toggle Display" hint (hud/single_screen_card.py)
    screens |= card_info_files(rom, {**prior, **screens})
    # the hall's member list laid out as the players' box (hud/single_screen_players.py)
    screens |= players_files(rom, {**prior, **screens})
    # last: the arranged screens' layouts fixed and wrapped for the game GUI engine (gamegui/build.py)
    arranged = single_screen_build(rom.read, {**prior, **screens})
    screens |= arranged.files
    return SingleScreenFiles(screens, offsets, arranged.table)
