"""CPU-only tests for --lingbot-ou-noise (no GPU, no external API calls)."""
from __future__ import annotations
import contextlib, json, sys  # noqa: E401
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from adapters.lingbot_world2 import ou_noise as OU, run as R, session as S


class _T(np.ndarray):
    device = "cpu"
    def __new__(cls, a): return np.asarray(a, dtype=np.float32).view(cls)
    def sqrt(self): return _T(np.sqrt(self))
    def clamp_min(self, lo): return _T(np.maximum(self, lo))
    def clamp(self, lo, hi): return _T(np.clip(self, lo, hi))
    def to(self, d): return np.asarray(self).astype(d).view(_T) if d is np.uint8 else self
    def permute(self, *ax): return np.transpose(self, ax).view(_T)
    def cpu(self): return self
    def detach(self): return self
    def numpy(self): return np.asarray(self)
    def clone(self): return _T(self.copy())


def test_cli_and_env_parsing_and_validation():
    assert R.configure(["run.py", "--tasks", "OE001"], environ={}) == (R.configure(["run.py"], environ={})[0], ["run.py", "--tasks", "OE001"])
    assert R.configure(["run.py"], environ={})[0]["ou_noise"] == OU.OUNoiseConfig(False, 0.35, True)
    flags, rest = R.configure(["run.py", "--lingbot-ou-noise", "--lingbot-ou-rho=0.5", "--tasks", "OE001"], environ={})
    assert flags["ou_noise"] == OU.OUNoiseConfig(True, 0.5, True) and rest == ["run.py", "--tasks", "OE001"]
    assert OU.parse(["run.py", "--lingbot-ou-rho", "0.0"], environ={"LINGBOT_OU_NOISE": "1", "LINGBOT_OU_STRATIFY": "0"})[0] == OU.OUNoiseConfig(True, 0.0, False)
    with pytest.raises(SystemExit, match="session mode"): R.configure(["run.py", "--lingbot-ou-noise", "--lingbot-stateless"], environ={})  # noqa: E701
    for argv, env in ((["--lingbot-ou-rho"], {}), (["--lingbot-ou-rho", "--tasks"], {}), (["--lingbot-ou-rho=-0.01"], {}),
                      (["--lingbot-ou-rho=1.0"], {}), (["--lingbot-ou-rho=nan"], {}), ([], {"LINGBOT_OU_RHO": "1.2"}), ([], {"LINGBOT_OU_STRATIFY": "2"})):
        with pytest.raises(SystemExit): OU.parse(["run.py", *argv], environ=env)  # noqa: E701


@pytest.mark.parametrize("wrap", [lambda a: a, _T])
def test_identity_moments_temporal_correlation_seam_and_reset(wrap):
    rng = np.random.default_rng(123)
    raw = wrap(rng.standard_normal((4, 4, 32, 32), dtype=np.float32))
    snap = np.array(raw, copy=True)
    assert OU.OUNoiseFilter(OU.OUNoiseConfig(True, 0.0, False)).apply(raw) is raw and np.array_equal(raw, snap)
    filt = OU.OUNoiseFilter(OU.OUNoiseConfig(True, 0.35, True))
    c0, c1 = (np.asarray(filt.apply(wrap(rng.standard_normal((4, 4, 256, 256), dtype=np.float32)))) for _ in range(2))
    for ch in (c0, c1):
        assert np.max(np.abs(ch.mean(axis=(-2, -1)))) < 1e-5 and np.max(np.abs(ch.var(axis=(-2, -1)) - 1.0)) < 1e-2
        assert all(np.corrcoef(ch[:, f - 1].ravel(), ch[:, f].ravel())[0, 1] == pytest.approx(0.35, abs=0.015) for f in range(1, 4))
    assert np.corrcoef(c0[:, -1].ravel(), c1[:, 0].ravel())[0, 1] == pytest.approx(0.35, abs=0.015)
    filt.reset()
    c2 = np.asarray(filt.apply(wrap(rng.standard_normal((4, 4, 256, 256), dtype=np.float32))))
    assert filt.prev_last is not None and abs(np.corrcoef(c1[:, -1].ravel(), c2[:, 0].ravel())[0, 1]) < 0.015


def test_session_step_flag_stats_and_gen_arms_isolation(monkeypatch, tmp_path, capsys):
    draws, x_in, nc = [], [], lambda *a, **kw: contextlib.nullcontext()
    randn = lambda *s, **kw: (draws.append(sh := s[0] if isinstance(s[0], tuple) else s), _T(np.random.default_rng(len(draws)).standard_normal(sh, dtype=np.float32)))[1]  # noqa: E731
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        amp=SimpleNamespace(autocast=nc), autocast=nc, no_grad=nc, float32=np.float32, uint8=np.uint8, randn=randn,
        cuda=SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0),
        stack=lambda xs: _T(xs), cat=lambda xs, dim=0: _T(np.concatenate(xs, axis=dim))))
    monkeypatch.setattr(__import__("imageio"), "mimsave", lambda *a, **kw: None)

    def make_sess(ou=None):
        pipe = SimpleNamespace(device="cpu", param_dtype="bf16", _convert_flow_pred_to_x0=lambda flow_pred, **kw: flow_pred, scheduler=SimpleNamespace(add_noise=lambda x0, *a: x0),
                               model=lambda x, t, **kw: (x_in.append(np.array(x[0], copy=True)) if float(t[0]) == 1000.0 else None) or x)
        s = S.LingBotSession(pipe, 480 * 832, 5.0, stream_decode=True, ou_noise=ou)
        s.started, s.track, s.y, s.lat_h, s.lat_w, s.frame_seqlen, s.max_seq_len, s.kv_size = True, S.PoseTrack(), np.zeros((20, 32, 32, 32)), 32, 32, 256, 1024, 4096
        s.context, s.kv, s.cross, s.cross_init, s.gen, s.timesteps = ["c"], [], [], False, None, [1000.0, 750.0, 500.0, 250.0]
        s._plucker, s._decode = lambda r: SimpleNamespace(chunk=lambda *a, **kw: ("e",)), lambda lat: _T(np.zeros((3, 4 * lat.shape[1] - (3 if s.chunk_id <= 2 else 0), 4, 4)))
        return s

    make_sess().step(["none"] * 28); n_base = len(draws); draws.clear(); x_in.clear()  # noqa: E702
    ou_sess = make_sess(OU.OUNoiseFilter(OU.OUNoiseConfig(True, 0.35, True)))
    ou_sess.step(["none"] * 28); ou_sess.step(["none"] * 32)  # noqa: E702
    assert len(draws) == 2 * n_base and ou_sess.ou_chunks == 4 and np.corrcoef(x_in[1][:, -1].ravel(), x_in[2][:, 0].ravel())[0, 1] == pytest.approx(0.35, abs=0.03)
    ou_sess._free(); assert ou_sess.ou_noise.prev_last is None  # noqa: E702
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), SimpleNamespace(_t5_cache={}), tmp_path, False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test"); monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)  # noqa: E702
    saved, p = [], tmp_path / "OE001" / "OE001_result.json"
    def run_task(task, eng, out, args):
        if eng.session.ou_noise is not None:
            eng._last_chunk, eng.session = ("OE001", 1), make_sess(eng.session.ou_noise)
            eng.session.track.prev_latent, eng.session.chunk_id, eng.session._last_frame = np.eye(4), 2, np.zeros((4, 4, 3), dtype=np.uint8)
            eng._generate_session(None, "g", "none-32", out, "OE001_chunk_02", 33)
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({"task_id": "OE001", "success": True}))  # noqa: E702
        return {"task_id": "OE001", "success": True}
    monkeypatch.setattr(R, "import_run_agent", lambda fresh=True: (ra := SimpleNamespace(run_task=run_task, decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none"),
        setattr(ra, "main", lambda: (ra.run_task({"task_id": "OE001"}, ra.SanaWMEngine(SimpleNamespace(max_total_frames=65, seed=0, fps=16)), tmp_path, None),
                                     saved.append(json.loads(p.read_text())["lingbot_flags"]), 0)[2]))[0])
    assert R.main(["run.py"]) == 0 and R.main(["run.py", "--lingbot-ou-noise"]) == 0 and R.main(["run.py"]) == 0
    out = capsys.readouterr().out
    assert "ou-noise on (rho=0.35, stratify=on)" in out and "ou_noise=on ou_chunks=2" in out
    assert "ou_noise" not in saved[0] and saved[1]["ou_noise"] == "on" and saved[1]["ou_chunks"] == 2 and "ou_noise" not in saved[2]
