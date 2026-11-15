"""Model prompt routing and per-arm isolation, without GPU/API calls."""
import json
import sys
from types import SimpleNamespace
import pytest
from adapters.common import prompts
from adapters.lingbot_world2 import if_subject as I, run as R
from adapters.lingbot_world2.flag_stats import FlagStats

TASK = {"task_id": "IF010", "category": "IF", "perspective": "third person", "image_caption": "A robot dog."}


@pytest.mark.parametrize("perspective", ["third person", "third-person"])
def test_subject_goal_and_caption_are_preserved(perspective):
    task = dict(TASK, perspective=perspective)
    original = task.copy()
    goal = "Turn left, then walk forward."
    result = I.compose(task, goal, "IF010_chunk_01")
    assert result == f"Subject action: {goal}\nScene: A robot dog.\n{I.CUE}"
    assert task == original and I.compose(task, goal, "IF010_full") == result


@pytest.mark.parametrize("changes,name,goal", [({}, "IF017_chunk_01", "walk"),
    ({"task_id": "GC016"}, "GC016_chunk_01", "walk"), ({"perspective": "first person"}, "IF010_full", "walk"),
    ({"image_caption": "  "}, "IF010_chunk_01", "walk"), ({}, "IF010_chunk_01", " ")])
def test_missing_context_and_other_tasks_are_untouched(changes, name, goal):
    assert I.compose(dict(TASK, **changes), goal, name) is None


def test_engine_routing_and_saved_counters(monkeypatch, tmp_path, capsys):
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    engine.session = object()
    monkeypatch.setattr(engine, "_generate_session", lambda image, prompt, *a: prompt)
    monkeypatch.setattr(engine, "_generate_stateless", lambda image, prompt, *a: prompt)
    monkeypatch.setattr(R, "PROMPT_MODE", "auto")
    monkeypatch.setattr(R, "IF_SUBJECT", True)
    stats = FlagStats(False, "auto", False, False, if_subject=True)
    monkeypatch.setattr(R, "STATS", stats)
    monkeypatch.setitem(prompts._current, "task", TASK)
    goal = "Turn left, then walk forward."
    call = lambda: engine.generate(None, goal, "w-32", None, "IF010_chunk_01", 33)
    assert call() == I.compose(TASK, goal, "IF010_chunk_01")
    engine.session = None
    assert call() == I.compose(TASK, goal, "IF010_chunk_01")
    assert "IF subject director:" in capsys.readouterr().out
    path = tmp_path / "IF010" / "IF010_result.json"
    path.parent.mkdir()
    def task_run(*a):
        call()
        path.write_text('{"success": true}')
        return {"success": True}
    ra = SimpleNamespace(run_task=task_run)
    stats.install(ra)
    result = ra.run_task(TASK, None, tmp_path, None)
    assert json.loads(path.read_text())["lingbot_flags"] == result["lingbot_flags"]
    assert result["lingbot_flags"]["if_subject_prompts"] == 1
    stats.new_task()
    assert stats.if_subject_prompts == 0 and "if_subject_prompts=1" in stats.total_line()
    monkeypatch.setattr(R, "IF_SUBJECT", False)
    assert call() == f"A robot dog. {goal}"
    assert "if_subject" not in FlagStats(False, "goal", False, False).total_line()


def test_flag_validation_and_arm_reset(monkeypatch):
    flag = "--lingbot-if-subject-director"
    assert R.configure([flag, "--lingbot-caption-prompt"], {})[1] == []
    assert R.configure([], {"LINGBOT_IF_SUBJECT_DIRECTOR": "1", "LINGBOT_PROMPT_MODE": "auto"})[0]["if_subject"]
    with pytest.raises(SystemExit, match="caption"):
        R.configure([flag], {})
    monkeypatch.delenv("LINGBOT_IF_SUBJECT_DIRECTOR", raising=False)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert R.main(["run.py", flag, "--lingbot-caption-prompt"]) == 0 and R.IF_SUBJECT
    assert R.main(["run.py"]) == 0 and not R.IF_SUBJECT and not R.STATS.if_subject
