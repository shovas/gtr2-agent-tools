#!/usr/bin/env python3
"""Competition leaderboard from the validated experiment records (first version).

Reads two record sources and writes a markdown table and a JSON file, both regenerated from the raw records on every run:
  - gtr2_ui/runs/paired.jsonl: one line per paired session (controller options, bend spin, bend laps, infrastructure errors).
    A session with an infrastructure error (launch refused, no signal log) is counted as infrastructure and is never evidence against
    the controller.
  - gtr2_ui/runs/lap_results.jsonl: one line per lap check, with the clean flag and per-lap times (clean-lap pace per layout and car).
    These records carry no controller identity yet, so they are reported per layout and car, not per controller.

Per controller (the options string of the paired arm): sessions, bend laps, spins, spin probability per bend lap with a 95 % Wilson
interval and a Beta(1, 1) posterior probability, and the infrastructure failures counted separately. Bend laps within one session are
correlated, so the session count is shown next to the lap count and the Wilson interval uses the lap count only as a rough guide.
Status: provisional when a controller has fewer than eight sessions (the working minimum), validated otherwise.

Usage:
  scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-leaderboard.py                 (writes gtr2_ui/runs/leaderboard.md and leaderboard.json)
  scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-leaderboard.py --min-sessions 8 --print
Standard library only.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "gtr2_ui" / "runs"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def beta_prob_above(k: int, n: int, threshold: float, steps: int = 4000) -> float:
    """P(p > threshold) under a Beta(1 + k, 1 + n - k) posterior, by the midpoint rule on [0, 1]."""
    a, b = 1 + k, 1 + n - k
    lognorm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    total = above = 0.0
    for i in range(steps):
        x = (i + 0.5) / steps
        w = math.exp(lognorm + (a - 1) * math.log(x) + (b - 1) * math.log(1 - x)) / steps
        total += w
        if x > threshold:
            above += w
    return above / total if total else float("nan")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            print("%s line %d: not JSON (%s); skipped" % (path.name, n, e), file=sys.stderr)
    return out


def label(options: str) -> str:
    """Options with any absolute path cut to its file name (no user paths in the shareable markdown)."""
    return " ".join(part.replace("\\", "/").split("/")[-1] if ("\\" in part or "/" in part) else part for part in options.split(" "))


def controllers(paired: list[dict], min_sessions: int) -> list[dict]:
    groups: dict[str, dict] = defaultdict(lambda: {"sessions": 0, "bend_laps": 0, "spins": 0, "infra": 0, "sids": []})
    for r in paired:
        if "outcome" not in r and r.get("check_output"):      # records from before the stall field: read the check's own output
            cp = RUNS / r["check_output"]
            if cp.exists() and any("stopped moving" in ln or "lap not completed" in ln for ln in cp.read_text(encoding="utf-8", errors="replace").splitlines()):
                r = dict(r, outcome="stall")
        g = groups[label(r.get("options", "?"))]
        if r.get("infra") or ("bend_laps" not in r and "error" in r and r.get("outcome") != "stall"):
            g["infra"] += 1
            continue
        if r.get("outcome") == "stall":      # the car stopped before the bend: a driving failure, counted separately, not a spin
            g["stalls"] = g.get("stalls", 0) + 1
            g["sessions"] += 1
            g["bend_laps"] += int(r.get("bend_laps") or 0)
            continue
        if "bend_laps" not in r:
            continue
        g["sessions"] += 1
        g["bend_laps"] += int(r["bend_laps"])
        g["spins"] += 1 if r.get("spin") else 0
        g["sids"].append(r.get("sid") or r.get("signals", "?"))
    rows = []
    for opts, g in groups.items():
        n, k = g["bend_laps"], g["spins"]
        lo, hi = wilson(k, n)
        rows.append({
            "options": opts,
            "sessions": g["sessions"],
            "bend_laps": n,
            "spins": k,
            "spin_per_bend_lap": (k / n) if n else None,
            "wilson95": [round(lo, 4), round(hi, 4)] if n else None,
            "p_spin_gt_10pct": round(beta_prob_above(k, n, 0.10), 4) if n else None,
            "infrastructure_failures": g["infra"],
            "stalls_before_bend": g.get("stalls", 0),
            "status": "validated" if g["sessions"] >= min_sessions else "provisional (%d of %d sessions)" % (g["sessions"], min_sessions),
        })
    rows.sort(key=lambda r: (r["spin_per_bend_lap"] if r["spin_per_bend_lap"] is not None else 9, -r["sessions"]))
    return rows


def clean_pace(results: list[dict]) -> list[dict]:
    """Clean-lap pace per layout and car: best and median clean lap time (seconds), counting the laps of the session_laps lists."""
    by: dict[tuple, list[float]] = defaultdict(list)
    fails: dict[tuple, int] = defaultdict(int)
    for r in results:
        key = (r.get("layout", "?"), r.get("car", "?"))
        laps = (r.get("result") or {}).get("session_laps") or []
        if not laps:
            fails[key] += 1
            continue
        # A lap counts when the lap itself is clean: its flag is set, it has no track-limit event and no impact, and its time is
        # plausible. The session flag is not used: one unclean lap (the warm-up lap, or a later lap) makes the session unclean but
        # not the other laps (the 1:52.98 lap is one of those). A 3.5 s "lap" appeared once, hence the plausible range.
        for lap in laps:
            t = lap.get("time")
            ok = (lap.get("clean") and lap.get("track_limits", 1) == 0 and lap.get("impacts", 1) == 0
                  and isinstance(t, (int, float)) and 60.0 <= float(t) <= 400.0)
            if ok:
                by[key].append(float(t))
            else:
                fails[key] += 1
    rows = []
    for key in sorted(set(by) | set(fails)):
        times = sorted(by.get(key, []))
        med = times[len(times) // 2] if times else None
        rows.append({
            "layout": key[0],
            "car": key[1],
            "clean_laps": len(times),
            "best_clean_s": round(times[0], 2) if times else None,
            "median_clean_s": round(med, 2) if med is not None else None,
            "unclean_or_failed_laps": fails.get(key, 0),
        })
    return rows


def fmt_time(s: float | None) -> str:
    if s is None:
        return "n/a"
    m = int(s // 60)
    return "%d:%04.1f" % (m, s - 60 * m)


def markdown(ctrl: list[dict], pace: list[dict], n_paired: int, n_results: int) -> str:
    lines = ["# Competition leaderboard (generated)", "",
             "Generated by `scripts/gtr2-leaderboard.py` from `gtr2_ui/runs/paired.jsonl` (%d records) and `lap_results.jsonl` (%d records). "
             "Raw records are the source; this file is regenerated, not edited." % (n_paired, n_results), "",
             "## Bend spin, paired sessions (2570 m bend, spin = yaw rate of 120 deg/s or more in the bend box)", "",
             "| controller options | status | sessions | bend laps | spins | spins per bend lap (95 % Wilson) | P(rate > 10 %) | stalls before the bend (driving) | infrastructure failures (not counted) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in ctrl:
        rate = "n/a" if r["spin_per_bend_lap"] is None else "%.0f %% (%.0f to %.0f %%)" % (100 * r["spin_per_bend_lap"], 100 * r["wilson95"][0], 100 * r["wilson95"][1])
        p10 = "n/a" if r["p_spin_gt_10pct"] is None else "%.2f" % r["p_spin_gt_10pct"]
        lines.append("| `%s` | %s | %d | %d | %d | %s | %s | %d | %d |" % (r["options"], r["status"], r["sessions"], r["bend_laps"], r["spins"], rate, p10, r["stalls_before_bend"], r["infrastructure_failures"]))
    lines += ["", "Bend laps within a session are correlated; the session count is the honest sample size. Lap times are not in these records yet, so this table has no pace column.", "",
              "## Clean-lap pace per layout and car (lap check records; no controller identity yet)", "",
              "| layout | car | clean laps | best clean | median clean | unclean or failed laps |", "|---|---|---|---|---|---|"]
    shown = [r for r in pace if r["clean_laps"] > 0]
    for r in shown:
        lines.append("| %s | %s | %d | %s | %s | %d |" % (r["layout"], r["car"], r["clean_laps"], fmt_time(r["best_clean_s"]), fmt_time(r["median_clean_s"]), r["unclean_or_failed_laps"]))
    lines.append("")
    lines.append("Combinations with no clean lap are not listed (%d of %d); their unclean and failed lap counts are in leaderboard.json." % (len(pace) - len(shown), len(pace)))
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the competition leaderboard from the raw records.")
    ap.add_argument("--min-sessions", type=int, default=8, help="sessions per controller before a result counts as validated (default 8)")
    ap.add_argument("--out-dir", default=str(RUNS), help="where leaderboard.md and leaderboard.json go (default gtr2_ui/runs)")
    ap.add_argument("--print", action="store_true", help="also print the markdown")
    a = ap.parse_args()
    paired = load_jsonl(RUNS / "paired.jsonl")
    results = load_jsonl(RUNS / "lap_results.jsonl")
    ctrl = controllers(paired, a.min_sessions)
    pace = clean_pace(results)
    md = markdown(ctrl, pace, len(paired), len(results))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.md").write_text(md, encoding="utf-8")
    (out / "leaderboard.json").write_text(json.dumps({"controllers": ctrl, "clean_pace": pace, "min_sessions": a.min_sessions},
                                                     indent=2), encoding="utf-8")
    if a.print:
        print(md)
    print("wrote %s and %s" % (out / "leaderboard.md", out / "leaderboard.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
