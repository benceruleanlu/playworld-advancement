"""Gaussian coupling invariants and CPU-only runner/session plumbing."""
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from adapters.lingbot_world2 import noise_mean as N, session as S, run as R
from adapters.lingbot_world2.flag_stats import FlagStats


def test_gaussian_marginal_and_shared_dc_without_repeating_texture():
    rng = np.random.default_rng(42)
    first, fresh = rng.normal(size=(2, 50000, 1, 2, 2))
    original = fresh.copy()
    coupling = N.CoupledMean()
    assert coupling.apply(first, 0) is first
    out = coupling.apply(fresh, 0)
    assert np.array_equal(fresh, original)  # no in-place write
    assert np.allclose(out.mean((1, 2, 3)), first.mean((1, 2, 3)))
    assert np.allclose(out - out.mean((1, 2, 3), keepdims=True),
                       fresh - fresh.mean((1, 2, 3), keepdims=True))
    assert not np.allclose(out, first)
    assert np.allclose(np.cov(out.reshape(50000, 4).T), np.eye(4), atol=0.025)
    assert abs(out.mean()) < 0.01 and coupling.count == 1


def test_sampler_stages_shapes_and_session_reset_are_independent():
    session = S.LingBotSession(object(), 480 * 832, 5.0)
    x = np.random.default_rng(5).normal(size=(16, 4, 3, 2)).astype(np.float32)
    assert session._couple_noise(x, 0) is x
    session.noise_mean = N.CoupledMean()
    for stage in range(4):
        assert session._couple_noise(x + stage, stage).mean() == pytest.approx((x + stage).mean())
    for stage in range(4):
        out = session._couple_noise(x * 2, stage)
        assert out.mean() == pytest.approx((x + stage).mean(), abs=1e-6)
    assert session.noise_mean.count == 4 and len(session.noise_mean.anchors) == 4
    changed_shape = np.zeros((16, 4, 2, 2))
    assert session._couple_noise(changed_shape, 0) is changed_shape
    session._free()
    assert session.noise_mean is None and session._couple_noise(x, 0) is x
    with pytest.raises(ValueError, match="nonempty"):
        N.CoupledMean().apply(np.zeros((1, 0, 2, 2)), 0)


@pytest.mark.parametrize("name,enabled,expected", [("GC033_chunk_01", True, 4),
    ("IF010_chunk_01", True, 4), ("GC033_chunk_01", False, 0),
    ("GC033_full", True, 0), ("OE018_chunk_01", True, 0)])
def test_runner_scope_counts_and_continuation(monkeypatch, tmp_path, name, enabled, expected):
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    session = engine.session = S.LingBotSession(object(), 480 * 832, 5.0)
    engine._last_chunk, engine.args = None, SimpleNamespace(seed=42, fps=16)
    def reset(*a, **kw):
        session._free()
        session.noise_mean = N.CoupledMean() if kw["noise_mean"] else None
        session.track, session.started = S.PoseTrack(), True
    def step(keys):
        for block in range(2):
            for stage in range(4):
                session._couple_noise(np.ones((16, 4, 2, 2)) * block, stage)
        return np.zeros((1, 2, 2, 3))
    monkeypatch.setattr(session, "reset", reset)
    monkeypatch.setattr(session, "step", step)
    monkeypatch.setattr(engine, "_calibrate", lambda *a: None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    import imageio
    monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None)
    monkeypatch.setattr(R, "NOISE_MEAN", enabled)
    stats = FlagStats(False, "goal", False, False, noise_mean=enabled)
    monkeypatch.setattr(R, "STATS", stats)
    path = tmp_path / "input.png"
    Image.new("RGB", (2, 2)).save(path)
    engine._generate_session(path, "goal", "j-32", tmp_path, name, 33)
    assert stats.noise_mean_samples == expected
    if expected:
        engine._generate_session(path, "goal", "l-32", tmp_path, name.rsplit("_", 1)[0] + "_02", 33)
        assert stats.finish_task(name)["noise_mean_samples"] == 12
        stats.new_task()
        assert stats.noise_mean_samples == 0 and "noise_mean_samples=12" in stats.total_line()
    if not enabled:
        assert "noise_mean" not in stats.total_line()


def test_flag_and_arm_isolation(monkeypatch):
    flag = "--lingbot-noise-mean-coupling"
    assert R.configure([flag, "--seed", "42"], {})[1] == ["--seed", "42"]
    assert R.configure([], {"LINGBOT_NOISE_MEAN_COUPLING": "1"})[0]["noise_mean"]
    with pytest.raises(SystemExit, match="session"):
        R.configure([flag, "--lingbot-stateless"], {})
    monkeypatch.delenv("LINGBOT_NOISE_MEAN_COUPLING", raising=False)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert R.main(["run.py", flag]) == 0 and R.NOISE_MEAN
    assert R.main(["run.py"]) == 0 and not R.NOISE_MEAN and not R.STATS.noise_mean
