"""Pure helpers of the SANA-WM streaming runner (no torch, no GPU)."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("httpx")  # upstream run_agent imports it
spec = importlib.util.spec_from_file_location("sana_stream_run", Path(__file__).parents[1] / "adapters/sana_stream/run.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def test_parse_action():
    assert ss.parse_action("j-25") == [("j", 25)]
    assert ss.parse_action("w-20,none-50") == [("w", 20), ("none", 50)]
    assert ss.parse_action("") == []


def test_closed_loop_call_is_exactly_one_block():
    assert ss.blocks_from_action("j-25", single_call_frames=25) == [["j"] * 24]
    assert ss.blocks_from_action("none-33", single_call_frames=33) == [["none"] * 24]


def test_open_loop_string_is_split_and_padded():
    blocks = ss.blocks_from_action("j-30,none-10")
    assert len(blocks) == 2 and blocks[0] == ["j"] * 24 and blocks[1] == ["j"] * 6 + ["none"] * 18


def test_harness_turn_keys_become_sana_yaw_keys(monkeypatch):
    monkeypatch.delenv("SANA_KEYMAP", raising=False)
    assert ss.keys_to_dsl(["j"] * 24 + ["none"] * 24 + ["a"] * 2 + ["w"]) == "a-24,none-24,j-2,w-1"
    monkeypatch.setenv("SANA_KEYMAP", "legacy")
    assert ss.keys_to_dsl(["j"] * 3) == "j-3"


def test_importing_the_runner_leaves_argv_and_the_engine_alone():
    assert ss.run_agent.SanaWMEngine is not ss.SanaStreamEngine  # installed only when run as a script
