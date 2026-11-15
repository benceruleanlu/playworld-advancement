"""Opt-in IF horizon: end a closed-loop IF rollout after a budget of chunks sized from its dataset action.

The harness lets the player run 30 chunks (about 60 s). IF dataset actions are short (median
`w*8`, 160 frames, 5 chunks), and the IF rubric does not reward duration: motion that goes on
after the action is complete earns nothing, a short clear process can reach level 3, and every
defect that shows up later is still scored. The baseline IF rollouts held one key for 28 to 30
chunks, and the judge's reasons place the defects in the middle or late part of the video
(IF002, IF010, IF031, IF052 in results/reports/lb14-session-agent-dev-v1.*.md).

`wrap()` gives each IF task a budget: `mult` (2) times the frames of its dataset action
(tokens x action_frame_unit), in chunks, at least `floor` (6). The player is told the budget as
its step limit and still chooses every action; at the budget the wrapper answers END.
Only the length of the dataset action is used, never its keys. GC, insight and out-of-sight
tasks pass through untouched.
"""
from __future__ import annotations

import math
import os


def is_if(task: dict) -> bool:
    return str(task.get("category") or "").upper() == "IF" or str(task.get("task_id") or "").upper().startswith("IF")


def budget(task: dict, parse_segments, chunk_frames: int = 33, unit: int = 20, mult: float = 2.0,
           floor: int = 6) -> int:
    """Chunks an IF rollout may run: mult x its dataset action's frames, at least floor."""
    tokens = sum(int(n) for _, n in parse_segments(task))
    return max(int(floor), math.ceil(mult * tokens * unit / max(1, int(chunk_frames) - 1)))


def wrap(decide_action, parse_segments, on_event=None, mult: float | None = None, floor: int | None = None):
    """Wrap decide_action. on_event("armed", cap) for each IF decision, on_event("end", cap) when the
    wrapper answers END at the budget."""
    mult = float(os.environ.get("LINGBOT_IF_HORIZON_MULT", "2")) if mult is None else mult
    floor = int(os.environ.get("LINGBOT_IF_HORIZON_MIN", "6")) if floor is None else floor
    emit = on_event or (lambda kind, cap: None)

    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        if kw.get("stationary_only") or kw.get("allow_next") or not is_if(task):
            return decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)
        cap = min(int(num_chunks), budget(task, parse_segments, int(getattr(args, "chunk_frames", 33) or 33),
                                           int(getattr(args, "action_frame_unit", 20) or 20), mult, floor))
        emit("armed", cap)
        if int(chunk_idx) >= cap:
            emit("end", cap)
            print(f"    [lingbot] IF horizon: {task.get('task_id')} reached its budget of {cap} chunks "
                  f"-> END (player not asked)", flush=True)
            return "END"
        return decide_action(task, frame, recent_actions, chunk_idx, cap, args, *rest, **kw)

    return decide
