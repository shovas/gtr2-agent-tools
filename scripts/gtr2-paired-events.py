#!/usr/bin/env python3
r"""Count track-limit and impact events per driver-option group across the paired A/B records.

Reads every gtr2_ui/runs/paired*.jsonl record that names a signal log, reads the events in that log's header
("events: track limits [(t, s), ...] impacts [(t, a), ...]"), maps each event to its lap in the log, and reports,
per option group: sessions, sessions with a track-limit event, sessions with an impact, laps with any event,
and laps in total. Records without a signal log are listed as "no log" and not counted.

Usage:  scripts\.venv\Scripts\python.exe -I scripts\gtr2-paired-events.py [--runs DIR] [--glob "paired*.jsonl"]
Standard library only.
"""
import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "gtr2_ui" / "runs"
EV = re.compile(r"\((\d+(?:\.\d+)?), [-\d.]+\)")


def header_events(lines):
    head = lines[0] if lines else ""
    tl = impacts = []
    if "track limits" in head:
        part = head.split("track limits", 1)[1].split("impacts", 1)[0]
        tl = [float(t) for t in EV.findall(part)]
    if "impacts" in head:
        impacts = [float(t) for t in EV.findall(head.split("impacts", 1)[1])]
    return tl, impacts


def lap_spans(path):
    lines = [l for l in path.read_text(encoding="utf-8", errors="replace").splitlines() if not l.startswith("#")]
    if len(lines) < 2:
        return [], {}
    cols = lines[0].split(",")
    spans = collections.OrderedDict()
    for ln in lines[1:]:
        parts = ln.split(",")
        if len(parts) != len(cols):
            continue
        r = dict(zip(cols, parts))
        k, t = int(float(r["lap"])), float(r["t"])
        spans.setdefault(k, [t, t])[1] = t
    return lines, spans


def lap_of(spans, t):
    for k, (a, b) in spans.items():
        if a <= t <= b:
            return k
    return None


def analyse(path):
    raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
    head = [l for l in raw if l.startswith("#")][:1]
    lines, spans = lap_spans(path)
    tl, im = header_events(head)
    bad_tl = {lap_of(spans, t) for t in tl} - {None}
    bad_im = {lap_of(spans, t) for t in im} - {None}
    return {"tl_events": len(tl), "impacts": len(im), "tl_laps": bad_tl, "impact_laps": bad_im,
            "laps": len([k for k in spans if k >= 1])}


def main():
    ap = argparse.ArgumentParser(description="Track-limit and impact events per option group across paired records.")
    ap.add_argument("--runs", default=str(RUNS), help="runs folder (default gtr2_ui/runs)")
    ap.add_argument("--glob", default="paired*.jsonl", help="records to read (default paired*.jsonl)")
    a = ap.parse_args()
    runs = Path(a.runs)
    groups = collections.OrderedDict()
    nolog = 0
    for jf in sorted(runs.glob(a.glob)):
        for raw in jf.read_text(encoding="utf-8", errors="replace").splitlines():
            if not raw.strip():
                continue
            r = json.loads(raw)
            sig = r.get("signals")
            if not sig or not (runs / sig).exists():
                nolog += 1
                continue
            res = analyse(runs / sig)
            key = (jf.name, r.get("options", "?"), r.get("arm", "?"))
            g = groups.setdefault(key, {"sessions": 0, "sess_tl": 0, "sess_im": 0, "tl_events": 0, "impacts": 0,
                                        "laps": 0, "laps_tl": 0, "laps_im": 0})
            g["sessions"] += 1
            g["sess_tl"] += 1 if res["tl_events"] else 0
            g["sess_im"] += 1 if res["impacts"] else 0
            g["tl_events"] += res["tl_events"]
            g["impacts"] += res["impacts"]
            g["laps"] += res["laps"]
            g["laps_tl"] += len(res["tl_laps"])
            g["laps_im"] += len(res["impact_laps"])
    print("file | arm | options | sessions | sessions with track-limit | track-limit events | laps with track-limit | sessions with impact | impacts | laps")
    for (f, opts, arm), g in groups.items():
        print("%s | %s | %s | %d | %d | %d | %d | %d | %d | %d" % (f, arm, opts[:48], g["sessions"], g["sess_tl"], g["tl_events"],
                                                                g["laps_tl"], g["sess_im"], g["impacts"], g["laps"]))
    print("records without a signal log (not counted): %d" % nolog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
