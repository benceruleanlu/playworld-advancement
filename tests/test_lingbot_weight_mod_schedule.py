"""Late-step camera scale schedule for weight modulation. Pure Python + numpy, no GPU/torch."""
import numpy as np
import pytest
from adapters.lingbot_world2 import session as S, weight_mod as W
from tests.test_lingbot_weight_mod import _dit

EYE = np.broadcast_to(np.eye(4), (4, 4, 4))


def _move_rel():
    return S.PoseTrack().advance(["w"] * 28)


def test_schedule_off_by_default():
    mod = W.WeightModulator(_dit(3, n=2))
    assert mod.late_steps == 0 and mod.cam_static_late == mod.cam_static and mod.cam_3p_late == mod.cam_3p
    mod.step(EYE)
    assert [mod.denoise_step(i, 4) for i in range(4)] == [0.0, 0.0, 0.0, 0.0]


def test_stationary_late_steps_restore_late_scale_then_end_chunk_restores_base():
    mod = W.WeightModulator(_dit(3, n=2), cam_static_late=1.0, late_steps=2)
    mod.step(EYE)
    assert [mod.denoise_step(i, 4) for i in range(4)] == [0.0, 0.0, 1.0, 1.0]
    mod.end_chunk()
    assert mod.cam_scale == 0.0


def test_third_person_schedule_and_move_never_rescheduled():
    mod = W.WeightModulator(_dit(3, n=2), cam_3p_late=1.0, late_steps=1)
    mod.step(_move_rel(), third_person=True)
    assert [mod.denoise_step(i, 4) for i in range(4)] == [0.85, 0.85, 0.85, 1.0]
    mod.step(_move_rel(), third_person=False)
    assert [mod.denoise_step(i, 4) for i in range(4)] == [1.0, 1.0, 1.0, 1.0]


def test_late_scale_applies_through_wrapped_layers(monkeypatch):
    x, c, a = np.random.default_rng(7).normal(size=(3, 3, 8))
    dit, ref = _dit(42), _dit(42)
    for b in ref.blocks:
        for lyr in (b.cam_scale_layer, b.cam_shift_layer):
            lyr.weight, lyr.bias = lyr.weight * 0.5, (None if lyr.bias is None else lyr.bias * 0.5)
    mod = W.WeightModulator(dit, cam_static_late=0.5, late_steps=2)
    mod.step(EYE)
    assert mod.denoise_step(0, 4) == 0.0
    assert np.allclose(dit.run(x, c, a), x + sum(b.cross_attn.o(a) for b in dit.blocks), rtol=1e-12, atol=1e-12)
    assert mod.denoise_step(3, 4) == 0.5
    assert np.allclose(dit.run(x, c, a), ref.run(x, c, a), rtol=1e-12, atol=1e-12)
    monkeypatch.setenv("LINGBOT_CAM_LATE_STEPS", "-1")
    with pytest.raises(ValueError):
        W.WeightModulator(dit)
    monkeypatch.setenv("LINGBOT_CAM_LATE_STEPS", "2")
    monkeypatch.setenv("LINGBOT_CAM_WEIGHT_STATIC_LATE", "0.25")
    mod2 = W.WeightModulator(dit)
    assert (mod2.late_steps, mod2.cam_static_late) == (2, 0.25)
