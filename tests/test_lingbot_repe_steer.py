"""CPU-only tests for --lingbot-repe-steer (no GPU, no external API calls)."""
from __future__ import annotations
import json, sys, numpy as np, pytest  # noqa: E401
from types import SimpleNamespace
from adapters.common import prompts
from adapters.lingbot_world2 import flag_stats as F, repe_steer as REPE, run as R, session as S

class _T:
    def __init__(self, a, dt=np.float32): self.a = np.asarray(a, dtype=dt); self.dtype, self.shape, self.ndim = self.a.dtype, self.a.shape, self.a.ndim  # noqa: E702
    clone = lambda s: _T(s.a.copy(), s.dtype); float = lambda s: _T(s.a, np.float32); to = lambda s, d: _T(s.a, d)  # noqa: E702,E731
    new_zeros = lambda s, sh: _T(np.zeros(sh, s.dtype), s.dtype); new_empty = lambda s, sh: _T(np.empty(sh, s.dtype), s.dtype)  # noqa: E702,E731
    mean = lambda s, dim=None, keepdim=False: _T(s.a.mean(axis=dim, keepdims=keepdim), s.dtype); sqrt = lambda s: _T(np.sqrt(s.a), s.dtype)  # noqa: E702,E731
    __getitem__ = lambda s, i: _T(s.a[i], s.dtype); __float__ = lambda s: float(s.a)  # noqa: E702,E731
    def __setitem__(self, i, v): self.a[i] = getattr(v, "a", v)
    __add__ = lambda s, o: _T(s.a + getattr(o, "a", o), s.dtype); __sub__ = lambda s, o: _T(s.a - getattr(o, "a", o), s.dtype)  # noqa: E702,E731
    __mul__ = __rmul__ = lambda s, o: _T(s.a * getattr(o, "a", o), s.dtype); __truediv__ = lambda s, o: _T(s.a / getattr(o, "a", o), s.dtype)  # noqa: E702,E731

def test_cli_env_parsing_and_validation():
    flags0, rest0 = R.configure(["run.py", "--tasks", "OE001"], {})
    assert flags0["repe_steer"] == REPE.SteerConfig() and rest0 == ["run.py", "--tasks", "OE001"]
    flags, rest = R.configure(["run.py", "--lingbot-repe-steer", "--lingbot-repe-scale=0.8", "--tasks", "OE001"], {})
    assert flags["repe_steer"] == REPE.SteerConfig(True, 0.8, ("insight", "outsight")) and rest == ["run.py", "--tasks", "OE001"]
    assert REPE.parse(["--lingbot-repe-scale", "0.25"], {"LINGBOT_REPE_STEER": "1", "LINGBOT_REPE_FAMILIES": "GC, insight"}) == (REPE.SteerConfig(True, 0.25, ("gc", "insight")), [])
    for argv, env in ((["--lingbot-repe-scale=-0.1"], {}), (["--lingbot-repe-scale", "-0.5"], {}), (["--lingbot-repe-scale"], {}), (["--lingbot-repe-scale=inf"], {}),
                      (["--lingbot-repe-scale=nan"], {}), ([], {"LINGBOT_REPE_SCALE": "-1"}), ([], {"LINGBOT_REPE_FAMILIES": "bogus"}),
                      (["--lingbot-repe-steer", "--lingbot-stateless"], {}), (["--lingbot-repe-steer"], {"LINGBOT_SESSION": "0"})):
        with pytest.raises(SystemExit): R.configure(["run.py", *argv], environ=env)  # noqa: E701

def test_steer_tensors_math_norm_dtype_and_prompt_pair():
    rng = np.random.default_rng(7); p32, n32 = _T(rng.normal(1.0, 2.0, (12, 16))), _T(rng.normal(-0.5, 1.5, (12, 16)))  # noqa: E702
    z = REPE.steer_tensors([p32], [n32], 0.0)[0]; rms = lambda x: float(np.sqrt(np.mean(x.astype(np.float32) ** 2)))  # noqa: E702,E731
    assert z is not p32 and z.dtype == np.float32 and np.array_equal(z.a, p32.a) and REPE.prompt_pair("S.") == (f"S.\n{REPE.POS_CUE}", f"S.\n{REPE.NEG_CUE}")
    for dt, rtol in ((np.float32, 1e-6), (np.float16, 2e-3)):
        cp, cn = p32.to(dt), n32.to(dt); out = REPE.steer_tensors([cp], [cn], 0.6)[0]  # noqa: E702
        assert out.dtype == dt and out.shape == cp.shape and rms(out.a) == pytest.approx(rms(cp.a), rel=rtol)
        assert float(np.sum((out.a.astype(np.float64) - cp.a.astype(np.float64)) * (cp.a.astype(np.float64) - cn.a.astype(np.float64)))) > 0.0
    uneq = REPE.steer_tensors(p32, _T(rng.normal(0.0, 1.0, (8, 16))), 0.5)
    assert uneq.shape == p32.shape and rms(uneq.a) == pytest.approx(rms(p32.a), rel=1e-6)

def test_applies_to_session_and_flag_stats(tmp_path, monkeypatch):
    cfg, all_cfg = REPE.SteerConfig(enabled=True), REPE.SteerConfig(enabled=True, families=("gc", "if", "insight", "outsight"))
    ins = {"task_id": "OE001", "sub_category": "insight evolution", "questions": [{"q": "SECRET"}]}
    assert REPE.applies_to(ins, "OE001_chunk_01", cfg) and not REPE.applies_to(ins, "OE001_chunk_01", REPE.SteerConfig()) and not REPE.applies_to(ins, "OE999_chunk_01", cfg)
    assert REPE.applies_to({"task_id": "OE034", "sub_category": "out-of-sight evolution"}, "OE034_chunk_01", cfg) and REPE.applies_to({"task_id": "OE048", "sub_category": "outofsight evolution"}, "OE048_full", cfg)
    assert not REPE.applies_to({"task_id": "GC033", "category": "GC"}, "GC033_chunk_01", cfg) and not REPE.applies_to({"task_id": "IF010", "category": "IF"}, "IF010_chunk_01", cfg)
    assert REPE.applies_to({"task_id": "GC033", "category": "GC"}, "GC033_chunk_01", all_cfg) and REPE.applies_to(None, "IF010_full", all_cfg)
    seen = []; monkeypatch.setattr(S, "encode_prompt", lambda pipe, p, disk=None: seen.append((p, disk)) or [_T([[1.0, 2.0] if "Active" in p else [2.0, -1.0]])])  # noqa: E702
    sess = S.LingBotSession(SimpleNamespace(), 480 * 832, 5.0, t5_cache="disk"); sess.started, sess.prompt, sess._repe_scale = True, "old", 0.5  # noqa: E702
    assert sess.update_prompt("scene") and sess.repe_steered == 1 and len(seen) == 2 and all(d == "disk" for _, d in seen) and "repe_steer" not in F.FlagStats(False, "goal", False, False).summary("OE001")
    on, d = F.FlagStats(False, "auto", False, False, repe_steer=True), tmp_path / "OE001"; d.mkdir(); (d / "OE001_result.json").write_text('{"task_id":"OE001","success":true}')  # noqa: E702
    ra = SimpleNamespace(run_task=lambda t, *a: (on.repe_armed(), on.steered(1)) and {"task_id": t["task_id"], "success": True} if t["task_id"] == "OE001" else {"task_id": t["task_id"], "success": False})
    on.install(ra); r1 = ra.run_task({"task_id": "OE001"}, None, tmp_path, None); ra.run_task({"task_id": "GC033"}, None, tmp_path, None)  # noqa: E702
    assert r1["lingbot_flags"]["repe_steer"] == "on" and json.loads((d / "OE001_result.json").read_text())["lingbot_flags"]["repe_steered"] == 1 and on.summary("GC033")["repe_steer"] == "skip" and "repe_steered=1" in on.total_line()

def test_multi_arm_isolation(monkeypatch, capsys, tmp_path):
    for k in [k for k in R.os.environ if k.startswith("LINGBOT_")]: monkeypatch.delenv(k, raising=False)  # noqa: E701
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), SimpleNamespace(_t5_cache={}), tmp_path, False))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test"); monkeypatch.setattr(R.agent_api, "finish", lambda *a: None)  # noqa: E702
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    import imageio; from PIL import Image; monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None); monkeypatch.setattr(Image, "open", lambda p: SimpleNamespace(convert=lambda m: "img"))  # noqa: E401,E702
    def fake_import(fresh=True):
        ra = SimpleNamespace(decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")
        def run_task(t, eng, out, args):
            prompts._current["task"] = t
            eng.session = SimpleNamespace(started=False, repe_steered=0, chunk_id=2, reanchor_events=0, stream_decode=True, track=SimpleNamespace(translation_gain=1.0),
                step=lambda k, **kw: np.zeros((1, 2, 2, 3)), reset=lambda *a, **kw: setattr(eng.session, "repe_steered", eng.session.repe_steered + ("repe_scale" in kw)))
            eng._generate_session("i.jpg", "scene", "none-33", tmp_path, f"{t['task_id']}_chunk_01", 33); return {"task_id": t["task_id"], "success": False}  # noqa: E702
        ra.run_task = run_task
        ra.main = lambda: (ra.run_task({"task_id": "OE001", "sub_category": "insight evolution"}, eng := ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16)), tmp_path, None), ra.run_task({"task_id": "GC033", "category": "GC"}, eng, tmp_path, None), 0)[2]
        return ra
    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py"]) == 0 and R.main(["run.py", "--lingbot-repe-steer", "--lingbot-repe-scale=0.75"]) == 0 and R.main(["run.py"]) == 0 and not R.REPE_STEER.enabled
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[lingbot] flags ")]
    assert lines[0] == lines[6] and lines[1] == lines[7] and lines[2] == lines[8] and "repe_steer" not in lines[0] and "repe_steer=on repe_steered=1" in lines[3] and "repe_steer=skip repe_steered=0" in lines[4] and "repe_steered=1" in lines[5]
