"""Run `pwa gen` shards on Modal GPUs. Rollouts land in the `pwa-runs` Volume at /<EXP>.

    modal run modal_app.py --exp sana-base-dev --split dev --runner sana --action-source dataset --num-shards 4
    modal volume get pwa-runs /sana-base-dev runs/      # then: pwa score / pwa report locally

GPU type: PWA_MODAL_GPU (default H100). Secrets: Modal secret `pwa` holding the
config/env.sh keys (PLAYER_API_*, HF_TOKEN). Weights cache in the `pwa-weights` Volume.

SANA install mirrors upstream environment_setup.sh at the pinned commit.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parent
GPU = os.environ.get("PWA_MODAL_GPU", "H100")
SANA_REF = os.environ.get("PWA_SANA_REF", "27303b8de8e3f02f5dc96acf14705a0e04fca355")  # pinned 2026-11-14

app = modal.App("playworld-advancement")
runs_vol = modal.Volume.from_name("pwa-runs", create_if_missing=True)
weights_vol = modal.Volume.from_name("pwa-weights", create_if_missing=True)

# Mirrors NVlabs/Sana environment_setup.sh (cu128 torch stack, mmcv without build
# isolation, Pi3 --no-deps). SANA uses its xFormers/SDPA fallback for video
# attention, avoiding a source build of flash-attn for the pinned Torch stack.
image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.11")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0", "build-essential", "ninja-build")
    .pip_install("pip", "wheel", "setuptools<80", "packaging", "ninja")
    .run_commands(
        "pip install --index-url https://download.pytorch.org/whl/cu128 "
        "torch==2.9.1 torchvision==0.24.1 torchaudio==2.9.1 xformers==0.0.33.post2",
        "pip install --no-build-isolation mmcv==1.7.2",
        f"git clone https://github.com/NVlabs/Sana /opt/Sana && cd /opt/Sana && git checkout {SANA_REF}",
        "cd /opt/Sana && pip install -e .",
        "pip install --no-deps git+https://github.com/yyfz/Pi3.git",
    )
    .pip_install("httpx", "imageio", "imageio-ffmpeg", "opencv-python-headless", "Pillow", "pyrallis")
    .env({
        "DISABLE_FLASH_ATTN": "1",
        "SANA_ROOT": "/opt/Sana",
        "HF_HOME": "/weights/hf",
        "PWA_ROOT": "/repo",
        "PWA_RUNS": "/runs",
        "PYTHONPATH": "/repo",
        "WORLDMODEL_BENCHMARK_DIR": "/repo/third_party/PlayWorld",
    })
    .add_local_dir(ROOT, "/repo", ignore=[".git", ".venv", "runs", "results", "**/__pycache__", "*.egg-info"])
)

# Runner-specific image. PWA_RUNNER must be set when launching a lingbot runner
# (the workflow sets it); the image bakes it in so containers pick the same branch.
RUNNER_ENV = os.environ.get("PWA_RUNNER", "")
if RUNNER_ENV.startswith("lingbot"):
    import sys
    sys.path.insert(0, str(ROOT))
    from adapters.lingbot_world2.modal_image import build as _lingbot_image
    image = _lingbot_image(ROOT, RUNNER_ENV)


def shard_argv(argv: list[str], shard: int, num_shards: int) -> list[str]:
    """`pwa gen` argv for one shard. The shard flags belong to pwa, so they go before the `--` that starts
    the runner's extra args; appended after it they would reach only the runner, and pwa would treat every
    worker as shard 0 of 1 (expecting all tasks and overwriting meta.json and gen.log)."""
    if num_shards <= 1:
        return list(argv)
    flags = ["--shard", str(shard), "--num-shards", str(num_shards)]
    i = argv.index("--") if "--" in argv else len(argv)
    return [*argv[:i], *flags, *argv[i:]]


def cap_argv(max_chunks: int) -> list[str]:
    """`pwa gen` flag for a capped smoke run (0 = uncapped, the default). A pwa flag, so it goes before `--`."""
    if max_chunks < 0:
        raise SystemExit("max_chunks must be >= 0 (0 = uncapped)")
    return [f"--max-chunks={max_chunks}"] if max_chunks else []


@app.function(image=image, gpu=GPU, timeout=6 * 3600,
              volumes={"/runs": runs_vol, "/weights": weights_vol},
              secrets=[modal.Secret.from_name("pwa")])
def gen_shard(argv: list[str], shard: int, num_shards: int, prov: dict[str, str]) -> int:
    env = {**os.environ, **prov}
    cmd = ["python", "-m", "pwa.cli", "gen", *shard_argv(argv, shard, num_shards)]
    try:
        return subprocess.run(cmd, cwd="/repo", env=env).returncode
    finally:
        runs_vol.commit()
        weights_vol.commit()


@app.function(image=image, gpu=GPU, timeout=6 * 3600,
              volumes={"/runs": runs_vol, "/weights": weights_vol},
              secrets=[modal.Secret.from_name("pwa")])
def gen_arms_shard(argv: list[str], shard: int, num_shards: int, prov: dict[str, str]) -> int:
    """`pwa gen-arms`: every arm on this shard's tasks in one process, so the model loads once per container."""
    env = {**os.environ, **prov}
    cmd = ["python", "-m", "pwa.cli", "gen-arms", *shard_argv(argv, shard, num_shards)]
    try:
        return subprocess.run(cmd, cwd="/repo", env=env).returncode
    finally:
        runs_vol.commit()
        weights_vol.commit()


def arm_exps(exp: str, arms: str) -> list[str]:
    """Experiment names `pwa gen-arms` writes for --arms (pwa/arms.py arm_names; '|'-separated)."""
    return [f"{exp}-a{i}" for i in range(1, len(arms.split("|")) + 1)] if arms.strip() else []


def claim_names(exp: str, arms: str, existing: set, resume: bool) -> list:
    """Experiment directories this invocation writes. The overwrite guard: refuses if one is already in the
    Volume (shards always pass --resume to pwa, so nothing else stops a reused name)."""
    names = arm_exps(exp, arms) or [exp]
    taken = [n for n in names if n in existing]
    if taken and not resume:
        raise SystemExit(f"{' '.join(taken)} already in the pwa-runs Volume; pick a new name or pass --resume")
    return names


def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


@app.local_entrypoint()
def main(exp: str, split: str = "dev", runner: str = "sana", action_source: str = "dataset",
         num_shards: int = 1, resume: bool = False, notes: str = "", tasks: str = "", extra: str = "",
         arms: str = "", max_chunks: int = 0):
    """arms: '|'-separated runner arg strings (pwa gen-arms). Each shard's container runs every arm, so the
    model loads once per container; arm i lands in the Volume at /<EXP>-a<i>."""
    import re
    if not re.fullmatch(r"[A-Za-z0-9._-]+", exp):
        raise SystemExit(f"bad experiment name {exp!r}")
    if runner.startswith("lingbot") != RUNNER_ENV.startswith("lingbot"):
        raise SystemExit(f"runner {runner!r} needs a matching image: rerun with PWA_RUNNER={runner} in the environment")
    existing = {e.path.strip("/") for e in runs_vol.listdir("/")}
    names = claim_names(exp, arms, existing, resume)
    argv = [exp, "--runner", runner, "--action-source", action_source]
    if arms:
        argv.append(f"--arms={arms}")  # one token: arm strings start with dashes
    argv += ["--tasks", *tasks.split(",")] if tasks else ["--split", split]
    if resume or num_shards > 1:
        # Shards share runs/EXP; pwa keeps per-shard meta files, so --resume is safe here.
        argv.append("--resume")
    if notes:
        argv.append(f"--notes={notes}")  # one token, so notes starting with a dash still parse
    argv += cap_argv(max_chunks)
    if extra:
        argv += ["--", *extra.split()]
    prov = {
        "PWA_GIT_SHA": _git("rev-parse", "HEAD"),
        "PWA_GIT_BRANCH": os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD"),
        "PWA_GIT_DIRTY": "1" if _git("status", "--porcelain", "--", ".", ":!runs", ":!results") else "0",
        "PWA_SUBMODULE_SHA": _git("rev-parse", "HEAD", cwd=ROOT / "third_party" / "PlayWorld"),
    }
    if os.environ.get("PWA_RUN_ID"):
        prov["PWA_RUN_ID"] = os.environ["PWA_RUN_ID"]  # recorded as run_id in each meta.json
    claim = os.environ.get("PWA_CLAIM_FILE")
    if claim:
        # Written only after the overwrite guard passed: the directories this invocation generates into.
        Path(claim).write_text("".join(f"{n}\n" for n in names))
    fn = gen_arms_shard if arms else gen_shard
    codes = list(fn.starmap([(argv, i, num_shards, prov) for i in range(num_shards)]))
    print(f"shard exit codes: {codes}")
    if any(codes):
        raise SystemExit(1)
