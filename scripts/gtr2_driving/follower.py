r"""Path followers: how the steering follows the racing line. Used by gtr2-drive-lap.py and by the offline simulator (gtr2-follower-sim.py),
so a follower can be tuned in seconds before it drives the game.

Conventions (the game's, measured): yaw increases when turning right; a positive steering command turns right; the line's lateral offset
(Track.lateral) is positive when the car is on its physical left, so a positive offset needs a positive (right) correction.

    pursuit(...)   the proven default: aim at a point look-ahead metres along the line, steer by the heading error to it
    stanley(...)   cross-track and heading error at the car plus curvature feed-forward, through a speed dependent steering gain
Standard library only.
"""
import math

# wheel angle in radians per unit of steering command, measured on the Maserati MC12 with the wheel profile (the game's speed sensitive
# steering): speed in m/s -> gain. Other cars: pass their own table (it can be learned from yaw rate over steering, see the driver).
G_TABLE = ((0.0, 0.17), (15.0, 0.139), (25.0, 0.107), (35.0, 0.092), (45.0, 0.059), (55.0, 0.047), (65.0, 0.050), (90.0, 0.045))


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def steer_gain(speed, table=G_TABLE):
    if speed <= table[0][0]:
        return table[0][1]
    for (s0, g0), (s1, g1) in zip(table, table[1:]):
        if speed <= s1:
            return g0 + (g1 - g0) * (speed - s0) / (s1 - s0)
    return table[-1][1]


def yaw_of(dx, dz):
    return math.degrees(math.atan2(-dx, -dz))


def pursuit_steer(herr, yawrate, steer_gain_deg, damping, live_scale=1.0):
    """The pursuit steering law alone: the heading error to the aim point over a gain, minus a yaw damping term, scaled by the live loop
    gain (1 when off), clipped to the wheel. The driver chooses the aim point and the heading error (target selection, pit and box logic,
    edge guard); this turns that error into the command."""
    return max(-1.0, min(1.0, live_scale * (herr / steer_gain_deg - yawrate / damping)))


def pursuit(track, chain, k, x, z, yaw, speed, yawrate, look_base=5.0, look_slope=1.2, steer_gain_deg=25.0, damping=90.0):
    """The existing follower: heading error to the point look metres ahead, over a gain, minus a yaw damping term."""
    look = look_base + look_slope * speed
    target = track.ahead_point(chain, k, look, x, z)
    want = yaw_of(target.x - x, target.z - z)
    herr = wrap(want - yaw)
    return max(-1.0, min(1.0, herr / steer_gain_deg - yawrate / damping))


def stanley(track, chain, k, x, z, yaw, speed, yawrate, lat, k_cross=1.0, ks=3.0, ff=1.0, preview=0.25, damp=90.0, wheelbase=2.7, table=G_TABLE, gain=None):
    """Steering command from cross-track and heading error at the car plus the curvature feed-forward, through the steering gain."""
    sp = max(speed, 1.0)
    w = chain[k]
    yaw_line = yaw_of(w.hx, w.hz)
    psi_e = math.radians(wrap(yaw_line - yaw))
    e_term = math.atan2(k_cross * lat, sp + ks)
    dff = preview * sp + 4.0
    pa = track.ahead_point(chain, k, dff, x, z)
    kappa = math.radians(wrap(yaw_of(pa.hx, pa.hz) - yaw_line)) / dff
    d_ff = math.atan(wheelbase * kappa) * ff
    g = gain if gain is not None else steer_gain(sp, table)
    w_des = math.degrees(sp * kappa)
    cmd = (d_ff + psi_e + e_term) / max(g, 0.02) - (yawrate - w_des) / damp
    return max(-1.0, min(1.0, cmd))


def designed(track, chain, k, x, z, yaw, speed, yawrate, lat, wn=1.2, zeta=0.9, ff=1.0, preview=0.25, damp=0.0, wheelbase=2.7, table=G_TABLE, gain=None, head_ahead=0.0):
    """Stanley-like follower with gains designed from speed: lateral error e and heading error psi obey
    e'' = -(v a / L) e' - (v^2 b / L) e, so a = 2 zeta wn L / v and b = wn^2 L / v^2 give the closed loop natural frequency wn (rad/s) and
    damping zeta whatever the speed (the plain Stanley gains are far too high at speed once the steering path has a delay)."""
    sp = max(speed, 1.0)
    w = chain[k]
    if head_ahead > 0.0:      # heading of the line head_ahead metres ahead, not the nearest waypoint (which lags at the entry of a bend)
        pw = track.ahead_point(chain, k, head_ahead, x, z)
        yaw_line = yaw_of(pw.hx, pw.hz)
    else:
        yaw_line = yaw_of(w.hx, w.hz)
    psi_e = math.radians(wrap(yaw_line - yaw))
    a = min(2.0 * zeta * wn * wheelbase / max(sp, 3.0), 1.0)
    b = min(wn * wn * wheelbase / (max(sp, 3.0) ** 2), 0.08)
    dff = preview * sp + 4.0
    pa = track.ahead_point(chain, k, dff, x, z)
    kappa = math.radians(wrap(yaw_of(pa.hx, pa.hz) - yaw_line)) / dff
    d_ff = math.atan(wheelbase * kappa) * ff
    g = gain if gain is not None else steer_gain(sp, table)
    w_des = math.degrees(sp * kappa)
    cmd = (d_ff + a * psi_e + b * lat) / max(g, 0.02) - (yawrate - w_des) / damp if damp else (d_ff + a * psi_e + b * lat) / max(g, 0.02)
    return max(-1.0, min(1.0, cmd))
