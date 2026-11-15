"""Opt-in visual progress check after four identical IF player actions."""

ACTIONS = {"W", "S", "A", "D", "LEFT", "RIGHT", "UP", "DOWN", "WAIT"}
REMINDER = (
    "Reassess visible progress before repeating again. Compare the latest frames with earlier "
    "frames: did the subject actually advance toward the goal, make the intended contact, or "
    "move the intended object? Repetition alone does not prove progress or failure. Continue "
    "the same action if it is visibly working; if blocked or repeating an ineffective gesture, "
    "reconsider the next control from the scene evidence while preserving the original goal. "
    "If the goal calls for continuing forward or attempting contact with an obstacle, keep that "
    "attempt; do not evade the obstacle just to create visible movement."
)


def wrap(decide_action, on_hint):
    def decide(task, frame, recent_actions, *args, **kwargs):
        recent = recent_actions or []
        last = recent[-1] if recent else None
        if str(task.get("task_id", "")).startswith("IF") and last in ACTIONS and len(recent) >= 4:
            if all(a == last for a in recent[-4:]):
                task = {**task, "prompt": f"{task.get('prompt', '')}\n{REMINDER}"}
                on_hint()
        return decide_action(task, frame, recent_actions, *args, **kwargs)
    return decide
