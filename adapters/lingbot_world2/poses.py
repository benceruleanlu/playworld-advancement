"""PlayWorld action strings -> LingBot-World v2 camera poses (numpy only).

LingBot-World v2's released causal-fast path is conditioned on camera poses
(poses.npy, OpenCV camera-to-world, one per pixel frame); its WASD/IJKL files
are never read. So each key becomes a per-frame camera delta in the camera
frame (x right, y down, z forward).

Translation scale is arbitrary: the pipeline divides translations by the max
per-latent-frame norm of the sequence. Rotation is in raw radians; defaults
approximate the rates measured in upstream examples/00-02 (J/L 0.02-0.05
rad/frame, K ~0.014). Signs were checked against those examples.
"""
from __future__ import annotations

import math
import os

import numpy as np


def reset(environ=os.environ) -> None:
    """Rotation rates and turn-cal angles from the env (their import-time values). calibrate() overwrites
    YAW/PITCH, so a process that runs several arms calls this before each one."""
    global YAW, PITCH, UNIT_YAW_DEG, UNIT_PITCH_DEG, CHUNK_UNITS, CHUNK_YAW_DEG
    YAW = float(environ.get("LINGBOT_YAW_RAD", "0.03"))
    PITCH = float(environ.get("LINGBOT_PITCH_RAD", "0.01"))
    # Turn calibration (off by default; run.py --lingbot-turn-cal). PlayWorld dataset tokens are
    # fixed angles: "→*4" is "turn right 90 degrees", "→*16" a full turn, "u*2" "look up 40 degrees".
    UNIT_YAW_DEG = float(environ.get("LINGBOT_UNIT_YAW_DEG", "22.5"))
    UNIT_PITCH_DEG = float(environ.get("LINGBOT_UNIT_PITCH_DEG", "20"))
    CHUNK_UNITS = float(environ.get("LINGBOT_CHUNK_UNITS", "2"))  # tokens one closed-loop chunk stands for
    # Turn step (off by default; run.py --lingbot-turn-step DEG): yaw degrees of one closed-loop chunk,
    # in place of CHUNK_UNITS x UNIT_YAW_DEG. Pitch and dataset mode keep the turn-cal values. 0 = unset.
    CHUNK_YAW_DEG = float(environ.get("LINGBOT_TURN_STEP_DEG") or 0)


YAW = PITCH = UNIT_YAW_DEG = UNIT_PITCH_DEG = CHUNK_UNITS = CHUNK_YAW_DEG = 0.0
reset()

LATENT_CHUNK = 4  # generate.py --chunk_size default; latent frames per causal chunk
# examples/*/intrinsics.npy row 0 (fx, fy, cx, cy) at 480x832; the pipeline rescales it.
INTRINSICS_480P = (502.9116, 503.10812, 415.77786, 239.77779)


def _rot_y(t: float) -> np.ndarray:
    c, s = math.cos(t), math.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rot_x(t: float) -> np.ndarray:
    c, s = math.cos(t), math.sin(t)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def calibrate(dataset: bool, n_keys: int, action_frame_unit: float = 20) -> tuple[float, float]:
    """Set YAW/PITCH (rad per pixel frame) so one dataset token turns UNIT_*_DEG.

    Dataset mode: the harness holds each token for action_frame_unit frames.
    Closed loop: the call's n_keys frames of one key stand for CHUNK_UNITS tokens
    (default 45 degrees of yaw per chunk, so 90/180/360 are whole chunks)."""
    global YAW, PITCH
    frames = float(action_frame_unit) if dataset else n_keys / CHUNK_UNITS
    if frames <= 0:
        raise ValueError(f"cannot calibrate turns over {frames} frames per token")
    YAW, PITCH = math.radians(UNIT_YAW_DEG) / frames, math.radians(UNIT_PITCH_DEG) / frames
    if CHUNK_YAW_DEG and not dataset:
        YAW = math.radians(CHUNK_YAW_DEG) / n_keys
    return YAW, PITCH


def key_delta(key: str, translation_gain: float = 1.0, rotation_scale: float = 1.0,
              yaw_gain: tuple[float, float] | None = None) -> np.ndarray:
    """4x4 camera-frame delta for one pixel frame. '+' combines keys, e.g. 'w+j'.
    yaw_gain (left, right): --lingbot-yaw-gain, multiplies j / l rotation (None = off; yaw_gain.py)."""
    d = np.eye(4)
    for k in key.lower().split("+"):
        if k == "w":
            d[2, 3] += 1.0
        elif k == "s":
            d[2, 3] -= 1.0
        elif k == "a":
            d[0, 3] -= 1.0
        elif k == "d":
            d[0, 3] += 1.0
        elif k == "j":  # look left
            d[:3, :3] = d[:3, :3] @ _rot_y(-YAW * rotation_scale * (yaw_gain[0] if yaw_gain else 1.0))
        elif k == "l":  # look right
            d[:3, :3] = d[:3, :3] @ _rot_y(YAW * rotation_scale * (yaw_gain[1] if yaw_gain else 1.0))
        elif k == "i":  # look up
            d[:3, :3] = d[:3, :3] @ _rot_x(PITCH * rotation_scale)
        elif k == "k":  # look down
            d[:3, :3] = d[:3, :3] @ _rot_x(-PITCH * rotation_scale)
        # anything else ("none") is a wait: identity
    d[:3, 3] *= translation_gain
    return d


def parse_action(action: str) -> list[str]:
    """'w-33,none-20' -> one key per generated frame (the frames after the first)."""
    keys: list[str] = []
    for seg in (action or "").split(","):
        seg = seg.strip()
        if not seg:
            continue
        key, _, n = seg.rpartition("-")
        keys += [key or "none"] * max(0, int(n))
    return keys


def frame_count(n_frames: int) -> int:
    """Smallest frame count >= n_frames the pipeline keeps whole: 4n+1 pixel
    frames whose latent length is a multiple of LATENT_CHUNK (it rounds down)."""
    lat = math.ceil(max(n_frames - 1, 1) / 4) + 1
    lat = math.ceil(lat / LATENT_CHUNK) * LATENT_CHUNK
    return (lat - 1) * 4 + 1


def build_poses(action: str, num_frames: int, yaw_gain: tuple[float, float] | None = None,
                turntable=None) -> np.ndarray:
    """float32 [F, 4, 4] camera-to-world poses; F = frame_count(num_frames).

    num_frames is the budget, as in the upstream harness (closed loop passes
    "w-29" with num_frames=29): deltas past it are dropped. Frames past the
    action string repeat its last key so padding does not freeze the camera. yaw_gain: see key_delta."""
    keys = parse_action(action)
    total = frame_count(num_frames if num_frames > 0 else len(keys) + 1)
    keys += [keys[-1] if keys else "none"] * (total - 1 - len(keys))
    poses = [np.eye(4)]
    if turntable is not None and turntable.enabled:
        from adapters.lingbot_world2.turntable import TurntableState  # noqa: PLC0415
        st = TurntableState()
        for k in keys[: total - 1]:
            poses.append(st.step(k, YAW, PITCH, yaw_gain=yaw_gain, walk=turntable.walk))
    else:
        for k in keys[: total - 1]:
            poses.append(poses[-1] @ key_delta(k, yaw_gain=yaw_gain))
    return np.stack(poses).astype(np.float32)


def intrinsics(num_frames: int) -> np.ndarray:
    return np.tile(np.array(INTRINSICS_480P, dtype=np.float32), (num_frames, 1))
