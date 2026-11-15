"""Half-speed translation math, engine setup and matching player information."""
from types import SimpleNamespace

import numpy as np
import pytest

from adapters.common import agent_api
from adapters.lingbot_world2 import poses as P, session as S, player_hint as H, run as R
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.mark.parametrize("key", ["w", "s", "a", "d", "w+j", "none", "j", "i"])
def test_gain_changes_translation_not_rotation_across_chunks(key):
    full, slow = S.PoseTrack(), S.PoseTrack(translation_gain=0.5)
    for first in (True, False):
        keys = [key] * S.keys_needed(2, first)
        a, b = full.advance(keys), slow.advance(keys)
        assert np.allclose(b[:, :3, :3], a[:, :3, :3])
        assert np.allclose(b[:, :3, 3], a[:, :3, 3] * 0.5)
        assert np.allclose(slow.last[:3, 3], full.last[:3, 3] * 0.5)
    assert np.array_equal(P.key_delta(key), P.key_delta(key, 1.0))


def test_engine_scope_counter_and_hint_agree(monkeypatch):
    stats = FlagStats(False, "goal", False, True, if_slow=True)
    monkeypatch.setattr(R, "STATS", stats)
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    engine.session = SimpleNamespace(track=S.PoseTrack())
    keys = ["w"] * 28
    engine._configure_if_motion("IF002_chunk_01", keys)
    engine.session.track.advance(keys)
    state = H.replay(["W"], lambda a: "w", 33, True, False, translation_gain=0.5)
    assert state["forward"] == engine.session.track.last[2, 3] / 32
    assert stats.finish_task("IF002")["if_translation_frames"] == 28
    stats.new_task()
    engine._configure_if_motion("GC038_chunk_01", keys)
    assert engine.session.track.translation_gain == 1 and stats.if_translation_frames == 0
    engine._configure_if_motion("IF002_chunk_02", ["j"] * 32)
    assert stats.if_translation_frames == 0
    assert "if_translation_frames=28" in stats.total_line()
    sent = []
    decide = H.wrap(lambda task, *a, **k: sent.append(task["prompt"]) or "W",
                    lambda a: "w", True, False, if_slow=True)
    for tid in ("IF002", "GC038"):
        decide({"task_id": tid}, None, ["W"], 1, 30, SimpleNamespace())
    assert "0.5 of a normal step" in sent[0] and "one step forward" in sent[1]


def test_flag_defaults_stateless_guard_and_arm_reset(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    monkeypatch.setattr(R, "import_run_agent", lambda **kw:
                        SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    flag = "--lingbot-if-slow-translation"
    assert not R.configure([], {})[0]["if_slow"]
    assert R.configure(["run.py", flag, "--seed", "42"], {})[1] == ["run.py", "--seed", "42"]
    assert R.configure([], {"LINGBOT_IF_SLOW_TRANSLATION": "1"})[0]["if_slow"]
    with pytest.raises(SystemExit, match="requires session"):
        R.configure([flag, "--lingbot-stateless"], {})
    with pytest.raises(SystemExit, match="requires session"):
        R.configure([flag], {"LINGBOT_SESSION": "0"})
    R.main(["run.py", flag])
    assert R.STATS.if_slow
    R.main(["run.py"])
    assert not R.STATS.if_slow and R.STATS.if_translation_frames == 0
    assert "if_translation_frames" not in R.STATS.total_line()
