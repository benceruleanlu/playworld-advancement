"""OpenAI-compatible stand-in for the Gemini client the upstream verifier uses. Screening judge only.

pwa.judge_shim installs `make_client` as metrics.gemini_client.create_gemini_client, then runs the upstream
metrics.vqa.score module unchanged. Upstream still samples the video, builds the contact sheets, writes the
prompt and parses the reply; this module only carries each generate_content call to
POST {JUDGE_API_URL}/chat/completions and hands back an object with the `.text` upstream reads.

Request translation (Gemini -> OpenAI chat):
  contents parts, in order   text -> {"type": "text"}; inline_data / uploaded file -> {"type": "image_url",
                             "image_url": {"url": "data:<mime>;base64,...", "detail": JUDGE_IMAGE_DETAIL}}
  config.system_instruction  a leading {"role": "system"} message
  response_mime_type json    response_format json_object, or json_schema when the config carries a schema
  temperature, top_p, seed, max_output_tokens   temperature, top_p, seed, max_completion_tokens
  thinking level             reasoning_effort (PWA_JUDGE_THINKING)
A 400 naming one of DROPPABLE as the rejected `param` (gpt-6-luna takes only the default temperature 1, so
upstream's 0.1 is refused) is retried once per param without it, with a stderr note; the client then leaves
that param out of its later calls. Other 400s raise.
Files API: upload keeps the local path and returns an ACTIVE file whose bytes are inlined at request time.

Env: JUDGE_API_URL / JUDGE_API_KEY (fall back to PLAYER_API_URL / PLAYER_API_KEY), JUDGE_API_RETRIES (4),
JUDGE_API_TIMEOUT_S (600), JUDGE_IMAGE_DETAIL (high), JUDGE_API_NO_TEMPERATURE=1 for models that reject a
temperature, JUDGE_API_TRUST_ENV=1 to use proxy env vars (ignored by default, as for the player).
Stdlib only. The key is never printed; error bodies are trimmed and scrubbed of it.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import Any

PREFIX = "openai:"
DEFAULT_URL = "https://api.openai.com/v1"
RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
# sampling params a model may reject that the call can go without; never reasoning_effort or response_format,
# which change what the judge is asked to do
DROPPABLE = ("temperature", "top_p", "seed")
_sleep = time.sleep  # tests replace this


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _data_uri(data: bytes | str, mime: str) -> str:
    b64 = data if isinstance(data, str) else base64.b64encode(data).decode("ascii")
    return f"data:{mime or 'image/jpeg'};base64,{b64}"


class Files:
    """The subset of client.files upstream uses (upload / get / delete). Nothing leaves the machine here:
    the uploaded path is read and inlined when generate_content references the file."""

    def __init__(self):
        self._by_uri: dict[str, SimpleNamespace] = {}

    def upload(self, file, **_kw) -> SimpleNamespace:
        path = Path(file).resolve()
        f = SimpleNamespace(name=f"files/pwa-{len(self._by_uri)}", uri=path.as_uri(), path=path,
                            mime_type=mimetypes.guess_type(path.name)[0] or "image/jpeg", state="ACTIVE")
        self._by_uri[f.uri] = f
        return f

    def get(self, name: str, **_kw) -> SimpleNamespace:
        for f in self._by_uri.values():
            if f.name == name:
                return f
        raise KeyError(name)

    def delete(self, name: str, **_kw) -> None:
        self._by_uri = {u: f for u, f in self._by_uri.items() if f.name != name}

    def read(self, uri: str) -> bytes:
        f = self._by_uri.get(uri)
        if f is None:
            raise ValueError(f"file {uri!r} was not uploaded through this client")
        return f.path.read_bytes()


def _part_to_openai(part: Any, files: Files) -> dict:
    if isinstance(part, str):
        return {"type": "text", "text": part}
    detail = os.environ.get("JUDGE_IMAGE_DETAIL", "high")
    text = _get(part, "text")
    if text is not None:
        return {"type": "text", "text": text}
    inline = _get(part, "inline_data")
    if inline is not None:
        return {"type": "image_url", "image_url": {"url": _data_uri(_get(inline, "data"), _get(inline, "mime_type")),
                                                   "detail": detail}}
    fd = _get(part, "file_data")
    if fd is not None:
        data = files.read(_get(fd, "file_uri"))
        return {"type": "image_url", "image_url": {"url": _data_uri(data, _get(fd, "mime_type")), "detail": detail}}
    raise ValueError(f"unsupported Gemini part for the OpenAI judge: {type(part).__name__}")


def _contents(contents: Any) -> list[Any]:
    """Normalise generate_content `contents` to a list of Content-like objects with .role / .parts."""
    if isinstance(contents, (str, bytes)) or _get(contents, "parts") is None and not isinstance(contents, list):
        return [SimpleNamespace(role="user", parts=[contents])]
    if not isinstance(contents, list):
        return [contents]
    if all(_get(c, "parts") is not None for c in contents):
        return contents
    return [SimpleNamespace(role="user", parts=contents)]  # a bare list of parts is one user turn


def _system_text(si: Any) -> str | None:
    if si is None:
        return None
    if isinstance(si, str):
        return si
    parts = _get(si, "parts")
    items = parts if parts is not None else (si if isinstance(si, list) else [si])
    texts = [p if isinstance(p, str) else _get(p, "text") for p in items]
    return "\n".join(t for t in texts if t) or None


def _lower_types(schema: Any) -> Any:
    """Gemini Schema dumps use upper-case type names (OBJECT, STRING); JSON Schema wants lower case."""
    if isinstance(schema, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _lower_types(v)) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_lower_types(v) for v in schema]
    return schema


def _schema(config: Any) -> dict | None:
    js = _get(config, "response_json_schema")
    if isinstance(js, dict):
        return js
    rs = _get(config, "response_schema")
    if hasattr(rs, "model_dump"):
        rs = rs.model_dump(exclude_none=True, mode="json")
    return _lower_types(rs) if isinstance(rs, dict) else None


def build_request(model: str, contents: Any, config: Any = None, reasoning_effort: str | None = None,
                  files: Files | None = None) -> dict:
    files = files or Files()
    messages = []
    sys_text = _system_text(_get(config, "system_instruction"))
    if sys_text:
        messages.append({"role": "system", "content": sys_text})
    for c in _contents(contents):
        role = "assistant" if _get(c, "role") == "model" else "user"
        messages.append({"role": role, "content": [_part_to_openai(p, files) for p in (_get(c, "parts") or [])]})
    body: dict[str, Any] = {"model": model[len(PREFIX):] if model.startswith(PREFIX) else model, "messages": messages}
    if _get(config, "response_mime_type") == "application/json":
        schema = _schema(config)
        body["response_format"] = ({"type": "json_schema", "json_schema": {"name": "verifier", "schema": schema}}
                                   if schema else {"type": "json_object"})
    temp = _get(config, "temperature")
    if temp is not None and os.environ.get("JUDGE_API_NO_TEMPERATURE") != "1":
        body["temperature"] = temp
    for src, dst in (("top_p", "top_p"), ("seed", "seed"), ("max_output_tokens", "max_completion_tokens")):
        if _get(config, src) is not None:
            body[dst] = _get(config, src)
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    return body


def response_from(body: dict) -> SimpleNamespace:
    """A Gemini-shaped response: `.text` (what upstream reads), `.candidates[0].content.parts[0].text`,
    `.usage_metadata` and `.model_version`. Raises when the reply carries no text, so the verifier exits
    non-zero and `pwa score` writes the .err file and retries."""
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"judge API response has no choices: {str(body)[:300]}")
    ch = choices[0]
    msg = ch.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    if not content:
        why = msg.get("refusal") or ch.get("finish_reason")
        raise RuntimeError(f"judge API returned no text (finish_reason/refusal: {why})")
    usage = body.get("usage") or {}
    return SimpleNamespace(
        text=content,
        candidates=[SimpleNamespace(content=SimpleNamespace(role="model", parts=[SimpleNamespace(text=content)]),
                                    finish_reason=ch.get("finish_reason"))],
        usage_metadata=SimpleNamespace(prompt_token_count=usage.get("prompt_tokens"),
                                       candidates_token_count=usage.get("completion_tokens"),
                                       total_token_count=usage.get("total_tokens")),
        model_version=body.get("model"))


class JudgeAPIError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None, param: str | None = None):
        super().__init__(msg)
        self.status, self.param = status, param


def _error_param(raw: str) -> str | None:
    """The `error.param` of an OpenAI-style error body, if any."""
    try:
        err = json.loads(raw).get("error")
    except (ValueError, AttributeError):
        return None
    return err.get("param") if isinstance(err, dict) and isinstance(err.get("param"), str) else None


def _scrub(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def _retry_after(headers) -> float | None:
    try:
        v = float((headers or {}).get("Retry-After"))
    except (TypeError, ValueError):
        return None
    return min(max(v, 0.0), 120.0)


def post_chat(base_url: str, api_key: str, body: dict, retries: int | None = None,
              timeout: float | None = None) -> dict:
    """POST /chat/completions with bounded retries on 408/409/429/5xx, timeouts and connection errors
    (backoff 2, 4, 8 ... s capped at 60, or Retry-After up to 120 s). Other HTTP errors raise at once."""
    retries = int(os.environ.get("JUDGE_API_RETRIES", "4")) if retries is None else retries
    timeout = float(os.environ.get("JUDGE_API_TIMEOUT_S", "600")) if timeout is None else timeout
    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    handlers = [] if os.environ.get("JUDGE_API_TRUST_ENV") == "1" else [urllib.request.ProxyHandler({})]
    opener = urllib.request.build_opener(*handlers)
    last = "no attempt"
    for attempt in range(retries + 1):
        wait = None
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers=headers)
            with opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            # 401/403 bodies can echo key fragments: status only
            raw = "" if e.code in (401, 403) else e.read().decode(errors="replace")
            detail = _scrub(raw[:300], api_key)
            last = f"HTTP {e.code}" + (f": {detail}" if detail else "")
            if e.code not in RETRY_STATUS:
                raise JudgeAPIError(f"judge API {last}", e.code, _error_param(raw)) from None
            wait = _retry_after(e.headers)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last = f"{type(e).__name__}: {_scrub(str(getattr(e, 'reason', e)), api_key)[:200]}"
        except json.JSONDecodeError as e:
            last = f"invalid JSON body: {e}"
        if attempt < retries:
            wait = wait if wait is not None else min(2.0 * 2 ** attempt, 60.0)
            print(f"[pwa judge] attempt {attempt + 1}/{retries + 1} failed ({last}); retrying in {wait:.0f}s",
                  file=sys.stderr)
            _sleep(wait)
    raise JudgeAPIError(f"judge API failed after {retries + 1} attempts: {last}")


class Models:
    def __init__(self, client: "OpenAIJudgeClient"):
        self._c = client

    def generate_content(self, *, model: str, contents: Any, config: Any = None, **_kw) -> SimpleNamespace:
        body = build_request(model, contents, config, self._c.reasoning_effort, self._c.files)
        for k in self._c.dropped:
            body.pop(k, None)
        while True:
            try:
                return response_from(post_chat(self._c.base_url, self._c.api_key, body))
            except JudgeAPIError as e:
                if e.status != 400 or e.param not in DROPPABLE or e.param not in body:
                    raise
                print(f"[pwa judge] model rejects {e.param}={body[e.param]!r}; retrying with the provider default",
                      file=sys.stderr)
                self._c.dropped.add(e.param)
                body.pop(e.param)


class OpenAIJudgeClient:
    """Duck-typed google.genai.Client: .models.generate_content and .files.upload/get/delete."""

    def __init__(self, base_url: str, api_key: str, reasoning_effort: str | None = None):
        self.base_url, self.api_key, self.reasoning_effort = base_url, api_key, reasoning_effort
        self.files = Files()
        self.models = Models(self)
        self.dropped: set[str] = set()  # DROPPABLE params this model rejected


def judge_api() -> tuple[str, str]:
    """(base_url, api_key): JUDGE_API_URL / JUDGE_API_KEY, falling back to PLAYER_API_URL / PLAYER_API_KEY.
    The URL falls back only when the player provider is openai (PLAYER_API_PROVIDER unset counts as openai,
    as in the workflow); otherwise set JUDGE_API_URL. Values are never logged."""
    e = os.environ
    url = (e.get("JUDGE_API_URL") or "").strip()
    if not url:
        if (e.get("PLAYER_API_PROVIDER") or "openai").strip().lower() != "openai":
            raise ValueError("PLAYER_API_PROVIDER is not openai; set JUDGE_API_URL for an openai: screening judge")
        url = (e.get("PLAYER_API_URL") or "").strip() or DEFAULT_URL
    return url, (e.get("JUDGE_API_KEY") or "").strip() or (e.get("PLAYER_API_KEY") or "").strip()


def make_client(reasoning_effort: str | None = None):
    """Factory with create_gemini_client's signature (keyword api_key ignored: the judge key is used)."""

    def create(*, api_key: str | None = None) -> OpenAIJudgeClient:  # noqa: ARG001
        url, key = judge_api()
        if not key:
            raise ValueError("Set JUDGE_API_KEY or PLAYER_API_KEY for the openai: screening judge")
        return OpenAIJudgeClient(url, key, reasoning_effort)

    return create
