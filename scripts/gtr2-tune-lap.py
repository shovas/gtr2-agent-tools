"""Tune the analog driver for a faster lap by trial: change one driving parameter at a time, drive the out lap, keep it if it was clean and faster.

Purpose: an experiment in letting the automation push for lap time. Each trial is one `gtr2-lap-check.py LAYOUT --input analog --quick` run
(fresh game launch, out lap from the pits, back out through the menus, profile reverted), scored by the time of the first start/finish
crossing (the telemetry's lap-counter change) and by the usual cleanliness test (completed, under 0.5% of samples off the road, largest
offset under --max-offset). Coordinate search: try a parameter one step up; if better keep going that way; if not try one step down;
then the next parameter. The baseline is driven first. Nothing is applied to the repo's defaults: the best values are written to
gtr2_ui/runs/tune_<layout>.json and printed as a gtr2-drive-lap command line. About 3.7 minutes per trial; the PC must be left alone.
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-tune-lap.py LAYOUT [--car KEY] [--max-trials 12] [--margin 0.3] [--dry-run]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-tune-lap.py Imola4Imol --max-trials 12
Log:     gtr2_ui/runs/tune_log.jsonl (one line per trial: parameters, time, clean, accepted). Exit 0 when finished, 2 on a bad start.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RUNS = SCRIPTS / "gtr2_ui" / "runs"
RESULTS = RUNS / "lap_results.jsonl"
LOG = RUNS / "tune_log.jsonl"
PY = sys.executable

# name, base value, step, lo, hi. The first three throttle ceilings (gears 1 to 3) are scaled together by "launch".
PARAMS = [
    ("lat-accel", 7.5, 0.5, 5.0, 14.0),      # range tops raised after pass 1 reached 10.0 and 8.0 with clean laps
    ("decel", 6.0, 0.5, 4.0, 11.0),
    ("lookahead-per", 1.2, 0.2, 0.6, 2.0),
    ("analog-steer", 0.6, 0.1, 0.4, 0.9),
    ("launch", 1.0, 0.1, 0.7, 1.7),      # gear 1 ceiling reaches 1.0 at about 1.67
    ("shift-rpm", 6300.0, 300.0, 5000.0, 7200.0),
]
BASE_CEILING = [0.6, 0.7, 0.85, 1.0, 1.0, 1.0]


def drive_args(v):
    ceil = [min(1.0, c * v["launch"]) if i < 3 else c for i, c in enumerate(BASE_CEILING)]
    return ["--lat-accel", "%g" % v["lat-accel"], "--decel", "%g" % v["decel"], "--lookahead", "5.0", "%g" % v["lookahead-per"],
            "--analog-steer", "%g" % v["analog-steer"], "--analog-throttle"] + ["%.3f" % c for c in ceil] + ["--shift-rpm", "%g" % v["shift-rpm"]]


def trial(layout, car, v, max_offset, extra=()):
    """Run one out lap. Returns dict(time, clean, why) or None if no result was produced."""
    n_before = len(RESULTS.read_text().splitlines()) if RESULTS.exists() else 0
    cmd = [PY, "-I", str(SCRIPTS / "gtr2-lap-check.py"), layout, "--car", car, "--input", "analog", "--quick",
           "--drive-args", " ".join(drive_args(v) + list(extra))]
    t0 = time.time()
    subprocess.run(cmd, cwd=SCRIPTS.parent, capture_output=True, text=True, timeout=1500)
    rows = RESULTS.read_text().splitlines() if RESULTS.exists() else []
    if len(rows) <= n_before:
        return None
    row = json.loads(rows[-1])
    res = row.get("result") or {}
    changes = res.get("lap_changes") or []
    t = changes[0]["t"] if changes else None
    clean = bool(row.get("clean")) and t is not None and res.get("max_offset", 99) <= max_offset
    return {"time": t, "clean": clean, "why": row.get("why"), "wall": round(time.time() - t0), "profile": row.get("profile")}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("layout")
    ap.add_argument("--car", default="gt/lamborghini_murcielago")
    ap.add_argument("--max-trials", type=int, default=12, help="including the baseline")
    ap.add_argument("--margin", type=float, default=0.3, help="seconds a trial must beat the best by (run-to-run noise was about 0.1 to 0.2 s)")
    ap.add_argument("--max-offset", type=float, default=7.0, help="metres: a trial whose largest offset from the line exceeds this is not clean")
    ap.add_argument("--start-from", help="a tune_<layout>.json from an earlier pass: start (and drive the baseline) from its values")
    ap.add_argument("--params", help="comma-separated parameter names to tune, in this order (default: all, in the built-in order)")
    ap.add_argument("--extra", default="", help="extra options passed to every trial's gtr2-drive-lap.py, e.g. \"--zones\"")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the first command, run nothing")
    a = ap.parse_args()

    best_v = {n: base for n, base, *_ in PARAMS}
    if a.start_from:
        best_v.update(json.loads(Path(a.start_from).read_text())["values"])
    starts = dict(best_v)
    if a.dry_run:
        print("baseline:", " ".join(drive_args(best_v)))
        print("order:", ", ".join(n for n, *_ in PARAMS), "; at most %d trials of about 3.7 min" % a.max_trials)
        return 0
    RUNS.mkdir(exist_ok=True)

    def log(rec):
        rec["at"] = time.strftime("%H:%M:%S")
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)

    used, failures = 0, 0
    r = trial(a.layout, a.car, best_v, a.max_offset, a.extra.split())
    used += 1
    if r is None or not r["clean"]:
        log({"trial": 0, "name": "baseline", "values": best_v, "result": r, "accepted": False})
        print("the baseline did not complete cleanly; nothing to improve on (see lap_drive.log)")
        return 2
    best_t = r["time"]
    log({"trial": 0, "name": "baseline", "values": dict(best_v), "result": r, "accepted": True})
    plist = PARAMS if not a.params else [next(p for p in PARAMS if p[0] == n) for n in a.params.split(",")]
    for name, base, step, lo, hi in plist:
        for direction in (+1, -1):
            improved = True
            while improved and used < a.max_trials:
                improved = False
                val = round(best_v[name] + direction * step, 4)
                if not lo <= val <= hi:
                    break
                cand = dict(best_v, **{name: val})
                r = trial(a.layout, a.car, cand, a.max_offset, a.extra.split())
                used += 1
                if r is None:
                    failures += 1
                    log({"trial": used - 1, "name": name, "values": cand, "result": None, "accepted": False})
                    if failures >= 2:
                        print("two runs in a row produced no result; stopping")
                        return 2
                    break
                failures = 0
                ok = r["clean"] and r["time"] < best_t - a.margin
                log({"trial": used - 1, "name": name, "values": cand, "result": r, "accepted": ok, "best_before": best_t})
                if ok:
                    best_v, best_t, improved = cand, r["time"], True
            if best_v[name] != starts[name]:
                break          # moved in the first direction that helped; do not try the other
    out = RUNS / ("tune_%s.json" % a.layout.lower())
    out.write_text(json.dumps({"layout": a.layout, "car": a.car, "first_crossing_s": best_t, "values": best_v,
                               "drive_args": drive_args(best_v), "trials": used}, indent=1), encoding="utf-8")
    print("best %.1f s after %d trials; written to %s" % (best_t, used, out))
    print("gtr2-drive-lap.py ... --fast " + " ".join(drive_args(best_v)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
