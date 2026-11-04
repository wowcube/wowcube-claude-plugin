#!/usr/bin/env python3
"""Keep a hidden simulator run out of battery save by spinning the whole cube about the vertical axis now and then.

Why: after 60 s with no user activity the engine enters battery save, which dims the cube and PAUSES a game. Activity
is a tap, a twist or *sustained movement*; a game's own autoplay bot is none of those, so every unattended hidden run
longer than a minute paused. This client is started by run_hidden.ps1 / run_hidden.sh for runs longer than 50 s (and
for runs until stopped) unless the keep-alive is switched off.

How:
  * the engine counts movement as sustained when the smoothed gyro rate stays above about 625 deg/s (summed over the
    axes) for 300 ms of consecutive motion samples; the idle clock then restarts.
  * the simulator's gyro is the scene rotation of each frame, paid out evenly over that frame (~16.7 ms headless).
    One MCP `turn` is applied in one frame, and a reply comes back on that frame, so sending the next `turn` the
    moment the reply arrives turns the cube once per frame: a steady rate, the way a hand turns it.
  * a pulse is PULSE_TURNS x `turn STEP 0 0` = 1080 deg of yaw (three whole turns, so the cube ends where it started),
    ~0.6 s at 60 fps = ~1800 deg/s, well above the threshold for the whole 300 ms window (and above it still at 30 fps).
    A pulse must last longer than that window: when the replies come faster than MIN_PULSE_S (0.4 s) for the whole
    pulse, the turns are paced so the pulse still lasts MIN_PULSE_S, and the log line says so.
  * yaw is a rotation about the WORLD vertical, so gravity in cube space - what the accelerometer, the tilt API and a
    tilt-controlled game read - does not change at all; only the gyro sees it.

Failures never end it silently: a turn answered with anything but "ok", a reply that does not come within 10 s or a
dropped connection is logged as a WARNING (an ERROR from the third failure in a row on), the connection is opened
again and the pulse is retried with a growing pause (1, 2, 4, 8 ... s, at most the period). It ends only when the
simulator is gone (the run ended: no connection for RECONNECT_S), when --until passes, or when it is stopped.

--run-info <run_info.json>: the wrappers write "keepalive": "starting" there; this client sets it to true after its
first complete pulse, "failing" while pulses fail three times or more in a row (true again after the next good one)
and "failed" when it never reached the simulator. A playtest reads it (and <out>/keepalive.log) to know whether
battery save is being held off.

Side effect: while a pulse runs (~0.6 s every --period s) the cube is "being turned", and the engine drops taps then
("rotating the cube is not tapping it"): an MCP `tap` landing inside a pulse can answer err tap_dropped. Every pulse
is logged with its start time and length, so such a reply can be matched to one; sending the tap again is the answer.

  python keepalive.py --port 8177 [--period 25] [--first 25] [--log <file>] [--until <epoch seconds>]
                      [--run-info <run_info.json>]

Exits 0 when the run ended (the simulator is gone) or --until passes; 1 when it never connects.
"""
import argparse
import json
import os
import socket
import sys
import time

STEP_DEG = 30
PULSE_TURNS = 36            # 36 x 30 = 1080 deg: three whole turns, the pose comes back exactly
MIN_PULSE_S = 0.4           # longer than the engine's 300 ms sustained-movement window, with a margin
REPLY_TIMEOUT_S = 10.0
RECONNECT_S = 5.0           # a connection that cannot be opened again within this time = the run ended
FAILING_AFTER = 3           # consecutive failed pulses before run_info.json says "failing"


def log_line(path, text):
    line = time.strftime("%Y-%m-%dT%H:%M:%S") + " " + text
    if path:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
    else:
        print(line, flush=True)


def set_run_info(path, state):
    """Set "keepalive" in run_info.json to `state` (True / "failing" / "failed"), keeping every other field."""
    if not path:
        return
    for _ in range(10):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                info = json.load(f)
            if info.get("keepalive") == state:
                return
            info["keepalive"] = state
            tmp = "%s.ka.%d" % (path, os.getpid())
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2)
                f.write("\n")
            os.replace(tmp, path)
            return
        except (OSError, ValueError):
            time.sleep(0.1)            # a reader holds it (Windows) or a wrapper is replacing it: try again


class Conn:
    def __init__(self, port, timeout):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.buf = b""

    def ask(self, cmd):
        self.sock.sendall((cmd + "\n").encode())
        while b"\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("simulator closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return line.decode("utf-8", "replace").strip()

    def closed_by_peer(self):
        """True when the simulator closed the connection (checked without blocking)."""
        self.sock.settimeout(0.0)
        try:
            return self.sock.recv(1, socket.MSG_PEEK) == b""
        except (BlockingIOError, socket.timeout):
            return False
        except OSError:
            return True
        finally:
            self.sock.settimeout(REPLY_TIMEOUT_S)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class TurnFailed(RuntimeError):
    pass


def pulse(conn, min_s=MIN_PULSE_S):
    """One keep-alive pulse. Returns (ms, pose_before, pose_after, paced). Raises TurnFailed on a non-ok reply."""
    before = conn.ask("turn 0 0 0")          # a zero turn only reads the pose: "ok cube <yaw> <pitch> <roll>"
    if not before.startswith("ok"):
        raise TurnFailed("pose read failed: " + before)
    t0 = time.perf_counter()
    paced = False                            # perf_counter: monotonic() ticks in ~16 ms on Windows
    for i in range(PULSE_TURNS):
        reply = conn.ask("turn %d 0 0" % STEP_DEG)
        if not reply.startswith("ok"):
            raise TurnFailed("turn %d of %d answered %r" % (i + 1, PULSE_TURNS, reply))
        # never faster than min_s for the whole pulse: turn i+1 is due at t0 + (i+1) * min_s / PULSE_TURNS
        due = t0 + (i + 1) * min_s / PULSE_TURNS
        wait = due - time.perf_counter()
        if wait > 0:
            paced = True
            time.sleep(wait)
    ms = int((time.perf_counter() - t0) * 1000)
    after = conn.ask("turn 0 0 0")
    return ms, before, after, paced


def connect(port, wait_s):
    """A connection, or None when none could be opened within wait_s."""
    deadline = time.monotonic() + wait_s
    last = None
    while True:
        try:
            return Conn(port, timeout=REPLY_TIMEOUT_S), None
        except OSError as e:
            last = e
            if time.monotonic() >= deadline:
                return None, last
            time.sleep(0.5)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--period", type=float, default=25.0, help="seconds between pulses (battery save comes at 60 s idle)")
    ap.add_argument("--first", type=float, default=25.0, help="seconds before the first pulse")
    ap.add_argument("--until", type=float, default=0.0, help="stop at this time (epoch seconds); 0 = when the run ends")
    ap.add_argument("--log", default="", help="append one line per pulse here (default: stdout)")
    ap.add_argument("--run-info", default="", help="run_info.json whose \"keepalive\" field this client keeps current")
    ap.add_argument("--connect-wait", type=float, default=30.0)
    ap.add_argument("--reconnect-wait", type=float, default=RECONNECT_S)
    a = ap.parse_args(argv)

    conn, err = connect(a.port, a.connect_wait)
    if conn is None:
        log_line(a.log, "keepalive: ERROR: no simulator on 127.0.0.1:%d (%s): battery save is NOT held off" % (a.port, err))
        set_run_info(a.run_info, "failed")
        return 1
    log_line(a.log, "keepalive: connected to 127.0.0.1:%d; a %d deg yaw pulse (%d x turn %d 0 0, at least %d ms) every %g s, "
             "first after %g s" % (a.port, STEP_DEG * PULSE_TURNS, PULSE_TURNS, STEP_DEG, MIN_PULSE_S * 1000, a.period, a.first))
    n = 0
    fails = 0
    next_at = time.monotonic() + a.first
    try:
        while True:
            # sleep in short steps, so the end of the run (connection closed) is noticed while waiting
            while time.monotonic() < next_at:
                if a.until and time.time() >= a.until:
                    log_line(a.log, "keepalive: --until reached after %d pulse(s)" % n)
                    return 0
                time.sleep(min(1.0, max(0.0, next_at - time.monotonic())))
                if conn is None or conn.closed_by_peer():
                    if conn is not None:
                        conn.close()
                    conn, err = connect(a.port, a.reconnect_wait)
                    if conn is None:
                        log_line(a.log, "keepalive: stopped after %d complete pulse(s): the simulator is gone (the run ended)" % n)
                        return 0
            started = time.strftime("%H:%M:%S")
            try:
                ms, before, after, paced = pulse(conn)
            except (OSError, ConnectionError, TurnFailed) as e:
                fails += 1
                level = "ERROR" if fails >= FAILING_AFTER else "WARNING"
                retry = min(2.0 ** (fails - 1), max(1.0, a.period))
                if isinstance(e, socket.timeout):
                    what = "no reply within %g s" % REPLY_TIMEOUT_S
                else:
                    what = str(e) or type(e).__name__
                log_line(a.log, "keepalive: %s: pulse %d (started %s) failed (%d in a row): %s; retrying in %g s"
                         % (level, n + 1, started, fails, what, retry))
                if fails >= FAILING_AFTER:
                    set_run_info(a.run_info, "failing")
                # a late reply would answer the next command: always start again on a fresh connection
                conn.close()
                conn, err = connect(a.port, a.reconnect_wait)
                if conn is None:
                    log_line(a.log, "keepalive: stopped after %d complete pulse(s): the simulator is gone (the run ended)" % n)
                    return 0
                next_at = time.monotonic() + retry
                continue
            n += 1
            if fails:
                log_line(a.log, "keepalive: pulse %d succeeded after %d failed attempt(s)" % (n, fails))
            fails = 0
            same = before.split()[2:] == after.split()[2:]
            note = ""
            if paced:
                note += "  (paced: the replies came faster than %d ms a pulse)" % (MIN_PULSE_S * 1000)
            if ms < 300:
                note += "  WARNING: shorter than the engine's 300 ms sustained-movement window"
            if not same:
                note += "  WARNING: pose changed"
            log_line(a.log, "keepalive: pulse %d took %d ms, started %s (%s -> %s)%s" % (n, ms, started, before, after, note))
            set_run_info(a.run_info, True)
            next_at += a.period
            if next_at < time.monotonic():          # after retries: the next pulse a full period from now
                next_at = time.monotonic() + a.period
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
