r"""Empirical performance envelope of the car from --sig-log files: how much lateral, braking and driving acceleration the car really delivers at each speed.

For every logged sample (10 per second) the longitudinal acceleration is the change of speed, the lateral acceleration is speed x yaw rate (the sideslip is small
in all but the spins, which are left out with --max-slip). Per 10 m/s speed bin it prints the 90th and 98th percentile of: pure cornering (|longitudinal| under 1.5),
pure braking (|lateral| under 2), pure acceleration at full throttle, and the combined use as a share of the ellipse (a_long / a_brake_max)^2 + (a_lat / a_lat_max)^2
in the samples where both are over 3 m/s^2. The numbers say how close the driver gets to what the car can do (the friction-ellipse view) and how conservative the
planner's grip numbers (--live-lat, --live-brake) are.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-vehicle-envelope.py [signals_*.csv ...] [--laps 2 99] [--max-slip 15]

With no file: all signals_*.csv of the last 24 hours with a lat_err column (the current no-aids driver). Standard library only.
"""
import argparse
import glob
import math
import os
import time
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "gtr2_ui" / "runs"


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--laps", type=int, nargs=2, default=[2, 99], metavar=("FIRST", "LAST"))
    ap.add_argument("--max-slip", type=float, default=15.0, help="leave out samples with a sideslip beyond this (degrees)")
    a = ap.parse_args()
    files = a.files or [f for f in sorted(glob.glob(str(RUNS / "signals_*.csv"))) if time.time() - os.path.getmtime(f) < 86400]
    rows = []
    for f in files:
        lines = Path(f).read_text(encoding="utf-8").splitlines()
        if len(lines) < 3:
            continue
        head = lines[1].split(",")
        if "lat_err" not in head:
            continue
        r = [dict(zip(head, map(float, l.split(",")))) for l in lines[2:] if l.strip()]
        rows.extend((p, q) for p, q in zip(r, r[1:]) if a.laps[0] <= p["lap"] <= a.laps[1])
    cor, brk, acc, both = {}, {}, {}, []
    for p, q in rows:
        dt = q["t"] - p["t"]
        if not 0.05 < dt < 0.2 or p["speed"] < 8.0 or abs(p["sideslip"]) > a.max_slip:
            continue
        al = (q["speed"] - p["speed"]) / dt
        at = abs(math.radians(p["yawrate"]) * p["speed"])
        b = int(p["speed"] // 10 * 10)
        if abs(al) < 1.5:
            cor.setdefault(b, []).append(at)
        if p["brake"] > 0.5 and at < 2.0:
            brk.setdefault(b, []).append(-al)
        if p["duty"] > 0.95 and p["brake"] == 0.0 and at < 2.0:
            acc.setdefault(b, []).append(al)
        both.append((b, al, at))
    print("%d samples from %d file(s)" % (len(both), len(files)))
    print("speed bin   cornering p90/p98 (n) | braking p90/p98 (n) | full throttle p90 (n)   [m/s^2]")
    lat_max, brk_max = {}, {}
    for b in sorted(set(cor) | set(brk) | set(acc)):
        c, k, d = cor.get(b, []), brk.get(b, []), acc.get(b, [])
        lat_max[b], brk_max[b] = pct(c, 0.98), pct(k, 0.98)
        print("%3d-%3d     %5.1f / %5.1f (%4d)    | %5.1f / %5.1f (%4d)  | %5.1f (%4d)" % (b, b + 10, pct(c, 0.9), pct(c, 0.98), len(c), pct(k, 0.9), pct(k, 0.98), len(k), pct(d, 0.9), len(d)))
    use = []
    for b, al, at in both:
        lm, bm = lat_max.get(b, float("nan")), brk_max.get(b, float("nan"))
        if al < -3.0 and at > 3.0 and lm == lm and bm == bm and lm > 0 and bm > 0:
            use.append((al / bm) ** 2 + (at / lm) ** 2)
    if use:
        print("combined braking and cornering (a_long < -3 and a_lat > 3): %d samples, ellipse use p50 %.2f, p90 %.2f (1.0 = on the ellipse of the car's own p98 maxima; over 1 = better than either pure maximum implies)" % (len(use), pct(use, 0.5), pct(use, 0.9)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
