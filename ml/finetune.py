"""Fine-tune the simulation-trained network on real recordings from the rover, and compare the two on recordings
neither has seen. Writes ml/models/csi_nn_real.npz and ml/results/real.md.

    python ml/finetune.py                        (recordings from ml/data/real/, made by ml/record.py)

The split is by recording, never by window: neighbouring 10 s windows of one recording are nearly the same signal, so
splitting windows would put the same moment in training and testing and score far too well. Each label's recordings
are dealt out newest first: one in five to test, one in five to validation, the rest to training, so every split has
every label; with
fewer than 3 recordings of a label, that label's test score is missing and the file says so.
"""
import argparse
import glob
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import csi_window as cw  # noqa: E402
from net import CsiNet  # noqa: E402
from record import LABELS, REAL  # noqa: E402
from train import person_threshold, train  # noqa: E402

HOP = 2.0                                           # s between window ends


def windows(path):
    """One recording → (normalised windows, labels)."""
    d = np.load(path)
    t, amp = d["t"], d["amp"]
    label = str(d["label"])
    out = []
    for end in np.arange(t[0] + cw.SECONDS, t[-1] + 1e-9, HOP):
        W = cw.to_window(t, amp, end)
        if W is not None:
            out.append(W)
    X = cw.normalise(np.array(out)) if out else np.zeros((0, cw.N_IN, cw.N_T), np.float32)
    k = LABELS.index(label)
    y = {"person": np.full(len(X), int(k > 0)), "moving": np.full(len(X), k - 1 if k > 0 else -1)}
    return X, y, label, bool(d["simulated"]) if "simulated" in d.files else False


def deal(files):
    """Recordings → split (0 train, 1 validation, 2 test): per label, newest first, 1 in 5 to test and 1 in 5 to validation."""
    split = {}
    for lab in LABELS:
        fs = sorted([f for f in files if os.path.basename(f).startswith(lab + "_")], reverse=True)
        for i, f in enumerate(fs):
            split[f] = (2 if i % 5 == 0 else 1 if i % 5 == 1 else 0) if len(fs) >= 3 else 0
    return split


def stack(items):
    X = np.concatenate([x for x, *_ in items]) if items else np.zeros((0, cw.N_IN, cw.N_T), np.float32)
    y = {k: np.concatenate([yy[k] for _, yy, *_ in items]).astype(np.int64) for k in ("person", "moving")} if items else {}
    return X, y


def report(net, X, y, thr):
    p = net.predict(X)
    said = p["person"][:, 1] > thr
    pres = y["person"] == 1
    r = {"windows": len(X), "person_acc": float((said == pres).mean())}
    if (~pres).any():
        r["empty_false_alarm"] = float(said[~pres].mean())
    for k, name in ((0, "still"), (1, "moving")):
        m = y["moving"] == k
        if m.any():
            r[f"{name}_found"] = float(said[m].mean())
    if pres.any():
        r["moving_acc"] = float((p["moving"][pres].argmax(1) == y["moving"][pres]).mean())
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--real", default=REAL)
    ap.add_argument("--model", default=os.path.join(HERE, "models", "csi_nn.npz"))
    ap.add_argument("--out", default=os.path.join(HERE, "models", "csi_nn_real.npz"))
    ap.add_argument("--results", default=os.path.join(HERE, "results", "real.md"))
    ap.add_argument("--epochs", type=int, default=20)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.real, "*.npz")))
    os.makedirs(os.path.dirname(a.results), exist_ok=True)
    head = "# Wi-Fi network: results on real recordings\n\n"
    if not files:
        open(a.results, "w").write(head + f"No recordings in `{os.path.relpath(a.real, os.path.dirname(HERE))}` yet, so there are no"
                                   " real results. Record with `ml/record.py` (empty, still, moving; three or more of each),"
                                   " then run `ml/finetune.py`.\n")
        print("no recordings: wrote", a.results)
        return
    split = deal(files)
    items = {f: windows(f) for f in files}
    sim = any(v[3] for v in items.values())
    parts = [stack([items[f] for f in files if split[f] == s]) for s in (0, 1, 2)]
    (Xtr, ytr), (Xv, yv), (Xte, yte) = parts
    print(f"{len(files)} recordings → windows: train {len(Xtr)}, validation {len(Xv)}, test {len(Xte)}")
    base = CsiNet.load(a.model)
    thr0 = base.meta.get("person_threshold", 0.5)
    net = CsiNet.load(a.model)
    t0 = time.time()
    net, hist = train(Xtr, ytr, Xv if len(Xv) else Xtr, yv if len(Xv) else ytr, epochs=a.epochs, lr=5e-4, patience=5, net=net)
    thr = person_threshold(net, Xv, yv) if len(Xv) and (yv["person"] == 0).any() else thr0
    net.save(a.out, **{**base.meta, "finetuned_on": len(files), "person_threshold": thr, "finetuned": time.strftime("%Y-%m-%d"),
                       "simulated_recordings": sim})
    rb, rf = (report(n, Xte, yte, th) for n, th in ((base, thr0), (net, thr))) if len(Xte) else ({}, {})
    rows = sorted(set(rb) | set(rf))
    doc = head
    if sim:
        doc += ("**These recordings are simulated** (`ml/replay.py --record`), not made on the rover: this run only shows that"
                " the record → fine-tune → test path works. Replace them with real recordings.\n\n")
    doc += (f"Written by `ml/finetune.py` on {time.strftime('%Y-%m-%d')}. {len(files)} recordings, split by recording: "
            f"train {sum(v == 0 for v in split.values())}, validation {sum(v == 1 for v in split.values())}, test {sum(v == 2 for v in split.values())}"
            f" ({len(Xte)} test windows of 10 s, every 2 s). Fine-tuning took {time.time() - t0:.0f} s.\n\n")
    doc += "| test recordings | trained on simulation only | fine-tuned on these recordings |\n|---|---|---|\n"
    for k in rows:
        f = lambda r: (f"{100 * r[k]:.1f} %" if k != "windows" else str(r[k])) if k in r else "-"
        doc += f"| {k.replace('_', ' ')} | {f(rb)} | {f(rf)} |\n"
    missing = [lab for lab in LABELS if sum(os.path.basename(f).startswith(lab + "_") for f in files) < 3]
    if missing:
        doc += f"\nFewer than 3 recordings of: {', '.join(missing)}. Those went to training only, so they are not in the test.\n"
    open(a.results, "w").write(doc)
    print(doc)


if __name__ == "__main__":
    main()
