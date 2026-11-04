<#
.SYNOPSIS
    Build a game's simulator plugin for Windows: <AppDir>\out\sim\<app>.dll

.DESCRIPTION
    Compiles api\plugin\sim_module.cpp with the game's src\app.h, against the public game API (api\include), as a
    DLL the standalone simulator loads with --game <AppDir>. The game is compiled as on the cube (OCT_APP_MODULE: every engine call through the import table)
    with TL = thread_local (OCT_SIM_PLUGIN). The compiler is clang-cl, which targets the MSVC ABI, so the structs
    exchanged with the MSVC-built simulator have the same layout (the simulator verifies sizes at load and refuses a
    mismatch). The app folder is only read, except <AppDir>\out\sim\ which receives the DLL and the source snapshot it
    is compiled from (obj\src). Starts nothing.

.PARAMETER AppDir
    The app_<game> folder (one *.target, src\app.h).
.PARAMETER Define
    NAME=VALUE (or NAME), e.g. -Define TD_DEBUG_AUTOPLAY=1,TD_MUTE=1 (the pipeline's test hooks <GAME>_DEBUG_AUTOPLAY,
    <GAME>_MUTE, <GAME>_DEBUG_PLAYFIELD_FACE). "#define NAME ..." lines in the
    source snapshot are rewritten (guarded or not); a NAME no source defines is passed as -DNAME=VALUE.
.PARAMETER Clang
    Path to clang-cl.exe (default: PATH, then C:\Program Files\LLVM\bin, then Visual Studio's bundled LLVM).
.PARAMETER ArmGcc
    Path to arm-none-eabi-g++ for the device check (default: PATH, then the Arm GNU Toolchain install folders).
.PARAMETER NoDeviceCheck
    Skip the device check: the snapshot compiled with arm-none-eabi-g++ and the cube's flags (api\apps:
    -Werror, -Werror=double-promotion, -Werror=float-conversion, -fsingle-precision-constant), syntax only. It is
    the authority on float rules: clang has no -fsingle-precision-constant, so the plugin evaluates an unsuffixed
    literal in double where the cube uses float.
.PARAMETER AllowDoubleLiterals
    Skip the float-literal rule (tools\sim\game_lint.py): by default an unsuffixed floating literal in src\ (0.5
    instead of 0.5f) fails the build, because the cube reads it as float (-fsingle-precision-constant) and clang
    reads it as double, so the simulator could branch differently from the cube. Only for old games that predate
    the rule. Static constructors (__attribute__((constructor)), init_priority) are always refused.
.PARAMETER DebugBuild
    -Od -Zi instead of -O2.
.PARAMETER OutDir
    Where the DLL, the snapshot and the logs go (default <AppDir>\out\sim). A coder's compile check passes its scratch
    folder (<ws>\.agent_scratch\pNN\build): the full check (device -Werror + plugin) without touching the app folder.
.PARAMETER ApiDir
    Maintainers: the header tree to compile against instead of <plugin>\api: a folder with include\ (or engine\),
    plugin\ and apps\src\ (an API parity check passes a sources checkout to compare the two builds).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\sim\build_game.ps1 -AppDir C:\ws\app_my_game -Define MYG_DEBUG_AUTOPLAY=1,MYG_MUTE=1
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)] [string] $AppDir,
    [string[]] $Define = @(),
    [string] $Clang,
    [string] $ArmGcc,
    [switch] $NoDeviceCheck,
    [switch] $AllowDoubleLiterals,
    [switch] $DebugBuild,
    [string] $OutDir,
    [string] $ApiDir
)
$ErrorActionPreference = 'Stop'
function Fail($m, $code = 1) { Write-Host "ERROR: $m" -ForegroundColor Red; exit $code }
# exit codes: 0 ok; 1 any other failure (clang-cl / Visual Studio, game_lint, the plugin compile); 3 arm-none-eabi-g++
# not found (device check); 4 the game fails the device check (arm-none-eabi-g++, the cube's -Werror flags)

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
# the public game API: the headers a game compiles against (api\include), the plugin entry point (api\plugin) and the
# device module glue (api\apps); no engine or simulator source
$api  = if ($ApiDir) { (Resolve-Path -LiteralPath $ApiDir).Path } else { Join-Path $repo 'api' }
$inc  = if (Test-Path (Join-Path $api 'include\oct_api.h')) { Join-Path $api 'include' } else { Join-Path $api 'engine' }
if (-not (Test-Path (Join-Path $inc 'oct_api.h')) -or -not (Test-Path (Join-Path $api 'plugin\sim_module.cpp'))) {
    Fail "public game API not found (${api}: include\oct_api.h, plugin\sim_module.cpp) - incomplete plugin"
}
$AppDir = (Resolve-Path -LiteralPath $AppDir -ErrorAction SilentlyContinue).Path
if (-not $AppDir) { Fail "app folder not found" }
$targets = @(Get-ChildItem -LiteralPath $AppDir -Filter *.target -File)
if ($targets.Count -ne 1) { Fail "$AppDir must hold exactly one *.target marker (found $($targets.Count))" }
$app = [IO.Path]::GetFileNameWithoutExtension($targets[0].Name)
if ($app -notmatch '^[a-z]{3}_[A-Za-z0-9_]+$') { Fail "invalid app name '$app' (expected <3 lowercase letters>_<name>)" }
$appSrc = Join-Path $AppDir 'src'
if (-not (Test-Path (Join-Path $appSrc 'app.h'))) { Fail "$appSrc\app.h not found" }

# --- compiler ---------------------------------------------------------------
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) { Fail "vswhere.exe not found - install Visual Studio (C++ desktop workload) or its Build Tools" }
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { Fail "Visual Studio with the C++ x64 tools not found (the plugin links against its CRT)" }
$vsDevCmd = Join-Path $vs 'Common7\Tools\VsDevCmd.bat'
if (-not $Clang) {
    $c = Get-Command clang-cl -ErrorAction SilentlyContinue
    if ($c) { $Clang = $c.Source }
    elseif (Test-Path "$env:ProgramFiles\LLVM\bin\clang-cl.exe") { $Clang = "$env:ProgramFiles\LLVM\bin\clang-cl.exe" }
    elseif (Test-Path (Join-Path $vs 'VC\Tools\Llvm\x64\bin\clang-cl.exe')) { $Clang = Join-Path $vs 'VC\Tools\Llvm\x64\bin\clang-cl.exe' }
}
if (-not $Clang -or -not (Test-Path $Clang)) {
    Fail "clang-cl.exe not found: install LLVM (winget install LLVM.LLVM) or the Visual Studio component 'C++ Clang tools for Windows', or pass -Clang"
}

# --- source snapshot + defines -----------------------------------------------
# The game is compiled from a snapshot of src\ (<AppDir>\out\sim\obj\src):
# -Define rewrites "#define NAME ..." lines there (so an unguarded test hook is overridden too) and passes -DNAME=VALUE
# when no source defines NAME. The real src\ is only read.
$out = if ($OutDir) { $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutDir) } else { Join-Path $AppDir 'out\sim' }
$tmp = Join-Path $out 'obj'
$snap = Join-Path $tmp 'src'
if (Test-Path $snap) { Remove-Item -Recurse -Force $snap }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Copy-Item -Recurse -LiteralPath $appSrc -Destination $snap
$defs = @()
foreach ($d in ($Define | ForEach-Object { $_ -split ',' } | Where-Object { $_ })) {
    $n, $v = $d -split '=', 2
    if ($n -notmatch '^[A-Za-z_]\w*$') { Fail "bad -Define '$d' (NAME or NAME=VALUE)" }
    if ($null -eq $v) { $v = '1' }
    if ($v -match '[\r\n]') { Fail "bad -Define '$n': the value must be one line" }
    # the whole definition, continuation lines (trailing backslash) included
    $rx = "(?m)^([ \t]*#[ \t]*define[ \t]+$n)\b(?![(])(?:[^\r\n]*\\\r?\n)*[^\r\n]*"
    $value = $v
    $evaluator = [System.Text.RegularExpressions.MatchEvaluator] { param($m) $m.Groups[1].Value + ' ' + $value + '   // [build_game -Define]' }   # literal: no $1/$& in values
    $hit = $false
    foreach ($f in @(Get-ChildItem -LiteralPath $snap -Recurse -File | Where-Object { $_.Extension -in '.h', '.hpp', '.c', '.cpp' })) {
        $bytes = [IO.File]::ReadAllBytes($f.FullName)
        $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
        $raw = [IO.File]::ReadAllText($f.FullName)
        if ([regex]::IsMatch($raw, $rx)) {   # case-sensitive, unlike -match
            $raw = [regex]::Replace($raw, $rx, $evaluator)
            [IO.File]::WriteAllText($f.FullName, $raw, (New-Object System.Text.UTF8Encoding($bom)))
            $hit = $true
            Write-Host "    $n = $v  (in $($f.Name))"
        }
    }
    if (-not $hit) { $defs += "-D$n=$v"; Write-Host "    $n = $v  (compiler -D)" }
}

# --- source rules: float literals as the cube reads them, no early static constructors (game_lint.py) ----------
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $py) { Fail "python not found: build_game checks the game's sources with tools\sim\game_lint.py" }
$lintArgs = @((Join-Path $PSScriptRoot 'game_lint.py'), $snap)
if ($AllowDoubleLiterals) { $lintArgs += '--allow-double-literals'; Write-Host "    float literals: not checked (-AllowDoubleLiterals)" -ForegroundColor Yellow }
& $py @lintArgs | Out-Host
if ($LASTEXITCODE -ne 0) { Fail "the game's sources break a simulator/cube parity rule (above; file:line in src\)" }

# --- device check: the same sources through the cube's compiler and flags ------
# clang has no -fsingle-precision-constant, so an unsuffixed literal (x * 0.5) is evaluated in double here and in float
# on the cube, and the device's -Werror=double-promotion / -Werror=float-conversion are not the plugin's rules. The
# authority is the device build: compile the snapshot with arm-none-eabi-g++ and api\apps' flags (syntax and
# diagnostics only, nothing is written), so a game that would not build for the cube fails HERE, before any run.
if (-not $NoDeviceCheck) {
    if (-not $ArmGcc) {
        $c = Get-Command arm-none-eabi-g++ -ErrorAction SilentlyContinue
        if ($c) { $ArmGcc = $c.Source }
        else {
            $found = @(Get-ChildItem "${env:ProgramFiles(x86)}\Arm GNU Toolchain arm-none-eabi", "$env:ProgramFiles\Arm GNU Toolchain arm-none-eabi", "${env:ProgramFiles(x86)}\Arm\GNU Toolchain mingw-w64-x86_64-arm-none-eabi" -Recurse -Filter arm-none-eabi-g++.exe -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)
            if ($found.Count) { $ArmGcc = $found[0].FullName }
        }
    }
    if (-not $ArmGcc -or -not (Test-Path -LiteralPath $ArmGcc)) {
        Fail "arm-none-eabi-g++ not found: the device check compiles the game as the cube does (install the Arm GNU Toolchain, or pass -ArmGcc; -NoDeviceCheck skips it, which lets device-only compile errors through)" 3
    }
    $armArgs = @('-mcpu=cortex-m4', '-mthumb', '-mfloat-abi=hard', '-mfpu=fpv4-sp-d16', '-std=c++20', '-Os', '-Wall',
                 '-Werror=float-conversion', '-Werror=double-promotion', '-Werror', '-ffreestanding', '-fno-builtin',
                 '-fsingle-precision-constant', '-fno-exceptions', '-fno-rtti', '-fno-threadsafe-statics', '-fno-use-cxa-atexit',
                 '-DOCT_APP_MODULE', '-fsyntax-only') + $defs + @("-I$snap", "-I$inc", (Join-Path $api 'apps\src\app_module.cpp'))
    Write-Host "==> Device check: $(Split-Path $ArmGcc -Leaf) -Werror (api\apps flags, syntax only)" -ForegroundColor Cyan
    $armLog = Join-Path $tmp 'device_check.log'
    $p = Start-Process -FilePath $ArmGcc -ArgumentList ($armArgs | ForEach-Object { if ($_ -match '\s') { "`"$_`"" } else { $_ } }) -NoNewWindow -Wait -PassThru `
         -RedirectStandardError $armLog -RedirectStandardOutput (Join-Path $tmp 'device_check.out')
    if ($p.ExitCode -ne 0) {
        Get-Content -LiteralPath $armLog | Select-Object -First 40 | Out-Host
        Fail "the game does not compile for the cube (arm-none-eabi-g++, device flags, -Werror) - fix it before simulating; log: $armLog" 4
    }
}

# --- compile ----------------------------------------------------------------
$dll = Join-Path $out "$app.dll"
function Q($s) { '"' + $s + '"' }
$opt = if ($DebugBuild) { @('-Od', '-Zi') } else { @('-O2') }
$rsp = @('/nologo', '-LD', '-MT', '/std:c++20', '/EHsc', '-W3') + $opt + @(
         '-DOCT_APP_MODULE', '-DOCT_SIM_PLUGIN', "-DOCT_SIM_APP_NAME=\`"$app\`"", '-D_CRT_SECURE_NO_WARNINGS') + $defs + @(
         # the game is freestanding code written for GCC: keep clang quiet about the engine's libc stand-ins
         '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable', '-Wno-missing-field-initializers',
         '-Wno-incompatible-library-redeclaration', '-Wno-builtin-requires-header', '-Wno-microsoft-cast',
         '-fno-builtin',
         # float in, float out as on the cube: report every silent promotion to double (the device check above is the gate)
         '-Wdouble-promotion', '-Wfloat-conversion',
         "/I$(Q $snap)", "/I$(Q $inc)", "/I$(Q (Join-Path $api 'plugin'))",
         "/Fo$(Q ($tmp + '\\'))", "/Fe$(Q $dll)",
         (Q (Join-Path $api 'plugin\sim_module.cpp')))
$rspFile = Join-Path $tmp 'clang.rsp'
$rsp -join "`r`n" | Set-Content -LiteralPath $rspFile -Encoding ascii
$log = Join-Path $tmp 'build.log'
$cmd = Join-Path $tmp 'build.cmd'
@"
@echo off
call "$vsDevCmd" -arch=amd64 -host_arch=amd64 -no_logo >nul 2>&1
"$Clang" @"$rspFile" /link /INCREMENTAL:NO > "$log" 2>&1
if errorlevel 1 exit /b 1
exit /b 0
"@ | Set-Content -LiteralPath $cmd -Encoding ascii

Write-Host "==> Compiling $app.dll (clang-cl, MSVC ABI; log: $log)" -ForegroundColor Cyan
if (Test-Path $dll) { Remove-Item -Force $dll }
& cmd.exe /d /c (Q $cmd)
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $dll)) {
    if (Test-Path $log) { Get-Content -LiteralPath $log | Where-Object { $_ -match 'error' } | Select-Object -First 40 | Out-Host }
    Fail "plugin build failed - full log: $log"
}
@{ app = $app; app_dir = $AppDir; defines = @($Define); compiler = $Clang; built = (Get-Date -Format o) } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'build_info.json') -Encoding utf8
Write-Host "BUILD OK: $dll" -ForegroundColor Green
if ($OutDir) { exit 0 }   # a compile check: the simulator loads only <AppDir>\out\sim
. (Join-Path $PSScriptRoot 'sim_path.ps1')
Write-Host "  run: $(Resolve-SimExe) --game $AppDir [--headless --mute --seconds 20 --frames <dir>]"
exit 0
