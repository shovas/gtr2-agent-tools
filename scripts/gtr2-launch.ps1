# Purpose: run GTR2.exe (or GTR2Config.exe) from this folder so that all game data stays here.
#   An unelevated GTR2 always reads Documents\GTR2\Config.ini (no command-line switch changes that). This launcher
#   temporarily puts this folder's config\Documents-Config.ini there (relative data paths), makes sure the empty
#   subfolders the game wants exist, runs the program, then restores Documents\GTR2 to exactly what it was.
#   A lock (Documents\GTR2.launcher.lock) keeps two launcher runs from overlapping; any running GTR2 blocks a start.
# Usage:   .\scripts\gtr2-launch.ps1 [-Program GTR2|GTR2Config] [-GameArgs '-trace=100'] [-KillAfter <sec>]
#                                    [-AdoptConfig] [-InitConfig] [-Restore] [-DryRun] [-Root <install>] [-Config <file>]
#   -KillAfter   stop the program after N seconds (tests); default waits until it exits
#   -AdoptConfig after the run, store the (relative-path-normalized) Documents Config.ini as the new local config
#                (use after changing video settings in GTR2Config)
#   -InitConfig  create the local config from the current Documents\GTR2\Config.ini and exit
#   -Restore     put back a leftover backup from an interrupted run
# Example: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gtr2-launch.ps1 -DryRun
param(
    [ValidateSet('GTR2', 'GTR2Config')][string]$Program = 'GTR2',
    [string[]]$GameArgs = @(),
    [int]$KillAfter = 0,
    [switch]$AdoptConfig, [switch]$InitConfig, [switch]$Restore, [switch]$DryRun,
    [switch]$Strict,        # restore Documents\GTR2 byte-identical to the backup, deleting any file created during the run (default: leave files that are not ours and report them)
    [int]$WaitOthers = 120, # seconds to wait for a GTR2 process this launcher did not start before restoring (then it leaves Documents alone and keeps the backup)
    [string]$Root = $(if ($env:GTR2_ROOT) { $env:GTR2_ROOT } elseif (Test-Path (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json')) { (Get-Content -Raw (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json') | ConvertFrom-Json).game_root } else { Split-Path $PSScriptRoot }),
    [string]$Config = '',
    [switch]$NoCompatLayer,   # do not set __COMPAT_LAYER for the game (by default it runs with DWM8And16BitMitigation, see below)
    [switch]$NoShell,   # start the program with CreateProcess (UseShellExecute=false) instead of Start-Process/ShellExecute (experiments: Windows applies its compatibility database on shell launches)
    [int]$WakeWait = 20,   # seconds to wait after waking a sleeping display before the game starts (see Wake-Display)
    [switch]$NoWakeDisplay,   # do not wake the display and keep it awake before the game starts (see Wake-Display)
    [switch]$Reap,          # only clean up after a dead or stuck launcher run (see Reap-Stale), then exit: 0 clean, 3 a live launcher run is active, 4 a GTR2 process that is not ours is running
    [string]$DocumentsDir = '',      # tests: use this folder instead of the real Documents
    [string[]]$ProcessNames = @('GTR2', 'GTR2Config', 'GTR2Dedicated'),   # tests: the process names that count as the game
    [string]$ExePath = ''   # run this exe instead of <Root>\<Program>.exe (experiments, e.g. an unflagged copy; Windows keys compatibility flags by exe path)
)
$ErrorActionPreference = 'Stop'
# The game crashes in VidMan::Enter (Direct3D start-up) when started from a path that has no Windows compatibility entry; the Steam install's path carries the
# DWM8And16BitMitigation layer. The same layer set as a process environment variable (nothing is written to the registry) fixes it, measured 2026-11-13.
if (-not $NoCompatLayer) { $env:__COMPAT_LAYER = 'DWM8And16BitMitigation' }
# A first start after the display went to sleep (Windows turns it off after 10 minutes without input by default) takes 10 to 20 s instead of 5: the graphics
# driver is busy that long creating the Direct3D device and the window stays white. Measured 2026-11-13: 13 to 14 min idle with the display asleep 13 to 20 s;
# with the display held awake 5.4 s; display asleep, woken and left 20 s before the start 6.3 s; woken only 2 s before the start 13 s. A forced 5 minute
# display-off (not Windows' own timeout) did not reproduce it. So the launcher asks Windows to keep the display on while it runs and, when the time without
# input is at least the display timeout (the display is asleep), wakes it with a 1 pixel mouse nudge and waits $WakeWait seconds before starting the game.
function Wake-Display {
    try {
        Add-Type -Namespace GtrPower -Name Native -ErrorAction SilentlyContinue -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint flags);
[DllImport("user32.dll")] public static extern void mouse_event(uint flags, int dx, int dy, uint data, UIntPtr extra);
[StructLayout(LayoutKind.Sequential)] public struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
[DllImport("user32.dll")] public static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
public static double IdleSeconds() { LASTINPUTINFO i = new LASTINPUTINFO(); i.cbSize = (uint)Marshal.SizeOf(typeof(LASTINPUTINFO)); GetLastInputInfo(ref i); return (uint)(Environment.TickCount - (int)i.dwTime) / 1000.0; }
'@
        $timeouts = @()   # the display-off timeouts of the active power plan, seconds (0 = never)
        foreach ($l in (powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE 2>$null)) { if ($l -match 'Power Setting Index:\s*0x([0-9a-fA-F]+)') { $v = [Convert]::ToInt64($matches[1], 16); if ($v -gt 0) { $timeouts += $v } } }
        $idle = [GtrPower.Native]::IdleSeconds()
        $asleep = $timeouts.Count -gt 0 -and $idle -ge (($timeouts | Measure-Object -Minimum).Minimum)
        [GtrPower.Native]::SetThreadExecutionState([uint32]2147483651) | Out-Null   # ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED: released when this script ends
        if ($asleep) {
            [GtrPower.Native]::mouse_event(1, 1, 0, 0, [UIntPtr]::Zero); [GtrPower.Native]::mouse_event(1, -1, 0, 0, [UIntPtr]::Zero)   # MOUSEEVENTF_MOVE wakes the display
            Say ("display was probably asleep (no input for {0:N0} s, display timeout {1} s): woke it, waiting {2} s before starting the game" -f $idle, (($timeouts | Measure-Object -Minimum).Minimum), $WakeWait)
            Start-Sleep -Seconds $WakeWait
        }
        else { Say ("display kept on while the launcher runs (no input for {0:N0} s)" -f $idle) }
    } catch { Say "could not check or wake the display: $($_.Exception.Message)" }
}
if (-not $Config) { $Config = Join-Path $Root 'config\Documents-Config.ini' }
$latin1 = [Text.Encoding]::GetEncoding(28591)   # one byte per char: keeps the NUL header and CRLFs intact
$my = if ($DocumentsDir) { $DocumentsDir } else { [Environment]::GetFolderPath('MyDocuments') }   # the real Documents, even if redirected
$docs = Join-Path $my 'GTR2'
$bak = Join-Path $my 'GTR2.launcher-backup'
$lockPath = Join-Path $my 'GTR2.launcher.lock'
$statePath = Join-Path $my 'GTR2.launcher.state'   # readable by others (the lock itself is held open exclusively): launcher pid and start time, then the game's
$paths = [ordered]@{ LOGDIR = 'USERDATA\LOG\'; REPLAYDIR = 'REPLAYDATA\'; TIMETRIALDIR = 'TIMETRIAL\'; DRIVINGSCHOOLDIR = 'GAMEDATA\DRIVINGSCHOOL\' }
$needDirs = 'GameData\DrivingSchool', 'ReplayData', 'TimeTrial', 'userdata\Log'

function Fail($m) { Write-Error $m; exit 1 }
function Say($m) { Write-Host $m }
function Act($m, [scriptblock]$do) { if ($DryRun) { Say "would: $m" } else { Say $m; & $do } }
function Get-Descendants([int]$rootPid) {   # processes started by $rootPid (children, grandchildren; orphans keep their parent id)
    $all = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId); $found = @(); $queue = @($rootPid)
    while ($queue) { $next = @(); foreach ($q in $queue) { foreach ($c in ($all | Where-Object ParentProcessId -eq $q)) { if ($found -notcontains $c.ProcessId) { $found += $c.ProcessId; $next += $c.ProcessId } } }; $queue = $next }
    $found
}
function Stop-Tree([int]$rootPid) {   # stop OUR program and what it started, never another session's GTR2 by name
    foreach ($id in @(Get-Descendants $rootPid) + $rootPid) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
}
function Normalize-Config([string]$path) {   # text of a config with the four data paths made relative
    $t = [IO.File]::ReadAllText($path, $latin1)
    foreach ($k in $paths.Keys) { $t = [regex]::Replace($t, "(?m)^$k=[^\r\n]*", "$k=$($paths[$k])") }   # [^\r\n]*, not .*: '.' would also eat the CR and leave LF-only lines
    $t
}
function Tree($d) {   # relative path -> sha256 (files) / '<dir>' (folders)
    $m = @{}
    if (Test-Path $d) {
        Get-ChildItem $d -Recurse -Force | ForEach-Object {
            $rel = $_.FullName.Substring($d.Length).TrimStart('\')
            $m[$rel] = if ($_.PSIsContainer) { '<dir>' } else { (Get-FileHash $_.FullName -Algorithm SHA256).Hash }
        }
    }
    $m
}
$script:installedTree = $null   # Documents\GTR2 as the launcher left it just before the program started
function Report-Changes {   # what the run did to Documents\GTR2 (anything but Config.ini/sysinfo.txt means data escaped our folder)
    if ($bootstrap -or $null -eq $script:installedTree -or -not (Test-Path $docs)) { return }   # a bootstrap run is expected to create the whole tree
    $now = Tree $docs; $changed = @()
    foreach ($k in $now.Keys) { if (-not $script:installedTree.ContainsKey($k)) { $changed += "created   $k" } elseif ($now[$k] -ne $script:installedTree[$k]) { $changed += "modified  $k" } }
    foreach ($k in $script:installedTree.Keys) { if (-not $now.ContainsKey($k)) { $changed += "deleted   $k" } }
    $own = '^\w+\s+(Config\.ini|sysinfo\.txt|UserData\\Log\\weather\.txt)$'   # weather.txt: the game writes a fresh forecast there at every race session start, whatever LOGDIR says
    $expected = $changed | Where-Object { $_ -match $own }; $escaped = $changed | Where-Object { $_ -notmatch $own }
    if ($expected) { Say "Documents\GTR2 during the run (expected, restored below): $(($expected | ForEach-Object { ($_ -split '\s+')[0..1] -join ' ' }) -join ', ')" }
    if ($escaped) { Say "WARNING: the run touched Documents\GTR2 beyond Config.ini/sysinfo.txt (restored below):"; $escaped | ForEach-Object { Say "   $_" } }
    else { Say 'nothing else touched Documents\GTR2: all data stayed in the install folder' }
}
function Restore-Safe {   # (a bootstrap run removed the whole folder, so it is restored completely)
    if (Test-Path (Join-Path $bak 'BOOTSTRAP')) { Restore-Docs; return @() }   # default: put back only what the launcher itself changed (Config.ini, sysinfo.txt, folders it added); leave and report anything else
    $absent = Test-Path (Join-Path $bak 'ABSENT'); $src = Join-Path $bak 'GTR2'
    foreach ($f in 'Config.ini', 'sysinfo.txt', 'UserData\Log\weather.txt') {
        $d = Join-Path $docs $f; $s = Join-Path $src $f
        if (-not $absent -and (Test-Path $s)) { if (-not (Test-Path $d) -or (Get-FileHash $d).Hash -ne (Get-FileHash $s).Hash) { [IO.File]::Copy($s, $d, $true) } }
        elseif (Test-Path $d) { Remove-Item $d -Force }
    }
    $cands = @(); foreach ($n in $needDirs) { $acc = ''; foreach ($seg in ($n -split '\\')) { $acc = if ($acc) { "$acc\$seg" } else { $seg }; $cands += $acc } }
    foreach ($c in ($cands | Sort-Object -Unique | Sort-Object { $_.Length } -Descending)) {
        $p = Join-Path $docs $c
        if (($absent -or -not (Test-Path (Join-Path $src $c))) -and (Test-Path $p) -and -not (Get-ChildItem $p -Force)) { Remove-Item $p -Force }
    }
    if ($absent -and (Test-Path $docs) -and -not (Get-ChildItem $docs -Force)) { Remove-Item $docs -Force }
    $left = @(); if (Test-Path $docs) { $left = @(Get-ChildItem $docs -Recurse -File -Force | ForEach-Object { $_.FullName.Substring($docs.Length).TrimStart('\') } | Where-Object { -not (Test-Path (Join-Path $src $_)) -or $absent }) }
    Remove-Item $bak -Recurse -Force
    $left
}
function Restore-Docs {   # -Strict: make Documents\GTR2 identical to the backup (or absent, if it was absent), deleting anything else
    if (Test-Path (Join-Path $bak 'ABSENT')) {
        if (Test-Path $docs) { Remove-Item $docs -Recurse -Force }
    } else {
        $src = Join-Path $bak 'GTR2'
        if (-not (Test-Path $docs)) { New-Item -ItemType Directory $docs | Out-Null }
        $want = Tree $src; $have = Tree $docs
        foreach ($k in ($have.Keys | Sort-Object { $_.Length } -Descending)) { if (-not $want.ContainsKey($k)) { Remove-Item (Join-Path $docs $k) -Recurse -Force -ErrorAction SilentlyContinue } }
        foreach ($k in ($want.Keys | Sort-Object { $_.Length })) {
            $s = Join-Path $src $k; $d = Join-Path $docs $k
            if ($want[$k] -eq '<dir>') { if (-not (Test-Path $d)) { New-Item -ItemType Directory $d | Out-Null } }
            elseif (-not $have.ContainsKey($k) -or $have[$k] -ne $want[$k]) { [IO.File]::Copy($s, $d, $true) }
        }
        $diff = Compare-Object @((Tree $src).GetEnumerator() | % { "$($_.Key)=$($_.Value)" }) @((Tree $docs).GetEnumerator() | % { "$($_.Key)=$($_.Value)" })
        if ($diff) { Fail "restore verification failed; backup kept at $bak" }
    }
    Remove-Item $bak -Recurse -Force
}

function Proc-Alive($id, $startIso) {   # is this process (same pid AND same start time, so a reused pid does not count) still running?
    if (-not $id) { return $false }
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if (-not $p) { return $false }
    if ($startIso) { try { return ($p.StartTime.ToUniversalTime().ToString('o') -eq [string]$startIso) } catch { return $true } }
    $true
}
function Write-State($prog) {
    $me = Get-Process -Id $PID
    $o = [ordered]@{ launcherPid = $PID; launcherStart = $me.StartTime.ToUniversalTime().ToString('o'); at = (Get-Date).ToUniversalTime().ToString('o'); programPid = $null; programStart = $null }
    if ($prog) { $o.programPid = $prog.Id; $o.programStart = $prog.StartTime.ToUniversalTime().ToString('o') }
    [IO.File]::WriteAllText($statePath, ($o | ConvertTo-Json), $latin1)
}
function Get-State { if (Test-Path $statePath) { try { [IO.File]::ReadAllText($statePath, $latin1) | ConvertFrom-Json } catch { $null } } }
function Game-Procs { @(Get-Process $ProcessNames -ErrorAction SilentlyContinue) }
function Reap-Stale {   # after a launcher run that died or got stuck: returns 'clean' (nothing left, or cleaned up), 'active' (a live launcher run owns the lock) or 'foreign' (a game process that is not ours is running)
    $st = Get-State
    if ($st -and $st.launcherPid -ne $PID -and (Proc-Alive $st.launcherPid $st.launcherStart)) {
        $age = ((Get-Date) - [datetime]$st.at).TotalSeconds
        if ((Proc-Alive $st.programPid $st.programStart) -or (Game-Procs).Count -or $age -lt 45) { return 'active' }
        Say "launcher $($st.launcherPid) has had no game running for $([int]$age) s: stopping it"
        Stop-Tree $st.launcherPid; Start-Sleep 1
    }
    if ($st -and (Proc-Alive $st.programPid $st.programStart)) { Say "stopping the game $($st.programPid) (its launcher is gone)"; Stop-Tree $st.programPid; Start-Sleep 1 }
    if ((Game-Procs).Count) { return 'foreign' }
    if (Test-Path $bak) { Say 'stale launcher backup: restoring Documents\GTR2'; $left = Restore-Safe; if ($left) { Say "left in place (not ours): $($left -join ', ')" } }
    Remove-Item $lockPath, $statePath -Force -ErrorAction SilentlyContinue
    'clean'
}
if ($Reap) { $r = Reap-Stale; Say "reap: $r"; exit @{ clean = 0; active = 3; foreign = 4 }[$r] }

if ($InitConfig) {
    if (-not (Test-Path "$docs\Config.ini")) { Fail "no $docs\Config.ini to copy from" }
    Act "write $Config from $docs\Config.ini with relative data paths" { New-Item -ItemType Directory -Force (Split-Path $Config) | Out-Null; [IO.File]::WriteAllText($Config, (Normalize-Config "$docs\Config.ini"), $latin1) }
    exit 0
}
$bootstrap = $false
if (-not (Test-Path $Config)) {   # first use of these tools on this machine: make the local config ourselves
    if ($Program -eq 'GTR2' -and -not $Restore) {
        $bootstrap = $true
        Say "no local config yet: bootstrap run. Any existing $docs is copied aside and removed so the game starts brand new and writes its own default config; the original is put back afterwards (a verified restore). The result becomes this folder's own config, so this happens once."
    }
    else { Fail "missing $Config (create it with -InitConfig, or run the game once without -Program)" }
}
$exe = if ($ExePath) { $ExePath } else { Join-Path $Root "$Program.exe" }
if (-not (Test-Path $exe)) { Fail "missing $exe" }
if (-not $DryRun) {
    $reaped = Reap-Stale
    if ($reaped -eq 'active') { Fail 'another launcher run is active (see GTR2.launcher.state)' }
}
if ((Game-Procs).Count) { Fail 'GTR2, GTR2Config or GTR2Dedicated is already running and was not started by this launcher (another session?). Close it first.' }
if ((Test-Path $bak) -and -not $Restore) { Fail "leftover backup from an interrupted run: $bak. Run with -Restore to put it back first." }
if ($Restore -and -not (Test-Path $bak)) { Say 'Nothing to restore.'; exit 0 }

$lock = $null
if (-not $DryRun) {
    try { $lock = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None') }
    catch { Fail 'another launcher run holds the lock (GTR2.launcher.lock).' }
    $b = $latin1.GetBytes("pid=$PID root=$Root $(Get-Date -Format s)"); $lock.SetLength(0); $lock.Write($b, 0, $b.Length); $lock.Flush()
    Write-State $null
}
try {
    if ($Restore) { Act "restore Documents\GTR2 from $bak" { if ($Strict) { Restore-Docs } else { $left = Restore-Safe; if ($left) { Say "left in place (use -Strict to remove): $($left -join ', ')" } } }; return }

    # 1. back up the shared folder (or note that it is absent)
    if (Test-Path $docs) { Act "back up $docs -> $bak\GTR2" { New-Item -ItemType Directory $bak | Out-Null; Copy-Item $docs "$bak\GTR2" -Recurse -Force } }
    else { Act "note that $docs is absent" { New-Item -ItemType Directory $bak | Out-Null; New-Item -ItemType File "$bak\ABSENT" | Out-Null } }
    if ($bootstrap -and -not $DryRun) {   # the game only writes its default setup when Documents\GTR2 is absent; BOOTSTRAP makes every later restore (also -Restore / -Reap) put the whole folder back
        New-Item -ItemType File "$bak\BOOTSTRAP" -Force | Out-Null
        if (Test-Path $docs) { Say "bootstrap: set aside the existing $docs (copy kept in $bak\GTR2)"; Remove-Item $docs -Recurse -Force }
    }
    try {
        # 2. our config in place, plus the empty folders the game needs (missing ones make it rebuild the tree and reset the paths)
        if ($bootstrap) { Say 'bootstrap: leaving Documents\GTR2 for the game to create' }
        else { Act "install $Config as $docs\Config.ini and ensure empty subfolders" {
            New-Item -ItemType Directory -Force $docs | Out-Null
            foreach ($d in $needDirs) { New-Item -ItemType Directory -Force (Join-Path $docs $d) | Out-Null }
            [IO.File]::Copy($Config, "$docs\Config.ini", $true)
        } }
        if (-not $DryRun) { $script:installedTree = Tree $docs }
        # 3. run
        if ($DryRun) { Say "would: run $exe $($GameArgs -join ' ') in $Root$(if ($KillAfter) { " (stop after $KillAfter s)" })" }
        else {
            if (-not $NoWakeDisplay) { Wake-Display }
            Say "running $exe $($GameArgs -join ' ')"
            $sp = @{ FilePath = $exe; WorkingDirectory = $Root; PassThru = $true }
            if ($GameArgs) { $sp.ArgumentList = $GameArgs }
            if ($NoShell) {   # plain CreateProcess (like a Python subprocess) instead of ShellExecute, which is what Start-Process uses
                $psi = New-Object Diagnostics.ProcessStartInfo $exe; $psi.WorkingDirectory = $Root; $psi.UseShellExecute = $false
                if ($GameArgs) { $psi.Arguments = $GameArgs -join ' ' }
                $p = [Diagnostics.Process]::Start($psi)
            }
            else { $p = Start-Process @sp }
            Write-State $p
            if ($bootstrap) {   # the game creates Documents\GTR2 and writes a default Config.ini, then starts GTR2Config itself: wait for the config, then stop OUR tree
                $deadline = (Get-Date).AddSeconds(60); $got = $false
                while ((Get-Date) -lt $deadline) { if (Test-Path "$docs\Config.ini") { Start-Sleep 3; $got = $true; break }; Start-Sleep 1 }
                Stop-Tree $p.Id; Start-Sleep 2
                if (-not $got) { Fail 'bootstrap: the game did not create Documents\GTR2\Config.ini within 60 s' }
            }
            elseif ($KillAfter) { if (-not $p.WaitForExit($KillAfter * 1000)) { Say "stopping after $KillAfter s (only the process this launcher started, and its children)"; Stop-Tree $p.Id; Start-Sleep 2 } }
            else { $p.WaitForExit(); Start-Sleep 1; while (@(Get-Descendants $p.Id).Count) { Start-Sleep 2 } }   # GTR2Config can be started by the game; wait only for OUR children
            # 4. what the game did to Config.ini
            if ($bootstrap) {
                New-Item -ItemType Directory -Force (Split-Path $Config) | Out-Null; [IO.File]::WriteAllText($Config, (Normalize-Config "$docs\Config.ini"), $latin1)
                Say "bootstrap: wrote $Config from the game's default config. It is fullscreen (VIDEOMODE 0 / WINDOWEDMODE 0) and NOT safe to run: next run scripts\gtr2-set-resolution.ps1 -Resolution 1280x720"
            }
            elseif (Test-Path "$docs\Config.ini") {
                $new = Normalize-Config "$docs\Config.ini"; $cur = [IO.File]::ReadAllText($Config, $latin1)
                if ($new -ne $cur) {
                    if ($AdoptConfig) { [IO.File]::WriteAllText($Config, $new, $latin1); Say "adopted the changed Config.ini into $Config (review with git diff)" }
                    else { Say 'note: the run changed Config.ini (not adopted; use -AdoptConfig after changing settings in GTR2Config)' }
                }
            }
        }
    }
    finally {
        # 5. always put Documents\GTR2 back
        if (-not $DryRun -and (Test-Path $bak)) {
            # Another session may have started its own GTR2 while ours ran: never restore underneath a running game; wait, then give up safely.
            $deadline = (Get-Date).AddSeconds($WaitOthers); $announced = $false
            while ((Game-Procs) -and (Get-Date) -lt $deadline) {
                if (-not $announced) { Say "another GTR2 process is running (not started by this launcher); waiting up to $WaitOthers s before restoring Documents\GTR2"; $announced = $true }
                Start-Sleep 2
            }
            if (Game-Procs) {
                Report-Changes
                Say "NOT restoring: another GTR2 process is still running. Documents\GTR2 still holds this folder's Config.ini and the backup is kept at $bak. When that process has ended run: scripts\gtr2-launch.ps1 -Restore"
                $script:notRestored = $true
            }
            else {
                Report-Changes; Say 'restoring Documents\GTR2'
                if ($Strict -or $bootstrap) { Restore-Docs; Say 'restored and verified (byte-identical to before)' }
                else { $left = Restore-Safe; if ($left) { Say "restored Config.ini/sysinfo.txt; LEFT IN PLACE (not ours to delete; use -Strict to remove): $($left -join ', ')" } else { Say 'restored and verified (identical to before)' } }
            }
        }
    }
}
finally { if ($lock) { $lock.Close(); Remove-Item $lockPath, $statePath -Force -ErrorAction SilentlyContinue } }
if ($script:notRestored) { exit 2 }
