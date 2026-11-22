"""The Wi-Fi network, live: feed it CSI packets as they arrive, ask it what it hears.

    venv/bin/python ml/infer.py              listen on UDP 5005 and print what the network says, once a second
    venv/bin/python ml/infer.py --bench      time one reading (window + network) on this computer

pi/rover/web.py uses LiveNet for the remote's "Wi-Fi neural network" view. A reading needs 10 s of packets; packets
lost on the way only thin the bins (csi_window.to_window holds the last value across a gap). The model is
ml/models/csi_nn_real.npz when it exists (fine-tuned on this rover's recordings), else ml/models/csi_nn.npz.
"""
import argparse
import os
import socket
import sys
import time
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import csi_window as cw  # noqa: E402
from net import CsiNet  # noqa: E402

FREQ_ORDER = np.argsort([i if i < 32 else i - 64 for i in cw.LLTF_USED], kind="stable")

def default_model():
    real = os.path.join(HERE, "models", "csi_nn_real.npz")
    return real if os.path.exists(real) else os.path.join(HERE, "models", "csi_nn.npz")


class LiveNet:
    def __init__(self, model=None):
        self.path = model or default_model()
        self.net = CsiNet.load(self.path)
        self.threshold = float(self.net.meta.get("person_threshold", 0.5))
        self.t, self.a = deque(), deque()

    def reset(self):
        self.t.clear(); self.a.clear()

    def push(self, t, amp):
        self.t.append(float(t)); self.a.append(np.asarray(amp, np.float32))
        while self.t and self.t[0] < t - cw.SECONDS - 1.0:
            self.t.popleft(); self.a.popleft()

    def pps(self, now):
        return sum(1 for x in self.t if x > now - 1.0)

    def bars(self, now, span=0.5):
        """The 51 amplitudes averaged over the last `span` s, for drawing, in frequency order (-26..-1, +2..+26; the
        ESP32's buffer has the positive half first); None before any packet."""
        recent = [a for x, a in zip(self.t, self.a) if x > now - span]
        return np.mean(recent, axis=0)[FREQ_ORDER] if recent else None

    def read(self, now):
        """{'ready': False, 'heard_s'} until 10 s are in; then P(person), the decision and P(moving). No breathing
        rate: through a wall it is right too rarely to show (ml/results/synthetic.md)."""
        heard = (now - self.t[0]) if self.t else 0.0
        W = cw.to_window(np.array(self.t), np.array(self.a), now) if heard >= cw.SECONDS - 0.05 else None
        if W is None:
            return {"ready": False, "heard_s": round(min(heard, cw.SECONDS), 1)}
        x = cw.normalise(W)[None]
        p = self.net.predict(x)
        person, moving = float(p["person"][0, 1]), float(p["moving"][0, 1])
        return {"ready": True, "person": round(person, 3), "is_person": person > self.threshold, "threshold": round(self.threshold, 3),
                "moving": round(moving, 3)}


def bench(n=200):
    sys.path.insert(0, HERE)
    import json
    import simulate_csi as S
    p = json.load(open(os.path.join(HERE, "data", "people.json")))["people"][0]
    ta, iq, _ = S.packets(np.random.default_rng(0), p, "still", cw.SECONDS + 1)
    live = LiveNet()
    for t, a in zip(ta, np.hypot(iq[..., 0], iq[..., 1])):
        live.push(t, a)
    live.read(ta[-1])
    t0 = time.perf_counter()
    for _ in range(n):
        live.read(ta[-1])
    ms = (time.perf_counter() - t0) / n * 1000
    print(f"{os.path.basename(live.path)}: one reading (10 s window + network) takes {ms:.1f} ms on this computer"
          f" → up to {1000 / ms:.0f} readings/s")
    return ms


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bench", action="store_true")
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--model")
    a = ap.parse_args()
    if a.bench:
        bench(); return
    from csi import parse_udp
    live = LiveNet(a.model)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", a.port)); sock.settimeout(0.1)
    print(f"{os.path.basename(live.path)} listening on UDP {a.port}; PERSON above P = {live.threshold:.2f}")
    last = time.time()
    while True:
        try:
            rec = parse_udp(sock.recvfrom(4096)[0])
            if rec is not None:
                live.push(time.time(), rec["amp"])
        except socket.timeout:
            pass
        now = time.time()
        if now - last >= 1.0:
            last = now
            r = live.read(now)
            if not r["ready"]:
                print(f"{live.pps(now):4d} packets/s  listening… {r['heard_s']:.0f} of 10 s")
            else:
                said = "PERSON" if r["is_person"] else "no one"
                extra = (" moving" if r["moving"] >= 0.5 else " still") if r["is_person"] else ""
                print(f"{live.pps(now):4d} packets/s  {said:6s} P {r['person']:.2f}{extra}")


if __name__ == "__main__":
    main()
