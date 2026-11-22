#!/usr/bin/env python3
"""
localize.py — put the person behind the wall ON A MAP, with the hardware in the box.

The Walleye rail moved one LD2410C along a line and intersected its range circles. Hound's mecanum base
IS that rail: it strafes along the wall, stopping every 25 cm, and at each stop reads the breathing gate's
distance. Five stops make a 1 m synthetic aperture. Two LD2410Cs toed out ±30° add a left/right amplitude
ratio at every stop (amplitude-comparison direction finding, the oldest trick in radar), which resolves the
mirror ambiguity a single line of ranges always has and tightens the along-wall estimate.

Range model: LD2410C in 0.2 m gate mode (command 0x00AA sets 0.2 m or 0.75 m resolution; Hi-Link user manual)
reports the gate centre, so the honest 1-σ is gate/√12 plus a wall bias of a few cm (the wall's dielectric
delays the wave). Toe-out ratio: each sensor's static energy falls with off-axis angle roughly as a Gaussian
beam of ±60° half-power (Hi-Link: ±60° coverage), so log(E_L/E_R) ∝ bearing.

Monte Carlo: person at random (x, y) up to 4 m behind the wall, ±1.5 m along it; report the 2-D position
error for 3, 5 and 9 stops and both gate resolutions.  Run: ~/Developer/walleye/.venv/bin/python localize.py
"""
from __future__ import annotations

import json
import os

import numpy as np

HALF_POWER_DEG = 60.0            # LD2410C coverage half-angle (Hi-Link)
TOE_DEG = 30.0                   # each sensor toed out from the rover's nose
BASELINE_M = 0.10                # the two LD2410Cs are 100 mm apart on the bar
WALL_BIAS_M = 0.04               # apparent extra range through 12.7 mm gypsum × 2 faces (ALLOC, small)


def beam(theta_deg):
    """Relative energy vs off-axis angle: Gaussian with the −3 dB point at ±60°."""
    s = HALF_POWER_DEG / np.sqrt(2 * np.log(2))
    return np.exp(-0.5 * (theta_deg / s) ** 2)


def observe(rng, px, py, stops, gate_m, energy_noise=0.12):
    """Rover at (sx, 0) facing +Y (the wall is the line y = 0.3). Returns per-stop (range, log L/R ratio)."""
    obs = []
    for sx in stops:
        d = np.hypot(px - sx, py) + WALL_BIAS_M
        r = (np.floor(d / gate_m) + 0.5) * gate_m                       # gate centre
        bearing = np.degrees(np.arctan2(px - sx, py))                    # + = right of the nose
        eL = beam(bearing + TOE_DEG) * (1 + rng.normal(0, energy_noise))
        eR = beam(bearing - TOE_DEG) * (1 + rng.normal(0, energy_noise))
        obs.append((sx, r, np.log(max(eL, 1e-3) / max(eR, 1e-3))))
    return obs


def solve(obs, gate_m):
    """Grid least squares over the half-plane behind the wall: range residuals + bearing-ratio residuals."""
    xs = np.linspace(-3, 3, 241); ys = np.linspace(0.3, 5.0, 189)
    X, Y = np.meshgrid(xs, ys)
    sig_r = gate_m / np.sqrt(12) + 0.03
    k = 2 * TOE_DEG / (HALF_POWER_DEG / np.sqrt(2 * np.log(2))) ** 2      # d(log ratio)/d(bearing) for the Gaussian beam
    sig_ratio = 0.25
    cost = np.zeros_like(X)
    for sx, r, lr in obs:
        d = np.hypot(X - sx, Y) + WALL_BIAS_M
        cost += ((d - r) / sig_r) ** 2
        bearing = np.degrees(np.arctan2(X - sx, Y))
        cost += ((-k * bearing - lr) / sig_ratio) ** 2                    # log(L/R) is negative for a target to the right
    i = np.unravel_index(np.argmin(cost), cost.shape)
    # 1-σ ellipse from the cost curvature: points within Δcost ≤ 1
    mask = cost <= cost[i] + 1.0
    ex = np.ptp(X[mask]) / 2 if mask.sum() > 1 else 0.0; ey = np.ptp(Y[mask]) / 2 if mask.sum() > 1 else 0.0
    return float(X[i]), float(Y[i]), float(ex), float(ey)


def trial(rng, n_stops, gate_m, span_m=1.0, ratio=True):
    px, py = rng.uniform(-1.5, 1.5), rng.uniform(0.8, 4.0)
    stops = np.linspace(-span_m / 2, span_m / 2, n_stops)
    obs = observe(rng, px, py, stops, gate_m)
    if not ratio:
        obs = [(sx, r, 0.0) for sx, r, _ in obs]
    ex_, ey_, sx_, sy_ = solve(obs, gate_m) if ratio else solve_range_only(obs, gate_m)
    return np.hypot(ex_ - px, ey_ - py), abs(ex_ - px), abs(ey_ - py), py


def solve_range_only(obs, gate_m):
    xs = np.linspace(-3, 3, 241); ys = np.linspace(0.3, 5.0, 189)
    X, Y = np.meshgrid(xs, ys); sig_r = gate_m / np.sqrt(12) + 0.03
    cost = sum(((np.hypot(X - sx, Y) + WALL_BIAS_M - r) / sig_r) ** 2 for sx, r, _ in obs)
    i = np.unravel_index(np.argmin(cost), cost.shape)
    return float(X[i]), float(Y[i]), 0.0, 0.0


def main():
    rng = np.random.default_rng(11)
    out = {}
    for gate in (0.75, 0.2):
        for n in (1, 3, 5, 9):
            for ratio in (False, True):
                errs = np.array([trial(rng, n, gate, ratio=ratio) for _ in range(150)])
                key = f"gate {gate} m · {n} stop{'s' if n > 1 else ''} · {'range + L/R ratio' if ratio else 'range only'}"
                out[key] = {"median_err_m": round(float(np.median(errs[:, 0])), 2), "p90_err_m": round(float(np.percentile(errs[:, 0], 90)), 2),
                            "median_along_wall_m": round(float(np.median(errs[:, 1])), 2), "median_depth_m": round(float(np.median(errs[:, 2])), 2)}
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "localize_results.json"), "w"), indent=1)
    print(f"{'configuration':52s} {'median':>7s} {'p90':>6s} {'along':>6s} {'depth':>6s}")
    for k, v in out.items():
        print(f"{k:52s} {v['median_err_m']:7.2f} {v['p90_err_m']:6.2f} {v['median_along_wall_m']:6.2f} {v['median_depth_m']:6.2f}")


if __name__ == "__main__":
    main()
