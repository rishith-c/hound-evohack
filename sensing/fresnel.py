#!/usr/bin/env python3
"""
fresnel.py — make WiFi breathing detection work ON PURPOSE instead of by luck.

The physics (Wang et al., UbiComp 2016 "Do user location and body orientation matter?"; Zhang et al., IMWUT
2018 "From Fresnel diffraction model to fine-grained respiration sensing"): a WiFi link between a transmitter
and a receiver is surrounded by Fresnel zones, ellipsoids where the reflected path is n·λ/2 longer than the
direct path (λ = 12.5 cm at 2.4 GHz). A chest moving 5 mm changes the reflected path by ~1 cm, which is a
large fraction of λ/2 = 6.25 cm — but the received AMPLITUDE only changes to first order when the reflected
and direct paths are in quadrature, i.e. when the person sits a quarter-wavelength off a zone boundary.
On a boundary the change is second order and breathing is nearly invisible. That is why "put two ESP32s
in a room" works one day and not the next: it depends on where the person is to within centimetres.

Hound's answer: the receiver is on a mecanum rover that can strafe by 3 cm with step precision. Moving the
receiver by λ/4 (3.1 cm) walks every point in the room a quarter of the way through its zone. Four stops
3.1 cm apart therefore GUARANTEE that some stop puts the person in quadrature, whatever the geometry.
We call it a Fresnel dither. It costs 12 s per station.

This file: (1) the model, (2) a Monte Carlo of detection probability for a random person position with
and without the dither, (3) the placement rule for the transmitter node relative to the wall.
Run: ~/Developer/walleye/.venv/bin/python fresnel.py
"""
from __future__ import annotations

import json
import os

import numpy as np

LAMBDA = 0.125                    # m, 2.4 GHz
CHEST_MM = 5.0                    # peak-to-peak chest displacement, LIT 4–8 mm
WALL_LOSS = 0.5                   # amplitude factor for one drywall partition on the reflected path (ALLOC)


def sensitivity(tx, rx, p):
    """Fractional amplitude modulation of the received signal from a breathing chest at p (2-D, metres)."""
    tx, rx, p = map(np.asarray, (tx, rx, p))
    d_direct = np.linalg.norm(rx - tx)
    d_refl = np.linalg.norm(p - tx) + np.linalg.norm(rx - p)
    phase = 2 * np.pi * (d_refl - d_direct) / LAMBDA
    # reflected/direct amplitude ratio: body RCS falls with both legs; through the wall it halves
    ratio = 0.15 / max(np.linalg.norm(p - tx) * np.linalg.norm(rx - p), 0.25) * WALL_LOSS
    # chest motion δ changes d_refl by ≈ δ·(cos a + cos b) ≈ δ..2δ; take 1.5·δ, in radians of phase
    dphi = 2 * np.pi * (1.5 * CHEST_MM / 1000) / LAMBDA
    # |direct + ratio·e^{jφ}| to first order in dφ: modulation ≈ ratio·|sin φ|·dφ  (quadrature = max)
    return ratio * abs(np.sin(phase)) * dphi


def detectable(sens, noise=0.004):
    """CSI amplitude noise on an ESP32 is ~1 % of amplitude per packet; 30 s at 50 Hz averages it to ~0.4 %.
    Breathing shows in the periodicity estimator from a modulation-to-noise ratio of about 1.5 (sim.py)."""
    return sens / noise >= 1.5


def monte_carlo(rng, n=400):
    """TX at the doorway (−1.5, 0), wall along y = 0.3, RX on the rover at (0, 0); person random behind the wall."""
    tx = (-1.5, 0.0); res = {"static": 0, "dither4": 0, "dither8": 0}
    for _ in range(n):
        p = (rng.uniform(-1.0, 1.5), rng.uniform(0.8, 3.5))
        base = sensitivity(tx, (0.0, 0.0), p)
        res["static"] += detectable(base)
        for k, steps in (("dither4", 4), ("dither8", 8)):
            best = max(sensitivity(tx, (i * LAMBDA / 4, 0.0), p) for i in range(steps))
            res[k] += detectable(best)
    return {k: round(v / n, 3) for k, v in res.items()}


def placement_rule():
    """Where to drop the transmitter so the searched region sits in the sensitive zones (1–8) of every link."""
    lines = []
    for depth in (1.0, 2.0, 3.0):
        for tx_x in (-1.0, -2.0, -3.0):
            d_direct = abs(tx_x); d_refl = np.hypot(tx_x, depth) + depth
            zone = int(2 * (d_refl - d_direct) / LAMBDA) + 1
            lines.append({"tx_offset_along_wall_m": -tx_x, "person_depth_m": depth, "fresnel_zone": zone})
    return lines


def main():
    rng = np.random.default_rng(5)
    mc = monte_carlo(rng)
    rule = placement_rule()
    out = {"detection_probability": mc, "zones": rule,
           "rule": "Sensitivity falls with zone number, and from one side of a wall the person is always far off the link line "
                   "(zones 19–83 here), so drop the transmitter as FAR along the wall as the room allows (3 m: zones 19/42/68), "
                   "keep the receiver on the rover, and dither it in 4 steps of λ/4 = 3.1 cm at every station. "
                   "CSI stays the corroborating vote; the radar is the one that reaches 3 m."}
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "fresnel_results.json"), "w"), indent=1)
    print("WiFi breathing detection probability, random person 0.8–3.5 m behind the wall:")
    for k, v in mc.items():
        print(f"  {k:9s} {v:.0%}")
    print("\nFresnel zone of the person's reflection, by transmitter drop and depth:")
    for r in rule:
        print(f"  TX {r['tx_offset_along_wall_m']:.0f} m along the wall, person {r['person_depth_m']:.0f} m deep → zone {r['fresnel_zone']}")


if __name__ == "__main__":
    main()
