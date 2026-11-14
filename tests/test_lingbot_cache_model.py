import math

import numpy as np
import pytest

from adapters.lingbot_world2 import cache_model as C
from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import probe as PR


# ---------------------------------------------------------------- visible

def test_visible_18_6():
    assert C.visible(0) == []
    assert C.visible(1) == [0, 1, 2, 3]
    assert C.visible(2) == list(range(8))
    assert C.visible(3) == list(range(12))  # end = 16 <= 18: everything before
    assert C.visible(4) == [0, 1, 2, 3, 4, 5] + list(range(8, 16))  # end = 20: 12 newest incl. itself
    assert C.visible(5) == [0, 1, 2, 3, 4, 5] + list(range(12, 20))
    assert C.visible(6) == [0, 1, 2, 3, 4, 5] + list(range(16, 24))
    for c in range(4, 12):
        v = C.visible(c)
        assert len(v) == 6 + 8 and v[:6] == list(range(6)) and v[-1] == 4 * c - 1


def test_visible_36_6_and_unbounded():
    for c in range(7):
        assert C.visible(c, 36, 6) == list(range(4 * c))
        assert C.visible(c, -1, 0) == list(range(4 * c))
    assert C.visible(9, 36, 6) == list(range(6)) + list(range(10, 36))
    assert C.visible(100, -1, 0) == list(range(400))


# ------------------------------------------------------------ chunk_report

def _latents(keys, yaw_deg):
    c2ws = [np.eye(4)]
    for k in keys:
        c2ws.append(c2ws[-1] @ P.key_delta(k))
    return C.latents_from_frames(np.stack(c2ws))


def test_latents_from_frames_whole_chunks_only():
    c = np.stack([np.eye(4)] * 70)
    assert len(C.latents_from_frames(c)) == 16  # ceil(70/4)=18 -> 16
    assert len(C.latents_from_frames(c[:17])) == 4


def test_static_camera_revisits_but_sink_keeps_it(monkeypatch):
    monkeypatch.setattr(P, "YAW", math.radians(1.5))
    rows = C.chunk_report(_latents(["none"] * 160, 0))
    assert [r["chunk"] for r in rows] == list(range(1, 10))
    assert not rows[0]["revisit"]  # chunk 1 only sees the previous chunk
    assert all(r["revisit"] for r in rows[1:])
    assert not any(r["evicted"] for r in rows)  # latent 0 sits in the sink
    assert all(r["best_all"] == 0.0 and r["best_vis"] == 0.0 for r in rows)
    assert 0 in rows[-1]["matched_latents"]
    s = C.summarize(rows)
    assert s == {"chunks": 10, "revisit_chunks": 8, "evicted_revisit_chunks": 0, "first_evicted_chunk": None}


def _turn_away_and_back(hold=40, deg=1.5, out=60):
    return ["none"] * 8 + ["l"] * out + ["none"] * hold + ["j"] * out + ["none"] * 24


def test_turn_away_and_back_evicts_at_18_6_only(monkeypatch):
    monkeypatch.setattr(P, "YAW", math.radians(1.5))
    lat = _latents(_turn_away_and_back(), 0)
    small = C.chunk_report(lat, 18, 6)
    big = C.chunk_report(lat, 36, 6)
    full = C.chunk_report(lat, -1, 0)
    assert any(r["revisit"] and r["evicted"] for r in small)
    assert not any(r["evicted"] for r in full)
    assert sum(r["evicted"] for r in big) <= sum(r["evicted"] for r in small)
    # same history in every window; only the visible part shrinks
    assert [r["revisit"] for r in small] == [r["revisit"] for r in full]
    assert [r["best_all"] for r in small] == [r["best_all"] for r in full]
    for r in small:
        if r["best_vis"] is not None and r["best_all"] is not None:
            assert r["best_vis"] >= r["best_all"]
    s = C.summarize(small)
    assert s["first_evicted_chunk"] == min(r["chunk"] for r in small if r["evicted"])
    assert s["evicted_revisit_chunks"] <= s["revisit_chunks"]
    assert C.summarize(full)["first_evicted_chunk"] is None


def test_distance_gate(monkeypatch):
    monkeypatch.setattr(P, "YAW", math.radians(1.5))
    lat = _latents(["w"] * 160, 0)  # straight ahead, same direction, camera moves 4 units per latent
    assert any(r["revisit"] for r in C.chunk_report(lat, dist=1000.0))
    near = C.chunk_report(lat, dist=16.0)
    assert not any(r["revisit"] for r in near)  # older than 1 chunk is >= 20 units away
    assert all(r["matched_latents"] == [] for r in near)


# ------------------------------------------------------------------- probe

@pytest.mark.parametrize("angle,hold", [(45, 0), (90, 0), (90, 48), (180, 48), (10, 7)])
def test_trajectory_whole_steps(angle, hold):
    rate = 45 / 32
    keys = PR.trajectory(angle, hold, rate)
    assert (len(keys) - 28) % 32 == 0 and len(keys) >= 28
    steps = PR.split_steps(keys)
    assert [len(s) for s in steps] == [28] + [32] * (len(steps) - 1)
    assert sum(steps, []) == keys
    n = round(angle / rate)
    assert keys.count("l") == n and keys.count("j") == n
    y = PR.yaws(keys, rate)
    assert len(y) == len(keys) + 1 and y[0] == 0.0
    assert y.max() == pytest.approx(n * rate) and y[-1] == pytest.approx(0.0, abs=1e-9)


def test_phases_consistent():
    rate = 45 / 32
    keys = PR.trajectory(90, 48, rate)
    ph = PR.phases(keys)
    n = round(90 / rate)
    y = PR.yaws(keys, rate)
    assert ph["pre"] == list(range(PR.SETTLE_IN + 1))
    assert len(ph["out"]) == n and len(ph["back"]) == n
    assert ph["out"][0] == ph["pre"][-1] + 1 and ph["back"][0] == ph["out"][-1] + 48 + 1
    assert ph["post"][0] == ph["back"][-1] + 1 and ph["post"][-1] == len(keys)
    hold = list(range(ph["out"][-1] + 1, ph["back"][0]))  # hold frames belong to no phase
    assert len(hold) == 48
    assert sorted(sum(ph.values(), []) + hold) == list(range(len(keys) + 1))
    assert y[ph["out"][-1]] == pytest.approx(n * rate) and y[ph["back"][-1]] == pytest.approx(0.0, abs=1e-9)
    assert PR.phases(PR.trajectory(90, 0, rate))["back"][0] == PR.phases(PR.trajectory(90, 0, rate))["out"][-1] + 1


def test_latent_of():
    assert [PR.latent_of(f) for f in (0, 1, 4, 5, 8, 9)] == [0, 1, 1, 2, 2, 3]


def test_pairs_structure():
    rate = 45 / 32
    keys = PR.trajectory(90, 48, rate)
    y = PR.yaws(keys, rate)
    ph = PR.phases(keys)
    rows = PR.pairs(keys, rate, 18, 6)
    turn = [r for r in rows if r["kind"] == "turn"]
    settle = [r for r in rows if r["kind"] == "settle"]
    assert len(turn) == len(ph["back"]) and len(settle) == len(ph["post"])
    for r in turn:
        assert r["frame"] in ph["back"] and r["ref"] in ph["out"] + ph["pre"]
        assert y[r["ref"]] == pytest.approx(y[r["frame"]], abs=1e-6)
        assert r["gap_latents"] > 0
    for r in settle:
        assert r["ref"] == ph["pre"][-1]
    for r in rows:
        lf, lj = PR.latent_of(r["frame"]), PR.latent_of(r["ref"])
        assert r["gap_latents"] == lf - lj
        assert r["in_cache"] == (lj in C.visible(lf // C.CHUNK, 18, 6))
        assert r["ref_in_sink"] == (lj < 6)
        if r["ref_in_sink"]:
            assert r["in_cache"]
    assert any(not r["in_cache"] for r in rows)  # a 48-frame hold pushes the outbound view out at 18:6
    assert any(r["in_cache"] for r in rows)


def test_pairs_unbounded_window_all_cached():
    rate = 45 / 32
    rows = PR.pairs(PR.trajectory(180, 48, rate), rate, -1, 0)
    assert rows and all(r["in_cache"] for r in rows)
    # bigger window never evicts more
    n18 = sum(not r["in_cache"] for r in PR.pairs(PR.trajectory(180, 48, rate), rate, 18, 6))
    n36 = sum(not r["in_cache"] for r in PR.pairs(PR.trajectory(180, 48, rate), rate, 36, 6))
    assert n36 <= n18


def test_pairs_tolerance_drops_unmatched():
    keys = PR.trajectory(90, 0, 45 / 32)
    assert PR.pairs(keys, 45 / 32, 18, 6, tol=-1.0) == []


def test_aggregate_keys_and_counts():
    rows = [
        {"kind": "turn", "in_cache": True, "psnr": 20.0, "corr": 0.5, "dino": None},
        {"kind": "turn", "in_cache": True, "psnr": 30.0, "corr": 0.7, "dino": 0.9},
        {"kind": "turn", "in_cache": False, "psnr": 10.0, "corr": 0.1, "dino": None},
        {"kind": "settle", "in_cache": False, "psnr": 12.0, "corr": 0.2, "dino": None},
    ]
    a = PR.aggregate(rows)
    assert len(a) == 4 * 4
    assert {k for k in a if k.endswith("_n")} == {"turn_cached_n", "turn_evicted_n", "settle_cached_n", "settle_evicted_n"}
    assert (a["turn_cached_n"], a["turn_evicted_n"], a["settle_cached_n"], a["settle_evicted_n"]) == (2, 1, 0, 1)
    assert a["turn_cached_psnr"] == 25.0 and a["turn_cached_corr"] == pytest.approx(0.6)
    assert a["turn_cached_dino"] == 0.9 and a["turn_evicted_dino"] is None
    assert a["settle_cached_psnr"] is None and a["settle_evicted_psnr"] == 12.0


def test_psnr_and_corr():
    rng = np.random.default_rng(0)
    a = rng.random((8, 8, 3)).astype(np.float32)
    assert PR.psnr(a, a) == 99.0
    assert PR.corr(a, a) == pytest.approx(1.0, abs=1e-4)
    assert PR.corr(a, 1 - a) == pytest.approx(-1.0, abs=1e-4)
    assert PR.psnr(a, np.clip(a + 0.1, 0, 1)) < 30
    assert PR.psnr(np.zeros((2, 2)), np.full((2, 2), 0.1)) == pytest.approx(20.0)
