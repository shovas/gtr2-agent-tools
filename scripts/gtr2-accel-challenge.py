"""Run Driving School's standing-start acceleration challenge (Basics - Acceleration, Level 1) with scripted keys. Uses only the standard library today (adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md).

Purpose: complete a challenge so Driving School's progress write can be checked (where does it land: this install or Documents\\GTR2?).
Usage:   python -I scripts\\gtr2-accel-challenge.py [--run 16] [--shift-rpm 7300] [--max-gear 4] [--dry-run]
Start it right after pressing ATTEMPT (or "Try again" in the pause menu). It selects 1st gear during the countdown, waits a fixed
--go-delay (3.8 s after its own start, calibrated from screenshots: GO is when the TIME LEFT timer starts), then holds the throttle (A) for
--run seconds, shifts up (Alt) on engine rpm from the shared-memory telemetry, and keeps the heading with short comma/period pulses.
Launching before GO fails the challenge immediately, so nothing is sent until the text is seen. Keys only go to the foreground
window if its title starts with "GTR2".
"""
import argparse
import math
import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import telemetry  # noqa: E402
import trackmap  # noqa: E402

user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
user32.SetProcessDPIAware()
SC = {"a": 0x1E, "q": 0x10, "comma": 0x33, "period": 0x34, "alt": 0x38, "ralt": (0x38, True)}
KEYUP, EXT, SCAN = 0x2, 0x1, 0x8


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


state = {"run": True}


def front_title():
    buf = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(user32.GetForegroundWindow(), buf, 64)
    return buf.value


def key(name, down):
    if not front_title().startswith("GTR2"):
        state["run"] = False
        return
    code = SC[name]
    ext = False
    if isinstance(code, tuple):
        code, ext = code
    flags = SCAN | (EXT if ext else 0) | (0 if down else KEYUP)
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(0, code, flags, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def tap(name, hold=0.08):
    key(name, True); time.sleep(hold); key(name, False); time.sleep(hold)


def hold_key(name, hold):
    """Press a key for `hold` seconds, then release and wait 0.03 s (steering pulses whose length scales with the error)."""
    key(name, True); time.sleep(hold); key(name, False); time.sleep(0.03)


def load_ghost(path):
    """The instructor's recorded line from a Driving School .dsi (gzip). Records are 63 bytes, each marked by
    01 00 00 34 00 20 00 40, with the car position (x, y, z; float32 little endian) at +35, +39, +43. 20 Hz.
    Returns the (x, z) points in order. Found by decoding Anderstorp A1_Level 4 (start x -251.2, goal x 210)."""
    import gzip
    import struct
    data = gzip.open(path).read()
    mark = b"\x01\x00\x00\x34\x00\x20\x00\x40"
    pts, i = [], data.find(mark)
    while i >= 0:
        x, z = struct.unpack_from("<f", data, i + 35)[0], struct.unpack_from("<f", data, i + 43)[0]
        pts.append((x, z))
        i = data.find(mark, i + 1)
    return pts


def ghost_target(pts, x, z, near, look):
    """Pure pursuit on the ghost line: the index of the point nearest the car (searched near `near`) and the point `look` m ahead."""
    n = len(pts)
    rng = range(n) if near is None else [(near + k) % n for k in range(-5, 40)]
    k = min(rng, key=lambda j: (pts[j][0] - x) ** 2 + (pts[j][1] - z) ** 2)
    j, run = k, 0.0
    while run < look and j + 1 < n:
        run += math.hypot(pts[j + 1][0] - pts[j][0], pts[j + 1][1] - pts[j][1])
        j += 1
    return k, pts[j]


def window_origin():
    h = user32.FindWindowW(None, "GTR2")
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y


def click_client(ox, oy, x, y):
    """Move to a client position, hover 30 ms, press, hold 10 ms, release, then keep the mouse there 30 ms.
    These are measured timings (buttons act on release). Earlier this used 0.4 s hover and 0.15 s hold."""
    user32.SetCursorPos(ox + x, oy + y)
    time.sleep(0.01)
    user32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.01)
    user32.mouse_event(4, 0, 0, 0, 0)
    time.sleep(0.01)


def go_text_visible(ox, oy):
    """The TIME LEFT label (white text, top left of the 1280x720 client, around x 287-487, y 246-264) is on screen."""
    # one BitBlt of the label region into a memory bitmap, then one GetDIBits (GetPixel on the screen takes ms per call)
    x0, y0, w, h = ox + 285, oy + 240, 205, 30
    sdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, sdc, x0, y0, 0x00CC0020)       # SRCCOPY
    bi = (ctypes.c_uint32 * 10)(40, w, ctypes.c_uint32(-h & 0xFFFFFFFF).value, (32 << 16) | 1, 0, 0, 0, 0, 0, 0)   # top-down 32 bit
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, bi, 0)
    gdi32.SelectObject(mdc, old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mdc); user32.ReleaseDC(0, sdc)
    white = 0
    for i in range(0, w * h * 4, 4):
        b, g, r = buf[i], buf[i + 1], buf[i + 2]
        if r > 150 and g > 150 and b > 150 and max(r, g, b) - min(r, g, b) < 40:   # light grey/white text, any lighting
            white += 1
    return white


def main():
    script_start = time.time()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", type=float, default=16.0, help="seconds of throttle after GO")
    ap.add_argument("--shift-rpm", type=float, default=7300.0)
    ap.add_argument("--max-gear", type=int, default=4)
    ap.add_argument("--steer-gain", type=float, default=3.0, help="degrees of heading error before a steering pulse")
    ap.add_argument("--go-delay", type=float, default=3.8, help="seconds after this script starts to launch (the timer starts about 4.0 s after Try again/ATTEMPT)")
    ap.add_argument("--click-attempt", action="store_true", help="press ATTEMPT (client 1173,620) from this script and time GO from that click (go-delay is then counted from the click, default 4.2)")
    ap.add_argument("--duty", type=float, default=1.0, help="throttle duty cycle (0-1) while below --duty-below m/s; wet challenges (Levels 4-7) spin the car at full throttle")
    ap.add_argument("--duty-below", type=float, default=25.0, help="m/s under which --duty applies (above it the throttle is held)")
    ap.add_argument("--traction", type=float, default=0.0, help="slip limit (0.1 = 10%%): lift the throttle while the speed implied by rpm exceeds the real speed by more than this (wet levels); 0 = off")
    ap.add_argument("--aiw", default=None, help="steer along this layout's racing line (e.g. GameData\\Locations\\Anderstorp\\3Anderstorp.AIW) instead of holding the start heading; needed on wet levels where the road bends")
    ap.add_argument("--look", type=float, default=12.0, help="pure-pursuit look-ahead distance in metres (with --aiw or --ghost)")
    ap.add_argument("--ghost", default=None, help="steer along the instructor's recorded line from this Driving School .dsi (e.g. GameData\\DrivingSchool\\Anderstorp\\A1_Level 4.dsi); the wet reset happens when the car is about 4.5 m off it")
    ap.add_argument("--dry-run", action="store_true", help="only read telemetry and the GO detector, press nothing")
    args = ap.parse_args()
    track = trackmap.Track(args.aiw) if args.aiw else None
    ghost = load_ghost(args.ghost) if args.ghost else None
    if ghost:
        print("ghost line: %d points from %s" % (len(ghost), args.ghost), flush=True)
    tm = telemetry.Telemetry()
    first = tm.read()
    if first is None:
        sys.exit("no telemetry")
    ox, oy = window_origin()
    print("car '%s' on '%s'; gear %d rpm %.0f speed %.1f; window origin %d,%d; GO text pixels now: %d" % (
        first["vehicle"], first["track"], first["gear"], first["rpm"], first["speed"], ox, oy, go_text_visible(ox, oy)))
    if args.dry_run:
        return
    if not front_title().startswith("GTR2"):
        sys.exit("the game window is not in front")
    press_time = None
    if args.click_attempt:
        click_client(ox, oy, 1173, 620)
        press_time = time.time()             # the button acts on release, which has just happened
        # the car is placed on the grid about 2.4 s after ATTEMPT; until then the gear reads the previous attempt's 1st gear,
        # so the gear check below would skip selecting it and the car would stay in neutral. Wait for the grid position.
        wait_t = time.time()
        while time.time() - wait_t < 6.0:
            p = tm.read()["pos"]
            if abs(p[0] + 251.2) < 2.0 and abs(p[2] - 138.4) < 2.0:
                break
            time.sleep(0.05)
        args.go_delay = args.go_delay if args.go_delay != 3.8 else 4.2
    yaw0 = first["yaw"]
    # 1st gear during the countdown (Alt = shift up, with the clutch Q held), only if not there yet
    # the engine is off after Return to Garage and starts about 1 s after GO; shifts do nothing before that
    eng = time.time()
    while time.time() - eng < 6.0 and tm.read()["rpm"] < 1000:
        time.sleep(0.05)
    for _ in range(6):
        if tm.read()["gear"] == 1:
            break
        key("q", True); time.sleep(0.25); tap("alt", 0.12); time.sleep(0.15); key("q", False); time.sleep(0.3)
    print("gear %d selected; waiting for GO" % tm.read()["gear"], flush=True)
    # The pixel/brightness detectors I tried were unreliable (the label sits on bright sky, GetPixel is slow). Calibrated from a
    # screenshot burst: the TIME LEFT timer starts (15.0) about 4.0 s after Try again/ATTEMPT is pressed, and this script starts about
    # 0.4 s after that key press, so launching --go-delay seconds after the script's own start (default 3.8) lands at GO.
    wait = args.go_delay - (time.time() - (press_time if press_time else script_start))
    print("waiting %.2f s for GO (fixed delay)" % max(0.0, wait), flush=True)
    if wait > 0:
        time.sleep(wait)
    if not state["run"]:
        sys.exit("lost the game window focus: not launching")
    t0 = time.time()
    go = time.time()
    print("throttle on %.2f s after the script started" % (go - script_start), flush=True)
    if args.duty >= 0.99 and args.traction <= 0:
        key("a", True)

    chain = track.main if track else None
    near = [None]

    def steer():
        while state["run"] and time.time() - go < args.run:
            t = tm.read()
            if ghost:
                # the instructor's line (the wet reset is triggered when the car is about 4.5 m off it)
                k, (gx, gz) = ghost_target(ghost, t["pos"][0], t["pos"][2], near[0], args.look)
                near[0] = k
                want = trackmap.Track.yaw_of(gx - t["pos"][0], gz - t["pos"][2])
                err = (t["yaw"] - want + 180) % 360 - 180
            elif track:
                # pure pursuit on the racing line: aim at the point --look metres ahead of the nearest waypoint
                k = track.nearest(chain, t["pos"][0], t["pos"][2], near=near[0], window=40)
                near[0] = k
                tgt = track.ahead(chain, k, args.look)
                want = trackmap.Track.yaw_of(tgt.x - t["pos"][0], tgt.z - t["pos"][2])
                err = (t["yaw"] - want + 180) % 360 - 180
            else:
                err = (t["yaw"] - yaw0 + 180) % 360 - 180
            if err > args.steer_gain:
                if track or ghost:   # longer pulses for bigger errors: 0.05 s taps were too weak at 30 m/s (wet run drifted off the line)
                    hold_key("comma", min(0.3, 0.05 + 0.01 * err))
                else:
                    tap("comma", 0.05)       # heading drifted right of the start heading: steer left
            elif err < -args.steer_gain:
                if track or ghost:
                    hold_key("period", min(0.3, 0.05 + 0.01 * -err))
                else:
                    tap("period", 0.05)
            else:
                time.sleep(0.03)
    th = threading.Thread(target=steer); th.start()
    last = 0.0
    a_down = args.duty >= 0.99 and args.traction <= 0
    next_toggle = 0.0
    RATIO = {1: 18.5 / 7311.0, 2: 31.0 / 7319.0, 3: 42.2 / 7304.0, 4: 53.0 / 7300.0}   # m/s per rpm, from the dry runs (shift points)
    while state["run"] and time.time() - go < args.run:
        t = tm.read()
        if args.traction > 0:
            g = t["gear"]
            if g in RATIO and t["speed"] < args.duty_below:
                implied = t["rpm"] * RATIO[g]
                slip = (implied - t["speed"]) / max(implied, 1.0)
                want_down = slip < args.traction or t["speed"] < 1.5 and t["rpm"] < 5500
            else:
                want_down = True
            if want_down and not a_down:
                key("a", True); a_down = True
            elif not want_down and a_down:
                key("a", False); a_down = False
        elif args.duty < 0.99:
            # pulse the throttle: duty of every 0.2 s period while slow, held down above --duty-below
            now = time.time()
            if t["speed"] >= args.duty_below:
                if not a_down:
                    key("a", True); a_down = True
            elif now >= next_toggle:
                if a_down:
                    key("a", False); a_down = False; next_toggle = now + 0.2 * (1 - args.duty)
                else:
                    key("a", True); a_down = True; next_toggle = now + 0.2 * args.duty
        # rpm spikes while the car is still standing (first run: shifted at 0.2 m/s and lost the launch), so also require speed
        if t["rpm"] > args.shift_rpm and t["gear"] < args.max_gear and time.time() - last > 0.6 and t["speed"] > 11.0 * t["gear"]:
            last = time.time(); tap("alt", 0.10)
            print("t=%5.2f shift to %d at %.0f rpm, %.1f m/s" % (time.time() - go, t["gear"] + 1, t["rpm"], t["speed"]), flush=True)
        time.sleep(0.02)
    key("a", False)
    state["run"] = False
    th.join(timeout=3)
    t = tm.read()
    print("done: speed %.1f m/s, gear %d, travelled to x=%.0f z=%.0f" % (t["speed"], t["gear"], t["pos"][0], t["pos"][2]))


if __name__ == "__main__":
    main()
