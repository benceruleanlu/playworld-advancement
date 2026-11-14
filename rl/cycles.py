"""Closed camera cycles for self-verifiable RL on LingBot-World v2 (numpy only).

A cycle is a per-pixel-frame key sequence (poses.py keys: j/l yaw, i/k pitch, none)
whose camera returns to poses it has already visited. Because every key is a pure
rotation here, any two frames whose views overlap are related by an exact homography
(see rewards.py), so the rollout can be scored without ground-truth video.

Frame f's pose is the product of the first f key deltas (frame 0 = identity), the same
accumulation as session.PoseTrack before translation normalisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from adapters.lingbot_world2 import poses as P
from adapters.lingbot_world2.session import FRAMES_PER_CHUNK, keys_needed

OPPOSITE = {"l": "j", "j": "l", "i": "k", "k": "i"}


@dataclass
class Cycle:
    kind: str
    keys: list[str]                       # one key per generated pixel frame (len F-1)
    yaw_rad: float                        # per-frame rates used to build the poses
    pitch_rad: float
    params: dict = field(default_factory=dict)

    @property
    def n_frames(self) -> int:
        return len(self.keys) + 1


def n_keys_for(n_chunks: int) -> int:
    """Keys a first session step of n_chunks consumes (frames = keys + 1)."""
    return keys_needed(n_chunks, first=True)


def _fit(keys: list[str], n: int) -> list[str]:
    """Trim or pad with 'none' to exactly n keys."""
    return list(keys[:n]) + ["none"] * max(0, n - len(keys))


def out_and_back(n_chunks: int, out_frames: int, key: str = "l", hold: int = 0,
                 repeats: int = 1) -> list[str]:
    """Turn `out_frames` with `key`, hold, turn back the same amount; repeat; pad with waits."""
    one = [key] * out_frames + ["none"] * hold + [OPPOSITE[key]] * out_frames
    return _fit(one * repeats, n_keys_for(n_chunks))


def full_turn(n_chunks: int, yaw_rad: float, key: str = "l") -> list[str]:
    """Keep turning one way; frames 2*pi/yaw apart share a pose."""
    return [key] * n_keys_for(n_chunks)


def sample_cycle(rng: np.random.Generator, n_chunks: int = 8,
                 yaw_range=(0.02, 0.04), pitch_rad: float = 0.01,
                 kinds=("out_back", "out_back_hold", "repeat", "full_turn", "pitch_back")) -> Cycle:
    """Random closed rotation cycle that fits n_chunks latent chunks."""
    n = n_keys_for(n_chunks)
    yaw = float(rng.uniform(*yaw_range))
    kind = str(rng.choice(list(kinds)))
    key = str(rng.choice(["l", "j"]))
    if kind == "full_turn":
        # turn ~1.1 full circles so the first frames are revisited inside the rollout
        yaw = float(max(yaw, 2.2 * np.pi / n))
        keys = full_turn(n_chunks, yaw, key)
        params = {"key": key}
    elif kind == "pitch_back":
        pk = str(rng.choice(["i", "k"]))
        out = int(rng.integers(n // 8, n // 4))
        yaw_out = int(rng.integers(n // 6, n // 3))
        keys = _fit([key] * yaw_out + [pk] * out + [OPPOSITE[pk]] * out + [OPPOSITE[key]] * yaw_out, n)
        params = {"key": key, "pitch_key": pk, "yaw_out": yaw_out, "pitch_out": out}
    else:
        repeats = 2 if kind == "repeat" else 1
        hold = int(rng.integers(4, n // 6)) if kind == "out_back_hold" else 0
        out = int(rng.integers(n // 8, (n - hold) // (2 * repeats) + 1))
        keys = out_and_back(n_chunks, out, key, hold, repeats)
        params = {"key": key, "out": out, "hold": hold, "repeats": repeats}
    return Cycle(kind=kind, keys=keys, yaw_rad=yaw, pitch_rad=pitch_rad, params=params)


def frame_rotations(cycle: Cycle) -> np.ndarray:
    """[F, 3, 3] camera-to-world rotations, frame 0 = identity, using poses.key_delta
    with the cycle's yaw/pitch rates (restores the module globals afterwards)."""
    saved = (P.YAW, P.PITCH)
    P.YAW, P.PITCH = cycle.yaw_rad, cycle.pitch_rad
    try:
        cur = np.eye(4)
        out = [cur[:3, :3].copy()]
        for k in cycle.keys:
            d = P.key_delta(k)
            if np.abs(d[:3, 3]).max() > 0:
                raise ValueError(f"cycles must be pure rotations, got translation key {k!r}")
            cur = cur @ d
            out.append(cur[:3, :3].copy())
    finally:
        P.YAW, P.PITCH = saved
    return np.stack(out)


def rotation_angle(Ra: np.ndarray, Rb: np.ndarray) -> np.ndarray:
    """Geodesic angle (rad) between camera rotations, broadcasting over leading dims."""
    R = np.swapaxes(Ra, -1, -2) @ Rb
    c = (np.trace(R, axis1=-2, axis2=-1) - 1.0) / 2.0
    return np.arccos(np.clip(c, -1.0, 1.0))


def revisit_pairs(rots: np.ndarray, min_gap: int, max_angle: float, stride: int = 1,
                  max_pairs: int | None = None, rng: np.random.Generator | None = None) -> np.ndarray:
    """[N, 2] frame pairs (i, j), j - i >= min_gap, whose views differ by at most max_angle
    rad, so they overlap and must agree after the rotation homography. Long gaps test memory
    (content left the KV window and came back); short gaps test control and local stability."""
    F = len(rots)
    idx = np.arange(0, F, stride)
    ang = rotation_angle(rots[idx][:, None], rots[idx][None, :])
    ii, jj = np.nonzero((idx[None, :] - idx[:, None] >= min_gap) & (ang <= max_angle))
    pairs = np.stack([idx[ii], idx[jj]], axis=1) if len(ii) else np.zeros((0, 2), dtype=int)
    if max_pairs is not None and len(pairs) > max_pairs:
        rng = rng or np.random.default_rng(0)
        pairs = pairs[np.sort(rng.choice(len(pairs), max_pairs, replace=False))]
    return pairs


def chunks_for_frames(n_frames: int) -> int:
    """Inverse of the first-step frame count 16n-3."""
    return (n_frames + 3) // FRAMES_PER_CHUNK
