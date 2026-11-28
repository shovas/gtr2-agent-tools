# Script conventions and deterministic tooling

Read this before writing or changing any script. Moved verbatim from `CLAUDE.md`.

## Prefer deterministic local tooling over inference

Goal: minimize AI token usage and spend. Inference is the expensive, non-repeatable path; a script is cheap, repeatable, and verifiable. Use inference for judgment and code for everything mechanical.

### Before starting any task

1. Check `scripts/README.md` for an existing script that does the job. If one exists, run it.
2. If not, check whether a standard local tool does it: `rg`, `sed`, `awk`, `jq`, `find`, `git`, the project's formatter, linter, test runner, and build tools.
3. Only work through the task directly if neither applies.

### When to write a script

Write a script when the task is deterministic (same input, same output) and at least one of these is true:

- It is likely to recur.
- It touches more than a handful of files or records.
- Doing it by hand would mean reading large files into context.

Typical cases: bulk renames, mechanical refactors, format conversions, data extraction, report generation, log analysis, validation checks, scaffolding.

Do not script tasks that need judgment (design decisions, ambiguous requirements, prose, code review), or one-off tasks where writing the script costs more than doing the work.

### Script conventions

- Save to `scripts/` with a descriptive name and a header comment giving purpose, usage, and an example.
- Take inputs as arguments; no hardcoded paths.
- Make scripts idempotent, with a `--dry-run` flag for anything that modifies or deletes.
- Exit non-zero with a clear message on failure.
- Add a one-line entry to `scripts/README.md`.
- Dependencies are allowed when they earn their place (more information or options than the standard library gives): pin the exact version in `scripts/requirements.txt`, install into `scripts/.venv`, and say in the script header what the dependency adds. Prefer the standard library when it is equally good, and keep optional extras optional (import inside a try) so a tool still runs without them.

### Keep context small

- Search and filter instead of reading whole files.
- Limit command output (`head`, `tail`, `wc`, `jq`) and summarize rather than dump.
- Verify with deterministic checks (tests, `diff`, lint, exit codes) rather than re-reading output.
- Do not spawn subagents for work a command can do.

### Close the loop
