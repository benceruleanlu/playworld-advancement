#!/usr/bin/env python3
"""LingBot-World v2 1.3B causal-fast: the lingbot_world2 runner with the small checkpoint."""
import os
import runpy
from pathlib import Path

os.environ.setdefault("LINGBOT_VARIANT", "1.3b")
runpy.run_path(str(Path(__file__).resolve().parents[1] / "lingbot_world2" / "run.py"), run_name="__main__")
