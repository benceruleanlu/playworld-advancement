"""Which text the world model is conditioned on (opt-in; the default is upstream's).

The upstream SANA-WM harness hands the engine the agent's goal (`task["prompt"]`) as its
text prompt. That goal is written for the player, not the model: 29 of the 30 Insight
tasks say "wait and observe" and Out-of-sight goals are camera instructions ("Turn the
camera right 90 degrees, then return to the starting view."), so a text-conditioned model
is told nothing about the scene or the process that should keep evolving. Upstream's
Genie 3 and HappyOyster players build the world from `task["image_caption"]` instead
(`task_environmental_caption` in their player.py).

Modes:
  goal     the task goal, unchanged (default; what upstream SANA-WM does)
  caption  the scene caption
  auto     the caption, plus the goal for IF tasks, whose goal describes the subject's action

The agent player still sees the goal: only the engine's text prompt changes.
"""
from __future__ import annotations

MODES = ("goal", "caption", "auto")
_current: dict = {}


def install(run_agent) -> None:
    """Wrap run_agent.run_task so the engine can see the task it is generating for.
    main() looks run_task up in the module at call time, like SanaWMEngine."""
    original = run_agent.run_task

    def run_task(task, *args, **kwargs):
        _current["task"] = task
        return original(task, *args, **kwargs)

    run_agent.run_task = run_task


def compose(task: dict | None, goal: str, mode: str = "goal") -> str:
    """Text prompt for `task` under `mode`; the goal whenever there is no caption."""
    if mode not in MODES:
        raise ValueError(f"prompt mode must be one of {MODES}, got {mode!r}")
    caption = " ".join(str((task or {}).get("image_caption") or "").split())
    if mode == "goal" or not caption:
        return goal
    if mode == "auto" and str(task.get("category", "")).upper() == "IF" and (goal or "").strip():
        return f"{caption} {goal.strip()}"
    return caption


def model_prompt(goal: str, name: str, mode: str = "goal") -> str:
    """Prompt for the generate() call `name` ('<task_id>_chunk_NN' or '<task_id>_full').
    Falls back to the goal unless install() recorded the task this call belongs to."""
    task = _current.get("task")
    if not task or not str(name or "").startswith(f"{task.get('task_id')}_"):
        task = None
    return compose(task, goal, mode)
