"""Capped smoke runs (pwa gen --max-chunks): reach the runner as upstream --num-chunks and are labelled everywhere."""
import ast
import csv
import json
import shutil
from pathlib import Path

import pytest

from pwa import core, report
from test_cli import FAKE, ROOT, _fake_eval, env, pwa  # noqa: F401  (env is a fixture)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


@pytest.mark.parametrize("meta,cap", [
    ({}, None),
    ({"max_chunks": 4}, 4),
    ({"runner_args": ["--seed", "1", "--num-chunks", "6"]}, 6),
    ({"runner_args": ["--num-chunks=3"]}, 3),
    ({"runner_args": ["--num-chunks", "30"]}, None),  # upstream default: not a cap
    ({"runner_args": ["--num-chunks", "40"]}, None),
    ({"runner_args": ["--num-chunks", "8", "--num-chunks", "2"]}, 2),  # argparse keeps the last
])
def test_chunk_cap_from_meta(meta, cap):
    assert core.chunk_cap(meta) == cap


def test_cap_label_and_notes():
    assert core.cap_label(None) == ""
    assert "capped smoke run: 1 agent chunk per rollout" in core.cap_label(1)
    assert "not comparable to official scores" in core.cap_label(4)
    assert report.capped_notes("try", 4) == "[capped smoke: 4 chunks] try"
    assert report.capped_notes(report.capped_notes("try", 4), 4) == "[capped smoke: 4 chunks] try"
    assert report.capped_notes("try", None) == "try"


def test_modal_cap_argv():
    tree = ast.parse((ROOT / "modal_app.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cap_argv")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "modal_app.py", "exec"), ns)  # noqa: S102
    assert ns["cap_argv"](0) == [] and ns["cap_argv"](4) == ["--max-chunks=4"]


@needs_ffmpeg
def test_capped_gen_report_and_csv(env):
    env = {**env, "PLAYER_API_KEY": "dummy-not-used-by-fake-runner"}
    runs = Path(env["PWA_RUNS"])
    pwa(env, "gen", "cap", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--max-chunks", "4",
        "--notes", "smoke", check=0)
    meta = json.loads((runs / "cap" / "meta.json").read_text())
    assert meta["max_chunks"] == 4 and "capped smoke run" in meta["label"]
    assert "--num-chunks 4" in (runs / "cap" / "gen.log").read_text()
    # uncapped runs keep the old command line
    pwa(env, "gen", "free", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", check=0)
    assert "--num-chunks" not in (runs / "free" / "gen.log").read_text()
    assert "max_chunks" not in json.loads((runs / "free" / "meta.json").read_text())

    _fake_eval(runs, "cap", 1, {"GC005": (3.0, True)})
    md = pwa(env, "report", "cap", "--md", check=0).stdout
    assert "Capped smoke run: 4 agent chunks per rollout" in md
    assert "capped smoke run" in pwa(env, "report", "cap", check=0).stdout
    assert json.loads(pwa(env, "report", "cap", "--json", check=0).stdout)["max_chunks"] == 4
    with open(env["PWA_RESULTS_CSV"]) as fh:
        row = next(r for r in csv.DictReader(fh) if r["exp"] == "cap")
    assert row["max_chunks"] == "4" and row["notes"] == "[capped smoke: 4 chunks] smoke"

    _fake_eval(runs, "free", 1, {"GC005": (3.0, True)})
    r = pwa(env, "compare", "free", "cap", check=0)
    assert "chunk caps differ" in r.stderr
    # a two-judge panel warns the same way, and its report keeps the capped banner
    for exp in ("free", "cap"):
        for slug in ("j1", "openai-j2"):
            _fake_eval(runs, exp, 1, {"GC005": (3.0, True)}, dirname=f"eval-{slug}")
    panel_args = ["--judge-model", "j1", "--judge-model", "openai:j2"]
    r = pwa(env, "cells", "free", "cap", *panel_args, check=0)
    assert r.returncode == 0 and "chunk caps differ" in r.stderr and "chunk caps differ (A=none, B=4)" in r.stdout
    assert "capped smoke run: 4 agent chunks" in pwa(env, "report", "cap", *panel_args, check=0).stdout


@needs_ffmpeg
def test_cap_refusals(env):
    env = {**env, "PLAYER_API_KEY": "dummy"}
    r = pwa(env, "gen", "d", "--runner", FAKE, "--tasks", "GC005", "--max-chunks", "4")
    assert r.returncode == 2 and "dataset" in r.stderr
    r = pwa(env, "gen", "z", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--max-chunks", "0")
    assert r.returncode == 2
    r = pwa(env, "gen", "both", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--max-chunks", "4",
            "--", "--num-chunks", "5")
    assert r.returncode == 2 and "once" in r.stderr
    pwa(env, "gen", "c", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--max-chunks", "4", check=0)
    r = pwa(env, "gen", "c", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--resume")
    assert r.returncode == 2 and "same cap" in r.stderr
    pwa(env, "gen", "c", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--max-chunks", "4",
        "--resume", check=0)


def test_mark_running_row_is_labelled(tmp_path):
    dest = tmp_path / "x.csv"
    report.mark_row("s1", dest, "running", "custom", "lingbot_world2", "agent", "try", "", max_chunks=4)
    report.mark_row("s2", dest, "running", "dev", "lingbot_world2", "agent", "", "")
    with open(dest) as fh:
        rows = {r["exp"]: r for r in csv.DictReader(fh)}
    assert rows["s1"]["max_chunks"] == "4" and rows["s1"]["notes"] == "[capped smoke: 4 chunks] try"
    assert rows["s2"]["max_chunks"] == "" and rows["s2"]["notes"] == ""
