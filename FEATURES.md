# Features

What the tools offer, most interesting first. Technical detail is in [CAPABILITIES.md](CAPABILITIES.md), requirements in [DEPENDENCIES.md](DEPENDENCIES.md), the history in [CHANGES.md](CHANGES.md). Status is marked where a feature is not fully proven.

## Drive the game hands-free

- **Automatic laps with a virtual wheel** (needs vJoy): the car drives a full lap from the pits on the track's racing line, with human-like steering and pedal inputs, and reports lap time, track-limit and contact checks. Imola with the Maserati MC12 is tuned (best clean no-aids lap about 121 s, against a real-life target of about 111 s: the goal is **not yet met**); every other layout is driven with defaults (all 34 layouts tested clean with the Maserati; other cars untested).
- **Honest driving conditions:** the driver runs in Simulation mode with every driving aid off, corner and pit-spot markers hidden, and never reads on-screen hints.
- **Self-improving driver** (experimental): it learns grip and corner speeds as it drives, recovers from spins and a stuck car, and tools measure the car's real braking, cornering and acceleration limits.

## Use the game without touching it

- **Menu navigator:** moves through the game's menus to the page you ask for, recognising pages from screenshots, with guards so it never starts, saves or deletes anything unless you allow it.
- **Full navigation test suite** (30 tours) to prove the tools still work after a change.
- **Weather forcing:** run a session in sunny, rainy or stormy conditions.

## Set up and protect your install

- **Guided setup** for a fresh clone: finds the game, asks for the profile and window size, sets the default environment (Simulation mode, no aids, markers off), creates the Python environment and a git baseline.
- **Safe launcher** that protects the shared `Documents\GTR2` folder, restores it afterwards and never lets two games run at once.
- **Window size tool** that sets and verifies the game's resolution.

## Diagnose

- **Crash-dump reader** that explains why the game crashed and keeps only the report.
- **Lap and session reports** (driving signals, sections, grip, vehicle envelope) for tuning.
- **Publishing check** that scans the repository for private data before anything is pushed.
