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
