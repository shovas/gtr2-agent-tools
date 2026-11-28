# Editing files: scripts, docs and game files

Read this before editing any file, especially CRLF scripts and game text or binary files. Moved verbatim from `CLAUDE.md`.

- **Editing scripts and docs safely (measured 2026-11-20):** several scripts are CRLF (`file scripts\x.py` says so). `sed -i` on this machine turns a whole CRLF file into LF (91 of 91 line endings on a test copy), and Python's default text mode does the same unless you pass `newline=''` to `open()` for both read and write. Use the Edit tool with a single-line `old_string` (it keeps CRLF), or a patch script written with the Write tool (no shell layer) that reads and writes bytes or `newline=''`. Never put `\n` escapes through a heredoc into a Python string: two layers eat one level of backslashes (a single `\n` becomes a real newline inside the string literal you meant to write). After every edit run `git diff --stat` (the diff must be only your lines) and a syntax check (`python -I -c "import ast;ast.parse(open(F,encoding='utf-8').read())"`).
- **Editing game text files:** `.gdb/.car/.hdc/.tyr/.dmg/.trk/.grd/.cam/.ddb` are CRLF text; `Config.ini`, `<profile>.PLR`, `raceresults.txt` have a NUL-byte header to preserve (use byte-preserving edits, `grep -a`); `.gtr` (MAS archive), `.bch`, `.hat`, `.aiw` are binary. Backups are named `<name>_<ext>_BAK_<YYMMDD>[_TAG]`. Autocrlf is off and `* -text` is set in git: never let line endings change.

## Working notes (game files)

- Content files (`.gdb`, `.txt`, `.AIW`, `.cam`, `.grd`, `.PLR`, `Config.ini`) are text and safe to edit/diff; `.gtr`, `.gmt`, `.dds`, `.LMA`, `.tyr`, `.dmg`, `.bik` etc. are mostly binary or tool-generated. Some `.txt` files in `Support/` use legacy (non-UTF-8) encoding – preserve bytes when editing.
- Commit to git after every successful change you are confident in. The whole install (~1.6 GB, ~4000 files, mostly binary) is tracked, so `git add` specific paths for routine changes. Autocrlf is off and the tracked `.gitattributes` sets `* -text` (plus text diffs for `Config.ini`, `*.PLR`, `raceresults.txt`); do not let line endings change.
- Adding a track or car generally means adding its folder under `Locations/` or `Teams/` **and** referencing it from a `.gdb` game mode; check an existing entry as the template.
