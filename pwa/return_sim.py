"""Return-to-start similarity of a rollout, without the judge (numpy only; imageio to read an mp4).

    python -m pwa.return_sim VIDEO.mp4 [VIDEO2.mp4 ...] [--after 4] [--fps 16] [--json]

Every frame is reduced to grayscale, block-averaged to 64 x 112, and compared with frame 0 by normalised
cross-correlation (1 = the same image up to brightness and contrast, about 0 = unrelated). The report gives the
maximum after the first `--after` seconds and the time it happens: a camera that turns away and comes back to the
start view shows a late peak; a rollout whose return lands somewhere else does not. It measures resemblance to the
opening frame only. For Out-of-sight a peak near 1.0 can also mean a hard reset to frame 0, which that rubric
scores as level 1; read it together with the clip.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

SIZE = (64, 112)  # rows, cols: 832x480 rollouts keep their aspect ratio


def to_small_gray(frame: np.ndarray, size: tuple[int, int] = SIZE) -> np.ndarray:
    """[H, W, 3] or [H, W] uint8/float -> float64 [h, w] grayscale, block-averaged (area resampling)."""
    f = np.asarray(frame, dtype=np.float64)
    if f.ndim == 3:
        f = f[..., :3] @ np.array([0.299, 0.587, 0.114])
    h, w = size
    rows = np.linspace(0, f.shape[0], h + 1).astype(int)
    cols = np.linspace(0, f.shape[1], w + 1).astype(int)
    if np.any(np.diff(rows) == 0) or np.any(np.diff(cols) == 0):
        raise ValueError(f"frame {f.shape[:2]} is smaller than the comparison size {size}")
    s = np.add.reduceat(np.add.reduceat(f, rows[:-1], axis=0), cols[:-1], axis=1)
    return s / np.outer(np.diff(rows), np.diff(cols))


def ncc(a: np.ndarray, b: np.ndarray) -> float:
    """Normalised cross-correlation of two equal-size images (0.0 if either is flat)."""
    a = a - a.mean()
    b = b - b.mean()
    den = float(np.sqrt((a * a).sum() * (b * b).sum()))
    return float((a * b).sum() / den) if den > 1e-12 else 0.0


def similarity_to_first(frames, fps: float = 16.0, after_s: float = 4.0, size=SIZE) -> dict:
    """Similarity of every frame to frame 0, and the maximum after the first after_s seconds."""
    it = iter(frames)
    try:
        ref = to_small_gray(next(it), size)
    except StopIteration:
        raise ValueError("no frames") from None
    sims = [1.0] + [ncc(ref, to_small_gray(f, size)) for f in it]
    start = int(round(after_s * fps))
    tail = sims[start:]
    out = {"frames": len(sims), "fps": fps, "after_s": after_s, "similarity": [round(s, 4) for s in sims]}
    if tail:
        i = int(np.argmax(tail))
        out.update(max_after=round(tail[i], 4), max_frame=start + i, max_time_s=round((start + i) / fps, 3),
                   last=round(sims[-1], 4))
    else:
        out.update(max_after=None, max_frame=None, max_time_s=None, last=round(sims[-1], 4))
    return out


def measure(path: str, after_s: float = 4.0, fps: float | None = None) -> dict:
    """similarity_to_first over an mp4, streamed frame by frame; fps from the container unless given (else 16)."""
    import imageio.v2 as imageio  # noqa: PLC0415
    reader = imageio.get_reader(path)
    try:
        fps = fps or float(reader.get_meta_data().get("fps") or 0) or 16.0
        return {"video": path, **similarity_to_first(iter(reader), fps=fps, after_s=after_s)}
    finally:
        reader.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pwa.return_sim", description=__doc__.split("\n\n")[0])
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--after", type=float, default=4.0, help="seconds to skip before taking the max (default 4)")
    ap.add_argument("--fps", type=float, default=None, help="override the container fps (default: read it, else 16)")
    ap.add_argument("--json", action="store_true", help="one JSON object per video, with the per-frame series")
    a = ap.parse_args(argv)
    rc = 0
    for v in a.videos:
        try:
            r = measure(v, a.after, a.fps)
        except Exception as e:  # noqa: BLE001
            print(f"{v}: error: {e}", file=sys.stderr)
            rc = 1
            continue
        if a.json:
            print(json.dumps(r))
        else:
            print(f"{v}\tframes={r['frames']}\tmax_after_{a.after:g}s={r['max_after']}\tat={r['max_time_s']}s"
                  f"\tlast={r['last']}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
