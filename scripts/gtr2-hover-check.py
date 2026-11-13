"""Hover over every button of every page the tours reach and list the buttons that do not visibly react.

Purpose: find greyed-out, inert or highlight-less buttons in this profile's state, deterministically and without clicking anything It takes the navigation tours of the suite (races and the control sweeps are left out), adds a
`!HOVER` step after the first arrival on each page, runs them in one game launch in the suite's order, closes the game through its menus,
reverts the profile and writes scripts/gtr2_ui/hover_silent.json: for each page, how many buttons were tried and which did not react.
A button reacts if its picture changes by more than 3.0 (mean) within 0.4 s of the mouse arriving. A page that animates behind its buttons
(a live monitor view) can hide a silent button, so treat the list as a lead, not proof.
Usage:   scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-hover-check.py [--only NAME,NAME] [--dry-run]
Example: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-hover-check.py --only options_main,setup_practice
About 8 minutes for all tours. Exit code 0 only if every tour ran and cleanup was clean.
"""
import argparse
import importlib.util
import json
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
import menumap  # noqa: E402

PAGES, _DUPS = menumap.load()
OUT = SCRIPTS / "gtr2_ui" / "hover_silent.json"
LOG = SCRIPTS / "gtr2_ui" / "runs" / "hover_results.jsonl"
TOUR_DIR = SCRIPTS / "gtr2_ui" / "runs" / "hover_tours"
SKIP = ("!RACE", "!NEXTSESSION", "!CONTROLS")        # race and control-sweep tours: other tours reach the same pages


def hover_version(name, seen):
    """Lines of the tour with a `!HOVER` step after each first arrival on a page of the menu map (and on the page it starts from)."""
    text = (suite.PATHS / (name + ".txt")).read_text(encoding="utf-8")
    header = [l for l in text.splitlines() if l.startswith("#")]
    out = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        out.append(line)
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 3 or cols[1].startswith("!"):
            continue
        dest = cols[2]
        if dest in PAGES and dest not in seen:
            seen.add(dest)
            out.append("%s | !HOVER | %s" % (dest, dest))
    return header, out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", help="comma separated tour names (with or without tour_ prefix)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    names = [t for t in suite.ORDER if (suite.PATHS / (t + ".txt")).exists()]
    names = [t for t in names if not any(s in (suite.PATHS / (t + ".txt")).read_text(encoding="utf-8") for s in SKIP)]
    if a.only:
        want = {w if w.startswith("tour_") else "tour_" + w for w in a.only.split(",")}
        names = [t for t in names if t in want]
    skipped = [t for t in names if suite.needs_unlock(t) and not (suite.ROOT / "SDNDTG.DYN").exists()]
    names = [t for t in names if t not in skipped]
    seen = {"MAIN MENU"}
    TOUR_DIR.mkdir(parents=True, exist_ok=True)
    plan = []
    for t in names:
        header, steps = hover_version(t, seen)
        if t == names[0]:
            steps.insert(0, "MAIN MENU | !HOVER | MAIN MENU")
        path = TOUR_DIR / ("hover_" + t[len("tour_"):] + ".txt")
        path.write_text("\n".join(header + steps) + "\n", encoding="utf-8", newline="\n")
        plan.append((t, path, sum("!HOVER" in s for s in steps)))
    if a.dry_run:
        for t, path, n in plan:
            print("%-32s %3d pages to hover  %s" % (t, n, " ".join(suite.flags_of(t)) or "(no flags)"))
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
    before = suite.untracked()
    LOG.unlink(missing_ok=True)
    if not suite.start_game():
        print("the game never reached the main menu; stopping")
        return 1
    ok, t0 = True, time.time()
    for t, path, n in plan:
        s = time.time()
        r = suite.nav("path", *suite.flags_of(t), str(path), timeout=900)
        out = r.stdout + r.stderr
        if r.returncode:
            bad = [l for l in out.splitlines() if "stopped at" in l or "NOT verified" in l or "refused" in l or "not on" in l]
            print("%-32s FAIL %s" % (t, "; ".join(bad[-2:])))
            print(suite.nav("diagnose").stdout.strip())
            ok = False
            break
        print("%-32s ok   %3d pages hovered  %6.1f s" % (t, n, time.time() - s), flush=True)
    closed = suite.exit_game()
    rows = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()] if LOG.exists() else []
    result = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}     # a partial run (--only) updates its pages and keeps the rest
    for page in {r["page"] for r in rows}:
        result.pop(page, None)
    for r in rows:
        e = result.setdefault(r["page"], {"buttons": 0, "silent": []})
        e["buttons"] += 1
        if not r["reacts"]:
            e["silent"].append("%s (%g,%g)" % (r["label"], r["x"], r["y"]))
    OUT.write_text(json.dumps(dict(sorted(result.items())), indent=1) + "\n", encoding="utf-8", newline="\n")
    tried = sum(e["buttons"] for e in result.values())
    silent = sum(len(e["silent"]) for e in result.values())
    print("\n%d pages, %d buttons tried, %d silent; written to %s" % (len(result), tried, silent, OUT.relative_to(suite.ROOT)))
    if closed:
        ok = suite.revert_and_check(before) and ok
    else:
        ok = False
    print("%d tours in %.0f s" % (len(plan), time.time() - t0))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
