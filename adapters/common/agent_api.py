"""Provider-aware replacement for run_agent.request_agent_action, plus player counters.

Upstream sends only `x-api-key` (plus internal-gateway headers), which OpenAI
rejects. `patch(run_agent)` swaps in a client whose payload and response
parsing are equivalent, with headers chosen by $PLAYER_API_PROVIDER:

  upstream  (default)  leave run_agent's request function untouched
  openai               Authorization: Bearer $PLAYER_API_KEY
  anthropic            x-api-key + anthropic-version: 2023-06-01

Also fills provider defaults for PLAYER_API_URL / PLAYER_MODEL when unset
(run_agent reads them as argparse defaults, so patch() must run before main()).
Stdlib only. Proxies from the environment are ignored unless
PLAYER_API_TRUST_ENV=1, matching upstream's httpx trust_env=False.

Request settings (runner arg after `--`, else env var, else default):

  --player-max-completion-tokens N  PLAYER_MAX_COMPLETION_TOKENS  4096 (upstream 128)
  --player-reasoning-effort E       PLAYER_REASONING_EFFORT       low for openai, omitted otherwise;
                                                                  "off" or an empty value omits it
  --player-empty-retries N          PLAYER_EMPTY_RETRIES          2

Why: a reasoning player can spend its whole completion budget thinking and return empty content with
finish_reason=length. Upstream decide_action then retries the same request 3 times and silently plays the
dataset action (or NEXT / WAIT). This client retries an empty or length-truncated reply (or a 400 saying
max_tokens was reached) up to N more times, the last retry with twice the budget, before upstream sees it.
A repeat of a prompt whose retries were already used up gets one call at the doubled budget, so one
decision costs at most 3 + 2 = 5 calls with the defaults. A 400 naming reasoning_effort drops the parameter
and retries once; later calls leave it out.

Counters (PlayerStats, every provider, installed by patch()): per task one line, then a run total from
finish(), and a "player" object in <task>_result.json:

  [agent] player task=GC031 decisions=27 calls=31 empty=4 retries=4 errors=0 fallbacks=0
  [agent] player total tasks=3 decisions=63 calls=70 empty=7 retries=7 errors=0 fallbacks=0

  decisions  upstream decide_action calls (a return-stop answer never reaches the player)
  calls      HTTP requests to the player API
  empty      replies with empty content or finish_reason=length, and 400s saying max_tokens was reached
  retries    extra requests this client made after an empty or truncated reply
  errors     requests that raised to upstream (HTTP error, timeout, no choices)
  fallbacks  decisions upstream answered itself (dataset action, NEXT or WAIT) after 3 failed attempts

Each empty reply also logs one line with the usage numbers (never the key or the prompt):
  [agent] empty reply (finish_reason=length, completion_tokens=1024, reasoning_tokens=1024) -> retry 1
"""
from __future__ import annotations

import builtins
import functools
import hashlib
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

DEFAULTS = {
    "openai": {"PLAYER_API_URL": "https://api.openai.com/v1",
               "PLAYER_MODEL": "gpt-4.1-mini"},
    "anthropic": {"PLAYER_API_URL": "https://api.anthropic.com/v1",
                  "PLAYER_MODEL": "claude-haiku-4-5-20251001"},
}
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_COMPLETION_TOKENS = 4096
DEFAULT_EMPTY_RETRIES = 2
OMIT_EFFORT = ("", "off")

# runner arg -> (env var, PlayerConfig field)
ARGS = {"--player-max-completion-tokens": ("PLAYER_MAX_COMPLETION_TOKENS", "max_completion_tokens"),
        "--player-reasoning-effort": ("PLAYER_REASONING_EFFORT", "reasoning_effort"),
        "--player-empty-retries": ("PLAYER_EMPTY_RETRIES", "empty_retries")}


def provider(environ=os.environ) -> str:
    return (environ.get("PLAYER_API_PROVIDER") or "upstream").strip().lower()


@dataclass
class PlayerConfig:
    max_completion_tokens: int = DEFAULT_MAX_COMPLETION_TOKENS
    reasoning_effort: str | None = None
    empty_retries: int = DEFAULT_EMPTY_RETRIES
    send_effort: bool = True  # cleared once the API rejects reasoning_effort

    def describe(self) -> str:
        return (f"max_completion_tokens={self.max_completion_tokens} "
                f"reasoning_effort={self.reasoning_effort or 'omitted'} empty_retries={self.empty_retries}")


def configure(argv: list[str], environ=os.environ) -> tuple[PlayerConfig, list[str]]:
    """PlayerConfig from the --player-* runner args (then env, then defaults) and argv without those args.
    Both `--flag VALUE` and `--flag=VALUE` work."""
    given, rest, i = {}, [], 0
    argv = list(argv)
    while i < len(argv):
        a = argv[i]
        name, eq, val = a.partition("=")
        if name in ARGS:
            if not eq:
                if i + 1 >= len(argv):
                    raise SystemExit(f"{name} needs a value")
                val, i = argv[i + 1], i + 1
            given[name] = val
        else:
            rest.append(a)
        i += 1

    def pick(flag):
        env, _ = ARGS[flag]
        return given[flag] if flag in given else environ.get(env)

    cfg = PlayerConfig()
    for flag in ("--player-max-completion-tokens", "--player-empty-retries"):
        raw = pick(flag)
        if raw not in (None, ""):
            try:
                n = int(raw)
            except ValueError:
                raise SystemExit(f"{flag} / {ARGS[flag][0]} must be an integer, got {raw!r}") from None
            if n < (1 if flag == "--player-max-completion-tokens" else 0):
                raise SystemExit(f"{flag} / {ARGS[flag][0]} is out of range: {n}")
            setattr(cfg, ARGS[flag][1], n)
    effort = pick("--player-reasoning-effort")
    if effort is None:
        effort = "low" if provider(environ) == "openai" else ""
    effort = effort.strip()
    cfg.reasoning_effort = None if effort.lower() in OMIT_EFFORT else effort
    return cfg, rest


FIELDS = ("decisions", "calls", "empty", "retries", "errors", "fallbacks")


@dataclass
class PlayerStats:
    task: dict = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    total: dict = field(default_factory=lambda: dict.fromkeys(FIELDS, 0))
    tasks: int = 0

    def add(self, key: str, n: int = 1):
        self.task[key] += n
        self.total[key] += n

    def new_task(self):
        self.task = dict.fromkeys(FIELDS, 0)

    def finish_task(self, task_id) -> dict:
        self.tasks += 1
        s = {"task": task_id, **self.task}
        print("[agent] player " + " ".join(f"{k}={v}" for k, v in s.items()), flush=True)
        return s

    def total_line(self) -> str:
        return f"[agent] player total tasks={self.tasks} " + " ".join(f"{k}={v}" for k, v in self.total.items())


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


def build_payload(model: str, prompt: str, images_b64: list[str], max_completion_tokens: int,
                  reasoning_effort: str | None = None) -> dict:
    parts = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}} for b64 in images_b64]
    parts.append({"type": "text", "text": prompt})
    body = {"model": model, "max_completion_tokens": int(max_completion_tokens),
            "messages": [{"role": "user", "content": parts}]}
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    return body


def parse_reply(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"Agent API response has no choices: {str(body)[:300]}")
    msg = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(msg, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in msg)
    return str(msg)


def usage_of(body: dict) -> str:
    """finish_reason and token counts of a reply, for the empty-reply log line."""
    choice = (body.get("choices") or [{}])[0] or {}
    usage = body.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return (f"finish_reason={choice.get('finish_reason')}, completion_tokens={usage.get('completion_tokens', '?')}, "
            f"reasoning_tokens={details.get('reasoning_tokens', '?')}")


def _error_param(text: str) -> str | None:
    try:
        err = json.loads(text).get("error")
    except (ValueError, AttributeError):
        return None
    return err.get("param") if isinstance(err, dict) and isinstance(err.get("param"), str) else None


def rejects_effort(text: str) -> bool:
    return _error_param(text) == "reasoning_effort" or "reasoning_effort" in text


def output_limit_error(text: str) -> bool:
    """The 400 a provider sends instead of a truncated reply, e.g. "Could not finish the message because
    max_tokens or model output limit was reached"."""
    t = text.lower()
    return "could not finish the message" in t or "output limit was reached" in t


def make_request_fn(name: str, *, show_error_body: bool = True, cfg: PlayerConfig | None = None,
                    stats: PlayerStats | None = None):
    cfg = cfg or configure([])[0]
    stats = stats or PlayerStats()
    exhausted = {"key": None}  # prompt digest whose retries were used up (upstream re-sends the same request)

    def post(url, body, api_key, timeout):
        """(status, parsed body or error text)."""
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers=headers_for(name, api_key))
        handlers = [] if os.environ.get("PLAYER_API_TRUST_ENV") == "1" else [urllib.request.ProxyHandler({})]
        opener = urllib.request.build_opener(*handlers)
        stats.add("calls")
        try:
            with opener.open(req, timeout=timeout) as resp:
                return 200, json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            return e.code, (text.replace(api_key, "***") if api_key else text)

    def request_agent_action(args, prompt, images_b64):
        url = args.agent_base_url.rstrip("/") + "/chat/completions"
        images = list(images_b64)
        key = hashlib.sha1(json.dumps([prompt, images]).encode()).hexdigest()
        repeat = exhausted["key"] == key
        retries = 0 if repeat else cfg.empty_retries
        attempt, content, last_error = 0, "", None
        while True:
            budget = cfg.max_completion_tokens * (2 if (repeat or (retries and attempt == retries)) else 1)
            body = build_payload(args.agent_model, prompt, images, budget,
                                 cfg.reasoning_effort if cfg.send_effort else None)
            try:
                status, reply = post(url, body, args.agent_api_key, args.agent_timeout_s)
            except Exception:
                stats.add("errors")
                raise
            if status == 400 and "reasoning_effort" in body and rejects_effort(reply):
                cfg.send_effort = False
                print(f"    [agent] player API rejects reasoning_effort={cfg.reasoning_effort!r}; "
                      f"retrying without it (and leaving it out of later calls)", flush=True)
                continue
            if status == 200:
                try:
                    content = parse_reply(reply)
                except RuntimeError:
                    stats.add("errors")
                    raise
                finish = ((reply.get("choices") or [{}])[0] or {}).get("finish_reason")
                if content.strip() and finish != "length":
                    exhausted["key"] = None
                    return content
                why, last_error = usage_of(reply), None
            elif status == 400 and output_limit_error(reply):
                content, why = "", f"HTTP 400 output limit reached, max_completion_tokens={budget}"
                last_error = f"Agent API HTTP 400{': ' + reply[:300] if show_error_body else ''}"
            else:
                stats.add("errors")
                raise RuntimeError(f"Agent API HTTP {status}{': ' + reply[:300] if show_error_body else ''}")
            stats.add("empty")
            if attempt < retries:
                attempt += 1
                stats.add("retries")
                nxt = cfg.max_completion_tokens * (2 if attempt == retries else 1)
                print(f"    [agent] empty reply ({why}) -> retry {attempt} (max_completion_tokens={nxt})", flush=True)
                continue
            exhausted["key"] = key
            print(f"    [agent] empty reply ({why}) -> no retries left; upstream retries or falls back", flush=True)
            if last_error and not content.strip():
                stats.add("errors")
                raise RuntimeError(last_error)
            return content

    request_agent_action.provider = name
    request_agent_action.cfg = cfg
    request_agent_action.stats = stats
    return request_agent_action


def install_stats(run_agent_module, stats: PlayerStats) -> None:
    """Count decisions and fallbacks on upstream's own functions, and print/record per-task counters.

    decide_action is wrapped here, before any adapter wrapper, so it counts only decisions that reach upstream.
    Fallbacks are counted from upstream's own `[agent] fallback=` print via a module-level print in run_agent
    (its functions look `print` up in the module globals first). Attributes missing on a stand-in are skipped."""
    run_agent_module._pwa_player_stats = stats

    def counting_print(*a, **kw):
        if a and isinstance(a[0], str) and a[0].lstrip().startswith("[agent] fallback="):
            stats.add("fallbacks")
        return builtins.print(*a, **kw)

    run_agent_module.print = counting_print
    decide = getattr(run_agent_module, "decide_action", None)
    if callable(decide):
        @functools.wraps(decide)
        def decide_action(*a, **kw):
            stats.add("decisions")
            return decide(*a, **kw)
        run_agent_module.decide_action = decide_action
    run_task = getattr(run_agent_module, "run_task", None)
    if callable(run_task):
        @functools.wraps(run_task)
        def wrapped_run_task(task, engine, output_dir, args, *rest, **kw):
            stats.new_task()
            result = None
            try:
                result = run_task(task, engine, output_dir, args, *rest, **kw)
                return result
            finally:
                tid = (task or {}).get("task_id")
                s = stats.finish_task(tid)
                if isinstance(result, dict) and result.get("success"):
                    result["player"] = s
                    _add_to_result_json(Path(output_dir) / str(tid) / f"{tid}_result.json", s)
        run_agent_module.run_task = wrapped_run_task


def _add_to_result_json(path: Path, summary: dict):
    """Best effort: never fail a rollout over bookkeeping."""
    try:
        data = json.loads(path.read_text())
        data["player"] = summary
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        print(f"[agent] player counters: could not update {path}: {e}", flush=True)


def patch(run_agent_module, cfg: PlayerConfig | None = None) -> str:
    """Patch run_agent in place and install the player counters. Returns the active provider name.
    cfg comes from configure(argv); without it the env and defaults apply."""
    name = provider()
    if name != "upstream":
        headers_for(name, "")  # validate early
    stats = PlayerStats()
    install_stats(run_agent_module, stats)
    if name == "upstream":
        return name
    cfg = cfg or configure([])[0]
    for key, val in DEFAULTS.get(name, {}).items():
        if not os.environ.get(key):
            os.environ[key] = val
    run_agent_module.request_agent_action = make_request_fn(name, cfg=cfg, stats=stats)
    print(f"[adapter] player request: {cfg.describe()}", flush=True)
    return name


def finish(run_agent_module) -> None:
    """Print the run total (call after run_agent.main())."""
    stats = getattr(run_agent_module, "_pwa_player_stats", None)
    if stats is not None:
        print(stats.total_line(), flush=True)


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
