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
        stub = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
                out = json.dumps(stub.reply if stub.status == 200 else {"error": "bad key"}).encode()
                self.send_response(stub.status)
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
    fn = agent_api.make_request_fn("openai")
    assert fn(args(stub.url), "pick", ["QUJD", "REVG"]) == " w "
    r = stub.requests[0]
    assert r["path"] == "/v1/chat/completions"
    assert r["headers"]["Authorization"] == "Bearer sekrit"
    assert "x-api-key" not in {k.lower() for k in r["headers"]}
    b = r["body"]
    assert b["model"] == "m-1" and b["max_completion_tokens"] == 1024
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
