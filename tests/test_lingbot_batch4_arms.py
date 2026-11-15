"""Proposal batch 4 flags (weight-mod, attention window, IF identity cue, measured turn) under pwa gen-arms:
several main() calls in one process, one flag per arm, with no-flag and caption-only arms before and after. No
state, counter, prompt, DiT wrapper or KV window may leak between arms, and the no-flag lines and model prompts
must stay byte-identical. Mocked upstream and pipe; no GPU, no API. The flags' own effects are unit-tested in
test_lingbot_weight_mod*.py, test_lingbot_window.py, test_if_identity_cue.py and test_lingbot_measured_turn.py."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.common import agent_api
from adapters.lingbot_world2 import if_identity as IFI
from adapters.lingbot_world2 import run as R
from tests.test_lingbot_weight_mod import _dit

GC_TASK = {"task_id": "GC001", "category": "GC", "image_caption": "A quiet street.", "prompt": "Turn right."}
IF_TASK = {"task_id": "IF002", "category": "IF", "perspective": "third person", "image_caption": "A dog.",
           "prompt": "The dog walks to the bench."}
BASE_LINE = "[lingbot] flags task={} turn_cal=0 caption={} reanchor=off reanchor_events=0 player_hint=off player_hints=0"
MODE_PARTS = ("weight-mod on", "window local_attn", "IF identity cue on", "measured turn on")
FIELDS = ("weight_mod", "window=", "if_identity", "measured_")


class _Attn:
    def __init__(self):
        self.local_attn_size, self.sink_size = 18, 6


def _pipe():
    model = _dit(3, n=2)
    attn = [_Attn(), _Attn()]
    model.modules = lambda: [model, *attn]
    return SimpleNamespace(model=model, attn=attn, local_attn_size=18, sink_size=6)


@pytest.fixture
def harness(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    pipe = _pipe()
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), pipe,
                                                              Path("weights"), False))
    arms = []

    def fresh(fresh=False):
        m = SimpleNamespace()
        rec = {"model": [], "pipe": pipe}

        def run_task(task, engine, output_dir, args):
            engine._generate_session = engine._generate_stateless = lambda *a: rec["model"].append(a[1]) or "v.mp4"
            for chunk, action in ((1, "l-33"), (2, "w-33")):
                engine.generate("image.jpg", task["prompt"], action, output_dir,
                                f"{task['task_id']}_chunk_{chunk:02d}", 33)
            return {"task_id": task["task_id"], "success": False}

        def main():
            args = SimpleNamespace(seed=42, fps=16, max_total_frames=961, action_frame_unit=20, chunk_frames=33)
            engine = m.SanaWMEngine(args)
            rec["window"] = (pipe.local_attn_size, pipe.sink_size, [(a.local_attn_size, a.sink_size) for a in pipe.attn])
            rec["weight_mod"] = engine.weight_mod is not None
            rec["attached"] = hasattr(pipe.model, "_weight_mod")
            for task in (GC_TASK, IF_TASK):
                m.run_task(dict(task), engine, "out", args)
            return 0

        m.run_task, m.main = run_task, main
        m.decide_action = lambda *a, **k: "W"
        m.extract_video_frames_with_timestamps_b64 = lambda path, n=8: []
        m.parse_segments = lambda task: [("w", 8)]
        m.to_sana_key = lambda a: "none"
        rec["module"] = m
        arms.append(rec)
        return m

    monkeypatch.setattr(R, "import_run_agent", fresh)
    return arms


def _run(capsys, *flags):
    assert R.main(["run.py", "--tasks", "GC001,IF002", *flags]) == 0
    out = capsys.readouterr().out.splitlines()
    return {"lines": [ln for ln in out if ln.startswith("[lingbot] flags task=")],
            "total": [ln for ln in out if ln.startswith("[lingbot] flags total")],
            "mode": [ln for ln in out if ln.startswith("[lingbot] mode:")][0],
            "window": [ln for ln in out if ln.startswith("[lingbot] window:")]}


def test_one_flag_per_arm_no_leaks_and_no_flag_arms_unchanged(harness, capsys):
    cap = "--lingbot-caption-prompt"
    plan = [(), (cap,), ("--lingbot-weight-mod",), ("--lingbot-sink-size", "1"),
            (cap, "--lingbot-if-identity-cue"), ("--lingbot-measured-turn",), (cap,), ()]
    out = [_run(capsys, *flags) for flags in plan]
    assert len(harness) == len(plan) and len({id(a["module"]) for a in harness}) == len(plan)
    bare, caption = (out[0], harness[0]), (out[1], harness[1])
    default_window = (18, 6, [(18, 6), (18, 6)])

    # no-flag and caption-only arms: main's exact lines and prompts, identical before and after the flag arms
    for (arm, rec), (again, rec2) in ((bare, (out[7], harness[7])), (caption, (out[6], harness[6]))):
        assert arm["lines"] == again["lines"] and arm["total"] == again["total"] and arm["mode"] == again["mode"]
        assert rec["model"] == rec2["model"]
        assert not any(f in " ".join(arm["lines"] + arm["total"]) for f in FIELDS)
        assert not any(p in arm["mode"] for p in MODE_PARTS) and not arm["window"]
        assert rec2["window"] == default_window and not rec2["weight_mod"] and not rec2["attached"]
    assert bare[0]["lines"] == [BASE_LINE.format("GC001", "off"), BASE_LINE.format("IF002", "off")]
    assert bare[1]["model"] == [GC_TASK["prompt"]] * 2 + [IF_TASK["prompt"]] * 2
    assert caption[0]["lines"] == [BASE_LINE.format("GC001", "used"), BASE_LINE.format("IF002", "used")]
    gc_cap, if_cap = caption[1]["model"][0], caption[1]["model"][2]

    # each flag arm: only its own fields and mode part, main's fields first and unchanged
    for i, field in ((2, "weight_mod"), (3, "window="), (4, "if_identity"), (5, "measured_")):
        control = caption[0] if i == 4 else bare[0]
        text = " ".join(out[i]["lines"] + out[i]["total"])
        assert field in text and not any(f in text for f in FIELDS if f != field), (i, text)
        assert [p for p in MODE_PARTS if p in out[i]["mode"]] == [MODE_PARTS[i - 2]]
        for line, base in zip(out[i]["lines"], control["lines"]):
            assert line.startswith(base + " "), (line, base)

    # weight-mod: wrappers attached only in its arm, scales printed, prompts unchanged
    assert harness[2]["weight_mod"] and harness[2]["attached"] and not harness[3]["attached"]
    assert "weight-mod on (static 0.0, 3p 0.85, move 1.0, text 1.0, text move 1.0)" in out[2]["mode"]
    assert "weight_mod=on weight_mod_steps=0 weight_mod_chunks=0" in out[2]["lines"][0]
    assert harness[2]["model"] == bare[1]["model"]
    # window: set on the shared pipe for its arm only, no reload
    assert out[3]["window"] == ["[lingbot] window: local_attn=18 sink=1"]
    assert harness[3]["window"] == (18, 1, [(18, 1), (18, 1)]) and harness[4]["window"] == default_window
    assert "window=18:1" in out[3]["lines"][0] and "window=18:1" in out[3]["total"][0]
    assert harness[3]["model"] == bare[1]["model"]
    # IF identity cue: third-person IF only, appended to the caption prompt, counted once per reset
    cued = IFI.compose(IF_TASK, if_cap, "IF002_chunk_01")
    assert harness[4]["model"] == [gc_cap, gc_cap, cued, cued]
    assert "if_identity=on if_identity_prompts=0" in out[4]["lines"][0]
    assert "if_identity=on if_identity_prompts=1" in out[4]["lines"][1]
    # measured turn: player-side only, nothing measured without decide_action calls
    assert harness[5]["model"] == bare[1]["model"]
    assert "measured_turn=skip measured_chunks=0" in out[5]["lines"][0]
    assert not (R.WEIGHT_MOD or R.IF_IDENTITY) and (R.LOCAL_ATTN, R.SINK) == (18, 6)


def test_all_batch4_flags_together(harness, capsys):
    arm = _run(capsys, "--lingbot-caption-prompt", "--lingbot-weight-mod", "--lingbot-local-attn", "13",
               "--lingbot-sink-size", "0", "--lingbot-if-identity-cue", "--lingbot-measured-turn")
    assert all(p in arm["mode"] for p in MODE_PARTS)
    gc, if_ = arm["lines"]
    assert "weight_mod=on" in gc and "window=13:0" in gc and "if_identity_prompts=0" in gc and "measured_turn=" in gc
    assert "if_identity_prompts=1" in if_
    assert harness[0]["window"] == (13, 0, [(13, 0), (13, 0)])


def test_weight_mod_schedule_shows_only_when_set(harness, capsys, monkeypatch):
    monkeypatch.setenv("LINGBOT_CAM_LATE_STEPS", "2")
    monkeypatch.setenv("LINGBOT_CAM_WEIGHT_STATIC_LATE", "1.0")
    monkeypatch.setenv("LINGBOT_TEXT_WEIGHT_STATIC", "1.3")
    arm = _run(capsys, "--lingbot-weight-mod")
    assert "text static 1.3, late steps 2, static late 1.0" in arm["mode"]
    assert "weight_mod_late=2:static=1.0,3p=0.85" in arm["lines"][0]


def test_weight_mod_and_cond_schedule_are_refused_together(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    with pytest.raises(SystemExit, match="both wrap"):
        R.configure(["run.py", "--lingbot-weight-mod", "--lingbot-cond-schedule"], {})
