#!/usr/bin/env python3
"""LingBot-World v2 1.3B causal-fast: the lingbot_world2 runner with the small checkpoint."""
import os
import runpy
import sys
from pathlib import Path


def main(argv=None) -> int:
    """In-process entry point (pwa gen-arms): same as running this script, but the loaded pipe is kept
    in adapters.lingbot_world2.run between calls."""
    os.environ.setdefault("LINGBOT_VARIANT", "1.3b")
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from adapters.lingbot_world2 import run  # noqa: PLC0415
    return run.main(argv)


if __name__ == "__main__":
    os.environ.setdefault("LINGBOT_VARIANT", "1.3b")
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "lingbot_world2" / "run.py"), run_name="__main__")
