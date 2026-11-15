"""Scripted-player runs (--lingbot-scripted-player) are labelled as A/B only, never as AI-played closed loop."""
import csv
import json
import shutil
from pathlib import Path

import pytest

from pwa import core, media, report
from test_cli import FAKE, _fake_eval, env, pwa  # noqa: F401  (env is a fixture)

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


def test_detection_notes_and_labels():
    assert core.scripted_player({"runner_args": ["--lingbot-turn-cal", "--lingbot-scripted-player"]})
    assert core.scripted_player({"scripted_player": True, "runner_args": []})
    assert not core.scripted_player({"runner_args": ["--lingbot-turn-cal"]}) and not core.scripted_player({})
    assert core.scripted_runner([], {"LINGBOT_SCRIPTED_PLAYER": "1"}) and not core.scripted_runner([], {})
    tag = core.SCRIPTED_TAG
    assert report.scripted_notes("try", True) == f"{tag} try"
    assert report.scripted_notes(report.scripted_notes("try", True), True) == f"{tag} try"
    assert report.scripted_notes("try", False) == "try" and report.scripted_notes("", True) == tag
    meta = {"action_source": "agent", "runner_args": ["--lingbot-scripted-player"]}
    assert core.SCRIPTED_LABEL in media.run_labels(meta, scored=True)
    assert media.run_labels({"action_source": "agent"}, scored=True) == []


@needs_ffmpeg
def test_scripted_gen_needs_no_key_and_report_row_is_tagged(env):
    env = {k: v for k, v in env.items() if k != "PLAYER_API_KEY"}
    runs = Path(env["PWA_RUNS"])
    r = pwa(env, "gen", "nokey", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent")
    assert r.returncode != 0 and "PLAYER_API_KEY" in r.stderr
    pwa(env, "gen", "scr", "--runner", FAKE, "--tasks", "GC005", "--action-source", "agent", "--notes", "ab",
        "--", "--lingbot-scripted-player", check=0)
    assert json.loads((runs / "scr" / "meta.json").read_text())["scripted_player"] is True
    _fake_eval(runs, "scr", 1, {"GC005": (3.0, True)})
    assert core.SCRIPTED_LABEL in pwa(env, "report", "scr", check=0).stdout
    assert core.SCRIPTED_LABEL.capitalize() in pwa(env, "report", "scr", "--md", check=0).stdout
    with open(env["PWA_RESULTS_CSV"]) as fh:
        row = next(r for r in csv.DictReader(fh) if r["exp"] == "scr")
    assert row["action_source"] == "agent" and row["notes"] == f"{core.SCRIPTED_TAG} ab"
