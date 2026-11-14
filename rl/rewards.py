"""Self-verifiable rewards for rotation cycles (numpy + OpenCV, no learned models).

For a camera that only rotates, two frames i, j are related by the exact homography
H_ij = K R_j^T R_i K^-1 (pixels of i -> pixels of j); no depth is needed. A rollout that
follows its commanded rotations and keeps the world fixed makes every overlapping pair
agree after warping. We score:

  local   short gaps (4-8 frames): did the camera turn as commanded, any hard cuts?
          (mean and 10th percentile, so a single snap is not averaged away)
  memory  long gaps (>= min_gap frames, overlapping views): is a revisited view the same
          world as before, after the content left the model's KV window?
  sharp   Laplacian variance relative to the input frame. Used only as a guard,
          min(1, sharp / sharp_floor): it penalises blur but pays nothing for extra
          sharpening (rl-v1, an uncapped term, learned to add bright specks).
  ctrl    exp(-err / 5 deg), err = angle between the rotation measured from ORB matches
          and the commanded one, per 4 frames.

Frames are uint8 [F, H, W, 3] at generation resolution; scoring runs at 1/scale.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from adapters.lingbot_world2 import poses as P
from rl.cycles import revisit_pairs

GAP_BINS = ((4, 8), (9, 24), (25, 48), (49, 96), (97, 10_000))


@dataclass
class RewardConfig:
    scale: int = 4                # score at H/scale x W/scale
    local_gaps: tuple = (4, 8)
    memory_min_gap: int = 49      # > the 48-frame rolling KV window (12 latents)
    max_angle_deg: float = 25.0   # overlap needed for a pair to count
    max_pairs: int = 96
    w_memory: float = 1.0
    w_local: float = 0.5
    w_sharp: float = 0.5
    sharp_floor: float = 0.65     # guard only: min(1, sharp / floor); rl-v1 showed an uncapped term buys specks
    w_ctrl: float = 1.0
    ctrl_deg: float = 5.0         # ctrl = exp(-ctrl_err_deg / ctrl_deg)
    erode: int = 3


def intrinsics_matrix(h: int, w: int) -> np.ndarray:
    """K of the session's camera embedding (poses.INTRINSICS_480P rescaled to h x w)."""
    fx, fy, cx, cy = P.INTRINSICS_480P
    sx, sy = w / 832.0, h / 480.0
    return np.array([[fx * sx, 0, cx * sx], [0, fy * sy, cy * sy], [0, 0, 1]], dtype=np.float64)


def homography(K: np.ndarray, Ri: np.ndarray, Rj: np.ndarray) -> np.ndarray:
    """Maps pixels of view i to view j for camera-to-world rotations Ri, Rj."""
    return K @ Rj.T @ Ri @ np.linalg.inv(K)


def _gray(f: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0


def masked_ssim(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    """Mean SSIM of grayscale float images a, b over mask (Gaussian 7x7 window)."""
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    blur = lambda x: cv2.GaussianBlur(x, (7, 7), 1.5)  # noqa: E731
    mu_a, mu_b = blur(a), blur(b)
    va = blur(a * a) - mu_a ** 2
    vb = blur(b * b) - mu_b ** 2
    cov = blur(a * b) - mu_a * mu_b
    s = ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (va + vb + c2))
    m = mask > 0
    return float(s[m].mean()) if m.any() else float("nan")


def pair_similarity(fi: np.ndarray, fj: np.ndarray, H: np.ndarray, erode: int = 3) -> float:
    """Warp frame i into j and compare the overlap: 0.7 SSIM + 0.3 (1 - L1 colour)."""
    h, w = fj.shape[:2]
    warped = cv2.warpPerspective(fi, H, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    mask = cv2.warpPerspective(np.ones((fi.shape[0], fi.shape[1]), np.uint8), H, (w, h),
                               flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT)
    if erode:
        mask = cv2.erode(mask, np.ones((2 * erode + 1, 2 * erode + 1), np.uint8))
    m = mask > 0
    if m.sum() < 0.2 * h * w:
        return float("nan")
    ssim = masked_ssim(_gray(warped), _gray(fj), mask)
    l1 = float(np.abs(warped[m].astype(np.float32) - fj[m].astype(np.float32)).mean() / 255.0)
    return float(np.clip(0.7 * ssim + 0.3 * (1.0 - l1), 0.0, 1.0))


def _orthonormal(M: np.ndarray) -> np.ndarray:
    U, _, Vt = np.linalg.svd(M)
    R = U @ Vt
    return R if np.linalg.det(R) > 0 else U @ np.diag([1, 1, -1]) @ Vt


def measured_rotations(frames: np.ndarray, K: np.ndarray, step: int = 4, min_inliers: int = 20) -> list:
    """Camera rotation between frames i and i+step from ORB matches + RANSAC homography, read as a pure
    rotation M = K^-1 H K (camera i coords -> camera j coords). None where matching is unreliable.
    Independent of the reward's own warping, so it also checks the reward's camera model."""
    orb = cv2.ORB_create(1500)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    feats = [orb.detectAndCompute(cv2.cvtColor(f, cv2.COLOR_RGB2GRAY), None) for f in frames[::step]]
    Kinv = np.linalg.inv(K)
    out = []
    for (ka, da), (kb, db) in zip(feats[:-1], feats[1:]):
        M = None
        if da is not None and db is not None and len(da) >= min_inliers and len(db) >= min_inliers:
            m = bf.match(da, db)
            if len(m) >= min_inliers:
                pa = np.float32([ka[x.queryIdx].pt for x in m])
                pb = np.float32([kb[x.trainIdx].pt for x in m])
                H, inl = cv2.findHomography(pa, pb, cv2.RANSAC, 3.0)
                if H is not None and inl is not None and inl.sum() >= min_inliers:
                    M = _orthonormal(Kinv @ H @ K)
        out.append(M)
    return out


def control_metrics(frames: np.ndarray, rots: np.ndarray, scale: int = 2, step: int = 4) -> dict:
    """ctrl_err_deg: mean angle between measured and commanded rotation per `step` frames.
    closure_err_deg: angle between the composed measured rotation and the commanded net rotation over
    the whole rollout (None if any step was unmeasurable). valid: fraction of measurable steps."""
    small = downscale(frames, scale)
    K = intrinsics_matrix(frames.shape[1], frames.shape[2])
    K[:2] /= scale
    meas = measured_rotations(small, K, step)
    idx = np.arange(0, len(frames), step)
    errs, net, ok = [], np.eye(3), True
    for (i, j), M in zip(zip(idx[:-1], idx[1:]), meas):
        if M is None:
            ok = False
            continue
        cmd = rots[j].T @ rots[i]
        errs.append(np.degrees(float(np.arccos(np.clip((np.trace(M.T @ cmd) - 1) / 2, -1, 1)))))
        net = M @ net
    closure = None
    if ok and len(meas):
        cmd_net = rots[idx[-1]].T @ rots[0]
        closure = float(np.degrees(np.arccos(np.clip((np.trace(net.T @ cmd_net) - 1) / 2, -1, 1))))
    return {"ctrl_err_deg": float(np.mean(errs)) if errs else None,
            "closure_err_deg": closure, "ctrl_valid": len(errs) / max(len(meas), 1)}


def lap_var(f: np.ndarray) -> float:
    return float(cv2.Laplacian(_gray(f), cv2.CV_32F).var())


def downscale(frames: np.ndarray, s: int) -> np.ndarray:
    if s == 1:
        return frames
    h, w = frames.shape[1] // s, frames.shape[2] // s
    return np.stack([cv2.resize(f, (w, h), interpolation=cv2.INTER_AREA) for f in frames])


def score_pairs(frames: np.ndarray, rots: np.ndarray, pairs: np.ndarray, K: np.ndarray,
                erode: int = 3) -> np.ndarray:
    return np.array([pair_similarity(frames[i], frames[j], homography(K, rots[i], rots[j]), erode)
                     for i, j in pairs], dtype=np.float64)


def cycle_reward(frames: np.ndarray, rots: np.ndarray, cfg: RewardConfig = RewardConfig(),
                 rng: np.random.Generator | None = None) -> dict:
    """Reward and its components for one rollout of a rotation cycle."""
    rng = rng or np.random.default_rng(0)
    assert len(frames) == len(rots), (len(frames), len(rots))
    small = downscale(frames, cfg.scale)
    K = intrinsics_matrix(frames.shape[1], frames.shape[2])
    K[:2] /= cfg.scale
    ang = np.radians(cfg.max_angle_deg)

    lo, hi = cfg.local_gaps
    local_pairs = np.array([(i, i + g) for g in (lo, hi) for i in range(0, len(frames) - g, 2)])
    local = score_pairs(small, rots, local_pairs, K, cfg.erode)
    local = local[np.isfinite(local)]

    mem_pairs = revisit_pairs(rots, cfg.memory_min_gap, ang, stride=2, max_pairs=cfg.max_pairs, rng=rng)
    memory = score_pairs(small, rots, mem_pairs, K, cfg.erode) if len(mem_pairs) else np.zeros(0)
    memory = memory[np.isfinite(memory)]

    base = max(lap_var(small[0]), 1e-6)
    sharp = float(np.mean([min(1.0, lap_var(f) / base) for f in small[1::4]]))

    r_local = 0.5 * float(local.mean()) + 0.5 * float(np.percentile(local, 10)) if len(local) else 0.0
    r_memory = float(memory.mean()) if len(memory) else float("nan")
    cm = control_metrics(frames, rots)
    r_ctrl = (float(np.exp(-cm["ctrl_err_deg"] / cfg.ctrl_deg))
              if cm["ctrl_err_deg"] is not None and cm["ctrl_valid"] >= 0.5 else r_local)
    sharp_guard = min(1.0, sharp / cfg.sharp_floor)
    total = cfg.w_local * r_local + cfg.w_sharp * sharp_guard + cfg.w_ctrl * r_ctrl
    total += cfg.w_memory * (r_memory if np.isfinite(r_memory) else r_local)
    return {"reward": float(total), "local": r_local, "local_min": float(local.min()) if len(local) else 0.0,
            "memory": r_memory, "sharp": sharp, "sharp_guard": sharp_guard, "ctrl": r_ctrl, **cm,
            "n_local": int(len(local)), "n_memory": int(len(memory))}


def gap_curve(frames: np.ndarray, rots: np.ndarray, cfg: RewardConfig = RewardConfig(),
              bins=GAP_BINS) -> dict:
    """Mean pair similarity by time gap, over all overlapping pairs (eval, not reward):
    shows where consistency decays relative to the KV window."""
    small = downscale(frames, cfg.scale)
    K = intrinsics_matrix(frames.shape[1], frames.shape[2])
    K[:2] /= cfg.scale
    pairs = revisit_pairs(rots, bins[0][0], np.radians(cfg.max_angle_deg), stride=2)
    out = {}
    for lo, hi in bins:
        sel = pairs[(pairs[:, 1] - pairs[:, 0] >= lo) & (pairs[:, 1] - pairs[:, 0] <= hi)] if len(pairs) else pairs
        if len(sel) > 64:
            sel = sel[np.linspace(0, len(sel) - 1, 64).astype(int)]
        s = score_pairs(small, rots, sel, K, cfg.erode) if len(sel) else np.zeros(0)
        s = s[np.isfinite(s)]
        out[f"{lo}-{hi}"] = (float(s.mean()) if len(s) else None, int(len(s)))
    return out
