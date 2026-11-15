"""Proposal batch 3 flags (GC chunk director, GC ease turns, IF subject director) under pwa gen-arms: several
main() calls in one process, one flag per arm, with no-flag and caption-only arms before and after. No state,
counter or prompt may leak between arms, and the no-flag lines and model prompts must stay byte-identical.
Mocked upstream and pipe; no GPU, no API. The session-side effects (text refresh, eased poses) are unit-tested
in test_gc_chunk_director.py and test_gc_ease_turns.py."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.common import agent_api
from adapters.lingbot_world2 import if_subject as IFS
from adapters.lingbot_world2 import run as R

GC_TASK = {"task_id": "GC001", "category": "GC", "image_caption": "A quiet street.", "prompt": "Turn right."}
IF_TASK = {"task_id": "IF002", "category": "IF", "perspective": "third person", "image_caption": "A dog.",
           "prompt": "The dog walks to the bench."}
BASE_LINE = "[lingbot] flags task={} turn_cal=0 caption={} reanchor=off reanchor_events=0 player_hint=off player_hints=0"
MODE_PARTS = ("GC chunk director", "GC ease turns", "IF subject director")
FIELDS = ("gc_director", "gc_ease_turns", "if_subject")


@pytest.fixture
def harness(monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(agent_api, "patch", lambda ra, *a, **k: "test")
    monkeypatch.setattr(R, "load_pipe", lambda environ=None: (SimpleNamespace(sample_shift=5.0), SimpleNamespace(),
                                                              Path("weights"), False))
    arms = []

    def fresh(fresh=False):
        m = SimpleNamespace()
        rec = {"model": []}

        def run_task(task, engine, output_dir, args):
            engine._generate_session = engine._generate_stateless = lambda *a: rec["model"].append(a[1]) or "v.mp4"
            for chunk, action in ((1, "l-33"), (2, "w-33")):
                engine.generate("image.jpg", task["prompt"], action, output_dir,
                                f"{task['task_id']}_chunk_{chunk:02d}", 33)
            return {"task_id": task["task_id"], "success": False}

        def main():
            args = SimpleNamespace(seed=42, fps=16, max_total_frames=961, action_frame_unit=20, chunk_frames=33)
            engine = m.SanaWMEngine(args)
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
            "mode": [ln for ln in out if ln.startswith("[lingbot] mode:")][0]}


def test_one_flag_per_arm_no_leaks_and_no_flag_arms_unchanged(harness, capsys):
    cap = "--lingbot-caption-prompt"
    plan = [(), (cap,), (cap, "--lingbot-gc-chunk-director"), ("--lingbot-gc-ease-turns",),
            (cap, "--lingbot-if-subject-director"), (cap,), ()]
    out = [_run(capsys, *flags) for flags in plan]
    assert len(harness) == len(plan) and len({id(a["module"]) for a in harness}) == len(plan)
    bare, caption = (out[0], harness[0]), (out[1], harness[1])

    # no-flag and caption-only arms: main's exact lines and prompts, identical before and after the flag arms
    for (arm, rec), (again, rec2) in ((bare, (out[6], harness[6])), (caption, (out[5], harness[5]))):
        assert arm["lines"] == again["lines"] and arm["total"] == again["total"] and arm["mode"] == again["mode"]
        assert rec["model"] == rec2["model"]
        assert not any(f in " ".join(arm["lines"] + arm["total"]) for f in FIELDS)
        assert not any(p in arm["mode"] for p in MODE_PARTS)
    assert bare[0]["lines"] == [BASE_LINE.format("GC001", "off"), BASE_LINE.format("IF002", "off")]
    assert bare[1]["model"] == [GC_TASK["prompt"]] * 2 + [IF_TASK["prompt"]] * 2
    assert caption[0]["lines"] == [BASE_LINE.format("GC001", "used"), BASE_LINE.format("IF002", "used")]
    gc_cap, if_cap = caption[1]["model"][0], caption[1]["model"][2]

    # each flag arm: only its own fields and mode part, main's fields first and unchanged
    for i, field in ((2, "gc_director"), (3, "gc_ease_turns"), (4, "if_subject")):
        control = caption[0] if i != 3 else bare[0]
        text = " ".join(out[i]["lines"] + out[i]["total"])
        assert field in text and not any(f in text for f in FIELDS if f != field), (i, text)
        assert [p for p in MODE_PARTS if p in out[i]["mode"]] == [MODE_PARTS[i - 2]]
        for line, base in zip(out[i]["lines"], control["lines"]):
            assert line.startswith(base + " "), (line, base)

    director, ease, subject = harness[2]["model"], harness[3]["model"], harness[4]["model"]
    assert director == [f"{gc_cap}\nDuring this segment, the camera pans right.",
                        f"{gc_cap}\nDuring this segment, the camera moves forward.", if_cap, if_cap]
    assert "gc_director=on gc_director_chunks=2 gc_director_updates=0" in out[2]["lines"][0]
    assert "gc_director=on gc_director_chunks=0" in out[2]["lines"][1]
    assert ease == bare[1]["model"]  # engine-only flag; the eased pose track is unit-tested
    assert "gc_ease_turns=on gc_eased_turns=0" in out[3]["lines"][0]
    composed = IFS.compose(IF_TASK, IF_TASK["prompt"], "IF002_chunk_01")
    assert subject == [gc_cap, gc_cap, composed, composed]
    assert "if_subject=on if_subject_prompts=0" in out[4]["lines"][0]
    assert "if_subject=on if_subject_prompts=2" in out[4]["lines"][1]
    assert not (R.GC_DIRECTOR or R.GC_EASE_TURNS or R.IF_SUBJECT)


@pytest.mark.parametrize("flags,needs", [
    (("--lingbot-gc-chunk-director",), "caption prompting"),
    (("--lingbot-caption-prompt", "--lingbot-gc-chunk-director", "--lingbot-stateless"), "session mode"),
    (("--lingbot-gc-ease-turns", "--lingbot-stateless"), "session mode"),
    (("--lingbot-if-subject-director",), "caption prompting")])
def test_flag_requirements_are_refused(flags, needs, monkeypatch):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    with pytest.raises(SystemExit, match=needs):
        R.configure(["run.py", *flags], {})


def test_all_batch3_flags_together(harness, capsys):
    arm = _run(capsys, "--lingbot-caption-prompt", "--lingbot-gc-chunk-director", "--lingbot-gc-ease-turns",
               "--lingbot-if-subject-director")
    assert all(p in arm["mode"] for p in MODE_PARTS)
    gc, if_ = arm["lines"]
    assert "gc_director_chunks=2" in gc and "gc_ease_turns=on" in gc and "if_subject_prompts=0" in gc
    assert "gc_director_chunks=0" in if_ and "if_subject_prompts=2" in if_
    total = arm["total"][0]
    assert "gc_director_chunks=2" in total and "gc_eased_turns=0" in total and "if_subject_prompts=2" in total
