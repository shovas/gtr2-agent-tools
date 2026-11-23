r"""Benchmark: the game's own autopilot (its AI driver) drives the given car round the given layout in a short solo Race Weekend race, and the
lap times it sets are reported. It shows what lap time this car and track allow in the game's physics when the game drives (the benchmark the
hands-free driver is compared with).

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-ai-benchmark.py 4Imol --car gt/maserati_mc12

Reuses the lap runner's profile writing, launch and clean-up (gtr2-lap-check.py, gtr2-nav-suite.py); the race is the existing Race Weekend tour
(!SHORTRACE: shortest distance, no opponents; !RACE: the pause menu's Autopilot row, time acceleration, wait for the results). It reports every new
file the race wrote under UserData and ReplayData (lap times are read from the results/replay files that hold them), then reverts the game folder
like every other run. Leave the PC alone while it runs. Standard library only (plus the tools it imports).
"""
import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--car", default="gt/maserati_mc12")
    ap.add_argument("--timeout", type=int, default=1200, help="seconds the race may take")
    a = ap.parse_args()
    lc = load("lapcheck", "gtr2-lap-check.py")
    suite = lc.suite
    items, car_files = lc.layouts(), lc.cars()
    venue, trk, aiw = lc.pick_layout(a.layout, items)
    if a.car not in car_files:
        print("unknown car %r" % a.car, file=sys.stderr)
        return 2
    if suite.game_running():
        print("GTR2 is already running; close it first")
        return 2
    if suite.dirty_tracked() or suite.untracked():
        print("UserData or ReplayData has uncommitted changes; commit or revert them first")
        return 2
    before = suite.untracked()
    lc.PLR.write_bytes(lc.set_values(lc.PLR.read_bytes(), lc.profile_values(venue, trk, aiw, car_files[a.car], False, False)))
    message = ""
    out = ""
    new_files = []
    try:
        if not suite.start_game():
            print("the game never reached the main menu")
            return 1
        ok, out = lc.run_path(["MAIN MENU | APP_BUTTON_GAMEMODESELECT_GRANDPRIX | SUMMARY_GRANDPRIX",
                               "SUMMARY_GRANDPRIX | !SHORTRACE | SUMMARY_GRANDPRIX",
                               "SUMMARY_GRANDPRIX | CONTINUE | MONITOR_SINGLE",
                               "MONITOR_SINGLE | !RACE | POST RACE MONITOR"], "--session-step", "--drive-step", timeout=a.timeout)
        print("race:", "ok" if ok else "FAILED", "-", out.splitlines()[-1] if out else "")
        ok2, out2 = lc.run_path(["POST RACE MONITOR | APP_BUTTON_POSTRACENAVIGATION | MAIN MENU"], "--session-step", "--drive-step")
        if not ok2:
            message = "could not leave the results page (the game is left open): " + out2.splitlines()[-1]
        after = suite.untracked()
        new_files = sorted(set(after) - set(before))
        for f in new_files:
            print("new file:", f)
            p = lc.ROOT / f
            if p.suffix.lower() in (".txt", ".xml", ".log", ".dat", ".res") and not f.endswith("trace.txt"):
                text = p.read_text(encoding="latin1", errors="replace")
                for line in text.splitlines():
                    if line.strip() and (f.endswith("raceresults.txt") or re.search(r"lap|best|time", line, re.I)):
                        print("   ", line.strip().replace(chr(0), "")[:200])
    finally:
        if not message:
            if suite.exit_game():
                clean = suite.revert_and_check(before)
                print("cleanup:", "clean" if clean else "NOT clean")
            else:
                print("the game was left open")
    if message:
        print(message)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
