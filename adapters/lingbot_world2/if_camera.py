"""Optional third-person IF reminder about this adapter's camera-only controls."""

REMINDER = (
    "Control semantics for this adapter: W/S/A/D translate the camera and LEFT/RIGHT/UP/DOWN "
    "rotate the camera; they are not direct commands to the visible subject's limbs or heading. "
    "Keep the requested subject in view and judge its motion against stable scene landmarks. "
    "A camera turn alone is not evidence that the subject turned or walked. WAIT holds the "
    "camera still while the scene can continue evolving. Choose the next action from visible "
    "subject progress toward the original goal."
)


def wrap(decide_action, on_hint):
    def decide(task, *args, **kwargs):
        perspective = str(task.get("perspective", "")).lower().replace("-", " ")
        if str(task.get("task_id", "")).startswith("IF") and perspective == "third person":
            task = {**task, "prompt": f"{task.get('prompt', '')}\n{REMINDER}"}
            on_hint()
        return decide_action(task, *args, **kwargs)
    return decide
