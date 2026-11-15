"""CPU checks for preserving first-person GC conditioning, including WAIT tails."""
import sys
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from adapters.lingbot_world2 import cond_schedule as C, flag_stats as F, run as R, session as S


class Linear:
    def forward(self, x):
        return x * 2 + 0.5


def model():
    return SimpleNamespace(blocks=[SimpleNamespace(cam_scale_layer=Linear(), cam_shift_layer=Linear(),
        cross_attn=SimpleNamespace(o=Linear()))])


def test_exact_outputs_and_task_switching():
    m = model()
    layers = (m.blocks[0].cam_scale_layer, m.blocks[0].cam_shift_layer, m.blocks[0].cross_attn.o)
    x = np.array([-2, 0, 3], dtype=np.float32)
    base = [layer.forward(x) for layer in layers]
    cfg = C.ScheduleConfig(enabled=True, gc_guard=True)
    sched = C.CondScheduler(m, cfg)
    wait = np.repeat(np.eye(4)[None], 4, axis=0)
    moving = wait.copy()
    moving[:, 0, 3] = 0.25
    sched.set_task("GC033_full", False)
    for rel in (moving, wait, moving, wait):
        for step in range(4):
            assert not sched.set_step(rel, step)
            assert all(np.array_equal(layer.forward(x), b) for layer, b in zip(layers, base))
    assert sched.guard_calls == 4  # 2 WAIT blocks x 2 early steps; moving/late forwards never counted
    for name, third in (("IF010_full", True), ("OE001_full", False), ("GC016_full", True)):
        sched.set_task(name, third)
        assert sched.set_step(wait, 0, third)
        assert (sched.cam_scale, sched.text_scale) == (0, 1.15)
    assert sched.guard_calls == 4
    sched.detach()
    plain = C.CondScheduler(m, C.ScheduleConfig(enabled=True))
    plain.set_task("GC033_full", False)
    assert plain.set_step(wait, 0) and plain.guard_calls == 0
    plain.detach()


@pytest.mark.parametrize("name,third,expected", [("GC033_chunk_01", False, 4),
    ("GC033_full", False, 4), ("GC016_full", True, 0), ("IF010_full", True, 0), ("OE001_full", False, 0)])
def test_runner_route_and_counters(monkeypatch, tmp_path, name, third, expected):
    cfg = C.ScheduleConfig(enabled=True, gc_guard=True)
    sched = C.CondScheduler(model(), cfg)
    sess = S.LingBotSession(object(), 480 * 832, 5.0, cond_sched=sched)
    engine = R.LingBotWorld2Engine.__new__(R.LingBotWorld2Engine)
    engine.session, engine.weight_mod, engine._last_chunk = sess, None, None
    engine.args = SimpleNamespace(seed=42, fps=16)
    engine._calibrate = lambda *a: None
    def reset(*a, **kw):
        sess._free()
        sess.started, sess.track = True, S.PoseTrack()
    def step(keys):
        rel = sess.track.advance(keys)
        for start in range(0, len(rel), 4):
            for i in range(4):
                sess.cond_sched_calls += sched.set_step(rel[start:start + 4], i, sess.third_person)
            sched.reset()
            sess.chunk_id += 1
        return np.zeros((1, 2, 2, 3), dtype=np.uint8)
    monkeypatch.setattr(sess, "reset", reset)
    monkeypatch.setattr(sess, "step", step)
    monkeypatch.setattr(C, "is_third_person", lambda *a: third)
    for flag in ("NOISE_MEAN", "REANCHOR", "GC_DIRECTOR", "GC_EASE_TURNS"):
        monkeypatch.setattr(R, flag, False)
    defaults, _ = R.configure([], {})
    for flag in ("SINK_SCALE", "YAW_GAIN", "KV_NOISE", "STG", "POSE_MEM"):
        monkeypatch.setattr(R, flag, defaults[flag.lower()])
    monkeypatch.setattr(R, "COND_SCHED", cfg)
    stats = F.FlagStats(False, "auto", False, False, cond_sched="on", cond_gc_guard=True)
    monkeypatch.setattr(R, "STATS", stats)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(
        reset_peak_memory_stats=lambda: None, max_memory_allocated=lambda: 0)))
    import imageio
    monkeypatch.setattr(imageio, "mimsave", lambda *a, **kw: None)
    path = tmp_path / "image.png"
    Image.new("RGB", (2, 2)).save(path)
    engine._generate_session(path, "scene", "none-32", tmp_path, name, 33)
    assert stats.gc_cond_guard_calls == expected
    assert stats.cond_sched_calls == (0 if expected else 4)
    if name.endswith("chunk_01"):
        engine._generate_session(path, "scene", "none-32", tmp_path, "GC033_chunk_02", 33)
        assert stats.gc_cond_guard_calls == 8
    result = stats.finish_task(name)
    assert result["gc_cond_guard_calls"] == stats.gc_cond_guard_calls
    assert f"gc_cond_guard_calls={stats.gc_cond_guard_calls}" in stats.total_line()
    stats.new_task()
    assert stats.gc_cond_guard_calls == 0


def test_cli_dependencies_default_and_arm_reset(monkeypatch):
    flag, schedule = C.GC_GUARD, C.FLAG
    flags, rest = R.configure([flag, schedule, "--seed", "42"], {})
    assert flags["cond_sched"].gc_guard and rest == ["--seed", "42"]
    assert R.configure([schedule], {"LINGBOT_COND_GC_GUARD": "1"})[0]["cond_sched"].gc_guard
    for args in ([flag], [flag, schedule, "--lingbot-stateless"]):
        with pytest.raises(SystemExit, match="requires"):
            R.configure(args, {})
    monkeypatch.delenv("LINGBOT_COND_GC_GUARD", raising=False)
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    monkeypatch.setattr(sys, "argv", ["run.py"])
    assert R.main(["run.py", schedule, flag]) == 0
    assert R.COND_SCHED.gc_guard and "GC guard on" in R.COND_SCHED.describe()
    assert R.main(["run.py", schedule]) == 0
    assert not R.COND_SCHED.gc_guard and "cond_gc_guard" not in R.STATS.total_line()
    assert R.main(["run.py"]) == 0 and not R.COND_SCHED.enabled


@pytest.mark.parametrize("task_id,still_blocks", [("GC033", [11, 12]), ("GC036", [21, 22])])
def test_real_dev_dataset_wait_tail(task_id, still_blocks):
    import json
    from adapters.common.upstream import import_run_agent, REPO
    from adapters.lingbot_world2 import poses as P
    task = next(t for t in json.loads((REPO / "data/gc/data.json").read_text()) if t["task_id"] == task_id)
    action, log = import_run_agent().build_full_sana_action(task, 20, 50, 961)
    n = S.chunks_for(sum(row["frames"] for row in log) + 1)
    rel = S.PoseTrack().advance(S.fit_keys(P.parse_action(action), S.keys_needed(n, first=True)))
    assert [i // 4 for i in range(0, len(rel), 4) if C.is_stationary(rel[i:i + 4])] == still_blocks
    sched = C.CondScheduler(model(), C.ScheduleConfig(enabled=True, gc_guard=True))
    sched.set_task(f"{task_id}_full", C.is_third_person(task, f"{task_id}_full"))
    for i in range(0, len(rel), 4):
        for step in range(4):
            assert not sched.set_step(rel[i:i + 4], step)
    assert sched.guard_calls == 4
    sched.detach()
