"""Return stop: goal parsing, the commanded-return test and the decide_action wrapper. No GPU, no API calls."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import return_stop as R  # noqa: E402

KEY = {"W": "w", "S": "s", "A": "a", "D": "d", "LEFT": "j", "RIGHT": "l", "UP": "i", "DOWN": "k", "WAIT": "none"}.get
ARGS = SimpleNamespace(chunk_frames=33, action_frame_unit=20)
OUT_BACK = "Turn the camera right 90 degrees, then return to the starting view."
FULL_TURN = "Rotate the camera 360 degrees in place, then return to the original angle facing the original view."


def runs(spec):
    """'R2 L1' -> ['RIGHT', 'RIGHT', 'LEFT'] (the census notation)."""
    names = {"R": "RIGHT", "L": "LEFT", "U": "UP", "Dn": "DOWN", "Wt": "WAIT"}
    out = []
    for tok in spec.split():
        head = tok.rstrip("0123456789")
        out += [names.get(head, head)] * int(tok[len(head):])
    return out


def at(goal, spec, turn_cal=False):
    return R.returned_at(runs(spec), KEY, R.plan(goal), 33, True, turn_cal)


def test_plan_arms_only_on_one_final_return():
    assert R.plan(OUT_BACK) == {"deg": 67.5, "steps": None, "both_sides": False, "side": "right", "move": "any"}
    assert R.plan(FULL_TURN)["side"] == "yaw" and R.plan(FULL_TURN.replace("degrees", "degrees clockwise"))["side"] == "right"
    assert R.plan("Tilt the camera downward 90 degrees, then return to the original view.")["side"] == "down"
    assert R.plan("Move right 10 steps, then move back to the original position.")["steps"] == 7.5
    assert R.plan("Pan slowly from left to right, then back to center")["both_sides"]
    # something is ordered after the return, two returns, or no return at all: the player keeps control
    assert R.plan("Turn the camera right 90 degrees, then turn back to the original view, then look up 40 degrees.") is None
    assert R.plan("Turn right 180 degrees, turn back to the original direction, wait for 2 seconds, "
                  "then turn the camera left 90 degrees and turn back to the original direction.") is None
    assert R.plan("Rotate the camera 360 degrees once in place.") is None
    assert R.plan("The sword-wielding man walks forward.") is None


def test_out_and_back_fires_at_the_return_at_both_turn_rates():
    assert at(OUT_BACK, "R2 L2") == 4          # default rates: 48 + 55 out, 110 back, 7 degrees off
    assert at(OUT_BACK, "R2 L2", turn_cal=True) == 4
    assert at(OUT_BACK, "R2 L1") is None       # still 48 degrees away
    assert at(OUT_BACK, "R2 L2 R3") == 4       # the first return, whatever came after


def test_dithering_never_counts_as_having_left():
    # baseline player on GC036 / OE047: R1 L1 repeated; the net turn never reaches 0.75 x 90
    assert at(OUT_BACK, "R1 L1 R1 L1 R1 L1 R1 L1") is None
    assert at(FULL_TURN, "R2 L2") is None      # 103 degrees is not a full turn


def test_wrong_side_or_axis_does_not_count_as_having_left():
    assert at(OUT_BACK, "L2 R2") is None       # the goal turns right; a left excursion is not it
    assert at(OUT_BACK, "U4 Dn4") is None      # nor is a tilt
    assert at(OUT_BACK, "L2 R4 L2") == 8       # home after the rightward turn
    assert at(FULL_TURN, "L7") == 7            # no direction named: either way round


def test_full_turn_fires_when_the_heading_wraps_to_the_start():
    assert at(FULL_TURN, "R6") is None         # 323 degrees, 37 short
    assert at(FULL_TURN, "R10 L1") == 7        # GC031 baseline actions: 378 degrees after 7
    assert at(FULL_TURN, "R8", turn_cal=True) == 8


def test_tilt_steps_and_both_sides():
    tilt = "Tilt the camera upward 90 degrees, then return to the starting view."
    assert at(tilt, "U2 Dn2") is None          # default rates: 34 degrees up is not 0.75 x 90
    assert at(tilt, "U4 Dn4") == 8             # 71 degrees up, then back
    assert at(tilt, "U2 Dn2", turn_cal=True) == 4
    steps = "Move right 10 steps, then move back to the original position."
    assert at(steps, "D2 A2") is None          # 3.2 of 10 steps
    assert at(steps, "D5 A5") == 10            # 8 steps out, then home
    assert at(steps, "W5 S5") is None          # forward and back is not a move to the right
    assert at(steps, "A5 D5") is None          # nor is the left
    assert R.plan(steps)["move"] == "right" and R.plan(OUT_BACK)["move"] == "any"
    pan = "Pan slowly from left to right, then back to center"
    assert at(pan, "L1 R1") is None            # never went right of the start
    assert at(pan, "L1 R2 L1") == 4


def _wrapped(hold=2):
    calls, events = [], []

    def player(task, frame, recent, chunk_idx, num_chunks, args, **kw):
        calls.append(list(recent or []))
        return "RIGHT"

    return R.wrap(player, KEY, session=True, turn_cal=False, on_event=events.append, hold=hold), calls, events


def test_wrapper_holds_then_ends_and_does_not_ask_the_player(capsys):
    decide, calls, events = _wrapped()
    task = {"task_id": "OE034", "prompt": OUT_BACK}
    acts = runs("R2 L1")
    assert decide(task, None, acts, 3, 30, ARGS) == "RIGHT" and len(calls) == 1
    acts = runs("R2 L2")
    assert decide(task, None, acts, 4, 30, ARGS) == "WAIT"
    assert decide(task, None, acts + ["WAIT"], 5, 30, ARGS) == "WAIT"
    assert decide(task, None, acts + ["WAIT", "WAIT"], 6, 30, ARGS) == "END"
    assert len(calls) == 1 and events == ["armed", "armed", "stop", "armed", "stop", "armed", "stop"]
    assert "[lingbot] return stop: OE034 back at the start after action 4 (LEFT), step 7 -> END" in capsys.readouterr().out


def test_wrapper_passes_through_when_not_armed():
    decide, calls, events = _wrapped()
    tail = {"task_id": "OE047", "prompt": OUT_BACK[:-1] + ", then look up 40 degrees."}
    assert decide(tail, None, runs("R2 L2"), 4, 30, ARGS) == "RIGHT"
    assert decide({"task_id": "OE001", "prompt": OUT_BACK}, None, runs("R2 L2"), 4, 30, ARGS, stationary_only=True) == "RIGHT"
    assert decide({"task_id": "X", "prompt": OUT_BACK}, None, None, 0, 30, ARGS) == "RIGHT"
    assert len(calls) == 3 and events == ["armed"]


def test_flag_line_only_grows_when_the_flag_is_on():
    off = F.FlagStats(False, "goal", False, False)
    assert "return_stop" not in F.FlagStats.line(off.summary("GC033")) and "return_stops" not in off.total_line()
    st = F.FlagStats(False, "goal", False, False, True)
    assert F.FlagStats.line(st.summary("OE001")).endswith("player_hints=0 return_stop=skip return_stops=0")
    for kind in ("armed", "stop", "stop"):
        st.return_stop_event(kind)
    assert F.FlagStats.line(st.finish_task("GC033")).endswith("return_stop=on return_stops=2")
    assert st.total_line().endswith("player_hints=0 return_stops=2")
    st.new_task()
    assert st.summary("GC036")["return_stop"] == "skip"


def test_configure_strips_the_flag_and_is_off_by_default():
    from adapters.lingbot_world2 import run as RUN
    flags, argv = RUN.configure(["run.py", "--tasks", "OE034"], environ={})
    assert flags["return_stop"] is False and argv == ["run.py", "--tasks", "OE034"]
    flags, argv = RUN.configure(["run.py", "--lingbot-return-stop", "--tasks", "OE034"], environ={})
    assert flags["return_stop"] is True and argv == ["run.py", "--tasks", "OE034"]
    assert RUN.configure(["run.py"], environ={"LINGBOT_RETURN_STOP": "1"})[0]["return_stop"] is True
    assert RUN.configure(["run.py"], environ={"LINGBOT_RETURN_STOP": "0"})[0]["return_stop"] is False


def test_counterclockwise_is_the_left_side_and_default_steps_are_dataset_steps():
    for word in ("counterclockwise", "counter-clockwise", "anticlockwise"):
        assert R.plan(f"Rotate the camera 360 degrees {word} in place, then return to the original view.")["side"] == "left"
    walk = "Walk forward to the door, then walk back to the original position."
    assert R.plan(walk) == {"deg": None, "steps": None, "both_sides": False, "side": "any", "move": "any"}
    assert at(walk, "W1 S1") is None           # 0.9 action = 1.45 dataset steps: not yet 2
    assert at(walk, "W2 S2") == 4              # 3 steps out, then home
