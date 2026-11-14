"""Shrink a training LoRA checkpoint to bf16 for inference (adapters/lingbot_world2 --lingbot-lora=PATH).

    python -m rl.export runs/rl/rl-v1/lora_step030.safetensors rl/checkpoints/rl-v1-step030.safetensors
"""
from __future__ import annotations

import sys
from pathlib import Path


def main(src: str, dst: str):
    import torch  # noqa: PLC0415
    from safetensors.torch import load_file, save_file  # noqa: PLC0415
    state = {k: v.to(torch.bfloat16).contiguous() for k, v in load_file(src).items()}
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    save_file(state, dst, metadata={"source": Path(src).as_posix()})
    print(f"{dst}: {len(state)} tensors, {Path(dst).stat().st_size / 2**20:.1f} MiB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
