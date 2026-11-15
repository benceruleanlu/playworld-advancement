"""CPU unit and integration tests for homography-warped spatial y view re-anchoring (--lingbot-warp-reanchor).
Runs without GPU, Modal, API keys, or real torch installed."""
from __future__ import annotations

import contextlib
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from adapters.common import agent_api
from adapters.lingbot_world2 import flag_stats
from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import run as R
from adapters.lingbot_world2 import session as S
from adapters.lingbot_world2 import warp_reanchor as WR
from tests.test_lingbot_weight_mod import _dit


def test_no_top_level_torch_in_warp_reanchor():
    assert "torch" not in WR.__dict__


# ------------------------------------------------------------ CLI & env parsing

def test_parse_defaults_and_knobs():
    cfg, rest = WR.parse(["run.py", "--tasks", "GC033"], {})
    assert cfg == WR.WarpReanchorConfig() and not cfg.enabled
    assert rest == ["run.py", "--tasks", "GC033"]

    cfg_on, rest_on = WR.parse([
        "run.py",
        "--lingbot-warp-reanchor",
        "--lingbot-warp-max-deg", "35",
        "--lingbot-warp-max-trans=10.5",
        "--lingbot-warp-leave-deg", "20",
        "--lingbot-warp-leave-trans=6",
        "--lingbot-warp-focus", "16",
        "--lingbot-warp-erode=2",
        "--lingbot-warp-tasks", "GC|OE034",
        "--keep-me",
    ], {})
    assert rest_on == ["run.py", "--keep-me"]
    assert cfg_on == WR.WarpReanchorConfig(
        enabled=True, max_deg=35.0, max_trans=10.5,
        leave_deg=20.0, leave_trans=6.0, focus=16.0, erode=2, tasks="GC|OE034",
    )
    assert cfg_on.applies("GC036_chunk_04") and cfg_on.applies("OE034_full")
    assert not cfg_on.applies("OE048_chunk_01") and not cfg_on.applies("IF001_chunk_01")
    assert "focus 16" in cfg_on.describe() and "erode 2" in cfg_on.describe()


def test_parse_env_and_knob_without_enable():
    env = {
        "LINGBOT_WARP_REANCHOR": "1",
        "LINGBOT_WARP_MAX_DEG": "48",
        "LINGBOT_WARP_MAX_TRANS": "9",
        "LINGBOT_WARP_LEAVE_DEG": "28",
        "LINGBOT_WARP_LEAVE_TRANS": "5",
        "LINGBOT_WARP_FOCUS": "0",
        "LINGBOT_WARP_ERODE": "0",
        "LINGBOT_WARP_TASKS": "GC03",
    }
    cfg, rest = WR.parse(["--lingbot-warp-max-deg=36"], env)
    assert rest == [] and cfg.enabled and cfg.max_deg == 36.0 and cfg.max_trans == 9.0
    assert cfg.leave_deg == 28.0 and cfg.leave_trans == 5.0 and cfg.erode == 0
    assert "focus inf" in cfg.describe()

    # Knobs passed without --lingbot-warp-reanchor validate & strip while keeping enabled=False.
    cfg_dark, rest_dark = WR.parse(["--lingbot-warp-max-deg", "30", "--other"], {})
    assert not cfg_dark.enabled and cfg_dark.max_deg == 30.0 and rest_dark == ["--other"]
    assert not cfg_dark.applies("GC033_chunk_01")


@pytest.mark.parametrize("argv, match", [
    (["--lingbot-warp-max-deg"], "needs a value"),
    (["--lingbot-warp-max-deg", "--next"], "needs a value"),
    (["--lingbot-warp-max-deg=abc"], "must be a float"),
    (["--lingbot-warp-max-deg=nan"], "must be finite"),
    (["--lingbot-warp-max-deg=0"], r"\(0.0, 75.0\]"),
    (["--lingbot-warp-max-deg=76"], r"\(0.0, 75.0\]"),
    (["--lingbot-warp-leave-deg=0"], r"\(0.0, 180.0\]"),
    (["--lingbot-warp-leave-deg=185"], r"\(0.0, 180.0\]"),
    (["--lingbot-warp-max-trans=-1"], r"\[0.0,"),
    (["--lingbot-warp-leave-trans=-0.1"], r"\[0.0,"),
    (["--lingbot-warp-focus=-2"], r"\[0.0,"),
    (["--lingbot-warp-erode=-1"], r"\[0, 8\]"),
    (["--lingbot-warp-erode=9"], r"\[0, 8\]"),
    (["--lingbot-warp-erode=1.5"], "must be a int"),
    (["--lingbot-warp-tasks=["], "valid regex"),
])
def test_parse_rejects_bad_values(argv, match):
    with pytest.raises(SystemExit, match=match):
        WR.parse(["--lingbot-warp-reanchor", *argv], {})


@pytest.mark.parametrize("extra, match", [
    (["--lingbot-stateless"], "session mode"),
    (["--lingbot-reanchor"], "both write return latents"),
    (["--lingbot-pose-memory"], "both target view returns"),
])
def test_configure_refuses_incompatible_flags(monkeypatch, extra, match):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    with pytest.raises(SystemExit, match=match):
        R.configure(["run.py", "--lingbot-warp-reanchor", *extra], {})


# --------------------------------------------------------- geometry & masks

def _c2w_yaw(deg: float, trans=(0.0, 0.0, 0.0)) -> np.ndarray:
    m = np.eye(4, dtype=np.float64)
    m[:3, :3] = P._rot_y(math.radians(deg))
    m[:3, 3] = trans
    return m


def test_identity_projection_and_mask_100_percent_with_erosion():
    h, w = 480, 832
    lat_h, lat_w = h // 8, w // 8
    uv0, valid = WR.project_to_start(np.eye(4), P.INTRINSICS_480P, h, w, focus=0.0)
    assert uv0.shape == (h, w, 2) and valid.shape == (h, w)
    assert valid.all()

    gx = 2.0 * np.arange(w, dtype=np.float64) / (w - 1) - 1.0
    gy = 2.0 * np.arange(h, dtype=np.float64) / (h - 1) - 1.0
    want = np.stack(np.meshgrid(gx, gy), axis=-1)
    assert np.max(np.abs(uv0 - want)) < 1e-12

    for erode in (0, 1, 2):
        mask = WR.latent_valid_mask(valid, lat_h, lat_w, erode=erode)
        assert mask.shape == (lat_h, lat_w) and mask.dtype == np.float32
        assert np.all(mask == 1.0)


def test_pan_30_deg_sides_erosion_and_monotonic_overlap():
    h, w = 480, 832
    lat_h, lat_w = 60, 104

    # Left pan (-30 deg yaw): left image columns look into newly exposed space (0.0),
    # right image columns look back into frame 0 (1.0), and outer right border is NOT eroded.
    _, valid_l = WR.project_to_start(_c2w_yaw(-30.0), P.INTRINSICS_480P, h, w)
    m_l0 = WR.latent_valid_mask(valid_l, lat_h, lat_w, erode=0)
    m_l1 = WR.latent_valid_mask(valid_l, lat_h, lat_w, erode=1)
    assert np.all(m_l1[:, 0] == 0.0)
    assert np.all(m_l1[:, -1] == 1.0)  # outer frame border stays 1.0 even with erode=1
    assert 0 < int(m_l1.sum()) < int(m_l0.sum()) < lat_h * lat_w
    # Interior frustum boundary (vertical cut + keystone top/bottom tilt) is eroded, while outer border stays 1.0.
    assert lat_h <= int(m_l0.sum()) - int(m_l1.sum()) <= 3 * lat_h

    # Right pan (+30 deg yaw): horizontal mirror up to cx=w/2 vs (w-1)/2 half-pixel convention.
    _, valid_r = WR.project_to_start(_c2w_yaw(30.0), P.INTRINSICS_480P, h, w)
    m_r1 = WR.latent_valid_mask(valid_r, lat_h, lat_w, erode=1)
    assert np.all(m_r1[:, 0] == 1.0) and np.all(m_r1[:, -1] == 0.0)
    assert abs(int(m_r1.sum()) - int(m_l1.sum())) <= 2

    # Overlap grows monotonically as camera approaches start pose: 45 -> 30 -> 15 -> 0 deg.
    counts = []
    for deg in (45.0, 30.0, 15.0, 0.0):
        _, vp = WR.project_to_start(_c2w_yaw(deg), P.INTRINSICS_480P, h, w)
        counts.append(int(WR.latent_valid_mask(vp, lat_h, lat_w, erode=1).sum()))
    assert counts[0] < counts[1] < counts[2] < counts[3] == lat_h * lat_w


def test_pan_90_deg_zero_overlap_and_no_nan():
    h, w = 480, 832
    for sign in (-1.0, 1.0):
        uv0, valid = WR.project_to_start(_c2w_yaw(sign * 90.0), P.INTRINSICS_480P, h, w)
        assert np.isfinite(uv0).all()
        assert uv0.min() >= -1.0 and uv0.max() <= 1.0
        mask = WR.latent_valid_mask(valid, h // 8, w // 8, erode=1)
        assert int(mask.sum()) == 0


def test_focus_depth_reprojects_orbit_center_landmark():
    """Camera orbits at radius focus=16 around [0, 0, 16] by theta=25 deg:
    with focus=16, the target center pixel maps back to start frame center; with focus=0 it misses."""
    h, w = 160, 256
    fx, fy, cx, cy = 128.0, 128.0, (w - 1) / 2.0, (h - 1) / 2.0
    focus = 16.0
    theta = math.radians(25.0)
    c2w = np.eye(4, dtype=np.float64)
    c2w[:3, :3] = P._rot_y(-theta)
    c2w[:3, 3] = (focus * math.sin(theta), 0.0, focus * (1.0 - math.cos(theta)))

    uv_inf, _ = WR.project_to_start(c2w, (fx, fy, cx, cy), h, w, focus=0.0)
    uv_foc, valid_foc = WR.project_to_start(c2w, (fx, fy, cx, cy), h, w, focus=focus)

    ic, jc = round(cy), round(cx)
    assert valid_foc[ic, jc]
    assert abs(uv_foc[ic, jc, 0]) < 0.01 and abs(uv_foc[ic, jc, 1]) < 0.01
    assert abs(uv_inf[ic, jc, 0]) > 0.35  # pure rotational homography misses by ~55 px


def test_latent_valid_mask_rejects_non_divisible_shape():
    with pytest.raises(ValueError, match="not divisible"):
        WR.latent_valid_mask(np.ones((15, 16), dtype=bool), 2, 2)


# -------------------------------------------------------------- WarpTracker

def test_tracker_never_false_anchors_on_outbound_walk_or_pan():
    tracker = WR.WarpTracker(WR.WarpReanchorConfig(enabled=True))
    # Outbound walk: translation grows monotonically 0 -> 2 -> 4 -> ... -> 20 (crosses leave_trans=8 while < max_trans=12).
    walk = np.stack([_c2w_yaw(0.0, (0.0, 0.0, float(k))) for k in range(12)])
    assert tracker.select_chunk_anchors(walk, start_lat=0, chunk_size=4) == []
    assert tracker.away and not tracker.parked

    # Outbound pan: yaw grows 0 -> 10 -> 20 -> 28 -> 35 -> 45 -> 60.
    tracker.reset()
    pan = np.stack([_c2w_yaw(d) for d in (0, 5, 10, 15, 20, 26, 32, 38, 45, 52, 60, 65)])
    assert tracker.select_chunk_anchors(pan, start_lat=0, chunk_size=4) == []


def test_tracker_picks_one_best_per_chunk_and_latches_parked_tail():
    cfg = WR.WarpReanchorConfig(enabled=True)
    tracker = WR.WarpTracker(cfg)

    # Chunk 0 (g=0..3): outbound 0 -> 30 deg (crosses leave_deg=25, never anchors g=0 or outbound).
    c0 = np.stack([_c2w_yaw(d) for d in (0.0, 10.0, 20.0, 30.0)])
    # Chunk 1 (g=4..7): turn around 45 -> 38 -> 30 -> 22 deg -> approaches in g=5,6,7, best is g=7 (22 deg).
    c1 = np.stack([_c2w_yaw(d) for d in (45.0, 38.0, 30.0, 22.0)])
    # Chunk 2 (g=8..11): 15 -> 8 -> 2 -> 0 deg -> best is g=11 (0 deg <= 1.0 -> latches parked!).
    c2 = np.stack([_c2w_yaw(d) for d in (15.0, 8.0, 2.0, 0.0)])
    # Chunks 3 & 4 (g=12..19): stationary WAIT tail at 0 deg -> parked suppresses all repeats.
    c34 = np.stack([_c2w_yaw(0.0) for _ in range(8)])

    got = tracker.select_chunk_anchors(np.concatenate([c0, c1, c2, c34], axis=0), start_lat=0, chunk_size=4)
    assert [g for g, _, _ in got] == [7, 11]
    assert tracker.parked

    # Second excursion: leaves again (0 -> 15 -> 30 -> 35) then returns (25 -> 10 -> 0 -> 0).
    c5 = np.stack([_c2w_yaw(d) for d in (5.0, 15.0, 30.0, 35.0)])
    c6 = np.stack([_c2w_yaw(d) for d in (25.0, 10.0, 0.0, 0.0)])
    got2 = tracker.select_chunk_anchors(np.concatenate([c5, c6], axis=0), start_lat=20, chunk_size=4)
    # In c6: g=24 (25 deg, approaching), g=25 (10 deg, approaching), g=26 (0 deg, approaching, score 0), g=27 (0 deg, not < 0).
    assert [g for g, _, _ in got2] == [26]
    assert tracker.parked


# -------------------------------------------- fake torch + session rollout

class _A(np.ndarray):
    """Numpy array stand-in for torch.Tensor supporting session.step and _warp_anchor_y."""
    device = "cpu"

    def to(self, *a, **kw):
        dt = kw.get("dtype")
        if isinstance(dt, (type, np.dtype)):
            return self.astype(dt).view(_A)
        return self

    def detach(self):
        return self

    def cpu(self):
        return self

    def float(self):
        return self.astype(np.float32).view(_A)

    def numpy(self):
        return np.asarray(self)

    def clone(self):
        return np.array(self, copy=True).view(_A)

    def fill_(self, v):
        self.fill(v)
        return self

    def unsqueeze(self, dim):
        return np.expand_dims(self, dim).view(_A)

    def permute(self, *ax):
        return np.transpose(self, ax).view(_A)

    def repeat(self, *sizes):
        return np.tile(np.asarray(self), sizes).view(_A)

    def chunk(self, n, dim=0):
        return tuple(x.view(_A) for x in np.array_split(self, n, axis=dim))


def _a(x) -> _A:
    return np.asarray(x).view(_A)


def _grid_sample_np(img, grid, mode="bilinear", padding_mode="border", align_corners=True):
    assert mode == "bilinear" and padding_mode == "border" and align_corners is True
    arr = np.asarray(img, dtype=np.float32)  # [N, C, H, W]
    g = np.asarray(grid, dtype=np.float32)   # [N, Ho, Wo, 2]
    n, _, h, w = arr.shape
    gx = np.clip((g[..., 0] + 1.0) * 0.5 * (w - 1), 0.0, w - 1)
    gy = np.clip((g[..., 1] + 1.0) * 0.5 * (h - 1), 0.0, h - 1)
    x0 = np.floor(gx).astype(np.int64)
    y0 = np.floor(gy).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    wx = (gx - x0)[..., None]
    wy = (gy - y0)[..., None]
    nhwc = np.transpose(arr, (0, 2, 3, 1))
    b = np.arange(n)[:, None, None]
    v00 = nhwc[b, y0, x0]
    v01 = nhwc[b, y0, x1]
    v10 = nhwc[b, y1, x0]
    v11 = nhwc[b, y1, x1]
    out = (1.0 - wy) * ((1.0 - wx) * v00 + wx * v01) + wy * ((1.0 - wx) * v10 + wx * v11)
    return np.transpose(out, (0, 3, 1, 2)).astype(np.float32).view(_A)


def _fake_torch(counter, grid_calls):
    nc = lambda *a, **kw: contextlib.nullcontext()  # noqa: E731

    def randn(*shape, **kw):
        shape = shape[0] if isinstance(shape[0], tuple) else shape
        counter[0] += 1
        return _a(np.full(shape, float(counter[0]), dtype=np.float32))

    def gs(img, grid, **kw):
        grid_calls.append(np.array(grid, copy=True))
        return _grid_sample_np(img, grid, **kw)

    return SimpleNamespace(
        amp=SimpleNamespace(autocast=nc),
        autocast=nc,
        no_grad=nc,
        float32=np.float32,
        uint8=np.uint8,
        long=np.int64,
        cuda=SimpleNamespace(is_available=lambda: False, synchronize=lambda: None),
        randn=randn,
        from_numpy=lambda arr: _a(np.asarray(arr)),
        stack=lambda xs: _a(np.array([float(x) for x in xs], dtype=np.float32)),
        cat=lambda xs, dim=0: _a(np.concatenate([np.asarray(x) for x in xs], axis=dim)),
        nn=SimpleNamespace(functional=SimpleNamespace(grid_sample=gs)),
    )


def _make_session(monkeypatch, cfg=None, on=True, lat_h=6, lat_w=10):
    counter = [0]
    grid_calls = []
    vae_calls = []
    dit_y = []
    monkeypatch.setitem(sys.modules, "torch", _fake_torch(counter, grid_calls))

    h, w = lat_h * 8, lat_w * 8
    fx = P.INTRINSICS_480P[0] * (w / 832.0)
    fy = P.INTRINSICS_480P[1] * (h / 480.0)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0

    def vae_encode(videos):
        vid = np.asarray(videos[0], dtype=np.float32)  # [3, 5, h, w]
        vae_calls.append(vid.copy())
        n_lat = (vid.shape[1] - 1) // 4 + 1
        out = np.zeros((16, n_lat, lat_h, lat_w), dtype=np.float32)
        for t in range(n_lat):
            frame = vid[:, 0] if t == 0 else vid[:, 4 * t - 3 : 4 * t + 1].mean(axis=1)
            patch = frame.reshape(3, lat_h, 8, lat_w, 8).mean(axis=(2, 4))
            out[:3, t] = patch + 10.0  # distinct from baseline y[4:] = -0.5
            out[3:, t] = 7.0
        return [_a(out)]

    def model(x, t, y, current_start, frame_seqlen, **kw):
        dit_y.append((current_start // frame_seqlen, float(np.asarray(t)[0]), np.array(y[0], copy=True)))
        return x

    pipe = SimpleNamespace(
        device="cpu",
        param_dtype="bf16",
        sink_size=6,
        local_attn_size=18,
        vae=SimpleNamespace(encode=vae_encode),
        model=model,
        _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred,
        scheduler=SimpleNamespace(add_noise=lambda x0, noise, t: noise),
    )
    sess = S.LingBotSession(pipe, h * w, 5.0, stream_decode=True,
                            **({"warp_reanchor": cfg} if cfg is not None else {}))
    sess.started = True
    sess.track = S.PoseTrack()
    sess.h, sess.w = h, w
    sess.lat_h, sess.lat_w = lat_h, lat_w
    sess.frame_seqlen = lat_h * lat_w // 4
    sess.max_seq_len = 4 * sess.frame_seqlen
    sess.Ks = _a(np.array([[fx, fy, cx, cy]], dtype=np.float32))
    # Ramp image across columns so horizontal warps shift pixel intensity predictably.
    ramp = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, None, None, :]
    sess._img = _a(np.broadcast_to(ramp, (3, 1, h, w)).copy())

    n_lat = 64
    y_arr = np.zeros((20, n_lat, lat_h, lat_w), dtype=np.float32)
    y_arr[:4, 0] = 1.0
    y_arr[4:, 0] = 10.0
    y_arr[4:, 1:] = -0.5  # non-zero baseline VAE(zeros) latent; must stay -0.5 on unmasked patches!
    sess.y = _a(y_arr)

    sess.kv_size = 18 * sess.frame_seqlen
    sess.kv = []
    sess.context, sess.cross, sess.cross_init, sess.gen = ["ctx"], [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: _a(np.zeros((1, 1, len(r), lat_h, lat_w), dtype=np.float32))
    sess._decode = lambda lat: _a(np.zeros((3, 4 * lat.shape[1], h, w), dtype=np.uint8))
    sess.warp_reanchor_on = on
    return sess, dit_y, vae_calls, grid_calls, counter


def test_session_progressive_warp_reanchor_preserves_unmasked_and_latches_tail(monkeypatch, capsys):
    # Make each 16-frame chunk turn 24 deg (1.5 deg / pixel frame).
    monkeypatch.setattr(P, "YAW", math.radians(1.5))
    cfg = WR.WarpReanchorConfig(enabled=True, max_deg=40.0, leave_deg=25.0, erode=1)
    sess, dit_y, vae_calls, grid_calls, _ = _make_session(monkeypatch, cfg=cfg, on=True)
    total = sess.lat_h * sess.lat_w  # 60

    # Step 0 (2 chunks = 28 keys -> latents 0..7): right turn 'l' * 28 -> 0..42 deg (outbound only!).
    sess.step(["l"] * 28)
    assert sess.warp_events == 0 and len(vae_calls) == 0

    # Step 1 (1 chunk = 16 keys -> latents 8..11): turn back left 'j' * 16 -> 42 -> 36 -> 30 -> 24 -> 18 deg.
    # Latent 11 is at ~18 deg: partial overlap!
    sess.step(["j"] * 16)
    assert sess.warp_events == 1 and len(vae_calls) == 1 and len(grid_calls) == 1
    assert 11 in sess._anchored
    y_g11 = np.asarray(sess.y[:, 11])
    mask_11 = y_g11[0]
    n_valid_11 = int(mask_11.sum())
    assert 0 < n_valid_11 < total
    # All 4 mask channels match, valid patches carry warped VAE (> 5.0), invalid patches keep -0.5!
    for ch in range(4):
        assert np.array_equal(y_g11[ch], mask_11)
    assert np.all(y_g11[4:, mask_11 == 1.0] > 5.0)
    assert np.all(y_g11[4:, mask_11 == 0.0] == -0.5)
    # Other latents in chunk 2 (8, 9, 10) stay untouched (mask 0, y[4:] == -0.5).
    for g_other in (8, 9, 10):
        assert np.all(np.asarray(sess.y[:4, g_other]) == 0.0)
        assert np.all(np.asarray(sess.y[4:, g_other]) == -0.5)

    # Step 2 (1 chunk = 16 keys -> latents 12..15): 'j' * 12 + 'none' * 4 -> reaches 0 deg at latent 14 (frame 56)!
    sess.step(["j"] * 12 + ["none"] * 4)
    assert sess.warp_events == 2 and len(vae_calls) == 2
    assert len(grid_calls) == 1  # exact 0 deg reused/populated self._anchor without grid_sample!
    assert sess._anchor is not None and 14 in sess._anchored
    mask_14 = np.asarray(sess.y[0, 14])
    assert int(mask_14.sum()) == total  # 100% valid at 0 deg even with erode=1!
    assert sess.warp_patches == n_valid_11 + total

    # Step 3 (2 WAIT chunks -> latents 16..23): parked latch prevents repeated re-anchoring on still tail!
    sess.step(["none"] * 32)
    assert sess.warp_events == 2 and len(vae_calls) == 2

    out = capsys.readouterr().out
    logs = [ln for ln in out.splitlines() if "warp-reanchor:" in ln]
    assert len(logs) == 2
    assert f"{n_valid_11}/{total} patches" in logs[0]
    assert f"{total}/{total} patches" in logs[1]
    # Verify DiT actually received the updated y slice on chunk 2 (start=8) and chunk 3 (start=12).
    chunk2_y = next(y_slice for start, _, y_slice in dit_y if start == 8)
    assert np.array_equal(chunk2_y[:, 3], y_g11)


def test_flag_off_and_unmatched_task_are_bit_identical(monkeypatch, capsys):
    monkeypatch.setattr(P, "YAW", math.radians(1.5))
    cfg = WR.WarpReanchorConfig(enabled=True)
    runs = []
    for c, on in ((None, False), (cfg, False), (None, True)):
        sess, dit_y, vae_calls, grid_calls, counter = _make_session(monkeypatch, cfg=c, on=on)
        sess.step(["l"] * 28)
        sess.step(["j"] * 16)
        sess.step(["j"] * 12 + ["none"] * 4)
        assert sess.warp_events == 0 and sess.warp_patches == 0
        assert vae_calls == [] and grid_calls == [] and sess._warp_tracker is None
        runs.append((counter[0], np.array(sess.y, copy=True), dit_y))

    assert "warp-reanchor" not in capsys.readouterr().out
    n0, y0, dy0 = runs[0]
    for n, y, dy in runs[1:]:
        assert n == n0 and np.array_equal(y, y0) and len(dy) == len(dy0)
        for (s1, t1, a1), (s2, t2, a2) in zip(dy, dy0):
            assert s1 == s2 and t1 == t2 and np.array_equal(a1, a2)


# ----------------------------------------- FlagStats & multi-arm R.main()

def test_flag_stats_off_vs_on(capsys):
    off = flag_stats.FlagStats(False, "goal", False, False)
    assert "warp_reanchor" not in off.summary("GC033")
    assert "warp_" not in off.total_line()

    on = flag_stats.FlagStats(True, "goal", False, False, warp_reanchor=True)
    # Armed GC task:
    on.new_task()
    on.warp_armed()
    on.warp_reanchored(2, 95)
    s_gc = on.finish_task("GC033")
    assert s_gc["warp_reanchor"] == "on" and s_gc["warp_events"] == 2 and s_gc["warp_patches"] == 95
    assert capsys.readouterr().out.strip().endswith("warp_reanchor=on warp_events=2 warp_patches=95")

    # Unmatched OE task:
    on.new_task()
    s_oe = on.finish_task("OE048")
    assert s_oe["warp_reanchor"] == "skip" and s_oe["warp_events"] == 0 and s_oe["warp_patches"] == 0
    assert capsys.readouterr().out.strip().endswith("warp_reanchor=skip warp_events=0 warp_patches=0")
    assert on.total_line().endswith("warp_events=2 warp_patches=95")


def test_gen_arms_isolation_no_leak_between_arms(monkeypatch, capsys):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    model = _dit(2, n=2)
    for b in model.blocks:
        b.self_attn = SimpleNamespace(local_attn_size=18, sink_size=6, forward=lambda x, *a, **kw: x)
    model.modules = lambda: [model, *(b.self_attn for b in model.blocks)]
    pipe = SimpleNamespace(model=model, local_attn_size=18, sink_size=6)
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe,
                                                              Path("weights"), False))

    sessions = []
    gc_task = {"task_id": "GC033", "category": "GC", "image_caption": "A plaza.", "prompt": "Pan right and back."}
    oe_task = {"task_id": "OE048", "category": "Out-of-sight", "image_caption": "A room.", "prompt": "Pan left."}

    def fresh(fresh=False):
        m = SimpleNamespace()

        def run_task(task, engine, output_dir, args):
            if engine.session is not None and R.WARP_REANCHOR.enabled:
                engine.session.warp_reanchor_on = R.WARP_REANCHOR.applies(f"{task['task_id']}_chunk_01")
                if engine.session.warp_reanchor_on:
                    R.STATS.warp_armed()
                    R.STATS.warp_reanchored(1, 42)
            engine._generate_session = engine._generate_stateless = lambda *a: "v.mp4"
            engine.generate("img.jpg", task["prompt"], "l-33", output_dir, f"{task['task_id']}_chunk_01", 33)
            return {"task_id": task["task_id"], "success": False}

        def main():
            args = SimpleNamespace(seed=42, fps=16, max_total_frames=961, action_frame_unit=20, chunk_frames=33)
            engine = m.SanaWMEngine(args)
            sessions.append(None if engine.session is None else engine.session.warp_reanchor)
            for t in (gc_task, oe_task):
                m.run_task(dict(t), engine, "out", args)
            return 0

        m.run_task, m.main = run_task, main
        m.decide_action = lambda *a, **k: "W"
        m.extract_video_frames_with_timestamps_b64 = lambda path, n=8: []
        m.parse_segments = lambda task: [("w", 8)]
        m.to_sana_key = lambda a: "none"
        return m

    monkeypatch.setattr(R, "import_run_agent", fresh)

    def run_arm(*flags):
        assert R.main(["run.py", "--tasks", "GC033,OE048", *flags]) == 0
        out = capsys.readouterr().out.splitlines()
        return {
            "mode": [ln for ln in out if ln.startswith("[lingbot] mode:")][0],
            "lines": [ln for ln in out if ln.startswith("[lingbot] flags task=")],
            "total": [ln for ln in out if ln.startswith("[lingbot] flags total")][0],
        }

    arm0 = run_arm()
    arm1 = run_arm("--lingbot-warp-reanchor", "--lingbot-warp-max-deg=35", "--lingbot-warp-focus=12")
    arm2 = run_arm()

    assert sessions[0] is None and sessions[2] is None
    assert sessions[1] == WR.WarpReanchorConfig(enabled=True, max_deg=35.0, focus=12.0)
    assert not R.WARP_REANCHOR.enabled

    # Leading and trailing no-flag arms are byte-identical and contain zero warp tokens.
    assert arm0 == arm2
    assert "warp" not in arm0["mode"] and "warp" not in " ".join(arm0["lines"]) and "warp" not in arm0["total"]

    # Middle arm logs mode and task/total counters cleanly.
    assert "warp-reanchor max 35 deg / 12 units, leave 25 deg / 8 units, focus 12, erode 1, tasks 'GC'" in arm1["mode"]
    assert arm1["lines"][0].endswith("warp_reanchor=on warp_events=1 warp_patches=42")
    assert arm1["lines"][1].endswith("warp_reanchor=skip warp_events=0 warp_patches=0")
    assert arm1["total"].endswith("warp_events=1 warp_patches=42")
