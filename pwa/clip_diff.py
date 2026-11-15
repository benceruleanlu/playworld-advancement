"""Are two rollouts the same video? Frame-by-frame comparison without the judge (numpy + imageio).

    python -m pwa.clip_diff A.mp4 B.mp4 [C.mp4 ...]            # every clip against the first
    python -m pwa.clip_diff --exps EXP_A EXP_B [EXP_C ...] [--tasks GC031,OE039] [--json]

Why: generation is deterministic, so two arms whose flag never fired, or two controls with the same
settings and seed, should be the same video, and then any score difference between them is the judge
alone. Whether they are has usually been left unchecked. This reads it from the clips.

`--exps` compares the published 480p clips of experiments task by task (video URLs from
results/media/EXP.json, downloaded once into --cache, default runs/_clips), the first experiment being
the reference. Paths compare any local mp4s, e.g. runs/EXP/videos/TASK/TASK.mp4 at full size.

Per pair: sha256 equality of the files, frame counts, and the mean absolute difference per frame on
0-255 RGB (MAD). Verdict:
  identical       same bytes
  same frames     every compared frame within --same (default 1.0): the same video up to encoding
  near-identical  no frame over --differ (default 10.0): the same content with low-level pixel differences
  diverges        frames match at first, then differ; the note gives the first frame over --differ
  different       already differ at frame 0 (other first image or crop), or no common frames
The defaults come from published 480p clips: pairs that should be the same video but are not byte-equal
peak at 3 to 7, and pairs known to differ (a control against an arm that changed the rollout) at 40 to 85.
`length` is reported separately: one clip can be a prefix of the other (a rollout that ended earlier).

Published clips are re-encodes (480p H.264) of the rollouts, so `identical` and `same frames` there mean
the re-encodes match; that is what the judge-noise question needs, but the originals are the ground truth.
It answers "same pixels or not", nothing about quality or which clip is better.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SAME, DIFFER = 1.0, 10.0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def frame_mad(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a[..., :3].astype(np.int16) - b[..., :3].astype(np.int16)).mean())


def read_video(path) -> tuple[list[np.ndarray], float]:
    import imageio
    reader = imageio.get_reader(str(path))
    try:
        fps = float(reader.get_meta_data().get("fps") or 16.0)
        return [np.asarray(f) for f in reader], fps
    finally:
        reader.close()


def compare_frames(a: list, b: list, fps: float = 16.0, same: float = SAME, differ: float = DIFFER) -> dict:
    """Compare two frame lists over their common length."""
    n = min(len(a), len(b))
    shorter = "a" if len(a) < len(b) else "b"
    out = {"frames_a": len(a), "frames_b": len(b), "compared": n,
           "length": "equal" if len(a) == len(b) else f"{shorter} is shorter by {abs(len(a) - len(b))} frames"}
    if n == 0:
        return {**out, "verdict": "different", "why": "no common frames"}
    if a[0].shape != b[0].shape:
        return {**out, "verdict": "different",
                "why": f"frame sizes differ ({a[0].shape[1]}x{a[0].shape[0]} vs {b[0].shape[1]}x{b[0].shape[0]})"}
    mad = np.array([frame_mad(a[i], b[i]) for i in range(n)])
    over = np.flatnonzero(mad > differ)
    out.update(mad_mean=round(float(mad.mean()), 3), mad_max=round(float(mad.max()), 3),
               frames_over=int(over.size), share_over=round(float(over.size) / n, 3))
    if mad.max() <= same:
        return {**out, "verdict": "same frames"}
    if over.size and over[0] == 0:
        return {**out, "verdict": "different", "why": "differ from frame 0"}
    if over.size:
        first = int(over[0])
        return {**out, "verdict": "diverges", "at_frame": first, "at_s": round(first / fps, 2)}
    return {**out, "verdict": "near-identical", "why": f"low-level differences only (max {mad.max():.2f}, under {differ})"}


def compare_files(a: Path, b: Path, same: float = SAME, differ: float = DIFFER) -> dict:
    if sha256(a) == sha256(b):
        frames, _ = read_video(a)
        return {"frames_a": len(frames), "frames_b": len(frames), "compared": len(frames), "length": "equal",
                "mad_mean": 0.0, "mad_max": 0.0, "frames_over": 0, "share_over": 0.0, "verdict": "identical"}
    fa, fps = read_video(a)
    fb, _ = read_video(b)
    return compare_frames(fa, fb, fps, same, differ)


def manifest(exp: str, media_dir: Path) -> dict:
    path = media_dir / f"{exp}.json"
    if not path.is_file():
        raise SystemExit(f"no scenes manifest {path} (the run published no clips, or the name is wrong)")
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(url: str, dest: Path) -> Path:
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=300) as resp, open(tmp, "wb") as f:  # noqa: S310 (manifest URL)
        while block := resp.read(1 << 20):
            f.write(block)
    tmp.replace(dest)
    return dest


def compare_exps(exps: list[str], tasks: list[str] | None, media_dir: Path, cache: Path,
                 same: float = SAME, differ: float = DIFFER, log=print, fetcher=fetch) -> list[dict]:
    mans = {e: {t["task_id"]: t for t in manifest(e, media_dir).get("tasks", [])} for e in exps}
    ref = exps[0]
    rows = []
    for task in tasks or sorted(mans[ref]):
        a = mans[ref].get(task, {}).get("video")
        for other in exps[1:]:
            b = mans[other].get(task, {}).get("video")
            row = {"task": task, "a": ref, "b": other}
            if not a or not b:
                rows.append({**row, "verdict": "missing", "why": f"no clip in {ref if not a else other}"})
                continue
            log(f"[clip-diff] {task}: {ref} vs {other}")
            pa = fetcher(a, cache / ref / f"{task}.mp4")
            pb = fetcher(b, cache / other / f"{task}.mp4")
            rows.append({**row, **compare_files(pa, pb, same, differ)})
    return rows


def render(rows: list[dict]) -> str:
    lines = [f"{'task':<8} {'a':<24} {'b':<24} {'verdict':<14} {'frames':>11} {'MAD mean':>8} {'max':>7}  note"]
    for r in rows:
        frames = f"{r.get('frames_a', '-')}/{r.get('frames_b', '-')}"
        note = r.get("why", "")
        if r.get("verdict") == "diverges":
            note = (f"first differs at {r['at_s']} s (frame {r['at_frame']}), "
                    f"{round(100 * r['share_over'])}% of frames differ")
        if r.get("length", "equal") != "equal":
            note = (note + "; " if note else "") + r["length"]
        lines.append(f"{r.get('task', ''):<8} {r['a']:<24} {r['b']:<24} {r['verdict']:<14} {frames:>11} "
                     f"{r.get('mad_mean', '-'):>8} {r.get('mad_max', '-'):>7}  {note}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare rollouts frame by frame: same video or not.")
    ap.add_argument("videos", nargs="*", help="mp4 paths; each is compared with the first")
    ap.add_argument("--exps", nargs="+", help="experiments with published clips; each is compared with the first")
    ap.add_argument("--tasks", default="", help="comma-separated task ids (default: every task of the first experiment)")
    ap.add_argument("--media-dir", default=str(REPO / "results" / "media"))
    ap.add_argument("--cache", default=str(REPO / "runs" / "_clips"), help="where --exps downloads clips")
    ap.add_argument("--same", type=float, default=SAME, help="max per-frame MAD still called the same frames")
    ap.add_argument("--differ", type=float, default=DIFFER, help="per-frame MAD that counts as a different frame")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if bool(a.videos) == bool(a.exps):
        ap.error("give either mp4 paths or --exps")
    if a.exps:
        if len(a.exps) < 2:
            ap.error("--exps needs at least two experiments")
        rows = compare_exps(a.exps, [t for t in a.tasks.split(",") if t] or None, Path(a.media_dir), Path(a.cache),
                            a.same, a.differ, log=lambda m: print(m, file=sys.stderr))
    else:
        if len(a.videos) < 2:
            ap.error("give at least two mp4 paths")
        ref = Path(a.videos[0])
        rows = [{"task": "", "a": ref.name, "b": Path(v).name, **compare_files(ref, Path(v), a.same, a.differ)}
                for v in a.videos[1:]]
    print(json.dumps(rows, indent=1) if a.json else render(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
