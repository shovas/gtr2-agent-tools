r"""Best upshift rpm per gear for a GTR 2 car, from its own files (engine torque curve, gear ratios, rev limit).

For each gear the best upshift is where the wheel force in the next gear (torque at the lower rpm x its ratio) first equals the
force in the current one; if the engine never gets there before the rev limit, the shift is at the limit (97% of it, as the
game's own auto-shift does, `UpshiftAlgorithm`). Prints the numbers and the driver option `--shift-rpms` for gtr2-drive-lap.py.
Standard library only; reads the game folder, changes nothing.

    scripts\.venv\Scripts\python.exe -I scripts\gtr2-shift-points.py gt/maserati_mc12
    scripts\.venv\Scripts\python.exe -I scripts\gtr2-shift-points.py --hdc "<path to .hdc>"
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "gtr2_ui"))
import diag  # noqa: E402


def num(text):
    return [float(v) for v in re.findall(r"[-+]?\d+\.?\d*", text)]


def find_hdc(key):
    root = diag.game_root() / "GameData" / "Teams"
    cars = root / key.split("/")[0].upper()
    want = key.split("/")[1].replace("_", " ").lower()
    for d in sorted(cars.iterdir()):
        if want in d.name.lower() and d.is_dir():
            for f in d.glob("*.hdc"):
                return f
    raise SystemExit("no car %r under %s" % (key, root))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("car", nargs="?", help="car key such as gt/maserati_mc12 (folder under GameData/Teams)")
    ap.add_argument("--hdc", help="path to the car's .hdc instead")
    a = ap.parse_args()
    hdc = Path(a.hdc) if a.hdc else find_hdc(a.car)
    txt = hdc.read_bytes().decode("latin1")
    get = lambda name: re.search(r"^\s*%s\s*=\s*([^\r\n/]*)" % name, txt, re.M | re.I)
    eng = hdc.parent / get("EngineFile").group(1).strip() if get("EngineFile") else next(hdc.parent.glob("*.eng"))
    grb = hdc.parent / get("GearFile").group(1).strip()
    etxt = eng.read_bytes().decode("latin1")
    curve = sorted((num(m)[0], num(m)[2]) for m in re.findall(r"^RPMTorque=\(([^)]*)\)", etxt, re.M))
    lim_range = num(re.search(r"^RevLimitRange=\(([^)]*)\)", etxt, re.M).group(1))
    setting = int(num(re.search(r"^RevLimitSetting=(\S+)", etxt, re.M).group(1))[0])
    limit = lim_range[0] + lim_range[1] * setting
    g = open(grb, "rb").read().decode("latin1")
    ratios = [b / a_ for a_, b in (num(m)[:2] for m in re.findall(r"^Ratio=\(([^)]*)\)", g.split("[FINAL_DRIVE]")[0], re.M | re.I))]
    final = [num(m) for m in re.findall(r"^ratio=\(([^)]*)\)", g.split("[FINAL_DRIVE]")[1], re.M | re.I)][0]
    nfwd = int(num(get("ForwardGears").group(1))[0])
    gears = [ratios[int(num(get("Gear%dSetting" % i).group(1))[0])] for i in range(1, nfwd + 1)]

    def torque(rpm):
        if rpm <= curve[0][0]:
            return curve[0][1]
        for (r0, t0), (r1, t1) in zip(curve, curve[1:]):
            if r0 <= rpm <= r1:
                return t0 + (t1 - t0) * (rpm - r0) / (r1 - r0)
        return curve[-1][1]

    cap = 0.97 * limit
    out = []
    for n in range(nfwd - 1):
        best = cap
        rpm = 3000.0
        while rpm <= cap:
            if torque(rpm) * gears[n] <= torque(rpm * gears[n + 1] / gears[n]) * gears[n + 1]:
                best = rpm
                break
            rpm += 25.0
        out.append(round(best / 50.0) * 50)
    print("car file %s\nengine %s, rev limit %.0f (setting %d), 97%% = %.0f\ngears %s, final drive %.2f" % (hdc.name, eng.name, limit, setting, cap, ", ".join("%.3f" % x for x in gears), final[1] / final[0]))
    print("peak torque %.0f Nm at %.0f rpm" % (max(t for _, t in curve), max(curve, key=lambda c: c[1])[0]))
    print("best upshift rpm 1>2 .. %d>%d: %s" % (nfwd - 1, nfwd, " ".join("%d" % v for v in out)))
    print("driver option: --shift-rpms %s" % " ".join("%d" % v for v in out))


if __name__ == "__main__":
    main()
