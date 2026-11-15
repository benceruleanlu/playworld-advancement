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
    YS.step(weak, servo, ["l"] * 12 + ["l"] * 16 + ["l"] * 16, RATE, _measure(weak), rigid=None)
    assert servo.est["l"] == 1.0 and servo.untrusted == 3 and servo.heading == pytest.approx(servo.intended)
    assert [g for _n, g in weak.calls] == [(1.0, 1.0)] * 3             # never measured: the rollout is the open-loop one
    assert servo.locked and "locked after" in servo.describe()
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
    on.yaw_servo_locked = True
    assert on.summary("GC033")["yaw_servo"] == "locked"
    on.yaw_servo_locked = False
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
    assert servo.locked


# ------------------------------------------- through the runner, next to no-flag arms

class _RunnerSession:
    """The runner's session interface with a camera that renders g x the yaw the model track commands.
    Uses the real PoseTrack, so the gain reaches the model the way it does on a GPU."""

    def __init__(self, g_left, g_right):
        from adapters.lingbot_world2 import session as S
        self.S, self.g = S, {"j": g_left, "l": g_right}
        self.started, self.chunk_id, self.reanchor_events, self.track = False, 0, 0, S.PoseTrack()
        self.heading, self.steps, self.gains = 0.0, 0, []

    def reset(self, *a, **kw):
        self.started, self.chunk_id, self.track, self.heading = True, 0, self.S.PoseTrack(), 0.0

    def step(self, keys, **kw):
        from adapters.lingbot_world2 import poses as P
        import math
        gain = self.track.yaw_gain or (1.0, 1.0)
        rel = self.track.advance(keys)
        self.chunk_id += len(rel) // self.S.CHUNK
        self.steps += 1
        self.gains.append(gain)
        out = np.zeros((len(keys) + 1, 2, 2, 3), dtype=np.float64)
        out[0] = self.heading
        for i, key in enumerate(keys, 1):
            y = YS.yaw_part(key)
            if y:
                self.heading += YS.SIGN[y] * math.degrees(P.YAW) * (gain[0] if y == "j" else gain[1]) * self.g[y]
            out[i] = self.heading
        return out


def test_runner_arms_servo_corrects_and_neighbours_are_untouched(monkeypatch, capsys, tmp_path):
    import functools
    import sys
    from pathlib import Path
    from types import ModuleType

    from PIL import Image

    from adapters.lingbot_world2 import run as R
    img = tmp_path / "in.png"
    Image.new("RGB", (8, 8)).save(img)
    torch = ModuleType("torch")
    torch.cuda = SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)
    imageio = ModuleType("imageio")
    imageio.mimsave = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "imageio", imageio)
    pipe = SimpleNamespace(model=None, _t5_cache={})
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe, Path("."), False))
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    # the fake frames carry the heading instead of an image: read it back, and skip the image-based rigid test
    monkeypatch.setattr(R.MT, "chunk_turn", lambda frames: (float(frames[-1, 0, 0, 0] - frames[0, 0, 0, 0]), 0.0, 1.0))
    monkeypatch.setattr(R.YSV, "step", functools.partial(YS.step, rigid=None))
    seen = []

    def fake_import(fresh=True):
        def run_task(task, eng, out, args):
            eng.generate(str(img), "p", "j-80,l-80,none-12", tmp_path, "GC033_full", 173)   # left 90, right 90, dataset mode
            return {"task_id": task["task_id"], "success": False}

        ra = SimpleNamespace(run_task=run_task, decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")

        def run_main():
            eng = ra.SanaWMEngine(SimpleNamespace(max_total_frames=961, seed=0, fps=16, action_frame_unit=20))
            eng.session = _RunnerSession(1.237, 0.935)        # GC033 as measured on the 14B
            seen.append(eng.session)
            ra.run_task({"task_id": "GC033"}, eng, tmp_path, None)
        ra.main = run_main
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py", "--lingbot-turn-cal"]) == 0
    assert R.main(["run.py", "--lingbot-turn-cal", "--lingbot-yaw-servo"]) == 0
    assert R.main(["run.py", "--lingbot-turn-cal"]) == 0
    base, servo, again = seen
    assert base.heading == pytest.approx(-90 * 1.237 + 90 * 0.935, abs=0.01)       # 27 degrees left of the start
    assert abs(servo.heading) < 2.0                                                # the servo arm comes back
    assert again.heading == pytest.approx(base.heading) and again.steps == base.steps == 1 and again.gains == [(1.0, 1.0)]
    assert servo.steps == 11 and servo.gains[0] == (1.0, 1.0) and any(g != (1.0, 1.0) for g in servo.gains)
    assert R.YAW_SERVO is False
    out = capsys.readouterr().out
    modes = [ln for ln in out.splitlines() if ln.startswith("[lingbot] mode:")]
    assert "yaw servo" not in modes[0] and ", yaw servo on" in modes[1] and "yaw servo" not in modes[2]
    flags = [ln for ln in out.splitlines() if ln.startswith("[lingbot] flags task=")]
    assert "yaw_servo" not in flags[0] and "yaw_servo=on yaw_servo_chunks=11 yaw_servo_untrusted=0" in flags[1] and "yaw_servo" not in flags[2]
    assert out.count("[lingbot] yaw servo: GC033_full est L") == 1


def test_one_untrusted_chunk_does_not_bias_the_heading():
    # GC031 on the 14B: one chunk of an otherwise static scene failed the rigid test and cost 12 degrees when its
    # turn was booked as intended. Booked at the estimate, the rollout still closes.
    keys = _script(("j", 80), ("l", 80))
    s = FakeSession(1.7, 1.3)
    servo = YS.YawServo()
    calls = iter(range(100))
    rigid = lambda frames: 0.4 if next(calls) == 3 else 1.0          # the fourth chunk is not trusted
    YS.step(s, servo, keys, RATE, _measure(s), rigid=rigid)
    assert servo.untrusted == 1 and not servo.locked
    assert abs(s.heading) < 3.0 and abs(servo.heading - s.heading) < 3.0


def test_servo_locks_on_a_scene_with_a_moving_subject():
    keys = _script(("j", 80), ("l", 80))
    s = FakeSession(1.4, 1.1)
    servo = YS.YawServo()
    calls = iter(range(100))
    rigid = lambda frames: 0.4 if next(calls) in (2, 4) else 1.0     # two untrusted turn chunks: a subject is moving
    YS.step(s, servo, keys, RATE, _measure(s), rigid=rigid)
    assert servo.locked and servo.untrusted == 2 and servo.est == {"j": 1.0, "l": 1.0}
    gains = [g for _n, g in s.calls]
    assert all(g == (1.0, 1.0) for g in gains[5:]) and any(g != (1.0, 1.0) for g in gains[:5])
    assert servo.plan(["l"] * 16, RATE) == (1.0, 1.0)
    servo.reset()
    assert not servo.locked                                           # the next rollout starts fresh


# ------------------------------------------- heading credit on runs it does not measure (review of #125)

def _trusted_chunk_leaves_error():
    """One trusted pure-right chunk on a camera that renders half the command: est R 0.7, error +6.75 degrees."""
    s = FakeSession(1.0, 0.5)
    servo = YS.YawServo()
    YS.step(s, servo, ["l"] * 12, RATE, _measure(s), rigid=None)
    assert servo.error() == pytest.approx(6.75) and servo.est["l"] == pytest.approx(0.7)
    return s, servo


def test_combo_chunks_book_the_extra_yaw_they_send():
    # Before 038892e a w+l run was booked at the asked angle, not at what the raised gain sends: the error never
    # went down and every later w+l chunk was planned at gain 1.96 with the error stuck at 6.75.
    s, servo = _trusted_chunk_leaves_error()
    errs, gains = [], []
    for _ in range(4):
        YS.step(s, servo, ["w+l"] * 16, RATE, _measure(s), rigid=None)
        errs.append(servo.error())
        gains.append(servo.last_gain[1])
    assert gains[0] == pytest.approx((16 * RATE + 6.75) / (16 * RATE * 0.7))       # corrects once
    assert all(abs(e) < 1e-9 for e in errs)                                          # and the error is closed
    assert gains[1:] == pytest.approx([1 / 0.7] * 3)                                 # then only the estimate


def test_untrusted_run_books_the_extra_yaw_it_sends():
    s, servo = _trusted_chunk_leaves_error()
    YS.step(s, servo, ["l"] * 16, RATE, _measure(s), rigid=lambda frames: 0.4)      # one subject-motion chunk
    assert servo.untrusted == 1 and not servo.locked and abs(servo.error()) < 1e-9
    YS.step(s, servo, ["l"] * 16, RATE, _measure(s), rigid=None)
    assert servo.last_gain[1] == pytest.approx(1 / 0.7)                              # not re-sending the 6.75


class _NoisyCamera(FakeSession):
    """Renders left 1.40x and right 1.11x of the commanded yaw (the 14B means in #125), each chunk drawn with 5%
    spread around them, and the measurement adds 1 degree of noise per run."""

    def __init__(self, rng):
        super().__init__(1.40, 1.11)
        self.base, self.rng = dict(self.g), rng

    def step(self, keys):
        self.g = {d: v * (1 + self.rng.normal(0, 0.05)) for d, v in self.base.items()}
        return super().step(keys)

    def measure(self, frames):
        return float(frames[-1, 0] - frames[0, 0]) + float(self.rng.normal(0, 1.0)), 0.0, 1.0


def _intended(keys):
    return sum(YS.SIGN[YS.yaw_part(k)] * RATE for k in keys if YS.yaw_part(k))


@pytest.mark.parametrize("segs", [(("j", 80), ("l", 80)), (("l", 320),)], ids=["left90-right90", "right360"])
def test_simulated_14b_camera_heading_converges(segs):
    keys = _script(*segs)
    open_err, servo_err = [], []
    for seed in range(20):
        o = _NoisyCamera(np.random.default_rng(seed))
        o.step(keys)
        open_err.append(abs(o.heading - _intended(keys)))
        s, servo, done, track = _NoisyCamera(np.random.default_rng(seed)), YS.YawServo(), [], []
        for piece in YS.split_chunks(keys, first=True):
            YS.step(s, servo, piece, RATE, s.measure, rigid=None)
            done += piece
            track.append(s.heading - _intended(done))
        servo_err.append(abs(track[-1]))
        assert max(abs(e) for e in track[2:]) < 15.0                  # no growing swing once it has two readings
        for d in (0, 1):
            g = [gain[d] for _n, gain in s.calls]
            assert all(YS.LO <= x <= YS.HI for x in g)
            assert not any({a, b} == {YS.LO, YS.HI} for a, b in zip(g, g[1:]))   # never clamp to clamp
    assert np.mean(servo_err) < 0.2 * np.mean(open_err) and max(servo_err) < 10.0


# ------------------------------------------------------------ knobs as runner args

def test_knobs_as_args_env_and_refusals():
    from adapters.lingbot_world2 import run as R
    base = ["run.py", "--lingbot-turn-cal", "--tasks", "GC033"]
    flags, rest = R.configure(base + ["--lingbot-yaw-servo"], environ={})
    assert flags["yaw_servo_cfg"] == YS.ServoConfig(True, 1.0, 0.6) and rest == ["run.py", "--tasks", "GC033"]
    flags, rest = R.configure(base + ["--lingbot-yaw-servo", "--lingbot-yaw-servo-k", "0.5", "--lingbot-yaw-servo-beta=0.3"],
                              environ={"LINGBOT_YAW_SERVO_K": "1.5"})
    assert flags["yaw_servo_cfg"] == YS.ServoConfig(True, 0.5, 0.3) and rest == ["run.py", "--tasks", "GC033"]
    flags, _ = R.configure(base + ["--lingbot-yaw-servo"], environ={"LINGBOT_YAW_SERVO_K": "1.5"})
    assert flags["yaw_servo_cfg"].k == 1.5                                         # env still honoured
    flags, _ = R.configure(base, environ={"LINGBOT_YAW_SERVO_K": "1.5"})
    assert flags["yaw_servo_cfg"] == YS.ServoConfig() and not flags["yaw_servo"]  # env knob alone: off
    for bad in (["--lingbot-yaw-servo-k", "0.5"],                                  # knob without the flag
                ["--lingbot-yaw-servo", "--lingbot-yaw-servo-k", "3"], ["--lingbot-yaw-servo", "--lingbot-yaw-servo-beta=0"],
                ["--lingbot-yaw-servo", "--lingbot-yaw-servo-k=x"], ["--lingbot-yaw-servo", "--lingbot-yaw-servo-k"]):
        with pytest.raises(SystemExit):
            R.configure(base + bad, environ={})


def test_knobs_reach_the_engine_per_main_call(monkeypatch, capsys, tmp_path):
    from adapters.lingbot_world2 import run as R
    seen = []

    class Engine:
        def __init__(self, args):
            seen.append((R.YAW_SERVO, R.YAW_SERVO_CFG))

    def fake_import(fresh=True):
        ra = SimpleNamespace(main=lambda: ra.SanaWMEngine(None), run_task=lambda *a: None,
                             decide_action=lambda *a, **kw: "WAIT", to_sana_key=lambda a: "none")
        return ra

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    monkeypatch.setattr(R, "LingBotWorld2Engine", Engine)
    monkeypatch.setattr(R.agent_api, "patch", lambda ra, *a: "test")
    monkeypatch.setattr(R.agent_api, "finish", lambda ra: None)
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    R.main(["run.py", "--lingbot-turn-cal", "--lingbot-yaw-servo", "--lingbot-yaw-servo-k", "0.5"])
    R.main(["run.py", "--lingbot-turn-cal", "--lingbot-yaw-servo"])
    R.main(["run.py", "--lingbot-turn-cal"])
    assert [(on, c.k) for on, c in seen] == [(True, 0.5), (True, 1.0), (False, 1.0)]
