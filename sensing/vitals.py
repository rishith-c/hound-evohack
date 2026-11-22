"""
vitals.py — breathing-like periodicity from a slow-time signal (radar gate energy or a CSI subcarrier amplitude).

Ported from Walleye bench/vitals.py with three changes the external review asked for:
  1. TIMESTAMPS. Samples arrive with real times (USB latency, dropped frames). They are resampled onto a
     uniform 10 Hz grid before any filtering, so a 20 % frame loss does not masquerade as a slower rate.
  2. REGULARITY. A fan is *more* periodic than a person. Breath-to-breath intervals in adults vary by
     8–15 % (respiratory variability is physiological); a fan's vary by well under 1 %. The interval
     coefficient of variation is reported so the fusion can down-weight machine-like periodicity.
  3. TWO WINDOWS. `consistent()` says whether two consecutive estimates agree in rate — the rule that
     rejects a one-off noise peak.

Confidence is autocorrelation at 1..3 periods, scaled 0–10, exactly as Walleye — it measures REPETITION,
not life. The label for a high value is "breathing-like periodicity". Never "alive".
"""
from __future__ import annotations

import numpy as np
from scipy import signal

FS = 10.0
WINDOW_S = 30.0
F_LO, F_HI = 0.13, 0.60          # 8–36 breaths/min
MIN_SAMPLES = 200


def resample(t: np.ndarray, x: np.ndarray, fs: float = FS) -> np.ndarray:
    """Irregular (t, x) → uniform grid at fs by linear interpolation. Gaps > 1 s are bridged and reported by the caller."""
    t = np.asarray(t, float); x = np.asarray(x, float)
    if len(t) < 2:
        return x
    grid = np.arange(t[0], t[-1], 1.0 / fs)
    return np.interp(grid, t, x)


def _periodicity(x, f0, fs=FS, n_lags=3):
    if f0 <= 0 or len(x) < 3:
        return 0.0
    x = x - x.mean(); denom = float(np.dot(x, x))
    if denom <= 1e-12:
        return 0.0
    vals = []
    for k in range(1, n_lags + 1):
        lag = int(round(fs / f0 * k))
        if lag <= 0 or lag >= len(x):
            break
        vals.append(float(np.dot(x[:-lag], x[lag:]) / denom))
    return max(0.0, float(np.mean(vals))) * 10.0 if vals else 0.0


def _bandpass(x, fs=FS):
    nyq = fs / 2.0
    sos = signal.butter(4, [F_LO / nyq, min(F_HI / nyq, 0.99)], btype="band", output="sos")
    padlen = min(len(x) - 1, 24)
    return signal.sosfiltfilt(sos, x, padlen=padlen) if padlen >= 1 else x - x.mean()


def persistence(x: np.ndarray, f0: float, fs: float = FS, lags=(5, 6, 7)) -> float:
    """Normalised autocorrelation at 5–7 periods. A motor stays correlated for tens of periods; a person's
    breath-to-breath variability (8–15 %) diffuses the phase, so the correlation at lag k falls roughly as
    exp(-½ (2π·CV·√k)²): about 0.3 at six periods for a person, above 0.8 for a fan."""
    if f0 <= 0 or len(x) < 3:
        return 0.0
    x = x - x.mean()
    vals = []
    for k in lags:
        lag = int(round(fs / f0 * k))
        if 0 < lag < len(x) - 10:
            a, b = x[:-lag], x[lag:]                       # normalise on the OVERLAP, or half a window of lag halves the value
            den = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
            if den > 1e-12:
                vals.append(float(np.dot(a, b) / den))
    return float(np.mean(vals)) if vals else 0.0


def interval_cv(wave: np.ndarray, f0: float, fs: float = FS) -> float:
    """Coefficient of variation of breath-to-breath intervals (peak to peak of the band-passed wave)."""
    if f0 <= 0:
        return 1.0
    dist = int(0.6 * fs / f0)
    peaks, _ = signal.find_peaks(wave, distance=max(dist, 2), prominence=0.2 * (np.std(wave) + 1e-9))
    if len(peaks) < 4:
        return 1.0
    iv = np.diff(peaks) / fs
    return float(np.std(iv) / (np.mean(iv) + 1e-9))


def estimate(x: np.ndarray, fs: float = FS) -> dict:
    """Rate, confidence (0–10 repetition score), in-band SNR and interval CV for one uniformly sampled signal."""
    x = np.asarray(x, float); n = len(x)
    if n < MIN_SAMPLES or not np.all(np.isfinite(x)) or np.ptp(x) < 1e-9:
        return {"bpm": 0.0, "confidence": 0.0, "snr": 0.0, "cv": 1.0, "persist": 0.0, "samples": n}
    wave = _bandpass(signal.detrend(x), fs)
    nper = min(len(wave), int(WINDOW_S * fs))
    freqs, psd = signal.welch(wave, fs=fs, nperseg=nper, nfft=8192)
    band = (freqs >= F_LO) & (freqs <= F_HI)
    if not band.any() or psd[band].max() <= 0:
        return {"bpm": 0.0, "confidence": 0.0, "snr": 0.0, "cv": 1.0, "persist": 0.0, "samples": n}
    f0 = float(freqs[band][np.argmax(psd[band])])
    snr = float(psd[band].max() / (float(np.median(psd[band])) or 1e-20))
    return {"bpm": round(f0 * 60, 1), "confidence": round(_periodicity(wave, f0, fs), 2),
            "snr": round(snr, 1), "cv": round(interval_cv(wave, f0, fs), 3),
            "persist": round(persistence(wave, f0, fs), 3), "samples": n}


def estimate_timestamped(t, x, fs: float = FS) -> dict:
    """The same, from irregular timestamps. Also reports the fraction of the window lost to gaps > 0.5 s."""
    t = np.asarray(t, float)
    gaps = float(np.sum(np.clip(np.diff(t) - 0.5, 0, None))) / max(t[-1] - t[0], 1e-9) if len(t) > 1 else 1.0
    out = estimate(resample(t, x, fs), fs)
    out["gap_frac"] = round(gaps, 3)
    return out


def consistent(a: dict, b: dict, tol: float = 0.10, min_conf: float = 3.5) -> bool:
    """Two consecutive windows agree: both confident, rates within `tol` of each other."""
    if a["confidence"] < min_conf or b["confidence"] < min_conf or a["bpm"] <= 0 or b["bpm"] <= 0:
        return False
    return abs(a["bpm"] - b["bpm"]) / max(a["bpm"], b["bpm"]) <= tol


def classify(est: dict) -> str:
    """Periodicity class from one estimate. 'machine' = too regular to be a person."""
    if est["confidence"] < 3.0:
        return "none"
    p, cv = est.get("persist", 0.0), est["cv"]
    if est["confidence"] >= 6.0 and ((p >= 0.85 and cv < 0.04) or p >= 0.95):   # a missed person costs more than a counted fan: both tests, or an extreme one
        return "machine"                       # correlated for six-plus periods: a motor, not a chest
    return "breathing-like"
