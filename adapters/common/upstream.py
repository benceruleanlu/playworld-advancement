"""Locate and import the upstream SANA-WM run_agent module (no code copied)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANA_WM_DIR = REPO / "third_party" / "PlayWorld" / "Agent_player" / "SANA-WM"


def import_run_agent(fresh: bool = False):
    """fresh=True drops a previously imported run_agent first, so module globals and any functions an
    adapter patched onto it (run_task, decide_action, request_agent_action) start from upstream again."""
    if fresh:
        sys.modules.pop("run_agent", None)
    for p in (str(SANA_WM_DIR), str(REPO)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import run_agent  # noqa: PLC0415
    return run_agent
