r"""Time budget of a driven lap against the game's own AI lap, per stretch of track: where the seconds are.

Purpose: the lap-time gap to the target is spread over a dozen corners; this lists, for every 100 m of the lap, how much slower (or faster) the driven lap is than the recorded AI lap
(scripts/gtr2_ui/runs/ai_imola_mc12.csv, lap 2), with the speeds of both at the stretch (minimum, mean) and the share of the stretch spent braking, and groups the losing stretches into
corners. The AI uses simplified physics (docs/analog-driving.md): the gap is where to look, not a limit to reach. Needs a --sig-log session (signals_*.csv, with x, z, speed, brake).

Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2-corner-budget.py [signals_<stamp>.csv] [--lap N] [--ai scripts\gtr2_ui\runs\ai_imola_mc12.csv]
Example: scripts\.venv\Scripts\python.exe -I scripts\gtr2-corner-budget.py scripts\gtr2_ui\runs\signals_20261125_001122.csv --lap 6
"""
import argparse
import collections
import csv
import glob
import math
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "gtr2_ui" / "runs"


def ours(path):
    rows = [r for r in csv.reader(open(path)) if r and not r[0].startswith("#")]
    h = rows[0]
    laps = collections.defaultdict(list)
    for r in rows[1:]:
        d = dict(zip(h, map(float, r)))
        laps[int(d["lap"])].append(d)
    return laps


def ai_lap(path, lap=2):
    out = []
    for r in csv.DictReader(open(path)):
        if int(r["lap"]) == lap:
            out.append({"t": 0.0, "x": float(r["x"]), "z": float(r["z"]), "speed": float(r["speed"]), "brake": 0.0})
    # the AI file's own time column is not in seconds (3.6 s for a 108 s lap): integrate the distance over the speed instead
    t = 0.0
    for a, b in zip(out, out[1:]):
        t += math.hypot(b["x"] - a["x"], b["z"] - a["z"]) / max(0.5 * (a["speed"] + b["speed"]), 1.0)
        b["t"] = t
    return out


def profile(v, step=100.0):
    """per `step` metres of arc length from the first sample: elapsed time at the stretch boundaries, minimum and mean speed, braking share."""
    s, S = 0.0, [0.0]
    for p, q in zip(v, v[1:]):
        s += math.hypot(q["x"] - p["x"], q["z"] - p["z"])
        S.append(s)
    nseg = int(S[-1] // step)
    seg = []
    for k in range(nseg):
        idx = [i for i, d in enumerate(S) if k * step <= d < (k + 1) * step]
        if not idx:
            seg.append(None)
            continue
        i0, i1 = idx[0], min(idx[-1] + 1, len(v) - 1)
        seg.append({"t": v[i1]["t"] - v[i0]["t"], "vmin": min(v[i]["speed"] for i in idx), "vmean": sum(v[i]["speed"] for i in idx) / len(idx),
                    "brk": sum(1 for i in idx if v[i]["brake"] > 0.05) / len(idx)})
    return seg


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log", nargs="?")
    ap.add_argument("--lap", type=int)
    ap.add_argument("--ai", default=str(RUNS / "ai_imola_mc12.csv"))
    ap.add_argument("--step", type=float, default=100.0)
    a = ap.parse_args()
    path = a.log or sorted(glob.glob(str(RUNS / "signals_*.csv")))[-1]
    laps = ours(path)
    full = {n: v for n, v in laps.items() if len(v) > 900}
    if not full:
        raise SystemExit("no full lap in " + path)
    dur = {n: v[-1]["t"] - v[0]["t"] for n, v in full.items()}
    lap = a.lap if a.lap is not None else min(dur, key=dur.get)
    mine, ref = profile(full[lap], a.step), profile(ai_lap(a.ai), a.step)
    n = min(len(mine), len(ref))
    t_me = sum(s["t"] for s in mine[:n] if s)
    t_ai = sum(s["t"] for s in ref[:n] if s)
    print("%s lap %d: %.1f s over %d stretches of %.0f m; AI lap %.1f s; gap %.1f s" % (Path(path).name, lap, t_me, n, a.step, t_ai, t_me - t_ai))
    print("  from(m)  gap(s)  mine vmin/vmean  AI vmin/vmean  mine brake%")
    rows = []
    for k in range(n):
        if not mine[k] or not ref[k]:
            continue
        gap = mine[k]["t"] - ref[k]["t"]
        rows.append((k, gap))
        print("  %6d  %+6.2f   %5.1f/%5.1f     %5.1f/%5.1f      %3.0f" % (k * a.step, gap, mine[k]["vmin"], mine[k]["vmean"], ref[k]["vmin"], ref[k]["vmean"], 100 * mine[k]["brk"]))
    # group neighbouring stretches that lose time into corners
    groups, cur = [], []
    for k, g in rows:
        if g > 0.08:
            cur.append((k, g))
        elif cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    print("corners (runs of stretches losing more than 0.08 s): from m, to m, total loss s")
    for gr in sorted(groups, key=lambda g: -sum(x[1] for x in g)):
        print("  %5d to %5d  %.2f s" % (gr[0][0] * a.step, (gr[-1][0] + 1) * a.step, sum(x[1] for x in gr)))


if __name__ == "__main__":
    main()
