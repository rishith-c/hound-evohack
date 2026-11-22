#!/usr/bin/env python3
"""
thermal_gui.py — live MLX90640 thermal camera viewer for the thermal_bridge.ino Arduino (UNO R3 or R4).

    pip install pyserial numpy pillow adafruit-circuitpython-mlx90640
    python3 thermal_gui.py                # picks the first Arduino-looking port; or --port /dev/cu.usbmodem…
    python3 thermal_gui.py --demo         # no hardware: a synthetic warm person walking across the frame

The Arduino is only an I2C bridge; the Melexis calibration maths runs here through Adafruit's CircuitPython driver,
fed by a fake I2C bus that talks the bridge protocol over serial.
"""
import argparse
import csv
import math
import struct
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

import numpy as np
from PIL import Image, ImageTk

W, H = 32, 24


# ── the bridge: a fake busio.I2C that the Adafruit driver can use ─────────────────────────────────────────────
class SerialI2C:
    def __init__(self, ser):
        self.ser = ser; self.lock = threading.Lock()

    def try_lock(self): return True
    def unlock(self): pass
    def scan(self): return [0x33]

    def writeto(self, address, buffer, *, start=0, end=None):
        buf = bytes(buffer[start:end])
        if not buf: return                                   # the driver's probe writes an empty buffer
        with self.lock:
            self.ser.write(b"W" + bytes([len(buf)]) + buf)
            st = self.ser.read(1)
        if st != b"\x00": raise OSError(f"I2C write failed (status {st!r})")

    def readfrom_into(self, address, buffer, *, start=0, end=None):
        raise OSError("bridge has no plain read")

    def writeto_then_readfrom(self, address, out, inb, *, out_start=0, out_end=None, in_start=0, in_end=None):
        reg = bytes(out[out_start:out_end]); n = (len(inb) if in_end is None else in_end) - in_start; words = n // 2
        with self.lock:
            self.ser.write(b"R" + reg[:2] + words.to_bytes(2, "big"))
            data = self.ser.read(words * 2); st = self.ser.read(1)
        if len(data) != words * 2 or st != b"\x00": raise OSError(f"I2C read failed at 0x{reg.hex()} (status {st!r}, {len(data)} bytes)")
        inb[in_start:in_start + len(data)] = data


def open_sensor(port, rate):
    import serial
    import adafruit_mlx90640
    ser = serial.Serial(port, 115200, timeout=3)
    time.sleep(2.0)                                          # the R3 resets on connect
    ser.reset_input_buffer(); ser.write(b"P")
    if ser.read(2) != b"OK": raise RuntimeError("no bridge on that port — is thermal_bridge.ino flashed?")
    mlx = adafruit_mlx90640.MLX90640(SerialI2C(ser))
    rates = {1: adafruit_mlx90640.RefreshRate.REFRESH_1_HZ, 2: adafruit_mlx90640.RefreshRate.REFRESH_2_HZ,
             4: adafruit_mlx90640.RefreshRate.REFRESH_4_HZ, 8: adafruit_mlx90640.RefreshRate.REFRESH_8_HZ}
    mlx.refresh_rate = rates[rate]
    return ser, mlx


def auto_port():
    from serial.tools import list_ports
    ports = list(list_ports.comports())
    for p in ports:
        if any(k in (p.description or "").lower() + (p.device or "").lower() for k in ("arduino", "usbmodem", "usbserial", "ch340", "cp210", "ttyacm", "ttyusb")):
            return p.device
    return ports[0].device if ports else None


# ── colour maps (no matplotlib needed) ───────────────────────────────────────────────────────────────────────
def lut(anchors):
    xs = np.linspace(0, 1, len(anchors)); cols = np.array(anchors, float)
    t = np.linspace(0, 1, 256)
    return np.stack([np.interp(t, xs, cols[:, i]) for i in range(3)], 1).astype(np.uint8)


LUTS = {
    "inferno": lut([(0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99), (212, 72, 66), (245, 125, 21), (250, 193, 39), (252, 255, 164)]),
    "jet": lut([(0, 0, 131), (0, 60, 255), (0, 200, 255), (110, 255, 140), (255, 240, 0), (255, 90, 0), (128, 0, 0)]),
    "ironbow": lut([(0, 0, 0), (32, 0, 96), (120, 0, 160), (200, 40, 110), (240, 110, 30), (255, 190, 0), (255, 255, 200)]),
    "gray": lut([(0, 0, 0), (255, 255, 255)]),
}


# ── demo frames: a warm blob walking across a 22 °C room ────────────────────────────────────────────────────
def demo_frame(t):
    yy, xx = np.mgrid[0:H, 0:W]
    cx = 6 + (t * 3) % 20; cy = 12 + 3 * math.sin(t)
    body = 12.0 * np.exp(-(((xx - cx) / 3.2) ** 2 + ((yy - cy) / 5.0) ** 2))
    head = 14.0 * np.exp(-(((xx - cx) / 1.6) ** 2 + ((yy - cy + 6) / 1.8) ** 2))
    lamp = 20.0 * np.exp(-(((xx - 27) / 1.2) ** 2 + ((yy - 4) / 1.2) ** 2))
    return 22.0 + body + head + lamp + np.random.normal(0, 0.15, (H, W))


# ── the GUI ──────────────────────────────────────────────────────────────────────────────────────────────────
class App:
    SCALE = 22

    def __init__(self, root, port, demo, rate):
        self.root = root; root.title("MLX90640 thermal — Hound test rig")
        self.frame = np.full((H, W), 22.0); self.frozen = None; self.fps = 0.0; self.t_last = time.time(); self.ta = None
        self.err = None; self.running = True; self.demo = demo; self.port = port; self.rate = rate; self.mlx = None; self.ser = None
        self.hist = []

        bar = ttk.Frame(root, padding=6); bar.pack(fill="x")
        self.var_cmap = tk.StringVar(value="inferno"); self.var_auto = tk.BooleanVar(value=True); self.var_smooth = tk.BooleanVar(value=True)
        self.var_mirror = tk.BooleanVar(value=True); self.var_min = tk.DoubleVar(value=20.0); self.var_max = tk.DoubleVar(value=36.0); self.var_freeze = tk.BooleanVar(value=False)
        ttk.Label(bar, text="colours").pack(side="left"); ttk.OptionMenu(bar, self.var_cmap, "inferno", *LUTS).pack(side="left", padx=(2, 10))
        ttk.Checkbutton(bar, text="auto range", variable=self.var_auto).pack(side="left")
        ttk.Label(bar, text="min").pack(side="left", padx=(10, 2)); ttk.Spinbox(bar, from_=-40, to=300, increment=1, textvariable=self.var_min, width=5).pack(side="left")
        ttk.Label(bar, text="max").pack(side="left", padx=(6, 2)); ttk.Spinbox(bar, from_=-40, to=300, increment=1, textvariable=self.var_max, width=5).pack(side="left")
        ttk.Checkbutton(bar, text="smooth", variable=self.var_smooth).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(bar, text="mirror", variable=self.var_mirror).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(bar, text="freeze", variable=self.var_freeze, command=self.toggle_freeze).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="save PNG", command=self.save_png).pack(side="right", padx=2)
        ttk.Button(bar, text="save CSV", command=self.save_csv).pack(side="right", padx=2)

        self.canvas = tk.Canvas(root, width=W * self.SCALE, height=H * self.SCALE, bg="#000", highlightthickness=0); self.canvas.pack()
        self.canvas.bind("<Motion>", self.on_motion); self.hover = None
        self.status = ttk.Label(root, text="connecting…", padding=6, font=("Menlo", 11)); self.status.pack(fill="x")
        self.strip = tk.Canvas(root, width=W * self.SCALE, height=70, bg="#111", highlightthickness=0); self.strip.pack()

        threading.Thread(target=self.reader, daemon=True).start()
        self.tick()

    # reader thread: hardware or demo
    def reader(self):
        t0 = time.time()
        if self.demo:
            while self.running:
                self.push(demo_frame(time.time() - t0), 22.5); time.sleep(0.25)
            return
        try:
            self.ser, self.mlx = open_sensor(self.port, self.rate)
            buf = [0.0] * (W * H)
            while self.running:
                try:
                    self.mlx.getFrame(buf)
                except (OSError, ValueError) as e:              # a bad frame over serial: skip it
                    self.err = f"frame error: {e}"; continue
                self.push(np.array(buf).reshape(H, W), None)
        except Exception as e:
            self.err = f"{e.__class__.__name__}: {e}"

    def push(self, fr, ta):
        now = time.time(); dt = now - self.t_last; self.t_last = now
        self.fps = 0.8 * self.fps + 0.2 * (1 / dt if dt > 0 else 0)
        self.frame = fr; self.ta = ta; self.err = None
        self.hist.append((now, float(fr.max()), float(fr.mean()))); self.hist = self.hist[-300:]

    def toggle_freeze(self):
        self.frozen = self.frame.copy() if self.var_freeze.get() else None

    def current(self):
        fr = self.frozen if self.frozen is not None else self.frame
        return fr[:, ::-1] if self.var_mirror.get() else fr

    def render(self):
        fr = self.current()
        lo, hi = (float(fr.min()), float(fr.max())) if self.var_auto.get() else (self.var_min.get(), self.var_max.get())
        if hi - lo < 0.5: hi = lo + 0.5
        idx = np.clip(((fr - lo) / (hi - lo) * 255), 0, 255).astype(np.uint8)
        rgb = LUTS[self.var_cmap.get()][idx]
        img = Image.fromarray(rgb).resize((W * self.SCALE, H * self.SCALE), Image.BICUBIC if self.var_smooth.get() else Image.NEAREST)
        self.photo = ImageTk.PhotoImage(img)
        c = self.canvas; c.delete("all"); c.create_image(0, 0, anchor="nw", image=self.photo)
        # hottest / coldest markers
        (hy, hx) = np.unravel_index(int(fr.argmax()), fr.shape); (cy, cx) = np.unravel_index(int(fr.argmin()), fr.shape)
        s = self.SCALE
        for (x, y, col, txt) in ((hx, hy, "#ffffff", f"{fr[hy, hx]:.1f}°"), (cx, cy, "#8ec6ff", f"{fr[cy, cx]:.1f}°")):
            X, Y = x * s + s / 2, y * s + s / 2
            c.create_line(X - 12, Y, X + 12, Y, fill=col, width=2); c.create_line(X, Y - 12, X, Y + 12, fill=col, width=2)
            c.create_text(X + 14, Y - 12, text=txt, fill=col, anchor="w", font=("Menlo", 12, "bold"))
        if self.hover:
            x, y = self.hover
            if 0 <= x < W and 0 <= y < H:
                c.create_rectangle(x * s, y * s, x * s + s, y * s + s, outline="#00ff88", width=2)
                c.create_text(min(x * s + s + 4, W * s - 70), y * s, text=f"{fr[y, x]:.1f}°", fill="#00ff88", anchor="w", font=("Menlo", 12, "bold"))
        # colour bar + history strip
        st = self.strip; st.delete("all")
        bar = LUTS[self.var_cmap.get()][np.linspace(0, 255, W * s).astype(int)][None, :, :]
        self.barimg = ImageTk.PhotoImage(Image.fromarray(np.repeat(bar, 12, 0))); st.create_image(0, 0, anchor="nw", image=self.barimg)
        st.create_text(4, 16, text=f"{lo:.1f}°", fill="#ddd", anchor="nw", font=("Menlo", 10)); st.create_text(W * s - 4, 16, text=f"{hi:.1f}°", fill="#ddd", anchor="ne", font=("Menlo", 10))
        if len(self.hist) > 2:
            t0 = self.hist[0][0]; span = max(1.0, self.hist[-1][0] - t0)
            mx = [h[1] for h in self.hist]; mn = [h[2] for h in self.hist]; ylo, yhi = min(mn) - 1, max(mx) + 1
            pts = [(4 + (h[0] - t0) / span * (W * s - 8), 68 - (h[1] - ylo) / (yhi - ylo) * 36) for h in self.hist]
            st.create_line(*[v for p in pts for v in p], fill="#ffb347", width=2)
            pts = [(4 + (h[0] - t0) / span * (W * s - 8), 68 - (h[2] - ylo) / (yhi - ylo) * 36) for h in self.hist]
            st.create_line(*[v for p in pts for v in p], fill="#6cc4ff", width=1)
            st.create_text(6, 30, text="max / mean over the last frames", fill="#888", anchor="nw", font=("Menlo", 9))

    def tick(self):
        self.render()
        fr = self.current()
        src = "DEMO" if self.demo else (self.port or "?")
        msg = self.err or f"{src} · {self.fps:.1f} fps · min {fr.min():.1f} · mean {fr.mean():.1f} · max {fr.max():.1f} °C" + (f" · ambient {self.ta:.1f}" if self.ta else "")
        self.status.config(text=msg, foreground="#c92a2a" if self.err else "")
        if self.running: self.root.after(80, self.tick)

    def on_motion(self, e):
        self.hover = (e.x // self.SCALE, e.y // self.SCALE)

    def save_png(self):
        p = filedialog.asksaveasfilename(defaultextension=".png", initialfile=time.strftime("thermal-%Y%m%d-%H%M%S.png"))
        if p:
            fr = self.current(); lo, hi = float(fr.min()), float(fr.max())
            idx = np.clip(((fr - lo) / max(0.5, hi - lo) * 255), 0, 255).astype(np.uint8)
            Image.fromarray(LUTS[self.var_cmap.get()][idx]).resize((W * 20, H * 20), Image.BICUBIC).save(p)

    def save_csv(self):
        p = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=time.strftime("thermal-%Y%m%d-%H%M%S.csv"))
        if p:
            with open(p, "w", newline="") as f:
                csv.writer(f).writerows([[f"{v:.2f}" for v in row] for row in self.current()])

    def close(self):
        self.running = False
        try:
            if self.ser: self.ser.close()
        except Exception: pass
        self.root.destroy()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port of the Arduino bridge (default: first Arduino-looking port)")
    ap.add_argument("--rate", type=int, default=4, choices=(1, 2, 4, 8), help="sensor refresh rate in Hz (4 is right for 115200 baud)")
    ap.add_argument("--demo", action="store_true", help="synthetic frames, no hardware")
    ap.add_argument("--seconds", type=float, default=0, help="quit after N seconds (self-test)")
    a = ap.parse_args()
    port = a.port or (None if a.demo else auto_port())
    if not a.demo and not port:
        sys.exit("no serial port found — plug the Arduino in or pass --port")
    root = tk.Tk(); app = App(root, port, a.demo, a.rate)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.lift(); root.attributes("-topmost", True); root.after(1500, lambda: root.attributes("-topmost", False)); root.focus_force()   # macOS: come to the front
    if sys.platform == "darwin":
        import os, subprocess
        subprocess.Popen(["osascript", "-e", f'tell application "System Events" to set frontmost of (first process whose unix id is {os.getpid()}) to true'])
    if a.seconds: root.after(int(a.seconds * 1000), app.close)
    root.mainloop()
