r"""Bisection search of one driver setting by lap sessions: between a low value that is known good and a high value that is not, test the midpoint with a fresh
10-lap session (gtr2-lap-campaign.py, one session, --fresh), call it good when at least --min-clean of the timed laps were clean (an unclean lap is a fail,
not a slow time), keep the half that brackets the limit, and stop when the bracket is narrower than --tol. Every test (value, clean laps, best clean lap)
is appended to scripts/gtr2_ui/runs/bisect.jsonl and printed, and the end result is the highest good value with its best clean lap time.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-bisect.py Imola4Imol --car gt/maserati_mc12 --lo 1.0 --hi 1.5 --tol 0.02 \
        --template "--meta-start {v} --meta-min {v} --meta-max {v}"

{v} in --template is the tested value (here a fixed push factor: the push does not climb, so a session measures one value). The PC must be left alone:
a test takes about 25 minutes, so a bracket of 0.5 down to 0.02 takes five tests. Standard library only.
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--car", default="gt/maserati_mc12")
    ap.add_argument("--lo", type=float, required=True, help="a value expected to be good (clean)")
    ap.add_argument("--hi", type=float, required=True, help="a value expected to fail")
    ap.add_argument("--tol", type=float, default=0.02, help="stop when hi - lo is below this")
    ap.add_argument("--template", required=True, help='driver options with {v}, e.g. "--meta-start {v} --meta-min {v} --meta-max {v}"')
    ap.add_argument("--common", default="", help="driver options added to every test")
    ap.add_argument("--min-clean", type=int, default=8, help="clean timed laps (of 10) for a value to count as good")
    ap.add_argument("--lap-allow", type=int, default=150)
    ap.add_argument("--max-tests", type=int, default=8)
    a = ap.parse_args()
    lo, hi, best = a.lo, a.hi, None
    for n in range(a.max_tests):
        if hi - lo < a.tol:
            break
        v = round((lo + hi) / 2.0, 4)
        t0 = time.time()
        r = run_test(a, v)
        if r is None:
            print("test at %g did not run: stopping" % v, flush=True)
            return 1
        good = r["clean"] >= a.min_clean
        r.update(good=good, bracket=[lo, hi], layout=a.layout, car=a.car, template=a.template, seconds=round(time.time() - t0))
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r) + "\n")
        print("test %d: %g -> %d of %d clean, best clean %s s: %s" % (n + 1, v, r["clean"], r["laps"], ("%.2f" % r["best_clean"]) if r["best_clean"] else "none", "good" if good else "fail"), flush=True)
        if good:
            lo, best = v, r
        else:
            hi = v
    print("bracket %g to %g; highest good value %s%s" % (lo, hi, ("%g" % best["value"]) if best else "none tested", (", best clean lap %.2f s" % best["best_clean"]) if best and best["best_clean"] else ""), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
