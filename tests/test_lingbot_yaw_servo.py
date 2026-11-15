from types import SimpleNamespace

import numpy as np
import pytest

from adapters.lingbot_world2 import yaw_servo as YS

RATE = 1.125   # degrees per frame: 22.5 per 20-frame token


class FakeSession:
    """A camera that renders g x the commanded yaw per direction. Frames are 1-pixel 'images' holding the heading."""

    def __init__(self, g_left, g_right, peak=1.0):
        self.g = {"j": g_left, "l": g_right}
        self.chunk_id, self.heading, self.peak = 0, 0.0, peak
        self.track = SimpleNamespace(yaw_gain=None)
        self.calls = []

    def step(self, keys):
        gl, gr = self.track.yaw_gain or (1.0, 1.0)
        out = [self.heading]
        for key in keys:
            y = YS.yaw_part(key)
            if y:
                self.heading += YS.SIGN[y] * RATE * (gl if y == "j" else gr) * self.g[y]
            out.append(self.heading)
        self.chunk_id += max(1, len(keys) // 16)
        self.calls.append((len(keys), self.track.yaw_gain))
        return np.array(out, dtype=np.float64).reshape(-1, 1)


def _measure(session):
    return lambda frames: (float(frames[-1, 0] - frames[0, 0]), 0.0, session.peak)


def _script(*segs):
    keys = []
    for key, n in segs:
        keys += [key] * n
    keys += ["none"] * ((16 - (len(keys) + 4) % 16) % 16)
    return keys


def test_helpers():
    keys = _script(("j", 80), ("l", 80))
    assert len(keys) == 172
    pieces = YS.split_chunks(keys, first=True)
    assert [len(p) for p in pieces] == [12] + [16] * 10 and sum(pieces, []) == keys
    assert [len(p) for p in YS.split_chunks(keys[12:44], first=False)] == [16, 16]
    with pytest.raises(ValueError):
        YS.split_chunks(keys[:20], first=True)
    assert YS.runs(["j", "j", "l", "none"]) == [("j", 0, 2), ("l", 2, 3), ("none", 3, 4)]
    assert [YS.yaw_part(k) for k in ("j", "l", "w+j", "none", "w", "i")] == ["j", "l", "j", "", "", ""]
    assert [YS.measurable(k) for k in ("j", "l", "none", "w", "w+j", "i", "k")] == [True, True, True, False, False, False, False]
    assert YS.enabled(["x", "--lingbot-yaw-servo"], {}) and YS.enabled([], {"LINGBOT_YAW_SERVO": "1"}) and not YS.enabled([], {})
    with pytest.raises(SystemExit):
        YS.YawServo(beta=0.0)


@pytest.mark.parametrize("segs,g", [
    ((("j", 80), ("l", 80)), (1.237, 0.935)),        # GC033 as measured: ends 27 degrees left without the servo
    ((("l", 80), ("j", 80)), (1.44, 1.18)),          # GC005
    ((("l", 160), ("j", 160)), (1.6, 1.3)),          # a 180 out and back on a fast scene
    ((("j", 80), ("l", 160), ("j", 80)), (1.3, 0.9)),
])
def test_servo_closes_the_heading_in_one_long_step(segs, g):
    keys = _script(*segs)
    open_loop = FakeSession(*g)
    open_loop.step(keys)
    s = FakeSession(*g)
    servo = YS.YawServo()
    frames = YS.step(s, servo, keys, RATE, _measure(s), rigid=None)
    assert frames.shape == (len(keys) + 1, 1)                           # same frames a single step returns
    assert abs(s.heading) < 2.0 and abs(s.heading) < 0.15 * abs(open_loop.heading)
    assert servo.intended == pytest.approx(0.0, abs=1e-9) and servo.heading == pytest.approx(s.heading)
    assert servo.est["j"] == pytest.approx(g[0], abs=0.05) and servo.est["l"] == pytest.approx(g[1], abs=0.05)
    assert all(YS.LO <= x <= YS.HI for _n, gain in s.calls for x in gain) and servo.chunks == len(s.calls)


def test_servo_works_across_closed_loop_calls_and_resets():
    s = FakeSession(1.3, 0.9)
    servo = YS.YawServo()
    first = YS.step(s, servo, ["j"] * 28, RATE, _measure(s), rigid=None)            # chunk 01 of a rollout: 29 frames
    assert first.shape == (29, 1)
    for keys in (["j"] * 32, ["l"] * 32, ["l"] * 32):                   # later agent steps: 33 frames each
        assert YS.step(s, servo, keys, RATE, _measure(s), rigid=None).shape == (33, 1)
    # intended: 60 frames left, 64 right; the rendered heading follows it instead of the raw gains
    assert servo.intended == pytest.approx(4 * RATE)
    assert abs(s.heading - servo.intended) < 2.0
    raw = -60 * RATE * 1.3 + 64 * RATE * 0.9
    assert abs(raw - servo.intended) > 20
    servo.reset()
    assert servo.est == {"j": 1.0, "l": 1.0} and servo.heading == 0.0 and servo.chunks == 0


def test_servo_does_not_learn_from_moving_or_untrusted_chunks():
    s = FakeSession(1.5, 1.5)
    servo = YS.YawServo()
    YS.step(s, servo, ["w+l"] * 12 + ["w"] * 16, RATE, _measure(s), rigid=None)     # walking while turning: not measurable
    assert servo.est == {"j": 1.0, "l": 1.0} and servo.heading == pytest.approx(servo.intended) == pytest.approx(12 * RATE)
    weak = FakeSession(1.5, 1.5, peak=0.0)
    servo = YS.YawServo()
    YS.step(weak, servo, ["l"] * 12 + ["l"] * 16, RATE, _measure(weak), rigid=None)
    assert servo.est["l"] == 1.0 and servo.untrusted == 2 and servo.heading == pytest.approx(servo.intended)
    assert [g for _n, g in weak.calls] == [(1.0, 1.0), (1.0, 1.0)]     # stood down: the rollout is the open-loop one
    still = FakeSession(1.0, 1.0)
    servo = YS.YawServo()
    YS.step(still, servo, ["none"] * 12, RATE, _measure(still), rigid=None)         # nothing to correct: gain stays 1
    assert still.calls == [(12, (1.0, 1.0))] and servo.corrected == 0


# ------------------------------------------------------------ runner flag

def test_runner_flag_parses_and_refuses_bad_combinations():
    from adapters.lingbot_world2 import run as R
    flags, rest = R.configure(["run.py", "--tasks", "GC033"], environ={})
    assert flags["yaw_servo"] is False and rest == ["run.py", "--tasks", "GC033"]
    flags, rest = R.configure(["run.py", "--lingbot-turn-cal", "--lingbot-yaw-servo", "--tasks", "GC033"], environ={})
    assert flags["yaw_servo"] is True and rest == ["run.py", "--tasks", "GC033"]
    flags, _ = R.configure(["run.py", "--lingbot-turn-cal"], environ={"LINGBOT_YAW_SERVO": "1"})
    assert flags["yaw_servo"] is True
    for argv, msg in ((["--lingbot-yaw-servo"], "requires session mode and --lingbot-turn-cal"),
                      (["--lingbot-turn-cal", "--lingbot-yaw-servo", "--lingbot-stateless"], "requires session mode"),
                      (["--lingbot-turn-cal", "--lingbot-yaw-servo", "--lingbot-yaw-gain", "0.8"], "use one"),
                      (["--lingbot-turn-cal", "--lingbot-yaw-servo", "--lingbot-gc-ease-turns"], "gc-ease-turns")):
        with pytest.raises(SystemExit, match=msg):
            R.configure(["run.py", *argv], environ={})


def test_flag_counters_only_with_the_flag():
    from adapters.lingbot_world2 import flag_stats as F
    off = F.FlagStats(True, "goal", False, False)
    assert "yaw_servo" not in off.summary("GC033") and "yaw_servo" not in off.total_line()
    on = F.FlagStats(True, "goal", False, False, yaw_servo=True)
    assert on.summary("GC033")["yaw_servo"] == "skip"                 # on, but this task had no turn chunk
    on.yaw_servo_chunks, on.yaw_servo_untrusted = 11, 1
    s = on.summary("GC033")
    assert (s["yaw_servo"], s["yaw_servo_chunks"], s["yaw_servo_untrusted"]) == ("on", 11, 1)
    on.finish_task("GC033")
    assert "yaw_servo=on yaw_servo_chunks=11 yaw_servo_untrusted=1" in on.total_line()


def test_rigid_share_tells_a_camera_turn_from_a_moving_subject():
    rng = np.random.default_rng(0)
    tex = rng.random((480, 2000)).astype(np.float32)
    c = np.cumsum(np.cumsum(tex, axis=0), axis=1)
    tex = (c[8:, 8:] - c[:-8, 8:] - c[8:, :-8] + c[:-8, :-8]) / 64.0
    pan = np.stack([tex[:464, 100 + 6 * i:100 + 6 * i + 832] for i in range(9)])        # whole image shifts together
    assert YS.rigid_share(pan) == 1.0
    subject = np.stack([tex[:464, 100:932].copy() for _ in range(9)])                   # still camera ...
    for i in range(9):
        subject[i, 232:, :] = tex[:232, 300 + 8 * i:300 + 8 * i + 832]                  # ... the lower half moves
    assert YS.rigid_share(subject) < YS.RIGID_MIN
    assert YS.rigid_share(pan[:1]) == 1.0


def test_step_stands_down_when_the_motion_is_not_rigid():
    s = FakeSession(1.5, 1.5)
    servo = YS.YawServo()
    YS.step(s, servo, ["l"] * 12 + ["l"] * 16, RATE, _measure(s), rigid=lambda frames: 0.4)
    assert servo.est["l"] == 1.0 and servo.untrusted == 2 and [g for _n, g in s.calls] == [(1.0, 1.0), (1.0, 1.0)]
