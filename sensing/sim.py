#!/usr/bin/env python3
"""
sim.py — Monte Carlo of the whole sensing chain: sensor models → detectors → calibration → fusion → labels.

  1. CALIBRATE: run each sensor under H1 (person) and H0 (empty / fan / radiator / laptop) many times, bin the
     detector score, and store log-likelihood-ratio tables → calibration.json  (train half of the trials).
  2. EVALUATE on fresh trials: per scenario, the distribution of labels; detection and false-alarm rates.
  3. SWEEPS: breathing detector ROC vs modulation-to-noise ratio and dwell; fan discrimination; thermal vs range;
     mission time for a 3-room search.

Writes results.json and results.md next to this file.  Run: ~/Developer/walleye/.venv/bin/python sim.py
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from models import radar_energy, csi_frames, thermal_frame, camera_scores   # noqa: E402
from detectors import radar_features, csi_features, thermal_features, camera_features  # noqa: E402
from fusion import Calibration, fuse  # noqa: E402

HERE = os.path.dirname(__file__)
rng = np.random.default_rng(7)
N = int(os.environ.get("SIM_N", "120"))          # trials per scenario per phase


# ── one station under one scenario ──────────────────────────────────────────
def station(rng, sc: dict) -> dict:
    """Simulate one 60 s station: two 30 s radar windows, one CSI window, a thermal + camera sweep."""
    person = sc.get("person"); wall = sc.get("wall", False); fan = sc.get("fan"); hot = sc.get("hot")
    breath = None
    if person:
        f0 = rng.uniform(0.18, 0.40) if person.get("posture") != "lie" else rng.uniform(0.15, 0.30)
        breath = {"f0": f0, "cv": rng.uniform(0.06, 0.15)}
        r = person["r"]
        mnr = sc.get("mnr", 6.0 * (1.5 / r) ** 2 * (0.5 if wall else 1.0))     # ALLOC range law; sweep overrides
    else:
        mnr = 0.0
    fan_spec = {"f0": rng.uniform(0.2, 0.55), "amp": rng.uniform(2, 6)} if fan else None
    base = rng.uniform(25, 45) + (20 * (1.5 / person["r"]) if person else 0)  # presence: mean static energy
    t1, e1 = radar_energy(rng, 30, breath, mnr, base=base, fan=fan_spec, motion=sc.get("motion", False))
    t2, e2 = radar_energy(rng, 30, breath, mnr, base=base, fan=fan_spec, motion=sc.get("motion", False))
    rad = radar_features(t1, e1, t2, e2)

    csi_breath = {"f0": breath["f0"]} if breath else None
    depth = rng.uniform(0.006, 0.02) if person else 0.0
    tc, A = csi_frames(rng, 30, csi_breath, depth=depth, motion=sc.get("motion", False), wall=wall)
    baseline = sc.get("csi_baseline_var", 1.0 + 0.02)               # empty-room calibration (var of noise + drift)
    if fan:                                                             # a fan modulates CSI too, regularly
        A[:, ::3] += 0.4 * np.sin(2 * np.pi * fan_spec["f0"] * tc)[:, None]
    csi = csi_features(tc, A, baseline_var=baseline if sc.get("csi_calibrated", True) else None)

    frames = [thermal_frame(rng, person, hot=hot, wall=wall) for _ in range(3)]
    th = max((thermal_features(f) for f in frames), key=lambda d: d["score"])
    cam = camera_features(camera_scores(rng, 6, person, lit=sc.get("lit", True), wall=wall))
    return {"radar": rad, "csi": csi, "thermal": th, "camera": cam}


SCENARIOS = {
    "empty room":                  {"person": None},
    "empty room + fan":            {"person": None, "fan": True},
    "empty room + HVAC rumble":    {"person": None, "motion": True},
    "hot radiator, visible":       {"person": None, "hot": {"kind": "radiator"}},
    "warm laptop, visible":        {"person": None, "hot": {"kind": "laptop"}},
    "sunlit wall patch, visible":  {"person": None, "hot": {"kind": "sun"}},
    "person visible 2 m standing": {"person": {"r": 2.0, "posture": "stand"}},
    "person visible 4 m lying":    {"person": {"r": 4.0, "posture": "lie"}},
    "person visible, dark":        {"person": {"r": 2.5, "posture": "sit"}, "lit": False},
    "behind drywall 2 m standing": {"person": {"r": 2.0, "posture": "stand"}, "wall": True},
    "behind drywall 3 m sitting":  {"person": {"r": 3.0, "posture": "sit"}, "wall": True},
    "behind drywall 4 m lying":    {"person": {"r": 4.0, "posture": "lie"}, "wall": True},
    "behind drywall 3 m + fan":    {"person": {"r": 3.0, "posture": "sit"}, "wall": True, "fan": True},
    "behind drywall, CSI uncal.":  {"person": {"r": 3.0, "posture": "sit"}, "wall": True, "csi_calibrated": False},
}
H1 = {k for k, v in SCENARIOS.items() if v.get("person")}


# ── calibration: histogram LLR tables ───────────────────────────────────────
def llr_table(pos, neg, edges, floor=0.02):
    hp, _ = np.histogram(pos, edges); hn, _ = np.histogram(neg, edges)
    hp = (hp + floor * len(pos)) / (len(pos) * (1 + floor * len(edges))); hn = (hn + floor * len(neg)) / (len(neg) * (1 + floor * len(edges)))
    return {"edges": list(map(float, edges)), "llr": [float(np.clip(np.log(p / n), -3, 3)) for p, n in zip(hp, hn)]}


def calibrate(trials):
    def col(f, key, only=None):
        return [f(t["features"]) for t in trials if (only is None or (t["scenario"] in H1) == only) and f(t["features"]) is not None]
    tabs = {}
    tabs["radar_conf"] = llr_table(col(lambda f: f["radar"]["conf"] if f["radar"]["cls"] != "machine" else None, "", True),
                                   col(lambda f: f["radar"]["conf"] if f["radar"]["cls"] != "machine" else None, "", False), np.array([0, 2, 3, 4, 5, 6, 7, 8, 9, 10.01]))
    tabs["radar_presence"] = llr_table(col(lambda f: f["radar"]["presence"], "", True), col(lambda f: f["radar"]["presence"], "", False), np.array([0, 30, 40, 50, 60, 101]))
    tabs["csi_presence"] = llr_table(col(lambda f: f["csi"]["presence_ratio"], "", True), col(lambda f: f["csi"]["presence_ratio"], "", False), np.array([0, 0.9, 1.1, 1.3, 1.6, 2.5, 5, 1e9]))
    tabs["csi_conf"] = llr_table(col(lambda f: f["csi"]["conf"] if f["csi"]["cls"] != "machine" else None, "", True),
                                 col(lambda f: f["csi"]["conf"] if f["csi"]["cls"] != "machine" else None, "", False), np.array([0, 2, 3, 4, 5, 6, 7, 8, 10.01]))
    vis = lambda t: t["scenario"] in H1 and not SCENARIOS[t["scenario"]].get("wall")
    tabs["camera"] = llr_table([t["features"]["camera"]["second"] for t in trials if vis(t)], [t["features"]["camera"]["second"] for t in trials if not vis(t)], np.array([0, 0.2, 0.4, 0.5, 0.6, 0.7, 0.8, 1.01]))
    tabs["thermal"] = llr_table([t["features"]["thermal"]["score"] for t in trials if vis(t)], [t["features"]["thermal"]["score"] for t in trials if not vis(t)], np.array([0, 0.05, 0.2, 0.35, 0.5, 0.8, 1.01]))
    json.dump(tabs, open(os.path.join(HERE, "calibration.json"), "w"), indent=1)
    return tabs


# ── sweeps ──────────────────────────────────────────────────────────────────
def sweep_breathing(rng, n=60):
    """Breathing detector: P(class = breathing-like & conf ≥ 5) vs modulation-to-noise ratio and dwell."""
    out = {}
    for dwell in (15, 30, 45):
        row = {}
        for mnr in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
            hits = 0
            for _ in range(n):
                f0 = rng.uniform(0.18, 0.40)
                t, e = radar_energy(rng, dwell, {"f0": f0, "cv": 0.10}, mnr)
                r = radar_features(t, e)
                hits += r["cls"] == "breathing-like" and r["conf"] >= 5.0
            row[str(mnr)] = round(hits / n, 3)
        fa = 0
        for _ in range(n):
            t, e = radar_energy(rng, dwell, None, 0.0)
            r = radar_features(t, e); fa += r["cls"] == "breathing-like" and r["conf"] >= 5.0
        row["false_alarm_empty"] = round(fa / n, 3)
        out[str(dwell)] = row
    return out


def sweep_fan(rng, n=80):
    """Can regularity separate a fan from a person? Report class rates for fan-only and person-only windows."""
    res = {}
    for name, kw in (("fan only", dict(breath=None, fan={"f0": 0.35, "amp": 4.0})),
                     ("person only", dict(breath={"f0": 0.28, "cv": 0.10}, mnr=3.0)),
                     ("person + fan", dict(breath={"f0": 0.28, "cv": 0.10}, mnr=3.0, fan={"f0": 0.35, "amp": 4.0}))):
        cnt = {"none": 0, "breathing-like": 0, "machine": 0}
        for _ in range(n):
            t, e = radar_energy(rng, 30, kw.get("breath"), kw.get("mnr", 0.0), fan=kw.get("fan"))
            cnt[radar_features(t, e)["cls"]] += 1
        res[name] = {k: round(v / n, 3) for k, v in cnt.items()}
    return res


def sweep_thermal(rng, n=40):
    out = {}
    for posture in ("stand", "lie"):
        row = {}
        for r in (1, 2, 3, 4, 5, 6):
            hits = sum(thermal_features(thermal_frame(rng, {"r": r, "posture": posture}))["score"] >= 0.5 for _ in range(n))
            row[str(r)] = round(hits / n, 3)
        out[posture] = row
    fp = {}
    for kind in ("radiator", "laptop", "sun"):
        fp[kind] = round(sum(thermal_features(thermal_frame(rng, None, hot={"kind": kind}))["score"] >= 0.5 for _ in range(n)) / n, 3)
    out["false_positive"] = fp
    return out


def mission():
    """Time to search a small apartment: stations × 60 s + travel at 0.4 m/s, vs a 43 min pack."""
    rooms = [("hall", 2), ("living", 3), ("bedroom", 2), ("kitchen", 2)]
    stations = sum(n for _, n in rooms); travel_m = 4 * stations
    t_station, t_travel = stations * 60, travel_m / 0.4
    return {"rooms": len(rooms), "stations": stations, "station_s": 60, "travel_m": travel_m,
            "total_min": round((t_station + t_travel) / 60, 1), "pack_min": 43, "fits": (t_station + t_travel) / 60 < 43,
            "with_second_angle_min": round((2 * t_station + t_travel) / 60, 1)}


# ── main ───────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    print(f"simulating {len(SCENARIOS)} scenarios × {N} trials × 2 phases …", flush=True)
    train = [{"scenario": k, "features": station(rng, v)} for k, v in SCENARIOS.items() for _ in range(N)]
    tabs = calibrate(train)
    cal = Calibration()
    test = [{"scenario": k, "features": station(rng, v)} for k, v in SCENARIOS.items() for _ in range(N)]
    labels = {}
    for tr in test:
        f = tr["features"]; res = fuse(f["radar"], f["csi"], f["thermal"], f["camera"], cal)
        labels.setdefault(tr["scenario"], {}).setdefault(res["label"], 0)
        labels[tr["scenario"]][res["label"]] += 1
    per = {}
    for sc, d in labels.items():
        tot = sum(d.values()); frac = {k: round(v / tot, 3) for k, v in sorted(d.items(), key=lambda kv: -kv[1])}
        found = sum(v for k, v in d.items() if k in ("PERSON VISIBLE", "RF CORROBORATED", "BREATHING-LIKE PERIODICITY")) / tot
        per[sc] = {"labels": frac, "person_reported": round(found, 3), "truth": "person" if sc in H1 else "no person"}
    fa = np.mean([per[s]["person_reported"] for s in per if s not in H1]); det_wall = np.mean([per[s]["person_reported"] for s in per if s in H1 and SCENARIOS[s].get("wall")])
    det_vis = np.mean([per[s]["person_reported"] for s in per if s in H1 and not SCENARIOS[s].get("wall")])
    results = {
        "n_per_scenario": N, "scenarios": per,
        "summary": {"false_alarm_rate_no_person": round(float(fa), 3), "detection_behind_drywall": round(float(det_wall), 3),
                    "detection_visible": round(float(det_vis), 3)},
        "breathing_roc": sweep_breathing(rng), "fan_discrimination": sweep_fan(rng), "thermal_vs_range": sweep_thermal(rng),
        "mission": mission(), "calibration": tabs, "seconds": round(time.time() - t0, 1),
    }
    json.dump(results, open(os.path.join(HERE, "results.json"), "w"), indent=1)
    # human-readable
    L = ["# Sensing simulation results", "", f"{N} trials per scenario (fresh trials after calibration).", "",
         "| scenario | truth | person reported | labels |", "|---|---|---|---|"]
    for sc, d in per.items():
        L.append(f"| {sc} | {d['truth']} | {d['person_reported']:.0%} | " + ", ".join(f"{k} {v:.0%}" for k, v in d["labels"].items()) + " |")
    s = results["summary"]
    L += ["", f"False alarm (person reported with nobody there): **{s['false_alarm_rate_no_person']:.1%}** · "
              f"detection behind drywall: **{s['detection_behind_drywall']:.0%}** · visible: **{s['detection_visible']:.0%}**", "",
          "## Breathing detector vs modulation-to-noise ratio (P of breathing-like, conf ≥ 5)", "",
          "| dwell s | " + " | ".join(f"MNR {m}" for m in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)) + " | false alarm, empty |", "|---|" + "---|" * 8]
    for dw, row in results["breathing_roc"].items():
        L.append(f"| {dw} | " + " | ".join(f"{row[str(m)]:.0%}" for m in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0)) + f" | {row['false_alarm_empty']:.0%} |")
    L += ["", "## Fan discrimination (regularity test)", "", "| window | none | breathing-like | machine |", "|---|---|---|---|"]
    for k, v in results["fan_discrimination"].items():
        L.append(f"| {k} | {v['none']:.0%} | {v['breathing-like']:.0%} | {v['machine']:.0%} |")
    L += ["", "## Thermal blob detection vs range (P score ≥ 0.5)", "", "| posture | " + " | ".join(f"{r} m" for r in (1, 2, 3, 4, 5, 6)) + " |", "|---|" + "---|" * 6]
    for p in ("stand", "lie"):
        L.append(f"| {p} | " + " | ".join(f"{results['thermal_vs_range'][p][str(r)]:.0%}" for r in (1, 2, 3, 4, 5, 6)) + " |")
    L.append("| false positives | " + ", ".join(f"{k} {v:.0%}" for k, v in results["thermal_vs_range"]["false_positive"].items()) + " |")
    m = results["mission"]
    L += ["", f"## Mission: {m['rooms']} rooms, {m['stations']} stations × {m['station_s']} s + {m['travel_m']} m travel → **{m['total_min']} min** of a {m['pack_min']} min pack ({'fits' if m['fits'] else 'DOES NOT FIT'})", ""]
    open(os.path.join(HERE, "results.md"), "w").write("\n".join(L))
    print("\n".join(L))
    print(f"\n{results['seconds']} s")


if __name__ == "__main__":
    main()
