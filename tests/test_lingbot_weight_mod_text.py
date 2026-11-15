"""Stationary-only text scale for weight modulation. Pure Python + numpy, no GPU/torch."""
import numpy as np
import pytest
from adapters.lingbot_world2 import session as S, weight_mod as W
from tests.test_lingbot_weight_mod import _dit


def _rel(key):
    return S.PoseTrack().advance([key] * 28)


def test_stationary_text_scale_is_separate_from_third_person_and_move():
    mod = W.WeightModulator(_dit(3, n=2), text_scale=1.15, text_static=1.3)
    rw, rm = _rel("none"), _rel("w")
    assert mod.step(rw, third_person=False) and (mod.cam_scale, mod.text_scale) == (0.0, 1.3)
    assert mod.step(rm, third_person=True) and (mod.cam_scale, mod.text_scale) == (0.85, 1.15)
    assert not mod.step(rm, third_person=False) and (mod.cam_scale, mod.text_scale) == (1.0, 1.0)


def test_text_static_defaults_to_text_gain(monkeypatch):
    dit = _dit(3, n=2)
    assert W.WeightModulator(dit).text_static == 1.0
    monkeypatch.setenv("LINGBOT_TEXT_WEIGHT_SCALE", "1.15")
    assert W.WeightModulator(dit).text_static == 1.15
    monkeypatch.setenv("LINGBOT_TEXT_WEIGHT_STATIC", "1.3")
    mod = W.WeightModulator(dit)
    assert (mod.text_gain, mod.text_static) == (1.15, 1.3)
    monkeypatch.setenv("LINGBOT_TEXT_WEIGHT_STATIC", "-0.5")
    with pytest.raises(ValueError):
        W.WeightModulator(dit)


def test_stationary_text_up_scales_cross_attn_output_only():
    x, c, a = np.random.default_rng(7).normal(size=(3, 3, 8))
    dit, ref = _dit(42), _dit(42)
    for b in ref.blocks:
        b.cross_attn.o.weight, b.cross_attn.o.bias = b.cross_attn.o.weight * 1.3, (
            None if b.cross_attn.o.bias is None else b.cross_attn.o.bias * 1.3)
        for lyr in (b.cam_scale_layer, b.cam_shift_layer):
            lyr.weight, lyr.bias = lyr.weight * 0.0, (None if lyr.bias is None else lyr.bias * 0.0)
    W.WeightModulator(dit, text_static=1.3).step(np.broadcast_to(np.eye(4), (4, 4, 4)))
    assert np.allclose(dit.run(x, c, a), ref.run(x, c, a), rtol=1e-12, atol=1e-12)
