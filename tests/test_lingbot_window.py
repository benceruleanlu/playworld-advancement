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


@pytest.mark.parametrize("argv", [
    ["run.py", "--lingbot-local-attn", "1"],
    ["run.py", "--lingbot-local-attn", "6", "--lingbot-sink-size", "6"],
    ["run.py", "--lingbot-local-attn", "18", "--lingbot-sink-size", "18"],
    ["run.py", "--lingbot-local-attn", "-1", "--lingbot-sink-size", "6"],
    ["run.py", "--tasks", "OE018", "--lingbot-sink-size"],
])
def test_windows_upstream_cannot_run_are_rejected_before_load(argv):
    with pytest.raises(SystemExit):
        R.configure(argv, environ={})


def test_full_attention_with_no_sink_and_smallest_window_accepted():
    flags, _ = R.configure(["run.py", "--lingbot-local-attn", "-1", "--lingbot-sink-size", "0"], environ={})
    assert (flags["local_attn"], flags["sink"]) == (-1, 0)
    flags, _ = R.configure(["run.py", "--lingbot-local-attn", "5", "--lingbot-sink-size", "1"], environ={})
    assert (flags["local_attn"], flags["sink"]) == (5, 1)


class _Attn:
    def __init__(self):
        self.local_attn_size, self.sink_size = 18, 6


class _Model:
    def __init__(self):
        self.blocks = [_Attn(), _Attn()]

    def modules(self):
        return [self, *self.blocks]


class _Pipe:
    def __init__(self):
        self.model, self.local_attn_size, self.sink_size = _Model(), 18, 6


def test_set_window_changes_the_loaded_pipe_in_place_and_restores_defaults():
    pipe = _Pipe()
    assert R.set_window(pipe, 18, 1) == 2
    assert (pipe.local_attn_size, pipe.sink_size) == (18, 1)
    assert all((b.local_attn_size, b.sink_size) == (18, 1) for b in pipe.model.blocks)
    R.set_window(pipe, 18, 6)  # the next arm in the same process
    assert all((b.local_attn_size, b.sink_size) == (18, 6) for b in pipe.model.blocks)


def test_pipe_cache_key_does_not_include_the_window():
    import inspect
    src = inspect.getsource(R.load_pipe)
    assert "LOCAL_ATTN," not in src and "SINK)" not in src
