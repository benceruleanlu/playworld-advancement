"""Per-slice VAE decode in LingBotSession: frames identical to the old full-video post-processing, no
full-video tensor on the device, and stall-watchdog progress marks during a long step."""
import contextlib
import re
import sys
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from adapters.lingbot_world2 import session as S
from adapters.lingbot_world2 import watchdog as W

H, W_PX, Z = 3, 5, 16


# ------------------------------------------------- real torch (CPU): identical frames

def _torch_vae(torch):
    """Fake causal VAE: conv2 is a fixed channel mix, the decoder emits 1 frame for the first latent it sees
    (empty cache) and 4 after, in bf16 with values outside [-1, 1], and depends on the cached latent."""
    mix = torch.linspace(-0.7, 0.9, Z)

    def decoder(x, feat_cache, feat_idx):
        prev = feat_cache[0]
        n = 1 if prev is None else 4
        base = x[0, :, 0].sum(0) + (0 if prev is None else 0.37 * prev[0, :, 0].sum(0))  # [h, w]
        t = torch.arange(3 * n * H * W_PX, dtype=torch.float32).view(3, n, H, W_PX)
        out = 1.4 * torch.sin(0.91 * t + base.repeat(1, 1)[None, None].mean() + t * base.mean() * 0.01)
        feat_cache[0] = x.detach().clone()
        return out[None].to(torch.bfloat16)

    model = SimpleNamespace(z_dim=Z, decoder=decoder, conv2=lambda z: z * mix.view(1, Z, 1, 1, 1))
    scale = (torch.full((Z,), 0.1), torch.full((Z,), 2.0))
    return SimpleNamespace(model=model, scale=scale, dtype=torch.bfloat16)


def _old_stream(torch, vae, feat, lat):
    """The streaming decode and step() post-processing before this change, verbatim."""
    m = vae.model
    mean, inv_std = vae.scale
    with torch.cuda.amp.autocast(dtype=vae.dtype):
        z = lat.unsqueeze(0)
        z = z / inv_std.view(1, m.z_dim, 1, 1, 1) + mean.view(1, m.z_dim, 1, 1, 1)
        x = m.conv2(z)
        outs = []
        for i in range(x.shape[2]):
            outs.append(m.decoder(x[:, :, i:i + 1], feat_cache=feat, feat_idx=[0]))
        out = torch.cat(outs, 2)
    video = out.float().clamp_(-1, 1).squeeze(0)
    return ((video.clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()


def _old_full(torch, vae, all_lat, lat):
    """The non-streaming path before this change: Wan2_1_VAE.decode (fresh cache) of every latent so far,
    keep the new frames, then the old post-processing."""
    m = vae.model
    mean, inv_std = vae.scale
    zs = torch.cat(all_lat, 1)
    with torch.cuda.amp.autocast(dtype=vae.dtype):
        z = zs.unsqueeze(0) / inv_std.view(1, Z, 1, 1, 1) + mean.view(1, Z, 1, 1, 1)
        x = m.conv2(z)
        feat = [None]
        out = torch.cat([m.decoder(x[:, :, i:i + 1], feat_cache=feat, feat_idx=[0]) for i in range(x.shape[2])], 2)
        full = out.float().clamp_(-1, 1).squeeze(0)
    n_new = 4 * lat.shape[1] - (3 if len(all_lat) == 1 else 0)
    video = full[:, -n_new:]
    return ((video.clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()


def _step_frames(sess, lat, first):
    """step()'s tail after the denoise loop, as it now stands (decode, to host, previous-last-frame join)."""
    video = sess._decode(lat)
    frames = video.permute(1, 2, 3, 0).cpu().numpy()
    if not first:
        frames = np.concatenate([sess._last_frame[None], frames])
    sess._last_frame = frames[-1].copy()
    return frames


@pytest.mark.parametrize("stream", [True, False])
def test_per_slice_decode_matches_old_frames_across_two_steps(monkeypatch, stream):
    torch = pytest.importorskip("torch")
    monkeypatch.setitem(sys.modules, "wan.modules.vae2_1", SimpleNamespace(count_conv3d=lambda dec: 1))
    monkeypatch.setitem(sys.modules, "wan.modules", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "wan", SimpleNamespace())
    vae = _torch_vae(torch)
    sess = S.LingBotSession(SimpleNamespace(vae=vae), 1, 1.0, stream_decode=stream)
    sess._feat_map = [None]
    g = torch.Generator().manual_seed(0)
    lats = [torch.randn(Z, 8, H, W_PX, generator=g), torch.randn(Z, 8, H, W_PX, generator=g)]  # 2 chunks a step

    old_feat, old_all, old_last, got, want = [None], [], None, [], []
    for k, lat in enumerate(lats):
        got.append(_step_frames(sess, lat, first=k == 0))
        old_all.append(lat)
        ref = _old_stream(torch, vae, old_feat, lat) if stream else _old_full(torch, vae, old_all, lat)
        if k:
            ref = np.concatenate([old_last[None], ref])
        old_last = ref[-1].copy()
        want.append(ref)

    assert [f.shape for f in got] == [(29, H, W_PX, 3), (33, H, W_PX, 3)]  # 16n-3, then last frame + 16n
    for a, b in zip(got, want):
        assert a.dtype == np.uint8 and np.array_equal(a, b)
    assert np.array_equal(got[1][0], got[0][-1])  # chunk boundary: the repeated frame
    assert len({int(v) for v in np.concatenate([f.ravel() for f in got])}) > 50  # not a trivial video
    assert (np.concatenate([f.ravel() for f in got]) == 0).any() and (np.concatenate([f.ravel() for f in got]) == 255).any()


# ------------------------------------------- fake device: no full-video tensor on the GPU

class _Dev:
    """numpy tensor tagged with a device; records the size of every tensor created on 'cuda'."""
    sizes: list = []

    def __init__(self, arr, device="cuda"):
        self.arr, self.device = np.asarray(arr), device
        if device == "cuda":
            _Dev.sizes.append(self.arr.size)

    shape = property(lambda self: self.arr.shape)

    def __getitem__(self, idx): return _Dev(self.arr[idx], self.device)
    def __add__(self, o): return _Dev(self.arr + (o.arr if isinstance(o, _Dev) else o), self.device)
    def __mul__(self, o): return _Dev(self.arr * (o.arr if isinstance(o, _Dev) else o), self.device)
    def __truediv__(self, o): return _Dev(self.arr / (o.arr if isinstance(o, _Dev) else o), self.device)
    def float(self): return _Dev(self.arr.astype(np.float32), self.device)
    def clamp(self, lo, hi): return _Dev(np.clip(self.arr, lo, hi), self.device)
    def round(self): return _Dev(np.round(self.arr), self.device)
    def to(self, dt): return _Dev(self.arr.astype(dt), self.device)
    def cpu(self): return _Dev(self.arr, "cpu")
    def unsqueeze(self, d): return _Dev(np.expand_dims(self.arr, d), self.device)
    def squeeze(self, d): return _Dev(np.squeeze(self.arr, d), self.device)
    def view(self, *s): return _Dev(self.arr.reshape(s), self.device)
    def permute(self, *ax): return _Dev(np.transpose(self.arr, ax), self.device)
    def numpy(self):
        assert self.device == "cpu"
        return self.arr


def _fake_torch(marks=None):
    nc = lambda *a, **kw: contextlib.nullcontext()

    def cat(xs, dim=0):
        dev = {x.device for x in xs}
        assert len(dev) == 1
        return _Dev(np.concatenate([x.arr for x in xs], axis=dim), dev.pop())

    return SimpleNamespace(uint8=np.uint8, cat=cat, autocast=nc,
                           cuda=SimpleNamespace(empty_cache=lambda: None, is_available=lambda: False,
                                                amp=SimpleNamespace(autocast=nc)))


def test_streaming_decode_keeps_no_full_video_on_device(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", _fake_torch())

    def decoder(x, feat_cache, feat_idx):
        n = 1 if feat_cache[0] is None else 4
        feat_cache[0] = True
        return _Dev(np.full((1, 3, n, 8, 8), 0.25, dtype=np.float32))

    model = SimpleNamespace(z_dim=Z, decoder=decoder, conv2=lambda z: z)
    vae = SimpleNamespace(model=model, scale=(_Dev(np.zeros(Z)), _Dev(np.ones(Z))), dtype="bf16")
    sess = S.LingBotSession(SimpleNamespace(vae=vae), 1, 1.0, stream_decode=True)
    sess._feat_map = [None]
    n_lat = 40  # 157 frames
    lat = _Dev(np.zeros((Z, n_lat, 2, 2), dtype=np.float32))
    _Dev.sizes.clear()
    video = sess._decode(lat)
    full = 3 * (4 * n_lat - 3) * 8 * 8
    assert video.device == "cpu" and video.arr.dtype == np.uint8 and video.shape == (3, 4 * n_lat - 3, 8, 8)
    assert (video.arr == round(1.25 * 127.5)).all()
    assert max(_Dev.sizes) <= lat.arr.size < full / 10  # nothing on the device is bigger than the latents


# --------------------------------------------------------------- watchdog progress marks

def test_progress_marks_keep_a_long_call_alive_then_a_stall_aborts(tmp_path):
    exits, done = [], threading.Event()

    def exit_fn(code):
        exits.append(code)
        done.set()

    with open(tmp_path / "err", "w+") as f:
        with W.watch("OE001_full", W.Limits(0, 0.4), file=f, exit_fn=exit_fn):
            t0 = time.time()
            while time.time() - t0 < 1.2:  # three abort windows of work, marked every 0.05 s
                time.sleep(0.05)
                W.progress()
            assert exits == []
            assert done.wait(5), "no abort after progress stopped"
        f.seek(0)
        out = f.read()
    assert exits == [W.ABORT_EXIT_CODE]
    m = re.search(r"OE001_full still running after (\d+)s, no progress for 0s", out)
    assert m and int(m[1]) >= 1  # the call outlived the abort limit; only the silence after it counted


def test_session_step_marks_progress_per_chunk_and_per_decoded_latent(monkeypatch):
    class _T:
        def __init__(self, arr): self.arr, self.shape, self.device, self.dtype = np.asarray(arr), np.asarray(arr).shape, "cpu", "f32"
        def to(self, d): return self
        def permute(self, *ax): return _T(np.transpose(self.arr, ax))
        def cpu(self): return self
        def numpy(self): return self.arr

    nc = lambda *a, **kw: contextlib.nullcontext()
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8,
        randn=lambda *s, **kw: _T(np.zeros(s[0] if isinstance(s[0], tuple) else s)),
        stack=lambda xs: _T([x for x in xs]), cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim))))
    marks = []
    monkeypatch.setattr(W, "progress", lambda: marks.append("mark"))
    pipe = SimpleNamespace(device="cpu", param_dtype="bf16", _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred,
                           scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0), model=lambda x, t, **kw: x)
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True)
    sess.started, sess.track, sess.y = True, S.PoseTrack(), np.zeros((20, 64, 1, 1))
    sess.lat_h = sess.lat_w = sess.frame_seqlen = 1
    sess.max_seq_len, sess.kv_size, sess.context, sess.kv, sess.cross, sess.cross_init, sess.gen = 4, 16, ["c"], [], [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",))

    def decode(lat):
        marks.append(f"decode {lat.shape[1]}")
        return _T(np.zeros((3, 4 * lat.shape[1] - 3, 2, 2), dtype=np.uint8))

    sess._decode = decode
    frames = sess.step(["none"] * (16 * 5 - 4))  # one 5-chunk step, as dataset mode runs a whole task
    assert marks == ["mark"] * 5 + ["decode 20"]  # one mark per latent chunk, all before the decode
    assert frames.shape == (77, 2, 2, 3)
