r"""Bisection search of one driver setting by lap sessions: between a low value that is known good and a high value that is not, test the midpoint with a fresh
10-lap session (gtr2-lap-campaign.py, one session, --fresh), call it good when at least --min-clean of the timed laps were clean (an unclean lap is a fail,
not a slow time), keep the half that brackets the limit, and stop by the 1% rule: the test whose value differs from the previous test by 1% or less (--stop-rel) is the last one. Every test (value, clean laps, best clean lap)
is appended to scripts/gtr2_ui/runs/bisect.jsonl and printed, and the end result is the highest good value with its best clean lap time.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-bisect.py Imola4Imol --car gt/maserati_mc12 --lo 1.0 --hi 1.5 \
        --template "--meta-start {v} --meta-min {v} --meta-max {v}"

With --gallop STEP (and no --hi) the upper end is found first by doubling: lo+STEP, then +2 STEP, +4 STEP, ... while the tests are good; the first failure is hi and the bisection runs in [last good, hi].
{v} in --template is the tested value (here a fixed push factor: the push does not climb, so a session measures one value). The PC must be left alone:
a test takes about 25 minutes, so 1.0 to 1.5 takes about six tests. Standard library only.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMP = HERE / "gtr2_ui" / "runs" / "campaign.jsonl"
OUT = HERE / "gtr2_ui" / "runs" / "bisect.jsonl"


def run_test(a, v):
    before = len(CAMP.read_text(encoding="utf-8").splitlines()) if CAMP.exists() else 0
    drive = a.template.format(v=("%g" % v)) + (" " + a.common if a.common else "")
    cmd = [sys.executable, "-I", str(HERE / "gtr2-lap-campaign.py"), a.layout, "--car", a.car, "--max-sessions", "1", "--fresh", "--lap-allow", str(a.lap_allow), "--drive-args=" + drive]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    lines = CAMP.read_text(encoding="utf-8").splitlines() if CAMP.exists() else []
    if len(lines) <= before:
        return None
    laps = json.loads(lines[-1]).get("laps") or []
    clean = [l["time"] for l in laps if l.get("clean")]
    return {"value": v, "laps": len(laps), "clean": len(clean), "best_clean": min(clean) if clean else None}


def test_one(a, v, lo, hi, n):
    t0 = time.time()
    r = run_test(a, v)
    if r is None:
        print("test at %g did not run: stopping" % v, flush=True)
        return None
    good = r["clean"] >= a.min_clean
    r.update(good=good, bracket=[lo, hi], layout=a.layout, car=a.car, template=a.template, seconds=round(time.time() - t0))
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(r) + "\n")
    print("test %d: %g -> %d of %d clean, best clean %s s: %s" % (n + 1, v, r["clean"], r["laps"], ("%.2f" % r["best_clean"]) if r["best_clean"] else "none", "good" if good else "fail"), flush=True)
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--car", default="gt/maserati_mc12")
    ap.add_argument("--lo", type=float, required=True, help="a value expected to be good (clean)")
    ap.add_argument("--hi", type=float, default=None, help="a value expected to fail (with --gallop: an optional cap on the doubling)")
    ap.add_argument("--gallop", type=float, default=0.0, help="find the upper end first by doubling steps: lo+G, then +2G, +4G, ... while good; the first failure becomes hi")
    ap.add_argument("--stop-rel", type=float, default=0.01, help="stop after a test whose value is within this relative change of the previous test (rule: 1 percent)")
    ap.add_argument("--tol", type=float, default=0.0, help="also stop when hi - lo is below this absolute width (0 = off)")
    ap.add_argument("--template", required=True, help='driver options with {v}, e.g. "--meta-start {v} --meta-min {v} --meta-max {v}"')
    ap.add_argument("--common", default="", help="driver options added to every test")
    ap.add_argument("--min-clean", type=int, default=8, help="clean timed laps (of 10) for a value to count as good")
    ap.add_argument("--lap-allow", type=int, default=150)
    ap.add_argument("--max-tests", type=int, default=8)
    a = ap.parse_args()
    if a.hi is None and a.gallop <= 0:
        ap.error("give --hi, or --gallop STEP to find the upper end")
    lo, hi, best, prev, n, step = a.lo, a.hi, None, None, 0, a.gallop
    while step > 0 and n < a.max_tests:
        v = round(lo + step, 4)
        if hi is not None and v >= hi:
            break
        r = test_one(a, v, lo, hi, n)
        n += 1
        if r is None:
            return 1
        prev = v
        if r["good"]:
            lo, best, step = v, r, step * 2
        else:
            hi = v
            break
    if hi is None:
        print("no failure found up to %g in %d tests: raise --max-tests or --hi; highest good value %g" % (lo, n, lo), flush=True)
        return 0
    while n < a.max_tests:
        if a.tol > 0 and hi - lo < a.tol:
            break
        v = round((lo + hi) / 2.0, 4)
        r = test_one(a, v, lo, hi, n)
        n += 1
        if r is None:
            return 1
        if r["good"]:
            lo, best = v, r
        else:
            hi = v
        if prev is not None and abs(v - prev) <= a.stop_rel * abs(prev):
            print("change from the previous test %.2f percent: stop (1 percent rule)" % (100.0 * abs(v - prev) / abs(prev)), flush=True)
            break
        prev = v
    print("bracket %g to %g; highest good value %s%s" % (lo, hi, ("%g" % best["value"]) if best else "none tested", (", best clean lap %.2f s" % best["best_clean"]) if best and best["best_clean"] else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
