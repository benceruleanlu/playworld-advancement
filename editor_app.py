"""Live LingBot kernel for weight editing: the model stays loaded on a Modal GPU and
the editing model, running on your machine, sends it Python cells.

    modal run prefetch_lingbot.py --variant 1.3b   # once: weights into the pwa-weights Volume
    modal deploy editor_app.py                     # once, and again after changing adapters/, pwa/ or this file
    pwa kernel status                              # first call cold-starts the GPU (about 2 min); later calls are warm
    pwa kernel exec cell.py                        # or: -c "ws.params('cam_scale')", or a cell on stdin
    pwa kernel reset                               # stock weights, fresh namespace
    modal app stop pwa-editor                      # remove the deployment (it also scales to zero by itself)

What a cell can use: adapters/lingbot_world2/workspace.py.

At most one container, so every cell sees the same state. It scales to zero
after PWA_EDITOR_IDLE seconds without a call (default 900) and the GPU is billed
until then. The Python namespace is lost when it does; saved edits are not (they
live in the pwa-weights Volume under /weights/edits, where `--lingbot-edit NAME`
finds them). Redeploying also starts a fresh kernel.

Set at deploy time: PWA_MODAL_GPU (default H100; the 1.3B model peaks near 27 GiB, the 14B near 66),
PWA_EDITOR_VARIANT (1.3b default, or 14b), PWA_EDITOR_IDLE. No secrets are mounted. The pipe is loaded by
the runner's own load_pipe (adapters/lingbot_world2/run.py), so the kernel edits the model the runs use.
It runs in whichever Modal workspace this machine is logged in to.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2.modal_image import build as _lingbot_image  # noqa: E402
from pwa.kernel import APP  # noqa: E402

GPU = os.environ.get("PWA_MODAL_GPU", "H100")
VARIANT = os.environ.get("PWA_EDITOR_VARIANT", "1.3b")
IDLE = int(os.environ.get("PWA_EDITOR_IDLE", "900"))

app = modal.App(APP)
weights_vol = modal.Volume.from_name("pwa-weights", create_if_missing=True)
image = _lingbot_image(ROOT, "lingbot_world2_1p3b" if VARIANT == "1.3b" else "lingbot_world2")
# The container imports this file again: give it the deploy-time settings so it builds the same definition.
ENV = {"PWA_EDITOR_VARIANT": VARIANT, "LINGBOT_VARIANT": VARIANT, "PWA_MODAL_GPU": GPU, "PWA_EDITOR_IDLE": str(IDLE),
       "LINGBOT_CPU_THREADS": "auto",  # the 14B runs T5 on the CPU: one thread takes about 68 s per new prompt
       **({"LINGBOT_FAST_DIT": "1", "LINGBOT_FAST_LOAD": "1"} if VARIANT == "14b" else {})}  # GPU-side load (#79)
CPU = float(os.environ.get("PWA_EDITOR_CPU", "8"))


@app.cls(image=image, gpu=GPU, timeout=3600, startup_timeout=1800, scaledown_window=IDLE, max_containers=1,
         volumes={"/weights": weights_vol}, env=ENV, cpu=CPU)
class Kernel:  # the name is pwa.kernel.CLS
    @modal.enter()
    def start(self):
        from adapters.lingbot_world2 import run as R  # noqa: PLC0415
        from adapters.lingbot_world2 import workspace as W  # noqa: PLC0415

        R.FAST = R.FS.parse_flags([], os.environ)  # fast-start flags from ENV, as a run would read them
        R.FS.apply_cpu_threads(R.FAST.cpu_threads)
        cfg, pipe, _weights, _t5_cpu = R.load_pipe()
        self.W = W
        self.ws = W.Workspace(pipe, cfg, VARIANT, commit=weights_vol.commit, max_area=R.MAX_AREA)
        self.ns = self.ws.namespace()

    @modal.method()
    def run(self, code: str) -> dict:
        res = self.W.execute(self.ns, code)
        res["artifacts"] = self.ws.drain()
        res["status"] = self.ws.status()
        return res

    @modal.method()
    def status(self) -> dict:
        return self.ws.status()

    @modal.method()
    def reset(self) -> dict:
        self.ws.revert()
        self.ws.drain()
        self.ns = self.ws.namespace()
        return self.ws.status()
