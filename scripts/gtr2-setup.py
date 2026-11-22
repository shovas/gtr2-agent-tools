"""Guided first-time setup for the GTR2 tools (Windows). Standard library only ON PURPOSE: it runs before scripts/.venv exists (it creates it), so it cannot import anything that is installed there. Other tools may use dependencies.

Purpose: ask for (or detect) everything that differs between machines, show it all for review, and only then change anything:
  the game folder, the player profile, the window size, the Python environment, git tracking of the game folder, vJoy.
  It writes gtr2-tools.json (git-ignored, in the repository root), which every tool reads as the fallback after the
  GTR2_ROOT / GTR2_PROFILE environment variables, then runs the first-run steps (bootstrap launch, window size, preflight).
Usage:   python scripts/gtr2-setup.py [--game-root DIR] [--profile NAME] [--resolution WxH] [--shader TEXT] [--yes] [--dry-run]
                                      [--no-venv] [--no-git] [--no-launch] [--no-claude-md] [--suite] [--check-deps]
         --check-deps  only list the requirements (DEPENDENCIES.md) and what was found on this machine, then exit
         --yes      take the detected/default answer for every question (still prints the review, does not wait)
         --dry-run  ask and review, change nothing
         --no-launch  do not start the game (skips the bootstrap run and the window-size check)
         --suite    finish by running the full navigation suite (about 6 minutes; needs the PC left alone)
Example: python scripts\\gtr2-setup.py --dry-run
"""
import argparse
import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
TEMPLATE = TOOLS / "templates" / "game-folder-CLAUDE.md"      # agent instructions for the game folder
TEMPLATE_MARKER = "<!-- gtr2-agent-tools: game-folder instructions v1 -->"
MERGE_NAME = "CLAUDE.gtr2-tools.md"
SCRIPTS = TOOLS / "scripts"
CONFIG = TOOLS / "gtr2-tools.json"
VENV_PY = SCRIPTS / ".venv" / "Scripts" / "python.exe"
STEAM_APP = "8790"            # GTR 2 - FIA GT Racing Game on Steam
SIZES = [(1920, 1080), (1600, 900), (1366, 768), (1280, 720), (1024, 768), (800, 600)]


# ---------- small helpers
def say(msg=""):
    print(msg, flush=True)


def ask(question, default="", yes=False):
    """Prompt with a default; --yes takes the default without waiting."""
    shown = " [%s]" % default if default != "" else ""
    if yes:
        say("%s%s -> %s" % (question, shown, default or "(none)"))
        return default
    try:
        got = input("%s%s: " % (question, shown)).strip()
    except EOFError:
        got = ""
    return got or default


def confirm(question, default=True, yes=False):
    d = "Y/n" if default else "y/N"
    if yes:
        say("%s [%s] -> %s" % (question, d, "yes" if default else "no"))
        return default
    try:
        got = input("%s [%s]: " % (question, d)).strip().lower()
    except EOFError:
        got = ""
    return default if not got else got.startswith("y")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ---------- detection
def steam_libraries():
    """Steam library folders (steamapps parents) from the registry and libraryfolders.vdf."""
    roots = []
    try:
        import winreg
        for hive, key, name in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(Path(winreg.QueryValueEx(k, name)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    libs = []
    for r in roots:
        libs.append(r)
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
    out, seen = [], set()
    for p in libs:
        if str(p).lower() not in seen:
            seen.add(str(p).lower())
            out.append(p)
    return out


def looks_like_game(p):
    return p.is_dir() and (p / "GTR2.exe").is_file() and (p / "GameData").is_dir()


def detect_game_roots():
    found = []
    for lib in steam_libraries():
        manifest = lib / "steamapps" / ("appmanifest_%s.acf" % STEAM_APP)
        if manifest.is_file():
            m = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding="utf-8", errors="replace"))
            if m and looks_like_game(lib / "steamapps" / "common" / m.group(1)):
                found.append(lib / "steamapps" / "common" / m.group(1))
    for cand in (os.environ.get("GTR2_ROOT"), json.loads(CONFIG.read_text(encoding="utf-8")).get("game_root") if CONFIG.is_file() else None,
                 Path.cwd()):
        if cand and looks_like_game(Path(cand)):
            found.append(Path(cand))
    out, seen = [], set()
    for p in found:
        if str(p).lower() not in seen:
            seen.add(str(p).lower())
            out.append(p)
    return out


def work_area_and_scale():
    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
    rect = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)   # SPI_GETWORKAREA
    try:
        scale = ctypes.windll.user32.GetDpiForSystem() / 96.0
    except Exception:
        scale = 1.0
    return rect.right - rect.left, rect.bottom - rect.top, scale


def sizes_that_fit(workw, workh, scale):
    """Window sizes (client) whose frame fits the work area; GTR2 is not DPI aware, so Windows scales the whole window."""
    return [(w, h) for w, h in SIZES if (w + 6) * scale <= workw and (h + 35) * scale <= workh]


def profiles(root):
    ud = root / "UserData"
    if not ud.is_dir():
        return []
    return sorted(d.name for d in ud.iterdir() if d.is_dir() and (d / (d.name + ".PLR")).is_file())


def vjoy_installed():
    for p in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        if p and (Path(p) / "vJoy").is_dir():
            return True
    return False


def vjoy_bound(root, profile):
    """Whether the profile's driving keys are bound to vJoy device 1 as the analog driver expects."""
    plr = root / "UserData" / profile / (profile + ".PLR")
    if not plr.is_file():
        return None
    text = plr.read_bytes().decode("latin1")
    return 'Control - Accelerate="(1, 6)"' in text and 'Control - Brake="(1, 8)"' in text


# The default GTR2 environment of these tools (user requirement, 2026-11-22): Simulation mode, every driving assist off, no corner or pit-spot marker graphics.
# The driver must run on real data (track geometry, speed, momentum), and an assist takes over the inputs the driver makes. gtr2-lap-check.py also writes these
# values into the profile before every run, so a profile that drifts back is corrected at the next run.
ENVIRONMENT = {
    "Difficulty Type": "2", "Steering Help": "0", "Brake Help": "0", "Stability Control": "0", "Traction Control": "0.00000", "Auto Clutch": "0",
    "Invulnerability": "0", "Spin Recovery": "0", "Opposite Lock": "0", "Auto Reverse": "0", "Shift Mode": "0",
    "Corner Markers": "0", "Pit Spot Marker": "0",
}


def environment_state(plr):
    """(differences, missing): {key: (current, wanted)} for the ENVIRONMENT keys in the profile file, and the keys it does not have."""
    text = plr.read_bytes().decode("latin1")
    diff, missing = {}, []
    for key, want in ENVIRONMENT.items():
        m = re.search(r'^%s="([^"]*)"' % re.escape(key), text, re.M)
        if not m:
            missing.append(key)
        elif m.group(1) != want and not (key == "Traction Control" and float(m.group(1) or 0) == 0.0):
            diff[key] = (m.group(1), want)
    return diff, missing


def apply_environment(plr):
    """Write the ENVIRONMENT values into the profile, byte for byte otherwise (the NUL header and the trailing // comments stay). Returns the changed keys."""
    raw = plr.read_bytes()
    text = raw.decode("latin1")
    changed = []
    for key, want in ENVIRONMENT.items():
        pat = re.compile(r'^(%s=")([^"]*)(")' % re.escape(key), re.M)
        m = pat.search(text)
        if m and m.group(2) != want and not (key == "Traction Control" and float(m.group(2) or 0) == 0.0):
            text = text[:m.start(2)] + want + text[m.end(2):]
            changed.append(key)
    if changed:
        plr.write_bytes(text.encode("latin1"))
    return changed


def git_info(root):
    r = run(["git", "--version"])
    have = r.returncode == 0
    return have, (root / ".git").exists()


def documents_gtr2():
    docs = Path(os.path.expanduser("~")) / "Documents" / "GTR2"
    try:
        import ctypes.wintypes as w
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(0, 5, 0, 0, buf) == 0:      # CSIDL_PERSONAL
            docs = Path(buf.value) / "GTR2"
    except Exception:
        pass
    return docs


def claude_md_state(root):
    """'absent' (no CLAUDE.md), 'merged' (it already carries our marker) or 'other' (someone else's CLAUDE.md that must be merged)."""
    f = root / "CLAUDE.md"
    if not f.is_file():
        return "absent"
    return "merged" if TEMPLATE_MARKER in f.read_text(encoding="utf-8", errors="replace") else "other"


def requirements():
    """(name, needed, status) for everything DEPENDENCIES.md lists. Checks only; changes nothing."""
    rows = []
    rows.append(("Windows 10/11", "yes", "%s %s" % (platform.system(), platform.release())))
    rows.append(("Windows PowerShell 5.1", "yes", "found" if shutil.which("powershell") else "NOT FOUND"))
    v = sys.version_info
    rows.append(("Python 3.11+", "yes", "%d.%d.%d%s" % (v[0], v[1], v[2], "" if v >= (3, 11) else " (too old)")))
    rows.append(("git", "yes", "found" if shutil.which("git") else "NOT FOUND (install Git for Windows)"))
    cands = detect_game_roots()
    rows.append(("GTR 2 (Steam app %s)" % STEAM_APP, "yes", ("found: %s" % cands[0]) if cands else "not detected (you will be asked for the folder)"))
    rows.append(("vJoy 2.1.8 (driver)", "analog driving only", "installed" if vjoy_installed() else "not installed"))
    want = []
    for line in (SCRIPTS / "requirements.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s#]+)", line)
        if m:
            want.append((m.group(1), m.group(2)))
    have = {}
    if VENV_PY.is_file():
        probe = ("import importlib.metadata as m, json, sys\n"
                 "d = {}\n"
                 "for n in sys.argv[1:]:\n"
                 "    try:\n"
                 "        d[n] = m.version(n)\n"
                 "    except Exception:\n"
                 "        pass\n"
                 "print(json.dumps(d))\n")
        r = subprocess.run([str(VENV_PY), "-c", probe] + [n for n, _v in want], capture_output=True, text=True)
        try:
            have = json.loads(r.stdout)
        except ValueError:
            have = {}
    optional = {"capstone", "pefile"}
    for n, pin in want:
        if not VENV_PY.is_file():
            st = "not installed (setup creates scripts\\.venv)"
        elif n in have:
            st = "installed %s%s" % (have[n], "" if have[n] == pin else " (pinned %s)" % pin)
        else:
            st = "not installed"
        rows.append(("%s==%s" % (n, pin), "optional" if n in optional else "yes", st))
    return rows


def print_requirements():
    say("Requirements (what each is for: DEPENDENCIES.md):")
    for name, need, status in requirements():
        say("  %-26s %-20s %s" % (name, "needed" if need == "yes" else need, status))
    say()


def game_running():
    r = run(["tasklist", "/FO", "CSV", "/NH"])
    return [n for n in ("GTR2.exe", "GTR2Config.exe", "GTR2Dedicated.exe") if n.lower() in r.stdout.lower()]


# ---------- the questions
def gather(a):
    ans = {}
    say("GTR2 tools setup. Nothing is changed until you have reviewed everything at the end.\n")
    print_requirements()
    if sys.version_info < (3, 11):
        say("WARNING: Python %d.%d found; the pinned numpy/Pillow need 3.11 or newer for the venv." % sys.version_info[:2])
    running = game_running()
    if running:
        say("WARNING: %s is running. Close the game before the launch steps." % ", ".join(running))

    # 1. game folder
    cands = detect_game_roots()
    if a.game_root:
        default = a.game_root
    elif cands:
        default = str(cands[0])
        say("Detected game folder(s): " + "; ".join(str(c) for c in cands))
    else:
        default = ""
        say("No GTR2 install detected automatically.")
    while True:
        root = Path(ask("1. Game folder (the one that holds GTR2.exe)", default, a.yes).strip('"'))
        if looks_like_game(root):
            break
        say("   %s does not look like a GTR2 folder (needs GTR2.exe and GameData)." % root)
        if a.yes:
            sys.exit("setup: no usable game folder")
        default = ""
    ans["game_root"] = str(root.resolve())

    # 2. profile
    prof = profiles(root)
    if a.profile:
        ans["profile"] = a.profile
    elif len(prof) == 1:
        say("2. Player profile: only one found (%s); it will be used." % prof[0])
        ans["profile"] = prof[0]
    elif prof:
        say("2. Player profiles found: " + ", ".join(prof))
        pick = ask("   Profile to use (empty = newest, picked automatically)", "", a.yes)
        ans["profile"] = pick
    else:
        say("2. No player profile yet; the game creates a placeholder on its first full run. The newest profile is used automatically.")
        ans["profile"] = ""

    # 3. window size
    ww, wh, scale = work_area_and_scale()
    fit = sizes_that_fit(ww, wh, scale)
    say("3. Screen work area %dx%d, display scale %d%%. Window sizes that fit: %s" % (ww, wh, round(scale * 100), ", ".join("%dx%d" % s for s in fit) or "none"))
    default_res = a.resolution or ("1280x720" if (1280, 720) in fit else "640x480")
    ans["resolution"] = ask("   Test window size: the tools run the game windowed at this size, and it must fit the screen with its title bar (1280x720 on a 1080p screen; 640x480 on a 4:3 screen)", default_res, a.yes)
    if not re.fullmatch(r"\d+x\d+", ans["resolution"].replace(" ", "")):
        sys.exit("setup: bad resolution %r (use WxH)" % ans["resolution"])
    ans["resolution"] = ans["resolution"].replace(" ", "")
    ans["shader"] = ask("   Shader level (matched by text against GTR2Config's list; usual options: Auto, DirectX 9, DirectX 8, DirectX 7)",
                        a.shader or "Auto", a.yes)

    # 4. environment, git, vJoy (detected, confirmed)
    ans["venv"] = (not a.no_venv) and confirm("4. Create the Python environment scripts\\.venv and install scripts\\requirements.txt (numpy, Pillow, mss, capstone, pefile; see DEPENDENCIES.md)?",
                                              not VENV_PY.is_file(), a.yes)
    have_git, is_repo = git_info(root)
    if not have_git:
        say("5. git not found on PATH: the tools use git to revert the game's profile files after tests; install Git for Windows first.")
        ans["git_init"] = False
    elif is_repo:
        say("5. The game folder is already a git repository.")
        ans["git_init"] = False
    else:
        ans["git_init"] = (not a.no_git) and confirm("5. The game folder is not a git repository. Initialise one and commit its current state "
                                                     "(the tools revert game-written files with git; the commit may take a few minutes)?", True, a.yes)
    vj = vjoy_installed()
    say("6. vJoy (needed only for analog driving): %s." % ("installed" if vj else "NOT installed (https://github.com/njz3/vJoy, device 1 with X, Y, Z, Rx axes and 2 buttons)"))
    if vj and prof:
        bound = vjoy_bound(root, ans["profile"] or prof[-1])
        say("   Profile driving keys bound to vJoy: %s" % ({True: "yes", False: "no (see CLAUDE.md, 'Driving needs vJoy')", None: "unknown"}[bound]))
    plr_path = (root / "UserData" / ans["profile"] / (ans["profile"] + ".PLR")) if ans["profile"] else (root / "UserData" / prof[-1] / (prof[-1] + ".PLR") if prof else None)
    ans["environment"] = False
    if plr_path is not None and plr_path.is_file():
        diff, missing = environment_state(plr_path)
        if diff:
            say("   Game environment of the tools: Simulation mode, all driving assists off, corner and pit-spot markers off. The profile differs in: " +
                ", ".join("%s %s -> %s" % (k, v[0], v[1]) for k, v in diff.items()))
            ans["environment"] = confirm("   Set these in the profile (only those keys change; the driver needs them: an assist takes over the driver's inputs, and the corner markers must not be a source of information)?", True, a.yes)
            ans["plr_path"] = str(plr_path)
        else:
            say("   Game environment (Simulation mode, assists off, markers off): the profile already has it.")
    else:
        say("   Game environment (Simulation mode, assists off, markers off): no profile file yet. The lap runner writes these values into the profile before every run; rerun setup after the game has created the profile to set them permanently.")
    docs = documents_gtr2()
    if (root / "config" / "Documents-Config.ini").is_file():
        say("7. The game folder already has its own config (config\\Documents-Config.ini): no bootstrap needed, Documents\\GTR2 is left alone.")
    else:
        say("7. Documents\\GTR2 %s. The first launch needs it ABSENT: %s" % (
            "exists" if docs.exists() else "is absent",
            "it will be copied aside, removed, and put back after the game wrote its fresh default config (verified restore)." if docs.exists() else "nothing to move."))
    ans["launch"] = (not a.no_launch) and confirm("   Start the game now for the first-run steps (bootstrap config, then set and verify the window size)? "
                                                 "Leave the PC alone while it runs (about 2 minutes).", True, a.yes)
    state = claude_md_state(root)
    ans["claude_md"] = False
    if not a.no_claude_md and TEMPLATE.is_file():
        msg = {"absent": "8. The game folder has no CLAUDE.md. Copy in the game-folder agent instructions (templates/game-folder-CLAUDE.md)?",
               "merged": "8. The game folder's CLAUDE.md already has the game-folder instructions: nothing to add.",
               "other": "8. The game folder already has its own CLAUDE.md. It will NOT be changed; the new instructions are written next to it as %s "
                        "and you will be shown what to tell your agent so it merges them." % MERGE_NAME}[state]
        ans["claude_md"] = (state == "other") or (state == "absent" and confirm(msg, True, a.yes))
        if state != "absent":
            say(msg)
    ans["claude_md_state"] = state
    ans["suite"] = a.suite
    ans["learn"] = False
    if ans["resolution"] != "1280x720":
        local = SCRIPTS / "gtr2_ui" / "baselines" / "local" / ans["resolution"]
        if not (local.is_dir() and any(local.glob("*.png"))):
            say("   %s has no reference pictures yet: only 1280x720 ships with them. The navigator needs them to recognise the menu pages, so setup can learn them now:" % ans["resolution"])
            say("   it runs a full navigation sweep of every tour in the game (about 10 minutes, plus about 4 to build the page-pair scores) and saves a picture of each page.")
            say("   The PC must be left alone meanwhile. Choose 1280x720 on a 16:9 screen to skip this; use 640x480 on a 4:3 screen.")
            ans["learn"] = confirm("   Learn the reference pictures for %s at the end of setup?" % ans["resolution"], True, a.yes)
    return ans


def review(ans, a):
    say("\n==== Review ====")
    say("  game folder     : %s" % ans["game_root"])
    say("  player profile  : %s" % (ans["profile"] or "(newest, automatic)"))
    say("  window size     : %s (windowed)" % ans["resolution"])
    say("  shader level    : %s" % ans["shader"])
    say("  settings file   : %s (git-ignored)" % CONFIG)
    say("  Python env      : %s" % ("create scripts\\.venv" if ans["venv"] else "leave as is"))
    say("  game CLAUDE.md  : %s" % ({"absent": "copy in the game-folder instructions", "other": "write %s next to the existing CLAUDE.md (your agent merges it)" % MERGE_NAME,
                                      "merged": "already there"}[ans["claude_md_state"]] if ans["claude_md"] or ans["claude_md_state"] == "merged" else "skipped"))
    say("  game folder git : %s" % ("git init + baseline commit" if ans["git_init"] else "leave as is"))
    say("  game environment: %s" % ("set Simulation mode, all assists off, markers off in the profile" if ans.get("environment") else "unchanged"))
    say("  first launch    : %s" % ("bootstrap config, set and verify the window size, preflight" if ans["launch"] else "skipped"))
    if ans["learn"]:
        say("  reference pictures: learn for %s (full navigation sweep, about 15 minutes)" % ans["resolution"])
    say("  navigation suite: %s" % ("run at the end" if ans["suite"] else "not run (use --suite)"))
    if a.dry_run:
        say("  (dry run: nothing will be changed)")


# ---------- the work
def step(title, ok, detail=""):
    say("  [%s] %s%s" % ("ok" if ok else "FAILED", title, (": " + detail) if detail else ""))
    return ok


def ps(script, *args, root):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPTS / script), *args, "-Root", str(root)]
    return run(cmd, cwd=str(root))


def execute(ans):
    root = Path(ans["game_root"])
    say("\n==== Setting up ====")
    cfg = {"game_root": ans["game_root"], "resolution": ans["resolution"], "shader": ans["shader"]}
    if ans["profile"]:
        cfg["profile"] = ans["profile"]
    CONFIG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    ok = step("wrote %s" % CONFIG.name, True)
    os.environ["GTR2_ROOT"] = ans["game_root"]

    if ans["venv"]:
        r = run([sys.executable, "-m", "venv", str(SCRIPTS / ".venv")])
        ok &= step("created scripts\\.venv", r.returncode == 0, "" if r.returncode == 0 else r.stderr.strip()[-200:])
        if r.returncode == 0:
            r = run([str(VENV_PY), "-m", "pip", "install", "-r", str(SCRIPTS / "requirements.txt")])
            ok &= step("installed scripts\\requirements.txt (see DEPENDENCIES.md)", r.returncode == 0, "" if r.returncode == 0 else r.stderr.strip()[-200:])
    if ans["claude_md"]:
        dst = root / ("CLAUDE.md" if ans["claude_md_state"] == "absent" else MERGE_NAME)
        dst.write_bytes(TEMPLATE.read_bytes())
        ok &= step("game-folder agent instructions written", dst.is_file(), str(dst))
        if ans["claude_md_state"] == "other":
            say("")
            say("  The game folder already had a CLAUDE.md, so nothing was overwritten. Tell your coding agent (copy this):")
            say('    "Merge the new instructions in %s into CLAUDE.md in this folder. Keep every existing instruction, add the new ones,' % MERGE_NAME)
            say("     ask me about any conflict, keep the line '%s' so setup knows it is merged, then delete %s.\"" % (TEMPLATE_MARKER, MERGE_NAME))
            say("")
    if ans.get("environment"):
        try:
            changed = apply_environment(Path(ans["plr_path"]))
            ok &= step("game environment (Simulation mode, assists off, markers off)", True, "changed " + (", ".join(changed) or "nothing"))
        except OSError as e:
            ok &= step("game environment", False, str(e))
    if ans["git_init"]:
        steps = [["git", "init", "-q", "-b", "main"], ["git", "config", "core.autocrlf", "false"], ["git", "add", "-A"]]
        if not (root / ".gitattributes").exists():
            (root / ".gitattributes").write_bytes(b"* -text\nConfig.ini diff\n*.PLR diff\nraceresults.txt diff\n")
        good = True
        for c in steps:
            r = run(c, cwd=str(root))
            good &= r.returncode == 0
        ident = run(["git", "config", "user.email"], cwd=str(root)).stdout.strip()
        cmt = ["git"] + ([] if ident else ["-c", "user.name=GTR2 tools", "-c", "user.email=gtr2-tools@localhost"]) + \
              ["commit", "-q", "-m", "Baseline: game folder as found by the GTR2 tools setup"]
        r = run(cmt, cwd=str(root))
        ok &= step("game folder git baseline", good and r.returncode == 0, "" if r.returncode == 0 else r.stderr.strip()[-200:])
    if ans["launch"]:
        running = game_running()
        if running:
            ok &= step("game launch steps", False, "%s is running; close it and rerun setup" % ", ".join(running))
        else:
            cfgfile = root / "config" / "Documents-Config.ini"
            if cfgfile.is_file():
                step("first-run config", True, "already exists (%s), no bootstrap needed" % cfgfile)
            else:
                r = ps("gtr2-launch.ps1", root=root)                # no local config yet: the launcher does the bootstrap run, then exits
                ok &= step("first-run config (bootstrap)", cfgfile.is_file(), (r.stdout + r.stderr).strip()[-300:] if not cfgfile.is_file() else str(cfgfile))
            if cfgfile.is_file():
                r = ps("gtr2-set-resolution.ps1", "-Resolution", ans["resolution"], "-Shader", ans["shader"], root=root)
                good = r.returncode == 0
                ok &= step("window size %s set and verified by launching" % ans["resolution"], good,
                           "" if good else (r.stdout + r.stderr).strip()[-400:] + "\n         try: scripts\\gtr2-set-resolution.ps1 -List, then -Resolution WxH -VideoMode N")
    if VENV_PY.is_file():
        r = run([str(VENV_PY), "-I", str(SCRIPTS / "gtr2-nav.py"), "preflight"], cwd=str(root))
        ok &= step("preflight (session, config, no other GTR2, capture)", r.returncode == 0, "" if r.returncode == 0 else r.stdout.strip()[-400:])
    if ans["learn"] and VENV_PY.is_file():
        say("  learning the reference pictures for %s (a full navigation sweep, about 15 minutes; leave the PC alone)..." % ans["resolution"])
        r = subprocess.run([str(VENV_PY), "-I", str(SCRIPTS / "gtr2-nav-suite.py"), "--learn"], cwd=str(root))
        ok &= step("reference pictures learned for %s" % ans["resolution"], r.returncode == 0)
    if ans["suite"] and VENV_PY.is_file():
        say("  running the navigation suite (about 6 minutes)...")
        r = subprocess.run([str(VENV_PY), "-I", str(SCRIPTS / "gtr2-nav-suite.py")], cwd=str(root))
        ok &= step("navigation suite", r.returncode == 0)
    say("\n%s" % ("Setup finished. Next: scripts\\.venv\\Scripts\\python.exe -I scripts\\gtr2-nav-suite.py (full navigation test)"
                  if ok else "Setup finished with problems (see FAILED above)."))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--game-root")
    ap.add_argument("--profile")
    ap.add_argument("--resolution")
    ap.add_argument("--shader", help="Shader Level drop-down choice by text (default Auto)")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-venv", action="store_true")
    ap.add_argument("--no-git", action="store_true")
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--no-claude-md", action="store_true", help="do not add the game-folder agent instructions (CLAUDE.md)")
    ap.add_argument("--suite", action="store_true")
    ap.add_argument("--check-deps", action="store_true", help="only list the requirements (DEPENDENCIES.md) and what was found, then exit")
    a = ap.parse_args()
    if os.name != "nt":
        sys.exit("setup: these tools are for Windows")
    if a.check_deps:
        print_requirements()
        return 0
    ans = gather(a)
    review(ans, a)
    if a.dry_run:
        return 0
    if not confirm("\nProceed with exactly this?", True, a.yes):
        say("Nothing changed.")
        return 0
    return execute(ans)


if __name__ == "__main__":
    sys.exit(main())
