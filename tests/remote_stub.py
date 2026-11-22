#!/usr/bin/env python3
"""Serve the Pi remote (pi/rover/web.py) on this computer against a fake R4 — for working on the page without the rover.

    python3 tests/remote_stub.py [port]        → http://localhost:8099/?k=dev

The Wi-Fi network view listens on UDP 5005 here too (it needs a Python with numpy); feed it simulated people with
`python ml/replay.py --kind moving` in another terminal.

Commands are printed instead of sent; the fake R4 reports a held tilt and a found servo board. Recordings and the
pan trim go to a throwaway HOME, never to ~/rover."""
import os
import sys
import tempfile
import time
import types

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
HOME = tempfile.mkdtemp(prefix="hound-remote-")
os.makedirs(os.path.join(HOME, "rover"))
open(os.path.join(HOME, "rover", "web.key"), "w").write("dev")
os.environ["HOME"] = HOME


class FakeR4:
    port = "stub"

    def __init__(self, *a, **k):
        self.status = {"tilton": 1, "tilt": 92, "rate": [0, 0, 0, 0], "inv": [0, 0, 0, 0], "ms": 32, "spm": 25.46,
                       "maxmm": 530, "en": 0, "wd": 0, "pca": 1, "ptrim": 0, "ppos": 0, "vbat": 0}

    def _send(self, cmd):
        print(f"{time.strftime('%H:%M:%S')}  R4 ← {cmd}", flush=True)
        if cmd.startswith("T "): self.status["ptrim"] = int(cmd.split()[1])
        if cmd.startswith("K "): self.status["show"] = int(float(cmd.split()[1]) > 0.5)     # the R4 reports its show state

    def tilt(self, d): self._send(f"t {int(d)}"); self.status.update(tilt=int(d), tilton=int(d) >= 0)
    def nudge_pan(self, d, ms=300): self._send(f"n {1 if d > 0 else -1} {int(ms)}")
    def pan_stop(self): self._send("p 0")
    def velocity(self, vx, vy, wz): self._send(f"v {vx:.0f} {vy:.0f} {wz:.3f}")
    def stop(self): self._send("s")
    def jog(self, w, d, s=60): self._send(f"j {w} {d} {s}")
    def hold_enable(self, on): self._send(f"e {int(on)}")
    def close(self): pass


sys.modules["r4"] = types.SimpleNamespace(R4=FakeR4)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pi", "rover"))
import web  # noqa: E402
web.SENSING = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sensing")   # the repo's, not ~/rover's
web.ML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ml")             # the Wi-Fi network

print(f"Hound remote (stub R4) → http://localhost:{PORT}/?k=dev   (throwaway HOME {HOME})", flush=True)
web.ThreadingHTTPServer(("127.0.0.1", PORT), web.H).serve_forever()
