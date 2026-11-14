r"""Axis probe: in the cockpit with the car parked, sweep the vJoy steering axis (X) and watch the shared-memory telemetry
for the floats that follow it. Purpose: find out whether the game's per-axis Dead Zone / Sensitivity / Center (PLR `Axis [00, 00] ...`)
change what vJoy input does, and where the steering response is not linear. Standard library only (uses gtr2_driving.vjoy / telemetry).

Run through the lap runner (set GTR2_PROBE_TAG to label the run; GTR2_PROBE_OFFSET picks the telemetry float, default 268 = the steering input after the game's axis processing, -1..1) so the game is started and the car is in the cockpit (it replaces the driver script):
    $env:GTR2_DRIVER_SCRIPT='gtr2-axis-probe.py'; python -I scripts\gtr2-lap-check.py Imola4Imol --input wheel --garage-exit
Output: scripts/gtr2_ui/runs/axis_probe.txt (and stdout). Does not drive: the car stays put.
Options: --steps N (axis values between 0 and 1, default 21), --hold S (seconds per value, default 1.2), --axis X|Z|RX.
"""
import argparse, os, struct, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gtr2_driving.vjoy import VJoy
from gtr2_driving.telemetry import Telemetry

ap = argparse.ArgumentParser()
ap.add_argument("--aiw"); ap.add_argument("--fast", action="store_true"); ap.add_argument("--input")
ap.add_argument("--total"); ap.add_argument("--stop-at-merge"); ap.add_argument("--laps-crossed")
ap.add_argument("--steps", type=int, default=21); ap.add_argument("--hold", type=float, default=1.2); ap.add_argument("--axis", default="X")
a, _ = ap.parse_known_args()
tm = Telemetry()
t0 = time.time()
while tm.raw() is None and time.time() - t0 < 10:
    time.sleep(0.2)
levels = [i / (a.steps - 1) for i in range(a.steps)]
order = [0.5] + levels + [0.5]
rows = []
with VJoy() as vj:
    for v in order:
        vj.axis(a.axis, v)
        time.sleep(a.hold)
        raw = tm.raw()
        rows.append((v, struct.unpack_from("<%df" % (len(raw) // 4), raw, 0)))
n = len(rows[0][1])
xs = [r[0] for r in rows]
out = []
for k in range(n):
    col = [r[1][k] for r in rows]
    if not all(c == c and abs(c) < 1e9 for c in col):
        continue
    lo, hi = min(col), max(col)
    if hi - lo < 1e-4:
        continue
    mx = sum(xs) / len(xs); mc = sum(col) / len(col)
    sxx = sum((x - mx) ** 2 for x in xs); scc = sum((c - mc) ** 2 for c in col)
    sxc = sum((x - mx) * (c - mc) for x, c in zip(xs, col))
    r = sxc / (sxx * scc) ** 0.5 if sxx and scc else 0
    out.append((abs(r), k * 4, lo, hi, col))
out.sort(reverse=True)
lines = ["axis %s steps %d hold %.1f s; candidates by |correlation| (offset, corr, min, max)" % (a.axis, a.steps, a.hold)]
for r, off, lo, hi, col in out[:8]:
    lines.append("offset %d corr %.3f min %.4f max %.4f" % (off, r, lo, hi))
if out:
    r, off, lo, hi, col = out[0]
    lines.append("best offset %d, value per axis fraction:" % off)
    for x, c in zip(xs, col):
        lines.append("  %.3f -> %.5f" % (x, c))
off = int(os.environ.get("GTR2_PROBE_OFFSET", "268"))
k = off // 4
lines.append("TAG %s axis %s offset %d: " % (os.environ.get("GTR2_PROBE_TAG", ""), a.axis, off) + " ".join("%.2f:%.3f" % (r[0], r[1][k]) for r in rows))
text = "\n".join(lines)
print(text)
runs = Path(__file__).resolve().parent / "gtr2_ui" / "runs"
(runs / "axis_probe.txt").write_text(text, encoding="utf-8")
with (runs / "axis_probe_all.txt").open("a", encoding="utf-8") as f:
    f.write(lines[-1] + chr(10))
