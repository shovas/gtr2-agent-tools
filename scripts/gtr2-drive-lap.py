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
from types import SimpleNamespace
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import pitzones  # noqa: E402
import cargears  # noqa: E402
import racingline  # noqa: E402
import follower  # noqa: E402
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
    ap.add_argument("--device", choices=("stick", "wheel"), default="stick", help="analog only: which hardware the vJoy axes stand for. stick: a joystick/gamepad, full steering range under one hand (the tuned default, unchanged). wheel: a rim turned through --wheel-degrees lock to lock, so the hand needs more travel per unit of axis (the steering speed limit becomes --wheel-hand-dps divided by half the range) and the axis is quantised to --wheel-bits")
    ap.add_argument("--wheel-degrees", type=float, default=900.0, help="wheel device: wheel rotation lock to lock in degrees (G27: 900)")
    ap.add_argument("--wheel-hand-dps", type=float, default=1000.0, help="wheel device: fastest hand rotation of the rim, degrees per second (a quick sawing hand is about 1000)")
    ap.add_argument("--wheel-bits", type=int, default=14, help="wheel device: steering axis resolution in bits (14 for a G27 in its native mode, from memory, not verified; vJoy itself has 15)")
    ap.add_argument("--wheel-pedal-bits", type=int, default=8, help="wheel device: throttle/brake/clutch pedal resolution in bits (stock G25/G27 potentiometer pedals: about 8 per community sources, not verified; a Leo Bodnar adapter gives 10, Hall sensor mods 12)")
    ap.add_argument("--analog-slew", type=float, default=3.0, help="analog only: top steering speed in full-lock units per second; 0 = no smoothing (the control loop runs at about 40 Hz measured 2026-11-17; a 100 Hz writer ramps between its commands)")
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
    ap.add_argument("--box-yaw-bias", default="auto", help="with --box-pick heading: aim this many degrees off the car's own heading while driving straight out of the box (positive = the yaw angle grows), or auto (default) = pick it from the track's own wall meshes (gtr2_driving/boxplan.py: reads the .trk and .gtr; the first run of a layout and start takes several seconds, then it is cached). Anderstorp 3 needed -6 by hand")
    ap.add_argument("--box-max", type=float, default=14.0, help="with --box-pick heading: never drive straight further than this (m)")
    ap.add_argument("--box-straight-throttle", type=float, default=0.15, help="throttle ceiling for the straight run out of the garage box only (a walking-pace roll over the lip at the garage mouth; the box-throttle ceiling then applies to the merge)")
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
    ap.add_argument("--aim-step", action="store_true", help="aim at whole waypoints as before (the aim point jumps a waypoint spacing each time the nearest waypoint advances); the default interpolates the aim point exactly the lookahead distance along the line from the car")
    ap.add_argument("--steer-gain", type=float, default=25.0)
    ap.add_argument("--damping", type=float, default=90.0)
    ap.add_argument("--steer-period", type=float, default=0.4)
    ap.add_argument("--brake-gain", type=float, default=0.25, help="brake pedal per m/s over the target speed (default 0.25)")
    ap.add_argument("--impact-track", type=float, default=0.0, help="impact threshold on the racing line (m/s^2, 0 = --impact-accel). Live mode sets 20: ordinary bumps and kerb jolts of 14 to 20 are racing, walls read far higher (the garage wall hit read 16, so the garage exit keeps --impact-accel)")
    ap.add_argument("--impact-spike", type=float, default=0.0, help="m/s^2 an impact must rise above the median of the last six samples (0: off, the plain threshold alone). Use about 6 with high cornering limits (--lat-accel 9+), where the car itself pulls over 14 m/s^2 in a corner")
    ap.add_argument("--kerb-max-accel", type=float, default=60.0, help="a jolt on the racing line that looks like a kerb strike (mostly vertical, or kerb/rumble surfaces) counts as a kerb strike up to this many m/s^2; above it, or with no kerb sign, it is an impact (default 60: kerb strikes can be hard in real racing; garage wall hits read 72)")
    ap.add_argument("--tc-gain", type=float, default=0.0, help="traction-aware throttle: cut the throttle cap by this much per m/s^2 of measured lateral load above --tc-free (0: off)")
    ap.add_argument("--tc-free", type=float, default=6.0, help="lateral load (m/s^2) below which --tc-gain does nothing")
    ap.add_argument("--tc-floor", type=float, default=0.3, help="lowest throttle cap --tc-gain can reach")
    ap.add_argument("--line-opt", action="store_true", help="drive a time-optimal racing line found from the track's widths and the grip/braking/power numbers (gtr2_driving/racingline.py; cached per layout); replaces --line-smooth")
    ap.add_argument("--line-opt-margin", type=float, default=1.2, help="--line-opt: metres the car's side stays inside each white line")
    ap.add_argument("--follower", choices=("pursuit", "stanley", "designed"), default="pursuit", help="how the steering follows the line: pursuit (aim at a point look-ahead metres ahead, the proven default) or stanley (cross-track and heading error at the car plus curvature feed-forward, with a steering gain learned from the car's own yaw response)")
    ap.add_argument("--steer-id", action="store_true", help="identify the steering while driving (yaw rate per steering command per m/s, per 10 m/s speed bin, steady stretches only) and record it in the result; does not change the steering yet. On in live mode")
    ap.add_argument("--steer-live", action="store_true", help="scale the pursuit steering by reference / measured yaw response per command at the current speed (needs --steer-id), so the heading loop keeps one time constant at every speed")
    ap.add_argument("--steer-live-ref", type=float, default=0.8, help="--steer-live: reference yaw response, rad/s per unit of steering command")
    ap.add_argument("--steer-live-min", type=float, default=0.7)
    ap.add_argument("--steer-live-max", type=float, default=1.4)
    ap.add_argument("--st-learn", action="store_true", help="--follower stanley: adapt the steering gain per speed bin from the yaw response (off: use the measured table)")
    ap.add_argument("--st-wn", type=float, default=1.2, help="--follower designed: closed loop natural frequency, rad/s (gains are designed from speed: a = 2 zeta wn L / v, b = wn^2 L / v^2)")
    ap.add_argument("--st-zeta", type=float, default=0.8, help="--follower designed: damping ratio")
    ap.add_argument("--st-k", type=float, default=1.0, help="--follower stanley: cross-track gain (1/s)")
    ap.add_argument("--st-ks", type=float, default=3.0, help="--follower stanley: speed softening of the cross-track term (m/s)")
    ap.add_argument("--st-ff", type=float, default=1.0, help="--follower stanley: scale of the curvature feed-forward")
    ap.add_argument("--st-preview", type=float, default=0.45, help="--follower stanley: seconds ahead the curvature is read for the feed-forward")
    ap.add_argument("--st-damp", type=float, default=90.0, help="--follower stanley: yaw-rate error damping, degrees per second per unit of steering")
    ap.add_argument("--wheelbase", type=float, default=2.7, help="wheelbase in metres, for --follower stanley")
    ap.add_argument("--line-smooth", type=int, default=0, help="passes of racing-line smoothing (0 = follow the AIW line as it is); a smoother line has lower curvature, so the speed planner allows more speed")
    ap.add_argument("--line-pin", type=float, default=0.0, help="with --line-smooth: keep the AIW line where the corner radius is under this many metres (tight chicanes have kerbs and bollards inside; 0 = smooth everywhere)")
    ap.add_argument("--line-margin", type=float, default=1.8, help="metres to stay inside the road edges when --line-smooth moves the line")
    ap.add_argument("--shift-rpms", type=float, nargs="+", default=None, metavar="RPM", help="upshift rpm for each gear (1>2, 2>3, ...), e.g. from gtr2-shift-points.py; overrides --shift-rpm")
    ap.add_argument("--dyn", action="store_true", help="real-time wheel monitoring: ease the throttle on driven-wheel slip and the brake on a locking wheel; replaces the per-gear throttle caps and the steering ease")
    ap.add_argument("--dyn-slip", type=float, default=0.10, help="--dyn: rear/front wheel speed excess (beyond the rolling baseline) the throttle tolerates before easing (default 0.10)")
    ap.add_argument("--dyn-brake-slip", type=float, default=0.12, help="--dyn: wheel slip against the car's speed the brake tolerates before easing (default 0.12)")
    ap.add_argument("--dyn-rear-brake-slip", type=float, default=0.25, help="--dyn: wheel slip against the car's speed the REAR axle tolerates under braking before the brake eases (the rear runs about 0.1 slow in every hard stop)")
    ap.add_argument("--dyn-gain", type=float, default=6.0, help="--dyn: pedal cut per unit of slip above the tolerance (default 6)")
    ap.add_argument("--dyn-grip", type=float, default=0.4, help="--dyn: a driven (or front, braking) wheel with a grip fraction below this also cuts the pedal")
    ap.add_argument("--dyn-recover", type=float, default=3.0, help="--dyn: how fast a cut pedal comes back, fraction per second (default 3)")
    ap.add_argument("--dyn-min", type=float, default=0.25, help="--dyn: lowest throttle scale")
    ap.add_argument("--dyn-min-brake", type=float, default=0.3, help="--dyn: lowest brake scale")
    ap.add_argument("--live", action="store_true", help="live grip model: cornering and braking limits scale with the measured tyre load (downforce) and adapt while driving from the tyres' grip fraction, wheel lock and impacts (needs --dyn's wheel data); replaces --lat-accel and --decel on the racing line")
    ap.add_argument("--live-adapt", action="store_true", help="--live: also adapt the base grips while driving (unstable so far: the braking grip collapses to its floor; off by default)")
    ap.add_argument("--live-fit", action="store_true", help="--live: fit the downforce coefficient from tyre load against speed while driving instead of using --live-k")
    ap.add_argument("--live-brake-k", type=float, default=0.0, help="--live: how much braking grip grows with speed (0: constant; measured braking did not grow with speed)")
    ap.add_argument("--slow-zone", type=float, nargs=3, action="append", metavar=("FROM", "TO", "FACTOR"), default=[], help="scale the cornering limit by FACTOR between these lap distances (metres); may be given several times (the Imola chicane at about 3120 m); with --live or the plain planner")
    ap.add_argument("--car-key", default="", help="the car's key (gt/maserati_mc12), set by gtr2-lap-check.py; used by --gear-opt to read the engine and gear files")
    ap.add_argument("--gear-down-hyst", type=float, default=1.15, help="with --gear-opt: a downshift must give this much more wheel thrust than the current gear (1.04 = the old rule)")
    ap.add_argument("--gear-first-max", type=float, default=8.0, help="with --gear-opt: no downshift into 1st above this speed, m/s (99 = the old rule)")
    ap.add_argument("--gear-opt", action="store_true", help="pick the gear with the most wheel thrust from the car's own torque curve and gear ratios (down under braking for the corner exit speed), instead of upshift at a fixed rpm and downshift below --down-rpm")
    ap.add_argument("--aim-comp-max", type=float, default=2.5, help="the most --aim-comp moves the aim point, metres")
    ap.add_argument("--aim-comp", type=float, default=0.0, help="move the aim point outward by this fraction of the corner-cutting a pure-pursuit aim point would do (look x turn / 8); 0 = off")
    ap.add_argument("--edge-guard", type=float, default=0.0, help="live track-limit guard: degrees of extra heading correction back towards the line per metre the car is inside --edge-room of a white line (0 = off)")
    ap.add_argument("--edge-room", type=float, default=1.0, help="--edge-guard: distance in metres from the car's side to the white line where the guard starts")
    ap.add_argument("--edge-slow", type=float, default=0.1, help="--edge-guard: target speed cut per metre inside the guard distance")
    ap.add_argument("--car-half-width", type=float, default=1.0, help="half the car's width in metres, for the white-line distance")
    ap.add_argument("--grip-map", action="store_true", help="live cornering grip map: the grip the planner uses is a factor per 20 m of lap distance that the car itself moves while driving: up a little where it carried the load near the limit with every tyre gripping and stayed on the line, down at once (on the stretch before, too) where an outer tyre slid, the car ran wide or hit something; the out lap teaches the flying lap, nothing is set per track")
    ap.add_argument("--gm-up", type=float, default=0.10, help="--grip-map: factor gain per clean pass of a 20 m bin near the limit")
    ap.add_argument("--gm-down", type=float, default=0.02, help="--grip-map: factor loss when the car slides in a bin")
    ap.add_argument("--gm-max", type=float, default=1.6)
    ap.add_argument("--gm-min", type=float, default=0.6)
    ap.add_argument("--gm-use", type=float, default=0.85, help="--grip-map: share of the planned lateral load the car must reach in a bin before the factor may rise")
    ap.add_argument("--gm-heal", type=float, default=0.04, help="--grip-map: a clean pass of a bin below 1.0 raises its factor by this much even when the grip was not used to the limit")
    ap.add_argument("--gm-limit", type=float, default=0.08, help="--grip-map: factor loss on the six 20 m bins before a track-limit event (all four tyres beyond the white line)")
    ap.add_argument("--gm-slide", type=float, default=0.50, help="--grip-map: grip fraction of an outer tyre under which it counts as sliding")
    ap.add_argument("--gm-line", type=float, default=1.5, help="--grip-map: metres off the line beyond which a bin counts as run wide")
    ap.add_argument("--outlap-scale", type=float, default=0.97, help="live mode: the out lap (before the first lap change) is driven at this share of the planned corner and braking speeds: it is not a valid lap (cold tyres), it only teaches the maps")
    ap.add_argument("--no-memory", action="store_true", help="live mode: do not load or save what the maps learned (scripts/gtr2_driving/learned/<layout>_<car>.json)")
    ap.add_argument("--geo-limits", action="store_true", help="experiment: also test the track limits geometrically (each tyre's position against the white lines from the waypoint widths) next to the surface rule, and record both in the result (geo_*)")
    ap.add_argument("--wheel-track", type=float, default=1.65, help="--geo-limits: distance between the left and right wheels, metres")
    ap.add_argument("--tyre-half", type=float, default=0.15, help="--geo-limits: half the tyre width, metres: a tyre is over the line when its whole width is beyond it")
    ap.add_argument("--session-laps", type=int, default=0, help="keep lapping: the out lap plus this many timed laps in one session, and adjust a push factor on the planned corner speeds lap by lap (--meta-*): a clean lap that is faster than the best raises it, an unclean lap or a slower one takes it back and shrinks the step. Raise --total and the lap check's --timeout with it")
    ap.add_argument("--meta-start", type=float, default=1.0, help="--session-laps: starting push factor")
    ap.add_argument("--meta-step", type=float, default=0.02, help="--session-laps: starting push step")
    ap.add_argument("--meta-max", type=float, default=1.25)
    ap.add_argument("--meta-min", type=float, default=0.85)
    ap.add_argument("--line-seed-dry", action="store_true", help="with --line-opt: the optimiser starts from the game's own dry line (wp_path in the AIW) and refines it with the driver's own physics; the result is the driver's line, not the file's")
    ap.add_argument("--dry-line", action="store_true", help="drive the game's own dry racing line stored in the AIW (wp_path, the line the in-game AI follows) instead of the smoothed file line; the margin to the white lines is --line-margin")
    ap.add_argument("--limit-guard", action="store_true", help="track-limit prevention: when three tyres are already off the road surface (the fourth would void the lap), cut the throttle and steer back towards the line until a tyre is back on the road. Live mode turns it on")
    ap.add_argument("--limit-guard-throttle", type=float, default=0.3, help="--limit-guard: throttle ceiling while three tyres are off the road")
    ap.add_argument("--limit-guard-steer", type=float, default=0.15, help="--limit-guard: extra steering towards the line (units of the steering command) while three tyres are off the road, four times that if all four")
    ap.add_argument("--kerb-vert-share", type=float, default=0.5, help="a jolt counts as a kerb strike or bump (not an impact) when its vertical part is at least this share of it (or kerb surfaces are under a tyre). Live mode uses 0.35: measured at Imola, bumps under braking give 0.40 to 0.41, garage wall hits 0.01")
    ap.add_argument("--contact-min", type=float, default=10.0, help="record every jolt of at least this many m/s^2 (with the surfaces under the wheels) in the result's `contacts`, whatever the hit limits say; read them with gtr2-contact-stats.py")
    ap.add_argument("--kerb-mode", action="store_true", help="on a kerb or rumble strip (and for --kerb-hold seconds after): cap the throttle, ease the brake and hold the gear, so the kick does not become wheelspin, a lockup or an unloaded shift")
    ap.add_argument("--kerb-hold", type=float, default=0.4)
    ap.add_argument("--kerb-throttle", type=float, default=0.5, help="--kerb-mode: throttle ceiling on a kerb")
    ap.add_argument("--kerb-brake", type=float, default=0.6, help="--kerb-mode: brake scale on a kerb")
    ap.add_argument("--kerb-steer", type=float, default=1.0, help="--kerb-mode: steering scale on a kerb (1 = unchanged)")
    ap.add_argument("--recover", action="store_true", help="when the car has stopped (against a wall, spun) for --recover-after seconds while trying to drive, reverse out towards the line (neutral, reverse), then shift back up and carry on")
    ap.add_argument("--recover-after", type=float, default=2.0)
    ap.add_argument("--recover-dist", type=float, default=7.0, help="metres to back up")
    ap.add_argument("--brake-ctl", action="store_true", help="regulate the brake pedal by measured front-wheel slip: it rises towards the full pedal while the front wheels slip less than --brake-slip and falls fast when they slip more, so braking runs at the lock-up threshold")
    ap.add_argument("--brake-slip", type=float, default=0.12, help="--brake-ctl: front wheel slip to hold (fraction of the speed of the car)")
    ap.add_argument("--brake-ki", type=float, default=8.0, help="--brake-ctl: pedal change per second per unit of slip error")
    ap.add_argument("--brake-adapt", action="store_true", help="the braking number of the planner follows the deceleration the car achieves at the lock-up threshold, per speed bin (starts at --decel)")
    ap.add_argument("--learn-hits", action="store_true", help="a hard hit (impact or kerb strike over --learn-min m/s^2) makes the planner take that stretch of the lap slower from then on (the out lap teaches the flying lap); nothing is set per track")
    ap.add_argument("--learn-heal", type=float, default=0.05, help="--learn-hits in a lap session: each lap gives the zones learned from hits this much of their factor back")
    ap.add_argument("--learn-kerb-min", type=float, default=35.0, help="--learn-hits: a kerb strike must be at least this hard (m/s^2) to take a stretch slower and the braking number down; ordinary kerb strikes, 14 to 30, do not (impacts still teach from --learn-min)")
    ap.add_argument("--brake-heal", type=float, default=0.03, help="--brake-adapt in a lap session: each clean lap raises every learned braking number by this share (hits under braking lower them)")
    ap.add_argument("--learn-min", type=float, default=20.0)
    ap.add_argument("--debug-stop", type=float, nargs=2, metavar=("AT", "SECONDS"), default=None, help="test hook: at AT seconds brake to a stop and hold for SECONDS, to exercise --recover")
    ap.add_argument("--live-lat", type=float, default=10.0, help="--live: starting cornering grip at rest, m/s^2")
    ap.add_argument("--live-brake", type=float, default=11.0, help="--live: starting braking grip at rest, m/s^2")
    ap.add_argument("--live-k", type=float, default=1.8e-4, help="--live: starting downforce coefficient (extra grip fraction per (m/s)^2); fitted live from tyre load against speed")
    ap.add_argument("--live-max", type=float, default=24.0, help="--live: ceiling for the adapted grips, m/s^2")
    ap.add_argument("--live-grip-lo", type=float, default=0.80, help="--live: front grip fraction under which cornering counts as sliding")
    ap.add_argument("--brake-allow", type=float, default=12.0, help="m/s^2 of longitudinal acceleration that our own braking explains on the main line and that impact detection ignores (0 counts it all; default 12)")
    ap.add_argument("--brake-max",type=float, default=0.9, help="brake pedal ceiling (default 0.9)")
    ap.add_argument("--brake-deadband", type=float, default=0.7, help="m/s over the target before braking starts (default 0.7)")
    ap.add_argument("--throttle-gain", type=float, default=0.25, help="throttle change per m/s under the target speed (default 0.25)")
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
    ap.add_argument("--stop-at-merge", type=float, default=0.0, metavar="SECONDS", help="garage-exit test: stop SECONDS after merging onto the pit lane line (outcome 'merged')")
    ap.add_argument("--total", type=float, default=900.0, help="give up after this many seconds")
    ap.add_argument("--every", type=int, default=60, help="print a status line every N loops")
    ap.add_argument("--dry-run", action="store_true", help="read the telemetry and the track, print the plan, press no keys")
    ap.add_argument("--fixed", action="store_true", help="fixed-limit mode: the planner uses --lat-accel and --decel as given (and the per-track \"<stem>:fixed\" numbers of track_params.json) and none of the live systems start by themselves. The default for --fast is live: the cornering grip map, the braking map (--brake-ctl --brake-adapt), wheel control (--dyn), contact learning and stall recovery, starting from generic priors and adapting to what the car does")
    ap.add_argument("--no-track-params", action="store_true", help="ignore scripts/gtr2_driving/track_params.json")
    args = ap.parse_args()
    if args.session_laps > 0:
        args.laps_crossed = args.session_laps + 1
    # Per-track settings (gtr2_driving/track_params.json): maps an AIW file stem (lower case) to extra options for a
    # layout whose tight corners need something the others don't. They replace the same options given on the command line and
    # are applied before the --fast/slow preset fills in what is still unset.
    params_file = Path(__file__).resolve().parent / "gtr2_driving" / "track_params.json"
    all_params = {} if args.no_track_params or not params_file.exists() else json.loads(params_file.read_text())
    extra = all_params.get(Path(args.aiw).stem.lower())
    if args.fixed and all_params.get(Path(args.aiw).stem.lower() + ":fixed"):
        extra = ((extra or "") + " " + all_params[Path(args.aiw).stem.lower() + ":fixed"]).strip()
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
    if args.fast and not args.fixed:      # the default: live, dynamic, feedback driven; the numbers below are only the starting priors the maps adapt from
        if args.kerb_vert_share == 0.5:
            args.kerb_vert_share = 0.35
        if args.impact_track <= 0:
            args.impact_track = 20.0
        for name in ("grip_map", "brake_ctl", "brake_adapt", "dyn", "learn_hits", "recover", "live", "live_fit", "gear_opt", "limit_guard", "steer_id"):
            setattr(args, name, True)
        print("live mode: grip map, braking map, wheel control, contact learning, stall recovery (--fixed for fixed limits)", flush=True)
    slow = dict(speed=6.0, pit_speed=8.0, lat_accel=2.0, decel=3.0, max_gear=3, shift_rpm=6800.0, down_rpm=2800.0)
    fast = dict(speed=60.0 if args.fixed else 150.0, pit_speed=16.0, lat_accel=7.5 if args.fixed else 10.0, decel=6.0 if args.fixed else 12.0, max_gear=6, shift_rpm=6300.0, down_rpm=3000.0)
    for name, value in (fast if args.fast else slow).items():
        if getattr(args, name) is None:      # an explicit option always wins over the preset
            setattr(args, name, value)

    CLUTCH_HOLD_MS, CLUTCH_LEAD_S = 500, 0.15      # first-gear step (was 900 ms and 0.3 s; shortened 2026-11-14, a failed shift is retried up to 8 times)
    STAGE = lambda name: print("STAGE %s epoch=%.3f" % (name, time.time()), flush=True)      # start-up timing: compared with gtr2-lap-check.py's own stamps
    STAGE("script_started")
    track = trackmap.Track(args.aiw)
    if args.line_opt:
        ph = racingline.Physics(lat=args.lat_accel, decel=args.decel, kk=args.live_k if args.live else 0.0)
        offs = racingline.cached_offsets(track, Path(args.aiw).stem, ph, margin=args.line_opt_margin, log=lambda m: print("racing line: " + m, flush=True), seed=([-w_.dry for w_ in track.main] if args.line_seed_dry else None))
        racingline.apply(track, offs)
        print("racing line applied: offsets %.1f to %.1f m (mean %.1f)" % (offs.min(), offs.max(), abs(offs).mean()), flush=True)
    if args.dry_line:
        import numpy as np_
        c0_, r0_, left_, right_ = racingline.geometry(track)
        offs_ = np_.array([-w_.dry for w_ in track.main])
        offs_ = np_.minimum(np_.maximum(offs_, -(right_ - args.line_margin)), left_ - args.line_margin)
        racingline.apply(track, offs_)
        print("the game's dry line applied: offsets %.1f to %.1f m (mean abs %.1f)" % (offs_.min(), offs_.max(), abs(offs_).mean()), flush=True)
    if args.line_smooth > 0 and not args.dry_line:
        print("racing line smoothed (%d passes, margin %.1f m): largest move %.1f m" % (args.line_smooth, args.line_margin, track.smooth_line(track.main, args.line_smooth, args.line_margin, pin_radius=args.line_pin)), flush=True)
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
            box_bias = 0.0
            if str(args.box_yaw_bias).lower() == "auto":
                try:
                    sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
                    import boxplan
                    trk_file = next((q for q in Path(args.aiw).parent.iterdir() if q.suffix.lower() == ".trk" and q.stem.lower() == Path(args.aiw).stem.lower()), None)
                    if trk_file is None:
                        raise FileNotFoundError("no .trk next to the AIW")
                    t_plan = time.time()
                    box_bias, box_gap, note = boxplan.plan(trk_file, box_start, box_heading, max(2.0, d0 - box_stop_lat) + 1.0)
                    print("garage exit: walls from the track meshes: %s -> yaw bias %+.0f deg (%.1f s)" % (note, box_bias, time.time() - t_plan), flush=True)
                except Exception as e:     # never stop a run for the planner: fall back to the straight heading
                    print("garage exit: wall planner unavailable (%s: %s), yaw bias 0" % (type(e).__name__, e), flush=True)
            else:
                box_bias = float(args.box_yaw_bias)
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

    steer_vmax = args.analog_slew if args.device == "stick" else args.wheel_hand_dps / (args.wheel_degrees / 2.0)   # wheel: the same hand speed covers fewer axis units when the rim turns 900 degrees for the whole range
    fol = {"steer": (RackModel(steer_vmax, args.analog_inertia, args.analog_friction, args.analog_stiction, args.analog_wn)
                     if args.analog_inertia > 0 else Follower(steer_vmax, args.analog_accel, -1.0, 1.0)),
           "throttle": pedal(args.analog_throttle_model),
           "brake": pedal(args.analog_brake_model)}

    def drive_analog():
        # steering X: right = above centre; throttle Z and brake Rx: below centre (each direction is half the axis)
        now_w = time.time()
        dt = min(0.1, now_w - shared["wt"])
        shared["wt"] = now_w
        x = fol["steer"].step(shared["steer"] * shared["scale"], dt)
        cap = args.analog_throttle[max(1, min(6, shared["gear"])) - 1] * (1.0 - args.analog_steer_ease * min(1.0, abs(shared["steer"])))
        if args.dyn:      # the wheels are watched instead (see the dynamic control in the main loop)
            cap = 1.0
        if args.tc_gain > 0:      # traction-aware: ease the throttle by the lateral load the car is carrying right now (measured, not commanded); the sliding car spins when the throttle stays high at the limit of grip
            cap *= max(args.tc_floor, 1.0 - args.tc_gain * max(0.0, shared.get("lat_load", 0.0) - args.tc_free))
        th = fol["throttle"].step(min(cap, shared["duty"]), dt)
        br = fol["brake"].step(shared["brake"], dt)
        xa = 0.5 + 0.5 * x
        if args.device == "wheel":
            steps = (1 << args.wheel_bits) - 1      # the wheel reports whole steps of its sensor, not any fraction
            xa = round(xa * steps) / steps
        joy.axis("X", xa)
        if args.device == "wheel":      # pedal sensors report whole steps (stock G25/G27 pedals: about 8 bits, source-reported, not verified)
            ps_n = (1 << args.wheel_pedal_bits) - 1
            th, br = round(th * ps_n) / ps_n, round(br * ps_n) / ps_n
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
    wheel_dev = analog and args.device == "wheel"

    def clutch_pedal():
        """Wheel device: the clutch is a foot pedal on the vJoy RY axis (below centre = pressed; the game binds Clutch In to (1, 10) in the wheel profile):
        pressed in 0.12 s, held for CLUTCH_HOLD_MS, let out over 0.25 s, in steps of the pedal's resolution."""
        steps_n = (1 << args.wheel_pedal_bits) - 1
        def put(v):
            joy.axis("RY", 0.5 - 0.5 * round(v * steps_n) / steps_n)
        t_start = time.time()
        while time.time() - t_start < 0.12:
            put((time.time() - t_start) / 0.12); time.sleep(0.01)
        put(1.0); time.sleep(max(0.0, CLUTCH_HOLD_MS / 1000.0 - 0.12 - 0.25))
        t_start = time.time()
        while time.time() - t_start < 0.25:
            put(1.0 - (time.time() - t_start) / 0.25); time.sleep(0.01)
        put(0.0)

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
            clutch = threading.Thread(target=clutch_pedal if wheel_dev else press_key, **({} if wheel_dev else {"args": ("q",), "kwargs": {"hold": CLUTCH_HOLD_MS}})); clutch.start()
            time.sleep(CLUTCH_LEAD_S)
            if analog:      # shift on the virtual joystick's buttons (1 up, 2 down); the clutch stays on keyboard Q unless the wheel device presses it on the RY axis
                joy.button(1 if gear < 1 else 2, True); time.sleep(0.1); joy.button(1 if gear < 1 else 2, False)
            else:
                press_key("alt" if gear < 1 else "ralt", hold=150)
            clutch.join()
            for _ in range(12):      # wait for the shift to show on the telemetry (at most 0.6 s) instead of a fixed 0.4 s
                if tm.read()["gear"] != gear:
                    break
                time.sleep(0.05)
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
        geo = {"events": [], "open": None, "last": -9.0, "n": 0, "surf_only": 0, "geo_only": 0, "both": 0, "margins": []}
        limit_events, limit_open, limit_last = [], None, -9.0      # track limits: all four wheels beyond the white line (no wheel on a ROAD or DRAIN surface)
        peak_pit = peak_all = 0.0
        impacts, last_impact, bumps = [], -1.0, 0
        kerbs = []
        contacts = []
        last_contact = -9.0
        KERB_STR = ("BRICK", "RMBL", "RMBB", "CURB", "KERB")
        kerb_until = -1.0
        rec = {"phase": None, "n": 0, "t": 0.0, "x": 0.0, "z": 0.0, "shift": 0.0, "still": None}
        bcap = {"cap": 1.0}
        padec = {}
        bslip = {}
        bev = {"on": False, "peak": 0.0, "lock": False, "bands": set()}
        learned = []        # (from lap distance, to lap distance, factor)
        meta = {"push": args.meta_start, "step": args.meta_step, "best": None, "best_push": args.meta_start, "t": None, "imp": 0, "lim": 0, "kerb": 0, "laps": []}
        mem_file = Path(__file__).resolve().parent / "gtr2_driving" / "learned" / ("%s_%s.json" % (Path(args.aiw).stem.lower(), (args.car_key or "car").replace("/", "_").lower()))
        gm = {}             # --grip-map: 20 m bin of lap distance -> factor on the planner's cornering grip
        gmh = {}
        guard_n = 0
        if args.grip_map and not args.no_memory and mem_file.exists():
            try:
                mem = json.loads(mem_file.read_text())
                gm.update({int(k_): float(v_) for k_, v_ in mem.get("gm", {}).items()})
                padec.update({int(k_): float(v_) for k_, v_ in mem.get("padec", {}).items()})
                if args.session_laps > 0 and mem.get("meta"):      # a later session (fresh tyres) starts from the push that worked, with a small step
                    meta["push"] = meta["best_push"] = min(args.meta_max, max(args.meta_min, float(mem["meta"].get("push", args.meta_start))))
                    meta["step"] = args.meta_step      # a new session starts with the full step again (the tyres are fresh)
                    meta["prev_best"] = mem["meta"].get("best_time")
                print("memory loaded from %s: %d grip bins, %d braking bands" % (mem_file.name, len(gm), len(padec)), flush=True)
            except Exception as e_:
                print("memory not read (%s)" % e_, flush=True)
        gms = {"bin": None, "use": 0.0, "slid": False, "wide": False, "up": 0, "down": 0, "t_dn": -9.0}

        def learn_hit(a, dist):
            if not args.learn_hits or a < args.learn_min:
                return
            for i, (lo, hi, f) in enumerate(learned):
                if abs((lo + hi) / 2 - (dist - 60)) < 90:
                    learned[i] = (lo, hi, max(0.55, f * 0.85))
                    print("hit learned again at lap distance %d: zone factor %.2f" % (dist, learned[i][2]), flush=True)
                    return
            learned.append((dist - 150, dist + 30, 0.85 if a < 40 else 0.7))
            print("hit learned at lap distance %d (%.0f m/s^2): zone %d..%d factor %.2f" % (dist, a, dist - 150, dist + 30, learned[-1][2]), flush=True)

        def hit_braking(sp_):
            """a hard hit while braking: the braking number of the speed band (and the next one up) was too bold there; take it down for the rest of the run"""
            if args.brake_adapt and shared.get("brake", 0.0) > 0.3 and padec:
                bb = int(min(sp_, 79.0) // 10)
                for b_ in (bb, bb + 1):
                    if b_ in padec:
                        padec[b_] = max(8.0, padec[b_] * 0.88)
                print("hit under braking at %.0f m/s: braking numbers of the bands %d and %d lowered" % (sp_, bb * 10, bb * 10 + 10), flush=True)

        def zone_factor(w):
            f = gm.get(int(w.dist // 20), 1.0) if args.grip_map else 1.0
            for lo, hi, ff in args.slow_zone:
                if lo <= w.dist <= hi:
                    f = min(f, ff)
            for lo, hi, ff in learned:
                if lo <= w.dist <= hi:
                    f = min(f, ff)
            return f
        sid = {"hist": [], "k": {}}      # steering identification (--steer-id): samples of yaw rate per steering command per m/s, by speed bin
        stn = {"g": {},"last": 0.0, "hist": [], "lat2": 0.0, "lat_n": 0, "lats": []}      # Stanley follower: learned steering gain per speed bin, cross-track statistics
        gearcar = cargears.load(args.car_key) if args.gear_opt and args.car_key else None
        print("gear optimisation: %s (car key %r, option %s)" % ("on, gears %s, limit %.0f" % ([round(x, 2) for x in gearcar["gears"]], gearcar["limit"]) if gearcar else "off", args.car_key, args.gear_opt), flush=True)
        live = {"a_lat": args.live_lat, "a_brk": args.live_brake, "kk": args.live_k, "sx": 0.0, "sy": 0.0, "sxx": 0.0, "sxy": 0.0, "n": 0, "t": 0.0, "lat_lo": 99.0, "lat_hi": 0.0, "brk_lo": 99.0, "brk_hi": 0.0, "pen": 0}
        dyn = {"t": 0.0, "tc": 1.0, "abs": 1.0, "radius": [], "base": [], "tc_n": 0, "thr_n": 0, "abs_n": 0, "brk_n": 0}
        pending = None      # the last impact on the main line, judged one sample later: a single-sample spike on plain road is a seam in the track mesh, not a collision
        steer_travel, last_steer = 0.0, 0.0      # sum of |change of the steering command| per loop on the main line: a jerkiness measure
        off_buckets = {}
        off_lat = {}
        max_lat = 0.0
        STAGE_MOVED = []
        merged_at = None
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
                if args.session_laps > 0:      # a lap is done: judge it and adjust the push for the next one
                    n_imp = len([i_ for i_ in impacts if not i_.get("pit")])
                    n_lim = len([e_ for e_ in limit_events if e_["seconds"] >= 0.06])
                    clean_ = False
                    if meta["t"] is not None:      # the first change only ends the out lap
                        lt_ = now - meta["t"]
                        d_imp, d_lim, d_kerb = n_imp - meta["imp"], n_lim - meta["lim"], len(kerbs) - meta["kerb"]
                        clean_ = d_imp == 0 and d_lim == 0 and d_kerb <= 5
                        used_ = meta["push"]
                        if clean_:
                            meta["bad"] = 0
                        if clean_ and (meta["best"] is None or lt_ < meta["best"]):
                            meta["best"], meta["best_push"] = lt_, used_
                            meta["push"] = min(args.meta_max, used_ + meta["step"])
                        elif clean_:
                            meta["push"] = min(args.meta_max, meta["best_push"] + 0.5 * meta["step"])
                            meta["step"] = max(0.004, meta["step"] * 0.7)
                        else:      # an unclean lap: the maps already slow the corner where it happened (track-limit and hit responses), so the push is held; only a second unclean lap in a row takes it down
                            meta["bad"] = meta.get("bad", 0) + 1
                            if meta["bad"] >= 2:
                                meta["push"] = max(args.meta_min, used_ - meta["step"])
                                meta["step"] = max(0.004, meta["step"] * 0.7)
                            else:
                                meta["push"] = used_
                        gmv_ = list(gm.values())
                        diag_ = {"gm_mean": round(sum(gmv_) / len(gmv_), 3) if gmv_ else 1.0, "gm_min": round(min(gmv_), 2) if gmv_ else 1.0, "learned": len(learned), "learned_min": round(min([f_ for _, _, f_ in learned], default=1.0), 2),
                                 "brake_mean": round(sum(padec.values()) / len(padec), 2) if padec else None, "tyre_wear": round(sum(w_["wear"] for w_ in tel["wheels"]) / 4, 4), "tyre_temp": round(sum(sum(w_["temps"]) / 3 for w_ in tel["wheels"]) / 4, 1)}
                        print("SESSION diag: " + " ".join("%s=%s" % kv_ for kv_ in diag_.items()), flush=True)
                        meta["still"] = 0 if (clean_ and meta["best"] is not None and lt_ <= meta["best"] + 1e-9) else meta.get("still", 0) + 1
                        if meta["still"] >= 3 and meta["step"] < args.meta_step:      # no gain for three laps: the step has shrunk too far to explore, widen it again
                            meta["step"] = min(args.meta_step, meta["step"] * 2.0)
                            meta["still"] = 0
                        meta["laps"].append({"lap": tel["lap"] - 1, "time": round(lt_, 2), "clean": clean_, **diag_, "impacts": d_imp, "track_limits": d_lim, "kerbs": d_kerb, "push": round(used_, 3), "next_push": round(meta["push"], 3)})
                        print("SESSION lap %d: %.2f s, %s (impacts %d, track limits %d, kerb strikes %d) push %.3f -> %.3f, best %s" % (tel["lap"] - 1, lt_, "clean" if clean_ else "NOT clean", d_imp, d_lim, d_kerb, used_, meta["push"], ("%.2f" % meta["best"]) if meta["best"] else "none"), flush=True)
                    meta["t"], meta["imp"], meta["lim"], meta["kerb"] = now, n_imp, n_lim, len(kerbs)
                    if clean_ and args.brake_adapt and padec:      # braking numbers lowered by a hit under braking heal with clean laps too (the probe raises them only where the pedal stayed under 90%)
                        for bb_ in list(padec):
                            padec[bb_] = min(22.0, padec[bb_] * (1.0 + args.brake_heal))
                    if learned:      # zones learned from hits heal with the laps: a clean lap gives 5% back, a hit again takes it away
                        learned[:] = [(lo_, hi_, min(1.0, f_ + args.learn_heal)) for lo_, hi_, f_ in learned if f_ + args.learn_heal < 1.0]
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
            shared["lat_load"] = abs(tel["accel"][0])
            a_long = abs(tel["accel"][2])
            if shared.get("brake", 0.0) > 0.1:
                shared["brake_t"] = now
            if now - shared.get("brake_t", -9.0) < 0.5 and chain is track.main and args.brake_allow > 0:     # braking now or within the last half second (the pedal eases off before the load does)
                a_long = max(0.0, a_long - max(args.brake_allow, 1.1 * padec.get(int(min(speed, 79.0) // 10), 0.0) if (args.brake_adapt and padec) else args.brake_allow))      # live: the braking the car has shown it can do is not a collision either     # our own braking (a GT car stops at 11 to 15 m/s^2 with 1.0 g of grip and downforce) is not a collision: only what is beyond it counts
            a_h = math.hypot(tel["accel"][0], a_long)
            peak_all = max(peak_all, a_h)
            hist = shared.setdefault("a_hist", [])
            base = sorted(hist[-6:])[len(hist[-6:]) // 2] if hist else a_h
            hist.append(a_h)
            del hist[:-12]
            spiky = args.impact_spike <= 0 or a_h - base >= args.impact_spike or a_h > 2 * args.impact_accel      # a sustained load (cornering at 1.3 g, braking) is not a collision: only a jump over the last half second counts
            if chain is track.pit:
                peak_pit = max(peak_pit, a_h)
            if pending is not None and now > pending[2]:
                entry, peak, _t, kerb = pending
                pending = None
                if a_h < 0.3 * peak and not kerb and entry in impacts:     # gone by the next sample, nothing but road under the wheels: Donington's start/finish joins (44 to 92 m/s^2 at 52 m/s, steering 0) and Spa's (35 to 46 braking), one 20 ms spike each; the Monza Junior bollard hit lasts two samples
                    impacts.remove(entry)
                    bumps += 1
                    print("t=%5.1f BUMP (single-sample seam, %.1f m/s^2 at (%.1f, %.1f)): not counted as an impact" % (entry["t"], peak, entry["x"], entry["z"]), flush=True)
            if chain is track.main and a_h >= args.contact_min and now - last_contact > 0.3 and (a_h - base >= 3.0 or abs(tel["accel"][1]) >= 0.5 * args.contact_min):
                last_contact = now      # measure every jolt (also the small ones under the hit limits) with what is under the wheels, to set the limits from data (gtr2-contact-stats.py)
                kind_c = "impact" if (a_h > args.impact_accel and (a_h > args.kerb_max_accel or not (abs(tel["accel"][1]) >= args.kerb_vert_share * a_h or any(any(k in sf for k in KERB_STR) for sf in tel["surfaces"])))) else ("kerb" if a_h > args.impact_accel else "jolt")
                contacts.append({"t": round(now - t0, 2), "x": round(x, 1), "z": round(z, 1), "dist": int(w.dist), "a": round(a_h, 1), "vert": round(abs(tel["accel"][1]), 1), "lat": round(abs(tel["accel"][0]), 1), "long": round(abs(tel["accel"][2]), 1), "speed": round(speed, 1), "kind": kind_c, "surfaces": sorted(set(tel["surfaces"]))})
            if a_h > args.impact_accel and now - last_impact > 0.3 and (box_target is not None or merging) and abs(tel["accel"][1]) >= 0.3 * a_h:
                last_impact = now      # in the garage exit only: a jolt with a big vertical part is the lip at the garage mouth, not a wall (Zhuhai 4: 15 to 54 m/s^2 with vert 8 to 17; Anderstorp's pillar: 70 with vert 0.5). Everywhere else every jolt counts as an impact
                bumps += 1
                print("t=%5.1f BUMP %.1f m/s^2 at (%.1f, %.1f) speed %.1f accel (lat %.1f, vert %.1f, long %.1f)" % (now - t0, a_h, x, z, speed, tel["accel"][0], tel["accel"][1], tel["accel"][2]), flush=True)
            elif a_h > (args.impact_track if args.impact_track > 0 else args.impact_accel) and now - last_impact > 0.3 and spiky and chain is track.main and a_h <= args.kerb_max_accel and (abs(tel["accel"][1]) >= args.kerb_vert_share * a_h or any(any(k in sf for k in ("BRICK", "RMBL", "RMBB", "CURB", "KERB")) for sf in tel["surfaces"])):
                last_impact = now      # a kerb strike (real racing has them): a vertical-dominated jolt, or kerb/rumble surfaces under a wheel, on the racing line and below --kerb-max-accel; counted apart from impacts, the lap check allows a few
                kerbs.append({"t": round(now - t0, 2), "x": round(x, 1), "z": round(z, 1), "a": round(a_h, 1), "vert": round(abs(tel["accel"][1]), 1), "speed": round(speed, 1)})
                if a_h >= args.learn_kerb_min:      # kerb strikes are part of racing: only a hard one teaches the planner anything
                    learn_hit(a_h, w.dist)
                    hit_braking(speed)
                print("t=%5.1f KERB %.1f m/s^2 at (%.1f, %.1f) speed %.1f accel (lat %.1f, vert %.1f, long %.1f)" % (now - t0, a_h, x, z, speed, tel["accel"][0], tel["accel"][1], tel["accel"][2]), flush=True)
            elif a_h > (args.impact_track if (args.impact_track > 0 and chain is track.main) else args.impact_accel) and now - last_impact > 0.3 and spiky:
                last_impact = now
                impacts.append({"t": round(now - t0, 2), "x": round(x, 1), "z": round(z, 1), "a": round(a_h, 1), "pit": chain is track.pit})
                if chain is track.main:
                    learn_hit(a_h, w.dist)
                    hit_braking(speed)
                if args.live and args.live_adapt:
                    live["a_lat"] *= 0.93
                    live["a_brk"] *= 0.93
                    live["pen"] += 1
                if chain is track.main:
                    pending = (impacts[-1], a_h, now, any(any(k in sf for k in ("BRICK", "RMBL", "RMBB", "CURB", "KERB")) or any(bad in sf for bad in OFF_ROAD) for sf in tel["surfaces"]))
                print("t=%5.1f IMPACT %.1f m/s^2 at (%.1f, %.1f) speed %.1f accel (lat %.1f, vert %.1f, long %.1f) yaw %.1f" % (now - t0, a_h, x, z, speed, tel["accel"][0], tel["accel"][1], tel["accel"][2], tel["yaw"]), flush=True)
            if any(any(bad in s for bad in OFF_ROAD) for s in tel["surfaces"]):
                off_samples += 1
                if chain is track.main:      # where on the lap (20 m buckets of lap distance) and on what surface
                    key = "%d %s" % (int(w.dist // 20) * 20, ",".join(sorted({s for s in tel["surfaces"] if any(b in s for b in OFF_ROAD)})))
                    off_buckets[key] = off_buckets.get(key, 0) + 1
                    off_lat.setdefault(key, []).append(lat)      # lateral offset from the line at those samples (sign: see trackmap.lateral)
            if args.geo_limits and chain is track.main and speed > 3.0:
                yr_ = math.radians(tel["yaw"])
                hxc, hzc = -math.sin(yr_), -math.cos(yr_)
                px_, pz_ = -hzc, hxc      # the lateral direction of Track.lateral, for the car's heading
                side_out = {"l": 0, "r": 0}
                gap_min = 99.0
                for fa_, fb_ in ((1.35, 1), (1.35, -1), (-1.35, 1), (-1.35, -1)):      # four tyres: 1.35 m ahead or behind the centre, either side
                    wx_, wz_ = x + fa_ * hxc + fb_ * args.wheel_track / 2 * px_, z + fa_ * hzc + fb_ * args.wheel_track / 2 * pz_
                    wp_ = chain[track.nearest(chain, wx_, wz_, near=k, window=40)]
                    lt_ = track.lateral(wp_, wx_, wz_)
                    left_edge, right_edge = wp_.left - wp_.off, wp_.right + wp_.off      # the white lines, from the (shifted) line
                    if lt_ - args.tyre_half > left_edge:
                        side_out["l"] += 1
                    if lt_ + args.tyre_half < -right_edge:
                        side_out["r"] += 1
                    gap_min = min(gap_min, left_edge - lt_, lt_ + right_edge)      # least distance from a tyre centre to a white line (negative: beyond it)
                geo_out = side_out["l"] == 4 or side_out["r"] == 4
                surf_out = all(not any(k_ in sf.upper() for k_ in ("ROAD", "DRAIN")) for sf in tel["surfaces"])
                geo["n"] += 1
                geo["both"] += 1 if (geo_out and surf_out) else 0
                geo["geo_only"] += 1 if (geo_out and not surf_out) else 0
                geo["surf_only"] += 1 if (surf_out and not geo_out) else 0
                any_off = any(not any(k_ in sf.upper() for k_ in ("ROAD", "DRAIN")) for sf in tel["surfaces"])
                geo.setdefault("m_off" if any_off else "m_on", []).append(round(gap_min, 2))      # nearest white line (tyre centre) while a tyre is off the road surface / while all are on it
                if surf_out:
                    geo["margins"].append(round(gap_min, 2))      # where the white line is, in tyre metres, when the surface rule says off
                if geo_out:
                    if geo["open"] is None or now - geo["last"] > 0.5:
                        geo["open"] = {"t": round(now - t0, 2), "x": round(x, 1), "z": round(z, 1), "dist": int(w.dist), "seconds": 0.0, "surface": ",".join(sorted(set(tel["surfaces"])))}
                        geo["events"].append(geo["open"])
                    geo["open"]["seconds"] = round(geo["open"]["seconds"] + (now - geo["last"] if geo["last"] > 0 and now - geo["last"] < 0.2 else 0.02), 3)
                    geo["last"] = now
            if chain is track.main:
                if all(not any(k in sf.upper() for k in ("ROAD", "DRAIN")) for sf in tel["surfaces"]):
                    if limit_open is None or now - limit_last > 0.5:
                        limit_open = {"t": round(now - t0, 2), "x": round(x, 1), "z": round(z, 1), "dist": int(w.dist), "seconds": 0.0, "surface": ",".join(sorted(set(tel["surfaces"])))}
                        limit_events.append(limit_open)
                        if args.grip_map:      # live response: the corners before this point were taken too fast to stay inside the white lines; take their grip factor down now and for the next pass
                            for bb in range(int(w.dist // 20) - 6, int(w.dist // 20) + 1):
                                gm[bb] = max(args.gm_min, gm.get(bb, 1.0) * (1.0 - args.gm_limit))
                            gms["down"] += 1
                    limit_open["seconds"] = round(now - t0 - limit_open["t"], 2)
                    limit_last = now
            if chain is track.main:
                max_lat = max(max_lat, abs(lat))

            look = args.lookahead[0] + args.lookahead[1] * speed
            if chain is track.pit:
                # a short aim distance in the pit lane: the narrow winding service roads at Estoril and Anderstorp (4 to 6 m wide, 90 degree
                # bends) were cut by 1.5 m or more with the circuit's 5 m + 1.2 per m/s, which put the car into the wall
                look = max(args.pit_lookahead[0] + args.pit_lookahead[1] * speed, 1.5 * abs(lat))
            target = track.ahead(chain, k, look) if args.aim_step else track.ahead_point(chain, k, look, x, z)
            if args.aim_comp != 0.0 and chain is track.main:
                # aiming at a point on a bend cuts the corner by about look x turn / 8: move the aim point outward by that much (aim_comp 1 = all of it)
                a0 = chain[k]
                turn = math.atan2(a0.hx * target.hz - a0.hz * target.hx, a0.hx * target.hx + a0.hz * target.hz)      # positive: turning to the road's right
                sag = args.aim_comp * look * turn / 8.0
                sag = max(-args.aim_comp_max, min(args.aim_comp_max, sag))
                target = SimpleNamespace(x=target.x + target.hz * sag, z=target.z - target.hx * sag, hx=target.hx, hz=target.hz,
                                         left=target.left, right=target.right, dist=target.dist)
            edge_over = 0.0
            if args.edge_guard > 0.0 and chain is track.main:
                # live track-limit guard: the distance from the car's side to each white line (road width either side of the file's line,
                # corrected for the racing line's own sideways shift); inside the guard distance, steer back towards the line and ease off
                half = args.car_half_width
                left_room = (w.left - w.off) - lat - half          # positive lat and w.off point to the car's physical left
                right_room = (w.right + w.off) + lat - half
                room = min(right_room, left_room)
                if room < args.edge_room:
                    edge_over = args.edge_room - room
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
                    want, pull = box_heading + box_bias, 0.0
                else:
                    want, pull = track.yaw_of(box_target.x - x, box_target.z - z), 0.0
            herr = wrap(want - yaw + pull)
            if edge_over > 0.0:
                herr += args.edge_guard * edge_over * (1.0 if lat > 0.0 else -1.0)      # the heading error already has the sign of the offset (measured): add to it
            if merging and (chain is not track.pit or (abs(herr) < 15.0 and abs(lat) < 2.5)):
                print("t=%5.1f merged onto the pit lane line" % (now - t0), flush=True)
                merging = False
                merged_at = now
            if args.stop_at_merge and merged_at is not None and now - merged_at >= args.stop_at_merge:
                result["outcome"] = "merged"; break
            shared["scale"] = args.merge_steer if (merging or box_target is not None or chain is track.pit) else args.analog_steer   # slow in the pit lane: full lock (Anderstorp's 90 degree bend, 5 to 6 m wide)
            if args.follower in ("stanley", "designed") and chain is track.main and not merging and box_target is None:
                # Stanley follower with curvature feed-forward (gtr2_driving/follower.py, tuned offline in gtr2-follower-sim.py): the steering gain is the
                # measured per speed table; --st-learn adapts it per speed bin from the car's own yaw response (it collapsed once while the car was oscillating)
                sp = max(speed, 1.0)
                gl = follower.steer_gain(sp)
                if args.st_learn:
                    b = int(min(sp, 79.0) // 10)
                    gl = stn["g"].get(b, gl)
                    cmd = shared["steer"]
                    stn["hist"].append(cmd)
                    del stn["hist"][:-8]
                    if abs(cmd) > 0.08 and speed > 8.0 and abs(tel["accel"][0]) < 9.0 and len(stn["hist"]) >= 8 and max(stn["hist"]) - min(stn["hist"]) < 0.05 and shared["brake"] < 0.1 and abs(lat) < 1.5:
                        meas = math.atan2(args.wheelbase * math.radians(yawrate), sp) / cmd
                        if 0.5 * gl < meas < 1.5 * gl:
                            stn["g"][b] = gl + 0.02 * (meas - gl)
                            gl = stn["g"][b]
                if args.follower == "designed":
                    shared["steer"] = follower.designed(track, chain, k, x, z, yaw, speed, yawrate, lat, wn=args.st_wn, zeta=args.st_zeta, ff=args.st_ff, preview=args.st_preview, wheelbase=args.wheelbase, gain=gl)
                else:
                    shared["steer"] = follower.stanley(track, chain, k, x, z, yaw, speed, yawrate, lat, k_cross=args.st_k, ks=args.st_ks, ff=args.st_ff, preview=args.st_preview, damp=args.st_damp, wheelbase=args.wheelbase, gain=gl)
            else:
                sl_ = 1.0
                if args.steer_live and chain is track.main and not merging and box_target is None:
                    # live loop gain: the car's measured yaw response per steering command at this speed (steer-id) against a reference response, so the
                    # heading loop has about the same time constant at every speed
                    b_ = int(min(speed, 79.0) // 10)
                    ks_ = sid["k"].get(b_, [])
                    if len(ks_) >= 20:
                        y_ = sorted(ks_[-200:])[len(ks_[-200:]) // 2] * (b_ * 10 + 5.0)
                        sl_ = max(args.steer_live_min, min(args.steer_live_max, args.steer_live_ref / max(y_, 0.1)))
                shared["steer"] = max(-1.0, min(1.0, sl_ * (herr / args.steer_gain - yawrate / args.damping)))
            if args.steer_id and chain is track.main:
                # online identification of the steering: yaw rate per unit of command per metre/second (k = yaw rate / (steer x speed)), from steady stretches only
                cmd_ = shared["steer"]
                sid["hist"].append(cmd_)
                del sid["hist"][:-12]
                if abs(cmd_) > 0.06 and speed > 6.0 and len(sid["hist"]) >= 12 and max(sid["hist"]) - min(sid["hist"]) < 0.04 and shared["brake"] < 0.1 and abs(tel["accel"][0]) < 9.0:
                    sid["k"].setdefault(int(min(speed, 79.0) // 10), []).append(math.radians(yawrate) / (cmd_ * speed))
            if chain is track.main and speed > 10.0:
                stn["lat2"] += lat * lat
                stn["lat_n"] += 1
                stn["lats"].append(abs(lat))
            if chain is track.main:
                steer_travel += abs(shared["steer"] - last_steer)
            last_steer = shared["steer"]

            decel_plan = args.decel
            if args.brake_adapt and padec:
                db = lambda sp_: int(min(sp_, 79.0) // 10)
                decel_plan = min(padec.get(db(speed), args.decel), padec.get(db(speed / 2.0), args.decel))
            window = 25.0 + speed * speed / (2.0 * decel_plan)
            if args.live and chain is track.main:
                a_brk_p = decel_plan if args.brake_adapt else live["a_brk"]      # the braking map's number when it is on
                window = 25.0 + speed * speed / (2.0 * a_brk_p * (1.0 + args.live_brake_k * speed * speed))
                corner_v, _ = track.speed_limit_live(chain, k, window, live["a_lat"], live["kk"], a_brk_p, kb=args.live_brake_k, scale=zone_factor if (args.slow_zone or learned or args.grip_map) else None)
            else:
                corner_v, _ = track.speed_limit(joined if (chain is track.pit and joined) else chain, k, window, args.pit_lat_accel if chain is track.pit else (lat_at if zones else ((lambda w: args.lat_accel * zone_factor(w)) if (args.slow_zone or learned or args.grip_map) else args.lat_accel)), decel_plan, tight_radius=args.tight_radius, tight_speed=args.tight_speed)
            if args.grip_map and chain is track.main and last_lap == start_lap:
                corner_v *= args.outlap_scale
            elif args.session_laps > 0 and chain is track.main:
                corner_v *= meta["push"]
            in_lane = chain is track.pit and (lane_end_k is None or k <= lane_end_k)
            if chain is track.pit and not in_lane and not lane_end_said:
                lane_end_said = True
                print("t=%5.1f past the pit lane exit (waypoint %d of %d): pit speed cap off" % (now - t0, k, len(chain)), flush=True)
            vmax = args.pit_speed if in_lane else args.speed
            if chain is track.pit and abs(lat) > 3.0:
                vmax = min(vmax, 5.0)
            target_v = max(3.0, min(vmax, corner_v))
            if edge_over > 0.0:
                target_v = max(4.0, target_v * max(0.6, 1.0 - args.edge_slow * edge_over))
            if box_target is not None:
                target_v = min(target_v, args.box_speed)
            elif merging:
                target_v = min(target_v, args.merge_speed)
            over = abs(herr) - args.guard_deg
            if over > 0:
                target_v = max(4.0, target_v * max(args.guard_floor, 1.0 - over / args.guard_span))
            shared["duty"] = max(0.0, min(1.0, 0.45 + args.throttle_gain * (target_v - speed))) if speed > 1.5 else 1.0
            shared["brake"] = max(0.0, min(args.brake_max, args.brake_gain * (speed - target_v - args.brake_deadband)))
            if box_target is not None or merging:       # creeping out of the box: gentle throttle (a full launch reached 6.5 m/s in 3 m)
                cap = args.box_throttle
                if box_target is not None and not (speed < 0.4 and now - t0 > 2.5):      # the straight run out of the box: a walking-pace roll over the sill at the garage mouth (0.4 reached it at 3.5 to 4 m/s and jolted 15 to 54 m/s^2); 0.15 gives 2 m/s, no jolt. A car that has not moved after 2.5 s gets the old ceiling
                    cap = min(cap, args.box_straight_throttle)
                shared["duty"] = min(shared["duty"], cap)
            if args.dyn and chain is track.main and analog:
                # Real-time wheel monitoring (rFactor 1 shared-memory wheels: rotation rad/s, grip fraction), see docs/analog-driving.md.
                # Front wheels of this rear-drive car roll freely, so rear/front rotation measures driven-wheel slip; braking slip is
                # 1 - wheel speed (rotation x calibrated rolling radius) / car speed. The cut is immediate, the recovery is a ramp.
                wl = tel["wheels"]
                fr = (abs(wl[0]["rot"]) + abs(wl[1]["rot"])) / 2.0
                rr = (abs(wl[2]["rot"]) + abs(wl[3]["rot"])) / 2.0
                dt_d = max(0.001, min(0.2, now - dyn["t"]))
                dyn["t"] = now
                free = shared["brake"] < 0.02 and abs(tel["accel"][0]) < 2.5 and abs(tel["accel"][2]) < 3.0 and speed > 10.0 and fr > 1.0
                if free:
                    dyn["radius"].append(speed / fr)
                    dyn["base"].append(rr / fr - 1.0)
                    del dyn["radius"][:-300], dyn["base"][:-300]
                radius = sorted(dyn["radius"])[len(dyn["radius"]) // 2] if len(dyn["radius"]) >= 20 else 0.322
                base = sorted(dyn["base"])[len(dyn["base"]) // 2] if len(dyn["base"]) >= 20 else -0.03
                slip_drive = (rr / fr - 1.0 - base) if fr > 3.0 else 0.0
                target = max(args.dyn_min, 1.0 - args.dyn_gain * max(0.0, slip_drive - args.dyn_slip))
                if min(wl[2]["grip"], wl[3]["grip"]) < args.dyn_grip:
                    target = min(target, 0.5)
                dyn["tc"] = target if target < dyn["tc"] else min(1.0, dyn["tc"] + args.dyn_recover * dt_d)
                # the rear axle runs about 10% slower than the car in every hard stop (brake bias), so it gets its own, looser tolerance
                slip_f = max(1.0 - abs(w["rot"]) * radius / max(speed, 0.1) for w in wl[:2]) if speed > 8.0 else 0.0
                slip_r = max(1.0 - abs(w["rot"]) * radius / max(speed, 0.1) for w in wl[2:]) if speed > 8.0 else 0.0
                excess = max(slip_f - args.dyn_brake_slip, slip_r - args.dyn_rear_brake_slip, 0.0)
                target_b = max(args.dyn_min_brake, 1.0 - args.dyn_gain * excess)
                if min(w["grip"] for w in wl[:2]) < args.dyn_grip:
                    target_b = min(target_b, 0.6)
                dyn["abs"] = target_b if target_b < dyn["abs"] else min(1.0, dyn["abs"] + args.dyn_recover * dt_d)
                if shared["duty"] > 0.0:
                    dyn["tc_n"] += 1 if dyn["tc"] < 0.9 else 0
                    dyn["thr_n"] += 1
                if shared["brake"] > 0.1:
                    dyn["abs_n"] += 1 if dyn["abs"] < 0.9 else 0
                    dyn["brk_n"] += 1
                shared["duty"] *= dyn["tc"]
                shared["brake"] *= dyn["abs"]
            if args.brake_ctl and chain is track.main and analog:
                dt_b = max(0.001, min(0.2, now - bcap.get("t", now - 0.02)))
                bcap["t"] = now
                wl_b = tel["wheels"]
                rad = sorted(dyn["radius"])[len(dyn["radius"]) // 2] if len(dyn["radius"]) >= 20 else 0.322
                sf = max(1.0 - abs(w_["rot"]) * rad / max(speed, 0.1) for w_ in wl_b[:2]) if speed > 8.0 else 0.0
                if shared["brake"] > 0.05:
                    bcap["cap"] = max(0.25, min(1.0, bcap["cap"] + args.brake_ki * (args.brake_slip - sf) * dt_b))
                    if args.brake_adapt and shared["brake"] >= 0.9 * bcap["cap"] and speed > 12.0 and 0.5 * args.brake_slip < sf < 1.6 * args.brake_slip:
                        bb = int(min(speed, 79.0) // 10)
                        cur = padec.get(bb, args.decel)
                        padec[bb] = max(8.0, min(20.0, cur + 0.04 * (0.92 * tel["accel"][2] - cur)))
                    shared["brake"] = min(shared["brake"], bcap["cap"])
                else:
                    bcap["cap"] = min(1.0, bcap["cap"] + 2.0 * dt_b)
                if args.brake_adapt:      # probe: after each braking zone, if the pedal never needed to go near full and no wheel locked, the planner was braking earlier than the car needs: raise its braking number for the speed bands passed; if a wheel locked, lower it
                    if shared["brake"] > 0.05:
                        bev["on"] = True
                        bev["peak"] = max(bev["peak"], shared["brake"])
                        hb_ = bslip.setdefault(int(min(sf, 0.6) * 20), [0, 0.0])      # front slip histogram while braking (0.05 steps) with the mean deceleration
                        hb_[0] += 1
                        hb_[1] += -tel["accel"][2]
                        bev["lock"] = bev["lock"] or sf > 2.5 * args.brake_slip      # a front wheel well past the slip the brake holds (the rear axle runs slow in every stop, so only the front counts)
                        bev["bands"].add(int(min(speed, 79.0) // 10))
                    elif bev["on"] and shared["brake"] < 0.02:
                        if bev["lock"]:
                            for bb in bev["bands"]:
                                padec[bb] = max(8.0, padec.get(bb, args.decel) * 0.95)
                        elif bev["peak"] < 0.9 and len(bev["bands"]) >= 2:
                            for bb in bev["bands"]:
                                padec[bb] = min(22.0, padec.get(bb, args.decel) * 1.08)
                        bev.update(on=False, peak=0.0, lock=False, bands=set())
            if any(any(k_ in sf_ for k_ in KERB_STR) for sf_ in tel["surfaces"]):
                kerb_until = now + args.kerb_hold
            if args.limit_guard and chain is track.main and speed > 8.0:
                n_off = sum(1 for sf_ in tel["surfaces"] if not any(k_ in sf_.upper() for k_ in ("ROAD", "DRAIN")))
                if n_off >= 3:
                    shared["duty"] = min(shared["duty"], args.limit_guard_throttle)
                    shared["steer"] = max(-1.0, min(1.0, shared["steer"] + math.copysign(args.limit_guard_steer * (1 if n_off == 3 else 4), lat)))
                    guard_n += 1
            if args.kerb_mode and now < kerb_until and chain is track.main:
                shared["duty"] = min(shared["duty"], args.kerb_throttle)
                shared["brake"] *= args.kerb_brake
                shared["steer"] *= args.kerb_steer
            if args.grip_map and chain is track.main and speed > 8.0:
                wl_g = tel["wheels"]
                b_now = int(w.dist // 20)
                cap_g = args.lat_accel * zone_factor(w) * (args.outlap_scale ** 2 if last_lap == start_lap else 1.0)      # the out lap plans less: the use is measured against that
                if gms["bin"] is not None and b_now != gms["bin"]:      # a 20 m bin is done: raise its factor if the car used the grip cleanly
                    if not gms["slid"] and not gms["wide"] and gms["use"] >= args.gm_use:
                        gm[gms["bin"]] = min(args.gm_max, gm.get(gms["bin"], 1.0) + args.gm_up)
                        gms["up"] += 1
                    elif not gms["slid"] and not gms["wide"] and gm.get(gms["bin"], 1.0) < 1.0:      # a clean pass heals an earlier penalty even where the grip was not used fully
                        gm[gms["bin"]] = min(1.0, gm[gms["bin"]] + args.gm_heal)
                    gms.update(use=0.0, slid=False, wide=False)
                gms["bin"] = b_now
                gms["use"] = max(gms["use"], abs(tel["accel"][0]) / max(cap_g, 1.0))
                front = wl_g[0] if wl_g[0]["load"] >= wl_g[1]["load"] else wl_g[1]
                rear = wl_g[2] if wl_g[2]["load"] >= wl_g[3]["load"] else wl_g[3]
                loaded = abs(tel["accel"][0]) > 0.5 * cap_g
                if loaded:      # distribution of the outer tyres' grip fraction against the lateral load (what "sliding" looks like on this car)
                    for nm_, wh_ in (("f", front), ("r", rear)):
                        hb = gmh.setdefault("%s%d" % (nm_, min(9, max(0, int(wh_["grip"] * 10)))), [0, 0.0])
                        hb[0] += 1
                        hb[1] += abs(tel["accel"][0])
                if abs(lat) > args.gm_line:
                    gms["wide"] = True
                if loaded and min(front["grip"], rear["grip"]) < args.gm_slide:
                    gms["slid"] = True
                    if gms.get("dn_bin") != b_now:      # once per 20 m bin and pass: this bin and the two before it (entered too fast)
                        gms["dn_bin"] = b_now
                        gms["down"] += 1
                        for bb in range(b_now - 2, b_now + 1):
                            gm[bb] = max(args.gm_min, gm.get(bb, 1.0) * (1.0 - args.gm_down))
            if args.live and chain is track.main and speed > 8.0:
                wl = tel["wheels"]
                dtl = max(0.001, min(0.2, now - live["t"]))
                live["t"] = now
                v2 = speed * speed
                fz = sum(w["load"] for w in wl)
                if args.live_fit and fz > 1000.0:      # least squares Fz = F0 + F1 v^2 with a slow forgetting: kk = F1 / F0
                    for key, val in (("sx", v2), ("sy", fz), ("sxx", v2 * v2), ("sxy", v2 * fz)):
                        live[key] = live[key] * 0.9995 + val
                    live["n"] = live["n"] * 0.9995 + 1.0
                    den = live["n"] * live["sxx"] - live["sx"] ** 2
                    if live["n"] > 300 and den > 1e-3 * live["n"] * live["sxx"]:
                        f1 = (live["n"] * live["sxy"] - live["sx"] * live["sy"]) / den
                        f0 = (live["sy"] - f1 * live["sx"]) / live["n"]
                        if f0 > 3000.0 and f1 > 0.0:
                            live["kk"] = max(0.0, min(6e-4, f1 / f0))
                lat_cap, brk_cap = live["a_lat"] * (1.0 + live["kk"] * v2), live["a_brk"] * (1.0 + args.live_brake_k * v2)
                outer = wl[0] if wl[0]["load"] >= wl[1]["load"] else wl[1]
                if args.live_adapt and abs(tel["accel"][0]) > 0.6 * lat_cap:
                    if outer["grip"] < args.live_grip_lo:
                        live["a_lat"] *= 1.0 - 0.6 * dtl
                    elif outer["grip"] > 0.92 and abs(tel["accel"][0]) > 0.9 * lat_cap:
                        live["a_lat"] *= 1.0 + 0.10 * dtl
                if args.live_adapt and shared["brake"] > 0.5:
                    if dyn["abs"] < 0.9:
                        live["a_brk"] *= 1.0 - 0.8 * dtl
                    elif -tel["accel"][2] > 0.9 * brk_cap and dyn["abs"] > 0.97:
                        live["a_brk"] *= 1.0 + 0.10 * dtl
                live["a_lat"] = max(6.0, min(args.live_max, live["a_lat"]))
                live["a_brk"] = max(6.0, min(args.live_max, live["a_brk"]))
                live["lat_lo"], live["lat_hi"] = min(live["lat_lo"], live["a_lat"]), max(live["lat_hi"], live["a_lat"])
                live["brk_lo"], live["brk_hi"] = min(live["brk_lo"], live["a_brk"]), max(live["brk_hi"], live["a_brk"])
            if analog:
                shared["gear"] = tel["gear"]

            n += 1
            if now - t0 < args.trace:
                print("T %5.2f x=%7.1f z=%7.1f yaw=%7.1f rate=%+6.1f v=%5.2f herr=%+6.1f steer=%+5.2f duty=%.2f brake=%.2f gear=%d ax=%+6.1f ay=%+6.1f az=%+6.1f %s" % (
                    now - t0, x, z, yaw, yawrate, speed, herr, shared["steer"], shared["duty"], shared["brake"], tel["gear"], tel["accel"][0], tel["accel"][1], tel["accel"][2], "/".join(tel["surfaces"])), flush=True)
                if n % 25 == 0:
                    print("R %5.2f v=%.2f %s" % (now - t0, speed, tel["dump"].hex()), flush=True)
                wl = tel["wheels"]
                print("W %5.2f rpm=%5.0f rot=%s grip=%s load=%s lat=%s defl=%s" % (now - t0, tel["rpm"], ",".join("%.1f" % w["rot"] for w in wl), ",".join("%.2f" % w["grip"] for w in wl), ",".join("%.0f" % w["load"] for w in wl), ",".join("%.0f" % w["lat"] for w in wl), ",".join("%.3f" % w["defl"] for w in wl)), flush=True)
            if rec["phase"] is not None or (args.kerb_mode and now < kerb_until):
                pass
            elif gearcar is not None and now - last_shift > 0.35 and not in_lane and chain is track.main and shared["brake"] < 0.05 and abs(tel["accel"][0]) < 8.0:
                gear, rpm = tel["gear"], tel["rpm"]
                if gear >= 1:
                    scale = 1.04 if shared["duty"] > 0.5 else 1.0      # accelerating: the revs are about to rise. No gear change under braking or in a hard corner: a downshift without a rev-matching blip locks the rear wheels (tried: a spin at (-512, -401))
                    want = cargears.best_gear(gearcar, rpm, gear, scale, 0.95, down_hysteresis=args.gear_down_hyst, speed=speed, first_max=args.gear_first_max)
                    g = gearcar["gears"]
                    if want < gear and rpm * g[want - 1] / g[gear - 1] > 0.95 * gearcar["limit"]:
                        want = gear                                                          # the lower gear would over-rev at the speed we have now
                    if want > gear:
                        last_shift = now; shift(True)
                    elif want < gear:
                        last_shift = now; shift(False)
            elif now - last_shift > 0.35 and not in_lane:      # only a debounce (the gear read-back lags the button); the game enforces the shift time
                gear, rpm = tel["gear"], tel["rpm"]
                if gear < args.max_gear and rpm > (args.shift_rpms[gear - 1] if args.shift_rpms and gear <= len(args.shift_rpms) else args.shift_rpm):
                    last_shift = now; shift(True)
                elif gear > 1 and rpm < args.down_rpm:
                    last_shift = now; shift(False)
            if args.debug_stop and args.debug_stop[0] <= now - t0 <= args.debug_stop[0] + args.debug_stop[1]:
                shared["duty"], shared["brake"] = 0.0, 1.0      # test hook: hold the car still to exercise the stall recovery
            if args.recover and chain is track.main and not merging and box_target is None:
                if speed < 1.0:
                    if rec["still"] is None:
                        rec["still"] = now
                else:
                    rec["still"] = None
                if rec["phase"] is None and rec["still"] is not None and now - rec["still"] > args.recover_after and now - t0 > 20.0 and rec["n"] < 6:
                    rec.update(phase="reverse", n=rec["n"] + 1, t=now, x=x, z=z, shift=0.0)
                    print("t=%5.1f stopped at (%.0f, %.0f): reversing out (attempt %d)" % (now - t0, x, z, rec["n"]), flush=True)
                if rec["phase"] == "reverse":
                    g_now = tel["gear"]
                    if g_now > -1:
                        if now - rec["shift"] > 0.5:
                            rec["shift"] = now
                            shift(False)
                        shared["duty"], shared["brake"], shared["steer"] = 0.0, 0.0, 0.0
                    else:
                        shared["duty"], shared["brake"] = 0.6, 0.0
                        shared["steer"] = -max(-1.0, min(1.0, herr / 25.0))      # backing up: the wheel works the other way round
                        if math.hypot(x - rec["x"], z - rec["z"]) > args.recover_dist or now - rec["t"] > 6.0:
                            rec["phase"] = "forward"
                            rec["shift"] = 0.0
                    if rec["phase"] == "reverse" and now - rec["t"] > 9.0:
                        rec["phase"] = "forward"
                elif rec["phase"] == "forward":
                    shared["duty"], shared["brake"] = 0.0, 0.0
                    if tel["gear"] < 1:
                        if now - rec["shift"] > 0.5:
                            rec["shift"] = now
                            shift(True)
                    else:
                        rec["phase"] = None
                        rec["still"] = None
                        last_move = now
                        print("t=%5.1f back in gear %d, driving on" % (now - t0, tel["gear"]), flush=True)
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
        if args.session_laps > 0:
            result["session_laps"] = meta["laps"]
        if args.steer_id:
            result["steer_id"] = {str(b * 10): {"n": len(v_), "k_med": round(sorted(v_)[len(v_) // 2], 5), "k_p10": round(sorted(v_)[len(v_) // 10], 5), "k_p90": round(sorted(v_)[-1 - len(v_) // 10], 5)} for b, v_ in sorted(sid["k"].items()) if len(v_) >= 5}
        if args.geo_limits:
            mg = sorted(geo["margins"])
            result["geo"] = {"samples": geo["n"], "both": geo["both"], "geometric_only": geo["geo_only"], "surface_only": geo["surf_only"],
                             "events": [e_ for e_ in geo["events"] if e_["seconds"] >= 0.06][:10], "surface_off_margin_m": ([mg[0], mg[len(mg) // 10], mg[len(mg) // 2], mg[-1]] if mg else None),
                             "gap_any_tyre_off_road_surface(min,p5,p50,p95,n)": (lambda v_: [v_[0], v_[len(v_) // 20], v_[len(v_) // 2], v_[-1 - len(v_) // 20], len(v_)] if v_ else None)(sorted(geo.get("m_off", []))),
                             "gap_all_tyres_on_road_surface(min,p5,p50,p95,n)": (lambda v_: [v_[0], v_[len(v_) // 20], v_[len(v_) // 2], v_[-1 - len(v_) // 20], len(v_)] if v_ else None)(sorted(geo.get("m_on", [])))}
        if args.grip_map and not args.no_memory and len(result["lap_changes"]) >= 2 and (args.session_laps > 0 or not [i_ for i_ in impacts if not i_.get("pit")]):      # a completed lap without impacts: remember what the maps learned
            try:
                mem_file.parent.mkdir(exist_ok=True)
                if args.session_laps > 0 and (meta["best"] is None or (meta.get("prev_best") is not None and meta["best"] >= meta["prev_best"] - 0.05)):
                    raise RuntimeError("this session was not faster than the remembered one (%s s): memory kept" % meta.get("prev_best"))
                mem_file.write_text(json.dumps({"gm": {str(k_): round(v_, 3) for k_, v_ in gm.items()}, "padec": {str(k_): round(v_, 2) for k_, v_ in padec.items()}, "meta": ({"push": round(meta["best_push"], 4), "step": round(meta["step"], 4), "best_time": round(meta["best"], 2)} if args.session_laps > 0 and meta["best"] is not None else None)}))
                print("memory saved to %s" % mem_file.name, flush=True)
            except Exception as e_:
                print("memory not saved (%s)" % e_, flush=True)
        result.update(off_road_at=[[k, n, round(sum(off_lat[k]) / len(off_lat[k]), 1)] for k, n in sorted(off_buckets.items(), key=lambda kv: -kv[1])[:8]], impacts=impacts[:10], kerbs=kerbs[:10], contacts=contacts[:300],kerb_count=len(kerbs), recoveries=rec["n"], grip_map=({str(k_ * 20): round(v_, 2) for k_, v_ in sorted(gm.items()) if abs(v_ - 1.0) > 0.01} if args.grip_map else None), grip_map_hist={k_: [v_[0], round(v_[1] / max(v_[0], 1), 1)] for k_, v_ in sorted(gmh.items())}, brake_slip_hist={str(round(k_ / 20.0, 2)): [v_[0], round(v_[1] / max(v_[0], 1), 1)] for k_, v_ in sorted(bslip.items())}, limit_guard_samples=guard_n, grip_map_up=gms["up"], grip_map_down=gms["down"], learned_zones=[[int(a_), int(b_), round(f_, 2)] for a_, b_, f_ in learned], plan_decel={str(k_ * 10): round(v_, 1) for k_, v_ in sorted(padec.items())}, lat_rms=round(math.sqrt(stn["lat2"] / max(stn["lat_n"], 1)), 2), lat_p95=round(sorted(stn["lats"])[int(len(stn["lats"]) * 0.95)], 2) if stn["lats"] else 0.0, st_gain=[round(stn["g"].get(i, 0.0), 3) for i in range(8)], live_final=[round(live["a_lat"], 2), round(live["a_brk"], 2), round(live["kk"] * 1e4, 2)], live_range=[round(live["lat_lo"], 1), round(live["lat_hi"], 1), round(live["brk_lo"], 1), round(live["brk_hi"], 1)], live_penalties=live["pen"], track_limit_events=len([e for e in limit_events if e['seconds'] >= 0.06]), track_limit_seconds=round(sum(e['seconds'] for e in limit_events if e['seconds'] >= 0.06), 2), track_limit_list=[e for e in limit_events if e['seconds'] >= 0.06][:10], dyn_throttle_cut_share=round(dyn["tc_n"] / max(dyn["thr_n"], 1), 3), dyn_brake_cut_share=round(dyn["abs_n"] / max(dyn["brk_n"], 1), 3), pit_impacts=sum(1 for i in impacts if i["pit"]), bumps=bumps, peak_accel_pit=round(peak_pit, 1), peak_accel=round(peak_all, 1), seconds=round(time.time() - t0), off_road_share=round(off_samples / max(samples, 1), 4), steer_travel=round(steer_travel / max(samples, 1) * 100, 2), max_offset=round(max_lat, 1))
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
