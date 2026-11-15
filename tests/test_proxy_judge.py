"""Proxy judge (`--judge openai`): flag parsing, routing to the OpenAI shim, output dir and csv separation from the
official Gemini judge, report labelling, the cost guard and failure handling. No network: a local fake
OpenAI-compatible server stands in for the API (tests/test_judge_openai.py)."""
import argparse
import csv
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from pwa import report, score
from pwa.core import PwaError

from test_judge_openai import FAKE_RUNNER, KEY, FakeChat, _fake_eval, cli_env, needs_verifier, no_sleep, ok, pwa  # noqa: F401

INFO = {"dataset": "/d.json", "task_id": "GC005", "image": "/nonexistent.png", "family": "gc"}
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def ns(**kw):
    return argparse.Namespace(**{"judge": None, "judge_model": None, "judge_thinking": None, **kw})


def test_judge_flag_parsing(monkeypatch):
    monkeypatch.delenv("PWA_PROXY_JUDGE_MODEL", raising=False)
    assert score.judges_of(ns()) == [] and score.judges_of(ns(judge="gemini")) == []  # official judge, unchanged
    (j,) = score.judges_of(ns(judge="openai"))
    assert (j.provider, j.model, j.slug, j.proxy) == ("openai", "gpt-4.1", "openai-gpt-4.1", True)
    assert j.label == "PROXY JUDGE (openai:gpt-4.1), not comparable to the leaderboard"
    assert score.judges_of(ns(judge="openai", judge_model=["gpt-5-mini"]))[0].spec == "openai:gpt-5-mini"
    assert score.judges_of(ns(judge="openai", judge_model=["openai:gpt-5-mini"]))[0].spec == "openai:gpt-5-mini"
    monkeypatch.setenv("PWA_PROXY_JUDGE_MODEL", "gpt-4o")
    assert score.judges_of(ns(judge="openai"))[0].model == "gpt-4o"
    with pytest.raises(PwaError):
        score.judges_of(ns(judge="openai", judge_model=["gemini:gemini-4-hydrogen"]))
    # a Gemini screening judge is not a proxy and keeps its label
    g = score.Judge.parse("gemini-4-hydrogen")
    assert not g.proxy and g.label.startswith("screening judge:")


def test_proxy_routes_to_openai_shim_and_gemini_path_is_untouched(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
    monkeypatch.setenv("GEMINI_API_KEY", "real-gemini-key")
    monkeypatch.setenv("PWA_JUDGE_PROVIDER", "openai")  # a stray value must never reach the official judge
    out = Path("/o.json")
    official = score.verifier_cmd("score", INFO, Path("/v.mp4"), out, False)
    assert official == [score.sys.executable, "-m", "metrics.vqa.score", "--mode", "score", "--dataset", "/d.json",
                        "--task-id", "GC005", "--video", "/v.mp4", "--world-model", score.WORLD_MODEL,
                        "--model", "gemini-3.1-pro-preview", "--output", "/o.json"]
    env = score.verifier_env()
    assert env["GEMINI_API_KEY"] == "real-gemini-key" and "PWA_JUDGE_PROVIDER" not in env
    assert score.eval_dir("x") == score.exp_dir("x") / "eval"

    (j,) = score.judges_of(ns(judge="openai"))
    cmd = score.verifier_cmd("score", INFO, Path("/v.mp4"), out, False, judge=j)
    assert cmd[1:3] == ["-m", "pwa.judge_shim"] and cmd[cmd.index("--model") + 1] == "openai:gpt-4.1"
    env = score.verifier_env(j)
    assert env["PWA_JUDGE_PROVIDER"] == "openai" and env["GEMINI_API_KEY"] == score.GEMINI_KEY_PLACEHOLDER
    assert score.eval_dir("x", judge=j) == score.exp_dir("x") / "eval-openai-gpt-4.1"


def test_estimate_images_uses_upstream_specs(monkeypatch, tmp_path):
    specs = score._upstream_specs()
    if specs is None:
        pytest.skip("PlayWorld submodule not checked out")
    primary, detail = specs  # upstream: 10 fps in 5x5 sheets, 0.5 fps in 2x2 sheets
    assert (primary.fps, primary.frames_per_sheet, detail.fps, detail.frames_per_sheet) == (10.0, 25, 0.5, 4)
    monkeypatch.setattr(score, "video_seconds", lambda v: 30.0)  # 300 primary frames, 15 detail frames
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"x")
    gc = score.estimate_images({**INFO, "image": str(ref)}, Path("/v.mp4"), specs)
    assert gc == {"score": 12 + 4 + 1, "gate": 16, "total": 33, "calls": 2}
    ins = score.estimate_images({**INFO, "family": "insight"}, Path("/v.mp4"), specs)
    assert ins == {"score": 16, "gate": 0, "total": 16, "calls": 1}
    monkeypatch.setattr(score, "video_seconds", lambda v: None)
    assert score.estimate_images(INFO, Path("/v.mp4"), specs) is None


def _rep(exp="e"):
    return {"exp": exp, "generated": "2026-11-15T00:00:00", "families": {"gc": {"mean": 2.5, "dropped": 0}},
            "overall": 2.5, "overall_std": 0.1, "passes": [1, 2], "n_tasks": 1, "n_missing": 0}


def test_proxy_csv_is_separate_and_keyed_by_judge(monkeypatch, tmp_path):
    main_csv = tmp_path / "experiments.csv"
    monkeypatch.setattr(report, "RESULTS_CSV", main_csv)
    monkeypatch.delenv("PWA_PROXY_CSV", raising=False)
    assert report.proxy_csv() == tmp_path / "proxy_experiments.csv"
    a, b = score.Judge.parse("openai:gpt-4.1"), score.Judge.parse("openai:gpt-5-mini")
    report.upsert_proxy_csv(_rep(), {"runner": "r"}, "dev", a)
    report.upsert_proxy_csv(_rep(), {"runner": "r"}, "dev", b)
    report.upsert_proxy_csv({**_rep(), "overall": 3.0}, {"runner": "r"}, "dev", a)  # replaces a's row only
    assert not main_csv.exists()
    rows = list(csv.DictReader(report.proxy_csv().open()))
    assert [(r["judge"], r["overall"], r["status"]) for r in rows] == [
        ("openai:gpt-5-mini", "2.5000", "proxy"), ("openai:gpt-4.1", "3.0000", "proxy")]
    assert list(rows[0]) == report.CSV_FIELDS + ["judge"]
    # the workflow copies a run's proxy rows into main's proxy csv by exp+split+judge
    dest = tmp_path / "main_proxy.csv"
    assert report.upsert_row_into("e", report.proxy_csv(), dest, keys=report.PROXY_KEYS) == 2
    assert report.upsert_row_into("e", report.proxy_csv(), dest, keys=report.PROXY_KEYS) == 2
    assert len(list(csv.DictReader(dest.open()))) == 2


def test_site_reads_only_the_official_csv():
    root = Path(__file__).resolve().parents[1]
    for f in [root / ".github/workflows/pages.yml", *(root / "site/src").rglob("*.*")]:
        assert "proxy_experiments" not in f.read_text(errors="replace"), f


@needs_ffmpeg
def test_report_compare_failures_read_proxy_dir_with_label(cli_env):
    env, runs = cli_env, Path(cli_env["PWA_RUNS"])
    tasks = ["IF002", "IF003"]
    for exp in ("a", "b"):
        pwa(env, "gen", exp, "--runner", FAKE_RUNNER, "--tasks", *tasks, check=0)
    for k in (1, 2):
        _fake_eval(runs, "a", "eval", k, {"IF002": 4.0, "IF003": 4.0})  # official scores, must not be read
        _fake_eval(runs, "a", "eval-openai-gpt-4.1", k, {"IF002": 2.0, "IF003": 3.0})
        _fake_eval(runs, "b", "eval-openai-gpt-4.1", k, {"IF002": 3.0, "IF003": 3.0})
    label = "PROXY JUDGE (openai:gpt-4.1), not comparable to the leaderboard"
    out = pwa(env, "report", "a", "--judge", "openai", check=0).stdout
    assert out.splitlines()[0] == f"*** {label} ***"
    md = pwa(env, "report", "a", "--judge", "openai", "--md", check=0).stdout
    assert md.splitlines()[0].startswith(f"**{label}.**")
    rep = json.loads(pwa(env, "report", "a", "--judge", "openai", "--json", check=0).stdout)
    assert rep["tasks"]["IF002"]["mean"] == pytest.approx(2.0) and rep["judge"]["label"] == label
    assert pwa(env, "compare", "a", "b", "--judge", "openai", check=0).stdout.splitlines()[0] == f"*** {label} ***"
    c = json.loads(pwa(env, "compare", "a", "b", "--judge", "openai", "--json", check=0).stdout)
    assert c["tasks"]["IF002"]["delta"] == pytest.approx(1.0)
    f = pwa(env, "failures", "a", "--judge", "openai", "--all", check=0).stdout
    assert f.splitlines()[0] == f"*** {label} ***"
    # official csv untouched; proxy csv holds the row; official report.json never written
    assert not Path(env["PWA_RESULTS_CSV"]).exists() and not (runs / "a" / "report.json").exists()
    proxy = Path(env["PWA_RESULTS_CSV"]).parent / "proxy_experiments.csv"
    rows = list(csv.DictReader(proxy.open()))
    assert [(r["exp"], r["judge"]) for r in rows] == [("a", "openai:gpt-4.1")]
    # the official report still reads eval/ only
    off = json.loads(pwa(env, "report", "a", "--json", check=0).stdout)
    assert off["judge"] is None and off["tasks"]["IF002"]["mean"] == pytest.approx(4.0)
    assert [r["exp"] for r in csv.DictReader(Path(env["PWA_RESULTS_CSV"]).open())] == ["a"]
    assert [r["exp"] for r in csv.DictReader(proxy.open())] == ["a"]


@needs_verifier
def test_proxy_score_end_to_end_with_fake_openai(cli_env):
    reply = {"final_score_1_to_5": 3.0, "summary_zh": "ok",
             "if_instruction_following_check": {"verdict": "pass", "instruction_following_score": 1}}
    srv = FakeChat([(429, {"error": {"message": "slow down"}}, {"Retry-After": "0"}), ok(json.dumps(reply))])
    env = {**cli_env, "JUDGE_API_URL": srv.url}
    try:
        pwa(env, "gen", "t", "--runner", FAKE_RUNNER, "--tasks", "IF002", check=0)
        r = pwa(env, "score", "t", "--passes", "1", "--json", "--judge", "openai", "--judge-model", "fake-judge")
    finally:
        srv.close()
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    assert s["failed"] == [] and s["judge"]["slug"] == "openai-fake-judge"
    assert "cost guard" in r.stderr and "IF002: ~" in r.stderr and KEY not in r.stderr + r.stdout
    runs = Path(env["PWA_RUNS"]) / "t"
    res = json.loads((runs / "eval-openai-fake-judge" / "pass1" / "IF002_score.json").read_text())
    assert res["score"] == reply and not (runs / "eval").exists()
    assert len(srv.requests) == 2 and srv.requests[1]["body"]["model"] == "fake-judge"  # 429 retried once


@needs_verifier
def test_proxy_failure_is_reported_failed_never_one(cli_env):
    srv = FakeChat([(503, {"error": {"message": "overloaded"}}, {"Retry-After": "0"})])
    env = {**cli_env, "JUDGE_API_URL": srv.url, "JUDGE_API_RETRIES": "1"}
    try:
        pwa(env, "gen", "t", "--runner", FAKE_RUNNER, "--tasks", "IF002", check=0)
        r = pwa(env, "score", "t", "--passes", "1", "--retries", "0", "--json", "--judge", "openai")
    finally:
        srv.close()
    assert r.returncode == 1 and [e["task_id"] for e in json.loads(r.stdout)["failed"]] == ["IF002"]
    err = (Path(env["PWA_RUNS"]) / "t" / "eval-openai-gpt-4.1" / "pass1" / "IF002_score.err").read_text()
    assert "HTTP 503" in err and KEY not in err
    assert not (Path(env["PWA_RUNS"]) / "t" / "eval-openai-gpt-4.1" / "pass1" / "IF002_score.json").exists()
