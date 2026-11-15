import threading
import time

import pytest

from adapters.lingbot_world2 import run as R
from adapters.lingbot_world2 import watchdog as W


def test_parse_defaults_env_and_args():
    assert W.parse([], {}) == (W.Limits(300.0, 0.0), [])
    assert W.parse([], {"LINGBOT_STALL_DUMP_S": "0", "LINGBOT_STALL_ABORT_S": "900"})[0] == W.Limits(0.0, 900.0)
    assert W.parse([], {"LINGBOT_STALL_DUMP_S": " "})[0] == W.Limits(300.0, 0.0)
    lim, rest = W.parse(["run.py", "--lingbot-stall-abort", "900", "--tasks", "GC005",
                         "--lingbot-stall-dump=60"], {"LINGBOT_STALL_ABORT_S": "5"})
    assert lim == W.Limits(60.0, 900.0)  # args beat env
    assert rest == ["run.py", "--tasks", "GC005"]
    for argv, env in ((["--lingbot-stall-abort", "soon"], {}), (["--lingbot-stall-abort"], {}),
                      ([], {"LINGBOT_STALL_DUMP_S": "-1"}), ([], {"LINGBOT_STALL_ABORT_S": "nan"})):
        with pytest.raises(SystemExit):
            W.parse(argv, env)


def test_configure_strips_stall_args_and_keeps_arms_apart():
    flags, argv = R.configure(["run.py", "--lingbot-stall-abort", "900", "--tasks", "A", "--lingbot-turn-cal"], {})
    assert flags["stall"] == W.Limits(300.0, 900.0) and flags["turn_cal"]
    assert argv == ["run.py", "--tasks", "A"]
    # a later arm without the arg gets the defaults back (configure is per main() call)
    assert R.configure(["run.py", "--tasks", "A"], {})[0]["stall"] == W.Limits()
    assert "abort off" in W.Limits().describe() and "abort 900s (exit 124)" in W.Limits(300, 900).describe()


def test_fast_call_prints_nothing_and_never_aborts(tmp_path):
    exits = []
    with open(tmp_path / "err", "w+") as f:
        with W.watch("GC005_chunk_01", W.Limits(5, 5), file=f, exit_fn=exits.append):
            pass
        time.sleep(0.05)
        f.seek(0)
        assert f.read() == ""
    assert exits == []


def test_stuck_call_dumps_stacks_then_aborts(tmp_path, capsys):
    exits = []
    done = threading.Event()

    def exit_fn(code):
        exits.append(code)
        done.set()

    with open(tmp_path / "err", "w+") as f:
        with W.watch("GC033_chunk_01", W.Limits(0.1, 0.4), file=f, exit_fn=exit_fn):
            assert done.wait(5), "abort timer never fired"
        f.seek(0)
        out = f.read()
    assert exits == [W.ABORT_EXIT_CODE]
    assert "Thread" in out or "Stack" in out  # faulthandler dump
    assert "test_stuck_call_dumps_stacks_then_aborts" in out  # the stuck frame is named
    assert "GC033_chunk_01 still running after 0s" in out
    assert "returned after" in out  # the late return is logged too
    # the stall line also reaches the current sys.stderr (gen.log under pwa gen-arms)
    assert "[lingbot] stall: GC033_chunk_01 still running" in capsys.readouterr().err


def test_off_by_zero(tmp_path):
    exits = []
    with open(tmp_path / "err", "w+") as f:
        with W.watch("x", W.Limits(0, 0), file=f, exit_fn=exits.append):
            time.sleep(0.2)
        f.seek(0)
        assert f.read() == ""
    assert exits == []


def test_timers_are_cleared_when_the_call_raises(tmp_path):
    exits = []
    with open(tmp_path / "err", "w+") as f:
        with pytest.raises(RuntimeError):
            with W.watch("x", W.Limits(0.2, 0.2), file=f, exit_fn=exits.append):
                raise RuntimeError("boom")
        time.sleep(0.4)
        f.seek(0)
        assert f.read() == ""
    assert exits == []
