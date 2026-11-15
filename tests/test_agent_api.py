"""Provider-aware agent client against a local stub server. No real API calls."""
import importlib.util
import json
import subprocess
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.common import agent_api  # noqa: E402


class Stub:
    def __init__(self):
        self.requests = []
        self.reply = {"choices": [{"message": {"content": " w "}}]}
        self.status = 200
        self.queue = []  # (status, body) served first, one per request; then reply/status
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                if stub.queue:
                    status, reply = stub.queue.pop(0)
                else:
                    status = stub.status
                    reply = stub.reply if status == 200 else {"error": "bad key"}
                out = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.server.shutdown()


def args(url):
    return types.SimpleNamespace(agent_base_url=url, agent_model="m-1", agent_api_key="sekrit",
                                 agent_user_key="sekrit", agent_biz_scene="offline", agent_timeout_s=5)


def test_openai_headers_payload_parse(stub, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")  # must be ignored, like upstream trust_env=False
    monkeypatch.setenv("PLAYER_API_PROVIDER", "openai")
    for k in ("PLAYER_MAX_COMPLETION_TOKENS", "PLAYER_REASONING_EFFORT", "PLAYER_EMPTY_RETRIES"):
        monkeypatch.delenv(k, raising=False)
    fn = agent_api.make_request_fn("openai")
    assert fn(args(stub.url), "pick", ["QUJD", "REVG"]) == " w "
    r = stub.requests[0]
    assert r["path"] == "/v1/chat/completions"
    assert r["headers"]["Authorization"] == "Bearer sekrit"
    assert "x-api-key" not in {k.lower() for k in r["headers"]}
    b = r["body"]
    assert b["model"] == "m-1" and b["max_completion_tokens"] == 4096 and b["reasoning_effort"] == "low"
    content = b["messages"][0]["content"]
    assert [c["type"] for c in content] == ["image_url", "image_url", "text"]
    assert content[0]["image_url"]["url"] == "data:image/jpeg;base64,QUJD" and content[2]["text"] == "pick"


def test_anthropic_headers_and_list_content(stub):
    stub.reply = {"choices": [{"message": {"content": [{"type": "text", "text": "LE"}, {"text": "FT"}]}}]}
    assert agent_api.make_request_fn("anthropic")(args(stub.url), "p", []) == "LEFT"
    h = {k.lower(): v for k, v in stub.requests[0]["headers"].items()}
    assert h["x-api-key"] == "sekrit" and h["anthropic-version"] == "2023-06-01" and "authorization" not in h


def test_errors(stub):
    fn = agent_api.make_request_fn("openai")
    stub.status = 401
    with pytest.raises(RuntimeError) as e:
        fn(args(stub.url), "p", [])
    assert "401" in str(e.value) and "sekrit" not in str(e.value)
    stub.status, stub.reply = 200, {"choices": []}
    with pytest.raises(RuntimeError, match="no choices"):
        fn(args(stub.url), "p", [])


def test_patch_sets_defaults_and_replaces(monkeypatch):
    mod = types.SimpleNamespace(request_agent_action="orig")
    monkeypatch.delenv("PLAYER_API_PROVIDER", raising=False)
    assert agent_api.patch(mod) == "upstream" and mod.request_agent_action == "orig"
    monkeypatch.setenv("PLAYER_API_PROVIDER", "OpenAI")
    monkeypatch.delenv("PLAYER_MODEL", raising=False)
    monkeypatch.delenv("PLAYER_API_URL", raising=False)
    assert agent_api.patch(mod) == "openai"
    assert mod.request_agent_action.provider == "openai"
    import os
    assert os.environ["PLAYER_MODEL"] == "gpt-4.1-mini" and os.environ["PLAYER_API_URL"].startswith("https://api.openai.com")
    monkeypatch.setenv("PLAYER_API_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        agent_api.patch(mod)


needs_httpx = pytest.mark.skipif(importlib.util.find_spec("httpx") is None, reason="upstream run_agent needs httpx")


@needs_httpx
def test_patch_real_run_agent_module(monkeypatch):
    from adapters.common.upstream import import_run_agent
    ra = import_run_agent()
    monkeypatch.setenv("PLAYER_API_PROVIDER", "openai")
    monkeypatch.setattr(ra, "request_agent_action", ra.request_agent_action)  # restore after test
    agent_api.patch(ra)
    assert getattr(ra.request_agent_action, "provider", None) == "openai"


@needs_httpx
@pytest.mark.parametrize("runner", ["sana_wm", "matrix_game3"])
def test_adapter_help(runner):
    r = subprocess.run([sys.executable, str(ROOT / "adapters" / runner / "run.py"), "--help"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0 and "--action-source" in r.stdout


# -- empty replies, truncation, reasoning_effort, counters ----------------------------------------------------

def ok(text, finish="stop"):
    return 200, {"choices": [{"message": {"content": text}, "finish_reason": finish}],
                 "usage": {"completion_tokens": 3, "completion_tokens_details": {"reasoning_tokens": 0}}}


def empty(finish="length", tokens=4096):
    return 200, {"choices": [{"message": {"content": ""}, "finish_reason": finish}],
                 "usage": {"completion_tokens": tokens, "completion_tokens_details": {"reasoning_tokens": tokens}}}


def player(argv=(), env=None):
    cfg, _ = agent_api.configure(list(argv), env if env is not None else {"PLAYER_API_PROVIDER": "openai"})
    stats = agent_api.PlayerStats()
    return agent_api.make_request_fn("openai", cfg=cfg, stats=stats), cfg, stats


def test_configure_defaults_args_and_env():
    cfg, rest = agent_api.configure(["run.py", "--tasks", "A"], {"PLAYER_API_PROVIDER": "openai"})
    assert rest == ["run.py", "--tasks", "A"]
    assert (cfg.max_completion_tokens, cfg.reasoning_effort, cfg.empty_retries) == (4096, "low", 2)
    cfg, _ = agent_api.configure([], {"PLAYER_API_PROVIDER": "anthropic"})
    assert cfg.reasoning_effort is None  # only openai gets a default effort
    env = {"PLAYER_API_PROVIDER": "openai", "PLAYER_MAX_COMPLETION_TOKENS": "2048", "PLAYER_REASONING_EFFORT": "",
           "PLAYER_EMPTY_RETRIES": "1"}
    cfg, _ = agent_api.configure([], env)
    assert (cfg.max_completion_tokens, cfg.reasoning_effort, cfg.empty_retries) == (2048, None, 1)
    # runner args win over env, both spellings, and are stripped from argv
    cfg, rest = agent_api.configure(["run.py", "--player-max-completion-tokens", "8192", "--tasks", "A",
                                     "--player-reasoning-effort=medium", "--player-empty-retries", "0"], env)
    assert rest == ["run.py", "--tasks", "A"]
    assert (cfg.max_completion_tokens, cfg.reasoning_effort, cfg.empty_retries) == (8192, "medium", 0)
    off = agent_api.configure(["--player-reasoning-effort", "off"], {"PLAYER_API_PROVIDER": "openai"})[0]
    assert off.reasoning_effort is None
    with pytest.raises(SystemExit):
        agent_api.configure(["--player-max-completion-tokens", "lots"], {})
    with pytest.raises(SystemExit):
        agent_api.configure(["--player-empty-retries"], {})


def test_empty_then_good_reply_is_retried(stub, capsys):
    fn, _, stats = player()
    stub.queue = [empty(), ok("LEFT")]
    assert fn(args(stub.url), "pick", ["QUJD"]) == "LEFT"
    assert [r["body"]["max_completion_tokens"] for r in stub.requests] == [4096, 4096]
    out = capsys.readouterr().out
    assert ("[agent] empty reply (finish_reason=length, completion_tokens=4096, reasoning_tokens=4096) -> retry 1 "
            "(max_completion_tokens=4096)") in out
    assert stats.total == {"decisions": 0, "calls": 2, "empty": 1, "retries": 1, "errors": 0, "fallbacks": 0}


def test_last_retry_doubles_budget_then_repeat_gets_one_call(stub, capsys):
    fn, _, stats = player()
    stub.queue = [empty(), empty(finish="stop"), empty()]
    assert fn(args(stub.url), "pick", []) == ""
    assert [r["body"]["max_completion_tokens"] for r in stub.requests] == [4096, 4096, 8192]
    out = capsys.readouterr().out
    assert "-> retry 2 (max_completion_tokens=8192)" in out and "no retries left" in out
    # upstream re-sends the same request: one call at the doubled budget, no more retries
    stub.queue = [empty()]
    assert fn(args(stub.url), "pick", []) == ""
    assert stub.requests[-1]["body"]["max_completion_tokens"] == 8192
    assert stats.total["calls"] == 4 and stats.total["retries"] == 2 and stats.total["empty"] == 4
    # a new prompt starts over with the normal budget and retries
    stub.queue = [ok("W")]
    assert fn(args(stub.url), "other", []) == "W"
    assert stub.requests[-1]["body"]["max_completion_tokens"] == 4096


def test_length_truncated_reply_with_text_is_retried(stub):
    fn, _, stats = player()
    stub.queue = [ok("RI", finish="length"), ok("RIGHT")]
    assert fn(args(stub.url), "pick", []) == "RIGHT"
    assert stats.total["empty"] == 1 and stats.total["retries"] == 1


def test_output_limit_400_is_retried_then_raises(stub):
    fn, _, stats = player(env={"PLAYER_API_PROVIDER": "openai", "PLAYER_EMPTY_RETRIES": "1"})
    limit = (400, {"error": {"message": "Could not finish the message because max_tokens or model output limit "
                                        "was reached. Please try again with higher max_tokens.", "param": None}})
    stub.queue = [limit, ok("UP")]
    assert fn(args(stub.url), "pick", []) == "UP"
    assert [r["body"]["max_completion_tokens"] for r in stub.requests] == [4096, 8192]
    stub.queue = [limit, limit]
    with pytest.raises(RuntimeError, match="HTTP 400"):
        fn(args(stub.url), "again", [])
    assert stats.total["errors"] == 1 and stats.total["empty"] == 3


def test_rejected_reasoning_effort_is_dropped_and_remembered(stub, capsys):
    fn, cfg, stats = player()
    stub.queue = [(400, {"error": {"message": "Unsupported parameter: 'reasoning_effort' is not supported with "
                                              "this model.", "param": "reasoning_effort"}}), ok("D")]
    assert fn(args(stub.url), "pick", []) == "D"
    assert stub.requests[0]["body"]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in stub.requests[1]["body"]
    assert "rejects reasoning_effort='low'" in capsys.readouterr().out
    stub.queue = [ok("A")]
    fn(args(stub.url), "next", [])
    assert "reasoning_effort" not in stub.requests[2]["body"] and cfg.send_effort is False
    assert stats.total["errors"] == 0 and stats.total["calls"] == 3


def test_other_400_raises_and_counts_error(stub):
    fn, _, stats = player()
    stub.queue = [(400, {"error": {"message": "bad image", "param": "messages"}})]
    with pytest.raises(RuntimeError, match="HTTP 400"):
        fn(args(stub.url), "pick", [])
    assert stats.total["errors"] == 1 and stats.total["empty"] == 0 and len(stub.requests) == 1


def test_no_secrets_in_logs_or_errors(stub, capsys):
    fn, _, _ = player()
    stub.queue = [empty(), (400, {"error": {"message": "bad key sekrit", "param": None}})]
    with pytest.raises(RuntimeError) as e:
        fn(args(stub.url), "pick", [])
    out = capsys.readouterr()
    assert "sekrit" not in out.out + out.err and "sekrit" not in str(e.value) and "***" in str(e.value)


def _fake_run_agent():
    """run_agent stand-in: decide_action asks request_agent_action like upstream (3 attempts, then a fallback
    printed through the module's print); run_task makes script[task] decisions and writes <tid>_result.json."""
    mod = types.SimpleNamespace(script={})

    def decide_action(task, *a, **kw):
        for attempt in range(1, 4):
            try:
                text = str(mod.request_agent_action(mod.args, "goal " + task["task_id"], []) or "").strip().upper()
                if text:
                    return text
                mod.print(f"    [agent] invalid response attempt {attempt}: {text!r}")
            except Exception as exc:  # noqa: BLE001
                mod.print(f"    [agent] error attempt {attempt}: {exc}")
        mod.print("    [agent] fallback=RIGHT")
        return "RIGHT"

    def run_task(task, engine, output_dir, args):
        for _ in range(mod.script[task["task_id"]]):
            mod.decide_action(task)
        d = Path(output_dir) / task["task_id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{task['task_id']}_result.json").write_text(json.dumps({"success": True}))
        return {"task_id": task["task_id"], "success": True}

    mod.decide_action, mod.run_task, mod.request_agent_action = decide_action, run_task, None
    return mod


def test_counters_per_task_total_and_result_json(stub, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PLAYER_API_PROVIDER", "openai")
    mod = _fake_run_agent()
    mod.script = {"GC031": 2, "GC036": 1}
    cfg, _ = agent_api.configure(["--player-empty-retries", "1"])
    assert agent_api.patch(mod, cfg) == "openai"
    mod.args = args(stub.url)
    # GC031 decision 1: empty, retry good. Decision 2: empty, retry (2x) empty; upstream attempts 2 and 3 are
    # repeats, one call each, both empty -> fallback. GC036: good at once.
    stub.queue = [empty(), ok("LEFT"), empty(), empty(), empty(), empty(), ok("END")]
    mod.run_task({"task_id": "GC031"}, None, tmp_path, None)
    mod.run_task({"task_id": "GC036"}, None, tmp_path, None)
    agent_api.finish(mod)
    out = capsys.readouterr().out
    assert "[adapter] player request: max_completion_tokens=4096 reasoning_effort=low empty_retries=1" in out
    assert [ln for ln in out.splitlines() if ln.startswith("[agent] player")] == [
        "[agent] player task=GC031 decisions=2 calls=6 empty=5 retries=2 errors=0 fallbacks=1",
        "[agent] player task=GC036 decisions=1 calls=1 empty=0 retries=0 errors=0 fallbacks=0",
        "[agent] player total tasks=2 decisions=3 calls=7 empty=5 retries=2 errors=0 fallbacks=1",
    ]
    assert out.count("[agent] fallback=RIGHT") == 1
    saved = json.loads((tmp_path / "GC031" / "GC031_result.json").read_text())
    assert saved["player"]["fallbacks"] == 1 and saved["player"]["decisions"] == 2


def test_upstream_provider_still_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PLAYER_API_PROVIDER", raising=False)
    mod = _fake_run_agent()
    mod.script = {"IF001": 1}
    mod.request_agent_action = lambda *a: ""
    assert agent_api.patch(mod) == "upstream"
    mod.args = None
    mod.run_task({"task_id": "IF001"}, None, tmp_path, None)
    assert "[agent] player task=IF001 decisions=1 calls=0 empty=0 retries=0 errors=0 fallbacks=1" in \
        capsys.readouterr().out


def test_pwa_gen_player_fields_match_agent_api():
    from pwa import gen
    assert gen.PLAYER_FIELDS == agent_api.FIELDS
    line = "[agent] player total tasks=2 decisions=3 calls=7 empty=5 retries=2 errors=0 fallbacks=1\n"
    assert gen.parse_kv(line)["fallbacks"] == "1"
