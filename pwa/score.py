"""pwa score / preview: run the official Rubric Verifier as subprocesses."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .aggregate import valid_review
from .core import PLAYWORLD, ROOT, PwaError, exp_dir, log, read_json, video_path

WORLD_MODEL = "world_model"  # neutral name: it is shown to the judge, keep it constant across experiments
TIMEOUT_S = 1800
OFFICIAL_MODEL = "gemini-3.1-pro-preview"
THINKING_LEVELS = ("minimal", "low", "medium", "high")


@dataclass(frozen=True)
class Judge:
    """A screening judge: same upstream verifier, another Gemini model (and optionally a thinking level).
    Its scores live in runs/EXP/eval-<slug>/ and never reach eval/, report.json or results/experiments.csv."""
    model: str
    thinking: str | None = None

    def __post_init__(self):
        if not self.model.strip():
            raise PwaError("--judge-model must not be empty")
        if self.thinking is not None and self.thinking not in THINKING_LEVELS:
            raise PwaError(f"--judge-thinking must be one of {', '.join(THINKING_LEVELS)}")

    @property
    def slug(self) -> str:
        s = re.sub(r"[^A-Za-z0-9._-]", "-", self.model)
        return f"{s}-think-{self.thinking}" if self.thinking else s

    @property
    def label(self) -> str:
        name = self.model + (f", thinking {self.thinking}" if self.thinking else "")
        return f"screening judge: {name}, not comparable to the leaderboard"


def judge_of(a) -> Judge | None:
    """Judge from parsed args (--judge-model / --judge-thinking), or None for the official judge."""
    model = getattr(a, "judge_model", None)
    thinking = getattr(a, "judge_thinking", None)
    if not model:
        if thinking:
            raise PwaError("--judge-thinking needs --judge-model (the official judge runs at upstream settings)")
        return None
    return Judge(model, thinking)


def eval_dir(exp: str, dry: bool = False, judge: Judge | None = None) -> Path:
    if dry:
        return exp_dir(exp) / "eval_dry"  # no model is called; shared by every judge
    return exp_dir(exp) / (f"eval-{judge.slug}" if judge else "eval")


def passes_present(exp: str, judge: Judge | None = None) -> list[int]:
    d = eval_dir(exp, judge=judge)
    return sorted(int(p.name[4:]) for p in d.glob("pass*") if p.name[4:].isdigit()) if d.is_dir() else []


def verifier_cmd(mode: str, info: dict, video: Path, out: Path, dry: bool,
                 sampling_dir: Path | None = None, context: Path | None = None,
                 judge: Judge | None = None) -> list[str]:
    module = "pwa.judge_shim" if judge and judge.thinking else "metrics.vqa.score"
    model = judge.model if judge else os.environ.get("GEMINI_MODEL", OFFICIAL_MODEL)
    cmd = [sys.executable, "-m", module, "--mode", mode, "--dataset", info["dataset"],
           "--task-id", info["task_id"], "--video", str(video), "--world-model", WORLD_MODEL,
           "--model", model, "--output", str(out)]
    if mode == "score" and Path(info["image"]).is_file():
        cmd += ["--reference-image", info["image"]]
    if sampling_dir:
        cmd += ["--sampling-output-dir", str(sampling_dir)]
    if context:
        cmd += ["--context-output", str(context)]
    return cmd + (["--dry-run"] if dry else [])


def verifier_env(judge: Judge | None = None) -> dict:
    paths = [str(PLAYWORLD), os.environ.get("PYTHONPATH")]
    env = {k: v for k, v in os.environ.items() if k != "PWA_JUDGE_THINKING"}
    if judge and judge.thinking:  # pwa.judge_shim must be importable from the PlayWorld cwd
        paths.insert(1, str(ROOT))
        env["PWA_JUDGE_THINKING"] = judge.thinking
    return {**env, "PYTHONPATH": os.pathsep.join(filter(None, paths))}


def run_verifier(cmd: list[str], err_path: Path, retries: int, judge: Judge | None = None) -> bool:
    env = verifier_env(judge)
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(cmd, cwd=PLAYWORLD, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
            ok, msg = r.returncode == 0, r.stderr[-4000:]
        except subprocess.TimeoutExpired:
            ok, msg = False, f"timeout after {TIMEOUT_S}s"
        if ok:
            err_path.unlink(missing_ok=True)
            return True
        err_path.parent.mkdir(parents=True, exist_ok=True)
        err_path.write_text(f"attempt {attempt + 1}\n$ {' '.join(cmd)}\n{msg}\n")
        if attempt < retries:
            time.sleep(5 * (attempt + 1))
    return False


def done(path: Path, dry: bool) -> bool:
    res = read_json(path)
    return isinstance(res, dict) and (dry or res.get("score") is not None)


def needs_gate(info: dict, score_result: dict | None, dry: bool) -> bool:
    """GC always needs gate mode. Out-of-sight OE normally embeds its check in the score
    result; gate only as a fallback. IF third-person must be embedded: upstream gate_kind()
    compares perspective to 'third-person' but the dataset says 'third person', so gate
    mode raises for IF."""
    if info["family"] == "gc":
        return True
    if info["family"] == "outsight":
        if dry:
            return True
        emb = (score_result or {}).get("oeInstructionFollowingCheck") or (score_result or {}).get("oe_instruction_following_check")
        return valid_review(emb) is None
    return False


def score_task(exp: str, info: dict, k: int, a, judge: Judge | None = None) -> list[dict]:
    d = eval_dir(exp, a.dry_run, judge) / f"pass{k}"
    video = video_path(exp, info["task_id"])
    events = []
    for mode in ("score", "gate"):
        out = d / f"{info['task_id']}_{mode}.json"
        if mode == "gate":
            sres = (read_json(d / f"{info['task_id']}_score.json") or {}).get("score")
            if not needs_gate(info, sres, a.dry_run):
                continue
        if done(out, a.dry_run) and not a.force:
            events.append({"task_id": info["task_id"], "pass": k, "mode": mode, "status": "skipped"})
            continue
        ok = run_verifier(verifier_cmd(mode, info, video, out, a.dry_run, judge=judge), out.with_suffix(".err"),
                          a.retries, judge)
        events.append({"task_id": info["task_id"], "pass": k, "mode": mode, "status": "ok" if ok else "failed"})
        log(f"[pwa] pass{k} {info['task_id']} {mode}: {'ok' if ok else 'FAILED (see ' + str(out.with_suffix('.err')) + ')'}")
        if not ok and mode == "score":
            break
    return events


def score(a, sel: list[dict]) -> dict:
    judge = judge_of(a)
    if judge:
        log(f"[pwa] {judge.label}; writing {eval_dir(a.exp, a.dry_run, judge)}")
    if not a.dry_run and not os.environ.get("GEMINI_API_KEY"):
        raise PwaError("GEMINI_API_KEY is not set (config/env.sh); use --dry-run to test sampling only")
    with_video = [t for t in sel if video_path(a.exp, t["task_id"]).is_file()]
    no_video = [t["task_id"] for t in sel if t not in with_video]
    if no_video:
        log(f"[pwa] {len(no_video)} tasks have no video (count as 1.0): {' '.join(no_video)}")
    missing_img = [t["task_id"] for t in with_video if not Path(t["image"]).is_file()]
    if missing_img:
        log(f"[pwa] WARNING: no reference image for {len(missing_img)} tasks (scored without it): "
            f"{' '.join(missing_img)}. Run ./setup.sh to fetch images.")
    jobs = [(t, k) for k in range(1, a.passes + 1) for t in with_video]
    events: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
        futs = [pool.submit(score_task, a.exp, t, k, a, judge) for t, k in jobs]
        for f in as_completed(futs):
            events += f.result()
    failed = [e for e in events if e["status"] == "failed"]
    summary = {"exp": a.exp, "dry_run": a.dry_run, "passes": a.passes, "tasks": len(with_video),
               "no_video": no_video, "ran": sum(e["status"] == "ok" for e in events),
               "skipped": sum(e["status"] == "skipped" for e in events), "failed": failed,
               "dir": str(eval_dir(a.exp, a.dry_run, judge)),
               "judge": {"model": judge.model, "thinking": judge.thinking, "slug": judge.slug} if judge else None}
    log(f"[pwa] score {a.exp}: ran={summary['ran']} skipped={summary['skipped']} failed={len(failed)}")
    return summary


def preview(exp: str, info: dict) -> Path:
    video = video_path(exp, info["task_id"])
    if not video.is_file():
        raise PwaError(f"no video {video}")
    d = exp_dir(exp) / "preview" / info["task_id"]
    d.mkdir(parents=True, exist_ok=True)
    cmd = verifier_cmd("score", info, video, d / "dry_run.json", True, sampling_dir=d, context=d / "context.json")
    if not run_verifier(cmd, d / "error.txt", 0):
        raise PwaError(f"verifier dry run failed; see {d / 'error.txt'}")
    return d
