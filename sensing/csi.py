"""Host-side WiFi CSI: frame parsing, amplitude, and breathing.

Complements the radar rather than replacing it. The radar is monostatic — it
bounces off a target from one side and gives range. CSI is bistatic — the person
stands between transmitter and receiver and distorts the signal passing through,
which gives no range at all but is the better vital-sign detector, and it does
not need to be pointed anywhere.

Wire format from csi_rx.ino, little-endian:

    A5 5A | seq u16 | rssi i8 | len u8 | len bytes of raw CSI

The CSI buffer is pairs of signed bytes, (imaginary, real), one pair per
subcarrier. **Amplitude only.** ESP32 CSI phase carries a random per-packet
carrier and sampling frequency offset, so it cannot be used coherently across
packets; every attempt to do so measures the offset, not the room.
"""

from __future__ import annotations

import numpy as np

HEAD = b"\xa5\x5a"
MAX_CSI = 256


def amplitudes(raw: bytes) -> np.ndarray:
    """Per-subcarrier magnitude from interleaved (imag, real) int8 pairs."""
    n = len(raw) // 2 * 2
    if n < 2:
        return np.zeros(0)
    v = np.frombuffer(raw[:n], dtype=np.int8).astype(float)
    imag, real = v[0::2], v[1::2]
    return np.hypot(real, imag)


# ── Hound's UDP packets (firmware/csi_rx_udp) ───────────────────────────────────────────────────────────────
UDP_MAGIC = b"HC"
LLTF_BYTES = 128                                   # the LLTF block: 64 subcarriers × (imag, real), always first
# ESP32 LLTF order is 0..31 then −32..−1, and ±1..±26 carry signal. +1 is left out: it sits in the buffer's first 4 bytes,
# which the radio marks invalid on some frames (first_word_invalid). csi_rx_udp zeroes them, and a subcarrier that is
# sometimes 0 and sometimes real is a square wave to every variance and periodicity test downstream.
LLTF_USED = list(range(2, 27)) + list(range(38, 64))


def parse_udp(data: bytes) -> dict | None:
    """One csi_rx_udp packet: 'H' 'C' | node u8 | seq u16 | rssi i8 | n u8 | n bytes of (imag, real) int8.
    Returns node, seq, rssi and the 51 used LLTF subcarrier amplitudes; None if it is not such a packet."""
    if len(data) < 7 or data[:2] != UDP_MAGIC:
        return None
    n = data[6]
    if n < LLTF_BYTES or len(data) < 7 + n:
        return None
    amp = amplitudes(data[7:7 + LLTF_BYTES])
    return {"node": data[2], "seq": int.from_bytes(data[3:5], "little"),
            "rssi": int.from_bytes(data[5:6], "little", signed=True), "amp": amp[LLTF_USED]}


class FrameReader:
    """Feed it bytes, get back CSI records. Resyncs on garbage."""

    MAX_BUF = 8192

    def __init__(self):
        self.buf = bytearray()
        self.dropped = 0

    def feed(self, data: bytes) -> list[dict]:
        self.buf.extend(data)
        if len(self.buf) > self.MAX_BUF:
            del self.buf[: -self.MAX_BUF]
            self.dropped += 1

        out = []
        while True:
            i = self.buf.find(HEAD)
            if i < 0:
                if len(self.buf) > 1:
                    del self.buf[:-1]
                break
            if i:
                del self.buf[:i]
            if len(self.buf) < 6:
                break

            seq = int.from_bytes(self.buf[2:4], "little")
            rssi = int.from_bytes(self.buf[4:5], "little", signed=True)
            ln = self.buf[5]
            # CSI is (imag, real) pairs, so the length must be even. A
            # `> MAX_CSI` test can never fire here -- a uint8 tops out at 255
            # and MAX_CSI is 256 -- so parity is the check that actually
            # catches a header found in noise.
            if ln == 0 or ln % 2 or ln > MAX_CSI:
                del self.buf[:2]
                self.dropped += 1
                continue
            if len(self.buf) < 6 + ln:
                break

            raw = bytes(self.buf[6:6 + ln])
            del self.buf[:6 + ln]
            amp = amplitudes(raw)
            out.append({"seq": seq, "rssi": rssi, "len": ln,
                        "amp": amp, "n_sub": len(amp)})
        return out


class CsiTracker:
    """Rolling per-subcarrier amplitude, and the breathing hidden in it.

    Most subcarriers see nothing useful at any given moment -- a target sits in
    a null for some and a peak for others. So rank by in-band variance and keep
    only the best few, rather than averaging the informative ones away.
    """

    def __init__(self, fs: float = 20.0, window_s: float = 30.0, keep: int = 8):
        self.fs = fs
        self.maxlen = int(fs * window_s)
        self.keep = keep
        self.hist: dict[int, list[float]] = {}
        self.rssi: list[float] = []

    def push(self, rec: dict) -> None:
        for i, a in enumerate(rec["amp"]):
            h = self.hist.setdefault(i, [])
            h.append(float(a))
            if len(h) > self.maxlen:
                del h[: len(h) - self.maxlen]
        self.rssi.append(float(rec["rssi"]))
        if len(self.rssi) > self.maxlen:
            del self.rssi[: len(self.rssi) - self.maxlen]

    def reset(self) -> None:
        self.hist.clear()
        self.rssi.clear()

    def fill(self) -> float:
        if not self.hist:
            return 0.0
        return min(len(h) for h in self.hist.values()) / self.maxlen

    def best_subcarriers(self) -> list[int]:
        """The subcarriers carrying the most variation, most informative first."""
        scored = [(float(np.var(np.asarray(h))), i)
                  for i, h in self.hist.items() if len(h) >= 40]
        scored.sort(reverse=True)
        return [i for _, i in scored[: self.keep]]

    def estimate(self) -> dict:
        """Breathing rate from the combined best subcarriers."""
        from vitals import estimate_rate

        idx = self.best_subcarriers()
        if not idx:
            return {"bpm": 0.0, "confidence": 0.0, "subcarriers": 0,
                    "fill": round(self.fill(), 2)}

        n = min(len(self.hist[i]) for i in idx)
        M = np.array([self.hist[i][-n:] for i in idx], dtype=float)

        # Normalise each subcarrier before combining. They respond with
        # arbitrary sign and scale, so a plain sum can cancel the very signal
        # it is meant to reinforce.
        M = M - M.mean(axis=1, keepdims=True)
        sd = M.std(axis=1, keepdims=True)
        M = M / np.where(sd < 1e-9, 1.0, sd)

        # First principal component: the one pattern all of them share.
        try:
            u, s, vt = np.linalg.svd(M, full_matrices=False)
            combined = vt[0] * s[0]
        except np.linalg.LinAlgError:
            combined = M.mean(axis=0)

        r = estimate_rate(combined, self.fs)
        return {**r, "subcarriers": len(idx), "fill": round(self.fill(), 2),
                "rssi": round(float(np.mean(self.rssi)), 1) if self.rssi else 0.0}
