"""CPU-only tests for --lingbot-split-sink (no GPU, no torch, no API calls)."""
from __future__ import annotations

import contextlib
import math
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import run as R  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402
from adapters.lingbot_world2 import split_sink as SS  # noqa: E402


def test_split_sink_does_not_import_torch():
    proc = subprocess.run(
        [sys.executable, "-c", "import sys; from adapters.lingbot_world2 import split_sink; assert 'torch' not in sys.modules"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_parse_defaults_knobs_env_and_validation():
    cfg, rest = SS.parse(["run.py", "--tasks", "OE047"], environ={})
    assert cfg == SS.SplitSinkConfig() and not cfg.enabled
    assert (cfg.fg_scale, cfg.bg_scale, cfg.fg_frac, cfg.after, cfg.tasks) == (0.25, 1.0, 0.25, 4, "OE")
    assert rest == ["run.py", "--tasks", "OE047"]

    cfg, rest = SS.parse([
        "run.py", "--lingbot-split-sink",
        "--lingbot-split-sink-fg-scale", "0.15",
        "--lingbot-split-sink-bg-scale=0.9",
        "--lingbot-split-sink-fg-frac", "0.3",
        "--lingbot-split-sink-after=6",
        "--lingbot-split-sink-tasks", "OE|GC",
        "--tasks", "OE047",
    ], environ={})
    assert cfg == SS.SplitSinkConfig(True, 0.15, 0.9, 0.3, 6, "OE|GC")
    assert rest == ["run.py", "--tasks", "OE047"]

    env_cfg, _ = SS.parse(["run.py"], environ={
        "LINGBOT_SPLIT_SINK": "1",
        "LINGBOT_SPLIT_SINK_FG_SCALE": "0.2",
        "LINGBOT_SPLIT_SINK_BG_SCALE": "0.8",
        "LINGBOT_SPLIT_SINK_FG_FRAC": "0.4",
        "LINGBOT_SPLIT_SINK_AFTER": "2",
        "LINGBOT_SPLIT_SINK_TASKS": "OE048",
    })
    assert env_cfg == SS.SplitSinkConfig(True, 0.2, 0.8, 0.4, 2, "OE048")

    # Knobs without main flag validate and strip while leaving enabled=False
    off_cfg, rest = SS.parse(["run.py", "--lingbot-split-sink-fg-scale=0.5", "--lingbot-split-sink-bg-scale=0.5", "--x"], environ={})
    assert not off_cfg.enabled and off_cfg.fg_scale == 0.5 and off_cfg.bg_scale == 0.5 and rest == ["run.py", "--x"]

    bad_cases = (
        ["--lingbot-split-sink-fg-scale"],
        ["--lingbot-split-sink-fg-scale", "--tasks"],
        ["--lingbot-split-sink-fg-scale=0"],
        ["--lingbot-split-sink-fg-scale=-0.1"],
        ["--lingbot-split-sink-fg-scale=1.1"],
        ["--lingbot-split-sink-fg-scale=nan"],
        ["--lingbot-split-sink-fg-scale=inf"],
        ["--lingbot-split-sink-fg-scale=abc"],
        ["--lingbot-split-sink-bg-scale=0"],
        ["--lingbot-split-sink-bg-scale=1.2"],
        ["--lingbot-split-sink-bg-scale=abc"],
        ["--lingbot-split-sink-fg-scale=0.8", "--lingbot-split-sink-bg-scale=0.5"],  # fg_scale > bg_scale
        ["--lingbot-split-sink-fg-frac=0"],
        ["--lingbot-split-sink-fg-frac=1"],
        ["--lingbot-split-sink-fg-frac=-0.2"],
        ["--lingbot-split-sink-fg-frac=1.2"],
        ["--lingbot-split-sink-fg-frac=nan"],
        ["--lingbot-split-sink-fg-frac=abc"],
        ["--lingbot-split-sink-after=-1"],
        ["--lingbot-split-sink-after=2.5"],
        ["--lingbot-split-sink-after=abc"],
        ["--lingbot-split-sink-tasks=("],
    )
    for bad in bad_cases:
        with pytest.raises(SystemExit):
            SS.parse(["run.py", "--lingbot-split-sink", *bad], environ={})
        with pytest.raises(SystemExit):  # validated even when main flag is absent
            SS.parse(["run.py", *bad], environ={})


def test_configure_refusals_and_predicates(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)

    flags, rest = R.configure(["run.py", "--tasks", "OE047"], environ={})
    assert flags["split_sink"] == SS.SplitSinkConfig() and rest == ["run.py", "--tasks", "OE047"]

    flags, rest = R.configure(["run.py", "--lingbot-split-sink", "--tasks", "OE047"], environ={})
    assert flags["split_sink"].enabled and rest == ["run.py", "--tasks", "OE047"]

    refusals = (
        (["--lingbot-stateless"], "session mode"),
        (["--lingbot-sink-size", "0"], "no-op arm"),
        (["--lingbot-sink-size", "0", "--lingbot-local-attn", "-1"], "no-op arm"),
        (["--lingbot-sink-key-scale", "0.7"], "sink-key-scale"),
        (["--lingbot-pose-memory"], "pose-memory"),
    )
    for extra, match in refusals:
        with pytest.raises(SystemExit, match=match):
            R.configure(["run.py", "--lingbot-split-sink", *extra], environ={})

    # Knobs without --lingbot-split-sink leave enabled=False and do not trigger refusals
    flags, rest = R.configure(["run.py", "--lingbot-split-sink-after", "6", "--lingbot-stateless"], environ={})
    assert not flags["split_sink"].enabled and flags["split_sink"].after == 6 and rest == ["run.py"]

    cfg = SS.SplitSinkConfig(enabled=True, after=4, tasks="OE")
    assert cfg.applies("OE047_chunk_01") and cfg.applies("OE048_full") and not cfg.applies("GC031_chunk_01")
    assert not SS.SplitSinkConfig().applies("OE047_chunk_01")
    assert [SS.active(cfg, c, 4, 6) for c in (0, 1, 3, 4, 10)] == [False, False, False, True, True]
    early = SS.SplitSinkConfig(enabled=True, after=0, tasks="OE")
    assert [SS.active(early, c, 4, 6) for c in (0, 1, 2)] == [False, False, True]
    assert not SS.active(early, 4, 4, 0) and not SS.active(None, 4, 4, 6)
    assert SS.sink_tokens(6, 1560) == 9360


def test_stationary_camera_localized_quadrant_motion():
    rng = np.random.default_rng(7)
    c_dim, s_len, lat_h, lat_w = 4, 6, 8, 8  # ph=4, pw=4, frame_seqlen=16
    bg = rng.standard_normal((c_dim, 1, lat_h, lat_w)).astype(np.float32)
    latents = np.repeat(bg, s_len, axis=1)
    # Animate ONLY the bottom-right quadrant: latent y in [4..7], x in [4..7] -> patches py in [2..3], px in [2..3]
    for idx in range(1, s_len):
        latents[:, idx, 4:8, 4:8] += float(idx) * 0.8

    poses = np.repeat(np.eye(4, dtype=np.float32)[None], s_len, axis=0)
    cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=1.0, fg_frac=0.25)
    scales, fg_count = SS.compute_sink_scales(latents, poses, cfg)

    assert scales.shape == (s_len * 16,) and scales.dtype == np.float32
    assert fg_count == s_len * 4  # 4 foreground patches per frame across 6 sink frames
    grid = scales.reshape(s_len, 4, 4)
    for idx in range(s_len):
        assert np.all(grid[idx, 2:4, 2:4] == np.float32(0.25))
        assert np.all(grid[idx, :2, :] == np.float32(1.0))
        assert np.all(grid[idx, 2:4, :2] == np.float32(1.0))

    # Even if only a single 2x2 patch moves while fg_frac=0.25 (k=4), static zero-residual quadrants stay bg_scale
    latents_one = np.repeat(bg, s_len, axis=1)
    for idx in range(1, s_len):
        latents_one[:, idx, 6:8, 6:8] += float(idx) * 1.0
    scales_one, fg_one = SS.compute_sink_scales(latents_one, poses, cfg)
    grid_one = scales_one.reshape(s_len, 4, 4)
    assert fg_one == s_len * 1
    for idx in range(s_len):
        assert grid_one[idx, 3, 3] == np.float32(0.25)
        mask = np.ones((4, 4), dtype=bool)
        mask[3, 3] = False
        assert np.all(grid_one[idx][mask] == np.float32(1.0))


def _render_world_background(c2w: np.ndarray, lat_h: int, lat_w: int,
                             intrinsics_480p=P.INTRINSICS_480P) -> np.ndarray:
    """Render a smooth, high-contrast 4-channel spherical texture at camera pose `c2w`."""
    fx0, fy0, cx0, cy0 = intrinsics_480p
    fx, fy = fx0 * (lat_w / 832.0), fy0 * (lat_h / 480.0)
    cx, cy = cx0 * (lat_w / 832.0), cy0 * (lat_h / 480.0)
    xg, yg = np.meshgrid(np.arange(lat_w, dtype=np.float64), np.arange(lat_h, dtype=np.float64))
    d_cam = np.stack([(xg - cx) / fx, (yg - cy) / fy, np.ones_like(xg)], axis=0).reshape(3, -1)
    d_world = (c2w[:3, :3] @ d_cam).reshape(3, lat_h, lat_w)
    yaw = np.arctan2(d_world[0], d_world[2])
    pitch = np.arctan2(d_world[1], np.hypot(d_world[0], d_world[2]))
    return np.stack([
        2.5 * np.sin(5.0 * yaw) * np.cos(4.0 * pitch),
        2.5 * np.cos(6.0 * yaw + 2.0 * pitch),
        2.0 * np.sin(4.0 * yaw - 5.0 * pitch),
        2.0 * np.cos(3.0 * yaw) * np.sin(6.0 * pitch),
    ], axis=0)


def test_panning_camera_homography_cancels_background_and_isolates_foreground():
    s_len, lat_h, lat_w = 6, 32, 48  # ph=16, pw=24, frame_seqlen=384
    ph, pw = lat_h // 2, lat_w // 2
    frame_seqlen = ph * pw

    # Camera pans right 2.5 deg per latent across 0..5 (12.5 deg total pan during the opening sink)
    poses = np.zeros((s_len, 4, 4), dtype=np.float64)
    for idx in range(s_len):
        poses[idx] = np.eye(4)
        poses[idx, :3, :3] = P._rot_y(math.radians(2.5 * idx))

    latents = np.stack([_render_world_background(poses[idx], lat_h, lat_w) for idx in range(s_len)], axis=1)

    # Add an independently evolving/moving foreground blob centered at (y=16, x=28) in frame 0 (patches py=7..8, px=13..14)
    yg, xg = np.mgrid[0:lat_h, 0:lat_w]
    for idx in range(s_len):
        # Foreground subject walks upward in world/screen and changes appearance (unlike the rigid background)
        cy_fg = 16.0 - 1.4 * idx
        cx_fg = 28.0 - 1.2 * idx
        blob = np.exp(-((yg - cy_fg) ** 2 + (xg - cx_fg) ** 2) / (2.0 * 2.0 ** 2))
        latents[:, idx] += (4.0 + 1.5 * idx) * blob[None, :, :]

    # In frame-0 patch coordinates, the blob's vertical trajectory spans py in [3..9] around px in [12..16].
    # Uncompensated frame difference misclassifies static high-gradient background edges outside that corridor:
    uncomp_res = np.mean([np.linalg.norm(latents[:, idx] - latents[:, 0], axis=0) for idx in range(1, s_len)], axis=0)
    uncomp_patch = uncomp_res.reshape(ph, 2, pw, 2).max(axis=(1, 3))
    k = 16  # fg_frac = 16 / 384
    uncomp_py, uncomp_px = np.unravel_index(np.argsort(-uncomp_patch.reshape(-1))[:k], (ph, pw))
    uncomp_on_blob = (uncomp_py >= 2) & (uncomp_py <= 10) & (uncomp_px >= 12) & (uncomp_px <= 16)
    assert not np.all(uncomp_on_blob), "uncompensated frame diff should suffer background pan false positives"

    # Pose-compensated split_sink cancels the rigid pan and isolates ONLY the moving foreground blob's corridor
    cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=1.0, fg_frac=k / frame_seqlen)
    scales, fg_count = SS.compute_sink_scales(latents.astype(np.float32), poses.astype(np.float32), cfg)
    assert scales.shape == (s_len * frame_seqlen,) and fg_count > 0

    grid = (scales == np.float32(0.25)).reshape(s_len, ph, pw)
    fg0_py, fg0_px = np.where(grid[0])
    assert len(fg0_py) == k
    assert np.all((fg0_py >= 2) & (fg0_py <= 10) & (fg0_px >= 12) & (fg0_px <= 16))

    # As the camera pans RIGHT (+yaw), the projected frame-0 foreground region shifts LEFT in camera l's view
    mean_px_0 = float(np.where(grid[0])[1].mean())
    mean_px_5 = float(np.where(grid[5])[1].mean())
    assert mean_px_5 < mean_px_0 - 1.5


def test_static_clip_fallback_and_bank():
    rng = np.random.default_rng(11)
    frame = rng.standard_normal((4, 1, 6, 8)).astype(np.float32)
    latents = np.repeat(frame, 6, axis=1)
    poses = np.repeat(np.eye(4, dtype=np.float32)[None], 6, axis=0)
    cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=0.95, fg_frac=0.25)

    scales, fg_count = SS.compute_sink_scales(latents, poses, cfg)
    assert fg_count == 0
    assert scales.shape == (6 * 12,) and scales.dtype == np.float32
    assert np.all(scales == np.float32(0.95))

    # Single-latent sink (S=1) also falls back cleanly
    s1, fg1 = SS.compute_sink_scales(latents[:, :1], poses[:1], cfg)
    assert fg1 == 0 and s1.shape == (12,) and np.all(s1 == np.float32(0.95))

    # SplitSinkBank accumulates chunk 0 (4 latents) + chunk 1 (2 of 4 latents) for sink=6
    latents_mov = latents.copy()
    latents_mov[:, 2:, 0:2, 0:2] += 3.0
    bank = SS.SplitSinkBank(cfg=cfg, sink=6)
    assert not bank.ready and bank.have == 0
    assert bank.record(latents_mov[:, :4], poses[:4]) == 4
    assert not bank.ready and bank.have == 4
    assert bank.record(latents_mov[:, 4:6], poses[4:6]) == 2
    assert bank.ready and bank.have == 6
    assert bank.record(latents_mov[:, :4], poses[:4]) == 0
    b_scales, b_fg = bank.build()
    d_scales, d_fg = SS.compute_sink_scales(latents_mov, poses, cfg)
    assert b_fg == d_fg == 6 and np.array_equal(b_scales, d_scales)


def test_scale_keys_vector_and_restore_including_mid_loop_exception():
    rng = np.random.default_rng(3)
    kv = [{"k": rng.standard_normal((1, 10, 2, 8)).astype(np.float32), "v": np.zeros((1, 10, 2, 8), np.float32)}
          for _ in range(3)]
    before = [b["k"].copy() for b in kv]
    scales = np.array([0.25, 1.0, 0.25, 1.0, 1.0, 0.25], dtype=np.float32)

    saved = SS.scale_keys_vector(kv, scales)
    for blk, orig in zip(kv, before):
        assert np.array_equal(blk["k"][:, :6], orig[:, :6] * scales[None, :, None, None])
        assert np.array_equal(blk["k"][:, 6:], orig[:, 6:])

    q = rng.standard_normal((4, 8)).astype(np.float32)
    k0, k1 = before[0][0, :, 0], kv[0]["k"][0, :, 0]
    assert np.allclose(q @ k1.T[:, :6], (q @ k0.T[:, :6]) * scales[None, :], atol=1e-6)
    assert np.array_equal(q @ k1.T[:, 6:], q @ k0.T[:, 6:])

    SS.restore_keys(kv, 6, saved)
    assert all(np.array_equal(b["k"], o) for b, o in zip(kv, before))

    # Mid-loop exception during scale_keys_vector still restores every touched block bit-for-bit
    class _BoomArray:
        def __getitem__(self, idx):
            return before[1][idx]

        def __setitem__(self, idx, val):
            raise RuntimeError("mid-block boom")

    kv_boom = [{"k": before[0].copy()}, {"k": _BoomArray()}, {"k": before[2].copy()}]
    partial_saved = []
    with pytest.raises(RuntimeError, match="mid-block boom"):
        SS.scale_keys_vector(kv_boom, scales, partial_saved)
    assert len(partial_saved) == 2
    # Restore block 0 from partial_saved[0]
    SS.restore_keys(kv_boom[:1], 6, partial_saved[:1])
    assert np.array_equal(kv_boom[0]["k"], before[0])
    assert np.array_equal(kv_boom[2]["k"], before[2])


class _T:
    def __init__(self, arr):
        self.arr = np.asarray(arr, dtype=np.float32)
        self.shape, self.device, self.dtype = self.arr.shape, "cpu", "f32"

    def detach(self):
        return self

    def float(self):
        return self

    def to(self, d):
        return _T(self.arr.astype(d)) if d is np.uint8 else self

    def clamp(self, lo, hi):
        return _T(np.clip(self.arr, lo, hi))

    def __add__(self, o):
        return _T(self.arr + (o.arr if isinstance(o, _T) else o))

    def __mul__(self, o):
        return _T(self.arr * (o.arr if isinstance(o, _T) else o))

    def round(self):
        return _T(np.round(self.arr))

    def permute(self, *ax):
        return _T(np.transpose(self.arr, ax))

    def cpu(self):
        return self

    def numpy(self):
        return self.arr


def _make_session(monkeypatch, cfg: SS.SplitSinkConfig | None, *, armed: bool = True, sink: int = 6,
                  fail_at: int | None = None, yaw_gain: tuple[float, float] | None = None):
    nc = lambda *a, **kw: contextlib.nullcontext()  # noqa: E731
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8,
        randn=lambda *s, **kw: _T(np.zeros(s[0] if isinstance(s[0], tuple) else s, dtype=np.float32)),
        stack=lambda xs: _T([x for x in xs]),
        cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim)),
    ))
    lat_h, lat_w = 4, 4  # ph=2, pw=2, frame_seqlen=4
    fs = (lat_h // 2) * (lat_w // 2)
    rng = np.random.default_rng(19)
    kv = [{"k": rng.standard_normal((1, 80, 2, 4)).astype(np.float32), "v": np.zeros((1, 80, 2, 4), np.float32)}
          for _ in range(2)]
    pristine = [b["k"].copy() for b in kv]
    calls = []

    def model(x, t, **kw):
        call_idx = len(calls)
        cid = kw["current_start"] // (4 * fs)
        t_val = float(t.arr[0])
        n_sink = sink * fs
        k_snapshots = [b["k"][:, :n_sink].copy() for b in kw["kv_cache"]]
        tail_untouched = all(np.array_equal(b["k"][:, n_sink:], p[:, n_sink:]) for b, p in zip(kw["kv_cache"], pristine))
        calls.append((cid, t_val, k_snapshots, tail_untouched))
        if fail_at is not None and call_idx == fail_at:
            raise RuntimeError("denoise boom")
        # Return clean x0 whose top-left 2x2 patch (patch 0) moves across chunk 0..1 while other patches stay 0
        out = np.zeros((16, 4, lat_h, lat_w), dtype=np.float32)
        if cid == 1:
            out[:, :, 0:2, 0:2] = 5.0
        return [_T(out)]

    pipe = SimpleNamespace(
        device="cpu", param_dtype="bf16", sink_size=sink, model=model,
        _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred,
        scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0),
    )
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True,
                            **({"split_sink": cfg} if cfg is not None else {}))
    track = S.PoseTrack(yaw_gain=yaw_gain)

    sess.started, sess.track, sess.y = True, track, np.zeros((20, 64, lat_h, lat_w), dtype=np.float32)
    sess.lat_h, sess.lat_w, sess.frame_seqlen = lat_h, lat_w, fs
    sess.max_seq_len, sess.kv_size = 4 * fs, 80
    sess.context, sess.kv, sess.cross, sess.cross_init, sess.gen = ["c"], kv, [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",))
    sess._decode = lambda lat: _T(np.zeros((3, 29, 2, 2), dtype=np.float32))
    sess.split_sink_on = bool(cfg is not None and armed)
    return sess, calls, kv, pristine


def test_session_scales_denoise_only_restores_before_kv_write_and_reuses_mask(monkeypatch, capsys):
    cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=1.0, fg_frac=0.25, after=4, tasks="OE")
    sess, calls, kv, pristine = _make_session(monkeypatch, cfg, armed=True, sink=6)
    sess.step(["none"] * 28)  # chunks 0, 1 (populates 4 + 2 = 6 sink latents)
    sess.step(["none"] * 32)  # chunks 2, 3 (still < after=4)
    sess.step(["none"] * 32)  # chunks 4, 5 (active!)
    out = capsys.readouterr().out
    assert out.count("[lingbot] split-sink: built spatial mask") == 1

    # 6 sink latents x 4 patches = 24 tokens; patch 0 of each latent gets 0.25, patches 1..3 get 1.0
    expected_scales = np.tile(np.array([0.25, 1.0, 1.0, 1.0], dtype=np.float32), 6)[None, :, None, None]
    assert sess.split_sink_chunks == 2
    assert sess.split_sink_fg_tokens == 6  # incremented once across the rollout

    assert len(calls) == 6 * 5
    for cid, t_val, k_snaps, tail_ok in calls:
        assert tail_ok
        if cid >= 4 and t_val > 0.0:
            for snap, p in zip(k_snaps, pristine):
                assert np.array_equal(snap, p[:, :24] * expected_scales)
        else:
            # Chunks < 4 AND every clean t=0 KV write see bit-identical pristine sink keys
            for snap, p in zip(k_snaps, pristine):
                assert np.array_equal(snap, p[:, :24])

    assert all(np.array_equal(b["k"], p) for b, p in zip(kv, pristine))


def test_session_restores_pristine_keys_on_denoise_exception(monkeypatch):
    cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=1.0, fg_frac=0.25, after=2, tasks="OE")
    # Chunk 0 (5 calls) + Chunk 1 (5 calls) = 10 calls; fail on second denoise step of Chunk 2 (call index 11)
    sess, _, kv, pristine = _make_session(monkeypatch, cfg, armed=True, sink=6, fail_at=2 * 5 + 1)
    sess.step(["none"] * 28)
    with pytest.raises(RuntimeError, match="denoise boom"):
        sess.step(["none"] * 16)
    assert sess.split_sink_chunks == 1
    assert all(np.array_equal(b["k"], p) for b, p in zip(kv, pristine))


def test_session_records_yaw_gain_scaled_model_latents_from_real_pose_track(monkeypatch):
    P.reset({})
    try:
        P.calibrate(True, 0, 20)  # 22.5 deg per 20-frame token -> 4.5 deg per 4-frame latent step
        cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=1.0, fg_frac=0.25, after=2, tasks="OE")

        # 1) Single 2-chunk step across a right turn with non-unit yaw_gain=(1.0, 1.5)
        sess, _, _, _ = _make_session(monkeypatch, cfg, armed=True, sink=6, yaw_gain=(1.0, 1.5))
        sess.step(["l"] * 28)
        assert len(sess._ss_poses) == 6
        step_rad = 4.0 * P.YAW
        for idx, pose in enumerate(sess._ss_poses):
            expected_model_r = P._rot_y(1.5 * idx * step_rad)
            intended_r = P._rot_y(1.0 * idx * step_rad)
            assert np.allclose(pose[:3, :3], expected_model_r, atol=1e-6)
            assert np.allclose(sess.track.latents[idx, :3, :3], intended_r, atol=1e-6)
            if idx > 0:
                assert not np.allclose(pose[:3, :3], sess.track.latents[idx, :3, :3], atol=1e-3)

        # 2) Per-chunk opening steps with changing yaw_gain (as --lingbot-yaw-servo does)
        sess2, _, _, _ = _make_session(monkeypatch, cfg, armed=True, sink=6, yaw_gain=(1.5, 1.0))
        sess2.step(["j"] * 12)  # chunk 0: latents 0..3 at left gain 1.5
        sess2.track.yaw_gain = (0.75, 1.0)
        sess2.step(["j"] * 16)  # chunk 1: latents 4..5 continue from chunk 0's model pose at left gain 0.75
        assert len(sess2._ss_poses) == 6
        expected_angles = [0.0, -1.5 * step_rad, -3.0 * step_rad, -4.5 * step_rad,
                           -(4.5 + 0.75) * step_rad, -(4.5 + 1.5) * step_rad]
        for idx, (pose, ang) in enumerate(zip(sess2._ss_poses, expected_angles)):
            assert np.allclose(pose[:3, :3], P._rot_y(ang), atol=1e-6), f"latent {idx} mismatch"
            if idx > 0:
                intended_ang = -1.0 * idx * step_rad
                assert not np.allclose(pose[:3, :3], P._rot_y(intended_ang), atol=1e-3)
    finally:
        P.reset({})


def test_session_unmatched_task_and_flag_off_are_bit_identical(monkeypatch):
    cfg = SS.SplitSinkConfig(enabled=True, fg_scale=0.25, bg_scale=1.0, fg_frac=0.25, after=2, tasks="OE")
    sess_off, calls_off, kv_off, pristine_off = _make_session(monkeypatch, None, armed=False, sink=6)
    sess_skip, calls_skip, kv_skip, pristine_skip = _make_session(monkeypatch, cfg, armed=False, sink=6)

    f_off = sess_off.step(["none"] * 60)
    f_skip = sess_skip.step(["none"] * 60)
    assert np.array_equal(f_off, f_skip)
    assert sess_skip.split_sink_chunks == 0 and sess_skip.split_sink_fg_tokens == 0
    assert sess_skip._ss_poses == [] and sess_skip._ss_latents == [] and sess_skip._ss_scales is None
    for (_, _, snaps_off, _), (_, _, snaps_skip, _) in zip(calls_off, calls_skip):
        assert all(np.array_equal(a, b) for a, b in zip(snaps_off, snaps_skip))
    assert all(np.array_equal(b["k"], p) for b, p in zip(kv_off, pristine_off))
    assert all(np.array_equal(b["k"], p) for b, p in zip(kv_skip, pristine_skip))


def test_flag_stats_and_multi_arm_main_isolation(monkeypatch, capsys, tmp_path):
    off = F.FlagStats(False, "goal", False, False)
    assert "split_sink" not in off.summary("OE047") and "split_sink" not in off.total_line()

    on = F.FlagStats(False, "goal", False, False, split_sink=True)
    on.split_sink_armed()
    on.split_sink_counted(22, 390)
    s = on.finish_task("OE047")
    assert (s["split_sink"], s["split_sink_chunks"], s["split_sink_fg_tokens"]) == ("on", 22, 390)
    on.new_task()
    s_gc = on.finish_task("GC031")
    assert (s_gc["split_sink"], s_gc["split_sink_chunks"], s_gc["split_sink_fg_tokens"]) == ("skip", 0, 0)
    assert on.total_line().endswith(" split_sink_chunks=22 split_sink_fg_tokens=390")
    capsys.readouterr()

    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    pipe = SimpleNamespace(model=SimpleNamespace(blocks=[]), _t5_cache={}, local_attn_size=18, sink_size=6)
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        ra = SimpleNamespace(decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")

        def run_task(task, eng, out, args):
            if eng.session is not None:
                eng.session.reset = lambda *a, **kw: (setattr(eng.session, "started", True),
                                                      setattr(eng.session, "track", S.PoseTrack()))

                def fake_step(keys, **kw):
                    if eng.session.split_sink_on:
                        if eng.session.split_sink_chunks == 0:
                            eng.session.split_sink_fg_tokens += 390
                        eng.session.split_sink_chunks += 1
                    return np.zeros((29, 2, 2, 3), np.uint8)

                eng.session.step = fake_step
                monkeypatch.setitem(sys.modules, "imageio", SimpleNamespace(mimsave=lambda *a, **kw: None))
                monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
                    reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
                monkeypatch.setitem(sys.modules, "PIL", SimpleNamespace(Image=SimpleNamespace(
                    open=lambda p: SimpleNamespace(convert=lambda m: None))))
                for i in (1, 2):
                    eng._generate_session("img.jpg", "p", "none-33", str(tmp_path), f"{task['task_id']}_chunk_{i:02d}", 33)
            return {"task_id": task["task_id"], "success": True}

        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16))
            seen.append(eng.session.split_sink if eng.session else "stateless")
            for tid in ("OE047", "GC031"):
                ra.run_task({"task_id": tid}, eng, tmp_path, None)

        ra.run_task, ra.main = run_task, run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    arms = [[], ["--lingbot-split-sink"], [], []]
    outs = []
    for k, extra in enumerate(arms):
        assert R.main(["run.py", *extra]) == 0
        outs.append(capsys.readouterr().out.splitlines())
        if k == 1:
            for bad in (["--lingbot-stateless"], ["--lingbot-sink-size", "0"],
                        ["--lingbot-sink-key-scale", "0.7"], ["--lingbot-pose-memory"]):
                with pytest.raises(SystemExit):
                    R.main(["run.py", "--lingbot-split-sink", *bad])

    lines = [[ln for ln in o if ln.startswith("[lingbot] flags ")] for o in outs]
    modes = [[ln for ln in o if ln.startswith("[lingbot] mode:")][0] for o in outs]
    assert seen[0] is None and seen[1] == SS.SplitSinkConfig(enabled=True) and seen[2] is None and seen[3] is None
    assert lines[0] == lines[2] == lines[3] and modes[0] == modes[2] == modes[3]
    assert not any("split" in ln or "sink" in ln for ln in lines[0] + [modes[0]])
    assert "split sink fg 0.25 bg 1 frac 0.25 from chunk 4 tasks 'OE'" in modes[1]
    assert lines[1][0].startswith(lines[0][0] + " ")
    assert lines[1][0].endswith("split_sink=on split_sink_chunks=2 split_sink_fg_tokens=390")
    assert lines[1][1].endswith("split_sink=skip split_sink_chunks=0 split_sink_fg_tokens=0")
    assert lines[1][2].endswith(" split_sink_chunks=2 split_sink_fg_tokens=390")
    assert not R.SPLIT_SINK.enabled
