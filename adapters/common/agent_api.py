"""Provider-aware replacement for run_agent.request_agent_action.

Upstream sends only `x-api-key` (plus internal-gateway headers), which OpenAI
rejects. `patch(run_agent)` swaps in a client whose payload and response
parsing are equivalent, with headers chosen by $PLAYER_API_PROVIDER:

  upstream  (default)  leave run_agent untouched
  openai               Authorization: Bearer $PLAYER_API_KEY
  anthropic            x-api-key + anthropic-version: 2023-06-01

Also fills provider defaults for PLAYER_API_URL / PLAYER_MODEL when unset
(run_agent reads them as argparse defaults, so patch() must run before main()).
Stdlib only. Proxies from the environment are ignored unless
PLAYER_API_TRUST_ENV=1, matching upstream's httpx trust_env=False.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULTS = {
    "openai": {"PLAYER_API_URL": "https://api.openai.com/v1",
               # non-reasoning + vision: 128 completion tokens can be eaten by hidden reasoning
               "PLAYER_MODEL": "gpt-4.1-mini"},
    "anthropic": {"PLAYER_API_URL": "https://api.anthropic.com/v1",
                  "PLAYER_MODEL": "claude-haiku-4-5-20251001"},
}
ANTHROPIC_VERSION = "2023-06-01"


def provider() -> str:
    return (os.environ.get("PLAYER_API_PROVIDER") or "upstream").strip().lower()


def headers_for(name: str, api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if name == "openai":
        h["Authorization"] = f"Bearer {api_key}"
    elif name == "anthropic":
        h["x-api-key"] = api_key
        h["anthropic-version"] = ANTHROPIC_VERSION
    else:
        raise ValueError(f"unknown PLAYER_API_PROVIDER {name!r} (use openai, anthropic, upstream)")
    return h


def build_payload(model: str, prompt: str, images_b64: list[str]) -> dict:
    parts = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}} for b64 in images_b64]
    parts.append({"type": "text", "text": prompt})
    return {"model": model,
            "max_completion_tokens": int(os.environ.get("PLAYER_MAX_COMPLETION_TOKENS", "128")),
            "messages": [{"role": "user", "content": parts}]}


def parse_reply(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"Agent API response has no choices: {str(body)[:300]}")
    msg = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(msg, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in msg)
    return str(msg)


def make_request_fn(name: str):
    def request_agent_action(args, prompt, images_b64):
        url = args.agent_base_url.rstrip("/") + "/chat/completions"
        data = json.dumps(build_payload(args.agent_model, prompt, list(images_b64))).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers=headers_for(name, args.agent_api_key))
        handlers = [] if os.environ.get("PLAYER_API_TRUST_ENV") == "1" else [urllib.request.ProxyHandler({})]
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(req, timeout=args.agent_timeout_s) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:  # surface the provider's message; never the key
            raise RuntimeError(f"Agent API HTTP {e.code}: {e.read().decode(errors='replace')[:300]}") from None
        return parse_reply(body)

    request_agent_action.provider = name
    return request_agent_action


def patch(run_agent_module) -> str:
    """Patch run_agent in place. Returns the active provider name."""
    name = provider()
    if name == "upstream":
        return name
    headers_for(name, "")  # validate early
    for key, val in DEFAULTS.get(name, {}).items():
        if not os.environ.get(key):
            os.environ[key] = val
    run_agent_module.request_agent_action = make_request_fn(name)
    return name
