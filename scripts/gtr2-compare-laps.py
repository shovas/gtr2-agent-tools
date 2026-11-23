r"""Compare a reference lap (the AI benchmark's telemetry CSV, gtr2-record-telemetry.py) with a hands-free driver lap (signals_*.csv) per stretch of the lap:
the time lost (or gained) against the reference on each stretch, with the mean speed, the minimum speed and the gear of both.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-compare-laps.py REF.csv SIGNALS.csv [--ref-lap 2] [--lap 2] [--bin 100]

Distance along the lap is the integral of the path between logged positions; the two laps are aligned at the start/finish line (the lap counter change).
Standard library only.
"""
import argparse
import math
from pathlib import Path


def load(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    head = lines[1].split(",") if lines[0].startswith("#") else lines[0].split(",")
    body = lines[2:] if lines[0].startswith("#") else lines[1:]
    return [dict(zip(head, map(float, l.split(",")))) for l in body if l.strip()]


def lap_profile(rows, lap):
    v = [r for r in rows if int(r["lap"]) == lap]
    s, dist = 0.0, []
    for i, r in enumerate(v):
        if i:
            s += math.hypot(r["x"] - v[i - 1]["x"], r["z"] - v[i - 1]["z"])
        dist.append(s)
    return v, dist


def stretches(v, dist, b):
    out = {}
    for r, d in zip(v, dist):
        out.setdefault(int(d // b), []).append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ref")
    ap.add_argument("ours")
    ap.add_argument("--ref-lap", type=int, default=2)
    ap.add_argument("--lap", type=int, default=2)
    ap.add_argument("--bin", type=float, default=100.0)
    a = ap.parse_args()
    rv, rd = lap_profile(load(a.ref), a.ref_lap)
    ov, od = lap_profile(load(a.ours), a.lap)
    rs, os_ = stretches(rv, rd, a.bin), stretches(ov, od, a.bin)

    def tm(w):      # time to cover the stretch: sum of ds / v
        t = 0.0
        for p, q in zip(w, w[1:]):
            ds = math.hypot(q["x"] - p["x"], q["z"] - p["z"])
            t += ds / max(0.5 * (p["speed"] + q["speed"]), 1.0)
        return t
    tot_r = tot_o = 0.0
    print("stretch   ref v(mean/min) gear | ours v(mean/min) gear | time lost (s)")
    rows = []
    for k in sorted(set(rs) & set(os_)):
        r, o = rs[k], os_[k]
        if len(r) < 3 or len(o) < 3:
            continue
        # the stretches have almost the same length; scale the reference time to ours by the length ratio
        lr = sum(math.hypot(q["x"] - p["x"], q["z"] - p["z"]) for p, q in zip(r, r[1:])) or 1.0
        lo = sum(math.hypot(q["x"] - p["x"], q["z"] - p["z"]) for p, q in zip(o, o[1:])) or 1.0
        tr, to = tm(r) * lo / lr, tm(o)
        tot_r += tr
        tot_o += to
        rows.append((to - tr, k, r, o))
        print("%5d m   %5.1f / %5.1f  %d   |  %5.1f / %5.1f  %d   | %+5.2f" % (k * a.bin, sum(x["speed"] for x in r) / len(r), min(x["speed"] for x in r), sorted(x["gear"] for x in r)[len(r) // 2],
              sum(x["speed"] for x in o) / len(o), min(x["speed"] for x in o), sorted(x["gear"] for x in o)[len(o) // 2], to - tr))
    print("total over the compared stretches: reference %.1f s, ours %.1f s, difference %+.1f s" % (tot_r, tot_o, tot_o - tot_r))
    print("largest losses:", ", ".join("%d m %+.2f s" % (k * a.bin, d) for d, k, _, _ in sorted(rows, reverse=True)[:8]))


if __name__ == "__main__":
    main()
