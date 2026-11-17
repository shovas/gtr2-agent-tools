r"""Where does a lap lose time? Reads the status lines of a lap log (lap_drive.log: t, waypoint k, speed) for the timed lap, cuts the lap into
sections of lap distance, and compares the time spent in each with the time the offline speed model (racingline.lap_time on the same
line, grip/braking numbers given) says is possible; the sections are listed worst first. Status lines come about every 1.3 s (--every 60),
so run the lap with a smaller --every (--drive-args=--every=10) for finer sections.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-sections.py Imola/4Imol [--log scripts\gtr2_ui\runs\lap_drive.log] [--section 150] [--lat 11 --decel 13]
Needs numpy (pinned); reads the game folder.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "gtr2_driving"))
import numpy as np  # noqa: E402
import racingline  # noqa: E402
import trackmap  # noqa: E402

LINE = re.compile(r"^t=\s*([\d.]+) main k=\s*(\d+) .* v=\s*([\d.]+)->\s*([\d.]+) gear=(-?\d+) lap=(\d+)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--log", default=str(HERE / "gtr2_ui" / "runs" / "lap_drive.log"))
    ap.add_argument("--section", type=float, default=150.0, help="section length, metres of lap distance")
    ap.add_argument("--lat", type=float, default=11.0)
    ap.add_argument("--decel", type=float, default=13.0)
    ap.add_argument("--lap", type=int, default=1, help="the timed lap (the status line's lap number)")
    ap.add_argument("--smooth", type=int, default=25)
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    venue, stem = a.layout.split("/")
    t = trackmap.Track(str(trackmap.ROOT / "GameData" / "Locations" / venue / (stem + ".AIW")))
    t.smooth_line(t.main, a.smooth, 1.8, pin_radius=45.0)
    ch = t.main
    ph = racingline.Physics(lat=a.lat, decel=a.decel)
    t_ideal, vprof, ds = racingline.lap_time(np.array([[w.x, w.z] for w in ch]), ph, with_profile=True)
    dist = np.concatenate([[0.0], np.cumsum(ds)])
    rows = []
    for l in Path(a.log).read_text(errors="replace").splitlines():
        m = LINE.match(l)
        if m and int(m.group(6)) == a.lap:
            rows.append((float(m.group(1)), int(m.group(2)), float(m.group(3)), int(m.group(5))))
    if len(rows) < 10:
        print("no status lines for lap %d in %s" % (a.lap, a.log))
        return 1
    total = float(dist[-1])
    nsec = int(total // a.section) + 1
    # time at each section boundary, by interpolating the logged (distance, time) pairs
    d_log = np.array([dist[min(k, len(dist) - 1)] for _, k, _, _ in rows])
    t_log = np.array([r[0] for r in rows])
    order = np.argsort(d_log)
    d_log, t_log = d_log[order], t_log[order]
    edges = np.arange(0.0, total + a.section, a.section)
    t_at = np.interp(edges, d_log, t_log)
    # model time at the same edges
    vmid = 0.5 * (vprof + np.roll(vprof, -1))
    tm = np.concatenate([[0.0], np.cumsum(ds / np.maximum(vmid, 1.0))])
    tm_at = np.interp(edges, dist, tm)
    out = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        if lo < d_log[0] or hi > d_log[-1]:
            continue
        real = t_at[i + 1] - t_at[i]
        ideal = tm_at[i + 1] - tm_at[i]
        sel = [r for r, d in zip(rows, d_log) if lo <= d < hi]
        vmin = min((r[2] for r in sel), default=0.0)
        vavg = (hi - lo) / max(real, 0.01)
        out.append((real - ideal, lo, hi, real, ideal, vavg, vmin, sel[0][3] if sel else 0))
    print("%s lap %d: logged %.1f s over %.0f m, model on the same line %.1f s" % (a.layout, a.lap, t_log[-1] - t_log[0], d_log[-1] - d_log[0], t_ideal))
    print("%-11s %7s %7s %7s %8s %7s %4s" % ("section m", "real s", "model s", "loss s", "avg m/s", "min m/s", "gear"))
    for loss, lo, hi, real, ideal, vavg, vmin, g in sorted(out, reverse=True)[:a.top]:
        print("%4.0f-%-6.0f %7.2f %7.2f %+7.2f %8.1f %7.1f %4d" % (lo, hi, real, ideal, loss, vavg, vmin, g))
    print("sum of losses over the listed sections: %.1f s; over all: %.1f s" % (sum(o[0] for o in sorted(out, reverse=True)[:a.top]), sum(o[0] for o in out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
