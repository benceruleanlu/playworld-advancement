"""pwa score / preview: run the official Rubric Verifier as subprocesses."""
from __future__ import annotations

import json
import math
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


PROVIDERS = ("gemini", "openai")
# `--judge openai` with no --judge-model: a vision-capable non-reasoning chat model (it takes upstream's
# temperature 0.1). Override per call with --judge-model, or for every call with PWA_PROXY_JUDGE_MODEL.
PROXY_DEFAULT_MODEL = "gpt-4.1"


def proxy_default_model() -> str:
    return (os.environ.get("PWA_PROXY_JUDGE_MODEL") or "").strip() or PROXY_DEFAULT_MODEL


@dataclass(frozen=True)
class Judge:
    """A screening judge: the same upstream verifier with another model (and optionally a thinking level).
    provider "gemini" calls Gemini as upstream does; "openai" runs upstream through pwa.judge_shim with its
    Gemini client swapped for an OpenAI-compatible chat client (same prompts, contact sheets, parsing).
    Its scores live in runs/EXP/eval-<slug>/ and never reach eval/, report.json or results/experiments.csv."""
    model: str
    thinking: str | None = None
    provider: str = "gemini"

    def __post_init__(self):
        if not self.model.strip():
            raise PwaError("--judge-model must not be empty")
        if self.thinking is not None and self.thinking not in THINKING_LEVELS:
            raise PwaError(f"--judge-thinking must be one of {', '.join(THINKING_LEVELS)}")
        if self.provider not in PROVIDERS:
            raise PwaError(f"judge provider must be one of {', '.join(PROVIDERS)}")

    @classmethod
    def parse(cls, spec: str, thinking: str | None = None) -> "Judge":
        """`[openai:|gemini:]MODEL[:THINKING]`. No prefix = Gemini (unchanged behaviour); `openai:` = the
        OpenAI-compatible chat API. A trailing `:minimal|low|medium|high` is the thinking level (Gemini
        thinking_level, OpenAI reasoning_effort); --judge-thinking may give it instead, not both."""
        s = spec.strip()
        head, sep, tail = s.rpartition(":")
        if sep and tail in THINKING_LEVELS:
            if thinking and thinking != tail:
                raise PwaError(f"judge {spec!r}: thinking given twice ({tail} and --judge-thinking {thinking})")
            s, thinking = head, tail
        provider = "gemini"
        for p in PROVIDERS:
            if s.startswith(p + ":"):
                provider, s = p, s[len(p) + 1:]
                break
        return cls(s, thinking, provider)

    @property
    def spec(self) -> str:
        return ("openai:" if self.provider == "openai" else "") + self.model + (f":{self.thinking}" if self.thinking else "")

    @property
    def upstream_model(self) -> str:
        """--model passed to upstream; recorded as `gemini_model` in each result. The shim strips `openai:`."""
        return f"openai:{self.model}" if self.provider == "openai" else self.model

    @property
    def needs_shim(self) -> bool:
        return self.provider == "openai" or bool(self.thinking)

    @property
    def slug(self) -> str:
        s = re.sub(r"[^A-Za-z0-9._-]", "-", self.upstream_model)
        return f"{s}-think-{self.thinking}" if self.thinking else s

    @property
    def name(self) -> str:
        return self.upstream_model + (f", thinking {self.thinking}" if self.thinking else "")

    @property
    def proxy(self) -> bool:
        """An OpenAI judge stands in for Gemini while Gemini cannot be called: a proxy, uncalibrated."""
        return self.provider == "openai"

    @property
    def label(self) -> str:
        if self.proxy:
            return f"PROXY JUDGE ({self.name}), not comparable to the leaderboard"
        return f"screening judge: {self.name}, not comparable to the leaderboard"


def judges_of(a) -> list[Judge]:
    """Screening judges from parsed args (--judge-model, repeatable; --judge-thinking for a single judge).
    Empty list = the official judge."""
    models = getattr(a, "judge_model", None) or []
    if isinstance(models, str):
        models = [models]
    if getattr(a, "judge", None) == "openai":  # proxy judge: every model is an openai: one
        models = [proxy_spec(m) for m in models] or ["openai:" + proxy_default_model()]
    thinking = getattr(a, "judge_thinking", None)
    if not models:
        if thinking:
            raise PwaError("--judge-thinking needs --judge-model (the official judge runs at upstream settings)")
        return []
    if thinking and len(models) > 1:
        raise PwaError("--judge-thinking applies to one judge; in a panel write MODEL:THINKING per --judge-model")
    judges = [Judge.parse(m, thinking) for m in models]
    slugs = [j.slug for j in judges]
    if len(set(slugs)) != len(slugs):
        raise PwaError(f"duplicate screening judge in {' '.join(models)}")
    return judges


def proxy_spec(model: str) -> str:
    """`--judge openai --judge-model M`: M with the openai: prefix (added when missing)."""
    m = model.strip()
    if m.startswith("gemini:"):
        raise PwaError(f"--judge openai with --judge-model {model!r}: drop --judge or the gemini: prefix")
    return m if m.startswith("openai:") else "openai:" + m


def judge_of(a) -> Judge | None:
    """The single judge from parsed args, or None for the official judge. Commands that read one judge."""
    judges = judges_of(a)
    if len(judges) > 1:
        raise PwaError(f"`pwa {getattr(a, 'cmd', '')}` takes one --judge-model (panels: report, cells, judges, score)")
    return judges[0] if judges else None


def eval_dir(exp: str, dry: bool = False, judge: Judge | None = None) -> Path:
    if dry:
        return exp_dir(exp) / "eval_dry"  # no model is called; shared by every judge
    return exp_dir(exp) / (f"eval-{judge.slug}" if judge else "eval")


def passes_present(exp: str, judge: Judge | None = None) -> list[int]:
    d = eval_dir(exp, judge=judge)
    return sorted(int(p.name[4:]) for p in d.glob("pass*") if p.name[4:].isdigit()) if d.is_dir() else []


BACKENDS = ("aistudio", "gcp")
GCP_API_VERSIONS = ("v1", "v1beta1")  # aiplatform.googleapis.com paths; AI Studio's v1beta (workflow default) 404s there


def judge_backend() -> str:
    """Where a Gemini judge is called. "gcp" = Google Cloud's Gemini Enterprise Agent Platform (formerly Vertex AI,
    host aiplatform.googleapis.com): GCP_GEMINI_API_KEY set (a Google Cloud API key, express mode) or
    PWA_JUDGE_BACKEND=gcp (no key: ADC with GOOGLE_CLOUD_PROJECT). Else "aistudio", which is upstream unchanged. Same model either way; the backend is recorded so a row says which API scored it."""
    forced = os.environ.get("PWA_JUDGE_BACKEND", "").strip().lower()
    if forced and forced not in BACKENDS:
        raise PwaError(f"PWA_JUDGE_BACKEND must be one of {', '.join(BACKENDS)}")
    if forced:
        return forced
    return "gcp" if os.environ.get("GCP_GEMINI_API_KEY", "").strip() else "aistudio"


def on_gcp(judge: Judge | None = None) -> bool:
    return judge_backend() == "gcp" and not (judge and judge.provider == "openai")


def gcp_adc(judge: Judge | None = None) -> bool:
    """Google Cloud without an API key: upstream always passes GEMINI_API_KEY explicitly, which the SDK would send as an
    express-mode key, so pwa.judge_shim builds the client from project/location and ADC instead."""
    return on_gcp(judge) and not os.environ.get("GCP_GEMINI_API_KEY", "").strip()


def uses_shim(judge: Judge | None = None) -> bool:
    return bool(judge and judge.needs_shim) or gcp_adc(judge)


def verifier_cmd(mode: str, info: dict, video: Path, out: Path, dry: bool,
                 sampling_dir: Path | None = None, context: Path | None = None,
                 judge: Judge | None = None) -> list[str]:
    module = "pwa.judge_shim" if uses_shim(judge) else "metrics.vqa.score"
    model = judge.upstream_model if judge else os.environ.get("GEMINI_MODEL", OFFICIAL_MODEL)
    cmd = [sys.executable, "-m", module, "--mode", mode, "--dataset", info["dataset"],
           "--task-id", info["task_id"], "--video", str(video), "--world-model", WORLD_MODEL,
           "--model", model, "--output", str(out)]
    if mode == "score" and Path(info["image"]).is_file():
        cmd += ["--reference-image", info["image"]]
    if sampling_dir:
        cmd += ["--sampling-output-dir", str(sampling_dir)]
    if context:
        cmd += ["--context-output", str(context)]
    if not dry and on_gcp(judge):
        # Agent Platform has no Files API (upstream's auto transport uploads above 18 MB). Same sheets, sent inline.
        cmd += ["--evidence-transport", "inline"]
    return cmd + (["--dry-run"] if dry else [])


SHIM_VARS = ("PWA_JUDGE_THINKING", "PWA_JUDGE_PROVIDER", "PWA_JUDGE_GCP_ADC")
# upstream main() exits unless GEMINI_API_KEY is set; an openai: judge never builds a Gemini client
GEMINI_KEY_PLACEHOLDER = "unused-by-openai-judge"
GCP_ADC_PLACEHOLDER = "unused-gcp-adc"


def verifier_env(judge: Judge | None = None) -> dict:
    paths = [str(PLAYWORLD), os.environ.get("PYTHONPATH")]
    env = {k: v for k, v in os.environ.items() if k not in SHIM_VARS}
    if uses_shim(judge):  # pwa.judge_shim must be importable from the PlayWorld cwd
        paths.insert(1, str(ROOT))
        if judge and judge.thinking:
            env["PWA_JUDGE_THINKING"] = judge.thinking
    if judge and judge.provider == "openai":
        env["PWA_JUDGE_PROVIDER"] = "openai"
        env["GEMINI_API_KEY"] = GEMINI_KEY_PLACEHOLDER  # the real Gemini key stays out of this process
    if on_gcp(judge):
        # google-genai reads these even when upstream passes api_key explicitly; an api key with no project/location is
        # express mode on the global endpoint (aiplatform.googleapis.com). USE_ENTERPRISE is the current name (it wins
        # when both are set), USE_VERTEXAI the legacy one older SDKs read.
        env["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"
        env["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
        if env.get("GOOGLE_GENAI_API_VERSION") not in GCP_API_VERSIONS:
            env["GOOGLE_GENAI_API_VERSION"] = "v1beta1"
        if gcp_adc(judge):
            env["PWA_JUDGE_GCP_ADC"] = "1"
            env["GEMINI_API_KEY"] = GCP_ADC_PLACEHOLDER  # upstream main() needs one; the shim never sends it
            env.setdefault("GOOGLE_CLOUD_LOCATION", "global")  # Gemini 3.x previews are served from global only
        else:
            env["GEMINI_API_KEY"] = os.environ["GCP_GEMINI_API_KEY"].strip()
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


def stamp_backend(path: Path, backend: str) -> None:
    """Add judge_backend to a verifier result. Only gcp results carry it; absent = aistudio (upstream as is)."""
    res = read_json(path)
    if isinstance(res, dict):
        res["judge_backend"] = backend
        path.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        if ok and not a.dry_run and on_gcp(judge):
            stamp_backend(out, "gcp")
        events.append({"task_id": info["task_id"], "pass": k, "mode": mode, "status": "ok" if ok else "failed"})
        log(f"[pwa] pass{k} {info['task_id']} {mode}: {'ok' if ok else 'FAILED (see ' + str(out.with_suffix('.err')) + ')'}")
        if not ok and mode == "score":
            break
    return events


def score(a, sel: list[dict]) -> dict:
    """Score with the official judge, or with each --judge-model in turn. One judge (or none) returns its
    summary; a panel returns {"judges": [summary, ...], "failed": [...all failed events...]}."""
    judges = judges_of(a)
    if len(judges) <= 1:
        return score_one(a, sel, judges[0] if judges else None)
    out = [score_one(a, sel, j) for j in judges]
    return {"exp": a.exp, "judges": out, "failed": [e for s in out for e in s["failed"]]}


def check_keys(judge: Judge | None) -> None:
    if judge and judge.provider == "openai":
        from .judge_openai import judge_api  # noqa: PLC0415
        try:
            _, key = judge_api()
        except ValueError as e:
            raise PwaError(str(e)) from e
        if not key:
            raise PwaError("an openai: judge needs JUDGE_API_KEY or PLAYER_API_KEY (config/env.sh)")
    elif gcp_adc(judge):
        if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
            raise PwaError("PWA_JUDGE_BACKEND=gcp without GCP_GEMINI_API_KEY needs GOOGLE_CLOUD_PROJECT and ADC "
                           "(gcloud auth application-default login)")
    elif on_gcp(judge):
        pass  # GCP_GEMINI_API_KEY is set
    elif not os.environ.get("GEMINI_API_KEY"):
        raise PwaError("GEMINI_API_KEY is not set (config/env.sh); use --dry-run to test sampling only")


def _upstream_specs():
    """Upstream's two sampling specs (metrics.vqa.sampling), imported, or None when the submodule is absent."""
    import importlib  # noqa: PLC0415
    if str(PLAYWORLD) not in sys.path:
        sys.path.append(str(PLAYWORLD))
    try:
        mod = importlib.import_module("metrics.vqa.sampling")
        return (mod.PRIMARY_SPEC, mod.DETAIL_SPEC)
    except Exception:  # noqa: BLE001
        return None


def video_seconds(video: Path) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(video)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def estimate_images(info: dict, video: Path, specs=None) -> dict | None:
    """Images one pass sends for one task: upstream's contact sheets per call (primary + detail stream, frames at
    each spec's fps, frames_per_sheet per sheet), the reference image on the score call, and the gate call for
    GC (out-of-sight gates only when the score reply lacks its embedded check; counted as 0 here). An estimate:
    upstream's ffmpeg fps filter may differ by a frame. None when the duration or the specs are unknown."""
    specs = specs or _upstream_specs()
    secs = video_seconds(video) if specs else None
    if not specs or secs is None:
        return None
    sheets = sum(math.ceil(max(1, math.ceil(secs * sp.fps)) / sp.frames_per_sheet) for sp in specs)
    ref = 1 if Path(info["image"]).is_file() else 0
    gate = sheets if info["family"] == "gc" else 0
    return {"score": sheets + ref, "gate": gate, "total": sheets + ref + gate, "calls": 1 + (gate > 0)}


def cost_guard(sel: list[dict], exp: str, passes: int, judge: Judge) -> int | None:
    """Print the estimated image count per task and in total before any proxy call. Returns the total."""
    specs = _upstream_specs()
    total, calls, unknown = 0, 0, []
    detail = os.environ.get("JUDGE_IMAGE_DETAIL", "high")
    log(f"[pwa] cost guard ({judge.name}, image detail {detail}): estimated images per task per pass")
    for t in sel:
        est = estimate_images(t, video_path(exp, t["task_id"]), specs)
        if est is None:
            unknown.append(t["task_id"])
            continue
        total, calls = total + est["total"], calls + est["calls"]
        log(f"[pwa]   {t['task_id']}: ~{est['total']} images in {est['calls']} call(s) "
            f"(score {est['score']}" + (f" + gate {est['gate']}" if est["gate"] else "") + ")")
    if unknown:
        log(f"[pwa]   no estimate (no ffprobe duration or upstream specs): {' '.join(unknown)}")
    log(f"[pwa] cost guard: ~{total * passes} images in ~{calls * passes} calls over {len(sel) - len(unknown)} "
        f"tasks x {passes} passes (retries not counted)")
    return total * passes


def score_one(a, sel: list[dict], judge: Judge | None) -> dict:
    if judge:
        log(f"[pwa] {judge.label}; writing {eval_dir(a.exp, a.dry_run, judge)}")
    if not a.dry_run:
        check_keys(judge)
        if not (judge and judge.provider == "openai"):
            b = judge_backend()
            log(f"[pwa] judge backend: {b}" + (" (Gemini Enterprise Agent Platform, formerly Vertex AI)" if b == "gcp" else ""))
    with_video = [t for t in sel if video_path(a.exp, t["task_id"]).is_file()]
    no_video = [t["task_id"] for t in sel if t not in with_video]
    if no_video:
        log(f"[pwa] {len(no_video)} tasks have no video (count as 1.0): {' '.join(no_video)}")
    missing_img = [t["task_id"] for t in with_video if not Path(t["image"]).is_file()]
    if missing_img:
        log(f"[pwa] WARNING: no reference image for {len(missing_img)} tasks (scored without it): "
            f"{' '.join(missing_img)}. Run ./setup.sh to fetch images.")
    if judge and judge.proxy and not a.dry_run and with_video:
        cost_guard(with_video, a.exp, a.passes, judge)
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
               "judge_backend": None if a.dry_run or (judge and judge.provider == "openai") else judge_backend(),
               "judge": {"model": judge.model, "thinking": judge.thinking, "provider": judge.provider,
                         "slug": judge.slug} if judge else None}
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
