# Driving theory notes (sources and what they mean for the driver)

Collected 2026-11-23 on the user's suggestion (read race-driving and tyre theory, then simulate a driver by it). Only freely and publicly readable sources were used; where a source could not be read, that is said. Everything is paraphrased. What it means for `gtr2-drive-lap.py` is under each heading, and the ranked list at the end is what to try next. Lap times in this file are written m:ss.s.

## Sources read

| Source | What it gives | Status |
|---|---|---|
| [Wikipedia: Racing line](https://en.wikipedia.org/wiki/Racing_line) | the outside-inside-outside line, late versus early apex, compound corners | read |
| [Wikipedia: Trail braking](https://en.wikipedia.org/wiki/Trail_braking) | brake past turn-in, release progressively; load transfer and rotation | read |
| Kapania and Gerdes, [Path tracking of highly dynamic autonomous vehicle trajectories via iterative learning control](https://arxiv.org/abs/1902.00611) (HTML on arXiv) | lookahead feedback plus a learned steering command, lap by lap | read |
| Heilmeier et al., [Minimum curvature trajectory planning and control for an autonomous race car](https://portal.fis.tum.de/en/publications/minimum-curvature-trajectory-planning-and-control-for-an-autonomo/) (Vehicle System Dynamics 2020) | quadratic-programme racing line plus a forward-backward speed solver | abstract only |
| Becker et al., [Model- and Acceleration-based Pursuit Controller for High-Performance Autonomous Racing](https://arxiv.org/abs/2209.04346) (HTML on ar5iv) | pure pursuit that maps the wanted lateral acceleration to steering through a tyre model | read |
| Ross Bentley's free PDFs at speedsecrets.com (trail braking, Performance Driving Illustrated) | race-driving technique | the PDFs are fonts without a text layer: not readable by the tools; the Wikipedia pages quote Bentley's rules |
| Beckman, The Physics of Racing (miata.net) | friction circle, weight transfer | the host answers 403: not read |
| Pacejka, Tyre and Vehicle Dynamics | the Magic Formula | the book is paid; the only free copy found sits on a host whose TLS certificate does not verify, so it was not fetched; the Chalmers vehicle dynamics compendium (open PDF, combined slip, brush model) is the open alternative; the Magic Formula is summarised below from the papers that use it |
| Autosport, Pirelli, Catapult articles on tyre temperature | grip window, graining and blistering | read (qualitative) |

## Racing line

- Outside-inside-outside uses the whole width to make the radius as large as the corner allows. The ideal path has a radius that opens while the car slows, tightens to the apex and opens again on the throttle.
- Late apex: turn-in later, a longer exit radius, more exit speed, less entry speed. The faster the corner, the closer to the geometric line; the slower the corner, the later the apex. An early apex (faster entry, slower exit) is called mostly a beginner error.
- Compound corners and chicanes: sacrifice the line through the early turns to set up the last one, which decides the exit speed.
- The optimum is a minimum-time problem; the minimum-curvature line with a good speed profile is within 0.1 s of a human in Heilmeier et al., and is found by a quadratic programme re-linearised a few times.
- Driver here: matches what the AI benchmark showed (1.5 to 2.5 times our corner radius, full width). Our `--line-opt` is a time-optimal search; the zoned line (slow corners only) agrees with "the slower the corner, the more the line matters", but `--line-opt` on the fast kink at 600 m failed because the follower could not hold it.

## Braking, trail braking, throttle

- Brake hard first, release progressively, with the full release somewhere between turn-in and the apex. Braking loads the front (more front grip, less understeer) and helps the car rotate; releasing the brake lightens the front and lets the rear step out. The slower and tighter the corner, the more trail braking helps; in fast corners the driver is often on the throttle at turn-in. The grip is shared between braking and cornering, so the brake has to come off as the steering goes on (the friction circle).
- Driver here: our pedal is proportional to the speed error plus the kinematic braking term; it holds the brake to the apex in the slow corners (brake on in 17 to 59 percent of the samples around them). The rule "release as the steering goes on" is in the friction-ellipse planner, not in the pedal.

## Tyre model (Magic Formula) and temperature

- The Magic Formula gives the side force Fy = D sin(C arctan(B a - E (B a - arctan(B a)))) from the slip angle a: B stiffness, C shape, D peak, E curvature; the peak force D depends on the vertical load (it grows less than linearly: load sensitivity) and the force falls past the peak slip angle, so more steering beyond it only adds understeer. Fits for autonomous racing cap C at 1.5 and E at 1.1.
- From the Wikipedia pages on Pacejka, slip angle, cornering force, tyre load sensitivity and understeer: the formula is y = D sin(C arctan(B x - E (B x - arctan(B x)))) with each force needing 10 to 20 fitted coefficients (the page calls them fitting constants; the letters' usual meanings are stiffness, shape, peak, curvature); the side force rises about linearly for the first degrees of slip angle, peaks (road tyres at about 6 to 10 degrees of slip, F1 tyres about 3, the peak angle growing with load) and then falls; the friction coefficient falls as the load rises while the maximum side force still rises, roughly with the load to the power 0.7 to 0.9; the side force builds up over a relaxation length of rolling (no value given); a heavier front axle (braking, or a forward weight bias) increases understeer through the same load sensitivity; the combined braking-and-cornering limit is the traction circle (the vector sum of the two forces cannot pass the grip). The MathWorks page for the Magic Formula tyre block lists the coefficient names (PCY1 shape, PDY1 peak friction with PDY2 its load variation, PEY curvature, PKY cornering stiffness, RBY/RCY the combined-slip reduction, PPY the inflation pressure effect) and cites Pacejka's book for the equations; no default values.
- Not found openly: the friction-ellipse weighting formulas and typical coefficient values (they are in the book, whose only free copy found is on a mirror with an invalid TLS certificate).
- Grip needs a temperature window: cold rubber does not conform (graining), hot rubber loses strength (blistering); a harder compound needs more heat. The tyres here run at about 69 C (Soft, 90 C optimum from the tyre files).
- Driver here: the yaw response per steering command is identified live (`--steer-id`); the planner's grip (`--live-lat`, `--live-k`) is the peak D; the spins at a push over about 1.1 are the car going past the peak.

## Path tracking at the limit

- Pure pursuit assumes no side slip (steering from the geometry of the aim point, delta = atan(2 L sin(eta) / Ld)); at the limit it drives wide (Becker et al.). Their fix: take the lateral acceleration pure pursuit asks for, a = 2 v^2 sin(eta) / Ld, and look the steering up in a table built from a single-track tyre model for that speed and acceleration, with an upper bound where no steady state exists: four times lower lateral error than pure pursuit, 0.35 s (5 percent) per lap faster on a 1:10 car; a lookahead that scales with speed (Ld = m + q v) keeps the loop's natural frequency constant.
- Kapania and Gerdes: a feedback law on the lookahead error (x_LA 5 to 20 m) plus a learned steering command per point of the lap, update delta_next = delta - kp e - kd (e - e_previous_point), the error low-pass filtered along the lap (2 Hz, zero phase), gains small; converged in two or three laps on a car at 8 m/s^2; the error can rise again after more laps from noise, so stop learning when the RMS stops falling; the learning only works until the front axle saturates (then the line and speed have to change).
- Driver here: our `--ilc` learns an aim-point shift per 10 m with a gain, a cap and a decay; it did what the paper says (error 1.8 to 1.2 m rms, two to four laps, a rise afterwards, wind-up at the cap). Missing compared with the paper: smoothing of the error along the lap before the update, the neighbour-difference (kd) term, and a stop rule.

## Next, in order (each testable in about 15 minutes of game time)

1. The slip-aware steering map (Becker et al.): compute the lateral acceleration the aim point asks for and turn it into steering through the measured yaw gain per speed (`--steer-id` data), clamped at the grip limit; replace `herr / steer_gain - yawrate / damping` in corners (keep it on straights).
2. ILC with the paper's ingredients: low-pass the error along the lap before the update, add the neighbour-difference term, stop learning after the RMS stops falling.
3. A minimum-curvature line with iterated curvature constraints (Heilmeier) as the line for the zoned corners, in place of the time-optimal search, and a larger zone coverage once the follower holds it.
4. Trail-braking release rule tied to the steering angle in the slow corners (brake pressure falls as the lateral acceleration used rises, from the planner's friction ellipse).
