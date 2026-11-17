r"""Offline simulator for the path followers (gtr2_driving/follower.py): a bicycle-model car with the game's speed-sensitive steering gain,
actuator lag and understeer, driven round a track layout's racing line at the planner's speed. Reports the cross-track error (rms, 95th
percentile, maximum) so a follower can be tuned in seconds instead of 6 minute laps; calibrate the model against the game first
(pure pursuit measured 1.7 to 1.9 m rms, 3.3 to 3.6 m p95 at Imola 4).

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-follower-sim.py Imola/4Imol --follower pursuit
    scripts\.venv\Scripts\python.exe -I scripts\gtr2-follower-sim.py Imola/4Imol --follower stanley --k 1.0 --ff 1.0
    ... --line-opt               drive the optimised racing line (racingline.py) instead of the smoothed one
Needs numpy (pinned); reads the game folder.
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import follower  # noqa: E402
import racingline  # noqa: E402
import trackmap  # noqa: E402


def simulate(track, args, quiet=False):
    ch = track.main
    ph = racingline.Physics(lat=args.lat, decel=args.decel, kk=0.0)
    pts = [[w.x, w.z] for w in ch]
    import numpy as np
    t_lap, vprof, ds = racingline.lap_time(np.array(pts), ph, with_profile=True)
    vprof = np.minimum(vprof, args.vmax)
    n = len(ch)
    # start on the line at waypoint 0, at the planned speed
    x, z = ch[0].x, ch[0].z
    yaw = follower.yaw_of(ch[0].hx, ch[0].hz)
    speed = float(vprof[0])
    delta = 0.0
    queue = []
    prev_yaw = yaw
    k = 0
    dt = 0.02
    t = 0.0
    lats, lap_t = [], 0.0
    travelled = 0.0
    total = float(ds.sum())
    yawrate = 0.0
    steps = 0
    while travelled < total * args.laps and steps < 400000:
        k = track.nearest(ch, x, z, near=k, window=40)
        w = ch[k]
        lat = track.lateral(w, x, z)
        if abs(lat) > 60:
            return None
        if args.follower == "pursuit":
            cmd = follower.pursuit(track, ch, k, x, z, yaw, speed, yawrate, look_slope=args.look)
        elif args.follower == "designed":
            cmd = follower.designed(track, ch, k, x, z, yaw, speed, yawrate, lat, wn=args.wn, zeta=args.zeta, ff=args.ff, preview=args.preview, damp=args.damp if args.use_damp else 0.0)
        else:
            cmd = follower.stanley(track, ch, k, x, z, yaw, speed, yawrate, lat, k_cross=args.k, ks=args.ks, ff=args.ff, preview=args.preview, damp=args.damp)
        # the game's rack and hand: a first order lag, and a speed limit on the command's rate of change
        queue.append(max(-1.0, min(1.0, cmd)))
        cmd_eff = queue.pop(0) if len(queue) > args.delay_steps else queue[0] * 0.0 + (queue[0] if queue else 0.0)
        target_delta = follower.steer_gain(speed) * cmd_eff * args.gain_scale
        delta += (target_delta - delta) * min(1.0, dt / args.lag)
        # bicycle model with understeer: the yaw rate falls as the lateral acceleration nears the grip limit
        omega = speed * math.tan(delta) / args.wheelbase
        ay = abs(speed * omega)
        if ay > args.grip:
            omega *= args.grip / ay
        yaw += math.degrees(omega) * dt
        yawrate = math.degrees(omega)
        h = (-math.sin(math.radians(yaw)), -math.cos(math.radians(yaw)))
        x += speed * h[0] * dt
        z += speed * h[1] * dt
        speed = float(vprof[k])
        travelled += speed * dt
        if speed > 10.0:
            lats.append(abs(lat))
        steps += 1
    lats.sort()
    rms = math.sqrt(sum(l * l for l in lats) / max(len(lats), 1))
    return rms, lats[int(len(lats) * 0.95)] if lats else 0.0, lats[-1] if lats else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("layout")
    ap.add_argument("--follower", choices=("pursuit", "stanley", "designed"), default="stanley")
    ap.add_argument("--k", type=float, default=1.0)
    ap.add_argument("--ks", type=float, default=3.0)
    ap.add_argument("--ff", type=float, default=1.0)
    ap.add_argument("--preview", type=float, default=0.45)
    ap.add_argument("--damp", type=float, default=90.0)
    ap.add_argument("--look", type=float, default=1.2, help="pursuit look-ahead slope")
    ap.add_argument("--wn", type=float, default=1.2, help="designed follower: closed loop natural frequency, rad/s")
    ap.add_argument("--zeta", type=float, default=0.8)
    ap.add_argument("--use-damp", action="store_true", help="designed follower: also the yaw-rate error damping")
    ap.add_argument("--delay", type=float, default=0.15, help="transport delay in the steering path, seconds")
    ap.add_argument("--lag", type=float, default=0.30, help="steering actuator lag, seconds")
    ap.add_argument("--wheelbase", type=float, default=2.7)
    ap.add_argument("--grip", type=float, default=12.0, help="lateral acceleration where the car stops turning more, m/s^2")
    ap.add_argument("--gain-scale", type=float, default=1.0)
    ap.add_argument("--lat", type=float, default=11.0)
    ap.add_argument("--decel", type=float, default=13.0)
    ap.add_argument("--vmax", type=float, default=150.0)
    ap.add_argument("--laps", type=float, default=1.0)
    ap.add_argument("--smooth", type=int, default=25)
    ap.add_argument("--pin", type=float, default=45.0)
    ap.add_argument("--line-opt", action="store_true")
    a = ap.parse_args()
    a.delay_steps = int(round(a.delay / 0.02))
    venue, stem = a.layout.split("/")
    t = trackmap.Track(str(trackmap.ROOT / "GameData" / "Locations" / venue / (stem + ".AIW")))
    if a.line_opt:
        ph = racingline.Physics(lat=a.lat, decel=a.decel, kk=0.0)
        racingline.apply(t, racingline.cached_offsets(t, stem, ph, margin=1.2, log=lambda m: None))
    elif a.smooth:
        t.smooth_line(t.main, a.smooth, 1.8, pin_radius=a.pin)
    r = simulate(t, a)
    if r is None:
        print("the car left the road (more than 60 m from the line)")
        return 1
    print("%s %s: cross-track rms %.2f m, p95 %.2f m, max %.2f m" % (a.layout, a.follower, r[0], r[1], r[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
