r"""A time-optimal racing line for any track, from the track's own geometry and the car's grip and power: nothing scripted per track.

The line is a sideways offset from the AI waypoint line at every waypoint, kept inside the white lines (road width left and right from
the waypoint file, minus a safety margin). An offset set is judged by the lap time of the speed profile the driver's own planner would
hold on it: corner speed from curvature and grip that grows with speed (downforce), braking by a constant deceleration, acceleration
limited by power and drag. The search is coordinate descent on offset knots every few waypoints with a shrinking step, so it
finds out-in-out lines with a late apex by itself. Needs numpy (pinned in scripts/requirements.txt). The result is cached under
scripts/gtr2_driving/line_cache/ (git-ignored), keyed by the layout, its waypoints and the physics numbers.

    optimise(track, Physics(), margin=1.2) -> numpy array of offsets (metres, positive to the road's right, as Track.lateral)
    lap_time(points_xz, physics) -> seconds (estimate, a floor)
"""
import hashlib
import json
import math
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

CACHE = Path(__file__).resolve().parent / "line_cache"


@dataclass
class Physics:
    lat: float = 11.0          # cornering grip at rest, m/s^2
    kk: float = 1.8e-4         # extra cornering grip per (m/s)^2 (downforce)
    decel: float = 13.0        # braking, m/s^2
    power: float = 330000.0    # wheel power, W
    mass: float = 1300.0
    cda: float = 0.75
    acc_cap: float = 9.0       # traction limit on acceleration, m/s^2
    vmax: float = 150.0
    span: float = 12.0         # metres of line over which the planner measures curvature
    slope: float = 0.12        # steepest sideways change of the line, metres per metre of track (about 7 degrees): the follower cannot make faster moves
    rmin: float = 15.0         # tightest radius the line may ask for over about 6 m, metres (penalised)


def lap_time(points, ph, with_profile=False):
    """Estimated lap time (s) of a closed line given as an (n, 2) array of x, z."""
    n = len(points)
    nxt = np.roll(points, -1, axis=0)
    seg = nxt - points
    ds = np.hypot(seg[:, 0], seg[:, 1]) + 1e-9
    tan = seg / ds[:, None]
    m = max(1, int(round(ph.span / ds.mean())))
    tan2 = np.vstack([tan, tan])
    ds2 = np.concatenate([ds, ds])
    cs = np.concatenate([[0.0], np.cumsum(ds2)])
    idx = np.arange(n)
    ta, tb = tan2[idx], tan2[idx + m]
    ang = np.abs(np.arctan2(ta[:, 0] * tb[:, 1] - ta[:, 1] * tb[:, 0], (ta * tb).sum(axis=1)))
    arc = cs[idx + m] - cs[idx]
    curv = ang / np.maximum(arc, 1.0)
    tight = np.abs(np.arctan2(tan[:, 0] * np.roll(tan, -1, axis=0)[:, 1] - tan[:, 1] * np.roll(tan, -1, axis=0)[:, 0], (tan * np.roll(tan, -1, axis=0)).sum(axis=1))) / ds
    pen = float(np.sum(np.maximum(0.0, tight - 1.0 / ph.rmin) * ds)) * 6.0      # seconds of penalty per radian of excess turning
    den = curv - ph.lat * ph.kk
    ok = (curv > 1e-4) & (den > 1e-6)
    vc = np.where(ok, np.sqrt(ph.lat / np.where(ok, den, 1.0)), ph.vmax)
    vc = np.minimum(vc, ph.vmax)
    # braking envelope: v_i^2 = min over j >= i of (vc_j^2 + 2 d (S_j - S_i)), on two laps so it wraps
    s = cs[:2 * n]
    w = np.concatenate([vc, vc]) ** 2 + 2.0 * ph.decel * s
    rev = np.minimum.accumulate(w[::-1])[::-1]
    env = np.sqrt(np.maximum(rev[:n] - 2.0 * ph.decel * s[:n], 1.0))
    # acceleration limited by power and drag, two laps to settle the start
    v = np.empty(n)
    cur = float(env[0])
    half = 0.5 * 1.2 * ph.cda / ph.mass
    envl = env.tolist()
    dsl = ds.tolist()
    for lap in range(2):
        for i in range(n):
            a = ph.power / (ph.mass * max(cur, 5.0)) - half * cur * cur
            a = min(ph.acc_cap, max(a, 0.3))
            cur = min(envl[i], math.sqrt(cur * cur + 2.0 * a * dsl[i - 1]))
            if lap == 1:
                v[i] = cur
    vn = np.roll(v, -1)
    t = float((ds / np.maximum(0.5 * (v + vn), 1.0)).sum())
    t += pen
    return (t, v, ds) if with_profile else t


def geometry(track):
    """The file's own line (undoing any shift already applied), the right-hand unit vectors and the road widths."""
    ch = track.main
    c = np.array([[w.x - w.off * -w.hz, w.z - w.off * w.hx] for w in ch])
    r = np.array([[-w.hz, w.hx] for w in ch])
    left = np.array([w.left for w in ch])
    right = np.array([w.right for w in ch])
    return c, r, left, right


def _knot_offsets(z, n, every):
    k = len(z)
    xk = np.arange(k) * every
    xs = np.arange(n)
    return np.interp(xs, np.append(xk, k * every), np.append(z, z[0]))


def optimise(track, ph=None, margin=1.2, every=6, steps=(3.0, 1.5, 0.75, 0.35), max_sweeps=6, smooth=5, log=print, deadline=None, seed=None):
    ph = ph or Physics()
    c0, r0, left, right = geometry(track)
    n = len(c0)
    # offsets are measured from the line the file gives; limits keep the car's side margin metres inside each white line
    # positive offsets are towards the car's physical left (the lateral() sign) and are limited by the LEFT width (measured: 70 off-road events, scatter 0.96 m against 1.72 m the other way round)
    lo = np.minimum(-(right - margin), 0.0)
    hi = np.maximum(left - margin, 0.0)
    k = n // every + (1 if n % every else 0)
    z = np.zeros(k)
    if seed is not None:      # start from a given line (the game's dry line) instead of the file line; the search refines it with our own physics
        z = np.clip(np.array([seed[min(j * every, n - 1)] for j in range(k)]), lo[np.minimum(np.arange(k) * every, n - 1)], hi[np.minimum(np.arange(k) * every, n - 1)])
    dsm = np.hypot(*(np.roll(c0, -1, axis=0) - c0).T)

    def offsets(zv):
        o = _knot_offsets(zv, n, every)
        if smooth > 1:
            kern = np.ones(smooth) / smooth
            o = np.convolve(np.concatenate([o[-smooth:], o, o[:smooth]]), kern, mode="same")[smooth:-smooth]
        o = np.minimum(np.maximum(o, lo), hi)
        if ph.slope > 0:
            lim = ph.slope * dsm
            for _ in range(2):       # limit the sideways change per waypoint, forwards and backwards round the lap
                for i in range(1, 2 * n):
                    a_, b_ = (i - 1) % n, i % n
                    o[b_] = min(max(o[b_], o[a_] - lim[a_]), o[a_] + lim[a_])
                for i in range(2 * n - 2, -1, -1):
                    a_, b_ = (i + 1) % n, i % n
                    o[b_] = min(max(o[b_], o[a_] - lim[b_]), o[a_] + lim[b_])
            o = np.minimum(np.maximum(o, lo), hi)
        return o

    def score(zv):
        o = offsets(zv)
        return lap_time(c0 + o[:, None] * r0, ph)

    base = score(z)
    best = base
    t0 = time.time()
    for step in steps:
        for sweep in range(max_sweeps):
            improved = 0
            for j in range(k):
                for d in (step, -step):
                    zz = z.copy()
                    zz[j] += d
                    t = score(zz)
                    if t < best - 1e-4:
                        best, z = t, zz
                        improved += 1
                        break
                if deadline and time.time() > deadline:
                    break
            log("step %.2f sweep %d: %d knots moved, estimate %.2f s (file line %.2f s)" % (step, sweep + 1, improved, best, base))
            if improved == 0 or (deadline and time.time() > deadline):
                break
    log("line optimised in %.1f s: %.2f s -> %.2f s" % (time.time() - t0, base, best))
    return offsets(z)


def cache_key(track, ph, margin, seeded=False):
    h = hashlib.sha1()
    h.update(json.dumps(asdict(ph), sort_keys=True).encode())
    h.update(("v2|%.2f|%d|%s|" % (margin, len(track.main), "seed" if seeded else "")).encode())
    for w in track.main[:: max(1, len(track.main) // 40)]:
        h.update(("%.1f,%.1f,%.1f,%.1f;" % (w.x - w.off * -w.hz, w.z - w.off * w.hx, w.left, w.right)).encode())
    return h.hexdigest()[:16]


def cached_offsets(track, aiw_stem, ph=None, margin=1.2, log=print, **kw):
    ph = ph or Physics()
    key = cache_key(track, ph, margin, kw.get("seed") is not None)
    CACHE.mkdir(exist_ok=True)
    f = CACHE / ("%s_%s.json" % (aiw_stem.lower(), key))
    if f.exists():
        try:
            o = np.array(json.loads(f.read_text())["offsets"])
            if len(o) == len(track.main):
                log("racing line from cache %s" % f.name)
                return o
        except Exception:
            pass
    o = optimise(track, ph, margin, log=log, **kw)
    f.write_text(json.dumps({"physics": asdict(ph), "margin": margin, "offsets": [round(float(x), 3) for x in o]}))
    return o


def apply(track, offsets):
    """Move the main chain's waypoints onto the line (x, z and headings); remembers the shift in w.off like Track.smooth_line."""
    ch = track.main
    for w, o in zip(ch, offsets):
        bx, bz = w.x - w.off * -w.hz, w.z - w.off * w.hx      # the file's position
        w.x, w.z = bx + o * -w.hz, bz + o * w.hx
        w.off = float(o)
    n = len(ch)
    for k, w in enumerate(ch):
        nx = ch[(k + 1) % n]
        dx, dz = nx.x - w.x, nx.z - w.z
        d = math.hypot(dx, dz) or 1.0
        w.hx, w.hz = dx / d, dz / d
