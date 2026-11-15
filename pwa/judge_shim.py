"""Run the upstream verifier (metrics.vqa.score) unchanged with a screening judge. Never the official judge.

Two runtime patches, chosen by env (set by `pwa score --judge-model ...`, see pwa.score.verifier_env):

PWA_JUDGE_THINKING=L (Gemini judge): upstream builds GenerateContentConfig(response_mime_type=...,
  temperature=0.1) with no thinking config and reads no env var for one. The config class is subclassed so
  every instance gets thinking_config=ThinkingConfig(thinking_level=L).

PWA_JUDGE_PROVIDER=openai (`--judge-model openai:MODEL`): metrics.gemini_client.create_gemini_client is
  replaced by pwa.judge_openai.make_client, so upstream's own generate_content call (same prompt, contact
  sheets, reference image, JSON parsing and output file) goes to an OpenAI-compatible chat API. A thinking
  level becomes reasoning_effort. Upstream binds the factory with `from metrics.gemini_client import
  create_gemini_client` when the module runs, so the patch is installed before runpy executes it.
"""
from __future__ import annotations

import os
import runpy


def install(level: str) -> None:
    from google.genai import types  # noqa: PLC0415  (only installed where the verifier runs)

    base = types.GenerateContentConfig
    if getattr(types, "_pwa_thinking_installed", False):
        return

    class ThinkingConfigured(base):  # type: ignore[misc, valid-type]
        def __init__(self, **kw):
            kw.setdefault("thinking_config", types.ThinkingConfig(thinking_level=level.upper()))
            super().__init__(**kw)

    ThinkingConfigured.__name__ = base.__name__
    types.GenerateContentConfig = ThinkingConfigured
    types._pwa_thinking_installed = True


def install_openai(reasoning_effort: str | None = None) -> None:
    import metrics.gemini_client as gc  # noqa: PLC0415  (upstream, on PYTHONPATH from the PlayWorld cwd)

    from .judge_openai import make_client  # noqa: PLC0415

    gc.create_gemini_client = make_client(reasoning_effort or None)


def main() -> None:
    level = os.environ.get("PWA_JUDGE_THINKING", "").strip()
    provider = os.environ.get("PWA_JUDGE_PROVIDER", "").strip().lower()
    if provider == "openai":
        install_openai(level)
    elif provider:
        raise SystemExit(f"PWA_JUDGE_PROVIDER={provider!r} is not supported (openai)")
    elif level:
        install(level)
    else:
        raise SystemExit("neither PWA_JUDGE_THINKING nor PWA_JUDGE_PROVIDER is set; call metrics.vqa.score directly")
    runpy.run_module("metrics.vqa.score", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
