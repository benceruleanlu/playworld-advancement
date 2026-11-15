"""Screening judge: paths, verifier command, env isolation, cells readout, thinking shim. No dataset, no API."""
import argparse
import os
from pathlib import Path

import pytest

from pwa import report, score
from pwa.core import PwaError, RUNS

INFO = {"family": "gc", "task_id": "GC005", "dataset": "/d/gc/data.json", "image": "/nonexistent.jpg"}


def test_slug_and_dirs():
    assert score.Judge("gemini-4-hydrogen").slug == "gemini-4-hydrogen"
    assert score.Judge("models/gemini 4:x").slug == "models-gemini-4-x"
    assert score.Judge("gemini-4-hydrogen", "low").slug == "gemini-4-hydrogen-think-low"
    j = score.Judge("gemini-4-hydrogen")
    assert score.eval_dir("e") == RUNS / "e" / "eval"
    assert score.eval_dir("e", judge=j) == RUNS / "e" / "eval-gemini-4-hydrogen"
    assert score.eval_dir("e", True, j) == RUNS / "e" / "eval_dry"  # dry runs call no model
    assert "not comparable to the leaderboard" in j.label
    with pytest.raises(PwaError):
        score.Judge("x", "turbo")


def test_judge_of():
    ns = lambda **kw: argparse.Namespace(**{"judge_model": None, "judge_thinking": None, **kw})  # noqa: E731
    assert score.judge_of(ns()) is None
    assert score.judge_of(ns(judge_model="m", judge_thinking="low")) == score.Judge("m", "low")
    with pytest.raises(PwaError):
        score.judge_of(ns(judge_thinking="low"))  # the official judge stays at upstream settings
    assert score.judge_of(argparse.Namespace()) is None  # commands without the flags


def test_verifier_cmd_model_and_module(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
    out = Path("/o.json")
    cmd = score.verifier_cmd("score", INFO, Path("/v.mp4"), out, False)
    assert cmd[1:3] == ["-m", "metrics.vqa.score"] and cmd[cmd.index("--model") + 1] == "gemini-3.1-pro-preview"
    cmd = score.verifier_cmd("score", INFO, Path("/v.mp4"), out, False, judge=score.Judge("gemini-4-hydrogen"))
    assert cmd[1:3] == ["-m", "metrics.vqa.score"] and cmd[cmd.index("--model") + 1] == "gemini-4-hydrogen"
    cmd = score.verifier_cmd("gate", INFO, Path("/v.mp4"), out, False, judge=score.Judge("gemini-4-hydrogen", "low"))
    assert cmd[1:3] == ["-m", "pwa.judge_shim"] and cmd[cmd.index("--model") + 1] == "gemini-4-hydrogen"


def test_verifier_env_isolation(monkeypatch):
    monkeypatch.setenv("PWA_JUDGE_THINKING", "low")  # stray value must never reach the official judge
    assert "PWA_JUDGE_THINKING" not in score.verifier_env()
    assert "PWA_JUDGE_THINKING" not in score.verifier_env(score.Judge("m"))
    e = score.verifier_env(score.Judge("m", "low"))
    assert e["PWA_JUDGE_THINKING"] == "low" and str(score.ROOT) in e["PYTHONPATH"].split(os.pathsep)


def _rep(exp, means):
    return {"exp": exp, "judge": None, "tasks": {t: {"family": "gc", "mean": m} for t, m in means.items()}}


def test_cells_counts_full_point_moves_only():
    a = _rep("a", {"T1": 2.0, "T2": 3.0, "T3": 2.0, "T4": None, "T5": 1.0})
    b = _rep("b", {"T1": 3.0, "T2": 2.0, "T3": 2.9, "T4": 2.0, "T6": 5.0})
    c = report.cells(a, b)
    by = {r["task_id"]: r for r in c["tasks"]}
    assert set(by) == {"T1", "T2", "T3"}  # T4 unscored on one side, T5/T6 not shared
    assert (by["T1"]["move"], by["T2"]["move"], by["T3"]["move"]) == ("up", "down", "")
    assert (c["up"], c["down"], c["n_common"], c["unscored"]) == (1, 1, 3, ["T4"])
    assert [r["task_id"] for r in c["tasks"]] == ["T1", "T3", "T2"]  # sorted by delta, best first
    assert "up 1  down 1  of 3" in report.render_cells(c)


def test_thinking_shim_sets_level(monkeypatch):
    types = pytest.importorskip("google.genai.types")
    from pwa import judge_shim
    monkeypatch.setattr(types, "GenerateContentConfig", types.GenerateContentConfig)  # restored after the test
    monkeypatch.setattr(types, "_pwa_thinking_installed", False, raising=False)
    judge_shim.install("low")
    cfg = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert cfg.temperature == 0.1 and cfg.response_mime_type == "application/json"
