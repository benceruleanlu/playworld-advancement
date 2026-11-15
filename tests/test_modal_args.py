"""modal_app.shard_argv: harness shard flags must stay before the `--` that starts runner args."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _shard_argv():
    # modal_app imports modal and builds images at import time; load just the pure helper.
    tree = ast.parse((ROOT / "modal_app.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "shard_argv")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "modal_app.py", "exec"), ns)  # noqa: S102
    return ns["shard_argv"]


def test_shard_flags_go_before_runner_args():
    f = _shard_argv()
    base = ["e", "--runner", "lingbot_world2", "--action-source", "agent", "--tasks", "A", "B", "--resume"]
    assert f(base, 2, 6) == [*base, "--shard", "2", "--num-shards", "6"]
    extra = [*base, "--", "--lingbot-turn-cal", "--agent-model", "gpt-6-luna"]
    got = f(extra, 2, 6)
    assert got == [*base, "--shard", "2", "--num-shards", "6", "--", "--lingbot-turn-cal", "--agent-model", "gpt-6-luna"]
    assert got.index("--shard") < got.index("--")
    assert f(extra, 0, 1) == extra  # single shard: unchanged


def test_runner_args_are_exactly_what_follows_the_separator():
    f = _shard_argv()
    argv = f(["e", "--runner", "x", "--tasks", "A", "--", "--agent-model", "m"], 3, 6)
    i = argv.index("--")
    assert argv[i + 1:] == ["--agent-model", "m"]           # what pwa forwards to the runner
    assert argv[:i][-4:] == ["--shard", "3", "--num-shards", "6"]  # what pwa itself parses


def test_cpu_request_defaults_to_modal_default():
    tree = ast.parse((ROOT / "modal_app.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cpu_request")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "modal_app.py", "exec"), ns)  # noqa: S102
    f = ns["cpu_request"]
    assert f(None) is None and f("") is None and f("  ") is None  # unchanged: no cpu= request
    assert f("8") == 8.0 and f("2.5") == 2.5
    for bad in ("lots", "0", "-1"):
        try:
            f(bad)
        except SystemExit:
            continue
        raise AssertionError(bad)
    src = (ROOT / "modal_app.py").read_text()
    assert src.count("gpu=GPU, cpu=CPU,") == 2  # both generation functions take the request
