r"""A lap campaign: keeps lowering the lap time with lap by lap live adjustment (gtr2-drive-lap.py --session-laps), in sessions of at most
--laps timed laps each (the tyres fall off after about 10 laps), and restarts the session for fresh tyres while the adjustments are still
gaining time. What the maps and the push factor learned is carried from one session to the next (the driver's learned memory, scripts/
gtr2_driving/learned/). It stops when a session's best clean lap is not faster than the previous session's by --gain seconds (default 0.1), after --max-sessions,
or when a session fails to run. The PC must be left alone; a session is about 25 minutes. Every session's laps go to
scripts/gtr2_ui/runs/campaign.jsonl.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-campaign.py Imola4Imol --car gt/maserati_mc12 [--laps 10 --max-sessions 5 --gain 0.1] [--drive-args="--line-opt"]
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "gtr2_ui" / "runs" / "lap_results.jsonl"
OUT = HERE / "gtr2_ui" / "runs" / "campaign.jsonl"


def last_result():
    lines = [l for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
    return json.loads(lines[-1]) if lines else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--car", default="gt/maserati_mc12")
    ap.add_argument("--input", default="wheel")
    ap.add_argument("--laps", type=int, default=10, help="timed laps per session (fresh tyres at each session start)")
    ap.add_argument("--max-sessions", type=int, default=5)
    ap.add_argument("--gain", type=float, default=0.1, help="a session must beat the previous best clean lap by this many seconds for another session to start")
    ap.add_argument("--drive-args", default="", help="extra driver options for every session")
    ap.add_argument("--fresh", action="store_true", help="ignore the learned memory of earlier campaigns in the first session")
    a = ap.parse_args()
    best_prev, session = None, 0
    while session < a.max_sessions:
        session += 1
        total = 200 + a.laps * 150
        extra = "--session-laps %d --total %d %s" % (a.laps, total, a.drive_args)
        if a.fresh and session == 1:
            extra += " --no-memory"
        cmd = [sys.executable, "-I", str(HERE / "gtr2-lap-check.py"), a.layout, "--car", a.car, "--input", a.input, "--timeout", str(total + 600), "--drive-args=" + extra.strip()]
        t0 = time.time()
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        res = last_result() or {}
        x = res.get("result") or {}
        laps = x.get("session_laps") or []
        clean = [l["time"] for l in laps if l.get("clean")]
        best = min(clean) if clean else None
        with OUT.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"layout": a.layout, "car": a.car, "session": session, "laps": laps, "best_clean": best, "outcome": x.get("outcome"), "seconds": round(time.time() - t0)}) + "\n")
        print("session %d: %d laps, %d clean, best clean %s s, outcome %s" % (session, len(laps), len(clean), "%.2f" % best if best else "none", x.get("outcome")), flush=True)
        if best is None:
            print("no clean lap: stopping", flush=True)
            break
        if best_prev is not None and best > best_prev - a.gain:
            print("no gain of %.1f s over the previous session (%.2f s): stopping" % (a.gain, best_prev), flush=True)
            break
        best_prev = best if best_prev is None else min(best_prev, best)
    print("campaign done: best clean lap %s s" % ("%.2f" % best_prev if best_prev else "none"), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
