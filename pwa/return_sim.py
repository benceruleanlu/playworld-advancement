"""Return-to-start similarity of a rollout, without the judge (numpy only; imageio to read an mp4).

    python -m pwa.return_sim VIDEO.mp4 [VIDEO2.mp4 ...] [--after 4] [--fps 16] [--ref FRAME] [--pairs C:J,...] [--json]

Every frame is reduced to grayscale, block-averaged to 64 x 112, and compared with frame 0 by normalised
cross-correlation (1 = the same image up to brightness and contrast, about 0 = unrelated). The report gives the
maximum after the first `--after` seconds and the time it happens: a camera that turns away and comes back to the
start view shows a late peak; a rollout whose return lands somewhere else does not. It measures resemblance to the
opening frame only. For Out-of-sight a peak near 1.0 can also mean a hard reset to frame 0, which that rubric
scores as level 1; read it together with the clip.

`left_min` is the lowest similarity between `--after` and the peak and `return_gain` = max_after - left_min: a clip
that never leaves the reference (static, or frozen) has a gain near 0, a true leave-and-return a large one.
`--ref FRAME` compares against another frame than 0. `--pairs C:J,...` compares latent chunk C with chunk J frame
by frame (chunk j covers pixel frames 16j-3 .. 16j+12, clipped at 0) and reports the mean NCC per pair; take the
pairs from the `pose-mem: chunk C <- chunk J` lines in gen.log to check a revisit of a view other than the start.
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


CHUNK_FRAMES = 16  # pixel frames per latent chunk (4 latents x 4 frames)


def chunk_frames(j: int) -> range:
    """Pixel frames of latent chunk j: latent l covers 4l-3 .. 4l, so chunk j covers 16j-3 .. 16j+12 (from 0)."""
    return range(max(0, CHUNK_FRAMES * j - 3), CHUNK_FRAMES * j + 13)


def similarity_to_first(frames, fps: float = 16.0, after_s: float = 4.0, size=SIZE, ref_frame: int = 0) -> dict:
    """Similarity of every frame to frame ref_frame (default 0), the maximum after the first after_s seconds, and
    left_min / return_gain (lowest similarity between after_s and the peak; peak minus that)."""
    small = [to_small_gray(f, size) for f in frames]
    if not small:
        raise ValueError("no frames")
    if not 0 <= ref_frame < len(small):
        raise ValueError(f"ref frame {ref_frame} outside 0..{len(small) - 1}")
    ref = small[ref_frame]
    sims = [ncc(ref, f) for f in small]
    start = int(round(after_s * fps))
    tail = sims[start:]
    out = {"frames": len(sims), "fps": fps, "after_s": after_s, "ref_frame": ref_frame,
           "similarity": [round(s, 4) for s in sims]}
    if tail:
        i = int(np.argmax(tail))
        left = min(tail[:i + 1])
        out.update(max_after=round(tail[i], 4), max_frame=start + i, max_time_s=round((start + i) / fps, 3),
                   left_min=round(left, 4), return_gain=round(tail[i] - left, 4), last=round(sims[-1], 4))
    else:
        out.update(max_after=None, max_frame=None, max_time_s=None, left_min=None, return_gain=None,
                   last=round(sims[-1], 4))
    return out


def pair_similarity(frames, pairs, size=SIZE) -> list[dict]:
    """Mean frame-by-frame NCC of latent chunk C against chunk J for each (C, J); None when C is past the clip."""
    small = [to_small_gray(f, size) for f in frames]
    out = []
    for c, j in pairs:
        fc, fj = list(chunk_frames(c)), list(chunk_frames(j))
        n = min(len(fc), len(fj))
        fc, fj = fc[-n:], fj[-n:]  # chunk 0 is shorter (starts at frame 0): align on the chunk ends
        vals = [ncc(small[a], small[b]) for a, b in zip(fc, fj) if a < len(small) and b < len(small)]
        out.append({"chunk": c, "ref_chunk": j, "frames": len(vals),
                    "mean": round(float(np.mean(vals)), 4) if vals else None})
    return out


def parse_pairs(raw: str) -> list[tuple[int, int]]:
    try:
        pairs = [tuple(int(x) for x in p.split(":")) for p in raw.split(",") if p.strip()]
    except ValueError:
        raise ValueError(f"--pairs wants C:J,..., got {raw!r}") from None
    if not pairs or any(len(p) != 2 or min(p) < 0 for p in pairs):
        raise ValueError(f"--pairs wants C:J,... with chunk indices >= 0, got {raw!r}")
    return pairs


def measure(path: str, after_s: float = 4.0, fps: float | None = None, ref_frame: int = 0, pairs=None) -> dict:
    """similarity_to_first (and pair_similarity when pairs are given) over an mp4, each frame reduced to 64 x 112
    as it is read; fps from the container unless given (else 16)."""
    import imageio.v2 as imageio  # noqa: PLC0415
    reader = imageio.get_reader(path)
    try:
        fps = fps or float(reader.get_meta_data().get("fps") or 0) or 16.0
        small = [to_small_gray(f) for f in reader]
    finally:
        reader.close()
    out = {"video": path, **similarity_to_first(small, fps=fps, after_s=after_s, ref_frame=ref_frame)}
    if pairs:
        out["pairs"] = pair_similarity(small, pairs)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pwa.return_sim", description=__doc__.split("\n\n")[0])
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--after", type=float, default=4.0, help="seconds to skip before taking the max (default 4)")
    ap.add_argument("--fps", type=float, default=None, help="override the container fps (default: read it, else 16)")
    ap.add_argument("--ref", type=int, default=0, help="reference frame index (default 0)")
    ap.add_argument("--pairs", default="", help="C:J,... compare latent chunk C with chunk J (from gen.log)")
    ap.add_argument("--json", action="store_true", help="one JSON object per video, with the per-frame series")
    a = ap.parse_args(argv)
    try:
        pairs = parse_pairs(a.pairs) if a.pairs else None
    except ValueError as e:
        ap.error(str(e))
    rc = 0
    for v in a.videos:
        try:
            r = measure(v, a.after, a.fps, a.ref, pairs)
        except Exception as e:  # noqa: BLE001
            print(f"{v}: error: {e}", file=sys.stderr)
            rc = 1
            continue
        if a.json:
            print(json.dumps(r))
        else:
            print(f"{v}\tframes={r['frames']}\tref={r['ref_frame']}\tmax_after_{a.after:g}s={r['max_after']}"
                  f"\tat={r['max_time_s']}s\tleft_min={r['left_min']}\treturn_gain={r['return_gain']}\tlast={r['last']}")
            for p in r.get("pairs", []):
                print(f"{v}\tchunk {p['chunk']} vs chunk {p['ref_chunk']}\tframes={p['frames']}\tmean={p['mean']}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
