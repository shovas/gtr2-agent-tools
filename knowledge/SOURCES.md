# Sources

Examination depth: `full` = read the whole file; `section` = read the parts named; `analysed` = data analysed by script, not read line by line.

| Path | Subject | Authority | Depth | Indexed |
|---|---|---|---|---|
| `CLAUDE.md` | agent rules, game safety, commands | authoritative | full | yes |
| `AGENTS.md` | redirect to `CLAUDE.md` (rules merged there, 2026-11-28) | redirect | full | n/a |
| `docs/controller-competition.md` | controller record, all dated investigations | project record | section (this stretch) | yes |
| `docs/analog-driving.md` | driving history, aim, steering, guard options | project record | section | partly |
| `scripts/gtr2-drive-lap.py` | lap driver; steering, guard, live mode, chain, logging | code | section (steering, guard, fast preset) | partly |
| `scripts/gtr2_driving/track_params.json` | Imola entry | config | full (Imola entry) | yes |
| `GameData/Locations/Imola/4Imol.AIW` (game folder) | main and pit waypoints, widths, planned offsets | game data | section (waypoints 4400 to 4700 m, parsing) | partly |
| `scripts/gtr2_ui/runs/signals_*.csv` | per-sample signal logs | data | analysed (476 logs) | yes |

Not yet read: `docs/driving-theory.md`, `docs/imola-slow-corner-2400-2900.md`, `docs/follower-redesign-plan.md`, the reference books in `..\gtr2-agent-tools-reference` (not copied; see `CLAUDE.md`).
