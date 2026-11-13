"""Click every checkbox and spinner of the settings pages, then check what the game saved to the profile.

Purpose: value-level control test. For each controls_* tour (nav_paths/, made by
gen-controls-tours.py) it launches the game, runs the tour (the `!CONTROLS` step clicks every control of a page and checks which changed on
screen), closes the game through its menus, and then compares the profile the game wrote on exit (UserData/<profile>/<profile>.PLR) with git:
 - every control that changed on screen must have changed its profile key;
 - for the main-menu pages, no other key may have changed (a mode's pages also rewrite the mode's own track, car and driver, so there the
   unexplained keys are only listed).
It then reverts UserData and ReplayData and checks Documents\\GTR2 like the suite does. Each tour gets its own launch because a mode's copy of a
page shares its keys with the others (a second click would toggle a key back).
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-control-check.py [--only main,school,practice,24h]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-control-check.py --only main
Exit code 0 only if every check passed and cleanup was clean. About 40 s per tour. Needs a clean UserData/ReplayData (it reverts them).
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
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
import coords  # noqa: E402

ROOT = suite.ROOT
PLR = suite.diag.plr_path(ROOT).relative_to(ROOT).as_posix()
LOG = SCRIPTS / "gtr2_ui" / "runs" / "controls_clicked.jsonl"
MODES = ("main", "school", "practice", "24h")


def settings(data):
    """Every simple Key="value" line of a profile file."""
    return dict(re.findall(r'^([^=\r\n/]+)="([^"]*)"', data.decode("latin1"), re.M))


def key_matches(key, suffix):
    """Whether a profile key is the one named by `suffix`: equal, or ending in it after a mode prefix (FRACE, QUICK...); `a|b` lists alternatives."""
    return any(key == alt or key.endswith(" " + alt) for alt in suffix.split("|"))


def changed_keys():
    old = settings(subprocess.run(["git", "show", "HEAD:" + PLR], cwd=ROOT, capture_output=True).stdout)
    new = settings((ROOT / PLR).read_bytes())
    return {k for k in new if new[k] != old.get(k)}


def baseline_noise():
    """Profile keys the game rewrites on exit whatever is clicked: a game run that only navigates the same pages (tour_options_main)."""
    print("== baseline (navigation only, to find the keys the game rewrites on exit by itself)", flush=True)
    before = suite.untracked()
    if not start_with_retry():
        return None
    r = suite.nav("path", str(suite.PATHS / "tour_options_main.txt"))
    if r.returncode or not suite.exit_game():
        print("the baseline run failed:", (r.stdout + r.stderr).strip()[-300:])
        return None
    noise = changed_keys()
    suite.revert_and_check(before)
    print("  %d keys changed with no clicks: %s" % (len(noise), ", ".join(sorted(noise)) or "-"), flush=True)
    return noise


def start_with_retry():
    """The game window sometimes cannot be brought to the front right after it opens (a notification took the focus): try `ready` once more."""
    if suite.start_game():
        return True
    r = suite.nav("ready", "--timeout", "30")
    print(r.stdout.strip() or r.stderr.strip())
    return r.returncode == 0


def evaluate(mode, clicked, noise):
    """(lines, ok): the screen and the profile on disk against what the clicks should have done. `noise` = keys the game rewrites by itself."""
    changed = changed_keys()
    lines, ok = [], True
    on_screen = [c for c in clicked if c["changed"]]
    lines.append("  %d controls clicked, %d changed on screen, %d profile keys changed" % (len(clicked), len(on_screen), len(changed)))
    wrong = ["%s %s" % (c["page"], c["kind"]) for c in clicked if c["expected"] and not c["changed"]]
    if wrong:
        ok = False
        lines.append("  DID NOT CHANGE ON SCREEN BUT SHOULD HAVE: " + "; ".join(wrong))
    odd = ["%s %s" % (c["page"], c["kind"]) for c in clicked if c["changed"] and not c["expected"]]
    if odd:       # the 'inert' spinners change on screen only now and then here: reported, not a failure
        lines.append("  changed on screen though listed inert (flaky, not a failure): " + "; ".join(odd))
    required = sorted({c["key"] for c in on_screen if c["key"]})
    missing = [s for s in required if not any(key_matches(k, s) for k in changed)]
    if missing:
        ok = False
        lines.append("  CHANGED ON SCREEN BUT NOT IN THE PROFILE: " + ", ".join(missing))
    allowed = {v for page in coords.CONTROL_PAGES.values() for v in page.values()} | \
        {v for page in coords.LOCAL_WORKING.values() for v in page.values()}
    unexplained = sorted(k for k in changed - set(noise or ()) - coords.SIDE_EFFECT_KEYS if not any(key_matches(k, s) for s in allowed))
    if unexplained:
        if mode == "main":
            ok = False
            lines.append("  CHANGED IN THE PROFILE BUT NOT BY AN EXPECTED CONTROL: " + ", ".join(unexplained))
        else:
            lines.append("  also changed (the mode's own track, car, driver...): " + ", ".join(unexplained[:8]))
    return lines, ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="comma separated: " + ", ".join(MODES))
    a = ap.parse_args()
    modes = [m for m in MODES if not a.only or m in a.only.split(",")]
    if suite.game_running():
        print("GTR2 is already running; close it first (nothing was started)")
        return 2
    if suite.dirty_tracked() or suite.untracked():
        print("UserData or ReplayData has uncommitted changes; commit or revert them first (the run reverts these folders)")
        return 2
    noise = baseline_noise() if "main" in modes else None
    if "main" in modes and noise is None:
        return 1
    all_ok = True
    for mode in modes:
        name = "controls_" + mode
        if not (suite.PATHS / (name + ".txt")).exists():
            print("%s: tour file missing (run scripts\\gen-controls-tours.py)" % name)
            return 2
        print("== %s" % name, flush=True)
        before = suite.untracked()
        LOG.unlink(missing_ok=True)
        if not start_with_retry():
            print("the game never reached the main menu; stopping")
            return 1
        r = suite.nav("path", *suite.flags_of(name), str(suite.PATHS / (name + ".txt")))
        out = (r.stdout + r.stderr).strip().splitlines()
        for line in out:
            if "!CONTROLS" in line or "stopped at" in line or "refused" in line or "NOT verified" in line or "path of" in line:
                print("  " + line)
        ok = r.returncode == 0
        if not suite.exit_game():
            print("the game is still open (not on the main menu): close it by hand; nothing was reverted")
            return 1
        clicked = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()] if LOG.exists() else []
        lines, good = evaluate(mode, clicked, noise)
        print("\n".join(lines))
        ok = ok and good
        ok = suite.revert_and_check(before) and ok
        print("%s: %s" % (name, "ok" if ok else "FAILED"), flush=True)
        all_ok = all_ok and ok
        if r.returncode:
            break
    print("\n%s" % ("all control checks passed" if all_ok else "SOME CONTROL CHECKS FAILED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
