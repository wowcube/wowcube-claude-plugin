#!/usr/bin/env bash
# run_info.json of a hidden simulator run (source it: . tools/sim/run_info.sh). bash 3.2 compatible.
# The same fields as run_hidden.ps1 writes, so agents read one shape on every OS (cube_orchestrator SIM_MCP.md,
# VISUAL_GATE.md): pid, exe, start_time, out_dir, work_dir, log, mcp_port, seconds, every_ms, ends_at; plus run_id,
# and after the run exit and ended_at.
#
#   ri_iso_utc [<epoch>]       ISO 8601 UTC time (now, or the given epoch seconds)
#   ri_ends_at <seconds>       when a run of <seconds> started now closes itself (empty for 0 = until stopped)
#   ri_mcp_port <file>         the port of the "[mcp] control socket listening on 127.0.0.1:<port>" line, if any
#   ri_write <path>            writes the file atomically (temp + mv) from the RI_* variables:
#       RI_PID RI_EXE RI_START RI_OUT RI_WORK RI_LOG RI_MCP_PORT RI_SECONDS RI_EVERY_MS RI_ENDS_AT RI_RUN_ID
#       [RI_EXIT RI_ENDED]     (an empty RI_MCP_PORT / RI_ENDS_AT is null; an empty RI_EXIT leaves exit out)
#       [RI_KEEPALIVE RI_KEEPALIVE_LOG]  keepalive: 1 or true = true; starting / failing / failed = that string
#                              (keepalive.py moves "starting" to true after its first complete pulse); else false;
#                              its log (empty = null)
#   ri_keepalive_read <path>   the "keepalive" value run_info.json holds now (true, false, starting, failing, failed),
#                              so a rewrite keeps what keepalive.py set

ri_iso_utc() {
    if [ $# -eq 0 ]; then date -u +%Y-%m-%dT%H:%M:%SZ; return; fi
    date -u -d "@$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$1" +%Y-%m-%dT%H:%M:%SZ
}

ri_ends_at() {
    [ "${1:-0}" -gt 0 ] || return 0
    ri_iso_utc $(( $(date +%s) + $1 ))
}

ri_mcp_port() {
    [ -f "$1" ] || return 0
    sed -n 's/.*\[mcp\] control socket listening on 127\.0\.0\.1:\([0-9][0-9]*\).*/\1/p' "$1" 2>/dev/null | head -n 1
}

# a JSON string literal: backslash, quote and control characters escaped
ri_json_str() {
    local s="$1"
    s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
    s="${s//$'\t'/\\t}"; s="${s//$'\r'/\\r}"; s="${s//$'\n'/\\n}"
    printf '"%s"' "$s"
}

# a JSON number, else null
ri_json_num() {
    case "$1" in ''|*[!0-9-]*) printf 'null';; *) printf '%s' "$1";; esac
}

ri_json_opt_str() {
    if [ -n "$1" ]; then ri_json_str "$1"; else printf 'null'; fi
}

ri_keepalive_read() {
    [ -f "$1" ] || return 0
    tr -d '\r' < "$1" | sed -n 's/^[[:space:]]*"keepalive":[[:space:]]*"\{0,1\}\([a-z]*\)"\{0,1\},\{0,1\}[[:space:]]*$/\1/p' | head -n 1
}

ri_write() {
    local path="$1" tmp
    tmp="$path.tmp.$$"
    {
        printf '{\n'
        printf '  "pid": %s,\n' "$(ri_json_num "${RI_PID:-}")"
        printf '  "exe": %s,\n' "$(ri_json_str "${RI_EXE:-}")"
        printf '  "start_time": %s,\n' "$(ri_json_opt_str "${RI_START:-}")"
        printf '  "out_dir": %s,\n' "$(ri_json_str "${RI_OUT:-}")"
        printf '  "work_dir": %s,\n' "$(ri_json_str "${RI_WORK:-}")"
        printf '  "log": %s,\n' "$(ri_json_str "${RI_LOG:-}")"
        printf '  "mcp_port": %s,\n' "$(ri_json_num "${RI_MCP_PORT:-}")"
        printf '  "seconds": %s,\n' "$(ri_json_num "${RI_SECONDS:-}")"
        printf '  "every_ms": %s,\n' "$(ri_json_num "${RI_EVERY_MS:-}")"
        printf '  "ends_at": %s,\n' "$(ri_json_opt_str "${RI_ENDS_AT:-}")"
        case "${RI_KEEPALIVE:-0}" in
            1|true) printf '  "keepalive": true,\n';;
            starting|failing|failed) printf '  "keepalive": "%s",\n' "$RI_KEEPALIVE";;
            *) printf '  "keepalive": false,\n';;
        esac
        printf '  "keepalive_log": %s,\n' "$(ri_json_opt_str "${RI_KEEPALIVE_LOG:-}")"
        if [ -n "${RI_EXIT:-}" ]; then
            printf '  "exit": %s,\n' "$(ri_json_str "$RI_EXIT")"
            printf '  "ended_at": %s,\n' "$(ri_json_opt_str "${RI_ENDED:-}")"
        fi
        printf '  "run_id": %s\n' "$(ri_json_str "${RI_RUN_ID:-}")"
        printf '}\n'
    } > "$tmp" && mv -f "$tmp" "$path"
}
