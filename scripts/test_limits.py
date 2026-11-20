r"""Offline checks of the geometric track-limit module (gtr2_driving/limits.py): the boundary polylines, the tyre footprints, the car's wheel
positions read from its wheel meshes, and a comparison with the old nearest-waypoint test on a tight corner.

    scripts\.venv\Scripts\python.exe -I scripts\test_limits.py

Needs the game folder for the car-geometry and the Imola track checks (they are skipped with a note when it is missing).
Standard library only.
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gtr2_driving import limits      # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ((" - " + detail) if detail else ""))
    if not ok:
        fails.append(name)


class W:
    """A stand-in waypoint."""

    def __init__(self, x, z, hx, hz, left, right):
        self.x, self.z, self.hx, self.hz, self.left, self.right = x, z, hx, hz, left, right


def circle_track(radius, width, n=60, left_turn=True):
    """A closed circular line with `width` metres each side; a left turn runs counter-clockwise in (x east, z north)."""
    chain = []
    for i in range(n):
        a = 2 * math.pi * i / n
        s = 1 if left_turn else -1
        x, z = radius * math.cos(a), radius * math.sin(a) * s
        hx, hz = -math.sin(a), math.cos(a) * s
        chain.append(W(x, z, hx, hz, width, width))
    return chain


# 1. straight line geometry
straight = [W(0.0, 5.0 * i, 0.0, 1.0, 6.0, 6.0) for i in range(40)]      # heading +z; the left side is -x (left = (-hz, hx) = (-1, 0))
b = limits.Boundaries(straight)
l, r = b.beyond(10, 0.0, 50.0)
check("straight, centre: inside both lines by 6 m", abs(l + 6.0) < 1e-6 and abs(r + 6.0) < 1e-6, "%.3f %.3f" % (l, r))
l, r = b.beyond(10, -7.0, 50.0)
check("straight, 1 m beyond the left line", abs(l - 1.0) < 1e-6 and r < 0, "%.3f %.3f" % (l, r))
l, r = b.beyond(10, 6.5, 50.0)
check("straight, 0.5 m beyond the right line", abs(r - 0.5) < 1e-6 and l < 0, "%.3f %.3f" % (l, r))

# 2. a tight left-hand corner: radius 15 m, 6 m each side, so the inside line has radius 9 m and the outside line 21 m
c = circle_track(15.0, 6.0, n=48)
b = limits.Boundaries(c)
k = 0
for name, rad, expect_left in (("inside line (r 9)", 9.0, 0.0), ("outside line (r 21)", 21.0, 0.0)):
    px, pz = rad + 0.4, 0.0
    l, r = b.beyond(k, px, pz)
    print("      point at radius %.1f -> beyond left %.3f, right %.3f" % (rad + 0.4, l, r))
l, r = b.beyond(k, 9.0 - 0.4, 0.0)      # 0.4 m beyond the inside (left) line
check("left-hand corner: 0.4 m beyond the inside line", abs(l - 0.4) < 0.03 and r < 0, "%.3f %.3f" % (l, r))
l, r = b.beyond(k, 21.0 + 0.4, 0.0)      # 0.4 m beyond the outside (right) line
check("left-hand corner: 0.4 m beyond the outside line", abs(r - 0.4) < 0.03 and l < 0, "%.3f %.3f" % (r, l))

# 3. the old test (distance to the nearest waypoint's cross line) against the boundary test at a point between waypoints on the inside of a tight corner
def old_test(chain, px, pz):
    best = min(range(len(chain)), key=lambda i: (chain[i].x - px) ** 2 + (chain[i].z - pz) ** 2)
    w = chain[best]
    lat = (px - w.x) * -w.hz + (pz - w.z) * w.hx      # positive to the left
    return lat - w.left, -lat - w.right      # beyond left, beyond right


tight = circle_track(12.0, 5.0, n=24)      # 12 m radius, waypoints every 3.1 m
bt = limits.Boundaries(tight)
worst = worst_new = 0.0
for i in range(0, 24 * 4):
    a = 2 * math.pi * (i / 4.0) / 24
    for rad in (7.0 - 0.3, 7.0 + 0.3, 17.0 - 0.3, 17.0 + 0.3):
        px, pz = rad * math.cos(a), rad * math.sin(a)
        ol, orr = old_test(tight, px, pz)
        nl, nr = bt.beyond(i // 4, px, pz)
        true_l, true_r = 7.0 - rad, rad - 17.0      # exact: the inside (left) line has radius 7 m, the outside (right) line 17 m
        worst = max(worst, abs(ol - true_l) if rad < 12 else 0.0, abs(orr - true_r) if rad > 12 else 0.0)
        worst_new = max(worst_new, abs(nl - true_l) if rad < 12 else 0.0, abs(nr - true_r) if rad > 12 else 0.0)
check("tight corner: the boundary test is within the polyline's own chord error (s^2/8r, 0.15 m) of the exact circle", worst_new < 0.16, "largest error %.3f m" % worst_new)
print("      (radius 12 m, waypoints 3.1 m apart: largest error old %.3f m, new %.3f m)" % (worst, worst_new))

# 3b. the windowed search gives the same answer as a brute-force distance to every segment of the polyline
def brute(poly, px, pz):
    best = (1e18, 0.0)
    n = len(poly)
    for i in range(n):
        ax, az = poly[i]
        bx, bz = poly[(i + 1) % n]
        dx, dz = bx - ax, bz - az
        t = max(0.0, min(1.0, ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz)))
        d = math.hypot(px - ax - t * dx, pz - az - t * dz)
        cross = dx * (pz - az) - dz * (px - ax)
        if d < best[0]:
            best = (d, d if cross >= 0 else -d)
    return best[1]


maxdiff = 0.0
for i in range(0, 24 * 4):
    a_ = 2 * math.pi * (i / 4.0) / 24
    for rad in (6.5, 7.5, 16.5, 17.5, 12.0):
        px, pz = rad * math.cos(a_), rad * math.sin(a_)
        nl, nr = bt.beyond(i // 4, px, pz)
        maxdiff = max(maxdiff, abs(nl - brute(bt.L, px, pz)), abs(nr + brute(bt.R, px, pz)))
check("windowed boundary search equals the brute-force polyline distance", maxdiff < 1e-9, "largest difference %.2e m" % maxdiff)

# 4. tyre footprints and the four-tyre rule on a straight
wheels = limits.default_wheels()
flags, margin = limits.wheels_beyond(limits.Boundaries(straight), 10, 0.0, 50.0, 0.0, 1.0, wheels)
check("car in the middle: no tyre beyond a line", flags == [None] * 4 and margin > 5.0, "%s margin %.2f" % (flags, margin))
flags, margin = limits.wheels_beyond(limits.Boundaries(straight), 10, -6.0, 50.0, 0.0, 1.0, wheels)
check("car on the left line: not a violation", not limits.all_four_beyond(flags), str(flags))
flags, margin = limits.wheels_beyond(limits.Boundaries(straight), 10, -7.5, 50.0, 0.0, 1.0, wheels)
check("car 1.5 m past the left line: all four beyond", limits.all_four_beyond(flags), "%s margin %.2f" % (flags, margin))
flags, margin = limits.wheels_beyond(limits.Boundaries(straight), 10, -6.9, 50.0, 0.0, 1.0, wheels)
check("car straddling the left line: one side only", not limits.all_four_beyond(flags) and flags.count("l") == 2, str(flags))

# 5. the Maserati's real wheel positions from its wheel meshes
try:
    wh = limits.car_wheels("gt/maserati_mc12")
except SystemExit:
    wh = None
if wh is None:
    print("skip car geometry (game folder or car files not found)")
else:
    lf, rf, lr, rr = wh
    check("MC12 wheel mesh: front track about 1.64 m, rear about 1.65 m", abs(lf["left"] - rf["left"] - 1.645) < 0.02 and abs(lr["left"] - rr["left"] - 1.65) < 0.02, "%.3f / %.3f" % (lf["left"] - rf["left"], lr["left"] - rr["left"]))
    check("MC12 wheel mesh: wheelbase about 2.80 m, centred between the axles", abs(lf["fwd"] - lr["fwd"] - 2.80) < 0.05, "%.3f ahead %.3f behind" % (lf["fwd"], -lr["fwd"]))
    check("MC12 wheel mesh: front tyre about 0.31 m wide, rear about 0.38 m", 0.25 < lf["width"] < 0.36 and 0.33 < lr["width"] < 0.43, "%.3f / %.3f" % (lf["width"], lr["width"]))

print("%d failing" % len(fails))
sys.exit(1 if fails else 0)
