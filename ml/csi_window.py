"""One path from Wi-Fi packets to the network's input, shared by the simulator, the recorder, fine-tuning and the
live view, so the network never sees data shaped one way in training and another way on the rover.

ESP32 #3 sends ~100 CSI packets/s (firmware/csi_rx_udp). The LLTF has 52 data subcarriers (±1..±26); +1 is left out
because the radio sometimes marks the buffer's first word invalid (sensing/csi.py), so 51 are used. Phase is not
usable on the ESP32 (random per packet), so everything here is amplitude.

    packets (t, 51 amplitudes)  →  to_window: AGC steps out; 10 s at 20 bins/s, the mean of the packets in each
                                   bin, plus a motion row from the packets inside each bin  →  (52, 200)
    (52, 200)  →  normalise: each subcarrier as % change from its mean  →  the network's input
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SENSING = os.path.join(os.path.dirname(HERE), "sensing")
if os.path.isdir(SENSING) and SENSING not in sys.path:
    sys.path.insert(0, SENSING)
from csi import LLTF_BYTES, LLTF_USED, UDP_MAGIC  # noqa: E402

N_SUB = len(LLTF_USED)                              # 51
SECONDS, HZ = 10.0, 20                              # window: 10 s holds at least one slow breath (6 /min)
N_T = int(SECONDS * HZ)                             # 200
MAX_EMPTY = 0.35                                    # a window with more empty bins than this is not used
N_IN = N_SUB + 1                                    # the network's input rows: 51 subcarriers + the motion row
AGC_STEP = 0.04                                     # a jump in the shared gain bigger than 4 % between packets


def remove_agc_steps(t, amp):
    """The ESP32's AGC changes the gain of every subcarrier at once, in steps. A person changes the subcarriers
    almost together too (the body's echo is only ~10 ns behind the direct path, so it hardly varies across 16 MHz),
    so the shared gain cannot simply be divided out without dividing out the person. A body moves the shared level
    smoothly; the AGC jumps from one packet to the next. Only the jumps are removed."""
    order = np.argsort(t, kind="stable")
    t, amp = t[order], amp[order]
    g = np.log(np.maximum(amp.mean(axis=1), 1e-6))
    d = np.diff(g, prepend=g[:1])
    steps = np.cumsum(np.where(np.abs(d) > AGC_STEP, d, 0.0))
    return t, amp / np.exp(steps)[:, None]


def to_window(t, amp, t_end, seconds=SECONDS, hz=HZ):
    """Packets (arrival time t[n], amplitudes amp[n, 51]) → (52, seconds·hz) float32, AGC steps removed:
    rows 0-50  the mean amplitude of each subcarrier over the packets in each bin;
    row 51     motion: how much the packets inside each bin differ from each other (% of each subcarrier's level,
               mean over subcarriers). Walking changes the reflected path by ~2 m/s, a flicker of ~16 Hz that 20
               bins/s would average away; this row keeps it.
    Empty bins (dropped packets) hold the last value; returns None when too many bins are empty."""
    n = int(round(seconds * hz))
    t, amp = remove_agc_steps(np.asarray(t, float), np.asarray(amp, float))
    k = np.floor((t - (t_end - seconds)) * hz).astype(int)
    ok = (k >= 0) & (k < n)
    k, a = k[ok], amp[ok]
    if len(a) == 0:
        return None
    rel = a / np.maximum(a.mean(axis=0, keepdims=True), 1e-6)
    s, s1, sq = (np.zeros((n, amp.shape[1])) for _ in range(3))
    c = np.zeros(n)
    np.add.at(s, k, a)
    np.add.at(s1, k, rel)
    np.add.at(sq, k, rel * rel)
    np.add.at(c, k, 1)
    have = c > 0
    if have.mean() < 1 - MAX_EMPTY:
        return None
    ch = c[have, None]
    s[have] /= ch
    m = s1[have] / ch
    var = np.clip(sq[have] / ch - m * m, 0, None) * ch / np.maximum(ch - 1, 1)
    motion = np.zeros(n)
    motion[have] = 100 * np.sqrt(var).mean(axis=1) * (c[have] > 1)
    idx = np.where(have, np.arange(n), 0)
    np.maximum.accumulate(idx, out=idx)              # forward fill...
    s, motion = s[idx], motion[idx]
    first = np.argmax(have)
    s[:first], motion[:first] = s[first], motion[first]   # ...and the start from the first filled bin
    return np.vstack([s.T, motion[None]]).astype(np.float32)


def normalise(W):
    """(…, 52, T) window → the network's input: each subcarrier as % change from its own mean over the window, and
    the motion row in %, less 1 % (the receiver's own packet-to-packet noise)."""
    W = np.asarray(W, np.float32)
    A, M = W[..., :N_SUB, :], W[..., N_SUB:, :]
    A = A / np.maximum(A.mean(axis=-1, keepdims=True), 1e-6) - 1
    return np.concatenate([np.clip(100 * A, -50, 50), np.clip(M - 1, -5, 50)], axis=-2).astype(np.float32)


def breathing_rate(Wn, hz=HZ, lo=0.12, hi=0.70):
    """Breaths per minute from a normalised window (52, T): the strongest common rhythm across subcarriers (first
    principal component, slow trend removed), its spectral peak in 7-42 /min. Returns (bpm, peak share of band
    power): a low share means there is no clear rhythm."""
    Wn = Wn[:N_SUB]
    tt = np.linspace(-1, 1, Wn.shape[1])
    V = np.vander(tt, 3)                             # slow gain drift bends the window: take out a parabola
    X = Wn - (V @ np.linalg.lstsq(V, Wn.T, rcond=None)[0]).T
    u, s, vt = np.linalg.svd(X, full_matrices=False)
    pc = vt[0] * s[0]
    nfft = 2048                                      # zero padding: 0.6 /min steps
    spec = np.abs(np.fft.rfft(pc * np.hanning(len(pc)), nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / hz)
    band = (f >= lo) & (f <= hi)
    i = np.argmax(np.where(band, spec, 0))
    return float(60 * f[i]), float(spec[i] / max(spec[band].sum(), 1e-12))


# ── packets on the wire (what csi_rx_udp sends): for replaying simulated people into the real receiver code ─────────
def encode_packet(iq, node=2, seq=0, rssi=-50):
    """iq[51, 2] int8 (imag, real) for the used subcarriers → one 'HC' UDP packet that csi.parse_udp reads back."""
    buf = np.zeros((64, 2), np.int8)
    buf[LLTF_USED] = iq
    body = buf.tobytes()
    assert len(body) == LLTF_BYTES
    return UDP_MAGIC + bytes([node]) + int(seq & 0xFFFF).to_bytes(2, "little") + int(rssi).to_bytes(1, "little", signed=True) \
        + bytes([len(body)]) + body
