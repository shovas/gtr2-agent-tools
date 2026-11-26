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

## Follower alternatives (already tested, do not repeat without a new reason)

`--follower stanley` and `--follower designed` (`gtr2_driving/follower.py`) were tested on Imola earlier (see `docs/analog-driving.md`, the entries around lines 502, 730, 867, 936 and 975). Stanley spun on the out lap (430 m, 113 degrees) and at 1150 and 1171 m; designed had 9 to 14 track-limit events with 2.97 m rms error, and in another run 126.65 s clean at most. Neither beat pure pursuit. Changing the follower's gain or form again is therefore not a new test.

## Ideas not yet tested

- Brake release finished before the apex as an explicit rule on the yaw rate rising (listed in `docs/analog-driving.md`, not implemented).
- A later apex and exit-first line for the 2400 to 2900 m corners, with a follower that holds about 0.5 m (the optimiser zone 2400 to 2750 m failed twice on track limits; see `docs/analog-driving.md`).
- Per-section learned throttle (a driver-side rule using measured yaw and lateral error, not a fixed lap-distance zone: the rules forbid fixed slow zones).

## How to test (same conditions every time)

- Fresh session, 12 laps, `--live-off learn_hits --sig-log`, the committed Imola entry, one change at a time.
- Compare the best clean lap and the 2400 to 2900 m loss with the control of the same day. Use `gtr2-session-report.py` and `gtr2-corner-budget.py` on the newest `signals_*.csv`.
- Watch the live status with `gtr2-watch.py` (see `docs/lap-session-monitoring.md`).
- Write every result here, including the rejected ones, with the session count and the best clean lap.

## Offline follower simulator (2026-11-25): calibration result

`scripts/gtr2-follower-sim.py Imola/4Imol` (the bicycle model, grip limit `--grip` 12 m/s^2 by default):

| Follower | grip 10 | grip 12 (default) | grip 14 | Game (measured, earlier sessions) |
|---|---|---|---|---|
| pursuit | 3.81 m rms, p95 9.6 m | **1.95 m rms, p95 4.0 m, max 8.4 m** | 1.54 m | 1.7 to 1.9 m rms, p95 3.3 to 3.6 m |
| designed | 2.66 m rms | **0.99 m rms, p95 1.9 m, max 3.3 m** | 1.00 m | 2.97 m rms, 17 m off at 600 m |
| stanley | (grip 12: 1.57 m rms, p95 3.7 m, max 6.8 m) | | | spins on the out lap (game) |

Reading: grip 12 reproduces the game for pursuit, but the simulator then ranks designed as the best follower by a wide margin, while the game ranks it the worst. No single grip value fits both. The simulator therefore cannot choose a follower yet. What it misses is whatever makes designed fail in the game (candidates: the speed-dependent steering gain table at high steering rates, the rack's real rate limit, the delay, and the tyre slip at the limit, none of which the bicycle model has). Fixing that needs a logged designed session with the `steer` column, not more grip sweeps. Until then, offline results for designed or stanley are not evidence.

## First logged designed-follower session (2026-11-25, one session, lap 1 only)

`--follower designed` with `--sig-log` and the committed entry: the car stalled on lap 1 at 639 m (x=639, z=437, about 317 s; recovery attempt 1, still for 4.8 s, then the driver stopped). The stall watcher caught it live (alerts in `runs/stall_alerts.log`); the campaign ended with no clean lap (no stop request: only one recovery attempt, below the default trigger of three).

Tracking before the stall, from the log: lateral error rms 1.4 m at 200 to 400 m (max 3.1 m) and 1.1 m at 400 to 650 m (max 2.7 m); steering rms 0.34 with a maximum of 0.66 at 400 to 650 m (yaw up to 48 deg/s). That is close to the simulator's 0.99 m rms for the whole lap, so the simulator's tracking is roughly right for designed. The earlier game failure (2.97 m rms, 17 m off) was a different setup (a zoned line at live-lat 16). The problem in this run is the stall, not the tracking. Open question: what makes the car stall at 639 m with the designed follower (the lap-1 stall cause is still not identified).

## The lap-1 spin of the designed session (diagnosed 2026-11-25, from the signal log and the driver log)

Not a stall to begin with. Sequence (signal log times, which match the driver's run time at this point):

- 238.0 s: braking at 60 m/s (brake 0.91), steering small (-0.1), 2.2 m off the line.
- 239.4 s: brake released to 0 at 46 m/s; the steering command goes from -0.58 to **-1.00 (full lock)** by 239.8 s while the car is still only 1.2 to 1.5 m off the line (the driver's heading error is -23 deg).
- 239.8 to 240.8 s: yaw rate swings -37 to +28 deg/s, sideslip rises to 8.6 deg, speed falls 46 to 35 m/s. The rear steps out.
- 240.8 to 242.5 s: off the road at about (650, 420), 14 to 42 m off the line, heading error to -105 deg; barrier hit at 243 s (80.7 m/s^2, Barrier30).
- 316 to 326 s: the car is stopped at (639, 437) in reverse (gear -1); the driver's recovery attempts and the stale status follow. The 639 m location is the stop, not the cause.

Hypothesis (not confirmed): the designed follower divides its command by the speed steering gain, which is small at speed, so a moderate heading error at 46 m/s saturates the steering at full lock, and the brake release at the same moment leaves the car with no load-transfer help. The simulator cannot test this (it does not spin at these settings; its grip-limit calibration misses the spin). Test to run next: log the designed command (the value before clipping) on the same corner, and check whether a speed-dependent cap on the command (for example a rate or magnitude limit above about 35 m/s) removes the full-lock step without raising the lateral error elsewhere.

**Confirmed by arithmetic (same day):** at the logged state (46 m/s, heading error -23 deg, lateral -1.5 m) the designed command is a*psi/g + b*lat/g with a = 2 zeta wn L / v = 0.127, b = 0.0018, g = steer_gain(46 m/s) = 0.058: the heading term alone is -0.88, and the wheel is at full lock (-1.0) for a heading error of about 25 deg. So at speed the designed follower saturates the steering on a heading error that the simulator's grip-limited car never reaches, and the lateral error at that moment (1.5 m) is not what drives it. This is a property of the follower's gain division (command units per degree of heading error at speed), not a model error. Fix to test in the game, not offline: a speed-dependent limit on the designed command (for example a cap on |command| of about 0.4 above 35 m/s, or a rate limit on the command) with the brake release unchanged; judged by the lap-1 spin and by the lateral error on the straights.

**Designed follower with the steering cap (`--designed-cap 0.4`, cap above 35 m/s), one session (2026-11-25):** the lap-1 spin at 639 m did not happen. The session ran 3 laps (198.6 s, 218.9 s, 123.8 s; no clean lap) and then stopped on lap 4 at (669, 439), at the same place as the earlier spin (about 650 to 670, 440). So the cap removes the full-lock step but not the car's loss of grip on the bend there, and the laps 1 and 2 were far slower than normal. Not adopted; designed stays a side branch. Next only if the bend itself is studied: the heading error and sideslip at 650 to 670 m on the lap-4 stop.

**Designed follower, cap at all speeds (`--designed-cap 0.4 --designed-cap-speed 0`), one session (2026-11-25): worse.** The car stopped on the out lap at 140 s at (594, 470), in reverse, with no clean lap. The earlier cap runs (cap above 35 m/s) got to laps 1 to 3 and to lap 4; this one stopped before the first timed lap. So the cap at low speed does not help: the full-lock saturation at 20 to 35 m/s (the designed command is about -2.3 for a 60 degree heading error at 25 m/s) is a symptom, and capping the command only moves the failure. Diagnosis (from the logs of the two cap runs): the designed follower's command grows with the heading error divided by a speed gain that falls to about 0.05 at 35 m/s and 0.1 at 25 m/s, so any large heading error (from a kerb strike, a brake release or a slide) saturates the wheel. Not adopted. The next designed test would have to limit the heading error itself (not the command), and the designed branch is still a side branch of the goal.

**Pursuit with the heading error capped, offline (2026-11-25, rejected):** clipping the heading error that pursuit feeds into the steering (the same idea as the designed cap, moved to the error) in `gtr2-follower-sim.py Imola/4Imol`: no cap 1.95 m rms (p95 4.0 m); cap 20 deg 3.80 m (p95 9.1 m); cap 15 deg 8.87 m (p95 22.9 m, max 43 m); cap 10 deg the car leaves the road. Pursuit needs the large heading errors to turn, so limiting the error costs far more tracking than the spin it would prevent. Not a route to the 2400 to 2900 m fix. Scratch script only (not in the repository).

**Delay-compensated pursuit, offline (2026-11-25, rejected):** pursuit aimed from the position the car reaches TAU seconds ahead along its heading (the steering delay the mission lists as 0.27 to 0.35 s; the simulator itself has 0.15 s delay and 0.30 s lag). Cross-track rms: TAU 0 1.95 m (p95 4.0 m); 0.1 s 2.04 m (p95 4.5 m); 0.2 s 2.54 m (p95 5.6 m); 0.3 s 3.24 m (p95 7.1 m). Worse at every delay. The aim point already leads the car by the look-ahead distance, so moving the start point forward double-counts the lead. Scratch script only (not in the repository). The delay the mission asks about is real in the game, but compensating it in the aim point is not the fix.

**Pursuit sweep, offline (2026-11-25):** look-ahead slope 0.9, 1.2, 1.5 against steering gain scale 0.8, 1.0, 1.2 (the simulator's default gain is 25 deg; the Imola entry's `--steer-gain 20` is scale 1.25). Best: look 1.2 with scale 1.25 to 1.3, cross-track rms 1.76 m (p95 3.9 m, max 5.5 m); the default is 1.95 m. The entry already sits on the plateau: gains above 1.25 change nothing. So pursuit's tracking is near its limit in this form; a real gain needs a different controller structure (the follower redesign), not more tuning of this one.

**Speed-curve limit on the designed command, offline (2026-11-25):** the user's proposal (one curve with one sensitivity multiplier, 50% as the neutral point) applied as the road angle the grip allows, max angle = atan(L x grip / v^2), with grip = multiplier x the simulator's 12 m/s^2 limit, and the command clipped to that angle over the steering gain. Designed follower, `gtr2-follower-sim.py Imola/4Imol`: multiplier off 0.99 m rms; 1.0 1.01 m (p95 1.93 m, max 3.7 m); 0.5 and 0.25 the car leaves the road. So a curve with one multiplier is the right structure, but the offline range that keeps the car on the road is narrow (about 1.0 and above), and at 1.0 it does nothing. It can only be judged in the game, and the simulator does not reproduce the spins. Scratch script only (not in the repository).

**Designed follower with the speed-curve limit (`--designed-curve 1.0`, the plan of 2026-11-25), one game session: rejected.** The first attempt never ran: the driver crashed at start-up on a `%` in its help text (argparse), which my `--help` check missed because the error also named the option. Fixed, then rerun: the car stopped on lap 1 at (642, 439) at about 354 s (recovery attempt 1, then still for 5 s), the same place as the earlier designed stalls, with no clean lap. The curve at multiplier 1.0 changes nothing that matters in the game, as the offline test predicted (it does nothing at 1.0). The one-multiplier curve is a sound structure, but the designed follower is still not usable at this bend: the limit cannot be set to 0.5 offline without leaving the road, and at 1.0 it does not stop the spin. Option stays in the driver, off by default.

## Bend spin: what separates the spin laps (paired records, 2026-11-26)

- **Not the grip drop.** Aligned at fixed z (-215 to -105 m, in the 2570 m bend), the spin laps and the non-spin laps look alike: front grip falls from about 0.96 to 0.4 to 0.5 and yaw rises to about 30 deg/s at z -105 in all of them, with slide -5 to -7 deg. The grip loss is common to the bend; it does not mark the spin.
- **Entry speed is the separating variable, but it is only a risk factor.** Speed at z -145: the two spin laps (run 2 arm A sessions 1 and 5, laps 6 and 7) were at 53.4 and 52.9 m/s. Of the 13 bend laps at 50 m/s or more, 2 spun; of the 53 laps below 50 m/s, none did (66 laps with the speed recorded, the 10 paired sessions). Several non-spin laps were also at 50 to 54 m/s, so speed alone does not explain it.
- **After the trigger the spin is a grip failure.** On the spin lap the car holds about 45 m/s through z -100 to -60 while the front grip stays near 0.4. The non-spin laps are at 38 to 40 m/s there and the grip recovers to 0.6 to 0.7 by z -85. Steering reaches full counter-lock only after the slide passes -25 deg (grip near 0).
- **Caveat.** Two spins in 13 fast laps is not a statistic; the comparison is observational (the laps differ in their braking too). The next test is a planned speed change at z -145 with everything else fixed.
- **Earlier entry-window analysis was wrong to look only at the first 2 s.** The spin peak comes 1 to 2 s into the bend, so the peak within the first 2 s of entry does not separate the laps.

## Entry-speed test: frozen plan against the same plan with the bend entry raised by 5 m/s (four pairs, 2026-11-26)

- Arm A: frozen plan (plan_181941_lap3). Arm B: the same plan with +5 m/s over lap distance 2390 to 2440 m (tapering to zero over 15 m each side), `plan_fast5.json`. Eight laps per session, `--follower designed --st-head-ahead 8`, no other change.
- **The manipulation worked.** Speed at z -145 (the bend entry): arm A median 46.9 m/s, arm B median 51.0 m/s, 32 bend laps each.
- **Spins:** arm A 0 of 32 bend laps (4 sessions); arm B 1 of 32 (4 sessions; spin in lap 7, session 8, where the entry speed was 52.2 m/s).
- **Reading:** one spin against none, at equal laps, is not a difference (the chance of a single spin landing in one arm by chance is one half). The direction matches the observational finding (spins above 50 m/s at z -145), but the observational count was 2 in 13 laps and this test has 1 in 32 for the raised arm. Not a conclusion either way.
- **Next:** the spin rate at this bend is low under both plans (under 10 per cent per bend lap in every arm tested), so separating 5 per cent from 15 per cent needs roughly 60 bend laps per arm, which is about eight sessions per arm at eight laps. Either run that, or use a larger entry-speed change to raise the spin rate first (the 2 spins observed above 50 m/s were both at 52.9 to 53.4 m/s entry).

## +8 m/s entry test: first spin (2026-11-26)

- Session 4 (arm B, +8 m/s over 2390 to 2440 m, `plan_fast8.json`) spun in lap 7 (peak 130 deg/s). Entry speed at z -145 in that lap was 52.4 m/s; the same session's laps 6 and 8 entered at 55.3 and 55.1 m/s and did not spin.
- So entry speed is not sufficient for the spin. The spin lap is not the fastest entry, and the faster laps are not spinning. Something else in the lap (the braking profile, the steering state at turn-in, or the grip at the entry) decides the outcome, and the entry speed only sets its odds.
- Arm B entries in this session: 48 to 55 m/s, against about 47 m/s for the frozen plan (arm A).
