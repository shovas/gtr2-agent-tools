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
ROAD_STEP = 0.4      # steep faces of road/terrain meshes lower than this are kerb and edge steps, not walls


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
                    if max(ys) - min(ys) < ROAD_STEP and inst.upper().startswith(("TRACK", "TERRAIN")):
                        continue      # the road's own kerb and edge steps (Spa Track55: 0.13 to 0.23 m high), not a structure
                    item =([(p[0], p[2]) for p in tri], inst, min(ys), max(ys))
                    xs, zs = [p[0] for p in tri], [p[2] for p in tri]
                    for cx in range(int(min(xs) // CELL), int(max(xs) // CELL) + 1):
                        for cz in range(int(min(zs) // CELL), int(max(zs) // CELL) + 1):
                            self.cells.setdefault((cx, cz), []).append(item)
                    self.count += 1

    def point_gap(self, x, y, z, below=0.15, above=1.0, reach=4.0):
        """Distance from the point to the nearest wall face meeting the height band [y - below, y + above] (None when none within `reach`)."""
        best = None
        for cx in range(int((x - reach) // CELL), int((x + reach) // CELL) + 1):
            for cz in range(int((z - reach) // CELL), int((z + reach) // CELL) + 1):
                for poly, inst, lo, hi in self.cells.get((cx, cz), ()):
                    if hi < y - below or lo > y + above:
                        continue
                    d = 0.0 if garage._inside((x, z), poly) else min(garage._seg_dist((x, z), poly[a], poly[(a + 1) % 3]) for a in range(3))
                    if best is None or d < best:
                        best = d
        return best if best is not None and best < reach else None

    def free_widths(self, chain, step=0.5, need=1.5, max_width=40.0):
        """[(left, right)] metres each side of every waypoint of `chain` that a car centre can use before a wall face comes within `need` m
        (the car's half width plus a margin); the waypoints' own road widths are the upper limit. Left/right: physical sides of the direction of travel; trackmap.lateral() is positive to the LEFT."""
        out = []
        for w in chain:
            res = []
            for sign, road in ((1.0, w.left), (-1.0, w.right)):      # (-hz, hx) is the car's physical left, limited by wp_width's left (as in trackmap.smooth_line)
                free = min(road, max_width)
                off = step
                while off <= free + 1e-9:
                    px, pz = w.x + sign * off * (-w.hz), w.z + sign * off * w.hx
                    g = self.point_gap(px, w.y, pz)
                    if g is not None and g < need:
                        free = max(0.0, off - step)
                        break
                    off += step
                res.append(free)
            out.append((res[0], res[1]))
        return out

    def clearance(self,x, y, z, yaw, width=2.0, length=4.8, front=2.6, below=0.15, above=1.0, reach=6.0):
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
