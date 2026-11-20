"""Hands-free lap check: launch the game, drive one lap of a layout with a car, say whether the lap was clean, and put everything back.

Purpose: a repeatable regression run for the telemetry driver (gtr2-drive-lap.py), and
car_tests.py. One run = set the profile (the driving keys on the keyboard, the layout, optionally another car; byte-preserving edits, put back with git),
launch through gtr2-launch.ps1, Open Practice, DRIVE, drive the lap, Esc / Return to Garage, LEAVE TRACK, EXIT through the menus, revert, check
Documents\\GTR2. A lap is clean if it was completed and under 0.5% of the samples had a wheel on grass, gravel, sand or dirt.
The driving settings are `--fast` plus the layout's entry in gtr2_driving/track_params.json (applied by gtr2-drive-lap.py).
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-lap-check.py LAYOUT [--car KEY] [--runs N] [--limit SHARE] [--no-fast]
         scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-lap-check.py --all-layouts [--car KEY] [--resume]       every layout (34), one car
         scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-lap-check.py LAYOUT --all-cars [--resume]               every car (24), one layout
         scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-lap-check.py --list | --list-cars
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-lap-check.py Imola4Imol
LAYOUT is text matched against "<venue><file>" (case-insensitive) and must pick exactly one layout. Run it with the PC left alone: the script
takes the keyboard and the mouse for 3 to 6 minutes per lap. Results are appended to gtr2_ui/runs/lap_results.jsonl.
Exit code 0 if every run was clean, 1 if not, 2 for a bad argument or a refused start.
"""
import argparse
import importlib.util
import json
import re
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "gtr2_ui"))


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


suite = _load("gtr2_nav_suite", "gtr2-nav-suite.py")
ROOT = suite.ROOT
LOC = ROOT / "GameData" / "Locations"
TEAMS = ROOT / "GameData" / "Teams"
PLR = suite.diag.plr_path(ROOT)
RESULTS = SCRIPTS / "gtr2_ui" / "runs" / "lap_results.jsonl"
CLEAN_LIMIT = 0.005
NL = bytes([10])
# Keyboard driving profile (from the 2026-11-10 notes in CLAUDE.md: the settings the first hands-free lap used).
DRIVING_PROFILE = {
    "Basic Controls": "1", "Shift Mode": "0", "Auto Reverse": "0", "Opposite Lock": "0", "Speed Sensitive Steering": "0.6",
    "Steer Ratio Speed": "25", "Difficulty Type": "2",
    "Control - Accelerate": "(0, 30)", "Control - Brake": "(0, 44)", "Control - Steer Left": "(0, 51)", "Control - Steer Right": "(0, 52)",
    "Control - Shift Up": "(0, 56)", "Control - Shift Down": "(0, 184)", "Control - First Gear": "(1, 152)",
}
DEFAULT_CAR = "gt/lamborghini_murcielago"
# Difficulty and driver-aid settings recorded with every result (the committed profile is Novice: Difficulty Type 0; the driving
# profile sets Difficulty Type 2, but the Steering Help / Brake Help / Stability Control / Auto Clutch / Invulnerability aids stay on).
MODE_KEYS = ["Difficulty Type", "Difficulty", "Arcade Mode", "Steering Help", "Steering Help Functionality", "Brake Help", "Stability Control",
             "Spin Recovery", "Opposite Lock", "Auto Clutch", "Shift Mode", "Auto Reverse", "Invulnerability", "Damage Multiplier",
             "Speed Sensitive Steering", "Steer Ratio Speed", "Basic Controls", "PRACT Weather", "PRACT Failure Rate",
             "PRACT Fuel Consumption Multiplier"]
LAST_PROFILE = {}
LAST_OUT = [""]       # the last driver run's stdout (for --garage-exit)


def mode_snapshot(data):
    """{key: value} of MODE_KEYS from the profile bytes (what the game will read for this run)."""
    out = {}
    for line in data.decode("latin1").splitlines():
        m = re.match(r'([^="]+)="([^"]*)"', line)
        if m and m.group(1) in MODE_KEYS:
            out[m.group(1)] = m.group(2)
    return out


def layouts():
    """[(venue, trk file name, aiw path)] for every .trk that has an .AIW of the same name."""
    out = []
    for venue in sorted(p for p in LOC.iterdir() if p.is_dir()):
        aiws = {p.stem.lower(): p for p in venue.iterdir() if p.suffix.lower() == ".aiw"}
        for trk in sorted(venue.iterdir()):
            if trk.suffix.lower() == ".trk" and trk.stem.lower() in aiws:
                out.append((venue.name, trk.name, aiws[trk.stem.lower()]))
    return out


def cars():
    """{key: path}: one representative .car per model, key 'class/model' in lower case; the profile's own car (the Murcielago) is the proven one."""
    out = {}
    for cls in sorted(p for p in TEAMS.iterdir() if p.is_dir() and p.name in ("GT", "NGT", "24H")):
        for model in sorted(p for p in cls.iterdir() if p.is_dir() and p.name.lower().endswith(" teams")):
            files = sorted(model.rglob("*.car"), key=lambda f: str(f).lower())
            if files:
                out[cls.name.lower() + "/" + model.name[:-len(" Teams")].lower().replace(" ", "_")] = files[0]
    for f in (TEAMS / "GT" / "Lamborghini Murcielago Teams").rglob("*.car"):
        if f.name.lower() == "04024_gt_murc.car":
            out[DEFAULT_CAR] = f
    return out


def pick_layout(text, items):
    hits = [i for i in items if text.lower() in (i[0] + i[1]).lower()]
    if len(hits) != 1:
        raise ValueError("%r matches %d layouts%s" % (text, len(hits), ": " + ", ".join("%s/%s" % (v, t) for v, t, _ in hits) if hits else ""))
    return hits[0]


def set_values(data, values):
    """Profile bytes with each `Key="value"` line's value replaced (everything else, including the trailing comment, kept)."""
    lines = data.split(NL)
    for key, value in values.items():
        hit = [i for i, l in enumerate(lines) if l.startswith(key.encode("latin1") + b'="')]
        if len(hit) != 1:
            raise ValueError("%r is on %d lines of the profile" % (key, len(hit)))
        head, _, tail = lines[hit[0]].partition(b'="')
        lines[hit[0]] = head + b'="' + value.encode("latin1") + b'"' + tail.partition(b'"')[2]
    return NL.join(lines)


PROFILE_EXTRA = {}      # --profile Key=Value,...: extra profile values for the run (reverted with git afterwards)


def profile_values(venue, trk, aiw, car_path, analog=False, wheel=False):
    rel = lambda name: "GAMEDATA\\LOCATIONS\\%s\\%s" % (venue, name)      # noqa: E731
    values = dict(DRIVING_PROFILE)
    if analog:      # the committed profile already binds the vJoy axes (CLAUDE.md); only the non-control driving settings
        values = {k: v for k, v in values.items() if not k.startswith("Control - ")}
        values["Basic Controls"] = "2" if wheel else "0"
        if wheel:
            values["Control - Clutch In"] = "(1, 10)"      # wheel profile: the clutch is a pedal axis too (vJoy RY below centre), not keyboard Q      # 2 = what the game writes once JOY1 is selected on the Controls page (gtr2-select-wheel.py)
    values.update(PROFILE_EXTRA)
    values.update({"Track File": rel(trk), "Track Description": Path(trk).stem, "AI Database File": rel(aiw.name)})
    if car_path is not None:
        car = ("GAMEDATA\\" + str(car_path.relative_to(ROOT / "GameData")).replace("/", "\\")).upper()
        values.update({"Profile Vehicle File": car, "Vehicle File": car, "Reserved Vehicle File": car})
    return values


TRACK_LIMIT_BUDGET = 0     # laps with all four wheels over the white line: none allowed
RUN_TIMEOUT = 1500      # seconds one driver run may take (--timeout; a long session needs more)
KERB_BUDGET = None     # kerb strikes allowed on a lap: None = no limit (user, 2026-11-19: kerbs are fine while a tyre stays on the road; all four beyond the white line is the track limit rule)


def judge(result, limit=CLEAN_LIMIT):
    """(clean, why) for one gtr2-drive-lap RESULT."""
    if result.get("outcome") != "completed":
        return False, "lap not completed (%s)" % result.get("outcome")
    if result.get("pit_impacts", 0) > 0:
        return False, "the garage exit hit the wall (%d impacts, first %s)" % (result["pit_impacts"], result["impacts"][0] if result.get("impacts") else "?")
    hits = [i for i in result.get("impacts", []) if not i.get("pit")]
    if hits:       # a hit on the track counts like one in the garage exit (the garage-mouth lip is already left out by the driver as a BUMP)
        return False, "%d impact(s) on the track, peak %.0f m/s^2, first %s" % (len(hits), result.get("peak_accel", 0), hits[0])
    if KERB_BUDGET is not None and result.get("kerb_count", 0) > KERB_BUDGET:
        return False, "%d kerb strikes (budget %d), first %s" % (result["kerb_count"], KERB_BUDGET, (result.get("kerbs") or ["?"])[0])
    if "track_limit_events" in result:
        if result.get("lap_changes"):      # the out lap is not a valid lap (cold tyres): its track limits do not count, only the timed lap's
            t_fly = result["lap_changes"][0]["t"]
            fly = [e for e in (result.get("track_limit_list") or []) if e.get("t", 0) >= t_fly]
            result = dict(result, track_limit_events=len(fly), track_limit_seconds=sum(e.get("seconds", 0) for e in fly), track_limit_list=fly)
    if "track_limit_events" in result:      # real-racing rule: a lap is void when all four wheels are beyond the white line; touching grass with one to three wheels is allowed
        if result["track_limit_events"] > TRACK_LIMIT_BUDGET:
            return False, "exceeded track limits %d time(s) (all four wheels beyond the white line, %.1f s), first %s" % (result["track_limit_events"], result.get("track_limit_seconds", 0), (result.get("track_limit_list") or ["?"])[0])
        return True, "clean, no track-limit violation, %.2f%% of samples with a wheel on grass, largest offset %s m, %s s%s" % (result.get("off_road_share", 0) * 100, result.get("max_offset"), result.get("seconds"), (", %d kerb strike(s)" % result["kerb_count"]) if result.get("kerb_count") else "")
    share = result.get("off_road_share", 1.0)
    if share >= limit:
        return False, "%.2f%% of samples off the road (limit %.2f%%)" % (share * 100, limit * 100)
    return True, "clean, %.2f%% off the road, largest offset %s m, %s s%s" % (share * 100, result.get("max_offset"), result.get("seconds"), (", %d kerb strike(s)" % result["kerb_count"]) if result.get("kerb_count") else "")


def run_path(lines, *flags, timeout=300):
    tmp = SCRIPTS / "gtr2_ui" / "runs" / "lap_steps.txt"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    r = suite.nav("path", *flags, str(tmp), timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def one_run(venue, trk, aiw, car_key, car_path, fast, input_mode="keyboard", drive_args=()):
    """One lap. Returns (result dict or None, message)."""
    before = suite.untracked()
    PLR.write_bytes(set_values(PLR.read_bytes(), profile_values(venue, trk, aiw, car_path, input_mode in ("analog", "wheel"), input_mode == "wheel")))
    LAST_PROFILE.clear()
    LAST_PROFILE.update(mode_snapshot(PLR.read_bytes()))
    result, message = None, ""
    try:
        if not suite.start_game():
            return None, "the game never reached the main menu"
        ok, out = run_path(["MAIN MENU | APP_BUTTON_GAMEMODESELECT_PRACTICE | SUMMARY_PRACTICE", "SUMMARY_PRACTICE | CONTINUE | MONITOR_SINGLE"], "--session-step", "--drive-step")
        t_drive = time.time()
        if ok:
            ok, out = run_path(["MONITOR_SINGLE | !DRIVE | MONITOR_SINGLE"], "--session-step", "--drive-step")
        t_cockpit = time.time()
        if not ok:
            tr = ROOT / "UserData" / "LOG" / "trace.txt"       # keep the game's trace for diagnosing a failed start
            if tr.exists():
                (SCRIPTS / "gtr2_ui" / "runs" / "last_failure_trace.txt").write_bytes(tr.read_bytes())
            return None, "could not get into the car: " + out.splitlines()[-1]
        cmd = [suite.PY, "-I", str(SCRIPTS / os.environ.get("GTR2_DRIVER_SCRIPT", "gtr2-drive-lap.py")), "--aiw", str(aiw), "--car-key", car_key] + (["--fast"] if fast else []) + ["--input", "analog" if input_mode == "wheel" else input_mode] + (["--device", "wheel"] if input_mode == "wheel" else []) + list(drive_args)
        t_spawn = time.time()
        LAST_OUT[0] = ""
        STAGE_TEXT = "".join("STAGE %s epoch=%.3f" % (n, v) + chr(10) for n, v in (("drive_step_begin", t_drive), ("drive_step_done", t_cockpit), ("driver_spawned", t_spawn)))
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=RUN_TIMEOUT)
        (SCRIPTS / "gtr2_ui" / "runs" / "lap_drive.log").write_text(STAGE_TEXT + r.stdout + r.stderr, encoding="utf-8")
        with (SCRIPTS / "gtr2_ui" / "runs" / "start_timing.log").open("a", encoding="utf-8") as f:      # every run's start-up stages, for comparing changes
            f.write("# %s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), Path(trk).stem) + "".join(l + "\n" for l in (STAGE_TEXT + r.stdout).splitlines() if l.startswith("STAGE ") or l.startswith("gear before")))
        LAST_OUT[0] = r.stdout
        line = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")]
        result = json.loads(line[-1][7:]) if line else {"outcome": "no result: " + (r.stderr or r.stdout)[-300:].replace("\n", " | ")}
        ok, out = run_path(["MONITOR_SINGLE | !LEAVEDRIVE | MONITOR_SINGLE", "MONITOR_SINGLE | LEAVE TRACK | CONFIRM_EXIT",
                            "CONFIRM_EXIT | APP_BUTTON_BACKTOMAIN | MAIN MENU"], "--session-step", "--drive-step")
        if not ok:
            message = "could not leave the session (the game is left open): " + out.splitlines()[-1]
            return result, message
    finally:
        if not message:
            closed = suite.exit_game()
            if closed:
                clean = suite.revert_and_check(before)
                message = "" if clean else "cleanup was not clean"
            else:
                message = "the game was left open"
    return result, message


def record_box_start(stem, car, out):
    r"""Parse the driver's garage-exit lines ("start (x, z) yaw Y, pit line D m away", "until within S m of the pit line") and keep them per
    layout and car in gtr2_driving/box_starts.json: {layout: {car: [x, z, yaw, pit_line_distance, stop_distance]}} (the game puts different
    cars in different bays). gtr2-garage-map.py and the box planning read it. Returns the list or None."""
    m = re.search(r"garage exit: start \((-?[\d.]+), (-?[\d.]+)\) yaw (-?[\d.]+), pit line ([\d.]+) m away", out or "")
    if not m:
        return None
    stop = re.search(r"until within ([\d.]+) m of the pit line", out or "")
    start = [float(m.group(i)) for i in range(1, 5)] + [float(stop.group(1)) if stop else None]
    path = SCRIPTS / "gtr2_driving" / "box_starts.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data.setdefault(stem.lower(), {})[car] = start
    path.write_text(json.dumps({k: dict(sorted(v.items())) for k, v in sorted(data.items())}, indent=1) + chr(10))
    return start


def garage_done(venue, trk, car, input_mode):
    f = SCRIPTS / "gtr2_ui" / "runs" / "garage_exit.jsonl"
    if not f.exists():
        return False
    return any(r.get("ok") and r.get("layout") == "%s/%s" % (venue, trk) and r.get("car") == car and r.get("input") == input_mode
               for r in (json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()))


def garage_verdict(out, result, message):
    """--garage-exit: did the car leave the box, merge onto the pit lane line, reach the racing line, with no impact and no stall?"""
    if result is None:
        return False, message or "no result"
    need = ("gear before moving off: 1", "left the box path", "merged onto the pit lane line")
    missing = [n for n in need if n not in out]
    impacts = [l.strip() for l in out.splitlines() if "IMPACT" in l]
    outcome = str(result.get("outcome"))
    bad_outcome = outcome != "merged"
    first_move = [l for l in out.splitlines() if l.startswith("STAGE first_movement")]
    if missing or impacts or bad_outcome or not first_move or message:
        return False, "; ".join(x for x in ("missing: " + ", ".join(missing) if missing else "", "%d impact(s), first: %s" % (len(impacts), impacts[0]) if impacts else "", outcome if bad_outcome else "", "" if first_move else "never moved", message) if x)
    return True, "left the box, merged onto the pit lane line, no impact"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("layout", nargs="?")
    ap.add_argument("--car", default=DEFAULT_CAR, help="car key (see --list-cars); default: the Murcielago")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--limit", type=float, default=CLEAN_LIMIT)
    ap.add_argument("--input", choices=("keyboard", "analog", "wheel"), default="keyboard", help="analog: drive through the vJoy virtual joystick; wheel: the same with the profile as after selecting the wheel in the game (Basic Controls 2; run gtr2-select-wheel.py first)")
    ap.add_argument("--profile", default="", help="extra profile values for the run, e.g. \"Speed Sensitive Steering=0,Steer Ratio Speed=40\" (reverted afterwards); separate with ; when a key contains a comma (Axis [00, 00] Dead Zone=0.1)")
    ap.add_argument("--timeout", type=int, default=1500, help="seconds one driver run may take (raise it for --drive-args=\"--session-laps 20 --total 3600\")")
    ap.add_argument("--quick", action="store_true", help="stop at the first start/finish crossing: the out lap from the pits (about 3 min) instead of out lap plus a timed lap (about 5.5 min)")
    ap.add_argument("--drive-args", default="", help="extra options for gtr2-drive-lap.py, e.g. \"--analog-steer 0.3\"")
    ap.add_argument("--no-fast", action="store_true", help="drive at the slow default settings instead of --fast")
    ap.add_argument("--all-layouts", action="store_true", help="every layout with --car (about 3 to 7 minutes each)")
    ap.add_argument("--all-cars", action="store_true", help="every car on LAYOUT (with --all-layouts: every car at every layout, 34 x 24 runs)")
    ap.add_argument("--skip-done", action="store_true", help="with --garage-exit: skip layout/car pairs that already have an ok row in runs/garage_exit.jsonl")
    ap.add_argument("--garage-exit", action="store_true", help="only check leaving the garage: drive until 2 s after merging onto the pit lane line (at most 40 s), judge that the car left the box, merged onto the pit lane line and hit nothing (rows go to runs/garage_exit.jsonl, not to lap_results.jsonl)")
    ap.add_argument("--resume", action="store_true", help="with --all-*: skip combinations whose newest fast result is already clean")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--list-cars", action="store_true")
    a = ap.parse_args()
    global RUN_TIMEOUT
    RUN_TIMEOUT = a.timeout
    for kv in [x for x in a.profile.split(";" if ";" in a.profile else ",") if x]:
        PROFILE_EXTRA[kv.split("=", 1)[0].strip()] = kv.split("=", 1)[1].strip()
    items, car_files = layouts(), cars()
    if a.list:
        for v, t, p in items:
            print("%s/%s  (%s)" % (v, t, p.name))
        return 0
    if a.list_cars:
        for k, f in car_files.items():
            print(k, f.relative_to(ROOT))
        return 0
    if not a.layout and not a.all_layouts:
        ap.error("LAYOUT is required (or --all-layouts)")
    try:
        first = pick_layout(a.layout, items) if a.layout else items[0]
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    if a.car not in car_files:
        print("unknown car %r; --list-cars shows the keys" % a.car, file=sys.stderr)
        return 2
    plan = [(layout, a.car) for layout in (items if a.all_layouts else [first])]
    if a.all_cars:      # with --all-layouts too: every car at every layout
        plan = [(lay, k) for lay in (items if a.all_layouts else [first]) for k in car_files]
    done = set()
    if a.resume and RESULTS.exists():
        rows = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines() if l.strip()]
        newest = {}
        for r in rows:
            if r.get("mode") == "fast":
                newest[(r["layout"], r["car"])] = r["clean"] or str(r.get("why", "")).startswith("clean,")   # a clean lap flagged only by a cleanup note counts as done
        done = {k for k, v in newest.items() if v}
    plan = [(lay, car) for lay, car in plan if ("%s/%s" % (lay[0], lay[1]), car) not in done]
    if not plan:
        print("nothing to do (every combination already has a clean result)")
        return 0
    if suite.game_running():
        print("GTR2 is already running; close it first (nothing was started)")
        return 2
    if suite.dirty_tracked() or suite.untracked():
        print("UserData or ReplayData has uncommitted changes; commit or revert them first (the run reverts these folders)")
        return 2
    pre = suite.nav("preflight")
    print(pre.stdout.strip())
    if pre.returncode:
        return 2
    failed = infra = 0
    for (venue, trk, aiw), car in plan:
        for n in range(1, a.runs + 1):
            began = time.time()
            if a.garage_exit and a.skip_done and garage_done(venue, trk, car, a.input):
                print("skip %s/%s %s (already ok)" % (venue, trk, car), flush=True)
                continue
            result, message = one_run(venue, trk, aiw, car, car_files[car], not a.no_fast, a.input, (["--total", "40", "--stop-at-merge", "2"] if a.garage_exit else ["--laps-crossed", "1", "--total", "420"] if a.quick else []) + a.drive_args.split())
            if a.garage_exit:
                ok, why = garage_verdict(LAST_OUT[0], result, message)
                start = record_box_start(Path(trk).stem, car, LAST_OUT[0])
                with (SCRIPTS / "gtr2_ui" / "runs" / "garage_exit.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"layout": "%s/%s" % (venue, trk), "car": car, "input": a.input, "ok": ok, "why": why, "start": start, "time": time.strftime("%Y-%m-%d %H:%M:%S")}) + "\n")
                print("run %d/%d %s/%s %s: %s - %s" % (n, a.runs, venue, trk, car, "PASS" if ok else "FAIL", why), flush=True)
                failed += not ok
                infra = infra + 1 if result is None else 0
                if infra >= 2 or (message and "left open" in message):
                    print("stopping the batch (no result twice in a row, or the game was left open)")
                    return 1
                continue
            if result is None:
                ok, why = False, message
            else:
                ok, why = judge(result, a.limit)
                if message:
                    ok, why = False, why + "; " + message
            row = {"layout": "%s/%s" % (venue, trk), "car": car, "mode": "slow" if a.no_fast else "fast", "input": a.input, "clean": ok, "why": why,
                   "wall_seconds": round(time.time() - began), "profile": dict(LAST_PROFILE), "result": result, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
            RESULTS.parent.mkdir(exist_ok=True)
            with RESULTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            print("run %d/%d %s/%s %s: %s - %s" % (n, a.runs, venue, trk, car, "PASS" if ok else "FAIL", why), flush=True)
            failed += not ok
            infra = infra + 1 if result is None else 0
            if infra >= 2:
                print("two runs in a row produced no result (the game or the launcher is not working): stopping the batch")
                return 1
            if message and "left open" in message:
                print("the game was left open: stopping")
                return 1
    print("%d run(s), %d failing" % (len(plan) * a.runs, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
