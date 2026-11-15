"""GC completion hints, runner wiring and counters: no GPU or API calls."""
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.common import agent_api, upstream
from adapters.lingbot_world2 import gc_completion as C, player_hint as H
from adapters.lingbot_world2.flag_stats import FlagStats

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("tid", ["GC033", "GC036", "IF017", "OE034", "OE001"])
def test_scope_task_copy_and_call_forwarding(tid):
    calls, hints, ends = [], [], []
    inner = lambda *a, **kw: calls.append((a, kw)) or "END"
    decide = C.wrap(inner, lambda: hints.append(1), lambda: ends.append(1))
    task = {"task_id": tid, "prompt": "Return, then move backward."}
    tail = (object(), ["LEFT"], 1, 30, object(), "RIGHT")
    assert decide(task, *tail, allow_next=True) == "END"
    sent, kw = calls[0]
    assert sent[1:] == tail and kw == {"allow_next": True}
    assert task["prompt"] == "Return, then move backward."
    if tid.startswith("GC"):
        assert sent[0] is not task and sent[0]["prompt"] == task["prompt"] + "\n" + C.REMINDER
        assert hints == ends == [1]
    else:
        assert sent[0] is task and hints == ends == []


def test_upstream_prompt_composes_with_pose_hint_and_preserves_actions(monkeypatch, capsys):
    ra = upstream.import_run_agent()
    sent, replies = [], iter(["RIGHT", "END"])
    monkeypatch.setattr(ra, "request_agent_action", lambda args, prompt, images: sent.append(prompt) or next(replies))
    stats = FlagStats(False, "goal", False, True, gc_completion=True)
    decide = H.wrap(ra.decide_action, ra.to_sana_key, session=True, turn_cal=False)
    decide = C.wrap(decide, stats.completion_hint, stats.completion_end)
    task = {"task_id": "GC033", "prompt": "Turn left, then return."}
    args = SimpleNamespace(chunk_frames=33, action_frame_unit=20)
    assert decide(task, None, [], 0, 30, args) == "RIGHT"
    assert decide(task, None, ["RIGHT"], 1, 30, args) == "END"
    assert all(C.REMINDER in p and "Commanded camera now" in p for p in sent)
    assert task["prompt"] == "Turn left, then return."
    summary = stats.finish_task("GC033")
    assert summary["gc_completion_hints"] == 2 and summary["gc_completion_ends"] == 1
    assert "gc_completion=on gc_completion_hints=2 gc_completion_ends=1" in capsys.readouterr().out
    stats.new_task()
    summary = stats.finish_task("IF017")
    assert summary["gc_completion_hints"] == summary["gc_completion_ends"] == 0
    assert stats.total_line().endswith("gc_completion=on gc_completion_hints=2 gc_completion_ends=1")


def test_counters_are_saved_with_task_result(tmp_path):
    path = tmp_path / "GC033" / "GC033_result.json"
    path.parent.mkdir()
    def run_task(*args):
        stats.completion_hint()
        stats.completion_end()
        path.write_text('{"success": true}')
        return {"success": True}
    ra = SimpleNamespace(run_task=run_task)
    stats = FlagStats(False, "goal", False, False, gc_completion=True)
    stats.install(ra)
    result = ra.run_task({"task_id": "GC033"}, None, tmp_path, None)
    saved = json.loads(path.read_text())["lingbot_flags"]
    assert saved == result["lingbot_flags"]
    assert saved["gc_completion_hints"] == saved["gc_completion_ends"] == 1


@pytest.mark.parametrize("mode", ["off", "flag", "env"])
def test_runner_flag_defaults_and_installation(monkeypatch, mode):
    calls = []
    def original(task, *args, **kw):
        calls.append(task)
        return "WAIT"
    ra = SimpleNamespace(decide_action=original, run_task=lambda *a: None, main=lambda: 0)
    monkeypatch.setattr(upstream, "import_run_agent", lambda: ra)
    monkeypatch.setattr(agent_api, "patch", lambda ra: "test")
    for name in ("LINGBOT_PLAYER_HINT", "LINGBOT_GC_COMPLETION_HINT"):
        monkeypatch.delenv(name, raising=False)
    flag = "--lingbot-gc-completion-hint"
    monkeypatch.setattr(sys, "argv", ["run.py", "--seed", "42"] + ([flag] if mode == "flag" else []))
    if mode == "env":
        monkeypatch.setenv("LINGBOT_GC_COMPLETION_HINT", "1")
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "adapters/lingbot_world2/run.py"))
    assert exc.value.code == 0 and sys.argv == ["run.py", "--seed", "42"]
    assert (ra.decide_action is original) == (mode == "off")
    task = {"task_id": "GC036", "prompt": "Pan, then recenter."}
    assert ra.decide_action(task, None, [], 0, 30, SimpleNamespace()) == "WAIT"
    assert (C.REMINDER in calls[0]["prompt"]) == (mode != "off")
