"""
models.py — physics-shaped simulators for the four senses, used to calibrate and test the fusion before
any sensor is wired. Every number is tagged: DS (datasheet), LIT (paper), BENCH (Walleye measurement), ALLOC (allocated,
to be replaced by the bench test the runbook already schedules).

Radar (LD2410C static-gate energy, 10 Hz, 0–100 int):
  A chest wall moves 4–8 mm at 0.13–0.6 Hz (LIT). At 24 GHz (λ 12.5 mm) that is 4–8 rad of phase, so the
  gate's reflected power beats at the breathing rate and its harmonics. Walleye saw this as a 5–15 unit
  swing at 1–2 m through one drywall sheet (BENCH, unquantified) on a noise floor of ~2–4 units (BENCH).
  Modulation amplitude falls with range as (r0/r)^p and with wall loss; the exponent and the wall loss on the
  *energy metric* are unknown (ALLOC p = 2, wall factor 0.5 for 6 dB two-way at 24 GHz through 12.7 mm gypsum,
  LIT), so the simulation sweeps modulation-to-noise ratio and maps it to range only as an illustration.
  Fan: same band, interval CV ≈ 0.005 (a motor), constant amplitude. Person: interval CV ≈ 0.10 (LIT: adult
  respiratory variability 8–15 %), amplitude wander ±20 %.

CSI (ESP32-S3, per-subcarrier amplitude, ~50 Hz packets, 52 subcarriers, int8 magnitudes ~20–60):
  Static room: amplitude noise σ ≈ 1.0 units, slow drift. A breathing person on or near the bistatic line
  modulates a subset of subcarriers by 0.5–2 % (LIT: ESP32 CSI respiration papers). Motion: broadband
  variance 10–30× baseline. Through one wall the modulation halves (ALLOC).

Thermal (MLX90640, 32×24, 55° FoV, NETD 0.1 K at 4 Hz, DS):
  Room 22 °C; a clothed torso reads 26–30 °C, face/hands 32–34 °C (LIT); a person 0.5 m wide × 1.7 m tall
  standing, or 0.5 × 0.5 m lying face-on. Pixel size = 55°/32 = 1.72°/px. Hot false targets: radiator 45–60 °C,
  laptop 34–38 °C small, sunlit wall patch 25–28 °C large and flat. A wall blocks it completely.

Camera (MobileNet-SSD on a Pi 4, LIT/BENCH-class figures): P(detect | person in view) 0.95 < 3 m lit, 0.85 at
  3–5 m, 0.5 in low light; per-frame false positive 1 % (posters, coats). Score in [0, 1].
"""
from __future__ import annotations

import numpy as np

FS_RADAR = 10.0
FS_CSI = 50.0
N_SUB = 52

# ── radar ─────────────────────────────────────────────────────────────────────
def radar_energy(rng, seconds=30.0, breath=None, mnr=3.0, noise=3.0, base=35.0, drop_frac=0.1,
                 fan=None, motion=False):
    """Timestamped static-gate energy for one gate.
    breath: dict(f0 Hz, cv) or None. mnr = modulation amplitude / noise σ. fan: dict(f0, amp) or None.
    Returns (t, e) with irregular timestamps (a `drop_frac` of frames missing) and integer-quantized e.
    """
    n = int(seconds * FS_RADAR)
    t = np.arange(n) / FS_RADAR + rng.normal(0, 0.008, n)          # USB jitter
    e = base + rng.normal(0, noise, n) + np.cumsum(rng.normal(0, 0.05, n))   # noise + drift
    if breath:
        # breath-to-breath intervals with physiological variability → phase accumulates irregularly
        f0, cv = breath["f0"], breath.get("cv", 0.10)
        phase = np.zeros(n); ph = 0.0; period = 1.0 / f0
        for i in range(n):
            ph += 2 * np.pi / (period * FS_RADAR); phase[i] = ph
            if ph >= 2 * np.pi:                                       # new breath: draw the next interval
                ph -= 2 * np.pi; period = max(0.8, rng.normal(1.0 / f0, cv / f0))
        amp = mnr * noise * (1 + 0.2 * np.sin(2 * np.pi * 0.01 * t + rng.uniform(0, 6.28)))  # slow amplitude wander
        wave = np.sin(phase) + 0.3 * np.sin(2 * phase)                # asymmetric breath (fast inhale)
        e += amp * wave / 1.05
    if fan:
        e += fan["amp"] * noise * np.sin(2 * np.pi * fan["f0"] * t + rng.uniform(0, 6.28))   # machine: CV ≈ 0
    if motion:
        e += rng.normal(0, 8 * noise, n) + 20 * np.sin(2 * np.pi * rng.uniform(0.05, 0.3) * t)
    keep = rng.random(n) > drop_frac
    e = np.clip(np.round(e), 0, 100)
    return t[keep], e[keep]


# ── CSI ───────────────────────────────────────────────────────────────────────
def csi_frames(rng, seconds=30.0, breath=None, depth=0.01, motion=False, wall=False, drift=True):
    """(t, A) with A shape (n_packets, N_SUB) int-like amplitudes. depth = fractional breathing modulation."""
    n = int(seconds * FS_CSI)
    t = np.arange(n) / FS_CSI + rng.normal(0, 0.003, n)
    base = rng.uniform(20, 60, N_SUB)
    A = base[None, :] + rng.normal(0, 1.0, (n, N_SUB))
    if drift:
        A += np.cumsum(rng.normal(0, 0.01, (n, 1)), axis=0) * rng.uniform(0.5, 1.5, (1, N_SUB))
    if breath:
        d = depth * (0.5 if wall else 1.0)
        affected = rng.random(N_SUB) < 0.4                             # the subcarriers the body sits in
        wave = np.sin(2 * np.pi * breath["f0"] * t + rng.uniform(0, 6.28))
        A[:, affected] += (d * base[affected])[None, :] * wave[:, None]
    if motion:
        A += rng.normal(0, 4.0, (n, N_SUB)) * (0.5 if wall else 1.0)
    keep = rng.random(n) > 0.05
    return t[keep], np.clip(A[keep], 0, 127)


# ── thermal ───────────────────────────────────────────────────────────────────
def thermal_frame(rng, person=None, room=22.0, hot=None, wall=False):
    """32×24 °C frame. person: dict(r m, posture 'stand'|'sit'|'lie', az deg, clothed bool). hot: dict(kind)."""
    f = room + rng.normal(0, 0.1, (24, 32)) + rng.normal(0, 0.3) + 0.4 * np.linspace(-1, 1, 32)[None, :]
    if hot:
        k = hot["kind"]
        if k == "radiator":   f[6:20, 4:12] = 50 + rng.normal(0, 1)
        elif k == "laptop":   f[12:15, 14:19] = 36 + rng.normal(0, 0.5)
        elif k == "sun":      f[0:24, 18:32] = 27 + rng.normal(0, 0.3)
    if person and not wall:
        r, posture = person["r"], person.get("posture", "stand")
        w_m, h_m = {"stand": (0.5, 1.7), "sit": (0.5, 1.2), "lie": (0.5, 0.5)}[posture]
        px = lambda m: max(1, int(round(np.degrees(2 * np.arctan(m / 2 / r)) / 1.72)))
        w, h = min(px(w_m), 32), min(px(h_m), 24)
        cx = int(16 + person.get("az", 0) / 1.72); cy = 12
        x0, x1 = max(0, cx - w // 2), min(32, cx - w // 2 + w); y0, y1 = max(0, cy - h // 2), min(24, cy - h // 2 + h)
        body = 27.5 if person.get("clothed", True) else 32.0
        f[y0:y1, x0:x1] = body + rng.normal(0, 0.4, (y1 - y0, x1 - x0))
        if h >= 4:  f[y0:y0 + max(1, h // 5), x0:x1] = 32.5 + rng.normal(0, 0.3)   # face on top
    return f


# ── camera ────────────────────────────────────────────────────────────────────
def camera_scores(rng, frames=6, person=None, lit=True, wall=False):
    """Per-frame best person-box score in [0,1] for a station's sweep frames."""
    s = np.clip(rng.normal(0.08, 0.06, frames), 0, 1)
    fp = rng.random(frames) < 0.01
    s[fp] = rng.uniform(0.5, 0.8, fp.sum())
    if person and not wall:
        r = person["r"]; p = (0.95 if r < 3 else 0.85) * (1.0 if lit else 0.55)
        hit = rng.random(frames) < p
        s[hit] = np.clip(rng.normal(0.82, 0.08, hit.sum()), 0, 1)
    return s
