r"""Live watchdog for a running lap session: reads the driver's status file (scripts/gtr2_ui/runs/live_status.json, rewritten once a second
by gtr2-drive-lap.py) and prints one line when the car stops moving, starts a recovery, keeps trying to recover, changes lap, or the
status goes stale (the driver has stopped). Silent while all is well, so it can run as a monitor during a session.

Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2-watch.py [--stall 4] [--lap-limit 150] [--stale 3] [--once]
  --stall N      report when the car has not moved for N seconds (the driver gives up after 8 s, recovery starts after 2 s)
  --lap-limit N  report when the lap number has not changed for N seconds (a lap at this pace takes about 115 s)
  --stale N      report when the status has not been rewritten for N seconds (driver stopped or session ended)
  --once         print the current status once and exit
Example: a Monitor running `scripts\.venv\Scripts\python.exe -I scripts\gtr2-watch.py` during a campaign.
"""
import argparse
import json
import sys
import time
from pathlib import Path

# CONFIDENCE NOTES (written 2026-11-25; read these before debugging the watcher's behaviour):
# - Not tested in a live session. Only `--once` was run, against no status file. The first campaign session with the automatic watcher is the test.
# - The status file (gtr2_ui/runs/live_status.json) is written once a second by gtr2-drive-lap.py, inside its main loop only. A run that fails before the loop, or a
#   tool that does not go through the driver, writes nothing: the watcher then says nothing, which is NOT evidence that the car is fine.
# - "still" uses the driver's own last_move (the car must move 0.5 m in 8 s, the 0.25 m^2 test in gtr2-drive-lap.py). A deliberate stop (pit box, garage,
#   a red flag) looks like a stall. Expect false alarms there. The threshold (--stall 4) is a guess, not measured.
# - "lap" fires when the lap number has not changed for --lap-limit (150 s). A slow first lap, a pit stop or a long recovery can trip it. The 150 s is a guess
#   (clean laps take about 113 to 118 s; the 1166 m first-lap stalls end in about 40 s, so they are caught by "still", not "lap").
# - "recovering" and "attempts" (3 or more) only report what the driver's recovery reports; they do not check whether the recovery works.
# - Each alert is printed once per lap (the set resets when the lap number changes). If a stall repeats within one lap it is not printed again.
# - "stale" (no write for --stale 3 s) ends the watcher. The driver writes once a second, so one slow write (disk, antivirus) could end it early, and
#   the campaign then stops watching for that session without saying so.
# - The watcher never looks at the game window or the inputs, so it cannot tell a stalled car from a driver that has frozen but still writes the file.
#   A frozen driver would keep writing an unchanged position, so "still" would fire: this case is inferred, not checked.
# - The campaign clears live_status.json before each session. If a run is started outside the campaign, an old file can make the watcher report "stale" at once.
# - STOP REQUEST (added 2026-11-25, untested live): by default only "attempts" (3 or more recovery attempts within one trouble) writes gtr2_ui/runs/stop_request.json.
#   The driver checks for it once a second and exits through its normal cleanup with the outcome "stop requested: ...", and the campaign then stops
#   (no next session). Unknowns: whether 3 attempts ever happens in a run that would recover by itself (then the stop costs a session); whether the
#   driver's exit path really releases the inputs when stopped this way (check the vJoy buttons after the first stop); and "lap" and "still" are
#   report-only by default because they have false alarms in pit stops and slow laps.

STATUS =Path(__file__).resolve().parent / "gtr2_ui" / "runs" / "live_status.json"


def read():
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def line(st, why):
    return "%7.1fs lap %s speed %4.1f m/s gear %s at x=%.0f z=%.0f: %s" % (
        st["run_s"], st["lap"], st["speed"], st["gear"], st["x"], st["z"], why)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stall", type=float, default=4.0)
    ap.add_argument("--lap-limit", type=float, default=150.0)
    ap.add_argument("--stale", type=float, default=3.0)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--stop-on", default="attempts", help="alerts that ask the driver to stop through its normal cleanup (a stop-request file); comma separated from still, attempts, lap, stale; empty = report only")
    a = ap.parse_args()
    stop_keys = set(k for k in a.stop_on.split(",") if k)
    requested = False
    last_lap, lap_since, reported = None, time.time(), set()
    while True:
        st = read()
        now = time.time()
        if st is None:
            if a.once:
                print("no status file yet (no driver running)")
                return 0
            time.sleep(1.0)
            continue
        if a.once:
            print(json.dumps(st))
            return 0
        if st["lap"] != last_lap:
            if last_lap is not None:
                print(line(st, "lap %s done" % last_lap), flush=True)
            last_lap, lap_since, reported = st["lap"], now, set()
        alerts = []
        if now - st["time"] > a.stale:
            alerts.append(("stale", "status not updated for %.0f s: the driver has stopped or the session ended" % (now - st["time"])))
        if st["still_s"] > a.stall:
            alerts.append(("still", "not moving for %.1f s" % st["still_s"]))
        if st["recovering"]:
            alerts.append(("recovering", "recovery under way (attempt %d)" % st["recover_attempts"]))
        if st["recover_attempts"] >= 3:
            alerts.append(("attempts", "%d recovery attempts in this trouble" % st["recover_attempts"]))
        if now - lap_since > a.lap_limit:
            alerts.append(("lap", "lap %s taking more than %.0f s" % (st["lap"], a.lap_limit)))
        for key, why in alerts:
            if key not in reported:
                reported.add(key)
                print(line(st, why), flush=True)
                if key in stop_keys and not requested:
                    requested = True
                    STATUS.with_name("stop_request.json").write_text(json.dumps({"reason": why, "time": round(now, 2)}), encoding="utf-8")
                    print(line(st, "stop requested: the driver exits through its normal cleanup"), flush=True)
                if key == "stale":
                    return 0
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
