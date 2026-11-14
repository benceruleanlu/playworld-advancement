"""Run the LingBot memory probe (adapters/lingbot_world2/probe.py) on one Modal GPU.

    modal run probe_lingbot.py --exp probe-w-v1 --variant 1.3b --windows 18:6,36:6,-1:0
    modal volume get pwa-runs /probe-w-v1 runs/

Needs data/ (./setup.sh) and the weights in the pwa-weights Volume (prefetch_lingbot.py).
Output lands in the pwa-runs Volume at /<EXP>/probe. GPU: PWA_MODAL_GPU (default H100).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2.modal_image import build  # noqa: E402

GPU = os.environ.get("PWA_MODAL_GPU", "H100")
app = modal.App("playworld-lingbot-probe")
runs_vol = modal.Volume.from_name("pwa-runs", create_if_missing=True)
weights_vol = modal.Volume.from_name("pwa-weights", create_if_missing=True)
image = build(ROOT, "lingbot_world2")


@app.function(image=image, gpu=GPU, timeout=3 * 3600,
              volumes={"/runs": runs_vol, "/weights": weights_vol},
              secrets=[modal.Secret.from_name("pwa")])
def probe_job(argv: list[str], variant: str) -> int:
    env = {**os.environ, "LINGBOT_VARIANT": variant}
    try:
        return subprocess.run([sys.executable, "-m", "adapters.lingbot_world2.probe", *argv],
                              cwd="/repo", env=env).returncode
    finally:
        runs_vol.commit()


@app.local_entrypoint()
def main(exp: str, variant: str = "1.3b", tasks: str = "OE034,OE039,OE047", angles: str = "45,90,180",
         holds: str = "0,48", windows: str = "18:6", dino: bool = False, resume: bool = False):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", exp):
        raise SystemExit(f"bad experiment name {exp!r}")
    if variant not in ("14b", "1.3b"):
        raise SystemExit("--variant must be 14b or 1.3b")
    if not (ROOT / "data").is_dir():
        raise SystemExit("data/ missing; run ./setup.sh first (the image ships the local checkout)")
    argv = [exp, "--tasks", *tasks.split(","), "--angles", *angles.split(","), "--holds", *holds.split(","),
            f"--windows={windows}"]
    argv += ["--dino"] if dino else []
    argv += ["--resume"] if resume else []
    code = probe_job.remote(argv, variant)
    print(f"probe exit code {code}; fetch with: modal volume get pwa-runs /{exp} runs/")
    if code:
        raise SystemExit(1)
