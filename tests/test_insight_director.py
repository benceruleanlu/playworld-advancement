"""Fixed model direction: pure text and mocked engine routing, no GPU or APIs."""
from types import SimpleNamespace

import pytest

from adapters.common import agent_api, prompts
from adapters.lingbot_world2 import run as R
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.fixture(autouse=True)
def clean_task():
    prompts.reset()
    yield
    prompts.reset()


def record(task):
    ra = SimpleNamespace(run_task=lambda *a: None)
    prompts.install(ra)
    ra.run_task(task)


@pytest.mark.parametrize("category", ["insight evolution", "out-of-sight evolution", "", "IF"])
def test_scope_and_only_input_fields(category):
    task = {"task_id": "OE035", "sub_category": category, "image_caption": " Workers  lift a frame. ",
            "questions": [{"question": "DO NOT SEND"}], "oe_dynamicity_policy": "DO NOT SEND"}
    record(task)
    actual = prompts.directed_insight("existing model text", "OE035_chunk_01")
    if category == "insight evolution":
        # the cue alone on top of the caption: no "Task: <goal>" line (the goal is the player's "wait and observe")
        assert actual == "Workers lift a frame.\n" + prompts.INSIGHT_DIRECTION
    else:
        assert actual == "existing model text"
    assert "DO NOT SEND" not in actual and task["image_caption"].startswith(" ")
    assert prompts.directed_insight("existing", "OE034_chunk_01") == "existing"


def test_missing_caption_and_task_are_noops():
    assert prompts.directed_insight("existing", "OE001_chunk_01") == "existing"
    record({"task_id": "OE001", "sub_category": "insight evolution"})
    assert prompts.directed_insight("existing", "OE001_full") == "existing"


@pytest.mark.parametrize("session", [False, True])
@pytest.mark.parametrize("enabled,mode", [(False, "goal"), (True, "goal"), (True, "auto")])
def test_engine_gets_fixed_text_and_counts(monkeypatch, enabled, mode, session):
    stats = FlagStats(False, mode, False, False, insight_director=enabled)
    monkeypatch.setattr(R, "STATS", stats)
    monkeypatch.setattr(R, "PROMPT_MODE", mode)
    record({"task_id": "OE035", "sub_category": "insight evolution", "image_caption": "Workers lift a frame."})
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    engine.session = object() if session else None
    calls = []
    engine._generate_session = engine._generate_stateless = lambda *a: calls.append(a) or "video.mp4"
    for name in ("OE035_chunk_01", "OE035_chunk_02"):
        assert engine.generate("image.jpg", "wait and observe", "none-33", ".", name, 33) == "video.mp4"
    assert calls[0][1] == calls[1][1]
    assert (prompts.INSIGHT_DIRECTION in calls[0][1]) == enabled
    if enabled:
        assert calls[0][1] == "Workers lift a frame.\n" + prompts.INSIGHT_DIRECTION
    else:
        assert calls[0][1] == "wait and observe"
    summary = stats.finish_task("OE035")
    assert summary.get("insight_director_prompts", 0) == (2 if enabled else 0)
    stats.new_task()
    assert stats.insight_director_prompts == 0
    assert ("insight_director_prompts=2" in stats.total_line()) == enabled


def test_runner_flag_env_and_arm_reset(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    monkeypatch.setattr(R, "import_run_agent", lambda **kw:
                        SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    flag = "--lingbot-insight-director"
    assert R.configure(["run.py", flag, "--seed", "42"], {})[1] == ["run.py", "--seed", "42"]
    assert R.configure([], {"LINGBOT_INSIGHT_DIRECTOR": "1"})[0]["insight_director"]
    R.main(["run.py", flag])
    assert R.STATS.insight_director
    R.main(["run.py"])
    assert not R.STATS.insight_director and R.STATS.insight_director_prompts == 0
