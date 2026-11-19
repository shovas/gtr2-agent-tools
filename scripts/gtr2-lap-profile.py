r"""Where does the lap time go? Reads a --sig-log CSV (scripts/gtr2_ui/runs/signals_*.csv) and, for one timed lap, prints the speed along the lap in
bins of metres (mean and lowest speed, the planned speed when logged) and the time spent per speed class, so the slow sections stand out.
With --target SECONDS it also shows how much time each bin would have to lose to reach that lap time if every bin were scaled alike.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-profile.py [signals.csv] [--lap N] [--bin 100] [--target 105.8]

Default file: the newest signals_*.csv; default lap: the fastest full lap in it (laps are the 'lap' column; the first and last are partial and skipped).
Standard library only.
"""
import argparse
import glob
import math
import sys
from pathlib import Path

RUNS = Path(__file__).resolve().parent / "gtr2_ui" / "runs"


def load(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    head = [h for h in lines[1].split(",")]
    rows = [dict(zip(head, map(float, l.split(",")))) for l in lines[2:] if l.strip()]
    return lines[0], rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--lap", type=int)
    ap.add_argument("--bin", type=float, default=100.0)
    ap.add_argument("--target", type=float)
    a = ap.parse_args()
    path = a.file or sorted(glob.glob(str(RUNS / "signals_*.csv")))[-1]
    head, rows = load(path)
    laps = {}
    for r in rows:
        laps.setdefault(int(r["lap"]), []).append(r)
    full = {n: v for n, v in laps.items() if len(v) > 200}
    times = {n: v[-1]["t"] - v[0]["t"] for n, v in full.items() if n not in (min(full), max(full))}
    if not times:
        print("no full laps in", path)
        return 1
    lap = a.lap if a.lap is not None else min(times, key=times.get)
    v = full.get(lap) or laps[lap]
    d, dist = 0.0, [0.0]
    for p, q in zip(v, v[1:]):
        d += math.hypot(q["x"] - p["x"], q["z"] - p["z"])
        dist.append(d)
    total = dist[-1]
    t_lap = v[-1]["t"] - v[0]["t"]
    print("%s: lap %d, %.1f s, %.0f m, mean %.1f m/s (%d samples)" % (Path(path).name, lap, t_lap, total, total / t_lap, len(v)))
    bins = {}
    for r, s in zip(v, dist):
        b = bins.setdefault(int(s // a.bin), {"v": [], "p": [], "t": 0.0})
        b["v"].append(r["speed"])
        if r.get("plan_speed") is not None and r["plan_speed"] < 140:
            b["p"].append(r["plan_speed"])
    for p_, q_, s in zip(v, v[1:], dist[1:]):
        bins[int(s // a.bin)]["t"] += q_["t"] - p_["t"]
    print("%6s %6s %6s %6s %6s" % ("from m", "mean", "min", "plan", "time s"))
    classes = {"under 30 m/s": 0.0, "30 to 45": 0.0, "45 to 60": 0.0, "over 60": 0.0}
    for k in sorted(bins):
        b = bins[k]
        mean = sum(b["v"]) / len(b["v"])
        print("%6d %6.1f %6.1f %6s %6.2f" % (k * a.bin, mean, min(b["v"]), ("%.1f" % (sum(b["p"]) / len(b["p"]))) if b["p"] else "-", b["t"]))
        classes["under 30 m/s" if mean < 30 else "30 to 45" if mean < 45 else "45 to 60" if mean < 60 else "over 60"] += b["t"]
    print("time by mean bin speed:", ", ".join("%s %.1f s" % kv for kv in classes.items()))
    if a.target:
        print("to reach %.1f s every bin must be %.1f%% faster (mean %.1f m/s)" % (a.target, 100.0 * (t_lap / a.target - 1.0), total / a.target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
