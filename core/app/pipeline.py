"""End-to-end run of Heavenfall Beta: the player's game -> a Citra/Azahar mod folder.

Heavenfall Beta puts the touch screen's menus on the top screen (single-screen mode), shrinks the HUD, adds a page to
the game's START menu, Mod Settings, where the player changes the cheats, the lock-on with L and holding A during play,
and adds Layered Gear (the looks of the Smithy's Layered Equipment line), the Wyporium's new trades and its Rare
Materials Exchange, all for the emulator (docs/how_it_works.md). They come in three modules, each with a switch of its
own (gui_presets.json `install.modules`): single screen (with the HUD size, the lock-on, the aspect ratio and Select's
kick), Layered Gear (with the new trades and the Rare Materials Exchange) and the quality-of-life one (holding A, fast
text, the camera, the item boxes and the cheats); a module that is off leaves the game as it is, but for Layered Gear's
new items (the rare materials of MH XX's monsters, Foreign Scrap), which every run defines so that a save holding them
reads them whatever is on. Input: the player's
decrypted base game, European or American; the executable and the interface's files are read from it in memory, and the
update is never needed. MH XX's decrypted game is optional: with it, Layered Gear also offers XX's looks and the
Wyporium trades the new materials they cost.

Output (copy its contents into the emulator's load/mods/<title>/: 0004000000126100 European, 0004000000126300
American; the program does it for the player):

    romfs/<lang>/data/*.arc        the single-screen layouts, the smaller HUD, the Smithy's and the Wyporium's texts
    romfs/...                      with MH XX: the models of XX's looks
    exefs/code.bin, exheader.bin   the whole executable with the patches: written for the canonical executable and
                                   carried onto the player's own version (docs/how_it_works.md, "The executable"); the
                                   exheader is his game's, extended when a patch uses the executable's extension
    settings_<seed>.json           the settings used

The original files are never modified; every run starts from them.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.equipment.layered import felyne_looks
from core.equipment.layered.layered_equipment import patch_layered_equipment, supports_layered_equipment
from core.equipment.layered.texts import layered_text_files, remove_layered_text_files
from core.equipment.layered.xx_materials import add_materials, load_materials
from core.equipment.mhgen import felyne_pack
from core.equipment.mhgen.looks import GenLooks
from core.equipment.mhgen.pack_run import cached_pack, remove_pack_files, write_pack_files
from core.equipment.mhgen.tables import patch_executable
from core.equipment.mhgen.xx_sources import write_sources
from core.equipment.new_gear.new_items import supports_new_items
from core.equipment.new_gear.new_texts import CommonTexts
from core.game.executable.romfs import RomFS
from core.game.executable.code_bin import is_container
from core.game.executable.containers import kept_reads
from core.game.executable import session, titles
from core.cheats.cheats import patch_cheats, supports_cheats, wants_cheats
from core.game.files.text.common_texts import remove_common_text_files
from core.interface.mod_settings.mod_options import available_options, patch_mod_options, supports_mod_options
from core.interface.mod_settings.mod_texts import mod_settings_texts
from core.game.executable.memory_split import patch_memory_split, resource_to_root_mb
from core.game.executable.output import remove_exefs, write_exefs
from core.game.executable.player_code import open_code
from core.game.executable.rebase import feature_gaps
from core.interface.single_screen.executable.single_screen import patch_single_screen, supports_single_screen
from core.game.executable.versions import VersionMap
from core.gameplay.meownster_scrap.meownster_scrap import patch_meownster_scrap
from core.gameplay.select_kick.select_kick import patch_select_kick, supports_select_kick
from core.gameplay.wyporium.exchange_texts import exchange_text_files, remove_exchange_text_files
from core.gameplay.wyporium.rare_exchange import patch_rare_exchange, supports_rare_exchange
from core.gameplay.wyporium.trades import patch_trades
from core.interface.font.blank_glyphs import font_files
from core.interface.hud.anchors import interface_anchors, remove_backdrop_files
from core.interface.hud.build import hud_files, remove_hud_files
from core.interface.hud.build import hint_files
from core.interface.hud.code_patch import patch_interface
from core.interface.hud.scale import NO_EDGE
from core.interface.single_screen.layout.single_screen import remove_single_screen_files
from core.app import presets
from core.app.record import RunRecord, save_run
from core.app.settings import HudScale, Settings
from core.interface.single_screen.run import single_screen_romfs
from core.install.title.split_romfs import patch_split_romfs, supports_split_romfs, title_exheader

# Stages announced through run(stage=...), in order.
STAGES = ("rom", "write")
# Why a run leaves a feature out (its notice): the game version lacks its code, or the input is no game ROM
NOT_AVAILABLE = "not available on this game version"
NEEDS_ROM = "needs the game ROM"


@dataclass(frozen=True)
class Probe:
    """A developer probe's own executable patch (tools/ui/ui_probe.py's frame counters): `patch` takes the canonical
    executable after every patch of the mod and returns it patched; `layout` places the blocks it places (the committed
    layout plus the probe's), so the run carries them to the player's version like the mod's."""
    patch: Callable[[bytes], bytes]
    layout: object      # exefs.code_space.Layout


@dataclass
class RunResult:
    output_dir: Path
    seed: str
    executable_path: Path | None = None  # exefs/code.bin (None: the run patches no executable)
    hud_scale: HudScale = HudScale.FULL
    hud_paths: list[Path] = field(default_factory=list)  # files of the smaller HUD
    single_screen_paths: list[Path] = field(default_factory=list)  # single-screen layouts
    interface_patched: bool = False  # the executable carries the interface patches
    notices: list[str] = field(default_factory=list)  # features left out (no ROM, or not on this game version)
    game_version: str | None = None  # the version the executable was built from (game/executable/versions.py key)
    checksum: None = None  # nothing is randomized: there is no code to compare
    settings_path: Path | None = None  # settings_<seed>.json
    # the mod folder's name: the game's region (game/executable/titles.py)
    mod_title: str = titles.mod_title(titles.EUR)

    @property
    def warnings(self) -> list[str]:
        return list(self.notices)


def game_mod_title(game: Path) -> str:
    """The mod folder's title for the player's game file: its region's (another file: European)."""
    return titles.mod_title_of_file(game) or titles.mod_title(titles.EUR)


def mod_folder(output_dir: Path) -> Path:
    """Root of the mod."""
    return Path(output_dir)


def version_notices(version: VersionMap) -> list[str]:
    """The patch sites the player's version lacks (rebase.feature_gaps), one notice per module that names them: its
    feature cannot patch that version (its own byte checks then leave it out)."""
    return [f"{module}: {NOT_AVAILABLE} ({', '.join(names)})" for module, names in feature_gaps(version).items()]


def left_out(feature: str, kept: str, why: str) -> str:
    """The notice of a feature the run leaves out: `why` (NOT_AVAILABLE or NEEDS_ROM), then what the game keeps."""
    return f"{feature}: {why}; {kept}"


def write_interface_files(result: RunResult, rom: RomFS | None, settings: Settings, with_code_patch: bool,
                          single_screen: bool = False, menu_texts: bool = False,
                          target_switch: bool = False, layered_texts: bool = False, exchange_texts: bool = False,
                          gen_looks: GenLooks | None = None, gear_texts: CommonTexts | None = None,
                          felynes: felyne_looks.FelyneLooks | None = None
                          ) -> tuple[dict[int, int], bytes | None, bytes | None]:
    """The HUD size's, the START menu page's (`menu_texts`), the new items' names (`gear_texts`: the rare materials of
    MH XX's monsters), Layered Gear's (with MH XX's looks: `gen_looks`; the Felynes': `felynes`), the Rare Materials
    Exchange's and the single-screen mode's RomFS files, and with the game's files always the font's (its blank
    characters, away from its glyphs). They may change the same ARCs, so each is made on the previous
    one's copies and everything is written once; files of an earlier run are removed first (they would still be
    loaded). `target_switch`: the lock-on with L is in the mod, so the item selector shows its hint. Returns the
    single-screen mode's draw order offsets and the game GUI engine's table
    (interface/single_screen/executable/single_screen.patch_single_screen; empty and None without it), and the aspect
    ratio's table of the interface's groups (interface/hud/anchors.py; None without it)."""
    output_dir = result.output_dir
    remove_hud_files(output_dir)
    remove_layered_text_files(output_dir)
    remove_exchange_text_files(output_dir)
    remove_common_text_files(output_dir)
    remove_single_screen_files(output_dir)
    remove_backdrop_files(output_dir)
    # the aspect ratio moves the HUD only with the game's files; it needs no more than the executable to work
    edge = settings.hud_edge if rom is not None else NO_EDGE
    resize_hud = settings.hud_scale != HudScale.FULL or edge != NO_EDGE
    target_hint = target_switch and rom is not None  # the L + D-pad up glyph in the item selector
    if resize_hud:
        hud = dict(hud_files(rom, settings.hud_scale.factor, with_code_patch, target_hint, edge))
    else:
        hud = dict(hint_files(rom)) if target_hint else {}
    anchored = settings.aspect_on and rom is not None
    names = gear_texts.files(lambda path: hud.get(path) or rom.read(path)) if gear_texts else {}
    if menu_texts and rom is not None:      # the START menu's third page: the options and the aspect ratio's list
        names |= mod_settings_texts().files(lambda path: {**hud, **names}.get(path) or rom.read(path))
    texts = dict(layered_text_files(rom, {**hud, **names}, gen=gen_looks, felynes=felynes)) if layered_texts else {}
    if exchange_texts:      # the Wyporium's messages and panes, on top of the other options' copies
        texts.update(exchange_text_files(rom, {**hud, **names, **texts}))
    screens, offsets, engine_table, engine_groups = {}, {}, None, frozenset()
    if single_screen:       # last: it places whole layouts, with what the others added (single_screen.py)
        made = single_screen_romfs(rom, {**hud, **names, **texts}, edge if anchored else None)
        screens, offsets, engine_table, engine_groups = made.files, made.offsets, made.engine_table, made.engine_groups
    written = {**hud, **names, **texts, **screens}
    if rom is not None:     # always: the font's blank characters away from its glyphs (interface/font/blank_glyphs.py)
        written |= font_files(lambda path: written.get(path) or rom.read(path))
    # after all of them: the backdrops of the files as they are, and the table of each layout's final places
    backdrops, anchors = interface_anchors(rom, written, edge, engine_groups) if anchored else ({}, None)
    for path, data in {**written, **backdrops}.items():
        target = output_dir / "romfs" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if path in hud or path in backdrops:
            result.hud_paths.append(target)
        if path in screens:
            result.single_screen_paths.append(target)
    if resize_hud:
        result.hud_scale = HudScale(settings.hud_scale)
    return offsets, engine_table, anchors


@kept_reads()
def run(game: Path, output_dir: Path, settings: Settings, progress: Callable | None = None,
        code_path: Path | None = None, stage: Callable[[str], None] | None = None, record: RunRecord | None = None,
        xx_rom: Path | None = None, console: bool = False, probe: Probe | None = None,
        title_build: bool = False) -> RunResult:
    """`game` is the player's base game (European or American). The executable is his own: the game's, or
    `code_path`'s (a code.bin or game file of any version with a map, for developers and tests). It is laid out as the
    canonical one, every patcher works on that image, and the patched image is carried back onto his bytes
    (game/executable/player_code.py): an executable of no known version raises versions.UnsupportedVersion before any
    work, a patch his version cannot take rebase.RebaseError. A feature whose code his version lacks is left out with a
    notice. `stage` is told when each of STAGES starts. `xx_rom`: MH XX's decrypted .3ds, the only other game a run
    reads, never required: with it (and Layered Gear on) the Smithy also offers XX's looks, whose models are made from
    its files, and the Wyporium trades the rare materials of XX's monsters that MH4U lacks; without it the run has
    MH4U's looks and the Rare Materials Exchange alone. Layered Gear's looks and the new trades open by rank with
    `settings.layered_by_rank`, all at once without it. `progress` and `console` are kept for the installer's sake:
    Heavenfall Beta counts nothing and makes no Luma3DS mod. `title_build`: the mod is for a real 3DS as an installed
    title (install/title/build_title.py): the emulator's form, with the settings a console can use
    (Settings.for_console: no single-screen mode) and the START menu's rows a console allows; its executable reads the
    game from the game data title and the mod's files from its own RomFS first (install/title/split_romfs.py), and its
    exheader may open the game data title. `probe`: a developer probe's own patch, after the mod's (Probe). A module
    whose switch is off in `settings` has every field of it at the game's own value (presets.apply_modules) and no row
    in the START menu's page. Layered Gear's new items are defined in every run, its module on or off, so the
    executable is written even with every module off."""
    if console:
        raise ValueError("Heavenfall Beta makes no Luma3DS mod; its form for a real 3DS is an installed title")
    # The three modules (gui_presets.json install.modules): one that is off leaves the game as it is in all it holds.
    # Their switches are the player's, read before a console's settings: a console has no single-screen mode but keeps
    # the rest of that module, Select and Start
    off = presets.module_off_fields(settings)
    settings = presets.apply_modules(settings)
    screen_module = settings.single_screen
    if title_build:
        settings = settings.for_console()
    if not is_container(game):
        raise ValueError(f"{game} is not a decrypted game file (.3ds, .cia, .zcci, .zcia...)")
    if xx_rom is not None and not Path(xx_rom).is_file():
        raise ValueError(f"{xx_rom}: MH XX's decrypted .3ds is not a file")
    announce = stage or (lambda _name: None)
    announce("rom")
    # The player's executable (the game's, or code_path's) as the canonical one: an unknown one fails before any work
    player = open_code(code_path or game, game)
    code = player.image
    # the installed title reads the game from the game data title: its build refuses an executable that cannot
    if title_build and not (player.exheader is not None and supports_split_romfs(code)):
        raise ValueError("the installed title's build needs the game ROM and its executable's RomFS mount")
    notices = version_notices(player.version)
    # The options a player changes in the game (the START menu's Mod Settings, interface/mod_settings/mod_options.py):
    # every mod carries them, with the Settings values as the defaults of a character with no choice. The page needs the
    # executable's extension (the exheader)
    in_menu = player.exheader is not None and supports_mod_options(code)
    menu_options = [key for key in available_options(code, settings, title_build) if key not in off] if in_menu else []
    if not in_menu:
        notices.append(left_out("Mod Settings", "the cheats, the lock-on with L and holding A are left out",
                                NEEDS_ROM if player.exheader is None else NOT_AVAILABLE))
    in_menu = in_menu and bool(menu_options or settings.aspect_on)
    target_switch = "touchless_target" in menu_options
    patch_interface_code = settings.hud_scale != HudScale.FULL or target_switch
    # the touch screen's menus on the top screen (interface/single_screen/executable/single_screen.py, single_screen.py)
    single_screen = settings.single_screen and supports_single_screen(code)
    if settings.single_screen and not single_screen:
        notices.append(left_out("single screen", "the touch screen's menus stay on it", NOT_AVAILABLE))
    cheats = wants_cheats(settings) and supports_cheats(code)
    if wants_cheats(settings) and not cheats:
        notices.append(left_out("cheats", "the game keeps its picture's shape", NOT_AVAILABLE))
    # Select and Start follow the game's option START (gameplay/select_kick/select_kick.py): no option of the program,
    # part of the single-screen module, on a console too
    select_start = screen_module and supports_select_kick(code)
    if screen_module and not select_start:
        notices.append(left_out("Select and Start", "Select opens the menu like Start and there is no kick button",
                                NOT_AVAILABLE))
    layered = settings.layered_equipment and supports_layered_equipment(code)
    if settings.layered_equipment and not layered:
        notices.append(left_out("layered equipment", "the Smithy has no Layered Equipment line", NOT_AVAILABLE))
    # Without that module Select and Start stay the game's, but their two calls still give Layered Gear's Armor screen
    # its Select (the colour window) and keep the START that skips a death camera out of the Game Menu
    select_plain = (not screen_module and (layered or "skip_death_camera" in menu_options)
                    and supports_select_kick(code))
    exchange = layered and settings.rare_exchange and supports_rare_exchange(code)
    if layered and settings.rare_exchange and not exchange:
        notices.append(left_out("rare materials exchange", "the Wyporium has no Rare Materials Exchange line",
                                NOT_AVAILABLE))
    # MH XX's looks, and the rare materials of its monsters that MH4U lacks: only with its game and Layered Gear
    prepared = cached_pack(Path(xx_rom), Path(game)) if layered and xx_rom is not None else None
    materials = load_materials() if prepared else None
    # the items are defined in every run, Layered Gear on or off and XX's game given or not (their records are
    # committed): a save that got one while Layered Gear was on reads it in any build, never an undefined id's junk
    # record; the trades and the Meownster haul need Layered Gear and XX's game (`materials`)
    defined = materials or (load_materials() if player.exheader is not None and supports_new_items(code) else None)
    notes = session.Session()   # what the patchers write that depends on where the game's code sits
    with session.recording(notes):
        added = add_materials(code, Path(xx_rom) if prepared else None, defined) if defined else None

    announce("write")
    output_dir = mod_folder(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(output_dir=output_dir, seed=settings.seed, notices=notices, mod_title=game_mod_title(game))
    # the models of MH XX's looks (a pack of archives), and the Felynes' looks: the game's own, and MH XX's
    made_from_xx: dict[str, tuple[str, ...]] = {}    # the MH XX files each archive was made from (xx_sources)
    if prepared:
        write_pack_files(output_dir, None, RomFS(game), prepared, RomFS(xx_rom), made_from_xx)
    else:
        remove_pack_files(output_dir)
    felynes = felyne_looks.run_catalog(RomFS(game).exists if layered else None,
                                       RomFS(xx_rom).exists if prepared else None)
    felyne_looks_pack = felyne_looks.convert_looks(RomFS(xx_rom), RomFS(game), felynes) if felynes else None
    felyne_pack.remove_files(output_dir)
    if felyne_looks_pack:
        felyne_pack.write_files(output_dir, felyne_looks_pack)
        made_from_xx.update({"romfs/" + path: read for path, read in felyne_looks_pack.sources.items()})
    write_sources(output_dir, made_from_xx)
    gen_looks = prepared.gen_looks() if prepared else None
    screen_offsets, engine_table, anchors = write_interface_files(
        result, RomFS(game), settings, patch_interface_code, single_screen, in_menu, target_switch, layered, exchange,
        gen_looks, added.texts if added else None, felynes)
    if not (patch_interface_code or single_screen or cheats or select_start or in_menu or layered or exchange
            or added or title_build or probe is not None):
        remove_exefs(output_dir)  # nothing to patch; a patch left by an earlier run would still be applied
    else:
        with session.recording(notes):
            patched = added.code if added else code
            if materials:   # the Wyporium's trades of XX's new materials (gameplay/wyporium/trades.py)
                patched = patch_trades(patched, materials, by_rank=settings.layered_by_rank)
            # room for the executable's extension on an Old 3DS (docs/how_it_works.md, "The executable")
            patched = patch_memory_split(patched, resource_to_root_mb())
            book = added.book if added else None    # the new items by name
            item_ids = {book.english[key]: item for key, item in book.ids.items()} if book else None
            if layered:
                if felyne_looks_pack:
                    patched = felyne_pack.patch_executable(patched, felyne_looks_pack.needs)
                patched = patch_layered_equipment(patched, gen=gen_looks, felynes=felynes, item_ids=item_ids,
                                                  by_rank=settings.layered_by_rank)
                if materials and materials.expedition:
                    # the run has XX's looks, so it has the foreign scraps: each Meownster Hunters expedition
                    # brings one more
                    patched = patch_meownster_scrap(patched, materials.expedition, materials.scrap_ids())
            if exchange:
                patched = patch_rare_exchange(patched, item_ids=item_ids)
            if select_start or select_plain:
                patched = patch_select_kick(patched, plain=select_plain)
            if in_menu:
                patched = patch_mod_options(patched, settings, menu_options, aspect=settings.aspect_on)
            if cheats:
                patched = patch_cheats(patched, settings, anchors=anchors)
            if patch_interface_code:
                patched = patch_interface(patched, settings.hud_scale.factor, target_switch, target_switch,
                                          settings.hud_edge, gated=target_switch)
                result.interface_patched = True
            if single_screen:
                patched = patch_single_screen(patched, screen_offsets, engine_table=engine_table)
            if prepared:    # the executable's tables for the pack's models
                patched = patch_executable(patched, prepared.needs)
            if title_build:     # the installed title's: the game data as `rom:`, its own RomFS first
                patched = patch_split_romfs(patched)
            if probe is not None:
                patched = probe.patch(patched)
        # The patches carried onto the player's own executable, and the whole code.bin written with his game's
        # exheader (extended when a block is in the extension)
        built = player.carry(patched, notes, probe.layout if probe is not None else None)
        result.executable_path = write_exefs(output_dir, player.original, built.code,
                                             title_exheader(player.exheader) if title_build else player.exheader)
        result.game_version = player.version.key
    result.settings_path = output_dir / f"settings_{settings.seed}.json"
    save_run(result.settings_path, settings, record or RunRecord())
    return result


__all__ = ["NEEDS_ROM", "NOT_AVAILABLE", "STAGES", "Probe", "RunResult", "game_mod_title", "left_out", "mod_folder",
           "run", "version_notices", "write_interface_files"]
