# Signal logs

- Location: `scripts/gtr2_ui/runs/signals_*.csv` (git-ignored). Header line: layout, car, track-limit and impact events.
- Columns: t, speed, sideslip, yawrate, grip (front and rear), lap, x, z, plan_speed, gear, rpm, duty, brake, lat_err, line_off (always 0), target_v, herr, steer, aim, br (steering branch and chain state, from the newest logging build).
- Caveats: the logged `steer` is the command read at the top of each loop iteration, so it lags one step. Lap distance from integrating speed is biased; use nearest-waypoint position.
- Analysis scripts are in the scratchpad and are not committed; the findings are in `docs/controller-competition.md`.
