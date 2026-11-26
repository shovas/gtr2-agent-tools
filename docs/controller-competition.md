# Automated-driver competition: plan, framework, to-dos

Status: plan (2026-11-25). Source: the "Automated Racing Controller Competition" brief (a user attachment, read this day). The brief is
advice, not a rule set. Each idea is checked against our own measurements before it is acted on. Reference: the confirmed clean lap is
1:52.98 (pursuit, committed settings); the target is 1:50.8.

## 1. What the brief changes in our thinking

- **The comparison must hold the planner fixed.** The designed-versus-pursuit comparison on 2026-11-25 (`follower-redesign-plan.md`) was
  matched by position, but the two sessions had different learned grip (the live grip map learns per session), so their speed plans
  differed. A follower competition cannot be read until every competitor has the same speed plan (same memory state, same
  `--fresh-memory`, same plan file). This is the first thing the framework must fix.
- **Tracking error is not the score.** Pursuit has a 1.76 m RMS plateau offline and the best laps in the game. The designed follower
  tracks better offline and stalls in the game. Score by in-game clean laps, repeatability and corner metrics.
- **The failures start at the entry.** The designed stall began with rotation in a bend that pursuit enters about 10 m/s slower (x 504 m).
  Steering saturation followed the rotation. A competitor therefore has to control entry speed as well as steering.
- **One failed implementation does not condemn a family.** Pursuit's tracking floor may come from the look-ahead geometry rather than the
  family itself (brief, section 1). Stanley and LQR have not been measured on this car.

## 2. Framework to build (before more competitors)

1. **Common interface.** One call per control step. Inputs: position, heading, speed, yaw rate, sideslip (from position change), wheel data
   when `--dyn`. Outputs: steering and pedals, plus a debug record. A follower becomes a plug-in (`--follower NAME`).
2. **Controlled follower competition.** Frozen speed plan and frozen learned grip for every competitor; identical start (fresh tyres,
   same fuel); same layout and car. Measured: corner-level tracking, entry speed, sideslip, saturation time, clean-lap percentage.
3. **Complete racing competition.** Each competitor may also choose its speed plan. Scored on clean laps only.
4. **Leaderboard (JSON plus markdown, generated).** Per competitor: best clean lap, median clean lap, clean %, sector times, minimum corner
   and exit speed, saturation seconds, track-limit events, recovery count, control latency. A champion claim needs repeated sessions.
5. **Paired sessions.** Interleave baseline and challenger (A B A B) so drift in tyres and game state is shared. Report the paired
   difference, not two session means.

## 3. Competitors to build (ordered by expected value)

Each has a one-line hypothesis and the cheapest test that could kill it.

- **P1, pursuit with adaptive look-ahead (Team A).** Look-ahead from speed and upcoming curvature, not speed alone. Test: offline tracking on
  the same speed plan, then one paired session. Kill: no change in clean laps after three paired sessions.
- **P2, pursuit with velocity-vector aim (Team A).** Heading error measured from the velocity direction (position change over 0.1 s).
  Test: offline sideslip sweep. Kill: no change in saturation time.
- **D1, designed with entry-speed coupling (Team B).** Designed steering plus an entry-speed rule tied to the rotation it sees. This is the
  test in progress (`--brake-plan-share 0.85`, see `follower-redesign-plan.md`). Kill: stalls before 640 m.
- **D2, designed with a bounded heading correction (Team B).** Cap the heading term by the achievable curvature rather than a fixed angle.
  Earlier fixed caps only moved the failure, so this cap must depend on the speed plan.
- **L1, LQR on the lateral model (Team C).** Gains from a linear model with tyre values fitted on the logs, plus integral action.
  Test: offline closed loop from the logged start (564 m). Kill: diverges from the logged yaw within 2 s.
- **M1, kinematic MPC (Team D).** Steering, heading and track-edge constraints on a short horizon, with the kinematic model (no tyre fit
  needed). Kill: no lap at 40 m/s offline.
- **E1, empirical response model (Team E).** A lookup from the logs: steering to yaw rate by speed bin (`--steer-id` already logs it), used
  as the feedforward inside the designed follower. Kill: prediction error above 20 percent of the yaw response on held-out laps.
- **G1, yaw cascade (Team G).** Regulate yaw rate to the rate the trajectory needs; steering becomes the inner loop. Test: the two seconds
  of rotation before the 640 m stall. Kill: no reduction in saturation time.
- **H1, joint trajectory and speed (Team H).** The line optimiser already contributed to the 1:52.66 offline-to-game result; extend it to
  choose entry speed per corner with the follower in the loop. Kill: no corner-level gain after one session.
- **I1, switching ensemble (Team I).** Pursuit normally; designed only in a bend without rotation; yaw cascade when rotation exceeds a
  threshold, with hysteresis on the switch. Kill: switching chatter or no clean-lap gain. Build only after two single-follower winners exist.

Wildcards, noted but not built: preview control on the planned line (cheap feedforward); MPPI (sampling-based, handles the saturation
limit directly); DeePC (data-driven prediction from our logs, needs identification first).

## 4. Empirical identification (needed by L1, M1, E1, D2)

- Steering to yaw rate and steering to curvature, by speed bin, from `--steer-id` and the signal logs (partly done).
- Available lateral acceleration per speed and per load, from the grip map.
- A held-out check: fit on laps 1 to 6, predict laps 7 to 12 (a different tyre state).
- Sideslip: the brief asks whether 4 to 5 degrees of sideslip rules out sideslip feedback. At the 640 m stall the measured sideslip was
  about 5 degrees against 80 degrees of heading error, so velocity-vector feedback would change little there. The question stays open for
  corners where sideslip grows (the 1470 m spin logged earlier).

## 5. To-do list (ordered)

1. [ ] Record the planner state of the pursuit control run with its signal log (the control completed; no signal log was written).
2. [ ] Finish the designed test with `--brake-plan-share 0.85` (running; check the signal log for 500 to 640 m).
3. [ ] Make the speed plan a file input shared by every follower (frozen plan, no learning) for the controlled competition.
4. [ ] Implement the follower plug-in interface and move pursuit and designed behind it (no behaviour change; check against the signal
       log from before the refactor).
5. [ ] Paired-session runner: A B A B interleaving, equal lap counts, same starting state.
6. [ ] Leaderboard generator (`scripts/gtr2-leaderboard.py`) from the lap result files, markdown output.
7. [ ] P1 adaptive look-ahead: offline first, then one paired session.
8. [ ] D2 speed-plan-bounded heading correction: offline on the logged start, then in the game.
9. [ ] E1 empirical steering-to-yaw table from the logs, with a held-out check.
10. [ ] L1 linear lateral model with fitted tyres: open-loop check from the logged start.
11. [ ] M1 kinematic MPC offline at 40 m/s: only if L1 or E1 fails its check.
12. [ ] G1 yaw cascade test on the two seconds before the 640 m rotation.
13. [ ] I1 switching ensemble: only after two single-follower winners exist.

A to-do is done when its kill test has run and the result, positive or negative, is written into this file.

## 6. Rules carried over (CLAUDE.md and the brief)

- Legitimate simulated inputs only; Simulation mode and assists off; no state or grip manipulation; never the game's AI line.
- Deterministic and feedback driven; no open-loop input playback.
- Nothing is pushed without the user's go-ahead.
- Offline results only screen candidates; the game decides.

## 7. To-do 3 status: frozen speed plan (2026-11-26)

- **What exists:** the planner's learned inputs are the grip map (`gm`) and the braking map (`padec`). `--no-memory` and `--fresh-memory` control whether they are loaded from the memory file, and `--live-off grip_map,brake_adapt,...` switches the online adaptation off.
- **Gap:** the adaptation still runs unless every live system is switched off, and the driver writes the memory file at session end, so a comparison session can change the plan for the next one. Nothing records the plan a session used, so two sessions cannot be shown to have the same plan.
- **Next (to-do 3 done when):** the driver writes the plan it used (the per-distance target speed and the grip and braking numbers) to the session's result file, and a `--plan-file` option loads a saved plan with every adaptation switched off. Acceptance: two sessions given the same plan file show the same target speed at every distance, before any follower difference is read.

### To-do 3 result: `--plan-file` acceptance (2026-11-26)

- Built the plan from lap 3 of session 181941 (457 points, lap distance and target speed). Two three-lap sessions, both with `--plan-file` and no other change: 044344 and 045232.
- Target speed at 493 shared lap distances (10 m bins): median difference 0.00 m/s, 90th percentile 0.75 m/s, maximum 38 m/s at a few points (not yet explained; pit or start rows are the likely cause). The plan is applied: the median difference from the saved plan in session 044344 is 0.02 m/s.
- Result: the plan is shared. To-do 3 is done for the main chain. The maximum outliers are open.

### To-do 4 audit: follower plug-in interface (2026-11-26)

- The driver dispatches followers inline (`gtr2-drive-lap.py`, the designed and Stanley calls at the steering step, around lines 1241 to 1254). The designed branch adds its own limits after the call (`--fgrip-steer`, `--designed-curve`, `--designed-cap`); the pursuit branch is not a call to `follower.pursuit` at all: it is inline, with the aim point, the aim compensation, the live gain (`--steer-live`) and the heading error it uses coming from the driver's own state.
- **Consequence:** a plug-in interface cannot just wrap the existing functions. Pursuit's logic has to move into a module with its state passed in, and that move changes no behaviour only if it is checked in the game (or offline against the logged states at each step).
- **Plan for the step:** (1) move the three post-call limits into a shared post-processing function; (2) move the pursuit branch into `follower.py` with its inputs as arguments; (3) check the move offline by replaying a logged state sequence through the old and new code and requiring identical steering commands; (4) one 3-lap session as the final check.
- Not started: this is a refactor of about 100 lines in the driver and needs the offline replay test before any game run.

### To-do 4 step 1 done (2026-11-26)

- The designed follower's three post-call limits (front-grip steering limit, speed curve, fixed cap) moved into one function `designed_limits_` in the driver, called once. Same order, same arguments. Checked by reading and by parsing and option help. **Not yet checked in the game:** a 3-lap session with the designed settings should match a session from before the change.
- Next: step 2 (pursuit inline logic into `follower.py`), then step 3 (offline replay of logged states through old and new code).
