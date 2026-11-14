#!/usr/bin/env python3
"""LingBot-World v2 (causal-fast) runner: upstream closed-loop harness with LingBot swapped in for SANA-WM.

Same argv as run_agent.py. `pwa gen EXP --runner lingbot_world2 ...` (14B) or
`--runner lingbot_world2_1p3b` (1.3B, for cheap iteration).

Baseline v0: every generate() call is a fresh LingBot rollout from `image_path`.
In closed loop the harness calls generate() once per chunk from the last frame,
so LingBot's KV cache (its only memory) does NOT persist across agent steps.
`--action-source dataset` is a single call, so the cache spans the whole rollout.

Env:
  LINGBOT_ROOT      checkout of Robbyant/lingbot-world-v2 (default /opt/lingbot)
  LINGBOT_WEIGHTS   dir holding lingbot-world-v2-{14b,1.3b}-causal-fast (default /weights/lingbot)
  LINGBOT_VARIANT   14b (default) | 1.3b
  LINGBOT_T5_CPU    1 keeps the 11 GB text encoder off the GPU (default: 1 for 14b, 0 for 1.3b)
  LINGBOT_YAW_RAD / LINGBOT_PITCH_RAD   per-frame camera rotation for arrow keys (poses.py)
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402

run_agent = import_run_agent()

MAX_AREA = 480 * 832  # the released checkpoints' reference resolution
LOCAL_ATTN, SINK = 18, 6  # README settings for causal-fast
DEFAULT_PROMPT = "A photo-realistic scene with rich details."


class LingBotWorld2Engine:
    """Drop-in for run_agent.SanaWMEngine."""

    def __init__(self, args):
        self.args = args
        root = os.environ.get("LINGBOT_ROOT", "/opt/lingbot")
        weights = Path(os.environ.get("LINGBOT_WEIGHTS", "/weights/lingbot"))
        variant = os.environ.get("LINGBOT_VARIANT", "14b").lower()
        if variant not in ("14b", "1.3b"):
            raise SystemExit(f"LINGBOT_VARIANT must be 14b or 1.3b, got {variant!r}")
        ckpt = weights / f"lingbot-world-v2-{variant}-causal-fast"
        # The 1.3B release ships DiT shards only; T5, VAE and tokenizer come from the 14B dir.
        assets = weights / "lingbot-world-v2-14b-causal-fast" if variant == "1.3b" else None
        for p in (Path(root) / "wan", ckpt, *( [assets] if assets else [])):
            if not p.exists():
                raise SystemExit(f"[lingbot] missing {p}; set LINGBOT_ROOT / LINGBOT_WEIGHTS or run prefetch_lingbot.py")
        t5_cpu = os.environ.get("LINGBOT_T5_CPU", "1" if variant == "14b" else "0") == "1"

        sys.path.insert(0, root)
        import wan  # noqa: PLC0415
        from wan.configs import WAN_CONFIGS  # noqa: PLC0415

        self.cfg = WAN_CONFIGS["i2v-1.3B" if variant == "1.3b" else "i2v-A14B"]
        t0 = time.time()
        self.pipe = wan.WanI2VCausal(
            config=self.cfg, checkpoint_dir=str(ckpt), device_id=0, rank=0, t5_cpu=t5_cpu,
            local_attn_size=LOCAL_ATTN, sink_size=SINK, infer_mode="causal_fast",
            assets_dir=str(assets) if assets else None)
        print(f"[lingbot] loaded {variant} from {ckpt} in {time.time() - t0:.0f}s (t5_cpu={t5_cpu})", flush=True)

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        """Write <output_dir>/<name>.mp4 continuing from image_path under `action`.

        `action` is run_agent's SANA-style string: comma-separated "<key>-<frames>"
        (w/s/a/d move, i/k/j/l look up/down/left/right, none = wait). The harness
        intrinsics are ignored: LingBot expects its own 480p calibration.
        The clip may be a few frames longer than num_frames (see poses.frame_count).
        """
        import imageio  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        output_dir = Path(output_dir)
        action_dir = output_dir / f"{name}_action"
        action_dir.mkdir(parents=True, exist_ok=True)
        c2ws = P.build_poses(action, int(num_frames))
        np.save(action_dir / "poses.npy", c2ws)
        np.save(action_dir / "intrinsics.npy", P.intrinsics(len(c2ws)))

        t0 = time.time()
        torch.cuda.reset_peak_memory_stats()
        video = self.pipe.generate(
            prompt or DEFAULT_PROMPT, Image.open(image_path).convert("RGB"), action_path=str(action_dir),
            chunk_size=P.LATENT_CHUNK, max_area=MAX_AREA, frame_num=len(c2ws),
            shift=self.cfg.sample_shift, seed=int(self.args.seed), offload_model=False)
        frames = ((video.clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()
        del video
        out = output_dir / f"{name}.mp4"
        imageio.mimsave(str(out), list(frames), fps=int(self.args.fps))
        dt = time.time() - t0
        print(f"[lingbot] {name}: {len(frames)} frames {frames.shape[2]}x{frames.shape[1]} in {dt:.1f}s "
              f"({len(frames) / dt:.1f} fps), peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)
        return out


run_agent.SanaWMEngine = LingBotWorld2Engine
print(f"[adapter] agent provider: {agent_api.patch(run_agent)}", flush=True)
raise SystemExit(run_agent.main())
