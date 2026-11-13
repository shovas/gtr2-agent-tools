# Dependencies

What to install for the tools in this repository to work fully. `python scripts\gtr2-setup.py --check-deps` prints this list with what it finds on your machine (and the guided setup shows it at the start); nothing is installed or changed by that check.

## What you need on the machine

| Need | Version | Required for | Notes |
|---|---|---|---|
| Windows | 10 or 11 | everything | The tools drive Win32 windows, scancode input and a Windows-only game. |
| GTR 2 - FIA GT Racing Game | the Steam release (app id 8790), or another install of the same game | everything | A 32-bit DirectX 9 game. The tools never contain game files: point them at the folder that holds `GTR2.exe`. |
| Windows PowerShell | 5.1 (ships with Windows) | launcher, resolution tool, setup steps | `gtr2-launch.ps1`, `gtr2-set-resolution.ps1`, `Tools\DocumentsGTR2.ps1`. |
| Python | 3.11 or newer | all Python tools, setup | Install from python.org or the Microsoft Store; "Add to PATH" helps. |
| git | any recent Git for Windows | reverting the game's profile files after tests, game-folder tracking | Setup can `git init` the game folder. Without git the suite cannot revert game-written files. |
| Game runtimes | the ones the game's own installer provides (DirectX 9, VC++ 2010 x86) | starting the game | If the game does not start, reinstall its redistributables (Steam: verify the game files). |
| vJoy (optional) | 2.1.8 or compatible (for example the maintained fork at https://github.com/njz3/vJoy) | hands-free analog driving (`gtr2-drive-lap.py --input analog`, `gtr2-lap-check.py`) | A kernel driver: install it once with administrator rights. Configure device 1 with the X, Y, Z and Rx axes and 2 buttons, and bind the game profile's controls to it (steering X, Accelerate button 6, Brake button 8, shifts on buttons 1 and 2). See `docs/analog-driving.md`. Everything else works without vJoy. |

## Python packages (installed into `scripts\.venv`)

`python scripts\gtr2-setup.py` creates the environment and installs `scripts\requirements.txt`. By hand:

```powershell
python -m venv scripts\.venv
scripts\.venv\Scripts\pip install -r scripts\requirements.txt
```

| Package | Pinned | Used by | Required? |
|---|---|---|---|
| numpy | 2.5.4 | page recognition (`gtr2_ui/pagerec.py`), pause-menu reader, `gtr2-nav.py`, the suite | yes, for navigation and the suite |
| pillow | 13.0.0 | the same (image handling, baselines, diagnostic pictures) | yes, for navigation and the suite |
| mss | 10.2.0 | screen capture in `gtr2-nav.py` | yes, for navigation and the suite |
| capstone | 5.0.9 | disassembly in the crash report (`gtr2-crash-report.py`) | optional: the report works without it, minus the disassembly |
| pefile | 2024.8.26 | PE section names in the crash report | optional, same |

Everything else (the launcher, the resolution tool, the weather and file tools, the telemetry lap driver, the setup script, the crash-dump reader) uses only the standard library and PowerShell. `gtr2-setup.py` itself must stay standard-library only: it runs before the environment exists.

Adding a dependency: pin the exact version in `scripts\requirements.txt`, say in the script's header what it adds, keep optional extras optional (import inside a `try`), and add a row here. Run Python tools with `-I` (isolated mode).

## Which feature needs what

| Feature | Needs |
|---|---|
| Launch the game safely, set the window size (`gtr2-launch.ps1`, `gtr2-set-resolution.ps1`) | Windows, PowerShell 5.1, the game |
| Menu navigation, the full navigation suite, hover and control checks | the above + Python 3.11+, numpy, pillow, mss, git |
| Telemetry lap driving with the keyboard | the above (no vJoy) |
| Analog driving (`--input analog`, `gtr2-lap-check.py`) | the above + vJoy |
| Weather forcing, file watching | Python (standard library) |
| Crash reports (`gtr2-crash-report.py`) | Python; capstone and pefile for the full report |
