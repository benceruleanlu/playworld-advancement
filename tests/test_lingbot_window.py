"""Attention window size flags (--lingbot-local-attn / --lingbot-sink-size). No GPU/torch."""
import pytest
from adapters.lingbot_world2 import run as R


def test_defaults_are_readme_settings_and_argv_untouched():
    flags, argv = R.configure(["run.py", "--tasks", "OE018"], environ={})
    assert (flags["local_attn"], flags["sink"]) == (18, 6)
    assert argv == ["run.py", "--tasks", "OE018"]


def test_argv_forms_and_stripping():
    flags, argv = R.configure(["run.py", "--lingbot-sink-size", "1", "--lingbot-local-attn=13", "--tasks", "OE018"], environ={})
    assert (flags["local_attn"], flags["sink"]) == (13, 1)
    assert argv == ["run.py", "--tasks", "OE018"]


def test_env_fallback_and_argv_wins():
    env = {"LINGBOT_SINK_SIZE": "0", "LINGBOT_LOCAL_ATTN_SIZE": "24"}
    flags, _ = R.configure(["run.py"], environ=env)
    assert (flags["local_attn"], flags["sink"]) == (24, 0)
    flags, _ = R.configure(["run.py", "--lingbot-sink-size", "2"], environ=env)
    assert flags["sink"] == 2


def test_invalid_sizes_rejected():
    for argv in (["run.py", "--lingbot-sink-size", "-1"], ["run.py", "--lingbot-local-attn", "0"],
                 ["run.py", "--lingbot-sink-size", "six"]):
        with pytest.raises(SystemExit):
            R.configure(argv, environ={})
