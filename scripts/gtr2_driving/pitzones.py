"""Where the pit lane ends, read from the track's own XPITOUT trigger object.

Purpose: the AIW racing-line file has no pit-exit marker, but each layout's .TRK lists an `xpitout` instance (a mesh with
`Response=VEHICLE,PITSTOP`) whose geometry sits across the lane at the pit exit. The mesh lives in one of the track folder's .gtr
archives (MAS format: 24-byte header, 256-byte entries [flag, offset, size, packed size, name], zlib-packed data at the end of the file).
The mesh is a (slightly skewed) box of 8 vertices (x, y, z floats starting at float index 7 of the unpacked data); its centre is the gate.
Uses only the standard library today (adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md); read-only.
Usage:   python -I scripts/gtr2_driving/pitzones.py GameData/Locations/Anderstorp/SANDERSTORP.AIW   (prints the gates)
Example: from gtr2_driving.pitzones import pit_gates; gates = pit_gates(aiw_path)   # {"in": (x, z) or None, "out": (x, z) or None}
"""
import re
import struct
import sys
import zlib
from pathlib import Path


def mas_entries(data):
    """{upper-case name: (offset, size, packed size)} of a GMOTORMAS archive held in `data` (bytes)."""
    if data[:10] != b"GMOTORMAS1":
        return {}
    count, datasize = struct.unpack_from("<II", data, 16)
    base = len(data) - datasize
    out = {}
    for i in range(count):
        at = 24 + i * 256
        if at + 256 > len(data):
            break
        _flag, off, usz, csz = struct.unpack_from("<4I", data, at)
        name = data[at + 16:at + 256].split(b"\0")[0].decode("latin1").upper()
        out[name] = (base + off, usz, csz)
    return out


def box_centre(mesh):
    """Centre (x, z) of an 8-vertex trigger box, or None if the mesh does not look like one."""
    if len(mesh) < 4 * 31:
        return None
    f = struct.unpack_from("<24f", mesh, 4 * 7)
    v = [f[i:i + 3] for i in range(0, 24, 3)]          # (x, y, z)
    xs, zs = [p[0] for p in v], [p[2] for p in v]
    if any(c != c or abs(c) > 20000 for p in v for c in p) or max(xs) - min(xs) > 150 or max(zs) - min(zs) > 150:
        return None          # a trigger box is a few metres to a few tens of metres across (Imola's is slightly skewed, so no exact test)
    return sum(p[0] for p in v) / 8.0, sum(p[2] for p in v) / 8.0


def pit_gates(aiw):
    """{"in": (x, z) or None, "out": (x, z) or None} for the layout whose AIW is `aiw` (its .trk sits beside it)."""
    aiw = Path(aiw)
    folder = aiw.parent
    trk = next((p for p in folder.iterdir() if p.suffix.lower() == ".trk" and p.stem.lower() == aiw.stem.lower()), None)
    result = {"in": None, "out": None}
    if trk is None:
        return result
    text = trk.read_text(encoding="latin1")
    wanted = {}
    for m in re.finditer(r"Instance=(\w+)\s*\{(.*?)\}", text, re.S):
        mesh = re.search(r"MeshFile=(\S+)", m.group(2))
        for key, tag in (("in", "pitin"), ("out", "pitout")):
            if tag in m.group(1).lower() and mesh:
                wanted[key] = mesh.group(1).upper()
    archives = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() == ".gtr":
            data = p.read_bytes()
            archives.append((data, mas_entries(data)))
    for key, name in wanted.items():
        for data, ents in archives:
            if name in ents:
                off, usz, csz = ents[name]
                try:
                    result[key] = box_centre(zlib.decompress(data[off:off + csz]))
                except zlib.error:
                    pass
                break
    return result


if __name__ == "__main__":
    for a in sys.argv[1:]:
        print(a, pit_gates(a))
