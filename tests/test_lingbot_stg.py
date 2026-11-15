"""CPU-only tests for --lingbot-stg (early-step layer-skip self-guidance): no GPU, no torch, no API calls."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.lingbot_world2 import flag_stats as F, run as R, session as S, stg as G  # noqa: E402


class _T:
    """Just enough of a tensor for LingBotSession.step and the skip hook."""

    def __init__(self, arr):
        self.arr = np.asarray(arr, dtype=np.float64)
        self.shape, self.device, self.dtype = self.arr.shape, "cpu", "f32"

    def _o(self, o): return o.arr if isinstance(o, _T) else o
    def to(self, d): return _T(self.arr) if d is not np.uint8 else _U(self.arr)
    def clamp(self, lo, hi): return _T(np.clip(self.arr, lo, hi))
    def __add__(self, o): return _T(self.arr + self._o(o))
    def __sub__(self, o): return _T(self.arr - self._o(o))
    def __mul__(self, o): return _T(self.arr * self._o(o))
    def round(self): return _T(np.round(self.arr))
    def permute(self, *ax): return _T(np.transpose(self.arr, ax))
    def new_zeros(self, shape): return _T(np.zeros(shape))
    def cpu(self): return self
    def numpy(self): return self.arr


class _U(_T):
    def numpy(self): return self.arr.astype(np.uint8)


class _Attn:
    def forward(self, x, *a, **kw): return _T(np.ones(x.shape))
    def __call__(self, *a, **kw): return self.forward(*a, **kw)  # like nn.Module.__call__


def _dit(n=40):
    return SimpleNamespace(blocks=[SimpleNamespace(self_attn=_Attn()) for _ in range(n)])


def _block_sum(model):
    """Fake DiT: each block adds its self-attention output (ones) to a [1, 2, 3] residual stream."""
    return sum(float(b.self_attn(_T(np.zeros((1, 2, 3))), "seq_lens", frame_seqlen=1).arr.mean()) for b in model.blocks)


def test_parse_configure_and_defaults():
    flags, rest = R.configure(["run.py", "--tasks", "OE001"], environ={})
    assert flags["stg"] == G.StgConfig() and not flags["stg"].enabled and rest == ["run.py", "--tasks", "OE001"]
    flags, rest = R.configure(["run.py", "--lingbot-stg", "--lingbot-stg-w=0.5", "--lingbot-stg-blocks", "18,22",
                               "--lingbot-stg-steps=2", "--tasks", "OE001"], environ={})
    assert flags["stg"] == G.StgConfig(True, 0.5, "18,22", 2) and rest == ["run.py", "--tasks", "OE001"]
    cfg, _ = G.parse(["run.py"], environ={"LINGBOT_STG": "1", "LINGBOT_STG_W": "0.2", "LINGBOT_STG_STEPS": "3"})
    assert cfg == G.StgConfig(True, 0.2, "mid", 3)
    for bad in (["--lingbot-stg-w"], ["--lingbot-stg-w=-1"], ["--lingbot-stg-w=inf"], ["--lingbot-stg-steps=0"],
                ["--lingbot-stg-steps=1.5"], ["--lingbot-stg-blocks=a,b"], ["--lingbot-stg-blocks=,"]):
        with pytest.raises(SystemExit):
            G.parse(["run.py", *bad], environ={})


def test_resolve_blocks():
    assert G.resolve_blocks("mid", 40) == (20,) and G.resolve_blocks("mid", 30) == (15,)
    assert G.resolve_blocks("22, 18,18", 40) == (18, 22)
    with pytest.raises(SystemExit):
        G.resolve_blocks("40", 40)
    with pytest.raises(SystemExit):
        G.SkipGuidance(_dit(30), G.StgConfig(True, blocks="35"))


def test_skip_hook_is_identity_and_restored():
    m = _dit(4)
    g = G.SkipGuidance(m, G.StgConfig(True, 0.3, "1,2", 1))
    assert g.describe() == "stg w=0.3 blocks=1,2 steps=1"
    assert _block_sum(m) == 4.0
    with g.skipped():
        assert _block_sum(m) == 2.0  # blocks 1 and 2 add zeros: the residual passes through unchanged
    assert _block_sum(m) == 4.0 and all("forward" not in b.self_attn.__dict__ for b in m.blocks)
    with pytest.raises(RuntimeError), g.skipped():
        raise RuntimeError("boom")
    assert all("forward" not in b.self_attn.__dict__ for b in m.blocks)
    assert [g.guided(i) for i in range(4)] == [True, False, False, False]
    assert np.allclose(g.combine(_T([2.0]), _T([1.0])).arr, [2.3])


def _session(monkeypatch, stg):
    nc = lambda *a, **kw: contextlib.nullcontext()  # noqa: E731
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8,
        randn=lambda *s, **kw: _T(np.zeros(s[0] if isinstance(s[0], tuple) else s)),
        stack=lambda xs: _T(list(xs)), cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim))))
    dit, calls, preds = _dit(4), [], []

    def model(x, t, cross_attn_first_call, **kw):
        out = _block_sum(dit)  # 4.0 on a full pass, 3.0 with the mid block skipped
        calls.append((float(t.arr[0]), out, cross_attn_first_call, kw["current_start"]))
        return [_T(np.full(x[0].shape, out))]

    def to_x0(flow_pred, **kw):
        preds.append(float(flow_pred.arr.flat[0]))
        return flow_pred

    pipe = SimpleNamespace(device="cpu", param_dtype="bf16", _convert_flow_pred_to_x0=to_x0,
                           scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0), model=model)
    g = G.SkipGuidance(dit, stg) if stg is not None else None
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, **({"stg": g} if g else {}))
    sess.started, sess.track, sess.y = True, S.PoseTrack(), np.zeros((20, 32, 1, 1))
    sess.lat_h = sess.lat_w = sess.frame_seqlen = 1
    sess.max_seq_len, sess.kv_size, sess.context, sess.kv, sess.cross, sess.cross_init, sess.gen = \
        4, 16, ["c"], [], [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",))
    sess._decode = lambda lat: _T(np.zeros((3, 29, 2, 2)))
    return sess, calls, preds, dit


def test_session_step_guides_first_step_only_skip_first_kv_write_clean(monkeypatch):
    sess, calls, preds, dit = _session(monkeypatch, G.StgConfig(True, 0.3, "mid", 1))
    sess.step(["none"] * 28)  # 2 chunks: per chunk skip pass, 4 full denoise passes, 1 clean t=0 KV write
    chunk = lambda first, start: [(1000.0, 3.0, first, start), (1000.0, 4.0, first, start),  # noqa: E731
                                  (750.0, 4.0, False, start), (500.0, 4.0, False, start), (250.0, 4.0, False, start),
                                  (0.0, 4.0, False, start)]
    assert calls == chunk(True, 0) + chunk(False, 4)  # the skip pass precedes the full pass of the same step
    assert preds == pytest.approx([4.3, 4.0, 4.0, 4.0] * 2)  # 4 + 0.3 * (4 - 3) on the guided step only
    assert (sess.stg_chunks, sess.stg_calls) == (2, 2)
    assert all("forward" not in b.self_attn.__dict__ for b in dit.blocks)
    calls.clear()
    sess.stg = G.SkipGuidance(dit, G.StgConfig(True, 0.3, "0,3", 2))
    sess.step(["w"] * 16)  # 1 moving chunk, 2 guided steps
    assert [c[1] for c in calls] == [2.0, 4.0, 2.0, 4.0, 4.0, 4.0, 4.0] and (sess.stg_chunks, sess.stg_calls) == (3, 4)


def test_session_without_flag_matches_main(monkeypatch):
    sess, calls, preds, _ = _session(monkeypatch, None)
    sess.step(["none"] * 28)
    assert [c[1] for c in calls] == [4.0] * 10 and preds == [4.0] * 8
    assert (sess.stg, sess.stg_chunks, sess.stg_calls) == (None, 0, 0)


def test_flag_stats_lines():
    off = F.FlagStats(False, "goal", False, False)
    assert "stg" not in off.summary("OE001") and "stg" not in off.total_line()
    on = F.FlagStats(False, "goal", False, False, stg="on")
    on.stg_counted(30, 30)
    s = on.finish_task("OE001")
    assert (s["stg"], s["stg_chunks"], s["stg_calls"]) == ("on", 30, 30)
    assert "stg=on stg_chunks=30 stg_calls=30" in on.total_line()


def test_multi_arm_main_isolation(monkeypatch, capsys):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    shared_pipe = SimpleNamespace(model=_dit(40), _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), shared_pipe,
                                                              Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        ra = SimpleNamespace(run_task=lambda task, eng, out, args: {"task_id": task["task_id"], "success": True},
                             decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")

        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16))
            seen.append(None if eng.session is None else getattr(eng.session, "stg"))
            ra.run_task({"task_id": "OE001"}, eng, Path("/tmp"), None)
        ra.main = run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py"]) == 0
    assert R.main(["run.py", "--lingbot-stg", "--lingbot-stg-blocks=18,22"]) == 0
    assert R.main(["run.py", "--lingbot-stg", "--lingbot-stateless"]) == 0
    assert R.main(["run.py"]) == 0
    out = capsys.readouterr().out
    assert seen[0] is None and seen[1].blocks == (18, 22) and seen[2] is None and seen[3] is None
    assert all("forward" not in b.self_attn.__dict__ for b in shared_pipe.model.blocks)
    modes = [line for line in out.splitlines() if line.startswith("[lingbot] mode:")]
    assert "stg" not in modes[0] and "stg w=0.3 blocks=18,22 steps=1" in modes[1]
    assert "stg ignored (stateless)" in modes[2] and modes[3] == modes[0]
    flags_lines = [line for line in out.splitlines() if line.startswith("[lingbot] flags task=")]
    assert "stg" not in flags_lines[0] and "stg=on stg_chunks=0 stg_calls=0" in flags_lines[1]
    assert "stg=skip" in flags_lines[2] and flags_lines[3] == flags_lines[0]
