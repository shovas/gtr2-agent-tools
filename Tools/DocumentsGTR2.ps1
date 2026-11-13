# Compares (default) or refreshes a snapshot of the shared Documents\GTR2 folder (game-generated files).
#   .\Tools\DocumentsGTR2.ps1 -Root <game folder>            report files that differ between the live folder and the snapshot
#   .\Tools\DocumentsGTR2.ps1 -Root <game folder> -Update    copy the live folder over the snapshot (then review `git diff` in the game repo and commit)
# The snapshot lives in the GAME folder (default <Root>\_DocumentsGTR2), never in this tools repo. It is created by -Update.
# -Root defaults to GTR2_ROOT, else game_root in gtr2-tools.json (written by scripts\gtr2-setup.py). Never writes to the live folder. Exit code 0 = identical, 1 = differences.
param(
    [switch]$Update,
    [string]$Root = $(if ($env:GTR2_ROOT) { $env:GTR2_ROOT } elseif (Test-Path (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json')) { (Get-Content -Raw (Join-Path (Split-Path $PSScriptRoot) 'gtr2-tools.json') | ConvertFrom-Json).game_root }),
    [string]$Snapshot,
    [string]$Live = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'GTR2')
)
if (-not $Snapshot) {
    if (-not $Root) { throw 'Give -Root <game folder> (or set GTR2_ROOT), or -Snapshot <folder>.' }
    $Snapshot = Join-Path $Root '_DocumentsGTR2'
}
$snap = $Snapshot
if (-not (Test-Path $Live)) { throw "missing live folder: $Live" }
function Get-Map($root) {
    $m = @{}
    if (Test-Path $root) {
        Get-ChildItem $root -Recurse -File -Force | ForEach-Object {
            $m[$_.FullName.Substring($root.Length).TrimStart('\')] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
        }
    }
    $m
}
$a = Get-Map $Live; $b = Get-Map $snap
$diff = foreach ($k in ($a.Keys + $b.Keys | Sort-Object -Unique)) {
    if (-not $b.ContainsKey($k)) { "only in live:     $k" }
    elseif (-not $a.ContainsKey($k)) { "only in snapshot: $k" }
    elseif ($a[$k] -ne $b[$k]) { "differs:          $k" }
}
if ($diff) { $diff } else { Write-Host 'Live Documents\GTR2 matches the snapshot.' }
if ($Update -and $diff) {
    # Mirror: copy live over snapshot, remove files that no longer exist live.
    if (Test-Path $snap) { Get-ChildItem $snap -Recurse -File -Force | Remove-Item -Force } else { New-Item -ItemType Directory -Path $snap | Out-Null }
    Copy-Item (Join-Path $Live '*') $snap -Recurse -Force
    Write-Host "Snapshot updated: $snap"
    exit 0
}
exit ([int][bool]$diff)
