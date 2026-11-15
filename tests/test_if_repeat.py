"""Repeated controls are a prompt trigger, never a forced failure or action."""
from types import SimpleNamespace

import pytest

from adapters.common import agent_api, upstream
from adapters.lingbot_world2 import if_repeat as C, run as R
from adapters.lingbot_world2.flag_stats import FlagStats


@pytest.mark.parametrize("tid,actions,expected", [
    ("IF002", [], False), ("IF002", ["W"] * 3, False), ("IF002", ["W"] * 4, True),
    ("IF017", ["RIGHT"] * 29, True), ("IF034", ["WAIT"] * 4, True),
    ("IF002", ["W"] * 4 + ["LEFT"], False), ("IF002", ["END"] * 4, False),
    ("GC033", ["LEFT"] * 4, False), ("OE001", ["WAIT"] * 4, False),
])
def test_trigger_scope_and_passthrough(tid, actions, expected):
    calls, events = [], []
    answer = object()
    decide = C.wrap(lambda *a, **k: calls.append((a, k)) or answer, lambda: events.append(1))
    task = {"task_id": tid, "prompt": "Keep walking forward."}
    tail = (None, actions, len(actions), 30, SimpleNamespace())
    assert decide(task, *tail, allow_stop=True) is answer
    sent, kw = calls[0]
    assert sent[1:] == tail and kw == {"allow_stop": True}
    assert task["prompt"] == "Keep walking forward."
    assert (C.REMINDER in sent[0]["prompt"]) == expected and len(events) == int(expected)


def test_actual_player_can_continue_after_check(monkeypatch):
    ra = upstream.import_run_agent(fresh=True)
    sent = []
    monkeypatch.setattr(ra, "request_agent_action", lambda a, p, images: sent.append(p) or "W")
    stats = FlagStats(False, "goal", False, False, if_repeat=True)
    decide = C.wrap(ra.decide_action, stats.if_repeat_hint)
    assert decide({"task_id": "IF002", "prompt": "Keep walking forward into the bench."}, None, ["W"] * 4,
                  4, 30, SimpleNamespace()) == "W"
    assert C.REMINDER in sent[0] and "Keep walking forward into the bench." in sent[0]
    assert stats.finish_task("IF002")["if_repeat_checks"] == 1
    stats.new_task()
    assert stats.if_repeat_checks == 0 and "if_repeat_checks=1" in stats.total_line()
    assert "if_repeat_checks" not in FlagStats(False, "goal", False, False).total_line()


def test_runner_flag_env_and_reset(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    modules = []
    def fresh(**kw):
        ra = SimpleNamespace(decide_action=lambda *a, **k: "W", run_task=lambda *a: None, main=lambda: 0)
        modules.append((ra, ra.decide_action))
        return ra
    monkeypatch.setattr(R, "import_run_agent", fresh)
    flag = "--lingbot-if-repeat-check"
    assert R.configure(["run.py", flag, "--seed", "42"], {})[1] == ["run.py", "--seed", "42"]
    assert R.configure([], {"LINGBOT_IF_REPEAT_CHECK": "1"})[0]["if_repeat"]
    R.main(["run.py", flag])
    modules[-1][0].decide_action({"task_id": "IF002"}, None, ["W"] * 4)
    assert R.STATS.if_repeat_checks == 1
    R.main(["run.py"])
    assert modules[-1][0].decide_action is modules[-1][1]
    assert not R.STATS.if_repeat and R.STATS.if_repeat_checks == 0
