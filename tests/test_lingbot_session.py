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


# ---- re-anchoring (--lingbot-reanchor) ----

def _dataset_track(action):
    """Absolute latent poses of a dataset-mode rollout: tokens x 20 frames, 50 tail frames."""
    keys = [k for key, n in action for k in [key] * (20 * n)] + ["none"] * 50
    keys = S.fit_keys(keys, S.keys_needed(S.chunks_for(len(keys) + 1), first=True))
    track = S.PoseTrack()
    rel = track.advance(keys)
    assert len(track.latents) == len(rel)  # index i of latents is latent i of this step
    return track.latents


def test_pose_offset_degrees_and_key_units():
    assert S.pose_offset(np.eye(4)) == (0.0, 0.0)
    T = np.eye(4)
    for _ in range(10):
        T = T @ P.key_delta("l+w")
    deg, trans = S.pose_offset(T)
    assert deg == pytest.approx(np.degrees(10 * P.YAW)) and 9.0 < trans <= 10.0


def test_return_detector_on_dataset_tracks():
    # turn left 4 tokens then right 4: back at the start on latent 40 (frame 160), once,
    # although the camera then rests there for the whole tail
    assert S.ReturnDetector().update(_dataset_track([("j", 4), ("l", 4)])) == [40]
    # pan left, right through the centre, back: the pass-through and the final return
    assert S.ReturnDetector().update(_dataset_track([("j", 4), ("l", 8), ("j", 4)])) == [40, 80]
    # translation loop (GC005's box path) returns at its end
    box = [("w", 4), ("d", 5), ("w", 6), ("a", 10), ("s", 6), ("d", 5), ("s", 4)]
    assert S.ReturnDetector().update(_dataset_track(box)) == [200]
    # one-way tracks, and a camera that never leaves, are never anchored
    assert S.ReturnDetector().update(_dataset_track([("w", 10), ("i", 4)])) == []
    assert S.ReturnDetector().update(_dataset_track([("none", 6)])) == []
    # a 2-frame nudge and back stays under the leave threshold
    nudge = S.PoseTrack()
    nudge.advance(S.fit_keys(["l", "l", "j", "j"], 28))
    assert S.ReturnDetector().update(nudge.latents) == []


def test_return_detector_across_closed_loop_steps():
    """Chunked like the harness: LEFT, RIGHT, then WAIT chunks. One anchor, at the first
    latent back at the start, and none while the camera keeps resting there."""
    track, det, anchors, done = S.PoseTrack(), S.ReturnDetector(), [], 0
    for step, key in enumerate(["j", "l", "none", "none"]):
        track.advance([key] * S.keys_needed(2, first=step == 0))
        anchors += [done + i for i in det.update(track.latents)]
        done += len(track.latents)
    # first step: 28 frames left; second: 32 right overshoots by 4 frames (one latent of
    # 4 x 0.03 rad = 6.9 deg, outside the 6 deg tolerance), passing the start at latent 14
    assert anchors == [14]
    deg, trans = S.pose_offset(track.last)
    assert deg == pytest.approx(np.degrees(4 * P.YAW)) and trans == 0.0


def test_reanchor_applies_to_gc_names_only(monkeypatch):
    monkeypatch.delenv("LINGBOT_REANCHOR_TASKS", raising=False)
    assert S.reanchor_task("GC033_full") and S.reanchor_task("GC033_chunk_04")
    # Out-of-sight scores a first-frame reset as level 1; Insight and IF never return
    assert not S.reanchor_task("OE048_full") and not S.reanchor_task("IF002_chunk_01")
    assert not S.reanchor_task("")
    monkeypatch.setenv("LINGBOT_REANCHOR_TASKS", "GC|OE04")
    assert S.reanchor_task("OE048_full") and not S.reanchor_task("OE058_full")


def test_anchor_y_marks_only_the_returned_latent():
    torch = pytest.importorskip("torch")

    class VAE:
        calls = 0

        def encode(self, videos):
            VAE.calls += 1
            assert videos[0].shape == (3, 5, 16, 16)  # a still clip of the input image
            return [torch.stack([torch.full((16, 2, 2), 1.0), torch.full((16, 2, 2), 7.0)], dim=1)]

    class Pipe:
        device, vae = torch.device("cpu"), VAE()

    s = S.LingBotSession(Pipe(), max_area=1, shift=1.0, stream_decode=False)
    s._img = torch.zeros(3, 1, 16, 16)
    s.y = torch.zeros(20, 8, 2, 2)
    s._anchor_y(5)
    s._anchor_y(6)
    assert VAE.calls == 1  # the anchor latent is encoded once per rollout
    assert (s.y[:4, 5:7] == 1).all() and (s.y[4:, 5:7] == 7).all()
    untouched = torch.cat([s.y[:, :5], s.y[:, 7:]], dim=1)
    assert (untouched == 0).all()
