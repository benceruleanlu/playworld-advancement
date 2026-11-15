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

PWA_JUDGE_GCP_ADC=1 (PWA_JUDGE_BACKEND=gcp with no GCP_GEMINI_API_KEY): upstream passes GEMINI_API_KEY to
  genai.Client explicitly, and an explicit key beats GOOGLE_CLOUD_PROJECT in the SDK. The factory is replaced by
  genai.Client(vertexai=True, project=..., location=...) (Agent Platform, formerly Vertex AI) with Application Default Credentials. Composes with
  PWA_JUDGE_THINKING. The express-key route needs no shim (pwa.score.verifier_env sets env vars only).
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


def install_gcp_adc() -> None:
    import metrics.gemini_client as gc  # noqa: PLC0415

    from google import genai  # noqa: PLC0415

    def create(*, api_key=None):  # same signature as upstream; the placeholder key is ignored
        return genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                            location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "global")

    gc.create_gemini_client = create


def main() -> None:
    level = os.environ.get("PWA_JUDGE_THINKING", "").strip()
    provider = os.environ.get("PWA_JUDGE_PROVIDER", "").strip().lower()
    if provider == "openai":
        install_openai(level)
    elif provider:
        raise SystemExit(f"PWA_JUDGE_PROVIDER={provider!r} is not supported (openai)")
    else:
        adc = os.environ.get("PWA_JUDGE_GCP_ADC", "").strip() == "1"
        if not (level or adc):
            raise SystemExit("none of PWA_JUDGE_THINKING, PWA_JUDGE_PROVIDER, PWA_JUDGE_GCP_ADC is set; "
                             "call metrics.vqa.score directly")
        if level:
            install(level)
        if adc:
            install_gcp_adc()
    runpy.run_module("metrics.vqa.score", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
