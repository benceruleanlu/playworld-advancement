#!/usr/bin/env python3
"""LingBot-World v2 (causal-fast) runner: upstream closed-loop harness with LingBot swapped in for SANA-WM.

Same argv as run_agent.py. `pwa gen EXP --runner lingbot_world2 ...` (14B) or
`--runner lingbot_world2_1p3b` (1.3B, for cheap iteration).

Default: a persistent session (session.py). The harness calls generate() once per
chunk; when the call is the next chunk of the same task (`<task>_chunk_<NN>`) the
session continues, so LingBot's KV cache (its only memory) spans the whole
closed-loop rollout. Chunk 01, another task or a `<task>_full` (dataset mode) call
resets it. Dataset mode is reset plus one long step.

Stateless A/B baseline: `--lingbot-stateless` (stripped before run_agent parses
argv) or LINGBOT_SESSION=0: every call is a fresh upstream rollout from image_path.

Turn calibration (off by default): `--lingbot-turn-cal` or LINGBOT_TURN_CAL=1 sets the
arrow-key rates so one dataset token turns 22.5 deg (yaw) / 20 deg (pitch); see poses.calibrate.

Caption prompt (off by default): `--lingbot-caption-prompt` or LINGBOT_PROMPT_MODE=auto conditions
the model on the task's scene caption instead of the agent goal ("wait and observe" for Insight);
see adapters/common/prompts.py. The agent player still gets the goal.

Env:
  LINGBOT_ROOT      checkout of Robbyant/lingbot-world-v2 (default /opt/lingbot)
  LINGBOT_WEIGHTS   dir holding lingbot-world-v2-{14b,1.3b}-causal-fast (default /weights/lingbot)
  LINGBOT_VARIANT   14b (default) | 1.3b
  LINGBOT_T5_CPU    1 keeps the 11 GB text encoder off the GPU (default: 1 for 14b, 0 for 1.3b)
  LINGBOT_YAW_RAD / LINGBOT_PITCH_RAD   per-frame camera rotation for arrow keys (poses.py)
  LINGBOT_TURN_CAL  1 = same as --lingbot-turn-cal (overrides the two rates above)
  LINGBOT_UNIT_YAW_DEG / LINGBOT_UNIT_PITCH_DEG / LINGBOT_CHUNK_UNITS   turn-cal angles (22.5 / 20 / 2)
  LINGBOT_PROMPT_MODE  goal (default) | caption | auto (= --lingbot-caption-prompt)
  LINGBOT_SESSION   0 = stateless (same as --lingbot-stateless)
  LINGBOT_STREAM_DECODE  0 = re-decode all latents each step instead of streaming the VAE cache
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from adapters.common import agent_api, prompts  # noqa: E402
from adapters.common.upstream import import_run_agent  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import session as S  # noqa: E402

run_agent = import_run_agent()

STATELESS = "--lingbot-stateless" in sys.argv or os.environ.get("LINGBOT_SESSION", "1") == "0"
TURN_CAL = "--lingbot-turn-cal" in sys.argv or os.environ.get("LINGBOT_TURN_CAL", "0") == "1"
PROMPT_MODE = "auto" if "--lingbot-caption-prompt" in sys.argv else os.environ.get("LINGBOT_PROMPT_MODE", "goal")
if PROMPT_MODE not in prompts.MODES:
    raise SystemExit(f"LINGBOT_PROMPT_MODE must be one of {prompts.MODES}, got {PROMPT_MODE!r}")
sys.argv = [a for a in sys.argv if a not in ("--lingbot-stateless", "--lingbot-turn-cal", "--lingbot-caption-prompt")]

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
        self.session = None
        if not STATELESS:
            self.session = S.LingBotSession(self.pipe, MAX_AREA, self.cfg.sample_shift,
                                            horizon_frames=int(getattr(args, "max_total_frames", 961) or 961))
        self._last_chunk = None
        print(f"[lingbot] mode: {'stateless' if STATELESS else 'session'}"
              + ("" if STATELESS else f" (stream_decode={self.session.stream_decode})")
              + (f", turn-cal {P.UNIT_YAW_DEG}/{P.UNIT_PITCH_DEG} deg per token" if TURN_CAL else "")
              + ("" if PROMPT_MODE == "goal" else f", prompt mode {PROMPT_MODE}"), flush=True)

    def _calibrate(self, name, n_keys):
        """--lingbot-turn-cal: arrow-key rates from dataset token angles (poses.calibrate)."""
        if TURN_CAL:
            P.calibrate(S.parse_chunk_name(name) is None, n_keys,
                        int(getattr(self.args, "action_frame_unit", 20) or 20))

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        if PROMPT_MODE != "goal":
            goal, prompt = prompt, prompts.model_prompt(prompt, name, PROMPT_MODE)
            if (S.parse_chunk_name(name) or (name, 1))[1] == 1:  # once per rollout
                print(f"[lingbot] {name}: prompt mode {PROMPT_MODE}, "
                      f"{'caption' if prompt != goal else 'goal (no caption found)'}: {prompt[:120]!r}", flush=True)
        if self.session is None:
            return self._generate_stateless(image_path, prompt, action, output_dir, name, num_frames)
        return self._generate_session(image_path, prompt, action, output_dir, name, num_frames)

    def _generate_session(self, image_path, prompt, action, output_dir, name, num_frames):
        """Continue (or reset and start) the persistent session; write <output_dir>/<name>.mp4.
        Frame counts follow session.frames_returned (33 -> 29 first, 33 after)."""
        import imageio  # noqa: PLC0415
        import torch  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        parsed = S.parse_chunk_name(name)
        cont = self.session.started and S.is_continuation(self._last_chunk, parsed)
        self._last_chunk = None  # stays None if this call fails, so the next one resets
        n = S.chunks_for(num_frames)
        keys = S.fit_keys(P.parse_action(action), S.keys_needed(n, first=not cont))
        self._calibrate(name, len(keys))
        t0 = time.time()
        torch.cuda.reset_peak_memory_stats()
        if not cont:
            horizon = max(int(num_frames), int(getattr(self.args, "max_total_frames", 961) or 961))
            self.session.reset(Image.open(image_path).convert("RGB"), prompt or DEFAULT_PROMPT,
                               int(self.args.seed), horizon_frames=horizon)
        start = self.session.chunk_id
        frames = self.session.step(keys)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{name}.mp4"
        imageio.mimsave(str(out), list(frames), fps=int(self.args.fps))
        self._last_chunk = parsed
        dt = time.time() - t0
        print(f"[lingbot] {name}: {'continue' if cont else 'reset'} latent chunks {start}->{self.session.chunk_id} "
              f"{len(frames)} frames {frames.shape[2]}x{frames.shape[1]} in {dt:.1f}s ({len(frames) / dt:.1f} fps), "
              f"peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)
        return out

    def _generate_stateless(self, image_path, prompt, action, output_dir, name, num_frames):
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
        self._calibrate(name, P.frame_count(int(num_frames)) - 1)
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
        print(f"[lingbot] {name}: stateless {len(frames)} frames {frames.shape[2]}x{frames.shape[1]} in {dt:.1f}s "
              f"({len(frames) / dt:.1f} fps), peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GiB", flush=True)
        return out


run_agent.SanaWMEngine = LingBotWorld2Engine
prompts.install(run_agent)
print(f"[adapter] agent provider: {agent_api.patch(run_agent)}", flush=True)
raise SystemExit(run_agent.main())
