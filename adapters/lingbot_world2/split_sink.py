"""Pose-compensated spatial foreground/background split sink-key scaling (opt-in, session only; numpy only).

`--lingbot-split-sink` (`LINGBOT_SPLIT_SINK=1`) separates the `sink_size * frame_seqlen` attention-sink tokens into
dynamic foreground patches and static background patches:
1. During the opening sink chunks (`cid * CHUNK < sink_size`), the clean `x0` latents `[C, S, lat_h, lat_w]` and
   camera-to-world poses `[S, 4, 4]` are recorded on the host.
2. Once all `S = sink_size` latents are written, each sink latent `z_l` (`l = 1 .. S - 1`) is warped back into
   latent `0`'s camera frame via the inverse rotational homography `d_l = R_l^T R_0 d_0` using latent-grid intrinsics
   scaled from `poses.INTRINSICS_480P` and bilinear interpolation over valid projected rays (`d_{l,z} > 1e-4` inside
   `[0, lat_h - 1] x [0, lat_w - 1]`). Rigid camera pans cancel on static background while independently moving or
   evolving foreground subjects keep a large L2 residual `||z_l^warped - z_0||_2`.
3. The mean residual map is `2x2` max-pooled to DiT patch resolution `(ph, pw) = (lat_h // 2, lat_w // 2)`. When
   `max(residual) <= 1e-6`, every sink token gets `bg_scale` (`fg_token_count = 0`). Otherwise the top
   `k = max(1, round(fg_frac * frame_seqlen))` frame-0 patches (above `1e-6`) are marked foreground and projected into
   each sink latent `l = 0 .. S - 1` via `d_0 = R_0^T R_l d_l` (nearest-neighbor lookup on patch centers), giving a
   flat float32 vector of length `S * frame_seqlen` with `fg_scale` on foreground tokens and `bg_scale` on background.
4. On denoising forwards of active chunks (`chunk_id >= after` and `chunk_id * CHUNK >= sink_size`), cached sink keys
   `blk['k'][:, :n_tokens]` are multiplied by `scales[None, :, None, None]` and restored from an exact copy before the
   clean `t=0` KV write (and on exceptions).
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

import numpy as np

from adapters.lingbot_world2 import poses as P

FLAG = "--lingbot-split-sink"
DEFAULT_FG_SCALE = 0.25
DEFAULT_BG_SCALE = 1.0
DEFAULT_FG_FRAC = 0.25
DEFAULT_AFTER = 4
DEFAULT_TASKS = "OE"
RESIDUAL_EPS = 1e-6
MIN_DEPTH = 1e-4

_ARGS = {
    "--lingbot-split-sink-fg-scale": ("fg_scale", "LINGBOT_SPLIT_SINK_FG_SCALE"),
    "--lingbot-split-sink-bg-scale": ("bg_scale", "LINGBOT_SPLIT_SINK_BG_SCALE"),
    "--lingbot-split-sink-fg-frac": ("fg_frac", "LINGBOT_SPLIT_SINK_FG_FRAC"),
    "--lingbot-split-sink-after": ("after", "LINGBOT_SPLIT_SINK_AFTER"),
    "--lingbot-split-sink-tasks": ("tasks", "LINGBOT_SPLIT_SINK_TASKS"),
}


@dataclass(frozen=True)
class SplitSinkConfig:
    enabled: bool = False
    fg_scale: float = DEFAULT_FG_SCALE
    bg_scale: float = DEFAULT_BG_SCALE
    fg_frac: float = DEFAULT_FG_FRAC
    after: int = DEFAULT_AFTER
    tasks: str = DEFAULT_TASKS

    def applies(self, name: str) -> bool:
        """True when this call name (e.g. 'OE047_chunk_01') matches --lingbot-split-sink-tasks."""
        return self.enabled and re.match(self.tasks, name or "") is not None

    def describe(self) -> str:
        return (f"split sink fg {self.fg_scale:g} bg {self.bg_scale:g} frac {self.fg_frac:g} "
                f"from chunk {self.after} tasks {self.tasks!r}")


def _take(argv: list[str]) -> tuple[dict, list[str]]:
    seen, rest, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        key = next((k for k in _ARGS if a == k or a.startswith(k + "=")), None)
        if key is None:
            rest.append(a)
            i += 1
        elif a == key:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise SystemExit(f"{key} needs a value")
            seen[key], i = argv[i + 1], i + 2
        else:
            seen[key], i = a[len(key) + 1:], i + 1
    return seen, rest


def _parse_float_open_closed(name: str, raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        val = float(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number in (0, 1], got {raw!r}") from None
    if not math.isfinite(val) or not 0.0 < val <= 1.0:
        raise SystemExit(f"{name} must be in (0, 1], got {raw!r}")
    return val


def _parse_float_open(name: str, raw: str | None, default: float) -> float:
    if raw is None:
        return default
    try:
        val = float(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a number in (0, 1), got {raw!r}") from None
    if not math.isfinite(val) or not 0.0 < val < 1.0:
        raise SystemExit(f"{name} must be in (0, 1), got {raw!r}")
    return val


def parse(argv: list[str], environ=os.environ) -> tuple[SplitSinkConfig, list[str]]:
    """Parse --lingbot-split-sink and its knobs out of argv (last value wins; env vars as fallback).
    Knobs given without the main flag are validated and stripped while leaving enabled=False."""
    enabled = FLAG in argv or environ.get("LINGBOT_SPLIT_SINK", "0") == "1"
    argv = [a for a in argv if a != FLAG]
    seen, rest = _take(argv)
    raw = {f: seen.get(arg, environ.get(env, "").strip() or None) for arg, (f, env) in _ARGS.items()}
    fg_scale = _parse_float_open_closed("--lingbot-split-sink-fg-scale", raw["fg_scale"], DEFAULT_FG_SCALE)
    bg_scale = _parse_float_open_closed("--lingbot-split-sink-bg-scale", raw["bg_scale"], DEFAULT_BG_SCALE)
    fg_frac = _parse_float_open("--lingbot-split-sink-fg-frac", raw["fg_frac"], DEFAULT_FG_FRAC)
    if fg_scale > bg_scale:
        raise SystemExit(f"--lingbot-split-sink-fg-scale ({fg_scale:g}) must be <= "
                         f"--lingbot-split-sink-bg-scale ({bg_scale:g})")
    if raw["after"] is None:
        after = DEFAULT_AFTER
    else:
        try:
            after = int(raw["after"])
        except ValueError:
            raise SystemExit(f"--lingbot-split-sink-after must be an integer, got {raw['after']!r}") from None
        if after < 0:
            raise SystemExit(f"--lingbot-split-sink-after must be >= 0, got {after}")
    tasks = DEFAULT_TASKS if raw["tasks"] is None else raw["tasks"]
    try:
        re.compile(tasks)
    except re.error as exc:
        raise SystemExit(f"--lingbot-split-sink-tasks is not a valid regex: {exc}") from None
    return SplitSinkConfig(enabled, fg_scale, bg_scale, fg_frac, after, tasks), rest


def sink_tokens(sink_latents: int, frame_seqlen: int) -> int:
    """Cache tokens held by the sink: sink_size * frame_seqlen."""
    return max(0, int(sink_latents)) * max(0, int(frame_seqlen))


def active(cfg: SplitSinkConfig | None, chunk_id: int, chunk_latents: int, sink_latents: int) -> bool:
    """Scale this latent chunk once chunk_id >= after and earlier chunks have filled the sink."""
    return (cfg is not None and cfg.enabled and sink_latents > 0 and chunk_id >= cfg.after
            and chunk_id * chunk_latents >= sink_latents)


def _bilinear_sample(img: np.ndarray, ys: np.ndarray, xs: np.ndarray) -> np.ndarray:
    """Bilinearly sample `img` [C, H, W] at floating-point grid coordinates `(ys, xs)` [H, W]."""
    _, h, w = img.shape
    yc = np.clip(ys, 0.0, h - 1.0)
    xc = np.clip(xs, 0.0, w - 1.0)
    y0 = np.floor(yc).astype(np.int64)
    x0 = np.floor(xc).astype(np.int64)
    y1 = np.minimum(y0 + 1, h - 1)
    x1 = np.minimum(x0 + 1, w - 1)
    wy = (yc - y0)[None, :, :]
    wx = (xc - x0)[None, :, :]
    top = (1.0 - wx) * img[:, y0, x0] + wx * img[:, y0, x1]
    bot = (1.0 - wx) * img[:, y1, x0] + wx * img[:, y1, x1]
    return (1.0 - wy) * top + wy * bot


def compute_sink_scales(
    latents: np.ndarray,
    poses: np.ndarray,
    cfg: SplitSinkConfig,
    intrinsics_480p: tuple[float, float, float, float] = P.INTRINSICS_480P,
) -> tuple[np.ndarray, int]:
    """Compute per-token sink scale vector and foreground token count from opening sink latents and poses.

    `latents` has shape `[C, S, lat_h, lat_w]` and `poses` has shape `[S, 4, 4]` (camera-to-world).
    Returns `(scales_1d, fg_token_count)` where `scales_1d` is float32 `[S * (lat_h // 2) * (lat_w // 2)]`.
    """
    lat = np.asarray(latents, dtype=np.float64)
    c2w = np.asarray(poses, dtype=np.float64)
    if lat.ndim != 4:
        raise ValueError(f"latents must have shape [C, S, lat_h, lat_w], got {lat.shape}")
    _, s_len, lat_h, lat_w = lat.shape
    if lat_h < 2 or lat_w < 2 or lat_h % 2 != 0 or lat_w % 2 != 0:
        raise ValueError(f"lat_h and lat_w must be positive even integers, got {(lat_h, lat_w)}")
    if c2w.shape != (s_len, 4, 4):
        raise ValueError(f"poses must have shape ({s_len}, 4, 4), got {c2w.shape}")
    ph, pw = lat_h // 2, lat_w // 2
    frame_seqlen = ph * pw
    if s_len == 0:
        return np.empty(0, dtype=np.float32), 0
    if s_len == 1:
        return np.full(frame_seqlen, cfg.bg_scale, dtype=np.float32), 0

    fx0, fy0, cx0, cy0 = (float(v) for v in intrinsics_480p)
    fx = fx0 * (lat_w / 832.0)
    fy = fy0 * (lat_h / 480.0)
    cx = cx0 * (lat_w / 832.0)
    cy = cy0 * (lat_h / 480.0)

    xg, yg = np.meshgrid(np.arange(lat_w, dtype=np.float64), np.arange(lat_h, dtype=np.float64))
    d0_flat = np.stack([(xg - cx) / fx, (yg - cy) / fy, np.ones_like(xg)], axis=0).reshape(3, -1)
    r0 = c2w[0, :3, :3]
    z0 = lat[:, 0, :, :]

    res_sum = np.zeros((lat_h, lat_w), dtype=np.float64)
    res_cnt = np.zeros((lat_h, lat_w), dtype=np.float64)
    for idx in range(1, s_len):
        rl = c2w[idx, :3, :3]
        dl = ((rl.T @ r0) @ d0_flat).reshape(3, lat_h, lat_w)
        dl_z = dl[2]
        valid = dl_z > MIN_DEPTH
        safe_z = np.where(valid, dl_z, 1.0)
        xl = fx * (dl[0] / safe_z) + cx
        yl = fy * (dl[1] / safe_z) + cy
        valid = valid & (yl >= 0.0) & (yl <= lat_h - 1.0) & (xl >= 0.0) & (xl <= lat_w - 1.0)
        if not np.any(valid):
            continue
        warped = _bilinear_sample(lat[:, idx, :, :], yl, xl)
        diff = np.linalg.norm(warped - z0, axis=0)
        res_sum += np.where(valid, diff, 0.0)
        res_cnt += valid.astype(np.float64)

    res_map = res_sum / np.maximum(res_cnt, 1.0)
    patch_res = res_map.reshape(ph, 2, pw, 2).max(axis=(1, 3))
    if float(patch_res.max()) <= RESIDUAL_EPS:
        return np.full(s_len * frame_seqlen, cfg.bg_scale, dtype=np.float32), 0

    k = min(frame_seqlen, max(1, int(round(cfg.fg_frac * frame_seqlen))))
    flat_res = patch_res.reshape(-1)
    top_idx = np.argsort(-flat_res, kind="stable")[:k]
    top_idx = top_idx[flat_res[top_idx] > RESIDUAL_EPS]
    if top_idx.size == 0:
        return np.full(s_len * frame_seqlen, cfg.bg_scale, dtype=np.float32), 0

    fg0 = np.zeros(frame_seqlen, dtype=bool)
    fg0[top_idx] = True
    fg0 = fg0.reshape(ph, pw)

    pxg, pyg = np.meshgrid(2.0 * np.arange(pw, dtype=np.float64) + 0.5,
                           2.0 * np.arange(ph, dtype=np.float64) + 0.5)
    dl_patch = np.stack([(pxg - cx) / fx, (pyg - cy) / fy, np.ones_like(pxg)], axis=0).reshape(3, -1)

    fg_masks = [fg0]
    for idx in range(1, s_len):
        rl = c2w[idx, :3, :3]
        d0_p = ((r0.T @ rl) @ dl_patch).reshape(3, ph, pw)
        d0_z = d0_p[2]
        valid_p = d0_z > MIN_DEPTH
        safe_pz = np.where(valid_p, d0_z, 1.0)
        x0_lat = fx * (d0_p[0] / safe_pz) + cx
        y0_lat = fy * (d0_p[1] / safe_pz) + cy
        px0_f = (x0_lat - 0.5) / 2.0
        py0_f = (y0_lat - 0.5) / 2.0
        px0 = np.rint(px0_f).astype(np.int64)
        py0 = np.rint(py0_f).astype(np.int64)
        in_bounds = (valid_p & (py0_f >= -0.5) & (py0_f <= ph - 0.5)
                     & (px0_f >= -0.5) & (px0_f <= pw - 0.5)
                     & (py0 >= 0) & (py0 < ph) & (px0 >= 0) & (px0 < pw))
        py0_c = np.clip(py0, 0, ph - 1)
        px0_c = np.clip(px0, 0, pw - 1)
        fg_masks.append(np.where(in_bounds, fg0[py0_c, px0_c], False))

    fg_flat = np.stack(fg_masks, axis=0).reshape(-1)
    scales = np.where(fg_flat, np.float32(cfg.fg_scale), np.float32(cfg.bg_scale)).astype(np.float32, copy=False)
    return scales, int(fg_flat.sum())


@dataclass
class SplitSinkBank:
    """Host accumulator for opening sink latents and camera poses of one rollout."""
    cfg: SplitSinkConfig
    sink: int
    intrinsics_480p: tuple[float, float, float, float] = P.INTRINSICS_480P
    latents: list[np.ndarray] = field(default_factory=list)
    poses: list[np.ndarray] = field(default_factory=list)
    scales: np.ndarray | None = None
    fg_tokens: int = 0

    @property
    def have(self) -> int:
        return len(self.poses)

    @property
    def ready(self) -> bool:
        return self.sink > 0 and len(self.poses) >= self.sink

    def record(self, x0_latents: np.ndarray, chunk_poses: np.ndarray) -> int:
        """Append up to `sink - have` latents `[C, L, lat_h, lat_w]` and `[L, 4, 4]` poses."""
        need = self.sink - len(self.poses)
        if need <= 0:
            return 0
        lat = np.asarray(x0_latents, dtype=np.float32)
        c2w = np.asarray(chunk_poses, dtype=np.float64)
        take = min(int(lat.shape[1]), len(c2w), need)
        if take <= 0:
            return 0
        self.latents.append(np.array(lat[:, :take], dtype=np.float32, copy=True))
        self.poses.extend(np.array(c2w[i], dtype=np.float64, copy=True) for i in range(take))
        return take

    def build(self) -> tuple[np.ndarray, int]:
        """Compute `(scales_1d, fg_tokens)` once all `sink` latents are collected."""
        if self.scales is None:
            if not self.ready:
                raise RuntimeError(f"split-sink bank has {len(self.poses)}/{self.sink} sink latents")
            full_lat = np.concatenate(self.latents, axis=1)[:, :self.sink]
            full_c2w = np.stack(self.poses[:self.sink], axis=0)
            self.scales, self.fg_tokens = compute_sink_scales(
                full_lat, full_c2w, self.cfg, intrinsics_480p=self.intrinsics_480p
            )
        return self.scales, self.fg_tokens


def _copy(t):
    return t.clone() if hasattr(t, "clone") else t.copy()


def scale_keys_vector(kv: list[dict], scales_tensor, saved: list | None = None) -> list:
    """Multiply `kv[b]['k'][:, :n_tokens]` by `scales_tensor` (`[1, n_tokens, 1, 1]` or `[n_tokens]`) in place.
    Each block's original slice is cloned into `saved` before modification so `restore_keys` is bit-exact
    even if an exception fires mid-loop."""
    saved = [] if saved is None else saved
    if getattr(scales_tensor, "ndim", 0) == 1:
        scales_tensor = scales_tensor[None, :, None, None]
    n_tokens = int(scales_tensor.shape[1])
    for blk in kv:
        orig = _copy(blk["k"][:, :n_tokens])
        saved.append(orig)
        blk["k"][:, :n_tokens] = orig * scales_tensor
    return saved


def restore_keys(kv: list[dict], n_tokens: int, saved: list) -> None:
    """Write the saved original slices back (exact copy, no division)."""
    for blk, orig in zip(kv, saved):
        blk["k"][:, :n_tokens] = orig
