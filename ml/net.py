"""HOUND's Wi-Fi network: a small 1-D convolutional network over a 10 s window of CSI, in plain NumPy.

NumPy because the network has to run on the rover's Raspberry Pi 4, where NumPy is already installed (setup_pi.sh)
and PyTorch is a 700 MB install; and because every gradient here is written out, tests/test_ml.py checks each one
against finite differences.

    input   (52, 200)   51 subcarriers (% change) + the motion row, 20 samples/s for 10 s
    conv    52 → 24, 9 taps, ReLU, average pool 4      (0.45 s filters; 5 samples/s after the pool)
    conv    24 → 24, 9 taps, ReLU, average pool 2      (sees ~2 s: one breath)
    conv    24 → 24, 9 taps, ReLU                      (sees ~5 s)
    pool    mean and max over time → 48
    dense   48 → 32, ReLU
    heads   person (2) · moving (2)    [· zone (3: left, centre, right), only with --zone: see ml/README.md]

The moving (and zone) heads only learn from windows that have a person in them; on the rover they are only shown
when the person head says someone is there.
"""
import json

import numpy as np

from csi_window import N_IN, N_T

HEAD_SIZES = {"person": 2, "moving": 2, "zone": 3}


class Conv1D:
    def __init__(self, cin, cout, k, rng):
        self.k = k
        self.W = (rng.standard_normal((cin * k, cout)) * np.sqrt(2 / (cin * k))).astype(np.float32)
        self.b = np.zeros(cout, np.float32)

    def params(self):
        return [self.W, self.b]

    def forward(self, x):                                     # x (N, C, T) → (N, F, T - k + 1)
        N, C, T = x.shape
        cols = np.lib.stride_tricks.sliding_window_view(x, self.k, axis=2)      # (N, C, T', k)
        cols = cols.transpose(0, 2, 1, 3).reshape(N * (T - self.k + 1), C * self.k)
        self.cache = (cols, x.shape)
        return (cols @ self.W + self.b).reshape(N, T - self.k + 1, -1).transpose(0, 2, 1)

    def backward(self, g):
        cols, (N, C, T) = self.cache
        Tp = T - self.k + 1
        g2 = g.transpose(0, 2, 1).reshape(N * Tp, -1)
        self.grads = [cols.T @ g2, g2.sum(0)]
        dcols = (g2 @ self.W.T).reshape(N, Tp, C, self.k)
        dx = np.zeros((N, C, T), np.float32)
        for j in range(self.k):
            dx[:, :, j:j + Tp] += dcols[:, :, :, j].transpose(0, 2, 1)
        return dx


class Dense:
    def __init__(self, cin, cout, rng, gain=2.0):
        self.W = (rng.standard_normal((cin, cout)) * np.sqrt(gain / cin)).astype(np.float32)
        self.b = np.zeros(cout, np.float32)

    def params(self):
        return [self.W, self.b]

    def forward(self, x):
        self.x = x
        return x @ self.W + self.b

    def backward(self, g):
        self.grads = [self.x.T @ g, g.sum(0)]
        return g @ self.W.T


class ReLU:
    def forward(self, x):
        self.m = x > 0
        return x * self.m

    def backward(self, g):
        return g * self.m


class AvgPool:
    def __init__(self, p):
        self.p = p

    def forward(self, x):
        N, C, T = x.shape
        self.T = T
        T2 = T // self.p
        return x[:, :, :T2 * self.p].reshape(N, C, T2, self.p).mean(-1)

    def backward(self, g):
        N, C, T2 = g.shape
        dx = np.zeros((N, C, self.T), np.float32)
        dx[:, :, :T2 * self.p] = np.repeat(g / self.p, self.p, axis=2)
        return dx


class MeanMax:
    """(N, C, T) → (N, 2C): each filter's mean and its peak over the window."""
    def forward(self, x):
        self.shape = x.shape
        self.arg = x.argmax(axis=2)
        return np.concatenate([x.mean(axis=2), x.max(axis=2)], axis=1)

    def backward(self, g):
        N, C, T = self.shape
        dx = np.repeat(g[:, :C, None] / T, T, axis=2).astype(np.float32)
        np.add.at(dx, (np.arange(N)[:, None], np.arange(C)[None], self.arg), g[:, C:])
        return dx


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class CsiNet:
    def __init__(self, seed=0, width=24, hidden=32, heads=("person", "moving")):
        rng = np.random.default_rng(seed)
        self.head_names = tuple(heads)
        self.config = {"seed": seed, "width": width, "hidden": hidden, "heads": list(heads), "n_in": N_IN, "n_t": N_T}
        w = width
        self.body = [Conv1D(N_IN, w, 9, rng), ReLU(), AvgPool(4),
                     Conv1D(w, w, 9, rng), ReLU(), AvgPool(2),
                     Conv1D(w, w, 9, rng), ReLU(), MeanMax(),
                     Dense(2 * w, hidden, rng), ReLU()]
        self.heads = [Dense(hidden, HEAD_SIZES[h], rng, gain=1.0) for h in heads]
        self.layers = [l for l in self.body + self.heads if hasattr(l, "params")]

    def params(self):
        return [p for l in self.layers for p in l.params()]

    def grads(self):
        return [g for l in self.layers for g in l.grads]

    def n_params(self):
        return int(sum(p.size for p in self.params()))

    def forward(self, x):
        """x (N, 52, 200), already normalised → [logits per head]."""
        h = x.astype(np.float32)
        for l in self.body:
            h = l.forward(h)
        return [hd.forward(h) for hd in self.heads]

    def loss(self, x, y, class_weights=None):
        """Cross-entropy summed over the heads; y = {head: labels}, -1 = no label (left out of that head);
        class_weights = {head: weight per class} (so a rare class counts as much as a common one).
        Returns the loss and fills every layer's .grads."""
        outs = self.forward(x)
        total, gh = 0.0, None
        for name, o, hd in zip(self.head_names, outs, self.heads):
            t = y[name]
            m = t >= 0
            p = softmax(o)
            g = np.zeros_like(o)
            if m.any():
                tt = t[m].astype(int)
                cw = np.asarray((class_weights or {}).get(name, np.ones(o.shape[1])), np.float32)[tt]
                cw = cw / cw.sum()
                total += float(-(cw * np.log(p[m, tt] + 1e-9)).sum())
                gm = p[m].copy()
                gm[np.arange(len(tt)), tt] -= 1
                g[m] = gm * cw[:, None]
            d = hd.backward(g.astype(np.float32))
            gh = d if gh is None else gh + d
        for l in reversed(self.body):
            gh = l.backward(gh)
        return total

    def predict(self, x, batch=256):
        """Probabilities per head: {'person': (N, 2), 'moving': (N, 2)[, 'zone': (N, 3)]}."""
        out = {n: [] for n in self.head_names}
        for i in range(0, len(x), batch):
            for n, o in zip(self.head_names, self.forward(x[i:i + batch])):
                out[n].append(softmax(o))
        return {n: np.concatenate(v) for n, v in out.items()}

    def save(self, path, **meta):
        np.savez(path, *self.params(), config=json.dumps(self.config), meta=json.dumps(meta))

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=False)
        net = cls(**{k: v for k, v in json.loads(str(z["config"])).items() if k in ("seed", "width", "hidden", "heads")})
        for p, k in zip(net.params(), [f"arr_{i}" for i in range(len(net.params()))]):
            p[...] = z[k]
        net.meta = json.loads(str(z["meta"]))
        return net


class Adam:
    def __init__(self, params, lr=2e-3, b1=0.9, b2=0.999, wd=1e-4):
        self.p, self.lr, self.b1, self.b2, self.wd, self.t = params, lr, b1, b2, wd, 0
        self.m = [np.zeros_like(p) for p in params]
        self.v = [np.zeros_like(p) for p in params]

    def step(self, grads):
        self.t += 1
        for p, g, m, v in zip(self.p, grads, self.m, self.v):
            g = g + self.wd * p if p.ndim > 1 else g
            m *= self.b1; m += (1 - self.b1) * g
            v *= self.b2; v += (1 - self.b2) * g * g
            mh, vh = m / (1 - self.b1 ** self.t), v / (1 - self.b2 ** self.t)
            p -= (self.lr * mh / (np.sqrt(vh) + 1e-8)).astype(p.dtype)
