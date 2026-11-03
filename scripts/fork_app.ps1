<#
.SYNOPSIS
    Fork a working app into a NEW game: copy app_<old> to app_<new> with the marker, headers, includes and APP_DIR
    renamed, a fresh random APP_GUID1, the new APP_TITLE and version 0.0.0 (the first repack_app ships 0.1.0). The source is never changed.

.DESCRIPTION
    Windows entry point of scripts\fork_app.py (one implementation for Windows, Linux and macOS; the same rename rules
    new_app.ps1 applies to the template). Builds nothing and starts nothing: afterwards rebuild the plugin
    (tools\sim\build_game.ps1) and repack (scripts\repack_app.py). The workspace next to the source (assets_<old>\,
    plans\<old>_*) is copied as assets_<new>\ and plans\<new>_* when present.

.PARAMETER Source     The working app folder to fork (app_<old>).
.PARAMETER Name       The new game's name: <new> or app_<new>.
.PARAMETER Workspace  Where app_<new> goes. Default: the folder that holds the source.
.PARAMETER Title      APP_TITLE of the fork (<= 79 bytes). Default: from the name.
.PARAMETER Json       Print the result (identity for the context's import record) as JSON.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File .\fork_app.ps1 -Source C:\ws\app_my_game -Name my_game_night -Title "My Game Night"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string] $Source,
    [Parameter(Mandatory = $true)] [string] $Name,
    [string] $Workspace,
    [string] $Title,
    [switch] $Json
)
$ErrorActionPreference = 'Stop'
$py = Join-Path $PSScriptRoot 'fork_app.py'
$argv = @($py, '--source', $Source, '--name', $Name)
if ($Workspace) { $argv += @('--workspace', $Workspace) }
if ($Title) { $argv += @('--title', $Title) }
if ($Json) { $argv += '--json' }
& python @argv
exit $LASTEXITCODE
