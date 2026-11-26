# Follower redesign plan (Imola 2400 to 2900 m and the wider deficit to 1:50.8)

Written 2026-11-25 from the experiments in `docs/imola-slow-corner-2400-2900.md` and `docs/analog-driving.md`. This is a plan, not a result. Read `docs/imola-slow-corner-2400-2900.md` first for what has been rejected, and do not repeat those tests.

## Why the current follower is the limit

- Pursuit (the adopted follower) tracks the line to 1.95 m rms in the simulator and 1.7 to 1.9 m in the game. At its best gain (scale 1.25, the Imola entry) it is at a plateau: 1.76 m rms offline, and more gain changes nothing.
- Every change that widens a slow-corner line, or that reduces the steering command near a bend, has either spun the car or sent it over the edge. Capping the heading error (offline) costs far more tracking than the spins it prevents (15 degrees: 8.9 m rms).
- The alternative followers already tested (stanley, designed) fail in the game: stanley spins on the out lap, designed saturates the steering at full lock whenever the heading error is large (about 25 degrees at 46 m/s, about 60 degrees at 25 m/s), and capping the command or limiting it by a speed curve only moves the failure to another point on the track.
- Delay compensation in the aim point is worse at every delay (the aim point already leads the car by the look-ahead distance).

The conclusion: the follower needs to plan over a horizon (what steering will keep the car on a track of given width and grip over the next second), not react to the heading error at one point.

## What a redesign has to do

1. **Predict the car, not just the line.** Use the bicycle model with the car's own yaw response (the calibrated steering lag: 0.15 s delay, 0.30 s lag in the simulator; 0.27 to 0.35 s measured in the game) to predict the next 0.5 to 1.0 s of position and heading for each candidate steering command.
2. **Plan over the horizon with the limits built in.** Choose the steering sequence that keeps all four tyres inside the boundary (the geometric track-limit rule, `gtr2_driving/limits.py`) and the lateral acceleration under the grip curve (one curve, one multiplier, 50 percent as the neutral point, as the user proposed), with the cost on lateral error and on the change of steering.
3. **Speed-scheduled everything from one curve.** The steering-to-road-angle gain is already a table (`follower.steer_gain`); the road-angle limit is `atan(L x grip / v^2)`. Both come from the car, not from fixed caps.

## Steps, in order (each one decides whether to continue)

1. **Calibrate the simulator on the designed spin first.** The simulator does not spin the car, so it cannot judge a controller that is meant to prevent spins. Log one more designed or pursuit session with `--sig-log` at the 639 m or 642 m bend and fit the car's grip limit at that point (`scripts/gtr2-model-fit.py`), or add a tyre-slip limit to the simulator until it reproduces the game's spin at 639 m. Acceptance: the simulator spins a controller that the game spins, and does not spin one the game does not.
2. **Offline MPC prototype.** A short-horizon optimiser (about 1 s, a few steering candidates per step, or a Newton step on the steering sequence) on the calibrated model, compared with pursuit on the same simulator and the same grip. Acceptance: lower cross-track rms and p95 than pursuit at the same grip, and no road exit in the simulator at grip 12.
3. **Game test, one change at a time.** Only the prototype that passes step 2. One designed session with the signal log, judged against the 1:52.98 baseline and the lateral error on the straights.
4. **Stop rules.** If step 1 cannot reproduce the game's spin, stop and record it; do not tune the prototype against the wrong model. If step 2 does not beat pursuit offline, do not run step 3.

## Status

- Not started in code. Nothing in `scripts/` implements this plan yet.
- Blocking question for step 1: whether a designed or pursuit session at the 639 m or 642 m bend (with the signal log) is enough to calibrate the tyre limit, or whether the game's spin needs a steering-rate limit in the model as well.

## Calibration result (offline, 2026-11-25): the simulator's grip limit is below the game's

From the last 12 signal logs (v x yaw rate, lateral acceleration the game car actually produces, by speed):

| speed (m/s) | median | p95 | max |
|---|---|---|---|
| 10 to 20 | 6.3 | 16.3 | 41.2 |
| 20 to 30 | 8.7 | 18.0 | 46.2 |
| 30 to 40 | 4.9 | 17.8 | 75.5 |
| 40 to 50 | 1.4 | 15.9 | 40.7 |
| 50 to 60 | 2.5 | 14.8 | 32.5 |
| 60 to 70 | 4.1 | 15.1 | 26.7 |

The 95th percentile is 15 to 18 m/s^2 at every speed; the simulator's grip limit (`--grip`, 12 m/s^2) is below it, so the simulator understeers where the game does not. The maxima (up to 75 m/s^2) are spins and kerb strikes, not grip. A single grip value does not fix the offline pursuit fit (grip 14 already gives pursuit 1.54 m, below the game's 1.7 to 1.9 m), so the mismatch is not only the grip limit: the simulator also lacks the game's rear-tyre loss, which is what the spin needs. Step 1 is therefore a model change (a rear-slip limit that depends on sideslip and load transfer), calibrated on the measured p95 and on the 639 m spin, not a change of one number. Offline check of this: the simulator should spin the designed controller at 639 m when its rear-slip limit is reached at the logged sideslip (about 8 deg at 46 m/s).

## Step 1 started (2026-11-25): the dynamic bicycle diverges, not yet usable

A scratch dynamic bicycle (front and rear tyres with saturation at mu x load, cornering stiffness 70 000 and 60 000 N/rad, mass 1290 kg, Iz 1230 kg m^2, the simulator's steering lag and delay) replaced the simulator's grip cap. Result: both pursuit and designed leave the road within 5 s, with sideslip reaching 1700 to 2800 deg. The same divergence appears at step 0.02 s and 0.005 s, so it is not integration. Checked: the bicycle equations alone are stable for constant steering at 46 m/s (the first 12 steps); so the fault is in the loop (the heading and sideslip frame, the yaw sign convention against the simulator's, or the speed profile jump at each step). Next: unit-test the loop against one logged state (the 239.4 s designed spin: 46 m/s, heading error -23 deg, lateral -1.5 m, sideslip about 8 deg) before running any controller on it. Scratch script only, not in the repository.

### Step 1, continued (2026-11-25): the sign bug is found; the rear grip is not yet calibrated

- **Fault found:** the sideslip enters the position update with the wrong sign. With the sign flipped the car stays on the track (40 s run, about 20 m off at the end) where the first version left the road within 5 s. The sideslip itself still grows without bound, which is now a spin, not a frame error.
- **Calibration sweep (designed follower, scratch model, first spin):** rear grip mu 1.5, stiffness 60 000 N/rad: spins at 1.6 s (near the start, 13 m off the line); mu 1.5, 120 000: spins at 10.3 s at 27 m/s; mu 2.0, 60 000: spins at 1.8 s; mu 2.0 or 2.5 with 120 000: no spin in 40 s. None reproduces the game, where the designed controller runs clean for about 240 s before its spin near 639 m (about 30 s into lap 1). The start-of-lap spins are a transient of the model (the car starts on the line at the planned speed of 63 m/s), not the game's behaviour.
- **Next:** calibrate the initial state (start from the logged state at about 30 s into lap 1, not from the lap start), then sweep the rear grip until the first spin falls at the 639 m bend, with the game's clean laps unchanged. Scratch scripts only, not in the repository.

### Step 1, the start from the logged state (2026-11-25)

- **Start:** the signal log of 13:31 at lap distance 564 m (x -781, z 262, 40.2 m/s, yaw rate 8.6 deg/s, sideslip -3.5 deg; the game car then spun near 640 to 650 m).
- **Model, both followers, same start:** rear grip mu 1.2 to 1.6, stiffness 100 000 to 120 000 N/rad. Designed spins at 1.4 to 3.4 s (about 80 to 120 m later); pursuit spins at 3.6 to 4.2 s. The spin location is close to the game's, but it is the same for both followers and insensitive to rear grip.
- **Reading:** the model spins from this state whatever the controller does, so the car model is unstable there (its understeer or balance is wrong), and the designed-follower spin is not identified by it yet. The game car is stable from the same state. The next fix is the car's balance (front and rear stiffness, mass distribution) against the logged yaw response (the steering gain and yaw rate already measured: yaw gain k about 0.021 to 0.029 rad/s per command per m/s), before any follower is judged on the model.
- Scratch scripts only (`rearslip_start.py`), not in the repository.

### Step 1, the car balance fitted (2026-11-25)

- `gtr2-model-fit.py` on the 13:31 log (laps 1 to 3, 65 windows): front grip mu_f 0.80 (at its lower bound), rear grip mu_r 3.44, front stiffness 34.1, rear 40.4 (the fitter's tyre form, sin(1.3 atan(c alpha)) times mu times load); yaw rate explained 80 percent, rms error 7.4 deg/s, sideslip rms 2.6 deg. Reading: the car understeers (front limited first, rear strong).
- Scratch model with these values from the logged start: **no spin in 40 s** for either controller; the car ends 1.0 to 1.7 m from the line. So the fitted balance does not contain the game's spin.
- Reading: the spin came as the brake was released at about 240 s (brake 0.2 to 0.3 with no throttle, then a yaw swing). The fit has no brake-induced loss at the rear (the `rb` split is 0.15, not identified) and no load transfer under braking into the corner. The next model step is the braking and load transfer at the rear (brake force on the rear axle, the weight that moves forward and back), then refit on a designed session that includes the brake release.
- Scratch scripts only (`rearslip_fit.py`), not in the repository.

- **Load transfer and rear braking added (`rearslip_brake.py`):** the longitudinal acceleration from the speed profile is fine (-13 to +9 m/s^2, the braking and acceleration the notes measure). But with the fitted front grip (mu_f 0.80) the friction circle leaves the front no cornering grip at 13 m/s^2 of braking (0.85 of the force on the front, about 14 000 N against a front grip of about 6 900 N), so both controllers run wide within 6 s. Reading: the fitted front grip is inconsistent with the braking the car does in the game (12 to 16 m/s^2). The fit found the front at its lower bound because the fitter has no braking data in its windows; the front grip has to be fitted jointly with the braking (mu_f at least about 1.2 to 1.4 from the braking). That contradicts the understeer reading of the fit, so the balance is not yet identified. Next: refit with the braking windows included (the fitter's windows are chosen by speed, so brake windows need a separate fit), then rerun the spin test from the logged start.

- **Refit with the front grip bounded at 1.2 (2026-11-25, same 13:31 log, laps 1 to 3):** front grip 1.20 (at the new bound), rear grip 3.40, front stiffness 4.0 (at its bound), rear 44.5, braking 19.1, rear brake share 0.19. Yaw rate explained 68 percent, rms 9.5 deg/s (the unbounded fit: 80 percent, 7.4 deg/s). So the braking-consistent front grip fits the logged yaw response worse; the front-grip conflict is real, and the single-track fitter cannot resolve it from these windows. Next: a separate fit on the braking windows only, with the speed profile's deceleration as the input, so braking and cornering grip are identified apart.
- **Game state:** the game was left on the multiplayer games list after the 367.8 s stop; it was returned to the main menu through `gtr2-nav.py goto SUMMARY_MPLIST "LEAVE MULTIPLAYER" --lan-step` and the `LEAVE LOBBY` path step (verified). The game-folder files my runs changed (Shovas.PLR, Career.blt, the replay, the new logs) are not reverted: they hold the profile the user plays with.

- **Braking-window fit (2026-11-25, ten sessions of today, laps 1 to 12, braking windows only, 11 to many windows):** front grip 1.22 (inside the range, no longer at a bound), rear grip 2.94, front stiffness 4.0 (at its bound), rear 56.7, **max braking 8.6 m/s^2**, rear brake share 0.28; yaw rate explained 89 percent, rms 4.5 deg/s. So the braking-consistent front grip is identified from braking, and it agrees with the cornering fit only once the front stiffness is free of its bound.
- **Two model gaps found from that fit:** (1) the fitted maximum braking is 8.6 m/s^2, but the game car brakes at 12 to 16 m/s^2 (the planner's measured braking map): the fit is missing the downforce that raises the braking grip at speed; (2) the scratch model had no downforce. With the fitter's downforce term (1 + 0.0004 v^2) added to the tyre loads (`rearslip_df.py`), the car stays on the road about 19 s from the logged start (before: 6.7 s), for both controllers; still no spin. So the downforce is part of the answer, but the spin mechanism is still not in the model.
- Next: fit the downforce coefficient and the braking limit jointly with the deceleration profile (the planner's brake map says 12 to 16 m/s^2 at speed), then rerun the spin test from the logged start.

- **Downforce sweep (2026-11-25, designed follower, braking-fitted tyres, from the logged start, scratch `rearslip_dfk.py`):** downforce coefficient 0.0004 and 0.0008: leaves the road at about 19 s (lateral 60 m); 0.0012 and 0.0016: stays on the road for 40 s, ending 9 and 5 m from the line. So on-road behaviour fits a downforce coefficient of about 0.0012 to 0.0016 (the fitter's own 0.0004 is too low for this car's braking). But no coefficient makes the model spin: the game spin at about 640 m is still not reproduced, from either controller. Reading: the spin needs a mechanism the model does not have (a rear loss at the moment of brake release with the designed command at full lock), not a grip number. Next: model the logged brake release explicitly (the pedal from the signal log, not the planner's decel) with the downforce at 0.0012, and test whether the rear loses grip then.

- **Logged pedal fed into the model (2026-11-25, `rearslip_pedal.py`, downforce 0.0012, braking-fitted tyres, designed follower, from the logged start):** the pedal from the signal log (brake 13 m/s^2 times the pedal when on, the profile otherwise). The logged start has no braking for the first 13 s; the heavy braking (over 0.5) comes at 14 s, and that is the brake release the game spun on. The model brakes through that window, stays on the road for 40 s (ends 9 m from the line) and does not spin. So the pedal-fed model reproduces the braking and still not the spin. The model's path and the game's diverge before 14 s, so the comparison at 14 s is only approximate. Next: compare the model's yaw and sideslip to the logged ones over 14 to 18 s, to see where the rear grip and the game's yaw part company.

- **Open-loop check (2026-11-25, `open_loop.py`):** the logged steering command and logged speed drive the model from the logged start (13:31 log, 564 m), with the braking-fitted tyres and downforce 0.0012. Over 3 s the model's yaw is about half the logged yaw (about -10 deg/s against -20 to -25 deg/s at 1.4 to 2.2 s) and its sideslip stays near zero, where the car shows 4 to 5 deg. The closed-loop traces (the model driving its own controller) were not comparable, because the controllers differ. So the tyre balance is still wrong for cornering, and the braking fit and the earlier cornering fit disagree about it. Reading: the single-track model with fixed tyre curves and constant load does not carry the car's yaw response; the front saturates in the model earlier than in the car. Next: fit the cornering windows only, open loop from the logged steering (not braking windows), and compare the yaw and sideslip directly; if the fit still cannot reach half the amplitude, add the front and rear load transfer through the corner to the model.

- **Cornering-window fit (2026-11-25, ten sessions, no brake, yaw over 3 deg/s):** front grip 0.82 (near its bound), rear grip 2.58, front stiffness 35.0, rear 57.5, braking 11.2 (not used for cornering), rear brake share 0.17; yaw rate explained 90 percent, rms 3.9 deg/s; sideslip rms 1.8 deg.
- **Open loop with the cornering values (`open_loop_corner.py`, same start):** the model's yaw now follows the logged yaw in amplitude and timing from 1.8 to 2.4 s (model -17, -20, -23 against logged -21, -22, -23 deg/s). The sideslip still stays near zero (model about 0, logged about 5 deg). So the yaw response is reproduced by the cornering balance, and the sideslip is not.
- **Reading:** the front grip is 0.82 in cornering and at least 1.2 in braking. Grip that rises with the load on the front under braking is the usual tyre load sensitivity, so the model needs a load-dependent front grip (grip = mu times load to a power below one), not two fixed values. The sideslip mismatch is a separate question (the game's sideslip definition, or the rear stiffness at low load). Next: a load-sensitive front grip, fitted on both windows together, then the open-loop sideslip check.

- **Sideslip check (2026-11-25, rear stiffness swept 10 to 57 N/rad equivalent, open loop, cornering values):** the model's sideslip stays between about -0.4 and +1.2 degrees for every stiffness, against the logged 4 to 5 degrees, and its sign flips with the stiffness. The logged sideslip has the opposite sign to the model's steady-turn relation (logged yaw -23 deg/s with sideslip +5, model yaw -17 with sideslip -0.3); the fitter already applies a sign flip to it. So the rear stiffness cannot produce the sideslip. Two explanations are open: the game's sideslip is measured at a point away from the centre of gravity (the offset gives only about 1 degree here, so it is not enough on its own), or the logged sideslip has a different reference. Next: check the game's sideslip definition against the logged values in a straight-line test (zero steering, known yaw), before changing the model again.

- **Straight-line check of the game's sideslip (2026-11-25, from the logs, no game run):** on straights (speed over 30 m/s, yaw under 2 deg/s, no steering, no brake; 18 198 samples) the logged sideslip has median 0.00 and a 5 to 95 percent range of -0.3 to 0.4 deg: no reading bias. While turning (yaw over 10 deg/s, 14 085 samples) the sideslip has the opposite sign to the yaw rate in 99.5 percent of samples: a fixed sign convention, which the fitter already flips. So the game's sideslip definition is sound. The remaining 4 to 5 deg gap in the turn is in the model's rear-slip physics: the model reaches 5 deg of rear slip only at saturation, so its steady sideslip stays small. Next: a rear-slip model that stays linear up to about 4 deg (the slip stiffness sets the sideslip directly), fitted to the logged sideslip while turning, then the open-loop yaw and sideslip check together.

- **Sideslip-weighted cornering fit (2026-11-25, `--slide-weight 4`, same ten sessions, cornering windows):** front grip 0.80 (at its bound), rear grip 2.51, front stiffness 31.4, rear 61.2; yaw rate explained 90 percent (3.88 deg/s rms), sideslip rms 1.77 deg. Raising the sideslip weight changed nothing: the fitter's sideslip error stays at 1.8 deg, so the sideslip is not a parameter it can reach with this tyre form. The single-track structure with these tyre curves cannot produce the 4 to 5 deg steady sideslip while turning. Decision for the plan: the model cannot be made to reproduce the car's sideslip without a different tyre model (a combined-slip or a load-sensitive tyre with linear slip up to about 4 deg), and step 1 of this plan is not complete.

## Stall at 639-670 m: the causal chain from the 14:03 log (2026-11-25, designed follower, lap 1)

Source: `scripts/gtr2_ui/runs/signals_20261125_140358.csv` (the session that stopped at 642 m, recovered and left the game at CONFIRM_EXIT). Logged samples are about 0.11 s apart; the chain below is read from every row in 341.0 to 345.2 s.

- **341.0 to 342.1 s (entry, 64 to 67 m/s):** throttle at full (duty 1.0) while the planned speed falls from 91 to 73 m/s. The planner's latest-braking envelope says brake from about here, but the throttle is still on until the plan drops below the car's speed (about 342.1 s).
- **Yaw builds from 1 to 13 deg/s with steer only +0.05 to +0.15.** Front grip use rises from 0.98 to 0.86 over the same window (the logged front_grip column; it is a utilisation, not a coefficient).
- **342.2 to 343.4 s: braking is gated by the trail limiter, not by the driver.** The limiter scales the pedal by sqrt(1 - (yaw_rad x speed / 18)^2). At 65 m/s the scale reaches zero at a yaw of about 15.6 deg/s. Logged yaw peaks at 15 to 18 deg/s in this window, and the logged brake is 0 to 0.4 (mean about 0.25) where a full pedal of 0.85 to 1.0 was asked. Speed falls only 67.6 to 62.0 m/s in 1.2 s (about 4.7 m/s^2 against the 12 to 13 the plan needs).
- **343.4 to 344.1 s:** the pedal comes back at 0.45 to 0.99 with the car at 62 to 54 m/s, 4 to 8 m/s faster than the plan, and the car is already yawing at the wrong moment: sideslip swings from -4.9 to +4.9 degrees and yaw reverses to -19.6 deg/s by 344.8 s.
- **344.8 to 346.9 s:** heading error grows from -13 to -82 degrees while steer goes to full lock (-1.0 at 346.9). Lateral error passes 20 m. The car stops at 641 to 642, 439 m, 24 m off the line.
- **What this rules out:** the trail limiter is a real, measurable cut of the brake at this entry (it explains the flicker), but it is not the only fault: the brake returned at 0.99 and the car still span.

**Test (2026-11-25):** the designed follower with `--trail-floor 0.5` (brake never below half the pedal). The first two attempts did not run: the first returned zero seconds because the previous game was still open (`GTR2 is already running`), the second because the game folder had run-generated changes (`UserData` and `ReplayData` uncommitted: Shovas.PLR, Career.blt, SIM_OFFICIAL.bch, Imola.Vcr and logs). Those changes were reverted to the committed profile with `git checkout` and the untracked run files removed; the lap-check writes its own environment (Speed Sensitive Steering 0.6, Steer Ratio Speed 25) before every run, so the committed profile is the correct base. Result of the run: see below.

**Result of the trail-floor 0.5 test (2026-11-25, designed follower, lap 1):** not a valid test of the stall. The run stopped at the pit exit (x -992, z -317, lap 0, recovery attempts 2), before reaching the 639 to 670 m zone. The control with the committed `--trail-floor 0.0`, same command and same reverted game state, stopped at 663 m, 445 (inside the known zone), so the revert itself did not change the stall. Reading: the floor change alters behaviour on the pit chain (the limiter acts from 12 m/s), so it cannot be judged at 642 m until the pit exit is handled. The limiter is therefore not shown to cause the 642 m stall. Next test that isolates it: apply the floor only above the pit speed (or start the floor after the first 300 m), then rerun the pair.

## Designed versus pursuit through the same corner (2026-11-25, signal logs 140358 designed, 152120 pursuit)

Matched by position (within 6 m) on lap 1, the two runs are the same to about x 454 (both 65 to 67 m/s, yaw 11 to 15 deg/s, steering small). They diverge in the braking zone:

| x, z (m) | designed speed / planned | pursuit speed / planned |
|---|---|---|
| 409, 246 | 65.8 / 80.3 | 65.0 / 129.2 |
| 454, 290 | 67.5 / 70.4 | 65.3 / 60.7 |
| 504, 324 | 62.8 / 59.4 | 53.5 / 51.7 |
| 555, 344 | 52.6 / 42.0 | 40.7 / 39.6 |
| 595, 359 | 42.4 / 30.4 | 25.5 / 24.7 |

Reading: the pursuit run brakes earlier in the 409 to 504 m stretch and enters the sweeping bend about 10 m/s slower; both cars rotate the same way there. The designed run carried its speed into the bend and was then a few m/s over the plan when the rotation started. The sessions did not have identical planner state (the live grip map learns per session), so this is a strong pointer, not proof. Test: designed follower with `--brake-plan-share 0.85` (earlier braking), one 12-lap session with signal log.

## Designed with earlier braking (`--brake-plan-share 0.85`, 2026-11-25, signal log 153825): first designed session past the 640 m zone

- Five laps completed on the designed follower: 126.1, 127.8, 128.4, 127.6 and 148.5 s. The sixth lap stopped at x -481, z 1 (not at 640 m).
- Every lap was marked not clean. The track-limit events were at x -880 to -930, z 120 to 190 (the pit-exit merge), and there was one kerb impact at the start-finish line (Kerbs21, 71 m/s^2 at x -3, z -1). The pursuit control had the same start-finish kerb on its lap 1.
- Entry: at x 542, z 338 the car was at 52 m/s with brake 0.99 and planned 40 m/s, i.e. braking before the bend; the earlier designed runs were at 65 m/s there.
- Reading: the earlier braking lets the designed follower through the 640 m zone (the stall was an entry-speed problem, as the position-matched comparison suggested). Laps are about 7 to 8 s slower than pursuit's 117 to 120 s, and the pit-exit merge needs its own look.
- Next: the lap-6 stop at x -481, and the pit-exit track-limit events, before any tuning of the designed follower.

### Lap 6 of the 153825 session and the pit-exit track-limit events (2026-11-25)

- **Lap 6 is a spin, not a stall.** At 868 to 875 s the car entered a bend at about 48 m/s (x -551, z -136) with brake 0.31 to 0.36 and steering +0.23 to +0.43 into rising yaw (8, 22, 37 deg/s). Steering then went to -0.58 (counter), and yaw reversed to -105 deg/s with sideslip 65 degrees at x -486, z -6. It came to rest at x -475, z 0, 10 s later, facing 137 to 160 degrees away from the line, and the recovery never freed it.
- **Same pattern as the 642 m stall:** trail braking while the yaw is already rising, then a counter-steer that comes too late. The brake was still applied at 0.31 to 0.36 when the yaw was 8 to 22 deg/s, which is the trail-limiter region.
- **Pit-exit track-limit events are not designed-specific.** The pursuit sig-log session (152120) logged a track-limit event at x -892, z 168.5, the same place as the designed events at x -880 to -930, z 120 to 190. So the merge is a track-geometry issue for every follower.
- **Next:** test one change at this bend only: the trail limiter with floor 0.5 and min-speed 25 (the isolating test, which has still not run past the pit), or an earlier entry at the same bend. Judge it by the same bend's yaw and speed, not by the lap time.

### Paired test: limiter floor 0.5 above 25 m/s on the earlier-braking designed follower (2026-11-25, signal log 160047)

- Control (153825, floor 0, earlier braking): five laps past 640 m at 126 to 148 s, then a spin at lap 6 (x -486, z -6).
- Treatment (160047, floor 0.5 above 25 m/s, earlier braking): seven laps, all not clean, at 127.7, 142.1, 165.5, 129.8, 161.4, 150.7 and 138.4 s. Lap 8 stopped at x -508, z -14, in the same bend as the control's spin.
- Peak yaw in that bend in the treatment: 75.7 deg/s at x -524, z -31, with steering at full lock and sideslip -28 degrees.
- Reading: the floor does not remove the spin in this bend; the treatment is slower and more variable than the control. The limiter floor is not the fix. Rejected for this bend on one paired session (two sessions would be needed to call it definitively, but the spin repeated in the same place).
- Next: the spin bend itself. Entry speed (48 m/s) and braking while the yaw rises are the common factor; test an earlier brake plan only into that bend (a position-limited speed cap), judged by yaw and speed there, before any lap-time claim.

### Correction: where the two problems are (lap distance, from `gtr2_driving/racingline` on 4Imol.AIW, 2026-11-25)

- The **640 m stall** is at lap distance about **3936 m** (x 642, z 439). Earlier braking (`--brake-plan-share 0.85`) fixed it: five laps past it.
- The **lap-6 spin** is at lap distance about **2570 m** (x -524 to -486, z -31 to -6), inside the 2400 to 2900 m section. It is a different problem, not the 640 m stall, and the earlier entries of this file that place the spin bend at the 640 m zone are wrong.
- Both problems have a separate lap-distance zone, so the braking change can be applied per zone. New option: `--brake-plan-zones FROM TO ...` with `--brake-plan-zone-share` (the braking share inside the zones; elsewhere `--brake-plan-share`).
- Test running: `--brake-plan-share 0.85 --brake-plan-zones 2300 2800 --brake-plan-zone-share 0.6`, one 12-lap designed session with the signal log. Control: the 153825 run (0.85 everywhere), which spun at about 2570 m on lap 6. If the spin still happens at 2570 m with the stronger zone braking, braking into that bend is not the lever.

### Zone braking at the spin bend, and why the designed follower steers harder there (2026-11-25)

- **Zone share 0.6 at 2300 to 2800 m (162327):** seven laps (126 to 145 s, all not clean), then a spin at lap 8 in the same bend (x -513, z -13): peak yaw -196 deg/s, sideslip 90 degrees, speed 12 m/s. Stronger braking into the bend only delayed the spin (lap 6 to lap 8); laps 4 to 7 were slower. Braking into the bend is not the lever.
- **Same bend, pursuit (152120) against designed (153825):** both enter at about 36 to 38 m/s. At x -538 to -541, z -44 to -48 pursuit steers 0.04 to 0.17 with heading error 2.4 to 5.6 degrees and yaw 6 to 10 deg/s. The designed run at the nearby point (x -536 to -554, z -39 to -80) steers 0.43 with heading error 12.7 degrees and yaw 22 to 37 deg/s.
- **Mechanism (a candidate, not yet proven):** the designed follower measures its heading error against the line direction at the nearest waypoint, which lags at the entry of a bend. The heading error is then too large, and the steer demand at about 40 m/s over-rotates the car. Pursuit measures against an aim point 60 m ahead, so its error is small.
- **Test (162327's sibling, 2026-11-25):** the designed follower with the heading measured 8 m ahead (`--st-head-ahead 8`) on the earlier-braking base (0.85 everywhere). Control: 153825. Judge by the steer and heading error at the entry of the bend, then by the spin.

### Heading measured 8 m ahead (`--st-head-ahead 8`, earlier-braking base, clean retry 170607, 2026-11-25)

- **Bend entry changed as predicted:** heading error 2.3 to 3.3 degrees and steering 0.05 to 0.08 at x -545 to -538, z -55 to -43, where the control (153825) had 12.7 degrees and 0.43.
- **The spin bend was passed on every lap:** five laps through it (about 2570 m) with no spin. The control spun there on lap 6; zone braking spun on lap 8.
- **Laps:** 129.0, 141.9, 130.4, 143.6 s, all marked not clean. Slower than pursuit (117 to 120 s), so the heading fix alone is not a lap-time gain.
- **New stop:** after lap 5 (715 s) the car stopped at x -1015, z -285 facing 147 degrees away from the line. This is the pit-exit stall pattern (x -992 to -1165) seen in earlier logs; it is a separate problem, not the bend.
- **Reading:** the nearest-waypoint heading lag was a real cause of the entry over-steer; measuring the heading ahead removes the spin in that bend. The next limits are the not-clean laps and the pit-exit stop.

### The pit-exit stop is a corner-exit excursion (lap 5 of 170607, 2026-11-25)

- **What happened:** from 724 s the car drifted up to 15 m off the line between x -700 and -1000 (lap distance about 650 to 800 m on the line). At 731 s the planned speed jumped from 52 to 127 m/s (the live planner had released the corner), throttle went to 1.0 while steering was still -0.6 to -1.0, and yaw swung from -17 to +35 deg/s. The car came to rest at x -1015, z -285 facing 147 degrees away from the line.
- **Offline profile (default physics, `racingline.lap_time`, not the live planner):** the speed falls to 26 m/s at 651 m and rises slowly to 49 m/s at 796 m, so the corner is long and still curving at the point where the live plan went to full speed.
- **Hypothesis (not yet tested):** the live planner's corner window ends at the apex of a long, opening corner, so it allows full throttle while the line still curves. The designed follower then has to hold a large steering angle through a corner the throttle is pushing it out of.
- **Test to run:** print the live planner's target speed along lap distance 600 to 800 m in one run (the `tvg` / `plan_speed` column), compare it with the offline profile, then, if it is short, extend the corner limit to the end of the curve (the curvature span option) and rerun the lap-5 segment.

### Live lateral limit 13 m/s^2 (vs 16) on the heading-ahead configuration (183516 against control 181941, 2026-11-25)

- **Control (heading 8 m ahead, live lateral 16, 181941):** six laps at 128 to 161 s, all not clean; the bend entry healthy every lap (heading error about 2 degrees); spin in the 2570 m bend on lap 5 (x -478, z 2, peak yaw 133 deg/s; lap 4 peaked at 116; corrected from an earlier note that said lap 7, checked against the per-lap peaks of 181941).
- **Treatment (live lateral 13, 183516):** five laps at 132.6 to 135.0 s, steadier but slower; bend peak yaw 41 to 47 deg/s on laps 1 to 5; spin in the same bend on lap 6 (x -511, z -4, peak yaw -130 deg/s, speed 17 m/s).
- **Reading:** a lower lateral prior makes the laps steadier and slower but does not stop the spin in the 2570 m bend. The planner's lateral limit is not the lever for this spin. Rejected for the bend; keep the 16 prior.
- **Where this leaves the bend spin:** entry steering is fixed (heading ahead), braking into the bend is not the lever (zone share 0.6 spun on lap 8), and the planner's lateral prior is not the lever (13 spun on lap 6). The spin is a late, recurring event in the same place; the next thing to look at is the yaw response to the trail-braking release just before the rotation (what the car does in the 0.5 s before yaw exceeds 25 deg/s), not another speed plan.

### Turn-in at the 2570 m bend: the same on every lap, the spin depends on the front tyres (183516 and 181941, 2026-11-25)

- Every lap, including the ones that do not spin, has the same turn-in at about x -555, z -110: speed 36 to 44 m/s, steering 0.3 to 0.4, heading error building from 2 to 12 to 13 degrees over about 1 s, brake falling from 0.3 to 0 as the steering comes on.
- Then the yaw jumps past 25 deg/s, and the front grip (logged `front_grip`) falls from about 0.9 to 0.4 to 0.6 in 0.3 s. The rear grip stays 0.8 to 0.98 until the snap. The spin happens when the front tyres saturate under steering at this speed; the non-spinning laps reach the same state and recover.
- So the mechanism is front-tyre saturation during turn-in, not the planner's speed (zone braking and lateral prior did not stop it) and not the heading reference (fixed).
- **Next candidate (new, not built):** a front-grip-aware steering limit. When the measured front grip drops below about 0.9 during turn-in, the steering command is limited (a friction-circle steering cap) so the front tyres are not pushed further into saturation. This is different from the fixed steering caps tested earlier: it reacts to the measured tyre state, and it is off unless the front grip falls. Test it as a paired session against the 181941 control.

### Front-grip steering limit (`--fgrip-steer 0.9`), two versions (2026-11-25)

- **Version 1, proportional (183957):** scaled all steering by front grip / 0.9 when the front grip was below 0.9. Lap 1 spun at about 154 s (x -711, z 360s, steering counter-steering at -0.56) because the limit cut the counter-steer. Rejected.
- **Version 2, only steering that adds to the rotation (190326):** the same limit, applied only when the steering and the yaw rate have the same sign (steer times yaw rate positive). Counter-steer is never cut.
- Result of version 2: nine laps, 130 to 146 s (lap 8 185 s), all not clean. Peak yaw in the 2570 m bend was 45, 49, 81, 82, 64, 39, 39 and 38 deg/s on laps 1 to 8: no spin in the bend. The control (181941) spun there on lap 7 and the 183516 lateral test on lap 6. Lap 9 stopped at x -630, z -475, away from the bend.
- **Reading:** this is the first change that keeps the bend from spinning for eight laps in one run. It is one session, so it needs a repeat against the same control before it counts. It is not yet a lap-time gain.

- **Repeat of version 2 (191219):** spin in the 2570 m bend on lap 3 (peak yaw 138 deg/s, x -489, z 3; the car stopped there). So version 2 is not a reliable fix: one run of eight clean bend laps and one spin on lap 3. Treat the first run as luck until a paired set of at least four sessions per arm shows the difference. The limit stays off by default.

### Paired test of the directional front-grip limit (8 sessions, 8 laps each, alternating C T, 193128 to 212629, 2026-11-25)

- Spin in the 2570 m bend counted as yaw of 120 deg/s or more. Control (C, sessions 1, 3, 5, 7): no bend spin in any session (peaks 84 to 107 deg/s; sessions 5 and 7 stopped at the pit exit, not in the bend). Treatment (T, `--fgrip-steer 0.9` directional, sessions 2, 4, 6, 8): spin on lap 3 (session 2, peak 130) and lap 6 (session 8, peak 149); sessions 4 and 6 had none.
- Count: control 0 of 4 sessions with a bend spin; treatment 2 of 4. Fisher's exact p about 0.5, not significant, but the limit is not better and may be worse.
- **Decision: rejected.** The earlier clean eight-lap run was luck. `--fgrip-steer` stays off by default. The option is kept in the tool for the record.
- Side finding: the control's bend peaks on laps 1 to 6 stayed below 110 deg/s, while the earlier 181941 control spun on lap 7 at 133 deg/s. The spin rate in the bend varies between sessions for the same settings, so any future bend comparison needs at least four sessions per arm.

### Turn-in demand against the front-tyre margin (all bend logs, 2026-11-25)

- At the first turn-in in the 2570 m bend the demand is the same in every log: steering 0.26 to 0.31, heading error 10.3 to 11.7 degrees, speed 30 to 38 m/s.
- What differs is the front grip in the next 0.6 s: 0.35 to 0.41 in the sessions that spun or came close (200548, 210739), about 0.75 in the sessions that held. Readings of 0.00 in 181941 and 183516 look like sensor dropouts and are not used.
- Reading: the turn-in steering is a reproducible demand; whether the front tyres keep their margin decides the spin. The next lever is the margin itself, so the planner should arrive at turn-in with more front grip in hand (slightly lower speed at the apex) or the follower should ask for less front lateral force at turn-in while the heading error is large. Both change the turn-in demand, so each needs a paired test with at least four sessions per arm.

### Turn-in margin test: braking share 0.6 in 2300 to 2800 m (four treatment sessions, 215633 to 225302, against the four control sessions of the paired set, 2026-11-25)

- Treatment: no bend spin in any of four sessions (peaks 82 to 102 deg/s). Session 1 stopped at x 625, z 455 (the old 640 m stall area), the others at the 8-lap time budget.
- Control (same base, four sessions): no bend spin (peaks 84 to 107 deg/s).
- **Reading:** both arms had zero bend spins, so this test cannot show that the lower speed at turn-in reduces spins. The spin rate in these sessions was too low to measure a difference. Not adopted as a fix; the lap-time effect is not shown either.
- **Next:** the spin rate changes between sessions with the same settings, so a bend-spin comparison needs at least eight sessions per arm, or a test that provokes the spin (a higher turn-in demand) so both arms spin often enough to compare.

### Provoking setting: braking share 1.0 in 2300 to 2800 m (four sessions, 231635 to 001307, 2026-11-25 to 26)

- Bend spin (yaw 120 deg/s or more) in three of four sessions, on laps 4, 6 and 7 (peaks 140, 135, 168 deg/s). The session with no spin peaked at 96 deg/s.
- Control at the 0.85 base (four sessions, same 8-lap budget): no bend spin in any session (peaks 84 to 107 deg/s). Fisher's exact (one-sided) about 0.07.
- **Reading:** raising the speed into the 2300 to 2800 m zone makes the 2570 m bend spin in most sessions. This is a usable test bed: a candidate fix can be judged on spins per session here, with four sessions per arm.
- **Next:** test the directional front-grip limit (`--fgrip-steer 0.9`) on this provoking setting, four sessions, against these four provoking sessions as the control.

### Directional front-grip (`--fgrip-steer 0.9`) on the provoking setting, first four sessions (2026-11-26)

- Bend spin (120 deg/s or more) in one of four sessions (lap 7, peak 162). Session 1: no spin across seven laps. Session 2 stopped at the old 640 m stall, before the bend. Session 3 stopped on lap 3 at x -960, before the bend. Provoking control: spin in three of four.
- Reading: a possible reduction (1 of 4 against 3 of 4), but two sessions failed before the bend, and four sessions per arm are not enough. Running four more directional sessions (5 to 8) to reach eight per arm before any decision.

### Directional front-grip on the provoking setting, all eight sessions (2026-11-26)

- Bend spin (120 deg/s or more in the 2570 m bend): sessions 4 (lap 7, 162 deg/s), 7 (lap 5, 121, stopped at the bend exit) and 8 (laps 4 and 5, 125 and 123). Sessions 1, 5 and 6 ran seven or six laps with no spin; sessions 2 and 3 stopped before the bend (at the 640 m stall and on lap 3).
- Provoking control: three spins in four sessions (laps 4, 6 and 7).
- Per bend lap: about 7% (3 in about 42 laps) against about 11% (3 in about 28). Not significant, and the effect is at most small.
- **Decision: not adopted.** `--fgrip-steer` stays off. The front-tyre margin at turn-in is the mechanism, but a steering-side limit does not remove it reliably. The next lever is the turn-in speed or the turn-in demand itself, tested on the provoking setting with eight sessions per arm.

### Turn-in demand: heading measured 16 m ahead on the provoking setting (four sessions, 2026-11-26)

- Session 1 stalled at x 631, z 444 (the 640 m point), before the bend. Session 2 spun in the bend on lap 6 (135 deg/s). Session 3 stopped at the bend exit (x -483, z 9) on lap 6, peak 116 deg/s (counted as a spin, as for the directional session with the same stop). Session 4 ran seven laps with no spin (peak 87 deg/s).
- Two bend spins in four sessions, against three in four for the 8 m heading control. Not a reduction, and one early stall at 640 m.
- **Decision: not adopted.** The 16 m heading is not better than the 8 m heading on this setting, and it adds the 640 m stall. Keep 8 m.

### Turn-in margin lever: zone braking share 0.6 on the provoking setting (four sessions, 2026-11-26)

- Two bend spins (sessions 2 and 4, laps 4 and 5, 147 and 139 deg/s) and two stalls at the 640 m point before the bend (sessions 1 and 3).
- Per bend lap: about 17% (2 in about 12 laps) against 11% (3 in about 28) for the share 1.0 control. Not a reduction.
- The 640 m stall shows up more often in this setting (two of four here, one of four with the heading at 16 m). It is a cost of the lower entry speed or the earlier braking.
- **Decision: not adopted.** Lowering the entry speed does not reduce the turn-in spin. The turn-in front-tyre margin is not fixed by speed alone.
