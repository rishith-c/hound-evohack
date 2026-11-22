"""
fusion.py — two-track Bayesian log-odds fusion. Explainable in one sentence to a judge:
"each sensor multiplies the odds of a person by a factor it earned in calibration; the factors are added
in log space; nothing optical can veto something behind a wall."

HIDDEN track (RF only): radar presence, radar breathing-like periodicity (with regularity class and the
two-window rule), CSI presence vs the empty-room baseline, CSI breathing periodicity.
VISIBLE track (optical only): camera person box, thermal warm blob, association by bearing.

Likelihood ratios come from `calibration.json`, which sim.py produces by running the sensor models under
H1 (person) and H0 (nothing / fan / radiator) and taking histogram ratios. On the real rover the same file
is refined from logged stations: it is the one thing that must be measured, not assumed.

Labels, in order of what they claim:
  NOTHING                   both tracks below threshold
  RF ACTIVITY               hidden track raised by presence but no periodicity
  MACHINE-LIKE PERIODICITY  periodic, but too regular to be a person (fan, pump) — reported, not counted
  BREATHING-LIKE PERIODICITY radar or CSI periodicity in the breathing band, physiological regularity
  RF CORROBORATED           radar AND CSI agree on breathing-band periodicity
  PERSON VISIBLE            camera and thermal agree at one bearing
The sentence for the judge is built from the labels, never from the word "alive".
"""
from __future__ import annotations

import json
import math
import os

PRIOR_P = 0.10                                   # a person at a random station
DEFAULT_CAL = os.path.join(os.path.dirname(__file__), "calibration.json")


def _logit(p): return math.log(p / (1 - p))
def _sigmoid(x): return 1 / (1 + math.exp(-x))


class Calibration:
    """Piecewise-constant log-likelihood ratios per feature, learned by sim.py (or from logged stations)."""

    def __init__(self, path=DEFAULT_CAL):
        self.tables = json.load(open(path)) if os.path.exists(path) else {}

    def llr(self, feature: str, value) -> float:
        tab = self.tables.get(feature)
        if not tab or value is None:
            return 0.0
        edges, llrs = tab["edges"], tab["llr"]
        for i in range(len(llrs)):
            if value < edges[i + 1]:
                return llrs[i]
        return llrs[-1]


def fuse(radar: dict | None, csi: dict | None, thermal: dict | None, camera: dict | None,
         cal: Calibration, prior=PRIOR_P) -> dict:
    """Combine one station's features. Returns posteriors, per-sensor contributions and the label."""
    hidden = _logit(prior); visible = _logit(prior); contrib = {}

    # ── hidden track ──
    machine = False
    if radar:
        c = cal.llr("radar_presence", radar.get("presence"))
        contrib["radar_presence"] = c; hidden += c
        if radar.get("cls") == "machine":
            machine = True                                            # periodic but not physiological: no credit
            contrib["radar_breath"] = 0.0
        else:
            c = cal.llr("radar_conf", radar.get("conf"))
            if radar.get("agree") is False:                           # two windows disagree: halve the credit
                c *= 0.5
            contrib["radar_breath"] = c; hidden += c
    if csi:
        c = cal.llr("csi_presence", csi.get("presence_ratio")) if csi.get("presence_ratio") is not None else 0.0
        contrib["csi_presence"] = c; hidden += c
        if csi.get("cls") == "machine":
            machine = True; contrib["csi_breath"] = 0.0
        else:
            c = cal.llr("csi_conf", csi.get("conf")); contrib["csi_breath"] = c; hidden += c

    # ── visible track ──
    if camera:
        c = cal.llr("camera", camera.get("second")); contrib["camera"] = c; visible += c
    if thermal:
        c = cal.llr("thermal", thermal.get("score")); contrib["thermal"] = c; visible += c
    if camera and thermal and thermal.get("blob") and camera.get("second", 0) > 0.5:
        contrib["association"] = 1.0; visible += 1.0                 # both at the same station/bearing: one more factor of e

    p_hidden, p_visible = _sigmoid(hidden), _sigmoid(visible)
    radar_breath = bool(radar and radar.get("cls") == "breathing-like" and radar.get("conf", 0) >= 5.0)
    csi_breath = bool(csi and csi.get("cls") == "breathing-like" and csi.get("conf", 0) >= 5.0)

    if p_visible >= 0.8:
        label = "PERSON VISIBLE"
    elif p_hidden >= 0.8 and radar_breath and csi_breath:
        label = "RF CORROBORATED"
    elif p_hidden >= 0.7 and (radar_breath or csi_breath):
        label = "BREATHING-LIKE PERIODICITY"
    elif machine and p_hidden < 0.7:
        label = "MACHINE-LIKE PERIODICITY"
    elif p_hidden >= 0.5:
        label = "RF ACTIVITY"
    else:
        label = "NOTHING"
    return {"p_hidden": round(p_hidden, 3), "p_visible": round(p_visible, 3), "label": label,
            "contrib": {k: round(v, 2) for k, v in contrib.items()}, "machine": machine}


def sentence(result: dict, radar: dict | None, station: str) -> str:
    """What the operator hears. Built from evidence, never from the word alive."""
    L = result["label"]
    bpm = f" at {radar['bpm']:.0f} breaths/min" if radar and radar.get("bpm") else ""
    return {
        "PERSON VISIBLE": f"{station}: camera and thermal see a person. Go look.",
        "RF CORROBORATED": f"{station}: radar and WiFi both show breathing-band periodicity{bpm}, stable across two windows; nothing optical can see it. Go look behind that wall.",
        "BREATHING-LIKE PERIODICITY": f"{station}: breathing-band periodicity{bpm} on one RF sense only. Worth a second station from another angle.",
        "MACHINE-LIKE PERIODICITY": f"{station}: periodic motion, too regular for a person (fan or pump). Not counted.",
        "RF ACTIVITY": f"{station}: something reflects behind the wall but nothing periodic. Inconclusive.",
        "NOTHING": f"{station}: nothing.",
    }[L]
