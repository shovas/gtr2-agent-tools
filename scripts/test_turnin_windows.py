#!/usr/bin/env python3
"""Synthetic and boundary tests for the turn-in window rule used in the bend analysis.

A window opens at the first sample with speed >= 25 m/s, brake > 0.3 and |steer| > 0.2, and closes when 1.5 s have passed or |steer|
falls below 0.1, whichever comes first. The yaw peak and the precursor are measured inside the window only.

Run:  python -I scripts\\test_turnin_windows.py     (exit 1 on any failure; standard library only)
"""
import sys


def windows(rows):
    """Return (start, end) index pairs, end exclusive, using the same rule as the analysis."""
    out = []
    i, n = 0, len(rows)
    while i < n:
        q = rows[i]
        if q["speed"] >= 25 and abs(q["steer"]) > 0.2 and q["brake"] > 0.3:
            t0 = q["t"]
            j = i
            while j < n and rows[j]["t"] - t0 <= 1.5 and abs(rows[j]["steer"]) >= 0.1:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def sample(t, speed=30.0, steer=0.0, brake=0.0, yawrate=0.0, front_grip=1.0):
    return dict(t=t, speed=speed, steer=steer, brake=brake, yawrate=yawrate, front_grip=front_grip)


def row_series(dt, values):
    return [sample(round(k * dt, 3), **v) for k, v in enumerate(values)]


CASES = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


@case("no window when speed is below 25 m/s")
def _():
    rows = row_series(0.1, [dict(speed=20, steer=0.5, brake=0.5)] * 5)
    assert windows(rows) == [], windows(rows)


@case("no window without braking (steering only)")
def _():
    rows = row_series(0.1, [dict(speed=40, steer=0.5, brake=0.0)] * 5)
    assert windows(rows) == []


@case("no window at the boundary |steer| = 0.2 exactly (not above)")
def _():
    rows = row_series(0.1, [dict(speed=40, steer=0.2, brake=0.5)] * 5)
    assert windows(rows) == []


@case("window at speed exactly 25 m/s, steer just above 0.2, brake just above 0.3")
def _():
    rows = row_series(0.1, [dict(speed=25.0, steer=0.21, brake=0.31)] + [dict(speed=25, steer=0.21, brake=0.0)] * 3)
    assert windows(rows) == [(0, 4)], windows(rows)


@case("window closes when steering falls below 0.1")
def _():
    vals = [dict(speed=40, steer=0.5, brake=0.5), dict(speed=40, steer=0.4, brake=0.5), dict(speed=40, steer=0.05, brake=0.0),
            dict(speed=40, steer=0.5, brake=0.0)]
    rows = row_series(0.1, vals)
    assert windows(rows) == [(0, 2)], windows(rows)


@case("window closes at the 1.5 s cap even while steering stays above 0.1")
def _():
    vals = [dict(speed=40, steer=0.5, brake=0.5)] + [dict(speed=40, steer=0.3, brake=0.0)] * 30
    rows = row_series(0.1, vals)
    w = windows(rows)
    assert len(w) == 1 and w[0][0] == 0 and rows[w[0][1] - 1]["t"] - rows[0]["t"] <= 1.5, w


@case("two separate windows are found and a window is not restarted inside another")
def _():
    vals = ([dict(speed=40, steer=0.5, brake=0.5)] * 3 + [dict(speed=40, steer=0.0, brake=0.0)] * 3
            + [dict(speed=40, steer=0.5, brake=0.5)] * 3)
    rows = row_series(0.1, vals)
    w = windows(rows)
    assert len(w) == 2, w


@case("precursor boundary: steering 0.95 with grip 0.3 is not below 0.3")
def _():
    rows = [sample(0.0, steer=0.95, front_grip=0.3)]
    assert not (abs(rows[0]["steer"]) >= 0.95 and rows[0]["front_grip"] < 0.3)


@case("rows are ordered by time; a window never spans a time gap longer than the cap")
def _():
    rows = row_series(0.1, [dict(speed=40, steer=0.5, brake=0.5)] * 3)
    rows.append(sample(5.0, speed=40, steer=0.5, brake=0.5))
    w = windows(rows)
    assert all(rows[e - 1]["t"] - rows[s]["t"] <= 1.5 for s, e in w), w


def main():
    failed = 0
    for name, fn in CASES:
        try:
            fn()
            print("ok    " + name)
        except AssertionError as e:
            failed += 1
            print("FAIL  " + name + "  " + str(e))
    print("%d case(s), %d failing" % (len(CASES), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
