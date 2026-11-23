r"""Record the game's shared-memory telemetry to a CSV at the highest rate until stopped (Ctrl+C / killed) or --seconds: wall time, lap counter, position,
speed, gear, rpm, the four wheels' grip fraction, lateral acceleration, heading. Used by gtr2-ai-benchmark.py to record the game's autopilot lap
(then compared with the hands-free driver's logs per metre of lap), but it works with any session.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-record-telemetry.py OUT.csv [--seconds 600]

Waits for the telemetry to exist (a session must be loaded). Standard library only (plus gtr2_driving/telemetry.py).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import telemetry  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=3600.0)
    a = ap.parse_args()
    tm = telemetry.Telemetry()
    t0 = time.time()
    rows = []
    last = None
    while time.time() - t0 < a.seconds:
        try:
            r = tm.read()
        except Exception:
            r = None
        if r is None or r["track"] == "":
            time.sleep(0.2)
            continue
        key = (r["pos"][0], r["pos"][2])
        if key != last:
            last = key
            w = r["wheels"]
            rows.append((round(time.time() - t0, 3), r["lap"], round(r["pos"][0], 1), round(r["pos"][2], 1), round(r["speed"], 2), r["gear"], int(r["rpm"]),
                         round(min(w[0]["grip"], w[1]["grip"]), 2), round(min(w[2]["grip"], w[3]["grip"]), 2), round(r["accel"][0], 2), round(r["accel"][2], 2), round(r["yaw"], 1)))
        time.sleep(0.002)
        if len(rows) % 2000 == 0 and rows:
            Path(a.out).write_text("t,lap,x,z,speed,gear,rpm,front_grip,rear_grip,ax_lat,ax_long,yaw\n" + "\n".join(",".join(str(v) for v in x) for x in rows) + "\n", encoding="utf-8")
    Path(a.out).write_text("t,lap,x,z,speed,gear,rpm,front_grip,rear_grip,ax_lat,ax_long,yaw\n" + "\n".join(",".join(str(v) for v in x) for x in rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
