"""CPU-only tests for --lingbot-sink-key-scale (no GPU, no torch, no API calls)."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.lingbot_world2 import flag_stats as F, run as R, session as S, sink_scale as SK  # noqa: E402


def test_parse_and_configure():
    flags, rest = R.configure(["run.py", "--tasks", "OE001"], environ={})
    assert flags["sink_scale"] == SK.SinkScaleConfig() and not flags["sink_scale"].enabled
    assert rest == ["run.py", "--tasks", "OE001"]
    flags, rest = R.configure(["run.py", "--lingbot-sink-key-scale", "0.7", "--lingbot-sink-scale-after=4",
                               "--lingbot-sink-scale-tasks", "OE", "--tasks", "OE001"], environ={})
    assert flags["sink_scale"] == SK.SinkScaleConfig(0.7, 4, "OE") and rest == ["run.py", "--tasks", "OE001"]
    cfg, _ = SK.parse(["run.py"], environ={"LINGBOT_SINK_KEY_SCALE": "0.5", "LINGBOT_SINK_SCALE_AFTER": "0"})
    assert cfg == SK.SinkScaleConfig(0.5, 0, ".*") and cfg.enabled
    assert not SK.parse(["run.py", "--lingbot-sink-key-scale=1.0"], environ={})[0].enabled
    for bad in (["--lingbot-sink-key-scale"], ["--lingbot-sink-key-scale=0"], ["--lingbot-sink-key-scale=1.5"],
                ["--lingbot-sink-key-scale=nan"], ["--lingbot-sink-key-scale=x"], ["--lingbot-sink-scale-after=-1"],
                ["--lingbot-sink-scale-after=2.5"], ["--lingbot-sink-scale-tasks=("]):
        with pytest.raises(SystemExit):
            SK.parse(["run.py", *bad], environ={})


def test_applies_and_active():
    cfg = SK.SinkScaleConfig(0.7, 8, "OE")
    assert cfg.applies("OE047_chunk_01") and cfg.applies("OE047_full") and not cfg.applies("GC005_chunk_01")
    assert not SK.SinkScaleConfig().applies("OE047_chunk_01")
    assert [SK.active(cfg, c, 4, 6) for c in (0, 7, 8, 30)] == [False, False, True, True]
    early = SK.SinkScaleConfig(0.7, 0)
    assert [SK.active(early, c, 4, 6) for c in (0, 1, 2)] == [False, False, True]  # sink written by chunks 0-1
    assert not SK.active(early, 5, 4, 0) and not SK.active(None, 9, 4, 6)
    assert SK.sink_tokens(6, 1560) == 9360


def test_scale_restore_is_exact_and_scales_logits():
    rng = np.random.default_rng(0)
    kv = [{"k": rng.standard_normal((1, 10, 2, 8)).astype(np.float32), "v": np.zeros((1, 10, 2, 8))} for _ in range(3)]
    before = [b["k"].copy() for b in kv]
    saved = SK.scale_keys(kv, 4, 0.7)
    for b, o in zip(kv, before):
        assert np.array_equal(b["k"][:, :4], o[:, :4] * np.float32(0.7)) and np.array_equal(b["k"][:, 4:], o[:, 4:])
    # Q (A K)^T == A Q K^T on the sink columns, other columns unchanged: the logit-scaling identity
    q = rng.standard_normal((5, 8)).astype(np.float32)
    k0, k1 = before[0][0, :, 0], kv[0]["k"][0, :, 0]
    assert np.allclose(q @ k1.T[:, :4], 0.7 * (q @ k0.T[:, :4]), atol=1e-6)
    assert np.array_equal(q @ k1.T[:, 4:], q @ k0.T[:, 4:])
    SK.restore_keys(kv, 4, saved)
    assert all(np.array_equal(b["k"], o) for b, o in zip(kv, before))  # bit-exact: copied back, not divided


def test_rope_rotation_commutes_with_scale():
    # the cache holds keys after RoPE, a per-pair rotation: rope(A k) == A rope(k), so scaling the cached
    # (already rotated) key is the same as scaling the normalised key before RoPE
    rng = np.random.default_rng(1)
    k = rng.standard_normal((6, 4)) + 1j * rng.standard_normal((6, 4))
    rot = np.exp(1j * rng.uniform(0, 2 * np.pi, (6, 4)))
    assert np.allclose((0.6 * k) * rot, 0.6 * (k * rot))


class _T:
    def __init__(self, arr): self.arr, self.shape, self.device, self.dtype = np.asarray(arr), np.asarray(arr).shape, "cpu", "f32"
    def to(self, d): return _T(self.arr.astype(d)) if d is np.uint8 else self
    def clamp(self, lo, hi): return _T(np.clip(self.arr, lo, hi))
    def __add__(self, o): return _T(self.arr + o)
    def __mul__(self, o): return _T(self.arr * o)
    def round(self): return _T(np.round(self.arr))
    def permute(self, *ax): return _T(np.transpose(self.arr, ax))
    def cpu(self): return self
    def numpy(self): return self.arr


def _session(monkeypatch, cfg, sink=6, fail_at=None):
    nc = lambda *a, **kw: contextlib.nullcontext()  # noqa: E731
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8,
        randn=lambda *s, **kw: _T(np.zeros(s[0] if isinstance(s[0], tuple) else s)),
        stack=lambda xs: _T([x for x in xs]), cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim))))
    rng = np.random.default_rng(2)
    kv = [{"k": rng.standard_normal((1, 40, 2, 3)).astype(np.float32), "v": np.zeros((1, 40, 2, 3))} for _ in range(2)]
    pristine = [b["k"].copy() for b in kv]
    calls = []

    def model(x, t, **kw):
        n = len(calls)
        calls.append((kw["current_start"] // 4, float(t.arr[0]),
                      [np.array_equal(b["k"][:, :sink], p[:, :sink]) for b, p in zip(kw["kv_cache"], pristine)],
                      [np.array_equal(b["k"][:, :sink], p[:, :sink] * np.float32(0.7))
                       for b, p in zip(kw["kv_cache"], pristine)]))
        if fail_at is not None and n == fail_at:
            raise RuntimeError("boom")
        return x

    pipe = SimpleNamespace(device="cpu", param_dtype="bf16", sink_size=sink, model=model,
                           _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred,
                           scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0))
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, **({"sink_scale": cfg} if cfg else {}))
    sess.started, sess.track, sess.y = True, S.PoseTrack(), np.zeros((20, 64, 1, 1))
    sess.lat_h = sess.lat_w = sess.frame_seqlen = 1
    sess.max_seq_len, sess.kv_size, sess.context, sess.kv, sess.cross, sess.cross_init, sess.gen = \
        4, 40, ["c"], kv, [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",))
    sess._decode = lambda lat: _T(np.zeros((3, 29, 2, 2)))
    sess.sink_scale_on = cfg is not None
    return sess, calls, kv, pristine


def test_session_scales_denoise_forwards_only_and_restores(monkeypatch):
    sess, calls, kv, pristine = _session(monkeypatch, SK.SinkScaleConfig(0.7, 3))
    sess.step(["none"] * 28)  # chunks 0, 1: before K=3, never scaled
    sess.step(["w"] * 32)     # chunks 2 (< K), 3 (scaled)
    assert len(calls) == 4 * 5
    for cid, t, pristine_ok, scaled_ok in calls:
        if cid == 3 and t > 0:  # chunk 3's four denoising forwards see A * sink keys in every block
            assert all(scaled_ok) and not any(pristine_ok), (cid, t)
        else:                   # earlier chunks and every clean t=0 KV write see the pristine cache
            assert all(pristine_ok), (cid, t)
    assert sess.sink_scaled_chunks == 1
    assert all(np.array_equal(b["k"], p) for b, p in zip(kv, pristine))


def test_session_restores_on_exception(monkeypatch):
    sess, calls, kv, pristine = _session(monkeypatch, SK.SinkScaleConfig(0.5, 0), fail_at=2 * 5 + 1)
    sess.step(["none"] * 28)
    with pytest.raises(RuntimeError, match="boom"):
        sess.step(["none"] * 16)  # chunk 2, second denoising forward raises
    assert sess.sink_scaled_chunks == 1
    assert all(np.array_equal(b["k"], p) for b, p in zip(kv, pristine))


def test_session_off_and_sink_zero_never_touch_cache(monkeypatch):
    for cfg, sink in ((None, 6), (SK.SinkScaleConfig(0.5, 0), 0)):
        sess, calls, kv, pristine = _session(monkeypatch, cfg, sink=sink)
        sess.step(["none"] * 28)
        sess.step(["none"] * 32)
        assert sess.sink_scaled_chunks == 0 and all(all(c[2]) for c in calls)
        assert all(np.array_equal(b["k"], p) for b, p in zip(kv, pristine))


def test_flag_stats_lines():
    off = F.FlagStats(False, "goal", False, False)
    assert "sink_scale" not in off.summary("OE001") and "sink_scale" not in off.total_line()
    on = F.FlagStats(False, "goal", False, False, sink_scale=True)
    on.sink_armed()
    on.sink_scaled(22)
    s = on.finish_task("OE001")
    assert (s["sink_scale"], s["sink_scaled_chunks"]) == ("on", 22)
    on.new_task()
    assert on.finish_task("GC001")["sink_scale"] == "skip"
    assert on.total_line().endswith(" sink_scaled_chunks=22")


def test_multi_arm_main_isolation(monkeypatch, capsys, tmp_path):
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
                eng.session.step = lambda keys, **kw: setattr(eng.session, "sink_scaled_chunks",
                                                              eng.session.sink_scaled_chunks + eng.session.sink_scale_on) \
                    or np.zeros((29, 2, 2, 3), np.uint8)
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
            seen.append(eng.session.sink_scale if eng.session else "stateless")
            for tid in ("OE001", "GC001"):
                ra.run_task({"task_id": tid}, eng, tmp_path, None)

        ra.run_task, ra.main = run_task, run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    arms = [[], ["--lingbot-sink-key-scale", "0.7", "--lingbot-sink-scale-tasks", "OE"],
            ["--lingbot-sink-key-scale", "0.7", "--lingbot-stateless"], []]
    outs = []
    for extra in arms:
        assert R.main(["run.py", *extra]) == 0
        outs.append(capsys.readouterr().out.splitlines())
    lines = [[ln for ln in o if ln.startswith("[lingbot] flags ")] for o in outs]
    modes = [[ln for ln in o if ln.startswith("[lingbot] mode:")][0] for o in outs]
    assert seen[0] is None and seen[1] == SK.SinkScaleConfig(0.7, 8, "OE") and seen[2] == "stateless" and seen[3] is None
    assert lines[0] == lines[3] and modes[0] == modes[3]
    assert not any("sink" in ln for ln in lines[0] + [modes[0]])
    assert "sink key scale 0.7 from chunk 8 tasks 'OE'" in modes[1]
    assert lines[1][0].startswith(lines[0][0] + " ") and lines[1][0].endswith("sink_scale=on sink_scaled_chunks=2")
    assert lines[1][1].endswith("sink_scale=skip sink_scaled_chunks=0")
    assert lines[1][2].endswith(" sink_scaled_chunks=2")
    assert "sink key scale ignored (stateless)" in modes[2]
    assert lines[2][0].endswith("sink_scale=skip sink_scaled_chunks=0")
    assert not R.SINK_SCALE.enabled
