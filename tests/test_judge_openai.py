"""OpenAI-compatible screening judge and judge panels: request translation, response shaping, retries
(against a local fake chat server), judge specs, panel agreement and calibration maths. No API key, no GPU."""
import argparse
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pwa import judge_openai as jo
from pwa import panel, score
from pwa.core import PwaError

KEY = "sk-test-not-a-real-key"


class FakeChat:
    """Local OpenAI-compatible /v1/chat/completions. `script` is a list of (status, body, headers) replies;
    the last one repeats. Every request body and its Authorization header are recorded."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        fake = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
                status, reply, headers = fake.script.pop(0) if len(fake.script) > 1 else fake.script[0]
                data = (reply if isinstance(reply, str) else json.dumps(reply)).encode()
                self.send_response(status)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ok(text, **extra):
    return 200, {"model": "fake", "choices": [{"message": {"role": "assistant", "content": text},
                                               "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, **extra}, None


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(jo, "_sleep", slept.append)
    return slept


# ---- request translation

def test_build_request_duck_typed_parts(tmp_path):
    img = tmp_path / "sheet.jpg"
    img.write_bytes(b"\xff\xd8jpegbytes")
    files = jo.Files()
    up = files.upload(file=img)
    assert files.get(up.name).state == "ACTIVE" and up.mime_type == "image/jpeg"
    content = NS(role="user", parts=[NS(text="PROMPT"), NS(text=None, inline_data=NS(data=b"\x89PNG", mime_type="image/png")),
                                     NS(text=None, inline_data=None, file_data=NS(file_uri=up.uri, mime_type="image/jpeg"))])
    cfg = NS(response_mime_type="application/json", temperature=0.1, system_instruction="be strict",
             response_schema=None, response_json_schema=None, top_p=None, seed=7, max_output_tokens=None)
    body = jo.build_request("openai:gpt-6-luna", content, cfg, "low", files)
    assert body["model"] == "gpt-6-luna"  # provider prefix is ours, never sent
    assert body["messages"][0] == {"role": "system", "content": "be strict"}
    parts = body["messages"][1]["content"]
    assert body["messages"][1]["role"] == "user" and parts[0] == {"type": "text", "text": "PROMPT"}
    assert parts[1]["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode()
    assert parts[2]["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(img.read_bytes()).decode()
    assert parts[1]["image_url"]["detail"] == "high"
    assert body["response_format"] == {"type": "json_object"}
    assert (body["temperature"], body["seed"], body["reasoning_effort"]) == (0.1, 7, "low")
    assert "top_p" not in body and "max_completion_tokens" not in body
    files.delete(up.name)
    with pytest.raises(ValueError):  # deleted, or never uploaded through this client
        jo.build_request("m", content, cfg, None, files)


def test_build_request_schema_order_and_temperature_switch(monkeypatch):
    cfg = {"response_mime_type": "application/json", "temperature": 0.1,
           "response_schema": {"type": "OBJECT", "properties": {"s": {"type": "NUMBER"}}}}
    body = jo.build_request("m", ["a", "b"], cfg)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object", "properties": {"s": {"type": "number"}}}
    assert [p["text"] for p in body["messages"][0]["content"]] == ["a", "b"]  # a bare list of parts is one turn
    assert "reasoning_effort" not in body
    monkeypatch.setenv("JUDGE_API_NO_TEMPERATURE", "1")
    assert "temperature" not in jo.build_request("m", "x", cfg)
    assert "response_format" not in jo.build_request("m", "x", {"temperature": 0.2})
    with pytest.raises(ValueError):
        jo.build_request("m", NS(role="user", parts=[NS(text=None, inline_data=None, file_data=None)]))


def test_build_request_with_real_genai_types(tmp_path):
    types = pytest.importorskip("google.genai.types")
    content = types.Content(role="user", parts=[types.Part.from_text(text="P"),
                                                types.Part.from_bytes(data=b"img", mime_type="image/jpeg")])
    cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1,
                                      system_instruction="sys")
    body = jo.build_request("openai:x", content, cfg)
    assert body["messages"][0]["content"] == "sys"
    assert body["messages"][1]["content"][1]["image_url"]["url"] == "data:image/jpeg;base64," + base64.b64encode(b"img").decode()
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0.1
    schema_cfg = types.GenerateContentConfig(response_mime_type="application/json", response_schema=types.Schema(
        type=types.Type.OBJECT, properties={"s": types.Schema(type=types.Type.NUMBER)}))
    sch = jo.build_request("m", "x", schema_cfg)["response_format"]["json_schema"]["schema"]
    assert sch["type"] == "object" and sch["properties"]["s"]["type"] == "number"


# ---- response shaping

def test_response_from():
    r = jo.response_from(ok('{"a": 1}')[1])
    assert r.text == '{"a": 1}' and r.candidates[0].content.parts[0].text == r.text
    assert r.usage_metadata.total_token_count == 15 and r.model_version == "fake"
    r = jo.response_from({"choices": [{"message": {"content": [{"type": "text", "text": "x"}, {"type": "text", "text": "y"}]}}]})
    assert r.text == "xy"
    with pytest.raises(RuntimeError, match="no text"):
        jo.response_from({"choices": [{"message": {"content": None, "refusal": "no"}, "finish_reason": "stop"}]})
    with pytest.raises(RuntimeError, match="no choices"):
        jo.response_from({"error": "x"})


# ---- HTTP, retries

def test_post_chat_retries_429_then_succeeds(no_sleep):
    srv = FakeChat([(429, {"error": "slow down"}, {"Retry-After": "3"}), (503, "busy", None), ok("{}")])
    try:
        out = jo.post_chat(srv.url, KEY, {"model": "m", "messages": []}, retries=3, timeout=5)
    finally:
        srv.close()
    assert out["choices"][0]["message"]["content"] == "{}"
    assert len(srv.requests) == 3 and srv.requests[0]["path"] == "/v1/chat/completions"
    assert srv.requests[0]["auth"] == f"Bearer {KEY}"
    assert no_sleep == [3.0, 4.0]  # Retry-After, then exponential backoff (2 * 2**1)


def test_post_chat_bounded_and_non_retryable(no_sleep):
    srv = FakeChat([(500, "down", None)])
    try:
        with pytest.raises(jo.JudgeAPIError, match="after 3 attempts: HTTP 500"):
            jo.post_chat(srv.url, KEY, {}, retries=2, timeout=5)
        assert len(srv.requests) == 3 and no_sleep == [2.0, 4.0]
        srv.script = [(400, f"bad request for key {KEY}", None)]
        with pytest.raises(jo.JudgeAPIError) as e:
            jo.post_chat(srv.url, KEY, {}, retries=2, timeout=5)
        assert "HTTP 400" in str(e.value) and KEY not in str(e.value) and len(srv.requests) == 4
        srv.script = [(401, f"Incorrect API key {KEY}", None)]
        with pytest.raises(jo.JudgeAPIError) as e:
            jo.post_chat(srv.url, KEY, {}, retries=2, timeout=5)
        assert str(e.value) == "judge API HTTP 401"  # auth errors: status only
    finally:
        srv.close()


def test_post_chat_connection_error_is_retried(no_sleep):
    with pytest.raises(jo.JudgeAPIError, match="after 2 attempts"):
        jo.post_chat("http://127.0.0.1:9/v1", KEY, {}, retries=1, timeout=2)
    assert no_sleep == [2.0]


def test_client_generate_content_roundtrip(no_sleep, monkeypatch):
    srv = FakeChat([ok('{"final_score_1_to_5": 3}')])
    monkeypatch.setenv("JUDGE_API_URL", srv.url)
    monkeypatch.setenv("JUDGE_API_KEY", KEY)
    try:
        client = jo.make_client("medium")()
        r = client.models.generate_content(model="openai:j", contents=NS(role="user", parts=[NS(text="hi")]),
                                           config=NS(response_mime_type="application/json", temperature=0.1))
    finally:
        srv.close()
    assert json.loads(r.text) == {"final_score_1_to_5": 3}
    assert srv.requests[0]["body"]["model"] == "j" and srv.requests[0]["body"]["reasoning_effort"] == "medium"


def test_rejected_temperature_is_dropped_and_remembered(no_sleep, monkeypatch, capsys):
    # the real gpt-6-luna reply to upstream's temperature 0.1 (all 48 calls of the first real screening run)
    rejected = {"error": {"message": "Unsupported value: 'temperature' does not support 0.1 with this model. "
                                     "Only the default (1) value is supported.", "type": "invalid_request_error",
                          "param": "temperature", "code": "unsupported_value"}}
    srv = FakeChat([(400, rejected, None), ok('{"s": 1}'), ok('{"s": 2}')])
    monkeypatch.setenv("JUDGE_API_URL", srv.url)
    monkeypatch.setenv("JUDGE_API_KEY", KEY)
    cfg = NS(response_mime_type="application/json", temperature=0.1)
    try:
        client = jo.make_client("low")()
        r1 = client.models.generate_content(model="openai:j", contents="x", config=cfg)
        r2 = client.models.generate_content(model="openai:j", contents="x", config=cfg)
    finally:
        srv.close()
    assert (json.loads(r1.text), json.loads(r2.text)) == ({"s": 1}, {"s": 2})
    bodies = [q["body"] for q in srv.requests]
    assert len(bodies) == 3 and bodies[0]["temperature"] == 0.1
    assert all("temperature" not in b for b in bodies[1:])  # retried without it, then left out up front
    assert all(b["reasoning_effort"] == "low" and b["response_format"] == {"type": "json_object"} for b in bodies)
    assert "rejects temperature=0.1" in capsys.readouterr().err


def test_other_400s_are_not_retried(no_sleep, monkeypatch):
    srv = FakeChat([(400, {"error": {"message": "bad effort", "param": "reasoning_effort"}}, None),
                    (400, {"error": {"message": "nope", "param": None}}, None)])
    monkeypatch.setenv("JUDGE_API_URL", srv.url)
    monkeypatch.setenv("JUDGE_API_KEY", KEY)
    try:
        client = jo.make_client("low")()
        for _ in range(2):
            with pytest.raises(jo.JudgeAPIError, match="HTTP 400"):
                client.models.generate_content(model="openai:j", contents="x", config=NS(temperature=0.1))
    finally:
        srv.close()
    assert len(srv.requests) == 2 and client.dropped == set()


def test_judge_api_env_fallbacks(monkeypatch):
    for k in ("JUDGE_API_URL", "JUDGE_API_KEY", "PLAYER_API_URL", "PLAYER_API_KEY", "PLAYER_API_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    assert jo.judge_api() == ("https://api.openai.com/v1", "")
    monkeypatch.setenv("PLAYER_API_URL", "https://player.example/v1")
    monkeypatch.setenv("PLAYER_API_KEY", "pk")
    assert jo.judge_api() == ("https://player.example/v1", "pk")
    monkeypatch.setenv("JUDGE_API_URL", "https://judge.example/v1")
    monkeypatch.setenv("JUDGE_API_KEY", "jk")
    assert jo.judge_api() == ("https://judge.example/v1", "jk")
    monkeypatch.setenv("JUDGE_API_KEY", "")  # empty secret in Actions: never the player key to another host
    assert jo.judge_api() == ("https://judge.example/v1", "")
    monkeypatch.setenv("JUDGE_API_URL", "https://player.example/v1/")  # the player's own URL -> fall back
    assert jo.judge_api()[1] == "pk"
    monkeypatch.delenv("JUDGE_API_URL")
    assert jo.judge_api() == ("https://player.example/v1", "pk")
    monkeypatch.delenv("JUDGE_API_URL", raising=False)
    monkeypatch.setenv("PLAYER_API_PROVIDER", "anthropic")
    with pytest.raises(ValueError, match="JUDGE_API_URL"):
        jo.judge_api()


# ---- judge specs, command and env

def test_judge_spec_parsing():
    j = score.Judge.parse("openai:gpt-6-luna")
    assert (j.provider, j.model, j.thinking, j.slug) == ("openai", "gpt-6-luna", None, "openai-gpt-6-luna")
    assert j.upstream_model == "openai:gpt-6-luna" and j.spec == "openai:gpt-6-luna" and j.needs_shim
    assert j.label == "PROXY JUDGE (openai:gpt-6-luna), not comparable to the leaderboard"
    j = score.Judge.parse("openai:gpt-6-luna:high")
    assert (j.thinking, j.slug) == ("high", "openai-gpt-6-luna-think-high")
    g = score.Judge.parse("gemini-4-hydrogen:low")
    assert g == score.Judge("gemini-4-hydrogen", "low") and g.slug == "gemini-4-hydrogen-think-low"
    assert score.Judge.parse("gemini-4-hydrogen") == score.Judge("gemini-4-hydrogen") and not score.Judge("x").needs_shim
    assert score.Judge.parse("gemini:gemini-4-hydrogen").provider == "gemini"
    assert score.Judge.parse("m", "low") == score.Judge("m", "low")
    with pytest.raises(PwaError):
        score.Judge.parse("m:low", "high")
    with pytest.raises(PwaError):
        score.Judge.parse("openai:")


def test_judges_of_panel():
    ns = lambda m=None, t=None: argparse.Namespace(judge_model=m, judge_thinking=t, cmd="x")  # noqa: E731
    assert score.judges_of(ns()) == []
    js = score.judges_of(ns(["gemini-4-hydrogen:low", "openai:gpt-6-luna"]))
    assert [j.slug for j in js] == ["gemini-4-hydrogen-think-low", "openai-gpt-6-luna"]
    assert score.judges_of(ns(["m"], "low")) == [score.Judge("m", "low")]
    with pytest.raises(PwaError):
        score.judges_of(ns(["a", "b"], "low"))  # thinking flag is ambiguous in a panel
    with pytest.raises(PwaError):
        score.judges_of(ns(["a", "a"]))
    with pytest.raises(PwaError):
        score.judge_of(ns(["a", "b"]))


def test_verifier_cmd_and_env_for_openai(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key")
    monkeypatch.setenv("PWA_JUDGE_PROVIDER", "openai")  # stray value never reaches other judges
    info = {"family": "if", "task_id": "IF002", "dataset": "/d.json", "image": "/nonexistent.jpg"}
    j = score.Judge.parse("openai:gpt-6-luna")
    cmd = score.verifier_cmd("score", info, Path("/v.mp4"), Path("/o.json"), False, judge=j)
    assert cmd[1:3] == ["-m", "pwa.judge_shim"] and cmd[cmd.index("--model") + 1] == "openai:gpt-6-luna"
    e = score.verifier_env(j)
    assert e["PWA_JUDGE_PROVIDER"] == "openai" and "PWA_JUDGE_THINKING" not in e
    assert e["GEMINI_API_KEY"] == score.GEMINI_KEY_PLACEHOLDER and str(score.ROOT) in e["PYTHONPATH"]
    assert score.verifier_env()["GEMINI_API_KEY"] == "real-gemini-key" and "PWA_JUDGE_PROVIDER" not in score.verifier_env()
    assert "PWA_JUDGE_PROVIDER" not in score.verifier_env(score.Judge("m", "low"))
    assert score.verifier_env(score.Judge.parse("openai:x:low"))["PWA_JUDGE_THINKING"] == "low"


def test_shim_installs_openai_factory(monkeypatch):
    pytest.importorskip("google.genai")
    import sys
    monkeypatch.syspath_prepend(str(score.PLAYWORLD))
    gc = pytest.importorskip("metrics.gemini_client")
    from pwa import judge_shim
    monkeypatch.setattr(gc, "create_gemini_client", gc.create_gemini_client)  # restored after the test
    monkeypatch.setenv("JUDGE_API_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("JUDGE_API_KEY", KEY)
    judge_shim.install_openai("low")
    client = sys.modules["metrics.gemini_client"].create_gemini_client()
    assert isinstance(client, jo.OpenAIJudgeClient) and client.reasoning_effort == "low"


# ---- panel agreement and calibration maths

def _rep(exp, slug, tasks):
    """tasks: {tid: [pass values]}"""
    out = {}
    for tid, vals in tasks.items():
        v = [x for x in vals if x is not None]
        out[tid] = {"family": "gc", "mean": sum(v) / len(v) if v else None, "values": vals}
    return {"exp": exp, "judge": {"slug": slug, "name": slug} if slug else None, "tasks": out,
            "passes": [1, 2], "overall": None}


def test_panel_report_keeps_capped_smoke_label():
    reps = [_rep("e", "j1", {"T1": [2, 2]}), _rep("e", "j2", {"T1": [3, 3]})]
    for r in reps:
        r["max_chunks"] = 4
    p = panel.panel(reps)
    assert p["max_chunks"] == 4
    for md in (False, True):
        out = panel.render_panel(p, md)
        assert "capped smoke run: 4 agent chunks per rollout (official 30)" in out.lower()
    for r in reps:
        r["max_chunks"] = None
    for md in (False, True):
        assert "capped" not in panel.render_panel(panel.panel(reps), md).lower()


def test_panel_cells_moves_only_when_every_judge_agrees():
    a1 = _rep("a", "j1", {"T1": [2, 2], "T2": [3, 3], "T3": [2, 2], "T4": [2, 2], "T5": [None, None]})
    b1 = _rep("b", "j1", {"T1": [3, 3], "T2": [2, 2], "T3": [3, 3], "T4": [2, 2], "T5": [3, 3]})
    a2 = _rep("a", "j2", {"T1": [2, 2], "T2": [3, 3], "T3": [2, 2], "T4": [2, 2], "T5": [2, 2]})
    b2 = _rep("b", "j2", {"T1": [3.5, 3.5], "T2": [1.5, 1.5], "T3": [2.5, 2.5], "T4": [1.5, 1.5], "T5": [3, 3]})
    c = panel.panel_cells([(a1, b1), (a2, b2)])
    by = {r["task_id"]: r for r in c["tasks"]}
    assert (by["T1"]["move"], by["T1"]["agree"]) == ("up", True)  # +1.0 and +1.5
    assert (by["T2"]["move"], by["T2"]["agree"]) == ("down", True)
    assert (by["T3"]["move"], by["T3"]["agree"]) == ("", True)  # +1.0 and +0.5: same way, only one moves
    assert (by["T4"]["move"], by["T4"]["agree"]) == ("", False)  # 0 and -0.5
    assert c["unscored"] == ["T5"] and (c["up"], c["down"], c["n_common"], c["n_agree"]) == (1, 1, 4, 3)
    # alone, each judge counts its own scored tasks: j1 T1, T3 up; j2 T1 and T5 (unscored under j1) up
    assert c["per_judge"] == {"j1": {"up": 2, "down": 1}, "j2": {"up": 2, "down": 1}}
    assert by["T1"]["judges"]["j2"]["delta"] == pytest.approx(1.5)
    txt = panel.render_panel_cells(c)
    assert "screening, not comparable to the leaderboard" in txt and "panel up 1  down 1  of 4" in txt
    assert "caps differ" not in txt
    c["max_chunks"] = {"a": 4, "b": None}  # set by `pwa cells` from each run's meta.json
    assert "chunk caps differ (A=4, B=none)" in panel.render_panel_cells(c)


def test_spearman_known_values():
    assert panel.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert panel.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    # ties take average ranks: x ranks 1, 2.5, 2.5, 4 vs y ranks 1..4 -> rho = 4.5 / sqrt(4.5 * 5)
    assert panel.spearman([1, 2, 2, 3], [1, 2, 3, 4]) == pytest.approx(4.5 / (4.5 * 5) ** 0.5)
    assert panel.spearman([1, 1, 1], [1, 2, 3]) is None and panel.spearman([1, 2], [1, 2]) is None


def test_calibrate_maths():
    off = _rep("e", None, {"T1": [1, 1], "T2": [2, 3], "T3": [4, 4], "T4": [3, 3], "T5": [None, None]})
    scr = _rep("e", "j", {"T1": [2, 2], "T2": [2, 2], "T3": [5, 4], "T4": [1, 1], "T5": [3, 3]})
    c = panel.calibrate(off, [scr])
    r = c["judges"][0]
    # official means 1, 2.5, 4, 3; screening 2, 2, 4.5, 1 over T1..T4 (T5 has no official mean)
    assert r["n"] == 4
    assert r["mad"] == pytest.approx((1 + 0.5 + 0.5 + 2) / 4) and r["bias"] == pytest.approx((1 - 0.5 + 0.5 - 2) / 4)
    assert (r["n_far"], r["far"]) == (2, ["T1", "T4"])
    assert r["spearman"] == pytest.approx(panel.spearman([2, 2, 4.5, 1], [1, 2.5, 4, 3]))
    # self-agreement: screening passes differ only on T3 (by 1.0) of 5 two-pass tasks
    assert r["self"]["n"] == 5 and r["self"]["mad"] == pytest.approx(0.2) and r["self"]["split"] == 1
    assert c["official"]["self"]["split"] == 1 and c["official"]["n"] == 4
    txt = panel.render_calibration(c)
    assert "screening, not comparable to the leaderboard" in txt and "T1 T4" in txt
    md = panel.render_calibration(c, md=True)
    assert "| official (reference) |" in md and "| j | 4 |" in md


# ---- end to end through the CLI: the real upstream verifier, its Gemini client swapped for the fake server

ROOT = Path(__file__).resolve().parents[1]
FAKE_RUNNER = str(ROOT / "tests" / "fake_runner.py")
needs_verifier = pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is None or __import__("importlib").util.find_spec("google.genai") is None,
    reason="needs ffmpeg and google-genai (the upstream verifier's own imports)")


@pytest.fixture
def cli_env(tmp_path):
    import os
    e = {**os.environ, "PWA_RUNS": str(tmp_path / "runs"), "PWA_RESULTS_CSV": str(tmp_path / "experiments.csv"),
         "FAKE_SECONDS": "3", "JUDGE_API_KEY": KEY, "JUDGE_API_RETRIES": "1", "JUDGE_API_TIMEOUT_S": "20"}
    for k in ("GEMINI_API_KEY", "JUDGE_API_URL", "PLAYER_API_KEY"):
        e.pop(k, None)
    return e


def pwa(env, *args, check=None):
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "pwa.cli", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if check is not None:
        assert r.returncode == check, r.stderr
    return r


@needs_verifier
def test_openai_judge_scores_through_upstream_verifier(cli_env):
    reply = {"final_score_1_to_5": 3.0, "summary_zh": "ok",
             "if_instruction_following_check": {"verdict": "pass", "instruction_following_score": 1}}
    srv = FakeChat([ok(json.dumps(reply))])
    env = {**cli_env, "JUDGE_API_URL": srv.url}
    try:
        pwa(env, "gen", "t", "--runner", FAKE_RUNNER, "--tasks", "IF002", check=0)
        s = json.loads(pwa(env, "score", "t", "--passes", "1", "--json", "--judge-model", "openai:fake-judge:low",
                           check=0).stdout)
    finally:
        srv.close()
    assert s["failed"] == [] and s["ran"] == 1 and s["judge"]["slug"] == "openai-fake-judge-think-low"
    runs = Path(env["PWA_RUNS"]) / "t"
    res = json.loads((runs / "eval-openai-fake-judge-think-low" / "pass1" / "IF002_score.json").read_text())
    assert res["score"] == reply and res["gemini_model"] == "openai:fake-judge"
    assert not (runs / "eval").exists() and not Path(env["PWA_RESULTS_CSV"]).exists()
    body = srv.requests[0]["body"]
    assert srv.requests[0]["auth"] == f"Bearer {KEY}"
    assert body["model"] == "fake-judge" and body["reasoning_effort"] == "low"
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0.1
    parts = body["messages"][0]["content"]
    assert parts[0]["type"] == "text" and "JSON" in parts[0]["text"]  # upstream's own prompt, first
    imgs = [p for p in parts if p["type"] == "image_url"]
    # upstream's contact sheets (both streams) plus the reference image when present, as JPEG data URIs
    assert len(imgs) >= 2 and all(p["image_url"]["url"].startswith("data:image/jpeg;base64,") for p in imgs)
    assert any("PRIMARY SHEET 1/" in p.get("text", "") for p in parts)
    rep = json.loads(pwa(env, "report", "t", "--judge-model", "openai:fake-judge:low", "--json", check=0).stdout)
    assert rep["tasks"]["IF002"]["mean"] == pytest.approx(3.0) and rep["judge"]["provider"] == "openai"


@needs_verifier
def test_openai_judge_failure_writes_err(cli_env):
    srv = FakeChat([(400, {"error": {"message": "model not found"}}, None)])
    env = {**cli_env, "JUDGE_API_URL": srv.url}
    try:
        pwa(env, "gen", "t", "--runner", FAKE_RUNNER, "--tasks", "IF002", check=0)
        r = pwa(env, "score", "t", "--passes", "1", "--retries", "0", "--json", "--judge-model", "openai:nope")
    finally:
        srv.close()
    assert r.returncode == 1 and json.loads(r.stdout)["failed"]
    err = (Path(env["PWA_RUNS"]) / "t" / "eval-openai-nope" / "pass1" / "IF002_score.err").read_text()
    assert "judge API HTTP 400" in err and "model not found" in err and KEY not in err


def _fake_eval(runs: Path, exp: str, d: str, k: int, scores: dict):
    p = runs / exp / d / f"pass{k}"
    p.mkdir(parents=True, exist_ok=True)
    for tid, val in scores.items():
        (p / f"{tid}_score.json").write_text(json.dumps({"task_id": tid, "score": {
            "final_score_1_to_5": val, "if_instruction_following_check": {"verdict": "pass",
                                                                          "instruction_following_score": 1}}}))


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="needs ffmpeg")
def test_panel_and_judges_cli(cli_env):
    env, runs = cli_env, Path(cli_env["PWA_RUNS"])
    tasks = ["IF002", "IF003", "IF004"]
    for exp in ("a", "b"):
        pwa(env, "gen", exp, "--runner", FAKE_RUNNER, "--tasks", *tasks, check=0)
    g, o = "eval-gemini-4-hydrogen-think-low", "eval-openai-gpt-6-luna"
    for k in (1, 2):
        _fake_eval(runs, "a", "eval", k, {"IF002": 2.0, "IF003": 3.0, "IF004": 4.0})
        _fake_eval(runs, "a", g, k, {"IF002": 2.0, "IF003": 3.0, "IF004": 4.0})
        _fake_eval(runs, "a", o, k, {"IF002": 1.0, "IF003": 3.0, "IF004": 3.0 + k})
        _fake_eval(runs, "b", g, k, {"IF002": 3.0, "IF003": 3.0, "IF004": 3.0})
        _fake_eval(runs, "b", o, k, {"IF002": 2.5, "IF003": 3.0, "IF004": 4.0})
    jm = ["--judge-model", "gemini-4-hydrogen:low", "--judge-model", "openai:gpt-6-luna"]
    c = json.loads(pwa(env, "cells", "a", "b", *jm, "--json", check=0).stdout)
    by = {r["task_id"]: r for r in c["tasks"]}
    # IF002: +1.0 and +1.5 -> panel up; IF004: -1.0 and -0.5 -> agree on direction, not moved
    assert (by["IF002"]["move"], by["IF004"]["move"], by["IF004"]["agree"]) == ("up", "", True)
    assert (c["up"], c["down"]) == (1, 0)
    assert "screening, not comparable" in pwa(env, "cells", "a", "b", *jm, check=0).stdout
    p = json.loads(pwa(env, "report", "a", *jm, "--json", check=0).stdout)
    assert p["panel"] and [t["spread"] for t in p["tasks"]] == pytest.approx([1.0, 0.0, 0.5])
    assert "screening panel" in pwa(env, "report", "a", *jm, "--md", check=0).stdout
    assert (runs / "a" / "report.openai-gpt-6-luna.json").is_file() and not (runs / "a" / "report.json").exists()
    cal = json.loads(pwa(env, "judges", "a", *jm, "--json", check=0).stdout)
    gj, oj = cal["judges"]
    assert gj["spearman"] == pytest.approx(1.0) and gj["mad"] == 0 and gj["n_far"] == 0
    assert oj["far"] == ["IF002"] and oj["bias"] == pytest.approx((-1.0 + 0 + 0.5) / 3)
    assert oj["self"]["split"] == 1  # IF004 passes 4 vs 5
    assert "| official (reference) |" in pwa(env, "judges", "a", *jm, "--md", check=0).stdout
    assert pwa(env, "judges", "b", *jm).returncode == 1  # b has no official passes
    assert pwa(env, "compare", "a", "b", *jm).returncode == 1  # one judge only
    assert not Path(env["PWA_RESULTS_CSV"]).exists()
