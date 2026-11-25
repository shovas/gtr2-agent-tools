# Lap sessions: live monitoring, stall watcher and stop requests

Read this before running or changing a lap session (`gtr2-lap-campaign.py`, `gtr2-lap-check.py`, `gtr2-drive-lap.py`) or the live watchdog (`gtr2-watch.py`). Written 2026-11-25. The code header of `gtr2-watch.py` has the confidence notes; this file has the reasons and the history.

## Why this exists

Until 2026-11-25 nothing was visible during a session. The driver's status lines went to a log, the signal log was written only at the end, and the campaign printed only when a session ended. A stall at about 1165 m on lap 1 (the car stopped and stalled in reverse) was found only when the session had already closed. The driver itself notices a stop after 8 s without movement (`last_move`, 0.5 m in 8 s) and gives up the lap; recovery starts after 2 s (`--recover-after 2.0`) and gives up after six attempts in 90 s (`--recover-max 6`).

## What exists now

| Piece | What it does | Where |
|---|---|---|
| Live status | The driver writes `gtr2_ui/runs/live_status.json` once a second (lap, speed, gear, position, `still_s`, recovery count, `recovering`). Written only inside the main loop. | `gtr2-drive-lap.py`, the block before the `last_move > 8.0` stop |
| Watcher | Reads the status file, prints one line per alert: `still` (not moving for 4 s), `recovering`, `attempts` (3 or more recovery attempts), `lap` (same lap for 150 s), `stale` (no write for 3 s, then it exits). Prints a line when the lap number changes. | `gtr2-watch.py` (`--once` prints the status and exits) |
| Stop request | With `--stop-on attempts` (the default), the watcher writes `gtr2_ui/runs/stop_request.json` when the attempts alert fires. The driver checks for the file once a second and exits through its normal cleanup with the outcome `stop requested: ...`. The campaign then stops and does not start the next session. | `gtr2-watch.py`, `gtr2-drive-lap.py`, `gtr2-lap-campaign.py` |
| Campaign integration | Before each session the campaign clears the old status and stop files, starts the watcher in the background, writes its output to `gtr2_ui/runs/stall_alerts.log` (a header line per session), and stops the watcher when the session ends. | `gtr2-lap-campaign.py` |

All run output is in `gtr2_ui/runs/`, which is git-ignored.

## What the watcher does not do

- It does not stop the task by itself. It writes a file, and the driver decides.
- It reports to the conversation only if something watches `stall_alerts.log`. For a session I arm a monitor on that log (`tail -n 0 -F ... | grep --line-buffered -v "^---"`). Monitors expire after 30 minutes, so re-arm for long sessions.
- It cannot tell a frozen driver that still writes its file from a stalled car. The "still" alert is inferred.
- Tools other than the lap driver do not write status: the navigation and menu scripts, the axis probe, and the AI benchmark (which drives the game AI, not us).

## Confidence and open questions (keep these in mind)

- **Not confirmed in a live session** at the time of writing (see the test log below). Only `--once` was run before the campaign integration.
- "still" has false alarms for deliberate stops (pit box, garage, a red flag). The 4 s limit is a guess.
- "lap" (150 s) can trip on a slow first lap or a pit stop. Clean laps take about 113 to 118 s.
- A stop request after three attempts may cost a session that would have recovered by itself. Check how often three attempts happen in runs that recover.
- After a stop request, check the vJoy buttons are released (the earlier shift-down latch bug, `docs/analog-driving.md`).
- A slow write (disk, antivirus) could trip the 3 s stale limit and end the watch early, without a message.

## Test log

- 2026-11-25, the first watcher run (before the stop request existed): not used. The yaw-rise session started before the status writer, so it has no file.
- 2026-11-25, live stop-path test (one 12-lap session, campaign with the automatic watcher, stop request written by hand at about 240 s). Result, all verified from the logs:
  - The driver consumed the stop request within 3 s and ended the run with the outcome `stop requested: manual stop test` (`runs/lap_drive.log`).
  - The status file stopped updating at 247.7 s, and the watcher reported "status not updated for 3 s" (the stale alert) in `stall_alerts.log`.
  - The campaign printed "stopped after session 1: the stall watcher asked for a stop" and started no second session. It exited with code 0, and the game closed.
  - vJoy release, checked separately with the game closed (2026-11-25): button 2 read as down inside the `VJoy` context and as up (dwButtons 0) after the exit, through winmm `joyGetPosEx` on device 0. The stop request ends the run through the same `with` exit, so the release is covered by this check. The game itself was not running, so the check does not show what the game saw.
  - An earlier attempt of this test wrote the stop file to the wrong folder (a shell `cd` and `&` mistake), so the driver never saw a request. Use absolute paths in such tests.

## Usage

```powershell
scripts\.venv\Scripts\python.exe -I scripts\gtr2-lap-campaign.py Imola4Imol --car gt/maserati_mc12 --laps 12 --max-sessions 1 --fresh --drive-args="--live-off learn_hits --sig-log"
scripts\.venv\Scripts\python.exe -I scripts\gtr2-watch.py --once
```

The second command prints the current status (or "no status file yet"). Do not run `gtr2-recover.py` while a session is running.

## Failures seen on 2026-11-25 after 17:00 (infrastructure, not the controller)

- **A run that times out inside the driver leaves the game open on a non-menu screen.** Every later lap-check then printed `not on the main menu` and ended with a `TimeoutExpired`. The message comes from the cleanup step after the run (`cmd_exit`), not from the start.
- **The lap-check's `TimeoutExpired` gave no driver output.** Its driver output is captured, so the stage lines were lost. Run the driver directly to a file when a run hangs (`gtr2-drive-lap.py` with the same arguments).
- **`vJoy device 1 not available (status 2)`** was seen once, when a leftover recovery process still held the device. A direct acquire test (`VJoy(1).__enter__`) passed after the processes exited. Check the device this way before blaming the driver.
- **`gtr2-recover.py --force --revert` once hung for more than 10 minutes** (its game-menu exit waited). Stop it by process id, then close the game by process name, and revert the game folder with git (`checkout -- UserData ReplayData`, then `clean -fd`). The lap-check refuses to start while the game folder has uncommitted changes.
- **Rule:** after any hung run, do this order: stop the runner and recovery processes, close the game, revert the game folder, confirm the vJoy device, then the control run, then the test run. A control run with the committed settings must pass before a test result is read.
