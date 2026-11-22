"""
detectors.py — per-sense feature extractors. Each turns raw sensor output into a small dict of scores that
fusion.py converts to likelihood ratios. Same code runs on the Pi and in the simulation.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from vitals import estimate_timestamped, classify, resample, estimate, consistent, FS


def radar_features(t, e, t2=None, e2=None) -> dict:
    """One or two 30 s windows of one gate's static energy → periodicity evidence.
    Returns conf (0–10), cls ('none'|'breathing-like'|'machine'), bpm, two-window agreement, presence (mean energy)."""
    a = estimate_timestamped(t, e)
    out = {"conf": a["confidence"], "cls": classify(a), "bpm": a["bpm"], "cv": a["cv"], "gap": a["gap_frac"],
           "presence": float(np.mean(e)), "agree": None}
    if t2 is not None:
        b = estimate_timestamped(t2, e2)
        out["agree"] = consistent(a, b)
        # the full 60 s carries more SNR than either half; credit it only when the halves agree on a rate
        both = estimate_timestamped(np.concatenate([t, t2 - t2[0] + t[-1] + 0.1]), np.concatenate([e, e2]))
        out["persist"] = both["persist"]; out["cv"] = both["cv"]
        if classify(both) == "machine":
            out["cls"] = "machine"
        if out["agree"]:
            out["conf"] = round(max(both["confidence"], min(a["confidence"], b["confidence"])), 2)
            out["bpm"] = both["bpm"] or out["bpm"]
            if out["cls"] == "none" and out["conf"] >= 3.0:
                out["cls"] = "breathing-like"
        else:
            out["conf"] = round(0.5 * min(a["confidence"], b["confidence"]), 2)
    return out


def csi_features(t, A, baseline_var=None) -> dict:
    """Per-subcarrier amplitude frames → presence (variance vs empty-room baseline) and breathing periodicity."""
    A = np.asarray(A, float)
    var = float(np.mean(np.var(A, axis=0)))
    presence = var / baseline_var if baseline_var else None
    # breathing: best subcarrier by repetition score, on a 10 Hz resample
    best = {"confidence": 0.0, "bpm": 0.0, "cv": 1.0}
    for k in range(0, A.shape[1], 2):
        x = resample(t, A[:, k], FS)
        est = estimate(x, FS)
        if est["confidence"] > best["confidence"]:
            best = est
    return {"var": var, "presence_ratio": presence, "conf": best["confidence"], "bpm": best["bpm"],
            "cv": best["cv"], "cls": classify(best)}


def thermal_features(frame, room=None) -> dict:
    """32×24 °C frame → warm-blob evidence: a connected region in the human band (25–38 °C) with plausible size."""
    f = np.asarray(frame, float)
    room = float(np.median(f)) if room is None else room
    band = (f > room + 2.5) & (f < 38.5)
    lab, n = ndimage.label(band)
    best = None
    for i in range(1, n + 1):
        m = lab == i
        area = int(m.sum())
        if area < 3:
            continue
        ys, xs = np.where(m)
        h, w = int(np.ptp(ys)) + 1, int(np.ptp(xs)) + 1
        mean_t = float(f[m].mean())
        # plausibility: warm (not hot), compact, aspect between lying (2:1) and standing (1:4)
        aspect = h / max(w, 1)
        score = (1.0 if 3 <= area <= 450 else 0.4) * (1.0 if 0.4 <= aspect <= 5.0 else 0.5) * (1.0 if 25 <= mean_t <= 36 else 0.3)
        if best is None or score > best["score"]:
            best = {"score": score, "area": area, "mean_t": round(mean_t, 1), "az_px": float(xs.mean() - 16), "h": int(h), "w": int(w)}
    hot = float((f > 42).sum())
    return {"blob": best, "score": best["score"] if best else 0.0, "hot_px": hot, "room": round(room, 1)}


def camera_features(scores) -> dict:
    """Per-frame person scores → station evidence: the second-best frame (one confident frame can be a poster)."""
    s = np.sort(np.asarray(scores, float))[::-1]
    return {"best": float(s[0]) if len(s) else 0.0, "second": float(s[1]) if len(s) > 1 else 0.0, "frames": int(len(s))}
