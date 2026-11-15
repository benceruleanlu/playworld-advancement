"""Ornstein-Uhlenbeck temporally colored + moment-stratified chunk noise (opt-in).
Transforms initial chunk noise `eps` [C, F, H, W] in-place from the session's `torch.randn`
draw (zero extra RNG steps): spatial (H, W) moment stratification per (c, f) slice plus a
stationary AR(1) filter across frames and chunk seams (`prev_last` [C, H, W])."""
from __future__ import annotations
from dataclasses import dataclass
import math, os  # noqa: E401
import numpy as np

FLAG, RHO_FLAG = "--lingbot-ou-noise", "--lingbot-ou-rho"


@dataclass(frozen=True)
class OUNoiseConfig:
    enabled: bool = False
    rho: float = 0.35
    stratify: bool = True
    def describe(self) -> str: return f"ou-noise on (rho={self.rho:g}, stratify={'on' if self.stratify else 'off'})"


def _parse_rho(label: str, raw: str) -> float:
    try: v = float(raw)  # noqa: E701
    except ValueError as exc: raise SystemExit(f"{label} must be a float in [0, 1), got {raw!r}") from exc  # noqa: E701
    if not (0.0 <= v < 1.0): raise SystemExit(f"{label} must satisfy 0.0 <= rho < 1.0, got {raw!r}")  # noqa: E701
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[OUNoiseConfig, list[str]]:
    enabled, rho_raw, rest, i = environ.get("LINGBOT_OU_NOISE", "0") == "1", None, [], 0
    while i < len(argv):
        if (a := argv[i]) == FLAG: enabled, i = True, i + 1  # noqa: E701
        elif a == RHO_FLAG:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"): raise SystemExit(f"{RHO_FLAG} needs a float value in [0, 1)")  # noqa: E701
            rho_raw, i = argv[i + 1], i + 2
        elif a.startswith(RHO_FLAG + "="): rho_raw, i = a.split("=", 1)[1], i + 1  # noqa: E701
        else: rest.append(a); i += 1  # noqa: E701,E702
    eraw, sraw = environ.get("LINGBOT_OU_RHO", "").strip(), environ.get("LINGBOT_OU_STRATIFY", "1").strip()
    if sraw not in ("", "0", "1"): raise SystemExit(f"LINGBOT_OU_STRATIFY must be 0 or 1, got {sraw!r}")  # noqa: E701
    rho = _parse_rho(RHO_FLAG, rho_raw) if rho_raw is not None else (0.35 if eraw == "" else _parse_rho("LINGBOT_OU_RHO", eraw))
    return OUNoiseConfig(enabled=enabled, rho=rho, stratify=sraw != "0"), rest


class OUNoiseFilter:
    def __init__(self, cfg: OUNoiseConfig = OUNoiseConfig(enabled=True)): self.cfg, self.prev_last = cfg, None
    def reset(self) -> None: self.prev_last = None

    def apply(self, eps):
        if len(eps.shape) != 4 or any(d <= 0 for d in eps.shape):
            raise ValueError(f"expected nonempty [C, F, H, W] noise, got {eps.shape}")
        c, f, h, w = eps.shape
        if self.cfg.stratify:
            eps -= eps.reshape(c, f, h * w).mean(-1).reshape(c, f, 1, 1)
            var = (eps * eps).reshape(c, f, h * w).mean(-1).reshape(c, f, 1, 1)
            eps /= var.sqrt().clamp_min(1e-6) if hasattr(var, "clamp_min") else np.maximum(np.sqrt(var), 1e-6)
        if (rho := self.cfg.rho) > 0.0:
            alpha = math.sqrt(1.0 - rho * rho)
            if self.prev_last is not None and self.prev_last.shape == eps[:, 0].shape:
                eps[:, 0] = rho * self.prev_last + alpha * eps[:, 0]
            for t in range(1, f): eps[:, t] = rho * eps[:, t - 1] + alpha * eps[:, t]  # noqa: E701
        last = eps[:, -1]
        self.prev_last = last.detach().clone() if hasattr(last, "detach") else last.copy()
        return eps
