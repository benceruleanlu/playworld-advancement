"""Google Cloud (Gemini Enterprise Agent Platform, formerly Vertex AI) judge backend: switch, verifier command and env, SDK client resolution, result stamp, report column.
No network: the SDK checks only build clients and read their resolved settings."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pwa import report, score
from pwa.core import PLAYWORLD, PwaError

INFO = {"family": "gc", "task_id": "GC005", "dataset": "/d/gc/data.json", "image": "/nonexistent.jpg"}
VARS = ("GCP_GEMINI_API_KEY", "PWA_JUDGE_BACKEND", "GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE",
        "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_API_KEY", "GEMINI_BASE_URL", "GEMINI_HEADERS_JSON")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for v in VARS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "aistudio-key")
    monkeypatch.setenv("GOOGLE_GENAI_API_VERSION", "v1beta")  # as the experiment workflow sets it


def cmd(dry=False, judge=None):
    return score.verifier_cmd("score", INFO, Path("/v.mp4"), Path("/o.json"), dry, judge=judge)


def test_off_is_unchanged(monkeypatch):
    base_cmd, base_env = cmd(), score.verifier_env()
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "  ")  # an unset GitHub secret arrives as ""
    assert score.judge_backend() == "aistudio"
    assert cmd() == base_cmd and "--evidence-transport" not in base_cmd and base_cmd[2] == "metrics.vqa.score"
    env = score.verifier_env()
    assert env == {**base_env, "GCP_GEMINI_API_KEY": "  "}
    assert env["GEMINI_API_KEY"] == "aistudio-key" and env["GOOGLE_GENAI_API_VERSION"] == "v1beta"
    assert "GOOGLE_GENAI_USE_VERTEXAI" not in env


def test_gcp_key_route(monkeypatch):
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "gcp-key")
    monkeypatch.setenv("GOOGLE_GENAI_USE_ENTERPRISE", "false")  # would override USE_VERTEXAI in the SDK
    assert score.judge_backend() == "gcp"
    c = cmd()
    assert c[2] == "metrics.vqa.score" and c[c.index("--evidence-transport") + 1] == "inline"
    assert c[c.index("--model") + 1] == os.environ.get("GEMINI_MODEL", score.OFFICIAL_MODEL)
    assert "--evidence-transport" not in cmd(dry=True)
    env = score.verifier_env()
    assert env["GEMINI_API_KEY"] == "gcp-key" and env["GOOGLE_GENAI_USE_VERTEXAI"] == "true"
    assert env["GOOGLE_GENAI_API_VERSION"] == "v1beta1" and env["GOOGLE_GENAI_USE_ENTERPRISE"] == "true"
    assert "PWA_JUDGE_GCP_ADC" not in env
    monkeypatch.setenv("GOOGLE_GENAI_API_VERSION", "v1")
    assert score.verifier_env()["GOOGLE_GENAI_API_VERSION"] == "v1"  # an Agent Platform version is kept


def test_gcp_override_and_openai_judge(monkeypatch):
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "gcp-key")
    monkeypatch.setenv("PWA_JUDGE_BACKEND", "aistudio")
    assert score.judge_backend() == "aistudio" and "GOOGLE_GENAI_USE_VERTEXAI" not in score.verifier_env()
    monkeypatch.setenv("PWA_JUDGE_BACKEND", "bogus")
    with pytest.raises(PwaError):
        score.judge_backend()
    monkeypatch.delenv("PWA_JUDGE_BACKEND")
    oj = score.Judge.parse("openai:gpt-x")
    env = score.verifier_env(oj)
    assert "GOOGLE_GENAI_USE_VERTEXAI" not in env and env["GEMINI_API_KEY"] == score.GEMINI_KEY_PLACEHOLDER
    assert "--evidence-transport" not in cmd(judge=oj)


def test_gcp_adc_route(monkeypatch):
    monkeypatch.setenv("PWA_JUDGE_BACKEND", "gcp")
    with pytest.raises(PwaError, match="GOOGLE_CLOUD_PROJECT"):
        score.check_keys(None)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    score.check_keys(None)
    assert cmd()[2] == "pwa.judge_shim"
    env = score.verifier_env()
    assert env["PWA_JUDGE_GCP_ADC"] == "1" and env["GEMINI_API_KEY"] == score.GCP_ADC_PLACEHOLDER
    assert env["GOOGLE_CLOUD_LOCATION"] == "global" and str(score.ROOT) in env["PYTHONPATH"].split(os.pathsep)


def test_check_keys_vertex_needs_no_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    with pytest.raises(PwaError):
        score.check_keys(None)
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "gcp-key")
    score.check_keys(None)


PROBE = """
import json, warnings
warnings.simplefilter("ignore")
from metrics.gemini_client import create_gemini_client
import metrics.gemini_client as gc
import pwa.judge_shim as shim
import os
if os.environ.get("PWA_JUDGE_GCP_ADC") == "1":
    shim.install_gcp_adc()
c = gc.create_gemini_client()._api_client
print(json.dumps({"vertexai": bool(c.vertexai), "base_url": c._http_options.base_url,
                  "api_version": c._http_options.api_version, "key": c.api_key,
                  "project": c.project, "location": c.location}))
"""


def resolved(env: dict) -> dict:
    pytest.importorskip("google.genai")
    env = {**env, "PYTHONPATH": os.pathsep.join([str(PLAYWORLD), str(score.ROOT), env.get("PYTHONPATH", "")])}
    r = subprocess.run([sys.executable, "-c", PROBE], cwd=PLAYWORLD, env=env, capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_sdk_resolves_upstream_client(monkeypatch):
    """The installed google-genai, given the env pwa passes, turns upstream's genai.Client(api_key=...) into a
    Agent Platform express-mode client on the global endpoint; off, it stays on AI Studio."""
    off = resolved(score.verifier_env())
    assert not off["vertexai"] and "generativelanguage" in off["base_url"] and off["key"] == "aistudio-key"
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "gcp-key")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")  # an explicit key still wins: express mode
    on = resolved(score.verifier_env())
    assert on["vertexai"] and on["base_url"] == "https://aiplatform.googleapis.com/"
    assert on["api_version"] == "v1beta1" and on["key"] == "gcp-key" and on["project"] is None
    monkeypatch.delenv("GCP_GEMINI_API_KEY")
    monkeypatch.setenv("PWA_JUDGE_BACKEND", "gcp")
    adc = resolved(score.verifier_env())
    assert adc["vertexai"] and adc["project"] == "proj" and adc["location"] == "global" and not adc["key"]
    assert adc["base_url"] == "https://aiplatform.googleapis.com/"


def test_stamp_and_report_column(monkeypatch, tmp_path):
    monkeypatch.setattr(score, "eval_dir", lambda exp, dry=False, judge=None: tmp_path / "eval")
    monkeypatch.setattr(report, "eval_dir", lambda exp, dry=False, judge=None: tmp_path / "eval")
    monkeypatch.setattr(score, "video_path", lambda exp, tid: tmp_path / "v.mp4")

    def fake_run(cmd, err, retries, judge=None):
        out = Path(cmd[cmd.index("--output") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"task_id": INFO["task_id"], "score": {"x": 1}}))
        return True

    monkeypatch.setattr(score, "run_verifier", fake_run)
    a = argparse.Namespace(dry_run=False, force=False, retries=0)
    info = {**INFO, "family": "if"}  # no gate
    score.score_task("e", info, 1, a)
    res = json.loads((tmp_path / "eval/pass1/GC005_score.json").read_text())
    assert "judge_backend" not in res  # aistudio results stay as upstream wrote them
    assert report.judge_backends("e", [1], [info]) == "aistudio"
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "gcp-key")
    score.score_task("e", info, 2, a)
    assert json.loads((tmp_path / "eval/pass2/GC005_score.json").read_text())["judge_backend"] == "gcp"
    assert report.judge_backends("e", [2], [info]) == "gcp"
    assert report.judge_backends("e", [1, 2], [info]) == "aistudio+gcp"
    assert report.judge_backends("e", [3], [info]) == ""
    assert report.CSV_FIELDS[-1] == "judge_backend"
