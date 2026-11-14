import importlib.util

import numpy as np
import pytest

from adapters.lingbot_world2 import poses as P


def test_parse_and_frame_count():
    assert P.parse_action("w-2,none-1,j-1") == ["w", "w", "none", "j"]
    assert P.frame_count(33) == 45  # latent 9 -> 12
    assert P.frame_count(29) == 29  # latent 8
    for n in (2, 33, 81, 961):
        f = P.frame_count(n)
        assert f >= n and (f - 1) % 4 == 0 and ((f - 1) // 4 + 1) % P.LATENT_CHUNK == 0


def test_pose_directions_opencv():
    fwd = P.build_poses("w-28", 29)
    assert fwd.shape == (29, 4, 4) and fwd.dtype == np.float32
    assert np.allclose(fwd[-1, :3, 3], [0, 0, 28])
    assert P.build_poses("a-28", 29)[-1, 0, 3] < 0 < P.build_poses("d-28", 29)[-1, 0, 3]
    z = np.array([0, 0, 1.0])
    assert (P.key_delta("l")[:3, :3] @ z)[0] > 0 > (P.key_delta("j")[:3, :3] @ z)[0]  # right is +x
    assert (P.key_delta("i")[:3, :3] @ z)[1] < 0 < (P.key_delta("k")[:3, :3] @ z)[1]  # up is -y
    assert np.allclose(P.build_poses("none-28", 29), np.eye(4))


def test_padding_repeats_last_key_and_turn_then_walk():
    p = P.build_poses("w-32", 33)  # padded to 45 frames
    assert len(p) == 45 and np.isclose(p[-1, 2, 3], 44)
    q = P.build_poses("l-10,w-18", 29)
    assert q[-1, 0, 3] > 0 and q[-1, 2, 3] > 0  # walks along the turned heading
    assert P.intrinsics(29).shape == (29, 4)


def test_harness_closed_loop_args_keep_frame_budget():
    # run_agent passes action=f"{key}-{chunk_frames}" with num_frames=chunk_frames
    assert len(P.build_poses("w-29", 29)) == 29
    assert len(P.build_poses("w-33", 33)) == 45
    # dataset mode passes num_frames = sum(frames) + 1
    assert len(P.build_poses("w-80,d-100,none-50", 231)) == P.frame_count(231)


def _yaw_deg(pose):
    """Heading of the camera z axis in the ground plane, degrees, right positive."""
    z = pose[:3, :3] @ np.array([0, 0, 1.0])
    return np.degrees(np.arctan2(z[0], z[2]))


def _pitch_deg(pose):
    return np.degrees(np.arcsin(-(pose[:3, :3] @ np.array([0, 0, 1.0]))[1]))  # up positive


@pytest.fixture
def turn_cal(monkeypatch):
    """Calibrate inside a test; monkeypatch restores the default rates afterwards."""
    monkeypatch.setattr(P, "YAW", P.YAW)
    monkeypatch.setattr(P, "PITCH", P.PITCH)
    return P.calibrate


def test_default_rates_overshoot_dataset_turns(monkeypatch):
    # Off by default: "→*4" (90 degrees in the task prompt) is 80 frames at 0.03 rad = 137.5.
    monkeypatch.setattr(P, "YAW", 0.03)
    assert np.isclose(_yaw_deg(P.build_poses("l-80", 81)[80]), 137.5, atol=0.1)


def test_turn_cal_dataset_tokens_are_prompt_angles(turn_cal):
    turn_cal(True, 0, 20)
    p = P.build_poses("l-80,j-80,none-50", 211)  # OE034: right 90, back
    assert np.isclose(_yaw_deg(p[80]), 90, atol=1e-3)
    assert np.allclose(p[160, :3, :3], np.eye(3), atol=1e-5)
    full = P.build_poses("l-320,s-40", 361)  # OE039: 360 in place ends on the start view
    assert np.isclose(_yaw_deg(full[160]) % 360, 180, atol=1e-3)
    assert np.allclose(full[320, :3, :3], np.eye(3), atol=1e-4)
    assert np.isclose(_pitch_deg(P.build_poses("i-40", 41)[40]), 40, atol=1e-3)  # "u*2": up 40


def test_turn_cal_closed_loop_chunk_is_45_degrees(turn_cal):
    from adapters.lingbot_world2 import session as S
    for n_keys in (S.keys_needed(2, first=True), S.keys_needed(2, first=False), P.frame_count(33) - 1):
        yaw, pitch = turn_cal(False, n_keys)
        assert np.isclose(np.degrees(yaw * n_keys), 45) and np.isclose(np.degrees(pitch * n_keys), 40)
    track = S.PoseTrack()
    for first in (True, False):  # two RIGHT chunks through the session track: 90 degrees
        keys = ["l"] * S.keys_needed(2, first=first)
        turn_cal(False, len(keys))
        track.advance(keys)
    assert np.isclose(_yaw_deg(track.last), 90, atol=1e-3)
    with pytest.raises(ValueError):
        turn_cal(False, 0)


@pytest.mark.skipif(importlib.util.find_spec("httpx") is None, reason="upstream run_agent needs httpx")
def test_turn_cal_matches_upstream_dataset_action_strings(turn_cal):
    """End to end with the harness's own token -> frames mapping (default 20 frames per token)."""
    from adapters.common.upstream import import_run_agent
    ra = import_run_agent()
    turn_cal(True, 0, 20)
    for action, turned, final in (("→*4 -> ←*4", 90, 0), ("←*8 -> →*8", -180, 0), ("→*16", 0, 0)):
        sana, log = ra.build_full_sana_action({"action": action}, 20, 50, 961)
        p = P.build_poses(sana, sum(r["frames"] for r in log) + 1)
        mid = log[0]["frames"]
        assert np.isclose((_yaw_deg(p[mid]) - turned + 180) % 360 - 180, 0, atol=1e-2), action
        end = sum(r["frames"] for r in log)
        assert np.isclose((_yaw_deg(p[end]) - final + 180) % 360 - 180, 0, atol=1e-2), action
