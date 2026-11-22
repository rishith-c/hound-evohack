"""
r4.py — the Pi's link to the UNO R4 drive controller over USB serial.

The R4 firmware (firmware/r4_drive) stops all motors if it hears nothing for 400 ms,
so this class keeps a background thread re-sending the current command at 10 Hz.
Set a velocity once; it holds until you change it or call stop().

    from r4 import R4
    r = R4()                  # finds the board on /dev/serial/by-id or /dev/ttyACM*
    r.velocity(100, 0, 0)     # forward 100 mm/s
    r.velocity(0, 80, 0)      # strafe left 80 mm/s
    r.velocity(0, 0, 0.5)     # rotate counter-clockwise 0.5 rad/s
    r.stop()
    print(r.status)           # last JSON the board reported
"""
import glob
import json
import threading
import time

import serial


class R4:
    KEEPALIVE_S = 0.1          # must stay well under the firmware's 400 ms watchdog

    def __init__(self, port=None, baud=115200):
        self.port = port or self.find_port()
        try:
            self.ser = serial.Serial(self.port, baud, timeout=0.05, exclusive=True)   # one owner: two would override each other's commands
        except serial.SerialException as e:
            if "exclusively lock" in str(e):
                raise serial.SerialException(f"{e} — another program has the R4; if it is the remote: sudo systemctl stop rover-web") from e
            raise
        self.ser.dtr = True
        time.sleep(1.0)
        self.ser.reset_input_buffer()
        self.status = {}
        self._cmd = "s"
        self._lock = threading.Lock()
        self._io = threading.Lock()
        self._send("?")                                      # first status BEFORE the keepalive thread exists
        self._alive = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @staticmethod
    def find_port():
        for p in sorted(glob.glob("/dev/serial/by-id/*")):
            if "Arduino" in p or "UNO" in p or "R4" in p:
                return p
        acm = sorted(glob.glob("/dev/ttyACM*"))
        if acm:
            return acm[0]
        raise RuntimeError("no UNO R4 found on USB")

    # ── commands ──────────────────────────────────────────────────────
    def velocity(self, vx_mm_s, vy_mm_s, wz_rad_s):
        """vx forward, vy left (mm/s), wz counter-clockwise (rad/s). Held until changed."""
        with self._lock:
            self._cmd = f"v {vx_mm_s:.1f} {vy_mm_s:.1f} {wz_rad_s:.4f}"

    def jog(self, wheel, direction, mm_s=60):
        """Single wheel: 0=FL 1=FR 2=BL 3=BR, direction ±1."""
        with self._lock:
            self._cmd = f"j {wheel} {direction} {mm_s:.1f}"

    def stop(self):
        with self._lock:
            self._cmd = "s"

    def tilt(self, deg):
        """Tilt servo (PCA9685 channel 3, driven by the R4): 78–150°, or -1 to release the servo (no pulses)."""
        self._send(f"t {int(deg)}")

    def pan_stop(self):
        """Cut the pan pulse (the Ceres pan servo is continuous-rotation: no pulse = coast to a stop)."""
        self._send("p 0")

    def nudge_pan(self, direction, ms=300):
        """Ceres-style pan: an eased turn for ms milliseconds (+1 right, −1 left), then the pulse is cut. ~20° per 300 ms nudge."""
        self._send(f"n {1 if direction > 0 else -1} {int(ms)}")

    def pan(self, deg=None):
        """Kept for callers: any angle request just stops the pan (it cannot hold an angle)."""
        self.pan_stop()

    def hold_enable(self, on):
        """Keep the drivers energised while stopped (holding torque, more heat)."""
        self._send(f"e {1 if on else 0}")

    def invert(self, wheel):
        """Flip one wheel's direction; the R4 saves it to EEPROM."""
        self._send(f"i {wheel}")

    def close(self):
        self.stop()
        time.sleep(0.25)
        self._alive = False
        self._thread.join(timeout=1.0)
        try:
            self.ser.write(b"s\n")
        finally:
            self.ser.close()

    # ── internals ─────────────────────────────────────────────────────
    def _loop(self):
        while self._alive:
            with self._lock:
                cmd = self._cmd
            try:
                self._send(cmd)
            except serial.SerialException:
                pass
            time.sleep(self.KEEPALIVE_S)

    def _send(self, cmd):
        with self._io:                                       # one serial exchange at a time: two readers on the port crash pyserial
            self.ser.write((cmd + "\n").encode())
            chunk = self.ser.read(2000)
            self._buf = getattr(self, "_buf", b"") + chunk      # inside the lock: callers on other threads share the buffer
            *lines, self._buf = self._buf.split(b"\n")      # keep the unfinished tail for next time
        for line in reversed(lines):
            line = line.strip()
            if line.startswith(b"{") and line.endswith(b"}"):
                try:
                    self.status = json.loads(line.decode(errors="replace"))
                    break
                except ValueError:
                    continue

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
