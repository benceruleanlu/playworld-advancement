"""Opt-in return stop: end a closed-loop rollout once the commanded camera has left and come back.

Most GC and out-of-sight goals are "go out, then return to the start view". The baseline
player never ended such a rollout before the step cap; it kept turning for 20 or more chunks
after the return, and the judge's reasons name that extra motion on GC031, GC033, GC036,
GC038, OE034 and OE058 (results/reports/lb14-session-agent-dev-v1.*.md).

`wrap()` replays the actions taken so far with the same key-to-pose math LingBot is driven
with (player_hint.replay). At the first step where the camera has gone far enough for the
goal and is back within half an action of the start on every axis, the player is no longer
asked: the wrapper answers WAIT for `hold` chunks (a still view of the start), then END.

Armed only when the goal has exactly one return phrase and nothing ordered after it
("..., then look up 40 degrees" is left to the player). How far counts as "left":
`frac` (0.75) of the largest angle and of the step count named in the goal, else 40
degrees or 2 steps. "left to right" goals must also have been on both sides of the start.

The pose is the commanded one, not measured from the video. numpy only.
"""
from __future__ import annotations

import math
import os
import re

from adapters.lingbot_world2 import player_hint as H

RETURN_RE = re.compile(r"\b(returns?|back)\b", re.I)
AFTER_RE = re.compile(r"\bthen\b", re.I)
DEG_RE = re.compile(r"(\d+)[- ]degrees?", re.I)
STEPS_RE = re.compile(r"(\d+) steps?", re.I)
SIDES_RE = re.compile(r"left to right|right to left", re.I)
DEFAULT_DEG, DEFAULT_STEPS = 40.0, 2.0


def plan(goal: str, frac: float = 0.75) -> dict | None:
    """What "left the start" means for this goal, or None when the stop must not arm."""
    hits = list(RETURN_RE.finditer(goal or ""))
    if len(hits) != 1 or AFTER_RE.search(goal, hits[0].end()):
        return None
    degs = [float(m) for m in DEG_RE.findall(goal)]
    steps = [float(m) for m in STEPS_RE.findall(goal)]
    return {"deg": frac * max(degs) if degs else None, "steps": frac * max(steps) if steps else None,
            "both_sides": bool(SIDES_RE.search(goal))}


def returned_at(actions, to_key, p: dict, chunk_frames: int, session: bool, turn_cal: bool, unit: int = 20):
    """1-based count of actions after which the commanded camera first has left (per plan p)
    and is back at the start, or None."""
    yaw_step, pitch_step = H.step_size(chunk_frames, session, turn_cal, unit)
    tokens_per_step = H.step_keys(1, chunk_frames, session) / float(unit)  # dataset "steps" per W/S/A/D action
    rot = pos = lo = hi = 0.0
    for k in range(1, len(actions) + 1):
        s = H.replay(actions[:k], to_key, chunk_frames, session, turn_cal, unit)
        net = s["turned_right"] - s["turned_left"]
        dist = math.hypot(s["forward"], s["right"])
        rot, pos = max(rot, abs(net), abs(s["tilt"])), max(pos, dist)
        lo, hi = min(lo, net), max(hi, net)
        if p["deg"] is None and p["steps"] is None:
            left = rot >= DEFAULT_DEG or pos >= DEFAULT_STEPS
        else:
            left = ((p["deg"] is None or rot >= p["deg"])
                    and (p["steps"] is None or pos * tokens_per_step >= p["steps"]))
        if p["both_sides"]:
            left = left and lo <= -yaw_step / 2 and hi >= yaw_step / 2
        home = abs(s["heading"]) <= yaw_step / 2 and abs(s["tilt"]) <= pitch_step / 2 and dist <= 0.5
        if left and home:
            return k
    return None


def wrap(decide_action, to_key, session: bool, turn_cal: bool, on_event=None, hold: int | None = None,
         frac: float | None = None):
    """Wrap decide_action. on_event("armed") once per decision of an armed task,
    on_event("stop") for every decision answered here instead of by the player."""
    hold = int(os.environ.get("LINGBOT_RETURN_STOP_HOLD", "2")) if hold is None else hold
    frac = float(os.environ.get("LINGBOT_RETURN_STOP_FRAC", "0.75")) if frac is None else frac
    emit = on_event or (lambda kind: None)

    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        p = None if kw.get("stationary_only") or kw.get("allow_next") else plan(task.get("prompt", ""), frac)
        if p is not None:
            emit("armed")
            acts = list(recent_actions or [])
            k = returned_at(acts, to_key, p, int(getattr(args, "chunk_frames", 33) or 33), session, turn_cal,
                            int(getattr(args, "action_frame_unit", 20) or 20))
            if k is not None:
                action = "WAIT" if len(acts) - k < hold else "END"
                emit("stop")
                print(f"    [lingbot] return stop: {task.get('task_id')} back at the start after action {k} "
                      f"({acts[k - 1]}), step {len(acts) + 1} -> {action} (player not asked)", flush=True)
                return action
        return decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)

    return decide
