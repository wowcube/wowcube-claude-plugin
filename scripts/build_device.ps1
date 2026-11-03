<#
.SYNOPSIS
    Build the cube-loadable .oct of an app_<game> folder into <workspace>\dist\, verified. No simulator, no octavios.

.DESCRIPTION
    No octavios checkout is needed: the device module is built against this plugin's public game API
    (api\apps + api\include: the declarations a game compiles against, api\README.md).
    Builder "python" (default): cmake + Ninja ARM build (arm-none-eabi-g++) of api\apps into <AppDir>\out,
      then scripts\pack_beta.py --build-oct. It stamps SaveSize from APP_SAVE_SIZE reached through
      src/app_metadata.h (sizeof(record) read from the static_assert of its wire size in app_save.h), like
      octpack-build's host probe. Needs cmake, ninja, arm-none-eabi-g++, python.
    Builder "octpack" (only with -OctaviOS <an octavios dev checkout>): the SDK's one-command build
        uv run --frozen --project <octavios>\octpacker octpack-build <AppDir> --out <Out> --engine <octavios>
      (compiles src\app_metadata.h for the header fields, packs art\octpack.json if the app has one, builds the
      ARM module, writes the .oct). Needs uv, Python 3.12 (uv-managed), clang++ (or g++), cmake, ninja,
      arm-none-eabi-g++. octpacker is not part of this plugin: the python builder writes the same container.
    Verification (both, mandatory): the last <size of out\<app>.bin> bytes of the .oct are the ARM code, then
      scripts\pack_beta.py --verify-oct: magic, Size, CRC32, code_size/offset, a non-zero build id, title /
      version / GUID / categories / save size == the app's defines (src\app.h -> app_metadata.h -> app_save.h),
      the launcher map "ico", assets == index.bin. The header comes from octpack-info when it runs, otherwise
      from a local read; any mismatch, or anything that cannot be checked, fails the build (exit 1).
    The deliverable lives in dist\ (the standalone simulator writes no .oct; an older baked-in build or octavios dev
    simulator rewrote <app>\<app>.oct on every launch, so a stray one there is never the deliverable).

.PARAMETER AppDir    The app_<game> folder (one *.target; packed: index.bin + art\packed).
.PARAMETER OctaviOS  Optional octavios SDK checkout to build against instead of the public game API (needed only for
                     -Builder octpack). Default: none = <repo>\api (apps\ + include\).
.PARAMETER Out       Output .oct. Default: <AppDir>\..\dist\<app>.oct.
.PARAMETER Builder   auto (default: octpack only when -OctaviOS has octpacker and uv runs, else python) | octpack | python.
.PARAMETER UvEnv     octpacker's Python environment. Default: UV_PROJECT_ENVIRONMENT, else <AppDir>\..\.uv_octpack_venv:
                     never inside octavios. Its first creation downloads the pinned packages (the one-time bootstrap
                     the user approves, AGENT_SAFETY.md); later builds reuse it.
.PARAMETER NoUv      Never start uv (python builder + the local header check); also WOWCUBE_NO_UV=1. repack_app.py
                     passes it when it runs on the Microsoft Store Python: everything that Python starts sees a
                     private copy of AppData, so uv would not find its managed Python and would rebuild the
                     octpacker environment.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\build_device.ps1 -AppDir C:\ws\app_my_game
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $AppDir,
    [string] $OctaviOS,
    [string] $Out,
    [ValidateSet('auto', 'octpack', 'python')] [string] $Builder = 'auto',
    [string] $UvEnv,
    [switch] $NoUv
)

$ErrorActionPreference = 'Stop'
function Fail($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Have($exe) { return [bool](Get-Command $exe -ErrorAction SilentlyContinue) }

# --- resolve ----------------------------------------------------------------
$AppDir = (Resolve-Path -LiteralPath $AppDir -ErrorAction SilentlyContinue).Path
if (-not $AppDir) { Fail "app folder not found" }
$targets = @(Get-ChildItem -LiteralPath $AppDir -Filter *.target -File)
if ($targets.Count -ne 1) { Fail "$AppDir must hold exactly one *.target marker (found $($targets.Count))" }
$app = [IO.Path]::GetFileNameWithoutExtension($targets[0].Name)
if (-not (Test-Path (Join-Path $AppDir 'index.bin'))) { Fail "$AppDir\index.bin missing - pack the assets first (Stage 3)" }

# the tree: apps\CMakeLists.txt (+ apps\src) and the headers next to it: include\ (this plugin's public game API, the
# default) or engine\ (an octavios SDK checkout)
$vendored = $false
if (-not $OctaviOS) { $OctaviOS = Join-Path $PSScriptRoot '..\api'; $vendored = $true }
$OctaviOS = (Resolve-Path -LiteralPath $OctaviOS -ErrorAction SilentlyContinue).Path
$headers = $(if ($vendored) { 'include' } else { 'engine' })
if (-not $OctaviOS -or -not (Test-Path (Join-Path $OctaviOS 'apps\CMakeLists.txt')) -or -not (Test-Path (Join-Path $OctaviOS "$headers\oct_app_module.h"))) {
    Fail $(if ($vendored) { "public game API not found ($PSScriptRoot\..\api\apps, include) - incomplete plugin" } else { "octavios SDK not found at -OctaviOS (needs apps\CMakeLists.txt and engine\)" })
}
Write-Host "    module build: $OctaviOS$(if ($vendored) { ' (public game API, api\SOURCE)' })"

if (-not $Out) { $Out = Join-Path (Split-Path $AppDir -Parent) "dist\$app.oct" }
$Out = [IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Out))
New-Item -ItemType Directory -Force -Path (Split-Path $Out -Parent) | Out-Null

$metadata = Join-Path $AppDir 'src\app_metadata.h'
$octpackProject = Join-Path $OctaviOS 'octpacker'
# octpacker's environment lives in the workspace, never in the SDK tree (uv would otherwise create octpacker\.venv)
if (-not $UvEnv) { $UvEnv = $(if ($env:UV_PROJECT_ENVIRONMENT) { $env:UV_PROJECT_ENVIRONMENT } else { Join-Path (Split-Path $AppDir -Parent) '.uv_octpack_venv' }) }
# absolute from the caller's PowerShell location (uv would resolve a relative one inside octpacker\, the SDK tree;
# [IO.Path]::GetFullPath alone uses the process cwd, which Set-Location does not move)
$env:UV_PROJECT_ENVIRONMENT = [IO.Path]::GetFullPath($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($UvEnv))
if ($env:WOWCUBE_NO_UV -match '^(1|true|yes)$') { $NoUv = $true }
$useUv = (Have 'uv') -and -not $NoUv
if ($NoUv) { Write-Host "    NOTE: -NoUv / WOWCUBE_NO_UV: uv is not started (python builder, local header check)" -ForegroundColor Yellow }
$octpackReady = (Test-Path (Join-Path $octpackProject 'pyproject.toml')) -and $useUv -and (Test-Path $metadata)
if ($Builder -eq 'auto') { $Builder = $(if ($octpackReady) { 'octpack' } else { 'python' }) }
if ($Builder -eq 'octpack' -and -not $octpackReady) {
    Fail ("octpack-build needs -OctaviOS <octavios dev checkout> (octpacker\pyproject.toml), uv on PATH (and no -NoUv) and " +
          "src\app_metadata.h; the default -Builder python needs none of them")
}

$bin = Join-Path $AppDir "out\$app.bin"
$started = Get-Date

# --- 1. build ----------------------------------------------------------------
if ($Builder -eq 'octpack') {
    if (Test-Path (Join-Path $AppDir 'art\octpack.json')) {
        Write-Host "    NOTE: art\octpack.json present: octpack-build re-packs art from its PSD/raw sources (wipes art\packed and index.bin)." -ForegroundColor Yellow
    }
    Step "octpack-build $app -> $Out"
    $venvState = $(if (Test-Path (Join-Path $env:UV_PROJECT_ENVIRONMENT 'pyvenv.cfg')) { 'reused' } else { 'FIRST USE: uv creates it and downloads the pinned packages' })
    Write-Host "    octpacker environment: $($env:UV_PROJECT_ENVIRONMENT) ($venvState)"
    & uv run --frozen --project $octpackProject octpack-build $AppDir --out $Out --engine $OctaviOS
    if ($LASTEXITCODE -ne 0) { Fail "octpack-build failed (exit $LASTEXITCODE). Stale out\ from another SDK checkout? Delete $AppDir\out and retry." }
} else {
    foreach ($t in 'arm-none-eabi-g++', 'cmake', 'ninja', 'python') {
        if (-not (Have $t)) { Fail "$t not on PATH - run scripts\check_env.ps1" }
    }
    $packPy = Join-Path $PSScriptRoot 'pack_beta.py'
    Step "ARM device build (cmake + Ninja) for $app"
    $outDir = Join-Path $AppDir 'out'
    & cmake -G Ninja -S (Join-Path $OctaviOS 'apps') -B $outDir -DAPP_TELEMETRY=OFF | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "cmake configure failed. Stale out\ from another SDK tree (CMakeCache.txt names another source)? Delete $outDir\CMakeCache.txt and $outDir\CMakeFiles and retry." }
    & cmake --build $outDir --parallel 4 | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "ARM build failed (exit $LASTEXITCODE)" }
    Step "Packing .oct (python scripts\pack_beta.py --build-oct)"
    if (Test-Path $Out) { Remove-Item -Force $Out }
    & python $packPy --build-oct --app-dir $AppDir --code $bin --out $Out | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "python .oct builder failed (exit $LASTEXITCODE)" }
}

# --- 2. verify -----------------------------------------------------------------
if (-not (Test-Path $Out)) { Fail "no .oct at $Out" }
if ((Get-Item $Out).LastWriteTime -lt $started) { Fail "$Out was not rewritten by this build" }
if (-not (Test-Path $bin)) { Fail "no ARM module at $bin" }
$binBytes = [IO.File]::ReadAllBytes($bin)
$octBytes = [IO.File]::ReadAllBytes($Out)
if ($binBytes.Length -eq 0) { Fail "$bin is empty - the ARM build produced no code" }
$embedded = $octBytes.Length -ge $binBytes.Length
if ($embedded) {
    $start = $octBytes.Length - $binBytes.Length
    for ($i = 0; $i -lt $binBytes.Length; $i++) { if ($octBytes[$start + $i] -ne $binBytes[$i]) { $embedded = $false; break } }
}
if (-not $embedded) { Fail "the .oct does NOT end with out\$app.bin: no ARM code, dead on the cube" }
Write-Host "    ARM code embedded ($($binBytes.Length) bytes)"

# Header verification is MANDATORY: magic, size, CRC, the ARM tail, a non-zero build id, title/version/GUID/
# categories/save size == the app's defines, MAP "ico", assets == index.bin (scripts\pack_beta.py --verify-oct).
# octpack-info supplies the header when it runs (engine-answered offsets); otherwise the same checks run on a local
# read of the header. Whatever cannot be verified fails the build.
$version = ''
$packPyVerify = Join-Path $PSScriptRoot 'pack_beta.py'
if (-not (Have 'python')) { Fail "cannot verify $Out`: python is not on PATH (scripts\pack_beta.py --verify-oct reads the header) - run scripts\check_env.ps1" }
$infoFile = $null
if ((Test-Path (Join-Path $octpackProject 'pyproject.toml')) -and $useUv) {
    $json = & uv run --frozen --project $octpackProject octpack-info $Out --engine $OctaviOS
    if ($LASTEXITCODE -eq 0 -and $json) {
        $infoFile = Join-Path ([IO.Path]::GetTempPath()) ("octpack_info_{0}.json" -f [guid]::NewGuid().ToString('N'))
        ($json -join "`n") | Set-Content -LiteralPath $infoFile -Encoding UTF8
    } else {
        Write-Host "    octpack-info failed (exit $LASTEXITCODE): verifying with the local header check instead" -ForegroundColor Yellow
    }
} else {
    Write-Host "    header read by the local check (scripts\pack_beta.py)$(if ($NoUv) { '; -NoUv' } elseif (-not $vendored) { '; octpack-info not available' })"
}
$verifyArgs = @($packPyVerify, '--verify-oct', $Out, '--app-dir', $AppDir, '--code', $bin)
if ($infoFile) { $verifyArgs += @('--info-json', $infoFile) }
$verifyOut = @(& python @verifyArgs)
$verifyCode = $LASTEXITCODE
if ($infoFile) { Remove-Item -LiteralPath $infoFile -Force -ErrorAction SilentlyContinue }
foreach ($line in $verifyOut) { Write-Host $line }
if ($verifyCode -ne 0) { Fail ".oct verification failed (exit $verifyCode): see the ERROR lines above - nothing to deliver" }
$vm = [regex]::Match(($verifyOut -join "`n"), '(?m)^VERSION=(\S+)')
if ($vm.Success) { $version = $vm.Groups[1].Value }

Write-Host ""
Write-Host "CUBE PACKAGE READY ($Builder): $Out" -ForegroundColor Green
Write-Host "  $($octBytes.Length) bytes = assets + sounds + $($binBytes.Length) bytes ARM code$(if ($version) { "; version $version" })"
Write-Host "  Install it (after the user agreed to the store upload): python scripts\store_upload.py $Out --yes --verify (QR code + link)"
Write-Host "  Deliver this file, never an .oct found in the app folder (an older simulator build may have written it)."
exit 0
