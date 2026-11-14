"""Run `pwa gen` shards on Modal GPUs. Rollouts land in the `pwa-runs` Volume at /<EXP>.

    modal run modal_app.py --exp sana-base-dev --split dev --runner sana --action-source dataset --num-shards 4
    modal volume get pwa-runs /sana-base-dev runs/      # then: pwa score / pwa report locally

GPU type: PWA_MODAL_GPU (default H100). Secrets: Modal secret `pwa` holding the
config/env.sh keys (PLAYER_API_*, HF_TOKEN). Weights cache in the `pwa-weights` Volume.

The SANA install below is a first guess at upstream's setup; verify on the first run.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent
GPU = os.environ.get("PWA_MODAL_GPU", "H100")
SANA_REF = os.environ.get("PWA_SANA_REF", "main")

app = modal.App("playworld-advancement")
runs_vol = modal.Volume.from_name("pwa-runs", create_if_missing=True)
weights_vol = modal.Volume.from_name("pwa-weights", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install("torch", "torchvision", "httpx", "imageio", "imageio-ffmpeg",
                 "opencv-python-headless", "Pillow", "numpy", "pyrallis")
    .run_commands(f"git clone --depth 1 --branch {SANA_REF} https://github.com/NVlabs/Sana /opt/Sana",
                  "cd /opt/Sana && pip install -e .")
    .env({
        "SANA_ROOT": "/opt/Sana",
        "HF_HOME": "/weights/hf",
        "PWA_ROOT": "/repo",
        "PWA_RUNS": "/runs",
        "PYTHONPATH": "/repo",
        "WORLDMODEL_BENCHMARK_DIR": "/repo/third_party/PlayWorld",
    })
    .add_local_dir(ROOT, "/repo", ignore=[".git", ".venv", "runs", "results", "**/__pycache__", "*.egg-info"])
)


@app.function(image=image, gpu=GPU, timeout=6 * 3600,
              volumes={"/runs": runs_vol, "/weights": weights_vol},
              secrets=[modal.Secret.from_name("pwa")])
def gen_shard(argv: list[str], shard: int, num_shards: int, prov: dict[str, str]) -> int:
    env = {**os.environ, **prov}
    cmd = ["python", "-m", "pwa.cli", "gen", *argv]
    if num_shards > 1:
        cmd += ["--shard", str(shard), "--num-shards", str(num_shards)]
    try:
        return subprocess.run(cmd, cwd="/repo", env=env).returncode
    finally:
        runs_vol.commit()
        weights_vol.commit()


def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


@app.local_entrypoint()
def main(exp: str, split: str = "dev", runner: str = "sana", action_source: str = "dataset",
         num_shards: int = 1, resume: bool = False, notes: str = "", tasks: str = "", extra: str = ""):
    import re
    if not re.fullmatch(r"[A-Za-z0-9._-]+", exp):
        raise SystemExit(f"bad experiment name {exp!r}")
    existing = {e.path.strip("/") for e in runs_vol.listdir("/")}
    if exp in existing and not resume:
        # Shards always pass --resume to pwa, so this is the overwrite guard.
        raise SystemExit(f"{exp} already exists in the pwa-runs Volume; pick a new name or pass --resume")
    argv = [exp, "--runner", runner, "--action-source", action_source]
    argv += ["--tasks", *tasks.split(",")] if tasks else ["--split", split]
    if resume or num_shards > 1:
        # Shards share runs/EXP; pwa keeps per-shard meta files, so --resume is safe here.
        argv.append("--resume")
    if notes:
        argv += ["--notes", notes]
    if extra:
        argv += ["--", *extra.split()]
    prov = {
        "PWA_GIT_SHA": _git("rev-parse", "HEAD"),
        "PWA_GIT_DIRTY": "1" if _git("status", "--porcelain", "--", ".", ":!runs", ":!results") else "0",
        "PWA_SUBMODULE_SHA": _git("rev-parse", "HEAD", cwd=ROOT / "third_party" / "PlayWorld"),
    }
    codes = list(gen_shard.starmap([(argv, i, num_shards, prov) for i in range(num_shards)]))
    print(f"shard exit codes: {codes}")
    if any(codes):
        raise SystemExit(1)
