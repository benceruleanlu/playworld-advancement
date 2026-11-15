"""Keep third-person IF camera poses fixed while the existing text specifies subject motion."""


def hold(task: dict | None, name: str, keys: list[str]) -> tuple[list[str], int]:
    """Return stationary pose inputs and the number of suppressed motion frames.

    Only matching third-person IF metadata with a subject goal is eligible. No rubric,
    reference actions or task-specific scripts are read. The input list is never mutated.
    """
    task = task or {}
    tid = str(task.get("task_id") or "")
    perspective = str(task.get("perspective") or "").lower().replace("-", " ").strip()
    if (not tid.startswith("IF") or not name.startswith(tid + "_")
            or perspective != "third person" or not str(task.get("prompt") or "").strip()):
        return keys, 0
    changed = sum(bool(set(k.lower().split("+")) & set("wasdijkl")) for k in keys)
    return ["none"] * len(keys), changed
