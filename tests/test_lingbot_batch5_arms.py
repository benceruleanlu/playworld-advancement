"""Proposal batch 5 flags (noisy KV writes, step-0 self-guidance, sink key scale) under pwa gen-arms: several
main() calls in one process, one flag per arm, with no-flag and caption-only arms before and after. No session
object, counter, prompt, self-attention patch or KV window may leak between arms, and the no-flag lines and model
prompts must stay byte-identical. Mocked upstream and pipe; no GPU, no API. The flags' own effects are unit-tested
in test_lingbot_kv_noise.py, test_lingbot_stg.py and test_lingbot_sink_scale.py."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.common import agent_api
from adapters.lingbot_world2 import kv_noise as KVN
from adapters.lingbot_world2 import run as R
from adapters.lingbot_world2 import sink_scale as SK
from adapters.lingbot_world2 import stg as STGM
from tests.test_lingbot_weight_mod import _dit

GC_TASK = {"task_id": "GC001", "category": "GC", "image_caption": "A quiet street.", "prompt": "Turn right."}
OE_TASK = {"task_id": "OE047", "category": "Out-of-sight", "image_caption": "A shelf.", "prompt": "Look left."}
BASE_LINE = "[lingbot] flags task={} turn_cal=0 caption={} reanchor=off reanchor_events=0 player_hint=off player_hints=0"
MODE_PARTS = ("kv-noise t=", "stg w=", "sink key scale")
FIELDS = ("kv_noise", "stg", "sink_scale")


class _Attn:
    def __init__(self):
        self.local_attn_size, self.sink_size = 18, 6

    def forward(self, x, *a, **kw):
        return x


def _pipe():
    model = _dit(3, n=4)
    for b in model.blocks:
        b.self_attn = _Attn()
    model.modules = lambda: [model, *(b.self_attn for b in model.blocks)]
    return SimpleNamespace(model=model, local_attn_size=18, sink_size=6)


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
            s = engine.session
            rec["session"] = None if s is None else (s.kv_noise, s.stg, s.sink_scale)
            rec["window"] = (pipe.local_attn_size, pipe.sink_size)
            for task in (GC_TASK, OE_TASK):
                m.run_task(dict(task), engine, "out", args)
            rec["patched"] = [b.self_attn for b in pipe.model.blocks if "forward" in b.self_attn.__dict__]
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
    assert R.main(["run.py", "--tasks", "GC001,OE047", *flags]) == 0
    out = capsys.readouterr().out.splitlines()
    return {"lines": [ln for ln in out if ln.startswith("[lingbot] flags task=")],
            "total": [ln for ln in out if ln.startswith("[lingbot] flags total")],
            "mode": [ln for ln in out if ln.startswith("[lingbot] mode:")][0]}


def test_one_flag_per_arm_no_leaks_and_no_flag_arms_unchanged(harness, capsys):
    cap = "--lingbot-caption-prompt"
    plan = [(), (cap,), ("--lingbot-kv-noise", "--lingbot-kv-noise-t=50"), ("--lingbot-stg",),
            ("--lingbot-sink-key-scale", "0.7", "--lingbot-sink-scale-tasks", "OE"), (cap,), ()]
    out = [_run(capsys, *flags) for flags in plan]
    assert len(harness) == len(plan) and len({id(a["module"]) for a in harness}) == len(plan)
    bare, caption = (out[0], harness[0]), (out[1], harness[1])

    for (arm, rec), (again, rec2) in ((bare, (out[6], harness[6])), (caption, (out[5], harness[5]))):
        assert arm["lines"] == again["lines"] and arm["total"] == again["total"] and arm["mode"] == again["mode"]
        assert rec["model"] == rec2["model"] and rec2["session"] == (None, None, None)
        assert not any(f in " ".join(arm["lines"] + arm["total"]) for f in FIELDS)
        assert not any(p in arm["mode"] for p in MODE_PARTS)
        assert rec2["window"] == (18, 6) and not rec2["patched"]
    assert bare[0]["lines"] == [BASE_LINE.format("GC001", "off"), BASE_LINE.format("OE047", "off")]
    assert caption[0]["lines"] == [BASE_LINE.format("GC001", "used"), BASE_LINE.format("OE047", "used")]

    for i, field in ((2, "kv_noise"), (3, "stg"), (4, "sink_scale")):
        text = " ".join(out[i]["lines"] + out[i]["total"])
        assert field in text and not any(f in text for f in FIELDS if f != field), (i, text)
        assert [p for p in MODE_PARTS if p in out[i]["mode"]] == [MODE_PARTS[i - 2]]
        for line, base in zip(out[i]["lines"], bare[0]["lines"]):
            assert line.startswith(base + " "), (line, base)
        assert harness[i]["model"] == bare[1]["model"] and not harness[i]["patched"]

    kvn, stg, sk = harness[2]["session"], harness[3]["session"], harness[4]["session"]
    assert isinstance(kvn[0], KVN.KVNoise) and kvn[0].cfg == KVN.KVNoiseConfig(True, 50.0) and kvn[1:] == (None, None)
    assert kvn[0] is not None and stg[0] is None and isinstance(stg[1], STGM.SkipGuidance) and stg[1].blocks == (2,)
    assert stg[2] is None and sk[:2] == (None, None) and sk[2] == SK.SinkScaleConfig(0.7, 8, "OE")
    assert "kv_noise=on kv_noise_t=50 kv_noise_chunks=0" in out[2]["lines"][0]
    assert "stg w=0.3 blocks=2 steps=1" in out[3]["mode"] and "stg=on stg_chunks=0 stg_calls=0" in out[3]["lines"][0]
    assert out[4]["lines"][0].endswith("sink_scale=skip sink_scaled_chunks=0")  # GC001 does not match 'OE'
    assert "sink key scale 0.7 from chunk 8 tasks 'OE'" in out[4]["mode"]
    assert not (R.KV_NOISE.enabled or R.STG.enabled or R.SINK_SCALE.enabled)


def test_all_batch5_flags_together(harness, capsys):
    arm = _run(capsys, "--lingbot-kv-noise", "--lingbot-stg", "--lingbot-stg-blocks=1,3", "--lingbot-sink-key-scale",
               "0.5", "--lingbot-sink-scale-after", "4")
    assert all(p in arm["mode"] for p in MODE_PARTS)
    assert all(f in arm["lines"][0] for f in ("kv_noise=on", "stg=on", "sink_scale="))  # sink arming happens at session reset (mocked here)
    kvn, stg, sk = harness[0]["session"]
    assert kvn.cfg.t == 25.0 and stg.blocks == (1, 3) and sk == SK.SinkScaleConfig(0.5, 4, ".*")


@pytest.mark.parametrize("argv, match", [
    (["--lingbot-kv-noise-t=300", "--lingbot-kv-noise"], r"\(0, 250\]"),
    (["--lingbot-stg", "--lingbot-stg-steps=5"], "denoising steps"),
    (["--lingbot-stg", "--lingbot-stg-w=0"], "no-op"),
    (["--lingbot-sink-key-scale", "0.7", "--lingbot-stateless"], "no-op arm"),
    (["--lingbot-sink-key-scale", "0.7", "--lingbot-sink-size", "0"], "no-op arm"),
    (["--lingbot-sink-key-scale", "0.7", "--lingbot-sink-size", "0", "--lingbot-local-attn", "-1"], "no-op arm"),
])
def test_batch5_refusals(monkeypatch, argv, match):
    for key in tuple(R.os.environ):
        if key.startswith("LINGBOT_"):
            monkeypatch.delenv(key)
    with pytest.raises(SystemExit, match=match):
        R.configure(["run.py", *argv], {})
