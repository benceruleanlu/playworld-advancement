"""Model text prompt selection (adapters/common/prompts.py). No GPU, no API calls."""
import importlib.util
import json
import types
from pathlib import Path

import pytest

from adapters.common import prompts

ROOT = Path(__file__).resolve().parents[1]
OE = {"task_id": "OE018", "category": "OE", "prompt": "wait and observe",
      "image_caption": "Hot water being poured\n from a kettle  into a glass teapot."}
IF = {"task_id": "IF052", "category": "IF", "prompt": "The boy walks forward. ",
      "image_caption": "A boy stands on a forest clearing."}


@pytest.fixture(autouse=True)
def _clean():
    prompts._current.clear()
    yield
    prompts._current.clear()


def test_goal_mode_is_upstream_behaviour():
    assert prompts.compose(OE, "wait and observe") == "wait and observe"
    assert prompts.compose(OE, "wait and observe", "goal") == "wait and observe"
    assert prompts.compose(None, "g", "auto") == "g"


def test_caption_and_auto_modes():
    cap = "Hot water being poured from a kettle into a glass teapot."  # whitespace collapsed
    assert prompts.compose(OE, OE["prompt"], "caption") == cap
    assert prompts.compose(OE, OE["prompt"], "auto") == cap  # goal dropped outside IF
    assert prompts.compose(IF, IF["prompt"], "caption") == "A boy stands on a forest clearing."
    assert prompts.compose(IF, IF["prompt"], "auto") == "A boy stands on a forest clearing. The boy walks forward."
    assert prompts.compose({"task_id": "X", "image_caption": "  "}, "goal text", "auto") == "goal text"
    with pytest.raises(ValueError):
        prompts.compose(OE, "g", "captions")


def test_install_records_the_task_and_calls_through():
    calls = []
    fake = types.SimpleNamespace(run_task=lambda task, engine, out, args: calls.append((task["task_id"], engine)) or "ok")
    prompts.install(fake)
    assert prompts.model_prompt("wait and observe", "OE018_chunk_01", "auto") == "wait and observe"  # nothing recorded yet
    assert fake.run_task(OE, "engine", "out", "args") == "ok" and calls == [("OE018", "engine")]
    assert prompts.model_prompt("wait and observe", "OE018_chunk_07", "auto").startswith("Hot water")
    assert prompts.model_prompt("wait and observe", "OE018_full", "caption").startswith("Hot water")
    assert prompts.model_prompt("wait and observe", "OE018_full", "goal") == "wait and observe"
    # a call for another task (stale record) keeps the goal
    assert prompts.model_prompt("other goal", "OE0180_full", "auto") == "other goal"
    assert prompts.model_prompt("other goal", "GC005_chunk_01", "auto") == "other goal"


@pytest.mark.skipif(importlib.util.find_spec("httpx") is None, reason="upstream run_agent needs httpx")
def test_upstream_main_looks_run_task_up_at_call_time():
    import inspect

    from adapters.common.upstream import import_run_agent
    ra = import_run_agent()
    assert "run_task(task, engine, output_dir, args)" in inspect.getsource(ra.main)
    assert list(inspect.signature(ra.run_task).parameters)[0] == "task"


@pytest.mark.skipif(not (ROOT / "data" / "insight" / "data.json").is_file(), reason="needs dataset metadata")
def test_dev_insight_and_outsight_tasks_get_a_scene_prompt():
    dev = {line.split()[1] for line in (ROOT / "splits" / "dev.tsv").read_text().splitlines()
           if line.split()[0] in ("insight", "outsight")}
    seen = 0
    for fam in ("insight", "outsight"):
        for task in json.loads((ROOT / "data" / fam / "data.json").read_text()):
            if task["task_id"] not in dev:
                continue
            seen += 1
            out = prompts.compose(task, task["prompt"], "auto")
            assert out != task["prompt"] and len(out) > 30
            assert "wait and observe" not in out.lower() and "turn the camera" not in out.lower()
    assert seen == 12
