"""Per-task flag counters and the `[lingbot] flags` summary line. No GPU, no API calls."""
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.lingbot_world2 import flag_stats as F  # noqa: E402
from adapters.lingbot_world2 import player_hint as H  # noqa: E402

LINE = re.compile(r"^\[lingbot\] flags task=(\S+) turn_cal=([01]) caption=(off|used|fallback|none) "
                  r"reanchor=(off|on|skip) reanchor_events=(\d+) player_hint=(off|on) player_hints=(\d+)$")


def _fake_upstream(tmp_path, calls_per_task=3):
    """run_agent stand-in: run_task writes <tid>_result.json like upstream and returns the result."""
    def run_task(task, engine, output_dir, args):
        tid = task["task_id"]
        d = Path(output_dir) / tid
        d.mkdir(parents=True, exist_ok=True)
        for _ in range(calls_per_task):
            engine(task)
        res = {"task_id": tid, "success": task.get("ok", True)}
        (d / f"{tid}_result.json").write_text(json.dumps(res))
        return res
    return SimpleNamespace(run_task=run_task)


def test_all_off_line(capsys, tmp_path):
    st = F.FlagStats(False, "goal", False, False)
    ra = _fake_upstream(tmp_path)
    st.install(ra)
    res = ra.run_task({"task_id": "GC005"}, lambda t: None, tmp_path, None)
    line = capsys.readouterr().out.strip()
    assert line == ("[lingbot] flags task=GC005 turn_cal=0 caption=off reanchor=off reanchor_events=0 "
                    "player_hint=off player_hints=0")
    assert LINE.match(line)
    assert res["lingbot_flags"]["caption"] == "off"
    assert json.loads((tmp_path / "GC005" / "GC005_result.json").read_text())["lingbot_flags"]["turn_cal"] == 0


def test_counters_reset_per_task_and_total(capsys, tmp_path):
    st = F.FlagStats(True, "auto", True, True)
    ra = _fake_upstream(tmp_path)
    st.install(ra)

    def engine(task):  # what run.py's hooks do during one generate() call
        st.caption(bool(task.get("image_caption")))
        if task["task_id"].startswith("GC"):
            st.armed()
            st.reanchored(1)
        st.hint()

    ra.run_task({"task_id": "GC033", "image_caption": "a room"}, engine, tmp_path, None)
    ra.run_task({"task_id": "IF052", "image_caption": ""}, engine, tmp_path, None)
    ra.run_task({"task_id": "OE018", "image_caption": "tea", "ok": False}, engine, tmp_path, None)
    print(st.total_line())
    lines = capsys.readouterr().out.strip().splitlines()
    got = [LINE.match(x).groups() for x in lines[:3]]
    assert got == [("GC033", "1", "used", "on", "3", "on", "3"),
                   ("IF052", "1", "fallback", "skip", "0", "on", "3"),
                   ("OE018", "1", "used", "skip", "0", "on", "3")]
    assert lines[3] == ("[lingbot] flags total tasks=3 turn_cal=1 caption_used=2 caption_fallback=1 "
                        "reanchor_events=3 player_hints=9")
    # a failed rollout keeps upstream's result file as it is
    assert "lingbot_flags" not in json.loads((tmp_path / "OE018" / "OE018_result.json").read_text())


def test_summary_line_printed_when_run_task_raises(capsys, tmp_path):
    st = F.FlagStats(False, "caption", False, False)
    st.install(ra := SimpleNamespace(run_task=lambda *a: 1 / 0))
    try:
        ra.run_task({"task_id": "GC001"}, None, tmp_path, None)
    except ZeroDivisionError:
        pass
    assert "task=GC001 turn_cal=0 caption=none" in capsys.readouterr().out


def test_player_hint_counts_hints_sent_only():
    n = []
    decide = H.wrap(lambda *a, **kw: "WAIT", {"LEFT": "j", "WAIT": "none"}.get, session=True, turn_cal=False,
                    on_hint=lambda: n.append(1))
    args = SimpleNamespace(chunk_frames=33, action_frame_unit=20)
    decide({"prompt": "g"}, None, ["LEFT"], 1, 30, args)
    decide({"prompt": "g"}, None, [], 0, 30, args, stationary_only=True)  # wait-only insight: no hint
    assert len(n) == 1


def test_run_py_wiring():
    src = (ROOT / "adapters" / "lingbot_world2" / "run.py").read_text()
    assert "STATS.install(run_agent)" in src and "print(STATS.total_line()" in src
    assert "STATS.caption(prompt != goal)" in src and "on_hint=STATS.hint" in src
    assert "STATS.reanchored(self.session.reanchor_events - anchored)" in src
    assert '", player hint on" if PLAYER_HINT' in src  # mode line lists every active flag
