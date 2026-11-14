r"""Control bindings of the player profile as named presets (keyboard, wheel on vJoy with split pedals, wheel with the game's combined pedal axis).

Purpose: the game's own Controls page writes `Basic Controls` and the `Control - *` keys; this module sets the same keys byte-preservingly
(NUL header and line endings of `<profile>.PLR` kept), so a driving run or setup can put the profile in a known state without the UI.
Adds nothing beyond the standard library. Codes are `(controller, code)`: controller 1 is JOY1 (vJoy here), codes X+=1, X-=2, Y+=3, Y-=4,
Z+=5, Z-=6, Rx+=7, Rx-=8, buttons from 9 (vJoy button 1 = 13 on this profile's page: measured with the Buttons list, `(1, 13)` shows as JOY1 B1).
Measured 2026-11-14: selecting JOY1 in the game's Controls page (`gtr2-nav.py ... !SELECTWHEEL`, `gtr2-select-wheel.py`) writes `Basic Controls="2"`
and resets Accelerate/Brake to Y-/Y+ `(1, 4)`/`(1, 3)`; steering X and shifts on buttons 1 and 2 were already those.
Usage:   scripts\.venv\Scripts\python.exe -I scripts\gtr2_driving\controls.py show|presets
         scripts\.venv\Scripts\python.exe -I scripts\gtr2_driving\controls.py apply wheel-split [--dry-run]
Example: ... controls.py apply wheel-split   (the pedals the analog driver uses: Accelerate Z below centre, Brake Rx below centre)
"""
import argparse
import sys
from pathlib import Path

NL = bytes([10])
STEER_SHIFT = {"Control - Steer Left": "(1, 2)", "Control - Steer Right": "(1, 1)", "Control - Shift Up": "(1, 13)", "Control - Shift Down": "(1, 14)"}
PRESETS = {
    # the analog driver's bindings (docs/analog-driving.md), selected as the wheel
    "wheel-split": {"Basic Controls": "2", "Control - Accelerate": "(1, 6)", "Control - Brake": "(1, 8)", **STEER_SHIFT},
    # what the game sets itself when the wheel is selected: both pedals on one Y axis (a real wheel set's usual layout)
    "wheel-combined": {"Basic Controls": "2", "Control - Accelerate": "(1, 4)", "Control - Brake": "(1, 3)", **STEER_SHIFT},
}
KEYS = ["Basic Controls", "Control - Accelerate", "Control - Brake", "Control - Steer Left", "Control - Steer Right", "Control - Shift Up", "Control - Shift Down"]


def get_values(data, keys=KEYS):
    out = {}
    for line in data.split(NL):
        for k in keys:
            if line.startswith(k.encode("latin1") + b'="'):
                out[k] = line.partition(b'="')[2].partition(b'"')[0].decode("latin1")
    return out


def set_values(data, values):
    """Profile bytes with each `Key="value"` line's value replaced (the rest of the line, a trailing comment included, kept)."""
    lines = data.split(NL)
    for key, value in values.items():
        hit = [i for i, l in enumerate(lines) if l.startswith(key.encode("latin1") + b'="')]
        if len(hit) != 1:
            raise ValueError("%r is on %d lines of the profile" % (key, len(hit)))
        head, _, tail = lines[hit[0]].partition(b'="')
        lines[hit[0]] = head + b'="' + value.encode("latin1") + b'"' + tail.partition(b'"')[2]
    return NL.join(lines)


def matching_preset(data):
    """Name of the preset the profile's bindings equal, or None."""
    have = get_values(data, list(PRESETS["wheel-split"]))
    return next((n for n, v in PRESETS.items() if have == v), None)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "gtr2_ui"))
    import diag
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("show", "presets", "apply"))
    ap.add_argument("name", nargs="?", choices=sorted(PRESETS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.action == "presets":
        for n, v in PRESETS.items():
            print(n, v)
        return 0
    plr = diag.plr_path(diag.game_root())
    data = plr.read_bytes()
    if a.action == "show":
        print(plr, matching_preset(data) or "no preset matches")
        for k, v in get_values(data).items():
            print("  %s = %s" % (k, v))
        return 0
    if not a.name:
        ap.error("apply needs a preset name")
    new = set_values(data, PRESETS[a.name])
    print("%s: %s" % (plr.name, "unchanged" if new == data else ("would change" if a.dry_run else "changed")))
    if new != data and not a.dry_run:
        plr.write_bytes(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
