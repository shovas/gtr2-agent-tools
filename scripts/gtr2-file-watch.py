"""Find out whether (and when) the game opens given files during a run, without admin rights.

Purpose: answer "does the game read this file?" for config, weather, mod marker files and the like. Each named file gets a read-handle oplock
(gtr2_ui/oplock.py): the oplock breaks the first time another process opens the file's contents,
and the break time is the answer. Existence and attribute checks do not break it, so they are not seen. After each break the file is armed again at
once, so every open is listed with its time (an open that happens in the few milliseconds between two arms can be missed).
The launcher itself opens files under Documents\\GTR2 (it copies the folder at the start and checks it at the end): those opens show as the first
and last times of such a file, so read the ones in between. The file is never read or changed by this script.
It runs the preflight, arms the files, launches the game through gtr2-launch.ps1, optionally runs tours (their own header flags are used),
closes the game through its menus, reverts UserData and ReplayData and checks Documents\\GTR2 like the suite.
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-file-watch.py [--tour NAME[,NAME]] PATH [PATH ...]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-file-watch.py --tour tour_race_weekend SDNDTG.DYN "%USERPROFILE%\\Documents\\GTR2\\UserData\\Log\\weather.txt"
A relative PATH is taken from the install folder. Exit code 0 if the run was clean (the report itself never fails the run).
"""
import argparse
import importlib.util
import threading
import os
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "gtr2_ui"))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


suite = _load("gtr2_nav_suite", "gtr2-nav-suite.py")
import oplock  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--plr", action="append", default=[], metavar="KEY=VALUE",
                    help='profile setting to change for this run only (byte-preserving edit of UserData/<profile>/<profile>.PLR, put back with git afterwards), e.g. --plr "FRACE Weather=0"')
    ap.add_argument("--tour", default="", help="comma separated tour names to run while watching (with or without tour_ prefix)")
    a = ap.parse_args()
    paths = [Path(os.path.expandvars(p)) for p in a.paths]
    paths = [p if p.is_absolute() else suite.ROOT / p for p in paths]
    tours = [t if t.startswith("tour_") else "tour_" + t for t in a.tour.split(",") if t]
    for t in tours:
        if not (suite.PATHS / (t + ".txt")).exists():
            print("no such tour: %s" % t)
            return 2
    if suite.game_running():
        print("GTR2 is already running; close it first (nothing was started)")
        return 2
    watched_here = set()
    for p in paths:
        try:
            watched_here.add(p.relative_to(suite.ROOT).as_posix())
        except ValueError:
            pass
    if suite.dirty_tracked() or (suite.untracked() - watched_here):       # a file you made to watch (not in git) is allowed; the run leaves it alone
        print("UserData or ReplayData has uncommitted changes; commit or revert them first (the run reverts these folders)")
        return 2
    if a.plr:
        plr = suite.diag.plr_path(suite.ROOT)
        lines = plr.read_bytes().split(b"\n")
        for tweak in a.plr:
            key, value = tweak.split("=", 1)
            hit = [i for i, l in enumerate(lines) if l.startswith(key.encode("latin1") + b'="')]
            if len(hit) != 1:
                print("--plr %r matches %d lines of the profile; nothing was started" % (key, len(hit)))
                return 2
            head, _, tail = lines[hit[0]].partition(b'="')
            lines[hit[0]] = head + b'="' + value.encode("latin1") + b'"' + tail.partition(b'"')[2]
        plr.write_bytes(b"\n".join(lines))
        print("profile for this run:", "; ".join(a.plr))
    pre = suite.nav("preflight")
    print(pre.stdout.strip())
    if pre.returncode:
        return 2
    wires, notes = {}, {}
    for p in paths:
        if not p.exists():
            notes[p] = "does not exist before the run (a file the game creates is not watched: an oplock needs the file to exist)"
            continue
        try:
            wires[p] = oplock.Tripwire(p).arm()
        except OSError as e:
            notes[p] = "could not be watched: %s" % e
    before = suite.untracked()
    armed = time.time()
    events, stop, marks = {p: [] for p in paths}, threading.Event(), {}

    def rearm_loop():
        while not stop.is_set():
            for p in list(wires):
                w = wires[p]
                if w.broke:
                    events[p].append(w.broke_at - armed)
                    w.disarm()
                    try:
                        wires[p] = oplock.Tripwire(p).arm()
                    except OSError as e:
                        notes[p] = "stopped being watched after %d opens: %s" % (len(events[p]), e)
                        del wires[p]
            time.sleep(0.01)
    threading.Thread(target=rearm_loop, daemon=True).start()
    ok = suite.start_game()
    marks["main menu ready"] = time.time() - armed
    if not ok:
        print("the game never reached the main menu; stopping")
    elif tours:
        for t in tours:
            r = suite.nav("path", *suite.flags_of(t), str(suite.PATHS / (t + ".txt")), timeout=900)
            line = (r.stdout + r.stderr).strip().splitlines()[-1:] or ["?"]
            print("%-32s %s  %s" % (t, "ok  " if r.returncode == 0 else "FAIL", line[0]), flush=True)
            if r.returncode:
                ok = False
                break
    marks["tours done"] = time.time() - armed
    closed = suite.exit_game() if suite.game_running() else True
    stop.set()
    time.sleep(0.1)
    print("\nopens of each file, in seconds after the watch began (main menu ready at %.1f s, tours done at %.1f s):" % (
        marks["main menu ready"], marks["tours done"]))
    for p in paths:
        if p in wires:
            w = wires[p]
            if w.broke:
                events[p].append(w.broke_at - armed)
            w.disarm()
        ev = events[p]
        if ev or p in wires:
            shown = ", ".join("%.1f" % e for e in ev[:14]) + (" ..." if len(ev) > 14 else "")
            print("  %3d opens  %s  %s%s" % (len(ev), p, shown, "  (" + notes[p] + ")" if p in notes else ""))
        else:
            print("  ???        %s  %s" % (p, notes.get(p, "")))
    clean = suite.revert_and_check(before) if closed else False
    return 0 if ok and clean else 1


if __name__ == "__main__":
    sys.exit(main())
