# CLAUDE.md

Guidance for Claude Code in this repository: the always-loaded core. Detail lives in the files below. **Before acting on a topic, read the matching file.** `AGENTS.md` only redirects here.

## Read before you act

| Situation | Read |
|---|---|
| Writing or changing a script | `docs/script-conventions.md` |
| Writing a recurring test, sweep, benchmark or parameter search | `docs/execution-modes.md` |
| Editing any file (CRLF scripts, game text and binary files) | `docs/editing-files.md` |
| Committing, or changing `CHANGES.md` | `docs/changelog-policy.md` |
| `gtr2-tools.json` missing (fresh clone) | `docs/fresh-clone.md` |
| Choosing the next task | `docs/open-items.md` |
| Any push or publication | `docs/publishing.md` |
| Full text of the rules below | `docs/agent-rules-detail.md` |
| Game launch, window, resolution, crashes | `docs/launcher-and-config.md`, `docs/crash-and-compat-layer.md` |
| Menus, page recognition, tours | `docs/ui-navigation.md` |
| Driving laps, steering, tuning, vJoy | `docs/analog-driving.md`, `docs/controller-competition.md` |
| Driving theory, tyre physics | `docs/driving-theory.md` |
| Designed-follower redesign | `docs/follower-redesign-plan.md` |
| Setup script, `gtr2-tools.json` | `docs/setup-and-config.md` |
| Driving School, Time Trial | `docs/driving-and-driving-school.md` |
| Lap session status, stall watcher | `docs/lap-session-monitoring.md` |
| Imola 2400 to 2900 m | `docs/imola-slow-corner-2400-2900.md` |
| Game install layout, shared folder | `docs/game-install.md` |
| Yaw-rate spikes | `docs/telemetry-anomalies.md` |
| Sibling conversion repo | `docs/external-conv-review.md` |
| Findings, sources, examination depth | `knowledge/INDEX.md` |

## Rules for every agent

- Other agent files (`AGENTS.md`, `GEMINI.md`, `.cursorrules`, ...) carry the same weight. The more specific file wins; ask when unclear.
- Use only the game folder you were pointed at (`GTR2_ROOT`, `gtr2-tools.json`). One exception: the reference books in `..\gtr2-agent-tools-reference` may be read for driving theory, never copied (`docs/driving-theory.md`).
- Dependencies: pin in `scripts/requirements.txt`, install into `scripts/.venv`, and say in the script header what each adds. Only `gtr2-setup.py` must stay stdlib-only. `DEPENDENCIES.md` lists them.
- Commit confident changes (this repo and the game folder separately). **Never push without the user's explicit go-ahead for that push** (`docs/publishing.md`).
- Commit subjects start with `highlight:`, `improve:`, `fix:`, `docs:` or `chore:`. Regenerate `CHANGES.md` after important commits (`docs/changelog-policy.md`).
- **Evidence first.** Research before reinventing; separate facts, inferences and unknowns; persist until verified or genuinely blocked; never confuse partial progress with success.
- **Documentation.** Keep `FEATURES.md`, `CAPABILITIES.md` and `DEPENDENCIES.md` in step with each meaningful change. Mark items implemented, experimental, partial, unsupported or planned. Never silently rewrite history.
- **Knowledge base.** At the start of a substantive task read `knowledge/INDEX.md`. Never mark a source complete unless it was examined. Keep this file under about 10 KB.
- **Game safety.** Nothing in this file relaxes the game, input or publishing rules.
- **Privacy.** No names, e-mail addresses or absolute user paths in this public repo (use `<game folder>`, `<profile>`, relative paths).

## Repository

`gtr2-agent-tools` is the tooling for *GTR 2 - FIA GT Racing Game* (Windows, 32-bit, DirectX 9): it launches the game safely, sets up, drives menus and laps, forces weather and reads crash dumps. It holds `scripts/`, `config/weather/`, `Tools/DocumentsGTR2.ps1`, `docs/` and the offline tests, and **no game files**. The game is a separate git repository, which the tools act on. Game folder and profile resolution: `scripts/gtr2_ui/diag.py` (`GTR2_ROOT`, then `gtr2-tools.json`, then the parent of `scripts/`). Per-machine files live in the game folder. `scripts/README.md` indexes every script: check it before writing one. **Never launch `GTR2.exe` directly.**

## Commands

Run from the tools repo; `GTR2_ROOT` or `gtr2-tools.json` must point at the game folder. Always run Python tools with `-I`.

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

Run one tour: `gtr2-nav.py path [--flags] scripts\nav_paths\<tour>.txt` (flags in the tour's header; see `docs/ui-navigation.md`).

## Hard-won rules (full text: `docs/agent-rules-detail.md`)

- **Launch only through `scripts\gtr2-launch.ps1`.** It swaps in the game folder's config for `Documents\GTR2` and always restores and verifies it.
- **One GTR2 at a time.** Leave the PC alone during suites, laps and races: a focus change pauses the simulation.
- **Choose GTR2Config drop-down entries by text, never by index.** The compatibility layer changes what `VIDEOMODE` means (`docs/crash-and-compat-layer.md`).
- **A game started after display sleep starts slowly.** The launcher wakes the display (`docs/ui-navigation.md`).
- **Input:** hardware scancodes only; the game window must be in front; `K` is time acceleration in this setup.
- **Navigator safety:** it never presses session, save, delete, host or exit buttons without an opt-in flag, and never opens online pages. Run `test_nav_guards.py` after changing `gtr2-nav.py`, `menumap.py` or `coords.py`.
- **Page recognition** references are per test size. After a profile or mode change run `learn --relearn`. Never leak a player name into a reference picture.
- **Game state:** a run rewrites the profile and replays. Revert them with `git checkout -- UserData ReplayData` in the game folder.
- **Track limits are judged by geometry only, never by road surface** (user rule, 2026-11-20): all four tyres wholly beyond the same boundary line. Kerbs have no limit (`docs/analog-driving.md`).
- **Driving needs vJoy** (device 1, bound profile; `--input wheel` after `gtr2-select-wheel.py`).
- **Crash dumps:** keep the report from `gtr2-crash-report.py`, never the dump.
- **`Documents\GTR2` is shared** with other installs. Never edit it by hand; check drift with `Tools\DocumentsGTR2.ps1`.
- **Never edit `installscript.vdf` or `SteamInstallscript.vdf`** (signed).
- **Before editing any file, read `docs/editing-files.md`.** CRLF scripts and game files with NUL headers break under `sed -i` and default Python text mode.

## Open items

`docs/open-items.md`: read it before choosing the next task. It holds the outstanding sweep, the missing `--mode` options and the open driving questions.
