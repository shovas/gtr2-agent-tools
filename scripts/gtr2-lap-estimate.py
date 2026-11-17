r"""Offline lap-time estimate of a planner setting on a track layout (no game needed): the speed profile the driver's own planner would
hold on the (optionally smoothed) racing line, with power-limited acceleration, constant or speed-dependent (downforce) grip and
braking, and the time to drive it. Use it to compare settings in seconds instead of 6 minute laps; calibrate against real laps first
(the estimate is a floor: the car loses time tracking the line).

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-estimate.py Imola/4Imol --lat 11 --decel 13 --smooth 25 --pin 45
    scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-estimate.py Imola/4Imol --lat 11 --decel 13 --down 0.004 --brake-down 0.003
Standard library only; reads the game folder.
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import trackmap  # noqa: E402


def profile(c, lat, dec, acc_power, mass, drag, down, bdown, span=12.0, vmax=150.0, acc_cap=9.0):
    n = len(c)
    ds = [math.hypot(c[(i + 1) % n].x - c[i].x, c[(i + 1) % n].z - c[i].z) for i in range(n)]
    v = []
    for i in range(n):
        tot, j = 0.0, i
        while tot < span:
            tot += ds[j % n]
            j += 1
        a, b = c[i], c[j % n]
        ang = abs(math.atan2(a.hx * b.hz - a.hz * b.hx, a.hx * b.hx + a.hz * b.hz))
        cur = ang / max(tot, 1.0)
        if cur < 1e-4 or cur <= down:
            v.append(vmax)
        else:
            v.append(min(vmax, math.sqrt(lat / (cur - down))))       # grip lat + down * v^2 against v^2 * curvature
    for _ in range(2):
        for i in range(2 * n - 1, -1, -1):
            a, b = i % n, (i + 1) % n
            # braking with grip dec + bdown * v^2: v_a^2 = (v_b^2 + dec/bdown) * exp(2 bdown ds) - dec/bdown
            if bdown > 1e-9:
                k = dec / bdown
                v[a] = min(v[a], math.sqrt((v[b] ** 2 + k) * math.exp(2 * bdown * ds[a]) - k))
            else:
                v[a] = min(v[a], math.sqrt(v[b] ** 2 + 2 * dec * ds[a]))
        for i in range(2 * n):
            a, b = i % n, (i + 1) % n
            acc = min(acc_cap, acc_power / (mass * max(v[a], 5.0)) - 0.5 * 1.2 * drag * v[a] ** 2 / mass)
            v[b] = min(v[b], math.sqrt(v[a] ** 2 + 2 * max(acc, 0.3) * ds[a]))
    t = sum(ds[i] / max(0.5 * (v[i] + v[(i + 1) % n]), 1.0) for i in range(n))
    return t, sum(ds), v, ds


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout", help="Venue/Layout stem, e.g. Imola/4Imol")
    ap.add_argument("--lat", type=float, default=11.0)
    ap.add_argument("--decel", type=float, default=13.0)
    ap.add_argument("--down", type=float, default=0.0, help="extra cornering grip per v^2 (m/s^2 per (m/s)^2), downforce")
    ap.add_argument("--brake-down", type=float, default=0.0, help="extra braking grip per v^2")
    ap.add_argument("--power", type=float, default=330000.0, help="wheel power in W")
    ap.add_argument("--mass", type=float, default=1300.0)
    ap.add_argument("--drag", type=float, default=0.75, help="CdA in m^2")
    ap.add_argument("--smooth", type=int, default=0)
    ap.add_argument("--margin", type=float, default=1.8)
    ap.add_argument("--pin", type=float, default=0.0)
    a = ap.parse_args()
    venue, stem = a.layout.split("/")
    t = trackmap.Track(str(trackmap.ROOT / "GameData" / "Locations" / venue / (stem + ".AIW")))
    if a.smooth:
        t.smooth_line(t.main, a.smooth, a.margin, pin_radius=a.pin)
    sec, length, v, ds = profile(t.main, a.lat, a.decel, a.power, a.mass, a.drag, a.down, a.brake_down)
    print("%s: %.1f s over %.0f m, mean %.1f m/s (%.0f km/h), top %.1f m/s, slowest %.1f m/s" % (a.layout, sec, length, length / sec, length / sec * 3.6, max(v), min(v)))


if __name__ == "__main__":
    main()
