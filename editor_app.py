"""Live LingBot kernel: the model stays loaded on a Modal GPU and takes Python cells from another machine.

Built for measuring the model directly (scripted camera trials, activations) without the player or the judge:
adapters/lingbot_world2/workspace.py lists what a cell can use, camera_probe.py the camera measurements.

    modal run prefetch_lingbot.py --variant 14b      # once: weights into the pwa-weights Volume
    PWA_EDITOR_VARIANT=14b modal deploy editor_app.py  # once; after changing code: modal app stop pwa-editor, then deploy
    python -m pwa.kernel status                      # first call cold-starts the GPU; later calls are warm
    python -m pwa.kernel exec cell.py                # or: -c "ws.status()", or a cell on stdin
    python -m pwa.kernel reset                       # fresh namespace
    modal app stop pwa-editor                        # remove the deployment (it also scales to zero by itself)

It runs in whichever Modal workspace this machine is logged in to, never through Actions, and mounts no secrets.
The GPU is billed while a container is up: it scales to zero after PWA_EDITOR_IDLE seconds without a call
(default 900), and the Python namespace is lost when it does.

A redeploy does NOT replace containers that are already up: they keep taking calls with the code they started
with (seen 2026-11-14: three containers from two earlier deploys took the next three batches and their results were
lost). After changing adapters/, pwa/ or this file run `modal app stop pwa-editor` first, then deploy.

Set at deploy time: PWA_EDITOR_APP (another name for a second deployment), PWA_EDITOR_VARIANT (1.3b default, or 14b), PWA_MODAL_GPU (H100; the 14B peaks near 64 GiB,
the 1.3B near 27), PWA_EDITOR_IDLE, PWA_EDITOR_CPU (8), PWA_EDITOR_MAX_CONTAINERS (1). The pipe is loaded by the
runner's own load_pipe (adapters/lingbot_world2/run.py), so the kernel measures the model the runs use.
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
ENV = {"PWA_EDITOR_APP": APP, "PWA_EDITOR_VARIANT": VARIANT, "LINGBOT_VARIANT": VARIANT, "PWA_MODAL_GPU": GPU, "PWA_EDITOR_IDLE": str(IDLE),
       "LINGBOT_CPU_THREADS": "auto", "PWA_EDITOR_MAX_CONTAINERS": os.environ.get("PWA_EDITOR_MAX_CONTAINERS", "1"),  # the 14B runs T5 on the CPU: one thread takes about 68 s per new prompt
       **({"LINGBOT_FAST_DIT": "1", "LINGBOT_FAST_LOAD": "1"} if VARIANT == "14b" else {})}  # GPU-side load (#79)
CPU = float(os.environ.get("PWA_EDITOR_CPU", "8"))
# More than one container runs batches in parallel, but then cells no longer share one namespace: keep 1 for
# interactive work and make every batch cell self-contained (and write to its own file) when raising it.
MAX_CONTAINERS = int(os.environ.get("PWA_EDITOR_MAX_CONTAINERS", "1"))


@app.cls(image=image, gpu=GPU, timeout=3600, startup_timeout=1800, scaledown_window=IDLE, max_containers=MAX_CONTAINERS,
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
        self.ws.drain()
        self.ns = self.ws.namespace()
        return self.ws.status()
