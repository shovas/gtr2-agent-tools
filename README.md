# gtr2-agent-tools

Automation tools for *GTR 2 - FIA GT Racing Game* (Windows): a launcher that keeps the game's shared `Documents\GTR2` folder safe, a verified-resolution tool, a scripted menu navigator with page recognition, hands-free lap driving from the shared-memory telemetry, weather forcing, Driving School helpers, a crash-dump reader and offline guard tests. They were built with an AI coding agent (see `CLAUDE.md` and `AGENTS.md`, the instructions it reads) and are meant to be usable by an agent or by hand.

This is an unofficial fan project. It is not affiliated with or endorsed by the publishers or developers of GTR 2 or by Steam. **This repository contains no game files**: you need your own copy of the game, and the tools act on that folder.

## Before you start

- **Status:** developed and tested on one Windows 10 machine with the Steam release of the game. Setup on other machines (no Steam, no vJoy, a game folder that is not a git repository) is untested.
- **Requirements:** Windows 10/11, Python 3.11+, git, PowerShell 5.1, the game, and optionally vJoy for hands-free driving. The full list and which feature needs what is in [DEPENDENCIES.md](DEPENDENCIES.md); `python scripts\gtr2-setup.py --check-deps` shows what your machine already has.
- **vJoy** (optional) is a kernel driver: installing it needs administrator rights, and your game profile's controls have to be bound to it. Everything except analog driving works without it.

## What to expect

- **The tools run your real game.** The navigator and the test suite start `GTR2.exe`, click through its menus with real mouse and keyboard input and take screenshots of its window. **Leave the PC alone while they run** (the full suite takes about 6 minutes): anything that takes the focus from the game pauses it, and stray input can click the wrong thing.
- **Always launch through the launcher** (`scripts\gtr2-launch.ps1`). The game only reads its configuration from the shared `Documents\GTR2`, so the launcher backs that folder up, swaps in the game folder's own configuration for the run, then restores it and verifies the result. On a first run it sets any existing `Documents\GTR2` aside and puts it back afterwards.
- **Game files change.** A run rewrites the player profile and writes logs and replays in the game folder. That is why the game folder should be a git repository (setup can create one): the test suite reverts those changes with git. Inside this repository a run only writes `scripts/gtr2_ui/runs/` (git-ignored), plus the reference pictures you choose to learn.
- **The game runs windowed at a test size, not your screen size.** Setup asks for it (`resolution` in `gtr2-tools.json`) and it has to fit your screen with its title bar: **1280x720 on a 1080p (or larger) screen**, which ships with ready-made reference pictures, or **640x480 on a 4:3 screen**. Any size other than 1280x720 needs a one-time learning sweep (`gtr2-nav-suite.py --learn`, which setup offers: about 15 minutes, a full navigation sweep of the game with the PC left alone) so the navigator can recognise the menu pages at that size. Tested: 1280x720 and 640x480 (30 of 30 tours each).
- **One GTR2 at a time.** A second copy of the game crashes; the tools refuse to start one.
- **A slow first start after the display slept.** On the machine this was developed on, a game started after Windows had turned the display off (default: 10 minutes without input) took 10 to 20 s to show its window instead of about 5, because the graphics driver was busy for that long; the window stays white meanwhile. The launcher works around it: it keeps the display on while it runs and, if the display was probably asleep, wakes it and waits 20 s first (`-WakeWait`, or `-NoWakeDisplay` to turn it off). If you see it anyway, or want it gone for everything, try a lighter setting on your side: a longer "Turn off display after" (or Never) in the Windows power plan, a plain black screen saver instead of turning the display off, a look at your monitor's own deep-sleep or eco setting, and the graphics driver's power management mode and PCI Express link power setting in the power plan. Only the first of these was measured (display held on: no slow start); the others are suggestions.

## Quick start

Get the tools and open a PowerShell in the folder:

```powershell
git clone https://github.com/shovas/gtr2-agent-tools.git
cd gtr2-agent-tools
```

If you use an AI coding agent, start it in this folder and ask it to set the tools up for your game: it reads `CLAUDE.md`, which tells it the first steps. Otherwise run the guided setup yourself. It detects what it can, asks for the rest and shows a review before it changes anything:

```powershell
python scripts\gtr2-setup.py --dry-run     # ask and review only
python scripts\gtr2-setup.py               # do it
```

Or set it up by hand and point the tools at your game folder:

```powershell
$env:GTR2_ROOT = 'D:\Games\GTR2'          # the folder that holds GTR2.exe
python -m venv scripts\.venv; scripts\.venv\Scripts\pip install -r scripts\requirements.txt
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gtr2-launch.ps1 -DryRun   # first real run creates <game>\config\Documents-Config.ini
scripts\.venv\Scripts\python.exe -I scripts\test_nav_guards.py                      # offline tests
```

Per-machine files (the config, the verified-resolution record, a snapshot of `Documents\GTR2`) are written to the game folder, not here. Optional: `GTR2_PROFILE` selects the player profile.

## What you can do with it

Start your agent in this folder (it reads `CLAUDE.md` and knows the tools) and ask in plain words. Examples of what to ask and which tool answers:

| You want to... | Ask your agent, for example | Tool |
|---|---|---|
| Set everything up for your game folder | "Set up the GTR2 tools for my game in D:\Games\GTR2" | `gtr2-setup.py` |
| Check what is missing on your PC | "What do I still need to install for these tools?" | `gtr2-setup.py --check-deps` |
| Start the game safely | "Start GTR2 and get to the main menu" | `gtr2-launch.ps1`, `gtr2-nav.py ready` |
| Change the window size or shader | "Set the game window to 1600x900" / "show me GTR2Config's drop-downs" | `gtr2-set-resolution.ps1` |
| Move around the menus | "Go to the Options page and tell me what is on it" / "open the Time Trial setup" | `gtr2-nav.py` (`where`, `goto`, `path`) |
| Check that every menu page still works | "Run the full navigation test and report what failed" (about 6 minutes) | `gtr2-nav-suite.py`, `test_nav_guards.py` (offline, 0.2 s) |
| Add menu pages to page recognition | "Learn reference pictures for the pages that have none" | `gtr2-nav.py learn`, `coverage.py` |
| Test the Options controls | "Click every checkbox and spinner on the Options pages and check they hold" | `gtr2-control-check.py` |
| Find buttons that do nothing | "Hover over every button and list the ones that do not react" | `gtr2-hover-check.py` |
| Drive a lap by itself (needs vJoy) | "Drive a hands-free lap at Imola in the Murcielago" | `gtr2-lap-check.py`, `gtr2-drive-lap.py`, `gtr2-tune-lap.py` |
| Pass a Driving School test | "Run the Acceleration level 1 challenge" | `gtr2-accel-challenge.py` |
| Force the weather | "Make the next race weekend rainy" / "restore the weather" | `gtr2-weather.py` |
| Read a crash | "Explain the latest GTR2 crash" | `gtr2-crash-report.py` |
| See which files the game reads | "Report when the game opens Config.ini during a run" | `gtr2-file-watch.py` |
| Check the shared `Documents\GTR2` folder | "Has anything changed in Documents\GTR2?" | `Tools\DocumentsGTR2.ps1` |
| Return to a first-run state | "Set my Documents\GTR2 and profiles aside for a clean first run" | `gtr2-clean-slate.ps1` |

Every script has a usage line in its header and a one-line entry in [scripts/README.md](scripts/README.md). The navigator never presses buttons that start sessions, save, delete, join or host unless you (or the agent, on your word) give the matching opt-in flag.

## Where things are

| Path | What it holds |
|---|---|
| `scripts/` | the tools (Python and PowerShell); `scripts/README.md` has a one-line index of every script |
| `scripts/nav_paths/` | the navigation tours the test suite runs |
| `scripts/gtr2_ui/baselines/` | reference pictures of the game's menu pages, used for page recognition (the player name is painted out) |
| `config/weather/` | weather files used by the weather-forcing tool |
| `docs/` | the findings and decisions behind the tools (see below) |
| `templates/` | the instructions file `setup` adds to your game folder |
| `DEPENDENCIES.md` | what to install |

**About `docs/`:** these files are the working notes of the project, split by topic: what was measured, what failed, what is still unexplained. They read as a dated log, not as a manual. Start with `scripts/README.md` and this file; open a `docs/` file when you work on that topic (the index is at the end of `CLAUDE.md`).

## License

[Creative Commons Attribution-NonCommercial 4.0 International](https://creativecommons.org/licenses/by-nc/4.0/) (CC BY-NC 4.0); the full text is in [LICENSE](LICENSE). Creative Commons does not recommend its licenses for software, so check that this suits how you want to use the code. The game and its assets belong to their owners and are not covered by this license.
