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
from types import SimpleNamespace

DEFAULTS = {
    "openai": {"PLAYER_API_URL": "https://api.openai.com/v1",
               # the reply is one action word; the completion budget (PLAYER_MAX_COMPLETION_TOKENS, 1024)
               # leaves room for models that reason before answering
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
            "max_completion_tokens": int(os.environ.get("PLAYER_MAX_COMPLETION_TOKENS", "1024")),
            "messages": [{"role": "user", "content": parts}]}


def parse_reply(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"Agent API response has no choices: {str(body)[:300]}")
    msg = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(msg, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in msg)
    return str(msg)


def make_request_fn(name: str, *, show_error_body: bool = True):
    def request_agent_action(args, prompt, images_b64):
        url = args.agent_base_url.rstrip("/") + "/chat/completions"
        data = json.dumps(build_payload(args.agent_model, prompt, list(images_b64))).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers=headers_for(name, args.agent_api_key))
        handlers = [] if os.environ.get("PLAYER_API_TRUST_ENV") == "1" else [urllib.request.ProxyHandler({})]
        opener = urllib.request.build_opener(*handlers)
        try:
            with opener.open(req, timeout=args.agent_timeout_s) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = f": {e.read().decode(errors='replace')[:300]}" if show_error_body else ""
            raise RuntimeError(f"Agent API HTTP {e.code}{detail}") from None
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


def preflight() -> None:
    key = os.environ.get("PLAYER_API_KEY")
    if not key:
        raise SystemExit("Closed-loop generation requires PLAYER_API_KEY.")
    if provider() != "openai":
        print("Player key configured. Live preflight is available for the OpenAI provider.")
        return

    args = SimpleNamespace(
        agent_base_url=os.environ.get("PLAYER_API_URL") or DEFAULTS["openai"]["PLAYER_API_URL"],
        agent_model=os.environ.get("PLAYER_MODEL") or DEFAULTS["openai"]["PLAYER_MODEL"],
        agent_api_key=key,
        agent_timeout_s=10,
    )
    try:
        reply = make_request_fn("openai", show_error_body=False)(args, "Reply with OK.", [])
    except Exception as exc:
        # Some API error bodies include credential fragments. Print only the status.
        status = str(exc) if str(exc).startswith("Agent API HTTP ") else type(exc).__name__
        raise SystemExit(f"Player API preflight failed ({status}). Check the key, endpoint, model and project access.") from None
    if not reply.strip():
        raise SystemExit("Player API preflight returned an empty reply.")
    print("Player API preflight succeeded.")


if __name__ == "__main__":
    preflight()
