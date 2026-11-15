"""Opt-in yaw gain (off by default): scale the per-frame yaw the engine sends to the model (numpy-free).

`--lingbot-yaw-gain G` (env LINGBOT_YAW_GAIN) multiplies the LEFT (j) and RIGHT (l) rotation of every
pixel-frame pose delta given to LingBot by G; `--lingbot-yaw-gain-left GL` / `--lingbot-yaw-gain-right GR`
(LINGBOT_YAW_GAIN_LEFT / _RIGHT) set one direction and default to G. Each value is in [0.5, 2.0]. Pitch and
translation are untouched. Requires turn calibration: the gain corrects a calibrated angle the model
renders too small or too large.

Only the poses sent to the model change. The intended camera track (the world angle the dataset token or
player action means) stays as commanded: session.PoseTrack keeps it beside the model track and gives it to
ReturnDetector (re-anchor), and player hint, return stop, measured turn and the scripted player replay
poses.key_delta without the gain. So "turned 360" and "back at the start" mean the intended angle, which
the gain is meant to make the video match.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

FLAG, LEFT, RIGHT = "--lingbot-yaw-gain", "--lingbot-yaw-gain-left", "--lingbot-yaw-gain-right"
ENV = {FLAG: "LINGBOT_YAW_GAIN", LEFT: "LINGBOT_YAW_GAIN_LEFT", RIGHT: "LINGBOT_YAW_GAIN_RIGHT"}
LO, HI = 0.5, 2.0
TURN_KEYS = frozenset("jl")


@dataclass(frozen=True)
class YawGain:
    enabled: bool = False
    left: float = 1.0
    right: float = 1.0

    def pair(self) -> tuple[float, float] | None:
        """(left, right) for poses.key_delta, or None when off (the call is then main's)."""
        return (self.left, self.right) if self.enabled else None

    def tag(self) -> str:
        return f"{self.left:g}" if self.left == self.right else f"{self.left:g}/{self.right:g}"

    def describe(self) -> str:
        return (f"yaw gain {self.left:g}" if self.left == self.right
                else f"yaw gain left {self.left:g} right {self.right:g}")


def _value(label: str, raw: str) -> float:
    try:
        v = float(raw)
    except ValueError:
        raise SystemExit(f"{label} needs a number, got {raw!r}") from None
    if not (math.isfinite(v) and LO <= v <= HI):
        raise SystemExit(f"{label} must be between {LO:g} and {HI:g}, got {raw!r}")
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[YawGain, list[str]]:
    """The yaw gain flags (or env) in argv, and argv without them."""
    seen, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        key = next((k for k in ENV if a == k or a.startswith(k + "=")), None)
        if key is None:
            rest.append(a)
            i += 1
        elif a == key:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{key} needs a value")
            seen[key], i = argv[i + 1], i + 2
        else:
            seen[key], i = a[len(key) + 1:], i + 1
    raw = {}
    for k, env in ENV.items():
        if k in seen:
            raw[k] = _value(k, seen[k])
        elif environ.get(env, "").strip():
            raw[k] = _value(env, environ[env].strip())
    if not raw:
        return YawGain(), rest
    g = raw.get(FLAG, 1.0)
    return YawGain(True, raw.get(LEFT, g), raw.get(RIGHT, g)), rest


def yaw_frames(keys) -> int:
    """Pixel-frame deltas whose yaw the gain scales (any key combo with j or l)."""
    return sum(bool(set(str(k).lower().split("+")) & TURN_KEYS) for k in keys)
