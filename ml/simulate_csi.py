"""What HOUND's Wi-Fi receiver would record with each Blender person behind the wall: packet by packet, then cut into
the same windows the rover makes.

    python ml/simulate_csi.py                       → ml/data/synth.npz   (from ml/data/people.json)
    python ml/simulate_csi.py --clean --out ml/data/synth_clean.npz     (no ESP32 faults: for the ablation)

The channel on each of the 51 subcarriers is a sum of paths (the same physics as sensing/fresnel.py, at channel 6's
real subcarrier frequencies instead of one wavelength):
  * the direct path ESP32 #2 → ESP32 #3, and 3-8 static room reflections (walls, furniture): random per window, so
    every window is a new room;
  * the body: every surface point Blender sampled is its own reflector, weighted by its area and how squarely it
    faces the link, falling with both path legs and crossing the wall (fresnel.WALL_LOSS). Breathing moves the torso
    points along their normals (4-12 mm peak to peak, 7-30 breaths/min, uneven), the heartbeat by a fraction of a mm,
    and a standing person sways a few mm.
Classes per person: still (breathing only), moving (a standing person walks 0.3-1.0 m/s and bounces inside the
search region; a person lying down moves an arm or a leg, the way someone trapped would), and empty rooms, a third
of them with an oscillating desk fan: a reflector that swings slowly, which looks a lot like breathing.

Then what the ESP32 does to it (left out with --clean): the gain (AGC) jumps now and then and drifts, amplitudes are
int8 I/Q (about 30 counts) with receiver noise, about 1 % per packet as on a real ESP32, 2-15 % of packets are lost plus whole bursts, and packets arrive with jitter.
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import csi_window as cw  # noqa: E402
from geometry import REGION, RX, TX, WALL_Y, zone_of  # noqa: E402
from fresnel import WALL_LOSS  # noqa: E402  (sensing/ is on the path through csi_window)

SUB = np.array([i if i < 32 else i - 64 for i in cw.LLTF_USED])   # subcarrier numbers, -26..26 without 0 and +1
F0, DF, C = 2.437e9, 312.5e3, 299792458.0                         # channel 6 centre, subcarrier spacing
KW = 2 * np.pi * (F0 + SUB * DF) / C                              # wavenumber of each subcarrier, rad/m
PKT_HZ = 100.0                                                    # csi_rx_udp's probe rate
BODY = 0.15                     # fresnel.sensitivity: reflected/direct amplitude of a body at d1·d2 = 1 m²
REF_AREA = 0.30                 # m² of body squarely facing the link that BODY stands for
TX_, RX_ = np.array(TX), np.array(RX)
CLASSES = ("empty", "still", "moving")
# the receiver's own frequency response: a property of the radio, the same in every window
RIPPLE = 1 + 0.1 * np.convolve(np.random.default_rng(3).standard_normal(len(KW) + 6), np.ones(7) / 7, "valid")


def smooth_noise(rng, n, dt, tau):
    """Zero-mean, unit-variance random wander with correlation time tau (first-order low-pass of white noise)."""
    a = np.exp(-dt / tau)
    w = rng.standard_normal(n) * np.sqrt(1 - a * a)
    x = np.empty(n)
    x[0] = rng.standard_normal()
    for i in range(1, n):
        x[i] = a * x[i - 1] + w[i]
    return x


def room(rng):
    """The static channel: direct path plus a few room reflections, as (51,) complex."""
    d0 = np.linalg.norm(RX_ - TX_)
    H = rng.uniform(0.6, 1.0) * np.exp(-1j * KW * d0)
    for _ in range(rng.integers(3, 9)):
        extra = rng.uniform(0.3, 9.0)
        H = H + 0.5 * rng.uniform(0.05, 1.0) / (1 + extra / 3) * np.exp(-1j * (KW * (d0 + extra) + rng.uniform(0, 2 * np.pi)))
    return H


def breathing(rng, t, still):
    """Chest displacement (m) over time: uneven breaths (inhale quicker than exhale), rate wandering ±8 %, plus the
    heartbeat. Returns (displacement, breaths/min)."""
    bpm = rng.uniform(7, 30)
    depth = rng.uniform(4, 12) / 1000                                # peak to peak
    f = bpm / 60 * (1 + 0.08 * smooth_noise(rng, len(t), t[1] - t[0], 8.0))
    ph = 2 * np.pi * np.cumsum(f) * (t[1] - t[0]) + rng.uniform(0, 2 * np.pi)
    shape = np.sin(ph) + 0.25 * np.sin(2 * ph + 0.8)
    d = depth / 2 * shape / np.abs(shape).max()
    hr = rng.uniform(55, 110) / 60
    d += rng.uniform(0.1, 0.4) / 1000 * np.sin(2 * np.pi * hr * t + rng.uniform(0, 6.3)) ** 3
    return d, bpm


def body_channel(rng, p, t, kind):
    """The body's reflections, (len(t), 51) complex, and the label facts (zone at the window's end, breaths/min)."""
    P = np.array(p["points"], float)
    off, z, nrm, area, part = P[:, :2], P[:, 2], P[:, 3:6], P[:, 6], P[:, 7].astype(int)
    n, dt = len(t), t[1] - t[0]
    lying = p["posture"] == "lying"
    cx, cy = np.full(n, p["x"]), np.full(n, p["y"])
    disp = np.zeros((n, len(P), 3))
    d, bpm = breathing(rng, t, kind == "still")
    disp += (part == 0)[None, :, None] * nrm[None] * d[:, None, None]                  # breathing: torso only
    if not lying:                                                                       # standing sway, a few mm
        for ax in (0, 1):
            disp[:, :, ax] += 0.003 * smooth_noise(rng, n, dt, 2.0)[:, None]
    if kind == "moving" and not lying:                                                  # walking
        v, head = rng.uniform(0.3, 1.0), rng.uniform(-np.pi, np.pi)
        (x0, x1), (y0, y1) = REGION
        x, y, vx, vy = p["x"], p["y"], v * np.cos(head), v * np.sin(head)
        for i in range(n):
            x, y = x + vx * dt, y + vy * dt
            if not x0 <= x <= x1: vx, x = -vx, np.clip(x, x0, x1)
            if not y0 <= y <= y1: vy, y = -vy, np.clip(y, y0, y1)
            cx[i], cy[i] = x, y
        step = rng.uniform(1.6, 2.2)                                                    # steps/s
        disp[:, :, 2] += 0.02 * np.sin(2 * np.pi * step * t)[:, None]                  # bob
        side = np.sign(off[:, 0] * -np.sin(head) + off[:, 1] * np.cos(head) + 1e-9)     # left or right of the heading
        swing = 0.15 * np.sin(np.pi * step * t)[:, None] * side[None] * np.isin(part, (2, 3))[None]
        disp[:, :, 0] += swing * np.cos(head)
        disp[:, :, 1] += swing * np.sin(head)
    elif kind == "moving":                                                              # lying: an arm or a leg moves
        limb = np.isin(part, (2, 3)) & (rng.random(len(P)) < 0.5)
        f = rng.uniform(0.4, 2.0)
        on = (smooth_noise(rng, n, dt, 1.5) > -0.3).astype(float)                       # in bursts, not all the time
        a = rng.uniform(0.05, 0.20) * np.sin(2 * np.pi * f * t) * on
        dirn = rng.normal(size=3)
        disp += limb[None, :, None] * a[:, None, None] * (dirn / np.linalg.norm(dirn))[None, None]
    pos = np.stack([cx[:, None] + off[None, :, 0], cy[:, None] + off[None, :, 1], np.broadcast_to(z, (n, len(P)))], -1) + disp
    v1, v2 = pos - TX_, pos - RX_
    d1, d2 = np.linalg.norm(v1, axis=-1), np.linalg.norm(v2, axis=-1)
    bis = -(v1 / d1[..., None] + v2 / d2[..., None]) / 2                                # towards TX and RX
    facing = np.clip(np.einsum("sk,tsk->ts", nrm, bis), 0, None)
    behind = pos[..., 1] > WALL_Y
    amp = BODY * area * facing / REF_AREA / np.maximum(d1 * d2, 0.25) * np.where(behind, WALL_LOSS, 1.0)
    H = np.einsum("ts,tsk->tk", amp, np.exp(-1j * (d1 + d2)[..., None] * KW))
    return H, zone_of(cx[-1]), bpm


def fan_channel(rng, t):
    """An oscillating desk fan somewhere in the room: its head swings ±35° every 6-16 s, the blades flicker."""
    (x0, x1), (y0, y1) = REGION
    c = np.array([rng.uniform(x0 - 1, x1 + 1), rng.uniform(-1.5, y1), rng.uniform(0.3, 1.2)])
    period, r = rng.uniform(6, 16), rng.uniform(0.10, 0.25)
    ang = np.radians(35) * np.sin(2 * np.pi * t / period + rng.uniform(0, 6.3))
    pos = c + r * np.stack([np.sin(ang), np.cos(ang), 0 * ang], -1)
    d = np.linalg.norm(pos - TX_, axis=1) + np.linalg.norm(pos - RX_, axis=1)
    d = d + 0.004 * np.sin(2 * np.pi * rng.uniform(8, 20) * t)                          # blades
    a = rng.uniform(0.02, 0.08) / max(np.linalg.norm(c - TX_) * np.linalg.norm(c - RX_), 0.25) * (WALL_LOSS if c[1] > WALL_Y else 1)
    return a * np.exp(-1j * d[:, None] * KW)


def esp32(rng, H, t, clean=False):
    """(n, 51) complex channel → what csi_rx_udp sends: arrival times and int8 (imag, real), with packets lost."""
    n = len(t)
    if clean:
        g = np.full(n, 30.0 / np.abs(H).mean())
        iq = H * g[:, None]
        return t, np.stack([iq.imag, iq.real], -1)
    g = rng.uniform(0.7, 1.4) * 30.0 / np.abs(H).mean() * np.ones(n)
    g *= 1 + 0.015 * np.sin(2 * np.pi * t / rng.uniform(60, 300) + rng.uniform(0, 6.3))    # slow (thermal) drift, minutes
    for tj in t[0] + np.cumsum(rng.exponential(20.0, 5)):                                   # AGC steps, ~1 per 20 s
        g[t >= tj] *= rng.uniform(0.8, 1.25)
    iq = H * RIPPLE[None] * g[:, None]
    iq = iq + rng.normal(0, 0.15, iq.shape) + 1j * rng.normal(0, 0.15, iq.shape)   # with int8 rounding: ~1 % per packet
    iq = np.clip(np.round(np.stack([iq.imag, iq.real], -1)), -127, 127)
    keep = rng.random(n) > rng.uniform(0.02, 0.15)
    for _ in range(rng.integers(0, 3)):                                                     # bursts of loss
        a = rng.uniform(t[0], t[-1]); keep &= ~((t > a) & (t < a + rng.uniform(0.1, 0.6)))
    ta = t + rng.uniform(0, 0.004, n)
    return ta[keep], iq[keep]


def packets(rng, p, kind, seconds, clean=False, static=None):
    """One recording: (arrival times, iq[n, 51, 2] int8-valued, facts). p is a person from people.json or None;
    static is a room's channel from room() to keep one room for several recordings (else a new room)."""
    t = np.arange(0, seconds, 1 / PKT_HZ) * (1 + rng.uniform(-0.02, 0.02))
    H = np.broadcast_to(room(rng) if static is None else static, (len(t), len(KW))).copy()
    facts = {"zone": -1, "bpm": 0.0, "fan": 0}
    if p is not None:
        Hb, facts["zone"], bpm = body_channel(rng, p, t, kind)
        H += Hb
        facts["bpm"] = bpm if kind == "still" else 0.0
    elif rng.random() < 0.35:
        H += fan_channel(rng, t)
        facts["fan"] = 1
    ta, iq = esp32(rng, H, t, clean)
    return ta, iq, facts


def window(args):
    i, seed, p, kind, clean = args
    rng = np.random.default_rng([seed, i])
    while True:
        ta, iq, f = packets(rng, p, kind, cw.SECONDS + 0.5, clean)
        W = cw.to_window(ta, np.hypot(iq[..., 0], iq[..., 1]), t_end=ta[0] + cw.SECONDS + 0.2)
        if W is not None:
            return W, f


def plan(people, seed, n_still=3, n_moving=2, empty_per_person=2.0):
    """Which windows to make: (index, seed, person or None, class, group). The group (person id; empty rooms get
    their own) keeps every window of one person in one split."""
    jobs, k = [], 0
    for p in people:
        for kind in ["still"] * n_still + ["moving"] * n_moving:
            jobs.append((k, seed, p, kind, p["id"])); k += 1
    for j in range(int(round(empty_per_person * len(people)))):
        jobs.append((k, seed, None, "empty", 100000 + j)); k += 1
    return jobs


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--people", default=os.path.join(HERE, "data", "people.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "synth.npz"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0, help="only the first N people (quick runs)")
    ap.add_argument("--clean", action="store_true", help="no ESP32 faults (ablation)")
    ap.add_argument("--jobs", type=int, default=min(12, os.cpu_count() or 1))
    a = ap.parse_args()
    people = json.load(open(a.people))["people"]
    if a.limit:
        people = people[:a.limit]
    jobs = plan(people, a.seed)
    t0 = time.time()
    with Pool(a.jobs) as pool:
        out = pool.map(window, [(k, s, p, kind, a.clean) for k, s, p, kind, g in jobs], chunksize=8)
    X = np.stack([w for w, f in out]).astype(np.float16)
    kind = np.array([CLASSES.index(j[3]) for j in jobs], np.int8)
    meta = {
        "presence": (kind > 0).astype(np.int8), "moving": np.where(kind > 0, kind == 2, -1).astype(np.int8),
        "zone": np.array([f["zone"] for w, f in out], np.int8), "kind": kind,
        "group": np.array([j[4] for j in jobs], np.int32), "bpm": np.array([f["bpm"] for w, f in out], np.float32),
        "fan": np.array([f["fan"] for w, f in out], np.int8),
        "lying": np.array([j[2] is not None and j[2]["posture"] == "lying" for j in jobs], np.int8),
        "depth": np.array([j[2]["y"] - WALL_Y if j[2] else 0 for j in jobs], np.float32)}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    np.savez_compressed(a.out, X=X, clean=a.clean, seed=a.seed, **meta)
    counts = {c: int((kind == i).sum()) for i, c in enumerate(CLASSES)}
    print(f"wrote {a.out}: X {X.shape} in {time.time() - t0:.0f} s; {counts}, {int(meta['fan'].sum())} empty rooms with a fan;"
          f" zones {np.bincount(meta['zone'][meta['zone'] >= 0], minlength=3).tolist()}")


if __name__ == "__main__":
    main()
