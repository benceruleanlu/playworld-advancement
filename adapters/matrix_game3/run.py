#!/usr/bin/env python3
"""Matrix-Game 3.0 runner skeleton: upstream closed-loop harness with MG3 swapped in for SANA-WM.

Same argv as run_agent.py. `pwa gen EXP --runner matrix_game3 ...`
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402

run_agent = import_run_agent()


class MatrixGame3Engine:
    """Drop-in for run_agent.SanaWMEngine."""

    def __init__(self, args):
        self.args = args
        self.root = os.environ.get("MG3_ROOT")
        self.checkpoint = os.environ.get("MG3_CHECKPOINT")
        # TODO: load the MG3 pipeline ONCE here from MG3_ROOT / MG3_CHECKPOINT (sys.path insert MG3_ROOT).

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        """Return the Path of an mp4 continuing from image_path under `action`.

        `action` is the SANA-style string run_agent builds, comma-separated
        "<key>-<frames>" segments (keys from run_agent.to_sana_key: w/s/a/d,
        camera keys i/k/j/l = up/down/left/right, "none" = wait). TODO:
          1. parse segments -> per-frame MG3 keyboard (WASD) + mouse (yaw/pitch) conditioning
          2. run MG3 for num_frames from image_path (prompt as text condition if supported)
          3. write <output_dir>/<name>.mp4 and return that Path
        """
        raise NotImplementedError(
            "MatrixGame3Engine.generate: TODO load MG3 from $MG3_ROOT/$MG3_CHECKPOINT once in __init__, "
            "map the PlayWorld action string to MG3 keyboard/mouse conditioning, return the mp4 path")


run_agent.SanaWMEngine = MatrixGame3Engine
print(f"[adapter] agent provider: {agent_api.patch(run_agent)}", flush=True)
raise SystemExit(run_agent.main())
