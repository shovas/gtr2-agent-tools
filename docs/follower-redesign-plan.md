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
