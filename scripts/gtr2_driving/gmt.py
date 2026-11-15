r"""Reader for the game's `.gmt` track meshes (ISI gMotor mesh files), read from a `.gtr` archive (see mas.py).

Only what the garage-exit planning needs: world-space triangles. Track meshes are stored in world coordinates (no instance transform
is applied), x east, y up, z north, the same x/z as the telemetry and the AIW.

What is known (checked on PITWALLCOLLIDE, ROADPITGARAGE and OBJ_GARAGE_00 of Anderstorp, matching positions and counts):
    0x000  u32 offset of the object/material list (names, textures; not read here), u32 0x20
    0x16c  u32 number of mesh records, u32 offset of the first record (0x210); records are 108 bytes
    record u32[27]: [1] flags, [3] vertex count, [4] offset of the vertex array, [10] index count, [11] offset of the u16 index array (4-byte lead first)
    vertex 32 bytes: u32 (unknown), position x y z (floats), normal x y z (floats), u32 (unknown)
    triangles: the index array is a triangle list (index count a multiple of 3)
Anything that fails these checks raises GmtError instead of returning guesses. Standard library only; only reads.

    python -I scripts\gtr2_driving\gmt.py ARCHIVE.gtr MESHNAME [MESHNAME ...]     (bounding box and counts)
"""
import struct
import sys

MESH_TABLE = 0x16C
RECORD = 108
VERTEX = 32


class GmtError(ValueError):
    pass


def parse(data):
    """-> list of meshes, each {"flags": int, "vertices": [(x, y, z), ...], "triangles": [(i, j, k), ...]}."""
    if len(data) < MESH_TABLE + 8:
        raise GmtError("file too short")
    count, first = struct.unpack_from("<II", data, MESH_TABLE)
    if not 1 <= count <= 64 or first + count * RECORD > len(data):
        raise GmtError("mesh table at 0x16c does not make sense (count %d, offset %d)" % (count, first))
    out = []
    for m in range(count):
        rec = struct.unpack_from("<27I", data, first + m * RECORD)
        flags, nv, voff, ni, ioff = rec[1], rec[3], rec[4], rec[10], rec[11]
        if voff + nv * VERTEX > len(data) or ioff + 4 + ni * 2 > len(data) or ni % 3:
            raise GmtError("mesh %d: vertex/index arrays outside the file or index count not a multiple of 3" % m)
        verts = [struct.unpack_from("<3f", data, voff + i * VERTEX + 4) for i in range(nv)]
        idx = struct.unpack_from("<%dH" % ni, data, ioff + 4)      # like the vertex array, the index array has a 4-byte lead
        if idx and max(idx) >= nv:
            raise GmtError("mesh %d: index %d beyond %d vertices" % (m, max(idx), nv))
        if any(not all(abs(c) < 1e5 for c in v) for v in verts):
            raise GmtError("mesh %d: vertex positions are not plausible" % m)
        out.append({"flags": flags, "vertices": verts, "triangles": [tuple(idx[i:i + 3]) for i in range(0, ni, 3)]})
    return out


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
    from mas import Mas
    mas = Mas(argv[1])
    for name in argv[2:]:
        for i, mesh in enumerate(parse(mas.read(name if "." in name else name + ".GMT"))):
            v = mesh["vertices"]
            lo = [min(c[k] for c in v) for k in range(3)] if v else None
            hi = [max(c[k] for c in v) for k in range(3)] if v else None
            print("%s mesh %d flags %#x: %d vertices, %d triangles, x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (
                name, i, mesh["flags"], len(v), len(mesh["triangles"]), lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]) if v else "%s mesh %d empty" % (name, i))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
