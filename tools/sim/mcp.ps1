<#
.SYNOPSIS
    Send wire commands to a running simulator's MCP control socket (127.0.0.1 only) and print the replies.

.DESCRIPTION
    One command per argument, one reply line per command, e.g.
      mcp.ps1 -RunInfo C:\ws\assets_x\qa\sim\p03-play\run_info.json ping info "screens faces C:\shots\p3_faces.png"
      mcp.ps1 -Port 8177 "twist 3" idle "sleep 200" "screens faces C:\shots\after.png" "record 40 50 C:\shots\rec_"
    Commands (skills\cube_orchestrator\SIM_MCP.md): ping | info | log | screens [faces] <png> | record <n 1..100>
    <ms 20..2000> <prefix> | twist <0..23> | tap quad <0..23> | tap face <0..5> <0..3> | tap module <0..7> <0..2> |
    tap <x> <y> | shake | cube <yaw> <pitch> <roll> | turn ... | (tap quad/face/module ... double = a double tap;
    taps are spaced by the simulator, no "sleep" between them) |
    camera <yaw> <pitch> | orbit ... | face <0..5> | reset | unfold <0|1> | idle | shot <max_side> <png>.
    Client-side (never sent): sleep <ms> - wait, e.g. after "twist"/"idle" so the game draws the new state
    (the reply comes when the snap settles; the modules redraw on their next ticks, 50 ms each).
    In a hidden instance prefer `screens` / `record` (they read the 24 framebuffers) over `shot` (window
    back buffer). Exit code 1 when any reply starts with "err" or a connection fails.

.PARAMETER Port        The control port (run_hidden.ps1 prints it; run_info.json "mcp_port").
.PARAMETER RunInfo     <OutDir>\run_info.json of run_hidden.ps1 instead of -Port: the port is read from it, else from
                       the "[mcp] control socket listening on 127.0.0.1:<port>" line of the run's log (the instance
                       may still be starting: waits up to -WaitSec).
.PARAMETER TimeoutSec  Read timeout per reply (default 60). A `record n ms` reply gets at least n*ms + n/4 s + 30 s,
                       the simulator's own budget plus a margin, so one long recording never times out here first.
#>
# Only named parameters bind by name: every bare word is a command (without this, "ping" bound to -TimeoutSec).
[CmdletBinding(PositionalBinding = $false)]
param(
    [int] $Port = 0,
    [string] $RunInfo,
    [int] $WaitSec = 30,
    [int] $TimeoutSec = 60,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]] $Command
)
if (-not $Command -or $Command.Count -eq 0) { Write-Host "usage: mcp.ps1 (-Port <port> | -RunInfo <run_info.json>) <command> [<command> ...]"; exit 1 }

function Get-PortFromRunInfo([string]$Path, [int]$Wait) {
    $deadline = (Get-Date).AddSeconds($Wait)
    do {
        $j = $null
        try { $j = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop | ConvertFrom-Json } catch { }
        if ($j -and $j.mcp_port) { return [int]$j.mcp_port }
        # the watcher may have stopped (its shell call ended) while the simulator runs on: read the run's log
        if ($j -and $j.log -and (Test-Path -LiteralPath $j.log)) {
            $fs = $null
            try {
                $fs = [IO.File]::Open($j.log, 'Open', 'Read', 'ReadWrite')
                $text = (New-Object IO.StreamReader($fs)).ReadToEnd()
                $ms = [regex]::Matches($text, '\[mcp\] control socket listening on 127\.0\.0\.1:(\d+)')
                if ($ms.Count) { return [int]$ms[$ms.Count - 1].Groups[1].Value }
            } catch { } finally { if ($fs) { $fs.Close() } }
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    return 0
}

if ($RunInfo) {
    if (-not (Test-Path -LiteralPath $RunInfo)) { "ERROR: $RunInfo not found (run_hidden.ps1 writes it at start)"; exit 1 }
    $Port = Get-PortFromRunInfo $RunInfo $WaitSec
    if (-not $Port) { "ERROR: no MCP port in $RunInfo or its log after $WaitSec s (did the instance start? see its log)"; exit 1 }
    "# port $Port"
}
if (-not $Port) { $Port = 8177 }

# the reply budget of one command: `record n ms` runs n*ms plus the PNG encode (the simulator allows 15 s + n*ms + n/4 s)
function Get-ReadTimeoutMs([string]$c) {
    $m = [regex]::Match($c, '^\s*record\s+(\d+)\s+(\d+)')
    if ($m.Success) {
        $n = [int]$m.Groups[1].Value; $ms = [int]$m.Groups[2].Value
        return [Math]::Max($TimeoutSec * 1000, $n * $ms + [int]($n / 4) * 1000 + 30000)
    }
    return $TimeoutSec * 1000
}

$failed = $false
try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.ReceiveTimeout = $TimeoutSec * 1000
    $client.SendTimeout = 5000
    $client.Connect('127.0.0.1', $Port)
    $stream = $client.GetStream()
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $writer = New-Object System.IO.StreamWriter($stream, $utf8); $writer.NewLine = "`n"; $writer.AutoFlush = $true
    $reader = New-Object System.IO.StreamReader($stream, $utf8)
    foreach ($c in $Command) {
        $s = [regex]::Match($c, '^\s*sleep\s+(\d+)\s*$')
        if ($s.Success) { Start-Sleep -Milliseconds ([int]$s.Groups[1].Value); "> $c"; "< ok sleep (client)"; continue }
        $client.ReceiveTimeout = Get-ReadTimeoutMs $c
        $writer.WriteLine($c)
        $reply = $reader.ReadLine()
        "> $c"
        "< $reply"
        if ($null -eq $reply -or $reply.StartsWith('err')) { $failed = $true }
    }
    $client.Close()
} catch {
    "ERROR: $($_.Exception.Message) (is a simulator listening on 127.0.0.1:$($Port)? run_hidden.ps1 prints the port; -RunInfo reads it)"
    exit 1
}
if ($failed) { exit 1 } else { exit 0 }
