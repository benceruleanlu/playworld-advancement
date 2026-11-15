"""CPU-only camera trajectory and runner checks."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from adapters.lingbot_world2 import poses as P, session as S, run as R
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.mark.parametrize("calibrated", [False, True])
def test_same_endpoints_new_latent_velocities_and_return(calibrated):
    P.reset({})
    plain, eased = S.PoseTrack(), S.PoseTrack()
    try:
        for idx, key in enumerate(["j", "l", "i", "k", "j", "j", "l", "l"]):
            n = 28 if idx == 0 else 32
            if calibrated:
                P.calibrate(False, n)
            a, b = plain.advance([key] * n), eased.advance([key] * n, ease_turns=True)
            assert a.shape == b.shape == (8, 4, 4)
            assert np.allclose(plain.last, eased.last, atol=1e-12)
            assert not np.allclose(a[:, :3, :3], b[:, :3, :3])
            angles = np.arccos(np.clip((np.trace(b[:, :3, :3], axis1=1, axis2=2) - 1) / 2, -1, 1))
            nonzero = angles[1:] if idx == 0 else angles
            assert nonzero[0] < nonzero[len(nonzero) // 2] and np.allclose(b[:, :3, 3], 0)
        if calibrated:
            assert np.allclose(eased.last, np.eye(4), atol=1e-12)
    finally:
        P.reset()


@pytest.mark.parametrize("keys", [["none"] * 28, ["w"] * 28, ["w+j"] * 28, ["j"] * 12 + ["l"] * 16])
def test_non_pure_turn_is_bit_identical(keys):
    assert np.array_equal(S.PoseTrack().advance(keys), S.PoseTrack().advance(keys, ease_turns=True))


@pytest.mark.parametrize("tid,key,enabled,expected", [("GC033", "j", True, True),
    ("GC036", "l", False, False), ("IF017", "j", True, False), ("GC038", "w", True, False)])
def test_runner_routes_pose_option_and_records_count(monkeypatch, tmp_path, tid, key, enabled, expected):
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    calls = []
    engine.session = SimpleNamespace(started=True, track=SimpleNamespace(translation_gain=1.0), chunk_id=2, reanchor_events=0,
        step=lambda keys, **kw: calls.append((keys, kw)) or np.zeros((1, 2, 2, 3)))
    engine._last_chunk, engine.args = (tid, 1), SimpleNamespace(fps=16)
    monkeypatch.setattr(engine, "_calibrate", lambda *a: None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    import imageio
    monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None)
    monkeypatch.setattr(R, "GC_EASE_TURNS", enabled)
    stats = FlagStats(False, "goal", False, False, gc_ease_turns=enabled)
    monkeypatch.setattr(R, "STATS", stats)
    engine._generate_session(None, "goal", f"{key}-33", tmp_path, f"{tid}_chunk_02", 33)
    assert calls == [([key] * 32, {"ease_turns": True} if expected else {})]
    summary = stats.finish_task(tid)
    assert summary.get("gc_eased_turns", 0) == int(expected)
    stats.new_task()
    assert stats.gc_eased_turns == 0
    assert ("gc_ease_turns" in stats.total_line()) == enabled
    assert stats.totals["gc_eased_turns"] == int(expected)


def test_flag_defaults_and_per_arm_reset(monkeypatch):
    flag = "--lingbot-gc-ease-turns"
    assert R.configure([flag, "--seed", "42"], {})[1] == ["--seed", "42"]
    assert R.configure([], {"LINGBOT_GC_EASE_TURNS": "1"})[0]["gc_ease_turns"]
    with pytest.raises(SystemExit, match="session"):
        R.configure([flag, "--lingbot-stateless"], {})
    monkeypatch.delenv("LINGBOT_GC_EASE_TURNS", raising=False)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert R.main(["run.py", flag]) == 0 and R.GC_EASE_TURNS
    assert R.main(["run.py"]) == 0 and not R.GC_EASE_TURNS and not R.STATS.gc_ease_turns
