# Fresh clone: first setup

Read this when `gtr2-tools.json` is missing from the repository root. Full context: `CLAUDE.md` (rules), `docs/setup-and-config.md` (setup details).

The user has just cloned this repository and wants to use it with their own copy of GTR 2. Do these in order and tell the user what you are doing:

1. `python scripts\gtr2-setup.py --check-deps`: report anything missing (Python 3.11+, git, PowerShell 5.1, the game; vJoy is optional). Do not install drivers for them.
2. Ask the user where their game folder is (the one holding `GTR2.exe`; setup finds a Steam install by itself) and which player profile to use. Tell them the game is run windowed at a test size (the user's own play size never matters: only these tools run the game): 1280x720 on a 1080p screen, which ships with reference pictures; 640x480 on a 4:3 screen, or any other size, for which setup runs a one-time learning sweep (`gtr2-nav-suite.py --learn`, about 15 minutes, PC left alone). Keep the choice to those two.
3. `python scripts\gtr2-setup.py --dry-run`, show the review, then, with the user's go-ahead, `python scripts\gtr2-setup.py`. It writes `gtr2-tools.json`, sets the default game environment in the profile (Simulation mode, every driving assist off, corner and pit-spot markers off: an absolute requirement, `ENVIRONMENT` in `gtr2-setup.py`, also written by `gtr2-lap-check.py` before every run), creates `scripts\.venv`, makes the game folder a git repository (a baseline commit), adds the game-folder `CLAUDE.md`, does the bootstrap launch, sets the window size through `GTR2Config.exe` and checks it by starting the game. Warn the user first: the game starts and clicks by itself, so they must leave the PC alone for a few minutes.
4. Confirm the game reaches the main menu: `scripts\.venv\Scripts\python.exe -I scripts\gtr2-nav.py preflight`, then `... gtr2-nav.py ready` and `where` (it should say MAIN MENU). Close the game with `gtr2-nav.py exit`.
5. Offer the offline tests (`test_nav_guards.py`) and, with the PC left alone for about 6 minutes, the full suite (`gtr2-nav-suite.py`). If a tour fails, read `docs/ui-navigation.md` before changing anything.

Never launch `GTR2.exe` directly (see the rules below). Things that are per machine and not in the repository on purpose: `gtr2-tools.json`, `scripts\.venv\`, `scripts\gtr2_ui\runs\` and everything under the game folder; setup recreates them.
