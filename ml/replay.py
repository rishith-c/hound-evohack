"""Simulated people as real packets: for running the live view and the recorder without the rover.

    python ml/replay.py --kind moving                     send to UDP 127.0.0.1:5005 at 100 packets/s, in the exact
                                                          format csi_rx_udp uses, until stopped
    python ml/replay.py --kind still --person 812 --seconds 60
    python ml/replay.py --record /tmp/rec --n 3           write simulated recordings in ml/record.py's format (3 of
                                                          each label, one simulated room), to try ml/finetune.py

People come from ml/data/people.json; by default ones in the test split, which the network never trained on.
"""
import argparse
import json
import os
import socket
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import csi_window as cw  # noqa: E402
import simulate_csi as S  # noqa: E402
from record import LABELS  # noqa: E402
from train import split_of  # noqa: E402


def test_people():
    ppl = json.load(open(os.path.join(HERE, "data", "people.json")))["people"]
    return [p for p in ppl if split_of(p["id"]) == 2]


def pick(rng, person=None):
    ppl = json.load(open(os.path.join(HERE, "data", "people.json")))["people"]
    return ppl[person] if person is not None else test_people()[rng.integers(len(test_people()))]


def write_recordings(out, n, seed=0, seconds=40.0):
    """n recordings of each label in one simulated room, saved like ml/record.py saves real ones."""
    rng = np.random.default_rng(seed)
    static = S.room(rng)
    os.makedirs(out, exist_ok=True)
    paths = []
    for lab in LABELS:
        for i in range(n):
            p = None if lab == "empty" else pick(rng)
            ta, iq, f = S.packets(rng, p, lab, seconds, static=static)
            path = os.path.join(out, f"{lab}_20000101-{i:06d}.npz")
            np.savez_compressed(path, t=ta, amp=np.hypot(iq[..., 0], iq[..., 1]).astype(np.float32),
                                rssi=np.full(len(ta), -50, np.int8), seq=np.arange(len(ta), dtype=np.uint16), label=lab,
                                note=f"simulated: person {p['id'] if p else '-'}", simulated=True)
            paths.append(path)
    return paths


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kind", choices=LABELS, default="still")
    ap.add_argument("--person", type=int)
    ap.add_argument("--seconds", type=float, default=0, help="0 = until stopped")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--record", help="write simulated recordings here instead of sending")
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    if a.record:
        for p in write_recordings(a.record, a.n, a.seed):
            print("wrote", p)
        return
    rng = np.random.default_rng(a.seed)
    p = None if a.kind == "empty" else pick(rng, a.person)
    static = S.room(rng)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"sending {a.kind}" + (f" (Blender person {p['id']}, {p['posture']}, {p['y'] - 0.3:.1f} m behind the wall)" if p else "")
          + f" to {a.host}:{a.port}, 100 packets/s")
    seq, t_start, sent = 0, time.time(), 0.0
    while not a.seconds or sent < a.seconds:
        ta, iq, f = S.packets(rng, p, a.kind, 10.0, static=static)        # 10 s at a time; the body moves on
        for t, q in zip(ta - ta[0] + sent, iq):
            wait = t_start + t - time.time()
            if wait > 0:
                time.sleep(wait)
            sock.sendto(cw.encode_packet(q.astype(np.int8), seq=seq), (a.host, a.port))
            seq += 1
        sent += 10.0


if __name__ == "__main__":
    main()
