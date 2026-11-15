"""pwa gen-arms: arm parsing and naming, in-process launches that leave no state behind, one model load for
N arms (fake runner end to end, and the LingBot runner with a mocked `wan` and upstream). No GPU, no API."""
import ast
import json
import os
import shutil
import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pwa import arms  # noqa: E402
from pwa.core import PwaError  # noqa: E402

FAKE = str(ROOT / "tests" / "fake_runner.py")


# -- parsing and naming ---------------------------------------------------------

def test_parse_arms():
    assert arms.parse_arms(" | --lingbot-turn-cal --lingbot-player-hint") == [
        [], ["--lingbot-turn-cal", "--lingbot-player-hint"]]
    assert arms.parse_arms("--a|--b x|") == [["--a"], ["--b", "x"], []]
    assert arms.parse_arms("--seed 1") == [["--seed", "1"]]
    for bad in ("", "   ", "--a 'unclosed", "|".join(["--x"] * (arms.MAX_ARMS + 1))):
        with pytest.raises(PwaError):
            arms.parse_arms(bad)


def test_names_and_listing():
    assert arms.arm_names("g", 3) == ["g-a1", "g-a2", "g-a3"]
    assert arms.listing("g", " | --lingbot-turn-cal --lingbot-player-hint") == [
        "g-a1 1/2 base", "g-a2 2/2 --lingbot-turn-cal --lingbot-player-hint"]


def test_labels_include_shared_args():
    # the args every arm gets come first; "base" only when the arm ran with no args at all
    assert arms.arm_label([], ["--lingbot-stateless"]) == "--lingbot-stateless"
    assert arms.arm_label(["--x"], ["--s"]) == "--s --x" and arms.arm_label([], []) == "base"
    assert arms.listing("g", " | --lingbot-turn-cal", "--lingbot-stateless") == [
        "g-a1 1/2 --lingbot-stateless", "g-a2 2/2 --lingbot-stateless --lingbot-turn-cal"]
    with pytest.raises(PwaError):
        arms.listing("g", "|", "'unclosed")


def test_listing_cli_takes_shared_args():
    r = subprocess.run([sys.executable, "-m", "pwa.arms", "g", " | --b", " --agent-model m"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.splitlines() == ["g-a1 1/2 --agent-model m", "g-a2 2/2 --agent-model m --b"]


def test_cli_accepts_arms_value_starting_with_dashes():
    from pwa import cli
    assert cli._join_arms(["gen-arms", "g", "--arms", "--a|--b", "--tasks", "X", "--", "--arms", "y"]) == [
        "gen-arms", "g", "--arms=--a|--b", "--tasks", "X", "--", "--arms", "y"]
    a = cli.parser().parse_args(cli._join_arms(["gen-arms", "g", "--arms", "--lingbot-turn-cal|--lingbot-stateless"]))
    assert a.arms == "--lingbot-turn-cal|--lingbot-stateless"
    assert cli._join_arms(["gen-arms", "g", "--arms= | --x"]) == ["gen-arms", "g", "--arms= | --x"]


def _modal_fn(name):
    # modal_app imports modal at import time; load just the pure helper.
    tree = ast.parse((ROOT / "modal_app.py").read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "modal_app.py", "exec"), ns)  # noqa: S102
    return ns[name]


def test_modal_arm_names_match_pwa():
    f = _modal_fn("arm_exps")
    for text in (" | --a", "--a|--b|--c", "--a|", "--x"):
        assert f("g", text) == arms.arm_names("g", len(arms.parse_arms(text)))
    assert f("g", "") == []


def test_modal_claim_names_refuses_a_reused_name():
    ns: dict = {}
    tree = ast.parse((ROOT / "modal_app.py").read_text())
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("arm_exps", "claim_names")]
    exec(compile(ast.Module(body=fns, type_ignores=[]), "modal_app.py", "exec"), ns)  # noqa: S102
    claim = ns["claim_names"]
    assert claim("g", " | --x", {"other"}, False) == ["g-a1", "g-a2"]
    assert claim("g", "", set(), False) == ["g"]
    with pytest.raises(SystemExit, match="g-a2 already in the pwa-runs Volume"):
        claim("g", " | --x", {"g-a2"}, False)
    assert claim("g", " | --x", {"g-a2"}, True) == ["g-a1", "g-a2"]


def test_owned_needs_every_meta_from_this_run(tmp_path, monkeypatch):
    from pwa import core
    monkeypatch.setattr(core, "RUNS", tmp_path)
    for name, ids in {"mine": ["r1"], "old": ["r0"], "mixed": ["r1", "r0"], "none": [None]}.items():
        for k, rid in enumerate(ids):
            d = tmp_path / name
            d.mkdir(exist_ok=True)
            (d / f"meta.shard{k}of{len(ids)}.json").write_text(json.dumps({"exp": name, **({"run_id": rid} if rid else {})}))
    assert arms.owned("mine", "r1")
    assert not arms.owned("old", "r1") and not arms.owned("mixed", "r1") and not arms.owned("none", "r1")
    assert not arms.owned("missing", "r1") and not arms.owned("mine", "")


def test_provenance_records_run_id_only_when_set(monkeypatch):
    from pwa import core
    monkeypatch.delenv("PWA_RUN_ID", raising=False)
    assert "run_id" not in core.provenance()
    monkeypatch.setenv("PWA_RUN_ID", "123-1")
    assert core.provenance()["run_id"] == "123-1"


# -- in-process launch ------------------------------------------------------------

def test_inproc_launch_restores_state_and_captures_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ARM_LEAK", raising=False)
    seen = {}

    def main(argv):
        seen["argv"], seen["sys_argv"], seen["cwd"] = argv, list(sys.argv), os.getcwd()
        seen["env"] = os.environ.get("FROM_LAUNCH")
        os.environ["ARM_LEAK"] = "1"
        print("hello")
        print("[agent] fallback=WAIT", file=sys.stderr)
        sys.stdout.write("no newline")
        raise SystemExit(3)

    lines = []
    argv_before = list(sys.argv)
    rc = arms.inproc_launch(main)(["python", "-u", "/r/run.py", "--tasks", "A"], {**os.environ, "FROM_LAUNCH": "x"},
                                  lines.append)
    assert rc == 3
    assert seen["argv"] == seen["sys_argv"] == ["/r/run.py", "--tasks", "A"]
    assert seen["cwd"] == str(arms.ROOT) and seen["env"] == "x"
    assert lines == ["hello\n", "[agent] fallback=WAIT\n", "no newline\n"]
    assert "ARM_LEAK" not in os.environ and "FROM_LAUNCH" not in os.environ
    assert sys.argv == argv_before and os.getcwd() == str(tmp_path)


def test_inproc_launch_crash_is_a_failed_family():
    def main(argv):
        raise RuntimeError("boom")
    lines = []
    assert arms.inproc_launch(main)(["python", "-u", "r.py"], dict(os.environ), lines.append) == 1
    assert any("RuntimeError: boom" in x for x in lines)
    assert arms.inproc_launch(lambda argv: None)(["python", "-u", "r.py"], dict(os.environ), lines.append) == 0


def test_on_line_echo_reaches_real_stderr_not_the_capture():
    # gen.py's on_line writes each line to sys.stderr; inside the capture that must not recurse.
    got = []

    def on_line(line):
        sys.stderr.write("")  # would recurse into the capture if it were still installed
        got.append(line)
    assert arms.inproc_launch(lambda argv: print("x"))(["python", "-u", "r.py"], dict(os.environ), on_line) == 0
    assert got == ["x\n"]


def test_load_main_refuses_scripts_without_guard(tmp_path):
    p = tmp_path / "script.py"
    p.write_text("raise SystemExit('ran at import')\n")
    with pytest.raises(PwaError, match="guard"):
        arms.load_main(p)
    with pytest.raises(PwaError, match="SANA"):
        arms.load_main(arms.SANA_RUNNER.resolve())


# -- end to end with the fake runner ------------------------------------------

@pytest.fixture
def env(tmp_path):
    e = {**os.environ, "PWA_RUNS": str(tmp_path / "runs"), "PWA_RESULTS_CSV": str(tmp_path / "experiments.csv"),
         "FAKE_SECONDS": "1"}
    e.pop("GEMINI_API_KEY", None)
    return e


def pwa(env, *args):
    return subprocess.run([sys.executable, "-m", "pwa.cli", *args], cwd=ROOT, env=env, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_gen_arms_end_to_end(env):
    r = pwa(env, "gen-arms", "g", "--arms", " | --foo --bar", "--tasks", "GC005", "OE034", "--runner", FAKE,
            "--notes", "smoke", "--json", "--", "--common")
    assert r.returncode == 0, r.stderr
    s = json.loads(r.stdout)
    assert [a["exp"] for a in s["arms"]] == ["g-a1", "g-a2"] and not s["failed"]
    runs = Path(env["PWA_RUNS"])
    assert not (runs / "g").exists()
    for i, (name, arm) in enumerate([("g-a1", []), ("g-a2", ["--foo", "--bar"])], 1):
        meta = json.loads((runs / name / "meta.json").read_text())
        assert meta["exp"] == name and meta["runner_args"] == ["--common", *arm]
        assert meta["arm_group"] == "g" and meta["arm"] == i and meta["num_arms"] == 2 and meta["arm_args"] == arm
        assert meta["tasks"] == [["gc", "GC005"], ["outsight", "OE034"]]
        # the label names every arg the arm ran with, shared ones included (arm 1 is not "base")
        assert meta["notes"] == f"smoke [arm {i}/2 of g: {' '.join(['--common', *arm])}]"
        assert meta["last_gen"]["produced"] == 2
        for tid in ("GC005", "OE034"):
            assert (runs / name / "videos" / tid / f"{tid}.mp4").is_file()
        log = (runs / name / "gen.log").read_text()
        # the fake model loaded once in the process: every family call of every arm reports loads=1
        assert log.count("[fake] model loads=1") == 2 and "loads=2" not in log
        assert f"args=--common {' '.join(arm)}".strip() in log
    # every arm name must be new, checked before anything runs
    r = pwa(env, "gen-arms", "g", "--arms", " | --foo", "--tasks", "GC005", "--runner", FAKE)
    assert r.returncode == 1 and "already exist" in r.stderr


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_gen_arms_failure_in_one_arm(env):
    r = pwa({**env, "FAKE_FAIL": "GC005"}, "gen-arms", "f", "--arms", "|", "--tasks", "GC005", "--runner", FAKE, "--json")
    assert r.returncode == 1
    s = json.loads(r.stdout)
    assert s["failed"] and all(a["failed"][0]["task_id"] == "GC005" for a in s["arms"])


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_gen_arms_dash_leading_arms_value(env):
    # no leading space: argparse alone would reject this value as a missing argument
    r = pwa(env, "gen-arms", "d", "--arms", "--foo|--bar", "--tasks", "GC005", "--runner", FAKE, "--json")
    assert r.returncode == 0, r.stderr
    assert [a["arm_args"] for a in json.loads(r.stdout)["arms"]] == [["--foo"], ["--bar"]]


def test_gen_arms_rejects_sana(env):
    r = pwa(env, "gen-arms", "s", "--arms", "|", "--tasks", "GC005", "--runner", "sana")
    assert r.returncode == 1 and "main(argv)" in r.stderr


# -- LingBot runner: one pipe for N arms, no state carried between them --------

def test_lingbot_main_loads_once_and_resets_state(tmp_path, monkeypatch):
    from adapters.lingbot_world2 import poses as P
    from adapters.lingbot_world2 import run as R

    root, weights = tmp_path / "lingbot", tmp_path / "weights"
    (root / "wan").mkdir(parents=True)
    (weights / "lingbot-world-v2-14b-causal-fast").mkdir(parents=True)
    for k in ("LINGBOT_VARIANT", "LINGBOT_TURN_CAL", "LINGBOT_SESSION", "LINGBOT_PLAYER_HINT", "LINGBOT_PROMPT_MODE",
              "LINGBOT_REANCHOR", "LINGBOT_YAW_RAD", "LINGBOT_PITCH_RAD", "PLAYER_API_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LINGBOT_ROOT", str(root))
    monkeypatch.setenv("LINGBOT_WEIGHTS", str(weights))

    loads = []

    class Pipe:
        def __init__(self, **kw):
            loads.append(kw)

    wan = types.ModuleType("wan")
    wan.WanI2VCausal = Pipe
    configs = types.ModuleType("wan.configs")
    configs.WAN_CONFIGS = {"i2v-A14B": SimpleNamespace(sample_shift=5.0), "i2v-1.3B": SimpleNamespace(sample_shift=5.0)}
    i2v = types.ModuleType("wan.image2video")  # the loader names fast_start patches during a load
    originals = {n: (lambda *a, **k: None) for n in ("T5EncoderModel", "Wan2_1_VAE", "load_dit_model")}
    for n, f in originals.items():
        setattr(i2v, n, f)
    wan.image2video = i2v
    monkeypatch.setitem(sys.modules, "wan", wan)
    monkeypatch.setitem(sys.modules, "wan.configs", configs)
    monkeypatch.setitem(sys.modules, "wan.image2video", i2v)
    monkeypatch.setattr(R, "_PIPES", {})
    for k in ("LINGBOT_FAST", "LINGBOT_FAST_T5", "LINGBOT_FAST_LOAD", "LINGBOT_FAST_Y", "LINGBOT_T5_CPU"):
        monkeypatch.delenv(k, raising=False)

    calls = []

    def fake_import(fresh=False):
        """A new run_agent stand-in per call, like a fresh upstream import; main() builds the engine from
        whatever SanaWMEngine is at call time and runs one task through run_task."""
        m = types.ModuleType("run_agent")

        def run_task(task, engine, output_dir, args):
            engine._calibrate("GC005_chunk_01", 29)  # closed-loop chunk: turn-cal sets the rates
            calls[-1]["yaw"] = P.YAW
            return {"task_id": task["task_id"], "success": True}

        def main():
            args = SimpleNamespace(seed=42, fps=16, max_total_frames=961, action_frame_unit=20, argv=list(sys.argv))
            engine = m.SanaWMEngine(args)
            calls[-1].update(engine=engine, argv=args.argv, run_task=m.run_task)
            m.run_task({"task_id": "GC005"}, engine, str(tmp_path), args)

        m.run_task, m.main = run_task, main
        m.decide_action = lambda *a, **k: "W"
        m.to_sana_key = lambda a: "w"
        calls.append({"fresh": fresh, "module": m, "decide": m.decide_action})
        return m

    monkeypatch.setattr(R, "import_run_agent", fake_import)
    default_yaw = P.YAW
    _, preloaded, _, _ = R.load_pipe()  # what warm_app.py's @modal.enter does before any call
    assert R.main(["run.py", "--tasks", "GC005", "--lingbot-turn-cal", "--lingbot-player-hint", "--lingbot-fast-y"]) == 0
    assert R.main(["run.py", "--tasks", "GC005", "--lingbot-stateless"]) == 0
    assert R.main(["run.py", "--tasks", "GC005"]) == 0

    assert len(loads) == 1  # one pipe for three arms, loaded ahead of them
    assert all(getattr(i2v, n) is f for n, f in originals.items())  # loader patches undone after the load
    # fast-start flags are per call: arm 1's streamed y does not leak into arm 3
    assert R.FAST == R.FS.FastFlags()
    a1, a2, a3 = calls
    assert all(c["fresh"] for c in calls) and len({id(c["module"]) for c in calls}) == 3
    assert preloaded is a1["engine"].pipe is a2["engine"].pipe is a3["engine"].pipe
    assert a1["argv"] == a2["argv"] == a3["argv"] == ["run.py", "--tasks", "GC005"]  # flags stripped
    # turn-cal arm calibrated; the next arms start from the default rates again
    assert a1["yaw"] != default_yaw and a2["yaw"] == a3["yaw"] == default_yaw == P.YAW
    # session per arm, none for the stateless arm; flags re-read per call
    assert a1["engine"].session is not None and a2["engine"].session is None and a3["engine"].session is not None
    assert a1["engine"].session is not a3["engine"].session
    assert a1["engine"].session.stream_encode and not a3["engine"].session.stream_encode
    assert (R.STATELESS, R.TURN_CAL, R.PLAYER_HINT) == (False, False, False)
    assert R.STATS.totals["tasks"] == 1  # counters belong to the last arm only
    # run_task wrapped once per fresh module (prompts + flag stats), never stacked across arms
    for c in calls:
        assert c["module"].run_task is c["run_task"]
    assert a1["module"].decide_action is not a1["decide"]  # player hint wraps it on arm 1 only
    assert a2["module"].decide_action is a2["decide"] and a3["module"].decide_action is a3["decide"]
