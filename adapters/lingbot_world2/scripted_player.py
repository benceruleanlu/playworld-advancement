"""Opt-in scripted player: a fixed, chunked replay of the task's dataset action in the closed-loop path.

For A/B iteration of model-side flags only, never a final-number mode (final numbers need the real
closed-loop player). `--action-source dataset` replays the dataset action as one long `<task>_full`
call, so chunk-level engine flags (GC chunk director, GC ease turns, re-anchor) never fire; with
`--action-source agent` an LLM player chooses every chunk and its choices differ between arms.
`wrap()` replaces the player: each closed-loop decision returns the next piece of the task's script,
so the harness still generates `<task>_chunk_NN` calls (one key held for `--chunk-frames`), the LLM is
never called, and every arm gets the same chunk list for the same task.

Chunking rule: upstream `run_agent.grouped_dataset_actions(task, units)`, the helper upstream uses for
its own per-chunk dataset recommendation. It parses the action with `parse_segments` (so `u*`/`j*`
are UP/DOWN, `interact(...)` is W, `hold(...)` steps are the fallback) and gives each segment
`ceil(count / units)` chunks of its action, in order. `units` is `poses.CHUNK_UNITS` (2,
LINGBOT_CHUNK_UNITS), the tokens one closed-loop chunk stands for under --lingbot-turn-cal, so with
turn calibration a script turns the dataset's angles (`→*4` = 2 chunks = 90 degrees). Upstream's
`--dataset-actions-per-chunk` (3) is not used. STOP or END inside a dataset action becomes WAIT.

After the script: `tail` WAIT chunks, then END. Dataset mode appends `--tail-frames` (50) frames of
no motion after the action (build_full_sana_action), so the scripted rollout ends on the same kind of
settled view: tail = ceil(tail_frames / (chunk_frames - 1)) = 2 chunks by default
(LINGBOT_SCRIPTED_TAIL overrides). The harness cap (`--num-chunks`, `--max-chunks`, frame budget)
still cuts a longer script.

The wrapper is the outermost decide_action wrapper: the player-side wrappers inside it (player hint,
IF repeat, IF camera, GC completion, return stop, IF horizon) are never reached, so their counters stay
0. Engine-side flags see the chunk calls as in a closed-loop run. Wait-only insight tasks never call
decide_action (upstream fixes their WAIT chunks), so they are unchanged.
"""
from __future__ import annotations

import math
import os

from . import poses as P


def units() -> int:
    """Dataset tokens per scripted chunk (poses.CHUNK_UNITS, rounded to a whole token count)."""
    return max(1, int(round(P.CHUNK_UNITS)))


def tail_chunks(args, environ=os.environ) -> int:
    raw = environ.get("LINGBOT_SCRIPTED_TAIL")
    if raw not in (None, ""):
        return max(0, int(raw))
    tail = int(getattr(args, "tail_frames", 50) or 0)
    return math.ceil(tail / max(1, int(getattr(args, "chunk_frames", 33) or 33) - 1)) if tail > 0 else 0


def script(task: dict, grouped_dataset_actions, n_units: int | None = None) -> list[str]:
    """The task's dataset action as one action word per chunk (no tail)."""
    n = units() if n_units is None else int(n_units)
    return ["WAIT" if a in ("STOP", "END") else a for a in grouped_dataset_actions(task, n)]


def plan(task: dict, args, grouped_dataset_actions) -> list[str]:
    """Script plus tail WAIT chunks; END follows."""
    return script(task, grouped_dataset_actions) + ["WAIT"] * tail_chunks(args)


def wrap(decide_action, grouped_dataset_actions, on_event=None):
    """Replace decide_action (which is kept only so the wrapper chain stays a chain; it is never called).
    on_event("plan", n) once per decision with the plan length, ("chunk", n) for a scripted action,
    ("end", n) when the plan is exhausted."""
    emit = on_event or (lambda kind, n: None)

    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        if kw.get("allow_next"):
            raise RuntimeError("--lingbot-scripted-player does not support --action-source dataset_then_agent")
        if kw.get("stationary_only"):  # upstream never asks on wait-only insight tasks; keep the LLM out anyway
            return "WAIT"
        steps = plan(task, args, grouped_dataset_actions)
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
