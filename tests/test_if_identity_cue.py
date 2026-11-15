"""CPU-only identity cue, actual prompt routing and result bookkeeping."""
import json
import sys
from types import SimpleNamespace
import pytest
from adapters.common import prompts
from adapters.lingbot_world2 import if_identity as I, run as R
from adapters.lingbot_world2.flag_stats import FlagStats

TASK = {"task_id": "IF010", "category": "IF", "perspective": "third person", "image_caption": "A robot dog."}


@pytest.mark.parametrize("task,name", [(None, "IF010_chunk_01"), (TASK, "IF031_chunk_01"),
    (dict(TASK, task_id="GC016"), "GC016_full"), (dict(TASK, perspective="first person"), "IF010_full"),
    (dict(TASK, image_caption=" "), "IF010_full")])
def test_scope_and_missing_context(task, name):
    assert I.compose(task, "unchanged", name) is None


def test_preserves_original_text_and_task():
    task = dict(TASK, perspective="third-person")
    original = task.copy()
    prompt = "A robot dog. Turn left, then walk forward."
    assert I.compose(task, prompt, "IF010_full") == prompt + "\n" + I.CUE
    assert task == original


def test_generate_both_paths_and_result_json(monkeypatch, tmp_path, capsys):
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    engine.session = object()
    monkeypatch.setattr(engine, "_generate_session", lambda image, prompt, *a: prompt)
    monkeypatch.setattr(engine, "_generate_stateless", lambda image, prompt, *a: prompt)
    monkeypatch.setattr(R, "PROMPT_MODE", "auto")
    monkeypatch.setattr(R, "IF_IDENTITY", True)
    stats = FlagStats(False, "auto", False, False, if_identity=True)
    monkeypatch.setattr(R, "STATS", stats)
    monkeypatch.setitem(prompts._current, "task", TASK)
    call = lambda name: engine.generate(None, "Walk forward.", "w-32", None, name, 33)
    assert call("IF010_chunk_01") == "A robot dog. Walk forward.\n" + I.CUE
    engine.session = None
    assert call("IF010_chunk_02").endswith(I.CUE)
    assert call("IF031_chunk_01") == "Walk forward."
    assert "IF identity cue:" in capsys.readouterr().out
    path = tmp_path / "IF010" / "IF010_result.json"
    path.parent.mkdir()
    def task_run(*a):
        call("IF010_chunk_01")
        path.write_text('{"success": true}')
        return {"success": True}
    ra = SimpleNamespace(run_task=task_run)
    stats.install(ra)
    result = ra.run_task(TASK, None, tmp_path, None)
    assert json.loads(path.read_text())["lingbot_flags"] == result["lingbot_flags"]
    assert result["lingbot_flags"]["if_identity_prompts"] == 1
    stats.new_task()
    assert stats.if_identity_prompts == 0 and "if_identity_prompts=1" in stats.total_line()
    monkeypatch.setattr(R, "IF_IDENTITY", False)
    assert call("IF010_chunk_02") == "A robot dog. Walk forward."
    assert "if_identity" not in FlagStats(False, "goal", False, False).total_line()


def test_flag_requires_scene_and_goal_and_resets_between_arms(monkeypatch):
    flag = "--lingbot-if-identity-cue"
    assert R.configure([flag, "--lingbot-caption-prompt"], {})[1] == []
    assert R.configure([], {"LINGBOT_IF_IDENTITY_CUE": "1", "LINGBOT_PROMPT_MODE": "auto"})[0]["if_identity"]
    for mode in ("goal", "caption"):
        with pytest.raises(SystemExit, match="scene plus IF goal"):
            R.configure([flag], {"LINGBOT_PROMPT_MODE": mode})
    monkeypatch.delenv("LINGBOT_IF_IDENTITY_CUE", raising=False)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert R.main(["run.py", flag, "--lingbot-caption-prompt"]) == 0 and R.IF_IDENTITY
    assert R.main(["run.py"]) == 0 and not R.IF_IDENTITY and not R.STATS.if_identity
