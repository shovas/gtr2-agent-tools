# Telemetry anomalies: what the logged yaw rate can and cannot be trusted for

Status: hypothesis with an offline reproduction; the in-game cause is not yet confirmed (2026-11-26).

## The yaw-rate spike (run 1, arm A, session 1: signals_20261126_054425.csv)

- At t 898.27 s (lap 6, speed 29.6 m/s, x -529, z -362) the logged yaw rate jumps 38, 355.8, -179.5, -28.3 deg/s over three samples. Front grip reads 0.0 at the same moment and sideslip swings from +6 to -8 and back to +17.
- Heading taken from the logged position (whole metres, about 4 m per sample) is too coarse to confirm a 356 deg/s rotation: it moves in 15 deg steps. The spike is therefore not confirmed by the position track, and the position track is not precise enough to disprove it.

## The driver computes yaw rate from one read interval

`gtr2-drive-lap.py` (before this change):

    yawrate = wrap(yaw - prev_yaw) / dt        dt = wall-clock time between two telemetry reads

Nothing bounds `dt` from below. When two reads come close together, a small yaw step over a tiny `dt` becomes a large rate.

## Scale of the problem in the logs

- 382 signal logs: 319 samples with |yaw rate| of at least 150 deg/s. 309 of them sit in sustained runs (real spins, or the steering dynamics that go with them). Only 5 are isolated (neighbours under 60 deg/s): -188 (t 1554.7 s in session 20261120_221854, 52.5 m/s), -232 (8.7 m/s), -152 (28.5 m/s), +433 (13.3 m/s, where steering drops from 1.0 to 0.6 next to it) and -186 (22.6 m/s).
- The isolated spikes are rare, but the +433 sample coincides with a steering drop: the damping term `yawrate / 90` in pursuit and the designed follower's damping would see a 4.8 unit kick there, which can move the wheel. The effect on control has not been measured.

## Offline reproduction (not in the game)

Steady 30 deg/s yaw, the game reporting yaw to 0.1 deg, reads at random intervals from 1 to 120 ms:

| estimator | max abs rate | 99th percentile | fraction over 100 deg/s |
|---|---|---|---|
| one read interval | 100 | 50.0 | 0.0000 |
| change over at least 0.05 s | 32 | 31.4 | 0.0000 |

The one-read estimator's worst case is set by the 0.1 deg resolution divided by the shortest read gap, so it can reach hundreds of deg/s on a real turn when two reads land together. The windowed estimator keeps it near the true rate.

## What is done

- `--yaw-window SECONDS` added to `gtr2-drive-lap.py`, default 0 (the old estimator, so no behaviour change). The steering law reads this same yaw rate (the pursuit damping term and the designed follower's damping), so turning it on changes control: any experiment with it must be a new arm, not a replacement of the baseline.

## Open

1. Confirm the game's yaw resolution and read cadence from a live run: log the read gap `dt` for each sample in a new run (not yet logged).
2. Measure whether the isolated spikes move the steering command (paired steer before and after each spike, across all sessions).
3. Decide whether `--yaw-window` becomes the default, only after a paired comparison shows no loss in the 2570 m bend.
4. The earlier note that a 0.1 s sample of the sideslip and yaw is enough to see a slide still holds for sustained spins; this file only concerns single-sample spikes.

## Frozen speed-plan outliers (38 m/s): a logging comparison, not a plan failure (2026-11-26)

- In the two plan-acceptance logs (044344 and 045232), 647 and 536 samples differ by more than 5 m/s between the applied target (`target_v`) and the live planner's column (`plan_speed`). The "38 m/s" maximum came from that comparison, not from the applied plan.
- `plan_speed` is the live planner's value, which the frozen plan does not replace. Its large values (127 to 145 m/s) sit at the start of lap 1 and on the main straight, where the live planner has no limit, while `target_v` follows the frozen plan.
- Of the large differences, 81 and 75 are in the pit-exit box (x below -850, z below -250), which is a separate chain: the plan only covers the main chain.
- Consequence: the acceptance check must compare `target_v` between the two sessions (both plan-applied), not against `plan_speed`, and must exclude the pit chain. The median difference between the two applied targets was 0.00 m/s (the earlier acceptance result); the outliers at a few points still need the lap-distance binning at the lap boundary checked.
