"""CPU-only checks of chunk text, cached conditioning and runner isolation."""
from types import SimpleNamespace
import sys

import numpy as np
import pytest

from adapters.common import prompts
from adapters.lingbot_world2 import gc_director as D, run as R, session as S
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.mark.parametrize("key,motion", D.MOTION.items())
def test_current_command_only(key, motion):
    assert D.compose("A shop.", "GC033_chunk_02", f"{key}-32").endswith(f"camera {motion}.")


@pytest.mark.parametrize("name,action", [("IF017_chunk_01", "w-32"), ("GC033_full", "j-32"),
                                           ("GC033_chunk_01", "j-16,l-16"), ("GC033_chunk_01", "w+j-32")])
def test_scope_and_unsupported_actions(name, action):
    assert D.compose("scene", name, action) == "scene"


def test_text_refresh_preserves_visual_history_and_failed_encode(monkeypatch):
    session = S.LingBotSession(object(), 480 * 832, 5.0)
    session.started, session.prompt, session.context, session.cross_init = True, "old", "old embedding", True
    before = vars(session).copy()
    calls = []
    monkeypatch.setattr(S, "encode_prompt", lambda *args: calls.append(args) or "new embedding")
    assert not session.update_prompt("old") and not calls
    assert session.update_prompt("new") and session.context == "new embedding" and not session.cross_init
    assert all(vars(session)[k] is v for k, v in before.items() if k not in {"prompt", "context", "cross_init"})
    def fail(*args):
        raise RuntimeError("encode failed")
    monkeypatch.setattr(S, "encode_prompt", fail)
    with pytest.raises(RuntimeError, match="encode failed"):
        session.update_prompt("bad")
    assert session.prompt == "new" and session.context == "new embedding"


def test_generate_caption_scope_and_default(monkeypatch):
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    engine.session = object()
    monkeypatch.setattr(engine, "_generate_session", lambda image, prompt, *args: prompt)
    monkeypatch.setattr(R, "PROMPT_MODE", "auto")
    monkeypatch.setattr(R, "GC_DIRECTOR", True)
    monkeypatch.setattr(R, "STATS", FlagStats(False, "auto", False, False, gc_director=True))
    monkeypatch.setitem(prompts._current, "task", {"task_id": "GC033", "image_caption": "A shop."})
    call = lambda name: engine.generate(None, "Turn then return.", "j-32", None, name, 33)
    assert call("GC033_chunk_01") == "A shop.\nDuring this segment, the camera pans left."
    assert call("GC036_chunk_01") == "Turn then return."  # no matching caption
    assert R.STATS.gc_director_chunks == 1
    monkeypatch.setattr(R, "GC_DIRECTOR", False)
    assert call("GC033_chunk_02") == "A shop."


def test_continuation_refresh_is_wired_and_counted(monkeypatch, tmp_path):
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    calls = []
    engine.session = SimpleNamespace(started=True, chunk_id=2, reanchor_events=0, track=S.PoseTrack(),
        update_prompt=lambda p: calls.append(p) or True, step=lambda k: np.zeros((1, 2, 2, 3)))
    engine._last_chunk, engine.args = ("GC033", 1), SimpleNamespace(fps=16)
    monkeypatch.setattr(engine, "_calibrate", lambda *a: None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    import imageio
    monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None)
    monkeypatch.setattr(R, "GC_DIRECTOR", True)
    monkeypatch.setattr(R, "STATS", FlagStats(False, "auto", False, False, gc_director=True))
    engine._generate_session(None, "right", "l-32", tmp_path, "GC033_chunk_02", 33)
    assert calls == ["right"] and R.STATS.finish_task("GC033")["gc_director_updates"] == 1
    R.STATS.new_task()
    assert R.STATS.gc_director_updates == 0 and "gc_director_updates=1" in R.STATS.total_line()
    assert "gc_director" not in FlagStats(False, "goal", False, False).total_line()


def test_flag_validation_and_arm_reset(monkeypatch):
    flag = "--lingbot-gc-chunk-director"
    assert R.configure([flag, "--lingbot-caption-prompt"], {})[1] == []
    assert R.configure([], {"LINGBOT_GC_CHUNK_DIRECTOR": "1", "LINGBOT_PROMPT_MODE": "caption"})[0]["gc_director"]
    for argv in ([flag], [flag, "--lingbot-caption-prompt", "--lingbot-stateless"]):
        with pytest.raises(SystemExit, match="requires"):
            R.configure(argv, {})
    monkeypatch.delenv("LINGBOT_GC_CHUNK_DIRECTOR", raising=False)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert R.main(["run.py", flag, "--lingbot-caption-prompt"]) == 0 and R.GC_DIRECTOR
    assert R.main(["run.py"]) == 0 and not R.GC_DIRECTOR and not R.STATS.gc_director
