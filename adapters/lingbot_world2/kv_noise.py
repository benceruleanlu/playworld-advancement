"""Noisy KV-cache writes (opt-in, session only): --lingbot-kv-noise [--lingbot-kv-noise-t T].

Upstream (and LingBotSession.step) writes each generated chunk into the self-attention KV cache with one
more DiT forward on the chunk's final x0 at t=0, so the cache treats the 4-step student output as clean
ground truth. With the flag, that write forward for a generated chunk takes
    x_kv = scheduler.add_noise(x0, eps, t_kv),   t = t_kv
instead, where t_kv is the entry of the session scheduler's timestep table closest to T, and eps comes
from a separate torch.Generator seeded from the session seed (seed + SEED_OFFSET). The main noise
generator is never touched, so every denoising input and every returned/decoded x0 stays what the flag-off
run produces; only the cache contents (and so later chunks) change.

Scale: LingBot's FlowUniPCMultistepScheduler sets 1000 int64 timesteps, t = sigma * 1000 with
x_t = (1 - sigma) * x0 + sigma * eps, and the DiT embeds the raw t. add_noise looks t up by exact equality
in that table (no entry raises), so T is snapped: at shift 10 (14B) T=25 -> 29 (sigma 0.029), shift 5
(1.3B) T=25 -> 24 (sigma 0.024). The low end of the table is sparse (9, 19, 29, ... at shift 10).

Chunks that stay clean: chunk 0 of the rollout (latent 0 has mask 1 and the image latent in y), any chunk
holding a latent re-anchored by --lingbot-reanchor, and any chunk whose latents overlap the attention sink
(cid * 4 < sink_size; sink slots are never evicted, so a noised write there would persist for the whole
rollout). At the default sink 6, chunks 0 and 1 stay clean, so a 30-decision rollout of 2-chunk steps
noises 58 of 60 chunks.

Not trained for: the distilled student samples at 4 timesteps, 999/967/908/768 (14B, shift 10) and
999/937/833/624 (1.3B, shift 5), and writes the cache at t=0. t_kv=29 or 24 is a value it never sees at any
forward. T is capped at 250: larger T writes keys of mostly-noise latents.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

FLAG = "--lingbot-kv-noise"
T_ARG = "--lingbot-kv-noise-t"
DEFAULT_T = 25.0
MAX_T = 250.0   # above this the write is mostly noise (sigma > 0.25)
SEED_OFFSET = 7_919  # eps generator seed = session seed + this; keeps it apart from the main noise stream


@dataclass(frozen=True)
class KVNoiseConfig:
    enabled: bool = False
    t: float = DEFAULT_T

    def describe(self) -> str:
        return f"kv-noise t={self.t:g}"


def _t(label: str, raw: str) -> float:
    try:
        v = float(raw)
    except ValueError as exc:
        raise SystemExit(f"{label} must be a number, got {raw!r}") from exc
    if not (math.isfinite(v) and 0 < v <= MAX_T):
        raise SystemExit(f"{label} must be in (0, {MAX_T:g}] (scheduler timestep scale; larger T writes "
                         f"mostly-noise keys), got {raw!r}")
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[KVNoiseConfig, list[str]]:
    """The flag and its knob out of argv (or LINGBOT_KV_NOISE=1 / LINGBOT_KV_NOISE_T), and argv without them."""
    enabled, raw, rest, i = environ.get("LINGBOT_KV_NOISE", "0") == "1", None, [], 0
    while i < len(argv):
        a = argv[i]
        if a == FLAG:
            enabled, i = True, i + 1
        elif a == T_ARG:
            if i + 1 >= len(argv):
                raise SystemExit(f"{T_ARG} needs a value")
            raw, i = argv[i + 1], i + 2
        elif a.startswith(T_ARG + "="):
            raw, i = a[len(T_ARG) + 1:], i + 1
        else:
            rest.append(a)
            i += 1
    env_t = environ.get("LINGBOT_KV_NOISE_T", "").strip()
    t = _t(T_ARG, raw) if raw is not None else (_t("LINGBOT_KV_NOISE_T", env_t) if env_t else DEFAULT_T)
    return KVNoiseConfig(enabled, t), rest


def snap_index(table, t: float) -> int:
    """Index of the entry of `table` (a 1-D sequence of timesteps) closest to t; the first on ties."""
    vals = [float(v) for v in (table.tolist() if hasattr(table, "tolist") else table)]
    if not vals:
        raise ValueError("empty timestep table")
    return min(range(len(vals)), key=lambda i: (abs(vals[i] - t), i))


class KVNoise:
    """Per-session state: the eps generator and the snapped timestep. LingBotSession calls reset() at each
    session reset and kv_input() for each generated chunk's KV write."""

    def __init__(self, cfg: KVNoiseConfig = KVNoiseConfig(enabled=True)):
        self.cfg = cfg
        self.gen = None
        self.t_kv = None   # scheduler timestep tensor (0-dim) used for add_noise and the model's t
        self._logged = None

    def reset(self, scheduler, seed: int, device) -> None:
        import torch  # noqa: PLC0415
        self.gen = torch.Generator(device=device)
        self.gen.manual_seed(int(seed) + SEED_OFFSET)
        i = snap_index(scheduler.timesteps, self.cfg.t)
        self.t_kv = scheduler.timesteps[i]
        snapped = float(self.t_kv)
        if self._logged != snapped:
            sigma = float(scheduler.sigmas[i])
            print(f"[lingbot] kv-noise: t={self.cfg.t:g} -> scheduler timestep {snapped:g} (sigma {sigma:.4f})",
                  flush=True)
            self._logged = snapped

    def kv_input(self, x0, scheduler):
        """(x_kv, t) for the KV-write forward of a generated chunk; x0 itself is not modified."""
        import torch  # noqa: PLC0415
        eps = torch.randn(x0.shape, generator=self.gen, device=x0.device, dtype=x0.dtype)
        return scheduler.add_noise(x0, eps, self.t_kv), self.t_kv
