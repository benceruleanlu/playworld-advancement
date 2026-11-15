import numpy as np
import pytest

from adapters.lingbot_world2 import camera_probe as CP
from adapters.lingbot_world2 import session as S


def _texture(seed=0, h=464, w=2900):
    """Smooth random texture with no repeating grid (a shared grid would correlate unrelated textures)."""
    rng = np.random.default_rng(seed)
    t = rng.random((h + 8, w + 8)).astype(np.float32)
    c = np.cumsum(np.cumsum(t, axis=0), axis=1)
    t = (c[8:, 8:] - c[:-8, 8:] - c[8:, :-8] + c[:-8, :-8]) / 64.0     # 8x8 box blur: survives the 2x downsample
    t = (t - t.min()) / (t.max() - t.min())
    return (t * 255).astype(np.uint8)


def _frames(offsets, tex=None, x0=700):
    """A camera whose heading is `offsets[i]` pixels right of the start: the view slides right over the texture."""
    tex = _texture() if tex is None else tex
    return np.stack([np.repeat(tex[:, x0 + o:x0 + o + 832, None], 3, axis=2) for o in offsets])


def test_build_frame_accounting_and_padding():
    keys, spans, n = CP.build([("l", 90), ("j", 90)])
    assert n == 11 and len(keys) == S.keys_needed(11, first=True) == 172
    assert keys[:80] == ["l"] * 80 and keys[80:160] == ["j"] * 80 and set(keys[160:]) == {"none"}  # padded with waits
    assert [(s["first"], s["last"], s["commanded"]) for s in spans] == [(0, 80, 90.0), (80, 160, -90.0)]
    keys, spans, n = CP.build([("j", 45), ("none", 8), ("l", 45)], rate_deg=2.25)
    assert [s["last"] - s["first"] for s in spans] == [20, 8, 20] and spans[1]["commanded"] == 0.0
    assert n == 4 and len(keys) == 60
    for bad in ([("x", 10)], [("none", 0)]):
        with pytest.raises(ValueError):
            CP.build(bad)
    with pytest.raises(ValueError):
        CP.build([("l", 10)], rate_deg=0)


def test_measure_signs_and_relative_gain():
    # right at 4 px per frame for 20 frames, then left at 2 px per frame for 20 frames
    offs = [4 * i for i in range(21)] + [80 - 2 * i for i in range(1, 21)]
    frames = _frames(offs)
    spans = [{"key": "l", "first": 0, "last": 20, "commanded": 20.0}, {"key": "j", "first": 20, "last": 40, "commanded": -10.0}]
    right, left = CP.measure(frames, spans)
    assert right["rendered"] > 0 > left["rendered"] and right["trusted"] and left["trusted"]
    assert right["rendered"] / -left["rendered"] == pytest.approx(2.0, rel=0.03)   # twice the pixels, twice the angle
    assert right["gain"] == pytest.approx(right["rendered"] / 20.0, abs=1e-3)
    assert abs(right["pitch"]) < 0.2
    wait = CP.measure(_frames([0] * 5), [{"key": "none", "first": 0, "last": 4, "commanded": 0.0}])[0]
    assert wait["rendered"] == pytest.approx(0.0, abs=0.05) and wait["gain"] is None


def test_closure_reads_residual_heading_and_content():
    frames = _frames([0, 40, 80, 40, 0, 12])
    back = CP.closure(frames, 0, 4)
    assert back["yaw"] == pytest.approx(0.0, abs=0.05) and back["same_view"] and back["match"] > 0.5
    assert back["ncc"] > 0.99
    off = CP.closure(frames, 0, 5)
    assert off["yaw"] > 0.5 and off["same_view"] and off["ncc"] > 0.95   # ends 12 px right of the start
    assert CP.closure(frames, 0, 1)["yaw"] == pytest.approx(-CP.closure(frames, 1, 0)["yaw"], abs=0.05)
    other = np.concatenate([frames[:1], _frames([0], tex=_texture(seed=9))])
    diff = CP.closure(other, 0, 1)
    assert not diff["same_view"] and abs(diff["ncc"]) < 0.3         # different content: no trusted offset


def test_best_return_finds_where_the_start_view_reappears():
    offs = [0, 60, 120, 180, 120, 60, 2, 60]
    best = CP.best_return(_frames(offs), after=3)
    assert best["frame"] == 6 and best["same_view"]
    gone = CP.best_return(_frames([0, 500, 900, 1300]), after=1)     # no frame overlaps the start crop again
    assert not gone["same_view"]


def test_summarize_and_gains():
    offs = [4 * i for i in range(21)] + [80 - 4 * i for i in range(1, 21)] + [0] * 4
    frames = _frames(offs)
    keys, spans, n = CP.build([("l", 22.5), ("j", 22.5)])           # 20 + 20 frames
    assert len(keys) + 1 == len(frames) == 45
    out = CP.summarize(frames, spans)
    assert out["commanded_net"] == 0 and abs(out["rendered_net"]) < 0.2 and out["trusted"]
    assert out["closure"]["same_view"] and abs(out["closure"]["yaw"]) < 0.1
    g = CP.gains_from([out, out])
    assert set(g) == {"right_out", "left_back"} and g["right_out"]["n"] == 2
    assert g["right_out"]["mean"] == pytest.approx(g["left_back"]["mean"], rel=0.03)
