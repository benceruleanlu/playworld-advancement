import numpy as np

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
