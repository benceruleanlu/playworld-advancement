"""Player hint: commanded-camera replay and the decide_action wrapper. No GPU, no API calls."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import player_hint as H  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402

KEY = {"W": "w", "S": "s", "A": "a", "D": "d", "LEFT": "j", "RIGHT": "l", "UP": "i", "DOWN": "k", "WAIT": "none"}.get
ARGS = SimpleNamespace(chunk_frames=33, action_frame_unit=20)


def replay(actions, session=True, turn_cal=True):
    return H.replay(actions, KEY, 33, session, turn_cal)


def test_step_keys_match_the_engine():
    assert [H.step_keys(i, 33, True) for i in range(3)] == [28, 32, 32]  # session.keys_needed
    assert H.step_keys(0, 33, False) == 44  # stateless pads 33 frames to 45


def test_default_rates_are_reported_as_they_are():
    yaw, pitch = H.step_size(33, True, False)
    assert yaw == pytest.approx(32 * 0.03 * 180 / 3.141592653589793, abs=1e-6)  # 55 degrees, not 45
    assert pitch == pytest.approx(32 * 0.01 * 180 / 3.141592653589793, abs=1e-6)
    s = replay(["LEFT", "LEFT"], turn_cal=False)
    assert s["heading"] == pytest.approx(-(28 + 32) * 0.03 * 180 / 3.141592653589793, abs=1e-6)


def test_turn_cal_steps_are_45_and_40_and_globals_are_restored():
    before = (P.YAW, P.PITCH)
    assert H.step_size(33, True, True) == pytest.approx((45.0, 40.0))
    assert H.step_size(33, False, True) == pytest.approx((45.0, 40.0))
    assert replay(["LEFT", "LEFT"])["heading"] == pytest.approx(-90.0)  # first chunk has 28 keys, still 45
    assert (P.YAW, P.PITCH) == before


def test_out_and_back_returns_to_the_start():
    s = replay(["RIGHT"] * 4 + ["LEFT"] * 4)
    assert s["heading"] == pytest.approx(0.0, abs=1e-6) and s["tilt"] == pytest.approx(0.0, abs=1e-6)
    assert (s["turned_left"], s["turned_right"]) == pytest.approx((180.0, 180.0))


def test_full_turn_wraps_heading_but_total_keeps_counting():
    s = replay(["RIGHT"] * 8)
    assert abs(s["heading"]) < 1e-6 and s["turned_right"] == pytest.approx(360.0)


def test_position_is_in_the_start_frame():
    s = replay(["WAIT", "W", "RIGHT", "RIGHT", "W"])  # forward, face right, forward again
    assert s["forward"] == pytest.approx(1.0) and s["right"] == pytest.approx(1.0)
    assert replay(["WAIT", "S", "A"])["forward"] == pytest.approx(-1.0)
    assert replay(["WAIT", "S", "A"])["right"] == pytest.approx(-1.0)


def test_tilt_sign():
    assert replay(["UP"])["tilt"] == pytest.approx(40.0)
    assert replay(["DOWN"])["tilt"] == pytest.approx(-40.0)


def test_hint_text():
    t = H.hint(["RIGHT", "RIGHT", "UP"], KEY, 33, True, True)
    assert "one LEFT or RIGHT turns the camera about 45 degrees" in t
    assert "heading 90 degrees right, tilt 40 degrees up, position 0.0 steps and 0.0 steps" in t
    assert t.endswith("0 degrees left, 90 degrees right.")
    assert "heading 0 degrees, tilt 0 degrees" in H.hint([], KEY, 33, True, True)


def test_wrap_appends_to_a_copy_and_skips_wait_only_tasks():
    seen = []
    inner = lambda task, *a, **kw: seen.append((task, a, kw)) or "LEFT"  # noqa: E731
    decide = H.wrap(inner, KEY, session=True, turn_cal=True)
    task = {"task_id": "OE034", "prompt": "Turn the camera right 90 degrees, then return to the starting view."}
    assert decide(task, None, ["RIGHT", "RIGHT"], 2, 30, ARGS, dataset_action="W") == "LEFT"
    sent, a, kw = seen[0]
    assert sent["prompt"].startswith(task["prompt"] + "\nControls: ")
    assert "heading 90 degrees right" in sent["prompt"]
    assert task["prompt"].endswith("starting view.") and sent["task_id"] == "OE034"  # original untouched
    assert a == (None, ["RIGHT", "RIGHT"], 2, 30, ARGS) and kw == {"dataset_action": "W"}
    decide(task, None, [], 0, 30, ARGS, stationary_only=True)
    assert seen[1][0] is task


@pytest.mark.skipif(importlib.util.find_spec("httpx") is None, reason="upstream run_agent needs httpx")
def test_hint_reaches_the_upstream_player_prompt(monkeypatch):
    from adapters.common.upstream import import_run_agent
    ra = import_run_agent()
    prompts = []
    monkeypatch.setattr(ra, "request_agent_action", lambda args, prompt, images: prompts.append(prompt) or "LEFT")
    decide = H.wrap(ra.decide_action, ra.to_sana_key, session=True, turn_cal=True)
    task = {"task_id": "OE034", "prompt": "Turn the camera right 90 degrees, then return to the starting view."}
    assert decide(task, None, ["RIGHT", "RIGHT"], 2, 30, ARGS, dataset_action="LEFT") == "LEFT"
    assert prompts[0].startswith("Our goal is: " + task["prompt"] + "\nControls: one LEFT or RIGHT turns the camera about 45")
    assert "heading 90 degrees right" in prompts[0] and "Choose one action from W, S, A, D, LEFT" in prompts[0]


def test_run_py_strips_the_flag_and_is_off_by_default():
    src = (ROOT / "adapters" / "lingbot_world2" / "run.py").read_text()
    assert '"--lingbot-player-hint")]' in src and 'os.environ.get("LINGBOT_PLAYER_HINT", "0") == "1"' in src
    assert "if PLAYER_HINT:\n    run_agent.decide_action = H.wrap(" in src
