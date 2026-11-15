"""Run the upstream verifier (metrics.vqa.score) with a Gemini thinking level. Screening judge only.

Upstream builds GenerateContentConfig(response_mime_type=..., temperature=0.1) with no thinking config and
reads no env var for one. This wrapper subclasses that config class so every instance gets
thinking_config=ThinkingConfig(thinking_level=$PWA_JUDGE_THINKING), then runs the upstream module unchanged.
`pwa score --judge-model M --judge-thinking low` uses it; the official judge never does.
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


def main() -> None:
    level = os.environ.get("PWA_JUDGE_THINKING", "").strip()
    if not level:
        raise SystemExit("PWA_JUDGE_THINKING is not set; call metrics.vqa.score directly instead")
    install(level)
    runpy.run_module("metrics.vqa.score", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
