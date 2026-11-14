"""pwa media: small web copies of a run's rollouts plus a manifest the results site reads.

The workflow uploads the clips and posters to a GitHub Release (run-EXP) and commits the manifest to
results/media/EXP.json on main, with results/media/index.json listing every run that has scenes.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .core import PwaError, log, now, read_meta, video_path
from .report import failures

LICENSE = "CC BY-NC-SA 4.0"


def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise PwaError("pwa media needs ffmpeg on PATH (or the imageio-ffmpeg package)") from e


def encode(src: Path, mp4: Path, jpg: Path, height: int = 480) -> None:
    """H.264 at `height` px, no audio, moov atom first so browsers can start playing before the end arrives."""
    ff = ffmpeg_exe()
    scale = f"scale=-2:'min({height},ih)'"
    runs = [
        [ff, "-y", "-loglevel", "error", "-i", str(src), "-an", "-vf", scale, "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(mp4)],
        # a representative frame, not the first one (which is the task's input image)
        [ff, "-y", "-loglevel", "error", "-i", str(src), "-vf", f"thumbnail,{scale}", "-frames:v", "1", "-q:v", "4", str(jpg)],
    ]
    for cmd in runs:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise PwaError(f"ffmpeg failed on {src}: {r.stderr.strip()[-300:]}")


def build(exp: str, sel: list[dict], out_dir: Path, base_url: str, release_url: str, height: int = 480) -> dict:
    """Encode every task video of EXP into out_dir and write out_dir/EXP.json. Asset URLs are base_url + file name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if base_url and not base_url.endswith("/"):
        base_url += "/"
    rows = {r["task_id"]: r for r in failures(exp, sel, all_tasks=True)}
    meta = read_meta(exp)
    tasks = []
    for t in sel:
        tid = t["task_id"]
        r = rows.get(tid, {})
        src = video_path(exp, tid)
        video = poster = None
        if src.is_file():
            encode(src, out_dir / f"{tid}.mp4", out_dir / f"{tid}.jpg", height)
            video, poster = base_url + f"{tid}.mp4", base_url + f"{tid}.jpg"
        tasks.append({"task_id": tid, "family": t["family"], "mean": r.get("mean"), "status": r.get("status") or ["missing"],
                      "reason": r.get("reason", ""), "video": video, "poster": poster})
    man = {"exp": exp, "release_tag": f"run-{exp}", "release_url": release_url, "generated": now(),
           "git_sha": meta.get("git_sha") or "", "runner": meta.get("runner") or "", "license": LICENSE, "tasks": tasks}
    (out_dir / f"{exp}.json").write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
    n = sum(1 for x in tasks if x["video"])
    log(f"[pwa] media {exp}: {n}/{len(tasks)} clips -> {out_dir}")
    return man


def update_index(index: Path, man: dict) -> dict:
    """Add or replace man's run in index.json, newest first."""
    data = json.loads(index.read_text()) if index.is_file() else {"runs": []}
    runs = [r for r in data.get("runs", []) if r.get("exp") != man["exp"]]
    runs.append({"exp": man["exp"], "generated": man["generated"], "n_tasks": len(man["tasks"]), "release_url": man["release_url"]})
    data["runs"] = sorted(runs, key=lambda r: r.get("generated", ""), reverse=True)
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(data, indent=1) + "\n")
    return data
