"""Was a jolt a structure hit? Distance from the car's outline to the near-vertical faces of the track's own collision meshes (walls, barriers, fences,
buildings), instead of judging by how hard the jolt was (a seam in the road mesh and a wall can read the same acceleration).

    idx = WallIndex(trk_path)                 # loads the collision meshes once (seconds on a big track); keeps near-vertical faces only
    gap, name = idx.clearance(x, y, z, yaw)   # smallest gap in metres between the car and a face at the car's height (negative: overlapping), the instance name

Pure Python (uses garage.py, gmt.py, mas.py). Used by gtr2-drive-lap.py (--hit-geometry) and gtr2-hit-locate.py.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import garage  # noqa: E402
from gmt import GmtError, parse  # noqa: E402

CELL = 20.0


class WallIndex:
    def __init__(self, trk, ignore=garage.IGNORE_PREFIXES):
        self.cells = {}
        self.count = 0
        arcs = [garage._mas(p) for p in garage.archives(trk)]
        for inst, mesh_name in garage.collision_meshes(trk):
            if inst.upper().startswith(ignore):
                continue
            key = mesh_name.upper()
            data = next((a.read(key) for a in arcs if key in a.entries), None)
            if data is None:
                continue
            try:
                meshes = parse(data)
            except GmtError:
                continue
            for mesh in meshes:
                v = mesh["vertices"]
                for i, j, k in mesh["triangles"]:
                    tri = (v[i], v[j], v[k])
                    if not garage.steep(tri):
                        continue
                    ys = [p[1] for p in tri]
                    item = ([(p[0], p[2]) for p in tri], inst, min(ys), max(ys))
                    xs, zs = [p[0] for p in tri], [p[2] for p in tri]
                    for cx in range(int(min(xs) // CELL), int(max(xs) // CELL) + 1):
                        for cz in range(int(min(zs) // CELL), int(max(zs) // CELL) + 1):
                            self.cells.setdefault((cx, cz), []).append(item)
                    self.count += 1

    def clearance(self, x, y, z, yaw, width=2.0, length=4.8, front=2.6, below=0.15, above=1.0, reach=6.0):
        """(gap m, instance) to the nearest wall face within `reach` m whose height range meets [y - below, y + above]; (None, None) when none is near."""
        here = garage.footprint(x, z, yaw, width, length, front)
        xs, zs = [p[0] for p in here], [p[1] for p in here]
        seen, best, name = set(), None, None
        for cx in range(int((min(xs) - reach) // CELL), int((max(xs) + reach) // CELL) + 1):
            for cz in range(int((min(zs) - reach) // CELL), int((max(zs) + reach) // CELL) + 1):
                for item in self.cells.get((cx, cz), ()):
                    if id(item) in seen:
                        continue
                    seen.add(id(item))
                    poly, inst, lo, hi = item
                    if hi < y - below or lo > y + above:
                        continue
                    g = garage.gap(here, [(poly, inst)])
                    if best is None or g < best:
                        best, name = g, inst
        return (best if best is not None and best < reach else None), name
