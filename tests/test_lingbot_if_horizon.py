"""IF horizon: the chunk budget, the decide_action wrapper and its counters. No GPU, no API calls."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import if_horizon as IH  # noqa: E402

ARGS = SimpleNamespace(chunk_frames=33, action_frame_unit=20)
IF052 = {"task_id": "IF052", "category": "IF", "prompt": "The boy walks forward.", "segs": [("W", 8)]}


def segs(task):  # stand-in for run_agent.parse_segments
    return task["segs"]


def test_budget_is_twice_the_dataset_action_with_a_floor():
    assert IH.budget(IF052, segs) == 10                                   # 8 tokens x 20 frames x 2 / 32
    assert IH.budget({"segs": [("W", 10)]}, segs) == 13                   # w*10: 12.5 rounds up
    assert IH.budget({"segs": [("W", 4), ("W", 1)]}, segs) == 7           # w*4 -> interact: 6.25 rounds up
    assert IH.budget({"segs": [("LEFT", 2)]}, segs) == 6                  # floor
    assert IH.budget(IF052, segs, mult=1.0, floor=1) == 5                 # the dataset action itself


def _wrapped(**kw):
    calls, events = [], []

    def player(task, frame, recent, chunk_idx, num_chunks, args, **kwargs):
        calls.append((chunk_idx, num_chunks))
        return "W"

    return IH.wrap(player, segs, on_event=lambda kind, cap: events.append((kind, cap)), **kw), calls, events


def test_player_is_told_the_budget_then_the_wrapper_ends(capsys):
    decide, calls, events = _wrapped()
    actions = [decide(IF052, None, ["W"] * i, i, 30, ARGS) for i in range(11)]
    assert actions == ["W"] * 10 + ["END"]
    assert calls == [(i, 10) for i in range(10)]                          # step limit shown to the player is 10
    assert events[-1] == ("end", 10) and events.count(("armed", 10)) == 11
    assert "[lingbot] IF horizon: IF052 reached its budget of 10 chunks -> END" in capsys.readouterr().out


def test_budget_never_exceeds_the_harness_limit():
    decide, calls, _ = _wrapped()
    assert decide(IF052, None, [], 5, 6, ARGS) == "W" and calls == [(5, 6)]
    assert decide(IF052, None, [], 6, 6, ARGS) == "END"


def test_other_families_and_wait_only_pass_through_unchanged():
    decide, calls, events = _wrapped()
    gc = {"task_id": "GC033", "category": "GC", "segs": [("LEFT", 4)]}
    assert decide(gc, None, [], 29, 30, ARGS) == "W"
    assert decide(IF052, None, [], 29, 30, ARGS, stationary_only=True) == "W"
    assert decide(IF052, None, [], 29, 30, ARGS, allow_next=True) == "W"
    assert calls == [(29, 30)] * 3 and events == []


def test_env_sets_mult_and_floor(monkeypatch):
    monkeypatch.setenv("LINGBOT_IF_HORIZON_MULT", "1")
    monkeypatch.setenv("LINGBOT_IF_HORIZON_MIN", "3")
    decide, calls, _ = _wrapped()
    assert decide(IF052, None, [], 4, 30, ARGS) == "W" and calls == [(4, 5)]
    assert decide(IF052, None, [], 5, 30, ARGS) == "END"


def test_flag_line_only_grows_when_the_flag_is_on():
    off = F.FlagStats(False, "goal", False, False)
    assert "if_horizon" not in F.FlagStats.line(off.summary("IF052")) and "if_horizon" not in off.total_line()
    st = F.FlagStats(False, "goal", False, False, if_horizon=True)
    assert F.FlagStats.line(st.summary("GC033")).endswith("if_horizon=skip if_horizon_chunks=0 if_horizon_ends=0")
    st.if_horizon_event("armed", 10)
    st.if_horizon_event("end", 10)
    assert F.FlagStats.line(st.finish_task("IF052")).endswith("if_horizon=on if_horizon_chunks=10 if_horizon_ends=1")
    st.new_task()
    st.finish_task("GC033")
    assert st.total_line().endswith("if_horizon_tasks=1 if_horizon_ends=1")


def test_configure_strips_the_flag_and_is_off_by_default():
    from adapters.lingbot_world2 import run as RUN
    flags, argv = RUN.configure(["run.py", "--tasks", "IF052"], environ={})
    assert flags["if_horizon"] is False and argv == ["run.py", "--tasks", "IF052"]
    flags, argv = RUN.configure(["run.py", "--lingbot-if-horizon", "--tasks", "IF052"], environ={})
    assert flags["if_horizon"] is True and argv == ["run.py", "--tasks", "IF052"]
    assert RUN.configure(["run.py"], environ={"LINGBOT_IF_HORIZON": "1"})[0]["if_horizon"] is True


def test_budgets_on_the_real_dataset_with_upstream_parse_segments():
    data = ROOT / "data" / "if" / "data.json"
    if not data.is_file():
        pytest.skip("dataset JSON not present")
    from adapters.common.upstream import import_run_agent
    run_agent = import_run_agent()
    tasks = {t["task_id"]: t for t in json.loads(data.read_text())}
    caps = {tid: IH.budget(t, run_agent.parse_segments) for tid, t in tasks.items()}
    assert all(IH.is_if(t) for t in tasks.values())
    assert caps["IF052"] == 10 and caps["IF002"] == 13 and caps["IF010"] == 18
    assert caps["IF034"] == 6                                             # `interact(...)` without a count is not a token
    assert caps["IF033"] >= 30                                            # no parsable action: upstream's W*80, so no cut
    assert sum(c < 30 for c in caps.values()) == 48 and len(caps) == 50
