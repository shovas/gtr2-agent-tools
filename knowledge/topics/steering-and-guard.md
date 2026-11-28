# Steering clamp and track-limit guard

- Fact: `--steer-clamp V LIMIT` (off by default) limits the pursuit command to ±LIMIT at speed V and above, on the main track. It bound on 80 samples exactly at ±0.35 in its run.
- Fact: the 51 escaping samples are the track-limit guard. It adds 0.15 × 4 = 0.60 to the command when all four tyres are off the road; −0.35 − 0.60 = −0.95, then −1.00.
- Fact: the guard is active by default, via the `--fast` preset (live mode), not opt-in.
- Fact: with the guard off, the 700 m excursion still occurs on four events in five laps; events last about 3.0 s against about 2.0 s with the guard (small sample).
- Status: the clamp verdict was rejected under its rules, but the test was confounded by the guard. A guard-off retest is pre-registered in `docs/controller-competition.md`.
