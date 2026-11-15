"""Scripted player (--lingbot-scripted-player): fixed chunk scripts from the dataset action, no LLM call.

Uses upstream run_agent's own helpers and closed loop (third_party/PlayWorld) with the real runner main();
the pipe, the session step and video I/O are mocked. No GPU, no API."""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.common.upstream import SANA_WM_DIR, import_run_agent  # noqa: E402
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import poses as P  # noqa: E402
from adapters.lingbot_world2 import run as R  # noqa: E402
from adapters.lingbot_world2 import scripted_player as SP  # noqa: E402

pytestmark = pytest.mark.skipif(not (SANA_WM_DIR / "run_agent.py").is_file(), reason="PlayWorld submodule missing")
FAMILY = {"GC": "gc", "IF": "if", "OE": "outsight"}
DEV = ("GC033", "GC036", "IF031", "OE047")
ARGS = SimpleNamespace(chunk_frames=33, tail_frames=50, action_frame_unit=20)
TOKEN = {"←": "LEFT", "→": "RIGHT", "↑": "UP", "↓": "DOWN", "u": "UP", "j": "DOWN", "w": "W", "s": "S", "a": "A",
         "d": "D", "wait": "WAIT"}


def _task(tid):
    path = ROOT / "data" / FAMILY[tid[:2]] / "data.json"
    if not path.is_file():
        pytest.skip(f"{path} not downloaded")
    rec = next((t for t in json.loads(path.read_text()) if t["task_id"] == tid), None)
    if rec is None:
        pytest.skip(f"{tid} not in {path}")
    return rec


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith(("LINGBOT_", "PLAYER_")):
            monkeypatch.delenv(key)
    P.reset()


def _runs(seq):
    out = []
    for a in seq:
        if out and out[-1][0] == a:
            out[-1][1] += 1
        else:
            out.append([a, 1])
    return [tuple(x) for x in out]


def _dataset_net(action):
    """Independent of upstream's parser: net tokens per axis of the `<tok>*<n>` segments in the dataset string."""
    out = {}
    for m in re.finditer(r"([←→↑↓]|[a-z]+)\s*\*\s*(\d+)", action):
        ax, sign = SP.AXIS[TOKEN[m.group(1)]]
        out[ax] = out.get(ax, 0.0) + sign * int(m.group(2))
    return out


@pytest.mark.parametrize("tid", DEV + ("GC005", "GC047", "IF041"))
def test_script_net_matches_the_dataset_within_half_a_chunk(tid):
    """Each axis ends within half a chunk of the dataset's net displacement (2 tokens per rotation chunk,
    32 / 20 = 1.6 per translation or WAIT chunk), and the order of keys follows the dataset."""
    ra = import_run_agent(fresh=True)
    task = _task(tid)
    chunks = SP.script(task, ra.parse_segments, ra.VALID_ACTIONS, move=SP.move_units(ARGS))
    want = _dataset_net(task["action"])
    got = {}
    for a in chunks:
        ax, sign = SP.AXIS[a]
        got[ax] = got.get(ax, 0.0) + sign * (2.0 if ax in SP.ROT_AXES else 1.6)
    for ax, tokens in want.items():
        if ax == "wait":
            continue
        unit = 2.0 if ax in SP.ROT_AXES else 1.6
        assert abs(got.get(ax, 0.0) - tokens) <= unit / 2 + 1e-9, (ax, got, want)
    keys = [TOKEN[m.group(1)] for m in re.finditer(r"([←→↑↓]|[a-z]+)\s*\*\s*\d+", task["action"])]
    assert [a for a, _ in _runs(chunks)] == [a for a, _ in _runs(keys)]
    # same task -> same plan, every call (arms differ only in their model-side flags)
    assert SP.plan(task, ARGS, ra.parse_segments, ra.VALID_ACTIONS) == \
        SP.plan(dict(task), ARGS, ra.parse_segments, ra.VALID_ACTIONS)


def test_gc005_loop_closes():
    """Regression: rounding each segment on its own left GC005's lateral loop one chunk right of the start."""
    ra = import_run_agent(fresh=True)
    chunks = SP.script(_task("GC005"), ra.parse_segments, ra.VALID_ACTIONS)
    assert chunks.count("D") == chunks.count("A") and chunks.count("W") == chunks.count("S")


def test_known_dev_scripts():
    ra = import_run_agent(fresh=True)
    want = {"GC033": ["LEFT"] * 2 + ["RIGHT"] * 2,
            "GC036": ["LEFT"] * 2 + ["RIGHT"] * 4 + ["LEFT"] * 2,
            "IF031": ["W"] * 6,                                       # w*10 = 200 frames ~ 6 x 32
            "OE047": ["RIGHT"] * 2 + ["LEFT"] * 2 + ["UP"]}
    for tid, chunks in want.items():
        assert SP.script(_task(tid), ra.parse_segments, ra.VALID_ACTIONS) == chunks
    assert SP.plan(_task("GC033"), ARGS, ra.parse_segments, ra.VALID_ACTIONS) == \
        want["GC033"] + ["WAIT", "WAIT"]  # ceil(50 / 32) tail chunks


def test_wrapper_never_calls_the_player_and_ends(capsys):
    ra = import_run_agent(fresh=True)
    asked, events = [], []
    decide = SP.wrap(lambda *a, **k: asked.append(a) or "W", ra.parse_segments, ra.VALID_ACTIONS,
                     on_event=lambda kind, n: events.append(kind))
    task = {"task_id": "GC033", "action": "←*4 -> →*4"}
    got = [decide(task, None, [], i, 30, ARGS, dataset_action="W") for i in range(7)]
    assert got == ["LEFT", "LEFT", "RIGHT", "RIGHT", "WAIT", "WAIT", "END"] and not asked
    assert events.count("chunk") == 6 and events[-1] == "end"
    assert decide(task, None, [], 0, 30, ARGS, stationary_only=True) == "WAIT" and not asked
    with pytest.raises(RuntimeError):
        decide(task, None, [], 0, 30, ARGS, allow_next=True)
    assert "scripted player: GC033 script done after 6 chunks -> END" in capsys.readouterr().out


def test_env_overrides_tail_and_units(monkeypatch):
    ra = import_run_agent(fresh=True)
    monkeypatch.setenv("LINGBOT_SCRIPTED_TAIL", "0")
    monkeypatch.setenv("LINGBOT_CHUNK_UNITS", "4")
    P.reset()
    assert SP.plan({"action": "←*4 -> →*8"}, ARGS, ra.parse_segments, ra.VALID_ACTIONS) == ["LEFT", "RIGHT", "RIGHT"]
    monkeypatch.setenv("LINGBOT_CHUNK_UNITS", "1.5")                    # a float unit is used as is, not rounded
    P.reset()
    assert SP.plan({"action": "←*3"}, ARGS, ra.parse_segments, ra.VALID_ACTIONS) == ["LEFT", "LEFT"]


@pytest.mark.parametrize("env", [{"LINGBOT_SCRIPTED_TAIL": "two"}, {"LINGBOT_SCRIPTED_TAIL": "-1"},
                                 {"LINGBOT_CHUNK_UNITS": "0"}, {"LINGBOT_CHUNK_UNITS": "x"}])
def test_bad_env_fails_at_configure(env):
    with pytest.raises(SystemExit):
        R.configure(["run.py", "--lingbot-scripted-player", "--action-source", "agent"], env)
    R.configure(["run.py", "--action-source", "agent"], env)            # flag off: not read


def test_configure_flag_env_and_action_source():
    flags, argv = R.configure(["run.py", "--lingbot-scripted-player", "--action-source", "agent"], {})
    assert flags["scripted"] and "--lingbot-scripted-player" not in argv
    assert R.configure(["run.py", "--action-source", "agent"], {"LINGBOT_SCRIPTED_PLAYER": "1"})[0]["scripted"]
    assert R.configure(["run.py"], {"LINGBOT_SCRIPTED_PLAYER": "1"})[0]["scripted"]  # upstream default: refined
    assert not R.configure(["run.py", "--action-source", "dataset"], {})[0]["scripted"]
    for src in (["--action-source", "dataset"], ["--action-source=dataset_then_agent"]):
        with pytest.raises(SystemExit):
            R.configure(["run.py", "--lingbot-scripted-player", *src], {})


def test_flag_stats_fields_only_when_on(capsys):
    off = F.FlagStats(False, "goal", False, False)
    assert "scripted" not in off.summary("GC033") and "scripted" not in off.total_line()
    on = F.FlagStats(False, "goal", False, False, scripted=True)
    assert on.summary("OE001")["scripted"] == "skip"
    for kind in ("plan", "chunk", "plan", "chunk", "plan", "end"):
        on.scripted_event(kind, 2)
    s = on.finish_task("GC033")
    assert (s["scripted"], s["scripted_planned"], s["scripted_chunks"], s["scripted_end"]) == ("on", 2, 2, 1)
    assert capsys.readouterr().out.strip().endswith("scripted=on scripted_planned=2 scripted_chunks=2 scripted_end=1")
    assert on.total_line().endswith(" scripted=on scripted_chunks=2 scripted_ends=1")


# ---------------------------------------------------------------- end to end: real upstream closed loop
@pytest.fixture
def upstream(monkeypatch, tmp_path):
    """R.main on the real upstream run_agent: real argparse, closed loop, decide_action and agent counters.
    Mocked: the pipe, the session step (records each generate() call), video I/O and the LLM request."""
    from PIL import Image
    import numpy as np

    tasks = []
    for tid in ("GC033", "IF031"):
        rec = dict(_task(tid))
        img = tmp_path / f"{tid}.jpg"
        Image.new("RGB", (8, 8)).save(img)
        rec["image_path"] = str(img)
        tasks.append(rec)
    mapping = tmp_path / "tasks.json"
    mapping.write_text(json.dumps(tasks))
    rec = {"calls": [], "llm": []}
    monkeypatch.setenv("PLAYER_API_PROVIDER", "upstream")
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), SimpleNamespace(),
                                                              Path("weights"), False))

    def session(self, image_path, prompt, action, output_dir, name, num_frames):
        rec["calls"].append((name, action, prompt))
        out = Path(output_dir) / f"{name}.mp4"
        out.write_bytes(b"")
        return out

    monkeypatch.setattr(R.LingBotWorld2Engine, "_generate_session", session)
    real_import = R.import_run_agent

    def fresh(fresh=False):
        m = real_import(fresh=True)
        m.request_agent_action = lambda *a, **k: rec["llm"].append(a) or "W"
        m.read_video = lambda path: [np.zeros((8, 8, 3), np.uint8)] * 3
        m.save_video = lambda frames, path, fps: Path(path).write_bytes(b"")
        m.extract_video_frames_with_timestamps_b64 = lambda path, n=8: []
        return m

    monkeypatch.setattr(R, "import_run_agent", fresh)

    def run(capsys, *flags, source="agent"):
        rec["calls"].clear()
        rec["llm"].clear()
        out_dir = tmp_path / f"out{len(list(tmp_path.glob('out*')))}"
        assert R.main(["run.py", "--mapping-json", str(mapping), "--output-dir", str(out_dir),
                       "--action-source", source, "--num-chunks", "8", *flags]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert not any("fatal:" in ln for ln in lines), [ln for ln in lines if "fatal:" in ln]
        return {"lines": lines, "calls": list(rec["calls"]), "llm": list(rec["llm"]), "out": out_dir}

    return run


def test_end_to_end_no_llm_and_chunk_names_reach_the_engine(upstream, capsys):
    r = upstream(capsys, "--lingbot-scripted-player", "--lingbot-caption-prompt", "--lingbot-gc-chunk-director")
    assert r["llm"] == []
    gc = [(n, a) for n, a, _ in r["calls"] if n.startswith("GC033")]
    assert gc == [(f"GC033_chunk_{i:02d}", f"{k}-33") for i, k in zip(range(1, 7), ["j", "j", "l", "l", "none", "none"])]
    ifc = [n for n, _, _ in r["calls"] if n.startswith("IF031")]
    assert ifc == [f"IF031_chunk_{i:02d}" for i in range(1, 9)]           # 6 W chunks + 2 WAIT = the 8-chunk cap
    # chunk-level engine flag fired: GC chunk director wrote this chunk's camera command into the prompt
    gc_prompts = [p for n, _, p in r["calls"] if n.startswith("GC033")]
    assert "the camera pans left" in gc_prompts[0] and "remains stationary" in gc_prompts[-1]
    flags = [ln for ln in r["lines"] if ln.startswith("[lingbot] flags task=")]
    assert flags[0].endswith("gc_director=on gc_director_chunks=6 gc_director_updates=0 "
                             "scripted=on scripted_planned=6 scripted_chunks=6 scripted_end=1")
    assert flags[1].endswith("scripted=on scripted_planned=8 scripted_chunks=8 scripted_end=0")
    assert "[agent] player total tasks=2 decisions=0 calls=0 empty=0 retries=0 errors=0 fallbacks=0" in r["lines"]
    assert not any("[agent] fallback=" in ln or "[agent] error attempt" in ln for ln in r["lines"])
    assert any(ln.startswith("[lingbot] mode:") and "scripted player on (2 tokens per chunk, angles uncalibrated: turn-cal off)" in ln
               for ln in r["lines"])
    res = json.loads((r["out"] / "GC033" / "GC033_result.json").read_text())
    assert [a["action"] for a in res["actions"]] == ["LEFT", "LEFT", "RIGHT", "RIGHT", "WAIT", "WAIT", "END"]


def test_harness_cap_cuts_the_script(upstream, capsys):
    r = upstream(capsys, "--lingbot-scripted-player", "--num-chunks", "3")
    assert [n for n, _, _ in r["calls"] if n.startswith("GC033")] == [f"GC033_chunk_{i:02d}" for i in (1, 2, 3)]
    flag = next(ln for ln in r["lines"] if ln.startswith("[lingbot] flags task=GC033"))
    assert flag.endswith("scripted=on scripted_planned=6 scripted_chunks=3 scripted_end=0")


def test_player_side_flags_are_not_reached(upstream, capsys):
    r = upstream(capsys, "--lingbot-scripted-player", "--lingbot-player-hint", "--lingbot-if-horizon",
                 "--lingbot-player-history-endpoints")
    assert r["llm"] == []
    assert any("not reached: player hint, IF horizon, player history endpoints" in ln for ln in r["lines"])
    flag = next(ln for ln in r["lines"] if ln.startswith("[lingbot] flags task=IF031"))
    assert "player_hints=0" in flag and "if_horizon=skip" in flag


def test_no_flag_output_is_byte_identical(upstream, capsys):
    """Without the flag nothing changes: same engine calls and the same log lines (paths aside) before and
    after a scripted arm, and the LLM player is asked as upstream does."""
    def norm(r):
        return [ln.replace(str(r["out"]), "OUT") for ln in r["lines"]]

    a = upstream(capsys)
    upstream(capsys, "--lingbot-scripted-player")
    b = upstream(capsys)
    assert norm(a) == norm(b) and a["calls"] == b["calls"]
    assert len(a["llm"]) == 16                                             # 8 chunks x 2 tasks, the stand-in says W
    assert not any("scripted" in ln for ln in a["lines"])
