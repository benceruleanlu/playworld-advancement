"""Deployed Modal app `playworld-warm`: LingBot containers that keep the loaded pipe between smoke runs.

    python -m pwa.warm run --exp NAME --arms "base" --tasks GC005 --runner lingbot_world2   # deploys if needed
    python -m pwa.warm stop                                                               # = modal app stop playworld-warm

One class per runner (Lingbot14b, Lingbot1p3b), so the two variants warm up and scale down independently.
@modal.enter loads the pipe into adapters.lingbot_world2.run._PIPES; run_arms then runs `pwa gen-arms`
in-process (pwa/warm.py WarmWorker), which finds the pipe there instead of loading it. Outputs and the
pwa-runs Volume layout are the same as modal_app.py's gen_arms_shard.

Settings are read when this file is deployed (pwa.warm.settings): PWA_MODAL_GPU (H100), PWA_WARM_IDLE_MIN
(scaledown_window, default 10, at most 20), PWA_WARM_MAX_CONTAINERS (per class, default 3, at most 8).
min_containers is 0: nothing stays up beyond the idle window after the last call. An idle container bills
the GPU rate until the window expires; `python -m pwa.warm stop` ends it at once.

The container runs the code baked in at deploy time. PWA_WARM_DEPLOY_SHA records that commit, and a call
from another commit is refused (pwa.warm.run redeploys first, which starts cold containers). A checkout with
uncommitted changes always redeploys with a fresh PWA_WARM_DEPLOY_TOKEN, and such a deployment accepts only
calls carrying that token (from the client that deployed it); a dirty caller is refused by any other deployment.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pwa import warm as W  # noqa: E402

S = W.settings()
DEPLOY_SHA = os.environ.get("PWA_WARM_DEPLOY_SHA") or W._git("rev-parse", "HEAD")

app = modal.App(W.APP_NAME)
runs_vol = modal.Volume.from_name("pwa-runs", create_if_missing=True)
weights_vol = modal.Volume.from_name("pwa-weights", create_if_missing=True)

# Same image as modal_app.py's lingbot path (its PWA_RUNNER value is unused here).
from adapters.lingbot_world2.modal_image import build as _lingbot_image  # noqa: E402
image = _lingbot_image(ROOT, "lingbot_world2")

CLS_KW = dict(image=image, gpu=S["gpu"], timeout=S["timeout"], scaledown_window=S["scaledown_window"],
              max_containers=S["max_containers"], min_containers=0,
              volumes={"/runs": runs_vol, "/weights": weights_vol}, secrets=[modal.Secret.from_name("pwa")])


def _worker(runner: str) -> W.WarmWorker:
    from pwa import arms, cli  # noqa: PLC0415
    w = W.WarmWorker(runner, os.environ.get("PWA_WARM_DEPLOY_SHA", ""), run_pwa=cli.main,
                     reload=runs_vol.reload, commit=runs_vol.commit, free=arms._free_gpu_cache,
                     deploy_token=os.environ.get(W.TOKEN_ENV, ""))
    from adapters.lingbot_world2 import run  # noqa: PLC0415
    w.load(run.load_pipe)
    print(f"[warm] {runner}: pipe ready in {w.loaded_in}s; idle window {S['scaledown_window']}s", flush=True)
    return w


def _env(runner: str) -> dict:
    return {"LINGBOT_VARIANT": W.VARIANTS[runner], "PWA_WARM_DEPLOY_SHA": DEPLOY_SHA,
            W.TOKEN_ENV: os.environ.get(W.TOKEN_ENV, "")}


@app.cls(env=_env("lingbot_world2"), **CLS_KW)
class Lingbot14b:
    @modal.enter()
    def load(self):
        self.worker = _worker("lingbot_world2")

    @modal.method()
    def run_arms(self, argv: list[str], shard: int, num_shards: int, prov: dict) -> dict:
        return self.worker.run(argv, shard, num_shards, prov)

    @modal.exit()
    def close(self):
        runs_vol.commit()


@app.cls(env=_env("lingbot_world2_1p3b"), **CLS_KW)
class Lingbot1p3b:
    @modal.enter()
    def load(self):
        self.worker = _worker("lingbot_world2_1p3b")

    @modal.method()
    def run_arms(self, argv: list[str], shard: int, num_shards: int, prov: dict) -> dict:
        return self.worker.run(argv, shard, num_shards, prov)

    @modal.exit()
    def close(self):
        runs_vol.commit()


assert {Lingbot14b.__name__, Lingbot1p3b.__name__} == set(W.CLASSES.values())  # names pwa.warm looks up
