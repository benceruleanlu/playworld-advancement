"""Opt-in GC completion reminder for the player; no forced actions or task plan."""

REMINDER = (
    "GC completion check: Execute the requested camera path once, not as a repeating loop. "
    "Use the chronological frames and action history to track which parts are finished, "
    "and choose actions only for the remaining parts. A return to the starting view does "
    "not finish a goal that requests another movement afterward. Once the frames show "
    "that every requested part is finished, choose END now. The step limit is a maximum, "
    "not a target: do not add another sweep, translation, or corrective turn to fill it. "
    "Commanded pose alone does not establish that the visual goal was achieved."
)


def wrap(decide_action, on_hint, on_end):
    def decide(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
        eligible = str(task.get("task_id", "")).startswith("GC")
        if eligible:
            task = {**task, "prompt": f"{task.get('prompt', '')}\n{REMINDER}"}
            on_hint()
        action = decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw)
        if eligible and action == "END":
            on_end()
        return action

    return decide
