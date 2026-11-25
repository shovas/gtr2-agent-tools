# Imola, the 2400 to 2900 m section: what was found and what failed (2026-11-25)

Read this before working on the 2400 to 2900 m corners, the throttle or the planner's corner speeds at Imola (4Imol, Maserati MC12). It collects the investigation of 2026-11-25 so the next person does not repeat the same tests. Evidence levels matter: most results are one or two sessions, and lap-time differences of 0.3 to 0.5 s are within session-to-session noise.

## Reference numbers

- Confirmed baseline (committed entry): best clean lap **1:52.98** (two sessions, 2026-11-24/25).
- Control on 2026-11-25 (committed entry, `--live-off learn_hits --sig-log`): best clean **1:54.07**, 2400 to 2900 m loss **2.04 s**.
- AI lap (`gtr2_ui/runs/ai_imola_mc12.csv`, lap 2): 1:46.9 to 1:48.6 depending on the run; its corner speeds are a pointer, not a limit (user rule).

## The causal chain in the 2026-11-25 control log (lap 12, sig-log)

- 2388 to 2458 m: brake 0.90 to 0.52 while the car is at 58 to 38 m/s, gear 4 to 5.
- **2467 m: brake goes to 0.00 and throttle (duty) goes to 1.00 in one sample**, at 36 m/s, mid-bend. Target speed 41.6 m/s, so the throttle law puts it at full.
- 2471 to 2492 m: yaw rate 16 to 41 deg/s, sideslip -2.5 to -4.7 deg. The rear steps out.
- 2502 to 2529 m: the planned speed rises from 41 to 59 m/s and falls back to 47 at 2529 m. The rise is the corner window looking past the apex, not an error.
- 2538 to 2597 m: downshift 3 to 2, braking again at 2552 m, minimum 17.4 m/s at 2597 m with **lateral error -4.6 m** (the car is off the line).
- 2600 m: 0.85 s of loss in that 100 m, the largest single 100 m in the log. 2440 to 2520 m is the bend the AI takes at about 50 m/s on a 128 to 144 m radius (ours 36 m/s on about 61 m).

Throttle law (`gtr2-drive-lap.py`, the duty line after the target speed): `duty = throttle-base + throttle-gain x (target - speed)`, clipped to 0 to 1. With base 0.65 and gain 0.5, a 2 m/s deficit is already full throttle. The planner (`gtr2_driving/trackmap.py`, `speed_limit_live`) is working as designed: the planned rise after the apex is the corner limit ahead.

## Experiments (in order)

| # | Change | Sessions | Result | Verdict |
|---|---|---|---|---|
| 1 | Throttle cap `--throttle-circle 12`: drive scaled by sqrt(1 - (v x yaw rate / 12)^2) | 2 (cap) + 1 (control) | Cap: **stalled on lap 1 at 1165 m both times** (x=-1165 z=-499, about 213 s). Control without the cap: laps completed, best 1:54.07. The 2400 to 2900 m section was never reached in the cap runs. | Rejected. Option stays in the driver, off. |
| 2 | Curvature window `--curv-span` 20 to 30 m | 1 | 2400 to 2900 m loss 2.04 to 1.86 s; laps 114.5 to 116.4, best clean 1:55.42, one unclean lap (Kerbs21); 4500 to 4800 m rose to 1.59 s. | Rejected (lap times worse). |
| 3 | Throttle gain 0.5 to 0.25 (`throttle-gain` in the Imola entry) | 5 | Best clean: 1:52.73, 1:53.50, 1:53.25, 1:54.53, 1:52.87 (mean 1:53.38). Section 2400 to 2700 m: 1.71 to 1.94 s where measured; one run 2400 to 2900 m 1.79 s. | Not adopted. The section loss fell in most runs but the best laps did not reliably beat 1:52.98. Worth a longer test (5 or more sessions with the same entry) only if a gain is needed. |
| 4 | Throttle base 0.65 to 0.5 | 1 | 8 of 12 clean, best 1:53.40, section 2400 to 2900 m 1.95 s. | Rejected. |
| 5 | Yaw-rise drive cut `--yaw-rise-cut 1.0` (drive scaled by 1 - K x (yaw acceleration - 0.5 rad/s^2), from the game's yaw rate) | 1 | 9 of 12 clean, best 1:58.08, **2000 to 2900 m loss 3.52 s** (worse). | Rejected. |

## What this says (keep it in mind)

- The throttle is not the whole story. Every throttle-side change either stalled the car at 1165 m (the cap, which acts at yaw spikes that also happen on the first lap) or moved the section loss by less than the session noise.
- The section's loss is spread across the brake release, the rotation at 2470 to 2500 m, the downshift and the re-brake at 2552 m, and the lateral error (up to -4.6 m) that starts at the snap. A change to one of those alone is unlikely to recover the 0.85 s.
- The first-lap stall at about 1165 m is sensitive to small changes in drive or rotation. It is also the known first-lap event in 8 of 14 earlier sessions. Any test of the drive needs a control with the same entry, and a stall at 1165 m is a driver/first-lap effect, not evidence about the 2400 to 2900 m section.
- Planner changes (curvature window) and the follower's lateral error are the next candidates. The planner is not the cause of the mid-bend throttle, but the 2400 to 2900 m section loses time because the car cannot hold the line the planner gives (lateral error to -4.6 m at the minimum).

## Ideas not yet tested

- Brake release finished before the apex as an explicit rule on the yaw rate rising (listed in `docs/analog-driving.md`, not implemented).
- A later apex and exit-first line for the 2400 to 2900 m corners, with a follower that holds about 0.5 m (the optimiser zone 2400 to 2750 m failed twice on track limits; see `docs/analog-driving.md`).
- Per-section learned throttle (a driver-side rule using measured yaw and lateral error, not a fixed lap-distance zone: the rules forbid fixed slow zones).

## How to test (same conditions every time)

- Fresh session, 12 laps, `--live-off learn_hits --sig-log`, the committed Imola entry, one change at a time.
- Compare the best clean lap and the 2400 to 2900 m loss with the control of the same day. Use `gtr2-session-report.py` and `gtr2-corner-budget.py` on the newest `signals_*.csv`.
- Watch the live status with `gtr2-watch.py` (see `docs/lap-session-monitoring.md`).
- Write every result here, including the rejected ones, with the session count and the best clean lap.
