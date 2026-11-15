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
    elif getattr(a, "judge", None) == "gemini":  # an explicit gemini request never runs an OpenAI judge
        bad = [m for m in models if m.strip().startswith("openai:")]
        if bad:
            raise PwaError(f"--judge gemini with --judge-model {bad[0]!r}: drop --judge gemini, or use --judge openai")
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
    if m.startswith("gemini:") or m.startswith("gemini-") or m == "gemini":
        raise PwaError(f"--judge openai with --judge-model {model!r} names a Gemini model: drop --judge openai "
                       "(a plain or gemini: model is a Gemini screening judge)")
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


# stderr note from pwa/judge_openai.py when a model rejects one of upstream's sampling params and the call is
# retried without it; e.g. "[pwa judge] model rejects temperature=0.1; retrying with the provider default"
_REJECTS = re.compile(r"\[pwa judge\] model rejects (temperature|top_p|seed)=")
# params an openai: judge model rejected (by judge slug). Each call is a fresh verifier process, so later calls of
# this run are told up front (JUDGE_API_NO_TEMPERATURE=1) instead of paying a 400 round trip each.
_DROPPED: dict[str, set[str]] = {}


def dropped_params(judge: Judge | None) -> set[str]:
    if not (judge and judge.provider == "openai"):
        return set()
    out = set(_DROPPED.get(judge.slug, set()))
    if os.environ.get("JUDGE_API_NO_TEMPERATURE") == "1":
        out.add("temperature")
    return out


def run_verifier(cmd: list[str], err_path: Path, retries: int, judge: Judge | None = None) -> bool:
    env = verifier_env(judge)
    if "temperature" in dropped_params(judge):
        env["JUDGE_API_NO_TEMPERATURE"] = "1"
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(cmd, cwd=PLAYWORLD, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
            ok, msg = r.returncode == 0, r.stderr[-4000:]
            if judge and judge.provider == "openai":
                for param in _REJECTS.findall(r.stderr):
                    if param not in _DROPPED.setdefault(judge.slug, set()):
                        log(f"[pwa] WARNING: {judge.spec} rejects {param}; this run samples at the provider "
                            f"default, not upstream's setting (recorded as judge_dropped in the results)")
                    _DROPPED[judge.slug].add(param)
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


def stamp_dropped(path: Path, params: set[str]) -> None:
    """Record on an openai: judge result which of upstream's sampling params the model rejected (sampled at the
    provider default instead), so the report can say so."""
    res = read_json(path)
    if isinstance(res, dict):
        res["judge_dropped"] = sorted(params)
        path.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
        if ok and not a.dry_run and dropped_params(judge):
            stamp_dropped(out, dropped_params(judge))
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
            raise PwaError("an openai: judge needs JUDGE_API_KEY, or PLAYER_API_KEY when JUDGE_API_URL is unset or the "
                           "player's URL (config/env.sh)")
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


def _ffmpeg_exe() -> str | None:
    """ffmpeg on PATH (the workflow links imageio-ffmpeg's static build there), else imageio-ffmpeg's own copy."""
    import shutil  # noqa: PLC0415
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # noqa: PLC0415
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def video_seconds(video: Path) -> float | None:
    """Container duration: ffprobe when present, else parsed from `ffmpeg -i` (the Actions runner has no ffprobe)."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(video)], capture_output=True, text=True, timeout=60)
        return float(r.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    exe = _ffmpeg_exe()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "-hide_banner", "-i", str(video)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _DURATION.search(r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None


def image_tokens(w: int, h: int, detail: str = "high") -> int:
    """OpenAI's published tile count for gpt-4o / gpt-4.1 class models: low = 85; high = fit in 2048x2048, then
    shortest side down to 768, then 85 + 170 per 512 px tile. Other model families count differently."""
    if detail == "low":
        return 85
    s = min(1.0, 2048 / max(w, h))
    w, h = w * s, h * s
    s = min(1.0, 768 / min(w, h))
    w, h = w * s, h * s
    return 85 + 170 * math.ceil(w / 512) * math.ceil(h / 512)


def _ref_size(path: str) -> tuple[int, int]:
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(path) as im:
            return im.size
    except Exception:  # noqa: BLE001
        return (1920, 1080)


def estimate_images(info: dict, video: Path, specs=None, detail: str = "high") -> dict | None:
    """Images and image input tokens one pass sends for one task: upstream's contact sheets per call (primary +
    detail stream, frames at each spec's fps, frames_per_sheet per full-size sheet), the reference image on the
    score call, and the gate call for GC (out-of-sight gates only when the score reply lacks its embedded check;
    counted as 0 here). An estimate: upstream's ffmpeg fps filter may differ by a frame, and prompt text is not
    counted. None when the duration or the specs are unknown."""
    specs = specs or _upstream_specs()
    secs = video_seconds(video) if specs else None
    if not specs or secs is None:
        return None
    per = [math.ceil(max(1, math.ceil(secs * sp.fps)) / sp.frames_per_sheet) for sp in specs]
    sheets = sum(per)
    sheet_tok = sum(n * image_tokens(*sp.sheet_size, detail) for n, sp in zip(per, specs))
    ref = 1 if Path(info["image"]).is_file() else 0
    ref_tok = image_tokens(*_ref_size(info["image"]), detail) if ref else 0
    gate = sheets if info["family"] == "gc" else 0
    return {"score": sheets + ref, "gate": gate, "total": sheets + ref + gate, "calls": 1 + (gate > 0),
            "score_tokens": sheet_tok + ref_tok, "gate_tokens": sheet_tok if gate else 0}


# A task whose duration cannot be read counts as this many images per pass (about a 60 s GC rollout, score + gate).
UNKNOWN_TASK_IMAGES = 70
UNKNOWN_TASK_TOKENS = 70 * 1105
# Default cap on the images one `pwa score` sends to a proxy judge (all passes). About 13M image tokens, ~$27 of
# gpt-4.1 input: a dev A/B fits, a 2-pass full 171-task run does not without --max-images.
DEFAULT_MAX_IMAGES = 12000
# USD per 1M input tokens, list prices when this was written; PWA_PROXY_USD_PER_MTOK overrides. Unknown model = no $.
USD_PER_MTOK = {"gpt-4.1": 2.00, "gpt-4o": 2.50}


def max_images(a) -> int:
    v = getattr(a, "max_images", None)
    if v is None:
        env = (os.environ.get("PWA_PROXY_MAX_IMAGES") or "").strip()
        try:
            v = int(env) if env else DEFAULT_MAX_IMAGES
        except ValueError as e:
            raise PwaError(f"PWA_PROXY_MAX_IMAGES must be an integer, got {env!r}") from e
    return v


def usd_per_mtok(judge: Judge) -> float | None:
    env = (os.environ.get("PWA_PROXY_USD_PER_MTOK") or "").strip()
    try:
        return float(env) if env else USD_PER_MTOK.get(judge.model)
    except ValueError:
        return None


def cost_guard(sel: list[dict], a, judge: Judge) -> dict:
    """Before any proxy call: print the estimated images and image tokens per task and in total, counting only
    the calls this run will make (results already on disk are skipped unless --force), and refuse to start when
    the total is over the cap (--max-images, else $PWA_PROXY_MAX_IMAGES, else DEFAULT_MAX_IMAGES; 0 = no cap)."""
    specs = _upstream_specs()
    detail = os.environ.get("JUDGE_IMAGE_DETAIL", "high")
    total, tokens, calls, unknown = 0, 0, 0, []
    log(f"[pwa] cost guard ({judge.name}, image detail {detail}): estimated images to send per task")
    for t in sel:
        est = estimate_images(t, video_path(a.exp, t["task_id"]), specs, detail)
        n_img = n_tok = n_calls = 0
        for k in range(1, a.passes + 1):
            d = eval_dir(a.exp, False, judge) / f"pass{k}"
            todo_score = getattr(a, "force", False) or not done(d / f"{t['task_id']}_score.json", False)
            todo_gate = t["family"] == "gc" and (getattr(a, "force", False) or not done(d / f"{t['task_id']}_gate.json", False))
            if est is None:
                if todo_score or todo_gate:
                    n_img, n_tok, n_calls = n_img + UNKNOWN_TASK_IMAGES, n_tok + UNKNOWN_TASK_TOKENS, n_calls + 2
                continue
            if todo_score:
                n_img, n_tok, n_calls = n_img + est["score"], n_tok + est["score_tokens"], n_calls + 1
            if todo_gate and est["gate"]:
                n_img, n_tok, n_calls = n_img + est["gate"], n_tok + est["gate_tokens"], n_calls + 1
        if est is None:
            unknown.append(t["task_id"])
        if n_calls:
            log(f"[pwa]   {t['task_id']}: ~{n_img} images, ~{n_tok} image tokens in {n_calls} call(s) over "
                f"{a.passes} pass(es)" + (" (duration unknown: assumed)" if est is None else ""))
        total, tokens, calls = total + n_img, tokens + n_tok, calls + n_calls
    if unknown:
        log(f"[pwa]   no duration for {len(unknown)} task(s), counted at {UNKNOWN_TASK_IMAGES} images per pass: "
            f"{' '.join(unknown)}")
    price = usd_per_mtok(judge)
    usd = f", ~${tokens / 1e6 * price:.2f} image input at ${price:g}/1M tokens" if price is not None else ""
    log(f"[pwa] cost guard: ~{total} images, ~{tokens} image tokens{usd} in ~{calls} calls (gpt-4o/4.1 tile "
        f"count; prompt text, output and retries not counted)")
    cap = max_images(a)
    if cap and total > cap:
        raise PwaError(f"cost guard: ~{total} images is over the cap of {cap}; nothing was sent. Score fewer tasks "
                       f"or passes, or raise the cap with --max-images N (or PWA_PROXY_MAX_IMAGES; 0 = no cap)")
    return {"images": total, "tokens": tokens, "calls": calls, "cap": cap}


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
        cost_guard(with_video, a, judge)
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
