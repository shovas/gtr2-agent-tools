# Purpose: put this machine back to a first-run GTR2 state without deleting anything.
#   Moves the shared Documents\GTR2 folder and every profile folder under this install's UserData\ (except Log)
#   into one timestamped Documents\GTR2_ASIDE_<yyMMdd_HHmmss> folder. Refuses if GTR2 or GTR2Config is running.
# Usage:   .\scripts\gtr2-clean-slate.ps1 [-Root <install folder>] [-DryRun]
# Example: powershell -NoProfile -ExecutionPolicy Bypass -File scripts\gtr2-clean-slate.ps1 -DryRun
# Undo:    move the folders back from the ASIDE folder, or `git checkout -- UserData` for tracked profiles.
param([string]$Root = $(if ($env:GTR2_ROOT) { $env:GTR2_ROOT } elseif (Test-Path (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json')) { (Get-Content -Raw (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json') | ConvertFrom-Json).game_root } else { Split-Path $PSScriptRoot }), [switch]$DryRun)
$ErrorActionPreference = 'Stop'
if (Get-Process GTR2, GTR2Config, GTR2Dedicated -ErrorAction SilentlyContinue) { Write-Error 'GTR2 is running; close it first.'; exit 1 }
$docs = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'GTR2'
$aside = Join-Path ([Environment]::GetFolderPath('MyDocuments')) ('GTR2_ASIDE_' + (Get-Date -Format 'yyMMdd_HHmmss'))
$moves = @()
if (Test-Path $docs) { $moves += , @($docs, (Join-Path $aside 'Documents_GTR2')) }
$ud = Join-Path $Root 'UserData'
if (Test-Path $ud) {
    Get-ChildItem $ud -Directory | Where-Object Name -ne 'Log' | ForEach-Object { $moves += , @($_.FullName, (Join-Path $aside ('UserData_' + $_.Name))) }
}
if (-not $moves) { Write-Host 'Already clean: no Documents\GTR2 and no profile folders.'; exit 0 }
foreach ($m in $moves) {
    Write-Host ("{0}: {1} -> {2}" -f $(if ($DryRun) { 'would move' } else { 'move' }), $m[0], $m[1])
    if (-not $DryRun) { New-Item -ItemType Directory -Force (Split-Path $m[1]) | Out-Null; Move-Item $m[0] $m[1] }
}
