r"""Select the wheel (vJoy as JOY1) in the game's Controls page and set the pedal bindings, then leave the profile changed.

Purpose: enable the wheel in the control mappings the way a player does (Controls > Buttons, the JOY1 name, the "Continue?" tick), through the
guarded navigator step `!SELECTWHEEL`, and then put the bindings in a known state with gtr2_driving/controls.py (the game resets the pedals to
its own Y-/Y+ when a controller is selected). Standard library only. Starts the game (leave the PC alone for about 40 s).
Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2-select-wheel.py [--preset wheel-split|wheel-combined] [--no-game] [--dry-run]
Example: scripts\.venv\Scripts\python.exe -I scripts\gtr2-select-wheel.py            (default preset wheel-split: the analog driver's Z/Rx pedals)
Exit code 0 when the profile ends up on the preset, 1 if not, 2 for a refused start. The profile is NOT reverted: it is the result.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path[:0] = [str(SCRIPTS / "gtr2_ui"), str(SCRIPTS)]
from gtr2_driving import controls  # noqa: E402


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preset", choices=sorted(controls.PRESETS), default="wheel-split")
    ap.add_argument("--no-game", action="store_true", help="only write the preset (no game start, no UI selection)")
    ap.add_argument("--dry-run", action="store_true", help="say what would happen")
    a = ap.parse_args()
    suite = _load("gtr2_nav_suite", "gtr2-nav-suite.py")
    plr = suite.diag.plr_path(suite.ROOT)
    if a.dry_run:
        print("would %s and set preset %s in %s (now: %s)" % ("skip the game" if a.no_game else "start the game, select JOY1 on Controls > Buttons",
              a.preset, plr.name, controls.matching_preset(plr.read_bytes()) or "no preset"))
        return 0
    if not a.no_game:
        pre = suite.nav("preflight")
        print(pre.stdout.strip())
        if pre.returncode != 0:
            return 2
        if not suite.start_game():
            return 2
        r = suite.nav("path", "--setting-step", str(SCRIPTS / "nav_paths" / "tour_select_wheel.txt"), timeout=120)
        print(r.stdout.strip() or r.stderr.strip())
        ok = suite.exit_game() and r.returncode == 0
        if not ok:
            print("the selection did not run cleanly: profile left as the game wrote it")
            return 1
        got = controls.get_values(plr.read_bytes(), ["Basic Controls"])
        print("game wrote Basic Controls=%s" % got.get("Basic Controls"))
        if got.get("Basic Controls") != "2":
            print("expected Basic Controls=2 after selecting JOY1")
            return 1
    data = plr.read_bytes()
    new = controls.set_values(data, controls.PRESETS[a.preset])
    if new != data:
        plr.write_bytes(new)
    ok = controls.matching_preset(plr.read_bytes()) == a.preset
    print("profile %s preset %s" % ("is on" if ok else "is NOT on", a.preset))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
