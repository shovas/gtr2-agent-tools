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

- **Game check of step 1 (051229, three laps, standard designed settings):** no traceback, first lap 129.3 s (earlier designed laps 126 to 131 s), mean |steer| 0.19 at speed above 15 m/s. The session stopped at the pit exit on lap 2 (the known pit-exit pattern). This is a smoke test that the moved function runs and does not change the car's pace; an exact comparison would need identical randomness, which the game does not give.

- **To-do 4 step 2 (pursuit):** the pursuit steering law moved to `follower.pursuit_steer(herr, yawrate, steer_gain, damping, live_scale)`, called by the driver. The target selection (aim point, aim compensation, box and pit logic, edge guard, wall clamp) stays in the driver by design: it depends on the driver's state, and the follower is the steering law, the driver the target.
- **Step 3 (offline replay of the steering law):** 200,000 random cases of heading error, yaw rate, gain, damping and live scale: maximum difference 0.0 against the old inline formula. The default scale gives the same value. This checks the arithmetic, not a full game replay; the target selection is unchanged code.
- Next: a three-lap game session with the pursuit settings, to confirm pursuit behaves as before (the designed check was done).
- **Game check of the pursuit move (pursuit_check.out, three laps, default pursuit follower):** no traceback. Lap 1 125.8 s (not clean), lap 2 125.3 s clean. That is in the pursuit range for this session length (the earlier pursuit control laps were 119 to 122 s, with its learned memory), so the moved steering law runs and does not slow the car in an obvious way. A same-session comparison would still need the paired protocol.

### First paired run through `gtr2-paired.py` (2026-11-26)

- Arm A: the provoking planner (braking share 1.0 in 2300 to 2800 m, heading 8 m ahead). Arm B: the same car with the frozen speed plan from control session 181941 (`--plan-file`). Two pairs, so **two sessions per arm** (an earlier note said four; that was wrong).
- Result: no bend spin in any of the four sessions (A 10 bend laps, B 16 bend laps). Too few sessions to read; the provoking arm had three spins in four sessions in the earlier run, so 0 of 2 here is within chance of that rate.
- Next: more pairs (at least four pairs per arm for a decision), and a check that the provoking setting still spins in this game state before reading the frozen plan against it.

### Second paired run (2026-11-26): arm A 2 spins in 5 sessions, arm B 0 in 4

- Run 2 (three pairs, `paired_run2.out`): A spun in lap 6 (session 1) and lap 7 (session 5), no spin in session 3. B had no spin in sessions 2 and 4. Session 6 (B) wrote no signal log (the session did not reach the driver's end), so it has no bend data and is not counted.
- Tally of all records in `gtr2_ui/runs/paired.jsonl` (10 lines): arm A 2 spins in 5 sessions with bend logs, 34 bend laps (about 6% per bend lap); arm B 0 spins in 4 sessions, 32 bend laps.
- Still below the eight sessions per arm the decision needs. Read this as a hint that the provoking planner spins more, not as a result. Next: a failed-session check (why session 6 wrote no log) and more pairs.

### Leaderboard v1 and validation findings (2026-11-26)

- `scripts/gtr2-leaderboard.py` builds the markdown and JSON from the raw records. Controllers are the paired arm options; spins have a 95 % Wilson interval and a Beta(1, 1) posterior probability; infrastructure failures are counted apart; status is provisional below eight sessions.
- **Clean-lap flags are not reliable enough to rank on.** A lap flagged clean sat in a session whose record says it exceeded track limits five times; a 3.5 s "lap" appeared at Monza. The leaderboard counts a lap only when its session is clean, the lap is flagged clean, and its time is between 60 and 400 s.
- With that strict rule the best Imola clean lap in the lap records is 1:55.4, and the median is 2:01.0 (322 clean laps, 3434 unclean or failed). That does not match the confirmed 1:52.98 in our notes. Until the 1:52.98 lap is traced to its record and signal log, the notes and the leaderboard disagree, and the leaderboard is the conservative one.
- Next: link each lap record to its controller (a controller id in the lap result), trace 1:52.98 and 1:52.7 to their records, and add the lap times of the paired sessions to the paired records.

### Correction: the clean-lap rule is per lap (2026-11-26)

- The strict session rule above was wrong. The 1:52.98 lap (2026-11-24 23:49, lap 9) is clean by its own flags (no track-limit event, no impact), but its session is unclean because of laps 1 and 12. The session flag cannot decide a single lap.
- The leaderboard now counts a lap when the lap is clean, has no track-limit event and no impact, and its time is between 60 and 400 s.
- Under that rule the best Imola clean lap is **1:52.66** (2026-11-25 00:17, lap 11; that session also had five track-limit events, all on other laps). The median clean lap is 2:03.3 across all sessions, because it includes laps in sessions that were not running the pace setup.
- Consequence: the confirmed baseline is 1:52.66 (the best per-lap clean lap), not 1:52.98; the notes should say so once the lap is checked against its signal log.

### Baseline check against the signal logs (2026-11-26)

- **1:52.66** (lap 11, session 2026-11-25 00:17:54, signal log `signals_20261125_001740.csv`): the lap's span in the signal log is 112.5 s; the lap check says 112.66 s. Agreement within the sampling of the log (0.1 to 0.2 s).
- **1:52.98** (lap 9, session 2026-11-24 23:49:37, signal log `signals_20261124_234925.csv`): the signal span is 112.9 s against 112.98 s in the lap check. Agreement within sampling.
- Both laps are supported by their own logs. The best clean lap under the per-lap rule is therefore 1:52.66, and the 1:52.98 baseline in the notes is a real clean lap, not a bad record. The target 1:50.8 is 1.86 s faster than 1:52.66.

### Where the fast laps gain time: a first look at the logs (2026-11-26, not conclusive)

- 706 usable laps (100 to 140 s, from the 2026-11-24 to 26 signal logs): the fastest fifth (111.5 to 115.9 s) against the slowest fifth (130.4 to 139.6 s), compared by mean speed in 50 m map cells with at least 40 samples.
- The cell comparison is not usable as it stands. The largest differences (+20 to +25 m/s at x -950, z -50 to 100) come from laps passing those cells at different points of their lap, not from different speeds. No lap there dropped below 5 m/s, so these are not stalls.
- Next (to answer the question properly): align every lap by lap distance (the lap check records the distance at each event; the signal log needs a distance column), then compare speed at equal distance. Until then no section is named as the place the fast laps gain time.

### Lap-distance alignment: where the fastest and slowest laps differ (2026-11-26)

- Lap distance rebuilt by summing the distance between logged positions from each lap's start (median lap 4882 m, 706 laps). Fastest fifth (111.5 to 115.9 s) against slowest fifth (130.4 to 139.6 s), speed at equal distance.
- The largest difference is **700 to 950 m**: fast laps average 56 m/s and slow laps 36 m/s in that stretch (slow laps' minimum 28 m/s, so no stop or recovery). Elsewhere the two groups match within about 2 m/s, including the 2400 to 2450 m bend.
- Caveat: the slow laps come from other sessions and settings (the logs are not one configuration), so this is a difference between configurations as much as a driving effect. Before a corner is named, check which settings each slow lap used, then re-measure in that stretch with one setting.
- The 700 to 950 m stretch is where the time differences between configurations sit, so it is the next place to look for the 1.86 s to the 1:50.8 target.

### The slow laps are a later era, not a random sample (2026-11-26)

- Per-session lap medians: sessions from 2026-11-24 23:00 to 2026-11-25 about 13:00 run at 112 to 117 s; sessions after about 14:00 on 2026-11-25 (and all of 2026-11-26) run at about 130 s. The split is sharp, not gradual.
- The signal logs have the same 20 columns in both eras, so the logs cannot say which follower or settings ran. Candidates: a change of follower, or the learned memory (the grip and braking maps the driver keeps between sessions and saves only when a session is faster).
- Test running now (`paired_memory.jsonl`): pursuit with its saved memory against pursuit with `--no-memory` (nothing loaded or saved), two pairs of eight laps. If `--no-memory` reproduces about 130 s and the saved memory gives 115 s, the era is the memory state, and the frozen-plan comparisons need their memory state fixed too.

### Memory test result: the memory is not the era (2026-11-26)

- Pursuit with saved memory: session 1, median 119.0 s, no spin. Pursuit with `--no-memory`: session 2, median 115.0 s, no spin. Fresh memory is not slower; the saved memory does not explain the 130 s laps.
- So the 130 s era is most likely the designed follower (the paired sessions since about 14:00 on 2026-11-25 are all designed-follower runs, at 126 to 131 s in the docs). The fast era (112 to 117 s) is pursuit.
- Consequence: the 700 to 950 m difference (fast laps 56 m/s average, the later laps 36 m/s) is most likely where the designed follower loses its time against pursuit. That turns the designed follower's weak section into a measured target: its speed over 700 to 950 m, against pursuit at the same distances.
- The paired memory test is kept (two pairs). It stays a useful control of the memory state, but the era question is answered: it is not memory.

### Time lost in 700 to 1000 m: designed era against pursuit era (2026-11-26)

- Time per 50 m segment (mean over laps, lap distance from the logged positions): pursuit era 592 laps, designed era 106 laps.
- Designed minus pursuit: +0.27 s (700 to 750 m), +0.61 (750 to 800), +0.71 (800 to 850), +0.54 (850 to 900), +0.43 (900 to 950), +0.29 (950 to 1000). Total about +2.9 s over the 300 m.
- The whole gap between the eras is about 15 s (about 115 against 130 s). This stretch accounts for about a fifth of it, and the 1.86 s needed for the 1:50.8 target is smaller than the loss here.
- Caveat: the eras differ in more than the follower (the designed era also has the paired-test settings), so this is where the two configurations differ most, not a measured effect of the follower alone. The clean test is a paired run of pursuit and designed with the same settings, timing these segments.

### Pursuit against designed, default settings, first pair (2026-11-26)

- Pursuit (session 1): full eight laps, median 120.9 s, no spin; 700 to 1000 m takes a median 6.45 s.
- Designed (session 2): **stopped moving at x 667, z 440 on lap 3** (the 640 m stall). Two laps were logged before it stopped (lap 2 at 115.7 s, reached before the stall; the stall itself is a driving failure, not infrastructure, and counts against the designed follower).
- Reading: with default settings the designed follower stalls at the 640 m point, the failure the earlier plan-based arms were built to avoid. It is not a pace comparison at all in this session. The earlier designed-era laps (130 s) came from the frozen-plan and braking-share settings, which keep the car out of that stall.
- The stall is now classified as a driving failure by the runner (outcome "stall"), so it is not counted as an infrastructure failure.

### Pursuit against designed, default settings, both pairs (2026-11-26): result

- Pursuit: 2 of 2 sessions completed eight laps, no spin, lap medians about 120.5 s (session 1 120.8, session 3 120.3 s).
- Designed: 0 of 2 sessions completed the lap. Both stopped moving at the 640 m point (x 663 to 667, z 440 to 444) on lap 3, after two logged laps (lap 1 189 to 201 s, which includes the start, and lap 2 at 116 to 118 s).
- Reading: with default settings the designed follower's stall at 640 m is repeatable (2 of 2, not a one-off), and pursuit does not have it. The designed era's 130 s laps came from the settings that avoid the stall (frozen plan, braking share). So the designed follower is not a pace comparison at default settings: it cannot finish the lap.
- The 700 to 1000 m time loss (+2.9 s) was measured on the designed laps that did avoid the stall; the default designed follower does not reach that section at all. Both facts go into the designed follower's next step: fix the 640 m stall first (the earlier heading-preview and brake-share tests reduced it, not removed it).

### The 640 m stall: mechanism and the first test (2026-11-26)

- Both default designed stalls (sessions 193437 and 201250) show the same sequence: steering at full lock (-1.0) from about 521.8 s, the heading error growing from -30 to -118 deg, the car 46 m off the line, speed falling from 46 to 9 m/s, front grip 0 to 0.3, sideslip swinging. The stall point is x 663, z 444.
- The gain table gives a limit: at 45 m/s the designed command reaches full lock at a heading error of about 26 deg (`a` = 0.13, steering gain 0.059 rad per command). Past that the steering cannot correct the error, and the car slides.
- The heading error grows because the designed follower measures the line's heading at the nearest waypoint, which lags at the bend entry. `--st-head-ahead 8` measures it 8 m ahead. Every paired test since the 14:00 era used that flag, and none of those sessions stalled at 640 m.
- Test running: designed with `--st-head-ahead 8` alone (no plan file, no brake share), two sessions, `paired_preview.jsonl`. If it completes the lap without the stall, the preview is the fix for the default designed follower, and the default should change.

### Heading preview test, session 1 (2026-11-26): the 640 m stall is gone

- Designed with `--st-head-ahead 8` (nothing else): it passed the 640 m point and completed six laps (lap times 193.5 s with the start, 123.6, 122.5, 137.8, 187.1, 140.5 s), then ran out of its session time (`--total` 1240 s) partway through lap 7. The record says "lap not completed (timeout)", which is the time budget, not a stall. No spin.
- So the preview fixes the early stall. What remains is slow laps (lap 5 at 187 s, lap 6 at 141 s), not a stop. The designed follower's pace is still the problem, and the time budget has to be larger for designed runs (its laps are longer than the 130 s that the budget assumes).
- Next: find where lap 5 (187 s) loses its time, using the same distance-aligned comparison as before, and set the session budget from the expected lap time.

### Heading preview, both sessions (2026-11-26): 640 m cleared twice, the failure moves to the bend

- Session 1 (saved memory): passed 640 m, six full laps, then the session time ran out on lap 7 (not a stall).
- Session 2 (`--no-memory`): passed 640 m, lap 2 completed (83.8 s, which is short: the lap ends at the bend), then **stopped moving at x -485, z 16 on lap 3**, the exit of the 2570 m bend. That is the bend's known failure area, not the 640 m point.
- Reading: with the preview, the designed follower clears the 640 m point in 2 of 2 sessions. Its failure then lands at the 2570 m bend exit in one of them. The preview is necessary for the 640 m point but not enough: the bend exit is the next limit.
- Next: the bend exit (x -485, z 16) is the place to check the designed follower's heading and steering at exit, using the same logs as the earlier bend work.

### The bend-exit stop (designed with preview, session 2, lap 3): the same spin as before (2026-11-26)

- Entry: 51 m/s at z -162 (the earlier spin laps were at 52 to 54 m/s at z -145). Braking starts at 351.65 s (brake 0.83), then yaw grows from 2.7 to 25 deg/s while front grip falls from 0.99 to 0.46 (352.6 s), with the heading error at 13 to 14 deg.
- Sideslip goes from 0 to -8 deg (353.5 to 354.2 s); steering swings from +0.5 to full counter-lock (-1.0) at 354.5 s; yaw reaches 90 deg/s; the car spins through about 180 deg and stops at x -484, z 16, facing back (heading error 158 deg), with the front and rear grip at 1.0 (no tyre load) and speed 0.
- Reading: the designed follower's failure at this bend is the failure already measured for the spin laps (fast entry, front grip collapse at turn-in, a late large counter-steer). The 640 m stall was a different failure (steering authority at the heading error), which the preview removes. So the preview moves the designed follower past one limit and into the bend's known one.
- Next test: the bend's entry speed for the designed follower with the preview against pursuit's entry speed at z -162, from the logs (no game run needed), to see whether pursuit's line enters the bend slower.

### Entry speed does not separate pursuit from designed (2026-11-26)

- Bend entry speed at z -160 (median over laps): pursuit era 50.8 m/s (315 laps), designed era 49.8 m/s (508 laps). The designed follower with the preview enters at 54.5 and 51.1 m/s (two laps).
- So the pace gap between the followers is not made at the bend entry. Pursuit's advantage lies elsewhere, consistent with the 700 to 1000 m result (about 2.9 s), and the designed follower's bend loss comes from how it leaves the entry (its turn-in), not from a faster or slower entry on average.
- This also means the entry-speed explanation of the spins is at most a risk factor; the same entry speed is used by both followers, and only the designed follower spins here.

### What pursuit does differently at 700 to 1000 m (2026-11-26)

- Pursuit: 56 m/s on average, steering centred (-0.01), line offset -0.9 m, front grip 0.95, throttle 93 per cent.
- Designed (all designed-era laps): 37 m/s, steering biased to -0.22, line offset -4.1 m, front grip 0.58, throttle 65 per cent, heading error -2 deg.
- So over this stretch the designed follower runs about 4 m off the line, with a steering bias, and lifts off the throttle. Pursuit holds the line within 1 m at full throttle.
- Mechanism candidate: the designed follower's lateral term is `b * lat`, with `b = w^2 L / v^2` falling with speed. At 37 to 56 m/s a 4 m offset gives a command of only 0.10 to 0.13, about the size of a 2 deg heading error. The correction for position is weak at speed, so the car drifts and the drift costs speed.
- Test to run: a lateral gain scale (`--st-lat-scale`, default 1.0 = no change), at 2 and 4, on the designed follower with the preview; success means the line offset in 700 to 1000 m falls below 1 m without the steering bias.

### Lateral-scale test, first attempt (2026-11-26): the preview did not clear 640 m this time

- Arm A (designed, preview 8, default lateral term): stopped moving at x 666, z 441 after one bend lap, which is the 640 m point. Earlier with the preview, 2 of 2 sessions had passed it (session 1 with saved memory and session 2 with no memory). So the preview clears the stall in 2 of 3 sessions, not reliably.
- Arm B (lateral scale 4): not run. The game was still open 90 s after arm A, so the runner refused to start (counted as an infrastructure failure, not a controller result, as designed). The pair was rerun in a fresh records file (`paired_lat2.jsonl`).
- Reading: the 640 m stall has an intermittent component the preview does not remove. Two sessions with the same settings went through, one stopped; that is the variation the preview test needs more sessions to measure.

### Lateral-scale test: the control stalls at 640 m again; a stalled session leaves the game open (2026-11-26)

- Preview record, all designed sessions with `--st-head-ahead 8`: passed 640 m in 2 of 4 (the other two stopped at x 663 to 666, z 441 to 444). So the preview does not reliably clear the 640 m stall; the earlier "cleared twice" was too strong.
- A stalled session left the game open (the lap check reported "could not leave the session"), and the next session was refused by the runner's "game still running" check. Fix: the runner now closes a still-open game with the recovery script before its next session (waits 30 s, recovers, waits 60 s more); the refused session is still counted as infrastructure.

### Lateral-scale test, first pair (2026-11-26): the scale moved the stall

- Arm A (preview 8, lateral term as before): stopped moving at x 634, z 444, before the bend (the 640 m stall again).
- Arm B (preview 8, lateral scale 4): passed that point and stopped at x -786, z 335, a different part of the lap, with no bend laps. Its line offset over 700 to 1000 m could not be measured (no complete lap).
- One session per arm, so this is an observation, not a result. It does show that changing the lateral term changes where the designed follower fails: the 640 m stall is not the only failure it has once the position correction is stronger. The second pair (sessions 3 and 4) is running in `paired_lat4.jsonl`.

- Second pair, session 1 and 3 (arm A, control): stalls at x 634, z 444 (640 m) in session 1, and at x -510, z -436 in session 3 (after three logged bend laps, so the lap reached the 2570 m bend region before stopping at a different place). Session 2 (arm B, lateral scale 4): no spin, stalled at x -786, z 335 in the first pair; this pair's arm B result is pending (session 4).
- So the designed follower with the preview stalls at several places around the lap, not only at 640 m: the failure location is spread, not fixed. This moves the designed follower's problem from "one stall point" to "unstable everywhere it is not steering conservatively", which is a stronger reason for the controller-level change than a single-point patch.

### Lateral scale 4: an oscillation, not a correction (2026-11-26)

- Both arm B sessions (lateral scale 4) stopped near x -773 to -786, z 335 to 344, with no bend lap; the session log for the second one shows why. Between x -500 and -650 at 47 to 52 m/s the steering swings -0.39, +0.46, -0.61 and then holds full lock (-1.0), with the heading error swinging about ±15 deg over about 1.5 s. The lateral error goes from +0.4 m to +5 m and then to -46 m as the car runs on with the steering held.
- Reading: a scale of 4 on the lateral term is over-gain. It produces a self-sustaining oscillation at speed and then the same saturation as the 640 m stall. So the lateral term at speed is not "too weak" in the simple sense: raising it destabilises the loop. The right fix is a gain schedule (lateral gain with speed and delay), not a larger constant.
- Summary of the second pair: arm A (control, preview 8) stopped at x 634 z 444 (640 m) and x -510 z -436 (after three bend laps); arm B (scale 4) stopped at x -786 z 335 and x -773 z 344 (oscillation then saturation). Neither arm completes a lap, so the 700–1000 m comparison cannot be made.

### Steering-to-yaw delay from the logs (2026-11-26)

- Cross-correlation of the steering command with the measured yaw rate (speed 30 to 60 m/s, 60 logs): the correlation peaks at a lag of 200 to 400 ms (0.667), against 0.62 at no lag and 0.57 at 800 ms. So the steering-to-yaw response carries a delay of about 0.3 s.
- Consequence: the designed law is tuned for a natural frequency of 1.2 rad/s, but with 0.3 s of delay its phase lag is about 0.36 rad (21 deg), and it rises steeply as the gain goes up. A lateral gain of 4 raises the effective frequency and pushes the loop into the oscillation seen in the logs. This is delay-limited stability, not a sign error.
- Candidate fixes: yaw-rate damping (the designed law has a `damp` term, off by default), and a predictor that acts on the state about 0.3 s ahead. The first is the cheaper test.

### Yaw damping 90 on the designed follower with the preview (2026-11-26): first pair

- Control (no damping): stopped at x 668, z 440 (640 m) after one bend lap.
- Damping 90: passed 640 m, logged five bend laps, then stopped at x -521, z -404 (near the x -510, z -436 stop of an earlier control session). No spin.
- One pair, so an observation: yaw damping clears the 640 m point in this sample, and the designed follower then stops later on the lap. It is the first setting that got past 640 m in a paired control, and the next failure is elsewhere. The second pair is running in `paired_damp.jsonl`.

### Yaw damping 90, full pair (2026-11-26): the 640 m stall is removed in 2 of 2, the next stop comes after five bend laps

- Control (no damping, preview 8): 2 of 2 stopped at the 640 m point (x 668, z 440 and x 640, z 443), after one and two bend laps.
- Damping 90 (preview 8): 2 of 2 passed 640 m and logged five bend laps each, then stopped at x -521, z -404 and at x 7, z -43. No spin in any of the four sessions.
- Exact one-sided p for 2 of 2 passing against 0 of 2 is 0.17. Too few sessions to call it, but the direction is clear and it is the first setting that cleared 640 m reliably in a paired control.
- Consequence: yaw damping is the first candidate for the designed follower's default with the preview. The next stop is later on the lap (x -521, z -404 and x 7, z -43 are two different places), so the damped follower still has a limit to find after the 640 m point.

### The two damped-session stops (2026-11-26): two different failures

- **Lap 1, x -577 to -521, z -466 to -404, 25 to 35 m/s:** the heading error holds at about -25 deg with the steering at full lock (-1.0) for over 1.5 s, and the lateral error grows from +0.2 to -14 m. The steering cannot close a 25 deg error at this speed: the same authority limit as the 640 m stall, now reached without a stall at 640 m.
- **Lap 5, x 0, z -1 (start-finish), 29 m/s:** the car is already sliding (sideslip -12 deg) when it reaches the line, the yaw swings to 50 to 70 deg/s, and the steering stays at -1.0 through the spin. The logs record kerb impacts at x -4, z -1.5 (the `Kerbs21` object) in other sessions too, so this spot is a recurring kerb and slide location, not a random one.
- Two failure modes, so the damped follower has at least two limits after the 640 m point: steering authority at high heading error, and a slide at the start-finish line. A fix for one will not remove the other, and each needs its own test.

### The start-finish slide is the bend mechanism again (2026-11-26)

- Approach (lap 5, damped session): full throttle on the straight to 57 m/s, hard braking at x -105 (brake 1.0), and the turn-in begins at x -52 while the car is still braking at 43 m/s (brake 0.8 to 0.9, steering 0.03 rising to 0.78 in about 0.9 s).
- In that second, front grip falls from 0.94 to 0.25 and the yaw rate jumps from 2 to 35 deg/s; sideslip grows from 0 to -6 deg; the steering then goes to full counter-lock, and the car spins at 28 m/s by x -5, z -5.
- So the start-finish slide is the braking-into-turn-in grip collapse measured at the 2570 m bend, at a different corner. It is a mechanism, not a kerb problem: the kerb impact is a consequence of the spin.
- Consequence for the designed follower: the braking point before a corner and the turn-in overlap (brake still 0.8 to 0.9 when the steering starts). A fix has to separate them: release the brake before the turn-in, or limit the steering rate while braking.

### Brake and turn-in overlap across all laps: a metric that does not discriminate (2026-11-26)

- Counting laps with any sample of brake above 0.3 and steering above 0.2 at 25 m/s or more flagged all 1354 laps, so the metric says nothing. It also counted any yaw of 120 deg/s or more anywhere on the lap as a spin (54 laps), so the spin label is not tied to the corner either.
- Next, to be useful: restrict both measures to a window around each turn-in (the lap's first brake-to-steer transition in each corner), measure the overlap time there, and compare spin with no spin in those windows only.

### Turn-in windows, first pass (2026-11-26): provisional, not validated

- Window: from the first sample at 25 m/s or more with brake above 0.3 and |steer| above 0.2, to 1.5 s later or until |steer| falls below 0.1. 11,248 windows over the logged laps (about 8 per lap).
- Spin label, now tied to the window: yaw rate of 120 deg/s or more inside it. Seven windows qualify, against 54 laps under the old whole-lap label. So most old "spins" were yaw events outside any corner, and the earlier counts overstated the bend problem as a per-corner event.
- Medians, spin (7) against no spin (11,241): entry speed 31.7 against 34.5 m/s; overlap 0.20 against 0.30 s; peak brake 0.39 against 0.64; minimum front grip 0.00 against 0.33; peak yaw 148 against 30 deg/s.
- Reading: the seven spin windows combine low braking with a complete front-grip loss, not heavy braking into turn-in. That contradicts the earlier "brake into turn-in" explanation for the bend, which came from a single lap. The sample is seven, the windows are not yet checked by hand, and no tests exist for the window code. Not a result yet.
- Next: hand-inspect the seven spin windows and a matched sample of clean windows; add synthetic tests for the window rule (a window opening, closing on the 1.5 s cap, and a spin on the boundary).

### Turn-in windows, corrected (2026-11-26): joint precursor, provisional

- Recount on deduplicated files (414 logs; the first pass had counted one session twice): 8,349 windows, 6 spins (yaw of 120 deg/s or more inside the window).
- Hand check of the spin windows: every one has full steering lock at or after the spin, so the spin label alone describes the aftermath. The precursor has to come from before the yaw peak.
- Precursor (measured before the yaw peak, not the spin itself): steering at 0.95 or more **and** front grip below 0.3. 115 windows contain it, with 4 spins (3.5%); the other 8,234 windows have 2 spins (0.02%). One-sided Fisher p about 5e-7. The thresholds (0.95, 0.3, the 5-sample cut before the peak) were chosen after looking, so this is a candidate rule, not a confirmed one.
- Grip below 0.3 alone is not the discriminator (20% of clean windows have it); steering saturation alone is not either (1.6% of clean windows; 4 of 6 spins).
- Lead time: the precursor appears 0.0 to 0.9 s before the spin peak (median about 0.4 s). Non-spin windows that reach the precursor have a similar median lead (0.35 s), so the lead time does not by itself separate them, and about 0.4 s is too short for most corrective action. A useful early warning needs a precursor that appears earlier.
- Not yet done: a synthetic test for the window rule, and a hand check of matched clean windows at the same speed and position.

### Hand check of spin windows against matched clean windows (2026-11-26)

- Five-ish spin windows and matched clean windows (same entry speed within 3 m/s) were read sample by sample before the yaw peak. Several spin windows already show full counter-lock and heading errors of -50 to -130 degrees when the window opens: they are late, not early.
- The matched clean windows look much the same: full steering, front grip at 0 to 0.3, sideslip 5 to 20 degrees, peak yaw 24 to 66 deg/s. They are near misses on the same path. The spin label is a threshold (120 deg/s) on a continuum, so a binary spin count discards most of the information.
- Consequence: the precursor (steering at 0.95 or more with grip below 0.3) describes a common unstable state, with spins as its tail. The useful measure is continuous: peak yaw rate, sideslip rate, and heading error growth inside the window, with the 120 deg/s label kept only as a tail marker.
- Not yet done: correlate those continuous measures with the precursor and with the lap-time loss in the same corners, which is what decides whether they matter for pace.

### Continuous measures against the precursor (2026-11-26)

- Windows with the precursor (292): peak yaw median 44 deg/s, 90th percentile 74, 99th percentile 152; peak sideslip median 8.4 degrees, 90th percentile 30.7. Six of them reach the 120 deg/s spin threshold.
- Windows without it (8,057): peak yaw median 30, 90th percentile 45, 99th 62; peak sideslip median 4.0, 90th 6.5. None reach 120 deg/s.
- Peak sideslip separates the two groups far better than peak yaw (90th percentile 31 against 6.5 degrees). It is the stronger candidate for a continuous precursor. Not yet tested as a predictor with lead time, nor against lap-time loss.

### Sideslip lead time (2026-11-26): short, and not much longer before spins

- Sideslip first reaches 15 degrees: median lead before the yaw peak 0.70 s for the four spin windows (10th percentile 0.00 s), and 0.34 s for 88 non-spin windows (10th percentile 0.00 s).
- The lead is about the same as the steering-and-grip precursor (about 0.4 s). Sideslip separates the groups in size (see previous entry), but not in time. A controller reacting at 0.3 to 0.4 s with a 0.3 s steering delay cannot prevent the peak with this signal alone.
- Caveat: four spin windows. The lead distribution needs more spins, or the provocative setting, before it is trusted.

### Do the precursors track lost lap time? (2026-11-26): yes, within each follower era, observationally

- Per lap (900 complete laps, 100 to 160 s): the count of precursor windows and the count of windows with sideslip of 15 degrees or more both correlate positively with lap time overall (+0.33 and +0.40). Turn-in window count alone correlates negatively (-0.46), which reflects the lap structure, not the driving: the count rises with the number of corners completed, so it is not a usable measure.
- Within the pursuit era (313 laps, median 116.2 s): precursor count +0.45, sideslip count +0.43 with lap time.
- Within the designed era (476 laps, median 130.1 s): precursor count +0.31, sideslip count +0.36.
- So the precursor and sideslip counts associate with slower laps inside each follower, not only between the two. Mean counts per lap are small (0.04 to 0.25), so each event is worth a fraction of a second at most, but they recur. Caveat: correlation, not cause. A slower lap may produce more of these events rather than the events producing the slowness. The test is a corner-level intervention (see the next entry).

### Corner-level intervention: design (2026-11-26)

- **Why this one.** A plan-file change at the 2570 m bend (entry plus or minus 5 m/s, mid-bend minus 4 m/s) has been run and has no measurable lap-time effect (0.19 s over four sessions). The precursor is a reaction to the slide, not a planned speed, so the intervention has to act on the slide itself.
- **Intervention (reactive, pursuit as the host, since it is the incumbent).** When peak-to-now sideslip exceeds 8 degrees and the brake is above 0.2, release the brake to zero for as long as the sideslip stays above 8 degrees, and keep the steering law unchanged. Off by default; a new option, `--slide-release DEG`.
- **Test.** Pursuit against pursuit with `--slide-release 8`, two pairs of eight laps, paired and logged to `paired_slide.jsonl`. Outcomes: lap time per corner window (time through each corner, from distance-aligned signal logs), spins and stalls, and the slide duration per window.
- **What would change the plan.** A lap-time gain of 0.1 s or more in the turn-in windows with no added spins: keep it and test it on the designed follower. No gain, or more spins: the sideslip signal is a symptom, and the next test is the steering-rate limit at turn-in. A loss of time in the windows: the brake release costs more than the slide it prevents.
- **Cost.** A few lines in the driver's brake logic (not yet read) and about 80 minutes of game time. Offline check first: replay the logged sideslip traces through the rule to count how often it would fire.

### Replay of the proposed brake-release rule over the logged laps (2026-11-26): too unspecific as written

- Rule replayed: sideslip above 8 degrees with brake above 0.2 at 20 m/s or more. It fires in 252 of 972 laps (26%) and in 1,174 of 1,021,100 samples (0.11%).
- Of 38 laps with a spin (yaw of 120 deg/s or more at speed), 19 contain at least one firing. This count is "anywhere in the lap", not "before the spin", so it is not a timing result.
- Reading: the rule fires in about 233 laps that do not spin, against about 19 that do. As written it would brake-release in many clean corners, and each release costs time that the replay cannot price.
- Next: restrict the rule to the turn-in windows (the same windows as the precursor analysis), require the firing to come before the yaw peak, and count the time that each release would cost in the clean laps where it fires.

### Restricted brake-release rule, replayed inside turn-in windows (2026-11-26)

- Rule: inside a turn-in window, before the yaw peak, sideslip above 8 degrees with brake above 0.2.
- Spin windows: 4 of 6 contain a firing. Clean windows: 166 of 8,343 (2.0%). Of the clean firings, the median time in release is 0.20 s and the median brake time in the window is 0.80 s.
- Reading: the rule is now specific (98% of clean windows do not fire) and still sensitive (4 of 6 spin windows). But the base rate of spin windows is about 0.07%, so a firing is a spin in about 2% of cases (4 of 170). Its value depends on the time cost of each release in the 166 clean windows, which the replay cannot price. The next step is the paired game test.

### Pursuit with slide release (2026-11-26): test running

- Arm A: pursuit (incumbent). Arm B: pursuit with `--slide-release 8` (brake released to zero while it is above 0.2 and the slide is above 8 degrees, after the ellipse cap). Two pairs of eight laps, logged to `paired_slide.jsonl`, option committed as `8450adf`.
- Decision rules (set before the run): a lap-time gain of 0.1 s or more in the turn-in windows with no added spins means keep it and test it on the designed follower; no gain or added spins means the sideslip signal is a symptom and the next test is a steering-rate limit at turn-in; a time loss means the release costs more than the slide it prevents.

### Pursuit slide release at 8 degrees: first full test (2026-11-26 to 27): inconclusive

- Session medians (eight laps each): baseline 120.04 and 120.20 s; slide release 118.30 and 121.43 s. No spin in any session (16 bend laps per arm).
- Mean difference (slide release minus baseline): -0.26 s. The pairs point in opposite directions (-1.74 s in pair 1, +1.23 s in pair 2).
- Session-to-session spread is about 1.3 s, so the standard error of the difference is about 1.3 s with two sessions per arm, and the 95 percent interval is roughly ±2.5 s. The test cannot distinguish a 0.1 s gain from no effect or a loss.
- Decision rule (set before the run): 0.1 s or more with no added spins means keep and test on the designed follower. This run does not meet it or fail it. Options: more pairs (about 80 minutes per two pairs for a standard error near 0.6 s), or measure the turn-in windows directly, the 0.1 s gain the rule targets, which the lap time averages over.

### Lap-time budget, first pass (2026-11-26): one reproducible section, the rest is noise

- Pursuit-era clean laps (282, 100 to 125 s, distance-aligned by integrated position in 50 m bins). A first version compared each bin's median against its single fastest execution and summed the gaps to 16.5 s. That is invalid: the minimum of hundreds of noisy samples picks outliers in every bin. Withdrawn.
- Corrected: the fastest decile (28 laps) against the rest, per 50 m bin, with a split-half check (fast set defined on one half of the sessions, tested on the other). Summed gaps across all bins: 3.6 s, an upper bound with noise in it.
- Reproducibility: only 1 of 98 bins has a gap above 0.15 s in both independent halves. That bin is 1100 to 1200 m (gap 0.47 overall, 0.47 and 0.35 in the two halves).
- 1100 to 1200 m: the fastest decile carries 38.5 m/s on average against 31.8 m/s for the rest. It uses less throttle (duty 0.18 against 0.24), more steering (0.31 against 0.23), more heading error (12.7 against 10.6 degrees) and more sideslip (-3.9 against -2.0). So the time is in a faster, more sliding line through this section, not in a braking or throttle difference.
- Consequence: with this log set the lap-time budget cannot be localised beyond this one section; the other bins are within session noise. A budget that finds the missing 1.86 s needs more clean laps per section, or the tests set up to measure sections directly.

### Section test at 1100 to 1200 m (2026-11-26): running

- Plans built from data, not from the designed follower's plan (that plan slows to about 17 m/s there, against the pursuit's 38 m/s, so it would make the baseline unfair): the fastest decile of pursuit-era clean laps, speed by 10 m bin (`plan_pursuit_fast.json`), and the same plus 4 m/s over 1100 to 1200 m (`plan_pursuit_fast_plus4.json`). Pursuit follows each plan (`--plan-file`, main chain).
- Arms: A, pursuit on the fastest-decile plan; B, the same plus 4 m/s over 1100 to 1200 m. Two pairs of eight laps, logged to `paired_section.jsonl`.
- Measure: time through 1100 to 1200 m per lap (sum of sample intervals in the distance window), spin or stall, and the lap time. Decision: a section gain of 0.1 s or more with no added stalls means the section responds to speed and the plus-4 line is worth extending; no gain means the section is limited by something other than entry speed.

### Section test, pair 1 (2026-11-26 to 27): provisional

- Arm A (fastest-decile plan): lap median 118.75 s, section (1100 to 1200 m) median 2.81 s, no spin. Arm B (+4 m/s over the section): lap median 118.33 s, section median 2.97 s, no spin.
- Section difference B minus A: +0.11 s (B slower through the section), but the lap is 0.4 s faster in B, so B recovers time elsewhere. Lap-to-lap spread in the section is 2.66 to 2.93 s, so this is within noise.
- Reading, provisional: raising the speed through the section did not make it faster; the lap gain in B lies outside the section, which argues the section is limited by something other than entry speed. Pair 2 is running.

### Section test, final (2026-11-26 to 27): no measurable effect

- Two pairs, eight laps each (16 laps per arm, no spin, no stall). Lap mean: A 118.49 s, B 118.52 s (difference +0.03 s). Section 1100 to 1200 m mean: A 2.879 s, B 2.835 s (difference -0.044 s; per-lap sd 0.17 s).
- Session-level lap differences (B minus A): -0.50 s and +0.56 s; they cancel. Approximate 95% interval for the section difference: about ±0.12 s.
- Reading: adding 4 m/s of target speed through the section does not make it faster, and the interval excludes a section gain above about 0.1 s. The section is not limited by entry speed. It is limited by how the car leaves the braking zone and reaches the turn-in at 1100 m, or by something else outside the speed plan. This matches the earlier turn-in finding: the time is in the line and the slide, not the target speed.

### The 1100 to 1200 m section: what the fastest laps do differently (2026-11-26 to 27)

- Path curvature from the logged positions, 1050 to 1250 m: the fastest decile arrives at the apex with more speed (32 to 36 m/s at 1150 to 1175 m, against 26 to 28 for the rest) and takes a flatter arc there (0.75 against 1.06 deg/m at 1175 m), with the same braking.
- At the apex (1140 to 1210 m), the fastest decile reverses steering more often (2.9 against 2.1 reversals per lap) and carries a larger mean heading error (15.8 against 13.8 deg), with the same steering variance and similar peak yaw (42 against 46 deg/s).
- Reading: the fastest laps do not rotate less or steer more calmly. They carry more speed into a flatter arc and correct more while doing it. The hypothesis that the slower laps over-rotate is not supported. The section's time is in apex speed and arc shape, which the plan test could not reach (adding target speed did nothing).
- Next: test the arc shape directly. The planner's line through the apex is the lever, since the fast laps' arc is flatter; whether the line can be made flatter at 1150 to 1200 m without losing the exit is the next experiment.

### Apex-shift test (2026-11-27): running

- Apex at about (-1000, -275), yaw +24.6 deg/s there, so a right-hand corner: the outside is physical left, and the shift is positive. Arm A: pursuit on the fastest-decile plan. Arm B: the same plus `--apex-shift 1.5` over 1150 to 1200 m (a guessed magnitude, inside the track width; the wall clamp applies). Two pairs of eight laps, logged to `paired_apex.jsonl`, option committed as `85f2aaf`.
- Decision rule (set before the run): the apex section (1150 to 1200 m) at least 0.1 s faster and the lap not slower, with no added stall: keep, and try 2.5 m. Section no faster: the arc shape is not the limit. Section slower or a stall: reject, the wider arc costs the exit.

### Apex-shift test, pair 1 (2026-11-27): one stall in the apex-shift arm

- Arm A (control, fastest-decile plan): eight laps, lap mean 119.05 s, apex (1150 to 1200 m) mean 1.574 s, no spin.
- Arm B (1.5 m outward shift): stopped moving at x -1058, z -314 in lap 5, about 60 m before the apex and near the pit-exit area of the earlier stalls. Four laps before the stall: apex mean 1.502 s, lap mean 120.56 s. This is a driving stop, not an infrastructure failure, and it is counted as one. Whether the shift caused it is not known from one session.
- Reading so far: the shifted arm's apex section is faster in the four laps it completed (-0.07 s), inside noise, and it stopped once. Pair 2 is running.

### Apex-shift test, final (2026-11-27): rejected by its rule

- Apex section (1150 to 1200 m), session means: control 1.574 and 1.514 s; shifted 1.502 and 1.448 s. The shift is faster in both pairs (difference -0.078 s overall, per-lap sd about 0.10 s).
- Lap mean: control 118.42 s (16 laps), shifted 118.54 s (12 laps, the stalled session contributes only its four laps before the stop). The lap is slower by 0.12 s, but the stopped session's laps are a biased subset, so this difference is not reliable on its own.
- Stall: one in arm B (x -1058, z -314, about 60 m before the apex, lap 5 of session 2). None in arm A.
- Decision rule (set before the run): keep only if the apex is at least 0.1 s faster with the lap not slower and no added stall. Here the apex is 0.08 s faster (under the threshold), the lap is not clearly slower, and one stall was added. Rejected as configured: 1.5 m outward is not kept. The consistent sign suggests a smaller shift, 0.75 m, could be tested later if the stall is shown to be unrelated to the shift.

### Correction to the apex-shift stall (2026-11-27)

- The earlier entry said the shifted arm stopped "about 60 m before the apex". That was wrong. In lap 5 of the stalled session the car passed through the shifted window (1150 to 1200 m, entering at t 645.25 s) and stopped at 1263 m, about 60 m after the window ends, on the exit of the apex.
- So the shift was applied when the stall happened, and the stall is on the exit, not the entry. The shift could still have affected the exit (a wider arc leaves the car further out), but one session cannot show it. The control had no stall at this place in its eight laps (pair 1 and pair 2 control: no stall).
- Consequence for the rule: the stall is a driving failure on the exit, plausibly linked to the shift; this supports rejecting the 1.5 m shift as configured, and the 0.75 m test would need the exit (1200 to 1270 m) watched as well as the apex.

### Exit speed after the apex, 1200 to 1260 m (2026-11-27)

- Control (16 laps): mean 34.54 m/s, sd 1.24. Shifted (12 laps, including the stalled session's laps): mean 33.37 m/s, sd 3.54.
- The shifted arm exits about 1.2 m/s slower and much more variably. That fits the apex gain (about 0.08 s) being paid back on the exit, consistent with the stall. The two effects go in opposite directions, so a wider arc trades apex speed for exit speed here.
- Next (cheap, offline): the exit trade-off decides whether any arc shift helps; a shift that keeps the exit (for example one that eases back to zero by 1200 m) is the only version worth a game test.

### Tapered apex shift (2026-11-27): test planned

- Shift 0.75 m (smaller, to limit the exit cost) over 1150 to 1200 m, easing back to zero over 40 m (to 1240 m), so the exit is not shifted. Control: the same fastest-decile plan with no shift. Two pairs, logged to `paired_taper.jsonl`.
- Decision rule (set before the run): keep only if the apex (1150 to 1200 m) is at least 0.05 s faster in both pairs, the exit speed (1200 to 1260 m) is within 0.3 m/s of the control, and there is no added stall.

### Tapered apex shift, pair 1 (2026-11-27): interim

- Control: apex 1.572 s, lap 119.08 s, exit 34.06 m/s. Tapered 0.75 m shift: apex 1.494 s (-0.078 s), lap 118.54 s (-0.54 s), exit 33.68 m/s (-0.38 m/s). No spin in either session.
- Against the rule: the apex condition is met in pair 1; the exit is 0.08 m/s outside the 0.3 m/s limit; no stall. The lap difference is one session and the session spread is about 0.5 s, so it is not a verdict. Pair 2 decides.

### Tapered apex shift, final (2026-11-27): not kept

- Apex (1150 to 1200 m), B minus A: -0.036 s overall, with pair 1 at -0.079 s and pair 2 at +0.007 s. The rule needs at least 0.05 s in both pairs: not met.
- Exit (1200 to 1260 m), B minus A: +0.02 m/s overall, but -0.38 and +0.43 m/s between the pairs. Not stable.
- Lap, B minus A: -0.41 s overall (sessions 118.54 and 118.44 s against 119.08 and 118.72 s). The session-to-session spread is about 0.5 s, so this is not a verdict. It is the only signal, and it would need about 8 sessions per arm to test.
- Result: the apex gain did not hold in pair 2, so the taper is not kept on the apex criterion. The lap difference is an open question, not a finding. No spins or stalls in either arm.

### Throttle application, lap-wide (2026-11-27): not a broad source

- Pursuit-era clean laps, fastest decile against the rest, throttle duty per 50 m bin, split-half reproducibility as in the lap-time budget: 98 bins tested. Fast laps use more throttle by more than 0.1 in both halves at one bin only (1050 m, +0.19 overall, +0.26 and +0.11 in the halves). No bin shows the fast laps off throttle more in both halves.
- So coasting and delayed throttle are not a broad source of the fastest laps' advantage. The one reproducible throttle difference is at 1050 m, just before the apex section (1100 to 1200 m) already found: the fastest laps carry more speed and throttle into that section. Consistent with the apex finding, not a separate lever.
- Candidate list after this step, all from the mission's list: gear and shift timing (not yet checked), braking onset in the 1000 to 1100 m approach (the apex's entry, partly checked), and the line through the apex (the arc test failed). Gear and shift timing is next (cheap, from the logs).

### Gear and shift timing (2026-11-27): not measurable from the logged gear field

- Pursuit-era clean laps: the logged `gear` changes about 87 times per lap; with a 0.5 s debounce it still changes about 36 times, and about 22 of those are upshifts per lap. A car with six gears makes about five upshifts per lap. So the logged gear field is not the gear the car is in, and the shift-timing comparison built on it (rpm and speed at upshift: 5942 against 5926 rpm, 50.2 against 50.1 m/s) is invalid, not a null result.
- What is needed: the driver's own shift events (its `shift(True)` and `shift(False)` calls, with time, speed, rpm and lap distance) written to the signal log, so shift timing comes from commands, not from the game's gear reading. That is a small driver change, to be made before any shift-timing claim.
- Status: gear and shift timing is blocked on the measurement, not on the car. Recorded as a blocker.

### Correction and a lead: the driver shifts gear about 65 times per lap (2026-11-27)

- My earlier entry (fd0369e) called the logged gear field noise. That was wrong. The field is the real gearbox: each shift passes through neutral (gear 0), so every commanded shift appears as two changes.
- Commanded shifts (the new `shifts_*.csv`, one pursuit session, eight laps): 523, about 65 per lap, 264 up and 259 down. The game field shows 931 changes, consistent with two per shift.
- The driver hunts. Example, 25 to 31 s into the session at 25 to 40 m/s: 4 to neutral to 3, then 3 to neutral to 2, then 2 to neutral to 3, within about 6 s.
- Time in neutral above 5 m/s: 4.5 to 6.6 s per lap (mean 5.3 s), about 4% of a 120 s lap. A normal lap needs about five shifts, perhaps 0.7 s of neutral. So the excess is a few seconds per lap, which is the same order as the 1.86 s target. This is the largest lever found so far, and it is measured, not inferred.
- Caveat, to be tested: some neutral time is unavoidable at each real shift, and the drive loss during neutral is assumed, not measured. The next step is to find the cause in the gear-selection code and test a fix in a paired run.

### Gear-cooldown test (2026-11-27): running

- Arm A: pursuit, default (0.35 s cooldown). Arm B: pursuit with `--gear-cooldown 1.5`. Two pairs of eight laps, logged to `paired_gear.jsonl`, option committed as `bc43588`.
- Measures: commanded shifts per lap (from `shifts_*.csv`), time in neutral above 5 m/s per lap, and lap time.
- Decision rule (set before the run): keep the longer cooldown if neutral time per lap falls by at least 2 s and the lap is no more than 0.1 s slower; reject if the lap is slower by more than 0.1 s or a stall is added; otherwise inconclusive.

### Shift-logging pair: an empty-output infrastructure failure (2026-11-27)

- Arm B, session 2: 82 s, check output 0 bytes, no signal log. Counted as infrastructure (not a controller result). Arm A, session 1: completed, 1165 s, eight laps, no spin.
- Cause not established. The check printed nothing, which suggests it exited before its first line. The runner's recovery step (close a game left open, then revert) ran in the same 60 s window before the session. That is the likely link, not a verified one. To check: re-run the failing sequence with the recovery step logged, or check whether the lap check exits when the game is closed by the recovery.

### Gear-cooldown result, then the mechanism (2026-11-27)

- Cooldown 1.5 s against the default 0.35 s, one pair: neutral 4.89 against 5.16 s per lap (-0.27 s), shifts 59.6 against 63.9 per lap, lap 119.87 against 120.80 s (noise). The rule needed at least 2 s of neutral: not met. A longer cooldown does not remove the hunting.
- Reading: the shifts continue at about one every two seconds with either cooldown, so the gear choice itself flips. The down-shift margin is already 1.15 (`--gear-down-hyst`), but the up-shift margin is only 1.04 (`--gear-up-hyst`, now an option, default unchanged). After a downshift the upshift test passes at once, so the car climbs back: 4 to 3 to 2 to 3.
- Test next: `--gear-up-hyst 1.2` against the default, same rule (at least 2 s of neutral per lap, lap not slower by more than 0.1 s).

### Gear hunting: three hypotheses, two rejected (2026-11-27)

- Upshift margin 1.2 (one pair, one session per arm): neutral -0.25 s per lap, shifts -2 per lap, lap -0.88 s (session noise is about 0.5 s). Rule needed -2 s of neutral: not met; rejected.
- Cooldown 1.5 s: rejected (-0.27 s neutral).
- Throttle-duty crossings (the speed scale of the gear choice flips at duty 0.5): shifts fall within 0.3 s of a crossing in 11% of cases, against a base rate of 16%. Not the cause; rejected.
- Remaining: the gear choice itself (the thrust comparison between gears 2, 3 and 4 at 25 to 40 m/s), or the rpm model's mismatch with the real rpm after a shift. Cost per shift is small (5.3 s of neutral over about 65 shifts is about 0.08 s each), so the loss is the number of shifts, not any one of them.
- Next: ablate the model-based gear choice (`--live-off gear_opt`, the old rpm-threshold rule) against the default. If the rpm rule shifts far less and is not slower, the model is the cause.

### Gear-model ablation, pair 1 (2026-11-27): the rpm rule cuts the neutral time, lap at the limit

- Model-based gear choice (default): neutral 5.59 s per lap, 66.1 shifts per lap, lap 121.09 s. Rpm-threshold rule (`--live-off gear_opt`): neutral 3.52 s, 44.8 shifts, lap 121.19 s.
- Difference: neutral -2.07 s per lap (meets the 2 s rule), shifts -21 per lap, lap +0.10 s (exactly at the limit of the rule, and one session each, with session noise of about 0.5 s).
- Not decided. Pair 2 replicates it before any keep decision. The shift count falls substantially in one pair, so the model's hunting is the lead, but whether the rpm rule loses time elsewhere (for example at gear changes near the apex) is the question the lap time has to answer.

### Gear-model ablation, both pairs (2026-11-27): provisional candidate, not yet a keep

- Model-based gear choice (A, two sessions): neutral 5.45 s per lap, 65.1 shifts, lap 121.38 s.
- Rpm-threshold rule (`--live-off gear_opt`, B, two sessions): neutral 3.66 s, 44.9 shifts, lap 120.78 s.
- Difference B minus A: neutral -1.79 s per lap (the rule asked for 2 s: short by 0.2 s; the two pairs were -2.07 and -1.51 s), shifts -20 per lap, lap -0.61 s (pair 1 +0.10, pair 2 -1.32; session noise about 0.5 s).
- Reading: the rpm rule removes most of the shifting and does not cost lap time in two pairs. The neutral criterion is marginal and the lap difference is inside noise for one pair, so this is a provisional candidate, not a verdict. Next: four more sessions (two pairs) on the same arms, with the rule as it stands, to confirm the lap time before the rpm rule becomes a default.

### Gear-model ablation, final (2026-11-27): candidate, default unchanged

- Four pairs, eight laps each (about 4 sessions per arm). Model-based gear choice (A): neutral 5.38 s per lap, 64.4 shifts, lap 121.19 s. Rpm-threshold rule (`--live-off gear_opt`, B): neutral 3.63 s, 44.4 shifts, lap 120.09 s.
- Per-pair lap difference B minus A: +0.10, -1.32, -1.12, -2.07 s (mean -1.10 s). Three of four pairs favour the rpm rule. No stall, no spin in any session.
- Against the rule (set before the first pair): the neutral criterion (at least 2 s less) is missed by 0.25 s (-1.75 s). The lap criterion (not slower by more than 0.1 s) is met with margin. Verdict: a strong lap-time candidate with a marginal neutral criterion, not a formal keep.
- The baseline stays on the model-based gear choice until a pre-registered confirmation, because the baseline is the fixed comparison for the rest of the work. Next: test the rpm rule on the designed follower (the other competitor), and, if it holds, add a `--gear-rule rpm` default option for pursuit only after a pre-registered pair.

### Rpm gear rule on the designed follower (2026-11-27): running

- Arm A: designed with the heading preview (`--st-head-ahead 8`), model-based gear choice. Arm B: the same with `--live-off gear_opt`. One pair first, logged to `paired_designed_gear.jsonl`. Both arms are subject to the designed follower's 640 m stall, so the test reads neutral time and shift counts first; lap time only where both arms complete laps.

- Designed control (A, session 1): stalled at x 670, z 438 (the 640 m point again) after two partial laps. Its shift count is far higher than pursuit's (about 280 commanded shifts over its two partial laps against about 65 per full lap for pursuit), and its neutral time per lap is about 5.0 s. So the designed follower hunts gears much more, at the same stall point. Arm B (rpm rule) is next; lap time cannot be compared because the control completes no lap.

### Rpm rule on the designed follower, pair 1 (2026-11-27): shifting falls about tenfold; both arms still stall at 640 m

- Model-based gear choice (A): stalled at x 670, z 438; 564 commanded shifts and 10 s of neutral over 225 s of driving (about 2.5 shifts per second, 4.4 per cent of driving time in neutral). Rpm rule (B): stalled at x 665, z 444; 54 commanded shifts over its run (no full lap logged).
- So on the designed follower the model's hunting is much larger than on pursuit (about ten times the shift rate), and the rpm rule removes nearly all of it. Lap time cannot be compared: neither arm completes a lap, because the 640 m stall comes first. The gear rule is therefore a separate, confirmed effect on shifting; its lap-time effect on the designed follower is untested until the stall is fixed.

### Shift-loss measurement, corrected (2026-11-27)

- Bug found and fixed in analysis: a neutral episode of one sample has zero duration when measured as last minus first timestamp, so per-shift neutral read as 0.00 s. A single neutral sample is about 0.11 s (the log rate), so the per-command neutral time is about 0.1 s, consistent with 5.3 s per lap over about 65 shifts.
- Command to neutral: about 0.04 s. Neutral sample to the new gear: about 0.1 s. A raw-row check (session 092954, command at 139.37 s) shows gear 4, then 0 at 139.41 s for one sample, then gear 5 at 139.53 s, with rpm falling from 7109 to 6428 across the shift.
- Command outcomes: 77% of 1,839 commands are followed by an arrival in a new gear within 1.5 s (median lag 0.16 s). The other 23% produce no change within 1.5 s: failed, ignored or overlapped. Not yet separated by cause.
- Drive lost during a neutral sample: acceleration in the neutral sample is 2.6 m/s² lower than in the three samples before it (median, 429 samples). So each neutral sample costs about 0.29 m/s of speed.
- Estimated lap cost (model, not measured): a speed loss of about 0.3 m/s carried over a 400 m straight at 40 m/s costs about 0.07 s, since time lost is about d times delta-v over v squared. If the excess shifts (about 60 per lap) fall on straights and the speed loss is not recovered, the lap cost is roughly 2 to 4 s. Events during braking or cornering cost less. The rpm rule's measured 1.1 s is within this range. This is an estimate, and it needs a direct test (see next entry).

### What the non-arriving and repeated shift commands are (2026-11-27)

- The 23% of commands with no arrival within 1.5 s: 21% are part of a reversal (the opposite command within 0.6 s before or after: 197 before and 195 after, overlapping), 0.8% are a repeated same-direction command within 0.6 s, and 0.8% have no command nearby. So most failed commands are cancelled reversals, not failed engagements.
- Where the reversals happen (216 pairs in five sessions): 89% at partial throttle or coasting, 11% at full throttle, none in the braking-flagged samples. That is the model-based path's territory.
- The cooldown session (1.5 s): reversals within 0.6 s fell from 6 (control) to 0, and within 1.5 s from 25 to 10. But its shift count barely changed (477 against 511 commands in the same time), so reversals are not most of the shifting.
- The dominant pattern is same-direction bursts: of 564 commands in the sample session, 212 are pairs of same-direction shifts within 1.5 s (typically two downshifts 0.4 to 1.0 s apart), 90 are single shifts, and 13 are bursts of three or more. The commanded gears are not visible in the command log, so I cannot yet say whether these downshifts are legitimate braking downshifts or spurious ones.
- Also: commands arrive 0.35 s apart in the cooldown session, below its 1.5 s cooldown, so a second caller of the shift function (the rpm fallback path) is active. Not yet identified.
- Next: log the gear before and after each command, to separate legitimate downshift cascades from repeats, and identify the second caller.

### The second shift caller and how the two paths divide the work (2026-11-27)

- The driver calls the shift function from two paths. The model path (`best_gear`, cooldown `--gear-cooldown`) runs only when the car is not braking (brake below 0.05), not hard accelerating (|accel| below 8 m/s^2), and on the main chain. Otherwise the rpm-threshold fallback runs, with its own 0.35 s debounce that the cooldown option does not change. Two further call sites run only in spin recovery.
- Evidence (cooldown session, 1.5 s model cooldown): of 173 commands made while braking, 31% come within 0.5 s of the previous command (median gap 0.88 s). Of 304 commands made when not braking, 2% do (median gap 2.36 s). So the close-spaced shifts are the fallback's braking shifts, not the model's.
- Reading: the model's flip-flops (reversals) sit in partial throttle and coasting (89%), where it runs; the braking downshifts come from the fallback. The rpm rule is good at braking, and the model is the problem in coasting. That points to a hybrid: model-free rpm thresholds in coasting and partial throttle, the braking logic as it is, and the thrust model only where it has shown no flips. Nothing is yet tested.
- Next test: model-path disabled in partial throttle and coasting only (the rpm rule there, braking unchanged), against the current model. Decision rule to be set before the run.

### Hybrid gear test (2026-11-27): running, rule set before the run

- Arm A: pursuit, the model-based gear choice everywhere (default). Arm B: the same with `--gear-model-duty 0.9`, so the model chooses only at full-throttle-ish duty and the rpm rule decides in coasting and partial throttle; braking is unchanged. Two pairs, logged to `paired_hybrid.jsonl`.
- Measures: commanded reversal pairs (within 0.6 s), commanded shifts and neutral time per lap, lap time.
- Decision rule (set before the run): keep the hybrid if reversal pairs fall by at least half, neutral time does not rise, and the lap is no more than 0.1 s slower on average. Reject if the lap is more than 0.1 s slower on average or a stall is added.

### Hybrid gear test, pair 1 (2026-11-27): no reduction

- Model everywhere (A): neutral 5.06 s per lap, 62.1 commanded shifts per lap, reversals 0.38 per lap, lap 121.30 s. Hybrid (`--gear-model-duty 0.9`, B): neutral 5.26 s, 62.1 shifts, reversals 0.62 per lap, lap 121.28 s.
- Against the rule: reversals did not fall (they rose), so the hybrid misses its first criterion. Shifting and neutral time are unchanged, so the coasting shifts do not come from the model path at duty below 0.9 in the way I assumed. Hypothesis rejected for now; the 89% of reversals in partial throttle and coasting need another explanation. Pair 2 runs to completion as the rule set, and the verdict follows it.

### Hybrid gear test, final (2026-11-27): rejected by its rule

- Two pairs, four sessions, no spin or stall. Model everywhere (A): neutral 5.20 s per lap, 62.8 shifts, reversals 0.62 per lap, lap 121.36 s. Hybrid (B, `--gear-model-duty 0.9`): neutral 5.13 s, 61.6 shifts, reversals 1.00 per lap, lap 121.40 s.
- Against the rule: reversals rose, so the rule's criterion (a fall of at least half) is not met; rejected. Shifting and neutral time barely moved, and the lap is unchanged.
- Reading: restricting the model to high throttle does not remove the shifting. So the coasting-reversal hypothesis from the earlier composition analysis is not supported by this test; the reversals are not caused by the model's choice at low duty alone. The rpm rule's advantage (pursuit candidate) therefore does not come from this mechanism, and the model's shifting needs a different explanation (for example its rpm prediction after a shift, which the mission lists).

### Gear model root cause: ratios verified, torque shape suspect (2026-11-27)

- Ratios: the model's gear ratios are proportional to the logged rpm per speed in every gear. Observed over model ratio is 28.6 to 28.9 for gears 2 to 6 (within about 1 per cent); gear 1 is 29.6 (about 3 per cent off, plausibly launch slip). So the RPM prediction after a shift is not mis-scaled. This rejects the wrong-ratio explanation.
- Torque shape: a fit of measured full-throttle acceleration to the model's torque times ratio, minus a drag term (9,396 samples, two sessions) explains only about a quarter of the variance (r squared 0.26). The residuals follow a systematic pattern by rpm: about -4.2 m/s^2 at 3000 to 3500 rpm, -2.5 at 3500 to 4000, -1.9 at 4000 to 4500, -0.6 to -0.8 at 4500 to 5500, then +0.1 to +0.6 at 5500 to 6500. So the model's torque is too high at low rpm relative to the rest of the curve.
- Caveats: the speed resolution (0.1 m/s over 0.1 s) makes single-sample acceleration noisy; the drag term is crude; the residual pattern across bins is the evidence, not the fit quality. Hypothesis, not yet a finding.
- Next (offline, cheap): replay the logged states through the gear choice with a rpm-corrected torque curve, count the disagreements and the reversal rate against the logged driver, and compare with the original curve. If the correction removes the low-rpm flips in replay, it is the root cause candidate for the in-game hunting.

### Offline replay of the gear choice: the torque-shape hypothesis is refuted (2026-11-27)

- Replay of 9,279 logged states (full throttle, above 20 m/s, two sessions) through `best_gear` with the original torque curve, and with the torque below 4,500 rpm scaled by 0.9 and by 0.8: all three recommend a gear change in exactly 806 states (8.69 per cent). The scaling changes no recommendation.
- Reading: the candidate gears are all scaled alike, so the ranking changes only where the rpm of a candidate crosses 4,500. The low-rpm torque error measured in the acceleration residuals does not decide the gear choice. The torque-shape explanation for the hunting is rejected.
- Also in the replay: the model recommends a change in 8.7 per cent of full-throttle states, where the driver keeps its gear. The disagreement with the driver is a separate question (the driver's fallback and its timing), not the cause of the flips.
- Next candidate: the hysteresis and cap settings, replayed over the logged rpm sequence, counting recommended-change events over time (not per state), so that flips are counted as they would be in the car.

### Hysteresis and cap replay, and the rpm rule's band (2026-11-27)

- Replay over the logged rpm sequences (two sessions, 3 minutes, the model path off the brakes, 0.35 s gap between changes): the model at its current settings (up 1.04, down 1.15, cap 0.95) recommends 26.1 changes per minute, with 58 reversals within 1.5 s. Cap 0.90 raises it to 43 per minute. Wider hysteresis (1.10/1.25, 1.20/1.30) lowers it only to 24 to 25 per minute, with 29 to 33 reversals.
- The rpm rule (upshift at 6,800 rpm, downshift at 2,800 rpm) in the same replay: 17.3 changes per minute, with no reversals within 1.5 s. Its band is wide (a 2.4 times rpm spread), so small speed changes do not move the gear.
- Reading: the model's thrust-ratio hysteresis (1.04 to 1.30) is a narrow band in thrust, and on this car's flat torque curve the thrust of neighbouring gears is nearly equal, so the best gear keeps flipping with small speed changes and widening the ratio barely helps. The rpm band does the job the thrust margin cannot. The root cause is the objective: it has no shift cost and no band, so it rewards every small change. Caveat: the replay counts recommendations on logged states, not real shifts; the in-game rpm rule result (about 1.1 s) is the performance evidence.
- Next: a band-limited thrust optimiser (change gear only when the best gear's rpm lies outside a wide band, with the thrust choice inside it), replayed, then a paired test.

### Band-limited thrust optimiser, replay (2026-11-27)

- Same logged sequences: the thrust choice is used only when the current rpm lies outside a band (2,800 to 6,800 rpm), and inside the band the gear is held. Results: 13.5 changes per minute (2,800 to 6,800), 19.4 (3,200 to 6,600), 21.3 (3,500 to 6,300), each with no reversals within 1.5 s.
- Against the other candidates in the same replay: the model at its settings 26.1 changes per minute with 58 reversals; the rpm rule 17.3 with none. So the band-limited thrust choice asks for the fewest changes with no flips, and it keeps the thrust reasoning inside the band.
- Caveat: a replay counts recommendations on logged states, not real shifts, and it cannot price lap time. Next: implement the band as `--gear-band LO HI` (default off), then a paired test against the default and the rpm rule.

### Band-limited optimiser, in-car test (2026-11-27): running, rule set before the run

- Arm A: pursuit, the model everywhere (default). Arm B: pursuit with `--gear-band 2800 6800`. Two pairs of eight laps, logged to `paired_band.jsonl`.
- Measures: lap time (median per session, mean per arm), commanded shifts and reversals per lap, neutral time per lap, stalls.
- Decision rule (set before the run): keep the band-limited optimiser as a candidate if its mean lap is at least 0.5 s faster than the model's over the two pairs, with no added stall. Reject if its lap is slower by more than 0.1 s or a stall is added. Otherwise inconclusive, and the rpm rule remains the candidate to beat.

### Band-limited optimiser, pair 1 (2026-11-27): interim, promising

- Model (A, session 1): neutral 5.13 s per lap, 61.6 shifts, reversals 1.12 per lap, lap 120.62 s, no spin. Band 2,800 to 6,800 rpm (B, session 2): neutral 4.22 s, 51.6 shifts, reversals 0.00, lap 120.35 s, no spin.
- Against the rule: the lap is 0.27 s faster in this one session (the rule asks for 0.5 s over two pairs; session noise is about 0.5 s). Shifts and neutral time fall as the replay predicted, and reversals vanish. Pair 2 decides.

### Band-limited optimiser, final (2026-11-27): shifting falls, lap time does not

- Two pairs, four sessions, no spin or stall. Model (A): neutral 5.31 s per lap, 63.6 shifts, reversals 1.25 per lap, lap 121.02 s. Band 2,800 to 6,800 rpm (B): neutral 4.42 s, 53.1 shifts, reversals 0.00, lap 120.95 s.
- Per-pair lap difference B minus A: -0.27 and +0.12 s; mean -0.07 s. The rule needed at least 0.5 s faster: not met, rejected as a lap-time candidate.
- What is established: the band removes the reversals completely, cuts shifting by about 17 per cent and neutral time by 0.9 s per lap, with no stall.
- What this changes: the 0.9 s of neutral reduction bought essentially no lap time. So the cost of neutral time is much smaller than the estimate of 2 to 4 s per lap in the shift-loss entry (which assumed the speed lost on straights is never recovered). The rpm rule's lap gain (-1.10 s over four pairs, three of four favouring it) is therefore not explained by shifting in any simple way, and it needs its own explanation. Next: check whether the rpm rule's gain is real and where in the lap it appears (distance-aligned), before choosing a gear controller.

### Where the rpm rule's gain appears (distance-aligned, 2026-11-27)

- Pooled over the four gear-ablation pairs (32 laps per arm; rpm rule B minus model A), per 100 m section, keeping sections with a difference of at least 0.08 s: the rpm rule is faster at 2500 to 2600 m (-0.09 s), 2600 to 2700 (-0.15), 2700 to 2800 (-0.21), plus smaller gains at 1100 to 1200, 1400 to 1500, 2000 to 2100, 3800 to 3900 (-0.17) and 4400 to 4500 (-0.12). It is slower at 600 to 700 m (+0.21 s), close to the old 640 m stall.
- The bend section (2500 to 2800 m) carries about -0.45 s of the gain in these pooled data, and the 600 to 700 m section gives back +0.21 s. The sections differ by about 0.1 s of noise each, so the pattern is a lead to test, not a finding.
- Reading: the rpm rule's advantage is concentrated where the car leaves the bend (the 2570 m area) and at the 640 m point. Those are the two places where gear choice matters most for exit speed. The next test is in those two sections only: fix the rpm rule and the model on the bend exit, and measure that section over more sessions.

### Bend-exit confirmation (2026-11-27): running, rule set before the run

- Arm A: pursuit, model (default). Arm B: pursuit with `--live-off gear_opt` (rpm rule). Two pairs of eight laps, logged to `paired_exit.jsonl`.
- Primary measure: time from 2500 to 2800 m per lap (distance-aligned, 100 m sections summed). Secondary: time from 600 to 700 m, and the whole-lap time.
- Decision rule (set before the run): keep the rpm rule's bend-exit advantage as confirmed if the 2500 to 2800 m time is at least 0.2 s less for B than A (mean over the eight-lap sessions), and the 600 to 700 m time is not more than 0.1 s more for B. Reject if the bend-exit advantage is below 0.1 s. Otherwise inconclusive.

### Bend-exit confirmation, pair 1 (2026-11-27): interim

- Model (A, session 1): lap 120.51 s, 2500 to 2800 m 10.55 s, 600 to 700 m 2.11 s. rpm rule (B, session 2): lap 121.80 s, 2500 to 2800 m 9.99 s, 600 to 700 m 2.07 s.
- B minus A: bend exit -0.57 s (meets the primary criterion of at least 0.2 s, one session), 600 to 700 m -0.03 s (within the check), whole lap +1.29 s (secondary, and a warning: the bend-exit gain in this session is paid back elsewhere in the lap).
- Pair 2 decides. If the bend-exit gain holds but the whole lap stays slower, the rpm rule trades bend-exit time for time elsewhere, and the rule's verdict must say so rather than adopt it on the bend section alone.

### Bend-exit confirmation, final (2026-11-27): rejected by its rule

- Two pairs, four sessions, no spin or stall. Model (A): lap 120.48 s, 2500 to 2800 m 10.19 s, 600 to 700 m 2.21 s. rpm rule (B): lap 121.30 s, 2500 to 2800 m 10.02 s, 600 to 700 m 2.08 s.
- B minus A: bend exit -0.18 s (the rule needed at least -0.2 s: not met); 600 to 700 m -0.13 s; whole lap +0.81 s (slower). Session-level bend-exit times: model 10.55 and 9.83 s; rpm rule 9.99 and 10.05 s, so the pair-1 gain was reversed in pair 2.
- Verdict: the bend-exit advantage found in the pooled data is not confirmed; the rpm rule is slower over the whole lap in this confirmation. Rejected. The earlier whole-lap gain of the rpm rule across four pairs (-1.10 s mean) is now contradicted by this confirmation (+0.81 s), so the rpm rule cannot be adopted on the existing evidence. Keep the model as the default; the rpm rule's lap-time effect is undecided and needs a larger pre-registered test before any default change.

### Reconciliation of the bend-exit records (2026-11-27): what the source records support

Source: `scripts/gtr2_ui/runs/paired_exit.jsonl` (four records: A1, B2, A3, B4; eight timed laps each; no spin in any). Signal logs were re-read directly. Monitor `bc6cvixf6` reported `PAIRED_EXIT_DONE` with two sessions per arm, which matches: there are two A-then-B pairs, (A1, B2) and (A3, B4), not four pairs. "Four paired comparisons" in the brief means these four sessions.

Confirmed (re-computed from the signal logs):
- Whole lap, mean of laps 1 to 8 per session: pair 1 B minus A = +1.29 s, pair 2 = +0.33 s, mean +0.81 s. This reproduces the `cd3d879` figure.
- Bend exit: pair differences -0.57 s and +0.22 s, mean -0.18 s (the doc says -0.18). The rule needed -0.2 s: not met. The rejection stands.
- No spin in any of the four sessions.

Not supported as stated:
- The whole-lap means include laps with impacts or track-limit events. The lap-check clean rule (no track-limit event, no impact) was not applied to these means.
- Impacts (Kerbs21, peak 68 to 80 m/s^2) occur in A1, A3 and B4 at about 94 s, 215 to 217 s and 819 s. The kerb rule allows kerb strikes; the lap-check still marks the session unclean. Which lap each falls in is not confirmed here.
- B4 has a track-limit event on 8 of its 9 logged laps (0.1 to 0.5 s each). Under the strict clean rule B4 has no clean lap. The rpm arm therefore ran unclean on nearly every lap in pair 2. This is an observation about the arm, and it was not reported before.
- Clean-lap-only means (A1 n=4, B2 n=2): A1 120.33 s, B2 121.34 s, B minus A +1.01 s. Pair 2 has no clean B lap, so it gives no clean comparison. The clean-only result rests on one pair and two B laps.

Why the paired laps are about 120 s and the best clean lap was 1:52.66 (inferred, not yet verified in the drive log):
- The paired runner (`gtr2-paired.py` line 93) passes each arm's options to `gtr2-lap-check.py` as `--drive-args` on top of the Imola entry in `track_params.json`. It also adds `--session-laps 8` for each session. CORRECTION (2026-11-27): an earlier note here said it did not; the dry-run plan shows it does.
- CORRECTION: the push ramp does run in the paired sessions, so it does not explain the gap to 1:52.66 by itself. The cause of the 120 s laps is open. The 1:52.66 lap came from a 12-lap session; whether the paired sessions differ in some other setting (entry options, the number of laps, or lap-to-lap tyre wear) is not yet checked.
- Consequence: the gear arms are measured inside a session with the push ramp, at about 120 s laps. The gear result is a result at that pace, not at the 1:52.66 pace, until the gap is explained.

Classification:
- Confirmed observation: the arithmetic above; zero spins in the four sessions.
- Preliminary: whole lap +0.81 s (unfiltered); clean-only +1.01 s (one pair, two B laps).
- Rejected: the rpm rule's bend-exit confirmation (rule set before the run, not met).
- Unresolved: (a) whether push factor explains the 120 s to 112.66 s gap (test: one session of the same two arms with `--session-laps` and the push ramp); (b) whether the rpm arm's track-limit rate is caused by the arm (a count of events per arm over the existing records would settle this cheaply); (c) whether a clean-lap comparison at push 1.15 favours either arm.

Next offline steps: count track-limit and impact events per arm across all existing paired records (`gtr2-leaderboard.py` does not yet report these per arm), and check the drive log of one paired session for the push value used.

### Track-limit events in the paired records (2026-11-27): the strict clean rule rarely holds for the baseline

Measured with `scripts/gtr2-paired-events.py` (reads each record's signal log header and maps every event to its lap). Track-limit events are the short edge events (0.1 to 2.9 s) the lap check counts.

- Across all paired records with a signal log, almost every session has at least one track-limit event, and most laps have one.
- Pursuit control arm (A, `--follower pursuit` alone) pooled over the 15 pair files that have it: 151 of 216 laps (70%) carry at least one track-limit event. Session-level: 15 of 15 files show events in every session.
- The strict clean-lap rule (`gtr2-leaderboard.py`, no track-limit event and no impact) therefore leaves roughly 30% of baseline laps usable. A paired whole-lap comparison built on clean laps rests on few laps and is biased toward the laps that happened to stay inside the line.
- Impacts (Kerbs21 kerb strikes, 60 to 80 m/s^2 peak) occur in some sessions (the share is not counted here). The kerb rule in the project allows kerb contact, so impacts are a secondary filter.

Classification:
- Confirmed observation: the counts above (script output, reproducible).
- Open question, to settle before using clean-lap means: whether the track-limit events are a driving defect (the follower runs wide) or a geometry artefact (the boundary line is too tight, or the tyre footprint is too wide). The boundary rule is the user's rule and is not changed here. The check is to compare the event positions with the line offset (`line_off` in the signal log) at the same distance: a consistent offset above the line margin points to the driver, a random scatter points to the geometry.
- Consequence: the 1.86 s budget and the gear comparison need either a looser lap-time filter that keeps every lap with a cleaner measure, or a per-lap event time summed as a lap-time penalty, not a binary clean flag.

### Where the track-limit events happen (2026-11-27): repeatable driver excursions, not random geometry

Checked against the signal logs of the four exit-test sessions (A1, B2, A3, B4). Each event time was matched to the lateral error (`lat_err`) in a window of 0.3 s.

- Each session's events fall at nearly the same times: about 32 s, 154 s, 276 s and later points, repeated across all four sessions (32.13 to 32.17 s, 153.96 to 154.83 s, 275.22 to 277.12 s). Scatter is about 1 s, so the cause is the same place on every lap, not random noise.
- At every event the lateral error is about -6 to -7 m (-5.5 to -7.2 m; one event at +9.4 m in A1). Over the whole session the lateral error has a standard deviation of 1.7 to 1.9 m, with 95% of samples within about 3 m. Samples beyond 6 m are only 1.0 to 1.4% of the run, and those are where the events sit.
- The planned line offset (`line_off`) is about 0 throughout, so the excursion is not the planned line. The car is 6 to 7 m from the line the driver follows, and the event happens where the tyres cross the boundary.

Reading (hypothesis, to confirm): the excursion is a driver or line-following error at fixed points, consistent with the follower's aim or the line-follow correction taking the car to the edge at a repeatable place. A geometry artefact would scatter across positions and would not give a consistent lateral error of -7 m. The next check is the lap distance of those points (the layout's waypoint file) and the steering and heading just before each event: a heading that points toward the edge before the event would confirm a driver cause.

Consequence: the strict clean rule is failing for a driver reason that repeats. Removing it from the lap-time comparison would hide a real and repeatable excursion, and it costs time at those points too.

### Where the first track-limit event falls on the lap (2026-11-27): a map from the lap check records

From the `dist` field of the first track-limit event in each lap check record (127 records; one event per record, so counts are first events only; lap distance in metres):

- 500 to 549 m: 22 records. 700 to 749 m: 20. 650 to 699 m: 10. 450 to 499 m: 8. Together the 450 to 749 m stretch holds 60 of 127 first events.
- 2100 to 2149 m: 17. 3900 to 3949 m: 9. 1150 to 1199 m: 8. 1450 to 1549 m: 7 across two bins.

Two links to other work:
- The 1150 to 1199 m bins are the 1100 to 1200 m section the mission asks about. Track-limit events there mean the car runs wide at that point, which is a candidate cause of the section's loss that is independent of speed planning (the earlier speed and apex tests did not change the excursion).
- The 650 to 749 m cluster overlaps the designed follower's recurring 640 m failure. Both may be the same repeatable excursion seen from two sides: a wide line at that point, and the follower's loss of control there.

Status: a hypothesis built from the event map. It does not yet show the excursion causes the lap-time loss. Next check: the same map from the signal logs (the exact lap distance of each event, all events, not only first events), and the heading and steering in the two seconds before each event at 1150 to 1199 m and 650 to 749 m.

### Track-limit events by lap distance from the signal logs (2026-11-27): two sharp points and the heading at the second

Method: lap distance is the integral of speed within each lap of the four exit-test signal logs (A1, B2, A3, B4). Every event in each log's header was mapped to its distance. Events counted per log, so one point repeats on each lap of each session. Integration drift over a lap is not measured; the bins are approximate to a few tens of metres.

- 700 to 749 m: 127 events. The largest cluster. Lateral error about -7 m, heading error about -4 to -10 degrees, steering about -0.25 to -0.35 two seconds before.
- 1150 to 1199 m: 81 events. Lateral error about -6 m, heading error +12 to +21 degrees, steering about -0.15 to -0.35 two seconds before. The 1100 to 1149 m bin adds 14 and 1200 to 1249 m adds 10, so the excursion covers about 1100 to 1250 m.
- Other bins (650, 800, 3850, 5200 m) hold 1 to 2 events each: not repeatable.

Reading: at 1150 to 1200 m the car leaves the line with a heading 12 to 21 degrees off the line direction, and the steering two seconds earlier is already small. A pure line-following error would show the lateral error without a large heading error. A heading error this size at the start of the excursion is consistent with a yaw or steering-to-heading problem at that point, which is the lead the 1100 to 1200 m section needs. At 700 to 749 m the heading error is smaller and changes sign, so the mechanism there may differ.

Status: observations, not yet causal. The sign convention for `herr` is the one in the signal log (not re-checked against the code here). Next checks: the heading error over the 3 s before each event at 1150 to 1200 m (its onset), and whether the designed follower and the pursuit driver show the same onset.

### The two excursion patterns, traced in time (2026-11-27): a steering spike at 700 m, and a yaw without steering at 1150 m

Each session's first crossing of the 5 m edge threshold on each lap was traced: heading error (`herr`) and steering (`steer`) from 3 s before to the crossing. Sessions A1, B2, A3, B4 (laps 1 to 8).

- CORRECTION: at 700 to 749 m (laps 3 and 5 checked in A1) there is no braking: brake is 0 throughout. The car is at 47 to 51 m/s at full throttle with a sustained heading error of about -13 to -15 degrees and steering of -0.4 to -0.5 for about 1 s, then the throttle lifts (duty from 1.0 to 0.3) and the steering spikes to -0.7 to -0.96 at the crossing. The earlier reading that the steering went to full lock about 1 s before the crossing was wrong: full lock comes at the crossing, after the excursion has started. So the excursion at 700 m is a mid-corner heading error under throttle, with a corrective steer and lift at the edge.
- At 1150 to 1200 m the pattern is different: steering stays small (about -0.2 to +0.3) while heading goes from about -3 to +7 to +15 to +21 degrees over the same 3 s. The car rotates with little steering input, which fits an oversteer or yaw event rather than a steering error. This is the mechanism to test in the 1100 to 1200 m section.
- The first pattern points at the driver's turn-in (a full-lock steering command at a fixed point); the second at the car's rotation (yaw with no steering). They may still share a cause (for example brake release or throttle at that point), which the logs do not yet show: the brake and throttle columns in the same window are the next check.

Status: traces from four sessions, all eight laps each; consistent within sessions. These are observations of inputs and states, not yet of cause. The sign convention for `herr` and `steer` is that of the signal log.

### The 1150 m excursion, traced in controls (2026-11-27): a downshift through neutral with a throttle lift and full steering

Checked in the first lap crossing of the 1150 m point in two sessions (A1 at 157.1 s, A3 at 156.9 s, lap 1, where the car is about 48 m/s at the start of the window).

- 30 rows before the crossing (about 3.3 s: a logged row is about 0.11 s): full throttle (1.0), gear 3, speed 48 m/s, steering -0.44 to -0.52, heading error -14 degrees.
- 20 rows before (about 2.2 s): throttle lifts to 0.3, steering goes to -0.9 to -1.0 (full lock), and the gear reads 0 (neutral) during a downshift from 3 to 2 (A1) or to 4 (A3).
- 10 rows before (about 1.1 s): lateral error -11 to -11.5 m (the car is 11 m off the line, past the edge), speed 38 m/s, yaw swings between about +16 and -19 degrees per second. Brakes are 0 throughout.
- At the crossing: heading error +11 to +12 degrees, speed 35 m/s, and within about 0.5 s the yaw reverses (+20 to +35 degrees per second) and the car recovers to within 1 m of the line.

So the excursion is a loss of control under a downshift: the throttle lift, the full-lock steer and the neutral gear coincide within about 1 s (20 rows). The speed loss (48 to 35 m/s) is larger than a shift or a lift alone would explain at this corner. Two candidate mechanisms, neither confirmed: (1) the lift and the neutral gap cut drive torque at the moment the car needs it to hold its yaw (a load-transfer or power-off snap), and (2) the full-lock steer is the response to the yaw the car already has, so steering follows the instability. The traces cannot yet separate them, because the steering and the lift start within a sample of each other.

Connection to the mission: this downshift through neutral at 48 m/s is a gear-selection event inside a corner, which the RPM-rule and model comparisons did not measure (they counted shifts on the whole lap, not the shift's position relative to the corner's yaw). A shift at this point is the lead to test first, with the throttle and steering held fixed for one lap if possible.

### No-downshift test at 1100 to 1200 m (2026-11-27): rule set before the run

Question: does the downshift through neutral inside the 1150 m corner cause the excursion there? Arm A: `--follower pursuit` (the incumbent, unchanged). Arm B: the same plus `--no-downshift-zone 1100 1200` (no downshift between 1100 and 1200 m; upshifts unchanged). Two pairs, eight timed laps per session (paired runner, `--log paired_nodown.jsonl`).

Primary metric: laps with a track-limit event between 1100 and 1250 m (signal-log distance, integrated speed), per arm.
Secondary: the whole-lap time (mean of clean laps only, per the lap-check clean rule; a lap with a track-limit event is not counted in the lap mean).

Decision rule:
- Adopt as a lead (not a default) if arm B has at least 3 fewer laps with an excursion in 1100 to 1250 m than arm A across the four sessions, and no more than 0.5 s slower on the clean-lap mean.
- Reject if arm B has the same or more excursions.
- Otherwise inconclusive: more sessions needed before any claim.

Limits: two pairs is a screen, not a confirmation. A sign of an effect is what would justify more sessions. The rule is set here so the run cannot choose its own criterion afterwards.

### Downshifts and excursions at 1100 to 1250 m (2026-11-27): an association, in both directions

Offline, from the 28 sessions with shift and signal logs (shift logs and signal logs matched by stamp; lap distance by integrated speed).

- Downshifts at 1100 to 1250 m: 548. An excursion (lateral error at or beyond -5 m) within 2 s of the shift: 356 (65%).
- Upshifts at the same distance: 163, with 0 excursions within 2 s.
- Sampled no-shift points at the same distance: 723, with an excursion within 2 s in 179 (25%).
- Order of events for the downshifts: in 197 of them the excursion was already under way within 2 s before the shift (so the shift may be the car's response to a slide); in 213 the excursion began after the shift, with a median lag of 0.34 s.

Reading: the association is strong, but it runs both ways. A downshift can cause the excursion (the 213 cases), or the excursion can slow the car and bring about the downshift (the 197 cases). The rate comparison also has a confound: the downshifts happen at corner entry, where the car is slowest and most likely to leave the line. So this table does not establish the cause.

What it does establish: the downshift is not a rare, incidental event at this point, and it is much more often inside an excursion than anything else there. The no-downshift paired test (pre-registered above) is the controlled check: it removes the downshift and keeps everything else.

### Sample size for a 0.5 s whole-lap effect (2026-11-27): a planning estimate from two pairs

The four exit-test sessions give two pair differences of +1.29 s and +0.33 s (whole-lap mean, unfiltered). Their spread is a rough estimate of the pair-level noise (SD about 0.68 s from only two values, so the estimate itself is uncertain).

- Pairs needed to detect a 0.5 s difference (two-sided alpha 0.05, power 0.80, pair-difference SD 0.68 s): about 15, so 16 pairs (32 sessions, about 11 hours at 20 minutes a session).
- For a 0.3 s difference: about 40 pairs. Not practical in the current session budget.

Reading: a confirmation of the rpm rule or any gear change at the 0.5 s level needs about 16 pairs, not the 2 to 4 used so far. Two-pair screens can detect a large effect (over 1 s) but cannot confirm a small one. This is why the no-downshift test is framed as a screen, with its own pre-registered decision rule.

Caveat: this uses the lap-level mean from only two pairs. Re-estimate the noise after more pairs before committing to a sample size.

### No-downshift screen: first attempt failed by a bug in the new option (2026-11-27)

- The first attempt (both B sessions) ended at 49 s with `AttributeError: 'float' object has no attribute 'dist'`. The check referenced `target.dist` in the gear block, where `target` is a float (a target speed), not the track point. The fix uses the car's track position `w.dist` (set on every loop iteration).
- The paired runner had classified that exception as a driving stall. It now classifies a Python exception in the driver as an infrastructure failure, which is excluded from driving results.
- The first attempt's records are kept, not counted: `scripts/gtr2_ui/runs/bugged_nodown_attempt1.jsonl`. Arm A in that attempt (two clean sessions, 0 spins) is valid and is repeated in the rerun.
- Rule unchanged (set above). The rerun uses a fresh log, `paired_nodown.jsonl`.

### No-downshift screen result (2026-11-27): rejected by its own rule

Rerun after the bug fix (`paired_nodown.jsonl`, two pairs, eight timed laps per session, all four sessions completed with no exception). Rule as pre-registered above.

- Primary metric (laps with a track-limit event at 1100 to 1250 m, signal-log distance): arm A (pursuit) 2 laps across its two sessions; arm B (`--no-downshift-zone 1100 1200`) 7 laps. Arm B has more, not fewer. The rule's reject condition ("same or more excursions") is met.
- Secondary (mean of clean laps, lap-check clean rule; few clean laps per session, so only indicative): arm A about 119.6 s from 9 clean laps; arm B about 121.8 s from 3 clean laps. No clean-lap comparison is possible with this few laps.
- Verdict: rejected. Blocking the downshift through 1100 to 1200 m did not remove the excursion there, and it added excursions in the 1100 to 1250 m range.

What this says about the hypothesis: the downshift is not the cause of the excursion. The association found offline (65% of downshifts followed by an excursion) was mostly the car's response to a slide, not the other way round, or the corner entry confound. The more likely reading now: the excursion is a power or yaw event at the corner (heading error and yaw swing with steering near zero at 1150 m), and a higher gear under the same throttle may make it worse, not better. That is a new hypothesis, not a result, and it has not been tested.

Next: not a second run of the same comparison. The rule is set and the lead is rejected. The next test would target the yaw event directly, for example throttle at the 1150 m corner held at the lift point, with the rule set before the run.

### Throttle-lift rate test at 1100 to 1250 m (2026-11-27): rule set before the run

Hypothesis: the excursion at 1150 m is a lift-off yaw event (the throttle falls from about 1.0 to 0.3 in the corner while the steering is already at full lock). A slower lift should reduce it.

Arm A: `--follower pursuit` (incumbent). Arm B: the same plus `--lift-zone 1100 1250 --lift-rate 0.5` (the throttle may fall at most 0.5 duty units per second inside 1100 to 1250 m; a lift from 1.0 to 0.3 then takes about 1.4 s, not about 0.2 s). Two pairs, eight timed laps, `--log paired_lift.jsonl`.

Primary metric: laps with a track-limit event at 1100 to 1250 m (signal-log distance), per arm, same as the no-downshift screen.
Secondary: mean of clean laps (lap-check clean rule), indicative only.

Decision rule:
- Adopt as a lead if arm B has at least 3 fewer excursion laps than arm A across its four sessions and its clean-lap mean is no more than 0.5 s slower.
- Reject if arm B has the same or more excursion laps.
- Otherwise inconclusive.

### Throttle-lift rate screen result (2026-11-27): rejected by its own rule

Two pairs, all four sessions completed with no exception (`paired_lift.jsonl`). Scored with the pre-registered primary metric.

- Excursion laps at 1100 to 1250 m: arm A (pursuit) 1 (sessions A1 and A3: 1 and 0); arm B (lift-rate 0.5) 5 (sessions B2 and B4: 2 and 3). The reject condition ("same or more") is met.
- Clean-lap means (indicative, few laps): arm A 119.77 s and 119.62 s; arm B 121.27 s and 120.99 s. Arm B is about 1.3 s slower per clean lap in both pairs.
- Verdict: rejected. Slowing the throttle lift at 1100 to 1250 m did not reduce the excursion; it added excursion laps and cost time. The lift-off yaw hypothesis is not supported by this screen.

Together with the rejected no-downshift screen, both direct controls on the 1150 m corner have made it worse. The incumbent pursuit's behaviour there is not improved by a smoother downshift or a smoother lift. Next step: characterise what the incumbent does at that point in the logs (heading onset against the steering command), not another control change.

### Heading onset in the incumbent (2026-11-27): ordinary corner turn-in, not a distinct trigger

Across six incumbent pursuit sessions (the A arms of the exit, no-downshift and lift tests), 93 onsets were found where the heading error crosses -10 degrees at speed above 30 m/s with the lateral error under 3 m. The steering at these onsets is -0.34 (median -0.36 mean): a normal corner turn-in, not a spike.

Reading: the heading swing that precedes an excursion is the same heading swing the car makes in ordinary corners. A heading onset does not, on its own, separate the excursion corners from the clean ones. The discriminating feature is probably the heading error growing past about -13 degrees while the steering stays at about -0.4 (no correction), which the traces showed before each excursion. That is the next thing to test, offline first.

### Heading-error windows as a predictor of an excursion (2026-11-27): weak

Across all signal logs of the session (1213 windows where the heading error is at or below -13 degrees, the steering is within 0.5, and the speed is above 30 m/s): 465 were followed by an excursion (lateral error at or beyond -5 m within the window or the next 2 s), and 748 were not. So 38% of such windows end in an excursion.

Reading: the feature is common and the excursion rate is 38%, which is a weak discriminator. It is not a usable trigger on its own. Any predictor for the excursion needs more than this heading window, probably the rate of change of heading together with the steering command, and it has not been fitted yet. This is an offline screen, not a game test.

### Baseline discrepancy located (2026-11-27): where the 1:52.66 lap and the paired laps part company

Sources: git history of `scripts/gtr2_driving/track_params.json` (commit `c9982e5` added the optimised-line zone 2400 to 2750 m and recorded 1:52.66; commit `8698c04` reverted it after a confirmation session had 0 of 12 clean laps). The committed Imola entry at HEAD does not contain the 2400 to 2750 m zone. The 1:52.66 lap is lap 11 of session 2026-11-25 00:17:54, signal log `signals_20261125_001740.csv` (present). The paired comparison lap is lap 4 of `signals_20261127_134353.csv` (paired A1).

Distance-aligned cumulative time (lap distance by integrated speed, same method for both logs):

| distance (m) | 1:52.66 lap | paired A1 lap 4 | paired minus best |
|---|---|---|---|
| 500 | 10.06 s | 10.57 s | +0.51 |
| 1000 | 20.01 s | 20.57 s | +0.56 |
| 1500 | 33.16 s | 35.21 s | +2.05 |
| 2000 | 43.45 s | 45.56 s | +2.11 |
| 2500 | 54.42 s | 57.67 s | +3.25 |
| 3000 | 67.48 s | 71.16 s | +3.68 |
| 3500 | 80.18 s | 84.79 s | +4.61 |
| 4000 | 91.62 s | 97.13 s | +5.51 |
| 4500 | 102.95 s | 108.78 s | +5.83 |

Reading:
- The loss builds in steps. About 0.5 s is lost in the first 1000 m. Between 1000 and 1500 m (the 1150 m excursion) it grows by 1.5 s. Between 2000 and 2500 m (the 2440 to 2520 m bend, the same section where the line-optimisation zone was added) it grows by 1.1 s. Between 3000 and 4500 m it grows by about 2.2 s over 1500 m.
- The steps line up with the places where the 2400 to 2750 m zone and the excursions act. That fits the revert being part of the cause, but it does not establish it: this is one lap against one lap.
- Selection: the comparison is the best clean lap against one typical lap. The paired A-arm clean laps average about 119.6 s, so the typical lap is about 7 s slower than the best. The 1:52.66 lap is a best-of-many lap, so some of the gap is selection, not configuration. This must be separated with the distribution of clean laps from the same configuration.
- Not yet checked: whether the paired runs apply the committed zones at runtime (they should), and the clean-lap distribution of the 1:52.66 configuration over more sessions.

Next: a targeted test of the reverted configuration against the zone, in the staged order of the mission (a short qualification run first, a paired run only if it passes).

### Qualification: the 2400 to 2750 m zone restored (2026-11-27): rule set before the run

Question: does the optimised-line zone at 2400 to 2750 m (the configuration that produced 1:52.66, reverted in `8698c04`) make the lap faster in the current build?

Arm A: the committed Imola entry (incumbent, `--follower pursuit` only, zones 1050 to 1550, 2950 to 3250, 3750 to 4100, 4350 to 4700). Arm B: the same plus `--line-opt-zones 1050 1550 2400 2750 2950 3250 3750 4100 4350 4700` (the zone string from `c9982e5`; the later flag overrides the entry's). One pair, eight timed laps per session, `--log paired_zone.jsonl`. This is a qualification, not a confirmation.

Primary: distance-aligned time at 2750 m (end of the zone), mean over clean and unclean laps, arm B minus arm A.
Secondary: laps with a track-limit event at 2400 to 2750 m, per arm; clean-lap mean, indicative only.

Decision rule:
- Continue to a larger paired comparison if arm B is at least 0.5 s faster at 2750 m (mean of the two sessions).
- Reject the zone if arm B is slower at 2750 m, or if it adds track-limit laps at 2400 to 2750 m.
- Otherwise: inconclusive, and not carried forward.

### Zone qualification result (2026-11-27): rejected by its rule

One pair (`paired_zone.jsonl`, sessions A1 and B2, eight laps each, both completed).

- Time at 2750 m, mean of the eight laps: arm A (committed entry) 67.38 s; arm B (zone 2400 to 2750 m restored) 68.61 s. Arm B is 1.23 s slower at the end of the zone, which meets the reject condition ("slower at 2750 m").
- Track-limit laps at 2400 to 2750 m: 0 in both arms in this pair.
- Verdict: rejected. Restoring the zone that produced 1:52.66 does not reproduce that lap's advantage in the current build.

What this means for the discrepancy: the reverted zone is not the explanation for the gap by itself. The 1:52.66 lap came from a build that differed from the current one in more than that zone, or it was a single lucky lap (selection). Either way, the 1:52.66 configuration cannot currently be reproduced by restoring one option. The next step is to identify what else changed between `c9982e5` and HEAD in the Imola entry and in the driver, before any further zone test.

### Old-build reproduction (2026-11-27): rule set before the run

Question: does the build that produced 1:52.66 (commit `c9982e5`, with its own committed Imola entry) run the paired-style arm A at about 112 to 116 s laps, or at the same 119 to 122 s as HEAD? Run: one session of the old build, from a worktree beside the repository (`gtr2-agent-tools-c9982`), with arm A's options (`--session-laps 8 --follower pursuit --sig-log`) through the old `gtr2-lap-check.py`. The paired runner did not exist at that commit, so the lap-check is called directly.

Metric: mean lap time of laps 1 to 8 in the signal log (same method as the HEAD sessions, which were 119.6 to 121.8 s per session).

Decision rule:
- Mean at or below 116.0 s: the regression is in the code or the entry since `c9982e5`. Next step: bisect the commits between `c9982e5` and HEAD, one session per step.
- Mean at or above 119.0 s: the code is not the cause. The 1:52.66 lap is a best-of-many or environment result, and the investigation moves to selection and session conditions.
- Between 116.0 and 119.0 s: inconclusive; one more old-build session before any conclusion.

### What changed between the 1:52.66 commit and HEAD (2026-11-27): one entry argument, and 27 driver commits

- Imola entry (`track_params.json`): the only argument that differs is the removal of the 2400 to 2750 m zone (commit `8698c04`). Every other argument is identical.
- Driver and followers: 27 commits from `c9982e5` to HEAD touch `gtr2-drive-lap.py` or `gtr2_driving/`. Most add options that are off by default (`--gear-band`, `--gear-model-duty`, `--fgrip-steer`, `--plan-file`, `--apex-shift`, `--slide-release`, `--lift-zone`, `--no-downshift-zone`, `--st-*`, and others). The commit messages say the defaults keep the old behaviour, and a logging change (`3899e3b`) was made to be harmless.
- One change is not checked in the game: `e009c12` (the designed follower's post-call limits, "no behaviour change; game check still owed"). It affects the designed follower, not the pursuit arm used here, but it is an unverified claim.
- The pursuit steering refactor (`1b43c21`) was checked for identical arithmetic (200,000 random cases, maximum difference 0).

Reading: the code diff does not, by itself, show a change to the pursuit arm's behaviour. The zone removal was tested directly (restoring it gave a slower lap at 2750 m in the current build). So the candidates are: a silent behaviour change from the defaults, a difference in the game environment, or selection (one best lap against typical laps). The old-build session (fc7d66a's rule above) separates the first from the other two.

### Old-build reproduction, session 1 (2026-11-27): inconclusive by its rule

One session of the 1:52.66 build (commit `c9982e5`, its own Imola entry), arm A options, through the old lap-check. Signal log `signals_20261127_205101.csv` in the worktree's runs folder.

- Laps: 117.11, 158.75, 120.04, 117.30, 116.38, 116.92 s; lap 7 was not completed. The session ended by timeout (the lap check's default timeout was too short for eight laps, a run-setup error on my side; the paired runner sets it longer).
- Mean of the five normal laps (lap 2 excluded: 158.75 s, a slow lap): 117.55 s. Fastest lap in the session: 116.38 s.
- Against the rule (at or below 116.0: code regression; at or above 119.0: not the code; between: inconclusive). Result: inconclusive. HEAD's paired sessions averaged 119.6 to 121.8 s, so the old build is about 2 s faster on average, but not the 112 to 113 s of the 1:52.66 lap.

Reading: the old build is faster than HEAD by about 2 s per lap on average, which is a difference between builds, not only selection. It is still about 4 to 5 s slower than 1:52.66, so the best lap is also part of the gap. One more old-build session is needed before any conclusion (the rule's requirement).
