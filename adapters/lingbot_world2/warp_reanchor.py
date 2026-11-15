"""Homography-warped spatial y-channel view re-anchoring (opt-in, session only; numpy only, no torch import).

`--lingbot-warp-reanchor` (LINGBOT_WARP_REANCHOR=1) projects the opening image into each returning
chunk's camera frustum via exact pinhole homography K R K^-1 (plus optional focus-depth translation
t / Z_0), encodes the warped frame as a 5-frame still clip through the causal VAE (at most 1 latent
per 4-latent chunk), and sets `y[:4, g]` (`mask`) to 1.0 only on valid in-frustum latent patches
(with interior frustum-cut erosion so border-clamped pixels never leak through VAE spatial receptive
fields) and 0.0 on newly exposed regions outside frame 0's frustum.
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass

import numpy as np

from adapters.lingbot_world2 import poses as P

FLAG = "--lingbot-warp-reanchor"
CHUNK = P.LATENT_CHUNK
DEFAULTS = {
    "max_deg": 40.0,
    "max_trans": 12.0,
    "leave_deg": 25.0,
    "leave_trans": 8.0,
    "focus": 0.0,
    "erode": 1,
    "tasks": "GC",
}
_ARGS = {  # flag -> (field, env var)
    "--lingbot-warp-max-deg": ("max_deg", "LINGBOT_WARP_MAX_DEG"),
    "--lingbot-warp-max-trans": ("max_trans", "LINGBOT_WARP_MAX_TRANS"),
    "--lingbot-warp-leave-deg": ("leave_deg", "LINGBOT_WARP_LEAVE_DEG"),
    "--lingbot-warp-leave-trans": ("leave_trans", "LINGBOT_WARP_LEAVE_TRANS"),
    "--lingbot-warp-focus": ("focus", "LINGBOT_WARP_FOCUS"),
    "--lingbot-warp-erode": ("erode", "LINGBOT_WARP_ERODE"),
    "--lingbot-warp-tasks": ("tasks", "LINGBOT_WARP_TASKS"),
}


@dataclass(frozen=True)
class WarpReanchorConfig:
    enabled: bool = False
    max_deg: float = DEFAULTS["max_deg"]
    max_trans: float = DEFAULTS["max_trans"]
    leave_deg: float = DEFAULTS["leave_deg"]
    leave_trans: float = DEFAULTS["leave_trans"]
    focus: float = DEFAULTS["focus"]
    erode: int = DEFAULTS["erode"]
    tasks: str = DEFAULTS["tasks"]

    def applies(self, name: str) -> bool:
        """True when this call name (e.g. 'GC036_chunk_03' or 'GC036_full') matches --lingbot-warp-tasks."""
        return self.enabled and re.match(self.tasks, name or "") is not None

    def describe(self) -> str:
        focus = f"focus {self.focus:g}" if self.focus > 0 else "focus inf"
        return (f"warp-reanchor max {self.max_deg:g} deg / {self.max_trans:g} units, "
                f"leave {self.leave_deg:g} deg / {self.leave_trans:g} units, {focus}, "
                f"erode {self.erode}, tasks {self.tasks!r}")


def _take(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    seen: dict[str, str] = {}
    rest: list[str] = []
    i = 0
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


def _num(name: str, raw: str, kind: type, lo: float, hi: float = math.inf, open_lo: bool = False):
    try:
        v = kind(raw)
    except ValueError:
        raise SystemExit(f"{name} must be a {kind.__name__}, got {raw!r}") from None
    if isinstance(v, float) and not math.isfinite(v):
        raise SystemExit(f"{name} must be finite, got {raw!r}")
    low_ok = (v > lo) if open_lo else (v >= lo)
    if not (low_ok and v <= hi):
        bracket = "(" if open_lo else "["
        raise SystemExit(f"{name} must be in {bracket}{lo}, {hi}], got {raw!r}")
    return v


def parse(argv: list[str], environ=os.environ) -> tuple[WarpReanchorConfig, list[str]]:
    """Extract --lingbot-warp-reanchor and its knobs from argv (env fallback), returning (cfg, rest).
    A knob arg without the flag (or LINGBOT_WARP_REANCHOR=1) is refused: that arm would silently run without it."""
    enabled = FLAG in argv or environ.get("LINGBOT_WARP_REANCHOR", "0") == "1"
    argv = [a for a in argv if a != FLAG]
    seen, rest = _take(argv)
    if seen and not enabled:
        raise SystemExit(f"{', '.join(sorted(seen))} without {FLAG}: the arm would run without warp re-anchoring")
    raw = {
        f: (seen[arg] if arg in seen else (environ.get(env, "").strip() or None))
        for arg, (f, env) in _ARGS.items()
    }
    names = {f: arg for arg, (f, _) in _ARGS.items()}
    v = dict(DEFAULTS)
    for f, lo, hi, open_lo in (
        ("max_deg", 0.0, 75.0, True),
        ("max_trans", 0.0, 1e6, False),
        ("leave_deg", 0.0, 180.0, True),
        ("leave_trans", 0.0, 1e6, False),
        ("focus", 0.0, 1e6, False),
    ):
        if raw[f] is not None:
            v[f] = _num(names[f], raw[f], float, lo, hi, open_lo=open_lo)
    if raw["erode"] is not None:
        v["erode"] = _num(names["erode"], raw["erode"], int, 0, 8)
    if raw["tasks"] is not None:
        try:
            re.compile(raw["tasks"])
        except re.error as exc:
            raise SystemExit(f"--lingbot-warp-tasks is not a valid regex: {exc}") from None
        v["tasks"] = raw["tasks"]
    return WarpReanchorConfig(enabled, **v), rest


# ----------------------------------------------------------- geometry & masks

def pose_offset(c2w: np.ndarray) -> tuple[float, float]:
    """(rotation in degrees, translation norm in key units) from identity start pose."""
    cos = (float(np.trace(c2w[:3, :3])) - 1.0) / 2.0
    return math.degrees(math.acos(min(1.0, max(-1.0, cos)))), float(np.linalg.norm(c2w[:3, 3]))


def project_to_start(
    c2w: np.ndarray,
    K: tuple[float, float, float, float],
    h: int,
    w: int,
    focus: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Project each pixel of current camera `c2w` into start frame 0 (`c2w_0 = I_4`).

    Returns `(uv0, valid_pix)` where `uv0` is float64 `[h, w, 2]` normalized to `[-1, 1]`
    (`align_corners=True`, clipped to `[-1, 1]` for clean border clamping) and `valid_pix`
    is bool `[h, w]` marking pixels whose ray lands in front of and inside frame 0.
    """
    fx, fy, cx, cy = (float(x) for x in K)
    u = np.arange(w, dtype=np.float64)
    v = np.arange(h, dtype=np.float64)
    uu, vv = np.meshgrid(u, v)
    xc = (uu - cx) / fx
    yc = (vv - cy) / fy

    mat = np.asarray(c2w, dtype=np.float64)
    R = mat[:3, :3]
    t = mat[:3, 3]
    d0_x = R[0, 0] * xc + R[0, 1] * yc + R[0, 2]
    d0_y = R[1, 0] * xc + R[1, 1] * yc + R[1, 2]
    d0_z = R[2, 0] * xc + R[2, 1] * yc + R[2, 2]
    if focus > 0.0:
        inv_z = 1.0 / float(focus)
        d0_x = d0_x + t[0] * inv_z
        d0_y = d0_y + t[1] * inv_z
        d0_z = d0_z + t[2] * inv_z

    safe_z = np.maximum(d0_z, 1e-4)
    u0 = fx * (d0_x / safe_z) + cx
    v0 = fy * (d0_y / safe_z) + cy

    eps = 1e-9
    valid_pix = (
        (d0_z > 1e-4)
        & (u0 >= -eps)
        & (u0 <= (w - 1) + eps)
        & (v0 >= -eps)
        & (v0 <= (h - 1) + eps)
    )
    denom_w = max(w - 1, 1)
    denom_h = max(h - 1, 1)
    x_norm = np.clip(2.0 * u0 / denom_w - 1.0, -1.0, 1.0)
    y_norm = np.clip(2.0 * v0 / denom_h - 1.0, -1.0, 1.0)
    return np.stack([x_norm, y_norm], axis=-1), valid_pix


def latent_valid_mask(valid_pix: np.ndarray, lat_h: int, lat_w: int, erode: int = 1) -> np.ndarray:
    """Downsample pixel validity `[h, w]` to VAE latent grid `[lat_h, lat_w]` (float32 1.0 / 0.0).

    A latent cell is valid iff every pixel in its `(h // lat_h) x (w // lat_w)` patch is valid.
    Erosion pads outer image borders with `True` so only interior frustum cuts against `False`
    regions are eroded — an all-valid frame at `0 deg` stays 100% `1.0` even for `erode >= 1`.
    """
    valid = np.asarray(valid_pix, dtype=bool)
    h, w = valid.shape
    if h % lat_h != 0 or w % lat_w != 0:
        raise ValueError(f"pixel mask {(h, w)} is not divisible by latent shape {(lat_h, lat_w)}")
    valid_lat = valid.reshape(lat_h, h // lat_h, lat_w, w // lat_w).all(axis=(1, 3))
    for _ in range(max(0, int(erode))):
        p = np.pad(valid_lat, 1, mode="constant", constant_values=True)
        valid_lat = (
            p[:-2, :-2] & p[:-2, 1:-1] & p[:-2, 2:]
            & p[1:-1, :-2] & p[1:-1, 1:-1] & p[1:-1, 2:]
            & p[2:, :-2] & p[2:, 1:-1] & p[2:, 2:]
        )
    return valid_lat.astype(np.float32)


# ----------------------------------------------------------- return tracker

class WarpTracker:
    """Stateful per-rollout return-approach latent selector (at most 1 latent per chunk)."""

    def __init__(self, cfg: WarpReanchorConfig):
        self.cfg = cfg
        self.reset()

    def reset(self) -> None:
        self.away: bool = False
        self.parked: bool = False
        self._prev_score: float | None = None

    def select_chunk_anchors(
        self,
        latent_c2ws: np.ndarray,
        start_lat: int,
        chunk_size: int = CHUNK,
    ) -> list[tuple[int, np.ndarray, float]]:
        """Return `[(global_lat_idx, c2w, score), ...]` with at most 1 anchor per chunk."""
        poses = np.asarray(latent_c2ws, dtype=np.float64)
        cfg = self.cfg
        out: list[tuple[int, np.ndarray, float]] = []
        for c0 in range(0, len(poses), chunk_size):
            best: tuple[float, int, np.ndarray, float, float] | None = None
            chunk = poses[c0 : c0 + chunk_size]
            for j, c2w in enumerate(chunk):
                g = start_lat + c0 + j
                deg, trans = pose_offset(c2w)
                score = deg + 0.5 * trans
                if self.parked and (deg > 2.0 or trans > 1.0):
                    self.parked = False
                if deg >= cfg.leave_deg or trans >= cfg.leave_trans:
                    self.away = True
                approaching = self._prev_score is None or score < self._prev_score - 1e-6
                self._prev_score = score
                if (
                    self.away
                    and not self.parked
                    and g > 0
                    and approaching
                    and deg <= cfg.max_deg
                    and trans <= cfg.max_trans
                ):
                    cand = (score, g, np.array(c2w, copy=True), deg, trans)
                    if best is None or cand[0] < best[0]:
                        best = cand
            if best is not None:
                b_score, b_g, b_c2w, b_deg, b_trans = best
                if b_deg <= 1.0 and b_trans <= 0.5:
                    self.parked = True
                out.append((b_g, b_c2w, b_score))
        return out
