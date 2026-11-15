"""CPU-only tests for --lingbot-cond-schedule (no GPU, no torch, no API calls)."""
from __future__ import annotations
import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.lingbot_world2 import cond_schedule as CS, flag_stats as F, poses as P, run as R, session as S  # noqa: E402


class _Lin:
    def __init__(self, w: float, b: float = 0.0): self.w, self.b = w, b
    def forward(self, x): return self.w * x + self.b


def _fake_model(n: int = 2):
    return SimpleNamespace(blocks=[SimpleNamespace(
        cam_scale_layer=_Lin(2.0, 0.5), cam_shift_layer=_Lin(-1.0, 0.25),
        cross_attn=SimpleNamespace(o=_Lin(3.0, 0.1))) for _ in range(n)])


def test_parse_and_configure_flags():
    flags, rest = R.configure(["run.py", "--tasks", "OE001"], environ={})
    assert not flags["cond_sched"].enabled and rest == ["run.py", "--tasks", "OE001"]
    flags, rest = R.configure(
        ["run.py", "--lingbot-cond-schedule", "--lingbot-cond-early=3", "--lingbot-cond-text", "1.2",
         "--lingbot-cond-cam=0.1", "--lingbot-cond-3p", "0.8", "--tasks", "OE001"], environ={})
    assert flags["cond_sched"] == CS.ScheduleConfig(True, 3, 0.1, 0.8, 1.2, 1.0) and rest == ["run.py", "--tasks", "OE001"]
    cfg, _ = CS.parse(["run.py"], environ={"LINGBOT_COND_SCHEDULE": "1", "LINGBOT_COND_TEXT_3P": "1.05"})
    assert cfg.enabled and cfg.early_steps == 2 and cfg.text_static == 1.15 and cfg.text_3p == 1.05
    for bad in (["--lingbot-cond-early"], ["--lingbot-cond-early=2.5"], ["--lingbot-cond-cam=-0.1"],
                ["--lingbot-cond-text=inf"], ["--lingbot-cond-3p=nan"]):
        with pytest.raises(SystemExit):
            CS.parse(["run.py", *bad], environ={})


def test_step_schedule_stationary_3p_and_1p_guard():
    P.reset({})
    m = _fake_model()
    b0, x = m.blocks[0], np.array([1.0, -2.0])
    base = (b0.cam_scale_layer.forward(x).copy(), b0.cam_shift_layer.forward(x).copy(), b0.cross_attn.o.forward(x).copy())
    sched = CS.CondScheduler(m, CS.ScheduleConfig(True, 2, 0.0, 0.85, 1.15, 1.0))
    wait, walk = S.PoseTrack().advance(["none"] * 12), S.PoseTrack().advance(["w"] * 12)

    for i in (0, 1):
        assert sched.set_step(wait, i) is True
        assert np.allclose(b0.cam_scale_layer.forward(x), 0.0) and np.allclose(b0.cam_shift_layer.forward(x), 0.0)
        assert np.allclose(b0.cross_attn.o.forward(x), 1.15 * base[2])
    for i in (2, 3):
        assert sched.set_step(wait, i) is False
        assert all(np.array_equal(f(x), r) for f, r in zip(
            (b0.cam_scale_layer.forward, b0.cam_shift_layer.forward, b0.cross_attn.o.forward), base))
    for i in range(4):
        assert sched.set_step(walk, i, third_person=False) is False
        assert all(np.array_equal(f(x), r) for f, r in zip(
            (b0.cam_scale_layer.forward, b0.cam_shift_layer.forward, b0.cross_attn.o.forward), base))
    assert sched.set_step(walk, 0, third_person=True) is True
    assert np.allclose(b0.cam_scale_layer.forward(x), 0.85 * base[0]) and np.array_equal(b0.cross_attn.o.forward(x), base[2])
    assert sched.set_step(walk, 2, third_person=True) is False and np.array_equal(b0.cam_scale_layer.forward(x), base[0])

    with pytest.raises(RuntimeError):
        with sched:
            sched.set_step(wait, 0)
            raise RuntimeError("boom")
    assert sched.cam_scale == 1.0 and sched.text_scale == 1.0
    sched.detach()
    assert not hasattr(m, "_cond_schedule") and "forward" not in b0.cam_scale_layer.__dict__


def test_third_person_and_flag_stats_lines():
    assert CS.is_third_person({"task_id": "GC016", "perspective": "third person"}, "GC016_chunk_01")
    assert not CS.is_third_person({"task_id": "GC033", "perspective": "first person"}, "GC033_chunk_01")
    assert CS.is_third_person({"task_id": "IF010", "category": "IF"}, "IF010_chunk_01")
    assert not CS.is_third_person({"task_id": "IF010", "category": "IF"}, "OE001_chunk_01")
    off = F.FlagStats(False, "goal", False, False)
    assert "cond_sched" not in off.summary("OE001") and "cond_sched" not in off.total_line()
    on = F.FlagStats(False, "auto", False, False, cond_sched="on")
    on.cond_scheduled(20, 40)
    s = on.finish_task("OE001")
    assert (s["cond_sched"], s["cond_sched_chunks"], s["cond_sched_calls"]) == ("on", 20, 40)
    assert "cond_sched=on cond_sched_chunks=20 cond_sched_calls=40" in on.total_line()


def test_multi_arm_main_isolation(monkeypatch, capsys):
    shared_pipe = SimpleNamespace(model=_fake_model(1), _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), shared_pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    seen = []

    def fake_import(fresh=True):
        ra = SimpleNamespace(run_task=lambda task, eng, out, args: {"task_id": task["task_id"], "success": True},
                             decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")
        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16))
            seen.append((hasattr(shared_pipe.model, "_cond_schedule"), eng.session.cond_sched if eng.session else None))
            ra.run_task({"task_id": "OE001"}, eng, Path("/tmp"), None)
        ra.main = run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py"]) == 0
    assert R.main(["run.py", "--lingbot-cond-schedule"]) == 0
    assert R.main(["run.py"]) == 0
    out = capsys.readouterr().out
    assert [x[0] for x in seen] == [False, True, False]
    assert seen[0][1] is None and seen[1][1] is not None and seen[2][1] is None
    assert "cond-schedule early=2 static=(0,1.15) 3p=(0.85,1)" in out
    flags_lines = [l for l in out.splitlines() if l.startswith("[lingbot] flags task=")]
    assert "cond_sched" not in flags_lines[0] and "cond_sched=on" in flags_lines[1] and "cond_sched" not in flags_lines[2]


def test_session_step_restores_scales_before_kv_write(monkeypatch):
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

    nc = lambda *a, **kw: contextlib.nullcontext()
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8,
        randn=lambda *s, **kw: _T(np.zeros(s[0] if isinstance(s[0], tuple) else s)),
        stack=lambda xs: _T([x for x in xs]), cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim))))
    calls, sched = [], CS.CondScheduler(_fake_model(1))
    pipe = SimpleNamespace(device="cpu", param_dtype="bf16", _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred,
                           scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0),
                           model=lambda x, t, **kw: calls.append((float(t.arr[0]), sched.cam_scale, sched.text_scale)) or x)
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, cond_sched=sched)
    sess.started, sess.track, sess.y = True, S.PoseTrack(), np.zeros((20, 32, 1, 1))
    sess.lat_h = sess.lat_w = sess.frame_seqlen = 1
    sess.max_seq_len, sess.kv_size, sess.context, sess.kv, sess.cross, sess.cross_init, sess.gen = 4, 16, ["c"], [], [], False, None
    sess.timesteps = [1000.0, 750.0, 500.0, 250.0]
    sess._plucker = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",))
    sess._decode = lambda lat: _T(np.zeros((3, 29, 2, 2)))

    sess.step(["none"] * 28)  # 2 stationary chunks: 4 denoise steps + 1 clean t=0 KV write each
    assert calls == [(1000.0, 0.0, 1.15), (750.0, 0.0, 1.15), (500.0, 1.0, 1.0), (250.0, 1.0, 1.0), (0.0, 1.0, 1.0)] * 2
    assert (sess.cond_sched_chunks, sess.cond_sched_calls) == (2, 4)
    calls.clear()
    sess.step(["w"] * 32)  # 2 moving 1P chunks: every denoise step and t=0 KV write stays (1.0, 1.0)
    assert all((cs, ts) == (1.0, 1.0) for _, cs, ts in calls) and len(calls) == 10
    assert (sess.cond_sched_chunks, sess.cond_sched_calls) == (2, 4)
