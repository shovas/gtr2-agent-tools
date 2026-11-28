# Summary (as of 2026-11-28)

**Goal status:** a repeatable clean 1:50.8 lap at Imola in the Maserati MC12 has not been run. The best confirmed clean lap is 1:52.66 (commit `95b03cf`). This is an open objective, not a result.

**Findings (verified by offline analysis of logged sessions unless stated):**
- The 1:52.66 lap is a tail lap; the typical lap of that build is about 2:00. The gap is mostly selection (`docs/controller-competition.md`).
- The logged `plan_speed` is a lateral speed limit with no acceleration limit. Speed gaps at corner exits are power-limited, not lost time.
- Mid-corner at 525 m: the car uses about 12 m/s² median lateral acceleration against a planner limit of 16, so that gap is not under-used grip.
- Lateral tracking: the car realises about 42% of the planned offset across the lap (slope 0.42, R² about 0.24). The logged aim offset does not explain it.
- The 700 m excursion reproduces on every lap in the committed configuration. Steering reaches about −0.45 about 2 s before the yaw divergence, while front grip falls first. This is a leading candidate, not an established cause.
- The track-limit guard is active by default (live mode). Removing it does not stop the 700 m excursion; it lengthens off-road time (about 3.0 s against about 2.0 s).
- The steering clamp rejection (`--steer-clamp`) was made under its own rules but is confounded by the guard. A guard-off retest is pre-registered and partly run (`docs/controller-competition.md`).

**Limits:** all findings come from a few sessions of one car at one track; sample sizes are small (four to twenty events); the sign conventions and the distance axis were checked, but the game's own track-limit boundary has not been checked against the waypoint widths.

**Principles:** evidence before reinvention; pre-register tests and fix rules before running; separate facts, interpretations and results; never push without the user's go-ahead.
