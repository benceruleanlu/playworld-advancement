"""Paths, env loading, task selection, experiment metadata. Stdlib only."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FAMILIES = ("gc", "if", "insight", "outsight")
GROUP = {"gc": "GC", "if": "IF", "insight": "OE", "outsight": "OE"}


def find_root() -> Path:
    if os.environ.get("PWA_ROOT"):
        return Path(os.environ["PWA_ROOT"]).resolve()
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / "splits").is_dir() and (d / "third_party").is_dir():
            return d
    return Path(__file__).resolve().parents[1]


ROOT = find_root()
PLAYWORLD = ROOT / "third_party" / "PlayWorld"
UPSTREAM_SANA_RUNNER = PLAYWORLD / "Agent_player" / "SANA-WM" / "run_agent.py"
SANA_RUNNER = ROOT / "adapters" / "sana_wm" / "run.py"  # upstream + agent provider patch
DATA = ROOT / "data"
RUNS = Path(os.environ.get("PWA_RUNS") or ROOT / "runs")
RESULTS_CSV = Path(os.environ.get("PWA_RESULTS_CSV") or ROOT / "results" / "experiments.csv")


class PwaError(Exception):
    """User-facing error: printed without traceback, exit code 1 (or .code)."""

    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


def log(*parts) -> None:
    print(*parts, file=sys.stderr, flush=True)


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- env
_EXPORT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_file(text: str, pwd: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        m = _EXPORT.match(line)
        if not m:
            continue
        key, raw = m.group(1), m.group(2).strip()
        if raw[:1] in ("'", '"'):
            q = raw[0]
            end = raw.find(q, 1)
            val = raw[1:end] if end > 0 else raw[1:]
            if q == "'":
                out[key] = val
                continue
        else:
            val = raw.split(" #", 1)[0].strip()
        scope = {**os.environ, **out, "PWD": pwd}
        val = re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda g: scope.get(g.group(1) or g.group(2), ""), val)
        out[key] = val
    return out


def load_env() -> Path | None:
    """Apply config/env.sh to os.environ without overriding set vars."""
    path = ROOT / "config" / "env.sh"
    if not path.is_file():
        return None
    for k, v in parse_env_file(path.read_text(), str(ROOT)).items():
        os.environ.setdefault(k, v)
    return path


# ---------------------------------------------------------------- tasks
_records: dict[str, dict[str, dict]] = {}


def records(family: str) -> dict[str, dict]:
    if family not in _records:
        path = DATA / family / "data.json"
        if not path.is_file():
            raise PwaError(f"missing {path}; run ./setup.sh")
        _records[family] = {r["task_id"]: r for r in json.loads(path.read_text())}
    return _records[family]


def view_of(rec: dict) -> str:
    """'third person' (dataset) -> 'third-person' (aggregation convention)."""
    return str(rec.get("perspective") or "").strip().lower().replace(" ", "-")


def task_info(family: str, task_id: str) -> dict:
    rec = records(family).get(task_id)
    if rec is None:
        raise PwaError(f"task {task_id} not in data/{family}/data.json")
    return {"family": family, "task_id": task_id, "view": view_of(rec),
            "group": GROUP[family], "image": str(DATA / rec.get("image_path", "")),
            "dataset": str(DATA / family / "data.json")}


def read_split(split: str) -> list[tuple[str, str]]:
    path = Path(split)
    if not path.is_file():
        path = ROOT / "splits" / f"{split}.tsv"
    if not path.is_file():
        raise PwaError(f"unknown split {split!r} (no splits/{split}.tsv and no such file)")
    out = []
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            fam, tid = line.split("\t")[:2]
            if fam not in FAMILIES:
                raise PwaError(f"{path}: bad family {fam!r}")
            out.append((fam, tid.strip()))
    return out


def family_of(task_id: str) -> str:
    for fam in FAMILIES:
        if task_id in records(fam):
            return fam
    raise PwaError(f"task {task_id} not found in any family")


def select(split: str | None, families: list[str] | None = None, tasks: list[str] | None = None) -> list[dict]:
    pairs = read_split(split or "dev")
    if tasks:
        wanted = set(tasks)
        pairs = [p for p in pairs if p[1] in wanted]
        missing = wanted - {p[1] for p in pairs}
        if missing and split is None:  # explicit --tasks outside the default split
            pairs += [(family_of(t), t) for t in sorted(missing)]
        elif missing:
            raise PwaError(f"tasks not in split {split}: {' '.join(sorted(missing))}")
    if families:
        pairs = [p for p in pairs if p[0] in families]
    if not pairs:
        raise PwaError("selection is empty")
    return [task_info(f, t) for f, t in pairs]


# ---------------------------------------------------------------- experiments
def split_label(split: str | None, families=None, tasks=None) -> str:
    """Name a selection for logs/CSV: 'dev', 'dev[gc,if]', 'custom' (explicit --tasks)."""
    if tasks:
        return "custom"
    label = Path(split).stem if split and Path(split).is_file() else (split or "dev")
    return f"{label}[{','.join(families)}]" if families else label


def exp_dir(exp: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", exp):
        raise PwaError(f"bad experiment name {exp!r}: use [A-Za-z0-9._-]")
    return RUNS / exp


def video_path(exp: str, task_id: str) -> Path:
    return exp_dir(exp) / "videos" / task_id / f"{task_id}.mp4"


def read_meta(exp: str) -> dict:
    d = exp_dir(exp)
    if not d.is_dir():
        raise PwaError(f"no experiment {exp} (expected {d})")
    p = d / "meta.json"
    if p.is_file():
        return json.loads(p.read_text())
    shards = sorted(d.glob("meta.shard*.json"))
    return json.loads(shards[0].read_text()) if shards else {}


def select_for_exp(exp: str, split: str | None, families, tasks) -> list[dict]:
    """Default to the task list recorded at gen time."""
    if split or tasks:
        return select(split, families, tasks)
    meta = read_meta(exp)
    if meta.get("tasks"):
        sel = [task_info(f, t) for f, t in meta["tasks"]]
        sel = [t for t in sel if not families or t["family"] in families]
        if not sel:
            raise PwaError("selection is empty")
        return sel
    return select(meta.get("split") or "dev", families, None)


UPSTREAM_NUM_CHUNKS = 30  # run_agent.py --num-chunks default: agent chunks per closed-loop rollout


def runner_num_chunks(args: list[str]) -> int | None:
    """Last --num-chunks value in runner args (argparse keeps the last one), or None."""
    val = None
    for i, x in enumerate(args or []):
        if x == "--num-chunks" and i + 1 < len(args):
            val = args[i + 1]
        elif x.startswith("--num-chunks="):
            val = x.split("=", 1)[1]
    try:
        return int(val) if val is not None else None
    except ValueError:
        return None


def chunk_cap(meta: dict) -> int | None:
    """Agent-chunk cap of a run (pwa gen --max-chunks, or --num-chunks below upstream's 30 in the runner args).
    None = uncapped, comparable to official scores. A capped run is a smoke run and never an official number."""
    if meta.get("max_chunks"):
        return int(meta["max_chunks"])
    n = runner_num_chunks(meta.get("runner_args") or [])
    return n if n is not None and n < UPSTREAM_NUM_CHUNKS else None


def cap_label(cap: int | None) -> str:
    """One label for a capped run, used in meta notes, the csv, reports and the site."""
    return f"capped smoke run: {cap} agent chunk{'s' if cap != 1 else ''} per rollout (official {UPSTREAM_NUM_CHUNKS}), " \
           f"not comparable to official scores" if cap else ""


def git(*args, cwd: Path = ROOT) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def current_branch() -> str:
    """Ref name the run was launched from: Actions' GITHUB_REF_NAME, else the checked-out branch, else ''."""
    b = os.environ.get("GITHUB_REF_NAME") or git("rev-parse", "--abbrev-ref", "HEAD") or os.environ.get("PWA_GIT_BRANCH") or ""
    return "" if b == "HEAD" else b


def provenance() -> dict:
    status = git("status", "--porcelain", "--", ".", ":!runs", ":!results")
    # Remote containers (Modal) get code without .git; the launcher passes these through.
    dirty = bool(status) if status is not None else None
    if dirty is None and os.environ.get("PWA_GIT_DIRTY") in ("0", "1"):
        dirty = os.environ["PWA_GIT_DIRTY"] == "1"
    return {"git_sha": git("rev-parse", "HEAD") or os.environ.get("PWA_GIT_SHA"), "branch": current_branch(),
            "git_dirty": dirty,
            "submodule_sha": git("rev-parse", "HEAD", cwd=PLAYWORLD) or os.environ.get("PWA_SUBMODULE_SHA"),
            "hostname": socket.gethostname()}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None
