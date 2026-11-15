"""Measured turn: the image-shift estimator against frames ray-cast at a known rotation, and the
decide_action wrapper. No GPU, no API calls, no video files."""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import measured_turn as MT  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402

KEY = {"W": "w", "S": "s", "A": "a", "D": "d", "LEFT": "j", "RIGHT": "l", "UP": "i", "DOWN": "k", "WAIT": "none"}.get
ARGS = SimpleNamespace(chunk_frames=33, action_frame_unit=20)
H_, W_ = 240, 416  # half of 480p; chunk_turn scales the intrinsics by the image width
TH, TW = 1024, 4096


def _texture():
    t = np.random.default_rng(0).random((TH, TW)).astype(np.float32)
    f1, f2 = np.fft.fftfreq(TH)[:, None], np.fft.rfftfreq(TW)[None, :]
    return np.fft.irfft2(np.fft.rfft2(t) * np.exp(-2 * (math.pi * 2.0) ** 2 * (f1 ** 2 + f2 ** 2)), s=t.shape)


TEX = _texture()


def render(yaw_deg=0.0, tilt_deg=0.0):
    """A far textured sphere seen by a camera turned yaw (right +) and tilted (up +): an exact rotation."""
    fx, fy, cx, cy = (v / 2 for v in P.INTRINSICS_480P)
    u, v = np.meshgrid(np.arange(W_) - cx, np.arange(H_) - cy)
    d = np.stack([u / fx, v / fy, np.ones_like(u, dtype=float)], -1)
    y, p = math.radians(yaw_deg), math.radians(tilt_deg)
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])  # image y is down
    w = d @ (ry @ rx).T
    x = (np.arctan2(w[..., 0], w[..., 2]) / (2 * math.pi) + 0.5) * TW
    yy = np.clip((np.arctan2(w[..., 1], np.hypot(w[..., 0], w[..., 2])) / math.pi + 0.5) * TH, 0, TH - 2)
    x0, y0 = np.floor(x).astype(int), np.floor(yy).astype(int)
    ax, ay = x - x0, yy - y0
    g = ((1 - ax) * (1 - ay) * TEX[y0, x0 % TW] + ax * (1 - ay) * TEX[y0, (x0 + 1) % TW]
         + (1 - ax) * ay * TEX[y0 + 1, x0 % TW] + ax * ay * TEX[y0 + 1, (x0 + 1) % TW])
    return np.repeat(g[..., None], 3, 2)


def clip(yaw_rate=0.0, tilt_rate=0.0, n=9):
    return [render(i * yaw_rate, i * tilt_rate) for i in range(n)]


# 1.4 and 1.7 degrees per frame are the commanded rates (45 and 55 degrees per 32-frame chunk); a slow
# 0.5 degrees per frame is about one pixel per frame at the working size and reads a few percent low
@pytest.mark.parametrize("rate,tol", [(1.4, 0.05), (-1.7, 0.05), (0.5, 0.10)])
def test_yaw_is_measured_with_the_right_sign(rate, tol):
    yaw, tilt, peak = MT.chunk_turn(clip(yaw_rate=rate))
    assert yaw == pytest.approx(8 * rate, rel=tol) and abs(tilt) < 0.3 and peak > MT.MIN_PEAK


def test_tilt_up_is_positive_and_a_still_clip_is_zero():
    yaw, tilt, _ = MT.chunk_turn(clip(tilt_rate=0.6))
    assert tilt == pytest.approx(4.8, rel=0.05) and abs(yaw) < 0.3
    yaw, tilt, peak = MT.chunk_turn(clip())
    assert abs(yaw) < 0.05 and abs(tilt) < 0.05 and peak > 0.9
    assert MT.chunk_turn([render()]) == (0.0, 0.0, 0.0)


def _wrapped(clips):
    seen, events = [], []

    def player(task, frame, recent, chunk_idx, num_chunks, args, **kw):
        seen.append(task["prompt"])
        return "RIGHT"

    reads = []

    def read(path):
        reads.append(path)
        return clips[path]

    return MT.wrap(player, KEY, session=True, turn_cal=True, on_event=events.append, read=read), seen, events, reads


def test_wrapper_tells_the_player_both_totals_and_measures_each_chunk_once(capsys):
    clips = {"c1.mp4": clip(yaw_rate=2.0), "c2.mp4": clip(), "c3.mp4": clip(yaw_rate=-1.0)}  # +16, 0, -8 degrees
    decide, seen, events, reads = _wrapped(clips)
    task = {"task_id": "GC033", "prompt": "Turn right 90 degrees, then turn back."}
    paths = list(clips)
    assert decide(task, None, ["RIGHT", "W", "LEFT"], 3, 30, ARGS, chunk_video_paths=paths) == "RIGHT"
    assert decide(task, None, ["RIGHT", "W", "LEFT"], 3, 30, ARGS, chunk_video_paths=paths) == "RIGHT"
    assert reads == ["c1.mp4", "c3.mp4"]                       # the W chunk is not measured; the cache holds the rest
    ev = events[-1]
    assert ev["chunks"] == 2 and ev["unreliable"] == 0
    assert ev["commanded_yaw"] == pytest.approx(0.0, abs=1e-6)  # 45 right, 45 left
    assert ev["measured_yaw"] == pytest.approx(8.0, rel=0.1)    # the video shows 16 right, 8 left
    assert "rotated the view a net 8 degrees right" in seen[-1] and "add up to 0 degrees and" in seen[-1]
    assert seen[-1].startswith(task["prompt"]) and task["prompt"] == "Turn right 90 degrees, then turn back."
    out = capsys.readouterr().out
    assert "[lingbot] measured turn: GC033 chunk 1 RIGHT commanded yaw +45 tilt +0, measured yaw +16 tilt +0" in out
    assert out.count("measured turn: GC033 chunk") == 2


def test_wrapper_passes_through_without_turn_chunks_or_on_wait_only_calls():
    decide, seen, events, reads = _wrapped({"c1.mp4": clip(yaw_rate=2.0)})
    task = {"task_id": "IF052", "prompt": "The boy walks forward."}
    assert decide(task, None, ["W"], 1, 30, ARGS, chunk_video_paths=["c1.mp4"]) == "RIGHT"
    assert decide(task, None, ["RIGHT"], 1, 30, ARGS, chunk_video_paths=["c1.mp4"], stationary_only=True) == "RIGHT"
    assert decide(task, None, [], 0, 30, ARGS) == "RIGHT"
    assert seen == [task["prompt"]] * 3 and events == [] and reads == []


def test_unreadable_or_flat_chunks_are_counted_unreliable_and_not_reported(capsys):
    flat = [np.zeros((H_, W_, 3), dtype=np.float32)] * 5

    def read(path):
        if path == "gone.mp4":
            raise OSError("no such file")
        return flat

    events, seen = [], []
    decide = MT.wrap(lambda task, *a, **k: seen.append(task["prompt"]) or "LEFT", KEY, session=True, turn_cal=False,
                     on_event=events.append, read=read)
    task = {"task_id": "OE034", "prompt": "goal"}
    assert decide(task, None, ["RIGHT", "RIGHT"], 2, 30, ARGS, chunk_video_paths=["gone.mp4", "flat.mp4"]) == "LEFT"
    assert events[-1]["chunks"] == 2 and events[-1]["unreliable"] == 2 and events[-1]["measured_yaw"] == 0
    assert seen == ["goal"]                                    # nothing measured, so nothing is claimed
    assert "could not read gone.mp4" in capsys.readouterr().out


def test_one_unreliable_chunk_silences_the_sentence_but_not_the_counters():
    # a good 16 degree RIGHT then an unmeasurable LEFT: "net 16 right against 0 commanded" would be false
    clips = {"c1.mp4": clip(yaw_rate=2.0), "c2.mp4": [np.zeros((H_, W_, 3), dtype=np.float32)] * 5}
    decide, seen, events, _ = _wrapped(clips)
    task = {"task_id": "GC033", "prompt": "goal"}
    assert decide(task, None, ["RIGHT", "LEFT"], 2, 30, ARGS, chunk_video_paths=list(clips)) == "RIGHT"
    assert seen == ["goal"]
    assert events[-1]["chunks"] == 2 and events[-1]["unreliable"] == 1
    assert events[-1]["measured_yaw"] == pytest.approx(16.0, rel=0.1)


def test_flag_line_only_grows_when_the_flag_is_on():
    off = F.FlagStats(False, "goal", False, False)
    assert "measured" not in F.FlagStats.line(off.summary("GC033"))
    st = F.FlagStats(False, "goal", False, False, measured_turn=True)
    assert F.FlagStats.line(st.summary("OE001")).endswith(
        "measured_turn=skip measured_chunks=0 measured_unreliable=0 commanded_yaw=0 measured_yaw=0 "
        "commanded_tilt=0 measured_tilt=0")
    st.measured_turn_event({"chunks": 8, "unreliable": 1, "commanded_yaw": 360.0, "measured_yaw": 58.6,
                            "commanded_tilt": 0.0, "measured_tilt": -1.2})
    assert F.FlagStats.line(st.finish_task("GC031")).endswith(
        "measured_turn=on measured_chunks=8 measured_unreliable=1 commanded_yaw=360 measured_yaw=59 "
        "commanded_tilt=0 measured_tilt=-1")
    st.new_task()
    assert st.summary("GC036")["measured_turn"] == "skip"


def test_configure_strips_the_flag_and_is_off_by_default():
    from adapters.lingbot_world2 import run as RUN
    flags, argv = RUN.configure(["run.py", "--tasks", "GC033"], environ={})
    assert flags["measured_turn"] is False and argv == ["run.py", "--tasks", "GC033"]
    flags, argv = RUN.configure(["run.py", "--lingbot-measured-turn", "--tasks", "GC033"], environ={})
    assert flags["measured_turn"] is True and argv == ["run.py", "--tasks", "GC033"]
    assert RUN.configure(["run.py"], environ={"LINGBOT_MEASURED_TURN": "1"})[0]["measured_turn"] is True
