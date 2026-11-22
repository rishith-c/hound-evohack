#!/usr/bin/env python3
"""
bringup.py — every sense a search stop depends on, checked in one pass. Run on the Pi with the motors off:

    venv/bin/python sensing/bringup.py [--seconds 5] [--skip camera,csi]

One line per sense: PASS / WARN / FAIL, what it measured, and the likely fault when it fails. Nothing moves.
The checks are station.py's own drivers (and tof.py, radar_check.py), so a PASS here means a stop can use it.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def check_i2c(text=None):
    """i2cdetect -y 1: the thermal array (0x33) and both ToFs (0x29 rear, 0x30 front once re-addressed)."""
    if text is None:
        text = subprocess.run(["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=10).stdout
    found = {int(a, 16) for row in re.findall(r"^[0-7]0:(.*)$", text, re.M) for a in re.findall(r"\b([0-7][0-9a-f])\b", row)}
    want = {0x33: "thermal", 0x29: "ToF"}
    missing = [f"0x{a:02x} {n}" for a, n in want.items() if a not in found]
    seen = " ".join(f"0x{a:02x}" for a in sorted(found)) or "nothing"
    if missing:
        return "FAIL", f"I2C-1 answers {seen}", "missing " + ", ".join(missing) + ": check 3V3 (pins 1/17), SDA 3 / SCL 5 and the chain through the boards' second headers"
    note = "" if 0x30 in found else " (front ToF not yet moved to 0x30 — the ToF check does that)"
    return "PASS", f"I2C-1 answers {seen}{note}", ""


def check_tof(init=None, read=None):
    import tof
    front, rear = (init or tof.init_tofs)()
    d = {"front": (read or tof.read_mm)(front), "rear": (read or tof.read_mm)(rear)}
    txt = ", ".join(f"{k} {v} mm" if v is not None else f"{k} no reading" for k, v in d.items())
    if any(v is None for v in d.values()):
        return "WARN", txt, "a ToF answered but gave no distance: nothing within ~4 m, or its lens is covered"
    return "PASS", txt, ""


def check_thermal(thermal=None):
    import numpy as np
    if thermal is None:
        from station import Thermal
        thermal = Thermal()
    f = thermal.frame()
    if f is None:
        return "FAIL", "no clean frame in 3 reads", "the driver kept rejecting frames: I2C errors — re-seat the thermal lead, keep it short"
    f = np.asarray(f, float)
    lo, hi, med = float(f.min()), float(f.max()), float(np.median(f))
    txt = f"frame {f.shape[1]}×{f.shape[0]}, {lo:.1f}–{hi:.1f} °C (room {med:.1f})"
    if not 5 < med < 40 or hi - lo < 0.3:
        return "FAIL", txt, "values are not a room: a stuck or flat frame means a bad I2C read — re-seat the thermal lead"
    return "PASS", txt, ""


def check_camera(camera=None):
    if camera is None:
        from station import Camera
        camera = Camera()
    ok, _ = camera.cap.read()
    if not ok:
        return "FAIL", "no frame", "the webcam is not delivering frames: USB 1, and nothing else holding /dev/video0"
    s = camera.score()
    return "PASS", f"frame ok, person score {s:.2f}", ""


def check_csi(sink=None, seconds=5.0):
    if sink is None:
        from station import CsiSink
        sink = CsiSink()
    t, a = sink.collect(seconds)
    rate = len(t) / seconds
    txt = f"{rate:.0f} CSI packets/s"
    if rate == 0:
        return "FAIL", txt, "nothing on UDP 5005: is ESP32 #3 powered and on the Pi's hotspot (channel 6), and ESP32 #2 transmitting?"
    if rate < 50:
        return "WARN", txt, "expect ~100/s from the 100 Hz probes: ESP32 #2 far away, or the channel is busy"
    return "PASS", txt, ""


def check_radars(seconds=5.0):
    from radar_check import check_ld2410, check_ld2450
    from station import port_label, radar_ports
    out = []
    for name, path in radar_ports().items():
        try:
            r = (check_ld2450 if name == "ld2450" else check_ld2410)(path, seconds)
            out.append((r["verdict"], f"radar {name} ({port_label(path)}): {r.get('fps', 0):.1f} frames/s", r["hint"]))
        except Exception as e:
            out.append(("FAIL", f"radar {name}", f"cannot open {path}: {e}"))
    return out or [("FAIL", "radars", "no radar ports: CP2102s not on USB, and /dev/serial0 is not the PL011 (enable_gpio_uart.sh)")]


CHECKS = ("i2c", "tof", "thermal", "camera", "csi", "radars")


def run(skip=(), seconds=5.0, report=print):
    results = []
    for name in CHECKS:
        if name in skip:
            continue
        try:
            got = {"i2c": check_i2c, "tof": check_tof, "thermal": check_thermal, "camera": check_camera,
                   "csi": lambda: check_csi(seconds=seconds), "radars": lambda: check_radars(seconds)}[name]()
        except Exception as e:                       # a missing library or device is a FAIL with its reason, never a crash
            got = ("FAIL", name, f"{e.__class__.__name__}: {e}")
        for verdict, txt, hint in (got if isinstance(got, list) else [got]):
            results.append((name, verdict, txt, hint))
            report(f"{verdict:4s}  {name:7s} {txt}" + (f"\n      → {hint}" if hint else ""))
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seconds", type=float, default=5.0)
    ap.add_argument("--skip", default="", help="comma-separated: " + ",".join(CHECKS))
    a = ap.parse_args(argv)
    res = run(skip=set(filter(None, a.skip.split(","))), seconds=a.seconds)
    return 0 if all(v == "PASS" for _, v, _, _ in res) else 1


if __name__ == "__main__":
    sys.exit(main())
