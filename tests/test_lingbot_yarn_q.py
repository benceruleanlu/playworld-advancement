"""CPU-only tests for --lingbot-yarn-q (no GPU, no torch, no API calls)."""
from __future__ import annotations
import contextlib, json, math, sys  # noqa: E401
from pathlib import Path
from types import SimpleNamespace
import numpy as np, pytest  # noqa: E401
from adapters.lingbot_world2 import cond_schedule as CS, flag_stats as F, run as R, session as S, weight_mod as WM, yarn_q as YQ


class _Lin:
    def __init__(self, w: float = 2.0): self.w = w
    def forward(self, x): return self.w * x
    def __call__(self, x): return self.forward(x)

def _fake_model(n: int = 2):
    return SimpleNamespace(blocks=[SimpleNamespace(local_attn_size=18, sink_size=6, cam_scale_layer=_Lin(1.5),
        cam_shift_layer=_Lin(-0.5), cross_attn=SimpleNamespace(o=_Lin(2.0)), self_attn=SimpleNamespace(norm_q=_Lin(1.0))) for _ in range(n)], modules=lambda: [])

def test_parse_validation_and_stateless_rejection():
    assert R.configure(["run.py", "--tasks", "GC033"], environ={}) == (R.configure(["run.py", "--tasks", "GC033"], environ={})[0], ["run.py", "--tasks", "GC033"])
    assert R.configure(["run.py"], environ={})[0]["yarn_q"] == YQ.YarnQConfig()
    flags, rest = R.configure(["run.py", "--lingbot-yarn-q", "--lingbot-yarn-ref=16", "--lingbot-yarn-gain", "1.05", "--lingbot-yarn-below-ref", "--tasks", "GC033"], environ={"LINGBOT_YARN_REF": "20"})
    assert flags["yarn_q"] == YQ.YarnQConfig(True, 16, 1.05, True) and rest == ["run.py", "--tasks", "GC033"]
    assert YQ.parse(["run.py"], environ={"LINGBOT_YARN_Q": "1", "LINGBOT_YARN_REF": "18", "LINGBOT_YARN_GAIN": "1.1"})[0] == YQ.YarnQConfig(True, 18, 1.1, False)
    for bad in (["--lingbot-yarn-ref"], ["--lingbot-yarn-ref=3"], ["--lingbot-yarn-ref=12.5"], ["--lingbot-yarn-gain"], ["--lingbot-yarn-gain=0"], ["--lingbot-yarn-gain=-1"], ["--lingbot-yarn-gain=inf"], ["--lingbot-yarn-gain=nan"]):
        with pytest.raises(SystemExit): YQ.parse(["run.py", *bad], environ={})  # noqa: E701
    for argv, env in ((["--lingbot-stateless"], {}), ([], {"LINGBOT_SESSION": "0"})):
        with pytest.raises(SystemExit, match="--lingbot-yarn-q requires session mode"): R.configure(["run.py", "--lingbot-yarn-q", *argv], environ=env)  # noqa: E701

def test_scale_math_and_hook_composition():
    fseq = 1560
    s4, s12, s18, s36, s240 = (YQ.scale_for_chunk(c, w, fseq) for c, w in ((0, 18), (2, 18), (4, 18), (8, 36), (59, -1)))
    assert s4 == 1.0 and s12 == 1.0 and 1.0 < s18 < s36 < s240 and all(math.isclose(s, math.sqrt(math.log(lat * fseq) / math.log(12 * fseq)), rel_tol=1e-12) for s, lat in ((s18, 18), (s36, 36), (s240, 240)))
    assert YQ.scale_for_chunk(0, 18, fseq, below_ref=True) < 1.0 and YQ.scale_for_chunk(2, 18, fseq, below_ref=True) == 1.0 and math.isclose(YQ.scale_for_chunk(4, 18, fseq, gain=1.05), 1.05 * s18, rel_tol=1e-12)
    m, x = _fake_model(2), np.array([2.0, -3.0])
    wm, yq = WM.WeightModulator(m), YQ.YarnQScaler(m)
    assert not yq.step(0, 18, fseq) and np.array_equal(m.blocks[0].self_attn.norm_q(x), x) and yq.step(8, 36, fseq) and np.allclose(m.blocks[0].self_attn.norm_q(x), s36 * x)
    assert wm.step(np.broadcast_to(np.eye(4), (4, 4, 4))) and np.allclose(m.blocks[0].cam_scale_layer(x), 0.0)
    with pytest.raises(RuntimeError):
        with yq: yq.step(8, 36, fseq); raise RuntimeError("boom")  # noqa: E701, E702
    assert yq.q_scale == 1.0 and (wm.detach(), yq.detach()) == (None, None) and not hasattr(m, "_yarn_q") and all("forward" not in b.self_attn.norm_q.__dict__ for b in m.blocks)
    cs, yq2 = CS.CondScheduler(m), YQ.YarnQScaler(m)
    assert hasattr(m, "_cond_schedule") and hasattr(m, "_yarn_q") and (cs.detach(), yq2.detach()) == (None, None)

def test_session_step_and_multi_arm_isolation(tmp_path, monkeypatch, capsys):
    class _T:
        def __init__(self, a): self.arr, self.shape, self.device, self.dtype = np.asarray(a), np.asarray(a).shape, "cpu", "f32"
        def __add__(self, o): return _T(self.arr + o)
        def __mul__(self, o): return _T(self.arr * o)
        def __getattr__(self, k): return (lambda: self.arr.astype(np.uint8)) if k == "numpy" else (lambda *ax: _T(np.transpose(self.arr, ax))) if k == "permute" else (lambda *a, **kw: self)
    nc = lambda *a, **kw: contextlib.nullcontext()  # noqa: E731
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32="f32", uint8=np.uint8, randn=lambda *s, **kw: _T(np.zeros(s[0] if isinstance(s[0], tuple) else s)), stack=lambda xs: _T([x for x in xs]), cat=lambda xs, dim=0: _T(np.concatenate([x.arr for x in xs], axis=dim))))
    m, scales = _fake_model(1), []
    yq, pipe = YQ.YarnQScaler(m), SimpleNamespace(device="cpu", param_dtype="bf16", local_attn_size=18, sink_size=6, _t5_cache={}, _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred, scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0), model=lambda x, t, **kw: scales.append((float(t.arr[0]), float(m.blocks[0].self_attn.norm_q(1.0)))) or x)
    sess = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, yarn_q=yq)
    sess.started, sess.track, sess.y, sess.lat_h, sess.lat_w, sess.frame_seqlen, sess.timesteps = True, S.PoseTrack(), np.zeros((20, 32, 1, 1)), 1, 1, 1560, [1000.0, 500.0]
    sess.max_seq_len, sess.kv_size, sess.context, sess.kv, sess.cross, sess.cross_init, sess.gen, sess._plucker, sess._decode = 4, 18, ["c"], [], [], False, None, lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",)), lambda lat: _T(np.zeros((3, 29, 2, 2)))
    for k, n in (("none", 28), ("w", 32), ("w", 32)): sess.step([k] * n)  # noqa: E701
    assert sess.yarn_q_chunks == 3 and yq.q_scale == 1.0 and [scales[3 * c][1] for c in range(6)] == [1.0, 1.0, 1.0, YQ.scale_for_chunk(3, 18, 1560), *((YQ.scale_for_chunk(4, 18, 1560),) * 2)]
    assert "yarn_q" not in (off := F.FlagStats(False, "goal", False, False)).summary("GC033") and "yarn_q" not in off.total_line()
    shared, attached = _fake_model(1), []
    shared.modules = lambda: [shared, *shared.blocks]
    sp = SimpleNamespace(model=shared, local_attn_size=18, sink_size=6, _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), sp, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test"); monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)  # noqa: E702
    def fake_import(fresh=True):
        def run_task(t, eng, out, args):
            if eng.session and eng.session.yarn_q is not None: R.STATS.yarn_q_chunks += 5  # noqa: E701
            (d := tmp_path / t["task_id"]).mkdir(parents=True, exist_ok=True); (d / f"{t['task_id']}_result.json").write_text(json.dumps({"task_id": t["task_id"], "success": True}))  # noqa: E702
            return {"task_id": t["task_id"], "success": True}
        ra = SimpleNamespace(run_task=run_task, decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")
        ra.main = lambda: (attached.append(hasattr(shared, "_yarn_q")) if (eng := ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16))) else None) or (ra.run_task({"task_id": "GC033"}, eng, tmp_path, None) and 0)
        return ra
    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py"]) == 0 and R.main(["run.py", "--lingbot-yarn-q", "--lingbot-local-attn", "36"]) == 0 and json.loads((tmp_path / "GC033" / "GC033_result.json").read_text())["lingbot_flags"]["yarn_q_chunks"] == 5
    assert R.main(["run.py"]) == 0 and "yarn_q" not in json.loads((tmp_path / "GC033" / "GC033_result.json").read_text())["lingbot_flags"] and attached == [False, True, False] and "forward" not in shared.blocks[0].self_attn.norm_q.__dict__
    out = capsys.readouterr().out.splitlines()
    lines, totals = [ln for ln in out if ln.startswith("[lingbot] flags task=")], [ln for ln in out if ln.startswith("[lingbot] flags total")]
    assert lines[0] == lines[2] and "yarn_q" not in lines[0] and "yarn_q=on yarn_q_chunks=5" in lines[1] and "yarn_q=on yarn_q_chunks=5" in totals[1]
