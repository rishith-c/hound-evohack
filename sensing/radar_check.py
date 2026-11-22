#!/usr/bin/env python3
"""
radar_check.py — bring-up check for the three radars after wiring. Run it on the Pi with the motors off:

    venv/bin/python sensing/radar_check.py [--seconds 5]

For each radar that station.radar_ports() finds (LD2410C LEFT/RIGHT on their CP2102s, the LD2450 on the Pi's UART) it
reads a few seconds and reports frames per second, whether they parse, and what the radar sees — with the likely
wiring fault when one is silent. Exit code 0 only if every radar found is healthy. Nothing is moved.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ld2410  # noqa: E402
import ld2450  # noqa: E402

MIN_FPS = 5.0                                  # both parts report ~10 frames/s; half that is already a sick link


def _read(ser, seconds, feed):
    raw = frames = 0
    out = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        data = ser.read(512)
        raw += len(data)
        got = feed(data)
        frames += len(got); out += got
    return raw, frames, out


def check_ld2410(port: str, seconds: float = 5.0, ser=None) -> dict:
    """LD2410C: arm engineering mode (as station.py does), count frames, and report the strongest static gate."""
    ser = ser or _open(port)
    for cmd in (ld2410.ENABLE_CONFIG, ld2410.ENG_ON, ld2410.END_CONFIG):
        ser.write(cmd); ser.flush(); time.sleep(0.12)
    rd = ld2410.FrameReader()
    raw, n, frames = _read(ser, seconds, rd.feed)
    eng = [f for f in frames if f.get("engineering")]
    r = {"kind": "LD2410C", "port": port, "bytes": raw, "fps": n / seconds, "engineering": len(eng) / n if n else 0.0,
         "dropped": rd.dropped}
    if eng:
        last = eng[-1]
        gates = last["static_gates"]
        g = max(range(len(gates)), key=gates.__getitem__) if gates else None
        r.update(state=last["state"], static_cm=last["static_cm"], strongest_gate=g,
                 strongest_m=None if g is None else f"{0.75 * g:.2f}–{0.75 * (g + 1):.2f} m")
    return _verdict(r, n, seconds, engineering_ok=bool(eng))


def check_ld2450(port: str, seconds: float = 5.0, ser=None) -> dict:
    """LD2450: count frames and report the nearest moving target (it only tracks things that move)."""
    ser = ser or _open(port)
    rd = ld2450.FrameReader()
    raw, n, frames = _read(ser, seconds, rd.feed)
    targets = [t for f in frames for t in f]
    r = {"kind": "LD2450", "port": port, "bytes": raw, "fps": n / seconds, "dropped": rd.dropped,
         "frames_with_targets": sum(1 for f in frames if f)}
    if targets:
        near = min(targets, key=lambda t: t["range_mm"])
        r.update(nearest_mm=near["range_mm"], nearest_xy_mm=(near["x_mm"], near["y_mm"]))
    return _verdict(r, n, seconds, engineering_ok=True)


def _verdict(r: dict, frames: int, seconds: float, engineering_ok: bool) -> dict:
    fps = frames / seconds
    if r["bytes"] == 0:
        r["verdict"], r["hint"] = "FAIL", ("no bytes at all: is the radar powered (VCC on the adapter's +5V / Pi pin 4, not 3V3)? "
                                           "Is its TX on the adapter's RXD (Pi pin 10)?")
    elif frames == 0:
        r["verdict"], r["hint"] = "FAIL", ("bytes but no frames: wrong baud or a noisy/shared line"
                                           + (" — or the Pi's login console / Bluetooth still owns this UART: run enable_gpio_uart.sh"
                                              if r["kind"] == "LD2450" else "; meter the adapter's TXD: 3.3 V at idle"))
    elif fps < MIN_FPS:
        r["verdict"], r["hint"] = "WARN", f"only {fps:.1f} frames/s (expect ~10): loose Dupont contact or a weak supply"
    elif not engineering_ok:
        r["verdict"], r["hint"] = "WARN", "frames but no engineering mode: its RX (the adapter's TXD) may not be connected, so the arm command never arrives"
    else:
        r["verdict"], r["hint"] = "PASS", ""
    return r


def _open(port):
    import serial
    return serial.Serial(port, 256000, timeout=0.1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seconds", type=float, default=5.0)
    a = ap.parse_args(argv)
    from station import port_label, radar_ports
    ports = radar_ports()
    if not ports:
        print("no radar ports found: no CP2102 in /dev/serial/by-id and /dev/serial0 is not the PL011 — check USB and enable_gpio_uart.sh")
        return 1
    ok = True
    for name, path in ports.items():
        try:
            r = (check_ld2450 if name == "ld2450" else check_ld2410)(path, a.seconds)
        except Exception as e:
            r = {"kind": name, "port": path, "verdict": "FAIL", "hint": f"cannot open: {e}"}
        ok &= r["verdict"] == "PASS"
        seen = (f"strongest static gate {r['strongest_m']}, state {r.get('state')}" if r.get("strongest_m") else
                f"nearest mover {r['nearest_mm']} mm at x/y {r['nearest_xy_mm']}" if r.get("nearest_mm") else "nothing in view")
        print(f"{r['verdict']:4s}  {name:6s} {r['kind']:7s} {port_label(path)[:40]:40s} "
              f"{r.get('fps', 0):4.1f} frames/s  {seen}" + (f"\n      → {r['hint']}" if r["hint"] else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
