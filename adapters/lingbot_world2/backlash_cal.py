"""Feedforward KV-backlash reversal compensation (opt-in; pure Python + numpy).
Boosts only the post-reversal camera rotation transient by `1 + boost * exp(-k / tau)`."""
from __future__ import annotations
import math
import os
from dataclasses import dataclass
import numpy as np
from adapters.lingbot_world2 import poses as P

FLAG, BOOST_FLAG = "--lingbot-backlash-cal", "--lingbot-backlash-boost"
_ROT = {"j": lambda s: P._rot_y(-P.YAW * s), "l": lambda s: P._rot_y(P.YAW * s),
        "i": lambda s: P._rot_x(P.PITCH * s), "k": lambda s: P._rot_x(-P.PITCH * s)}

@dataclass(frozen=True)
class BacklashConfig:
    enabled: bool = False
    boost: float = 0.22
    tau_frames: float = 16.0
    min_run_frames: int = 8
    def describe(self) -> str:
        return f"backlash-cal on (boost={self.boost:g}, tau={self.tau_frames:g}, min_run={self.min_run_frames})"

def _num(label: str, raw: str, typ, strict_pos: bool = False):
    try:
        v = typ(raw)
    except ValueError as exc:
        raise SystemExit(f"{label} must be a {typ.__name__}, got {raw!r}") from exc
    if not math.isfinite(v) or (v <= 0 if strict_pos else v < 0):
        raise SystemExit(f"{label} must be >{'' if strict_pos else '='} 0, got {raw!r}")
    return v

def parse(argv: list[str], environ=os.environ) -> tuple[BacklashConfig, list[str]]:
    on, raw, rest, i = environ.get("LINGBOT_BACKLASH_CAL", "0") == "1", None, [], 0
    while i < len(argv):
        if (a := argv[i]) == FLAG:
            on, i = True, i + 1
        elif a == BOOST_FLAG:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{BOOST_FLAG} needs a float value")
            raw, i = argv[i + 1], i + 2
        elif a.startswith(BOOST_FLAG + "="):
            raw, i = a[len(BOOST_FLAG) + 1:], i + 1
        else:
            rest.append(a)
            i += 1
    eb, et, em = (environ.get(k, "").strip() for k in ("LINGBOT_BACKLASH_BOOST", "LINGBOT_BACKLASH_TAU", "LINGBOT_BACKLASH_MIN_RUN"))
    boost = _num(BOOST_FLAG, raw, float) if raw is not None else (0.22 if not eb else _num("LINGBOT_BACKLASH_BOOST", eb, float))
    return BacklashConfig(on, boost, 16.0 if not et else _num("LINGBOT_BACKLASH_TAU", et, float, True),
                          8 if not em else _num("LINGBOT_BACKLASH_MIN_RUN", em, int, True)), rest

class BacklashTracker:
    def __init__(self, cfg: BacklashConfig = BacklashConfig(enabled=True)):
        self.cfg, self.reversals, self.boosted_frames = cfg, 0, 0
        self._axes: list[list] = [[0, 0, None], [0, 0, None]]  # [sign, run_frames, rev_k] for yaw, pitch

    def _axis(self, idx: int, s: int) -> float:
        ax = self._axes[idx]
        if not self.cfg.enabled or s == 0:
            ax[2] = ax[2] + 1 if (self.cfg.enabled and ax[2] is not None) else ax[2]
            return 1.0
        if s == ax[0]:
            ax[1] += 1
        else:
            ax[2] = 0 if (ax[0] != 0 and ax[1] >= self.cfg.min_run_frames) else None
            self.reversals += ax[2] == 0
            ax[0], ax[1] = s, 1
        if ax[2] is None:
            return 1.0
        ax[2] += 1
        return 1.0 + self.cfg.boost * math.exp(-(ax[2] - 1) / self.cfg.tau_frames)
    def step(self, key: str) -> tuple[float, float]:
        parts = key.lower().split("+")
        dy, dp = parts.count("l") - parts.count("j"), parts.count("i") - parts.count("k")
        ys, ps = self._axis(0, (dy > 0) - (dy < 0)), self._axis(1, (dp > 0) - (dp < 0))
        self.boosted_frames += ys > 1.001 or ps > 1.001
        return ys, ps
    def delta(self, key: str, translation_gain: float = 1.0, rotation_scale: float = 1.0,
              yaw_gain: tuple[float, float] | None = None) -> np.ndarray:
        ys, ps = self.step(key)
        if ys == ps:
            return P.key_delta(key, translation_gain, rotation_scale * ys, yaw_gain=yaw_gain)
        d = P.key_delta(key, translation_gain, 0.0)
        for k in (t for t in key.lower().split("+") if t in _ROT):
            g = (yaw_gain[0] if k == "j" else yaw_gain[1] if k == "l" else 1.0) if yaw_gain else 1.0
            d[:3, :3] = d[:3, :3] @ _ROT[k](rotation_scale * g * (ys if k in ("j", "l") else ps))
        return d
