"""The skinning of a MHGen Felyne body in MH4U.

MHGen's bodies weight vertices to cloth joints (ids 15, 16, 17) that a chain (CTC) moves. MH4U's Felyne path attaches
a chain only for a helm, and none of its 100 body archives weights a joint past the base Felyne's (ids 0-13; the one
exception is 101, a root of its own): the game never drives such a joint for a body, so the vertices skinned to it
are pulled away from the body. `reweight_cloth` gives their weight to the joint they would follow anyway.

Layout of a MOD v0xE6, as far as this needs it (u16 / u32 fields; offsets in the file): +0x06 the bone count, +0x08
the mesh count, +0x28 the bones (24 bytes each: joint id, parent bone index or 0xFF, ...), then two 64-byte matrix
arrays and the 256-byte table joint id -> bone index, then the sets (+0x2C is where they end): a u32 count and 24
bone indices, the palette a mesh's vertices index with their bone bytes (mesh +0x25 picks the set). A vertex has the
bone bytes at 24 and 25 and their weights at 26 and 27; the 36-byte formats (4 weights) add two pairs at 32-35.
"""

import struct
from collections.abc import Iterator

BONE_SIZE, MATRICES, ID_TABLE = 24, 128, 256     # per bone; the two matrix arrays, per bone; the whole table
SET_SIZE, SET_BONES = 28, 24
MESH_SIZE = 0x30
ROOT = 0xFF                                       # a bone's parent byte when it has none
# The joints a Felyne body may weight, in the ids of MH4U's own bodies: the base model's 0-13 and the roots 100 and
# 101 (body 107's). Ids 14 (the weapon) to 99 are joints a body never has (cloth, accessories).
KEPT = frozenset(range(14)) | {100, 101}
# Where a vertex's (bone byte, weight byte) pairs are, per vertex stride.
SLOTS = {28: ((24, 26), (25, 27)), 32: ((24, 26), (25, 27)),
         36: ((24, 26), (25, 27), (32, 34), (33, 35))}


def _vertices(mod: bytes, meshes: int, mesh_count: int, vertex_buffer: int, bone_set: int) -> Iterator[tuple[int, int]]:
    """(offset, stride) of every vertex of the meshes that use set number `bone_set`."""
    for m in range(mesh_count):
        record = mod[meshes + MESH_SIZE * m:meshes + MESH_SIZE * (m + 1)]
        if record[0x25] != bone_set:
            continue
        count, stride = struct.unpack_from("<H", record, 2)[0], record[0x0A]
        if stride not in SLOTS:
            raise ValueError(f"vertex stride {stride} in a mesh of set {bone_set}")
        base, offset = struct.unpack_from("<II", record, 0x0C)
        for v in range(count):
            yield vertex_buffer + offset + (base + v) * stride, stride


def reweight_cloth(mod: bytes) -> bytes:
    """`mod` (a MOD v0xE6) with the weight of every vertex on a joint a body never has (not in KEPT) moved to the
    nearest ancestor that is, the cloth joints leaving the sets they were in and an ancestor the set lacked joining
    it. Positions, the skeleton and everything else stay; a model with no such joint is returned as it is."""
    bone_count, mesh_count = struct.unpack_from("<HH", mod, 6)
    bones, sets_end, _, meshes, vertex_buffer = struct.unpack_from("<5I", mod, 0x28)
    ids = [mod[bones + BONE_SIZE * b] for b in range(bone_count)]
    parents = [mod[bones + BONE_SIZE * b + 1] for b in range(bone_count)]
    foreign = [i not in KEPT for i in ids]
    if not any(foreign):
        return mod

    def kept_ancestor(bone: int) -> int:
        while foreign[bone]:
            if parents[bone] == ROOT:
                if 0 not in ids:
                    raise ValueError("a cloth joint with no ancestor to take its weight")
                return ids.index(0)
            bone = parents[bone]
        return bone

    sets_at = bones + (BONE_SIZE + MATRICES) * bone_count + ID_TABLE
    if (sets_end - sets_at) % SET_SIZE:
        raise ValueError("the sets of the model do not end where its mesh records begin")
    out = bytearray(mod)
    for k in range((sets_end - sets_at) // SET_SIZE):
        entry = sets_at + SET_SIZE * k
        count = struct.unpack_from("<I", mod, entry)[0]
        if count > SET_BONES:
            raise ValueError(f"set {k} lists {count} bones")
        bone_set = list(mod[entry + 4:entry + 4 + count])
        if not any(foreign[b] for b in bone_set):
            continue
        spots = list(_vertices(mod, meshes, mesh_count, vertex_buffer, k))
        keep = [b for b in bone_set if not foreign[b]]
        for at, stride in spots:        # the ancestors the vertices need that the set lacks, in order of need
            for index_at, weight_at in SLOTS[stride]:
                if mod[at + weight_at] and foreign[bone_set[mod[at + index_at]]]:
                    target = kept_ancestor(bone_set[mod[at + index_at]])
                    if target not in keep:
                        keep.append(target)
        if len(keep) > SET_BONES:
            raise ValueError(f"set {k} would list {len(keep)} bones")
        out[entry:entry + SET_SIZE] = struct.pack("<I", len(keep)) + bytes(keep).ljust(SET_BONES, b"\x00")
        for at, stride in spots:        # the same weights, merged where two slots now name one bone
            weights: dict[int, int] = {}
            for index_at, weight_at in SLOTS[stride]:
                if mod[at + weight_at]:
                    bone = kept_ancestor(bone_set[mod[at + index_at]])
                    weights[bone] = weights.get(bone, 0) + mod[at + weight_at]
            slots = list(weights.items()) + [(keep[0] if keep else 0, 0)] * (len(SLOTS[stride]) - len(weights))
            for (index_at, weight_at), (bone, weight) in zip(SLOTS[stride], slots):
                out[at + index_at], out[at + weight_at] = keep.index(bone) if keep else 0, weight
    return bytes(out)
