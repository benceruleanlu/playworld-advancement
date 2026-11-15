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
    # every upstream sheet (1920x1080 primary, 1600x900 detail) is 6 high-detail tiles = 1105 tokens
    assert gc == {"score": 12 + 4 + 1, "gate": 16, "total": 33, "calls": 2,
                  "score_tokens": 17 * 1105, "gate_tokens": 16 * 1105}
    ins = score.estimate_images({**INFO, "family": "insight"}, Path("/v.mp4"), specs)
    assert ins == {"score": 16, "gate": 0, "total": 16, "calls": 1, "score_tokens": 16 * 1105, "gate_tokens": 0}
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


def test_image_tokens_tile_count():
    assert score.image_tokens(1920, 1080) == 1105 and score.image_tokens(1600, 900) == 1105
    assert score.image_tokens(512, 512) == 255 and score.image_tokens(4000, 4000, "low") == 85


def test_contradictory_judge_flags_are_refused():
    with pytest.raises(PwaError, match="--judge gemini"):
        score.judges_of(ns(judge="gemini", judge_model=["openai:gpt-4o"]))
    with pytest.raises(PwaError, match="Gemini model"):
        score.judges_of(ns(judge="openai", judge_model=["gemini-3.1-pro-preview"]))
    assert score.judges_of(ns(judge="gemini", judge_model=["gemini-4-hydrogen"]))[0].provider == "gemini"


def test_video_seconds_falls_back_to_ffmpeg_without_ffprobe(monkeypatch, tmp_path):
    real = score.subprocess.run

    def run(cmd, *a, **kw):
        if cmd[0] == "ffprobe":
            raise FileNotFoundError("ffprobe")
        return NS(stdout="", stderr="  Duration: 00:01:02.50, start: 0.000000, bitrate: 1 kb/s\n", returncode=1)

    monkeypatch.setattr(score.subprocess, "run", run)
    monkeypatch.setattr(score, "_ffmpeg_exe", lambda: "/x/ffmpeg")
    assert score.video_seconds(tmp_path / "v.mp4") == pytest.approx(62.5)
    monkeypatch.setattr(score, "_ffmpeg_exe", lambda: None)
    assert score.video_seconds(tmp_path / "v.mp4") is None
    monkeypatch.setattr(score.subprocess, "run", real)


def _guard_args(exp, passes=2):
    return NS(exp=exp, passes=passes, force=False, max_images=None)


def test_cost_guard_counts_pending_calls_and_caps(monkeypatch, tmp_path):
    monkeypatch.setattr(score, "exp_dir", lambda e: tmp_path / e)
    monkeypatch.delenv("PWA_PROXY_MAX_IMAGES", raising=False)
    monkeypatch.delenv("PWA_PROXY_USD_PER_MTOK", raising=False)
    est = {"score": 17, "gate": 16, "total": 33, "calls": 2, "score_tokens": 17000, "gate_tokens": 16000}
    monkeypatch.setattr(score, "estimate_images", lambda t, v, specs=None, detail="high": est)
    monkeypatch.setattr(score, "_upstream_specs", lambda: None)
    j = score.Judge.parse("openai:gpt-4.1")
    sel = [{**INFO, "task_id": "GC005"}]
    g = score.cost_guard(sel, _guard_args("e"), j)
    assert (g["images"], g["calls"], g["tokens"]) == (66, 4, 66000)
    # pass 1 already scored and gated: only pass 2 is counted
    d = tmp_path / "e" / "eval-openai-gpt-4.1" / "pass1"
    d.mkdir(parents=True)
    for mode in ("score", "gate"):
        (d / f"GC005_{mode}.json").write_text(json.dumps({"score": {"final_score_1_to_5": 3}}))
    assert score.cost_guard(sel, _guard_args("e"), j)["images"] == 33
    assert score.cost_guard(sel, NS(exp="e", passes=2, force=True, max_images=None), j)["images"] == 66
    with pytest.raises(PwaError, match="over the cap"):
        score.cost_guard(sel, NS(exp="e", passes=2, force=True, max_images=40), j)
    monkeypatch.setenv("PWA_PROXY_MAX_IMAGES", "10")
    with pytest.raises(PwaError, match="over the cap of 10"):
        score.cost_guard(sel, _guard_args("e"), j)
    monkeypatch.setenv("PWA_PROXY_MAX_IMAGES", "0")  # 0 = no cap
    assert score.cost_guard(sel, NS(exp="e", passes=50, force=True, max_images=None), j)["images"] == 50 * 33
    # unknown duration counts at the conservative per-task figure, never 0
    monkeypatch.setattr(score, "estimate_images", lambda t, v, specs=None, detail="high": None)
    assert score.cost_guard(sel, NS(exp="e", passes=1, force=True, max_images=0), j)["images"] == \
        score.UNKNOWN_TASK_IMAGES


def test_proxy_reports_leave_out_paper_reference_and_say_temperature_dropped(monkeypatch):
    rep = {"exp": "e", "passes": [1, 2], "n_tasks": 1, "n_missing": 0, "strict": False, "overall": 2.4,
           "overall_std": 0.1, "overall_per_pass": [2.3, 2.5], "families": {}, "judge_backend": "",
           "judge": report.judge_json(score.Judge.parse("openai:gpt-5-mini")), "judge_dropped": ["temperature"]}
    for text in (report.render(rep, {}), report.render_md(rep, {})):
        assert "Genie 3" not in text and "provider default" in text
    official = {**rep, "judge": None, "judge_dropped": []}
    assert "Genie 3" in report.render(official, {}) and "Genie 3" in report.render_md(official, {})


def test_compare_has_no_paper_fallback_for_proxy():
    fam = lambda m: {"gc": {"mean": m, "std": None}}  # noqa: E731
    mk = lambda e, m, judge: {"exp": e, "families": fam(m), "overall": m, "overall_std": None, "tasks": {},  # noqa: E731
                              "judge": judge}
    j = report.judge_json(score.Judge.parse("openai:gpt-4.1"))
    c = report.compare(mk("a", 2.0, j), mk("b", 2.5, j))
    assert c["overall"]["noise"] is None and c["overall"]["threshold"] is None and "?" in report.render_compare(c)
    off = report.compare(mk("a", 2.0, None), mk("b", 2.5, None))
    assert off["overall"]["noise"] is False and off["overall"]["threshold"] == pytest.approx(2 * report.FALLBACK_STD)


def test_proxy_rows_never_reach_the_results_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "RESULTS_CSV", tmp_path / "experiments.csv")
    monkeypatch.delenv("PWA_PROXY_CSV", raising=False)
    report.upsert_proxy_csv(_rep(), {"runner": "r"}, "dev", score.Judge.parse("openai:gpt-4.1"))
    for dest in (tmp_path / "experiments.csv", tmp_path / "main" / "results" / "experiments.csv"):
        with pytest.raises(ValueError, match="never go into the results csv"):
            report.upsert_row_into("e", report.proxy_csv(), dest, keys=report.PROXY_KEYS)
    # PWA_PROXY_CSV pointed at the results csv: the report warns and writes nothing
    monkeypatch.setenv("PWA_PROXY_CSV", str(tmp_path / "experiments.csv"))
    report.upsert_proxy_csv(_rep("x"), {"runner": "r"}, "dev", score.Judge.parse("openai:gpt-4.1"))
    assert not (tmp_path / "experiments.csv").exists()
    # a proxy row in a results csv (hand edit) is never copied by the default upsert-row
    src = tmp_path / "src.csv"
    src.write_text("exp,split,overall,status,judge\ne,dev,3.1,proxy,openai:gpt-4.1\n")
    with pytest.raises(ValueError, match="no row"):
        report.upsert_row_into("e", src, tmp_path / "out.csv")


def test_malformed_proxy_csv_warns_and_report_still_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "RESULTS_CSV", tmp_path / "experiments.csv")
    monkeypatch.delenv("PWA_PROXY_CSV", raising=False)
    report.proxy_csv().write_text("exp,split\na,b,c,d\n")
    report.upsert_proxy_csv(_rep(), {"runner": "r"}, "dev", score.Judge.parse("openai:gpt-4.1"))  # no raise
    assert report.proxy_csv().read_text() == "exp,split\na,b,c,d\n"


def test_upsert_row_proxy_copies_only_this_runs_judges(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "RESULTS_CSV", tmp_path / "experiments.csv")
    monkeypatch.delenv("PWA_PROXY_CSV", raising=False)
    old, new = score.Judge.parse("openai:gpt-4.1"), score.Judge.parse("openai:gpt-4o")
    report.upsert_proxy_csv(_rep(), {"runner": "r"}, "dev", old)  # stale copy inherited from main
    report.upsert_proxy_csv(_rep(), {"runner": "r"}, "dev", new)  # this run
    dest = tmp_path / "main_proxy.csv"
    dest.write_text(report.proxy_csv().read_text().replace("2.5000", "3.9000"))  # main has newer rows
    assert report.upsert_row_into("e", report.proxy_csv(), dest, keys=report.PROXY_KEYS,
                                  judges=["openai:gpt-4o"]) == 1
    rows = {r["judge"]: r["overall"] for r in csv.DictReader(dest.open())}
    assert rows == {"openai:gpt-4.1": "3.9000", "openai:gpt-4o": "2.5000"}


def test_temperature_rejection_is_remembered_and_stamped(monkeypatch, tmp_path):
    monkeypatch.delenv("JUDGE_API_NO_TEMPERATURE", raising=False)
    monkeypatch.setattr(score, "_DROPPED", {})
    j = score.Judge.parse("openai:gpt-5-mini")
    seen = []

    def run(cmd, cwd=None, env=None, **kw):
        seen.append(env.get("JUDGE_API_NO_TEMPERATURE"))
        return NS(returncode=0, stdout="",
                  stderr="[pwa judge] model rejects temperature=0.1; retrying with the provider default\n")

    monkeypatch.setattr(score.subprocess, "run", run)
    assert score.run_verifier(["x"], tmp_path / "a.err", 0, j)
    assert score.run_verifier(["x"], tmp_path / "b.err", 0, j)
    assert seen == [None, "1"] and score.dropped_params(j) == {"temperature"}
    assert score.dropped_params(score.Judge.parse("openai:gpt-4.1")) == set()
    out = tmp_path / "r.json"
    out.write_text(json.dumps({"score": {"final_score_1_to_5": 2}}))
    score.stamp_dropped(out, score.dropped_params(j))
    assert json.loads(out.read_text())["judge_dropped"] == ["temperature"]
