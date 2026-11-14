"""Cycle generator and rotation-consistency reward on synthetic, exactly rendered views.

A procedural texture on the unit sphere is rendered through the session's pinhole camera
for each frame's rotation: a perfect world model. Corruptions (no rotation, drifting
world, a hard cut, blur) must each lower the matching reward term.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rl.cycles import (frame_rotations, n_keys_for, out_and_back, revisit_pairs,  # noqa: E402
                       rotation_angle, sample_cycle, Cycle)
from rl.rewards import RewardConfig, cycle_reward, gap_curve, homography, intrinsics_matrix  # noqa: E402

H, W = 120, 208  # 1/4 of 480x832


def sphere_texture(d: np.ndarray, phase: float = 0.0) -> np.ndarray:
    """RGB in [0, 255] for unit directions d [..., 3]; smooth but structured."""
    lon = np.arctan2(d[..., 0], d[..., 2])
    lat = np.arcsin(np.clip(d[..., 1], -1, 1))
    r = 0.5 + 0.5 * np.sin(9 * lon + phase) * np.cos(7 * lat)
    g = 0.5 + 0.5 * np.sin(5 * lon - 3 * lat + 2 * phase)
    b = 0.5 + 0.5 * np.cos(13 * lat + 4 * lon)
    fine = 0.25 * np.sin(140 * lon + phase) * np.sin(110 * lat)  # texture detail that blur removes
    return (np.clip(np.stack([r + fine, g + fine, b + fine], -1), 0, 1) * 255).astype(np.uint8)


def render(rots: np.ndarray, phases=None) -> np.ndarray:
    K = intrinsics_matrix(H, W)
    ys, xs = np.mgrid[0:H, 0:W]
    pix = np.stack([xs + 0.5, ys + 0.5, np.ones_like(xs, dtype=float)], -1) @ np.linalg.inv(K).T
    pix /= np.linalg.norm(pix, axis=-1, keepdims=True)
    phases = np.zeros(len(rots)) if phases is None else phases
    return np.stack([sphere_texture(pix @ R.T, ph) for R, ph in zip(rots, phases)])


CFG = RewardConfig(scale=1)


def cycle(out=40, n_chunks=8, yaw=0.03, repeats=1):
    return Cycle("out_back", out_and_back(n_chunks, out, "l", repeats=repeats), yaw, 0.01)


def test_out_and_back_returns_to_start_and_fills_chunks():
    c = cycle(out=40)
    assert len(c.keys) == n_keys_for(8) == 124
    rots = frame_rotations(c)
    assert rots.shape == (125, 3, 3)
    assert np.allclose(rots[80], np.eye(3), atol=1e-9)
    assert np.isclose(np.degrees(rotation_angle(rots[0], rots[40])), np.degrees(40 * 0.03))


def test_sampled_cycles_are_closed_rotations():
    rng = np.random.default_rng(1)
    for _ in range(30):
        c = sample_cycle(rng)
        rots = frame_rotations(c)
        assert len(rots) == 125
        assert len(revisit_pairs(rots, 49, np.radians(25))) > 0, c.kind


def test_homography_maps_rendered_views():
    rots = frame_rotations(cycle(out=20))
    frames = render(rots[[0, 10]])
    K = intrinsics_matrix(H, W)
    warped = cv2.warpPerspective(frames[0], homography(K, rots[0], rots[10]), (W, H))
    m = cv2.warpPerspective(np.ones((H, W), np.uint8), homography(K, rots[0], rots[10]), (W, H)) > 0
    m = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    assert np.abs(warped[m].astype(int) - frames[1][m].astype(int)).mean() < 6


def test_perfect_world_scores_high():
    rots = frame_rotations(cycle(out=45))
    r = cycle_reward(render(rots), rots, CFG)
    assert r["local"] > 0.9 and r["memory"] > 0.9 and r["sharp"] > 0.9, r


def test_frozen_camera_loses_local_reward():
    rots = frame_rotations(cycle(out=45))
    still = np.repeat(render(rots[:1]), len(rots), axis=0)  # ignores the controls
    good = cycle_reward(render(rots), rots, CFG)
    bad = cycle_reward(still, rots, CFG)
    assert bad["local"] < good["local"] - 0.15, (bad, good)


def test_drifting_world_loses_memory_reward():
    rots = frame_rotations(cycle(out=45))
    drift = render(rots, phases=np.linspace(0, 2.5, len(rots)))  # world slowly changes
    good = cycle_reward(render(rots), rots, CFG)
    bad = cycle_reward(drift, rots, CFG)
    assert bad["memory"] < good["memory"] - 0.1, (bad, good)
    assert bad["local"] > bad["memory"]  # drift hurts long gaps more than short ones


def test_hard_cut_is_caught_by_local_percentile():
    rots = frame_rotations(cycle(out=45))
    frames = render(rots)
    cut = frames.copy()
    cut[60:] = render(rots[60:], phases=np.full(len(rots) - 60, 3.0))  # world swaps mid-rollout
    assert cycle_reward(cut, rots, CFG)["local_min"] < cycle_reward(frames, rots, CFG)["local_min"] - 0.2


def test_blur_loses_sharp_reward():
    rots = frame_rotations(cycle(out=45))
    frames = render(rots)
    blurred = frames.copy()
    blurred[1:] = np.stack([cv2.GaussianBlur(f, (9, 9), 3) for f in frames[1:]])
    assert cycle_reward(blurred, rots, CFG)["sharp"] < 0.5


def test_gap_curve_bins():
    rots = frame_rotations(cycle(out=30, repeats=2))
    curve = gap_curve(render(rots), rots, CFG)
    assert set(curve) == {"4-8", "9-24", "25-48", "49-96", "97-10000"}
    assert all(v[0] is None or v[0] > 0.9 for v in curve.values())


def test_group_r_centres_and_flags_no_signal():
    from rl.train import group_r
    r, std = group_r(np.array([1.0, 2.0, 3.0]))
    assert std > 0 and np.isclose(r.mean(), 0.5) and r[0] < 0.5 < r[2]
    r, std = group_r(np.array([1.0, 1.0]))
    assert std < 1e-4 and np.allclose(r, 0.5)


def test_eval_cycles_fit_and_revisit():
    from rl.train import eval_cycles
    for c in eval_cycles(8):
        rots = frame_rotations(c)
        assert len(rots) == 125, c.kind
        assert len(revisit_pairs(rots, 49, np.radians(25))) > 0, c.kind


def test_control_metrics_measure_rotation():
    from rl.rewards import control_metrics
    rots = frame_rotations(cycle(out=40))
    frames = render(rots)
    good = control_metrics(frames, rots, scale=1)
    still = control_metrics(np.repeat(frames[:1], len(rots), axis=0), rots, scale=1)
    assert good["ctrl_valid"] > 0.8 and good["ctrl_err_deg"] < 1.0, good
    assert still["ctrl_err_deg"] > 4.0, still  # commanded 0.03 rad x 4 frames = 6.9 deg per step
