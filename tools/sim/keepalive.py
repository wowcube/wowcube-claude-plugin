#!/usr/bin/env python3
"""Keep a hidden simulator run out of battery save by spinning the whole cube about the vertical axis now and then.

Why: after OCT_BATSAVE_IDLE_MS (60 s) with no user activity the engine enters battery save, which dims the cube and
PAUSES a game (APP_CATEGORY_GAME). Activity is a tap, a twist or *sustained movement*; a game's own autoplay bot is
none of those, so every unattended hidden run longer than a minute paused. This client is started by run_hidden.ps1 /
run_hidden.sh for runs longer than 50 s (and for runs until stopped) unless the keep-alive is switched off.

How (engine/oct_gesture_core.h, sim/src/sim_thread_module.h of the simulator sources):
  * sustained movement = the smoothed gyro L1 above OCT_MOTION_GYRO_THR (625 deg/s summed over the axes) for
    OCT_MOTION_SUSTAINED_MS (300 ms) of consecutive IMU samples; the leader then stamps activity, and the cube-wide
    bit stays fresh for 1 s (OCT_MOTION_FRESH_MS).
  * the simulator's gyro is the scene rotation of each frame, paid out evenly over that frame (~16.7 ms headless).
    One MCP `turn` is applied in one frame, and a reply comes back on that frame, so sending the next `turn` the
    moment the reply arrives turns the cube once per frame: a steady rate, the way a hand turns it.
  * a pulse is PULSE_TURNS x `turn STEP 0 0` = 1080 deg of yaw (three whole turns, so the cube ends where it started),
    ~0.6 s at 60 fps = ~1800 deg/s, well above the threshold for the whole 300 ms window (and above it still at 30 fps).
  * yaw is a rotation about the WORLD vertical (SetCubeAngles applies it last), so gravity in cube space - what the
    accelerometer, the tilt API and a tilt-controlled game read - does not change at all; only the gyro sees it.

Side effect: while a pulse runs (~0.6 s every --period s) the cube is "being turned", and the engine drops taps then
("rotating the cube is not tapping it"): an MCP `tap` landing inside a pulse can answer err tap_dropped. Every pulse
is logged with its time, so such a reply can be matched to one; retrying the tap is the answer.

  python keepalive.py --port 8177 [--period 25] [--first 25] [--log <file>] [--until <epoch seconds>]

Exits 0 when the simulator closes the connection (the run ended) or --until passes; 1 when it never connects.
"""
import argparse
import socket
import sys
import time

STEP_DEG = 30
PULSE_TURNS = 36            # 36 x 30 = 1080 deg: three whole turns, the pose comes back exactly


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

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def pulse(conn):
    """One keep-alive pulse. Returns (ms, pose_before, pose_after)."""
    before = conn.ask("turn 0 0 0")          # a zero turn only reads the pose: "ok cube <yaw> <pitch> <roll>"
    t0 = time.monotonic()
    for _ in range(PULSE_TURNS):
        reply = conn.ask("turn %d 0 0" % STEP_DEG)
        if not reply.startswith("ok"):
            raise RuntimeError("turn failed: " + reply)
    ms = int((time.monotonic() - t0) * 1000)
    after = conn.ask("turn 0 0 0")
    return ms, before, after


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--period", type=float, default=25.0, help="seconds between pulses (battery save comes at 60 s idle)")
    ap.add_argument("--first", type=float, default=25.0, help="seconds before the first pulse")
    ap.add_argument("--until", type=float, default=0.0, help="stop at this time (epoch seconds); 0 = when the run ends")
    ap.add_argument("--log", default="", help="append one line per pulse here (default: stdout)")
    ap.add_argument("--connect-wait", type=float, default=30.0)
    a = ap.parse_args(argv)

    conn = None
    deadline = time.monotonic() + a.connect_wait
    while conn is None:
        try:
            conn = Conn(a.port, timeout=10)
        except OSError as e:
            if time.monotonic() > deadline:
                log_line(a.log, "keepalive: no simulator on 127.0.0.1:%d (%s)" % (a.port, e))
                return 1
            time.sleep(0.5)
    log_line(a.log, "keepalive: connected to 127.0.0.1:%d; a %d deg yaw pulse (%d x turn %d 0 0) every %g s, first after %g s"
             % (a.port, STEP_DEG * PULSE_TURNS, PULSE_TURNS, STEP_DEG, a.period, a.first))
    n = 0
    next_at = time.monotonic() + a.first
    try:
        while True:
            # sleep in short steps, so the end of the run (connection closed) is noticed while waiting
            while time.monotonic() < next_at:
                if a.until and time.time() >= a.until:
                    log_line(a.log, "keepalive: --until reached after %d pulse(s)" % n)
                    return 0
                time.sleep(min(1.0, max(0.0, next_at - time.monotonic())))
                conn.sock.settimeout(0.0)
                try:
                    if conn.sock.recv(1, socket.MSG_PEEK) == b"":
                        raise ConnectionError("simulator closed the connection")
                except (BlockingIOError, socket.timeout):
                    pass
                finally:
                    conn.sock.settimeout(10)
            ms, before, after = pulse(conn)
            n += 1
            same = before.split()[2:] == after.split()[2:]
            log_line(a.log, "keepalive: pulse %d took %d ms (%s -> %s)%s"
                     % (n, ms, before, after, "" if same else "  WARNING: pose changed"))
            next_at += a.period
    except (OSError, ConnectionError, RuntimeError) as e:
        log_line(a.log, "keepalive: stopped after %d complete pulse(s): %s" % (n, e))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
