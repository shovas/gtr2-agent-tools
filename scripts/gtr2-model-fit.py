r"""Fit a single-track (bicycle) car model to a recorded --sig-log session by simulation error (step 1 of the model-based follower proposal in docs/driving-theory.md).

Purpose: replay the logged steering command and speed through the model over short windows (start state from the log) and compare the model's yaw rate and
sideslip with what the game logged; a random search with shrinking steps finds the parameters (steering gain and its speed fall-off, steering lag, tyre grip
and stiffness front and rear). Needs numpy (pinned). No game needed. The data are 8 samples a second, so the windows are short and the loss is the
mean squared error of yaw rate (deg/s) and sideslip (deg) over each window.

Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2-model-fit.py scripts\gtr2_ui\runs\signals_<stamp>.csv [--window 24] [--evals 4000] [--laps 1-10]
Example: scripts\.venv\Scripts\python.exe -I scripts\gtr2-model-fit.py scripts\gtr2_ui\runs\signals_20261124_113809.csv
Prints the fitted parameters, the loss against the do-nothing baseline (zero steering response) and the share of the yaw-rate variance explained.
"""
import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np

HCG = 0.245
M, IZ, L, WF = 1290.0, 1230.0, 2.70, 0.44      # MC12: mass with a little fuel, yaw inertia (.hdc), wheelbase, front weight share
A, B = L * (1.0 - WF), L * WF                  # centre of gravity to the front and to the rear axle
G = 9.81
NAMES = ["ks", "v0", "tau", "mu_f", "mu_r", "cf", "cr", "bmax", "rb"]
START = np.array([0.10, 40.0, 0.15, 1.6, 1.8, 14.0, 14.0, 16.0, 0.35])
LOW = np.array([0.02, 10.0, 0.02, 0.8, 0.8, 4.0, 4.0, 8.0, 0.15])
HIGH = np.array([0.60, 200.0, 0.60, 3.5, 3.5, 80.0, 80.0, 24.0, 0.70])


KEEP = ("t", "speed", "sideslip", "yawrate", "steer", "brake", "lap")


def load(path, laps):
    """one or several (comma separated) --sig-log files, joined (windows never cross a file boundary: the time jumps)."""
    parts = []
    for one in path.split(","):
        rows = [r for r in csv.reader(open(one)) if r and not r[0].startswith("#")]
        h = rows[0]
        if "steer" not in h or len(rows) < 100:      # older logs have no steering command column
            continue
        parts.append({k: np.array([float(r[i]) for r in rows[1:]]) for i, k in enumerate(h) if k in KEEP})
    d = {k: np.concatenate([q[k] + (1e5 * i if k == "t" else 0.0) for i, q in enumerate(parts)]) for k in parts[0]}
    keep = (d["lap"] >= laps[0]) & (d["lap"] <= laps[1])
    return {k: v[keep] for k, v in d.items()}


def windows(d, n):
    """index arrays of windows of n samples: moving (speed 15 to 70 m/s) and no gaps in time."""
    out = []
    t, v = d["t"], d["speed"]
    for s in range(0, len(t) - n, n // 2):
        e = s + n
        if t[e - 1] - t[s] > (n - 1) * 0.13 + 0.05:
            continue
        if v[s:e].min() < 15.0 or v[s:e].max() > 70.0:
            continue
        out.append(s)
    return np.array(out)


def simulate(p, d, starts, n, sgn_steer, sgn_beta):
    ks, v0, tau, mu_f, mu_r, cf, cr, bmax, rb = p
    t = d["t"]
    idx = starts[:, None] + np.arange(n)[None, :]
    T = t[idx] - t[idx][:, :1]
    V = d["speed"][idx]
    BR = d["brake"][idx]
    AX = np.gradient(V, 0.12, axis=1)      # longitudinal acceleration from the logged speed (m/s^2, negative when braking)
    S = sgn_steer * d["steer"][idx]
    r = np.radians(d["yawrate"][starts]) * 1.0
    beta = np.radians(d["sideslip"][starts]) * sgn_beta
    v = V[:, 0]
    delta = ks / (1.0 + (v / v0) ** 2) * S[:, 0]
    dt = 0.02
    steps = int(round(T[:, -1].max() / dt)) + 1
    r_out = np.zeros((len(starts), steps))
    b_out = np.zeros_like(r_out)
    for k in range(steps):
        tk = k * dt
        # linear interpolation of the logged inputs at time tk
        j = np.minimum((tk / 0.12).astype(int) if np.ndim(tk) else int(tk / 0.12), n - 2)
        frac = (tk - j * 0.12) / 0.12
        vk = V[:, j] * (1 - frac) + V[:, j + 1] * frac
        sk = S[:, j] * (1 - frac) + S[:, j + 1] * frac
        axk = AX[:, j] * (1 - frac) + AX[:, j + 1] * frac
        brk = BR[:, j] * (1 - frac) + BR[:, j + 1] * frac
        target = ks / (1.0 + (vk / v0) ** 2) * sk
        delta += (target - delta) * (dt / tau)
        vk = np.maximum(vk, 5.0)
        af = delta - (beta + A * r / vk)
        ar = -(beta - B * r / vk)
        shift = np.where(brk > 0.02, -M * bmax * brk, M * axk) * HCG / L                # load moves to the front when braking (ax < 0), to the rear when accelerating
        fzf = np.maximum(M * G * (1 - WF) * (1 + 0.0004 * vk * vk) - shift, 100.0)
        fzr = np.maximum(M * G * WF * (1 + 0.0004 * vk * vk) + shift, 100.0)
        # friction circle: the share of the grip the braking or the drive uses is not left for cornering
        fb = -M * bmax * brk                       # brake force from the pedal (negative), split front and rear by the brake bias
        fxf = np.where(brk > 0.02, (1.0 - rb) * fb, 0.0)
        fxr = np.where(brk > 0.02, rb * fb, np.maximum(M * axk, 0.0))
        cf_ = np.sqrt(np.maximum(0.05, 1.0 - (fxf / (mu_f * fzf)) ** 2))
        cr_ = np.sqrt(np.maximum(0.05, 1.0 - (fxr / (mu_r * fzr)) ** 2))
        fyf = mu_f * fzf * cf_ * np.sin(1.3 * np.arctan(cf * af))
        fyr = mu_r * fzr * cr_ * np.sin(1.3 * np.arctan(cr * ar))
        rdot = (A * fyf * np.cos(delta) - B * fyr) / IZ
        bdot = (fyf + fyr) / (M * vk) - r
        r += rdot * dt
        beta += bdot * dt
        r_out[:, k] = r
        b_out[:, k] = beta
    # sample the model at the log's time stamps
    ri = np.zeros((len(starts), n))
    bi = np.zeros((len(starts), n))
    for c in range(n):
        k = min(int(round(c * 0.12 / dt)), steps - 1)
        ri[:, c] = np.degrees(r_out[:, k])
        bi[:, c] = np.degrees(b_out[:, k]) * sgn_beta
    return ri, bi


SLIDE_W = [1.0]


def loss(p, d, starts, n, sgn_steer, sgn_beta):
    ri, bi = simulate(p, d, starts, n, sgn_steer, sgn_beta)
    idx = starts[:, None] + np.arange(n)[None, :]
    er = ri - d["yawrate"][idx]
    eb = bi - d["sideslip"][idx]
    w = np.where(np.abs(d["sideslip"][idx]).max(axis=1) > 6.0, SLIDE_W[0], 1.0)[:, None]
    return float(np.sum(w * (er[:, 3:] ** 2 + 4.0 * eb[:, 3:] ** 2)) / np.sum(w * np.ones_like(er[:, 3:]))), er, eb, idx


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("log")
    ap.add_argument("--window", type=int, default=24, help="samples per window (0.12 s each)")
    ap.add_argument("--evals", type=int, default=4000)
    ap.add_argument("--laps", default="1-10")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--slide-weight", type=float, default=1.0, help="weight of the windows where the car slides (sideslip over 6 deg): grip limits show only there")
    ap.add_argument("--check", default="", help="a second --sig-log session to score the fitted model on (hold-out)")
    a = ap.parse_args()
    SLIDE_W[0] = a.slide_weight
    lo, hi = (int(x) for x in a.laps.split("-"))
    d = load(a.log, (lo, hi))
    n = a.window
    starts = windows(d, n)
    print("%d windows of %d samples" % (len(starts), n))
    if len(starts) < 20:
        sys.exit("too few windows")
    rng = np.random.default_rng(a.seed)
    # which signs
    best = None
    for ss in (1.0, -1.0):
        for sb in (1.0, -1.0):
            l0 = loss(START, d, starts, n, ss, sb)[0]
            if best is None or l0 < best[0]:
                best = (l0, ss, sb)
    _, ss, sb = best
    print("signs: steer %+d, sideslip %+d" % (ss, sb))
    p = START.copy()
    cur = loss(p, d, starts, n, ss, sb)[0]
    # baseline: the model predicts the logged state at the window start for the whole window (persistence)
    idx = starts[:, None] + np.arange(n)[None, :]
    base_r = np.mean((d["yawrate"][starts][:, None] - d["yawrate"][idx]) ** 2)
    scale = (HIGH - LOW) * 0.25
    for e in range(a.evals):
        q = np.clip(p + rng.normal(size=len(p)) * scale * (0.1 + 0.9 * (1 - e / a.evals)), LOW, HIGH)
        l = loss(q, d, starts, n, ss, sb)[0]
        if l < cur:
            p, cur = q, l
        if (e + 1) % 1000 == 0:
            print("eval %d loss %.2f" % (e + 1, cur))
    l, er, eb, idx = loss(p, d, starts, n, ss, sb)
    var = np.var(d["yawrate"][idx])
    print("parameters: " + ", ".join("%s %.3f" % (k, v) for k, v in zip(NAMES, p)))
    print("yaw-rate rms error %.2f deg/s (persistence baseline %.2f, signal std %.2f); share of the variance explained %.2f; sideslip rms error %.2f deg"
          % (math.sqrt(np.mean(er[:, 3:] ** 2)), math.sqrt(base_r), math.sqrt(var), 1 - np.mean(er[:, 3:] ** 2) / var, math.sqrt(np.mean(eb[:, 3:] ** 2))))
    if a.check:
        d2 = load(a.check, (lo, hi))
        s2 = windows(d2, n)
        l2, er2, eb2, idx2 = loss(p, d2, s2, n, ss, sb)
        var2 = np.var(d2["yawrate"][idx2])
        print("hold-out %s: %d windows, yaw-rate rms error %.2f deg/s, variance explained %.2f, sideslip rms error %.2f deg"
              % (a.check, len(s2), math.sqrt(np.mean(er2[:, 3:] ** 2)), 1 - np.mean(er2[:, 3:] ** 2) / var2, math.sqrt(np.mean(eb2[:, 3:] ** 2))))


if __name__ == "__main__":
    main()
