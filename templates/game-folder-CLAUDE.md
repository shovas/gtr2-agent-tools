# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this folder is

An installed copy of *GTR 2 - FIA GT Racing Game* (Steam app 8790; 32-bit Windows, DirectX 9) kept as a **git repository to track game state**. It is not source code: the binaries (`GTR2.exe`, `GTR2Config.exe`, `GTR2Dedicated.exe`, `net.dll`, ...) are closed-source and read-only for us. Work here is game content/config and keeping the folder launchable and tracked.

The automation lives in a **separate repository, `gtr2-agent-tools`** (ask the user where it is checked out; it is shareable and holds no game files). Its `CLAUDE.md` and `docs/` hold the rules and history. Read them before launching or testing anything. The tools find this folder through `GTR2_ROOT` or their `gtr2-tools.json`.

## Rules

- Also respect `AGENTS.md`, `GEMINI.md`, `.cursorrules` and any other agent-instruction file here or in the tools repo, with the same weight as this file.
- **Launch the game only through the tools' `scripts\gtr2-launch.ps1`** (never a bare `GTR2.exe`): it swaps this folder's `config\Documents-Config.ini` into the shared `%USERPROFILE%\Documents\GTR2`, runs the game with the compatibility-layer environment it needs, and restores `Documents\GTR2` afterwards. One GTR2 at a time.
- Per-machine files tracked here: `config\Documents-Config.ini` (adapter id, `VIDEOMODE`, relative data paths), `config\resolution-verified.json`, `_DocumentsGTR2\` (snapshot of the live `Documents\GTR2`, refreshed by the tools' `Tools\DocumentsGTR2.ps1 -Update`). Do not copy them to another machine: re-run the tools' setup instead. Never hard-code a `VIDEOMODE`; the tools choose GTR2Config entries by text.
- `UserData\<profile>\` is save data: do not delete or overwrite it by hand. A game run rewrites the profile, `ReplayData\` and `UserData\Log\`; after tests revert with `git checkout -- UserData ReplayData` and delete new untracked files (the tools' suite does this itself).
- `SDNDTG.DYN` (empty, unlocks championships) and `MovieFiles\SimBin.bik.disabled` (intro movie off) are intentional. `installscript.vdf` / `SteamInstallscript.vdf` are signed: do not edit.
- Text content (`.gdb`, `.txt`, `.AIW`, `.cam`, `.grd`, `.PLR`, `Config.ini`) can be edited byte-preservingly (CRLF; `Config.ini`, `.PLR` and `raceresults.txt` have a NUL-byte header); `.gtr`, `.gmt`, `.dds`, `.LMA`, `.tyr`, `.dmg`, `.bik` are binary. Autocrlf is off and `.gitattributes` sets `* -text`: never let line endings change.
- Commit confident changes (`git add` specific paths); never push unless asked. Adding a track or car means adding its folder under `GameData\Locations` or `GameData\Teams` and referencing it from a `.gdb` game mode; copy an existing entry.
- `Readme.txt` and `Support\` (EULA, dedicated server and hosting notes) are the original docs; read `Support\GTR2_dedicated_server.txt` and `GTR2_Server_Hosting.txt` before touching server setup.

<!-- gtr2-agent-tools: game-folder instructions v1 -->
