"""The Wi-Fi network (ml/): simulator, packet path, network maths, the shipped model, live reading, fine-tuning.
Needs numpy (run with the rover's venv or any Python that has it); skipped otherwise."""
import json
import os
import sys

import pytest

np = pytest.importorskip("numpy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ML = os.path.join(ROOT, "ml")
sys.path.insert(0, ML)

import csi_window as cw  # noqa: E402
import simulate_csi as S  # noqa: E402
from net import Adam, CsiNet  # noqa: E402

PEOPLE = json.load(open(os.path.join(ML, "data", "people.json")))["people"]


def amps(iq):
    return np.hypot(iq[..., 0], iq[..., 1])


def test_people_from_blender_are_complete():
    assert len(PEOPLE) >= 500
    for p in PEOPLE[:50]:
        assert len(p["points"]) == 24 and p["posture"] in ("standing", "lying") and 1.2 <= p["height"] <= 1.95
        assert any(q[7] == 0 for q in p["points"])                                   # some torso points: they breathe


def test_simulator_is_deterministic_and_window_shaped():
    a, fa = S.window((5, 7, PEOPLE[3], "still", False))
    b, fb = S.window((5, 7, PEOPLE[3], "still", False))
    assert a.shape == (cw.N_IN, cw.N_T) == (52, 200)
    assert np.array_equal(a, b) and fa == fb
    c, _ = S.window((6, 7, PEOPLE[3], "still", False))
    assert not np.array_equal(a, c)


def test_simulated_packets_go_through_the_real_receiver_parser():
    from csi import parse_udp
    _, iq, _ = S.packets(np.random.default_rng(0), PEOPLE[0], "moving", 0.2)
    for q in iq[:10]:
        rec = parse_udp(cw.encode_packet(q.astype(np.int8), seq=7))
        assert rec["seq"] == 7 and np.allclose(rec["amp"], amps(q))


def test_body_echo_is_as_strong_as_fresnel_says():
    """The Blender body's echo, summed over its surface points, is the strength sensing/fresnel.py assumes for a person
    (0.15 / (d1·d2), halved by the wall) to within a factor of 4 for standing people facing any way."""
    t = np.arange(0, 1, 0.01)
    ratios = []
    for p in [p for p in PEOPLE if p["posture"] == "standing"][:40]:
        Hb, _, _ = S.body_channel(np.random.default_rng(1), p, t, "still")
        c = np.array([p["x"], p["y"], 1.0])
        model = S.BODY * S.WALL_LOSS / (np.linalg.norm(c - S.TX_) * np.linalg.norm(c - S.RX_))
        ratios.append(np.abs(Hb).mean() / model)
    assert 0.25 < np.median(ratios) < 4


def test_windows_survive_dropped_packets_and_refuse_when_too_many_are_lost():
    ta, iq, _ = S.packets(np.random.default_rng(2), PEOPLE[1], "moving", 11)
    a = amps(iq)
    keep = (np.random.default_rng(3).random(len(ta)) > 0.3) & ~((ta > 4) & (ta < 5))      # 30 % lost and a 1 s gap
    W = cw.to_window(ta[keep], a[keep], ta[0] + 10.5)
    assert W is not None and np.isfinite(W).all()
    sparse = np.arange(len(ta)) % 4 == 0
    sparse &= ta < ta[0] + 5                                                            # half the window is silent
    assert cw.to_window(ta[sparse], a[sparse], ta[0] + 10.5) is None


def test_agc_steps_are_taken_out_but_a_body_is_not():
    t = np.arange(0, 10, 0.01)
    a = np.tile(np.linspace(20, 40, cw.N_SUB), (len(t), 1))
    a[t >= 5] *= 1.2                                                                    # the AGC jumps 20 %
    x = cw.normalise(cw.to_window(t, a, 10.0))
    assert np.abs(x[:cw.N_SUB]).max() < 0.01
    a2 = a * (1 + 0.01 * np.sin(2 * np.pi * 0.3 * t))[:, None]                          # 1 % breathing, all subcarriers
    x2 = cw.normalise(cw.to_window(t, a2, 10.0))
    assert np.abs(x2[:cw.N_SUB]).max() > 0.5


def test_every_gradient_matches_finite_differences():
    rng = np.random.default_rng(0)
    net = CsiNet(seed=1, width=4, hidden=5, heads=("person", "moving", "zone"))
    x = rng.standard_normal((3, cw.N_IN, cw.N_T)).astype(np.float32)
    y = {"person": np.array([1, 0, 1]), "moving": np.array([0, -1, 1]), "zone": np.array([2, -1, 0])}
    net.loss(x, y)
    grads = [g.copy() for g in net.grads()]
    checked = 0
    for p, g in zip(net.params(), grads):
        for i in rng.choice(p.size, min(6, p.size), replace=False):
            old = p.flat[i]
            p.flat[i] = old + 1e-2; up = net.loss(x, y)
            p.flat[i] = old - 1e-2; dn = net.loss(x, y)
            p.flat[i] = old
            num = (up - dn) / 2e-2
            assert abs(num - g.flat[i]) < 2e-3 + 0.05 * abs(num), (p.shape, i, num, g.flat[i])
            checked += 1
    assert checked > 50


def test_network_can_learn_32_windows_by_heart():
    rng = np.random.default_rng(0)
    x = rng.standard_normal((32, cw.N_IN, cw.N_T)).astype(np.float32)
    y = {"person": rng.integers(0, 2, 32), "moving": rng.integers(0, 2, 32)}
    net = CsiNet(seed=0)
    opt = Adam(net.params(), lr=3e-3, wd=0)
    first = net.loss(x, y)
    for _ in range(150):
        net.loss(x, y); opt.step(net.grads())
    assert net.loss(x, y) < 0.05 < first
    p = net.predict(x)
    assert (p["person"].argmax(1) == y["person"]).all() and (p["moving"].argmax(1) == y["moving"]).all()


def test_saved_network_loads_back_the_same(tmp_path):
    net = CsiNet(seed=3)
    x = np.random.default_rng(1).standard_normal((2, cw.N_IN, cw.N_T)).astype(np.float32)
    net.save(tmp_path / "n.npz", person_threshold=0.6)
    back = CsiNet.load(tmp_path / "n.npz")
    assert back.meta["person_threshold"] == 0.6
    assert np.allclose(net.predict(x)["person"], back.predict(x)["person"])


def test_shipped_network_finds_walking_people_it_never_saw():
    """ml/models/csi_nn.npz on fresh simulated windows (a seed it was not trained with, test-split people): the
    numbers in ml/results/synthetic.md are 87 % of moving people found at ~11 % false alarms."""
    from train import split_of
    net = CsiNet.load(os.path.join(ML, "models", "csi_nn.npz"))
    thr = net.meta["person_threshold"]
    test = [p for p in PEOPLE if split_of(p["id"]) == 2][:40]
    mv = np.stack([S.window((i, 991, p, "moving", False))[0] for i, p in enumerate(test)])
    em = np.stack([S.window((100 + i, 991, None, "empty", False))[0] for i in range(40)])
    found = (net.predict(cw.normalise(mv))["person"][:, 1] > thr).mean()
    false_alarm = (net.predict(cw.normalise(em))["person"][:, 1] > thr).mean()
    assert found >= 0.7 and false_alarm <= 0.3, (found, false_alarm)


def test_live_reading_waits_for_10_s_then_reads_through_lost_packets():
    from infer import LiveNet
    ta, iq, _ = S.packets(np.random.default_rng(4), PEOPLE[2], "moving", 12)
    keep = np.random.default_rng(5).random(len(ta)) > 0.2
    live = LiveNet()
    for t, a in zip(ta[keep], amps(iq)[keep]):
        live.push(t, a)
        if t < ta[0] + 5:
            last = t
    r = live.read(ta[keep][-1])
    assert r["ready"] and 0 <= r["person"] <= 1 and 0 <= r["moving"] <= 1 and r["threshold"] == round(live.threshold, 3)
    assert live.bars(ta[keep][-1]).shape == (cw.N_SUB,)
    live.reset()
    assert live.read(ta[-1]) == {"ready": False, "heard_s": 0.0}
    early = LiveNet()
    for t, a in zip(ta[ta < last], amps(iq)[ta < last]):
        early.push(t, a)
    assert not early.read(last)["ready"]


def test_finetune_without_recordings_says_there_are_none(tmp_path, monkeypatch):
    import finetune
    monkeypatch.setattr(sys, "argv", ["finetune.py", "--real", str(tmp_path / "none"), "--out", str(tmp_path / "m.npz"),
                                      "--results", str(tmp_path / "real.md")])
    finetune.main()
    assert "No recordings" in (tmp_path / "real.md").read_text() and not (tmp_path / "m.npz").exists()


def test_finetune_splits_by_recording_and_reports_both_models(tmp_path, monkeypatch):
    import finetune
    from replay import write_recordings
    paths = write_recordings(str(tmp_path / "rec"), 3, seconds=16)
    split = finetune.deal(paths)
    for lab in ("empty", "still", "moving"):                                       # each label in every split
        assert sorted(v for p, v in split.items() if os.path.basename(p).startswith(lab)) == [0, 1, 2]
    monkeypatch.setattr(sys, "argv", ["finetune.py", "--real", str(tmp_path / "rec"), "--out", str(tmp_path / "m.npz"),
                                      "--results", str(tmp_path / "real.md"), "--epochs", "2"])
    finetune.main()
    doc = (tmp_path / "real.md").read_text()
    assert "simulated" in doc and "trained on simulation only" in doc and (tmp_path / "m.npz").exists()
