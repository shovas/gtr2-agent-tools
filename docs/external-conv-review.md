# Review of the sibling conversion repository (`../gtr2-agent-conv`), 2026-11-25

Read-only review, done on the user's explicit request. The sibling is a file-format research repository (GMT, FXM, MAS, ISI and JCA
crypto, SimBin event and text files, rFactor and Race 07 conversions, media). Nothing from it was copied here, and nothing in it was
changed. Its own rules (`AGENTS.md`) cover its own work, not this repository's.

## What is relevant to driving

1. **The replay and ghost frame stream (`simbin_events_tool.py`, `docs/format-findings.md`, `docs/open-issues-research.md`).**
   - Each replay or ghost record gives a world position (x, z) and a heading per frame, with a frame time. Frame stride is 63 bytes.
   - **Heading convention:** the replay heading is `atan2(dx, dz)` in the world x/z plane (dominant in 10 of 15 ghosts, median circular
     coherence 0.86). Our code uses `atan2(-dx, -dz)`, which is 180 degrees from it. The offset is constant, so heading error and
     sideslip (both differences of headings) are unaffected, and nothing in our code needs to change. It matters if a logged heading is
     ever compared with the game's own replay heading: subtract 180 degrees first.
   - **Use for us:** the game's own replay of our runs gives an independent position and heading record. It can check our logged
     coordinates, our heading convention and our sideslip sign, which caused earlier errors. It does not give velocity, wheel loads or
     sideslip, so it cannot replace our telemetry.

2. **Steering in the ghost frames (weak).** The low signed 16-bit half of slot +48 correlates with the steering input at +8 (median
   |r| 0.50 across 12 ghosts, against 0.02 when permuted). Units and sign are unknown, and the slope varies by file. Our tools would need
   a fitted scale before the channel can be used as a steering trace. Recorded time-trial ghosts (`.gtt`) in the game folder are a
   possible source of recorded steering behaviour.
   - **Limit:** the rule in `CLAUDE.md` is not to use the game's AI driving line as the automated driver's path. Studying a recorded
     ghost to understand how a steering input relates to yaw is research, not a path source. It must not become the controller's path.

3. **Track and car setup files.** The sibling parses `.hdc`, `.gdb`, `.car`, `.dmg` and `.sp` (suspension geometry) text files, and
   `.sp` gives body and joint records. Gear ratios were checked against the setup files. These are relevant to the tyre and load model
   work, but they hold setup and geometry, not the tyre curves, so they do not identify grip.

4. **Alignment helper (`ghost_align.py`).** Aligns 63-byte records by a marker; it is for file structure, not for lap alignment, and
   it is not needed for our lap-distance work.

## What is not relevant

MAS archives, GMT mesh and material conversion, FXM and LMA containers, ISI and JCA encryption, media (audio, video, texture)
conversion, and the Race 07, GT Legends and rFactor content conversions. They help other tasks, not driving.

## Ideas to test (not started)

- Compare our logged heading and sideslip against the game's own replay heading for a driven session, with the 180-degree offset removed.
  Acceptance: sideslip sign agrees on straights and in the bend.
- Read the game's recorded time-trial ghosts for the Imola Maserati only as a steering reference. Record how the steering input relates
  to yaw and front-grip loss at turn-in, and never copy the path.

## Rules that apply here

- `CLAUDE.md` says not to read other GTR2 installs or tools folders on this machine. This review was an explicit exception requested by the
  user for this one folder. The reference-books exception in `CLAUDE.md` is separate.
- No file from the sibling is copied into this repository.
