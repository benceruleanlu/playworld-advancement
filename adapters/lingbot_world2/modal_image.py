"""Modal image for the lingbot_world2 runners. modal_app.py selects it when PWA_RUNNER starts with "lingbot"."""
from __future__ import annotations

from pathlib import Path

import modal

LINGBOT_REF = "1895d300d8ac936401689b26389f51cbd36530eb"  # Robbyant/lingbot-world-v2, pinned 2026-11-14
# flash-attn is a hard dependency (cross-attention has no SDPA fallback); prebuilt wheel for torch 2.5 / cu12 / py311.
FLASH_ATTN = ("https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.4.post1/"
              "flash_attn-2.7.4.post1+cu12torch2.5cxx11abiFALSE-cp311-cp311-linux_x86_64.whl")


def build(root: Path, runner: str) -> modal.Image:
    return (
        modal.Image.from_registry("nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04", add_python="3.11")
        .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
        .pip_install("torch==2.5.1", "torchvision==0.20.1", "torchaudio==2.5.1",
                     index_url="https://download.pytorch.org/whl/cu124")
        .pip_install(
            # lingbot-world-v2 requirements.txt
            "opencv-python-headless>=4.9.0.80", "diffusers>=0.31.0", "transformers>=4.49.0,<=4.51.3",
            "tokenizers>=0.20.3", "accelerate>=1.1.1", "tqdm", "imageio[ffmpeg]", "easydict", "ftfy",
            "imageio-ffmpeg", "numpy>=1.23.5,<2", "scipy", "einops", "safetensors", FLASH_ATTN,
            # upstream run_agent
            "httpx", "Pillow")
        .run_commands(f"git clone https://github.com/Robbyant/lingbot-world-v2 /opt/lingbot "
                      f"&& cd /opt/lingbot && git checkout {LINGBOT_REF}")
        .env({
            "PWA_RUNNER": runner,  # containers re-import modal_app.py and must pick this image again
            "LINGBOT_ROOT": "/opt/lingbot",
            "LINGBOT_WEIGHTS": "/weights/lingbot",
            "HF_HOME": "/weights/hf",
            "PWA_ROOT": "/repo",
            "PWA_RUNS": "/runs",
            "PYTHONPATH": "/repo",
            "WORLDMODEL_BENCHMARK_DIR": "/repo/third_party/PlayWorld",
        })
        .add_local_dir(root, "/repo", ignore=[".git", ".venv", "runs", "results", "**/__pycache__", "*.egg-info"])
    )
