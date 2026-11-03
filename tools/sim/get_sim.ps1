<#
.SYNOPSIS
    Install the standalone simulator for Windows from this plugin (no download, no GitHub), verified.

.DESCRIPTION
    1. The plugin carries the prebuilt simulator: simulator\dist\<version>\windows\wowcube-sim.exe, described by
       simulator\dist\<version>\manifest.txt (written by tools\sim\stage_dist.py from the CI build of the private
       simulator sources). <version> is the one this plugin needs (sim_version in api\SOURCE: the public game API and
       the simulator come from one commit of the sources). No git, no network, no compiler.
    2. The exe's sha256 must match the manifest; a staged copy must answer "wowcube-sim.exe --version" (started
       hidden, killed by PID after 30 s) with that version and the manifest's build commit. Only then it
       replaces <sim dir>\wowcube-sim.exe: ~\.wowcube\sim\<version>\windows (or $env:WOWCUBE_SIM_DIR), outside the
       plugin folder, which may be read-only or replaced on an update (tools\sim\sim_path.ps1).
    3. There is no other way to get it: the plugin ships no simulator sources, so a missing or damaged prebuilt
       simulator is an incomplete plugin (reinstall or update it).
    The result must answer --version with the version this plugin needs, else exit 1. Starts nothing else; never
    shows a window.

    Exit codes: 0 the simulator is in place and is the version this plugin needs | 1 failed

.PARAMETER NoBuild   Ignored (kept for old command lines): there is no local build any more.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\sim\get_sim.ps1
#>
[CmdletBinding()]
param(
    [switch] $NoBuild
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hidden_launch.ps1')
. (Join-Path $PSScriptRoot 'sim_path.ps1')
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "    $m" -ForegroundColor Yellow }

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$binDir = Get-SimDir
$exe = Join-Path $binDir 'wowcube-sim.exe'
$want = Get-SimVersion
$distDir = Join-Path $repoRoot "simulator\dist\$want"

# key=value lines (manifest.txt); $null when the file is missing
function Read-KeyValues([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $h = @{}
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        $t = $line.Trim()
        if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
        $i = $t.IndexOf('=')
        $h[$t.Substring(0, $i).Trim()] = $t.Substring($i + 1).Trim()
    }
    return $h
}

function Install-FromPlugin {
    $ErrorActionPreference = 'Continue'
    $m = Read-KeyValues (Join-Path $distDir 'manifest.txt')
    if (-not $m) { Warn "this plugin carries no prebuilt simulator $want (simulator\dist\$want\manifest.txt)"; return $false }
    if ($m['version'] -ne $want) { Warn "the prebuilt simulator is version $($m['version']), this plugin needs $want"; return $false }
    $entry = [string]$m['windows']
    $parts = $entry -split '\s+'
    if ($parts.Count -ne 3) { Warn "manifest.txt has no windows entry"; return $false }
    $file = Join-Path $distDir ($parts[2] -replace '/', '\')
    if (-not (Test-Path -LiteralPath $file)) { Warn "$file is missing"; return $false }
    Step "Checking the prebuilt simulator (sha256, then --version, hidden)"
    $sha = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sha -ne $parts[0].ToLowerInvariant()) { Warn "$file does not match its sha256 in manifest.txt (damaged?)"; return $false }
    $stage = Join-Path ([IO.Path]::GetTempPath()) ("wowcube_sim_stage_" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    try {
        $staged = Join-Path $stage 'wowcube-sim.exe'
        Copy-Item -LiteralPath $file -Destination $staged
        $v = Get-SimExeVersion $staged
        if (-not $v) { Warn "the prebuilt exe does not answer --version"; return $false }
        Write-Host "    $v"
        $mv = [regex]::Match($v, '^wowcube-sim (\S+) \(([^,)]+)')
        if (-not $mv.Success -or $mv.Groups[1].Value -ne $want) { Warn "the prebuilt exe is not version $want"; return $false }
        if ($mv.Groups[2].Value -ne $m['build']) { Warn "the prebuilt exe names build $($mv.Groups[2].Value), not the manifest's $($m['build'])"; return $false }
        New-Item -ItemType Directory -Force -Path $binDir | Out-Null
        try { Copy-Item -LiteralPath $staged -Destination $exe -Force }
        catch { Warn "cannot replace $exe (is a simulator running?): $($_.Exception.Message)"; return $false }
        Remove-Item -LiteralPath (Join-Path $binDir 'wowcube-sim.pdb') -ErrorAction SilentlyContinue   # belonged to the old exe
        return $true
    } finally { Remove-Item -Recurse -Force -LiteralPath $stage -ErrorAction SilentlyContinue }
}

Step "Installing the simulator $want from this plugin (simulator\dist) into $binDir"
if (-not (Install-FromPlugin)) {
    Write-Host ("ERROR: the prebuilt simulator $want could not be installed (above). The plugin ships no simulator " +
                "sources, so there is no local build: reinstall or update the plugin.") -ForegroundColor Red
    exit 1
}
$check = Test-SimExe $exe
if (-not $check.Ok) { Write-Host "ERROR: $($check.Problem)" -ForegroundColor Red; exit 1 }
Write-Host "SIMULATOR READY: $exe" -ForegroundColor Green
Write-Host "  $($check.Line)"
exit 0
