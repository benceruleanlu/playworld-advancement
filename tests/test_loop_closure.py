"""Loop closure against a synthetic memoryless model (numpy + imageio, no GPU).

The fake model only sees the input image: a turn shifts the view and fills the revealed strip with fresh
noise, so turning away and back without help ends on a different picture than the first frame.
"""
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("imageio")
from PIL import Image  # noqa: E402

from adapters.common import loop_closure as lc  # noqa: E402

H, W, N, PX = 96, 160, 9, 6


def scene():
    rng = np.random.default_rng(0)
    return np.kron(rng.integers(0, 255, (12, 20, 3), dtype=np.uint8), np.ones((8, 8, 1), dtype=np.uint8))


class FakeModel:
    def __init__(self):
        self.calls = []

    def generate(self, image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None):
        key, n = lc.parse_action(action)[0]
        self.calls.append((name, key))
        rng = np.random.default_rng(len(self.calls))
        cur = np.asarray(Image.open(image_path).convert("RGB")).copy()
        frames = [cur]
        for _ in range(n - 1):
            cur = cur.copy()
            if key in ("j", "l"):
                shift = PX if key == "j" else -PX
                cur = np.roll(cur, shift, axis=1)
                strip = np.kron(rng.integers(0, 255, (12, 1, 3), dtype=np.uint8), np.ones((8, PX, 1), dtype=np.uint8))
                cur[:, :PX] = strip if shift > 0 else cur[:, :PX]
                cur[:, -PX:] = strip if shift < 0 else cur[:, -PX:]
            frames.append(cur)
        return lc.write_frames(frames, Path(output_dir) / f"{name}.mp4", 16)


def rollout(tmp_path, actions, task="GC001", **kw):
    base = FakeModel()
    eng = lc.LoopClosureEngine(base, **kw)
    img = tmp_path / task / "first.png"
    img.parent.mkdir(parents=True)
    Image.fromarray(scene()).save(img)
    cur, video = str(img), []
    for i, act in enumerate(actions, 1):
        out = tmp_path / task / "chunks" / f"chunk_{i:02d}"
        frames = lc.read_frames(eng.generate(cur, "p", f"{act}-{N}", out, f"{task}_chunk_{i:02d}", N))
        video.extend(frames if not video else frames[1:])
        nxt = tmp_path / task / f"last_{i}.png"
        Image.fromarray(frames[-1]).save(nxt)
        cur = str(nxt)
    return base, eng, video


def diff(a, b):
    return float(np.abs(a.astype(int) - b.astype(int)).mean())


def test_turn_out_and_back_lands_on_the_first_frame(tmp_path):
    base, eng, video = rollout(tmp_path, ["j", "j", "l", "l"])
    assert eng.closures == 1 and diff(video[0], video[-1]) < 10
    assert base.calls[-1] == ("GC001_chunk_04_anchor", "j")          # one extra call, from the first image
    assert (tmp_path / "GC001" / "loop_close.json").is_file()


def test_without_the_wrapper_the_fake_model_does_not_return(tmp_path):
    _, eng, video = rollout(tmp_path, ["j", "j", "l", "l"], tasks="NEVER")
    assert eng.closures == 0 and diff(video[0], video[-1]) > 15


def test_off_for_out_of_sight_call_names_by_default(tmp_path):
    base, eng, _ = rollout(tmp_path, ["j", "j", "l", "l"], task="OE034")
    assert eng.closures == 0 and len(base.calls) == 4


def test_no_closure_while_still_away_or_after_one_chunk(tmp_path):
    _, eng, _ = rollout(tmp_path, ["j", "j", "l"])
    assert eng.closures == 0


def test_pose_rules():
    p = lc.Pose()
    for k in ("d", "w", "a", "s"):                      # rectangle walk at the starting heading
        p.step(k, 24)
    assert p.at_start() and not p.unknown
    q = lc.Pose()
    for k in ("j", "w", "l", "s"):                      # walked while turned, yaw rate unknown: never a guess
        q.step(k, 24)
    assert q.unknown and not q.at_start()
    r = lc.Pose(deg_per_frame=0.9375)                   # 16 blocks of 24 frames = 360 degrees
    for _ in range(16):
        r.step("l", 24)
    assert r.at_start()
    s = lc.Pose(deg_per_frame=0.9375)                   # same keys as q with the rate known: not the start
    for k in ("j", "w", "l", "s"):
        s.step(k, 24)
    assert not s.at_start()


def test_install_is_off_unless_asked(monkeypatch):
    class RA:
        SanaWMEngine = FakeModel
    assert lc.install(RA, environ={}) is False and RA.SanaWMEngine is FakeModel
    assert lc.install(RA, environ={"LOOP_CLOSE": "1"}) is True and RA.SanaWMEngine is not FakeModel
