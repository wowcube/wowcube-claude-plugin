<#
.SYNOPSIS
    Check the WowCube toolchain. Everything a game needs comes from this plugin (the public game API in api\ and
    the prebuilt simulator in simulator\dist): no octavios or telemetry checkout is needed.

.DESCRIPTION
    Reports, never changes anything unless -Install is given (and then only winget packages: ask the user
    first, these are downloads):
      simulator  wowcube-sim.exe (~\.wowcube\sim\<version>\windows or $env:WOWCUBE_SIM_DIR) present and answering
                 --version (started hidden) with the version this plugin needs (sim_version in api\SOURCE; a
                 stale build is not OK); else MISSING with the get_sim.ps1 command (it installs the prebuilt simulator
                 this plugin carries): run only after the user agreed
      plugin     the game plugin compiler: clang-cl (LLVM, or the VS component "C++ Clang tools for Windows") plus
                 the MSVC linker and libraries (Visual Studio 2022 / Build Tools, C++ x64 tools)
      device     .oct build: cmake, ninja, arm-none-eabi-g++ (ARM GNU toolchain); the public game API (api\apps + include)
      assets     python 3.11+ with Pillow, numpy, pytoshop, psd-tools (scripts\pack.py), requests (paid image APIs);
                 ffmpeg (sound encoding)
      info       Codex CLI logged in with ChatGPT (image generation), ffprobe, Node.js + Playwright + Chromium
                 (optional: only HTML prototypes and demo videos need them), uv (only for octpack-build against an
                 optional octavios checkout), long-path risk
    Exit 0 = everything required is present; 2 = something required is missing; 3 = -Install without winget.

.PARAMETER Workspace Default: the current folder (only for the long-path note).
.PARAMETER Install   Install the missing winget-installable tools (LLVM, CMake, Ninja, Arm GNU
                     toolchain, FFmpeg, VS 2022 Build Tools). Only after the user agreed. Installs are windowless:
                     winget --silent, the VS installer --quiet --norestart (never --passive). winget shows the
                     package and source agreements and asks for them unless -AcceptAgreements is given.
.PARAMETER AcceptAgreements  With -Install: pass winget --accept-package-agreements --accept-source-agreements.
                     Only when the user has read and accepted those agreements.
.PARAMETER SkipMsvc  Do not count/install MSVC.
.PARAMETER Octavios  Ignored (kept for old command lines).
.PARAMETER ReportOnly  Accepted for compatibility; reporting is the default.
#>
[CmdletBinding()]
param(
    [string] $Octavios,
    [string] $Workspace = (Get-Location).Path,
    [switch] $Install,
    [switch] $AcceptAgreements,
    [switch] $SkipMsvc,
    [switch] $ReportOnly
)
# A report must never abort half-way. Callers such as new_app.ps1 run with $ErrorActionPreference = 'Stop', which
# this script would inherit; on Windows PowerShell 5.1 a native tool writing to stderr under `2>$null` (git, gh,
# ...) then raises a terminating NativeCommandError. This scope only.
$ErrorActionPreference = 'Continue'

function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Have($exe) { return [bool](Get-Command $exe -ErrorAction SilentlyContinue) }
$missing = New-Object System.Collections.ArrayList   # @{ What; Fix; Pkg }
function Ok($m)   { Write-Host "  [ok]      $m" }
function Info($m) { Write-Host "  [info]    $m" -ForegroundColor DarkGray }
function Warn($m) { Write-Host "  [warn]    $m" -ForegroundColor Yellow }
function Miss($what, $fix, $pkg = $null) {
    Write-Host "  [MISSING] $what  -> $fix" -ForegroundColor Yellow
    [void]$missing.Add(@{ What = $what; Fix = $fix; Pkg = $pkg })
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Step "WowCube toolchain (public game API in $repo\api, prebuilt simulator in $repo\simulator\dist)"
if ($Octavios) { Info "-Octavios is ignored: no octavios or telemetry checkout is needed" }

# --- MSVC (plugin linker + libraries) -------------------------------------------------------------
$MSVC_PKG  = 'Microsoft.VisualStudio.2022.BuildTools'
# --quiet: no installer window at all (--passive would show its progress UI over the user's screen);
# --norestart: an unattended install never reboots the machine
$MSVC_ARGS = '--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Llvm.Clang --add Microsoft.VisualStudio.Component.Windows11SDK.22621 --includeRecommended'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vsPath = $null
if (Test-Path $vswhere) { $vsPath = (& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null) | Select-Object -First 1 }
$msvcOk = [bool]$vsPath

# --- simulator ------------------------------------------------------------------------------
. (Join-Path $repo 'tools\sim\sim_path.ps1')
$simExe = Resolve-SimExe
# the plugin carries the prebuilt simulator (simulator\dist\<version>, tools\sim\stage_dist.py): get_sim installs it
$distReady = Test-Path -LiteralPath (Join-Path $repo "simulator\dist\$(Get-SimVersion)\manifest.txt")
# OK only for the version this plugin needs (api\SOURCE): a stale build answers --version too
$sim = Test-SimExe $simExe
if ($sim.Ok) { Ok "simulator: $($sim.Line)" }
# a missing or wrong simulator is always MISSING (exit 2), even when the plugin carries it: installing it puts
# software on the machine, which waits for the user's one-time environment approval (new_app.ps1 -GetSim runs get_sim.ps1)
$getSimCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$repo\tools\sim\get_sim.ps1`""
if (-not $sim.Ok) {
    $what = if ($sim.Version) { "simulator (wowcube-sim.exe): version $($sim.Version) installed, this plugin needs $($sim.Expected)" }
            elseif (Test-Path -LiteralPath $simExe) { "simulator (wowcube-sim.exe): $simExe does not answer --version" }
            else { "simulator (wowcube-sim.exe): not installed" }
    if ($distReady) { Miss "${what}; this plugin carries it prebuilt, get_sim installs it (no download)" "$getSimCmd (after the user approved it)" }
    else { Miss "${what}; this plugin carries no prebuilt simulator $($sim.Expected) (simulator\dist): an incomplete plugin" "reinstall or update the plugin, then $getSimCmd" }
}

# --- game plugin compiler: clang-cl + the MSVC linker/libraries ---------------------------------
$clang = $null
$c = Get-Command clang-cl -ErrorAction SilentlyContinue
if ($c) { $clang = $c.Source }
elseif (Test-Path "$env:ProgramFiles\LLVM\bin\clang-cl.exe") { $clang = "$env:ProgramFiles\LLVM\bin\clang-cl.exe" }
elseif ($vsPath -and (Test-Path (Join-Path $vsPath 'VC\Tools\Llvm\x64\bin\clang-cl.exe'))) { $clang = Join-Path $vsPath 'VC\Tools\Llvm\x64\bin\clang-cl.exe' }
if ($clang) { Ok "clang-cl (game plugin: tools\sim\build_game.ps1) ($clang)" }
else { Miss "clang-cl (compiles the game plugin with the MSVC ABI)" "winget install LLVM.LLVM (or the VS component 'C++ Clang tools for Windows')" 'LLVM.LLVM' }
if ($msvcOk) { Ok "MSVC C++ x64 tools: linker + libraries for the game plugin ($vsPath)" }
elseif ($SkipMsvc) { Info "MSVC not checked (-SkipMsvc)" }
else { Miss "MSVC C++ build tools + Windows SDK (the plugin links against them; several GB)" "winget install --id $MSVC_PKG -e --override `"$MSVC_ARGS`"" 'MSVC' }

# --- device .oct build ---------------------------------------------------------------------------
if ((Test-Path (Join-Path $repo 'api\apps\CMakeLists.txt')) -and (Test-Path (Join-Path $repo 'api\include\oct_api.h'))) {
    Ok "public game API + module build (api\include, api\apps)"
} else { Miss "api\include or api\apps (the public game API)" "the plugin is incomplete: reinstall or update it" }
foreach ($t in @(
        @{ Name = 'cmake';             Pkg = 'Kitware.CMake';               What = 'cmake (ARM build)' },
        @{ Name = 'ninja';             Pkg = 'Ninja-build.Ninja';           What = 'ninja (ARM build)' },
        @{ Name = 'arm-none-eabi-g++'; Pkg = 'Arm.GnuArmEmbeddedToolchain'; What = 'arm-none-eabi-g++ (ARM GNU toolchain: the module in the .oct)' })) {
    if (Have $t.Name) { Ok $t.What } else { Miss $t.What "winget install $($t.Pkg)" $t.Pkg }
}
if (Have 'uv') { Info "uv found (only octpack-build against an optional octavios checkout uses it)" }

# --- assets ----------------------------------------------------------------
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
$pyOld = $false
if ($python) { & $python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null; $pyOld = ($LASTEXITCODE -ne 0) }
# -Install puts Python in for this user (a per-user winget install: no admin rights needed), then its packages (PIP)
$pipFix = "python -m pip install -r $repo\scripts\requirements.txt"
if (-not $python -or $pyOld) {
    $why = if ($python) { "python 3.11+ (pipeline scripts; $python is older, the pinned numpy needs 3.11)" } else { "python 3.11+ (pipeline scripts)" }
    Miss $why "winget install --id Python.Python.3.12 -e --scope user (or python.org; the Microsoft Store build works too, see README)" 'Python.Python.3.12'
    [void]$missing.Add(@{ What = "python packages (scripts\requirements.txt)"; Fix = $pipFix; Pkg = 'PIP' })
}
else {
    $code = "import importlib.util as u; print(' '.join(m for m in ['PIL', 'numpy', 'pytoshop', 'psd_tools', 'requests', 'segno'] if u.find_spec(m) is None))"
    $absent = (& $python -c $code 2>$null) -join ''
    if ($LASTEXITCODE -ne 0) { Warn "could not query python packages with $python" }
    elseif ($absent.Trim()) { Miss "python packages: $($absent.Trim())" $pipFix 'PIP' }
    else { Ok "python + Pillow/numpy/pytoshop/psd-tools/requests/segno ($python)" }
    $prefix = (& $python -c "import sys; print(sys.prefix)" 2>$null) -join ''
    if ($python -like '*\WindowsApps\*' -or $prefix -like '*PythonSoftwareFoundation*') {
        # supported: every pipeline script runs on it; two things differ (README "Requirements")
        Warn ("python is the Microsoft Store build: supported, but its packages live in the user site, so run scripts as " +
              "'python <script>', never 'python -I' or '-s' (they hide Pillow); octpack-build through uv (PSD apps only) " +
              "needs a python.org Python")
    }
}
if (Have 'ffmpeg') { Ok "ffmpeg (sound encoding: scripts\sound_kit.py, gen_sounds.py)" } else { Miss "ffmpeg (sound encoding)" "winget install Gyan.FFmpeg" 'Gyan.FFmpeg' }
if (Have 'ffprobe') { Ok "ffprobe (video checks)" } elseif (Have 'ffmpeg') { Info "ffprobe not found next to ffmpeg: wowcube-demo-video checks its output with it (it ships with FFmpeg builds such as Gyan.FFmpeg)" }

# --- informational ------------------------------------------------------------
$codex = $null
$codexDir = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'
if (Test-Path $codexDir) { $codex = Get-ChildItem $codexDir -Recurse -Filter codex.exe -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName }
if (-not $codex -and (Have 'codex')) { $codex = (Get-Command codex).Source }
if ($codex) {
    # the login probe never sees a provider key (same list as art_codex.codex_env: these names plus *_API_KEY /
    # *_API_TOKEN): they leave this process's environment for the call and come back afterwards
    $billable = @('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'OPENROUTER_API_KEY', 'IMAGE_API', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'XAI_API_KEY', 'ANTHROPIC_API_KEY', 'DEEPSEEK_API_KEY', 'FAL_KEY', 'REPLICATE_API_TOKEN', 'ELEVENLABS_API_KEY')
    $hidden = @{}
    Get-ChildItem Env: | Where-Object { ($billable -contains $_.Name.ToUpper()) -or ($_.Name -match '_API_(KEY|TOKEN)$') } | ForEach-Object { $hidden[$_.Name] = $_.Value }
    foreach ($k in @($hidden.Keys)) { Remove-Item -LiteralPath "Env:$k" -ErrorAction SilentlyContinue }
    try { $status = (cmd /d /c "`"$codex`" login status 2>&1" | Out-String).Trim() }   # cmd merges stderr; PS 5.1 would wrap it in error records
    finally { foreach ($k in @($hidden.Keys)) { Set-Item -LiteralPath "Env:$k" -Value $hidden[$k] } }
    if ($status -match 'ChatGPT') { Info "Codex CLI logged in ($status): used only when the user says it is theirs and chooses it" }
    else { Info "Codex CLI found but not logged in with ChatGPT ($status): the user runs 'codex login' themselves" }
} else { Info "Codex CLI not found: sprites are the procedural style (agent-drawn in code, final quality) unless the user explicitly opts in to a paid image API (cube_asset-builder references\ART.md)" }
# optional: only the HTML prototype and demo video skills need Node.js + Playwright + Chromium. Playwright is never
# installed into the plugin folder: record_html.mjs and its probe (check_playwright.cjs) look in $env:WOWCUBE_NODE_DIR,
# ~\.wowcube\node, the workspace, then the recorder's folder (a global npm install does not count), and that
# Playwright's chromium.executablePath() must exist.
if (Have 'node') {
    $recDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'skills\wowcube-html-prototype\scripts'
    $nodePrefix = Join-Path $HOME '.wowcube\node'
    Push-Location -LiteralPath $Workspace
    try { $probe = ((& node (Join-Path $recDir 'check_playwright.cjs') 2>$null) -join '').Trim(); $pwRc = $LASTEXITCODE }
    finally { Pop-Location }
    if ($pwRc -eq 0) { Info "Node.js $((& node --version) -join '') + Playwright + Chromium ($probe) (HTML prototypes, demo videos)" }
    elseif ($pwRc -eq 3) { Info "Playwright found but its Chromium is not ($probe) (optional, prototypes/videos): npx --prefix `"$nodePrefix`" playwright install chromium, after the user approved the download" }
    else { Info "Node.js found, Playwright not installed (optional, prototypes/videos): npm i --prefix `"$nodePrefix`" playwright; npx --prefix `"$nodePrefix`" playwright install chromium, after the user approved the download (never into the plugin folder)" }
} else { Info "Node.js not found (optional: only HTML prototypes and demo videos need Node.js + Playwright + Chromium)" }
try {
    $lp = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
    if ($lp -ne 1) { Info "LongPathsEnabled=0: keep the workspace path short (Python and cl.exe fail past 260 chars)" }
} catch { }

# --- result / install ---------------------------------------------------------------
Write-Host ""
if ($missing.Count -eq 0) { Write-Host "Toolchain OK." -ForegroundColor Green; exit 0 }
if (-not $Install) {
    Write-Host "Missing $($missing.Count) item(s). Fix with the commands above; winget-installable ones: re-run with -Install (after the user agreed)." -ForegroundColor Yellow
    exit 2
}
if (-not (Have 'winget')) { Write-Host "winget is not available - install the items above manually." -ForegroundColor Red; exit 3 }
# agreements are accepted only with an explicit -AcceptAgreements; otherwise winget shows them and asks
$agree = @()
if ($AcceptAgreements) { $agree = @('--accept-package-agreements', '--accept-source-agreements') }
else { Write-Host "winget may show package/source agreements and ask to accept them (re-run with -AcceptAgreements only after the user accepted them)." -ForegroundColor Yellow }
$failed = New-Object System.Collections.ArrayList
foreach ($m in $missing) {
    if (-not $m.Pkg -or $m.Pkg -eq 'PIP') { continue }
    if ($m.Pkg -eq 'MSVC') {
        Step "Installing MSVC build tools (large download)"
        winget install --id $MSVC_PKG -e @agree --override $MSVC_ARGS | Out-Host
    } elseif ($m.Pkg -eq 'Python.Python.3.12') {
        Step "Installing Python 3.12 for this user (no admin rights needed)"
        winget install --id $m.Pkg -e --scope user @agree --silent | Out-Host
    } else {
        Step "Installing $($m.Pkg)"
        winget install --id $m.Pkg -e @agree --silent | Out-Host
    }
    if ($LASTEXITCODE -ne 0) { [void]$failed.Add($m) }
}
# Python's packages, with the Python found now or the one just installed (this process still has the old PATH)
$pipItem = $missing | Where-Object { $_.Pkg -eq 'PIP' } | Select-Object -First 1
if ($pipItem) {
    $py = if ($python -and -not $pyOld) { $python } else { $null }
    if (-not $py) {
        $cand = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Filter python.exe -Recurse -Depth 1 -ErrorAction SilentlyContinue |
                Where-Object { $_.DirectoryName -match 'Python3(1[1-9]|[2-9]\d)$' } | Sort-Object FullName -Descending | Select-Object -First 1
        if ($cand) { $py = $cand.FullName }
    }
    if ($py) {
        Step "Installing the Python packages (scripts\requirements.txt) with $py"
        & $py -m pip install --disable-pip-version-check -r (Join-Path $repo 'scripts\requirements.txt') | Out-Host
        if ($LASTEXITCODE -ne 0) { [void]$failed.Add($pipItem) }
    } else { [void]$failed.Add($pipItem) }
}
if ($failed.Count) {
    # no admin rights, a declined Windows prompt or no network: name exactly what is still needed and where it comes from
    Write-Host "Could not install $($failed.Count) item(s) (no admin rights, a declined Windows prompt, or no network):" -ForegroundColor Red
    foreach ($m in $failed) { Write-Host "  [FAILED]  $($m.What)  -> $($m.Fix)" -ForegroundColor Red }
}
Write-Host "Install attempted. Restart Claude Code (close it and open it again in the same folder) so the new programs are found, then re-run this check." -ForegroundColor Yellow
exit 2
