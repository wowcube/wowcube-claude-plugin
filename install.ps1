# WowCube Create: one-command install for Windows (PowerShell 5.1+).
#   irm https://raw.githubusercontent.com/wowcube/wowcube-create/main/install.ps1 | iex
# Installs git if missing, the Claude Code plugin, and every tool a game build needs (check_env.ps1 -Install:
# Python and its packages, LLVM, VS 2022 Build Tools, CMake, Ninja, the ARM toolchain, FFmpeg), then the build
# checker (get_sim.ps1). Running this command is the user's yes to those installs and to winget's agreements.
# Windows asks once for administrator permission (Visual Studio Build Tools). Runs inside the caller's session
# (iex), so it never calls exit.

function Install-WowCubeCreate {
    $ErrorActionPreference = 'Stop'
    $repo = 'wowcube/wowcube-create'
    $market = 'wowcube-skills'
    $plugin = "wowcube@$market"

    function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
    function Fail($m) { Write-Host "STOPPED: $m" -ForegroundColor Red }
    function Refresh-Path {
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }

    Say 'Setting up WowCube Create: about 4 GB on a clean computer, 30-60 minutes. You can leave it running.'

    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Fail 'Claude Code is not installed. Install it first (https://claude.com/claude-code), then run this command again.'
        return
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            Fail 'git is missing and winget is not available. Install git from https://git-scm.com/download/win, then run this command again.'
            return
        }
        Say 'Installing git'
        winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
        Refresh-Path
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Fail 'git did not install. Install it from https://git-scm.com/download/win, then run this command again.'
            return
        }
    }

    Say 'Installing the WowCube plugin for Claude Code'
    $known = (& claude plugin marketplace list 2>$null | Out-String)
    if ($known -match [regex]::Escape($market)) { & claude plugin marketplace update $market | Out-Host }
    else { & claude plugin marketplace add $repo | Out-Host }
    if ($LASTEXITCODE -ne 0) { Fail 'could not add the plugin marketplace (see above).'; return }
    & claude plugin install $plugin | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail 'could not install the plugin (see above).'; return }

    # the plugin's folder: installPath from the plugin list, else the marketplace clone (the plugin is its root)
    $root = $null
    try {
        $list = (& claude plugin list --json 2>$null | Out-String) | ConvertFrom-Json
        foreach ($p in @($list)) { if ($p.id -eq $plugin -or $p.name -eq $plugin) { $root = $p.installPath } }
    } catch { }
    if (-not $root -or -not (Test-Path (Join-Path $root 'scripts\check_env.ps1'))) {
        $root = Join-Path $env:USERPROFILE ".claude\plugins\marketplaces\$market"
    }
    if (-not (Test-Path (Join-Path $root 'scripts\check_env.ps1'))) {
        Fail "the plugin is installed but its folder was not found ($root). Open Claude Code and say: set up everything the WowCube plugin needs."
        return
    }

    Say 'Installing the tools that build and check games (Windows asks once for administrator permission)'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\check_env.ps1') -Install -AcceptAgreements | Out-Host
    Refresh-Path

    Say 'Installing the build checker'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'tools\sim\get_sim.ps1') | Out-Host

    Say 'Checking everything'
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root 'scripts\check_env.ps1') | Out-Host
    if ($LASTEXITCODE -eq 0) {
        Write-Host ''
        Write-Host 'Done. Open Claude Code in a folder for your games and say: "I want to make a game for my WowCube".' -ForegroundColor Green
        Write-Host '(If Claude Code was already open, close it and open it again first.)'
    } else {
        Write-Host ''
        Write-Host 'Almost done: some items above are still missing. Install them (or ask whoever manages this computer),' -ForegroundColor Yellow
        Write-Host 'or open Claude Code and say: "set up everything the WowCube plugin needs".' -ForegroundColor Yellow
    }
}

Install-WowCubeCreate
