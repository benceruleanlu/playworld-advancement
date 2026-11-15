"""Proposal batch 2 flags under pwa gen-arms: several main() calls in one process, one flag per arm, plus
no-flag arms before and after. No state, wrapper or counter may leak between arms, the no-flag flags lines
must keep main's format, and with every flag on the player prompt must compose in the documented order.
Mocked upstream and pipe; no GPU, no API."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.common import agent_api, prompts
from adapters.lingbot_world2 import if_camera as IC
from adapters.lingbot_world2 import if_repeat as IR
from adapters.lingbot_world2 import run as R

IF_TASK = {"task_id": "IF002", "category": "IF", "perspective": "third person", "prompt": "Walk to the bench."}
OE_TASK = {"task_id": "OE001", "sub_category": "insight evolution", "image_caption": "Workers lift a frame.",
           "prompt": "wait and observe"}
# what main prints for these two tasks with no flag (the format every no-flag arm must keep)
BASE_LINE = "[lingbot] flags task={} turn_cal=0 caption=off reanchor=off reanchor_events=0 player_hint=off player_hints=0"
BASE_TOTAL = ("[lingbot] flags total tasks=2 turn_cal=0 caption_used=0 caption_fallback=0 "
              "reanchor_events=0 player_hints=0")
MODE_PARTS = ("IF horizon", "IF camera hint", "player history endpoints", "insight director", "IF repeat check",
              "IF slow translation")


@pytest.fixture
def harness(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra: "test")
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), SimpleNamespace(),
                                                              Path("weights"), False))
    arms = []

    def fresh(fresh=False):
        """A new run_agent stand-in per call, like a fresh upstream import."""
        m = SimpleNamespace()
        rec = {"module": m, "player": [], "model": [], "actions": []}

        def decide_action(task, frame, recent_actions, chunk_idx, num_chunks, args, *rest, **kw):
            m.extract_video_frames_with_timestamps_b64("old.mp4", 4)  # an older chunk, as upstream samples it
            rec["player"].append((task["prompt"], num_chunks))
            return "W"

        def run_task(task, engine, output_dir, args):
            engine._generate_session = engine._generate_stateless = lambda *a: rec["model"].append(a[1]) or "v.mp4"
            engine.generate("image.jpg", task["prompt"], "w-33", output_dir, f"{task['task_id']}_chunk_01", 33)
            if task["task_id"].startswith("IF"):
                for chunk in (3, 20):  # inside the IF002 horizon budget (10), then past it
                    rec["actions"].append(m.decide_action(task, None, ["W"] * 4, chunk, 30, args))
            return {"task_id": task["task_id"], "success": False}

        def main():
            args = SimpleNamespace(seed=42, fps=16, max_total_frames=961, action_frame_unit=20, chunk_frames=33)
            engine = m.SanaWMEngine(args)
            for task in (IF_TASK, OE_TASK):
                m.run_task(dict(task), engine, "out", args)
            return 0

        m.decide_action, m.run_task, m.main = decide_action, run_task, main
        m.extract_video_frames_with_timestamps_b64 = lambda path, n=8: [{"b64": str(i)} for i in range(n)]
        m.parse_segments = lambda task: [("w", 8)]
        m.to_sana_key = lambda a: {"W": "w", "LEFT": "j", "RIGHT": "l", "WAIT": "none"}.get(a, "none")
        rec.update(decide=decide_action, sampler=m.extract_video_frames_with_timestamps_b64)
        arms.append(rec)
        return m

    monkeypatch.setattr(R, "import_run_agent", fresh)
    return arms


def _run(capsys, *flags):
    assert R.main(["run.py", "--tasks", "IF002,OE001", *flags]) == 0
    out = capsys.readouterr().out.splitlines()
    return {"lines": [ln for ln in out if ln.startswith("[lingbot] flags task=")],
            "total": [ln for ln in out if ln.startswith("[lingbot] flags total")],
            "mode": [ln for ln in out if ln.startswith("[lingbot] mode:")],
            "stats": R.STATS}


def test_one_flag_per_arm_no_leaks_and_no_flag_lines_unchanged(harness, capsys):
    flags = ("--lingbot-if-horizon", "--lingbot-if-camera-hint", "--lingbot-player-history-endpoints",
             "--lingbot-insight-director", "--lingbot-if-repeat-check", "--lingbot-if-slow-translation")
    out = [_run(capsys)] + [_run(capsys, f) for f in flags] + [_run(capsys)]
    assert len(harness) == len(out) and len({id(a["module"]) for a in harness}) == len(out)
    base, last = out[0], out[-1]

    # the no-flag arms: main's exact lines, upstream functions untouched, goal and model prompt unchanged
    for arm, rec in ((base, harness[0]), (last, harness[-1])):
        assert arm["lines"] == [BASE_LINE.format("IF002"), BASE_LINE.format("OE001")]
        assert arm["total"] == [BASE_TOTAL]
        assert not any(p in arm["mode"][0] for p in MODE_PARTS)
        assert rec["module"].decide_action is rec["decide"]
        assert rec["module"].extract_video_frames_with_timestamps_b64 is rec["sampler"]
        assert rec["player"] == [(IF_TASK["prompt"], 30)] * 2 and rec["actions"] == ["W", "W"]
        assert rec["model"] == [IF_TASK["prompt"], OE_TASK["prompt"]]
    assert base["mode"] == last["mode"]

    # each flag arm: only its own fields, its own mode-line part, and its own effect
    own = {1: ("if_horizon",), 2: ("if_camera",), 3: ("history_endpoints", "player_frames_removed"),
           4: ("insight_director",), 5: ("if_repeat",), 6: ("if_slow", "if_translation_frames")}
    for i, fields in own.items():
        line = out[i]["lines"][0] + " " + out[i]["total"][0]
        assert all(f in line for f in fields), (i, line)
        others = [f for j, fs in own.items() if j != i for f in fs]
        assert not any(f in line for f in others), (i, line)
        assert [p for p in MODE_PARTS if p in out[i]["mode"][0]] == [MODE_PARTS[i - 1]]
        assert out[i]["lines"][0].startswith(BASE_LINE.format("IF002") + " ")  # main's fields first, unchanged
    horizon, camera, history, director, repeat, slow = (harness[i] for i in range(1, 7))
    assert horizon["actions"] == ["W", "END"] and horizon["player"] == [(IF_TASK["prompt"], 10)]
    assert "if_horizon=on if_horizon_chunks=10 if_horizon_ends=1" in out[1]["lines"][0]
    assert "if_horizon=skip if_horizon_chunks=0 if_horizon_ends=0" in out[1]["lines"][1]
    assert camera["player"][0][0] == f"{IF_TASK['prompt']}\n{IC.REMINDER}" and "if_camera_hints=2" in out[2]["lines"][0]
    assert "player_frames_removed=4" in out[3]["lines"][0]  # two decisions, 4 -> 2 samples each
    assert director["model"] == [IF_TASK["prompt"], f"Workers lift a frame.\n{prompts.INSIGHT_DIRECTION}"]
    assert "caption=director" in out[4]["lines"][1] and "insight_director_prompts=1" in out[4]["lines"][1]
    assert "caption=off" in out[4]["lines"][0] and "insight_director_prompts=0" in out[4]["lines"][0]
    assert repeat["player"][0][0] == f"{IF_TASK['prompt']}\n{IR.REMINDER}" and "if_repeat_checks=2" in out[5]["lines"][0]
    assert slow["player"] == [(IF_TASK["prompt"], 30)] * 2  # engine-only flag (session pose track; unit-tested)
    assert "if_slow=on if_translation_frames=0" in out[6]["lines"][0]
    # counters belong to the last arm only; flags re-read per call
    assert R.STATS.totals["tasks"] == 2 and not R.IF_HORIZON
    assert not any(getattr(R.STATS, a) for a in ("if_horizon", "if_camera", "history_endpoints",
                                                 "insight_director", "if_repeat", "if_slow"))


def test_all_flags_compose_in_the_documented_order(harness, capsys):
    arm = _run(capsys, "--lingbot-turn-cal", "--lingbot-player-hint", "--lingbot-if-horizon",
               "--lingbot-if-camera-hint", "--lingbot-if-repeat-check", "--lingbot-if-slow-translation",
               "--lingbot-player-history-endpoints", "--lingbot-insight-director", "--lingbot-gc-completion-hint",
               "--lingbot-return-stop")
    rec = harness[0]
    # one player call: the horizon END at chunk 20 never reaches the hints or the player
    assert rec["actions"] == ["W", "END"] and len(rec["player"]) == 1
    sent, cap = rec["player"][0]
    assert cap == 10
    goal, camera, repeat, hint = sent.split("\n")
    assert (goal, camera, repeat) == (IF_TASK["prompt"], IC.REMINDER, IR.REMINDER)
    assert hint.startswith("Controls:") and "0.5 of a normal step" in hint  # player hint last, IF gain applied
    line = arm["lines"][0]
    for field in ("player_hints=1", "if_camera_hints=1", "if_repeat_checks=1", "player_frames_removed=2",
                  "gc_completion_hints=0", "return_stop=skip return_stops=0", "if_horizon_ends=1"):
        assert field in line, (field, line)
    assert all(p in arm["mode"][0] for p in MODE_PARTS)
