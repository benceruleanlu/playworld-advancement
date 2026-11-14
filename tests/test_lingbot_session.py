import numpy as np
import pytest

from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import session as S


def test_frame_accounting_matches_harness_stitching():
    assert S.chunks_for(33) == 2 and S.chunks_for(29) == 2 and S.chunks_for(17) == 1 and S.chunks_for(2) == 1
    assert S.chunks_for(861) == 54
    # first step: 16n-3 frames incl. the input frame; continuation: prev last + 16n new
    assert S.frames_returned(2, first=True) == 29 and S.keys_needed(2, first=True) == 28
    assert S.frames_returned(2, first=False) == 33 and S.keys_needed(2, first=False) == 32
    # stitched like run_task_closed_loop: frames if first else frames[1:]
    total = S.frames_returned(2, True) + 29 * (S.frames_returned(2, False) - 1)
    latents = 30 * 2 * S.CHUNK
    assert total == 1 + 4 * (latents - 1)  # one continuous rollout, no dropped or doubled frame
    assert latents <= S.ROPE_LATENTS


def test_fit_keys_pads_with_last_key():
    assert S.fit_keys(["w"] * 33, 28) == ["w"] * 28
    assert S.fit_keys(["w", "j"], 4) == ["w", "j", "j", "j"]
    assert S.fit_keys([], 3) == ["none"] * 3


def test_continuation_detection_from_names():
    assert S.parse_chunk_name("GC005_chunk_03") == ("GC005", 3)
    assert S.parse_chunk_name("IF_third_person_01_chunk_12") == ("IF_third_person_01", 12)
    assert S.parse_chunk_name("GC005_full") is None
    assert S.is_continuation(("GC005", 2), ("GC005", 3))
    assert not S.is_continuation(("GC005", 2), ("GC005", 1))  # chunk 01 always resets
    assert not S.is_continuation(("GC005", 2), ("GC006", 3))  # other task
    assert not S.is_continuation(("GC005", 2), ("GC005", 4))  # skipped chunk
    assert not S.is_continuation(None, ("GC005", 2))
    assert not S.is_continuation(("GC005", 1), None)          # _full resets


def _upstream_reference(keys, normalise_max=True):
    """Whole-sequence poses -> latent poses -> upstream compute_relative_poses(framewise)."""
    c2ws = [np.eye(4)]
    for k in keys:
        c2ws.append(c2ws[-1] @ P.key_delta(k))
    lat = np.stack(c2ws)[::4]  # interpolate_camera_poses at pixel frames 0, 4, 8, ...
    rel = lat[0:1].copy()
    rel = np.linalg.inv(lat[0]) @ lat            # relative to the first
    rel[0] = np.eye(4)
    fw = rel.copy()
    fw[1:] = np.linalg.inv(rel[:-1]) @ rel[1:]   # framewise
    t = fw[:, :3, 3]
    m = np.linalg.norm(t, axis=-1).max()
    if normalise_max and m > 0:
        fw[:, :3, 3] = t / m
    return fw


def test_straight_walk_gives_unit_translation_and_matches_upstream():
    tr = S.PoseTrack()
    rel = tr.advance(["w"] * 28)
    assert rel.shape == (8, 4, 4)
    assert np.allclose(rel[0], np.eye(4))
    assert np.allclose(np.linalg.norm(rel[1:, :3, 3], axis=-1), 1.0)
    assert np.allclose(rel[1:, :3, 3], [0, 0, 1])
    assert np.allclose(rel, _upstream_reference(["w"] * 28))
    assert np.allclose(np.linalg.norm(tr.advance(["s"] * 16)[:, :3, 3], axis=-1), 1.0)


def test_chunked_stepping_equals_whole_sequence():
    rng = np.random.default_rng(0)
    pool = ["w", "s", "a", "d", "j", "l", "i", "k", "none", "w+j"]
    keys = list(rng.choice(pool, size=28 + 32 * 5))
    tr = S.PoseTrack()
    parts = [tr.advance(keys[:28])]
    for i in range(5):
        parts.append(tr.advance(keys[28 + 32 * i: 60 + 32 * i]))
    chunked = np.concatenate(parts)
    # same sequence in one call (dataset mode) and the fixed-scale reference
    whole = S.PoseTrack().advance(keys)
    ref = _upstream_reference(keys, normalise_max=False)
    assert np.allclose(chunked, whole)
    assert np.allclose(chunked, S.normalise_translation(ref))
    # rotations untouched by normalisation, translations never above norm 1
    assert np.allclose(chunked[:, :3, :3], ref[:, :3, :3])
    assert (np.linalg.norm(chunked[:, :3, 3], axis=-1) <= 1 + 1e-9).all()


def test_wait_and_diagonal_normalisation():
    assert np.allclose(S.PoseTrack().advance(["none"] * 12), np.eye(4))
    diag = S.PoseTrack().advance(["w+d"] * 12)
    assert np.allclose(np.linalg.norm(diag[1:, :3, 3], axis=-1), 1.0)  # clipped, as upstream max-norm would
    slow = np.stack([np.eye(4)] * 2)
    slow[1, 2, 3] = 2.0  # half a latent of motion stays at half scale
    assert np.isclose(S.normalise_translation(slow)[1, 2, 3], 0.5)


def test_pose_track_rejects_partial_chunks():
    with pytest.raises(ValueError):
        S.PoseTrack().advance(["w"] * 30)
    tr = S.PoseTrack()
    tr.advance(["w"] * 12)
    with pytest.raises(ValueError):
        tr.advance(["w"] * 12)  # continuation needs multiples of 16


def test_horizon_latents():
    assert S.horizon_latents(961) == 248
    assert S.horizon_latents(29) == 12
    assert S.horizon_latents(10_000) == S.ROPE_LATENTS
    assert S.horizon_latents(961) % S.CHUNK == 0
