# Planned line and tracking

- Fact: the logged `lat_err` equals the negative of the geometric offset along the waypoint normal (`wp_perp`), correlation −0.90 to −0.99.
- Fact: the logged `line_off` is always zero and carries no information.
- Fact: the planner's `plan_speed` is a lateral speed limit with a deceleration envelope and no acceleration limit (`scripts/gtr2-drive-lap.py`, `corner_v`).
- Fact: over 3.2 million samples the car realises about 42% of the planned offset (slope 0.42). Adding the logged aim offset does not improve the fit.
- Interpretation: the shortfall is real and its cause is open. Sign convention: positive `wp_path` is right (supported by track-limit events, 91% outside the road on that side, against 46% the other way).
- Caveat: the distance from integrating speed is biased by about 0.5% (median 4881 m against 4906 m); use nearest-waypoint position instead.
