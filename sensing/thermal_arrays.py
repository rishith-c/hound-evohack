#!/usr/bin/env python3
"""
thermal_arrays.py — would a cheaper thermal array still find a person? The MLX90640 is the biggest single purchase.

A pixel reads the average of what it sees. A clothed torso at 27.5 °C against a 22 °C room lifts a pixel it covers a
fraction f of by f × 5.5 °C; thermal_features() calls a pixel warm at room + 2.5 °C, so some pixel must be ≥ 45 %
covered. Where the person lands on the pixel grid is luck, so the check uses the WORST alignment: a target A pixels
wide covers at least min(1, A/2) of its best pixel (it can straddle a boundary), in each axis.

    python3 sensing/thermal_arrays.py

Pixel counts and fields of view are DATASHEET (Melexis MLX90640-D55, MLX90641-ESF-BCA; Panasonic AMG8833); body and
room temperatures are models.py's; prices LISTING (Amazon, 2026-09-25).
"""
import math

ROOM, TORSO, WARM = 22.0, 27.5, 2.5                 # °C: models.py room and clothed torso; detectors.py warm threshold
F_MIN = WARM / (TORSO - ROOM)                       # 0.455 of a pixel
POSTURES = {"standing": (0.5, 1.7), "lying face-on": (0.5, 0.5)}      # m, models.py
ARRAYS = [  # name, cols, rows, fov_h°, fov_v°, $, ASIN
    ("MLX90640-D55 (as bought)", 32, 24, 55.0, 35.0, 66.30, "B0FQHVSX91"),
    ("MLX90641 55°", 16, 12, 55.0, 35.0, 53.75, "B0DZD2QFQ1"),
    ("AMG8833", 8, 8, 60.0, 60.0, 24.88, "B0C7KXHXTP"),
]


def cover(a_px):
    """Worst-alignment coverage of the best pixel by a target a_px pixels wide (one axis)."""
    return 1.0 if a_px >= 2 else a_px / 2


def worst_fill(arr, w, h, r):
    _, cols, rows, fh, fv, *_ = arr
    ang = lambda m: math.degrees(2 * math.atan(m / 2 / r))
    return cover(ang(w) / (fh / cols)) * cover(ang(h) / (fv / rows))


def max_range(arr, w, h):
    lo, hi = 0.3, 30.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if worst_fill(arr, w, h, mid) >= F_MIN else (lo, mid)
    return lo


def px_on(arr, w, h, r):
    _, cols, rows, fh, fv, *_ = arr
    ang = lambda m: math.degrees(2 * math.atan(m / 2 / r))
    return ang(w) / (fh / cols) * ang(h) / (fv / rows)


def main():
    print(f"\nTHERMAL ARRAY — worst-case warm-pixel range (a pixel ≥ {F_MIN:.0%} covered by a {TORSO} °C torso in a {ROOM} °C room)")
    print("=" * 104)
    for arr in ARRAYS:
        rng = {p: max_range(arr, *wh) for p, wh in POSTURES.items()}
        at4 = {p: px_on(arr, *wh, 4.0) for p, wh in POSTURES.items()}
        print(f"  {arr[0]:26s} ${arr[5]:6.2f}   warm to {rng['standing']:4.1f} m standing, {rng['lying face-on']:4.1f} m lying   "
              f"· at 4 m a person spans {at4['standing']:5.1f} / {at4['lying face-on']:4.1f} px")
    print(f"\n  The detector also wants ≥ 3 px and a person-like shape before it trusts a warm blob (a laptop or a mug is")
    print(f"  warm too). A person spanning under ~3 px is a warm dot: it can still vote, but it cannot be told from a laptop.")
    print(f"\nNOT ANALYSED: posture other than face-on, clothing emissivity, lens vignetting, the camera's own FoV match.\n")


if __name__ == "__main__":
    main()
