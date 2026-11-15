"""CPU-only tests for --lingbot-if-settle (SettleBudget, key rewriting, wrapper, FlagStats, gen-arms)."""
from __future__ import annotations
import json, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np, pytest
from adapters.common import prompts
from adapters.lingbot_world2 import flag_stats as F, if_settle as IS, run as R

ROOT = Path(__file__).resolve().parents[1]
IF052, GC033 = {"task_id": "IF052", "category": "IF", "action": "w*8"}, {"task_id": "GC033", "category": "GC", "action": "←*4"}
IF033 = {"task_id": "IF033", "category": "IF", "action": "interact(grip handle) -> interact(pull drawer)"}
_segs = lambda t: [("W", 8)] if t.get("action") == "w*8" else ([("LEFT", 4)] if "←" in str(t.get("action")) else [("W", 80)])

def test_parse_configure_and_validation():
    flags, rest = R.configure(["run.py", "--tasks", "IF052"], {})
    assert flags["if_settle"] == IS.SettleConfig(False, 1.25, 80, 2) and rest == ["run.py", "--tasks", "IF052"]
    flags, rest = R.configure(["run.py", "--lingbot-if-settle", "--lingbot-if-settle-mult=1.5", "--seed", "1"], {})
    assert flags["if_settle"] == IS.SettleConfig(True, 1.5, 80, 2) and rest == ["run.py", "--seed", "1"]
    assert IS.parse(["run.py"], {"LINGBOT_IF_SETTLE": "1", "LINGBOT_IF_SETTLE_MULT": "1.1", "LINGBOT_IF_SETTLE_MIN_FRAMES": "64", "LINGBOT_IF_SETTLE_HOLD_CHUNKS": "0"})[0] == IS.SettleConfig(True, 1.1, 64, 0)
    for bad in (["--lingbot-if-settle-mult"], ["--lingbot-if-settle-mult", "0"], ["--lingbot-if-settle-mult=-0.5"],
                ["--lingbot-if-settle-mult=nan"], ["--lingbot-if-settle", "--lingbot-stateless"], ["--lingbot-if-settle", "--lingbot-if-horizon"]):
        with pytest.raises(SystemExit): R.configure(["run.py", *bad], {})
    with pytest.raises(SystemExit, match="session mode"): R.configure(["run.py", "--lingbot-if-settle"], {"LINGBOT_SESSION": "0"})
    with pytest.raises(SystemExit, match="both bound IF duration"): R.configure(["run.py"], {"LINGBOT_IF_SETTLE": "1", "LINGBOT_IF_HORIZON": "1"})

def test_settle_budget_rewriting_fallback_and_non_if():
    sb = IS.SettleBudget(IS.SettleConfig(True, 1.25, 80, 2), _segs)
    assert sb.reset(IF052, "IF052_full", 20) == 200 and sb.apply(["w"] * 100 + ["none"] * 5 + ["w"] * 125) == ["w"] * 100 + ["none"] * 5 + ["w"] * 100 + ["none"] * 25
    assert (sb.active_frames, sb.settled_frames) == (200, 25) and sb.reset(GC033, "GC033_full", 20) == 0 and sb.apply(["j"] * 300) == ["j"] * 300 and not sb.armed
    assert sb.reset(IF033, "IF033_full", 20) == 200
    if (data := ROOT / "data" / "if" / "data.json").is_file():
        ra, tasks = R.import_run_agent(), {t["task_id"]: t for t in json.loads(data.read_text())}
        assert IS.budget_frames(tasks["IF033"], ra.parse_segments) == 200 and IS.budget_frames(tasks["IF002"], ra.parse_segments) == 250

def test_closed_loop_chunks_engine_wiring_and_flag_stats(monkeypatch, tmp_path, capsys):
    import PIL.Image, imageio
    sb, stats = IS.SettleBudget(IS.SettleConfig(True, 1.25, 80, 2), _segs), F.FlagStats(False, "goal", False, False, if_settle=True)
    calls, step_keys, actions = [], [], []
    decide, eng = IS.wrap(lambda *a, **kw: calls.append(a[3]) or "W", sb), R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    eng.if_settle, eng._last_chunk, eng.args = sb, None, SimpleNamespace(fps=16, seed=0, action_frame_unit=20, max_total_frames=961)
    eng.session = SimpleNamespace(started=False, track=SimpleNamespace(translation_gain=1.0), chunk_id=0, reanchor_events=0,
                                  reset=lambda *a, **kw: setattr(eng.session, "started", True), step=lambda k, **kw: step_keys.append(k) or np.zeros((1, 2, 2, 3), np.uint8))
    monkeypatch.setattr(eng, "_calibrate", lambda *a: None); monkeypatch.setattr(R, "STATS", stats)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    monkeypatch.setattr(PIL.Image, "open", lambda p: PIL.Image.new("RGB", (4, 4))); monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None)
    def run_if(t, *_):
        monkeypatch.setitem(prompts._current, "task", t)
        for idx in range(12):
            if (actions.append(d := decide(t, None, actions, idx, 30, eng.args)) or d) == "END": break
            eng._generate_session("x.jpg", "goal", "w-33", tmp_path, f"IF052_chunk_{idx + 1:02d}", 33)
        (p := tmp_path / "IF052" / "IF052_result.json").parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps({"task_id": "IF052", "success": True}))
        return {"task_id": "IF052", "success": True}
    stats.install(ra := SimpleNamespace(run_task=run_if)); res = ra.run_task(IF052, eng, tmp_path, eng.args)
    assert actions == ["W"] * 8 + ["END"] and calls == list(range(8)) and step_keys[6] == ["w"] * 12 + ["none"] * 20 and step_keys[7] == ["none"] * 32
    assert "[lingbot] IF settle: IF052 settled for 52 frames (budget 200) -> END" in capsys.readouterr().out
    assert (res["lingbot_flags"]["if_settle"], res["lingbot_flags"]["if_settle_budget"], res["lingbot_flags"]["if_settle_frames"]) == ("on", 200, 52)
    assert json.loads((tmp_path / "IF052" / "IF052_result.json").read_text())["lingbot_flags"]["if_settle_frames"] == 52
    stats.new_task(); monkeypatch.setitem(prompts._current, "task", GC033); eng._generate_session("x.jpg", "goal", "j-33", tmp_path, "GC033_chunk_01", 33)
    assert (sg := stats.finish_task("GC033"))["if_settle"] == "skip" and (sg["if_settle_budget"], sg["if_settle_frames"]) == (0, 0) and stats.total_line().endswith("if_settle_tasks=1 if_settle_frames=52")
    sb0 = IS.SettleBudget(IS.SettleConfig(True, 1.25, 80, 0), _segs)
    assert sb0.reset(IF052) == 200 and len(sb0.apply(["w"] * 260)) == 260 and IS.wrap(lambda *a, **kw: "W", sb0)(IF052, None, [], 8, 30, None) == "W"

def test_default_off_and_gen_arms_isolation(monkeypatch, capsys):
    for k in [k for k in R.os.environ if k.startswith("LINGBOT_")]: monkeypatch.delenv(k)
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test"); monkeypatch.setattr(R.agent_api, "finish", lambda *a: None)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda t, *a: {"task_id": t["task_id"], "success": False}, parse_segments=_segs, decide_action=lambda *a, **k: "W", main=lambda: 0))
    assert R.main(["run.py", "--lingbot-if-settle"]) == 0 and R.IF_SETTLE.enabled and R.SETTLE is not None
    assert R.main(["run.py"]) == 0 and not R.IF_SETTLE.enabled and R.SETTLE is None and not R.STATS.if_settle
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("[lingbot] flags total")]
    assert "if_settle_tasks=0 if_settle_frames=0" in lines[0] and "if_settle" not in lines[1]
