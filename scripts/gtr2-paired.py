#!/usr/bin/env python3
"""Paired (A B A B ...) lap sessions for a comparison, with a per-session record and a per-arm summary.

Runs `gtr2-lap-check.py` for each session of two driver-option sets, alternating A and B, reverts the game folder's run-generated files
before each session (the lap check refuses to start with them), and reads the session's signal log (`--sig-log` is added). For each
session it records whether the car spun in the 2570 m bend (yaw rate of 120 deg/s or more inside the box x -560..-470, z -200..10),
the laps through the bend and the worst yaw rate, and appends one JSON line per session to `gtr2_ui/runs/paired.jsonl`. The summary
per arm is the number of sessions with a bend spin and the spin rate per bend lap; a difference needs enough sessions per arm
(eight is the working minimum, see docs/follower-redesign-plan.md).

Usage:
  python -I scripts\\gtr2-paired.py --a "--follower designed --st-head-ahead 8" --b "--follower designed --st-head-ahead 16" --pairs 4 --laps 8
  python -I scripts\\gtr2-paired.py ... --dry-run     (prints the planned runs, runs nothing)

Adds only the listed driver options; the layout, car and input are the lap check's defaults for Imola 4Imol with the wheel.
Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUNS = HERE / "gtr2_ui" / "runs"
GAME = Path(ROOT.parent / "gtr2-agent-tools-game")
PY = HERE / ".venv" / "Scripts" / "python.exe"
BEND = (-560.0, -470.0, -200.0, 10.0)      # x0, x1, z0, z1 of the 2570 m bend box (lap distance about 2400 to 2650 m)
SPIN_DEG_S = 120.0


def bend_metrics(path: Path) -> dict:
    rows = []
    with path.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(line for line in f if not line.startswith("#"))]
    bend = [r for r in rows if BEND[0] <= float(r["x"]) <= BEND[1] and BEND[2] <= float(r["z"]) <= BEND[3]
            and float(r["speed"]) > 5.0 and r["lap"] != "0"]
    laps = sorted(set(r["lap"] for r in bend))
    spin = [r for r in bend if abs(float(r["yawrate"])) >= SPIN_DEG_S]
    return {
        "bend_laps": len(laps),
        "spin": bool(spin),
        "spin_lap": min((r["lap"] for r in spin), default=None),
        "bend_peak_yaw": round(max((abs(float(r["yawrate"])) for r in bend), default=0.0), 1),
        "max_yaw": round(max((abs(float(r["yawrate"])) for r in rows), default=0.0), 1),
    }


def revert_game() -> None:
    subprocess.run(["git", "-C", str(GAME), "checkout", "--", "UserData", "ReplayData"], check=False)
    subprocess.run(["git", "-C", str(GAME), "clean", "-fdq", "--", "UserData", "ReplayData"], check=False)


REFUSALS = ("GTR2 is already running", "uncommitted changes", "nothing was started")


def game_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq GTR2.exe", "/NH"], capture_output=True, text=True, check=False).stdout
    return "GTR2.exe" in out


def wait_game_closed(seconds: int = 90) -> bool:
    end = time.time() + seconds
    while game_running():
        if time.time() > end:
            return False
        time.sleep(3)
    return True


def run_session(arm: str, options: str, laps: int, timeout_s: int, n: int = 0) -> dict:
    sid = "%s%d_%s" % (arm, n, time.strftime("%Y%m%d%H%M%S"))     # unique id: a result can be traced to its own check output
    rec = {"arm": arm, "options": options, "sid": sid, "n": n}
    closed = wait_game_closed()
    if not closed:
        rec.update(seconds=0, error="infrastructure: GTR2 still running 90 s after the previous session; session not started", infra=True)
        return rec
    revert_game()
    drive = "--session-laps %d --total %d %s --sig-log" % (laps, 130 * laps + 200, options)
    before = set(RUNS.glob("signals_*.csv"))
    out_path = RUNS / ("paired_%s.out" % sid)
    t0 = time.time()
    with out_path.open("w", encoding="utf-8") as out:
        subprocess.run([str(PY), "-I", str(HERE / "gtr2-lap-check.py"), "Imola4Imol", "--car", "gt/maserati_mc12", "--input", "wheel",
                        "--timeout", str(timeout_s), "--drive-args=" + drive], cwd=str(ROOT), check=False,
                       stdout=out, stderr=subprocess.STDOUT)
    rec.update(seconds=round(time.time() - t0), check_output=out_path.name)
    text = out_path.read_text(encoding="utf-8", errors="replace")
    refusal = next((ln for ln in text.splitlines() if any(r in ln for r in REFUSALS)), None)
    new = sorted(set(RUNS.glob("signals_*.csv")) - before, key=lambda p: p.stat().st_mtime)
    if refusal:
        rec.update(error="infrastructure: lap check refused to start: " + refusal.strip(), infra=True)
    elif new:
        rec.update(bend_metrics(new[-1]))
        rec["signals"] = new[-1].name
    else:
        rec.update(error="no signal log written (the session did not reach the driver's end; see check_output)", infra=True)
    return rec


def summarise(recs: list[dict]) -> str:
    out = []
    for arm in sorted(set(r["arm"] for r in recs)):
        rs = [r for r in recs if r["arm"] == arm and "bend_laps" in r]
        spins = sum(1 for r in rs if r["spin"])
        laps = sum(r["bend_laps"] for r in rs)
        infra = sum(1 for r in recs if r["arm"] == arm and r.get("infra"))
        out.append("arm %s: %d sessions with a bend log, %d spins, %d bend laps, spin rate per bend lap %s; %d infrastructure failures (not counted)"
                   % (arm, len(rs), spins, laps, ("%.0f%%" % (100.0 * spins / laps)) if laps else "n/a", infra))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="Paired A/B lap sessions with bend-spin records.")
    ap.add_argument("--a", required=True, help="driver options for arm A (quoted)")
    ap.add_argument("--b", required=True, help="driver options for arm B (quoted)")
    ap.add_argument("--pairs", type=int, default=4, help="number of A-then-B pairs (default 4: eight sessions)")
    ap.add_argument("--laps", type=int, default=8, help="timed laps per session (default 8)")
    ap.add_argument("--timeout", type=int, default=1300, help="seconds allowed per session (default 1300)")
    ap.add_argument("--dry-run", action="store_true", help="print the planned sessions and do nothing else")
    a = ap.parse_args()
    plan = []
    for i in range(1, a.pairs + 1):
        plan += [("A", a.a), ("B", a.b)]
    if a.dry_run:
        for n, (arm, opts) in enumerate(plan, 1):
            print("%d %s: --session-laps %d %s --sig-log" % (n, arm, a.laps, opts))
        print("%d sessions; each reverts the game folder first" % len(plan))
        return 0
    if not PY.exists():
        print("scripts\\.venv is missing: run gtr2-setup.py first", file=sys.stderr)
        return 1
    log = RUNS / "paired.jsonl"
    RUNS.mkdir(parents=True, exist_ok=True)
    recs = []
    for n, (arm, opts) in enumerate(plan, 1):
        rec = run_session(arm, opts, a.laps, a.timeout, n)
        recs.append(rec)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        print("%d %s: %s" % (n, arm, ("spin in lap %s" % rec.get("spin_lap")) if rec.get("spin") else
                                     ("no spin" if "bend_laps" in rec else rec.get("error", ""))), flush=True)
    print(summarise(recs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
