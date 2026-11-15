"""Camera/subject semantics, without API calls or GPU imports."""
from types import SimpleNamespace

import pytest

from adapters.common import agent_api, upstream
from adapters.lingbot_world2 import if_camera as C, run as R
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.mark.parametrize("tid,perspective,expected", [
    ("IF017", "third person", True), ("IF034", "third-person", True),
    ("IF017", "first person", False), ("GC033", "third person", False),
    ("OE001", "third person", False), ("IF017", "", False),
])
def test_scope_and_passthrough(tid, perspective, expected):
    calls, events = [], []
    answer = object()
    decide = C.wrap(lambda *a, **kw: calls.append((a, kw)) or answer, lambda: events.append(1))
    task = {"task_id": tid, "perspective": perspective, "prompt": "Walk forward."}
    tail = (None, ["RIGHT"], 1, 30, None)
    assert decide(task, *tail, stationary_only=False) is answer
    sent, kw = calls[0]
    assert sent[1:] == tail and kw == {"stationary_only": False}
    assert task["prompt"] == "Walk forward."
    assert (C.REMINDER in sent[0]["prompt"]) == expected
    assert len(events) == int(expected)


def test_real_player_prompt_and_counters(monkeypatch, capsys):
    ra = upstream.import_run_agent(fresh=True)
    sent = []
    monkeypatch.setattr(ra, "request_agent_action", lambda args, prompt, images: sent.append(prompt) or "WAIT")
    stats = FlagStats(False, "goal", False, False, if_camera=True)
    decide = C.wrap(ra.decide_action, stats.if_camera_hint)
    assert decide({"task_id": "IF017", "perspective": "third person", "prompt": "Walk."},
                  None, [], 0, 30, SimpleNamespace()) == "WAIT"
    assert C.REMINDER in sent[0]
    assert stats.finish_task("IF017")["if_camera_hints"] == 1
    assert "if_camera=on if_camera_hints=1" in capsys.readouterr().out
    stats.new_task()
    assert stats.summary("IF017")["if_camera_hints"] == 0
    assert "if_camera_hints=1" in stats.total_line()
    assert "if_camera" not in FlagStats(False, "goal", False, False).total_line()


def test_per_arm_installation_and_env(monkeypatch):
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    modules = []
    def fresh(**kw):
        ra = SimpleNamespace(decide_action=lambda *a, **k: "WAIT", run_task=lambda *a: None, main=lambda: 0)
        modules.append((ra, ra.decide_action))
        return ra
    monkeypatch.setattr(R, "import_run_agent", fresh)
    flag = "--lingbot-if-camera-hint"
    assert R.configure(["run.py", flag, "--seed", "42"], {})[1] == ["run.py", "--seed", "42"]
    assert R.configure([], {"LINGBOT_IF_CAMERA_HINT": "1"})[0]["if_camera"]
    R.main(["run.py", flag])
    modules[-1][0].decide_action({"task_id": "IF017", "perspective": "third person"})
    assert R.STATS.if_camera_hints == 1
    R.main(["run.py"])
    assert modules[-1][0].decide_action is modules[-1][1]
    assert not R.STATS.if_camera and R.STATS.if_camera_hints == 0
