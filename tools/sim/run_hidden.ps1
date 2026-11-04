<#
.SYNOPSIS
    Run the standalone simulator hidden and silent on Windows, with a visibility watchdog, and report the frames.

.DESCRIPTION
    Starts the installed simulator, <sim dir>\wowcube-sim.exe ($env:WOWCUBE_SIM_DIR, else
    ~\.wowcube\sim\<version>\windows; tools\sim\sim_path.ps1), --headless --mute --game <AppDir> --seconds <Seconds> [--frames ...]
    through tools\sim\hidden_launch.ps1 (SW_HIDE + CREATE_NO_WINDOW; its top-level windows are polled every 50 ms
    and the process is killed BY PID the moment one is visible). Prints the last frame, a seam report for it
    (seams.py, never an exit code) and the summary. The work dir (cfg, logs, the SD-card and flash images that hold
    the game's saves) is <OutDir>\work unless -WorkDir is given, so a run with a new -OutDir starts with empty saves;
    pass the previous run's <OutDir>\work as -WorkDir to relaunch with its saves (a save-survives-relaunch check).
    <OutDir>\run_info.json holds pid, exe, start time, ends_at (when -Seconds runs out) and the MCP port: drive the instance with
    mcp.ps1 -Port <port>, stop it early with stop.ps1 -RunInfo <OutDir>\run_info.json (never a bare kill).

    Exit codes: 0 completed (sim_summary.txt written; with -AllowEarlyStop also a run stopped on purpose) |
    1 setup error | 2 a window became visible (killed) | 3 did not end in time (killed) | 4 no frames |
    5 crashed (exit 99 + headless_crash.txt, an NTSTATUS code, abort() = 3: always a failure) | 6 start error
    (simulator exit 10-14, sim_error.txt) | 7 ended before its timed exit without -AllowEarlyStop |
    8 the plugin is older than the game's sources (rebuild: build_game.ps1, or pass -AllowStale) |
    9 output incomplete (a PNG or the summary could not be written: simulator exit 15; or a PNG on disk does not
    decode) | 10 capture schedule incomplete (a frame slot skipped or dropped: simulator exit 16, or fewer frames
    than -Seconds / -EveryMs owe; -AllowDrops accepts it).
    A completed run means: exit 0, sim_summary.txt of THIS run (run id), completed=1, ok=1, elapsed >= -Seconds,
    as many PNGs on disk as the summary reports written, every one of them decoding (tools\sim\check_frames.py),
    and (unless -AllowDrops) exactly ceil(Seconds*1000 / EveryMs) of them. Every run writes into a fresh -OutDir
    (default) and refuses a frames folder that already holds frames.

.PARAMETER Seconds         Lifetime; the simulator then closes itself. 0 = until stopped (needs -AllowEarlyStop).
.PARAMETER EveryMs         PNG period of all 24 screens; 0 = no periodic frames (an MCP-only session).
.PARAMETER Face            -1 = the six faces as an unfolded cross (default); 0..5 = one face.
.PARAMETER McpPort         First control-socket port to try (default 8177, away from the stock 8077). Taken -> the
                           simulator tries the next ports (up to +15) and logs the one it got; run_info.json and the
                           "mcp: listening on" line report it (8178 = 8177 was still held, e.g. by a run just stopped).
.PARAMETER OutDir          Frames, log.txt, run_info.json (default: a fresh <app>\out\sim\runs\<time>_<id>).
.PARAMETER WorkDir         cfg, log_1.txt and the card images (= saves); default <OutDir>\work. Reuse an earlier
                           run's work dir to keep its saves.
.PARAMETER FreshSaves      Delete the work dir's card images first (saves start empty).
.PARAMETER AllowEarlyStop  Accept a run that ended before -Seconds because it was stopped (stop.ps1: exit -1/1/0).
.PARAMETER AllowStale      Run even when a file in src\ is newer than the plugin (assets are read at every start).
.PARAMETER AllowDrops      Accept frame slots the simulator skipped or dropped (a stall, slow disk): the frames on disk
                           are still all decoded, but their count is not held to the schedule.
.PARAMETER NoKeepAlive     Switch the battery-save keep-alive off. By default a run longer than 50 s (or -Seconds 0)
                           starts tools\sim\keepalive.py once the MCP port is known: every -KeepAliveSec seconds it spins
                           the cube 1080 deg about the vertical axis over ~0.6 s (36 MCP `turn 30 0 0`, one a frame).
                           The engine counts that as sustained movement, so the idle minute that would dim the cube
                           and PAUSE the game (battery save, OCT_BATSAVE_IDLE_MS = 60 s) never runs out; gravity in
                           cube space (tilt) does not change. Pass -NoKeepAlive only to test battery save itself.
                           Pulses are logged to <OutDir>\keepalive.log (an MCP tap inside a pulse may be dropped).
.PARAMETER KeepAliveSec    Seconds between keep-alive pulses (default 25; the first comes after the same time).

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\sim\run_hidden.ps1 -AppDir C:\ws\app_my_game -Seconds 20 -EveryMs 1000
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $AppDir,
    [int] $Seconds = 15,
    [int] $EveryMs = 500,
    [int] $Face = -1,
    [int] $McpPort = 8177,
    [string] $OutDir,
    [string] $WorkDir,
    [string] $Exe,
    [switch] $FreshSaves,
    [switch] $AllowEarlyStop,
    [switch] $AllowStale,
    [switch] $AllowDrops,
    [switch] $NoKeepAlive,
    [int] $KeepAliveSec = 25
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'hidden_launch.ps1')
. (Join-Path $PSScriptRoot 'sim_path.ps1')
function Fail($code, $m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit $code }

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if (-not $Exe) {
    # the installed simulator must be the version this checkout needs (a stale build behaves differently: taps, MCP forms)
    $simCheck = Test-SimExe
    if (-not $simCheck.Ok) { Fail 1 $simCheck.Problem }
    $Exe = $simCheck.Exe
}
if (-not (Test-Path -LiteralPath $Exe)) { Fail 1 "$Exe not found - get it: tools\sim\get_sim.ps1" }
$Exe = (Resolve-Path -LiteralPath $Exe).Path
$AppDir = (Resolve-Path -LiteralPath $AppDir -ErrorAction SilentlyContinue).Path
if (-not $AppDir) { Fail 1 "app folder not found" }
$t = @(Get-ChildItem -LiteralPath $AppDir -Filter *.target -File)
if ($t.Count -ne 1) { Fail 1 "$AppDir must hold exactly one *.target marker" }
$app = [IO.Path]::GetFileNameWithoutExtension($t[0].Name)
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
if ($EveryMs -gt 0 -and -not $py) { Fail 1 "python not found: every frame is checked with tools\sim\check_frames.py" }
if ($Seconds -le 0 -and -not $AllowEarlyStop) { Fail 1 "-Seconds 0 runs until stopped: pass -AllowEarlyStop (and stop it with stop.ps1)" }

# --- stale plugin? (it runs the game as it was compiled) -----------------------
$dll = Join-Path $AppDir "out\sim\$app.dll"
if (-not (Test-Path -LiteralPath $dll)) { Fail 1 "$dll not found - build it: tools\sim\build_game.ps1 -AppDir $AppDir" }
if (-not $AllowStale) {
    $built = (Get-Item -LiteralPath $dll).LastWriteTimeUtc
    # only the code is compiled into the plugin; the packed assets are read at every start
    $newerSrc = @(Get-ChildItem -LiteralPath (Join-Path $AppDir 'src') -Recurse -File -ErrorAction SilentlyContinue |
                  Where-Object { $_.LastWriteTimeUtc -gt $built })
    if ($newerSrc.Count) {
        Fail 8 ("$($newerSrc.Count) source file(s) changed after the plugin build (e.g. $($newerSrc[0].FullName)). " +
                "Rebuild: tools\sim\build_game.ps1 -AppDir $AppDir [-Define ...]   (or pass -AllowStale)")
    }
}

# every run gets its own artifacts: a fresh out dir by default, a run id the simulator echoes into sim_summary.txt
$runId = [guid]::NewGuid().ToString('N')
if (-not $OutDir) { $OutDir = Join-Path $AppDir ("out\sim\runs\" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + $runId.Substring(0, 6)) }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path
if (-not $WorkDir) { $WorkDir = Join-Path $OutDir 'work' }
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$WorkDir = (Resolve-Path -LiteralPath $WorkDir).Path
$frames = Join-Path $OutDir 'frames'
if (@(Get-ChildItem -LiteralPath $frames -Filter 'frame_*.png' -ErrorAction SilentlyContinue).Count) {
    Fail 1 "$frames already holds frames of another run: pass a new -OutDir (or none: each run gets its own)"
}
foreach ($f in 'sim_summary.txt', 'sim_error.txt', 'headless_crash.txt') { Remove-Item (Join-Path $WorkDir $f) -ErrorAction SilentlyContinue }
$logPath = Join-Path $WorkDir 'log_1.txt'
$logStart = if (Test-Path $logPath) { (Get-Item $logPath).Length } else { 0 }

$a = @('--headless', '--mute', '--run-id', $runId, '--game', "`"$AppDir`"", '--seconds', "$Seconds", '--mcp-port', "$McpPort", '--workdir', "`"$WorkDir`"", '--face', "$Face")
if ($EveryMs -gt 0) { $a += @('--frames', "`"$frames`"", '--every-ms', "$EveryMs") }
if ($FreshSaves) { $a += '--fresh-saves' }
if ($AllowDrops) { $a += '--allow-drops' }
$argLine = $a -join ' '
Write-Host "==> $Exe $argLine" -ForegroundColor Cyan

# --- start hidden, record the run --------------------------------------------
$visLog = Join-Path $OutDir 'visibility_log.txt'
$procId = Start-HiddenProcess -Exe $Exe -WorkDir $WorkDir -Arguments $argLine
# the creation handle still pins the PID here (Watch-HiddenProcess releases it), so this is our process
$procStart = $null
try { $procStart = (Get-Process -Id $procId -ErrorAction Stop).StartTime.ToUniversalTime().ToString('o') } catch { }
"pid=$procId exe=$Exe started=$(Get-Date -Format o) process_start=$procStart mcp_port_requested=$McpPort" | Out-File $visLog -Encoding utf8
# ends_at: when the instance closes itself (a playtest brief carries it: the agent must finish before it)
$endsAt = if ($Seconds -gt 0) { (Get-Date).ToUniversalTime().AddSeconds($Seconds).ToString('o') } else { $null }
# battery-save keep-alive (keepalive.py): runs longer than 50 s or until stopped, unless -NoKeepAlive
$keepAlive = (-not $NoKeepAlive) -and ($Seconds -eq 0 -or $Seconds -gt 50)
if ($keepAlive -and -not $py) {
    Write-Host "WARNING: python not found - no keep-alive: the game pauses (battery save) after 60 s without input" -ForegroundColor Yellow
    $keepAlive = $false
}
$kaLog = Join-Path $OutDir 'keepalive.log'
$info = [ordered]@{ pid = $procId; exe = $Exe; start_time = $procStart; out_dir = $OutDir; work_dir = $WorkDir; log = $logPath; mcp_port = $null; seconds = $Seconds; every_ms = $EveryMs; ends_at = $endsAt;
                    keepalive = $keepAlive; keepalive_log = $(if ($keepAlive) { $kaLog } else { $null }) }
$infoPath = Join-Path $OutDir 'run_info.json'
$info | ConvertTo-Json | Set-Content -LiteralPath $infoPath -Encoding utf8
Write-Host ("started hidden: pid $procId  (stop early: tools\sim\stop.ps1 -RunInfo $infoPath; exit 7 unless " +
            "-AllowEarlyStop$(if ($AllowEarlyStop) { ', given' }))  out: $OutDir")

# --- watch: visibility every 50 ms; learn the MCP port from the log ---------------
$script:mcpPort = $null
$script:kaProc = $null
$onPoll = {
    param($elapsedMs)
    if ($script:mcpPort -or -not (Test-Path $logPath)) { return }
    $len = (Get-Item $logPath).Length
    if ($len -le $logStart) { return }
    $fs = [IO.File]::Open($logPath, 'Open', 'Read', 'ReadWrite')
    try { $null = $fs.Seek($logStart, 'Begin'); $buf = New-Object byte[] ($len - $logStart); $null = $fs.Read($buf, 0, $buf.Length) } finally { $fs.Close() }
    $m = [regex]::Match([Text.Encoding]::UTF8.GetString($buf), '\[mcp\] control socket listening on 127\.0\.0\.1:(\d+)')
    if ($m.Success) {
        $script:mcpPort = [int]$m.Groups[1].Value
        $info.mcp_port = $script:mcpPort
        $info | ConvertTo-Json | Set-Content -LiteralPath $infoPath -Encoding utf8
        Write-Host "mcp: listening on 127.0.0.1:$($script:mcpPort)  (t=$elapsedMs ms; client: tools\sim\mcp.ps1 -Port $($script:mcpPort) ping)"
        if ($keepAlive) {
            # hidden like the simulator (no console window); it ends itself when the simulator closes the socket
            $kaArgs = "`"$(Join-Path $PSScriptRoot 'keepalive.py')`" --port $($script:mcpPort) --period $KeepAliveSec --first $KeepAliveSec --log `"$kaLog`""
            try {
                $kaPid = Start-HiddenProcess -Exe $py -WorkDir $OutDir -Arguments $kaArgs
                $script:kaProc = Get-Process -Id $kaPid -ErrorAction Stop   # taken while the creation handle pins the PID
                $null = $script:kaProc.Handle
                [WowcubeHiddenLaunch2]::Release($kaPid)
                Write-Host "keep-alive: pid $kaPid, a yaw pulse every $KeepAliveSec s (log $kaLog; off: -NoKeepAlive)"
            } catch { Write-Host "WARNING: keep-alive did not start ($($_.Exception.Message)): the game pauses after 60 s without input" -ForegroundColor Yellow }
        }
    }
}
$timeout = $(if ($Seconds -gt 0) { $Seconds + 40 } else { 24 * 3600 })
$r = Watch-HiddenProcess -ProcessId $procId -TimeoutSec $timeout -LogFile $visLog -OnPoll $onPoll -Exe $Exe
if ($script:kaProc) {
    # normally gone already (the simulator closed its socket); otherwise stop it through the handle we hold
    if (-not $script:kaProc.WaitForExit(3000)) { try { $script:kaProc.Kill() } catch { } }
    if (Test-Path -LiteralPath $kaLog) { Get-Content -LiteralPath $kaLog | ForEach-Object { "  $_" } }
}

# --- report -------------------------------------------------------------------
$pngs = @(Get-ChildItem -LiteralPath $frames -Filter 'frame_*.png' -ErrorAction SilentlyContinue | Sort-Object Name)
"polls=$($r.Polls) max_windows_owned=$($r.MaxWindows) max_visible=$($r.MaxVisible) exit=$($r.Exit) frames=$($pngs.Count) elapsed_ms=$($r.ElapsedMs)" |
    Out-File $visLog -Append -Encoding utf8
Write-Host "pid $($r.Pid): exit=$($r.Exit) max_visible=$($r.MaxVisible) polls=$($r.Polls) elapsed_ms=$($r.ElapsedMs) mcp_port=$(if ($script:mcpPort) { $script:mcpPort } else { 'not seen' })"
$summary = Join-Path $WorkDir 'sim_summary.txt'
$errFile = Join-Path $WorkDir 'sim_error.txt'
$crash = Join-Path $WorkDir 'headless_crash.txt'
# this run's own log lines (log_1.txt is appended by every run of a work dir)
$logLen = (Get-Item $logPath -ErrorAction SilentlyContinue).Length
if ($logLen -gt $logStart) {
    $fs = [IO.File]::Open($logPath, 'Open', 'Read', 'ReadWrite')
    try { $null = $fs.Seek($logStart, 'Begin'); $buf = New-Object byte[] ($logLen - $logStart); $null = $fs.Read($buf, 0, $buf.Length) } finally { $fs.Close() }
    [IO.File]::WriteAllBytes((Join-Path $OutDir 'log.txt'), $buf)
}

if ($r.Exit -eq 'not-ours') { Fail 1 "PID $procId no longer runs $Exe - nothing was touched" }
if ($r.Exit -eq 'killed-visible' -or $r.MaxVisible -gt 0) { Fail 2 "a window became visible - killed by PID: $($r.FirstVisible)" }
if ($r.Exit -eq 'timeout') { Fail 3 "did not end within $timeout s - killed by PID" }
$crashCode = ($r.Exit -is [int]) -and ($r.Exit -eq 99 -or $r.Exit -eq 3 -or $r.Exit -lt -1)
if ($crashCode -or (Test-Path $crash)) {
    $hex = if ($r.Exit -is [int]) { ' = 0x{0:X8}' -f $r.Exit } else { '' }
    Fail 5 "crashed (exit $($r.Exit)$hex): $(Get-Content $crash -ErrorAction SilentlyContinue)"
}
if (Test-Path $errFile) { Fail 6 "start error (exit $($r.Exit)): $((Get-Content $errFile) -join ' | ')" }
$sum = @{}
if (Test-Path $summary) {
    Get-Content $summary | ForEach-Object { "  $_"; if ($_ -match '^([a-z_]+)=(.*)$') { $sum[$Matches[1]] = $Matches[2] } }
    if ($sum['run_id'] -ne $runId) { Fail 7 "sim_summary.txt belongs to another run (run_id '$($sum['run_id'])', expected $runId)" }
}
if ($r.Exit -eq 15) { Fail 9 "the simulator could not write its output (a PNG or sim_summary.txt; disk full or permissions?): $OutDir\log.txt" }
$lostSlots = ([int]("0" + $sum['dropped'])) + ([int]("0" + $sum['skipped']))
# exit 16 = the simulator's "capture schedule incomplete"; a summary with ok=0 and lost slots means the same even when
# the exit code got lost on the way (an older simulator, a wrapper): never report that as "no summary"
if ($r.Exit -eq 16 -or ($sum.Count -and $sum['ok'] -eq '0' -and $lostSlots -gt 0 -and -not $AllowDrops)) {
    Fail 10 ("frame slots were lost (simulator exit $($r.Exit); summary ok=$($sum['ok']) dropped=$($sum['dropped']) " +
             "skipped=$($sum['skipped']) expected=$($sum['expected'])): the host stalled (often during the boot intro at " +
             "-EveryMs below 250) or the disk is slow; -AllowDrops accepts it when gaps between frames do not matter")
}
if ($pngs.Count) {
    Write-Host "frames: $($pngs.Count) in $frames"
    Write-Host "last frame: $($pngs[-1].FullName)"
    # thin background lines on screen edges (screen-filling art placed at +-120): a report, never an exit code
    if ($py) {
        $seamArgs = @((Join-Path $PSScriptRoot 'seams.py'), $pngs[-1].FullName)
        if ($Face -ge 0) { $seamArgs += '--face' }
        & $py @seamArgs | ForEach-Object { "  $_" }
    }
}
Write-Host "log: $OutDir\log.txt (this run)"
if ($EveryMs -gt 0 -and $pngs.Count -eq 0) { Fail 4 "no frames in $frames" }
if (-not ($r.Exit -eq 0 -and $sum['completed'] -eq '1')) {
    # only what a deliberate stop leaves: -1 (stop.ps1 / Process.Kill), 1 (TerminateProcess), 0
    if ($AllowEarlyStop -and ($r.Exit -is [int]) -and ($r.Exit -in @(-1, 0, 1))) {
        Write-Host "NOTE: stopped before its timed exit (exit $($r.Exit)) - accepted: -AllowEarlyStop" -ForegroundColor Yellow
        exit 0
    }
    $what = if ($sum.Count) { "sim_summary.txt: completed=$($sum['completed']) ok=$($sum['ok']) elapsed_ms=$($sum['elapsed_ms'])" }
            else { "no sim_summary.txt in $WorkDir" }
    Fail 7 "ended before its timed exit (exit $($r.Exit), $what); log: $OutDir\log.txt"
}
# a completed run: exit 0, its own summary, the full requested time, every capture written and on disk
if ($sum['ok'] -ne '1') { Fail 9 "the run's output is incomplete (summary ok=$($sum['ok']), write_failed=$($sum['write_failed']))" }
if ([int64]$sum['elapsed_ms'] -lt [int64]$Seconds * 1000) { Fail 7 "ran $($sum['elapsed_ms']) ms, less than the requested $Seconds s" }
if ($EveryMs -gt 0) {
    # every PNG decodes, as many as written, and (strict) as many as the schedule owes
    $expect = [int][math]::Ceiling($Seconds * 1000.0 / [math]::Max($EveryMs, 10))
    $cfArgs = @((Join-Path $PSScriptRoot 'check_frames.py'), $frames, $summary, '--expect', "$expect")
    if ($AllowDrops) { $cfArgs += '--allow-drops' }
    & $py @cfArgs | ForEach-Object { "  $_" }
    switch ($LASTEXITCODE) {
        0 { }
        1 { Fail 9 "a frame PNG does not decode (truncated or corrupt; above)" }
        2 { Fail 4 "the summary reports $($sum['written']) frames written, $frames holds $($pngs.Count)" }
        4 { Fail 10 "the capture schedule is incomplete (above); -AllowDrops accepts it" }
        default { Fail 1 "check_frames.py failed (exit $LASTEXITCODE)" }
    }
}
Write-Host "OK: never visible; timed run completed" -ForegroundColor Green
exit 0
