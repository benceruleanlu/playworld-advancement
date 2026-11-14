"""pwa doctor: environment checks. Never prints secret values."""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys

from .core import DATA, FAMILIES, PLAYWORLD, ROOT, SANA_RUNNER, UPSTREAM_SANA_RUNNER

# (name, needed_for) where needed_for is a set of actions that require it; others warn.
KEYS = [("PLAYER_API_KEY", {"gen"}),
        ("GEMINI_API_KEY", {"score"}), ("GEMINI_MODEL", {"score"}), ("HF_TOKEN", set())]


def _mod(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def checks(runner: str = "sana") -> list[dict]:
    out = []

    def add(name, ok, needed, fix=""):
        out.append({"check": name, "ok": bool(ok), "needed_for": sorted(needed), "fix": "" if ok else fix})

    every = {"gen", "score"}
    add("python>=3.10", sys.version_info >= (3, 10), every, "use python 3.10+")
    add("submodule third_party/PlayWorld", UPSTREAM_SANA_RUNNER.is_file() and (PLAYWORLD / "metrics" / "aggregate.py").is_file(),
        every, "git submodule update --init")
    for fam in FAMILIES:
        add(f"data/{fam}/data.json", (DATA / fam / "data.json").is_file(), every, "./setup.sh")
        imgs = DATA / fam / "images"
        n = len(list(imgs.iterdir())) if imgs.is_dir() else 0
        add(f"data/{fam}/images ({n} files)", n > 0, {"gen"}, "./setup.sh (downloads images)")
    add("ffmpeg on PATH", shutil.which("ffmpeg"), every, "apt install ffmpeg")
    add("config/env.sh", (ROOT / "config" / "env.sh").is_file(), every, "cp config/env.example.sh config/env.sh and fill it")
    prov0 = (os.environ.get("PLAYER_API_PROVIDER") or "upstream").lower()
    for key in ("PLAYER_API_URL", "PLAYER_MODEL"):  # agent_api fills these for openai/anthropic
        add(f"${key} set", os.environ.get(key) or prov0 in ("openai", "anthropic"), {"gen"}, f"set {key} in config/env.sh")
    for key, needed in KEYS:
        add(f"${key} set", os.environ.get(key), needed, f"set {key} in config/env.sh")
    prov = (os.environ.get("PLAYER_API_PROVIDER") or "upstream").lower()
    add(f"PLAYER_API_PROVIDER={prov} is known", prov in ("upstream", "openai", "anthropic"), {"gen"},
        "use openai, anthropic or upstream")
    pm = os.environ.get("PLAYER_MODEL") or ("gpt-4.1-mini" if prov == "openai" else "")
    add("PLAYER_MODEL is non-reasoning", not (prov == "openai" and re.match(r"^(o\d|gpt-5)", pm)), set(),
        "reasoning models can spend upstream's 128 max_completion_tokens on hidden reasoning and return "
        "empty; use gpt-4.1-mini or set PLAYER_MAX_COMPLETION_TOKENS")
    add(f"{SANA_RUNNER.relative_to(ROOT)}", SANA_RUNNER.is_file(), {"gen"} if runner == "sana" else set(), "restore adapters/")
    gm = os.environ.get("GEMINI_MODEL", "")
    add("GEMINI_MODEL is gemini-3.1-pro*", gm.startswith("gemini-3.1-pro"), set(),
        "leaderboard numbers need Gemini 3.1 Pro")
    add("google-genai importable", _mod("google.genai"), {"score"}, "pip install -e third_party/PlayWorld")
    add("httpx importable", _mod("httpx"), {"gen"}, "pip install httpx")
    for key in ("SANA_ROOT", "MG3_ROOT"):
        val = os.environ.get(key)
        needed = {"gen"} if (key == "SANA_ROOT" and runner == "sana") or (key == "MG3_ROOT" and runner == "matrix_game3") else set()
        add(f"${key} exists", val and os.path.isdir(val), needed, f"clone the model repo and set {key}")
    torch = _mod("torch")
    cuda = False
    if torch:
        try:
            r = subprocess.run([sys.executable, "-c", "import torch;print(torch.cuda.is_available())"],
                               capture_output=True, text=True, timeout=60)
            cuda = r.stdout.strip() == "True"
        except subprocess.TimeoutExpired:
            pass
    add("torch importable", torch, set(), "install torch (GPU box only)")
    add("torch.cuda available", cuda, set(), "needs a GPU box for generation")
    return out


def failing(results: list[dict], action: str) -> list[dict]:
    acts = {"gen", "score"} if action == "all" else {action}
    return [r for r in results if not r["ok"] and acts & set(r["needed_for"])]
