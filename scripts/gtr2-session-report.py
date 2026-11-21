r"""One-page report of a --sig-log session (scripts/gtr2_ui/runs/signals_*.csv): continuous metrics that separate two settings in fewer laps than clean/unclean counts.

For the fastest full lap (or --lap N) it prints: lap time, the ideal lap on the logged plan with the car's own acceleration and the loss against it (time lost per 100 m of lap
distance), the share of the lap spent braking and how far over the plan the car is while braking, the stretches where a tyre footprint is within 0.4 m of (or beyond) the
boundary line (needs the layout and car named in the log header), the corner minima with their gear, and, over the whole log, the track-limit events by distance.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-session-report.py [signals.csv] [--lap N] [--margin 0.4]

Default file: the newest signals_*.csv. Standard library only (reads the game folder through gtr2_driving/limits.py and trackmap.py).
"""
import argparse
import ast
import bisect
import collections
import glob
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
RUNS = HERE / "gtr2_ui" / "runs"
ACC = ((30, 8.0), (40, 7.3), (50, 6.0), (60, 4.0), (1e9, 3.6))      # measured p90 full-throttle acceleration by speed, m/s^2 (Maserati MC12, docs/analog-driving.md)


def load(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    head = lines[1].split(",")
    return lines[0], [dict(zip(head, map(float, l.split(",")))) for l in lines[2:] if l.strip()]


def lap_distance(v):
    d, out = 0.0, [0.0]
    for p, q in zip(v, v[1:]):
        d += math.hypot(q["x"] - p["x"], q["z"] - p["z"])
        out.append(d)
    return out


def acc(v):
    return next(a for lim, a in ACC if v < lim)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--lap", type=int)
    ap.add_argument("--margin", type=float, default=0.4)
    a = ap.parse_args()
    path = a.file or sorted(glob.glob(str(RUNS / "signals_*.csv")))[-1]
    header, rows = load(path)
    laps = collections.defaultdict(list)
    for r in rows:
        laps[int(r["lap"])].append(r)
    full = [n for n in sorted(laps) if len(laps[n]) > 900 and n not in (min(laps), max(laps))]
    if not full:
        print("no full lap in", path)
        return 1
    dur = {n: laps[n][-1]["t"] - laps[n][0]["t"] for n in full}
    lap = a.lap if a.lap is not None else min(full, key=dur.get)
    v = laps[lap]
    S = lap_distance(v)
    T = v[-1]["t"] - v[0]["t"]
    print("%s: lap %d of %s, %.1f s (laps: %s)" % (Path(path).name, lap, sorted(laps), T, ", ".join("%d %.1f" % (n, dur[n]) for n in full)))
    # ideal lap on the logged plan with the car's own acceleration
    n_ = int(S[-1] // 5)
    at = lambda s, key: next(r[key] for r, d in zip(v, S) if d >= s) if s <= S[-1] else v[-1][key]
    act = [at(5.0 * i, "speed") for i in range(n_)]
    plan = [min(at(5.0 * i, "plan_speed"), 75.0) for i in range(n_)]
    vi = [min(plan[0], act[0])] * n_
    for _ in range(3):
        for i in range(1, n_):
            vi[i] = min(plan[i], math.sqrt(vi[i - 1] ** 2 + 2 * acc(vi[i - 1]) * 5.0))
        vi[0] = min(plan[0], math.sqrt(vi[-1] ** 2 + 2 * acc(vi[-1]) * 5.0))
    t_act = sum(5.0 / max(s, 3) for s in act)
    t_id = sum(5.0 / max(s, 3) for s in vi)
    print("ideal lap on the plan %.1f s, driven %.1f s: loss %.1f s" % (t_id, t_act, t_act - t_id))
    loss = collections.defaultdict(float)
    for i in range(n_):
        loss[int(5 * i // 100)] += 5.0 / max(act[i], 3) - 5.0 / max(vi[i], 3)
    print("  largest loss per 100 m: " + ", ".join("%d m %.2f s" % (k * 100, x) for k, x in sorted(loss.items(), key=lambda kv: -kv[1])[:6]))
    # braking
    if "brake" in v[0]:
        br = [r for r in v if r["brake"] > 0.05]
        over = [r["speed"] - min(r["plan_speed"], 150) for r in br]
        print("braking %.0f%% of the lap, mean pedal %.2f, %+.1f m/s over the plan while braking, %.0f%% of braking samples more than 3 m/s over" % (
            100.0 * len(br) / len(v), sum(r["brake"] for r in br) / max(1, len(br)), sum(over) / max(1, len(over)), 100.0 * sum(1 for o in over if o > 3) / max(1, len(over))))
    # corner minima
    minima = []
    for i, r in enumerate(v):
        seg = v[max(0, i - 40):i + 40]
        if r["speed"] == min(s["speed"] for s in seg) and r["speed"] < 24 and (not minima or S[i] - minima[-1][0] > 80):
            minima.append((S[i], r["speed"], int(r.get("gear", 0))))
    print("corner minima: " + ", ".join("%d m %.1f m/s gear %d" % m for m in minima))
    # boundary stretches (needs the layout and the car from the header)
    m = re.search(r"# layout (\S+) car (\S+);", header)
    if m and Path(m.group(1)).exists():
        from gtr2_driving import limits, trackmap
        tr = trackmap.Track(m.group(1))
        bounds = limits.Boundaries(tr.main)
        wheels = limits.car_wheels(m.group(2)) or limits.default_wheels()
        k, run, runs = None, None, []
        for i in range(len(v) - 2):
            r, q = v[i], v[i + 2]
            dx, dz = q["x"] - r["x"], q["z"] - r["z"]
            nrm = math.hypot(dx, dz)
            if nrm < 0.5:
                continue
            k = tr.nearest(tr.main, r["x"], r["z"]) if k is None else tr.nearest(tr.main, r["x"], r["z"], near=k, window=40)
            _, margin = limits.wheels_beyond(bounds, k, r["x"], r["z"], dx / nrm, dz / nrm, wheels)
            if margin < a.margin and r["speed"] > 25:
                run = [S[i], S[i], margin, r["speed"]] if run is None else [run[0], S[i], min(run[2], margin), run[3]]
            else:
                if run and run[1] - run[0] >= 25:
                    runs.append(run)
                run = None
        print("stretches with a tyre within %.1f m of the boundary line or beyond it (25 m or longer, over 25 m/s): %s" % (a.margin, "; ".join("%d to %d m, least margin %.2f m, %d m/s" % tuple(x) for x in runs) or "none"))
    # track-limit events over the whole log
    ev = re.search(r"track limits (\[.*?\]) impacts", header)
    if ev:
        events = [e for e in ast.literal_eval(ev.group(1)) if e[1] >= 0.2]
        dist = []
        for lp, vv in laps.items():
            for r, d in zip(vv, lap_distance(vv)):
                dist.append((r["t"], lp, d))
        dist.sort()
        ts = [d[0] for d in dist]
        by = collections.Counter()
        secs = collections.Counter()
        for t0, sec in events:
            i = min(bisect.bisect_left(ts, t0), len(ts) - 1)
            if dist[i][1] >= 1:
                by[int(dist[i][2] // 100) * 100] += 1
                secs[int(dist[i][2] // 100) * 100] += sec
        print("track-limit events by lap distance: " + (", ".join("%d m: %d (%.1f s)" % (k, c, secs[k]) for k, c in sorted(by.items())) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
