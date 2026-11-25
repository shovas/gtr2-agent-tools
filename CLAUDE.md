# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file is the short, always-loaded core. The long history of what was measured and decided lives in `docs/` (nothing was dropped: the old CLAUDE.md was split verbatim by topic). **Read the matching `docs/` file before working on that topic** (index at the end).

## Rules for every agent

- **Respect other agents' instruction files exactly like this one.** If `AGENTS.md`, `GEMINI.md`, `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`, `.windsurfrules`, `CONVENTIONS.md` or any similar agent-instruction file exists in this repository or in the game folder, read it and follow it with the same weight as `CLAUDE.md`. When two files disagree, the more specific one (closest to the files being changed) wins; when still unclear, ask the user. `AGENTS.md` here only points back to this file.
- **Use only the game folder you were pointed at** (`GTR2_ROOT` / `gtr2-tools.json`). Any other GTR2 install or tools folder on the machine is not part of this project: do not read, run or change it. Mentions of "the other install" or "the earlier harness" in `docs/` are history: where findings came from. **One exception, by the user (2026-11-23): the reference folder `..\gtr2-agent-tools-reference` (three driving and tyre-physics books as PDFs, next to this repository) is meant to be read for driving theory** (`docs/driving-theory.md` says what is in it and how: `scripts\gtr2-pdf-text.py`); never copy those books into this repository.
- **Dependencies are allowed** when they earn their place: pin the exact version in `scripts/requirements.txt`, install into `scripts/.venv`, and say in the script header what it adds. Keep optional extras optional (import inside a try). "Standard library only" in a header describes today, not a rule; only `gtr2-setup.py` (runs before the venv exists) must stay stdlib-only.
- Prefer deterministic local tooling over inference (section below). Commit confident changes to git (this repo and the game folder separately); never push unless the user asks.
- **Start every commit subject with a changelog tag:** `highlight:` (something users of the tools will value: a new ability, faster, easier), `improve:` (mostly agents and tests), `fix:`, `docs:`, or `chore:` (left out of the notes). `CHANGES.md` is generated: run `scripts\.venv\Scripts\python.exe -I scripts\changelog.py --write` before a release (it groups by day, ordered highlights, improvements, fixes, documentation) and `--check` lists untagged commits; `CHANGES.md` is written for end users, so give each user-visible commit a short plain-language line in `scripts/changelog_overrides.json` (and `skip` the agent-only ones); the detailed, agent-level history is `git log`, not `CHANGES.md`. Commit the regenerated file with a `changelog:` subject.
- **Never push without the user's explicit go-ahead for that push, and follow `docs/publishing.md` first** (what may and must not be published, the pre-push procedure, `python -I scripts\publish-check.py`). Committing is not pushing.
- Treat the user's personal details as private: no names, e-mail addresses or absolute user paths in files of this public repo (use `<game folder>`, `<profile>`, relative paths).

## Fresh clone? Start here (no `gtr2-tools.json` in the repository root)

The user has just cloned this repository and wants to use it with their own copy of GTR 2. Do these in order and tell the user what you are doing:

1. `python scripts\gtr2-setup.py --check-deps`: report anything missing (Python 3.11+, git, PowerShell 5.1, the game; vJoy is optional). Do not install drivers for them.
2. Ask the user where their game folder is (the one holding `GTR2.exe`; setup finds a Steam install by itself) and which player profile to use. Tell them the game is run windowed at a test size (the user's own play size never matters: only these tools run the game): 1280x720 on a 1080p screen, which ships with reference pictures; 640x480 on a 4:3 screen, or any other size, for which setup runs a one-time learning sweep (`gtr2-nav-suite.py --learn`, about 15 minutes, PC left alone). Keep the choice to those two.
3. `python scripts\gtr2-setup.py --dry-run`, show the review, then, with the user's go-ahead, `python scripts\gtr2-setup.py`. It writes `gtr2-tools.json`, sets the default game environment in the profile (Simulation mode, every driving assist off, corner and pit-spot markers off: an absolute requirement, `ENVIRONMENT` in `gtr2-setup.py`, also written by `gtr2-lap-check.py` before every run), creates `scripts\.venv`, makes the game folder a git repository (a baseline commit), adds the game-folder `CLAUDE.md`, does the bootstrap launch, sets the window size through `GTR2Config.exe` and checks it by starting the game. Warn the user first: the game starts and clicks by itself, so they must leave the PC alone for a few minutes.
4. Confirm the game reaches the main menu: `scripts\.venv\Scripts\python.exe -I scripts\gtr2-nav.py preflight`, then `... gtr2-nav.py ready` and `where` (it should say MAIN MENU). Close the game with `gtr2-nav.py exit`.
5. Offer the offline tests (`test_nav_guards.py`) and, with the PC left alone for about 6 minutes, the full suite (`gtr2-nav-suite.py`). If a tour fails, read `docs/ui-navigation.md` before changing anything.

Never launch `GTR2.exe` directly (see the rules below). Things that are per machine and not in the repository on purpose: `gtr2-tools.json`, `scripts\.venv\`, `scripts\gtr2_ui\runs\` and everything under the game folder; setup recreates them.

## What this repository is

`gtr2-agent-tools` is the **tooling** for *GTR 2 - FIA GT Racing Game* (Windows, 32-bit, DirectX 9): automation for launching it safely, setting its window, driving its menus, driving laps, forcing weather, reading crash dumps. It holds `scripts/` (Python + PowerShell), `config/weather/`, `Tools/DocumentsGTR2.ps1`, `docs/` and the offline tests. It contains **no game files**. The game lives in a separate folder (a git repository of its own, with `config/`, `_DocumentsGTR2/` snapshot, `UserData/`, ...); the tools act on it.

- **Game folder and profile resolution** (`scripts/gtr2_ui/diag.py`: `game_root()`, `profile_name()`, `plr_path()`; same order in the PowerShell scripts): `GTR2_ROOT`, else `game_root` in `gtr2-tools.json` (git-ignored, written by setup), else the parent of `scripts/`. Profile: `GTR2_PROFILE`, else `profile` in the file, else the newest `UserData\<name>\<name>.PLR`. Pass `-Root` to PowerShell scripts to override.
- **Per-machine files live in the game folder**, not here: `config\Documents-Config.ini` (adapter id, video mode, relative data paths), `config\resolution-verified.json`, `_DocumentsGTR2\` (snapshot of the live `Documents\GTR2`). Per-run output (`scripts/gtr2_ui/runs/`, git-ignored) and the UI baselines stay here.
- **First-time setup:** `python scripts\gtr2-setup.py [--dry-run|--yes|--suite ...]` detects/asks (game folder, profile, window size, shader), shows a review, then acts (venv, game-folder git, bootstrap launch, window size check, preflight) and adds the game-folder `CLAUDE.md` from `templates/game-folder-CLAUDE.md` (never overwrites: a foreign one gets a `CLAUDE.gtr2-tools.md` plus a prompt telling the user's agent to merge it). Details: `docs/setup-and-config.md`.
- **Dependencies:** `DEPENDENCIES.md` lists everything to install (Windows, PowerShell 5.1, Python 3.11+, git, the game, optional vJoy, the pinned packages) and which feature needs what; `python scripts\gtr2-setup.py --check-deps` shows what this machine has. Keep it in step with `scripts/requirements.txt` when a dependency is added.
- `scripts/README.md` has a one-line index of every script: check it before writing a new one.

## Commands (run from the tools repo; `GTR2_ROOT` or `gtr2-tools.json` must point at the game folder)

```powershell
python scripts\gtr2-setup.py --dry-run                                   # guided setup, review only
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gtr2-launch.ps1            # run the game (ALWAYS through the launcher)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gtr2-set-resolution.ps1 -Resolution 1280x720 [-Shader 'Auto'] [-Dropdowns|-List|-Status]
scripts\.venv\Scripts\python.exe -I scripts\test_nav_guards.py          # offline guard tests (84), no game needed except UIData\gtr2ui.mnu
scripts\.venv\Scripts\python.exe -I scripts\test_garage_map.py          # offline checks of the .gtr/.gmt readers and the garage-wall prediction (needs the Anderstorp files)
scripts\.venv\Scripts\python.exe -I scripts\gtr2-nav-suite.py           # full UI navigation test, 30 tours, about 330 s: leave the PC alone
scripts\.venv\Scripts\python.exe -I scripts\gtr2-nav.py ready|where|goto|path|learn|refine|exit|preflight|diagnose
scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-check.py "Imola4Imol" --input analog --quick   # hands-free lap (needs vJoy)
scripts\.venv\Scripts\python.exe -I scripts\gtr2-weather.py run sunny|rainy|stormy
scripts\.venv\Scripts\python.exe -I scripts\gtr2-crash-report.py --latest [--short]
powershell -NoProfile -ExecutionPolicy Bypass -File Tools\DocumentsGTR2.ps1 [-Update]  # drift of Documents\GTR2 vs the snapshot
```

Always run Python tools with `-I` (isolated). Run one test file/tour: `gtr2-nav.py path [--flags] scripts\nav_paths\<tour>.txt` (flags per the tour's own header, see `docs/ui-navigation.md`).

## Hard-won rules (details and evidence in docs/)

- **Launch the game only through `scripts\gtr2-launch.ps1`.** An unelevated `GTR2.exe` reads `Documents\GTR2\Config.ini` only (no `config=` argument works); the launcher backs `Documents\GTR2` up, swaps in the game folder's own config (relative data paths keep all game data in the game folder), runs the game, always restores and verifies, keeps a lock/state file, never stops another session's GTR2, and sets `__COMPAT_LAYER=DWM8And16BitMitigation` for the game. `-Reap` cleans up after a dead launcher; `-Restore` after an interrupted run. First run without a local config does a bootstrap run (existing `Documents\GTR2` set aside and restored). `docs/launcher-and-config.md`.
- **The compatibility layer decides what `VIDEOMODE` means.** With the layer the raw mode list has 54 more (16-bit) entries in front: 32-bit 1280x720 is index 72 with it, 18 without; a mismatched index crashes at start-up (null deref in `VidMan`) or switches the desktop. Never hard-code an index: choose GTR2Config drop-down entries by their text (`-Dropdowns`, `-Resolution`, `-Shader`, `-Select id=regex`). `docs/crash-and-compat-layer.md`.
- **A game started after the display went to sleep starts slowly** (10 to 20 s in the graphics driver, white window): Windows turns the display off after 10 idle minutes by default. The launcher wakes the display and waits 20 s in that case (`Wake-Display`, `-WakeWait`, `-NoWakeDisplay`); `ready` logs a white/black window of 3 s to `runs/blank_window.log`. `docs/ui-navigation.md`.
- **Only one GTR2 runs at a time** (a second crashes). The game is windowed at the test size (`resolution` in `gtr2-tools.json`, default 1280x720; 640x480 tested for 4:3), moved to the screen's top-left by `gtr2-nav.py ready`. Anything that takes focus pauses the simulation completely; start helper windows hidden/non-activating. Leave the PC alone during suites, laps and races.
- **Input:** hardware scancodes only (`keybd_event` with scancode flag; `SendKeys` does nothing); the game window must be in front; the first click on a button often only hovers (second click acts). Time acceleration is **K** in this setup's profiles (the key is bound per profile: read `Control - Time Acceleration` first).
- **UI safety:** the navigator never presses buttons that start sessions, save, delete, join/host or exit unless the matching opt-in flag is given (`--session-step`, `--popup-step`, `--lan-step`, `--host-step`, `--season-step`, `--drive-step`, `--setting-step`); no online/account pages; the guards are unit-tested (`test_nav_guards.py`: run it after any change to `gtr2-nav.py`, `menumap.py` or `coords.py`).
- **Page recognition** compares screenshots with references (`scripts/gtr2_ui/baselines`, `baselines/local` overrides). After a profile or mode change use `learn --relearn`; `refine` only for popups; never relearn `MAIN MENU` right after leaving a session; run `gtr2-nav.py index` after changing references. References are per test size (`scripts/gtr2_ui/paths.py`): 1280x720 ships; another size needs `gtr2-nav-suite.py --learn` once (writes git-ignored `baselines/local/<size>` and `pair_scores_<size>.json`; learned masks inherit the shipped 1280x720 masks). A different player name does not break recognition (tested). The reference pictures carry no player name: the header name and the name in lists/tables were painted out and masked (`pagerec.NAME_BOX`, `scrub_name`; `learn` scrubs the header name of new references, but not names in lists or tables: check a new picture before committing it). `docs/ui-navigation.md`.
- **Game state:** a run rewrites the profile (`<profile>.PLR`, `Career.blt`, ...), replays and logs in the game folder. The suite reverts them with git (tracked files) and deletes new files; do the same after manual runs (`git checkout -- UserData ReplayData` in the game folder). Tour order matters (state leaks between tours); the suite encodes the order.
- **Track limits are judged by geometry only, never by road surface** (user rule, 2026-11-20): an event is all four tyres wholly beyond the same boundary line. `gtr2_driving/limits.py` builds the left/right boundary polylines from the waypoints as the file gives them (before any line smoothing) and tests every tyre footprint against the nearest boundary segment; the tyre positions and widths are read from the car's own wheel meshes (`*WHEELS.GTR`), the fixed numbers (`--wheel-track`, `--tyre-half`) are only the fallback; `--limit-trim` calibrates the line. Kerbs and rumble strips on the track are fine and kerb strikes have no limit. Surface names are logged as a diagnostic (`geo` in the result) and never decide a lap. If the geometry gives more unclean laps, investigate the geometry, do not go back. Offline checks: `scripts\.venv\Scripts\python.exe -I scripts\test_limits.py`.
- **Editing scripts and docs safely (measured 2026-11-20):** several scripts are CRLF (`file scripts\x.py` says so). `sed -i` on this machine turns a whole CRLF file into LF (91 of 91 line endings on a test copy), and Python's default text mode does the same unless you pass `newline=''` to `open()` for both read and write. Use the Edit tool with a single-line `old_string` (it keeps CRLF), or a patch script written with the Write tool (no shell layer) that reads and writes bytes or `newline=''`. Never put `\n` escapes through a heredoc into a Python string: two layers eat one level of backslashes (a single `\n` becomes a real newline inside the string literal you meant to write). After every edit run `git diff --stat` (the diff must be only your lines) and a syntax check (`python -I -c "import ast;ast.parse(open(F,encoding='utf-8').read())"`).
- **Editing game text files:** `.gdb/.car/.hdc/.tyr/.dmg/.trk/.grd/.cam/.ddb` are CRLF text; `Config.ini`, `<profile>.PLR`, `raceresults.txt` have a NUL-byte header to preserve (use byte-preserving edits, `grep -a`); `.gtr` (MAS archive), `.bch`, `.hat`, `.aiw` are binary. Backups are named `<name>_<ext>_BAK_<YYMMDD>[_TAG]`. Autocrlf is off and `* -text` is set in git: never let line endings change.
- **Driving needs vJoy** (device 1 with X, Y, Z, Rx and 2 buttons) and the profile bound to it (steering X, Accelerate `(1, 6)`, Brake `(1, 8)`, shifts on buttons 1 and 2, `Basic Controls="2"` = JOY1 selected as the wheel on the Controls page, done by `scripts\gtr2-select-wheel.py`; `--input wheel` in the lap runner); the lap runner drives pure pursuit on the AIW line. `docs/analog-driving.md`.
- **Crash dumps** (`UserData\Log\Minidump\*.dmp`, ~230 MB): analyse with `gtr2-crash-report.py`; only the report is kept, never the dump (the suite deletes dumps after writing a report to `scripts/gtr2_ui/runs/crashes/`).
- **Shared folder:** `Documents\GTR2` is shared with any other GTR2 install; never edit it by hand; check drift with `Tools\DocumentsGTR2.ps1` before and after anything that launches the game.
- The game folder has `SDNDTG.DYN` (empty marker: unlocks championships) and `MovieFiles\SimBin.bik.disabled` (intro movie off). The Steam files `installscript.vdf`/`SteamInstallscript.vdf` must not be edited (signed).

## Open items (not done; context in docs/)

- **Documentation set (`AGENTS.md`):** keep `CHANGES.md`, `FEATURES.md`, `CAPABILITIES.md`, `DEPENDENCIES.md` in step with every meaningful change. To do: `CHANGES.md` entries carry only the day, not a time (`YYYY-MM-DD HH:MM:SS +/-HHMM` wanted); the test and sweep scripts (`test_*.py`, `gtr2-nav-suite.py`, `gtr2-lap-campaign.py`) have no `--mode quick|normal|full` yet (suite is about 330 s, so Normal needs a subset of tours).
- **Reminder: full sweep of every car at every track (pit-lane exit and full lap, `--input wheel`) is still to do.** After an interrupted run use `gtr2-recover.py --force --revert` (stale nav servers and an orphaned game make every later run fail).
- Make the nav server optional/simpler (startup under 1 s is acceptable; see `docs/ui-navigation.md`).
- Driving: layouts and cars beyond Imola/Murcielago are untuned (every layout runs clean with defaults); pit-lane exit from the track's `XPITOUT` object was verified only on Imola and Anderstorp S (wheel garage-exit check passed 2026-11-14 at Magny-Cours 4, Hockenheim GP and Zhuhai 4 with 3 cars each; Estoril 3, Dubai 4, Donington 3 still to re-run; `--box-yaw-bias auto` (default) reads the garage walls from the track's own collision meshes, `gtr2-garage-map.py`, `gtr2_driving/{mas,gmt,garage,boxplan}.py`; all 34 layouts pass with the Maserati, see docs/analog-driving.md); Anderstorp S crawled in 1st gear on the pit chain (fix partly in); delay between entering the cockpit and the car moving not measured; wet Driving School levels 4 to 7 unsolved.
- Setup script untested on a machine without Steam/vJoy, with a non-git game folder, and its venv step.
- First-run bootstrap tested with the real game once; `Documents\GTR2` weather.txt drift (`only in snapshot`) is the known harmless drift.

## Docs index (read before working on the topic)

| File | Contents |
|---|---|
| `docs/game-install.md` | what the game install is, folder layout, working notes, shared `Documents\GTR2`, first launch findings (display modes, quitting) |
| `docs/launcher-and-config.md` | clean-slate path, config argument tests, relative data paths, launcher design and hardening, resolution tool, `VIDEOMODE` investigation, GTR2Config drop-downs |
| `docs/driving-and-driving-school.md` | hands-free driving with the keyboard, Time Trial lap save, Driving School challenges (what passed, wet levels, instructor data) |
| `docs/ui-navigation.md` | navigator speed, menu map, tours, guards, suite, hover/control checks, weather forcing, `SDNDTG.DYN`, lap runner, player-name test |
| `docs/analog-driving.md` | vJoy, analog control, tuning, garage/pit exit, all-layout results, focus-loss findings, to-dos, vJoy note |
| `docs/driving-theory.md` | race-driving and tyre theory from the reference books and open papers (racing line, braking, the friction circle, the nadir, Pacejka, iterative learning), where the books are, and the ranked plan for putting it into the driver |
| `docs/crash-and-compat-layer.md` | start-up crash and the compatibility layer, crash dump reader and what the dump showed |
| `docs/setup-and-config.md` | the setup script and `gtr2-tools.json` |
| `docs/lap-session-monitoring.md` | live status of a lap session, the stall watcher (`gtr2-watch.py`), stop requests, what is verified and what is not, how the campaign uses them |
| `docs/imola-slow-corner-2400-2900.md` | Imola 2400 to 2900 m: the causal chain from the logs, every throttle and planner experiment with its result, and what not to repeat |
| `docs/publishing.md` | what may be pushed to GitHub, privacy and safety rules, the pre-push procedure and scanner |

## Working notes (game files)

- Content files (`.gdb`, `.txt`, `.AIW`, `.cam`, `.grd`, `.PLR`, `Config.ini`) are text and safe to edit/diff; `.gtr`, `.gmt`, `.dds`, `.LMA`, `.tyr`, `.dmg`, `.bik` etc. are mostly binary or tool-generated. Some `.txt` files in `Support/` use legacy (non-UTF-8) encoding – preserve bytes when editing.
- Commit to git after every successful change you are confident in. The whole install (~1.6 GB, ~4000 files, mostly binary) is tracked, so `git add` specific paths for routine changes. Autocrlf is off and the tracked `.gitattributes` sets `* -text` (plus text diffs for `Config.ini`, `*.PLR`, `raceresults.txt`); do not let line endings change.
- Adding a track or car generally means adding its folder under `Locations/` or `Teams/` **and** referencing it from a `.gdb` game mode; check an existing entry as the template.

## Prefer deterministic local tooling over inference

Goal: minimize AI token usage and spend. Inference is the expensive, non-repeatable path; a script is cheap, repeatable, and verifiable. Use inference for judgment and code for everything mechanical.

### Before starting any task

1. Check `scripts/README.md` for an existing script that does the job. If one exists, run it.
2. If not, check whether a standard local tool does it: `rg`, `sed`, `awk`, `jq`, `find`, `git`, the project's formatter, linter, test runner, and build tools.
3. Only work through the task directly if neither applies.

### When to write a script

Write a script when the task is deterministic (same input, same output) and at least one of these is true:

- It is likely to recur.
- It touches more than a handful of files or records.
- Doing it by hand would mean reading large files into context.

Typical cases: bulk renames, mechanical refactors, format conversions, data extraction, report generation, log analysis, validation checks, scaffolding.

Do not script tasks that need judgment (design decisions, ambiguous requirements, prose, code review), or one-off tasks where writing the script costs more than doing the work.

### Script conventions

- Save to `scripts/` with a descriptive name and a header comment giving purpose, usage, and an example.
- Take inputs as arguments; no hardcoded paths.
- Make scripts idempotent, with a `--dry-run` flag for anything that modifies or deletes.
- Exit non-zero with a clear message on failure.
- Add a one-line entry to `scripts/README.md`.
- Dependencies are allowed when they earn their place (more information or options than the standard library gives): pin the exact version in `scripts/requirements.txt`, install into `scripts/.venv`, and say in the script header what the dependency adds. Prefer the standard library when it is equally good, and keep optional extras optional (import inside a try) so a tool still runs without them.

### Keep context small

- Search and filter instead of reading whole files.
- Limit command output (`head`, `tail`, `wc`, `jq`) and summarize rather than dump.
- Verify with deterministic checks (tests, `diff`, lint, exit codes) rather than re-reading output.
- Do not spawn subagents for work a command can do.

### Close the loop

- If you do the same manual step twice in a session, stop and propose a script for it.
- When finishing a task, state in one line whether it was scripted, and if not, why.
