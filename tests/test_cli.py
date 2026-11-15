"""End-to-end CLI tests: stub runner + verifier dry runs + synthetic verifier results. No GPU, no API."""
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE = str(ROOT / "tests" / "fake_runner.py")
pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


@pytest.fixture
def env(tmp_path):
    e = {**os.environ, "PWA_RUNS": str(tmp_path / "runs"), "PWA_RESULTS_CSV": str(tmp_path / "experiments.csv"),
         "FAKE_SECONDS": "3"}
    e.pop("GEMINI_API_KEY", None)
    return e


def pwa(env, *args, check=None):
    r = subprocess.run([sys.executable, "-m", "pwa.cli", *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if check is not None:
        assert r.returncode == check, r.stderr
    return r


def test_help():
    r = subprocess.run([sys.executable, "-m", "pwa.cli", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and "compare" in r.stdout
    r = subprocess.run([sys.executable, "-m", "pwa.cli", "nosuch"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2


def test_tasks(env):
    rows = json.loads(pwa(env, "tasks", "--split", "dev", "--json", check=0).stdout)
    assert len(rows) == 24 and {r["family"] for r in rows} == {"gc", "if", "insight", "outsight"}
    out = pwa(env, "tasks", "--split", "all", "--family", "if", check=0).stdout.splitlines()
    assert len(out) == 50 and all(l.startswith("if\tIF") for l in out)
    assert pwa(env, "tasks", "--split", "nope").returncode == 1


def test_gen_refuse_resume_and_failure(env):
    pwa(env, "gen", "e1", "--runner", FAKE, "--tasks", "GC005", "OE034", check=0)
    runs = Path(env["PWA_RUNS"])
    meta = json.loads((runs / "e1" / "meta.json").read_text())
    assert meta["tasks"] == [["gc", "GC005"], ["outsight", "OE034"]]
    assert meta["submodule_sha"].startswith("eeaea12") and meta["action_source"] == "dataset"
    assert (runs / "e1" / "videos" / "GC005" / "GC005.mp4").is_file()
    assert "GC005" in (runs / "e1" / "gen.log").read_text()
    r = pwa(env, "gen", "e1", "--runner", FAKE, "--tasks", "GC005")
    assert r.returncode == 1 and "--resume" in r.stderr
    r = pwa(env, "gen", "e1", "--runner", FAKE, "--tasks", "GC005", "--resume", check=0)
    assert "skip GC005" in r.stderr
    assert len(json.loads((runs / "e1" / "meta.json").read_text())["resumed"]) == 1
    env2 = {**env, "FAKE_FAIL": "GC016"}
    r = pwa(env2, "gen", "e2", "--runner", FAKE, "--tasks", "GC005", "GC016", "--json")
    assert r.returncode == 1
    s = json.loads(r.stdout)
    assert s["produced"] == 1 and s["failed"][0]["task_id"] == "GC016"


def test_sharded_gen_does_not_clash(env):
    pwa(env, "gen", "sh", "--runner", FAKE, "--family", "gc", "--shard", "0", "--num-shards", "2", check=0)
    pwa(env, "gen", "sh", "--runner", FAKE, "--family", "gc", "--shard", "1", "--num-shards", "2", check=0)
    vids = sorted(p.name for p in (Path(env["PWA_RUNS"]) / "sh" / "videos").iterdir())
    assert vids == ["GC005", "GC016", "GC031", "GC033", "GC036", "GC038"]


def test_preview_and_dry_score(env):
    env = {**env, "FAKE_SECONDS": "10"}
    pwa(env, "gen", "d", "--runner", FAKE, "--tasks", "GC005", "IF002", "OE001", "OE034", check=0)
    d = Path(pwa(env, "preview", "d", "GC005", check=0).stdout.strip())
    assert (d / "sampling_manifest.json").is_file() and list((d / "primary").glob("*.jpg"))
    assert pwa(env, "score", "d", "--passes", "1").returncode == 1  # no GEMINI_API_KEY
    s = json.loads(pwa(env, "score", "d", "--dry-run", "--passes", "1", "--json", check=0).stdout)
    assert s["failed"] == [] and s["ran"] == 6  # 4 score + gate for GC005, OE034 (IF must embed)
    ev = Path(env["PWA_RUNS"]) / "d" / "eval_dry" / "pass1"
    assert json.loads((ev / "GC005_gate.json").read_text())["mode"] == "gate"
    assert not (ev / "IF002_gate.json").exists()
    s = json.loads(pwa(env, "score", "d", "--dry-run", "--passes", "1", "--json", check=0).stdout)
    assert s["ran"] == 0 and s["skipped"] == 6  # idempotent


def _fake_eval(runs: Path, exp: str, k: int, scores: dict, dirname: str = "eval"):
    d = runs / exp / dirname / f"pass{k}"
    d.mkdir(parents=True, exist_ok=True)
    for tid, (val, passed) in scores.items():
        extra = {}
        if tid.startswith("IF"):
            extra["if_instruction_following_check"] = {"verdict": "pass" if passed else "fail",
                                                       "instruction_following_score": int(passed),
                                                       "failure_reason_zh": "" if passed else "subject static"}
        (d / f"{tid}_score.json").write_text(json.dumps(
            {"task_id": tid, "mode": "score", "score": {"final_score_1_to_5": val, "summary_zh": f"sum {tid}", **extra}}))
        if tid.startswith("GC"):
            (d / f"{tid}_gate.json").write_text(json.dumps(
                {"task_id": tid, "mode": "gate", "score": {"verdict": "pass" if passed else "fail",
                                                            "instruction_following_score": int(passed),
                                                            "failure_reason_zh": "" if passed else "no motion"}}))


def test_report_compare_failures_ls(env):
    runs = Path(env["PWA_RUNS"])
    tasks = ["GC005", "GC016", "IF002", "OE001", "OE034"]
    pwa(env, "gen", "a", "--runner", FAKE, "--tasks", *tasks, check=0)
    pwa(env, "gen", "b", "--runner", FAKE, "--tasks", *tasks, "--notes", "anchor v1", check=0)
    _fake_eval(runs, "a", 1, {"GC005": (3.0, True), "GC016": (4.0, False), "IF002": (2.0, True), "OE001": (2.0, True)})
    _fake_eval(runs, "a", 2, {"GC005": (3.2, True), "GC016": (4.0, False), "IF002": (2.2, True), "OE001": (2.2, True)})
    _fake_eval(runs, "b", 1, {"GC005": (4.0, True), "GC016": (4.0, True), "IF002": (2.0, False), "OE001": (2.0, True)})
    _fake_eval(runs, "b", 2, {"GC005": (4.0, True), "GC016": (4.2, True), "IF002": (2.0, False), "OE001": (2.1, True)})
    rep = json.loads(pwa(env, "report", "a", "--json", check=0).stdout)
    gc = rep["families"]["gc"]
    assert gc["per_pass"] == pytest.approx([2.0, 2.1]) and gc["gate_pass"] == 1
    # OE034 has a video but no score: dropped, outsight has no mean
    assert rep["families"]["outsight"]["dropped"] == 1 and rep["families"]["outsight"]["mean"] is None
    assert rep["overall_per_pass"] == pytest.approx([(2.0 + 2.0 + 2.0) / 3, (2.1 + 2.2 + 2.2) / 3])
    strict = json.loads(pwa(env, "report", "a", "--strict", "--json", check=0).stdout)
    assert strict["families"]["outsight"]["mean"] == 1.0
    txt = pwa(env, "report", "b", check=0).stdout
    assert "Genie 3" in txt and "overall" in txt
    with open(env["PWA_RESULTS_CSV"]) as fh:
        rows = list(csv.DictReader(fh))
    assert [r["exp"] for r in rows] == ["a", "b"] and rows[1]["notes"] == "anchor v1"
    pwa(env, "report", "a", check=0)  # upsert, not append
    with open(env["PWA_RESULTS_CSV"]) as fh:
        assert len(list(csv.DictReader(fh))) == 2
    c = json.loads(pwa(env, "compare", "a", "b", "--json", check=0).stdout)
    assert c["families"]["gc"]["delta"] == pytest.approx(4.05 - 2.05)
    assert c["families"]["gc"]["noise"] is False
    assert c["tasks"]["OE001"]["noise"] is True
    assert "REAL" in pwa(env, "compare", "a", "b", check=0).stdout
    f = {r["task_id"]: r for r in json.loads(pwa(env, "failures", "b", "--json", check=0).stdout)}
    assert f["IF002"]["status"] == ["gate_fail"] and f["IF002"]["reason"] == "subject static"
    assert "OE034" in f and "GC005" not in f
    ls = {r["exp"]: r for r in json.loads(pwa(env, "ls", "--json", check=0).stdout)}
    assert ls["a"]["gen"] == "done" and ls["a"]["passes"] == [1, 2] and ls["a"]["overall"] is not None


def test_screening_judge_never_touches_official_outputs(env):
    runs = Path(env["PWA_RUNS"])
    hy, slug = "gemini-4-hydrogen", "eval-gemini-4-hydrogen"
    tasks = ["GC005", "IF002", "OE001"]
    pwa(env, "gen", "a", "--runner", FAKE, "--tasks", *tasks, check=0)
    pwa(env, "gen", "b", "--runner", FAKE, "--tasks", *tasks, check=0)
    for k in (1, 2):
        _fake_eval(runs, "a", k, {"GC005": (3.0, True), "IF002": (2.0, True), "OE001": (2.0, True)}, slug)
        _fake_eval(runs, "b", k, {"GC005": (4.0, True), "IF002": (2.0, False), "OE001": (2.5, True)}, slug)
    # official view sees nothing: screening scores never count as official
    assert pwa(env, "report", "a").returncode == 1
    r = pwa(env, "report", "a", "--judge-model", hy, check=0)
    assert f"screening judge: {hy}, not comparable to the leaderboard" in r.stdout
    md = pwa(env, "report", "a", "--judge-model", hy, "--md", check=0).stdout
    assert "screening judge" in md and "not written to results/experiments.csv" in md
    rep = json.loads(pwa(env, "report", "a", "--judge-model", hy, "--json", check=0).stdout)
    assert rep["judge"]["model"] == hy and rep["families"]["gc"]["mean"] == pytest.approx(3.0)
    assert not Path(env["PWA_RESULTS_CSV"]).exists()
    assert not (runs / "a" / "report.json").exists() and (runs / "a" / "report.gemini-4-hydrogen.json").is_file()
    assert pwa(env, "compare", "a", "b").returncode == 1  # no official passes
    c = json.loads(pwa(env, "compare", "a", "b", "--judge-model", hy, "--json", check=0).stdout)
    assert c["judge"]["slug"] == "gemini-4-hydrogen" and c["families"]["gc"]["delta"] == pytest.approx(1.0)
    assert "screening judge" in pwa(env, "compare", "a", "b", "--judge-model", hy, check=0).stdout
    cl = json.loads(pwa(env, "cells", "a", "b", "--judge-model", hy, "--json", check=0).stdout)
    by = {r["task_id"]: r for r in cl["tasks"]}
    # GC005 3 -> 4 moves up; IF002 2 -> gate fail 1.0 moves down; OE001 +0.5 does not move
    assert (by["GC005"]["move"], by["IF002"]["move"], by["OE001"]["move"]) == ("up", "down", "")
    assert (cl["up"], cl["down"], cl["n_common"]) == (1, 1, 3)
    txt = pwa(env, "cells", "a", "b", "--judge-model", hy, check=0).stdout
    assert "screening judge" in txt and "up 1  down 1  of 3" in txt
    f = json.loads(pwa(env, "failures", "b", "--judge-model", hy, "--json", check=0).stdout)
    assert f["judge"]["model"] == hy and [r["task_id"] for r in f["tasks"]] == ["IF002"]
    fm = pwa(env, "failures", "b", "--judge-model", hy, "--all", "--md", check=0).stdout
    assert fm.startswith("> **screening judge") and "| GC005 |" in fm
    assert pwa(env, "report", "a", "--judge-thinking", "low").returncode == 1  # thinking needs a screening model
    assert not Path(env["PWA_RESULTS_CSV"]).exists() and not (runs / "a" / "report.json").exists()


def test_screening_dry_score_with_thinking(env):
    # the thinking shim runs the upstream module end to end (dry run: sampling only, no Gemini call)
    pytest.importorskip("google.genai")
    pwa(env, "gen", "t", "--runner", FAKE, "--tasks", "IF002", check=0)
    s = json.loads(pwa(env, "score", "t", "--dry-run", "--passes", "1", "--json", "--judge-model",
                       "gemini-4-hydrogen", "--judge-thinking", "low", check=0).stdout)
    assert s["failed"] == [] and s["ran"] == 1 and s["judge"]["slug"] == "gemini-4-hydrogen-think-low"
    assert (Path(env["PWA_RUNS"]) / "t" / "eval_dry" / "pass1" / "IF002_score.json").is_file()
    assert not (Path(env["PWA_RUNS"]) / "t" / "eval").exists()


def test_media_skips_pipeline_tests(env, tmp_path):
    # the fake runner makes test-pattern clips: never published, so no release or manifest
    runs = Path(env["PWA_RUNS"])
    pwa(env, "gen", "m", "--runner", FAKE, "--tasks", "GC005", "IF002", check=0)
    _fake_eval(runs, "m", 1, {"GC005": (3.0, True), "IF002": (2.0, False)})
    out = tmp_path / "media"
    s = json.loads(pwa(env, "media", "m", "--out", str(out), "--base-url", "https://x.test/dl/", check=0).stdout)
    assert s == {"exp": "m", "skipped": "pipeline test"}
    assert not list(out.glob("*")) if out.exists() else True


def test_doctor_json(env):
    r = pwa(env, "doctor", "--json", "--for", "score")
    out = json.loads(r.stdout)
    assert any(c["check"] == "$GEMINI_API_KEY set" and not c["ok"] for c in out["checks"])
    assert r.returncode == 1
    assert "sk-" not in r.stdout
