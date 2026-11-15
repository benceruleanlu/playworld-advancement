"""Inference-time DiT conditioning weight modulation. Pure Python + numpy, no GPU/torch."""
from functools import reduce
import json, sys, types  # noqa: E401
from types import SimpleNamespace
import numpy as np
import pytest
from adapters.lingbot_world2 import flag_stats as F, run as R, session as S, weight_mod as W


class _Lin:
    def __init__(self, w, b): self.weight, self.bias = w, b
    def forward(self, x): return x @ self.weight.T if self.bias is None else x @ self.weight.T + self.bias
    def __call__(self, x): return self.forward(x)

def _dit(seed: int = 0, n: int = 40, d: int = 8):
    rng = np.random.default_rng(seed)
    mk = lambda b: _Lin(rng.normal(0, 0.05, (d, d)), rng.normal(0, 0.02, d) if b else None)  # noqa: E731
    blks = [SimpleNamespace(cam_scale_layer=mk(i % 2 == 0), cam_shift_layer=mk(i % 2 == 0), cross_attn=SimpleNamespace(o=mk(i % 2 == 0))) for i in range(n)]
    return SimpleNamespace(blocks=blks, run=lambda x, c, a: reduce(lambda h, b: (1.0 + b.cam_scale_layer(c)) * h + b.cam_shift_layer(c) + b.cross_attn.o(a), blks, x))

def test_linearity_equivalence_across_40_blocks():
    x, c, a = np.random.default_rng(7).normal(size=(3, 3, 8))
    for cs, ts in ((0.0, 1.0), (0.85, 1.0), (0.0, 1.15), (1.0, 1.0)):
        dit, ref = _dit(42), _dit(42)
        for b in ref.blocks:
            for lyr, s in ((b.cam_scale_layer, cs), (b.cam_shift_layer, cs), (b.cross_attn.o, ts)):
                lyr.weight, lyr.bias = lyr.weight * s, (None if lyr.bias is None else lyr.bias * s)
        W.WeightModulator(dit, cam_static=cs, text_scale=ts).step(np.broadcast_to(np.eye(4), (4, 4, 4)))
        assert np.allclose(dit.run(x, c, a), ref.run(x, c, a), rtol=1e-12, atol=1e-12)

def test_wait_releases_cam_lock_and_30_steps_have_zero_drift():
    dit, base = _dit(9), _dit(9)
    snap = [(b.cam_scale_layer.weight.copy(), b.cross_attn.o.weight.copy()) for b in dit.blocks]
    x, c, a = np.random.default_rng(1).normal(size=(3, 2, 8))
    mod, trk = W.WeightModulator(dit), S.PoseTrack()
    for step in range(30):
        k = ("none", "j", "none", "w")[step % 4]
        with mod:
            assert mod.step(trk.advance([k] * S.keys_needed(2, first=step == 0)), third_person=False) == (k == "none")
            assert (all(np.array_equal((1.0 + b.cam_scale_layer(c)) * x + b.cam_shift_layer(c), x) for b in dit.blocks) if k == "none" else np.array_equal(dit.run(x, c, a), base.run(x, c, a)))
        assert (mod.cam_scale, mod.text_scale) == (1.0, 1.0)
    assert all(np.array_equal(b.cam_scale_layer.weight, wc) and np.array_equal(b.cross_attn.o.weight, wt) for b, (wc, wt) in zip(dit.blocks, snap))
    mod.detach()
    assert not hasattr(dit, "_weight_mod") and all("forward" not in b.cam_scale_layer.__dict__ for b in dit.blocks)

def test_task_perspective_schedule_and_env(monkeypatch):
    mod = W.WeightModulator(dit := _dit(3, n=2))
    rw, rm, rt = (S.PoseTrack().advance([k] * 28) for k in ("none", "w", "j"))
    assert mod.step(rw, W.is_third_person({"task_id": "OE001", "perspective": "first person"}, "OE001_chunk_01")) and (mod.cam_scale, mod.text_scale) == (0.0, 1.0)
    assert mod.step(rm, W.is_third_person({"task_id": "IF010", "category": "IF"}, "IF010_chunk_01")) and (mod.cam_scale, mod.text_scale) == (0.85, 1.0)
    assert mod.step(rm, W.is_third_person({"task_id": "GC016", "perspective": "third person"}, "GC016_chunk_01")) and (mod.cam_scale, mod.text_scale) == (0.85, 1.0)
    assert not mod.step(rt, W.is_third_person({"task_id": "GC033", "perspective": "first person"}, "GC033_chunk_01")) and not W.is_third_person({"task_id": "IF010"}, "GC033_chunk_01")
    monkeypatch.setenv("LINGBOT_TEXT_WEIGHT_SCALE", "1.15")
    assert W.WeightModulator(dit).text_gain == 1.15
    monkeypatch.setenv("LINGBOT_CAM_WEIGHT_STATIC", "-0.1")
    with pytest.raises(ValueError): W.WeightModulator(dit)  # noqa: E701

def test_multi_arm_in_process_isolation_and_flag_stats(tmp_path, monkeypatch, capsys):
    assert "weight_mod" not in (st := F.FlagStats(False, "goal", False, False)).summary("OE018") and "weight_mod" not in st.total_line()
    root, weights, dit = tmp_path / "lb", tmp_path / "w", _dit(5, n=2)
    for d in (root / "wan", weights / "lingbot-world-v2-14b-causal-fast", tmp_path / "OE018"): d.mkdir(parents=True)  # noqa: E701
    for k in ("LINGBOT_WEIGHT_MOD", "LINGBOT_SESSION", "LINGBOT_FAST", "LINGBOT_FAST_T5", "LINGBOT_FAST_LOAD", "LINGBOT_FAST_Y", "LINGBOT_FAST_DIT"): monkeypatch.delenv(k, raising=False)  # noqa: E701
    monkeypatch.setenv("LINGBOT_ROOT", str(root)); monkeypatch.setenv("LINGBOT_WEIGHTS", str(weights))  # noqa: E702
    wan, cfg, i2v = types.ModuleType("wan"), types.ModuleType("wan.configs"), types.ModuleType("wan.image2video")
    wan.WanI2VCausal, cfg.WAN_CONFIGS = (lambda **kw: SimpleNamespace(model=dit, _t5_cache={})), {"i2v-A14B": SimpleNamespace(sample_shift=5.0)}
    for n in ("T5EncoderModel", "Wan2_1_VAE", "load_dit_model"): setattr(i2v, n, lambda *a, **k: None)  # noqa: E701
    wan.image2video = i2v
    for name, mod in (("wan", wan), ("wan.configs", cfg), ("wan.image2video", i2v)): monkeypatch.setitem(sys.modules, name, mod)  # noqa: E701
    monkeypatch.setattr(R, "_PIPES", {})
    def fake_import(fresh=False):
        m = types.ModuleType("run_agent")
        m.to_sana_key, m.decide_action = {"WAIT": "none"}.get, lambda *a, **k: "WAIT"
        def run_task(t, eng, out_d, args):
            assert hasattr(dit, "_weight_mod") if eng.weight_mod else (not hasattr(dit, "_weight_mod") and all("forward" not in b.cam_scale_layer.__dict__ for b in dit.blocks))
            if eng.weight_mod: R.STATS.modulated(2)  # noqa: E701
            (tmp_path / "OE018" / "OE018_result.json").write_text(json.dumps({"task_id": "OE018", "success": True}))
            return {"task_id": "OE018", "success": True}
        m.run_task, m.main = run_task, lambda: (m.run_task({"task_id": "OE018", "prompt": "g"}, m.SanaWMEngine(SimpleNamespace(seed=0, fps=16, max_total_frames=961)), str(tmp_path), None), None)[1]
        return m
    monkeypatch.setattr(R, "import_run_agent", fake_import)
    assert R.main(["run.py", "--tasks", "OE018", "--lingbot-weight-mod"]) == 0 and "weight_mod=on weight_mod_steps=2" in (out1 := capsys.readouterr().out)
    assert "weight-mod on" in out1 and json.loads((tmp_path / "OE018" / "OE018_result.json").read_text())["lingbot_flags"]["weight_mod_steps"] == 2
    assert R.main(["run.py", "--tasks", "OE018"]) == 0 and R.WEIGHT_MOD is False and "weight_mod" not in capsys.readouterr().out
