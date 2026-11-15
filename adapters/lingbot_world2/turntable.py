"""Opt-in world-up turntable camera poses and dataset-rescale calibration (numpy only, no torch import).

`poses.py` composes per-frame camera deltas in the local camera frame (`cur = cur @ key_delta(k)`): pitching up or
down and then panning left or right rotates around the tilted camera y-axis, rolling the horizon ("Dutch tilt")
and preventing closed pan/tilt prompt loops (e.g. `u*2, →*4, d*2, ←*4`) from returning to the identity pose.
Walking forward (`w`) while tilted also lifts or sinks `c2w[1, 3]` off the ground plane.

`--lingbot-turntable-poses` (`LINGBOT_TURNTABLE_POSES=1`) tracks world yaw, camera pitch (clamped to +/-85 deg)
and world position explicitly, with orientation `R = _rot_y(yaw) @ _rot_x(pitch)`. Camera right is
`[cos(yaw), 0, -sin(yaw)]^T`, so horizon roll is identically zero for every `(yaw, pitch)`, pan/tilt loops commute
back to the exact start pose, and when `pitch == 0` throughout a trajectory both walk modes match `poses.py` to
floating-point precision (`1e-14`), including combined keys (`w+j`) and `--lingbot-yaw-gain`.

Knobs:
  * `--lingbot-turntable-walk ground|free` (`LINGBOT_TURNTABLE_WALK`, default `ground`): `ground` translates in
    the horizontal heading frame `_rot_y(yaw_before) @ dt` (`pos[1] == 0`); `free` translates along the pitched
    camera axes `(_rot_y(yaw_before) @ _rot_x(pitch_before)) @ dt`.
  * `--lingbot-turntable-rescale` (`LINGBOT_TURNTABLE_RESCALE=1`, requires `--lingbot-turntable-poses` and
    `--lingbot-turn-cal`): when upstream's dataset frame budget compresses a script's active frames below
    `tokens * action_frame_unit`, `effective_frame_unit` scales `action_frame_unit` down to
    `active_keys / total_tokens` so calibrated dataset turns still cover their full prompt angles.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import numpy as np

from adapters.lingbot_world2 import poses as P

FLAG = "--lingbot-turntable-poses"
WALK_FLAG = "--lingbot-turntable-walk"
RESCALE_FLAG = "--lingbot-turntable-rescale"
WALKS = ("ground", "free")
DEFAULT_MAX_PITCH = math.radians(85.0)
ACTIVE_KEYS = frozenset("wsadijkl")


@dataclass(frozen=True)
class TurntableConfig:
    enabled: bool = False
    walk: str = "ground"
    rescale: bool = False

    def describe(self) -> str:
        return f"walk={self.walk}" + (", rescale" if self.rescale else "")


def _walk_value(label: str, raw: str) -> str:
    val = raw.strip()
    if val not in WALKS:
        raise SystemExit(f"{label} must be one of {WALKS}, got {raw!r}")
    return val


def parse(argv: list[str], environ=os.environ) -> tuple[TurntableConfig, list[str]]:
    """Parse turntable flags (or env vars) from argv, returning `(TurntableConfig, remaining_argv)`.

    `--lingbot-turntable-walk` is validated even when `--lingbot-turntable-poses` is absent, leaving `enabled`
    False (matching `pose_memory.parse`). `--lingbot-turntable-rescale` sets `rescale=True` so `run.configure`
    can reject it when `--lingbot-turntable-poses` or `--lingbot-turn-cal` is off."""
    enabled = environ.get("LINGBOT_TURNTABLE_POSES", "0") == "1"
    rescale = environ.get("LINGBOT_TURNTABLE_RESCALE", "0") == "1"
    seen_walk: str | None = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == FLAG:
            enabled, i = True, i + 1
        elif a == RESCALE_FLAG:
            rescale, i = True, i + 1
        elif a == WALK_FLAG:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{WALK_FLAG} needs a value")
            seen_walk, i = argv[i + 1], i + 2
        elif a.startswith(WALK_FLAG + "="):
            seen_walk, i = a[len(WALK_FLAG) + 1:], i + 1
        else:
            rest.append(a)
            i += 1
    env_walk = environ.get("LINGBOT_TURNTABLE_WALK", "").strip()
    if seen_walk is not None:
        walk = _walk_value(WALK_FLAG, seen_walk)
    elif env_walk:
        walk = _walk_value("LINGBOT_TURNTABLE_WALK", env_walk)
    else:
        walk = "ground"
    return TurntableConfig(enabled=enabled, walk=walk, rescale=rescale), rest


def rotation(yaw: float, pitch: float) -> np.ndarray:
    """3x3 float64 world-up turntable rotation: world yaw then camera pitch (zero horizon roll)."""
    return P._rot_y(yaw) @ P._rot_x(pitch)


@dataclass
class TurntableState:
    """Mutable world-up turntable SE(3) camera state across pixel frames."""

    yaw: float = 0.0
    pitch: float = 0.0
    pos: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float64))
    max_pitch: float = DEFAULT_MAX_PITCH

    def __post_init__(self) -> None:
        self.pos = np.array(self.pos, dtype=np.float64, copy=True)

    @property
    def rotation(self) -> np.ndarray:
        return rotation(self.yaw, self.pitch)

    def c2w(self) -> np.ndarray:
        out = np.eye(4, dtype=np.float64)
        out[:3, :3] = rotation(self.yaw, self.pitch)
        out[:3, 3] = self.pos
        return out

    def step(
        self,
        key: str,
        yaw_rate: float,
        pitch_rate: float,
        translation_gain: float = 1.0,
        rotation_scale: float = 1.0,
        yaw_gain: tuple[float, float] | None = None,
        walk: str = "ground",
    ) -> np.ndarray:
        """Advance one pixel frame under `key` and return the new 4x4 float64 c2w matrix."""
        dt = np.zeros(3, dtype=np.float64)
        dyaw = 0.0
        dpitch = 0.0
        for k in key.lower().split("+"):
            if k == "w":
                dt[2] += 1.0
            elif k == "s":
                dt[2] -= 1.0
            elif k == "a":
                dt[0] -= 1.0
            elif k == "d":
                dt[0] += 1.0
            elif k == "j":
                dyaw -= yaw_rate * rotation_scale * (yaw_gain[0] if yaw_gain else 1.0)
            elif k == "l":
                dyaw += yaw_rate * rotation_scale * (yaw_gain[1] if yaw_gain else 1.0)
            elif k == "i":
                dpitch += pitch_rate * rotation_scale
            elif k == "k":
                dpitch -= pitch_rate * rotation_scale
        dt *= translation_gain

        yaw_before, pitch_before = self.yaw, self.pitch
        if walk == "ground":
            self.pos = self.pos + (P._rot_y(yaw_before) @ dt)
        elif walk == "free":
            self.pos = self.pos + (rotation(yaw_before, pitch_before) @ dt)
        else:
            raise ValueError(f"walk must be one of {WALKS}, got {walk!r}")

        self.yaw = yaw_before + dyaw
        self.pitch = max(-self.max_pitch, min(self.max_pitch, pitch_before + dpitch))
        return self.c2w()


def active_frames(keys) -> int:
    """Pixel-frame deltas with any rotation or translation key (w/s/a/d/i/j/k/l)."""
    return sum(bool(set(str(k).lower().split("+")) & ACTIVE_KEYS) for k in keys)


def effective_frame_unit(
    task: dict | None,
    action_str: str | None,
    nominal_unit: float,
    tail_frames: int = 50,
    parse_segments=None,
) -> float:
    """Dataset-mode frames per token after upstream frame-budget compression.

    When upstream `build_full_sana_action` compresses a script's active frames below `total_tokens * nominal_unit`,
    returns `active_keys / total_tokens`; otherwise returns `float(nominal_unit)`."""
    nominal = float(nominal_unit)
    if not isinstance(task, dict) or not task.get("action") or not action_str:
        return nominal
    keys = P.parse_action(action_str)
    if not keys or not any(k != "none" for k in keys):
        return nominal
    if parse_segments is None:
        from adapters.common.upstream import import_run_agent  # noqa: PLC0415
        parse_segments = import_run_agent().parse_segments
    total_tokens = sum(int(count) for _, count in parse_segments(task))
    strip = 0
    limit = min(max(0, int(tail_frames)), len(keys))
    while strip < limit and keys[-1 - strip] == "none":
        strip += 1
    active_keys = len(keys) - strip
    if total_tokens > 0 and 0 < active_keys < total_tokens * nominal:
        return active_keys / total_tokens
    return nominal
