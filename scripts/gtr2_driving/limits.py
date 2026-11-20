r"""Track limits by geometry: are all four tyres wholly beyond the track's boundary line?

Two parts, both offline-testable (scripts/test_limits.py):

* `car_wheels(car_key)`: where the four tyres really are, read from the car's own wheel meshes (`*WHEELS.GTR`, the `WHEEL_xx_A.GMT` of
  each corner, car-local coordinates: x to the left, z backwards, origin between the axles). Gives each tyre's forward and left offset
  and its width. If the files cannot be read, the caller gets None and falls back to fixed numbers (never silently: it says so).
* `Boundaries(chain)`: the left and right boundary lines as polylines (waypoint position +- road width along the waypoint's own
  perpendicular), built from the waypoints as the file gives them, BEFORE any line smoothing or racing-line change moves the waypoints.
  `side(k, x, z)` is the signed distance from a point to the nearest boundary SEGMENT (point to segment, not point to the nearest
  waypoint's cross line), positive beyond the line. In a corner the nearest waypoint's cross line is a poor stand-in for the boundary:
  the cross lines fan out on the outside and bunch up on the inside, and waypoints are 5 to 6 m apart.

Conventions: heading (hx, hz), the car's physical left is (-hz, hx), waypoint `left`/`right` are the widths on each side.
Standard library only (the car geometry reads game files through mas.py and gmt.py).
"""
import math
import re
from pathlib import Path

try:
    from . import cargears, gmt, mas
except ImportError:      # run as a script from scripts/gtr2_driving
    import cargears, gmt, mas

CORNERS = ("LF", "RF", "LR", "RR")      # the telemetry's wheel order: front left, front right, rear left, rear right


def car_wheels(car_key):
    """-> list of four dicts {"fwd": m ahead of the car's origin, "left": m to the left, "width": tyre width m} in telemetry order, or None."""
    try:
        hdc = cargears.find_hdc(car_key)
        archive = next(iter(sorted(Path(hdc).parent.glob("*WHEELS.GTR"))), None)
        if archive is None:
            return None
        m = mas.Mas(archive)
        out = []
        for c in CORNERS:
            name = next((n for n in m.names() if re.search(r"WHEEL_%s_A\.GMT$" % c, n, re.I)), None)
            if name is None:
                return None
            verts = [v for me in gmt.parse(m.read(name)) for v in me["vertices"]]
            xs, zs = [v[0] for v in verts], [v[2] for v in verts]
            out.append({"fwd": -(min(zs) + max(zs)) / 2.0, "left": (min(xs) + max(xs)) / 2.0, "width": max(xs) - min(xs)})
        return out
    except Exception:
        return None


def default_wheels(wheelbase_half=1.35, track_half=0.825, width=0.30):
    """The fixed fallback: the numbers used before the car files were read."""
    return [{"fwd": wheelbase_half, "left": track_half, "width": width}, {"fwd": wheelbase_half, "left": -track_half, "width": width},
            {"fwd": -wheelbase_half, "left": track_half, "width": width}, {"fwd": -wheelbase_half, "left": -track_half, "width": width}]


class Boundaries:
    """The two boundary polylines of a closed lap (chain = track.main, taken before the waypoints are moved)."""

    def __init__(self, chain, trim=0.0):
        n = len(chain)
        self.n = n
        # boundary points: centre +- width along the perpendicular (left = (-hz, hx)); `trim` pulls both lines inwards
        self.L = [(w.x - w.hz * (w.left - trim), w.z + w.hx * (w.left - trim)) for w in chain]
        self.R = [(w.x + w.hz * (w.right - trim), w.z - w.hx * (w.right - trim)) for w in chain]

    @staticmethod
    def _signed(poly, i0, i1, x, z, n):
        """Signed distance from (x, z) to the polyline segments i0..i1 (indices modulo n): positive on the LEFT of the travel direction."""
        best_d, best_s = 1e18, 0.0
        for i in range(i0, i1 + 1):
            ax, az = poly[i % n]
            bx, bz = poly[(i + 1) % n]
            dx, dz = bx - ax, bz - az
            ll = dx * dx + dz * dz
            if ll < 1e-12:
                continue
            t = max(0.0, min(1.0, ((x - ax) * dx + (z - az) * dz) / ll))
            px, pz = ax + t * dx, az + t * dz
            d = math.hypot(x - px, z - pz)
            cross = dx * (z - az) - dz * (x - ax)      # >0: the point is to the left of the directed segment (x east, z north)
            if d < best_d - 1e-9 or (abs(d - best_d) <= 1e-9 and abs(cross) > abs(best_s)):
                best_d, best_s = d, (d if cross >= 0 else -d)
        return best_s

    def beyond(self, k, x, z, span=6):
        """-> (left, right): how far (x, z) is beyond the left and the right boundary line, metres, negative while inside."""
        s_left = self._signed(self.L, k - span, k + span, x, z, self.n)      # the left line: left of its direction of travel = outside
        s_right = -self._signed(self.R, k - span, k + span, x, z, self.n)      # the right line: right of its direction of travel = outside
        return s_left, s_right


def tyre_corners(cx, cz, fx, fz, width, patch=0.2):
    """The four corners of a tyre's footprint: centre (cx, cz), forward unit vector (fx, fz), width across and `patch` along."""
    lx, lz = -fz, fx
    return [(cx + a * fx + b * lx, cz + a * fz + b * lz) for a in (patch / 2, -patch / 2) for b in (width / 2, -width / 2)]


def wheels_beyond(bounds, k, x, z, fx, fz, wheels, patch=0.2):
    """For each of the four tyres: (beyond_left, beyond_right) = whether the whole footprint is beyond that line, plus the least margin.

    -> (flags, margin): flags[i] is "l", "r" or None; margin is the smallest signed distance of any footprint corner to a line
    (negative: beyond), over all tyres, for diagnostics."""
    lx, lz = -fz, fx
    flags, margin = [], 99.0
    for wh in wheels:
        cx, cz = x + wh["fwd"] * fx + wh["left"] * lx, z + wh["fwd"] * fz + wh["left"] * lz
        sl, sr = [], []
        for px, pz in tyre_corners(cx, cz, fx, fz, wh["width"], patch):
            a, b = bounds.beyond(k, px, pz)
            sl.append(a)
            sr.append(b)
        margin = min(margin, -max(max(sl), max(sr)))      # distance of the footprint's most outward corner inside its nearest line (negative: beyond)
        flags.append("l" if min(sl) > 0 else ("r" if min(sr) > 0 else None))
    return flags, margin


def all_four_beyond(flags):
    """A track-limit violation: all four tyres wholly beyond the same line."""
    return flags.count("l") == 4 or flags.count("r") == 4
