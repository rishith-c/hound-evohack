"""Record labelled Wi-Fi CSI on the rover, for fine-tuning the network on the real room.

    cd ~/rover && venv/bin/python ml/record.py --label empty --seconds 60
    venv/bin/python ml/record.py --label still --seconds 60        (someone sits or lies still behind the wall)
    venv/bin/python ml/record.py --label moving --seconds 60       (someone walks around behind the wall)

Listens on UDP 5005 like sensing/station.py (stop the remote's Wi-Fi view first: one program per port) and saves
every packet, not windows: ml/data/real/<label>_<YYYYmmdd-HHMMSS>.npz with t, amp[n, 51], rssi, seq. Windows are cut
later by finetune.py, so a recording is never split across training and testing. Prints packets per second and
warns under 50 (csi_rx_udp sends ~100). HOUND must not drive during a recording.
"""
import argparse
import os
import socket
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import csi_window  # noqa: E402,F401  (puts sensing/ on the path)
from csi import parse_udp  # noqa: E402

LABELS = ("empty", "still", "moving")
REAL = os.path.join(HERE, "data", "real")


def record(sock, seconds, out=print, clock=time.time):
    t, amp, rssi, seq = [], [], [], []
    t0 = last = clock()
    n_last = 0
    while clock() - t0 < seconds:
        try:
            data, _ = sock.recvfrom(4096)
        except socket.timeout:
            data = None
        now = clock()
        rec = parse_udp(data) if data else None
        if rec is not None:
            t.append(now); amp.append(rec["amp"]); rssi.append(rec["rssi"]); seq.append(rec["seq"])
        if now - last >= 1.0:
            pps = (len(t) - n_last) / (now - last)
            out(f"{now - t0:5.0f} s  {pps:5.0f} packets/s" + ("   ← under 50: is ESP32 #2 on and close enough?" if pps < 50 else ""))
            last, n_last = now, len(t)
    return np.array(t), np.array(amp, np.float32).reshape(-1, csi_window.N_SUB), np.array(rssi, np.int8), np.array(seq, np.uint16)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--label", required=True, choices=LABELS)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--note", default="", help="where the person was, the wall, anything worth keeping")
    a = ap.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", a.port))
    sock.settimeout(0.2)
    print(f"recording '{a.label}' for {a.seconds:.0f} s on UDP {a.port}")
    t, amp, rssi, seq = record(sock, a.seconds)
    if len(t) < 0.5 * csi_window.HZ * a.seconds:
        sys.exit(f"only {len(t)} packets: not saved")
    os.makedirs(REAL, exist_ok=True)
    path = os.path.join(REAL, f"{a.label}_{time.strftime('%Y%m%d-%H%M%S')}.npz")
    np.savez_compressed(path, t=t, amp=amp, rssi=rssi, seq=seq, label=a.label, note=a.note, simulated=False)
    print(f"saved {path}: {len(t)} packets, {len(t) / (t[-1] - t[0]):.0f}/s")


if __name__ == "__main__":
    main()
