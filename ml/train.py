"""Train the Wi-Fi network on the simulated Blender people.

    python ml/train.py                                   → ml/models/csi_nn.npz, ml/results/train_log.json
    python ml/train.py --data ml/data/synth_clean.npz --out ml/models/csi_nn_clean.npz      (ablation)

The split is by person, never by window: every window of one Blender person (and every empty room) lands in exactly
one of train (70 %), validation (15 %) or test (15 %), so the test score is on people the network never saw.
Early stopping on validation loss; the best epoch's weights are kept.
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
from net import Adam, CsiNet  # noqa: E402


def split_of(group):
    """0 train, 1 validation, 2 test, fixed by the person (or empty room) a window came from."""
    h = (np.asarray(group, np.int64) * 2654435761) % 2 ** 32 % 20
    return np.where(h < 14, 0, np.where(h < 17, 1, 2))


def load(path):
    d = np.load(path)
    X = cw.normalise(d["X"].astype(np.float32))
    y = {"person": d["presence"].astype(np.int64), "moving": d["moving"].astype(np.int64), "zone": d["zone"].astype(np.int64)}
    return X, y, {k: d[k] for k in d.files if k not in ("X",)}


def take(y, m):
    return {k: v[m] for k, v in y.items()}


def batches(n, size, rng):
    idx = rng.permutation(n)
    for i in range(0, n, size):
        yield idx[i:i + size]


def balance(y):
    """Weight per class, so each class counts the same in the loss whatever its share of the windows."""
    out = {}
    for k, v in y.items():
        c = np.bincount(v[v >= 0], minlength=1).astype(float)
        out[k] = np.where(c > 0, c.sum() / np.maximum(c, 1) / len(c), 0.0)
    return out


def evaluate_loss(net, X, y, cw=None):
    tot, n = 0.0, 0
    for i in range(0, len(X), 256):
        sl = slice(i, i + 256)
        tot += net.loss(X[sl], take(y, sl), cw) * len(X[sl]); n += len(X[sl])
    return tot / n


def person_threshold(net, Xv, yv, false_alarm=0.10):
    """The P(person) above which the rover says PERSON: set so that at most `false_alarm` of the validation empty
    rooms (fans included) would be called a person."""
    p = net.predict(Xv)["person"][:, 1]
    return float(np.quantile(p[yv["person"] == 0], 1 - false_alarm))


def accuracy(net, X, y):
    out = {}
    for name, prob in net.predict(X).items():
        m = y[name] >= 0
        out[name] = float((prob[m].argmax(1) == y[name][m]).mean())
    return out


def train(X, y, Xv, yv, seed=0, epochs=40, patience=6, lr=2e-3, batch=64, net=None, log=print):
    rng = np.random.default_rng(seed)
    net = net or CsiNet(seed=seed)
    opt = Adam(net.params(), lr=lr)
    cw = balance(y)
    best, best_w, bad, hist = np.inf, None, 0, []
    for ep in range(epochs):
        t0, tl, n = time.time(), 0.0, 0
        for b in batches(len(X), batch, rng):
            xb = X[b].copy()
            flip = rng.random(len(b)) < 0.5                  # breathing and walking backwards in time are still that
            xb[flip] = xb[flip, :, ::-1]
            tl += net.loss(xb, take(y, b), cw) * len(b); n += len(b)
            opt.step(net.grads())
        vl = evaluate_loss(net, Xv, yv, cw)
        va = accuracy(net, Xv, yv)
        hist.append({"epoch": ep + 1, "train_loss": round(tl / n, 4), "val_loss": round(vl, 4), **{f"val_{k}": round(v, 4) for k, v in va.items()},
                     "seconds": round(time.time() - t0, 1)})
        log(f"epoch {ep + 1:2d}  train {tl / n:.3f}  val {vl:.3f}  " + "  ".join(f"{k} {v:.3f}" for k, v in va.items()) + f"  {time.time() - t0:.1f} s")
        if vl < best - 1e-4:
            best, best_w, bad = vl, [p.copy() for p in net.params()], 0
        else:
            bad += 1
            if bad == 3:
                opt.lr *= 0.5
            if bad >= patience:
                break
    for p, w in zip(net.params(), best_w):
        p[...] = w
    return net, hist


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.path.join(HERE, "data", "synth.npz"))
    ap.add_argument("--out", default=os.path.join(HERE, "models", "csi_nn.npz"))
    ap.add_argument("--log", default=os.path.join(HERE, "results", "train_log.json"))
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--zone", action="store_true", help="also train a left/centre/right head (the experiment in ml/README.md)")
    a = ap.parse_args()
    X, y, meta = load(a.data)
    s = split_of(meta["group"])
    print(f"{a.data}: {len(X)} windows; train {int((s == 0).sum())}, validation {int((s == 1).sum())}, test {int((s == 2).sum())} (split by person)")
    net = CsiNet(seed=a.seed, heads=("person", "moving", "zone") if a.zone else ("person", "moving"))
    print(f"network: {net.n_params()} parameters, heads {net.head_names}")
    t0 = time.time()
    net, hist = train(X[s == 0], take(y, s == 0), X[s == 1], take(y, s == 1), seed=a.seed, epochs=a.epochs, net=net)
    best = min(hist, key=lambda h: h["val_loss"])
    thr = person_threshold(net, X[s == 1], take(y, s == 1))
    print(f"person threshold {thr:.3f} (10 % false alarms on validation empty rooms)")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    net.save(a.out, person_threshold=thr, data=os.path.relpath(a.data, os.path.dirname(HERE)), data_seed=int(meta["seed"]), clean=bool(meta["clean"]),
             windows={"train": int((s == 0).sum()), "val": int((s == 1).sum()), "test": int((s == 2).sum())},
             best_epoch=best["epoch"], trained=time.strftime("%Y-%m-%d"), seconds=round(time.time() - t0))
    os.makedirs(os.path.dirname(a.log), exist_ok=True)
    json.dump({"data": os.path.relpath(a.data, os.path.dirname(HERE)), "params": net.n_params(), "epochs": hist}, open(a.log, "w"), indent=1)
    print(f"best epoch {best['epoch']} (val loss {best['val_loss']}); saved {a.out} in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
