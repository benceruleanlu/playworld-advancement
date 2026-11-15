"""pwa media: small web copies of a run's rollouts plus a manifest the results site reads.

The workflow uploads the clips and posters to a GitHub Release (run-EXP) and commits the manifest to
results/media/EXP.json on main, with results/media/index.json listing every run that has scenes. Every run that
generated videos publishes them (scored, gen-only, capped smoke, screening judge; never a pipeline test); the
manifest's `scored` and `labels` say which, and SCENES.md lists every task with a link that plays it on the site.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode

from .core import PwaError, cap_label, chunk_cap, log, now, read_meta, video_path
from .report import failures
from .score import passes_present

LICENSE = "CC BY-NC-SA 4.0"  # license of the published scene videos
REPO_URL = "https://github.com/benceruleanlu/playworld-advancement"
SITE_URL = "https://benceruleanlu.github.io/playworld-advancement/"

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


def run_labels(meta: dict, scored: bool, screening: str = "") -> list[str]:
    """Badges for a run's scenes: why its clips are not an official score. Empty for an official scored run."""
    labels = []
    cap = chunk_cap(meta)
    if cap:
        labels.append(cap_label(cap))
    if not scored:
        labels.append(f"not scored by the official judge; screened by {screening} (screening scores are not shown here)"
                      if screening else "not scored")
    if meta.get("action_source") == "dataset":
        labels.append("replayed dataset moves (open loop), A/B only")
    return labels


def player_model(runner_args: list[str]) -> str:
    """The AI player named by --agent-model in the runner args (the workflow passes it there), else ""."""
    out = ""
    for i, x in enumerate(runner_args or []):
        if x == "--agent-model" and i + 1 < len(runner_args):
            out = runner_args[i + 1]
        elif x.startswith("--agent-model="):
            out = x.split("=", 1)[1]
    return out


def watch_url(site_url: str, exp: str, task_id: str | None = None) -> str:
    """Deep link into the site's Scenes view: the run, and with task_id that one rollout, ready to play."""
    q = {"scenes": exp, **({"scene": task_id} if task_id else {})}
    return f"{site_url.rstrip('/')}/?{urlencode(q)}#scenes"


def build(exp: str, sel: list[dict], out_dir: Path, base_url: str, release_url: str, height: int = 480,
          screening: str = "", report_name: str = "", site_url: str = SITE_URL,
          extra_labels: list[str] | None = None) -> dict | None:
    """Encode every task video of EXP into out_dir and write out_dir/EXP.json, RELEASE_NOTES.md and SCENES.md.
    Asset URLs are base_url + file name. Works for unscored runs too (gen-only, capped smoke, screening judge):
    the manifest then says so in `scored` and `labels`, and its tasks carry no score. `screening` names the
    screening judge of a screening run; its scores never enter the manifest. `extra_labels` are appended to the
    labels (the arms workflow adds "arm i/N of EXP: ARGS")."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if base_url and not base_url.endswith("/"):
        base_url += "/"
    meta = read_meta(exp)
    if is_pipeline_test(meta.get("runner", "")):
        log(f"[pwa] media {exp}: pipeline test ({meta.get('runner')}), nothing to publish")
        return None
    scored = bool(passes_present(exp))
    rows = {r["task_id"]: r for r in failures(exp, sel, all_tasks=True)} if scored else {}
    tasks = []
    for t in sel:
        tid = t["task_id"]
        r = rows.get(tid, {})
        src = video_path(exp, tid)
        video = poster = None
        if src.is_file():
            encode(src, out_dir / f"{tid}.mp4", out_dir / f"{tid}.jpg", height)
            video, poster = base_url + f"{tid}.mp4", base_url + f"{tid}.jpg"
        status = r.get("status") or (["not scored"] if video else ["missing"])
        tasks.append({"task_id": tid, "family": t["family"], "mean": r.get("mean") if scored else None, "status": status,
                      "reason": r.get("reason", "") if scored else "", "video": video, "poster": poster})
    cap = chunk_cap(meta)
    args = [str(x) for x in meta.get("runner_args") or []]
    man = {"exp": exp, "release_tag": f"run-{exp}", "release_url": release_url, "generated": now(),
           "git_sha": meta.get("git_sha") or "", "branch": meta.get("branch") or "", "runner": meta.get("runner") or "",
           "action_source": meta.get("action_source") or "", "scored": scored, "max_chunks": cap,
           # shown under each clip in the site's Compare view: runner flags, AI player, the run's notes
           "runner_args": args, "player_model": player_model(args), "notes": meta.get("notes") or "",
           "labels": run_labels(meta, scored, screening) + [x for x in extra_labels or [] if x], "report": report_name or f"{exp}.md",
           "model": model_for(meta.get("runner") or ""), "license": LICENSE, "tasks": tasks}
    (out_dir / f"{exp}.json").write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
    (out_dir / "RELEASE_NOTES.md").write_text(release_notes(man))
    (out_dir / "SCENES.md").write_text(scenes_md(man, site_url))
    n = sum(1 for x in tasks if x["video"])
    log(f"[pwa] media {exp}: {n}/{len(tasks)} clips -> {out_dir}" + (f" ({'; '.join(man['labels'])})" if man["labels"] else ""))
    return man


def compare_url(site_url: str, task_id: str, exps: list[str]) -> str:
    """Deep link into the site's Compare view: task_id from up to three runs (a = baseline, then b, c)."""
    q = {"compare": task_id, **dict(zip("abc", exps[:3]))}
    return f"{site_url.rstrip('/')}/?{urlencode(q)}#compare-clips"


def arms_md(site_url: str, mans: list[dict]) -> str:
    """Markdown for the arms step summary: per task a play link for every arm with a clip and, when 2+ arms have
    one, compare links with the first such arm (arm 1 unless it has no clip) as the baseline a= and the others as
    b= / c=, two per link (the Compare view has three slots). `mans` are the arms' manifests in arm order."""
    tasks: dict[str, list[str]] = {}
    for m in mans:
        for t in m["tasks"]:
            row = tasks.setdefault(t["task_id"], [])
            if t.get("video"):
                row.append(m["exp"])
    out = ["### Arm scenes on the results site", "",
           "Live once the arm manifests are on main. **play** opens one arm's rollout in the site's Scenes view; "
           "**compare** plays the arms side by side, the first arm as the baseline.", "",
           "| task | play | compare |", "|---|---|---|"]
    for tid, exps in tasks.items():
        play = " · ".join(f"[{e}]({watch_url(site_url, e, tid)})" for e in exps) or "no video"
        groups = [[exps[0], *exps[1:][i:i + 2]] for i in range(0, len(exps) - 1, 2)]
        cmp_ = " · ".join(f"[{' vs '.join(g)}]({compare_url(site_url, tid, g)})" for g in groups) or "-"
        out.append(f"| {tid} | {play} | {cmp_} |")
    return "\n".join(out) + "\n"


def _index_with(data: dict, man: dict) -> dict:
    runs = [r for r in data.get("runs", []) if r.get("exp") != man["exp"]]
    runs.append({"exp": man["exp"], "generated": man["generated"], "n_tasks": len(man["tasks"]), "release_url": man["release_url"],
                 # manifests from before these fields were official scored runs
                 "scored": man.get("scored", True), "labels": man.get("labels", [])})
    data["runs"] = sorted(runs, key=lambda r: r.get("generated", ""), reverse=True)
    return data


def update_index(index: Path, man: dict) -> dict:
    """Add or replace man's run in index.json, newest first."""
    data = _index_with(json.loads(index.read_text()) if index.is_file() else {"runs": []}, man)
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(json.dumps(data, indent=1) + "\n")
    return data


def is_official(man: dict | None) -> bool:
    """True for an official scored manifest (manifests from before `scored` existed were official scored runs)."""
    return bool(man) and bool(man.get("scored", True))


def would_downgrade(existing: dict | None, new: dict) -> bool:
    """True if publishing `new` would replace an official scored manifest with an unscored one, e.g. a later
    screening-judge or gen-only run of the same EXP, which never sees the official eval/ dir. Such a publish is
    skipped so the official means, reasons and release notes survive."""
    return is_official(existing) and not is_official(new)


def to_main(media_dir: Path, man_path: Path) -> bool:
    """Copy the manifest at man_path to media_dir/EXP.json and add it to media_dir/index.json, all or nothing:
    everything is read and checked before anything is written, so a malformed file never leaves a manifest
    without an index entry. Returns False (writes nothing) when it would downgrade an official manifest."""
    man = json.loads(man_path.read_text())
    dest = media_dir / f"{man['exp']}.json"
    existing = json.loads(dest.read_text()) if dest.is_file() else None
    if would_downgrade(existing, man):
        log(f"[pwa] media {man['exp']}: main already has the official scored scenes; not replacing them with an unscored run")
        return False
    index = media_dir / "index.json"
    data = _index_with(json.loads(index.read_text()) if index.is_file() else {"runs": []}, man)
    media_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(json.dumps(man, indent=1, ensure_ascii=False) + "\n")
    index.write_text(json.dumps(data, indent=1) + "\n")
    tmp.replace(dest)
    return True


def _cell(x) -> str:
    return str(x).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def scenes_md(man: dict, site_url: str = SITE_URL) -> str:
    """Markdown for the step summary and results/reports/: every task with a link that plays its rollout."""
    exp = man["exp"]
    out = ["### Scenes", ""]
    labels = "; ".join(man.get("labels") or [])
    if labels:
        out += [f"> **{_cell(labels[0].upper() + labels[1:])}.**", ""]
    n = sum(1 for t in man["tasks"] if t["video"])
    out += [f"[Watch all {n} rollouts of `{exp}` on the results site]({watch_url(site_url, exp)}). "
            "Each **play** link opens that rollout in the site's Scenes view (live once this run's manifest is on main). "
            "The **mp4** link downloads the file: GitHub serves release assets as attachments, not inline.", "",
            "| task | family | score | status | watch |", "|---|---|---:|---|---|"]
    for t in man["tasks"]:
        score = f"{t['mean']:.2f}" if isinstance(t.get("mean"), (int, float)) else "-"
        watch = f"[play]({watch_url(site_url, exp, t['task_id'])}) · [mp4]({t['video']})" if t["video"] else "no video"
        out.append(f"| {t['task_id']} | {t['family']} | {score} | {_cell(', '.join(t['status']))} | {watch} |")
    return "\n".join(out) + "\n"


def release_notes(man: dict) -> str:
    """Markdown for the run-EXP release: provenance, attribution for the run's own model, license, removal requests."""
    m, exp = man["model"], man["exp"]
    who = ", ".join(x for x in (m["org"], m["paper"]) if x)
    model = f"[{m['name']}]({m['url']})" if m["url"] else m["name"]
    lic = f", {m['license']}" if m["license"] else ""
    note = f" {m['note']}" if m["note"] else ""
    sha = f" (commit {man['git_sha'][:12]})" if man.get("git_sha") else ""
    report = f"{REPO_URL}/blob/main/results/reports/{man.get('report') or exp + '.md'}"
    if man.get("scored", True):
        head = (f"Rollouts from experiment `{exp}`{sha}, scored by the PlayWorld verifier (Gemini 3.1 Pro). "
                f"Per-task scores and the verifier's reasons: [results/reports/{man.get('report') or exp + '.md'}]({report}). ")
    else:
        head = (f"Rollouts from experiment `{exp}`{sha}. Not scored by the official PlayWorld verifier. "
                f"Task list: [results/reports/{man.get('report') or exp + '.md'}]({report}). ")
    labels = "".join(f"- {lab}\n" for lab in man.get("labels") or [])
    return (head + f"Watch them on the [results site]({watch_url(SITE_URL, exp)}).\n\n"
            + (f"**Labels**\n{labels}\n" if labels else "")
            + "**Attribution**\n"
            f"- Generated with {model}{f' ({who})' if who else ''}{lic}, runner `{m['runner']}`.{note}\n"
            "- Each rollout starts from a [PlayWorld](https://github.com/kxding/PlayWorld) task image (Ding et al., arXiv:2608.13552; "
            "data: [jocelynd/playworld-bench](https://huggingface.co/datasets/jocelynd/playworld-bench)). Task images come from "
            "Pexels and web image search and remain subject to their sources' terms.\n\n"
            f"**License:** these videos are released under [{LICENSE}](https://creativecommons.org/licenses/by-nc-sa/4.0/), "
            "non-commercial use only. Changes: re-encoded to 480p H.264 without audio; posters are one frame of each rollout.\n\n"
            f"**Removal requests:** [open an issue]({REPO_URL}/issues/new?title=Scene+removal+request).\n")


def _main(argv: list[str]) -> int:
    """Workflow helpers (no dataset needed):
    python -m pwa.media to-main MEDIA_DIR MANIFEST   publish MANIFEST into MEDIA_DIR (exit 0 also when skipped)
    python -m pwa.media keeps-official MAIN_MANIFEST NEW_MANIFEST   exit 0 if NEW would downgrade MAIN, else 1
    python -m pwa.media arms-md SITE_URL MANIFEST...   play and compare links for arms (arm order), as Markdown"""
    if len(argv) >= 2 and argv[0] == "arms-md":
        print(arms_md(argv[1], [json.loads(Path(x).read_text()) for x in argv[2:]]), end="")
        return 0
    if len(argv) == 3 and argv[0] == "to-main":
        to_main(Path(argv[1]), Path(argv[2]))
        return 0
    if len(argv) == 3 and argv[0] == "keeps-official":
        try:
            main_man = json.loads(Path(argv[1]).read_text()) if Path(argv[1]).is_file() and Path(argv[1]).stat().st_size else None
            return 0 if would_downgrade(main_man, json.loads(Path(argv[2]).read_text())) else 1
        except (OSError, ValueError) as e:  # cannot tell: keep whatever is published
            print(f"keeps-official: {e}", file=sys.stderr)
            return 0
    print(_main.__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
