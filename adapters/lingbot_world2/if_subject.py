"""Bind IF goal verbs to the visible subject rather than to camera movement."""
CUE = ("The visible subject performs the subject action with its own body or mechanism. "
       "Camera motion changes the viewpoint; the subject's activity remains a separate motion. "
       "Direction words in the subject action refer to the subject's facing direction unless "
       "the action explicitly names the camera.")


def compose(task, goal, name):
    task = task or {}
    tid = str(task.get("task_id", ""))
    caption = " ".join(str(task.get("image_caption") or "").split())
    perspective = str(task.get("perspective") or "").lower().replace("-", " ")
    if (not tid.startswith("IF") or not name.startswith(tid + "_") or not caption
            or not (goal or "").strip() or perspective != "third person"):
        return None
    return f"Subject action: {goal.strip()}\nScene: {caption}\n{CUE}"
