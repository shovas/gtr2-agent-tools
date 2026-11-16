# Publishing this repository (privacy, safety, what may be pushed)

Rules for every agent and every person who pushes this repository to GitHub (or any other host). `CLAUDE.md` points here. Nothing in
this file is optional.

## The one rule

**Never push without the user's explicit go-ahead for that push, given in the current conversation.** An earlier "yes" does not
cover a later push; a request to commit is not a request to push. Never force-push, rewrite published history, change the remote,
change the repository's visibility or enable GitHub features (Pages, Actions, releases) without a separate explicit yes naming that
action.

## What may be published

- Our own code, tests and notes: `scripts/`, `docs/`, `config/` (weather presets), `templates/`, `Tools/`, `README.md`,
  `DEPENDENCIES.md`, `CLAUDE.md`, `AGENTS.md`, `CHANGES.md`, `LICENSE.md`.
- Reference pictures for page recognition under `scripts/gtr2_ui/baselines/1280x720/` (see "Pictures" below).
- Findings about how the game behaves, written in our own words, with measured numbers.

## What must never be published

1. **Game files or anything derived from them wholesale:** executables, DLLs, `.gtr`/`.mas` archives, `.gmt`/`.dds` meshes and
   textures, `.bik` movies, `.tyr/.hdc/.car/.aiw` copies, audio, `Config.ini`, `.PLR` profiles, replays, crash dumps. The tools read
   the user's own install; they never copy it. The README says "this repository contains no game files": keep that true.
2. **Personal details:** real names (other than the public GitHub handle the user chose), e-mail addresses other than a GitHub
   `noreply` address, absolute paths that contain a user name (`C:\Users\<name>\...`), machine names, adapter or hardware serial
   ids, IP addresses, player names from the game (profile names in screenshots, lists, logs).
3. **Secrets:** tokens, keys, passwords, the nav server token file, `gtr2-tools.json` (per machine, git-ignored), anything under
   `scripts/gtr2_ui/runs/` (logs, crash reports, results), and the whole of `scripts/.venv/`.
4. **Other people's content:** text or tables copied from the game's manuals, forums, other mods or other tool repositories without a
   licence that allows it. Link instead.
5. **Anything private the user said in conversation** (their name, plans, accounts): never in a file, a commit message or a PR.

Write examples with placeholders: `<game folder>`, `<profile>`, `<user>`, relative paths.

## Commit hygiene (applies to every commit, pushed or not)

- Subject starts with a changelog tag (`highlight:`, `improve:`, `fix:`, `docs:`, `chore:`; see `CLAUDE.md`).
- Commit trailers may carry the tool attribution line the harness asks for; they contain only the tool's own `noreply` address.
- The author identity of published commits should be the GitHub `noreply` address (`<id>+<handle>@users.noreply.github.com`), not a
  personal address. Set it before committing: `git config user.email <noreply address>`. Whatever is already pushed stays public;
  changing it means rewriting history, which needs the explicit yes above.
- Add specific paths (`git add <path>`), never `git add -A` or `git add .`, and read `git status` before every commit.
- Never commit a file you have not read when it came from outside this repository.

## Pictures

`scripts/gtr2_ui/baselines/` holds screenshots of the game's own screens, used to recognise pages. They are the largest privacy and
licence exposure of this repository, so:

- Only the shipped 1280x720 set is published; `baselines/local/` is per machine and must stay out of git except what the
  `.gitignore` exception names (and duplicates of the shipped set should be removed).
- Header and list names are painted out and masked (`pagerec.NAME_BOX`, `scrub_name`). **Look at every new picture before it is
  committed:** no player name, no profile name, no path in a title bar, no desktop, no notifications, no other window.
- Whether publishing screenshots of the game's UI is acceptable is the owner's decision (the pictures are the publishers' artwork).
  The owner decides once; agents do not add pictures beyond the existing set without asking.

## Procedure before a push (an agent does all of this, then waits for the yes)

1. `git status` is clean or only has files that belong in the push; run the offline tests
   (`scripts\.venv\Scripts\python.exe -I scripts\test_nav_guards.py`).
2. Run the scanner: `python -I scripts\publish-check.py` (commits not yet on the remote and every tracked file) and, before a first
   public release or a visibility change, `python -I scripts\publish-check.py --all-history`. Exit code 1 means a BLOCK: do not
   push; fix (a removed line is not enough if the string is in history: say so and ask). REVIEW items need a human decision.
3. Regenerate `CHANGES.md` (`scripts\changelog.py --write`) and commit it as `changelog:`.
4. Show the user: the commits that would be pushed (`git log origin/main..HEAD --oneline`), the scanner's output, the remote URL and
   branch, and whether the repository is public or private. Ask for the final approval in those words ("push N commits to
   <remote>/<branch>: yes?").
5. Only after a clear yes: `git push` (plain, to the branch named). Report the result. Do not tag, release or open pull requests
   unless asked.

## If something sensitive was pushed

Stop. Tell the user what and where. Do not try to fix it on your own: removing it from the latest commit does not remove it from
history or from forks and caches. The user decides about rewriting history (force-push), rotating anything secret and contacting the
host; offer the steps, do not run them.

## What the scanner cannot see

Names inside screenshots, private facts in prose that no pattern matches, and whether a picture or a document is allowed to be
public. Those are the reviewer's job (items marked REVIEW), which is why a human approves every push.
