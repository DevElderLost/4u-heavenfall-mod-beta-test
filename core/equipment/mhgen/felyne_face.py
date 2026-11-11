"""The Felyne's face under a MHGen helm in MH4U.

In MH XX a Felyne has no head of its own under the gear: the head is a mesh of the helm (`o_face`; the bare head is
helm 0) and so is the body, both textured with the placeholder `common/o_skin000_BM`, a copy of the file the arc of the
cat's coat holds (`otomo/mod/skin/<coat>`: `common/o_skin<coat>_BM`, only a texture and its material), which the game
evidently swaps in; the eyes and the ears are models of their own (`eye/<coat>`, `ear/<coat>`). MH4U has no such swap:
the placeholder is XX's cream skin, whatever the coat, and the helm's patch is a copy of XX's head, which differs a
little from MH4U's.

MH4U's head, eyes and ears are meshes of the base Felyne model (data/otomo001..006, one per coat), drawn before the
gear, and each eye is two layers on the head's surface: an opaque surround (a cell of the coat's own texture, painted
for that coat) and the alpha-tested iris. Where a helm shows the eyes, the eyes would lie on the patch: a polygon of
the patch's cream around each eye, and the patch and the eyes sharing their depth. So a helm that shows the eyes also
shows the base head (the mask's bits 0, 4 and 5, felyne_pack.HEAD_FACE: its skin and its whiskers, which the patch
carries), as MH4U's own helms do, and its skin patch is hidden (hide_skin_patch): the Felyne's own coat shows
everywhere the patch would, eyes included. A patch left drawn over the head, even sunk behind it, would poke through
it wherever XX's head is bigger than MH4U's (forehead, cheeks, mouth): cream polygons of another colour (Smithy
preview, v1_4). The helm's other surfaces that hug the eyes or the head would share their depth with them and win
pixels frame by frame: clear_of and lift_off move them.
"""

import bisect
import math
import struct
import zlib
from collections.abc import Collection, Sequence

from core.game.data.tuning import tuning
from core.game.files.arc import Arc, ArcEntry, parse_arc
from core.equipment.mhgen import convert
from core.equipment.mhgen.felyne_skin import BONE_SIZE
from core.native import kernels

COPLANAR = tuning("felyne_face", "coplanar")        # a surface this close to an eye or ear sample shares its depth
PARALLEL = tuning("felyne_face", "parallel")        # ... when it also faces the way the sample's surface does
EXTRA_SINKS = tuning("felyne_face", "extra_sinks")
HEAD_LIFTS = tuning("felyne_face", "head_lifts")
# The base Felyne model's mesh groups (mesh +0x04 & 0xFFF; data/otomo001..006, one model per coat): 20-22 the ears,
# 30-65 the eyes.
EAR_GROUPS, EYE_GROUPS = range(20, 23), range(30, 66)
HEAD_GROUPS = (0, 5)        # the head's skin (the mask's bits 0 and 5: felyne_pack.HEAD_FACE)
BASE_COATS = range(1, 7)
CELL = 1.0                  # the grid that finds the triangles near a sample, in the skeleton's unit
WELD = 1e-4                 # vertices closer than this (in the model's own unit) are one point for the normals
SKIN_TEXTURE = "o_skin"     # the start of the file name of the skin patch's albedo texture

# MOD v0xE6, as far as this needs it: u16 bone count (+6), mesh count (+8), material count (+0x0A); u32 offsets of
# the bones (+0x28), the 128-byte material names (+0x30), the 0x30-byte mesh records (+0x34), the vertex buffer
# (+0x38) and the index buffer (+0x3C). After the bones come a rest matrix and an inverse bind matrix each (64
# bytes); the inverse bind matrix's first float is the model's scale: skeleton unit = position * scale + offset.
MOD_COUNTS, MOD_BONES, MOD_NAMES, MOD_MESHES, MOD_VERTICES, MOD_INDICES = 6, 0x28, 0x30, 0x34, 0x38, 0x3C
NAME_SIZE, MATRIX_SIZE, MESH_SIZE = 128, 64, 0x30
MATERIAL_SHIFT = 12         # a mesh's material number is the top nibble of its u16 at +4
MRL_MATERIAL_SIZE = 60
MESH_GROUP = 0xFFF          # a mesh's group is the low bits of the same u16; bit i of a model's +0x108 draws group i
SHADOW_KIND = 0xE6C8        # a mesh of this kind (its first u16) is the shadow's copy of the model: no call draws it
FORM_GROUPS = (1, 2)        # the groups the game turns on and off to change a set's form (FUN_0069998c)
# The vertex formats whose position is three floats at the start of the vertex (stride at mesh +0x0A): the helm
# shells, their skin patches and the base Felyne's own, and (0x82917009, stride 24) four Felyne weapons of MH XX
# (127, 167, 193, 196; tests/equipment/mhgen/test_xx_felyne_glow.py proves their first twelve bytes are positions).
FLOAT_POSITIONS = frozenset({0x43FB3015, 0xD6784014, 0x01B36016, 0xF606F017, 0x82917009})

Vec = tuple[float, float, float]
Sample = tuple[float, float, float, float, float, float]     # a point and the unit normal of its surface


def sunk_positions(positions: Sequence[Vec], strip: Sequence[int], depth: float) -> list[Vec]:
    """`positions` with each vertex moved `depth` behind the surface `strip` (indices into `positions`) draws: along
    the opposite of the average front of the triangles around it. A strip alternates its triangles' winding, the
    front is the counterclockwise side, a repeated index is a degenerate triangle. Vertices at one position (a patch
    repeats those on a seam) take the same step; one in no triangle stays."""
    normals: dict[tuple[int, int, int], list[float]] = {}
    for i in range(len(strip) - 2):
        a, b, c = strip[i:i + 3]
        if a == b or b == c or a == c:
            continue
        if i % 2:
            b, c = c, b
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = positions[a], positions[b], positions[c]
        ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
        face = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)     # its length is twice the area
        for k in (a, b, c):
            total = normals.setdefault(_weld(positions[k]), [0.0, 0.0, 0.0])
            for axis in range(3):
                total[axis] += face[axis]
    out = []
    for position in positions:
        total = normals.get(_weld(position))
        length = math.sqrt(total[0] * total[0] + total[1] * total[1] + total[2] * total[2]) if total else 0.0
        out.append(position if not length else tuple(p - depth * n / length for p, n in zip(position, total)))
    return out


def _weld(position: Vec) -> tuple[int, int, int]:
    x, y, z = position
    return (round(x / WELD), round(y / WELD), round(z / WELD))


def sink_meshes(mod: bytes, meshes: Collection[int], depth: float) -> bytes:
    """MOD v0xE6 `mod` with the vertices of its meshes numbered `meshes` sunk `depth` (skeleton units) behind their
    surface (sunk_positions); every other byte stays. ValueError for a mesh whose vertices are not three floats at
    the start (FLOAT_POSITIONS), an index out of its mesh, or a model with no scale. The native kernel does it when
    it can, else _sink_meshes."""
    out = kernels.sink_meshes(mod, meshes, depth, WELD, FLOAT_POSITIONS, BONE_SIZE)
    return out if out is not None else _sink_meshes(mod, meshes, depth)


def _sink_meshes(mod: bytes, meshes: Collection[int], depth: float) -> bytes:
    """sink_meshes in Python: the native kernel's twin."""
    bone_count, mesh_count = struct.unpack_from("<HH", mod, MOD_COUNTS)
    bones, table, vertices, indices = (struct.unpack_from("<I", mod, at)[0]
                                       for at in (MOD_BONES, MOD_MESHES, MOD_VERTICES, MOD_INDICES))
    scale = struct.unpack_from("<f", mod, bones + (BONE_SIZE + MATRIX_SIZE) * bone_count)[0]
    if not scale > 0:
        raise ValueError("a model without a scale in its first bone's inverse bind matrix")
    out = bytearray(mod)
    for mesh in sorted(meshes):
        if not 0 <= mesh < mesh_count:
            raise ValueError(f"the model has no mesh {mesh}")
        at = table + MESH_SIZE * mesh
        count, stride = struct.unpack_from("<H", mod, at + 2)[0], mod[at + 0x0A]
        base, buffer, fmt, first, length = struct.unpack_from("<5I", mod, at + 0x0C)
        if fmt not in FLOAT_POSITIONS:
            raise ValueError(f"mesh {mesh} has vertex format {fmt:#x}: its positions are not three floats")
        start = vertices + buffer + stride * base
        strip = [i - base for i in struct.unpack_from(f"<{length}H", mod, indices + 2 * first)]
        if any(not 0 <= i < count for i in strip):
            raise ValueError(f"mesh {mesh} indexes vertices outside itself")
        positions = [struct.unpack_from("<3f", mod, start + stride * k) for k in range(count)]
        for k, position in enumerate(sunk_positions(positions, strip, depth / scale)):
            struct.pack_into("<3f", out, start + stride * k, *position)
    return bytes(out)


def _name_hash(name: str) -> int:
    """The hash an MRL material carries (+4) for the MOD material of this name: the complement of its crc32."""
    return zlib.crc32(name.encode()) ^ 0xFFFFFFFF


def _mesh_materials(mod: bytes) -> list[int | None]:
    """Per mesh of `mod`, the hash of the name of its material (_name_hash); None for a number with no name."""
    mesh_count, material_count = struct.unpack_from("<HH", mod, 8)[0], struct.unpack_from("<H", mod, 0x0A)[0]
    names_at, meshes_at = struct.unpack_from("<I", mod, MOD_NAMES)[0], struct.unpack_from("<I", mod, MOD_MESHES)[0]
    names = [mod[names_at + NAME_SIZE * i:names_at + NAME_SIZE * (i + 1)].split(b"\x00", 1)[0].decode("latin1")
             for i in range(material_count)]
    numbers = (struct.unpack_from("<H", mod, meshes_at + MESH_SIZE * mesh + 4)[0] >> MATERIAL_SHIFT
               for mesh in range(mesh_count))
    return [_name_hash(names[number]) if number < len(names) else None for number in numbers]


def skin_patch_meshes(mod: bytes, mrl: bytes, records: dict[int, str]) -> list[int]:
    """The numbers of the meshes of `mod` drawn with a skin texture (SKIN_TEXTURE): their material number picks a
    name of the MOD, whose hash is the MRL material's (`records`: the shader package's, convert.std_materials), and
    that material's albedo map is the texture record `albedo` of the MRL."""
    textures, materials = struct.unpack_from("<I", mrl, 0x14)[0], struct.unpack_from("<I", mrl, 0x18)[0]
    skins = set()
    for material in convert.std_materials(mrl, records):
        if not material.albedo:
            continue
        record = textures + convert.MRL_TEXTURE_SIZE * (material.albedo - 1)
        if struct.unpack_from("<I", mrl, record)[0] == convert.MRL_TEXTURE:
            path = mrl[record + convert.MRL_TEXTURE_PATH:record + convert.MRL_TEXTURE_PATH + convert.MRL_PATH_SIZE]
            if path.split(b"\x00", 1)[0].decode("latin1").rsplit("\\", 1)[-1].startswith(SKIN_TEXTURE):
                skins.add(struct.unpack_from("<I", mrl, materials + MRL_MATERIAL_SIZE * material.index + 4)[0])
    return [mesh for mesh, name_hash in enumerate(_mesh_materials(mod)) if name_hash in skins]


def hide_meshes(mod: bytes, meshes: Collection[int]) -> bytes:
    """MOD v0xE6 `mod` with every vertex of its meshes numbered `meshes` at the position of the mesh's first one: all
    their triangles have no area and draw nothing, and the mesh, its counts and the model's other bytes stay. ValueError
    for a mesh whose vertices are not three floats at the start (FLOAT_POSITIONS) or a mesh the model lacks."""
    mesh_count = struct.unpack_from("<H", mod, MOD_COUNTS + 2)[0]
    table, vertices = (struct.unpack_from("<I", mod, at)[0] for at in (MOD_MESHES, MOD_VERTICES))
    out = bytearray(mod)
    for mesh in sorted(meshes):
        if not 0 <= mesh < mesh_count:
            raise ValueError(f"the model has no mesh {mesh}")
        at = table + MESH_SIZE * mesh
        count, stride = struct.unpack_from("<H", mod, at + 2)[0], mod[at + 0x0A]
        base, buffer, fmt = struct.unpack_from("<3I", mod, at + 0x0C)
        if fmt not in FLOAT_POSITIONS:
            raise ValueError(f"mesh {mesh} has vertex format {fmt:#x}: its positions are not three floats")
        start = vertices + buffer + stride * base
        for k in range(1, count):
            out[start + stride * k:start + stride * k + 12] = mod[start:start + 12]
    return bytes(out)


def hide_skin_patch(arc: Arc, records: dict[int, str]) -> None:
    """Hide the skin patches (skin_patch_meshes) of the model in archive `arc` (a converted helm; `records`: MH4U's
    shader package's): a helm that shows the base head's skin needs no patch, XX's cream skin and copy of XX's head
    (hide_meshes). An archive without a skin patch stays."""
    mrl = next((e for e in arc.entries if e.type_hash == convert.MRL), None)
    for entry in arc.entries:
        if entry.type_hash == convert.MOD and mrl is not None:
            patches = skin_patch_meshes(entry.data, mrl.data, records)
            if patches:
                entry.data = hide_meshes(entry.data, patches)


# ----- the additive shells ------------------------------------------------------------------------------------------


def additive_meshes(mod: bytes, mrl: bytes, records: dict[int, str]) -> list[int]:
    """The numbers of the meshes of `mod` drawn with an additive material of `mrl` (any class, convert.is_additive of
    its blend state; `records`: the shader package's), masked or not: a converted piece keeps no glow."""
    additive = {name_hash for name_hash, (_, blend) in convert.material_blends(mrl, records).items()
                if convert.is_additive(blend)}
    return [mesh for mesh, name_hash in enumerate(_mesh_materials(mod)) if name_hash in additive]


def _vertex_users(mod: bytes, mesh: int) -> tuple[int, set[int]]:
    """(vertex buffer offset, the vertices) a mesh's record and its strip use: its own range, base to base + count,
    and every index of the strip, as numbers in the buffer."""
    at = struct.unpack_from("<I", mod, MOD_MESHES)[0] + MESH_SIZE * mesh
    count = struct.unpack_from("<H", mod, at + 2)[0]
    base, buffer, _, first, length = struct.unpack_from("<5I", mod, at + 0x0C)
    indices = struct.unpack_from("<I", mod, MOD_INDICES)[0] + 2 * first
    return buffer, set(range(base, base + count)) | set(struct.unpack_from(f"<{length}H", mod, indices))


def _strip_range(mod: bytes, mesh: int) -> range:
    """The places in the index buffer a mesh's strip takes (mesh +0x18 the first, +0x1C the count)."""
    at = struct.unpack_from("<I", mod, MOD_MESHES)[0] + MESH_SIZE * mesh
    first, length = struct.unpack_from("<2I", mod, at + 0x18)
    return range(first, first + length)


def collapse_strips(mod: bytes, meshes: Collection[int]) -> bytes:
    """MOD v0xE6 `mod` with every index of the strips of its meshes numbered `meshes` set to the strip's first: all
    their triangles have one vertex three times, no area, and draw nothing, whatever the vertex format (hide_meshes
    needs float positions). The vertices, the records and the model's other bytes stay. ValueError for a mesh the
    model lacks."""
    mesh_count = struct.unpack_from("<H", mod, MOD_COUNTS + 2)[0]
    indices = struct.unpack_from("<I", mod, MOD_INDICES)[0]
    out = bytearray(mod)
    for mesh in sorted(meshes):
        if not 0 <= mesh < mesh_count:
            raise ValueError(f"the model has no mesh {mesh}")
        places = _strip_range(mod, mesh)
        if places:
            first = mod[indices + 2 * places.start:indices + 2 * places.start + 2]
            out[indices + 2 * places.start:indices + 2 * places.stop] = first * len(places)
    return bytes(out)


def hide_apart(mod: bytes, meshes: Collection[int], what: str) -> bytes:
    """Hide `meshes`: those with float positions (FLOAT_POSITIONS) by hide_meshes, after making sure no mesh that stays
    reads a vertex of one that goes (the move would damage it); the others by collapse_strips, after making sure no
    mesh that stays shares a place of their strips. ValueError when one does (`what`: the kind of mesh hidden, for
    the message)."""
    table = struct.unpack_from("<I", mod, MOD_MESHES)[0]
    floats = {m for m in meshes
              if struct.unpack_from("<I", mod, table + MESH_SIZE * m + 0x14)[0] in FLOAT_POSITIONS}
    strips = set(meshes) - floats
    moved = {m: _vertex_users(mod, m) for m in floats}
    collapsed = {m: set(_strip_range(mod, m)) for m in strips}
    for mesh in set(range(struct.unpack_from("<H", mod, MOD_COUNTS + 2)[0])) - set(meshes):
        buffer, used = _vertex_users(mod, mesh)
        for gone, (gone_buffer, gone_used) in moved.items():
            if buffer == gone_buffer and used & gone_used:
                raise ValueError(f"mesh {mesh} uses vertices of the {what} mesh {gone}")
        places = set(_strip_range(mod, mesh))
        for gone, gone_places in collapsed.items():
            if places & gone_places:
                raise ValueError(f"mesh {mesh} shares its strip with the {what} mesh {gone}")
    return collapse_strips(hide_meshes(mod, floats), strips)


def hide_additive(arc: Arc, records: dict[int, str]) -> int:
    """Hide the additive meshes (additive_meshes) of the model in archive `arc` (`records`: MH4U's shader package's;
    hide_apart): an additive pass over a converted piece is a white veil and a halo at any strength of its colours,
    masked or not. Returns how many meshes.
    ValueError when a mesh that stays reads a vertex or a strip place of one that is hidden (hiding would damage it):
    that happens in no piece of MH XX's gear."""
    mrl = next((e for e in arc.entries if e.type_hash == convert.MRL), None)
    hidden = 0
    for entry in arc.entries:
        if entry.type_hash != convert.MOD or mrl is None:
            continue
        shells = additive_meshes(entry.data, mrl.data, records)
        if shells:
            entry.data = hide_apart(entry.data, shells, "additive")
            hidden += len(shells)
    return hidden


# ----- what MH XX decides while it runs: a material's skin, a set's form --------------------------------------------


def bare_skin_meshes(mod: bytes, mrl: bytes, records: dict[int, str]) -> list[int]:
    """The numbers of the meshes of `mod` that draw with a material of `mrl` with no texture (convert.bare_materials).
    The shadow's copy of a model (SHADOW_KIND) never draws on the picture, so its material does not matter."""
    table = struct.unpack_from("<I", mrl, 0x18)[0]
    bare = {struct.unpack_from("<I", mrl, table + MRL_MATERIAL_SIZE * m + 4)[0]
            for m in convert.bare_materials(mrl, records)}
    meshes_at = struct.unpack_from("<I", mod, MOD_MESHES)[0]
    return [mesh for mesh, name_hash in enumerate(_mesh_materials(mod)) if name_hash in bare
            and struct.unpack_from("<H", mod, meshes_at + MESH_SIZE * mesh)[0] != SHADOW_KIND]


def dress_bare_skin(arc: Arc, records: dict[int, str], skin: ArcEntry) -> list[int]:
    """Give the materials with no texture that a mesh draws with (bare_skin_meshes) the texture `skin`, the piece's
    skin as every other Felyne piece names and carries it: the material draws cream, not black, and a helm's bare copy
    of the head is a skin patch like any other (skin_patch_meshes, hide_skin_patch). The texture's entry joins the
    archive when it lacks it. Returns the meshes. `records`: MH4U's shader package's."""
    mrl = next((e for e in arc.entries if e.type_hash == convert.MRL), None)
    mod = next((e for e in arc.entries if e.type_hash == convert.MOD), None)
    if mrl is None or mod is None:
        return []
    meshes = bare_skin_meshes(mod.data, mrl.data, records)
    if not meshes:
        return []
    table = struct.unpack_from("<I", mrl.data, 0x18)[0]
    numbers = {struct.unpack_from("<I", mrl.data, table + MRL_MATERIAL_SIZE * m + 4)[0]: m
               for m in convert.bare_materials(mrl.data, records)}
    hashes = _mesh_materials(mod.data)
    mrl.data = convert.give_albedo(mrl.data, records, sorted({numbers[hashes[mesh]] for mesh in meshes}), skin.name)
    if skin.name not in {e.name for e in arc.entries if e.type_hash == skin.type_hash}:
        arc.entries.insert(0, ArcEntry(skin.name, skin.type_hash, skin.data, skin.flags))
    return meshes


def second_form_meshes(mod: bytes) -> list[int]:
    """The meshes of `mod` the game keeps hidden at rest in a set with two forms (FORM_GROUPS): group 0 is always
    drawn and, of its groups 1 and 2, the lower one is (FUN_0069998c: ids 0xAB and 0xAC). Other group numbers (a
    set's fists, its eyes) are no forms. Nothing for a model with no lower group to keep."""
    table = struct.unpack_from("<I", mod, MOD_MESHES)[0]
    groups = [struct.unpack_from("<H", mod, table + MESH_SIZE * m + 4)[0] & MESH_GROUP
              for m in range(struct.unpack_from("<H", mod, MOD_COUNTS + 2)[0])]
    forms = {group for group in groups if group in FORM_GROUPS}
    if not forms or max(forms) == min(groups):
        return []
    return [m for m, group in enumerate(groups) if group == max(forms)]


def hide_second_form(arc: Arc) -> list[int]:
    """Hide second_form_meshes of the model in archive `arc`, a piece of a set with two forms. Gear draws every group
    unless the game clears one, and the game only does for its own ids: both forms would be drawn at once. Returns the
    meshes. ValueError as hide_additive."""
    hidden = []
    for entry in arc.entries:
        if entry.type_hash == convert.MOD:
            meshes = second_form_meshes(entry.data)
            if meshes:
                entry.data = hide_apart(entry.data, meshes, "second form's")
                hidden += meshes
    return hidden


# ----- the base model's eyes and ears, and the helm surfaces that lie on them ----------------------------------------


WorldMesh = tuple[int, list[Vec], list[tuple[int, int, int]]]     # group, vertices, triangles


def world_meshes(mod: bytes, only: Collection[int] | None = None) -> list[WorldMesh]:
    """Per mesh of MOD v0xE6 `mod` (positions three floats, FLOAT_POSITIONS): its group (mesh +0x04 & 0xFFF), its
    vertices in the skeleton's unit (position x scale + offset, which holds for every bone at rest: the rest
    rotations are identity) and its triangles (front side counterclockwise, as sunk_positions reads a strip).
    `only`: just these meshes (the others come back empty). ValueError for another vertex format."""
    bone_count, mesh_count = struct.unpack_from("<HH", mod, MOD_COUNTS)
    bones, table, vertices, indices = (struct.unpack_from("<I", mod, at)[0]
                                       for at in (MOD_BONES, MOD_MESHES, MOD_VERTICES, MOD_INDICES))
    local = struct.unpack_from("<3f", mod, bones + BONE_SIZE * bone_count + 48)      # bone 0's rest translation
    inverse = bones + (BONE_SIZE + MATRIX_SIZE) * bone_count
    scale = struct.unpack_from("<f", mod, inverse)[0]
    shift = struct.unpack_from("<3f", mod, inverse + 48)
    offset = tuple(a + b for a, b in zip(local, shift))
    out = []
    for mesh in range(mesh_count):
        at = table + MESH_SIZE * mesh
        count, tag = struct.unpack_from("<HH", mod, at + 2)
        if only is not None and mesh not in only:
            out.append((tag & 0xFFF, [], []))
            continue
        stride = mod[at + 0x0A]
        base, buffer, fmt, first, length = struct.unpack_from("<5I", mod, at + 0x0C)
        if fmt not in FLOAT_POSITIONS:
            raise ValueError(f"mesh {mesh} has vertex format {fmt:#x}: its positions are not three floats")
        points = []
        for k in range(count):
            position = struct.unpack_from("<3f", mod, vertices + buffer + stride * (base + k))
            points.append(tuple(p * scale + o for p, o in zip(position, offset)))
        strip = [i - base for i in struct.unpack_from(f"<{length}H", mod, indices + 2 * first)]
        triangles = []
        for i in range(len(strip) - 2):
            a, b, c = strip[i:i + 3]
            if len({a, b, c}) == 3 and all(0 <= k < count for k in (a, b, c)):
                triangles.append((a, b, c) if i % 2 == 0 else (a, c, b))
        out.append((tag & 0xFFF, points, triangles))
    return out


def _unit_normal(a: Vec, b: Vec, c: Vec) -> Vec | None:
    """The unit normal of triangle abc (its front side), None for a degenerate one."""
    ab, ac = _sub(b, a), _sub(c, a)
    n = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
    length = math.sqrt(_dot(n, n))
    return tuple(x / length for x in n) if length > 1e-12 else None


def face_samples(coats: Sequence[bytes]) -> dict[str, list[Sample]]:
    """Points on the surface of the base Felyne's eyes, ears and head skin (`coats`: its MOD files, data/otomo001..006),
    each with the unit normal of its triangle: per triangle its corners, edge midpoints and centre, each distinct
    point once."""
    out = {"eyes": [], "ears": [], "head": []}
    seen = {"eyes": set(), "ears": set(), "head": set()}
    for mod in coats:
        for group, points, triangles in world_meshes(mod):
            kind = ("eyes" if group in EYE_GROUPS else "ears" if group in EAR_GROUPS
                    else "head" if group in HEAD_GROUPS else None)
            for a, b, c in triangles if kind else ():
                a, b, c = points[a], points[b], points[c]
                normal = _unit_normal(a, b, c)
                if normal is None:
                    continue
                for p in (a, b, c, *(tuple((x[k] + y[k]) / 2 for k in range(3)) for x, y in ((a, b), (b, c), (c, a))),
                          tuple((a[k] + b[k] + c[k]) / 3 for k in range(3))):
                    key = tuple(round(x, 3) for x in p)
                    if key not in seen[kind]:
                        seen[kind].add(key)
                        out[kind].append((*p, *normal))
    return out


def base_face_samples(m4) -> dict[str, list[Sample]]:
    """face_samples of MH4U's base Felyne (`m4`, a RomFS of the game; a coat it lacks adds none)."""
    paths = [f"data/otomo{coat:03d}.arc" for coat in BASE_COATS]
    return face_samples([next(e.data for e in parse_arc(m4.read(path)).entries if e.type_hash == convert.MOD)
                         for path in paths if m4.exists(path)])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _closest(p: Vec, a: Vec, b: Vec, c: Vec) -> Vec:
    """The point of triangle abc nearest to p (Ericson, Real-Time Collision Detection). Written out per axis, every
    sum left to right: the native kernel computes it in the same order."""
    (px, py, pz), (ax, ay, az), (bx, by, bz), (cx, cy, cz) = p, a, b, c
    abx, aby, abz, acx, acy, acz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    apx, apy, apz = px - ax, py - ay, pz - az
    d1, d2 = abx * apx + aby * apy + abz * apz, acx * apx + acy * apy + acz * apz
    if d1 <= 0 and d2 <= 0:
        return a
    bpx, bpy, bpz = px - bx, py - by, pz - bz
    d3, d4 = abx * bpx + aby * bpy + abz * bpz, acx * bpx + acy * bpy + acz * bpz
    if d3 >= 0 and d4 <= d3:
        return b
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        t = d1 / (d1 - d3)
        return (ax + t * abx, ay + t * aby, az + t * abz)
    cpx, cpy, cpz = px - cx, py - cy, pz - cz
    d5, d6 = abx * cpx + aby * cpy + abz * cpz, acx * cpx + acy * cpy + acz * cpz
    if d6 >= 0 and d5 <= d6:
        return c
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        t = d2 / (d2 - d6)
        return (ax + t * acx, ay + t * acy, az + t * acz)
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        t = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return (bx + t * (cx - bx), by + t * (cy - by), bz + t * (cz - bz))
    total = 1 / (va + vb + vc)
    v, w = vb * total, vc * total
    return (ax + abx * v + acx * w, ay + aby * v + acy * w, az + abz * v + acz * w)


def _samples_on(points: list[Vec], triangles: list[tuple[int, int, int]], samples: Collection[Sample],
                margin: float) -> int:
    """How many of `samples` lie on the surface of the triangles: within `margin` of a triangle that faces the same
    way (its normal within PARALLEL of the sample's, either side). A surface that only crosses an eye or an ear
    shares its depth with it along a line, not over an area.

    The triangles near a sample are those whose box, grown by `margin`, spans the sample's cell of a grid (CELL),
    tried in their order until one holds the sample; a triangle with no area never does. Per axis and per cell
    coordinate some sample has, the triangles whose box spans it are the bits of an int: a sample's triangles are
    the three ints of its cell ANDed."""
    if not triangles:
        return 0
    low = [min(p[k] for p in points) - margin for k in range(3)]
    high = [max(p[k] for p in points) + margin for k in range(3)]
    near = [s for s in samples if all(low[k] <= s[k] <= high[k] for k in range(3))]
    if not near:
        return 0
    cells = [(math.floor(s[0] / CELL), math.floor(s[1] / CELL), math.floor(s[2] / CELL)) for s in near]
    values = [sorted({cell[k] for cell in cells}) for k in range(3)]
    spans: list[dict[int, int]] = [dict.fromkeys(axis, 0) for axis in values]
    for number, (i, j, n) in enumerate(triangles):
        a, b, c = points[i], points[j], points[n]
        bit = 1 << number
        for k in range(3):
            lo = math.floor((min(a[k], b[k], c[k]) - margin) / CELL)
            hi = math.floor((max(a[k], b[k], c[k]) + margin) / CELL)
            axis, span = values[k], spans[k]
            for value in axis[bisect.bisect_left(axis, lo):bisect.bisect_right(axis, hi)]:
                span[value] |= bit
    normals: dict[int, Vec | None] = {}
    count = 0
    for s, (x, y, z) in zip(near, cells):
        near_triangles = spans[0][x] & spans[1][y] & spans[2][z]
        while near_triangles:
            lowest = near_triangles & -near_triangles
            near_triangles ^= lowest
            number = lowest.bit_length() - 1
            a, b, c = (points[i] for i in triangles[number])
            if number not in normals:
                normals[number] = _unit_normal(a, b, c)
            normal = normals[number]
            if normal is None:
                continue
            q = _closest(s[:3], a, b, c)
            dx, dy, dz = s[0] - q[0], s[1] - q[1], s[2] - q[2]
            if math.sqrt(dx * dx + dy * dy + dz * dz) < margin and abs(_dot(normal, s[3:])) >= PARALLEL:
                count += 1
                break
    return count


def coplanar_counts(mod: bytes, samples: Collection[Sample], margin: float = COPLANAR,
                    only: Collection[int] | None = None) -> dict[int, int]:
    """Per mesh of `mod` (`only` these) that has a surface on some of `samples` (_samples_on): how many. The native
    kernel counts when it can, else world_meshes and _samples_on."""
    counts = kernels.coplanar_counts(mod, samples, margin, CELL, PARALLEL, FLOAT_POSITIONS, BONE_SIZE, only)
    if counts is None:
        counts = [_samples_on(points, triangles, samples, margin) for _, points, triangles in world_meshes(mod, only)]
    return {i: n for i, n in enumerate(counts) if n}


def clear_of(mod: bytes, samples: Collection[Sample]) -> bytes:
    """MOD `mod` with each mesh that lies within COPLANAR of `samples` (the eyes and ears the base keeps showing)
    sunk behind its own front (sink_meshes), more each time (EXTRA_SINKS) until it clears them all: the skin patch's
    cure, for any surface of a helm (its own texture too) that shares its depth with them. A mesh no depth clears
    keeps the depth that left it the fewest samples."""
    out = mod
    for mesh in coplanar_counts(mod, samples):
        best, fewest = out, coplanar_counts(out, samples, only=[mesh]).get(mesh, 0)
        for depth in EXTRA_SINKS:
            trial = sink_meshes(out, [mesh], depth)
            left = coplanar_counts(trial, samples, only=[mesh]).get(mesh, 0)
            if left < fewest:
                best, fewest = trial, left
            if not left:
                break
        out = best
    return out


def lift_off(mod: bytes, samples: Collection[Sample], skip: Collection[int] = ()) -> bytes:
    """MOD `mod` with each mesh (but `skip`) that lies within COPLANAR of `samples` (the base head's skin, drawn
    under the helm) moved in front of its own surface, more each time (HEAD_LIFTS) until it clears them all: a
    surface that hugs the head would share its depth with it and win pixels frame by frame. `samples` also holds the
    eyes and ears, so that a lift never lands on them. A mesh no depth clears keeps the one that left it the fewest
    samples."""
    out = mod
    wanted = [i for i in range(struct.unpack_from("<H", mod, 8)[0]) if i not in skip]
    for mesh in coplanar_counts(mod, samples, only=wanted):
        best, fewest = out, coplanar_counts(out, samples, only=[mesh]).get(mesh, 0)
        for depth in HEAD_LIFTS:
            trial = sink_meshes(out, [mesh], -depth)
            left = coplanar_counts(trial, samples, only=[mesh]).get(mesh, 0)
            if left < fewest:
                best, fewest = trial, left
            if not left:
                break
        out = best
    return out


def fit_head(arc: Arc, records: dict[int, str], samples: Collection[Sample], skin: bool,
             head: Collection[Sample] = ()) -> None:
    """The converted helm in `arc` made fit for the base Felyne that shows under it: its skin patch hidden when `skin`
    (the eyes show, so the head's skin does: the coat shows there), every surface within COPLANAR of an eye or ear
    sample (`samples`: those its head mask keeps showing) sunk behind it (clear_of), and every other one that hugs
    the head skin (`head`, when its mask shows it) lifted off it (lift_off)."""
    if skin:
        hide_skin_patch(arc, records)
    mrl = next((e for e in arc.entries if e.type_hash == convert.MRL), None)
    for entry in arc.entries:
        if entry.type_hash != convert.MOD:
            continue
        if samples:
            entry.data = clear_of(entry.data, samples)
        if head:
            patches = skin_patch_meshes(entry.data, mrl.data, records) if mrl is not None else []
            entry.data = lift_off(entry.data, [*head, *samples], patches)
