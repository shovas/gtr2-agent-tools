"""Drive the car round a lap with the keyboard, steering from the track's own waypoint file and the game's telemetry.

Purpose: complete a timed lap hands-free (Time Trial has no Autopilot), so file saves can be tested. Uses only the standard library today (adding dependencies is fine: pin them in scripts/requirements.txt, see CLAUDE.md).
Usage:   python scripts/gtr2-drive-lap.py --aiw GameData/Locations/Dubai/4Dubai.AIW [--fast] [--laps-crossed 2] [--total 900] [--dry-run]
Example: python scripts/gtr2-drive-lap.py --aiw GameData/Locations/Dubai/4Dubai.AIW --fast

Preconditions (nothing here starts the game or presses menus): the game runs windowed and in front, a Time Trial / Open Practice
session is loaded and DRIVE has been pressed (the car is in its garage box), and the profile binds the DRIVING keys to the keyboard
(A throttle, Z brake, comma/period steer, Alt shift up, Right Alt shift down, Q clutch) with manual gearbox. The plugin
Plugins/rFactorSharedMemoryMap.dll supplies the telemetry (position, heading, speed, gear, rpm, lap counter).

The control loop is the one proven in an earlier harness (pure pursuit on the AIW racing line, corner speeds from the
bends ahead, throttle and brake duty cycles from the speed error, gears from engine rpm), rewritten here without numpy, PIL or its
test harness. Its parameter presets (--fast: 60 m/s top speed, cornering 7.5 m/s^2, braking 6.0, up to 6th gear) were tuned there
for the Donington/Dubai layouts; nothing here has been tuned independently. Keyboard input only goes to the foreground window if it
is the game (title starts with "GTR2"); if the focus is lost the run aborts and releases the keys.
Stops when the lap counter has advanced --laps-crossed times (default 2: start timing, finish the lap), when the car has not moved
for 8 s, or after --total seconds.
"""
import argparse
import ctypes
import json
import math
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import pitzones  # noqa: E402
import telemetry  # noqa: E402
import vjoy  # noqa: E402
import trackmap  # noqa: E402

user32 = ctypes.windll.user32
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 0x1, 0x2, 0x8
SCANCODES = {"a": 0x1E, "z": 0x2C, "q": 0x10, "comma": 0x33, "period": 0x34, "alt": 0x38, "ralt": (0x38, True), "space": 0x39}
OFF_ROAD = ("GRAS", "GRV", "SAND", "DIRT", "MUD", "GRAV")


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


state = {"run": True, "aborted": ""}


def game_in_front():
    h = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(64)
    user32.GetWindowTextW(h, buf, 64)
    return buf.value.startswith("GTR2")


def press_key(name, hold=60):
    """Press and release one key (hardware scancode) while the game window is in front; abort the whole run otherwise."""
    if not state["run"]:
        return
    if not game_in_front():
        state["run"] = False
        state["aborted"] = "the game window lost the focus"
        return
    code = SCANCODES[name]
    ext = False
    if isinstance(code, tuple):
        code, ext = code
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0)
    # Wait `hold` ms after the key-UP as well: every pulse is half down, half up. The
    # controller's duty cycles and steering gains were tuned with that, so a key that is released at once would steer and
    # accelerate twice as hard (first runs here overshot the turn out of the box by 70 degrees).
    for f, wait in ((flags, hold / 1000.0), (flags | KEYEVENTF_KEYUP, hold / 1000.0)):
        i = INPUT(type=1)
        i.u.ki = KEYBDINPUT(0, code, f, 0, None)
        user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
        time.sleep(wait)


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--input", choices=("keyboard", "analog"), default="keyboard",
                    help="keyboard: key pulses (default). analog: vJoy virtual joystick axes (steering X, throttle Z, brake Rx, shifts on "
                         "buttons 1/2); needs the analog profile bindings, see CLAUDE.md")
    ap.add_argument("--analog-steer", type=float, default=0.6, help="analog only: scale the steering command (0.6 passed at Imola; 1.0 and 0.3 failed in the garage box)")
    ap.add_argument("--analog-throttle", type=float, nargs=6, default=[0.6, 0.7, 0.85, 1.0, 1.0, 1.0], metavar="G",
                    help="analog only: throttle ceiling in gears 1 to 6 (full throttle in a low gear spins the car); also eased by "
                         "up to --analog-steer-ease of itself at full steering")
    ap.add_argument("--analog-slew", type=float, default=3.0, help="analog only: top steering speed in full-lock units per second; 0 = no smoothing (the control loop runs at about 12 Hz; a 100 Hz writer ramps between its commands)")
    ap.add_argument("--analog-accel", type=float, default=20.0, help="analog only: steering acceleration limit, units/s^2 (ramp up to speed, ramp down onto the new position)")
    ap.add_argument("--analog-inertia", type=float, default=1.0, help="analog only: steering rack/hand inertia (resists slowing down and reversing: the wheel carries on; 2.0 = twice as heavy, slower response). 0 = use the plain acceleration-limited follower instead of the rack model")
    ap.add_argument("--analog-friction", type=float, default=1.0, help="analog only: steering rack sliding friction, units/s^2 (drains speed while moving)")
    ap.add_argument("--analog-stiction", type=float, default=1.5, help="analog only: steering breakaway friction, units/s^2 (a push smaller than this does not start the wheel moving; resists accelerating from rest)")
    ap.add_argument("--analog-wn", type=float, default=14.0, help="analog only: rack model natural frequency at inertia 1, rad/s (damping ratio 0.9)")
    ap.add_argument("--analog-throttle-model", type=float, nargs=4, default=[0.7, 0.5, 0.8, 20.0], metavar=("INERTIA", "FRICTION", "STICTION", "WN"),
                    help="analog only: throttle pedal, same model as the steering ones (light, springy foot); INERTIA 0 = plain follower")
    ap.add_argument("--analog-brake-model", type=float, nargs=4, default=[1.2, 1.0, 1.5, 18.0], metavar=("INERTIA", "FRICTION", "STICTION", "WN"),
                    help="analog only: brake pedal (heavier and stiffer than the throttle); INERTIA 0 = plain follower")
    ap.add_argument("--analog-pedal-slew", type=float, default=5.0, help="analog only: top throttle/brake speed, units/s; 0 = off")
    ap.add_argument("--analog-pedal-accel", type=float, default=40.0, help="analog only: throttle/brake acceleration limit, units/s^2")
    ap.add_argument("--analog-steer-ease", type=float, default=0.4)
    ap.add_argument("--focus-test", nargs=2, type=float, metavar=("START", "SECONDS"), help="experiment: at START s (once above 25 m/s) open a Notepad window in front of the game for SECONDS, and report the sim speed rate (distance moved / (speed x wall time)) before, during and after")
    ap.add_argument("--lane-margin", type=float, default=5.0, help="metres past the track's XPITOUT gate where the pit lane is taken to end (the pit speed cap and the no-shift rule stop applying there)")
    ap.add_argument("--no-lane-end", action="store_true", help="treat the whole pit chain as pit lane (the older behaviour)")
    ap.add_argument("--zones", action="store_true", help="analog only: apply this layout's slow zones from analog_tuned.json (scale the cornering limit by a factor inside lap-distance ranges where the car ran off the road)")
    ap.add_argument("--tuned", action="store_true", help="analog only: apply this layout's entry in gtr2_driving/analog_tuned.json (limits found by gtr2-tune-lap.py); overrides the same options given on the command line")
    ap.add_argument("--impact-accel", type=float, default=14.0, help="local acceleration (m/s^2) above which a sample counts as an impact (launches reach about 10.5, normal driving 7.5; the wall hits in the garage read 16 and 72)")
    ap.add_argument("--box-speed", type=float, default=2.5, help="speed cap (m/s) while driving straight out of the garage box to its pit-stop point")
    ap.add_argument("--box-exit-dist", type=float, default=4.5, help="start turning onto the pit lane when this close (m) to the box's pit-stop point; the car starts turning later than this by its steering lag")
    ap.add_argument("--box-pick", choices=("nearest", "align", "heading"), default="heading", help="how the car leaves its box: heading (default) = straight along its own heading until inside the pit lane, no pit-stop waypoints used (clean at Imola, Donington, Dubai, Hockenheim, Magny-Cours); nearest / align = straight at the nearest / best-aligned pit-stop waypoint (failed at Donington and Dubai)")
    ap.add_argument("--box-margin", type=float, default=0.7, help="with --box-pick heading: start merging when this many metres inside the pit lane's wide side")
    ap.add_argument("--box-max", type=float, default=14.0, help="with --box-pick heading: never drive straight further than this (m)")
    ap.add_argument("--box-throttle", type=float, default=0.4, help="throttle ceiling while leaving the box and merging onto the pit lane line")
    ap.add_argument("--merge-speed", type=float, default=2.5, help="speed cap (m/s) while turning from the box onto the pit lane line, until the car is lined up (heading within 15 degrees, within 2.5 m of the line)")
    ap.add_argument("--merge-steer", type=float, default=1.0, help="analog only: steering scale during that merge (full lock is needed; the car is slow)")
    ap.add_argument("--no-box-path", action="store_true", help="steer from the start toward the pit lane line, as before (clips the garage wall at Imola); always the case for keyboard input")
    ap.add_argument("--pit-lookahead", type=float, nargs=2, default=[3.0, 0.4], metavar=("BASE", "PER_MS"), help="aim distance while on the pit chain: BASE + PER_MS * speed metres")
    ap.add_argument("--pit-lat-accel", type=float, default=3.0, help="cornering limit (m/s^2) for the planner while on the pit chain: Anderstorp's pit route has a 90 degree bend 5 to 6 m wide that the circuit limit took at 8 to 10 m/s (impact 245 m/s^2)")
    ap.add_argument("--no-pit-join", action="store_true", help="plan speed along the pit lane only (the old behaviour: the planner sees the lane end as a 97 degree bend and slows to about 5 m/s at the exit)")
    ap.add_argument("--trace", type=float, default=0.0, help="print every control loop (steer, yaw, rate, speed, position) for the first N seconds")
    ap.add_argument("--aiw", required=True, help="the track layout's AI waypoint file, e.g. GameData/Locations/Dubai/4Dubai.AIW")
    ap.add_argument("--fast", action="store_true", help="the proven fast preset (60 m/s, 7.5 lateral, 6.0 braking, 6th gear)")
    ap.add_argument("--speed", type=float, default=None, help="top speed m/s (default 6; --fast 60)")
    ap.add_argument("--pit-speed", type=float, default=None, help="pit lane speed m/s (default 8; --fast 16)")
    ap.add_argument("--lat-accel", type=float, default=None, help="cornering limit m/s^2 (default 2; --fast 7.5)")
    ap.add_argument("--decel", type=float, default=None, help="assumed braking m/s^2 (default 3; --fast 6)")
    ap.add_argument("--max-gear", type=int, default=None, help="default 3; --fast 6")
    ap.add_argument("--shift-rpm", type=float, default=None, help="default 6800; --fast 6300")
    ap.add_argument("--down-rpm", type=float, default=None, help="default 2800; --fast 3000")
    ap.add_argument("--lookahead", type=float, nargs=2, default=[5.0, 1.2], metavar=("BASE", "PER_MS"))
    ap.add_argument("--steer-gain", type=float, default=25.0)
    ap.add_argument("--damping", type=float, default=90.0)
    ap.add_argument("--steer-period", type=float, default=0.4)
    ap.add_argument("--guard-deg", type=float, default=18.0)
    ap.add_argument("--guard-span", type=float, default=50.0)
    ap.add_argument("--guard-floor", type=float, default=0.3)
    ap.add_argument("--pit-margin", type=float, default=2.6)
    ap.add_argument("--pit-aim", type=float, default=0.0,
                    help="aim this many metres to one side of the pit-lane line (positive = left, negative = right; clamped to stay inside "
                         "the lane). Time Trial puts a marshal and a car in the pit exit lane; -3 passes on the right.")
    ap.add_argument("--center-gain", type=float, default=0.0)
    ap.add_argument("--tight-radius", type=float, default=0.0)
    ap.add_argument("--tight-speed", type=float, default=7.0)
    ap.add_argument("--laps-crossed", type=int, default=2, help="stop after the lap counter has advanced this many times")
    ap.add_argument("--finish-extra", type=float, default=4.0, help="seconds to keep driving after that, then stop")
    ap.add_argument("--total", type=float, default=900.0, help="give up after this many seconds")
    ap.add_argument("--every", type=int, default=60, help="print a status line every N loops")
    ap.add_argument("--dry-run", action="store_true", help="read the telemetry and the track, print the plan, press no keys")
    ap.add_argument("--no-track-params", action="store_true", help="ignore scripts/gtr2_driving/track_params.json")
    args = ap.parse_args()
    # Per-track settings (gtr2_driving/track_params.json): maps an AIW file stem (lower case) to extra options for a
    # layout whose tight corners need something the others don't. They replace the same options given on the command line and
    # are applied before the --fast/slow preset fills in what is still unset.
    params_file = Path(__file__).resolve().parent / "gtr2_driving" / "track_params.json"
    extra = None if args.no_track_params or not params_file.exists() else json.loads(params_file.read_text()).get(Path(args.aiw).stem.lower())
    if extra:
        ap._option_string_actions["--aiw"].required = False       # re-parsing only the extras must not demand --aiw again
        keep = args.aiw
        ap.parse_known_args(extra.split(), namespace=args)
        args.aiw = keep
        print("track params for %s: %s" % (Path(args.aiw).stem.lower(), extra), flush=True)
    if args.tuned:
        tuned_file = Path(__file__).resolve().parent / "gtr2_driving" / "analog_tuned.json"
        entry = json.loads(tuned_file.read_text()).get(Path(args.aiw).stem.lower()) if tuned_file.exists() else None
        if entry is None:
            sys.exit("no tuned settings for %s in %s" % (Path(args.aiw).stem.lower(), tuned_file.name))
        ap._option_string_actions["--aiw"].required = False
        keep = args.aiw
        ap.parse_known_args(entry["args"].split(), namespace=args)
        args.aiw = keep
        print("tuned settings for %s: %s" % (Path(args.aiw).stem.lower(), entry["args"]), flush=True)
    slow = dict(speed=6.0, pit_speed=8.0, lat_accel=2.0, decel=3.0, max_gear=3, shift_rpm=6800.0, down_rpm=2800.0)
    fast = dict(speed=60.0, pit_speed=16.0, lat_accel=7.5, decel=6.0, max_gear=6, shift_rpm=6300.0, down_rpm=3000.0)
    for name, value in (fast if args.fast else slow).items():
        if getattr(args, name) is None:      # an explicit option always wins over the preset
            setattr(args, name, value)

    STAGE = lambda name: print("STAGE %s epoch=%.3f" % (name, time.time()), flush=True)      # start-up timing: compared with gtr2-lap-check.py's own stamps
    STAGE("script_started")
    track = trackmap.Track(args.aiw)
    tm = telemetry.Telemetry()
    first = tm.read()
    STAGE("telemetry_first_read")
    if first is None:
        sys.exit("no telemetry: is the game running with Plugins/rFactorSharedMemoryMap.dll loaded?")
    print("track '%s', car '%s'; waypoints: main %d, pit %d, lap length %.0f m; position (%.0f, %.0f), lap counter %d" % (
        first["track"], first["vehicle"], len(track.main), len(track.pit), track.lap_length, first["pos"][0], first["pos"][2], first["lap"]))
    # Start on whichever line is nearer: Open Practice starts in the garage box (pit lane), Time Trial puts the car on the main
    # straight shortly before the pit entry, already rolling.
    cand = []
    for ch in (track.pit, track.main):
        if ch:
            kk = track.nearest(ch, first["pos"][0], first["pos"][2])
            cand.append((math.hypot(ch[kk].x - first["pos"][0], ch[kk].z - first["pos"][2]), ch))
    d0, chain0 = min(cand, key=lambda c: c[0])
    print("nearest %s waypoint is %.1f m away" % ("pit-lane" if chain0 is track.pit else "racing-line", d0))
    if d0 > 40:
        sys.exit("the car is %.0f m from this layout's waypoints: wrong --aiw for the loaded track?" % d0)
    if args.dry_run:
        print("dry run: no keys pressed"); return
    if not game_in_front() and args.input == "keyboard":
        sys.exit("the game window is not in front; bring it forward and run again")

    # The pit chain's last waypoint has no successor (placeholder heading), so the speed planner read the join with the racing line as a
    # sharp bend and slowed the car to about 5 m/s just outside the pits. Plan along pit lane + racing line from the join instead.
    # Where the pit lane ends: the layout's .trk lists an xpitout trigger object (a box across the lane at the exit, mesh in the .gtr archive);
    # the pit-chain waypoint nearest its centre, plus a margin, is the end. Past it the pit speed cap and the no-shift rule stop applying:
    # the chain beyond can be a long service road (Anderstorp S: 650 m). No gate found (Hockenheim): the whole chain stays pit lane.
    lane_end_k = None
    if track.pit and not args.no_lane_end:
        try:
            gate = pitzones.pit_gates(args.aiw)["out"]
        except Exception as e:                                  # noqa: BLE001 - a missing or odd archive must not stop a lap
            gate = None
            print("pit exit gate: could not read (%s)" % e, flush=True)
        if gate:
            gk = track.nearest(track.pit, gate[0], gate[1])
            gd = math.hypot(track.pit[gk].x - gate[0], track.pit[gk].z - gate[1])
            if gd <= 15.0:
                lane_end_k, m = gk, 0.0
                while lane_end_k < len(track.pit) - 1 and m < args.lane_margin:
                    m += math.hypot(track.pit[lane_end_k + 1].x - track.pit[lane_end_k].x, track.pit[lane_end_k + 1].z - track.pit[lane_end_k].z)
                    lane_end_k += 1
        print("pit lane exit: %s" % ("waypoint %d of %d (gate at %.0f, %.0f, %.0f m from the chain)" % (lane_end_k, len(track.pit), gate[0], gate[1], gd) if lane_end_k is not None
                                       else "no usable xpitout gate: whole pit chain limited"), flush=True)
    lane_end_said = False
    joined = None
    if track.pit and track.main and not args.no_pit_join:
        jk = track.nearest(track.main, track.pit[-1].x, track.pit[-1].z)
        joined = list(track.pit[:-1]) + [track.main[(jk + i) % len(track.main)] for i in range(120)]
    # Garage exit: the pit chain's line starts at the lane, 10 m or so from the box, so steering at it from the box turns the car into the
    # bay's side wall (Imola: two impacts of 16 and 72 m/s^2 within 4 m). The AIW's pit-stop waypoints (branch 2 and up) sit in front of
    # each box; drive straight at the nearest one that is ahead of the car, then hand over to the pit lane line.
    box_target, merging = None, False
    if chain0 is track.pit and d0 > 5 and not args.no_box_path and args.input == "analog":   # keyboard steering cannot make the turn in the room (radius about 11 m against 7.7 m): see CLAUDE.md
        cands = []
        for w in track.wps:
            if w.branch >= 2:
                dd = math.hypot(w.x - first["pos"][0], w.z - first["pos"][2])
                ang = wrap(track.yaw_of(w.x - first["pos"][0], w.z - first["pos"][2]) - first["yaw"])
                if 3.0 < dd < 25.0:
                    cands.append((dd, ang, w))
        print("garage exit: start (%.1f, %.1f) yaw %.1f, pit line %.1f m away; pit-stop points within 25 m (distance, bearing off the car's heading): %s" % (
            first["pos"][0], first["pos"][2], first["yaw"], d0, ", ".join("%.1f m %+.0f deg" % (c[0], c[1]) for c in sorted(cands, key=lambda c: c[0])[:6])), flush=True)
        ok_c = [c for c in cands if abs(c[1]) < 35.0]
        if args.box_pick == "heading":
            # Drive straight along the car's own heading until it is inside the pit lane's wide side (where the garage fronts are), then merge.
            kk0 = track.nearest(track.pit, first["pos"][0], first["pos"][2])
            wide = max(track.pit[kk0].left, track.pit[kk0].right)
            box_heading = first["yaw"]
            box_stop_lat = wide + args.box_margin
            box_start = (first["pos"][0], first["pos"][2])
            print("garage exit: driving straight along the heading (%.1f deg) until within %.1f m of the pit line (lane %.1f wide on the garage side + %.1f margin), at most %.0f m" % (
                box_heading, box_stop_lat, wide, args.box_margin, args.box_max), flush=True)
            box_target = "heading"
        elif ok_c:
            pick = min(ok_c, key=(lambda c: (abs(c[1]), c[0])) if args.box_pick == "align" else (lambda c: c[0]))
            box_target = pick[2]
            print("garage exit: driving straight to the pit-stop point (%.1f, %.1f), %.1f m ahead, %+.0f deg off the heading (--box-pick %s)" % (
                box_target.x, box_target.z, pick[0], pick[1], args.box_pick), flush=True)
    zones = []
    if args.zones:
        zf = Path(__file__).resolve().parent / "gtr2_driving" / "analog_tuned.json"
        ent = json.loads(zf.read_text()).get(Path(args.aiw).stem.lower()) if zf.exists() else None
        zones = (ent or {}).get("zones", [])
        print("slow zones: %s" % (zones or "none"), flush=True)

    def lat_at(a):
        for z in zones:
            if z[0] <= a.dist <= z[1]:
                return args.lat_accel * z[2]
        return args.lat_accel

    def bias_at(a):
        """Aim this many metres to one side of the racing line inside a zone's range (optional 4th zone value; positive = left)."""
        for z in zones:
            if len(z) > 3 and z[0] <= a.dist <= z[1]:
                return z[3]
        return 0.0
    shared = {"duty": 1.0, "steer": 0.0, "brake": 0.0, "gear": 1, "wt": time.time(), "scale": args.analog_steer}
    analog = args.input == "analog"
    joy = vjoy.VJoy(1).__enter__() if analog else None

    class Follower:
        """Moves a value toward a goal like a hand: speeds up (limited acceleration), then slows so it stops on the goal.
        Each tick the wanted speed is the largest one that can still be stopped in the remaining distance, capped at vmax; the
        speed itself changes by at most amax*dt. vmax <= 0 turns the smoothing off (the value follows the goal at once)."""
        def __init__(self, vmax, amax, lo, hi):
            self.vmax, self.amax, self.lo, self.hi, self.x, self.v = vmax, amax, lo, hi, 0.0, 0.0

        def step(self, goal, dt):
            goal = max(self.lo, min(self.hi, goal))
            if self.vmax <= 0:
                self.x = goal
                return goal
            err = goal - self.x
            want = math.copysign(min(self.vmax, math.sqrt(2.0 * self.amax * abs(err))), err)
            dv = self.amax * dt
            self.v += max(-dv, min(dv, want - self.v))
            self.x += self.v * dt
            if abs(goal - self.x) < 1e-3 and abs(self.v) < dv:
                self.x, self.v = goal, 0.0
            self.x = max(self.lo, min(self.hi, self.x))
            return self.x

    class RackModel:
        """Steering as a hand driving a rack: a spring toward the goal (natural frequency wn/sqrt(inertia), damping ratio 0.9) acting on
        an inertia, with sliding friction that drains speed and a breakaway (stiction) threshold a push must exceed to start the wheel
        moving from rest. Speed is capped at vmax like the follower. Units are full-lock fractions and seconds."""
        def __init__(self, vmax, inertia, friction, stiction, wn, lo=-1.0, hi=1.0):
            self.vmax, self.fc, self.fs, self.lo, self.hi = vmax, friction, stiction, lo, hi
            self.wn = wn / math.sqrt(inertia)
            self.x = self.v = 0.0

        def step(self, goal, dt):
            goal = max(self.lo, min(self.hi, goal))
            drive = self.wn ** 2 * (goal - self.x) - 2.0 * 0.9 * self.wn * self.v
            if abs(self.v) < 1e-4 and abs(drive) <= self.fs:
                self.v = 0.0                          # stuck: the push does not break the friction away
            else:
                self.v += drive * dt
                drag = self.fc * dt                   # sliding friction opposes the motion and cannot reverse it
                self.v = math.copysign(max(0.0, abs(self.v) - drag), self.v)
                if self.vmax > 0:
                    self.v = max(-self.vmax, min(self.vmax, self.v))
            self.x = max(self.lo, min(self.hi, self.x + self.v * dt))
            if self.x <= self.lo or self.x >= self.hi:
                self.v = 0.0
            return self.x

    def pedal(m):
        return (RackModel(args.analog_pedal_slew, m[0], m[1], m[2], m[3], 0.0, 1.0) if m[0] > 0
                else Follower(args.analog_pedal_slew, args.analog_pedal_accel, 0.0, 1.0))

    fol = {"steer": (RackModel(args.analog_slew, args.analog_inertia, args.analog_friction, args.analog_stiction, args.analog_wn)
                     if args.analog_inertia > 0 else Follower(args.analog_slew, args.analog_accel, -1.0, 1.0)),
           "throttle": pedal(args.analog_throttle_model),
           "brake": pedal(args.analog_brake_model)}

    def drive_analog():
        # steering X: right = above centre; throttle Z and brake Rx: below centre (each direction is half the axis)
        now_w = time.time()
        dt = min(0.1, now_w - shared["wt"])
        shared["wt"] = now_w
        x = fol["steer"].step(shared["steer"] * shared["scale"], dt)
        cap = args.analog_throttle[max(1, min(6, shared["gear"])) - 1] * (1.0 - args.analog_steer_ease * min(1.0, abs(shared["steer"])))
        th = fol["throttle"].step(min(cap, shared["duty"]), dt)
        br = fol["brake"].step(shared["brake"], dt)
        joy.axis("X", 0.5 + 0.5 * x)
        joy.axis("Z", 0.5 - 0.5 * th)
        joy.axis("RX", 0.5 - 0.5 * br)

    def analog_loop():
        while state["run"]:
            drive_analog(); time.sleep(0.01)

    def shift(up):
        if analog:
            def pulse():
                joy.button(1 if up else 2, True); time.sleep(0.12); joy.button(1 if up else 2, False)
            threading.Thread(target=pulse).start()
        else:
            threading.Thread(target=press_key, args=("alt" if up else "ralt",), kwargs={"hold": 120}).start()

    def brake_loop():
        while state["run"]:
            d = shared["brake"]
            if d < 0.05:
                time.sleep(0.1)
            else:
                press_key("z", hold=int(300 * d)); time.sleep(0.3 * (1 - d))

    def steer_loop():
        period = args.steer_period
        while state["run"]:
            amount = shared["steer"]
            if abs(amount) < 0.1:
                time.sleep(0.05); continue
            on = period * min(1.0, abs(amount) * 1.6)
            press_key("period" if amount > 0 else "comma", hold=int(on * 1000)); time.sleep(max(0.0, period - on))

    def throttle_loop():
        while state["run"]:
            d = shared["duty"]
            if d >= 0.98:
                press_key("a", hold=300)
            elif d <= 0.02:
                time.sleep(0.3)
            else:
                press_key("a", hold=int(300 * d)); time.sleep(0.3 * (1 - d))

    result = {"outcome": "timeout", "lap_changes": []}
    threads = []
    try:
        # first gear, read from the telemetry: the car can start in any gear (the display showed 3 at the box). Alt shifts up and
        # Right Alt down, each with the clutch (Q) held; stop after 8 tries if the gear never reaches 1.
        # Time Trial starts the car already rolling (about 13 m/s in 3rd) at the pit lane and parks it by itself within ~15 s, so
        # with a moving car this step is skipped and the loop below takes over at once. Open Practice starts it at rest in the box.
        STAGE("gear_step_begin")
        for attempt in range(8):
            cur = tm.read()
            gear = cur["gear"]
            if gear == 1 or cur["speed"] > 2.0:
                break
            clutch = threading.Thread(target=press_key, args=("q",), kwargs={"hold": 900}); clutch.start()
            time.sleep(0.3)
            if analog:      # shift on the virtual joystick's buttons (1 up, 2 down); the clutch stays on keyboard Q
                joy.button(1 if gear < 1 else 2, True); time.sleep(0.15); joy.button(1 if gear < 1 else 2, False)
            else:
                press_key("alt" if gear < 1 else "ralt", hold=150)
            clutch.join(); time.sleep(0.4)
        print("gear before moving off: %d" % tm.read()["gear"], flush=True)
        STAGE("gear_step_done")
        for fn in ((analog_loop,) if analog else (throttle_loop, steer_loop, brake_loop)):
            th = threading.Thread(target=fn); th.start(); threads.append(th)

        t0 = time.time()
        chain, k = chain0, None
        prev_yaw, prev_t, last_move, n, last_shift = None, time.time(), time.time(), 0, 0.0
        start_lap, last_lap, finish_at = first["lap"], first["lap"], None
        accum, prev_dist, by_distance = 0.0, None, False     # distance covered along the racing line: a fallback when the game's lap counter never moves (Hockenheim Short)
        off_samples = samples = 0
        peak_pit = peak_all = 0.0
        impacts, last_impact = [], -1.0
        off_buckets = {}
        off_lat = {}
        max_lat = 0.0
        STAGE_MOVED = []
        ft = {"phase": 0, "until": 0.0, "proc": None, "sum": [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0]], "prev": None}
        while state["run"] and time.time() - t0 < args.total:
            tel = tm.read()
            if tel is None:
                time.sleep(0.05); continue
            now = time.time()
            if tel["speed"] > 0.3 and not STAGE_MOVED:
                STAGE_MOVED.append(1); STAGE("first_movement")
            x, z = tel["pos"][0], tel["pos"][2]
            yaw, speed = tel["yaw"], tel["speed"]
            dt = max(now - prev_t, 1e-3)
            yawrate = 0.0 if prev_yaw is None else wrap(yaw - prev_yaw) / dt
            prev_yaw, prev_t = yaw, now
            if args.focus_test:
                if ft["phase"] == 0 and now - t0 > args.focus_test[0] and speed > 25:
                    ft["phase"], ft["until"] = 1, now + args.focus_test[1]
                    si = subprocess.STARTUPINFO(); si.dwFlags = 1; si.wShowWindow = 7 if os.environ.get("GTR2_FT_NOACTIVATE") else 1     # 7 = minimised, not activated
                    ft["proc"] = subprocess.Popen(["notepad.exe"], startupinfo=si); ft["prev"] = None
                    print("focus test: Notepad opened at t=%.1f" % (now - t0), flush=True)
                elif ft["phase"] == 1 and now > ft["until"]:
                    ft["phase"] = 2; ft["prev"] = None
                    ft["proc"].kill(); print("focus test: Notepad closed at t=%.1f" % (now - t0), flush=True)
                if ft["prev"] is not None and speed > 15 and ft["phase"] in (0, 1, 2) and ft["sum"] is not None:
                    q = ft["prev"]; mv = ((x - q[0]) ** 2 + (z - q[1]) ** 2) ** 0.5
                    if (ft["phase"] == 0 and now - t0 > 5) or ft["phase"] > 0:
                        ft["sum"][ft["phase"]][0] += mv; ft["sum"][ft["phase"]][1] += speed * (now - q[2])
                ft["prev"] = (x, z, now)
            if speed > 0.3:
                last_move = now
            if tel["lap"] != last_lap:
                result["lap_changes"].append({"t": round(now - t0, 1), "lap": tel["lap"]})
                print("t=%5.1f lap counter %d -> %d" % (now - t0, last_lap, tel["lap"]), flush=True)
                last_lap = tel["lap"]
            if finish_at is None and last_lap == start_lap and accum >= 1.1 * args.laps_crossed * track.lap_length:
                by_distance = True
                result["lap_changes"].append({"t": round(now - t0, 1), "lap": start_lap + 1, "by_distance": True})     # a time for the tuner, from the distance rule
                print("t=%5.1f the lap counter has not moved after %.0f m along the racing line (%.1f laps): counting the lap as done" % (now - t0, accum, accum / track.lap_length), flush=True)
            if finish_at is None and (last_lap - start_lap >= args.laps_crossed or by_distance):
                finish_at = now
                print("t=%5.1f lap counter advanced %d times: finishing in %.0f s" % (now - t0, args.laps_crossed, args.finish_extra), flush=True)
            if finish_at is not None and now - finish_at > args.finish_extra:
                result["outcome"] = "completed"; break

            k = track.nearest(chain, x, z, near=k) if k is not None else track.nearest(chain, x, z)
            if chain is track.pit and k >= len(chain) - 2:
                chain, k = track.main, track.nearest(track.main, x, z)
                print("t=%5.1f on the racing line at lap distance %.0f" % (now - t0, track.main[k].dist), flush=True)
            w = chain[k]
            if chain is track.main:
                if prev_dist is not None:
                    dd = (w.dist - prev_dist) % track.lap_length
                    if dd < 60.0:
                        accum += dd
                prev_dist = w.dist
            lat = track.lateral(w, x, z)
            samples += 1
            a_h = math.hypot(tel["accel"][0], tel["accel"][2])
            peak_all = max(peak_all, a_h)
            if chain is track.pit:
                peak_pit = max(peak_pit, a_h)
            if a_h > args.impact_accel and now - last_impact > 0.3:
                last_impact = now
                impacts.append({"t": round(now - t0, 2), "x": round(x, 1), "z": round(z, 1), "a": round(a_h, 1), "pit": chain is track.pit})
                print("t=%5.1f IMPACT %.1f m/s^2 at (%.1f, %.1f) speed %.1f" % (now - t0, a_h, x, z, speed), flush=True)
            if any(any(bad in s for bad in OFF_ROAD) for s in tel["surfaces"]):
                off_samples += 1
                if chain is track.main:      # where on the lap (20 m buckets of lap distance) and on what surface
                    key = "%d %s" % (int(w.dist // 20) * 20, ",".join(sorted({s for s in tel["surfaces"] if any(b in s for b in OFF_ROAD)})))
                    off_buckets[key] = off_buckets.get(key, 0) + 1
                    off_lat.setdefault(key, []).append(lat)      # lateral offset from the line at those samples (sign: see trackmap.lateral)
            if chain is track.main:
                max_lat = max(max_lat, abs(lat))

            look = args.lookahead[0] + args.lookahead[1] * speed
            if chain is track.pit:
                # a short aim distance in the pit lane: the narrow winding service roads at Estoril and Anderstorp (4 to 6 m wide, 90 degree
                # bends) were cut by 1.5 m or more with the circuit's 5 m + 1.2 per m/s, which put the car into the wall
                look = max(args.pit_lookahead[0] + args.pit_lookahead[1] * speed, 1.5 * abs(lat))
            target = track.ahead(chain, k, look)
            margin = args.pit_margin if chain is track.pit else 0.0

            def aim_offset(p):
                shift = args.pit_aim if chain is track.pit else (bias_at(p) if zones else 0.0)
                if p.left < margin:
                    shift = min(shift, -(margin - p.left))
                elif p.right < margin:
                    shift = max(shift, margin - p.right)
                lo, hi = -(p.right - 0.8), p.left - 0.8
                if hi < lo:
                    return 0.5 * (p.left - p.right)
                return max(lo, min(hi, shift))
            lat_t, lat_here = aim_offset(target), aim_offset(w)
            want = track.yaw_of(target.x - target.hz * lat_t - x, target.z + target.hx * lat_t - z)
            lat = lat - lat_here
            pull = 0.0 if chain is track.pit else max(-20.0, min(20.0, args.center_gain * lat))
            if box_target is not None:
                if box_target == "heading":
                    done = chain is not track.pit or abs(track.lateral(w, x, z)) <= box_stop_lat or math.hypot(x - box_start[0], z - box_start[1]) > args.box_max
                else:
                    done = chain is not track.pit or math.hypot(box_target.x - x, box_target.z - z) < args.box_exit_dist
                if done:
                    print("t=%5.1f left the box path (%.1f m from the pit line)" % (now - t0, abs(track.lateral(w, x, z))), flush=True)
                    box_target, merging = None, chain is track.pit
                elif box_target == "heading":
                    want, pull = box_heading, 0.0
                else:
                    want, pull = track.yaw_of(box_target.x - x, box_target.z - z), 0.0
            herr = wrap(want - yaw + pull)
            if merging and (chain is not track.pit or (abs(herr) < 15.0 and abs(lat) < 2.5)):
                print("t=%5.1f merged onto the pit lane line" % (now - t0), flush=True)
                merging = False
            shared["scale"] = args.merge_steer if (merging or box_target is not None or chain is track.pit) else args.analog_steer   # slow in the pit lane: full lock (Anderstorp's 90 degree bend, 5 to 6 m wide)
            shared["steer"] = max(-1.0, min(1.0, herr / args.steer_gain - yawrate / args.damping))

            window = 25.0 + speed * speed / (2.0 * args.decel)
            corner_v, _ = track.speed_limit(joined if (chain is track.pit and joined) else chain, k, window, args.pit_lat_accel if chain is track.pit else (lat_at if zones else args.lat_accel), args.decel, tight_radius=args.tight_radius, tight_speed=args.tight_speed)
            in_lane = chain is track.pit and (lane_end_k is None or k <= lane_end_k)
            if chain is track.pit and not in_lane and not lane_end_said:
                lane_end_said = True
                print("t=%5.1f past the pit lane exit (waypoint %d of %d): pit speed cap off" % (now - t0, k, len(chain)), flush=True)
            vmax = args.pit_speed if in_lane else args.speed
            if chain is track.pit and abs(lat) > 3.0:
                vmax = min(vmax, 5.0)
            target_v = max(3.0, min(vmax, corner_v))
            if box_target is not None:
                target_v = min(target_v, args.box_speed)
            elif merging:
                target_v = min(target_v, args.merge_speed)
            over = abs(herr) - args.guard_deg
            if over > 0:
                target_v = max(4.0, target_v * max(args.guard_floor, 1.0 - over / args.guard_span))
            shared["duty"] = max(0.0, min(1.0, 0.45 + 0.25 * (target_v - speed))) if speed > 1.5 else 1.0
            shared["brake"] = max(0.0, min(0.9, 0.25 * (speed - target_v - 0.7)))
            if box_target is not None or merging:       # creeping out of the box: gentle throttle (a full launch reached 6.5 m/s in 3 m)
                shared["duty"] = min(shared["duty"], args.box_throttle)
            if analog:
                shared["gear"] = tel["gear"]

            n += 1
            if now - t0 < args.trace:
                print("T %5.2f x=%7.1f z=%7.1f yaw=%7.1f rate=%+6.1f v=%5.2f herr=%+6.1f steer=%+5.2f duty=%.2f brake=%.2f gear=%d ax=%+6.1f az=%+6.1f" % (
                    now - t0, x, z, yaw, yawrate, speed, herr, shared["steer"], shared["duty"], shared["brake"], tel["gear"], tel["accel"][0], tel["accel"][2]), flush=True)
            if now - last_shift > 1.2 and not in_lane:
                gear, rpm = tel["gear"], tel["rpm"]
                if gear < args.max_gear and rpm > args.shift_rpm:
                    last_shift = now; shift(True)
                elif gear > 1 and rpm < args.down_rpm:
                    last_shift = now; shift(False)
            if n % args.every == 0:
                print("t=%5.1f %s k=%3d lat=%+5.1f herr=%+6.1f v=%4.1f->%4.1f gear=%d lap=%d" % (
                    now - t0, "main" if chain is track.main else "pit ", k, lat, herr, speed, target_v, tel["gear"], tel["lap"]), flush=True)
            if now - last_move > 8.0:
                result["outcome"] = "stopped moving at x=%.0f z=%.0f" % (x, z); break
            time.sleep(0.02)
        if state["aborted"]:
            result["outcome"] = "aborted: " + state["aborted"]
        if args.focus_test:
            if ft["proc"] is not None and ft["proc"].poll() is None: ft["proc"].kill()
            print("FOCUS TEST sim rate (1.0 = real time): before %s, Notepad in front %s, after %s" % tuple(
                ("%.2f" % (a / b) if b > 1 else "n/a") for a, b in ft["sum"]), flush=True)
        result["lap_counter_missing"] = by_distance
        result.update(off_road_at=[[k, n, round(sum(off_lat[k]) / len(off_lat[k]), 1)] for k, n in sorted(off_buckets.items(), key=lambda kv: -kv[1])[:8]], impacts=impacts[:10], pit_impacts=sum(1 for i in impacts if i["pit"]), peak_accel_pit=round(peak_pit, 1), peak_accel=round(peak_all, 1), seconds=round(time.time() - t0), off_road_share=round(off_samples / max(samples, 1), 4), max_offset=round(max_lat, 1))
    finally:
        state["run"] = False
        shared["steer"] = shared["brake"] = 0.0
        for th in threads:
            th.join(timeout=5)
        # bring the car to a stop: hold the brake for a few seconds (the game window must still be in front)
        state["run"] = True
        if analog:
            joy.axis("X", 0.5); joy.axis("Z", 0.5); joy.axis("RX", 0.0)   # full brake for 4 s
            time.sleep(4.0)
            joy.__exit__()
        elif game_in_front():
            for _ in range(8):
                press_key("z", hold=400)
        state["run"] = False
    print("RESULT", json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
