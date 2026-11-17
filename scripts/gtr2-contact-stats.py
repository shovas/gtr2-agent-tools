r"""Summarise the contacts the lap runner measured (jolts of the car on kerbs, rumble strips, grass, walls): per surface under the wheels, how
many, and the size of the jolt (total, vertical, speed). The lap runner records every jolt above --contact-min in the result's `contacts`
(lap_results.jsonl); this reads them back so the hit limits can be set from measurements, per surface, instead of guessed.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-contact-stats.py [--results scripts\gtr2_ui\runs\lap_results.jsonl] [--layout 4Imol] [--car maserati]
Standard library only.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KERB = ("BRICK", "RMBL", "RMBB", "CURB", "KERB")
SOFT = ("GRAS", "GRASS", "DIRT", "SAND", "GRAV", "GRVL", "FLDGR", "MUD")


def surface_class(surfaces):
    s = [x.upper() for x in surfaces]
    if any(any(k in x for k in KERB) for x in s):
        return "kerb"
    if any(any(k in x for k in SOFT) for x in s):
        return "soft/off"
    return "road only"


def pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--results", default=str(ROOT / "gtr2_ui" / "runs" / "lap_results.jsonl"))
    ap.add_argument("--layout", default="")
    ap.add_argument("--car", default="")
    ap.add_argument("--last", type=int, default=0, help="only the last N result lines")
    a = ap.parse_args()
    lines = [l for l in Path(a.results).read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.last:
        lines = lines[-a.last:]
    groups = {}
    runs = 0
    for l in lines:
        try:
            r = json.loads(l)
        except ValueError:
            continue
        if a.layout.lower() not in str(r.get("layout", "")).lower() or a.car.lower() not in str(r.get("car", "")).lower():
            continue
        cs = r.get("contacts") or (r.get("result") or {}).get("contacts")
        if not cs:
            continue
        runs += 1
        for c in cs:
            key = (surface_class(c.get("surfaces", [])), c.get("kind", "?"))
            groups.setdefault(key, []).append(c)
    if not groups:
        print("no recorded contacts (run laps with a runner that records `contacts`)")
        return 1
    print("%d runs" % runs)
    print("%-10s %-7s %5s | %-22s | %-22s | %s" % ("surface", "kind", "n", "total m/s^2 med/p90/max", "vertical med/p90/max", "speed med"))
    for (cls, kind), cs in sorted(groups.items()):
        t = [c["a"] for c in cs]
        v = [c.get("vert", 0.0) for c in cs]
        sp = [c.get("speed", 0.0) for c in cs]
        print("%-10s %-7s %5d | %6.1f %6.1f %6.1f     | %6.1f %6.1f %6.1f     | %.0f" % (cls, kind, len(cs), statistics.median(t), pct(t, 0.9), max(t), statistics.median(v), pct(v, 0.9), max(v), statistics.median(sp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
