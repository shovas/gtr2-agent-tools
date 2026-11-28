# Open items

Read this before choosing the next task. Moved verbatim from `CLAUDE.md`.

- **Documentation:** `CHANGES.md` entries carry only the day, not a time (`YYYY-MM-DD HH:MM:SS +/-HHMM` wanted). The test and sweep scripts (`test_*.py`, `gtr2-nav-suite.py`, `gtr2-lap-campaign.py`) have no `--mode` option yet (suite is about 330 s, so Normal needs a subset of tours).
- **Reminder: full sweep of every car at every track (pit-lane exit and full lap, `--input wheel`) is still to do.** After an interrupted run use `gtr2-recover.py --force --revert` (stale nav servers and an orphaned game make every later run fail).
- Make the nav server optional/simpler (startup under 1 s is acceptable; see `docs/ui-navigation.md`).
- Driving: layouts and cars beyond Imola/Murcielago are untuned (every layout runs clean with defaults); pit-lane exit from the track's `XPITOUT` object was verified only on Imola and Anderstorp S (wheel garage-exit check passed 2026-11-14 at Magny-Cours 4, Hockenheim GP and Zhuhai 4 with 3 cars each; Estoril 3, Dubai 4, Donington 3 still to re-run; `--box-yaw-bias auto` (default) reads the garage walls from the track's own collision meshes, `gtr2-garage-map.py`, `gtr2_driving/{mas,gmt,garage,boxplan}.py`; all 34 layouts pass with the Maserati, see docs/analog-driving.md); Anderstorp S crawled in 1st gear on the pit chain (fix partly in); delay between entering the cockpit and the car moving not measured; wet Driving School levels 4 to 7 unsolved.
- Setup script untested on a machine without Steam/vJoy, with a non-git game folder, and its venv step.
- First-run bootstrap tested with the real game once; `Documents\GTR2` weather.txt drift (`only in snapshot`) is the known harmless drift.
