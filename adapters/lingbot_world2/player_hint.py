"""Opt-in player hint: tell the closed-loop player what its keys do and where the commanded camera is.

Upstream `decide_action` gives the player the goal, the frames and the list of actions
taken. It never says how far one action turns the camera, although most GC and
out-of-sight goals name an angle ("turn left 90 degrees") and a return to the start.
`wrap()` appends two sentences to the goal the player reads: the size of one action, and
the camera pose that the actions so far add up to (heading, tilt, position relative to
the start), replayed with the same key-to-pose math LingBot is driven with (poses.py).

The pose is the commanded one, not measured from the video. The world model's prompt is
untouched: only the copy of the task handed to `decide_action` changes. Wait-only
insight tasks never call the player, so they are unaffected. numpy only.
"""
from __future__ import annotations

import math

import numpy as np

from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2 import session as S

YAW_KEYS = {"j": -1.0, "l": 1.0}  # poses.key_delta: j looks left, l looks right


def step_keys(i: int, chunk_frames: int, session: bool) -> int:
    """Per-frame keys chunk i (0-based) of a rollout is driven with (see run.py)."""
    if session:
        return S.keys_needed(S.chunks_for(chunk_frames), first=i == 0)
    return P.frame_count(int(chunk_frames)) - 1


def _delta(key: str, n: int, turn_cal: bool, unit: int) -> np.ndarray:
    """Pose change of n frames of `key`, at the rates the engine uses for that call."""
    old = P.YAW, P.PITCH
    try:
        if turn_cal:
            P.calibrate(False, n, unit)
        return np.linalg.matrix_power(P.key_delta(key), n)
    finally:
        P.YAW, P.PITCH = old


def _angles(pose: np.ndarray) -> tuple[float, float]:
    """(heading, tilt) in degrees: right and up positive (camera x right, y down, z forward)."""
    f = pose[:3, 2]
    return math.degrees(math.atan2(f[0], f[2])), math.degrees(math.asin(max(-1.0, min(1.0, -f[1]))))


def replay(actions, to_key, chunk_frames: int, session: bool, turn_cal: bool, unit: int = 20) -> dict:
    """Commanded camera after `actions` (player words, e.g. 'LEFT'); to_key maps them to engine keys."""
    pose, turned = np.eye(4), {"left": 0.0, "right": 0.0}
    for i, a in enumerate(actions):
        key = to_key(a)
        d = _delta(key, step_keys(i, chunk_frames, session), turn_cal, unit)
        if key in YAW_KEYS:
            turned["left" if YAW_KEYS[key] < 0 else "right"] += abs(_angles(d)[0])
        pose = pose @ d
    heading, tilt = _angles(pose)
    step = float(step_keys(1, chunk_frames, session))  # frames of translation in one later action
    return {"heading": heading, "tilt": tilt, "forward": pose[2, 3] / step, "right": pose[0, 3] / step,
            "turned_left": turned["left"], "turned_right": turned["right"]}


def step_size(chunk_frames: int, session: bool, turn_cal: bool, unit: int = 20) -> tuple[float, float]:
    """(yaw, pitch) degrees one action turns the camera (a chunk after the first)."""
    n = step_keys(1, chunk_frames, session)
    return abs(_angles(_delta("l", n, turn_cal, unit))[0]), abs(_angles(_delta("i", n, turn_cal, unit))[1])


def _side(v: float, neg: str, pos: str, unit: str) -> str:
    r = round(v, 1) if unit == "steps" else float(round(v))
    num = f"{abs(r):.1f}" if unit == "steps" else f"{abs(r):.0f}"
    return f"{num} {unit}" + ("" if r == 0 else f" {pos if r > 0 else neg}")


def hint(actions, to_key, chunk_frames: int, session: bool, turn_cal: bool, unit: int = 20) -> str:
    yaw, pitch = step_size(chunk_frames, session, turn_cal, unit)
    s = replay(actions, to_key, chunk_frames, session, turn_cal, unit)
    return (
        f"Controls: one LEFT or RIGHT turns the camera about {yaw:.0f} degrees, one UP or DOWN tilts it about "
        f"{pitch:.0f} degrees, and one W, S, A or D moves it one step forward, back, left or right. "
        f"Commanded camera now, relative to the start (heading 0, tilt 0, position 0): heading "
        f"{_side(s['heading'], 'left', 'right', 'degrees')}, tilt {_side(s['tilt'], 'down', 'up', 'degrees')}, "
        f"position {_side(s['forward'], 'back', 'forward', 'steps')} and "
        f"{_side(s['right'], 'left', 'right', 'steps')}. Turned so far in total: "
        f"{s['turned_left']:.0f} degrees left, {s['turned_right']:.0f} degrees right."
    )


def wrap(decide_action, to_key, session: bool, turn_cal: bool, on_hint=None):
    """Wrap upstream decide_action so the goal it shows the player ends with hint().
    on_hint() is called once per hint sent (flag_stats counter)."""

    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        if not kw.get("stationary_only"):
            text = hint(recent_actions or [], to_key, int(getattr(args, "chunk_frames", 33) or 33), session,
                        turn_cal, int(getattr(args, "action_frame_unit", 20) or 20))
            print(f"    [lingbot] player hint: {text.split('Commanded camera now, ', 1)[1]}", flush=True)
            task = {**task, "prompt": f"{task.get('prompt', '')}\n{text}"}
            if on_hint is not None:
                on_hint()
        return decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)

    return decide
