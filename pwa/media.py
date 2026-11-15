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

LICENSE = "CC BY-NC-SA 4.0"  # license of the published scene videos
REPO_URL = "https://github.com/benceruleanlu/playworld-advancement"

# Model attribution by runner, from the run's meta.json, so a release never credits the wrong model.
MODELS = {
    "lingbot_world2": {"name": "LingBot-World v2", "org": "Robbyant Team", "url": "https://github.com/Robbyant/lingbot-world-v2",
                       "paper": "arXiv:2607.07534", "license": "CC BY-NC-SA 4.0",
                       "note": "Its released weights and modules run unchanged; our session wrapper "
                               "(adapters/lingbot_world2/session.py) re-implements its causal sampling loop."},
    "sana": {"name": "SANA-WM", "org": "NVIDIA", "url": "https://github.com/NVlabs/Sana", "paper": "", "license": "",
             "note": "Run through the PlayWorld harness's SANA-WM engine; see the upstream repository for its license."},
    "matrix_game3": {"name": "Matrix-Game 3.0", "org": "Skywork AI", "url": "https://github.com/SkyworkAI/Matrix-Game",
                     "paper": "", "license": "", "note": "See the upstream repository for its license."},
}


def is_pipeline_test(runner: str) -> bool:
    return "fake_runner" in (runner or "")


def model_for(runner: str) -> dict:
    """Attribution for the model behind a runner name or path (e.g. lingbot_world2_1p3b -> LingBot-World v2)."""
    p = Path(runner or "")
    parts = [p.stem, *p.parts]  # a name ("lingbot_world2_1p3b") or a path ("adapters/lingbot_world2_1p3b/run.py")
    for key in sorted(MODELS, key=len, reverse=True):
        if any(x == key or x.startswith(key + "_") for x in parts):
            return dict(MODELS[key], runner=runner)
    return {"name": runner or "unknown runner", "org": "", "url": "", "paper": "", "license": "", "note": "", "runner": runner}


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
    meta = read_meta(exp)
    if is_pipeline_test(meta.get("runner", "")):
        log(f"[pwa] media {exp}: pipeline test ({meta.get('runner')}), nothing to publish")
        return None
    rows = {r["task_id"]: r for r in failures(exp, sel, all_tasks=True)}
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
           "git_sha": meta.get("git_sha") or "", "runner": meta.get("runner") or "", "model": model_for(meta.get("runner") or ""),
           "license": LICENSE, "scored": any(x["mean"] is not None for x in tasks), "tasks": tasks}
    (out_dir / f"{exp}.json").write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
    (out_dir / "RELEASE_NOTES.md").write_text(release_notes(man))
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


def release_notes(man: dict) -> str:
    """Markdown for the run-EXP release: provenance, attribution for the run's own model, license, removal requests."""
    m, exp = man["model"], man["exp"]
    who = ", ".join(x for x in (m["org"], m["paper"]) if x)
    model = f"[{m['name']}]({m['url']})" if m["url"] else m["name"]
    lic = f", {m['license']}" if m["license"] else ""
    note = f" {m['note']}" if m["note"] else ""
    sha = f" (commit {man['git_sha'][:12]})" if man.get("git_sha") else ""
    if man.get("scored", True):
        head = (f"Rollouts from experiment `{exp}`{sha}, scored by the PlayWorld verifier (Gemini 3.1 Pro). "
                f"Per-task scores and the verifier's reasons: [results/reports/{exp}.md]({REPO_URL}/blob/main/results/reports/{exp}.md). "
                f"Browse them on the [results site](https://benceruleanlu.github.io/playworld-advancement/#scenes).\n\n")
    else:
        # no task has a score yet (e.g. clips published right after generation): claim no scoring, link no report
        head = f"Unscored rollouts from experiment `{exp}`{sha}. No verifier scores were available when these clips were published.\n\n"
    return (head +
            "**Attribution**\n"
            f"- Generated with {model}{f' ({who})' if who else ''}{lic}, runner `{m['runner']}`.{note}\n"
            "- Each rollout starts from a [PlayWorld](https://github.com/kxding/PlayWorld) task image (Ding et al., arXiv:2608.13552; "
            "data: [jocelynd/playworld-bench](https://huggingface.co/datasets/jocelynd/playworld-bench)). Task images come from "
            "Pexels and web image search and remain subject to their sources' terms.\n\n"
            f"**License:** these videos are released under [{LICENSE}](https://creativecommons.org/licenses/by-nc-sa/4.0/), "
            "non-commercial use only. Changes: re-encoded to 480p H.264 without audio; posters are one frame of each rollout.\n\n"
            f"**Removal requests:** [open an issue]({REPO_URL}/issues/new?title=Scene+removal+request).\n")
