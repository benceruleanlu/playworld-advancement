"""Opt-in scripted player: a fixed, chunked replay of the task's dataset action in the closed-loop path.

For A/B iteration of model-side flags only, never a final-number mode (final numbers need the real
closed-loop player). `--action-source dataset` replays the dataset action as one long `<task>_full`
call, so chunk-level engine flags (GC chunk director, GC ease turns, re-anchor) never fire; with
`--action-source agent` an LLM player chooses every chunk and its choices differ between arms.
`wrap()` replaces the player: each closed-loop decision returns the next piece of the task's script,
so the harness still generates `<task>_chunk_NN` calls (one key held for `--chunk-frames`), the LLM is
never called, and every arm gets the same chunk list for the same task.

Chunking rule (`script()`): upstream `parse_segments` reads the action (so `u*`/`j*` are UP/DOWN,
`interact(...)` with a count is W, an action with no `*n` count falls back to upstream's `W*80`), and
each axis converts dataset tokens to chunks with its own unit:
  * yaw and pitch (LEFT/RIGHT/UP/DOWN): `rot_units` = poses.CHUNK_UNITS (2, LINGBOT_CHUNK_UNITS) tokens
    per chunk, the rotation one chunk makes under --lingbot-turn-cal (`→*4` = 2 chunks = 90 degrees);
  * translation and WAIT (W/S/A/D/WAIT): `move_units` = (chunk_frames - 1) / action_frame_unit = 32 / 20
    = 1.6 tokens per chunk, because a token is held for 20 frames in dataset mode and translation per
    frame is fixed (session.TRANS_SCALE), whatever turn-cal does.
Rounding is on each axis's running total, so errors cancel across segments: a loop that closes in the
dataset (GC005, lateral net 0) closes in the script, and every axis ends within half a chunk of the
dataset's net displacement. Every segment still gets at least one chunk, so tasks that alternate
1-token segments (IF009, IF028 `w*1 -> d*1 ...`, OE033 `d*1 -> wait*1 ...`) move more than the dataset
until a later segment on that axis rounds the total back. Upstream's `--dataset-actions-per-chunk` (3)
and `grouped_dataset_actions` are not used. STOP or END inside a dataset action becomes WAIT.
Angles match the dataset only with --lingbot-turn-cal; without it one chunk turns about 55 degrees
(48 on the first).

After the script: `tail` WAIT chunks, then END. Dataset mode appends `--tail-frames` (50) frames of
no motion after the action (build_full_sana_action), so the scripted rollout ends on the same kind of
settled view: tail = ceil(tail_frames / (chunk_frames - 1)) = 2 chunks by default
(LINGBOT_SCRIPTED_TAIL overrides). The harness cap (`--num-chunks`, `--max-chunks`, frame budget)
still cuts a longer script, e.g. IF033 (no counts, `W*80` fallback, 50 W chunks) stops at 30, where
dataset mode rescales the same all-W action to the frame budget.

The wrapper is the outermost decide_action wrapper: the player-side wrappers inside it (player hint,
IF repeat, IF camera, GC completion, return stop, IF horizon) and player history endpoints (it patches
the frame sampler only decide_action calls) are never reached, so their counters stay 0. Engine-side
flags see the chunk calls as in a closed-loop run. Wait-only insight tasks never call decide_action
(upstream fixes their WAIT chunks), so they are unchanged.
"""
from __future__ import annotations

import math
import os

from . import poses as P

# action -> (axis, sign); yaw/pitch use rot_units, the rest move_units
AXIS = {"RIGHT": ("yaw", 1), "LEFT": ("yaw", -1), "UP": ("pitch", 1), "DOWN": ("pitch", -1),
        "W": ("fwd", 1), "S": ("fwd", -1), "D": ("lat", 1), "A": ("lat", -1), "WAIT": ("wait", 1)}
ROT_AXES = ("yaw", "pitch")


def units() -> float:
    """Dataset rotation tokens per scripted chunk (poses.CHUNK_UNITS)."""
    return float(P.CHUNK_UNITS)


def move_units(args) -> float:
    """Dataset translation/WAIT tokens per scripted chunk: chunk frames after the stitch frame / frames per token."""
    chunk = int(getattr(args, "chunk_frames", 33) or 33)
    unit = int(getattr(args, "action_frame_unit", 20) or 20)
    return max(1, chunk - 1) / max(1, unit)


def tail_chunks(args, environ=os.environ) -> int:
    raw = environ.get("LINGBOT_SCRIPTED_TAIL")
    if raw not in (None, ""):
        return max(0, int(raw))
    tail = int(getattr(args, "tail_frames", 50) or 0)
    return math.ceil(tail / max(1, int(getattr(args, "chunk_frames", 33) or 33) - 1)) if tail > 0 else 0


def validate(environ=os.environ) -> None:
    """Fail at startup, not inside upstream's per-task loop (which would skip every task and exit 0)."""
    raw = environ.get("LINGBOT_SCRIPTED_TAIL")
    if raw not in (None, ""):
        try:
            ok = int(raw) >= 0
        except ValueError:
            ok = False
        if not ok:
            raise SystemExit(f"LINGBOT_SCRIPTED_TAIL must be a non-negative integer, got {raw!r}")
    raw = environ.get("LINGBOT_CHUNK_UNITS", "2")
    try:
        ok = float(raw) > 0
    except ValueError:
        ok = False
    if not ok:
        raise SystemExit(f"LINGBOT_CHUNK_UNITS must be a positive number, got {raw!r}")


def script(task: dict, parse_segments, valid, rot_units: float | None = None,
           move: float = 32 / 20) -> list[str]:
    """The task's dataset action as one action word per chunk (no tail). parse_segments and valid are
    upstream run_agent.parse_segments and VALID_ACTIONS."""
    rot = units() if rot_units is None else float(rot_units)
    out, target, done = [], {}, {}
    for action, count in parse_segments(task):
        a = action if action in valid else "W"
        a = "WAIT" if a in ("STOP", "END") else a
        ax, sign = AXIS[a]
        target[ax] = target.get(ax, 0.0) + sign * int(count) / (rot if ax in ROT_AXES else float(move))
        k = max(1, sign * (math.floor(target[ax] + 0.5) - done.get(ax, 0)))
        done[ax] = done.get(ax, 0) + sign * k
        out += [a] * k
    return out or ["W"]


def plan(task: dict, args, parse_segments, valid) -> list[str]:
    """Script plus tail WAIT chunks; END follows."""
    return script(task, parse_segments, valid, move=move_units(args)) + ["WAIT"] * tail_chunks(args)


def wrap(decide_action, parse_segments, valid, on_event=None):
    """Replace decide_action (which is kept only so the wrapper chain stays a chain; it is never called).
    on_event("plan", n) once per decision with the plan length, ("chunk", n) for a scripted action,
    ("end", n) when the plan is exhausted."""
    emit = on_event or (lambda kind, n: None)

    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        if kw.get("allow_next"):
            raise RuntimeError("--lingbot-scripted-player does not support --action-source dataset_then_agent")
        if kw.get("stationary_only"):  # upstream never asks on wait-only insight tasks; keep the LLM out anyway
            return "WAIT"
        steps = plan(task, args, parse_segments, valid)
        emit("plan", len(steps))
        i = int(chunk_idx)
        if i < len(steps):
            emit("chunk", len(steps))
            print(f"    [lingbot] scripted player: {task.get('task_id')} chunk {i + 1}/{len(steps)} -> {steps[i]}",
                  flush=True)
            return steps[i]
        emit("end", len(steps))
        print(f"    [lingbot] scripted player: {task.get('task_id')} script done after {len(steps)} chunks -> END",
              flush=True)
        return "END"

    decide.scripted = True
    return decide


def check_action_source(argv: list[str]) -> None:
    """The flag needs the chunked closed-loop path: --action-source agent or refined (upstream default)."""
    src = "refined"
    for i, a in enumerate(argv):
        if a == "--action-source" and i + 1 < len(argv):
            src = argv[i + 1]
        elif a.startswith("--action-source="):
            src = a.split("=", 1)[1]
    if src not in ("agent", "refined"):
        raise SystemExit(f"--lingbot-scripted-player needs --action-source agent or refined, got {src!r}")
