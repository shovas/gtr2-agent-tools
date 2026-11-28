# Numerical search and execution modes

Read this when writing a recurring test, sweep, benchmark or parameter search. Moved verbatim from `CLAUDE.md`.

## Numerical search and execution modes

- **Parameter search is bounded, never trial and error.** Set bounds from domain knowledge and measurements (widen them if the optimum lies outside). Bisect monotonic thresholds; bracket unimodal objectives (golden-section), using either only with evidence. Start coarse, then narrow. Stop when the interval or the next step is 1 percent or less of the parameter's scale, or the objective stops improving. Compare candidates under identical conditions, allowing for noise and interaction. Record every tested value, its measurement, the bounds and the best verified result.
- **Recurring automation** (tests, validation, diagnostics, benchmarks, sweeps) takes `--mode quick|normal|full`, default `normal`, with Quick ⊆ Normal ⊆ Full. Quick: up to 60 s (aim for 10 s), changed behaviour, critical invariants, smoke tests. Normal: up to 5 min, Quick plus edge cases, regressions and integration; the routine pre-commit check. Full: exhaustive and stress checks, run **only** on the user's explicit request, never from hooks, commits, pushes or fallbacks; a generic "test" or "verify" does not authorise Full. Every run reports its mode, duration, what ran and what was skipped. Use fixed seeds and record them with the reproduction command.
