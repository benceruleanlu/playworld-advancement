"""Turn step: yaw degrees per closed-loop chunk, through poses, the player hint, return stop and the flags
line. No GPU, no API calls."""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import player_hint as H  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import return_stop as R  # noqa: E402
from adapters.lingbot_world2 import run as RUN  # noqa: E402

KEY = {"W": "w", "S": "s", "A": "a", "D": "d", "LEFT": "j", "RIGHT": "l", "UP": "i", "DOWN": "k", "WAIT": "none"}.get
OUT_BACK = "Turn the camera right 90 degrees, then turn back to the original view."


@pytest.fixture
def step90():
    P.reset({})
    P.CHUNK_YAW_DEG = 90.0
    yield
    P.reset({})


def test_default_is_unset_and_turn_cal_is_unchanged():
    P.reset({})
    assert P.CHUNK_YAW_DEG == 0
    yaw, pitch = P.calibrate(False, 32)
    assert math.degrees(yaw) * 32 == pytest.approx(45.0) and math.degrees(pitch) * 32 == pytest.approx(40.0)
    P.reset({})


def test_step_sets_yaw_per_chunk_and_leaves_pitch_and_dataset_mode(step90):
    yaw, pitch = P.calibrate(False, 32)
    assert math.degrees(yaw) * 32 == pytest.approx(90.0) and math.degrees(pitch) * 32 == pytest.approx(40.0)
    yaw, _ = P.calibrate(False, 28)                    # the first chunk has 28 keys and still turns 90
    assert math.degrees(yaw) * 28 == pytest.approx(90.0)
    yaw, pitch = P.calibrate(True, 80, 20)             # dataset mode: a token is still 22.5 / 20 degrees
    assert math.degrees(yaw) * 20 == pytest.approx(22.5) and math.degrees(pitch) * 20 == pytest.approx(20.0)


def test_env_sets_it_and_reset_clears_it():
    P.reset({"LINGBOT_TURN_STEP_DEG": "60"})
    assert P.CHUNK_YAW_DEG == 60.0
    P.reset({})
    assert P.CHUNK_YAW_DEG == 0


def test_player_hint_and_return_stop_follow_the_step(step90):
    assert H.step_size(33, True, True) == pytest.approx((90.0, 40.0))
    assert "one LEFT or RIGHT turns the camera about 90 degrees" in H.hint([], KEY, 33, True, True)
    s = H.replay(["RIGHT", "LEFT"], KEY, 33, True, True)
    assert s["turned_right"] == pytest.approx(90.0) and s["heading"] == pytest.approx(0.0, abs=1e-6)
    # "turn 90 and back" is two actions, 61 frames of video, where 45 degree chunks need four
    assert R.returned_at(["RIGHT", "LEFT"], KEY, R.plan(OUT_BACK), 33, True, True) == 2
    full = "Rotate the camera 360 degrees in place, then return to the original angle facing the original view."
    assert R.returned_at(["RIGHT"] * 4, KEY, R.plan(full), 33, True, True) == 4


def test_without_the_step_the_same_goal_needs_four_actions():
    P.reset({})
    assert R.returned_at(["RIGHT", "LEFT"], KEY, R.plan(OUT_BACK), 33, True, True) is None
    assert R.returned_at(["RIGHT", "RIGHT", "LEFT", "LEFT"], KEY, R.plan(OUT_BACK), 33, True, True) == 4


def test_configure_parses_validates_and_implies_turn_cal():
    flags, argv = RUN.configure(["run.py", "--tasks", "GC033"], environ={})
    assert flags["turn_step"] == 0 and flags["turn_cal"] is False and argv == ["run.py", "--tasks", "GC033"]
    flags, argv = RUN.configure(["run.py", "--lingbot-turn-step", "90", "--tasks", "GC033"], environ={})
    assert flags["turn_step"] == 90.0 and flags["turn_cal"] is True and argv == ["run.py", "--tasks", "GC033"]
    assert RUN.configure(["run.py", "--lingbot-turn-step=60"], environ={})[0]["turn_step"] == 60.0
    assert RUN.configure(["run.py"], environ={"LINGBOT_TURN_STEP_DEG": "60"})[0]["turn_step"] == 60.0
    for bad in ("5", "200", "fast"):
        with pytest.raises(SystemExit):
            RUN.configure(["run.py", "--lingbot-turn-step", bad], environ={})


def test_flag_line_only_grows_when_the_step_is_set():
    off = F.FlagStats(True, "goal", False, False)
    assert "turn_step" not in F.FlagStats.line(off.summary("GC033")) and "turn_step" not in off.total_line()
    st = F.FlagStats(True, "goal", False, False, turn_step=90.0)
    assert F.FlagStats.line(st.summary("GC033")).endswith("turn_step=90")
    assert st.total_line().endswith("turn_step=90")
