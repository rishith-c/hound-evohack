"""Score the Wi-Fi network on the test people (Blender people it never trained on) and write ml/results/synthetic.md.

    python ml/evaluate.py
    python ml/evaluate.py --model ml/models/csi_nn_clean.npz --name "trained on clean data"   (adds a section)

Every number in the results file is produced by this script from ml/data/synth.npz.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import csi_window as cw  # noqa: E402
from net import CsiNet  # noqa: E402
from train import load, split_of  # noqa: E402

LABELS = {"person": ("no one", "person"), "moving": ("still", "moving"), "zone": ("left", "centre", "right")}


def confusion(y, p, k):
    m = np.zeros((k, k), int)
    np.add.at(m, (y, p), 1)
    return m


def md_confusion(m, names):
    head = "| true \\ said | " + " | ".join(names) + " |\n|---|" + "---|" * len(names) + "\n"
    return head + "".join(f"| {names[i]} | " + " | ".join(str(v) for v in row) + " |\n" for i, row in enumerate(m))


def pct(x):
    return f"{100 * x:.1f} %"


def score(net, X, y, meta):
    p = net.predict(X)
    r = {"n": len(X), "threshold": net.meta.get("person_threshold", 0.5)}
    said = (p["person"][:, 1] > r["threshold"]).astype(int)
    kind = meta["kind"]
    r["person_acc"] = float((said == y["person"]).mean())
    r["person_conf"] = confusion(y["person"], said, 2)
    r["empty_ok"] = float((said[kind == 0] == 0).mean())
    r["fan_false_alarm"] = float((said[(kind == 0) & (meta["fan"] == 1)] == 1).mean())
    r["nofan_false_alarm"] = float((said[(kind == 0) & (meta["fan"] == 0)] == 1).mean())
    r["still_found"] = float((said[kind == 1] == 1).mean())
    r["moving_found"] = float((said[kind == 2] == 1).mean())
    for lab, m in (("standing", (kind == 1) & (meta["lying"] == 0)), ("lying", (kind == 1) & (meta["lying"] == 1))):
        r[f"still_found_{lab}"] = float((said[m] == 1).mean())
    d = meta["depth"]
    r["still_by_depth"] = [(lo, hi, float((said[(kind == 1) & (d >= lo) & (d < hi)] == 1).mean()), int(((kind == 1) & (d >= lo) & (d < hi)).sum()))
                           for lo, hi in ((0.5, 1.4, ), (1.4, 2.3), (2.3, 3.3))]
    pres = kind > 0
    mv = p["moving"].argmax(1)
    r["moving_acc"] = float((mv[pres] == y["moving"][pres]).mean())
    r["moving_conf"] = confusion(y["moving"][pres], mv[pres], 2)
    if "zone" in p:
        z = p["zone"].argmax(1)
        r["zone_acc"] = float((z[pres] == y["zone"][pres]).mean())
        r["zone_conf"] = confusion(y["zone"][pres], z[pres], 3)
    return r, p


def breathing(X, meta, said_person, said_moving):
    """Breathing rate (DSP on the window, not the network) on still people the network found."""
    m = (meta["kind"] == 1) & (said_person == 1) & (said_moving == 0)
    est = np.array([cw.breathing_rate(x) for x in X[m]]).reshape(-1, 2)
    err = np.abs(est[:, 0] - meta["bpm"][m])
    clear = est[:, 1] >= np.quantile(est[:, 1], 0.75) if len(est) else np.zeros(0, bool)
    return {"n": int(m.sum()), "median_err": float(np.median(err)) if len(err) else float("nan"),
            "within3": float((err <= 3).mean()) if len(err) else float("nan"),
            "within3_clear": float((err[clear] <= 3).mean()) if clear.any() else float("nan")}


def speed(net, x, n=50):
    net.predict(x[:1])
    t0 = time.perf_counter()
    for _ in range(n):
        net.predict(x[:1])
    return (time.perf_counter() - t0) / n * 1000


def section(title, r, net, extra=""):
    s = f"## {title}\n\n{extra}"
    s += f"Test set: {r['n']} windows of 10 s, from people and empty rooms the network never saw in training.\n\n"
    s += "### Is someone there?\n\n"
    s += (f"The rover says PERSON when the network's P(person) is above {r['threshold']:.2f}, a threshold set on the"
          " validation set so that at most 10 % of empty rooms (fans included) raise a false alarm.\n\n")
    s += f"Accuracy {pct(r['person_acc'])}.\n\n" + md_confusion(r["person_conf"], LABELS["person"]) + "\n"
    s += "| case | result |\n|---|---|\n"
    s += f"| empty room called empty | {pct(r['empty_ok'])} |\n"
    s += f"| empty room with an oscillating fan called a person (false alarm) | {pct(r['fan_false_alarm'])} |\n"
    s += f"| empty room without a fan called a person (false alarm) | {pct(r['nofan_false_alarm'])} |\n"
    s += f"| moving person found | {pct(r['moving_found'])} |\n"
    s += f"| still person (breathing only) found | {pct(r['still_found'])} |\n"
    s += f"| still person standing found | {pct(r['still_found_standing'])} |\n"
    s += f"| still person lying on the floor found | {pct(r['still_found_lying'])} |\n"
    for lo, hi, v, n in r["still_by_depth"]:
        s += f"| still person {lo:.1f}-{hi:.1f} m behind the wall found ({n} windows) | {pct(v)} |\n"
    s += f"\n### Still or moving? (windows with a person)\n\nAccuracy {pct(r['moving_acc'])}.\n\n" + md_confusion(r["moving_conf"], LABELS["moving"]) + "\n"
    if "zone_acc" in r:
        s += f"### Left, centre or right? (windows with a person)\n\nAccuracy {pct(r['zone_acc'])} (chance is about 33 %).\n\n" + md_confusion(r["zone_conf"], LABELS["zone"]) + "\n"
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.path.join(HERE, "data", "synth.npz"))
    ap.add_argument("--model", default=os.path.join(HERE, "models", "csi_nn.npz"))
    ap.add_argument("--name", default="")
    ap.add_argument("--out", default=os.path.join(HERE, "results", "synthetic.md"))
    a = ap.parse_args()
    X, y, meta = load(a.data)
    te = split_of(meta["group"]) == 2
    Xt, yt, mt = X[te], {k: v[te] for k, v in y.items()}, {k: (v[te] if np.ndim(v) else v) for k, v in meta.items()}
    net = CsiNet.load(a.model)
    r, p = score(net, Xt, yt, mt)
    b = breathing(Xt, mt, (p["person"][:, 1] > r["threshold"]).astype(int), p["moving"].argmax(1))
    ms = speed(net, Xt)
    for k, v in r.items():
        if not isinstance(v, (np.ndarray, list)):
            print(f"{k:28s} {v:.3f}" if isinstance(v, float) else f"{k:28s} {v}")
    print("breathing", b, f"; {ms:.1f} ms per window here")
    if a.name:                                              # an extra model: append its section
        open(a.out, "a").write("\n" + section(f"Model: {a.name} ({os.path.relpath(a.model, os.path.dirname(HERE))})", r, net))
        return
    m = net.meta
    log = json.load(open(os.path.join(HERE, "results", "train_log.json")))
    best = min(log["epochs"], key=lambda e: e["val_loss"])
    doc = ("# Wi-Fi network: results on simulated people\n\n"
           f"Written by `ml/evaluate.py` on {time.strftime('%Y-%m-%d')} from `{os.path.relpath(a.data, os.path.dirname(HERE))}`"
           f" (simulator seed {int(meta['seed'])}) and `{os.path.relpath(a.model, os.path.dirname(HERE))}`. Every number below is"
           " from simulation: the Blender people of `ml/data/people.json` in the simulator of `ml/simulate_csi.py`. None is from"
           " the rover; real recordings go in `ml/results/real.md`.\n\n"
           f"Network: {net.n_params()} parameters, heads {', '.join(net.head_names)}. Trained {m.get('trained')} on {m['windows']['train']}"
           f" windows (validation {m['windows']['val']}, test {m['windows']['test']}; split by person), best epoch {best['epoch']}"
           f" of {len(log['epochs'])}, {m.get('seconds')} s on a laptop CPU. One window takes {ms:.1f} ms here.\n\n")
    doc += section("Main model", r, net)
    doc += ("### Breathing rate (signal processing on the same window, for still people the network found)\n\n"
            f"{b['n']} windows: median error {b['median_err']:.1f} breaths/min, within 3 breaths/min in {pct(b['within3'])}."
            f" The quarter of windows with the clearest rhythm do no better ({pct(b['within3_clear'])} within 3), so the"
            " clarity cannot tell a right rate from a wrong one. The live view therefore shows no breathing rate.\n")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write(doc)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
