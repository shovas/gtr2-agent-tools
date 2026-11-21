r"""Mean lap time of the last lap sessions in scripts/gtr2_ui/runs/campaign.jsonl, for comparing a driver setting at a push below the cliff.

A session near the push limit passes or fails on a handful of unclean laps (noise); the mean of the clean laps' times over a fixed range of laps shows a speed difference
directly. Prints per session: laps, clean count, best clean, and the mean and median of the clean laps within --from..--to (timed lap numbers, 1 = first).

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-session-stats.py [-n 3] [--from 2] [--to 8]

Standard library only.
"""
import argparse
import json
import statistics
from pathlib import Path

CAMP = Path(__file__).resolve().parent / "gtr2_ui" / "runs" / "campaign.jsonl"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("-n", type=int, default=3, help="how many of the newest sessions")
    ap.add_argument("--from", dest="lo", type=int, default=2, help="first timed lap number to include (1 = the first timed lap)")
    ap.add_argument("--to", dest="hi", type=int, default=8)
    a = ap.parse_args()
    rows = [json.loads(l) for l in CAMP.read_text(encoding="utf-8").splitlines() if l.strip()][-a.n:]
    for r in rows:
        laps = r.get("laps") or []
        sel = [l for i, l in enumerate(laps, 1) if a.lo <= i <= a.hi and l.get("clean")]
        times = [l["time"] for l in sel]
        clean = sum(1 for l in laps if l.get("clean"))
        print("%d laps, %d clean, best clean %s | laps %d-%d: %d clean, mean %s s, median %s s" % (
            len(laps), clean, r.get("best_clean"), a.lo, a.hi, len(times),
            ("%.2f" % statistics.mean(times)) if times else "-", ("%.2f" % statistics.median(times)) if times else "-"))


if __name__ == "__main__":
    main()
