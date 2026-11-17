r"""A car's own drivetrain numbers from its game files: engine torque curve, rev limit, gear ratios (with the final drive folded in).

    load("gt/maserati_mc12") -> {"gears": [ratio x final per gear], "curve": [(rpm, Nm)], "limit": rev limit rpm}
    best_gear(car, rpm, gear, speed_scale=1.0, cap=0.95) -> the gear with the highest wheel thrust at the speed the car has (or will have:
    speed_scale), keeping the engine under cap x the rev limit.
Standard library only; reads the game folder.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gtr2_ui"))
import diag  # noqa: E402


def _num(text):
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


def load(key):
    hdc = find_hdc(key)
    txt = hdc.read_bytes().decode("latin1")
    get = lambda name: re.search(r"^\s*%s\s*=\s*([^\r\n/]*)" % name, txt, re.M | re.I)
    eng_m = get("EngineFile")
    eng = hdc.parent / eng_m.group(1).strip() if eng_m else next(hdc.parent.glob("*.eng"))
    grb = hdc.parent / get("GearFile").group(1).strip()
    etxt = eng.read_bytes().decode("latin1")
    curve = sorted((_num(m)[0], _num(m)[2]) for m in re.findall(r"^RPMTorque=\(([^)]*)\)", etxt, re.M))
    lr = _num(re.search(r"^RevLimitRange=\(([^)]*)\)", etxt, re.M).group(1))
    setting = int(_num(re.search(r"^RevLimitSetting=(\S+)", etxt, re.M).group(1))[0])
    g = grb.read_bytes().decode("latin1")
    ratios = [b / a for a, b in (_num(m)[:2] for m in re.findall(r"^Ratio=\(([^)]*)\)", g.split("[FINAL_DRIVE]")[0], re.M | re.I))]
    fin = _num(re.findall(r"^ratio=\(([^)]*)\)", g.split("[FINAL_DRIVE]")[1], re.M | re.I)[0])
    final = fin[1] / fin[0]
    n = int(_num(get("ForwardGears").group(1))[0])
    gears = [ratios[int(_num(get("Gear%dSetting" % i).group(1))[0])] * final for i in range(1, n + 1)]
    return {"gears": gears, "curve": curve, "limit": lr[0] + lr[1] * setting}


def torque(car, rpm):
    c = car["curve"]
    if rpm <= c[0][0]:
        return c[0][1]
    for (r0, t0), (r1, t1) in zip(c, c[1:]):
        if r0 <= rpm <= r1:
            return t0 + (t1 - t0) * (rpm - r0) / (r1 - r0)
    return c[-1][1]


def best_gear(car, rpm, gear, speed_scale=1.0, cap=0.95, hysteresis=1.04):
    """Gear (1 based) with the most wheel thrust (torque x ratio) at the rpm the car would have in it, from the rpm now in `gear`
    (the engine speed is proportional to the gear ratio at a given road speed; `speed_scale` is the speed to judge at over the speed now).
    A gear that would take the engine over cap x rev limit is out; the current gear stays unless another beats it by `hysteresis`."""
    g = car["gears"]
    if not 1 <= gear <= len(g) or rpm < 500:
        return gear
    best, best_f = gear, -1.0
    cur_f = -1.0
    for n in range(1, len(g) + 1):
        r = rpm * (g[n - 1] / g[gear - 1]) * speed_scale
        if r > cap * car["limit"]:
            continue
        f = torque(car, r) * g[n - 1]
        if n == gear:
            cur_f = f
        if f > best_f:
            best, best_f = n, f
    if best == gear:
        return gear
    if cur_f > 0 and best_f < hysteresis * cur_f:
        return gear
    return best


if __name__ == "__main__":
    c = load(sys.argv[1] if len(sys.argv) > 1 else "gt/maserati_mc12")
    print("gears", [round(x, 2) for x in c["gears"]], "limit", c["limit"])
    # best gear by road speed, from the rpm the car would have in 1st: rpm1 = v / R x ratio1 x 9.549 with R 0.322
    for v in (10, 13, 16, 20, 25, 30, 40, 50, 60, 65):
        rpm1 = v / 0.322 * c["gears"][0] * 9.5493
        print("v %2d m/s: best gear %d (rpm in 1st %.0f)" % (v, best_gear(c, rpm1, 1, hysteresis=1.0), rpm1))
