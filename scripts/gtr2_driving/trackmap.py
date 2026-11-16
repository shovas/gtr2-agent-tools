# uses only the standard library today (adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md).
# Changed: ROOT/DEFAULT resolve from scripts/gtr2_driving/ to this install.
"""The track's own geometry, from the AI waypoint file (GameData/Locations/<venue>/<layout>.AIW), in the same world
coordinates as the shared-memory telemetry (x east, z north; heading yaw as telemetry.Telemetry gives it).

Each waypoint has a centre position, a perpendicular, road width to the left and right, the lap distance, and a branch id
(0 the racing line, 1 the pit lane, 2.. the pit-stop slots). With the car's position this gives the lateral offset from the
centre, how far along the lap it is, the heading of the road ahead, and the curvature ahead (to choose a speed).

    _uitest/.venv/Scripts/python.exe _uitest/trackmap.py [AIW]      summary, and the corners found
"""
import math
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gtr2_ui"))
import diag  # noqa: E402
ROOT = diag.game_root()
DEFAULT = ROOT / "GameData" / "Locations" / "Donington" / "4Donington.AIW"
NUM = r"[-+0-9.eE]+"


class Waypoint:
    __slots__ = ("i", "x", "y", "z", "px", "pz", "left", "right", "dist", "branch", "ptrs", "hx", "hz")


def parse(path=DEFAULT):
    text = Path(path).read_bytes().decode("latin1")
    head = text.split("[Waypoint]", 1)
    lap_length = float(re.search(r"lap_length=(" + NUM + ")", head[1]).group(1))
    wps, cur = [], None
    for line in head[1].splitlines():
        line = line.split("//")[0].strip()
        if line.startswith("wp_pos="):
            cur = Waypoint()
            cur.i = len(wps)
            cur.x, cur.y, cur.z = map(float, re.findall(NUM, line.split("=", 1)[1])[:3])
            wps.append(cur)
        elif cur is None:
            continue
        elif line.startswith("wp_perp="):
            v = list(map(float, re.findall(NUM, line.split("=", 1)[1])))
            cur.px, cur.pz = v[0], v[2]
        elif line.startswith("wp_width="):
            v = list(map(float, re.findall(NUM, line.split("=", 1)[1])))
            cur.left, cur.right = v[0], v[1]
        elif line.startswith("wp_score="):
            cur.dist = float(re.findall(NUM, line.split("=", 1)[1])[1])
        elif line.startswith("wp_branchID="):
            cur.branch = int(float(re.findall(NUM, line.split("=", 1)[1])[0]))
        elif line.startswith("WP_PTRS="):
            cur.ptrs = tuple(int(float(v)) for v in re.findall(NUM, line.split("=", 1)[1]))
    return wps, lap_length


class Track:
    def __init__(self, path=DEFAULT):
        self.wps, self.lap_length = parse(path)
        # The file does not list a branch in driving order (some layouts store a stretch of the lap, or a detour, out of
        # sequence), so follow the waypoints' own next pointers (WP_PTRS = previous, next, link, ...). File order is only
        # the fallback when the pointers don't cover most of the branch.
        in_file_order = [[w for w in self.wps if w.branch == b] for b in (0, 1)]
        self.main = self._follow(in_file_order[0][:1], 0) or in_file_order[0]
        entries = [w for w in in_file_order[1] if not (0 <= w.ptrs[0] < len(self.wps) and self.wps[w.ptrs[0]].branch == 1)]
        pit = max((self._follow([w], 1) for w in entries), key=len, default=[])
        self.pit = pit if len(pit) >= 0.5 * len(in_file_order[1]) else in_file_order[1]
        if len(self.main) < 0.9 * len(in_file_order[0]):
            self.main = in_file_order[0]
        # the direction of travel at each waypoint: towards the next one on its own branch
        for chain in (self.main, self.pit):
            for k, w in enumerate(chain):
                n = chain[(k + 1) % len(chain)] if chain is self.main else chain[min(k + 1, len(chain) - 1)]
                dx, dz = n.x - w.x, n.z - w.z
                d = math.hypot(dx, dz) or 1.0
                w.hx, w.hz = dx / d, dz / d

    def _follow(self, start, branch):
        """Waypoints of one branch in driving order, from start[0] along the next pointers until the branch ends or loops."""
        out, seen = [], set()
        i = start[0].i if start else -1
        while 0 <= i < len(self.wps) and i not in seen and self.wps[i].branch == branch:
            seen.add(i)
            out.append(self.wps[i])
            i = self.wps[i].ptrs[1]
        return out

    @staticmethod
    def heading_vector(yaw_deg):
        """World direction the car points for a telemetry yaw: yaw 0 faces -z, yaw -90 faces +x."""
        y = math.radians(yaw_deg)
        return -math.sin(y), -math.cos(y)

    @staticmethod
    def yaw_of(dx, dz):
        return math.degrees(math.atan2(-dx, -dz))

    def nearest(self, chain, x, z, near=None, window=40):
        """Index into `chain` of the waypoint nearest (x, z); if `near` is given, only within `window` waypoints of it."""
        n = len(chain)
        idx = range(n) if near is None else [(near + k) % n for k in range(-5, window)]
        best, bi = 1e18, 0
        for k in idx:
            w = chain[k]
            d = (w.x - x) ** 2 + (w.z - z) ** 2
            if d < best:
                best, bi = d, k
        return bi

    def lateral(self, w, x, z):
        """Signed distance from the centre line (positive to the road's right, in the direction of travel)."""
        return (x - w.x) * (-w.hz) + (z - w.z) * w.hx  # right of the heading (hx, hz) in x-z with z north

    def ahead(self, chain, k, metres):
        """The waypoint `metres` further along from index k (stops at the end of an open chain)."""
        n, total = len(chain), 0.0
        j = k
        while total < metres:
            nj = (j + 1) % n if chain is self.main else min(j + 1, n - 1)
            if nj == j:
                break
            total += math.hypot(chain[nj].x - chain[j].x, chain[nj].z - chain[j].z)
            j = nj
        return chain[j]

    def ahead_point(self, chain, k, metres, x, z):
        """The point exactly `metres` along the chain from the car's own position (x, z), interpolated between waypoints.

        `ahead()` returns whole waypoints, so the aim point jumped by one waypoint spacing each time the nearest waypoint
        advanced (and the wheel with it); this one moves continuously with the car. Returns an object with the fields the
        driver reads (x, z, hx, hz, left, right, dist)."""
        n = len(chain)
        a = chain[k]
        s0 = (x - a.x) * a.hx + (z - a.z) * a.hz      # the car's distance past waypoint k along the line's heading (negative: before it)
        want = max(0.0, metres + s0)
        j, total = k, 0.0
        while True:
            nj = (j + 1) % n if chain is self.main else min(j + 1, n - 1)
            if nj == j:
                return chain[j]
            seg = math.hypot(chain[nj].x - chain[j].x, chain[nj].z - chain[j].z)
            if total + seg >= want:
                f = (want - total) / seg if seg > 1e-6 else 0.0
                p, q = chain[j], chain[nj]
                hx, hz = p.hx + f * (q.hx - p.hx), p.hz + f * (q.hz - p.hz)
                hn = math.hypot(hx, hz) or 1.0
                d = p.dist + f * (q.dist - p.dist) if q.dist >= p.dist else p.dist
                return SimpleNamespace(x=p.x + f * (q.x - p.x), z=p.z + f * (q.z - p.z), hx=hx / hn, hz=hz / hn,
                                       left=p.left + f * (q.left - p.left), right=p.right + f * (q.right - p.right), dist=d)
            total += seg
            j = nj

    def curvature_ahead(self, chain, k, metres=45.0):
        """Largest |turn rate| (rad per metre) over the next `metres` of the chain, and the distance to where it peaks."""
        n = len(chain)
        best, at, total, j = 0.0, 0.0, 0.0, k
        while total < metres:
            nj = (j + 1) % n if chain is self.main else min(j + 1, n - 1)
            if nj == j:
                break
            a, b = chain[j], chain[nj]
            seg = math.hypot(b.x - a.x, b.z - a.z) or 1.0
            ang = math.atan2(a.hx * b.hz - a.hz * b.hx, a.hx * b.hx + a.hz * b.hz)
            c = abs(ang) / seg
            if c > best:
                best, at = c, total
            total += seg
            j = nj
        return best, at

    def speed_limit(self, chain, k, metres, lat_accel, decel, span=12.0, tight_radius=0.0, tight_speed=99.0):
        """The speed to be doing now so as to meet every bend in the next `metres` at its own cornering speed:
        min over points ahead of sqrt(v_corner^2 + 2 * decel * distance), where v_corner = sqrt(lat_accel / curvature) and
        the curvature is the turn over the next `span` metres. Also returns the distance of the limiting point."""
        n = len(chain)
        pts, total, j = [], 0.0, k
        while total < metres + span:
            pts.append((total, chain[j]))
            nj = (j + 1) % n if chain is self.main else min(j + 1, n - 1)
            if nj == j:
                break
            total += math.hypot(chain[nj].x - chain[j].x, chain[nj].z - chain[j].z)
            j = nj
        best, at = 99.0, 0.0
        m = 0
        for i, (d, a) in enumerate(pts):
            if d > metres:
                break
            while m < len(pts) - 1 and pts[m][0] < d + span:
                m += 1
            b = pts[m][1]
            ds = max(pts[m][0] - d, 1.0)
            ang = abs(math.atan2(a.hx * b.hz - a.hz * b.hx, a.hx * b.hx + a.hz * b.hz))
            c = ang / ds
            la = lat_accel(a) if callable(lat_accel) else lat_accel      # a per-waypoint limit: slow zones
            vc = math.sqrt(la / c) if c > 1e-4 else 99.0
            if tight_radius > 0 and c > 1e-4 and 1.0 / c < tight_radius:
                vc = min(vc, tight_speed)       # a keyboard-steered car can't turn this tightly at speed: crawl round it
            v = math.sqrt(vc * vc + 2.0 * decel * d)
            if v < best:
                best, at = v, d
        return best, at


if __name__ == "__main__":
    t = Track(sys.argv[1] if len(sys.argv) > 1 else DEFAULT)
    print("waypoints", len(t.wps), "main", len(t.main), "pit", len(t.pit), "lap length", t.lap_length)
    print("branches", sorted({w.branch for w in t.wps}))
    p = t.pit
    if p:
        print("pit lane first", (round(p[0].x), round(p[0].z)), "last", (round(p[-1].x), round(p[-1].z)), "waypoints", len(p))
    m = t.main
    print("main first", (round(m[0].x), round(m[0].z), round(m[0].dist)), "last", (round(m[-1].x), round(m[-1].z), round(m[-1].dist)))
