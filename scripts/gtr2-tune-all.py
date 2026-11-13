"""Tune every layout with gtr2-tune-lap.py in turn and store each result in gtr2_driving/analog_tuned.json.

Purpose: unattended lap-time tuning of the analog driver across all layouts. For each layout (skipping those that already have a
gtr2_ui/runs/tune_<layout>.json, so it can be stopped and restarted) it runs the coordinate search with a trial cap, then writes
the best values as that layout's entry (key = AIW file stem, lower case; an existing entry's zones and note are kept). Layouts whose
baseline is not clean are skipped and listed. About 3.5 minutes per trial; leave the PC alone.
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-tune-all.py [--max-trials 7] [--only TEXT,TEXT] [--skip TEXT,TEXT] [--dry-run]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-tune-all.py --max-trials 7 --only Brno,Enna
Log:     gtr2_ui/runs/tune_all.log (one line per layout). Exit 0 when the list is done.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
RUNS = SCRIPTS / "gtr2_ui" / "runs"
TUNED = SCRIPTS / "gtr2_driving" / "analog_tuned.json"
LOG = RUNS / "tune_all.log"


def load_layouts():
    spec = importlib.util.spec_from_file_location("lapcheck", SCRIPTS / "gtr2-lap-check.py")
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS))
    spec.loader.exec_module(m)
    return m.layouts()


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def store(stem, car, data):
    raw = TUNED.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    d = json.loads(raw)
    ent = d.get(stem, {})
    ent.update(car=car, args=" ".join(data["drive_args"]), first_crossing_s=data["first_crossing_s"])
    ent["note"] = "Tuned %s by gtr2-tune-all.py (%d trials, coordinate search; see CLAUDE.md)." % (time.strftime("%Y-%m-%d"), data["trials"])
    d[stem] = ent
    tmp = TUNED.with_suffix(".tmp")
    tmp.write_bytes(json.dumps(d, indent=1).replace("\n", nl).encode("utf-8"))
    tmp.replace(TUNED)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-trials", type=int, default=7)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="4imol", help="comma-separated AIW stems or layout text to skip (default: Imola GP, already tuned)")
    ap.add_argument("--max-offset", type=float, default=7.0, help="passed to the tuner: largest offset from the line (m) a clean trial may have")
    ap.add_argument("--car", default="gt/lamborghini_murcielago")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    only = [t.lower() for t in a.only.split(",") if t]
    skip = [t.lower() for t in a.skip.split(",") if t]
    todo = []
    for venue, trk, aiw in load_layouts():
        key = "%s%s" % (venue, trk)
        if only and not any(t in key.lower() for t in only):
            continue
        if any(t == aiw.stem.lower() or t in key.lower() for t in skip):
            continue
        todo.append((key, aiw))
    log("plan: %d layouts, %d trials each" % (len(todo), a.max_trials))
    if a.dry_run:
        for key, aiw in todo:
            print(key, aiw.stem.lower())
        return 0
    for key, aiw in todo:
        out = RUNS / ("tune_%s.json" % key.lower())
        if out.exists():
            log("%s: already tuned, skipped" % key)
            continue
        t0 = time.time()
        r = subprocess.run([sys.executable, "-I", str(SCRIPTS / "gtr2-tune-lap.py"), key, "--car", a.car, "--max-trials", str(a.max_trials),
                            "--extra=--zones", "--max-offset", str(a.max_offset)], cwd=SCRIPTS.parent, capture_output=True, text=True)
        if r.returncode != 0 or not out.exists():
            log("%s: no tune (exit %d): %s" % (key, r.returncode, (r.stdout.strip().splitlines() or ["?"])[-1][:150]))
            if r.returncode == 2 and "two runs in a row" in r.stdout:
                log("stopping: the runs are not producing results")
                return 2
            continue
        data = json.loads(out.read_text())
        store(aiw.stem.lower(), a.car, data)
        log("%s: best %.1f s after %d trials (%.0f min) %s" % (key, data["first_crossing_s"], data["trials"], (time.time() - t0) / 60, " ".join(data["drive_args"])))
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
