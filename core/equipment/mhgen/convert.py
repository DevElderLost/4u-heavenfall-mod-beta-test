"""MH Generations' models, materials and textures as MH4U's.

Both games use the same MT Framework formats; what differs:
* TEX: version 0xA6 instead of 0xA5, same header and pixels;
* MOD v0xE6: a header flag (+0x78 bit 31) and the kind of some meshes;
* MRL v0x20: the shader package (system/ltshader/LtShaderPackage.lfx) differs, so every shader record a
  material names (state words, parameters, animation blocks: record_fields) is looked up by name in MH4U's
  package;
* ARC: version 17 instead of 19, and other entry flags.
"""

import struct
import zlib
from collections.abc import Callable, Collection
from dataclasses import dataclass

from core.game.files.arc import Arc, ArcEntry

# ARC entry types (~crc32(class name) & 0x7FFFFFFF).
TEX = 0x241F5DEB         # rTexture
MRL = 0x2749C8A8         # rMaterial
MOD = 0x58A15856         # rModel
CTC = 0x535D969F         # rChain: cloth physics, same version (0x16) in both games
CCL = 0x0026E7FF         # rChainCol: its collision, same version in both games
PARTS_DISP = 0x66C89ED2  # rPlayerPartsDisp: MHGen's hair shown under each helm; MH4U has no such class

MH4U_ARC_VERSION = 19
MH4U_FLAGS = {MOD: 0xA0}  # entry flags of MH4U's equipment archives; MH Generations writes 0x40
MH4U_DEFAULT_FLAGS = 0x20
DROPPED = {PARTS_DISP}

MH4U_TEX_VERSION = 0xA5
MHGEN_TEX_VERSION = 0xA6

MOD_MESH_COUNT, MOD_MESHES, MOD_FLAGS = 0x08, 0x34, 0x78  # MOD v0xE6 header: u16, u32 offset, u32
MOD_GEN_FLAG = 0x80000000  # set in nearly every MH Generations model, in no MH4U one
MESH_SIZE = 0x30
# Mesh kind (+0x00) MHGen -> MH4U, from the meshes of the ~2,000 equipment models both games share and
# Alatreon's tail. Any other kind 0xC... is its 0xE... twin (C_KIND).
MESH_KINDS = {0xC6C8: 0xE6C8, 0xEEDA: 0xE6C8, 0xECF3: 0xECD3}
C_KIND_MASK, C_KIND, C_TO_E = 0xE000, 0xC000, 0x2000

SHADER_VERSION = 52
RECORD_MASK = 0xFFF
RECORD_TAG = 0xFFFFF  # a record word's top 20 bits: the low 20 of ~crc32(the record's name) (record_tag)
STATE_RECORD_SLOTS = (0, 1, 2, 3)  # blend, depth-stencil, rasterizer, input layout; 4 is packed data, 9 a size
ANIMATION_SIZE, ANIMATION = 0x30, 0x38  # a material's animation block: its byte size (state word 9) and offset
# Where an MRL word holds a record's index, as (shift, mask): its low 12 bits, a descriptor's top 12, and in an
# animation block's track the top 10 (the word two after the record word it animates).
LOW, TOP, TRACK = (0, RECORD_MASK), (20, RECORD_MASK), (22, 0x3FF)
MRL_TEXTURE_SIZE = 0x4C  # texture records: u32 type, 8 bytes, path[64]
MRL_TEXTURE = 0x241F5DEB  # the type of a record naming a texture file; type 0 holds sampler data, no path
MRL_TEXTURE_PATH = 0x0C
MRL_PATH_SIZE = 64
MRL_TABLE_ALIGN = 16  # the boundary the files keep their tables at


def shader_records(package: bytes) -> tuple[int, dict[int, str]]:
    """(package hash, {record index: record name}) of an MFX v52 shader package (LtShaderPackage.lfx)."""
    if package[:4] != b"MFX\x00" or struct.unpack_from("<H", package, 4)[0] != SHADER_VERSION:
        raise ValueError("not an MFX v52 shader package")
    package_hash, count = struct.unpack_from("<II", package, 8)
    strings = struct.unpack_from("<I", package, 0x20)[0]
    records = {}
    for i in range(count - 1):
        offset = struct.unpack_from("<I", package, 0x2C + 4 * i)[0]
        name_offset, _, _, index = struct.unpack_from("<4I", package, offset)
        start = strings + name_offset
        records[index >> 16] = package[start:package.index(b"\x00", start)].decode("latin1")
    return package_hash, records


def convert_tex(data: bytes) -> bytes:
    """An MHGen texture (version 0xA6) as MH4U's 0xA5: the header and pixel layout are the same."""
    if data[:4] != b"TEX\x00" or data[4] != MHGEN_TEX_VERSION:
        raise ValueError("not an MH Generations texture")
    return data[:4] + bytes([MH4U_TEX_VERSION]) + data[5:]


def mesh_kind(kind: int) -> int:
    """MH4U's kind for an MHGen mesh kind."""
    if kind in MESH_KINDS:
        return MESH_KINDS[kind]
    return kind | C_TO_E if kind & C_KIND_MASK == C_KIND else kind


def convert_mod(data: bytes) -> bytes:
    """An MHGen MOD v0xE6 as MH4U's: the header flag only MH Generations sets cleared and each mesh's kind
    MH4U's. The rest of the file is the same in both games."""
    if data[:4] != b"MOD\0" or struct.unpack_from("<H", data, 4)[0] != 0xE6:
        raise ValueError("not a MOD v0xE6")
    out = bytearray(data)
    flags = struct.unpack_from("<I", data, MOD_FLAGS)[0]
    struct.pack_into("<I", out, MOD_FLAGS, flags & ~MOD_GEN_FLAG)
    meshes = struct.unpack_from("<I", data, MOD_MESHES)[0]
    for m in range(struct.unpack_from("<H", data, MOD_MESH_COUNT)[0]):
        at = meshes + MESH_SIZE * m
        struct.pack_into("<H", out, at, mesh_kind(struct.unpack_from("<H", data, at)[0]))
    return bytes(out)


def record_tag(name: str) -> int:
    """The top 20 bits of a word naming a shader record (tag << 12 | index): the same for the record in both games'
    packages, whatever its index."""
    return (zlib.crc32(name.encode()) ^ 0xFFFFFFFF) & RECORD_TAG


def _descriptors(data: bytes, base: int, records: dict[int, str]) -> tuple[list[tuple[int, int, int, int]], int]:
    """The parameter descriptors of the 60-byte material at `base` as (offset, a, value, word), and the offset where
    the constant buffer values that follow them start. The list ends at the first word that is not a descriptor of
    one of `records`."""
    size, params = struct.unpack_from("<II", data, base + 8)[0], struct.unpack_from("<I", data, base + 0x34)[0]
    out = []
    at = params
    while at < params + size:
        a, value, word = struct.unpack_from("<III", data, at)
        index = a >> 20
        if a & 0xF not in (1, 2, 3) or index != word & RECORD_MASK or index not in records:
            break  # the descriptors are over; the constant buffer values follow
        out.append((at, a, value, word))
        at += 12
    return out, at


def record_fields(data: bytes, records: dict[int, str]) -> list[tuple[int, tuple[int, int]]]:
    """(offset, field) of every word of an MRL v0x20 that names one of `records` (its package's, by index); a field
    is (shift, mask) of the index in the word (LOW, TOP, TRACK).

    The header names the package by its hash (+0x10). Each 60-byte material keeps state words (+0x0C...; those of
    STATE_RECORD_SLOTS name records in their low 12 bits, 4 is packed data, 9 is the animation block's size), a
    parameter list (+0x34, size at +0x08) of 12-byte descriptors (a, value, word) followed by the constant buffer
    values, and an animation block (ANIMATION, its size at ANIMATION_SIZE; 0: none). Words carry the record index
    in their low 12 bits; `a` carries it in its top 12 and the kind in its low 4 (1 constant buffer, 2 sampler,
    whose value is a record word too, 3 texture). In the animation block, a word whose top 20 bits are the tag
    (record_tag) of the record its low 12 name is a record word, and the word two after it, when its top 10 bits
    name that record, is a track animating it."""
    out = []
    materials, material_table = struct.unpack_from("<I", data, 8)[0], struct.unpack_from("<I", data, 0x18)[0]

    def word_at(at: int) -> int:
        return struct.unpack_from("<I", data, at)[0]

    for m in range(materials):
        base = material_table + 60 * m
        out += [(base + 0x0C + 4 * k, LOW) for k in STATE_RECORD_SLOTS if word_at(base + 0x0C + 4 * k) & RECORD_MASK]
        for at, a, value, word in _descriptors(data, base, records)[0]:
            out.append((at, TOP))
            if a & 0xF == 2 and value & RECORD_MASK:
                out.append((at + 4, LOW))
            if word & RECORD_MASK:
                out.append((at + 8, LOW))
        size, block = word_at(base + ANIMATION_SIZE), word_at(base + ANIMATION)
        words = struct.unpack_from(f"<{size // 4}I", data, block) if block else ()
        for i, word in enumerate(words):
            name = records.get(word & RECORD_MASK)
            if name is None or word >> 12 != record_tag(name):
                continue
            out.append((block + 4 * i, LOW))
            if i + 2 < len(words) and words[i + 2] >> TRACK[0] == word & RECORD_MASK:
                out.append((block + 4 * (i + 2), TRACK))
    return out


def convert_mrl(data: bytes, source: tuple[int, dict[int, str]], target: tuple[int, dict[int, str]]) -> bytes:
    """An MRL v0x20 whose shader records point into `target`'s package instead of `source`'s: its header's package
    hash, and every record it names (record_fields) the record of the same name. Refused when a record has no
    counterpart."""
    source_hash, source_records = source
    target_hash, target_records = target
    by_name = {name: index for index, name in target_records.items()}
    out = bytearray(data)
    magic, version, _, _, package_hash = struct.unpack_from("<4sIIII", data, 0)
    if magic != b"MRL\x00" or version != 0x20 or package_hash != source_hash:
        raise ValueError("not an MRL v0x20 of the source shader package")
    struct.pack_into("<I", out, 0x10, target_hash)
    for at, (shift, mask) in record_fields(data, source_records):
        word = struct.unpack_from("<I", data, at)[0]
        index = word >> shift & mask
        name = source_records.get(index)
        if name not in by_name or by_name[name] > mask:
            raise ValueError(f"shader record {index} ({name}) has no counterpart in the target package")
        struct.pack_into("<I", out, at, word & ~(mask << shift) | by_name[name] << shift)
    return bytes(out)


# ----- the look of a material ----------------------------------------------------------------------------------

STD_MATERIAL = 0x5FB0EBE4  # the class of nDraw::MaterialStd, the material of every equipment piece
STD_BUFFER = "CBMaterialStd"  # its first constant buffer: seven float4 (STD_COLOURS), then the 16 SWITCHES (ints)
STD_COLOURS = ("emission", "diffuse", "specular", "reflection", "ambient", "albedo", "light")
SWITCHES = ("UVSphereMap", "FresnelEnable", "VertexOcclusion", "VertexAlpha", "VertexColorShadow", "AlbedoAlpha",
            "UVExtend", "AlbedoType", "SpecularMaskType", "SpecularMaskExType", "SpecularColorType",
            "ReflectionType", "ReflectionMask", "MirrorNormal", "EnvMap", "ShadowMap")
STD_SWITCH_START = 4 * len(STD_COLOURS)  # index, in floats, of the first switch among the buffer's values
ALBEDO_MAP = "tAlbedoMap"


@dataclass(frozen=True)
class StdMaterial:
    """What a MaterialStd of an MRL says about its look (std_materials)."""
    index: int                    # the material's number in the file
    blend: str                    # its blend state record (BSSolid, BSAddAlpha...)
    albedo: int                   # the texture table entry of tAlbedoMap, 1-based; 0 when it has none
    values: int                   # file offset of the constant buffer's values
    colours: dict[str, tuple[float, ...]]
    switches: dict[str, int]


def std_materials(data: bytes, records: dict[int, str]) -> list[StdMaterial]:
    """The MaterialStd materials of MRL v0x20 `data` (shader package `records`), in file order. ValueError for one
    whose first constant buffer is not CBMaterialStd or holds fewer values than it should."""
    materials, table = struct.unpack_from("<I", data, 8)[0], struct.unpack_from("<I", data, 0x18)[0]
    out = []
    for m in range(materials):
        base = table + 60 * m
        if struct.unpack_from("<I", data, base)[0] != STD_MATERIAL:
            continue
        descriptors, values = _descriptors(data, base, records)
        buffers = [records[a >> 20] for _, a, _, _ in descriptors if a & 0xF == 1]
        size, params = struct.unpack_from("<II", data, base + 8)[0], struct.unpack_from("<I", data, base + 0x34)[0]
        count = STD_SWITCH_START + len(SWITCHES)
        if buffers[:1] != [STD_BUFFER] or (params + size - values) // 4 < count:
            raise ValueError(f"material {m} is a MaterialStd with another layout than {STD_BUFFER}")
        floats = struct.unpack_from(f"<{STD_SWITCH_START}f", data, values)
        ints = struct.unpack_from(f"<{len(SWITCHES)}i", data, values + 4 * STD_SWITCH_START)
        textures = {records[a >> 20]: value for _, a, value, _ in descriptors if a & 0xF == 3}
        out.append(StdMaterial(
            m, records.get(struct.unpack_from("<I", data, base + 0x0C)[0] & RECORD_MASK, "?"),
            textures.get(ALBEDO_MAP, 0), values,
            {name: floats[4 * i:4 * i + 4] for i, name in enumerate(STD_COLOURS)}, dict(zip(SWITCHES, ints))))
    return out


ADDITIVE = "BSAddAlpha"  # the blend of a glow laid over a model
MHGEN_ALBEDO_TYPE = 7  # a value of AlbedoType MH4U's equipment never has (it uses 0 and 9)
MASK_SWITCHES = ("AlbedoAlpha", "VertexAlpha", "SpecularMaskType")  # the switches that read a mask


def is_additive(blend: str) -> bool:
    """Whether the blend state record `blend` adds the material's colour to the picture: every record of the shader
    package named for an addition (BSAddAlpha, BSAddColor, BSBlendAddRGB...); BSSolid and BSBlendAlpha do not."""
    return "Add" in blend


def material_blends(data: bytes, records: dict[int, str]) -> dict[int, tuple[int, str]]:
    """{the hash of a material's name: (its number, its blend state record)} of MRL v0x20 `data` (shader package
    `records`), for a material of any class (std_materials reads MaterialStd only). The hash is the one a MOD's
    material name gives (felyne_face._name_hash)."""
    count, table = struct.unpack_from("<I", data, 8)[0], struct.unpack_from("<I", data, 0x18)[0]
    out = {}
    for m in range(count):
        base = table + 60 * m
        blend = records.get(struct.unpack_from("<I", data, base + 0x0C)[0] & RECORD_MASK, "?")
        out[struct.unpack_from("<I", data, base + 4)[0]] = (m, blend)
    return out


def fit_felyne_materials(data: bytes, records: dict[int, str]) -> bytes:
    """MRL v0x20 `data` (converted, shader package `records`) with the materials of a MHGen Felyne piece made to
    look in MH4U as the game's own gear does:
    * AlbedoType 7 (MHGen's: 150 Felyne materials, none of MH4U's) is 0, with VertexColorShadow;
    * FresnelEnable (the skin patches of MHGen's helms and bodies) is 0: MH4U's equipment has the same material
      without it 158 times, and the switch in 4 hunter materials only, with another ReflectionType.
    Everything else stays byte by byte. The additive shells that no mask reads are not dimmed here: their meshes are
    hidden (felyne_face.hide_additive)."""
    out = bytearray(data)
    for material in std_materials(data, records):
        clear = []
        if material.switches["AlbedoType"] == MHGEN_ALBEDO_TYPE:
            clear += ["AlbedoType", "VertexColorShadow"]
        if material.switches["FresnelEnable"]:
            clear.append("FresnelEnable")
        for name in clear:
            struct.pack_into("<i", out, material.values + 4 * (STD_SWITCH_START + SWITCHES.index(name)), 0)
    return bytes(out)


def _texture_fields(data: bytes) -> list[int]:
    count, table = struct.unpack_from("<I", data, 0x0C)[0], struct.unpack_from("<I", data, 0x14)[0]
    records = (table + MRL_TEXTURE_SIZE * i for i in range(count))
    return [at + MRL_TEXTURE_PATH for at in records if struct.unpack_from("<I", data, at)[0] == MRL_TEXTURE]


def mrl_texture_paths(data: bytes) -> list[str]:
    """The texture paths an MRL names (its records of type MRL_TEXTURE)."""
    return [data[at:at + MRL_PATH_SIZE].split(b"\x00", 1)[0].decode("ascii") for at in _texture_fields(data)]


def rename_mrl_textures(data: bytes, rename: Callable[[str], str]) -> bytes:
    """`data` with each texture path replaced by rename(path), in its fixed 64-byte field."""
    out = bytearray(data)
    for at, old in zip(_texture_fields(data), mrl_texture_paths(data)):
        path = rename(old)
        if path == old:
            continue
        encoded = path.encode("ascii")
        if len(encoded) >= MRL_PATH_SIZE:
            raise ValueError(f"texture path too long: {path}")
        out[at:at + MRL_PATH_SIZE] = encoded.ljust(MRL_PATH_SIZE, b"\x00")
    return bytes(out)


def bare_materials(data: bytes, records: dict[int, str]) -> list[int]:
    """The numbers of the solid MaterialStd materials of MRL v0x20 `data` (shader package `records`) with no albedo map:
    MH XX fills such a map with the coat's skin at run time, and MH4U draws the material black. A glow with no map (an
    additive blend) is another thing, and a material of another class has its own map."""
    return [m.index for m in std_materials(data, records) if not m.albedo and not is_additive(m.blend)]


def give_albedo(data: bytes, records: dict[int, str], materials: Collection[int], path: str) -> bytes:
    """MRL v0x20 `data` with the tAlbedoMap of its materials numbered `materials` naming the texture `path`. A path the
    file has no record of gets one: the table, which grows, is written again at the file's end, and the header follows
    it; no other byte moves. ValueError for a material with no tAlbedoMap to fill, or a file with no texture record
    to copy the new one's words from."""
    count, table = struct.unpack_from("<I", data, 0x0C)[0], struct.unpack_from("<I", data, 0x14)[0]
    entries = [table + MRL_TEXTURE_SIZE * i for i in range(count)]
    named = [at for at in entries if struct.unpack_from("<I", data, at)[0] == MRL_TEXTURE]
    encoded = path.encode("ascii")
    if len(encoded) >= MRL_PATH_SIZE:
        raise ValueError(f"texture path too long: {path}")
    field = encoded.ljust(MRL_PATH_SIZE, b"\x00")
    number = next((entries.index(at) + 1 for at in named
                   if data[at + MRL_TEXTURE_PATH:at + MRL_TEXTURE_PATH + MRL_PATH_SIZE] == field), None)
    out = bytearray(data)
    if number is None:
        if not named:
            raise ValueError("the file has no texture record")
        out += bytes(-len(out) % MRL_TABLE_ALIGN)
        struct.pack_into("<I", out, 0x14, len(out))
        out += data[table:table + MRL_TEXTURE_SIZE * count]
        out += data[named[0]:named[0] + MRL_TEXTURE_PATH] + field
        number = count + 1
        struct.pack_into("<I", out, 0x0C, number)
    first = struct.unpack_from("<I", data, 0x18)[0]
    for material in materials:
        slots = [at for at, a, _, _ in _descriptors(data, first + 60 * material, records)[0]
                 if a & 0xF == 3 and records[a >> 20] == ALBEDO_MAP]
        if len(slots) != 1:
            raise ValueError(f"material {material} has no {ALBEDO_MAP} to fill")
        struct.pack_into("<I", out, slots[0] + 4, number)
    return bytes(out)


def convert_arc(arc: Arc, source: tuple[int, dict[int, str]], target: tuple[int, dict[int, str]]) -> Arc:
    """An MHGen archive as MH4U's: every model, material and texture converted, MHGen-only classes left out,
    MH4U's version and entry flags. `source` and `target` are the two games' shader_records."""
    entries = []
    for entry in arc.entries:
        if entry.type_hash in DROPPED:
            continue
        data = entry.data
        if entry.type_hash == TEX:
            data = convert_tex(data)
        elif entry.type_hash == MOD:
            data = convert_mod(data)
        elif entry.type_hash == MRL:
            data = convert_mrl(data, source, target)
        entries.append(ArcEntry(entry.name, entry.type_hash, data,
                                MH4U_FLAGS.get(entry.type_hash, MH4U_DEFAULT_FLAGS)))
    return Arc(version=MH4U_ARC_VERSION, entries=entries)
