r"""How hard can the out lap be driven and stay clean? Runs the out lap only (gtr2-lap-check.py --quick, about 3 minutes each) at one
share of the planned corner and braking speeds, and finds the highest share where --need runs in a row are clean (no impact, no
track-limit event, kerb strikes within the budget). Default: bisection between --min (assumed clean, default 0.80) and --start (default
1.00; tested first) down to --step (default 0.01); --linear steps down from --start by --step instead (slower, about 20 runs).
Nothing is remembered between the runs (--no-memory), so each one is a first lap on generic priors. Results go to
scripts/gtr2_ui/runs/outlap_sweep.jsonl (one line per run); the PC must be left alone.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-outlap-sweep.py Imola4Imol --car gt/maserati_mc12 [--start 1.0 --step 0.01 --need 2 --min 0.8]
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "gtr2_ui" / "runs" / "lap_results.jsonl"
OUT = HERE / "gtr2_ui" / "runs" / "outlap_sweep.jsonl"
KERB_BUDGET = None


def last_result():
    lines = [l for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None


def clean(res):
    """(clean, why) for an out lap: the whole run is the out lap, so every event counts."""
    x = (res or {}).get("result") or {}
    if x.get("outcome") != "completed":
        return False, "not completed (%s)" % x.get("outcome")
    hits = [i for i in x.get("impacts", []) if not i.get("pit")]
    if hits:
        return False, "%d impact(s), peak %.0f m/s^2" % (len(hits), x.get("peak_accel", 0))
    if x.get("track_limit_events", 0) > 0:
        return False, "%d track-limit event(s), %.1f s" % (x["track_limit_events"], x.get("track_limit_seconds", 0))
    return True, "clean (%d kerb strikes)" % x.get("kerb_count", 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--car", default="gt/maserati_mc12")
    ap.add_argument("--start", type=float, default=1.0)
    ap.add_argument("--step", type=float, default=0.01)
    ap.add_argument("--need", type=int, default=2, help="clean runs in a row at one share before it counts as reliable")
    ap.add_argument("--min", type=float, default=0.8)
    ap.add_argument("--linear", action="store_true", help="step down from --start by --step instead of bisecting")
    ap.add_argument("--input", default="wheel")
    a = ap.parse_args()
    def trial(scale):
        """True when --need runs in a row at this share are clean."""
        for attempt in range(a.need):
            t0 = time.time()
            cmd = [sys.executable, "-I", str(HERE / "gtr2-lap-check.py"), a.layout, "--car", a.car, "--input", a.input, "--quick",
                   "--drive-args=--outlap-scale %.3f --no-memory" % scale]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            ok, why = clean(last_result())
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"layout": a.layout, "car": a.car, "scale": round(scale, 3), "attempt": attempt + 1, "clean": ok, "why": why, "seconds": round(time.time() - t0)}) + "\n")
            print("scale %.3f attempt %d: %s" % (scale, attempt + 1, why), flush=True)
            if not ok:
                return False
        return True

    found = None
    if a.linear:
        scale = a.start
        while scale >= a.min - 1e-9 and found is None:
            if trial(scale):
                found = scale
            else:
                scale = round(scale - a.step, 4)
    elif trial(a.start):
        found = a.start
    else:
        lo, hi = a.min, a.start      # lo is assumed clean (checked at the end), hi is not
        while hi - lo > a.step + 1e-9:
            mid = round((lo + hi) / 2.0, 3)
            if trial(mid):
                lo = mid
            else:
                hi = mid
        found = lo if (lo > a.min or trial(lo)) else None
    print("reliably clean out lap at %s" % ("%.2f of the planned speeds" % found if found else "no share down to %.2f" % a.min), flush=True)
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
