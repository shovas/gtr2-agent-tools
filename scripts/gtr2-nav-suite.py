"""Run every navigation tour against the real game, with no model in the loop, and report which pages and steps still work.

Purpose: a deterministic regression run for the menu map (scripts/nav_paths/*.txt). It launches the game through gtr2-launch.ps1, waits for
the main menu, runs each tour in the order that works (game state leaks between tours: Time Trial and Practice sessions first, the Driving School session and the season tour last), closes the
game through its own menus, puts the profile back with git, checks that Documents\\GTR2 is unchanged and prints a table.
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-nav-suite.py [--only NAME,NAME] [--skip-season] [--keep-open] [--dry-run]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-nav-suite.py --dry-run     (prints the plan and the flags each tour needs)
Exit code 0 only if every tour passed and cleanup was clean. Takes about 3 minutes. Needs a clean UserData/ReplayData (it reverts them).
Safety: each tour's own header says which opt-in flags it needs; they are read from the file, so a tour can't get a flag it doesn't declare.
Cleanup only touches UserData\\<profile>, UserData\\LOG, UserData\\<profile>\\Save and ReplayData: tracked files are restored with git, and
untracked files that did not exist before the run are deleted by exact path.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "gtr2_ui"))
import diag  # noqa: E402
from paths import WINDOW_KEY  # noqa: E402

ROOT = diag.game_root()                          # the game folder (GTR2_ROOT, else the parent of scripts/)
os.environ["GTR2_ROOT"] = str(ROOT)              # child processes (launcher, navigator) use the same folder
PROFILE = diag.profile_name(ROOT)
PATHS = SCRIPTS / "nav_paths"
PY = str(SCRIPTS / ".venv" / "Scripts" / "python.exe")
NAV = str(SCRIPTS / "gtr2-nav.py")
WATCHED = ["UserData", "ReplayData"]

# Order matters: sessions first on a fresh game (Time Trial loads as Open Practice once Practice pages were visited, and the Driving School
# tour changes the profile's track), then everything that does not start a session, the season tour last (it starts a season).
ORDER = [
    "tour_session_timetrial", "tour_popup_session_timetrial", "tour_session_practice", "tour_popup_session_practice",
    "tour_options_main", "tour_options_school", "tour_options_practice", "tour_options_24h",
    "tour_options_game_main", "tour_options_game_school", "tour_options_game_practice", "tour_options_game_24h", "tour_options_game_prechamp",
    "tour_setup_practice", "tour_setup_grandprix", "tour_setup_24h", "tour_setup_timetrial", "tour_setup_school", "tour_setup_championship",
    "tour_popup_menu", "tour_champ_preseason", "tour_champ_custom", "tour_lan", "tour_lan_host",
    "tour_race_weekend", "tour_replay", "tour_race_24h",   # races change the Race Weekend and 24 Hour setup pages (distance, opponents): after every tour that shows them
    "tour_session_school",       # sets the profile's track to Anderstorp, which changes the track-specific pages: after everything that shows them
    "tour_champ_season",
    "tour_champ_round",          # needs the season tour's season in progress (it restarts it through the warning's confirm)
    "tour_select_wheel",         # selects JOY1 as the control device (changes the Controls > Buttons page for the rest of the game process): last
]


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kw)


def flags_of(name):
    """The opt-in flags a tour declares in its header comment (e.g. --session-step)."""
    text = (PATHS / (name + ".txt")).read_text(encoding="utf-8")
    header = "\n".join(l for l in text.splitlines() if l.startswith("#"))
    return sorted(set(re.findall(r"--[a-z]+-step", header)))


def needs_unlock(name):
    """A tour whose header says it needs SDNDTG.DYN (the empty unlock-everything file in the install root)."""
    text = (PATHS / (name + ".txt")).read_text(encoding="utf-8")
    return any("SDNDTG.DYN" in l for l in text.splitlines() if l.startswith("#"))


def untracked():
    out = run(["git", "status", "--porcelain", "-uall", "-z", "--"] + WATCHED).stdout
    return {e[3:] for e in out.split("\0") if e.startswith("??")}


def dirty_tracked():
    out = run(["git", "status", "--porcelain", "-z", "--"] + WATCHED).stdout
    return [e[3:] for e in out.split("\0") if e and not e.startswith("??")]


def nav(*args, timeout=600):
    return run([PY, "-I", NAV, *args], timeout=timeout)


def game_running():
    return "GTR2.exe" in run(["tasklist", "/FI", "IMAGENAME eq GTR2.exe", "/NH"]).stdout


def wait_launcher_idle(timeout=120.0):
    """Clean up after a dead or stuck launcher run, immediately: `gtr2-launch.ps1 -Reap` reads the launcher's state file (its pid and the game's),
    stops an orphaned game or a stuck launcher, restores Documents/GTR2 from a stale backup and clears the lock. Exit 0 = clean (the usual
    case, takes under a second), 3 = a live launcher run owns the lock (wait for it, up to `timeout`), 4 = a game that is not ours is running."""
    t0 = time.time()
    while True:
        r = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "gtr2-launch.ps1"), "-Reap"])
        if r.stdout.strip() and "reap: clean" not in r.stdout:
            print(r.stdout.strip(), flush=True)
        if r.returncode == 0:
            return True
        if r.returncode == 4 or time.time() - t0 > timeout:
            return False
        time.sleep(1.0)


def start_game():
    """Launch the game through gtr2-launch.ps1 and wait for the main menu. Returns True when it is there."""
    if not wait_launcher_idle():
        print("the previous launcher has not finished: not starting another")
        return False
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File",
                      str(SCRIPTS / "gtr2-launch.ps1"), "-GameArgs", "-trace=100"], cwd=ROOT, creationflags=0x08000000)    # launches without the trace closed at the first track load (CLAUDE.md)
    r = nav("ready", "--timeout", "90")
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode == 0


def exit_game():
    """Close the game through its own menus (it must be on the main menu), wait for the process to end and stop the nav server.
    Returns True when the game is gone."""
    # `exit` checks for the main menu itself and refuses (exit code 2) otherwise; a separate `where` call first cost a whole
    # process start-up (about 5 s of loading references) while the game sat on the main menu.
    e = nav("exit", timeout=120)
    print(e.stdout.strip() or e.stderr.strip())
    good = e.returncode == 0
    if not good:
        print("left the game open: it is not on the main menu")
    for _ in range(40):
        if not game_running():
            break
        time.sleep(0.5)
    nav("stop")
    return good and not game_running()


def revert_and_check(before_untracked):
    """After the game has closed: put UserData and ReplayData back (tracked files with git, files that did not exist before the run by
    exact path), report crash dumps, wait for the launcher to restore Documents\\GTR2 and compare it with the snapshot. Returns True if clean."""
    ok = True
    run(["git", "checkout", "--"] + WATCHED)
    dumps = [p for p in sorted(untracked() - before_untracked) if "minidump" in p.lower()]
    if dumps:                         # a crash of the game: say so before the clean-up deletes the evidence
        print("GAME CRASH DUMP(S):", ", ".join(dumps))
        for d in dumps:               # keep the report (not the ~230 MB dump) in scripts/gtr2_ui/runs/crashes before the clean-up deletes the dump
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("crashreport", SCRIPTS / "gtr2-crash-report.py")
                cr = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(cr)
                rep = cr.save(ROOT / d, SCRIPTS / "gtr2_ui" / "runs" / "crashes")
                print("  saved crash report:", rep)
                print("  " + cr.summary(cr.MiniDump(ROOT / d)))
            except Exception as e:      # the report is a convenience: never let it hide the failure
                print("  could not analyse the dump:", e)
        ok = False
    for p in sorted(untracked() - before_untracked):
        f = ROOT / p
        if f.is_file():
            f.unlink()
    for d in sorted({(ROOT / p).parent for p in (untracked() - before_untracked)}, reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    for d in (ROOT / "UserData" / PROFILE / "Championships", ROOT / "UserData" / PROFILE / "Save"):
        if d.exists() and not any(d.rglob("*.*")):
            for sub in sorted(d.rglob("*"), reverse=True):
                sub.rmdir()
            d.rmdir()
    left = dirty_tracked() + sorted(untracked() - before_untracked)
    print("cleanup:", "clean" if not left else "NOT clean: " + ", ".join(left[:6]))
    ok = ok and not left
    docs = Path.home() / "Documents"
    wait_launcher_idle()          # the launcher restores Documents (once took over 60 s): wait for it, finish the restore if it never does
    d = run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS.parent / "Tools" / "DocumentsGTR2.ps1"), "-Root", str(ROOT)])
    lines = [l.strip() for l in d.stdout.strip().splitlines() if l.strip()]
    print("Documents\\GTR2:", "; ".join(lines) if lines else "?")
    # only-in-snapshot weather.txt is drift that appeared during the 2026-11-11 batches and that our runs do not cause (the launcher restores that
    # file from its backup; the other session writes it to force weather): reported, but it does not fail a lap
    other = [l for l in lines if l.startswith(("differs:", "only in live:", "only in snapshot:")) and "weather.txt" not in l]
    return ok and (d.returncode == 0 or not other)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="comma separated tour names (with or without tour_ prefix)")
    ap.add_argument("--skip-season", action="store_true", help="leave out the championship season tour (it starts a season)")
    ap.add_argument("--keep-open", action="store_true", help="do not close the game or clean up at the end")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--learn", action="store_true", help="learn the reference pictures for the configured test size: run every tour in learning mode, then compute the page-pair scores (use for a size other than 1280x720)")
    a = ap.parse_args()

    tours = [t for t in ORDER if (PATHS / (t + ".txt")).exists()]
    missing = sorted(p.stem for p in PATHS.glob("tour_*.txt") if p.stem not in ORDER)
    if a.only:
        want = {w if w.startswith("tour_") else "tour_" + w for w in a.only.split(",")}
        tours = [t for t in tours if t in want]
    skipped = [t for t in tours if needs_unlock(t) and not (ROOT / "SDNDTG.DYN").exists()]
    tours = [t for t in tours if t not in skipped]
    if skipped:
        print("skipped (SDNDTG.DYN is not in the install root):", ", ".join(skipped))
    if a.skip_season:
        tours = [t for t in tours if t != "tour_champ_season"]
    if a.dry_run:
        for t in tours:
            print("%-32s %s" % (t, " ".join(flags_of(t)) or "(no flags)"))
        if missing:
            print("NOT in ORDER (add them to the suite):", ", ".join(missing))
        return 0
    if missing:
        print("warning: tours not in the suite's ORDER:", ", ".join(missing))
    if a.learn:
        print("LEARNING MODE for the test size %s: this runs a full navigation sweep of every tour (about 6 to 10 minutes), saves a reference picture of each page it reaches to scripts/gtr2_ui/baselines/local/%s and then computes the page-pair scores (about 4 minutes more). Leave the PC alone while it runs." % (WINDOW_KEY, WINDOW_KEY), flush=True)
    if game_running():
        print("GTR2 is already running; close it first (nothing was started)")
        return 2
    if dirty_tracked() or untracked():
        print("UserData or ReplayData has uncommitted changes; commit or revert them first (the run reverts these folders):")
        for p in (dirty_tracked() + sorted(untracked()))[:10]:
            print("  ", p)
        return 2
    before_untracked = untracked()
    results, ok = [], True
    t0 = time.time()
    pre = nav("preflight")
    print(pre.stdout.strip())
    if pre.returncode:
        print("preflight failed; nothing was started")
        return 2
    if not start_game():
        print("the game never reached the main menu; stopping")
        return 1
    for t in tours:
        flags = flags_of(t)
        s = time.time()
        r = nav("learn", *flags, "--start", "MAIN MENU", str(PATHS / (t + ".txt"))) if a.learn else nav("path", *flags, str(PATHS / (t + ".txt")))
        out = r.stdout + r.stderr
        m = re.search(r"(\d+) page\(s\) learned", out) if a.learn else re.search(r"path of (\d+) steps done in ([\d.]+) s", out)
        if r.returncode == 0 and m and not (a.learn and ("stopped at" in out or "expected " in out)):
            if a.learn:
                results.append((t, "ok", int(m.group(1)), time.time() - s, ""))
                print("%-32s learned %2d page(s)  %6.2f s" % (t, int(m.group(1)), time.time() - s), flush=True)
                continue
            results.append((t, "ok", int(m.group(1)), float(m.group(2)), ""))
            print("%-32s ok   %3d steps  %6.2f s" % (t, int(m.group(1)), float(m.group(2))), flush=True)
            continue
        bad = [l for l in out.splitlines() if "stopped at" in l or "NOT verified" in l or "refused" in l or "not on" in l]
        if not bad:
            bad = [l for l in out.splitlines() if l.strip()][-3:]      # no known failure line: show the last output instead of nothing
        results.append((t, "FAIL", 0, time.time() - s, "; ".join(bad[-2:])))
        print("%-32s FAIL %s" % (t, "; ".join(bad[-2:])), flush=True)
        ok = False
        print(nav("diagnose").stdout.strip())
        break                                  # the game is on an unknown page: running on would only produce noise
    if not a.keep_open:
        closed = exit_game()
        ok = ok and closed
        if not game_running():
            ok = revert_and_check(before_untracked) and ok
    if a.learn and ok:
        print("computing the page-pair scores...", flush=True)
        ok = nav("index").returncode == 0 and ok
    passed = sum(1 for r in results if r[1] == "ok")
    steps = sum(r[2] for r in results)
    print("\n%d of %d tours passed, %d steps, %.0f s total" % (passed, len(tours), steps, time.time() - t0))
    return 0 if ok and passed == len(tours) else 1


if __name__ == "__main__":
    sys.exit(main())
