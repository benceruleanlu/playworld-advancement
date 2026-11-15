"""pwa.return_sim on synthetic frames (numpy only) and one tiny mp4 when imageio can write it."""
import numpy as np
import pytest

from pwa import return_sim as RS


def _pan_video(n=80, back=True, seed=0):
    """A wide random panorama; the camera pans right then (optionally) back to the start."""
    rng = np.random.default_rng(seed)
    pano = (rng.random((96, 600, 3)) * 255).astype(np.uint8)
    half = n // 2
    xs = list(np.linspace(0, 400, half).astype(int))
    xs += list(np.linspace(400, 0, n - half).astype(int)) if back else [400] * (n - half)
    return [pano[:, x:x + 168] for x in xs]


def test_small_gray_and_ncc():
    f = np.zeros((128, 224, 3), np.uint8)
    f[:, :112] = 200
    g = RS.to_small_gray(f)
    assert g.shape == RS.SIZE and np.allclose(g[:, :56], 200) and np.allclose(g[:, 56:], 0)
    assert RS.ncc(g, g * 0.5 + 10) == pytest.approx(1.0)  # brightness/contrast invariant
    assert RS.ncc(g, -g) == pytest.approx(-1.0) and RS.ncc(g, np.ones_like(g)) == 0.0
    with pytest.raises(ValueError):
        RS.to_small_gray(np.zeros((10, 10)))


def test_return_peak_and_no_return():
    back = RS.similarity_to_first(_pan_video(back=True), fps=16, after_s=1.0)
    away = RS.similarity_to_first(_pan_video(back=False), fps=16, after_s=1.0)
    assert back["frames"] == away["frames"] == 80 and back["similarity"][0] == 1.0
    assert back["max_after"] > 0.99 and back["max_frame"] == 79 and back["max_time_s"] == pytest.approx(79 / 16, abs=1e-3)
    assert away["max_after"] < 0.2 and back["last"] > 0.99 and away["last"] < 0.2
    assert min(back["similarity"][16:60]) < 0.2  # it did leave the start view
    short = RS.similarity_to_first(_pan_video(n=10), fps=16, after_s=4.0)
    assert short["max_after"] is None
    with pytest.raises(ValueError):
        RS.similarity_to_first([], fps=16)


def test_mp4_roundtrip(tmp_path, capsys):
    imageio = pytest.importorskip("imageio.v2")
    pytest.importorskip("imageio_ffmpeg")
    path = tmp_path / "v.mp4"
    frames = [np.repeat(np.repeat(f, 2, 0), 2, 1)[:192, :320] for f in _pan_video(n=48)]
    imageio.mimsave(str(path), frames, fps=16, macro_block_size=16)
    r = RS.measure(str(path), after_s=1.0)
    assert r["fps"] == 16 and r["frames"] == 48 and r["max_after"] > 0.9 and r["max_frame"] >= 44
    assert RS.main([str(path), "--after", "1"]) == 0 and "max_after_1s=" in capsys.readouterr().out
