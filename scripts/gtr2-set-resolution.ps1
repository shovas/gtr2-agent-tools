# Purpose: choose the game's resolution by its TEXT (e.g. "1280 x 720  32 bit") in GTR2Config instead of a machine-specific
#   VIDEOMODE number, store the result in config\Documents-Config.ini, and PROVE it by launching the game and measuring the window.
#   VIDEOMODE is an index into the graphics card's mode list and VIDEOGUID names the card, so neither can be copied between PCs.
#   The dialog-saved index is not always right (on 2026-11-10 GTR2Config's list had 23 entries and saved 18 for "1280 x 720 32 bit",
#   which made the game switch the whole display instead of opening a window; 72 worked), hence the verification launch.
#   GTR2Config runs through scripts\gtr2-launch.ps1, so the shared Documents\GTR2 is backed up and restored.
# Usage:   .\scripts\gtr2-set-resolution.ps1 -List
#          .\scripts\gtr2-set-resolution.ps1 -Resolution 1280x720 [-Bits 32] [-Refresh 60] [-DryRun] [-NoVerify] [-Force]
#          .\scripts\gtr2-set-resolution.ps1 -Resolution 1280x720 -VideoMode 72     (write that index directly, then verify)
#   -List        print every mode GTR2Config offers (and whether it fits on this screen as a window), change nothing
#   -Status      read-only: compare config, the last verified launch (config\resolution-verified.json), the display scale and this
#                screen; launches nothing; exit 0 only if windowed, verified for this config, same scale, and the window fits
#   -Scale       pretend the display scale is N (1.25 = 125%) for fit checks; the detected system scale is used otherwise
#   -DryRun      set the dialog, check what it shows, press Cancel (nothing adopted)
#   -VideoMode   skip the dialog and test this VIDEOMODE index for -Resolution (windowed); expert override only: the index is valid just for the compatibility-layer setting it was found under (see CLAUDE.md, crash dumps); prefer the dialog route, which reads the options and selects by text
#   -Dropdowns   list every drop-down GTR2Config shows (control id, label, current choice, all options) and exit; nothing is saved
#   -Shader      choose the Shader Level drop-down by its text (regex on the option, e.g. -Shader 'Level 0'); see -Dropdowns for the options
#   -Select      choose any drop-down by its text: -Select 1203='^60' ('id=regex', repeatable); options are READ from the dialog, never picked by position
#   -NoVerify    skip the ~30 s verification launch (window must open at exactly WxH and leave the desktop resolution alone)
#   -Fullscreen  untick Windowed Mode (switches the display, so it also needs -Force and cannot be verified here)
#   -Force       allow a window that does not fit the work area, or fullscreen
# On any failure the previous config\Documents-Config.ini is put back. Exit code 1 on failure.
# Example: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gtr2-set-resolution.ps1 -Resolution 1280x720 -VideoMode 72
param(
    [string]$Resolution = '', [ValidateSet(16, 32)][int]$Bits = 32, [string]$Refresh = '', [int]$VideoMode = 0, [switch]$Dropdowns, [string]$Shader = '', [string[]]$Select = @(),
    [switch]$Fullscreen, [switch]$List, [switch]$Status, [switch]$DryRun, [switch]$Force, [switch]$NoVerify, [switch]$NoCompatLayer, [double]$Scale = 0,
    [string]$Root = $(if ($env:GTR2_ROOT) { $env:GTR2_ROOT } elseif (Test-Path (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json')) { (Get-Content -Raw (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json') | ConvertFrom-Json).game_root } else { Split-Path $PSScriptRoot })
)
$ErrorActionPreference = 'Stop'
$latin1 = [Text.Encoding]::GetEncoding(28591)
function Fail($m) { Write-Error $m; exit 1 }
if (-not $Resolution -and -not $List -and -not $Status -and -not $Dropdowns) {   # default from the setup file
    $tc = Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json'
    if (Test-Path $tc) { $r = (Get-Content -Raw $tc | ConvertFrom-Json).resolution; if ($r) { $Resolution = $r } }
}
if (-not $Shader -and -not $List -and -not $Status -and -not $Dropdowns) {   # shader level from the setup file too
    $tc = Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json'
    if (Test-Path $tc) { $r = (Get-Content -Raw $tc | ConvertFrom-Json).shader; if ($r) { $Shader = $r } }
}
if (-not $List -and -not $Status -and -not $Dropdowns -and -not $Resolution) { Fail 'give -Resolution WxH (for example 1280x720), -List, -Dropdowns or -Status' }
if ($Resolution -and $Resolution -notmatch '^\s*(\d+)\s*[xX]\s*(\d+)\s*$') { Fail "bad -Resolution '$Resolution' (use WxH)" }
$wantW = $null; $wantH = $null
if ($Resolution) { $wantW = [int]$Matches[1]; $wantH = [int]$Matches[2] }
if ($Fullscreen -and -not $Force) { Fail 'fullscreen switches the display mode; add -Force if you really want it' }
if ($VideoMode -and -not $Resolution) { Fail '-VideoMode needs -Resolution (the size to verify)' }
if ($VideoMode -and $Fullscreen) { Fail '-VideoMode is only for windowed mode' }
$cfgPath = Join-Path $Root 'config\Documents-Config.ini'
if (-not (Test-Path $cfgPath)) { Fail "missing $cfgPath (create it with: scripts\gtr2-launch.ps1 -InitConfig)" }
$cfgBytes = [IO.File]::ReadAllBytes($cfgPath)
function Restore-Config { [IO.File]::WriteAllBytes($cfgPath, $cfgBytes) }
$recPath = Join-Path $Root 'config\resolution-verified.json'

Add-Type -AssemblyName System.Windows.Forms
Add-Type @'
using System;using System.Text;using System.Collections.Generic;using System.Runtime.InteropServices;
public class GtrWin {
  public delegate bool EP(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumChildWindows(IntPtr p, EP f, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetDlgCtrlID(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern IntPtr SendMessage(IntPtr h, int m, IntPtr w, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern IntPtr SendMessage(IntPtr h, int m, IntPtr w, StringBuilder l);
  [StructLayout(LayoutKind.Sequential)] public struct R { public int l, t, r, b; }
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out R r);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Auto)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetWindow(IntPtr h, uint cmd);
  public static string Cls(IntPtr h) { var s = new StringBuilder(64); GetClassName(h, s, 64); return s.ToString(); }
  public static string Txt(IntPtr h) { var s = new StringBuilder(256); GetWindowText(h, s, 256); return s.ToString(); }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern uint GetDpiForSystem();
  public static Dictionary<int, IntPtr> Controls(IntPtr p) { var d = new Dictionary<int, IntPtr>(); EnumChildWindows(p, (h, l) => { d[GetDlgCtrlID(h)] = h; return true; }, IntPtr.Zero); return d; }
}
'@
[GtrWin]::SetProcessDPIAware() | Out-Null   # real pixel sizes
$CB_GETCOUNT = 0x146; $CB_GETCURSEL = 0x147; $CB_GETLBTEXT = 0x148; $WM_KEYDOWN = 0x100; $WM_KEYUP = 0x101; $BM_GETCHECK = 0xF0; $BM_CLICK = 0xF5
$wa = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
# GTR2 is not DPI aware: at 125% / 150% display scaling Windows enlarges its whole window (this process is DPI aware, so the work area
# below is in real pixels). -Scale overrides the detected factor for what-if checks. Only 100% has been tried on real hardware.
$dpiScale = if ($Scale -gt 0) { $Scale } else { try { [GtrWin]::GetDpiForSystem() / 96.0 } catch { 1.0 } }
function Fits($w, $h) { [math]::Ceiling(($w + 6) * $dpiScale) -le $wa.Width -and [math]::Ceiling(($h + 29 + 6) * $dpiScale) -le $wa.Height }   # window = client + 6 px borders + 29 px title bar, times the scale
$scaleText = '{0:P0}' -f $dpiScale
function Squash($s) { ($s -replace '\s+', ' ').Trim() }
function Items($h) {
    $n = [GtrWin]::SendMessage($h, $CB_GETCOUNT, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32()
    for ($i = 0; $i -lt $n; $i++) { $sb = New-Object Text.StringBuilder 128; [GtrWin]::SendMessage($h, $CB_GETLBTEXT, [IntPtr]$i, $sb) | Out-Null; Squash $sb.ToString() }
}
function Label-Of($h) {   # the text of the nearest static control before this one in the dialog's order (GTR2Config puts a label before each drop-down)
    $p = [GtrWin]::GetWindow($h, 3)
    for ($i = 0; $i -lt 6 -and $p -ne [IntPtr]::Zero; $i++) { if ([GtrWin]::Cls($p) -eq 'Static' -and [GtrWin]::Txt($p)) { return (Squash ([GtrWin]::Txt($p))) }; $p = [GtrWin]::GetWindow($p, 3) }
    ''
}
function Combos($ctl) { $ctl.GetEnumerator() | Where-Object { [GtrWin]::SendMessage($_.Value, $CB_GETCOUNT, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32() -gt 0 } | Sort-Object Key }   # any control that answers CB_GETCOUNT with items, whatever its window class
function Current($h) { [GtrWin]::SendMessage($h, $CB_GETCURSEL, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32() }
function Select-Item($h, [string]$pattern) {   # arrow keys (CB_SETCURSEL does not take effect in this dialog); returns the chosen text or $null
    $items = @(Items $h); $target = -1
    for ($i = 0; $i -lt $items.Count; $i++) { if ($items[$i] -match $pattern) { $target = $i; break } }
    if ($target -lt 0) { return $null }
    for ($k = 0; $k -lt ($items.Count * 2) -and (Current $h) -ne $target; $k++) {
        $vk = if ((Current $h) -lt $target) { 0x28 } else { 0x26 }
        [GtrWin]::SendMessage($h, $WM_KEYDOWN, [IntPtr]$vk, [IntPtr]0) | Out-Null; [GtrWin]::SendMessage($h, $WM_KEYUP, [IntPtr]$vk, [IntPtr]0) | Out-Null; Start-Sleep -Milliseconds 40
    }
    Start-Sleep -Milliseconds 250
    if ((Current $h) -eq $target) { $items[$target] } else { $null }
}
function Get-Descendants([int]$rootPid) {
    $all = @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId); $found = @(); $queue = @($rootPid)
    while ($queue) { $next = @(); foreach ($q in $queue) { foreach ($c in ($all | Where-Object ParentProcessId -eq $q)) { if ($found -notcontains $c.ProcessId) { $found += $c.ProcessId; $next += $c.ProcessId } } }; $queue = $next }
    $found
}
function Stop-Tree([int]$rootPid) { foreach ($id in @(Get-Descendants $rootPid) + $rootPid) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue } }
function Cfg-Value($name) { [regex]::Match($latin1.GetString([IO.File]::ReadAllBytes($cfgPath)), "(?m)^$name=([^\r\n]*)").Groups[1].Value }

# Launch the game for ~14 s through the launcher and measure it: a window whose client is exactly WxH, desktop resolution unchanged.
function Test-Launch {
    $before = [Windows.Forms.Screen]::PrimaryScreen.Bounds
    $lv = Start-Process powershell -PassThru -WindowStyle Hidden -ArgumentList (@('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'gtr2-launch.ps1'), '-KillAfter', '26') + @($(if ($NoCompatLayer) { '-NoCompatLayer' })))
    $got = $null
    for ($t = 0; $t -lt 40 -and -not $got; $t++) {
        Start-Sleep -Milliseconds 500
        $g = Get-Process GTR2 -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
        if ($g) {
            Start-Sleep -Seconds 10; $r = New-Object GtrWin+R; [GtrWin]::GetClientRect($g.MainWindowHandle, [ref]$r) | Out-Null
            $now = Get-CimInstance Win32_VideoController | Select-Object -First 1
            $got = "$($r.r)x$($r.b)|$($now.CurrentHorizontalResolution)x$($now.CurrentVerticalResolution)"
        }
    }
    # the launcher stops its own game after -KillAfter; if it overruns, stop only ITS process tree (never another session's GTR2 by name)
    if (-not $lv.WaitForExit(75000)) { Stop-Tree $lv.Id; $lv.WaitForExit(30000) | Out-Null }
    if (-not $got) { Restore-Config; Fail 'verification launch: the game window never appeared; previous local config restored' }
    $gc, $gd = $got -split '\|'; $okDisplay = "$($before.Width)x$($before.Height)"
    $expClient = "$([int][math]::Round($wantW * $dpiScale))x$([int][math]::Round($wantH * $dpiScale))"   # a DPI-unaware window measures larger at scale > 100%
    if ($gc -ne $expClient -or $gd -ne $okDisplay) {
        Restore-Config
        Fail "verification launch FAILED: window client $gc (wanted $expClient at $scaleText scale), desktop $gd (was $okDisplay). A changed desktop means the saved VIDEOMODE selected a mode the game opens fullscreen. Previous local config restored. Try another index with -VideoMode (known good on the machine this was built on: 72 for 1280x720)."
    }
    "verified by launching: window client $gc, desktop unchanged ($gd)"
    # remember what was verified so -Status can compare later without launching anything
    [ordered]@{ resolution = "${wantW}x$wantH"; exe = (Join-Path $Root 'GTR2.exe'); videomode = [int](Cfg-Value 'VIDEOMODE'); windowed = [int](Cfg-Value 'WINDOWEDMODE'); videoguid = (Cfg-Value 'VIDEOGUID'); scale = $dpiScale; verified = (Get-Date -Format s) } |
        ConvertTo-Json | Set-Content -Path $recPath -Encoding ASCII
}

# ---- read-only status: config vs the last verified setting vs this screen; launches nothing, exit 0 only if all agree ----
if ($Status) {
    $problems = @()
    $vm = Cfg-Value 'VIDEOMODE'; $wm = Cfg-Value 'WINDOWEDMODE'; $guid = Cfg-Value 'VIDEOGUID'
    "config\Documents-Config.ini : VIDEOMODE=$vm WINDOWEDMODE=$wm VIDEOGUID=$guid"
    "screen                      : work area $($wa.Width)x$($wa.Height), display scale $scaleText$(if ($Scale -gt 0) { ' (from -Scale)' })"
    if ($wm -ne '1') { $problems += 'WINDOWEDMODE is not 1 (the game would use fullscreen and switch the display)' }
    if (-not (Test-Path $recPath)) { $problems += 'no verified record (config\resolution-verified.json): run -Resolution WxH once to verify by launching' }
    else {
        $rec = Get-Content $recPath -Raw | ConvertFrom-Json
        "last verified launch        : $($rec.resolution) with VIDEOMODE=$($rec.videomode), windowed=$($rec.windowed), scale $('{0:P0}' -f $rec.scale), $($rec.verified)"
        if ("$($rec.videomode)" -ne $vm -or "$($rec.windowed)" -ne $wm -or $rec.videoguid -ne $guid) { $problems += 'the config no longer matches what was verified (VIDEOMODE, WINDOWEDMODE or VIDEOGUID changed)' }
        $myExe = Join-Path $Root 'GTR2.exe'
        if (-not $rec.exe) { $problems += 'the record has no exe path (made by an older version): re-verify to record it' }
        elseif ($rec.exe -ne $myExe) { $problems += "verified at another path ($($rec.exe)), this folder is ${myExe}; a window at one path does not guarantee one at another, re-verify here" }
        if ([math]::Abs([double]$rec.scale - $dpiScale) -gt 0.01) { $problems += "display scale changed since verification ($('{0:P0}' -f $rec.scale) then, $scaleText now)" }
        if ($rec.resolution -match '^(\d+)x(\d+)$') {
            $fit = Fits ([int]$Matches[1]) ([int]$Matches[2])
            "window fits this screen     : $(if ($fit) { 'yes' } else { 'NO' }) ($($rec.resolution) needs $([math]::Ceiling(([int]$Matches[1] + 6) * $dpiScale))x$([math]::Ceiling(([int]$Matches[2] + 35) * $dpiScale)) incl. frame)"
            if (-not $fit) { $problems += "the verified size $($rec.resolution) does not fit this screen at $scaleText scale" }
        }
    }
    if ($Resolution) { "asked about $wantW x ${wantH}: $(if (Fits $wantW $wantH) { 'fits as a window' } else { 'does NOT fit as a window' }) at $scaleText scale" }
    if ($problems) { "NOT READY:"; $problems | ForEach-Object { "  - $_" }; exit 1 } else { "READY: windowed, verified for this config and this screen"; exit 0 }
}

# ---- explicit index: no dialog ----
if ($VideoMode) {
    if (-not $Force -and -not (Fits $wantW $wantH)) { Fail "$wantW x $wantH does not fit as a window in the $($wa.Width)x$($wa.Height) work area; use -Force to try anyway" }
    $t = $latin1.GetString($cfgBytes)
    $t = [regex]::Replace($t, '(?m)^VIDEOMODE=[0-9]+', "VIDEOMODE=$VideoMode"); $t = [regex]::Replace($t, '(?m)^WINDOWEDMODE=[0-9]+', 'WINDOWEDMODE=1')
    if ($DryRun) { "dry run: would write VIDEOMODE=$VideoMode, WINDOWEDMODE=1 and verify ${wantW}x$wantH"; exit 0 }
    [IO.File]::WriteAllBytes($cfgPath, $latin1.GetBytes($t))
    "wrote VIDEOMODE=$VideoMode WINDOWEDMODE=1 (VIDEOGUID=$(Cfg-Value 'VIDEOGUID'))"
    if ($NoVerify) { "not verified (-NoVerify)" } else { Test-Launch }
    "review with: git diff config"; exit 0
}

# ---- dialog route: run GTR2Config through the launcher (backs up and restores the shared Documents\GTR2) ----
$adopt = (-not $List -and -not $DryRun)
$log = Join-Path $env:TEMP "gtr2-set-resolution-$PID.log"
$la = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'gtr2-launch.ps1'), '-Program', 'GTR2Config') + @($(if ($NoCompatLayer) { '-NoCompatLayer' }))
if ($adopt) { $la += '-AdoptConfig' }
$launcher = Start-Process powershell -ArgumentList $la -PassThru -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError "$log.err"
$ctl = $null
for ($t = 0; $t -lt 80 -and -not $ctl; $t++) {
    Start-Sleep -Milliseconds 500
    if ($launcher.HasExited) { break }
    $gp = Get-Process GTR2Config -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($gp) { $c = [GtrWin]::Controls($gp.MainWindowHandle); if ($c.ContainsKey(1013) -and $c.ContainsKey(1201)) { $ctl = $c } }
}
function Finish($press) {   # press OK (1) or Cancel (2), wait for the launcher to restore Documents; only OK may leave a changed local config
    if ($ctl) { [GtrWin]::SendMessage($ctl[$press], $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null }
    if (-not $launcher.WaitForExit(60000)) { Stop-Tree $launcher.Id; $launcher.WaitForExit(30000) | Out-Null }   # only the launcher's own tree
    if ($press -ne 1) { Restore-Config }   # GTR2Config re-saves its config even on Cancel and the launcher adopts any change
    Get-Content $log, "$log.err" -ErrorAction SilentlyContinue | Where-Object { $_ -and $_ -notmatch '^\s*$' } | ForEach-Object { "  launcher: $_" }
    Remove-Item $log, "$log.err" -ErrorAction SilentlyContinue
}
if (-not $ctl) { Finish 2; Fail 'the GTR2Config dialog did not appear (see launcher messages above)' }
$res = $ctl[1013]
try {
    $items = @(Items $res); $cur = Current $res
    if ($Dropdowns) {
        "Drop-downs GTR2Config shows on this machine (options are read from the dialog; select by text, never by position):"
        foreach ($c in (Combos $ctl)) {
            $its = @(Items $c.Value); $cu = Current $c.Value
            "  id $($c.Key)  '$(Label-Of $c.Value)'  current: '$(if ($cu -ge 0) { $its[$cu] })'  ($($its.Count) options)"
            $its | ForEach-Object { "      $_" }
        }
        Finish 2; return
    }
    if ($List) {
        "Modes GTR2Config offers on this machine (work area $($wa.Width)x$($wa.Height); 'window' = fits as a window). Dialog opened on '$($items[$cur])'; list has $($items.Count) entries:"
        $items | ForEach-Object { if ($_ -match '^(\d+) x (\d+) (\d+) bit') { [pscustomobject]@{ Mode = $_; Window = $(if (Fits ([int]$Matches[1]) ([int]$Matches[2])) { 'fits' } else { 'too big' }) } } } | Format-Table -AutoSize | Out-String -Width 200
        Finish 2; return
    }
    if (-not $Fullscreen -and -not (Fits $wantW $wantH) -and -not $Force) { Finish 2; Fail "$wantW x $wantH does not fit as a window in the $($wa.Width)x$($wa.Height) work area (needs +6 x +35); pick a smaller size or use -Force" }
    $chosen = Select-Item $res ("^$wantW x $wantH $Bits bit")
    if (-not $chosen) { Finish 2; Fail "GTR2Config offers no '$wantW x $wantH $Bits bit' mode (run with -List)" }
    if ($Refresh) { $rf = Select-Item $ctl[1203] ("^$Refresh\s*Hz"); if (-not $rf) { Finish 2; Fail "no refresh rate '$Refresh Hz' for that mode" } }
    $extra = @($Select); if ($Shader) { $extra += "1204=$Shader" }
    foreach ($e in $extra) {
        if ($e -notmatch '^(\d+)=(.+)$') { Finish 2; Fail "bad -Select '$e' (use id=regex, ids from -Dropdowns)" }
        $cid = [int]$Matches[1]; $pat = $Matches[2]      # Select-Item uses -match, which overwrites $Matches
        if (-not $ctl.ContainsKey($cid)) { Finish 2; Fail "GTR2Config has no control $cid (run with -Dropdowns)" }
        $got = Select-Item $ctl[$cid] $pat
        if (-not $got) { $opts = (Items $ctl[$cid]) -join ' | '; Finish 2; Fail "control $cid has no option matching '$pat' (options: $opts)" }
        "selected on control ${cid}: $got"
    }
    $want = if ($Fullscreen) { 0 } else { 1 }
    if ([GtrWin]::SendMessage($ctl[1201], $BM_GETCHECK, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32() -ne $want) { [GtrWin]::SendMessage($ctl[1201], $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null; Start-Sleep -Milliseconds 400 }
    $shown = (Items $res)[(Current $res)]; $rate = @(Items $ctl[1203])[(Current $ctl[1203])]
    $win_on = [GtrWin]::SendMessage($ctl[1201], $BM_GETCHECK, [IntPtr]::Zero, [IntPtr]::Zero).ToInt32()
    if ($shown -ne $chosen -or $win_on -ne $want) { Finish 2; Fail "dialog verification failed (shows '$shown', windowed=$win_on); nothing saved" }
    "dialog verified: $shown, refresh $rate, windowed=$win_on"
    if ($DryRun) { "dry run: pressing Cancel, nothing adopted"; Finish 2; return }
    Finish 1
    $vm = Cfg-Value 'VIDEOMODE'; $wm = Cfg-Value 'WINDOWEDMODE'; $guid = Cfg-Value 'VIDEOGUID'
    if ($wm -ne "$want" -or -not $vm -or -not $guid) { Restore-Config; Fail "saved config check failed: VIDEOMODE=$vm WINDOWEDMODE=$wm VIDEOGUID=$guid (expected WINDOWEDMODE=$want); previous config restored" }
    "dialog saved VIDEOMODE=$vm for '$chosen', WINDOWEDMODE=$wm, VIDEOGUID=$guid"
    if ($NoVerify -or $Fullscreen) { "not verified by launching" } else { Test-Launch }
    "review with: git diff config"
}
catch { Finish 2; throw }
