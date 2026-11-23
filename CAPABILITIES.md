# Capabilities

What the tools can technically do, with scope, limits and prerequisites. The user-level summary is [FEATURES.md](FEATURES.md); one line per script is in `scripts/README.md`; evidence and history are in `docs/`. Status: **implemented** (tested on the one development machine), **partial**, **experimental**, **untested**.

## Launch, configuration, setup

| Capability | Status | Scope and limits |
|---|---|---|
| Safe launch (`gtr2-launch.ps1`) | implemented | Swaps the game folder's own config into `Documents\GTR2`, runs the game, restores and verifies; lock/state file; `-Reap` and `-Restore` recover after an interrupted run. One game at a time. |
| Window size (`gtr2-set-resolution.ps1`) | implemented | Chooses GTR2Config entries by their text, never by index (the compatibility layer shifts the indexes). Tested 1280x720 and 640x480. |
| Guided setup (`gtr2-setup.py`) | partial | Writes `gtr2-tools.json`, default environment (Simulation mode, all assists off, markers off), venv, game-folder git baseline. Untested without Steam or vJoy, with a non-git game folder, and its venv step. |
| Crash-dump reader (`gtr2-crash-report.py`) | implemented | Reads minidumps, keeps the report only. |

## Menu navigation

- Page recognition from screenshots against reference pictures (1280x720 shipped; other sizes need a one-time learning sweep of about 15 minutes), scancode keyboard and mouse input, and opt-in flags for every step that starts a session, saves, deletes or joins. 84 offline guard tests; a 30-tour suite of about 6 minutes (**implemented**). Online and account pages are never visited.
- Weather forcing for a session (`gtr2-weather.py`): sunny, rainy, stormy (**implemented**).

## Driving

| Capability | Status | Scope and limits |
|---|---|---|
| Hands-free lap from the pits through a vJoy wheel | implemented | Needs vJoy device 1 and a profile bound to it. Pure pursuit on the track's AIW line, live speed planning from track curvature, a friction-ellipse braking plan, software ABS and traction control, spin recovery. Human-like steering rate and pedal slew. |
| Track limits and contacts | implemented | Judged by geometry only: all four tyres beyond the same boundary line. Kerb strikes have no limit; walls and cars fail a lap. |
| Pit-lane exit and garage exit | partial | Verified on Imola and several layouts with three cars; some layouts still to re-run. |
| All 34 layouts, Maserati MC12 | implemented | Every layout runs clean with defaults. Other cars untested. |
| Imola 4 with the Maserati MC12 (tuned) | partial | Best clean no-aids lap about 121 s (target about 111 s: **goal not met**). Corner speeds are planned from geometry and measured grip; no fixed slow zones. Remaining weak spots: the 1100 m chicane, the 3900 m hairpin, recovery after some spins. |
| Driving analysis tools | implemented | Session reports, vehicle envelope (measured braking, cornering, acceleration per speed), follower simulation, lap estimate, tuning by bisection. |
| Adaptive meta-controller, learned grip map | experimental | Raises or lowers the planned corner speed per lap; results vary between sessions. |

Driving conditions are fixed: Simulation mode, all assists off, corner and pit-spot markers off. The driver never reads on-screen indicators.

## Publishing safety

- `publish-check.py` scans the files and history for private data and lists what would be published (**implemented**); the procedure is in `docs/publishing.md`.
