r"""Garage walls from the track's own collision meshes: what is in the way when the car leaves its box.

Reads the layout's `.trk` scene list (instances with `CollTarget=True`), finds each mesh in the `.gtr` archives the `.trk` names (mas.py),
parses its triangles (gmt.py; world coordinates, x/z as in the telemetry) and keeps those that can touch a car standing on the floor
near the start: triangles whose height range overlaps [floor + 0.15, floor + car height]. Everything is 2D after that (x, z).

    obstacles(layout_trk, start_xz, radius=30)        -> list of 2D triangles [(x, z), (x, z), (x, z)] (floor found from the meshes)
    swept_clearance(obstacles, start, yaw, bias, ...) -> smallest gap (m) between the car's footprint and any obstacle along a straight run;
                                                          negative = the car overlaps one (a hit)
    best_bias(...)                                    -> the yaw bias (degrees) with the largest clearance

Yaw is the telemetry's: forward = (-sin(yaw), -cos(yaw)) in (x, z). Standard library only; only reads. CLI: scripts\gtr2-garage-map.py.
"""
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gmt import GmtError, parse  # noqa: E402
from mas import Mas  # noqa: E402

_mas_cache = {}


def _mas(path):
    key = str(path).lower()
    if key not in _mas_cache:
        _mas_cache[key] = Mas(path)
    return _mas_cache[key]


def archives(trk):
    """The .gtr files a .trk names, found along its SearchPath lines (relative to the game folder, which is trk's grandparent's parent)."""
    trk = Path(trk)
    text = trk.read_bytes().decode("latin1")
    root = trk.parents[3]            # <game>\GameData\Locations\<venue>\x.trk -> <game>
    dirs = [root / p.replace("\\", "/") for p in re.findall(r"^SearchPath=(\S+)", text, re.M | re.I)]
    out = []
    for name in re.findall(r"^MASFile=(\S+)", text, re.M | re.I):
        for d in dirs:
            if (d / name).exists():
                out.append(d / name)
                break
    return out


def collision_meshes(trk):
    """[(instance, mesh file name)] with CollTarget=True."""
    text = Path(trk).read_bytes().decode("latin1")
    out = []
    for name, body in re.findall(r"Instance=(\S+)\s*\{(.*?)\}", text, re.S):
        m = re.search(r"MeshFile=(\S+)\s+CollTarget=(\w+)", body)
        if m and m.group(2).lower() == "true":
            out.append((name, m.group(1)))
    return out


def triangles_near(trk, start_xz, radius=30.0):
    """3D triangles [((x, y, z) x3), instance name] of every collision mesh with a vertex within `radius` m of the start."""
    arcs = [_mas(p) for p in archives(trk)]
    sx, sz = start_xz
    out = []
    for inst, mesh_name in collision_meshes(trk):
        key = mesh_name.upper()
        data = None
        for a in arcs:
            if key in a.entries:
                data = a.read(key)
                break
        if data is None:
            continue
        try:
            meshes = parse(data)
        except GmtError:
            continue
        for mesh in meshes:
            v = mesh["vertices"]
            if not any(math.hypot(p[0] - sx, p[2] - sz) < radius for p in v):
                continue
            for i, j, k in mesh["triangles"]:
                tri = (v[i], v[j], v[k])
                if any(math.hypot(p[0] - sx, p[2] - sz) < radius for p in tri):
                    out.append((tri, inst))
    return out


def steep(tri, max_ny=0.6):
    """True when the triangle's normal is closer to horizontal than max_ny (|ny| / |n|): a wall, not a floor."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    return n > 1e-9 and abs(ny) / n < max_ny


# Collision meshes that are not in a car's way although they are flagged CollTarget=True: the garage doors (PDOOR00..) sit across every
# garage opening at the start, yet all 34 layouts' garage exits drive through them (they open; checked 2026-11-14).
IGNORE_PREFIXES = ("PDOOR",)


def obstacles(trk, start_xz, radius=30.0, floor=None, car_height=1.2, step_up=0.15):
    """2D triangles [(x, z)] x3 that overlap the car's height band, and the floor height used."""
    tris = [t for t in triangles_near(trk, start_xz, radius) if not t[1].upper().startswith(IGNORE_PREFIXES)]
    if floor is None:
        sx, sz = start_xz
        ys = sorted(p[1] for tri, _ in tris for p in tri if math.hypot(p[0] - sx, p[2] - sz) < 3.0)
        floor = ys[0] if ys else 0.0
    lo, hi = floor + step_up, floor + car_height
    out = []
    for tri, inst in tris:
        ys = [p[1] for p in tri]
        if not (max(ys) > lo and min(ys) < hi):
            continue
        if not steep(tri):          # floors, road and kerbs are not walls: only near-vertical faces stop a car
            continue
        out.append(([(p[0], p[2]) for p in tri], inst))
    return out, floor


def _seg_dist(p, a, b):
    ax, az, bx, bz = a[0], a[1], b[0], b[1]
    dx, dz = bx - ax, bz - az
    t = 0.0 if dx == dz == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / (dx * dx + dz * dz)))
    return math.hypot(p[0] - ax - t * dx, p[1] - az - t * dz)


def _inside(p, poly):
    """Point in a convex-or-not polygon (ray casting)."""
    x, z = p
    c = False
    for i in range(len(poly)):
        (x1, z1), (x2, z2) = poly[i], poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < (x2 - x1) * (z - z1) / (z2 - z1) + x1:
            c = not c
    return c


def _seg_cross(a, b, c, d):
    def o(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return o(a, b, c) * o(a, b, d) < 0 and o(c, d, a) * o(c, d, b) < 0


def footprint(x, z, yaw, width, length, front):
    """Car rectangle corners (x, z): `front` m ahead of the reference point, length - front behind it."""
    fx, fz = -math.sin(math.radians(yaw)), -math.cos(math.radians(yaw))
    rx, rz = -fz, fx                      # to the right-hand side (unused sign: symmetric)
    hw = width / 2.0
    pts = []
    for f, s in ((front, -hw), (front, hw), (front - length, hw), (front - length, -hw)):
        pts.append((x + fx * f + rx * s, z + fz * f + rz * s))
    return pts


def gap(poly_a, tris):
    """Smallest distance from a rectangle to the triangles; negative when they overlap."""
    best = 1e9
    minx, maxx = min(p[0] for p in poly_a), max(p[0] for p in poly_a)
    minz, maxz = min(p[1] for p in poly_a), max(p[1] for p in poly_a)
    for tri, _inst in tris:
        if (min(p[0] for p in tri) > maxx + best or max(p[0] for p in tri) < minx - best
                or min(p[1] for p in tri) > maxz + best or max(p[1] for p in tri) < minz - best):
            continue
        for i in range(4):
            a, b = poly_a[i], poly_a[(i + 1) % 4]
            for j in range(3):
                c, d = tri[j], tri[(j + 1) % 3]
                if _seg_cross(a, b, c, d):
                    return -1.0
                best = min(best, _seg_dist(a, c, d), _seg_dist(b, c, d), _seg_dist(c, a, b), _seg_dist(d, a, b))
        if _inside(poly_a[0], tri) or _inside(tri[0], poly_a):
            return -1.0
    return best


def swept_clearance(obs, start_xz, yaw, bias, run=6.0, width=2.0, length=4.8, front=2.6, step=0.25, ramp=2.0):
    """Smallest gap along a run of `run` m that turns from the car's heading onto yaw + bias over the first `ramp` m."""
    h = yaw + bias
    fx, fz = -math.sin(math.radians(h)), -math.cos(math.radians(h))
    reach = run + length + width + 3.0      # nothing farther than this from the start can touch the car on this run
    obs = [o for o in obs if any(math.hypot(p[0] - start_xz[0], p[1] - start_xz[1]) < reach for p in o[0])]
    here = footprint(start_xz[0], start_xz[1], yaw, width, length, front)
    obs = [o for o in obs if gap(here, [o]) >= 0.15]      # anything already touching the parked car is not in its way (the game placed the car there)
    worst = 1e9
    x, z, s = start_xz[0], start_xz[1], 0.0
    while s <= run + 1e-9:
        hs = yaw + bias * min(1.0, s / ramp)         # the car turns onto the new heading over `ramp` metres, not at once
        worst = min(worst, gap(footprint(x, z, hs, width, length, front), obs))
        x += -math.sin(math.radians(hs)) * step
        z += -math.cos(math.radians(hs)) * step
        s += step
    return worst


def best_bias(obs, start_xz, yaw, biases=range(-12, 13), **kw):
    rows = [(swept_clearance(obs, start_xz, yaw, b, **kw), b) for b in biases]
    return max(rows, key=lambda r: (round(r[0], 2), -abs(r[1]))), rows      # largest gap; a tie goes to the smaller bias



# Car body for the sweep: (width, length, front) in metres. The .hdc files only list the generic example feelers (2.08 wide, 5.23 long,
# nose 2.64 m ahead of the reference point) for every car, commented out, so there is no per-car data to read there; a car's real body
# comes from its graphics mesh. This is wider and longer than any car in the game, so a bias that clears it clears all of them.
CAR_BOX = (2.08, 5.23, 2.64)
