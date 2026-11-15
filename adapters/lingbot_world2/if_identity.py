"""A fixed IF identity cue, without tracking, image edits or extra model calls."""
CUE = ("Throughout this continuous shot, each original subject retains one distinct identity. "
       "Its species or mechanical construction, clothing, colors and accessories stay consistent "
       "as it moves and interacts, except for changes explicitly required by the activity. "
       "The requested activity continues through the original subjects' motion.")


def compose(task, prompt, name):
    task = task or {}
    tid = str(task.get("task_id", ""))
    perspective = str(task.get("perspective") or "").lower().replace("-", " ")
    if (not tid.startswith("IF") or not name.startswith(tid + "_") or perspective != "third person"
            or not str(task.get("image_caption") or "").strip()):
        return None
    return f"{prompt}\n{CUE}"
