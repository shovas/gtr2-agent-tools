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
