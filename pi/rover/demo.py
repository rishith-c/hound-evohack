#!/usr/bin/env python3
"""
demo.py — drive the rover through every motion from the Pi.

    venv/bin/python demo.py            # forward, back, strafe L/R, rotate both ways, crab circle
    venv/bin/python demo.py circle     # just the crab circle
    venv/bin/python demo.py tilt       # turret tilt sweep (PCA9685 channel 3, driven by the R4)

Wheels up or a clear floor. Ctrl-C stops everything.
"""
import math
import sys
import time

from r4 import R4

V = 80.0                 # mm/s
K = 125.0 + 215.5        # half wheelbase + half track, mm  (wz = V/K makes each wheel run at V)


def hold(r, label, vx, vy, wz, secs):
    r.velocity(vx, vy, wz)
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(0.25)
        rate = r.status.get("rate", [0, 0, 0, 0])
        print(f"\r{label:18s} FL {rate[0]:>6} FR {rate[1]:>6} BL {rate[2]:>6} BR {rate[3]:>6} steps/s", end="", flush=True)
    r.stop()
    print()
    time.sleep(1.0)


def crab_circle(r, radius_mm=150.0, v=V, laps=1):
    period = 2 * math.pi * radius_mm / v
    print(f"crab circle: r = {radius_mm:.0f} mm, {period:.1f} s per lap, heading fixed")
    t0 = time.time()
    while (t := time.time() - t0) < period * laps:
        th = 2 * math.pi * t / period
        r.velocity(v * math.cos(th), v * math.sin(th), 0.0)
        time.sleep(0.05)
    r.stop()


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what == "tilt":
        from turret import Turret
        with R4() as r:
            t = Turret(r)
            for deg in (90, 80, 105, 90):
                print("tilt", t.tilt(deg)); time.sleep(0.8)
            t.relax()
        return

    with R4() as r:
        print("R4 on", r.port, "·", r.status.get("map"))
        if what in ("all", "basic"):
            hold(r, "forward",       V, 0, 0, 3)
            hold(r, "back",         -V, 0, 0, 3)
            hold(r, "strafe left",   0, V, 0, 3)
            hold(r, "strafe right",  0, -V, 0, 3)
            hold(r, "rotate CCW",    0, 0, V / K, 3)
            hold(r, "rotate CW",     0, 0, -V / K, 3)
        if what in ("all", "circle"):
            crab_circle(r)
        print("done")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\ninterrupted")
