"""Force the weather for sessions of this install: apply a weekend weather file, run the game, put everything back.

Purpose: the game takes the forecast from UserData\\LOG\\weather.txt (inside this install: the config's LOGDIR is relative) only when a mode's
Weather setting in the profile is 0 ("Random/season/sunny/etc." otherwise). This copies one of config/weather/weather_weekend_{sunny,rainy,stormy}.txt over that file and sets Weather to 0 for the Race Weekend (FRACE), the current mode (CURNT),
Open Practice (PRACT), Time Trial (TIMET) and Championship (CHAMP). 24 Hour uses FRACE and CURNT. Not covered: Driving School (its lessons never
opened the file; the weather there is fixed), Replay (plays what was recorded), Multiplayer.
Measured 2026-11-11: with Weather=0 and the sunny file the Race Weekend monitor showed track 42 and ambient 40 (default: 20 and 20).
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-weather.py apply|restore|status|run  [sunny|rainy|stormy]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-weather.py run rainy        (apply, run the game through gtr2-launch.ps1 until it exits, restore)
`apply` records what it changed in gtr2_ui/runs/weather_backup.json; `restore` puts the profile's values and the old weather.txt back (or deletes
the one it installed). The profile is edited byte for byte (its NUL-byte header survives). Refuses to apply twice without a restore.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS / "gtr2_ui"))
import diag  # noqa: E402

ROOT = diag.game_root()
PLR = diag.plr_path(ROOT)
TARGET = ROOT / "UserData" / "LOG" / "weather.txt"
SOURCES = SCRIPTS.parent / "config" / "weather"
STATE = SCRIPTS / "gtr2_ui" / "runs" / "weather_backup.json"
KEEP = SCRIPTS / "gtr2_ui" / "runs" / "weather_original.txt"
MODES = ("FRACE", "CURNT", "PRACT", "TIMET", "CHAMP")
NL = bytes([10])


def get_value(data, key):
    """The value of `<key> Weather="n"` in profile bytes, or None."""
    m = re.search(rb'^' + re.escape(key.encode()) + rb' Weather="(\d+)"', data, re.M)
    return m.group(1).decode() if m else None


def set_value(data, key, value):
    """Profile bytes with `<key> Weather="n"` changed to `value` and every other byte kept (the file has a NUL-byte header and CRLF lines)."""
    pat = re.compile(rb'^(' + re.escape(key.encode()) + rb' Weather=")\d+(")', re.M)
    if len(pat.findall(data)) != 1:
        raise ValueError("%s Weather is not exactly once in the profile" % key)
    return pat.sub(lambda m: m.group(1) + str(value).encode() + m.group(2), data)


def apply(name):
    if STATE.exists():
        sys.exit("weather is already applied (%s): run `restore` first" % STATE)
    src = SOURCES / ("weather_weekend_%s.txt" % name)
    if not src.exists():
        sys.exit("no such weather file: %s" % src)
    data = PLR.read_bytes()
    old = {k: get_value(data, k) for k in MODES}
    if None in old.values():
        sys.exit("the profile has no Weather line for: %s" % ", ".join(k for k, v in old.items() if v is None))
    state = {"weather": name, "profile": old, "had_file": TARGET.exists()}
    STATE.parent.mkdir(exist_ok=True)
    if TARGET.exists():
        shutil.copy2(TARGET, KEEP)
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, TARGET)
    for k in MODES:
        data = set_value(data, k, 0)
    PLR.write_bytes(data)
    STATE.write_text(json.dumps(state), encoding="utf-8")
    print("applied %s: %s copied over %s; Weather set to 0 for %s (was %s)" % (
        name, src.name, TARGET.relative_to(ROOT), ", ".join(MODES), ", ".join(old[k] for k in MODES)))


def restore():
    if not STATE.exists():
        print("nothing to restore")
        return
    state = json.loads(STATE.read_text(encoding="utf-8"))
    data = PLR.read_bytes()
    for k, v in state["profile"].items():
        data = set_value(data, k, v)
    PLR.write_bytes(data)
    if state["had_file"]:
        shutil.copy2(KEEP, TARGET)
        KEEP.unlink(missing_ok=True)
    else:
        TARGET.unlink(missing_ok=True)
    STATE.unlink()
    print("restored: Weather %s and %s" % (", ".join("%s=%s" % kv for kv in state["profile"].items()),
                                           "the old weather.txt" if state["had_file"] else "no weather.txt (the installed one was removed)"))


def status():
    if STATE.exists():
        s = json.loads(STATE.read_text(encoding="utf-8"))
        print("applied: %s (profile values before: %s)" % (s["weather"], s["profile"]))
    else:
        print("not applied")
    data = PLR.read_bytes()
    print("profile now:", ", ".join("%s=%s" % (k, get_value(data, k)) for k in MODES))
    print("%s: %s" % (TARGET.relative_to(ROOT), "%d bytes" % TARGET.stat().st_size if TARGET.exists() else "absent"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("apply", "restore", "status", "run"))
    ap.add_argument("weather", nargs="?", choices=("sunny", "rainy", "stormy"))
    a = ap.parse_args()
    if a.action in ("apply", "run") and not a.weather:
        ap.error("%s needs sunny, rainy or stormy" % a.action)
    if a.action == "apply":
        apply(a.weather)
    elif a.action == "restore":
        restore()
    elif a.action == "status":
        status()
    else:
        apply(a.weather)
        try:
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / "gtr2-launch.ps1")], cwd=ROOT)
        finally:
            # the game rewrites the profile on exit: put the Weather values back (by key, so other changes in the profile survive)
            restore()


if __name__ == "__main__":
    main()
