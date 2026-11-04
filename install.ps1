# WowCube Create: one-command install for Windows (PowerShell 5.1+).
#   irm https://raw.githubusercontent.com/wowcube/wowcube-create/main/install.ps1 | iex
# Installs git if missing, installs (or upgrades) the Claude Code plugin, and every tool a game build needs
# (check_env.ps1 -Install: Python and its packages, LLVM, VS 2022 Build Tools, CMake, Ninja, the ARM toolchain,
# FFmpeg), then the build checker (get_sim.ps1). Up to about 4 GB and 30-60 minutes on a clean computer.
# Running this command is the user's yes to those installs and to winget's agreements; it records install_consent
# in ~/.wowcube/config.json. Windows may ask for administrator permission a few times (the Visual Studio Build
# Tools, LLVM, CMake, the ARM toolchain, git): accept each. Runs inside the caller's session (iex), so it never
# calls exit. Native commands run with $ErrorActionPreference 'Continue' and are judged by $LASTEXITCODE: in
# PowerShell 5.1 any stderr line of a native command under 'Stop' would abort the script with a raw exception.

function Install-WowCubeCreate {
    $ErrorActionPreference = 'Continue'
    $repo = 'wowcube/wowcube-create'
    $market = 'wowcube-skills'
    $plugin = "wowcube@$market"
    $conf = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }

    function Say($m) { Write-Host "==> $m" -ForegroundColor Cyan }
    function Fail($m) { Write-Host "STOPPED: $m" -ForegroundColor Red }
    function Refresh-Path {
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    }
    # a claude command shown to the user; $true when it exited 0
    function Invoke-Claude([string[]] $CliArgs) {
        try {
            & claude @CliArgs | Out-Host
            return ($LASTEXITCODE -eq 0)
        } catch {
            Write-Host $_.Exception.Message
            return $false
        }
    }
    # a claude command's JSON output, or $null (an older CLI, an error, unreadable output)
    function Get-ClaudeJson([string[]] $CliArgs) {
        try {
            $text = (& claude @CliArgs 2>$null | Out-String)
            if ($LASTEXITCODE -ne 0 -or -not $text.Trim()) { return $null }
            # PowerShell 5.1 emits a JSON array as ONE object: assign it first, then wrap it
            $obj = $text | ConvertFrom-Json
            return ,@($obj)
        } catch {
            return $null
        }
    }
    # a PowerShell script of the plugin; returns its exit code
    function Invoke-PluginScript([string] $Path, [string[]] $ScriptArgs) {
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $Path @ScriptArgs | Out-Host
            return $LASTEXITCODE
        } catch {
            Write-Host $_.Exception.Message
            return 1
        }
    }
    # ours / other / absent / unknown: is the marketplace there, and does it point at $repo?
    function Get-MarketState {
        $entry = $null
        $list = Get-ClaudeJson @('plugin', 'marketplace', 'list', '--json')
        if ($null -ne $list) {
            $entry = $list | Where-Object { $_.name -eq $market } | Select-Object -First 1
            if (-not $entry) { return 'absent' }
            $src = [string]$entry.source; $where = [string]$(if ($entry.repo) { $entry.repo } else { $entry.url })
        } else {
            # an older CLI without --json: the config file it keeps
            try {
                $known = Join-Path $conf 'plugins\known_marketplaces.json'
                $data = [IO.File]::ReadAllText($known) | ConvertFrom-Json
                $prop = $data.PSObject.Properties[$market]
                if (-not $prop) { return 'absent' }
                $s = $prop.Value.source
                $src = [string]$s.source; $where = [string]$(if ($s.repo) { $s.repo } else { $s.url })
            } catch {
                return 'unknown'
            }
        }
        $where = $where.ToLower().TrimEnd('/')
        if ($where.EndsWith('.git')) { $where = $where.Substring(0, $where.Length - 4) }
        $src = $src.ToLower()
        if (($src -eq 'github' -and $where -eq $repo) -or (($src -eq 'git' -or $src -eq 'url') -and $where.EndsWith("github.com/$repo"))) {
            return 'ours'
        }
        return 'other'
    }
    # running this command is the yes to the installs: record it for the WowCube setup (merge, never clobber)
    function Save-InstallConsent {
        try {
            $dir = Join-Path $env:USERPROFILE '.wowcube'
            $path = Join-Path $dir 'config.json'
            New-Item -ItemType Directory -Force -Path $dir | Out-Null
            $data = $null
            if (Test-Path $path) {
                $text = [IO.File]::ReadAllText($path)
                if ($text.Trim()) { $data = $text | ConvertFrom-Json -ErrorAction Stop }   # unreadable: left alone
            }
            if ($null -eq $data) { $data = New-Object PSObject }
            elseif ($data -isnot [System.Management.Automation.PSCustomObject]) { throw 'config.json is not a JSON object' }
            if (-not $data.PSObject.Properties['schema_version']) {
                $data | Add-Member -NotePropertyName schema_version -NotePropertyValue 1
            }
            $consent = New-Object PSObject -Property @{ answer = 'yes'; date = (Get-Date -Format 'yyyy-MM-dd') }
            $data | Add-Member -NotePropertyName install_consent -NotePropertyValue $consent -Force
            $json = $data | ConvertTo-Json -Depth 20
            [IO.File]::WriteAllText($path, $json + "`n", (New-Object System.Text.UTF8Encoding $false))
        } catch {
            Say 'Could not record the install consent in ~/.wowcube/config.json; the WowCube setup will ask once.'
        }
    }

    Say 'Setting up WowCube Create: up to about 4 GB and 30-60 minutes on a clean computer. Windows may ask for administrator permission a few times; accept each. In between you can leave it running.'

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
        try { winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Host } catch { }
        Refresh-Path
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Fail 'git did not install. Install it from https://git-scm.com/download/win, then run this command again.'
            return
        }
    }

    Say 'Installing the WowCube plugin for Claude Code'
    switch (Get-MarketState) {
        'ours' {
            if (-not (Invoke-Claude @('plugin', 'marketplace', 'update', $market))) { Fail 'could not update the plugin marketplace (see above).'; return }
        }
        'other' {
            Say "The '$market' plugin source on this computer points somewhere else; replacing it with $repo."
            if (-not (Invoke-Claude @('plugin', 'marketplace', 'remove', $market))) { Fail 'could not remove the old plugin source (see above).'; return }
            if (-not (Invoke-Claude @('plugin', 'marketplace', 'add', $repo))) { Fail 'could not add the plugin marketplace (see above).'; return }
        }
        'absent' {
            if (-not (Invoke-Claude @('plugin', 'marketplace', 'add', $repo))) { Fail 'could not add the plugin marketplace (see above).'; return }
        }
        default {
            if (-not (Invoke-Claude @('plugin', 'marketplace', 'update', $market))) {
                if (-not (Invoke-Claude @('plugin', 'marketplace', 'add', $repo))) { Fail 'could not add the plugin marketplace (see above).'; return }
            }
        }
    }

    # installed already (user scope) -> update it to the latest version, else install it
    $plugins = Get-ClaudeJson @('plugin', 'list', '--json')
    $installed = $false
    if ($null -ne $plugins) {
        $installed = [bool]($plugins | Where-Object { $_.id -eq $plugin -and (-not $_.scope -or $_.scope -eq 'user') })
    }
    if ($installed) {
        if (-not (Invoke-Claude @('plugin', 'update', $plugin))) { Fail 'could not update the plugin (see above).'; return }
    } else {
        if (-not (Invoke-Claude @('plugin', 'install', $plugin))) { Fail 'could not install the plugin (see above).'; return }
    }

    # the plugin's folder, read fresh after the install or update: installPath from the plugin list, else the
    # marketplace clone (the plugin is its root)
    $root = $null
    $plugins = Get-ClaudeJson @('plugin', 'list', '--json')
    if ($null -ne $plugins) {
        $rows = @($plugins | Where-Object { $_.id -eq $plugin } | Sort-Object { $_.scope -and $_.scope -ne 'user' })
        if ($rows.Count) { $root = $rows[0].installPath }
    }
    if (-not $root -or -not (Test-Path (Join-Path $root 'scripts\check_env.ps1'))) {
        $root = Join-Path $conf "plugins\marketplaces\$market"
    }
    if (-not (Test-Path (Join-Path $root 'scripts\check_env.ps1'))) {
        Fail "the plugin is installed but its folder was not found ($root). Open Claude Code and say: install the WowCube plugin and everything it needs."
        return
    }

    Save-InstallConsent

    Say 'Installing the tools that build and check games (Windows may ask for administrator permission a few times; accept each)'
    $code = Invoke-PluginScript (Join-Path $root 'scripts\check_env.ps1') @('-Install', '-AcceptAgreements')
    Refresh-Path
    # 0 = everything was there; 2 = installs attempted (anything that failed is listed as [FAILED] and the final
    # check below names it); 3 = no winget; anything else = the check itself broke
    if ($code -eq 3) {
        Fail 'winget (the Windows package installer) is not available, so the tools above could not be installed. Install "App Installer" from the Microsoft Store, then run this command again.'
        return
    }
    if ($code -ne 0 -and $code -ne 2) { Fail "the tool installer stopped with exit code $code (see above)."; return }

    Say 'Installing the build checker'
    $code = Invoke-PluginScript (Join-Path $root 'tools\sim\get_sim.ps1') @()
    if ($code -ne 0) { Fail 'the build checker did not install (see above).'; return }

    Say 'Checking everything'
    $code = Invoke-PluginScript (Join-Path $root 'scripts\check_env.ps1') @()
    Write-Host ''
    if ($code -eq 0) {
        Write-Host 'Done. Close Claude Code if it is open, open it in a folder for your games, start a new session and say "I want to make a game for my WowCube".' -ForegroundColor Green
    } else {
        Write-Host 'Almost done: some items above are still missing. Install them (or ask whoever manages this computer),' -ForegroundColor Yellow
        Write-Host 'or open Claude Code and say: "install the WowCube plugin and everything it needs".' -ForegroundColor Yellow
    }
}

Install-WowCubeCreate
