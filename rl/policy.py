"""LingBot-World v2 1.3B causal-fast as an RL policy (torch; runs on a CUDA GPU).

Rollouts use the team's session (adapters/lingbot_world2/session.py): reset() prepares the
image condition, text context, KV caches and seeded generator; the chunk loop below is the
same computation as LingBotSession.step(), but records every chunk's clean latent x0 and
the relative camera poses so the rollout can be replayed for training.

Training (DiffusionNFT-style, as in WorldCycle) replays a rollout chunk by chunk. Clean
latents rebuild the KV cache exactly as in the rollout (no grad); a few chunks are noised
to one of the four student timesteps and get

    L = r * ||x0+ - x0||^2 + (1 - r) * ||x0- - x0||^2,
    x0+ = (1 - b) * x0_old + b * x0_theta,   x0- = (1 + b) * x0_old - b * x0_theta,

where x0 is the rollout's own clean latent, x0_theta the policy's prediction, x0_old the
same prediction before the update (on-policy: detached), and r in [0, 1] the group-normalised
reward. Good rollouts pull the policy toward their samples, bad ones push it away. Only LoRA
weights train; with lora_B initialised at zero, step 0 is exactly the released model.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np

from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2.session import CHUNK, LingBotSession

LORA_TARGETS = ("self_attn.q", "self_attn.k", "self_attn.v", "self_attn.o",
                "cam_scale_layer", "cam_shift_layer")
MAX_AREA = 480 * 832
LOCAL_ATTN, SINK = 18, 6


def load_pipe(root: str | None = None, weights: str | None = None):
    """Released 1.3B causal-fast pipeline, laid out as in prefetch_lingbot.py."""
    root = root or os.environ.get("LINGBOT_ROOT", "/opt/lingbot")
    weights = Path(weights or os.environ.get("LINGBOT_WEIGHTS", "/weights/lingbot"))
    if root not in sys.path:
        sys.path.insert(0, root)
    import wan  # noqa: PLC0415
    from wan.configs import WAN_CONFIGS  # noqa: PLC0415
    cfg = WAN_CONFIGS["i2v-1.3B"]
    local_rank = int(os.environ.get("LOCAL_RANK", 0))  # WanI2VCausal pins cuda:{device_id}
    pipe = wan.WanI2VCausal(
        config=cfg, checkpoint_dir=str(weights / "lingbot-world-v2-1.3b-causal-fast"), device_id=local_rank, rank=0,
        t5_cpu=False, local_attn_size=LOCAL_ATTN, sink_size=SINK, infer_mode="causal_fast",
        assets_dir=str(weights / "lingbot-world-v2-14b-causal-fast"))
    return pipe, cfg


def add_lora(model, rank: int = 16, alpha: int = 16, targets=LORA_TARGETS):
    """Inject LoRA (fp32 adapters, base frozen). Returns the trainable named parameters."""
    from peft import LoraConfig, inject_adapter_in_model  # noqa: PLC0415
    inject_adapter_in_model(LoraConfig(r=rank, lora_alpha=alpha, target_modules=list(targets),
                                       lora_dropout=0.0), model)
    params = {}
    for n, p in model.named_parameters():
        if "lora_" in n:
            p.data = p.data.float()
            p.requires_grad_(True)
            params[n] = p
        else:
            p.requires_grad_(False)
    if not params:
        raise RuntimeError(f"no LoRA modules matched {targets}")
    return params


def apply_lora_file(model, path: str) -> int:
    """Inject and load a LoRA saved by rl.train (rank and targets read from the file), for
    inference in adapters/lingbot_world2/run.py via LINGBOT_LORA. Returns the rank."""
    from safetensors.torch import load_file  # noqa: PLC0415
    state = load_file(path)
    rank = next(v.shape[0] for k, v in state.items() if ".lora_A." in k)
    targets = sorted({t for t in LORA_TARGETS if any(f".{t}.lora_A." in k for k in state)})
    params = add_lora(model, rank=rank, alpha=rank, targets=targets)
    load_lora_state(params, state)
    for p in params.values():
        p.requires_grad_(False)
    return rank


def lora_state(params: dict) -> dict:
    return {n: p.detach().float().cpu().contiguous() for n, p in params.items()}


def load_lora_state(params: dict, state: dict) -> None:
    missing = set(params) - set(state)
    if missing:
        raise KeyError(f"LoRA state missing {len(missing)} tensors, e.g. {sorted(missing)[:2]}")
    for n, p in params.items():
        p.data.copy_(state[n].to(p.device, p.dtype))


class CyclePolicy:
    def __init__(self, pipe, cfg, lora_params: dict):
        self.pipe, self.cfg, self.lora = pipe, cfg, lora_params
        self.sess = LingBotSession(pipe, MAX_AREA, cfg.sample_shift, horizon_frames=125)

    # -- shared chunk plumbing --------------------------------------------------
    def _kwargs(self, c: int, rel: np.ndarray) -> dict:
        import torch  # noqa: PLC0415
        s = self.sess
        with torch.autocast("cuda", enabled=False):
            emb = s._plucker(rel[c * CHUNK:(c + 1) * CHUNK])
        return {
            "context": [s.context[0]], "seq_len": s.max_seq_len,
            "y": [s.y[:, c * CHUNK:(c + 1) * CHUNK]],
            "dit_cond_dict": {"c2ws_plucker_emb": emb.chunk(1, dim=0)},
            "kv_cache": s.kv, "crossattn_cache": s.cross,
            "current_start": c * CHUNK * s.frame_seqlen,
            "max_attention_size": s.kv_size, "frame_seqlen": s.frame_seqlen,
        }

    def _model(self, x, t, kwargs):
        import torch  # noqa: PLC0415
        first = not self.sess.cross_init
        out = self.pipe.model(x=[x], t=torch.stack([t]).to(self.pipe.device), cross_attn_first_call=first, **kwargs)[0]
        self.sess.cross_init = True
        return out

    def _x0(self, pred, xt, t):
        return self.pipe._convert_flow_pred_to_x0(flow_pred=pred, xt=xt, timestep=t, scheduler=self.pipe.scheduler)

    def _prepare(self, image, prompt: str, keys: list[str], seed: int, yaw: float, pitch: float) -> np.ndarray:
        saved = (P.YAW, P.PITCH)
        P.YAW, P.PITCH = yaw, pitch
        try:
            self.sess.reset(image, prompt, seed, horizon_frames=len(keys) + 1)
            return self.sess.track.advance(keys)
        finally:
            P.YAW, P.PITCH = saved

    # -- rollout ------------------------------------------------------------------
    def rollout(self, image, prompt: str, keys: list[str], seed: int, yaw: float, pitch: float) -> dict:
        """Generate len(keys)+1 frames; returns frames uint8 [F,H,W,3], latents (cpu bf16) and rel poses."""
        import torch  # noqa: PLC0415
        t0 = time.time()
        rel = self._prepare(image, prompt, keys, seed, yaw, pitch)
        s, pipe = self.sess, self.pipe
        ts = s.timesteps
        lats = []
        with torch.amp.autocast("cuda", dtype=pipe.param_dtype), torch.no_grad():
            for c in range(len(rel) // CHUNK):
                kw = self._kwargs(c, rel)
                latent = torch.randn(16, CHUNK, s.lat_h, s.lat_w, dtype=torch.float32, generator=s.gen, device=pipe.device)
                for i in range(len(ts)):
                    x0 = self._x0(self._model(latent, ts[i], kw), latent, ts[i])
                    if i < len(ts) - 1:
                        noise = torch.randn(x0.shape, generator=s.gen, device=x0.device, dtype=x0.dtype)
                        latent = pipe.scheduler.add_noise(x0, noise, ts[i + 1])
                lats.append(x0)
                self._model(x0, ts[-1] * 0.0, kw)  # clean KV write, as upstream
                s.chunk_id += 1
            lat = torch.cat(lats, dim=1)
            video = s._decode(lat)
        frames = ((video.clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8).permute(1, 2, 3, 0).cpu().numpy()
        return {"frames": frames, "latents": lat.to(torch.bfloat16).cpu(), "rel": rel,
                "seconds": time.time() - t0}

    # -- training -----------------------------------------------------------------
    def accumulate_grad(self, image, prompt: str, keys: list[str], seed: int, yaw: float, pitch: float,
                        latents, r: float, train_chunks: list[int], beta: float = 1.0,
                        weight: float = 1.0, gen=None) -> float:
        """Replay one rollout and add weight * NFT loss gradients of train_chunks to the LoRA .grad.
        Returns the (unweighted) mean loss over trained chunks."""
        import torch  # noqa: PLC0415
        rel = self._prepare(image, prompt, keys, seed, yaw, pitch)
        s, pipe = self.sess, self.pipe
        ts = s.timesteps
        lat = latents.to(pipe.device, torch.float32)
        losses = []
        train = set(train_chunks)
        for c in range(len(rel) // CHUNK):
            kw = self._kwargs(c, rel)
            x0 = lat[:, c * CHUNK:(c + 1) * CHUNK]
            if c in train:
                k = int(torch.randint(len(ts), (1,), generator=gen).item()) if gen is not None else int(np.random.randint(len(ts)))
                eps = torch.randn(x0.shape, device=x0.device, dtype=x0.dtype, generator=None)
                xt = pipe.scheduler.add_noise(x0, eps, ts[k])
                with torch.amp.autocast("cuda", dtype=pipe.param_dtype):
                    x0_theta = self._x0(self._model(xt, ts[k], kw), xt, ts[k]).float()
                x0_old = x0_theta.detach()
                pos = (1 - beta) * x0_old + beta * x0_theta
                neg = (1 + beta) * x0_old - beta * x0_theta
                loss = r * (pos - x0).pow(2).mean() + (1 - r) * (neg - x0).pow(2).mean()
                (loss * weight).backward()
                losses.append(float(loss.detach()))
                for d in s.kv:  # drop the graph that the in-place cache writes attached
                    d["k"], d["v"] = d["k"].detach(), d["v"].detach()
            with torch.amp.autocast("cuda", dtype=pipe.param_dtype), torch.no_grad():
                self._model(x0, ts[-1] * 0.0, kw)
            s.chunk_id += 1
        return float(np.mean(losses)) if losses else 0.0
