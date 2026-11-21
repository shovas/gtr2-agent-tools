r"""Recover after an interrupted run: stop stale nav servers, close an orphaned game, clean up the launcher, optionally revert the game folder.

A killed batch (lap check, suite, tour) can leave a GTR2 window open, one or more `gtr2-nav.py serve` background servers that no longer
answer ("nav server closed the connection mid-command"), a launcher lock, and a changed profile in the game folder. Every later run then
fails or refuses to start. This does the clean-up in the order that worked by hand:
  1. stop every `gtr2-nav.py serve` process (they are re-started on demand);
  2. if a GTR2.exe is running: ask the menus to close it (`gtr2-nav.py exit`, a fresh server); only with --force kill it if that did not work;
  3. `gtr2-launch.ps1 -Reap` (restores Documents\GTR2 and the launcher state), then checks `Tools\DocumentsGTR2.ps1` drift;
  4. with --revert: `git checkout -- UserData ReplayData` and `git clean -fd` of those folders in the game folder (the suite does the same).
Standard library only. Exit 0 when nothing is left running and the launcher is clean, 2 otherwise.
Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2-recover.py [--dry-run] [--force] [--revert]
Example: scripts\.venv\Scripts\python.exe -I scripts\gtr2-recover.py --force --revert
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
from gtr2_ui import diag  # noqa: E402

PY = sys.executable


def ps(command, timeout=60):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()


def nav_servers():
    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'gtr2-nav\\.py\\s+serve' } | Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress")
    if not out:
        return []
    v = json.loads(out)
    return v if isinstance(v, list) else [v]


def runners():
    """Driver, lap check, campaign and bisect processes (a killed background chain leaves them running, and the driver holds the vJoy device)."""
    me = os.getpid()
    out = ps("Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and $_.CommandLine -match 'gtr2-(lap-campaign|lap-check|drive-lap|bisect)\.py' } | Select-Object -ExpandProperty ProcessId | ConvertTo-Json -Compress")
    if not out:
        return []
    v = json.loads(out)
    return [p for p in (v if isinstance(v, list) else [v]) if p != me]


def game_pids():
    out = ps("Get-Process GTR2 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id | ConvertTo-Json -Compress")
    if not out:
        return []
    v = json.loads(out)
    return v if isinstance(v, list) else [v]


def reap():
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "gtr2-launch.ps1"), "-Reap"], capture_output=True, text=True, timeout=120)
    return (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="only say what would be done")
    ap.add_argument("--force", action="store_true", help="kill the game if closing it through the menus did not work, and kill leftover lap campaign / lap check / driver / bisect processes (they hold the vJoy device)")
    ap.add_argument("--revert", action="store_true", help="revert UserData and ReplayData in the game folder to the last commit and delete new files there")
    a = ap.parse_args()
    ok = True

    if a.force:
        run_pids = runners()
        print("runner processes (lap campaign / lap check / driver / bisect): %s" % (run_pids or "none"))
        if run_pids and not a.dry_run:
            for p in run_pids:
                subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True)
            time.sleep(1.5)

    servers = nav_servers()
    print("nav servers: %s" % (servers or "none"))
    if servers and not a.dry_run:
        for p in servers:
            subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True)
        time.sleep(1.5)

    games = game_pids()
    print("GTR2.exe: %s" % (games or "not running"))
    if games and not a.dry_run:
        r = subprocess.run([PY, "-I", str(SCRIPTS / "gtr2-nav.py"), "exit"], capture_output=True, text=True, timeout=90)
        print("  menu exit: %s" % (r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or ["no output"])[-1])
        for _ in range(20):
            if not game_pids():
                break
            time.sleep(1)
        if game_pids():
            if a.force:
                for p in game_pids():
                    subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True)
                    print("  killed pid %s" % p)
                time.sleep(10)        # the launcher notices the game ended and restores Documents\GTR2
            else:
                print("  still running: use --force to kill it")
                ok = False
        subprocess.run([PY, "-I", str(SCRIPTS / "gtr2-nav.py"), "stop"], capture_output=True, text=True, timeout=30)
        for p in nav_servers():
            subprocess.run(["taskkill", "/PID", str(p), "/F"], capture_output=True)

    if not a.dry_run:
        line = reap()[0]
        print("launcher: %s" % line)
        ok = ok and "clean" in line
        if not game_pids() and not ok and "active" in line:
            time.sleep(10)
            line = reap()[0]
            print("launcher (again): %s" % line)
            ok = "clean" in line and not game_pids()

    root = diag.game_root()
    status = subprocess.run(["git", "-C", str(root), "status", "--short", "--", "UserData", "ReplayData"], capture_output=True, text=True).stdout.strip()
    print("game folder UserData/ReplayData: %s" % ("clean" if not status else "changed:\n" + status))
    if status and a.revert and not a.dry_run:
        subprocess.run(["git", "-C", str(root), "checkout", "--", "UserData", "ReplayData"], capture_output=True)
        subprocess.run(["git", "-C", str(root), "clean", "-fdq", "UserData", "ReplayData"], capture_output=True)
        print("  reverted")
    elif status and not a.revert:
        print("  (use --revert to put it back)")
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
