r"""Garage map: what the track's collision meshes put in the way of a car leaving its box, and which heading bias clears it.

Reads the layout's `.trk` + `.gtr` archives (gtr2_driving/garage.py, gmt.py, mas.py); no game needed. Predicts the hit that the driver
logs as IMPACT (Anderstorp 3: a pillar between two bays at x -348.0, z -30.9).
Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2-garage-map.py LAYOUT_TRK X Z YAW [--width 2.0] [--length 4.8] [--front 2.6] [--run 6]
Example: scripts\.venv\Scripts\python.exe -I scripts\gtr2-garage-map.py GameData\Locations\Anderstorp\3ANDERSTORP.trk -349.6 -35.4 -178
X Z YAW are the garage exit start the driver prints ("garage exit: start (x, z) yaw ..."). Prints the obstacles nearest the straight run
and the clearance for yaw biases -12..+12 degrees (negative = the car overlaps something).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_driving"))
import garage  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("trk")
    ap.add_argument("x", type=float)
    ap.add_argument("z", type=float)
    ap.add_argument("yaw", type=float)
    ap.add_argument("--width", type=float, default=garage.CAR_BOX[0], help="car width, m (default: wider than any car)")
    ap.add_argument("--length", type=float, default=garage.CAR_BOX[1], help="car length, m")
    ap.add_argument("--front", type=float, default=garage.CAR_BOX[2], help="distance from the car's reference point to its nose, m")
    ap.add_argument("--run", type=float, default=6.0, help="straight run to check, m")
    a = ap.parse_args()
    obs, floor = garage.obstacles(Path(a.trk).resolve(), (a.x, a.z))
    print("floor y %.2f; %d wall triangles in the car's height band within 30 m" % (floor, len(obs)))
    (best_gap, best), rows = garage.best_bias(obs, (a.x, a.z), a.yaw, run=a.run, width=a.width, length=a.length, front=a.front)
    for gp, b in rows:
        print("bias %+3d: %s" % (b, "HIT" if gp < 0 else "gap %.2f m" % gp))
    print("best bias %+d (gap %.2f m)" % (best, best_gap) if best_gap >= 0 else "no bias in -12..12 clears the walls")


if __name__ == "__main__":
    main()
