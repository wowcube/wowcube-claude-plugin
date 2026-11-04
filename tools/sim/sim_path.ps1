<#
.SYNOPSIS
    Where the standalone simulator lives, and whether it is the version this checkout needs
    (dot-source it: . tools\sim\sim_path.ps1).

.DESCRIPTION
    The simulator binaries are machine state, not plugin files: an installed plugin folder may be read-only or
    replaced on an update. get_sim.ps1 installs the plugin's prebuilt simulator (simulator\dist) into the user's
    folder; every tool runs that one.

      Get-SimVersion     the simulator version this plugin needs: sim_version in api\SOURCE (the public game API
                         and the prebuilt simulator match one engine version)
      Get-SimDir         the install folder: $env:WOWCUBE_SIM_DIR, else ~\.wowcube\sim\<version>\windows
      Resolve-SimExe     <Get-SimDir>\wowcube-sim.exe (it may be missing: get_sim.ps1). There is no other place:
                         a different folder is set through WOWCUBE_SIM_DIR
      Get-SimExeVersion  "<exe> --version", hidden, 30 s limit: the version line, or $null
      Test-SimExe        the check every tool runs before it relies on the exe: present, answers --version, and its
                         version equals Get-SimVersion. Returns @{ Ok; Exe; Line; Version; Expected; Problem }:
                         Problem names what is wrong and the fix (get_sim.ps1) when Ok is $false
#>

function Get-SimVersion {
    $h = Join-Path $PSScriptRoot '..\..\api\SOURCE'
    if (Test-Path -LiteralPath $h) {
        $m = [regex]::Match([IO.File]::ReadAllText((Resolve-Path -LiteralPath $h).Path), '(?m)^\s*sim_version\s*=\s*([A-Za-z0-9._-]+)\s*$')
        if ($m.Success) { return $m.Groups[1].Value }
    }
    return 'unknown'
}

function Get-SimDir {
    if ($env:WOWCUBE_SIM_DIR) { return $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($env:WOWCUBE_SIM_DIR) }
    $home_ = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
    return Join-Path $home_ (".wowcube\sim\" + (Get-SimVersion) + "\windows")
}

function Resolve-SimExe {
    return (Join-Path (Get-SimDir) 'wowcube-sim.exe')
}

# "wowcube-sim.exe --version", hidden, with a time limit; returns the version line or $null
function Get-SimExeVersion([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return $null }
    if (-not (Get-Command Invoke-Hidden -ErrorAction SilentlyContinue)) { . (Join-Path $PSScriptRoot 'hidden_launch.ps1') }
    $wd = Join-Path ([IO.Path]::GetTempPath()) ("wowcube_sim_ver_" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $wd | Out-Null
    try {
        # --headless first: a build without --version then fails quietly (exit 10) instead of showing a message box
        $r = Invoke-Hidden -Exe $Path -WorkDir $wd -TimeoutSec 30 -Arguments "--headless --version --workdir `"$wd`""
        $f = Join-Path $wd 'sim_version.txt'
        if ($r.Exit -eq 0 -and $r.MaxVisible -eq 0 -and (Test-Path $f)) {
            $v = (Get-Content -LiteralPath $f -Raw).Trim()
            if ($v -match '^wowcube-sim \S+') { return $v }
        }
        return $null
    } catch { return $null }
    finally { Remove-Item -Recurse -Force -LiteralPath $wd -ErrorAction SilentlyContinue }
}

function Test-SimExe([string]$Path) {
    if (-not $Path) { $Path = Resolve-SimExe }
    $expected = Get-SimVersion
    $fix = "run tools\sim\get_sim.ps1 (it installs simulator $expected from this plugin into $(Get-SimDir); " +
           "installing software waits for the user's approval)"
    $r = [pscustomobject]@{ Ok = $false; Exe = $Path; Line = $null; Version = $null; Expected = $expected; Problem = $null }
    if (-not (Test-Path -LiteralPath $Path)) { $r.Problem = "no simulator at ${Path}: $fix"; return $r }
    $r.Line = Get-SimExeVersion $Path
    if (-not $r.Line) { $r.Problem = "${Path} does not answer --version (an older build?): $fix"; return $r }
    $r.Version = ($r.Line -split '\s+')[1]
    if ($r.Version -ne $expected) {
        $r.Problem = "$Path is wowcube-sim $($r.Version), this checkout needs ${expected}: $fix"
        return $r
    }
    $r.Ok = $true
    return $r
}
